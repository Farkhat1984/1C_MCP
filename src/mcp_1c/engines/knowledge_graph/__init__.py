"""
Knowledge Graph Engine.

Builds and queries a metadata-level knowledge graph
from 1C:Enterprise configuration objects.
"""

from mcp_1c.engines.knowledge_graph.engine import KnowledgeGraphEngine
from mcp_1c.engines.knowledge_graph.storage import GraphStorage

__all__ = [
    "KnowledgeGraphEngine",
    "GraphStorage",
]
