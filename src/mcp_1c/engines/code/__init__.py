"""
Code Engine.

Provides BSL code reading, parsing, and analysis.
Phase 2: Extended parsing and dependency graph building.
Phase 2.3: BSL Language Server integration.
"""

from mcp_1c.engines.code.bsl_ls import BslLanguageServer, BslLsConfig
from mcp_1c.engines.code.dependencies import DependencyGraphBuilder
from mcp_1c.engines.code.engine import CodeEngine
from mcp_1c.engines.code.parser import BslParser
from mcp_1c.engines.code.reader import BslReader

__all__ = [
    "CodeEngine",
    "BslParser",
    "BslReader",
    "DependencyGraphBuilder",
    "BslLanguageServer",
    "BslLsConfig",
]
