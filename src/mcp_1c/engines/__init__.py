"""
Engines for MCP-1C.

Contains core processing engines for metadata, code, queries, etc.
"""

from mcp_1c.engines.metadata import MetadataEngine
from mcp_1c.engines.templates import TemplateEngine

__all__ = ["MetadataEngine", "TemplateEngine"]
