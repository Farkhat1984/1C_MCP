"""
Base prompt class for MCP Skills.

Implements the Template Method pattern for consistent prompt handling.
"""

from abc import ABC, abstractmethod
from typing import ClassVar

from mcp.types import Prompt, PromptArgument, PromptMessage, TextContent

from mcp_1c.utils.logger import get_logger


class BasePrompt(ABC):
    """
    Abstract base class for all MCP prompts (skills).

    Subclasses must implement:
        - name: Prompt name (e.g., "1c-query")
        - description: Human-readable description
        - arguments: List of prompt arguments
        - generate_messages(): Generate prompt messages
    """

    name: ClassVar[str]
    description: ClassVar[str]
    arguments: ClassVar[list[PromptArgument]]

    def __init__(self) -> None:
        """Initialize prompt with logger."""
        self.logger = get_logger(f"prompt.{self.name}")

    def get_prompt_definition(self) -> Prompt:
        """
        Get MCP Prompt definition.

        Returns:
            Prompt definition for MCP protocol
        """
        return Prompt(
            name=self.name,
            description=self.description,
            arguments=self.arguments,
        )

    async def get_messages(self, arguments: dict[str, str] | None = None) -> list[PromptMessage]:
        """
        Get prompt messages with provided arguments.

        Template method that:
        1. Validates arguments
        2. Generates messages
        3. Returns formatted messages

        Args:
            arguments: Prompt arguments

        Returns:
            List of prompt messages
        """
        self.logger.debug(f"Generating messages with arguments: {arguments}")

        # Validate required arguments
        validated = self.validate_arguments(arguments or {})

        # Generate messages
        messages = await self.generate_messages(validated)

        return messages

    def validate_arguments(self, arguments: dict[str, str]) -> dict[str, str]:
        """
        Validate prompt arguments.

        Args:
            arguments: Raw arguments

        Returns:
            Validated arguments

        Raises:
            ValueError: If required argument is missing
        """
        validated = {}

        for arg in self.arguments:
            value = arguments.get(arg.name)

            if arg.required and not value:
                raise ValueError(f"Required argument '{arg.name}' is missing")

            if value:
                validated[arg.name] = value

        return validated

    @abstractmethod
    async def generate_messages(
        self, arguments: dict[str, str]
    ) -> list[PromptMessage]:
        """
        Generate prompt messages.

        Must be implemented by subclasses.

        Args:
            arguments: Validated arguments

        Returns:
            List of prompt messages
        """
        raise NotImplementedError

    def create_user_message(self, content: str) -> PromptMessage:
        """
        Create a user message.

        Args:
            content: Message content

        Returns:
            PromptMessage with user role
        """
        return PromptMessage(
            role="user",
            content=TextContent(type="text", text=content),
        )

    def create_assistant_message(self, content: str) -> PromptMessage:
        """
        Create an assistant message.

        Args:
            content: Message content

        Returns:
            PromptMessage with assistant role
        """
        return PromptMessage(
            role="assistant",
            content=TextContent(type="text", text=content),
        )
