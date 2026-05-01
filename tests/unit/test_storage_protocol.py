"""Storage Protocol contract tests.

Two flavours:
1. Structural — concrete SQLite classes must satisfy the protocol
   shape. Caught at runtime via ``isinstance``-with-``runtime_checkable``.
   Catches drift when someone adds/renames a method on a backend without
   updating the protocol (or vice versa).
2. Behavioural — ``SqliteStorageBundle`` opens, exposes the trio,
   closes cleanly. Light: real DBs in tmp_path, no real workspace.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_1c.engines.storage import (
    GraphStorage,
    MetadataStorage,
    VectorStorage,
)
from mcp_1c.engines.storage.sqlite import SqliteStorageBundle, sqlite_bundle_factory


def test_metadata_cache_satisfies_protocol() -> None:
    from mcp_1c.engines.metadata.cache import MetadataCache

    cache = MetadataCache(Path("/tmp/x.db"))
    assert isinstance(cache, MetadataStorage)


def test_vector_storage_satisfies_protocol() -> None:
    from mcp_1c.engines.embeddings.storage import VectorStorage as VS

    storage = VS(Path("/tmp/y.db"), dimension=384)
    assert isinstance(storage, VectorStorage)


def test_graph_storage_satisfies_protocol() -> None:
    from mcp_1c.engines.knowledge_graph.storage import (
        GraphStorage as GS,
    )

    storage = GS()
    assert isinstance(storage, GraphStorage)


@pytest.mark.asyncio
async def test_sqlite_bundle_open_creates_three_dbs(tmp_path: Path) -> None:
    bundle = SqliteStorageBundle(
        workspace_id="ws-1",
        root=tmp_path / "ws-1",
        embedding_dimension=384,
    )
    await bundle.open()
    try:
        # Three concrete files exist after open().
        assert (tmp_path / "ws-1" / "cache.db").exists()
        assert (tmp_path / "ws-1" / "embeddings.db").exists()
        assert (tmp_path / "ws-1" / "knowledge_graph.db").exists()
        # Trio accessible.
        assert bundle.metadata is not None
        assert bundle.vectors is not None
        assert bundle.graph is not None
    finally:
        await bundle.close()


@pytest.mark.asyncio
async def test_sqlite_bundle_open_is_idempotent(tmp_path: Path) -> None:
    bundle = SqliteStorageBundle(
        workspace_id="ws-2",
        root=tmp_path / "ws-2",
        embedding_dimension=384,
    )
    await bundle.open()
    try:
        # Second open() must not crash and must not create new instances.
        first_metadata = bundle.metadata
        await bundle.open()
        assert bundle.metadata is first_metadata
    finally:
        await bundle.close()


@pytest.mark.asyncio
async def test_sqlite_bundle_close_idempotent(tmp_path: Path) -> None:
    bundle = SqliteStorageBundle(
        workspace_id="ws-3",
        root=tmp_path / "ws-3",
        embedding_dimension=384,
    )
    await bundle.open()
    await bundle.close()
    # Second close must be a clean no-op.
    await bundle.close()


@pytest.mark.asyncio
async def test_accessing_storage_before_open_raises(tmp_path: Path) -> None:
    bundle = SqliteStorageBundle(
        workspace_id="ws-4",
        root=tmp_path / "ws-4",
        embedding_dimension=384,
    )
    with pytest.raises(RuntimeError, match="not opened"):
        _ = bundle.metadata
    with pytest.raises(RuntimeError, match="not opened"):
        _ = bundle.vectors
    with pytest.raises(RuntimeError, match="not opened"):
        _ = bundle.graph


@pytest.mark.asyncio
async def test_factory_yields_independent_bundles(tmp_path: Path) -> None:
    factory = sqlite_bundle_factory(embedding_dimension=384)
    bundle_a = factory(workspace_id="a", root=tmp_path / "a")
    bundle_b = factory(workspace_id="b", root=tmp_path / "b")
    assert bundle_a is not bundle_b
    assert bundle_a.workspace_id != bundle_b.workspace_id
    await bundle_a.open()
    await bundle_b.open()
    try:
        # The two bundles point at different files — multi-tenant
        # smoke check.
        assert (tmp_path / "a" / "cache.db").exists()
        assert (tmp_path / "b" / "cache.db").exists()
    finally:
        await bundle_a.close()
        await bundle_b.close()
