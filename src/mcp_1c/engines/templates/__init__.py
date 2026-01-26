"""
Templates Engine for code generation.

Provides template loading, validation, and code generation.
"""

from mcp_1c.engines.templates.engine import TemplateEngine
from mcp_1c.engines.templates.loader import TemplateLoader
from mcp_1c.engines.templates.generator import CodeGenerator
from mcp_1c.engines.templates.query_parser import QueryParser

# Singleton instance
_template_engine: TemplateEngine | None = None


def get_template_engine() -> TemplateEngine:
    """Get singleton TemplateEngine instance."""
    global _template_engine
    if _template_engine is None:
        _template_engine = TemplateEngine()
    return _template_engine


__all__ = [
    "TemplateEngine",
    "TemplateLoader",
    "CodeGenerator",
    "QueryParser",
    "get_template_engine",
]
