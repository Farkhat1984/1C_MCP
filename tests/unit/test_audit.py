"""Audit log skeleton tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from mcp_1c.utils.audit import (
    AuditEvent,
    NullAuditWriter,
    SqliteAuditWriter,
    hash_arguments,
)


def test_hash_arguments_is_order_independent() -> None:
    assert hash_arguments({"a": 1, "b": 2}) == hash_arguments({"b": 2, "a": 1})


def test_hash_arguments_distinguishes_values() -> None:
    assert hash_arguments({"a": 1}) != hash_arguments({"a": 2})


def test_hash_arguments_handles_unicode() -> None:
    h1 = hash_arguments({"тип": "Справочник", "имя": "Контрагенты"})
    h2 = hash_arguments({"имя": "Контрагенты", "тип": "Справочник"})
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_hash_arguments_handles_non_serializable_via_default() -> None:
    """Non-JSON-serializable values fall through ``default=str`` rather
    than crashing — the audit log should never break a tool call."""
    h = hash_arguments({"path": Path("/tmp/x")})
    assert len(h) == 64


@pytest.mark.asyncio
async def test_sqlite_writer_appends_and_persists(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    writer = SqliteAuditWriter(db)
    try:
        await writer.record(
            AuditEvent(
                workspace_id="ws-1",
                user_sub="alice",
                tool="metadata-search",
                args_hash="abc123",
                status="ok",
                latency_ms=12.5,
            )
        )
        await writer.record(
            AuditEvent(
                workspace_id="ws-1",
                user_sub="bob",
                tool="runtime-eval",
                args_hash="def456",
                status="denied",
                latency_ms=2.0,
                error_code="WRITE_DISABLED",
            )
        )
    finally:
        await writer.close()

    # Verify rows landed via a fresh connection — no shared state.
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT tool, status, error_code FROM audit_log ORDER BY id"
    ).fetchall()
    conn.close()

    assert rows == [("metadata-search", "ok", None), ("runtime-eval", "denied", "WRITE_DISABLED")]


@pytest.mark.asyncio
async def test_sqlite_writer_does_not_raise_on_failure(tmp_path: Path) -> None:
    """A broken sink must not crash the caller — Phase 4 will wire it
    around runtime tools, and a failing audit must never abort a request."""
    # Point at a directory we can't write to (file-as-dir).
    blocker = tmp_path / "blocker"
    blocker.write_bytes(b"not a directory")
    bad_path = blocker / "audit.db"

    writer = SqliteAuditWriter(bad_path)
    # Should silently swallow the OSError and log a warning.
    await writer.record(
        AuditEvent(tool="x", args_hash="h", status="ok")
    )
    await writer.close()


@pytest.mark.asyncio
async def test_null_writer_is_silent() -> None:
    writer = NullAuditWriter()
    await writer.record(AuditEvent(tool="x", args_hash="h", status="ok"))
    await writer.close()


def test_audit_event_default_timestamp_is_utc() -> None:
    ev = AuditEvent(tool="x", args_hash="h", status="ok")
    assert ev.ts.tzinfo is not None
    assert ev.ts.utcoffset().total_seconds() == 0
