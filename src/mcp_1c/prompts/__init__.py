"""
Prompts (Skills) module for MCP-1C.

Provides predefined prompts for common 1C development tasks.
"""

from mcp_1c.prompts.base import BasePrompt
from mcp_1c.prompts.registry import PromptRegistry

__all__ = ["BasePrompt", "PromptRegistry"]
