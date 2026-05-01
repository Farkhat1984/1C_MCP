"""Storage protocols and backends.

Three protocols define the contract every storage backend must satisfy:

- :class:`MetadataStorage` — indexed metadata objects + subsystems
  (today implemented by :class:`mcp_1c.engines.metadata.cache.MetadataCache`).
- :class:`VectorStorage` — embedding documents with KNN search
  (today implemented by :class:`mcp_1c.engines.embeddings.storage.VectorStorage`).
- :class:`GraphStorage` — knowledge-graph nodes and edges
  (today implemented by :class:`mcp_1c.engines.knowledge_graph.storage.GraphStorage`).

Phase 2 will add a PostgreSQL backend (asyncpg + pgvector) behind the
same protocols. The Workspace abstraction (``engines/workspace.py``)
binds a single bundle of these three storages to one indexed
configuration, enabling multi-tenant deployments.
"""

from mcp_1c.engines.storage.protocol import (
    GraphStorage,
    MetadataStorage,
    StorageBundle,
    StorageBundleFactory,
    VectorStorage,
)

__all__ = [
    "GraphStorage",
    "MetadataStorage",
    "StorageBundle",
    "StorageBundleFactory",
    "VectorStorage",
]
