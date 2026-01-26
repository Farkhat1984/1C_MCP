"""
Prompt registry for managing MCP prompts (skills).

Implements Registry pattern for prompt discovery and invocation.
"""

from mcp.types import Prompt, PromptMessage

from mcp_1c.prompts.base import BasePrompt
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


class PromptRegistry:
    """
    Registry for MCP prompts (skills).

    Provides prompt registration, discovery, and message generation.
    """

    def __init__(self) -> None:
        """Initialize registry and register all prompts."""
        self._prompts: dict[str, BasePrompt] = {}
        self._register_all_prompts()

    def _register_all_prompts(self) -> None:
        """Register all available prompts."""
        # Import prompts here to avoid circular imports
        from mcp_1c.prompts.skills import (
            QuerySkill,
            MetadataSkill,
            HandlerSkill,
            PrintSkill,
            UsagesSkill,
            ValidateSkill,
            DepsSkill,
            MovementSkill,
            FormatSkill,
            ExplainSkill,
        )
        from mcp_1c.prompts.agents import (
            ExploreAgent,
            ImplementAgent,
            DebugAgent,
            ConfigureAgent,
        )

        # Register all skills
        self.register(QuerySkill())
        self.register(MetadataSkill())
        self.register(HandlerSkill())
        self.register(PrintSkill())
        self.register(UsagesSkill())
        self.register(ValidateSkill())
        self.register(DepsSkill())
        self.register(MovementSkill())
        self.register(FormatSkill())
        self.register(ExplainSkill())

        # Register all agents
        self.register(ExploreAgent())
        self.register(ImplementAgent())
        self.register(DebugAgent())
        self.register(ConfigureAgent())

        logger.info(f"Registered {len(self._prompts)} prompts")

    def register(self, prompt: BasePrompt) -> None:
        """
        Register a prompt.

        Args:
            prompt: Prompt instance to register
        """
        if prompt.name in self._prompts:
            logger.warning(f"Prompt '{prompt.name}' already registered, overwriting")
        self._prompts[prompt.name] = prompt
        logger.debug(f"Registered prompt: {prompt.name}")

    def get(self, name: str) -> BasePrompt | None:
        """
        Get prompt by name.

        Args:
            name: Prompt name

        Returns:
            Prompt instance or None
        """
        return self._prompts.get(name)

    def list_prompts(self) -> list[Prompt]:
        """
        List all registered prompts.

        Returns:
            List of Prompt definitions
        """
        return [prompt.get_prompt_definition() for prompt in self._prompts.values()]

    async def get_prompt_messages(
        self, name: str, arguments: dict[str, str] | None = None
    ) -> list[PromptMessage]:
        """
        Get messages for a prompt.

        Args:
            name: Prompt name
            arguments: Prompt arguments

        Returns:
            List of prompt messages

        Raises:
            ValueError: If prompt not found
        """
        prompt = self.get(name)
        if prompt is None:
            raise ValueError(f"Unknown prompt: {name}")

        return await prompt.get_messages(arguments)
