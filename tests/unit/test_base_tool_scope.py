"""BaseTool scope-check integration.

Verifies the contract: scope enforcement is opt-in on both sides
(``required_scope`` and bound identity must both be set), and when it
fires, the call is rejected with a structured ToolError that
``BaseTool.run`` translates into a FORBIDDEN error response.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

import pytest

from mcp_1c.auth import AuthIdentity, Scope, use_identity
from mcp_1c.tools.base import BaseTool


class _RecordingTool(BaseTool):
    """Stub tool that records whether ``execute`` actually ran."""

    name: ClassVar[str] = "recording-tool"
    description: ClassVar[str] = "test"
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def execute(self, arguments: dict[str, Any]) -> Any:  # noqa: ARG002
        self.calls += 1
        return {"ok": True}


@pytest.mark.asyncio
async def test_no_required_scope_means_no_check_runs() -> None:
    """Default tools (no required_scope) work for any identity."""
    tool = _RecordingTool()
    identity = AuthIdentity(sub="anyone", scopes=frozenset())
    with use_identity(identity):
        result = await tool.run({})
    assert tool.calls == 1
    assert "ok" in result


@pytest.mark.asyncio
async def test_required_scope_without_identity_is_permissive() -> None:
    """Stdio / single-tenant: no identity bound, even scoped tool runs."""
    class ScopedTool(_RecordingTool):
        required_scope: ClassVar[Any] = Scope.ADMIN

    tool = ScopedTool()
    # No use_identity wrapper → ContextVar is None.
    result = await tool.run({})
    assert tool.calls == 1
    assert "ok" in result


@pytest.mark.asyncio
async def test_scope_enforced_when_both_sides_opt_in() -> None:
    """Identity bound + tool has required_scope → real check happens."""
    class AdminOnly(_RecordingTool):
        required_scope: ClassVar[Any] = Scope.ADMIN

    tool = AdminOnly()
    insufficient = AuthIdentity(
        sub="dev", scopes=frozenset({Scope.METADATA_READ})
    )
    with use_identity(insufficient):
        result = await tool.run({})
    assert tool.calls == 0  # execute was never reached
    parsed = json.loads(result)
    assert parsed["error_code"] == "FORBIDDEN"
    assert "admin" in parsed["error"]


@pytest.mark.asyncio
async def test_scope_allows_when_identity_has_required() -> None:
    class AdminOnly(_RecordingTool):
        required_scope: ClassVar[Any] = Scope.ADMIN

    tool = AdminOnly()
    sufficient = AuthIdentity(
        sub="root", scopes=frozenset({Scope.ADMIN, Scope.METADATA_READ})
    )
    with use_identity(sufficient):
        result = await tool.run({})
    assert tool.calls == 1
    assert "ok" in result


@pytest.mark.asyncio
async def test_use_identity_context_resets_after_block() -> None:
    """ContextVar.reset must restore the previous (None) state."""
    from mcp_1c.auth.context import current_identity

    assert current_identity.get() is None
    with use_identity(
        AuthIdentity(sub="x", scopes=frozenset({Scope.ADMIN}))
    ):
        assert current_identity.get() is not None
    assert current_identity.get() is None


@pytest.mark.asyncio
async def test_metrics_records_forbidden_as_error() -> None:
    """A scope rejection must show up in tool_metrics so ops can spot
    misconfigured clients."""
    from mcp_1c.tools.base import tool_metrics

    class AdminOnly(_RecordingTool):
        name: ClassVar[str] = "admin-only-metric-test"
        required_scope: ClassVar[Any] = Scope.ADMIN

    tool = AdminOnly()
    insufficient = AuthIdentity(sub="dev", scopes=frozenset())
    with use_identity(insufficient):
        await tool.run({})
    stats = tool_metrics.get_stats().get("admin-only-metric-test", {})
    assert stats.get("errors", 0) >= 1
