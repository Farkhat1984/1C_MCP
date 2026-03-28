"""
MCP Server implementation.

Provides the core MCP server with tool registration and handling.
"""

import signal
from typing import Any, Sequence

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, Prompt, GetPromptResult

from mcp_1c.config import get_config
from mcp_1c.tools.registry import ToolRegistry
from mcp_1c.prompts.registry import PromptRegistry
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


def create_server() -> tuple[Server, ToolRegistry, PromptRegistry]:
    """
    Create and configure MCP server.

    Returns:
        Tuple of configured MCP Server instance, ToolRegistry, and PromptRegistry
    """
    config = get_config()
    server = Server(config.server.name)

    # Initialize registries
    registry = ToolRegistry()
    prompt_registry = PromptRegistry()

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List all available tools."""
        return registry.list_tools()

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> Sequence[TextContent]:
        """
        Handle tool invocation.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        logger.debug(f"Calling tool: {name} with args: {arguments}")

        try:
            result = await registry.call_tool(name, arguments)
            return [TextContent(type="text", text=result)]
        except ValueError as e:
            error_msg = f"Tool error: {e}"
            logger.error(error_msg)
            return [TextContent(type="text", text=error_msg)]
        except Exception as e:
            error_msg = f"Unexpected error in tool {name}: {e}"
            logger.exception(error_msg)
            return [TextContent(type="text", text=error_msg)]

    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        """List all available prompts (skills)."""
        return prompt_registry.list_prompts()

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict[str, str] | None = None) -> GetPromptResult:
        """
        Get prompt messages.

        Args:
            name: Prompt name
            arguments: Prompt arguments

        Returns:
            GetPromptResult with messages
        """
        logger.debug(f"Getting prompt: {name} with args: {arguments}")

        try:
            messages = await prompt_registry.get_prompt_messages(name, arguments)
            prompt = prompt_registry.get(name)
            return GetPromptResult(
                description=prompt.description if prompt else None,
                messages=messages,
            )
        except ValueError as e:
            logger.error(f"Prompt error: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error in prompt {name}: {e}")
            raise

    logger.info(
        f"Server '{config.server.name}' created with "
        f"{len(registry.list_tools())} tools and {len(prompt_registry.list_prompts())} prompts"
    )
    return server, registry, prompt_registry


async def shutdown_engines() -> None:
    """Graceful shutdown: close metadata engine connections and file watcher."""
    from mcp_1c.engines.metadata import MetadataEngine

    logger.info("Shutting down MCP server engines...")
    try:
        engine = MetadataEngine.get_instance()
        if engine.is_initialized:
            await engine.shutdown()
    except Exception as e:
        logger.warning(f"Error closing metadata engine: {e}")
    logger.info("Shutdown complete")


async def run_server(
    server: Server,
    registry: ToolRegistry | None = None,
    prompt_registry: PromptRegistry | None = None,
) -> None:
    """
    Run the MCP server with stdio transport.

    Args:
        server: Configured server instance
        registry: Optional ToolRegistry for initialization
        prompt_registry: Optional PromptRegistry (unused, for API consistency)
    """
    import asyncio

    logger.info("Starting stdio transport...")

    # Initialize async components
    if registry:
        await registry.initialize()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda s=sig: asyncio.create_task(_handle_signal(s)),
        )

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    finally:
        await shutdown_engines()


async def _handle_signal(sig: signal.Signals) -> None:
    """Handle OS signal for graceful shutdown.

    Args:
        sig: The signal received
    """
    logger.info(f"Received signal {sig.name}, initiating shutdown...")
    await shutdown_engines()
