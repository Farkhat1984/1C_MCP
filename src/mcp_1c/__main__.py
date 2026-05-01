"""
Entry point for MCP-1C server.

Usage:
    python -m mcp_1c
    mcp-1c (if installed)
"""

import asyncio
import sys

from mcp_1c.server import create_server, run_server
from mcp_1c.utils.logger import get_logger, setup_logging


def main() -> int:
    """Main entry point."""
    setup_logging(level="INFO")
    logger = get_logger(__name__)

    logger.info("Starting MCP-1C server...")

    try:
        server, registry, prompt_registry = create_server()
        asyncio.run(run_server(server, registry, prompt_registry))
        return 0
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        return 0
    except Exception as e:
        logger.exception(f"Server error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
