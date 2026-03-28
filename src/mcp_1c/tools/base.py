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

from pydantic import BaseModel, ConfigDict
from mcp.types import Tool

from mcp_1c.domain.metadata import MetadataType
from mcp_1c.utils.logger import get_logger


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


class ToolError(Exception):
    """Standard tool error with error code."""

    def __init__(self, message: str, code: str = "UNKNOWN") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def parse_metadata_type(type_str: str) -> MetadataType:
    """Parse metadata type from string (English or Russian).

    Args:
        type_str: Metadata type string

    Returns:
        Parsed MetadataType

    Raises:
        ToolError: If type is unknown
    """
    try:
        return MetadataType(type_str)
    except ValueError:
        mt = MetadataType.from_russian(type_str)
        if mt is None:
            raise ToolError(f"Unknown metadata type: {type_str}", code="INVALID_TYPE")
        return mt


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
        try:
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
            return self.format_output({"error": e.message, "error_code": e.code})
        finally:
            duration = time.monotonic() - start
            tool_metrics.record(self.name, duration, error_occurred)
            self.logger.debug(f"{self.name} completed in {duration * 1000:.1f}ms")

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
