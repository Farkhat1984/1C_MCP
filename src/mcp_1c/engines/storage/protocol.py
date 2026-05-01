"""Storage protocols — the contract every backend must satisfy.

These are deliberately *narrow*: each protocol exposes only what
engines actually call today. Adding a method here means adding it to
every implementation, so we keep the surface tight. When Phase 2
brings up PostgreSQL, the asyncpg implementation will only need to
honour these signatures — engines don't need to change.

Why ``Protocol`` and not ``ABC``? The existing classes
(``MetadataCache``, ``VectorStorage``, ``GraphStorage``) already match
this shape; structural typing avoids retrofit churn (no need to add
explicit ``MetadataCache(MetadataStorage)`` inheritance) while still
giving us a single place for type-checkers to verify the contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from mcp_1c.domain.embedding import EmbeddingDocument, EmbeddingStats, SearchResult
from mcp_1c.domain.graph import KnowledgeGraph
from mcp_1c.domain.metadata import MetadataObject, MetadataType, Subsystem


@runtime_checkable
class MetadataStorage(Protocol):
    """Persistent index of 1C configuration metadata objects.

    Backends may add features (TTL eviction, FTS5 search, etc.) but
    must implement the methods listed here. Concurrency is the
    backend's problem — the contract assumes coroutine-safety per
    instance.
    """

    async def connect(self) -> None: ...
    async def close(self) -> None: ...

    async def save_object(self, obj: MetadataObject) -> int: ...
    async def get_object(
        self, metadata_type: MetadataType, name: str
    ) -> MetadataObject | None: ...
    async def get_objects_by_type(
        self, metadata_type: MetadataType
    ) -> list[MetadataObject]: ...
    async def search_objects(
        self,
        query: str,
        metadata_type: MetadataType | None = None,
        limit: int = 50,
    ) -> list[MetadataObject]: ...

    async def get_hash(
        self, metadata_type: MetadataType, name: str
    ) -> str | None: ...
    async def save_subsystem(self, subsystem: Subsystem) -> None: ...
    async def get_subsystems(
        self, parent: str | None = None
    ) -> list[Subsystem]: ...

    async def get_stats(self) -> dict[str, int]: ...
    async def clear(self) -> None: ...


@runtime_checkable
class VectorStorage(Protocol):
    """Embedding store with KNN search over a vector column.

    Today this is sqlite-vec; tomorrow it'll be pgvector. Both honour
    the same signatures so the embedding engine is backend-agnostic.
    """

    async def init_tables(self) -> None: ...
    async def close(self) -> None: ...

    async def save_documents(self, documents: list[EmbeddingDocument]) -> int: ...
    async def search(
        self,
        query_vector: list[float],
        doc_type: str | None = None,
        object_type: str | None = None,
        module_type: str | None = None,
        limit: int = 20,
    ) -> list[SearchResult]: ...

    async def get_document(self, doc_id: str) -> EmbeddingDocument | None: ...
    async def get_existing_ids(
        self, id_prefixes: list[str] | None = None
    ) -> set[str]: ...
    async def delete_by_prefix(self, prefix: str) -> int: ...

    async def get_stats(self) -> EmbeddingStats: ...


@runtime_checkable
class GraphStorage(Protocol):
    """Persistence for the whole knowledge graph as one document.

    The current implementation serialises the entire ``KnowledgeGraph``
    domain model in/out — query operations live on the in-memory graph,
    not on storage. Phase 2 will keep this contract for SQLite and add
    a node/edge-granular PG variant alongside; engines pick whichever
    suits scale, mediated by ``KnowledgeGraphEngine``.
    """

    async def init_tables(self, db_path: Path) -> None: ...
    async def close(self) -> None: ...

    async def save_graph(self, graph: KnowledgeGraph) -> None: ...
    async def load_graph(self) -> KnowledgeGraph | None: ...
    async def clear(self) -> None: ...


# ---------------------------------------------------------------------------
# Bundle: every workspace owns exactly one of each storage.
# ---------------------------------------------------------------------------


class StorageBundle(Protocol):
    """The trio of storages a Workspace owns.

    Implementations either bind concrete backends directly
    (``SqliteStorageBundle``) or wrap a connection pool
    (``PostgresStorageBundle`` in Phase 2). The bundle's lifecycle is
    tied to the workspace: ``open()`` on workspace start,
    ``close()`` on shutdown.
    """

    metadata: MetadataStorage
    vectors: VectorStorage
    graph: GraphStorage

    async def open(self) -> None: ...
    async def close(self) -> None: ...


class StorageBundleFactory(Protocol):
    """Factory for ``StorageBundle`` instances bound to a workspace path.

    Phase 2 web mode picks the factory at app start (SQLite for dev,
    PostgreSQL for prod) and injects it into the WorkspaceRegistry.
    """

    def __call__(
        self, *, workspace_id: str, root: Path
    ) -> StorageBundle: ...


__all__ = [
    "GraphStorage",
    "MetadataStorage",
    "StorageBundle",
    "StorageBundleFactory",
    "VectorStorage",
]
