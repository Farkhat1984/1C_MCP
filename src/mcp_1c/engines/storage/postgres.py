"""PostgreSQL-backed StorageBundle — skeleton.

This module is intentionally a *skeleton*: the connection lifecycle and
schema are real, but the per-method query implementations raise
:class:`NotImplementedError`. SQLite handles the current scale (<100
workspaces); the PG backend exists so operators can validate the DSN
and schema today and fill in queries when the team actually needs to
push past the SQLite ceiling.

What's real
-----------
- ``open()`` / ``close()`` lifecycle on an ``asyncpg`` pool.
- A liveness ``SELECT 1`` at open time so a bad DSN fails loudly.
- Schema baseline lives in ``migrations/versions/0001_baseline.py`` —
  apply it with ``alembic upgrade head`` before opening the bundle.

What's a skeleton
-----------------
Every storage method (metadata save/get/search, vector save/search,
graph save/load, etc.) raises ``NotImplementedError`` with a message
containing "skeleton". When you fill these in, drop the skeleton
guards but keep the method signatures — they're locked to the
``MetadataStorage`` / ``VectorStorage`` / ``GraphStorage`` Protocols
in :mod:`mcp_1c.engines.storage.protocol`.

Why imports are guarded
-----------------------
``asyncpg`` and ``pgvector`` live in the optional ``[postgres]`` extra.
Importing this module without those dependencies installed should not
crash — only *opening* the bundle should. We guard at module top via
``importlib.util.find_spec`` and re-import lazily inside ``open()``.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp_1c.domain.embedding import EmbeddingDocument, EmbeddingStats, SearchResult
from mcp_1c.domain.graph import KnowledgeGraph
from mcp_1c.domain.metadata import MetadataObject, MetadataType, Subsystem
from mcp_1c.utils.logger import get_logger

if TYPE_CHECKING:  # pragma: no cover - type-only
    import asyncpg  # type: ignore[import-not-found]


logger = get_logger(__name__)


_SKELETON_MESSAGE = (
    "Postgres backend skeleton — fill in for production scale; "
    "SQLite covers current needs."
)

_HAS_ASYNCPG: bool = importlib.util.find_spec("asyncpg") is not None
_HAS_PGVECTOR: bool = importlib.util.find_spec("pgvector") is not None


def _require_asyncpg() -> None:
    """Raise a clear error if the optional Postgres deps are missing.

    Called at ``open()`` time only — module import must stay cheap so
    this file can be type-checked and imported in environments without
    the ``[postgres]`` extra installed.
    """

    if not _HAS_ASYNCPG:
        raise RuntimeError(
            "asyncpg is not installed. Install the optional postgres extra:\n"
            '    pip install -e ".[postgres]"'
        )
    if not _HAS_PGVECTOR:
        # pgvector's Python adapter is needed to bind ``vector`` columns
        # via asyncpg codecs. We accept a missing adapter at import-time
        # but reject it at open-time, same as asyncpg.
        raise RuntimeError(
            "pgvector is not installed. Install the optional postgres extra:\n"
            '    pip install -e ".[postgres]"'
        )


# ---------------------------------------------------------------------------
# Per-Protocol skeleton storages
# ---------------------------------------------------------------------------


class _PostgresMetadataStorage:
    """``MetadataStorage`` skeleton backed by an ``asyncpg`` pool.

    Schema lives in ``metadata_objects`` / ``subsystems`` (see baseline
    migration). All methods are stubs — they raise ``NotImplementedError``
    with a "skeleton" marker so future contributors don't mistake an
    unimplemented method for a bug.
    """

    def __init__(self, *, pool: asyncpg.Pool, workspace_id: str) -> None:
        self._pool = pool
        self._workspace_id = workspace_id

    async def connect(self) -> None:
        # The pool is created and validated by the parent bundle. The
        # per-storage ``connect`` is a no-op so engines that call it
        # directly (mirroring the SQLite contract) keep working.
        return None

    async def close(self) -> None:
        # Lifecycle is owned by the bundle's pool, not the storage.
        return None

    async def save_object(self, obj: MetadataObject) -> int:
        raise NotImplementedError(_SKELETON_MESSAGE)

    async def get_object(
        self, metadata_type: MetadataType, name: str
    ) -> MetadataObject | None:
        raise NotImplementedError(_SKELETON_MESSAGE)

    async def get_objects_by_type(
        self, metadata_type: MetadataType
    ) -> list[MetadataObject]:
        raise NotImplementedError(_SKELETON_MESSAGE)

    async def search_objects(
        self,
        query: str,
        metadata_type: MetadataType | None = None,
        limit: int = 50,
    ) -> list[MetadataObject]:
        raise NotImplementedError(_SKELETON_MESSAGE)

    async def get_hash(
        self, metadata_type: MetadataType, name: str
    ) -> str | None:
        raise NotImplementedError(_SKELETON_MESSAGE)

    async def save_subsystem(self, subsystem: Subsystem) -> None:
        raise NotImplementedError(_SKELETON_MESSAGE)

    async def get_subsystems(
        self, parent: str | None = None
    ) -> list[Subsystem]:
        raise NotImplementedError(_SKELETON_MESSAGE)

    async def get_stats(self) -> dict[str, int]:
        raise NotImplementedError(_SKELETON_MESSAGE)

    async def clear(self) -> None:
        raise NotImplementedError(_SKELETON_MESSAGE)


class _PostgresVectorStorage:
    """``VectorStorage`` skeleton backed by pgvector.

    The ``embedding_dimension`` is locked at table-create time in the
    Alembic migration; this storage just records what dimension the
    bundle was opened with so query implementations can sanity-check
    incoming vectors.
    """

    def __init__(
        self,
        *,
        pool: asyncpg.Pool,
        workspace_id: str,
        embedding_dimension: int,
    ) -> None:
        self._pool = pool
        self._workspace_id = workspace_id
        self._embedding_dimension = embedding_dimension

    async def init_tables(self) -> None:
        # Schema is owned by Alembic, not the runtime. Operators run
        # ``alembic upgrade head`` before starting the service.
        return None

    async def close(self) -> None:
        return None

    async def save_documents(self, documents: list[EmbeddingDocument]) -> int:
        raise NotImplementedError(_SKELETON_MESSAGE)

    async def search(
        self,
        query_vector: list[float],
        doc_type: str | None = None,
        object_type: str | None = None,
        module_type: str | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        raise NotImplementedError(_SKELETON_MESSAGE)

    async def get_document(self, doc_id: str) -> EmbeddingDocument | None:
        raise NotImplementedError(_SKELETON_MESSAGE)

    async def get_existing_ids(
        self, id_prefixes: list[str] | None = None
    ) -> set[str]:
        raise NotImplementedError(_SKELETON_MESSAGE)

    async def delete_by_prefix(self, prefix: str) -> int:
        raise NotImplementedError(_SKELETON_MESSAGE)

    async def get_stats(self) -> EmbeddingStats:
        raise NotImplementedError(_SKELETON_MESSAGE)


class _PostgresGraphStorage:
    """``GraphStorage`` skeleton.

    Today the SQLite implementation serialises the whole
    ``KnowledgeGraph`` document in/out. The PG schema (``graph_nodes`` /
    ``graph_edges``) keeps that contract while making node/edge-granular
    queries possible later — a real implementation will likely expose a
    second, granular API alongside the existing whole-graph one.
    """

    def __init__(self, *, pool: asyncpg.Pool, workspace_id: str) -> None:
        self._pool = pool
        self._workspace_id = workspace_id

    async def init_tables(self, db_path: Path) -> None:
        # ``db_path`` is meaningful for SQLite (per-file DB) but
        # irrelevant for PG. Accepted to match the protocol; logged for
        # diagnostic value only.
        logger.debug(
            "PostgresGraphStorage.init_tables called with db_path=%s "
            "(ignored — schema lives in Alembic baseline)",
            db_path,
        )

    async def close(self) -> None:
        return None

    async def save_graph(self, graph: KnowledgeGraph) -> None:
        raise NotImplementedError(_SKELETON_MESSAGE)

    async def load_graph(self) -> KnowledgeGraph | None:
        raise NotImplementedError(_SKELETON_MESSAGE)

    async def clear(self) -> None:
        raise NotImplementedError(_SKELETON_MESSAGE)


# ---------------------------------------------------------------------------
# Bundle
# ---------------------------------------------------------------------------


class PostgresStorageBundle:
    """PostgreSQL ``StorageBundle`` skeleton.

    One ``asyncpg.Pool`` is shared across the three sub-storages — that
    way every workspace pays one connection-pool's worth of resources,
    not three. The pool is created in ``open()`` and torn down in
    ``close()``; the sub-storages hold a reference but do not own its
    lifecycle.

    The ``root`` argument is kept for parity with
    :class:`SqliteStorageBundle` but is used purely for diagnostics:
    actual data lives in PostgreSQL, not on the local filesystem.
    """

    def __init__(
        self,
        *,
        workspace_id: str,
        root: Path,
        dsn: str,
        embedding_dimension: int = 4096,
    ) -> None:
        self._workspace_id = workspace_id
        self._root = root
        self._dsn = dsn
        self._embedding_dimension = embedding_dimension
        self._pool: asyncpg.Pool | None = None
        self._metadata_impl: _PostgresMetadataStorage | None = None
        self._vectors_impl: _PostgresVectorStorage | None = None
        self._graph_impl: _PostgresGraphStorage | None = None
        self._opened = False

    @property
    def workspace_id(self) -> str:
        return self._workspace_id

    @property
    def root(self) -> Path:
        return self._root

    @property
    def metadata(self) -> _PostgresMetadataStorage:
        if self._metadata_impl is None:
            raise RuntimeError("StorageBundle not opened; call open() first")
        return self._metadata_impl

    @property
    def vectors(self) -> _PostgresVectorStorage:
        if self._vectors_impl is None:
            raise RuntimeError("StorageBundle not opened; call open() first")
        return self._vectors_impl

    @property
    def graph(self) -> _PostgresGraphStorage:
        if self._graph_impl is None:
            raise RuntimeError("StorageBundle not opened; call open() first")
        return self._graph_impl

    async def open(self) -> None:
        """Create the asyncpg pool and verify the DSN with ``SELECT 1``.

        Idempotent: a second call is a no-op while the bundle is open.
        Raises ``RuntimeError`` if the optional Postgres extra is not
        installed; raises ``asyncpg`` errors verbatim on a bad DSN so
        operators see exactly what went wrong.
        """

        if self._opened:
            return

        _require_asyncpg()

        # Lazy imports keep the module importable without the extra.
        # The TYPE_CHECKING block above carries the ignore comment for
        # the type-checker; at runtime we've already gated on the spec.
        import asyncpg

        logger.info(
            "Opening Postgres storage bundle for workspace=%s "
            "(root=%s, dim=%d)",
            self._workspace_id,
            self._root,
            self._embedding_dimension,
        )

        self._pool = await asyncpg.create_pool(dsn=self._dsn)
        # ``create_pool`` does not connect lazily — it dispatches a
        # warm-up. Still, force a real round-trip so a wrong host or
        # missing extension fails at open() rather than at first query.
        async with self._pool.acquire() as conn:
            await conn.execute("SELECT 1")

        self._metadata_impl = _PostgresMetadataStorage(
            pool=self._pool, workspace_id=self._workspace_id
        )
        self._vectors_impl = _PostgresVectorStorage(
            pool=self._pool,
            workspace_id=self._workspace_id,
            embedding_dimension=self._embedding_dimension,
        )
        self._graph_impl = _PostgresGraphStorage(
            pool=self._pool, workspace_id=self._workspace_id
        )
        self._opened = True

    async def close(self) -> None:
        """Close the pool. Idempotent — safe to call twice."""

        if not self._opened:
            return
        if self._pool is not None:
            try:
                await self._pool.close()
            except Exception:  # pragma: no cover - defensive
                # Best-effort shutdown — match the SQLite bundle's
                # lenient close semantics so workspace teardown stays
                # unblocked even on a sick connection.
                logger.warning(
                    "Error closing asyncpg pool for workspace=%s",
                    self._workspace_id,
                    exc_info=True,
                )
        self._pool = None
        self._metadata_impl = None
        self._vectors_impl = None
        self._graph_impl = None
        self._opened = False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def postgres_bundle_factory(
    *, dsn: str, embedding_dimension: int = 4096
) -> Callable[..., PostgresStorageBundle]:
    """Build a ``StorageBundleFactory`` bound to a Postgres DSN.

    The factory shape matches :func:`sqlite_bundle_factory`: it takes
    keyword args ``workspace_id`` and ``root`` and returns an unopened
    bundle. ``dsn`` and ``embedding_dimension`` are captured in the
    closure so every workspace shares the same Postgres target — that
    matches how multi-tenant deployments will use a single PG cluster.

    ``root`` is plumbed through for diagnostic parity with SQLite; it
    is **not** used for data storage in the PG case.
    """

    def _factory(
        *, workspace_id: str, root: Path, **_kwargs: Any
    ) -> PostgresStorageBundle:
        return PostgresStorageBundle(
            workspace_id=workspace_id,
            root=root,
            dsn=dsn,
            embedding_dimension=embedding_dimension,
        )

    return _factory


__all__ = [
    "PostgresStorageBundle",
    "postgres_bundle_factory",
]
