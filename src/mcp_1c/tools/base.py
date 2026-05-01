"""
Base tool class and interfaces.

Implements the Template Method and Strategy patterns for tools.
"""

import json
import os
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any, ClassVar

from mcp.types import Tool
from pydantic import BaseModel, ConfigDict

from mcp_1c.domain.metadata import MetadataType
from mcp_1c.utils.logger import get_logger
from mcp_1c.utils.observability import record_tool_call, tool_span


class _RateLimiter:
    """Simple token bucket rate limiter.

    Tracks call timestamps within a sliding window and rejects
    calls that exceed the configured maximum.
    """

    def __init__(self, max_calls: int = 100, period: float = 60.0) -> None:
        self._max_calls = max_calls
        self._period = period
        self._calls: list[float] = []

    def allow(self) -> bool:
        """Check if a call is allowed under the rate limit."""
        now = time.monotonic()
        # Remove expired entries
        cutoff = now - self._period
        self._calls = [t for t in self._calls if t > cutoff]
        if len(self._calls) >= self._max_calls:
            return False
        self._calls.append(now)
        return True


class _ToolMetrics:
    """Simple in-memory tool metrics collector."""

    def __init__(self) -> None:
        self._calls: dict[str, int] = defaultdict(int)
        self._errors: dict[str, int] = defaultdict(int)
        self._total_time: dict[str, float] = defaultdict(float)

    def record(self, tool_name: str, duration: float, error: bool = False) -> None:
        """Record a tool invocation.

        Args:
            tool_name: Name of the tool
            duration: Execution duration in seconds
            error: Whether the call resulted in an error
        """
        self._calls[tool_name] += 1
        self._total_time[tool_name] += duration
        if error:
            self._errors[tool_name] += 1

    def get_stats(self) -> dict[str, dict[str, float | int]]:
        """Get aggregated stats for all tools.

        Returns:
            Mapping of tool name to stats dict with calls, errors,
            avg_time_ms, and total_time_ms.
        """
        return {
            name: {
                "calls": self._calls[name],
                "errors": self._errors.get(name, 0),
                "avg_time_ms": round(
                    (self._total_time[name] / self._calls[name] * 1000)
                    if self._calls[name] > 0
                    else 0,
                    2,
                ),
                "total_time_ms": round(self._total_time[name] * 1000, 2),
            }
            for name in self._calls
        }


# Module-level rate limiter: disabled by default, set MCP_RATE_LIMIT > 0 to enable
_RATE_LIMIT = int(os.environ.get("MCP_RATE_LIMIT", "0"))
_rate_limiter: _RateLimiter | None = (
    _RateLimiter(max_calls=_RATE_LIMIT) if _RATE_LIMIT > 0 else None
)

# Module-level metrics collector
tool_metrics = _ToolMetrics()


# Audit sink — set via ``set_audit_writer`` from web/server bootstrap.
# Module-level mutable so a freshly imported BaseTool sees whatever the
# caller configured. Stays at ``NullAuditWriter`` for stdio/CLI mode
# unless explicitly overridden — that's the no-audit default and is
# fine for single-tenant local use.
_audit_writer: Any = None


def set_audit_writer(writer: Any) -> None:
    """Bind the audit writer used by every tool's ``run`` method.

    Called from web bootstrap (or tests) to install a real
    :class:`SqliteAuditWriter` / :class:`PostgresAuditWriter` (Phase 2).
    Pass ``None`` to disable auditing.
    """
    global _audit_writer
    _audit_writer = writer


def get_audit_writer() -> Any:
    return _audit_writer


class ToolError(Exception):
    """Standard tool error with error code."""

    def __init__(self, message: str, code: str = "UNKNOWN") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def parse_metadata_type(type_str: str) -> MetadataType:
    """Parse metadata type from a tool argument and surface it as a ToolError.

    Thin adapter over :meth:`MetadataType.parse` — domain validation lives
    in ``domain/metadata.py``; this layer only translates ValueError into
    the tool-level ``ToolError`` so MCP handlers return a structured
    error code instead of an unhandled exception.
    """
    try:
        return MetadataType.parse(type_str)
    except ValueError as exc:
        raise ToolError(str(exc), code="INVALID_TYPE") from exc


class ToolInput(BaseModel):
    """Base class for tool input validation."""

    model_config = ConfigDict(extra="forbid")


class ToolResult(BaseModel):
    """Result of tool execution."""

    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: Any = None
    error: str | None = None


class BaseTool(ABC):
    """
    Abstract base class for all MCP tools.

    Implements Template Method pattern for consistent tool execution.
    Subclasses must implement:
        - name: Tool name
        - description: Tool description
        - input_schema: JSON schema for input validation
        - execute(): Actual tool logic
    """

    name: ClassVar[str]
    description: ClassVar[str]
    input_schema: ClassVar[dict[str, Any]]
    # Required scope for this tool. ``None`` means "no scope check"
    # — used by tools that don't yet have a scope assigned and by the
    # legacy single-tenant CLI path. ``WorkspaceToolRegistry`` (Phase 2)
    # populates this from ``auth.scopes.default_tool_scopes()`` at
    # registration time.
    required_scope: ClassVar[Any] = None

    def __init__(self) -> None:
        """Initialize tool with logger."""
        self.logger = get_logger(f"tool.{self.name}")

    def get_tool_definition(self) -> Tool:
        """
        Get MCP Tool definition.

        Returns:
            Tool definition for MCP protocol
        """
        # Support both input_schema attribute and get_input_schema() method
        if hasattr(self, "get_input_schema") and callable(self.get_input_schema):
            schema = self.get_input_schema()
        else:
            schema = self.input_schema
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema=schema,
        )

    async def run(self, arguments: dict[str, Any]) -> str:
        """
        Execute tool with validation, rate limiting, metrics, and error handling.

        Template method that:
        1. Checks rate limit
        2. Validates input
        3. Executes tool logic
        4. Records metrics
        5. Formats output

        Args:
            arguments: Tool arguments

        Returns:
            Formatted result string
        """
        if _rate_limiter and not _rate_limiter.allow():
            return self.format_output(
                {"error": "Rate limit exceeded, try again later", "error_code": "RATE_LIMITED"}
            )

        self.logger.debug(f"Running with arguments: {arguments}")

        start = time.monotonic()
        error_occurred = False
        error_code: str | None = None
        # ``tool_span`` is cheap (a no-op context manager) when OTel is
        # disabled, so wrapping the whole body is free in the default
        # install. When enabled, the span captures everything from
        # scope check through execute() — that's the surface ops cares
        # about.
        with tool_span(self.name):
            try:
                # Authorization: when an identity is bound (web mode with
                # JWT) and this tool declares a required scope, enforce it.
                # Stdio/CLI runs with no bound identity and falls through —
                # the legacy permissive path stays intact for now. Phase 2
                # web wires the verifier and binds the ``current_identity``
                # ContextVar before dispatching the tool call.
                self._check_scope()

                # Validate required parameters from schema
                schema = (
                    self.get_input_schema()
                    if hasattr(self, "get_input_schema") and callable(self.get_input_schema)
                    else getattr(self, "input_schema", {})
                )
                for field in schema.get("required", []):
                    if field not in arguments or arguments[field] is None:
                        raise ToolError(
                            f"Required parameter missing: {field}",
                            code="MISSING_PARAM",
                        )

                # Validate input
                validated = self.validate_input(arguments)

                # Execute tool logic
                result = await self.execute(validated)

                # Format and return
                return self.format_output(result)
            except ToolError as e:
                error_occurred = True
                error_code = e.code
                return self.format_output({"error": e.message, "error_code": e.code})
            finally:
                duration = time.monotonic() - start
                tool_metrics.record(self.name, duration, error_occurred)
                # Prometheus counter/histogram. No-op when prom isn't on
                # — this is the second instrumentation pass per the
                # observability skeleton, kept side-by-side with the
                # in-memory counter rather than replacing it so the
                # JSON ``/metrics`` fallback keeps working.
                record_tool_call(
                    self.name,
                    latency_ms=duration * 1000,
                    status="error" if error_occurred else "ok",
                    error_code=error_code,
                )
                self.logger.debug(f"{self.name} completed in {duration * 1000:.1f}ms")
                # Audit-log the call. Done in ``finally`` so denials and
                # crashes get a row too — the whole point of audit is to
                # see what was attempted, not just what succeeded.
                await self._record_audit(
                    arguments,
                    duration_ms=duration * 1000,
                    error_occurred=error_occurred,
                    error_code=error_code,
                )

    async def _record_audit(
        self,
        arguments: dict[str, Any],
        *,
        duration_ms: float,
        error_occurred: bool,
        error_code: str | None,
    ) -> None:
        """Append one row to the audit log.

        Best-effort: a failing audit writer never breaks the tool
        call. Auth identity is read from the same ContextVar the
        scope check uses; when no identity is bound (stdio, dev),
        ``user_sub`` falls back to ``"anonymous"``.

        Imported lazily for the same reason as ``_check_scope``: tests
        instantiating tools directly shouldn't pay the auth import
        cost. Returns immediately when no writer is configured —
        which is the normal stdio/CLI case.
        """
        writer = get_audit_writer()
        if writer is None:
            return
        try:
            from mcp_1c.auth.context import current_identity
            from mcp_1c.utils.audit import AuditEvent, hash_arguments

            identity = current_identity.get()
            event = AuditEvent(
                user_sub=identity.sub if identity is not None else "anonymous",
                tool=self.name,
                args_hash=hash_arguments(arguments),
                status="error" if error_occurred else "ok",
                latency_ms=round(duration_ms, 2),
                error_code=error_code,
            )
            await writer.record(event)
        except Exception as exc:
            self.logger.debug(f"Audit write failed for {self.name}: {exc}")

    def _check_scope(self) -> None:
        """Reject the call when the bound identity lacks ``required_scope``.

        ``required_scope=None`` → no check (legacy/stdio path).
        ``current_identity=None`` → no check (no caller identity bound;
        single-tenant mode). Both are deliberately permissive: scope
        enforcement only kicks in when both sides have opted in.

        Imported lazily so the auth package isn't a hard runtime
        dependency for tools that don't care about it (some test code
        instantiates BaseTool subclasses directly).
        """
        required = self.required_scope
        if required is None:
            return
        from mcp_1c.auth.context import current_identity

        identity = current_identity.get()
        if identity is None:
            return
        if not identity.has(required):
            raise ToolError(
                f"Tool {self.name!r} requires scope {required.value!r} "
                f"but caller has {sorted(s.value for s in identity.scopes)}",
                code="FORBIDDEN",
            )

    def validate_input(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Validate input arguments.

        Override for custom validation.

        Args:
            arguments: Raw arguments

        Returns:
            Validated arguments

        Raises:
            ValueError: If validation fails
        """
        return arguments

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> Any:
        """
        Execute the tool logic.

        Must be implemented by subclasses.

        Args:
            arguments: Validated arguments

        Returns:
            Execution result
        """
        raise NotImplementedError

    def format_output(self, result: Any) -> str:
        """
        Format execution result.

        Override for custom formatting.

        Args:
            result: Execution result

        Returns:
            Formatted string
        """
        if isinstance(result, str):
            return result
        if isinstance(result, BaseModel):
            return result.model_dump_json(indent=2)
        if isinstance(result, (dict, list)):
            return json.dumps(result, indent=2, ensure_ascii=False, default=str)
        return str(result)
