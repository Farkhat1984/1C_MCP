"""
Base tool class and interfaces.

Implements the Template Method and Strategy patterns for tools.
"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict
from mcp.types import Tool

from mcp_1c.utils.logger import get_logger


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
        Execute tool with validation and error handling.

        Template method that:
        1. Validates input
        2. Executes tool logic
        3. Formats output

        Args:
            arguments: Tool arguments

        Returns:
            Formatted result string
        """
        self.logger.debug(f"Running with arguments: {arguments}")

        # Validate input
        validated = self.validate_input(arguments)

        # Execute tool logic
        result = await self.execute(validated)

        # Format and return
        return self.format_output(result)

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
            import json
            return json.dumps(result, indent=2, ensure_ascii=False, default=str)
        return str(result)
