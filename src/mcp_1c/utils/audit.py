"""Append-only audit log for security-sensitive tool calls.

Skeleton for Phase 4 closed-loop integration. Records who called what,
with which arguments and what status. Schema is intentionally narrow —
no result payloads, no PII; we hash the arguments instead of storing
them so the log itself doesn't become a target.

Backend is SQLite for now (single-process, single-workspace dev/team
deploys). Phase 2 will add a PostgreSQL implementation behind the same
``AuditWriter`` Protocol.

Use ``hash_arguments`` from this module to canonicalize tool args before
recording — JSON keys are sorted, ensuring identical calls produce
identical hashes regardless of dict iteration order.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


class AuditEvent(BaseModel):
    """One audited tool invocation.

    Stored exactly as written — there is no update path. ``args_hash``
    is deterministic over the canonical JSON of the arguments, so two
    identical calls produce identical hashes (useful for replay /
    deduplication analytics).
    """

    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    workspace_id: str = ""
    user_sub: str = ""  # JWT 'sub' claim or "anonymous"
    tool: str
    args_hash: str
    status: str  # "ok" | "error" | "denied"
    latency_ms: float = 0.0
    error_code: str | None = None


def hash_arguments(arguments: dict[str, Any]) -> str:
    """Canonical SHA-256 over tool arguments.

    Keys are sorted, non-ASCII preserved verbatim, separators stripped of
    whitespace so the bytes-on-disk are stable across Python versions
    and dict insertion order.
    """
    canonical = json.dumps(
        arguments,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AuditWriter(Protocol):
    """Sink for audit events. Implementations must be safe to call from
    any coroutine — concrete writers are responsible for their own
    serialization (lock, single-thread executor, etc.)."""

    async def record(self, event: AuditEvent) -> None: ...
    async def close(self) -> None: ...


class SqliteAuditWriter:
    """SQLite-backed audit writer.

    Append-only schema with monotonically-increasing ``id``. WAL mode so
    readers (e.g. an admin viewing recent calls) don't block writers.

    Connection is opened lazily on first ``record`` to keep test setup
    cheap, and is held open for the lifetime of the writer.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS audit_log (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        ts           TEXT    NOT NULL,
        workspace_id TEXT    NOT NULL DEFAULT '',
        user_sub     TEXT    NOT NULL DEFAULT '',
        tool         TEXT    NOT NULL,
        args_hash    TEXT    NOT NULL,
        status       TEXT    NOT NULL,
        latency_ms   REAL    NOT NULL DEFAULT 0,
        error_code   TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
    CREATE INDEX IF NOT EXISTS idx_audit_tool_ts ON audit_log(tool, ts);
    CREATE INDEX IF NOT EXISTS idx_audit_workspace_ts ON audit_log(workspace_id, ts);
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._db_path), isolation_level=None)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(self._SCHEMA)
            self._conn = conn
        return self._conn

    async def record(self, event: AuditEvent) -> None:
        """Append one event. Failure is logged, not raised — the audit
        sink must never break the caller."""
        try:
            conn = self._connect()
            conn.execute(
                "INSERT INTO audit_log "
                "(ts, workspace_id, user_sub, tool, args_hash, status,"
                " latency_ms, error_code) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.ts.isoformat(),
                    event.workspace_id,
                    event.user_sub,
                    event.tool,
                    event.args_hash,
                    event.status,
                    event.latency_ms,
                    event.error_code,
                ),
            )
        except Exception as exc:
            logger.warning(f"Audit write failed for tool={event.tool!r}: {exc}")

    async def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None


class NullAuditWriter:
    """No-op writer for tests and dev environments where audit isn't
    configured. Has the same interface as :class:`SqliteAuditWriter`."""

    async def record(self, event: AuditEvent) -> None:  # noqa: ARG002
        return None

    async def close(self) -> None:
        return None


__all__ = [
    "AuditEvent",
    "AuditWriter",
    "SqliteAuditWriter",
    "NullAuditWriter",
    "hash_arguments",
]
