"""SQLite-backed StorageBundle.

Wires the three existing SQLite classes (``MetadataCache``,
``VectorStorage``, ``GraphStorage``) into the unified
:class:`StorageBundle` interface — no schema or behaviour change yet,
just a typed entry point so the rest of the codebase can be migrated
to the protocol incrementally.

Layout under ``root``::

    <root>/
      cache.db               # MetadataCache
      embeddings.db          # VectorStorage (sqlite-vec)
      knowledge_graph.db     # GraphStorage
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_1c.engines.embeddings.storage import (
        VectorStorage as _VectorStorageImpl,
    )
    from mcp_1c.engines.knowledge_graph.storage import (
        GraphStorage as _GraphStorageImpl,
    )
    from mcp_1c.engines.metadata.cache import (
        MetadataCache as _MetadataCacheImpl,
    )


class SqliteStorageBundle:
    """Single-process SQLite storage for one workspace.

    Three databases sit side-by-side; we don't merge them because the
    sqlite-vec extension is loaded into one connection only. Multiple
    files keep that local and let us swap any one engine for a remote
    backend (e.g. pgvector for embeddings) without touching the others.
    """

    def __init__(
        self,
        *,
        workspace_id: str,
        root: Path,
        embedding_dimension: int = 4096,
    ) -> None:
        self._workspace_id = workspace_id
        self._root = root
        self._embedding_dimension = embedding_dimension
        self._metadata_impl: _MetadataCacheImpl | None = None
        self._vectors_impl: _VectorStorageImpl | None = None
        self._graph_impl: _GraphStorageImpl | None = None
        self._opened = False

    @property
    def workspace_id(self) -> str:
        return self._workspace_id

    @property
    def root(self) -> Path:
        return self._root

    @property
    def metadata(self):  # type: ignore[override]
        if self._metadata_impl is None:
            raise RuntimeError("StorageBundle not opened; call open() first")
        return self._metadata_impl

    @property
    def vectors(self):  # type: ignore[override]
        if self._vectors_impl is None:
            raise RuntimeError("StorageBundle not opened; call open() first")
        return self._vectors_impl

    @property
    def graph(self):  # type: ignore[override]
        if self._graph_impl is None:
            raise RuntimeError("StorageBundle not opened; call open() first")
        return self._graph_impl

    async def open(self) -> None:
        """Connect every storage. Idempotent."""
        if self._opened:
            return
        self._root.mkdir(parents=True, exist_ok=True)

        # Lazy imports keep the storage package free of forward-looking
        # circular deps with the engines that own these classes.
        from mcp_1c.engines.embeddings.storage import (
            VectorStorage as VectorStorageImpl,
        )
        from mcp_1c.engines.knowledge_graph.storage import (
            GraphStorage as GraphStorageImpl,
        )
        from mcp_1c.engines.metadata.cache import (
            MetadataCache as MetadataCacheImpl,
        )

        self._metadata_impl = MetadataCacheImpl(self._root / "cache.db")
        await self._metadata_impl.connect()

        self._vectors_impl = VectorStorageImpl(
            self._root / "embeddings.db",
            dimension=self._embedding_dimension,
        )
        # ``init_tables`` is the vector backend's "connect" — it both
        # opens the connection and creates schema.
        await self._vectors_impl.init_tables()

        # GraphStorage takes the db path through init_tables, not the
        # constructor — see engines/knowledge_graph/storage.py.
        self._graph_impl = GraphStorageImpl()
        await self._graph_impl.init_tables(self._root / "knowledge_graph.db")
        self._opened = True

    async def close(self) -> None:
        """Tear every storage down. Idempotent."""
        if not self._opened:
            return
        for store in (self._metadata_impl, self._vectors_impl, self._graph_impl):
            if store is not None:
                # Closing must be best-effort — Phase 5 will turn this
                # into a structured shutdown report.
                with contextlib.suppress(Exception):
                    await store.close()
        self._metadata_impl = None
        self._vectors_impl = None
        self._graph_impl = None
        self._opened = False


def sqlite_bundle_factory(
    *, embedding_dimension: int = 4096
) -> object:
    """Build a :class:`StorageBundleFactory` for the SQLite backend.

    Returned closure is the factory; call it with workspace metadata
    to get an unopened bundle. Phase 2 web mode does this once per
    workspace at admit-time.
    """

    def _factory(*, workspace_id: str, root: Path) -> SqliteStorageBundle:
        return SqliteStorageBundle(
            workspace_id=workspace_id,
            root=root,
            embedding_dimension=embedding_dimension,
        )

    return _factory


__all__ = ["SqliteStorageBundle", "sqlite_bundle_factory"]
