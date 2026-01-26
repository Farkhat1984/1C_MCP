"""
MCP-1C: Model Context Protocol Server for 1C:Enterprise Platform.

Provides tools for metadata analysis, code navigation, and generation
for 1C:Enterprise configurations.
"""

__version__ = "0.1.0"
__author__ = "Developer"

from mcp_1c.server import create_server

__all__ = ["create_server", "__version__"]
