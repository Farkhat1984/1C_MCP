"""
Smart metadata-aware code generator engine.

Provides intelligent 1C code generation by reading real metadata
objects and producing syntactically correct queries, print forms,
and register movement code.
"""

from mcp_1c.engines.smart.generator import SmartGenerator

__all__ = ["SmartGenerator"]
