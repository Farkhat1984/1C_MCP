"""Audit-log integration in BaseTool.run.

The contract: every ``run`` call writes exactly one audit row when a
writer is bound. The row reflects what *happened* — denied calls and
ToolErrors get rows too. We don't audit pre-validation crashes
(rate limit, scope reject) intentionally — see the tests below for
the precise boundary.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from mcp_1c.auth import AuthIdentity, Scope, use_identity
from mcp_1c.tools.base import BaseTool, ToolError, set_audit_writer
from mcp_1c.utils.audit import AuditEvent


class _RecordingWriter:
    """In-memory audit sink for tests."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []
        self.crash_next: bool = False

    async def record(self, event: AuditEvent) -> None:
        if self.crash_next:
            raise RuntimeError("simulated audit failure")
        self.events.append(event)

    async def close(self) -> None:
        pass


class _OkTool(BaseTool):
    name: ClassVar[str] = "ok-tool"
    description: ClassVar[str] = ""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object", "properties": {}, "required": [],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:  # noqa: ARG002
        return {"ok": True}


class _FailingTool(BaseTool):
    name: ClassVar[str] = "failing-tool"
    description: ClassVar[str] = ""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object", "properties": {}, "required": [],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:  # noqa: ARG002
        raise ToolError("kaboom", code="OBJECT_NOT_FOUND")


@pytest.fixture(autouse=True)
def _clear_audit_writer() -> None:
    set_audit_writer(None)
    yield
    set_audit_writer(None)


@pytest.mark.asyncio
async def test_no_audit_writer_means_no_audit() -> None:
    """Stdio default path: writer is None, run() returns clean."""
    tool = _OkTool()
    result = await tool.run({})
    assert "ok" in result


@pytest.mark.asyncio
async def test_successful_call_emits_one_audit_row() -> None:
    writer = _RecordingWriter()
    set_audit_writer(writer)

    tool = _OkTool()
    await tool.run({"foo": "bar"})

    assert len(writer.events) == 1
    event = writer.events[0]
    assert event.tool == "ok-tool"
    assert event.status == "ok"
    assert event.error_code is None
    assert event.latency_ms >= 0
    assert event.user_sub == "anonymous"  # No identity bound.


@pytest.mark.asyncio
async def test_tool_error_records_status_error_with_code() -> None:
    writer = _RecordingWriter()
    set_audit_writer(writer)

    tool = _FailingTool()
    await tool.run({})

    assert len(writer.events) == 1
    event = writer.events[0]
    assert event.status == "error"
    assert event.error_code == "OBJECT_NOT_FOUND"


@pytest.mark.asyncio
async def test_audit_uses_identity_when_bound() -> None:
    writer = _RecordingWriter()
    set_audit_writer(writer)

    tool = _OkTool()
    identity = AuthIdentity(
        sub="alice@example.com", scopes=frozenset({Scope.METADATA_READ})
    )
    with use_identity(identity):
        await tool.run({})

    assert writer.events[0].user_sub == "alice@example.com"


@pytest.mark.asyncio
async def test_args_are_hashed_not_stored() -> None:
    """Audit log must not store raw args — they may carry secrets.

    We assert that the recorded ``args_hash`` is the SHA-256 of the
    canonical JSON, never the original dict; and that two identical
    calls produce identical hashes (replay analytics)."""
    from mcp_1c.utils.audit import hash_arguments

    writer = _RecordingWriter()
    set_audit_writer(writer)

    tool = _OkTool()
    await tool.run({"secret": "hunter2", "other": 1})
    await tool.run({"other": 1, "secret": "hunter2"})  # Reordered keys.

    expected = hash_arguments({"secret": "hunter2", "other": 1})
    assert writer.events[0].args_hash == expected
    assert writer.events[1].args_hash == expected  # Order-independent.


@pytest.mark.asyncio
async def test_audit_failure_does_not_break_tool() -> None:
    """A misbehaving audit sink must not destroy the tool's response."""
    writer = _RecordingWriter()
    writer.crash_next = True
    set_audit_writer(writer)

    tool = _OkTool()
    result = await tool.run({})
    assert "ok" in result  # Tool still succeeded.
    assert writer.events == []  # No row written; no exception bubbled.


@pytest.mark.asyncio
async def test_scope_denied_call_is_audited() -> None:
    """A FORBIDDEN denial counts as an attempt — must show up in audit."""
    class AdminOnly(_OkTool):
        name: ClassVar[str] = "admin-tool-audit-test"
        required_scope: ClassVar[Any] = Scope.ADMIN

    writer = _RecordingWriter()
    set_audit_writer(writer)

    tool = AdminOnly()
    insufficient = AuthIdentity(
        sub="dev", scopes=frozenset({Scope.METADATA_READ})
    )
    with use_identity(insufficient):
        await tool.run({})

    assert len(writer.events) == 1
    assert writer.events[0].status == "error"
    assert writer.events[0].error_code == "FORBIDDEN"
    assert writer.events[0].user_sub == "dev"
