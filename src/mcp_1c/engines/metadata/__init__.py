"""
Metadata Engine.

Provides XML parsing, indexing, caching, and file watching
for 1C:Enterprise configurations.
"""

from mcp_1c.engines.metadata.engine import MetadataEngine
from mcp_1c.engines.metadata.parser import XmlParser
from mcp_1c.engines.metadata.indexer import MetadataIndexer
from mcp_1c.engines.metadata.cache import MetadataCache

__all__ = [
    "MetadataEngine",
    "XmlParser",
    "MetadataIndexer",
    "MetadataCache",
]
