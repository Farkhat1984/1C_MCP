"""Integration tests for the Postgres StorageBundle skeleton.

Gated by ``-m postgres`` and ``MCP_PG_DSN``. The tests prove three
things:

1. The connection lifecycle (``open()`` / ``close()``) works against a
   real Postgres with pgvector — operators need this to validate a DSN
   before filling in queries.
2. The skeleton methods raise ``NotImplementedError`` with a "skeleton"
   marker. Future contributors greping for ``NotImplementedError`` will
   land on the right thing instead of mistaking it for a bug.
3. ``close()`` is idempotent and tolerates a never-opened bundle.

Run with::

    export MCP_PG_DSN=postgres://user:pass@host:5432/mcp_1c_test
    pytest tests/integration/test_postgres_skeleton.py -m postgres

The Alembic baseline does **not** need to be applied for these tests —
they only exercise the pool lifecycle and the unimplemented methods.
A separate suite (out of scope here) will run after ``alembic upgrade
head`` once queries land.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
import pytest_asyncio

_HAS_ASYNCPG = importlib.util.find_spec("asyncpg") is not None
_DSN = os.environ.get("MCP_PG_DSN")

# Skip the whole module unless both prerequisites are met. Two reasons
# rather than one so the skip message tells the operator exactly which
# piece is missing.
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not _HAS_ASYNCPG,
        reason="asyncpg not installed (pip install -e '.[postgres]')",
    ),
    pytest.mark.skipif(
        not _DSN,
        reason="MCP_PG_DSN not set — skipping live Postgres tests",
    ),
]


# Importing at module top would crash collection in environments
# without the optional extra. Defer to fixture scope where skips have
# already gated us.
@pytest_asyncio.fixture
async def opened_bundle(tmp_path: Path):  # type: ignore[no-untyped-def]
    from mcp_1c.engines.storage.postgres import PostgresStorageBundle

    assert _DSN is not None  # narrowed by pytestmark skip
    bundle = PostgresStorageBundle(
        workspace_id="test-workspace",
        root=tmp_path,
        dsn=_DSN,
        embedding_dimension=4096,
    )
    await bundle.open()
    try:
        yield bundle
    finally:
        await bundle.close()


@pytest.mark.asyncio
async def test_open_runs_select_one(opened_bundle) -> None:  # type: ignore[no-untyped-def]
    """``open()`` validated the DSN; storages are wired."""

    # Properties only return a value once ``open()`` has run — touching
    # them is itself the test that the bundle is in the opened state.
    assert opened_bundle.metadata is not None
    assert opened_bundle.vectors is not None
    assert opened_bundle.graph is not None
    assert opened_bundle.workspace_id == "test-workspace"


@pytest.mark.asyncio
async def test_close_is_idempotent(tmp_path: Path) -> None:
    from mcp_1c.engines.storage.postgres import PostgresStorageBundle

    assert _DSN is not None
    bundle = PostgresStorageBundle(
        workspace_id="idem-test",
        root=tmp_path,
        dsn=_DSN,
    )
    # Closing before opening must not raise.
    await bundle.close()

    await bundle.open()
    await bundle.close()
    # Second close on an already-closed bundle is a no-op.
    await bundle.close()


@pytest.mark.asyncio
async def test_open_is_idempotent(opened_bundle) -> None:  # type: ignore[no-untyped-def]
    # A second open() while already opened must not double-create the
    # pool — re-opening is a no-op and the same storages are returned.
    metadata_before = opened_bundle.metadata
    await opened_bundle.open()
    assert opened_bundle.metadata is metadata_before


@pytest.mark.asyncio
async def test_metadata_methods_are_skeleton(opened_bundle) -> None:  # type: ignore[no-untyped-def]
    """Every metadata method raises NotImplementedError with 'skeleton'."""

    from mcp_1c.domain.metadata import MetadataType

    storage = opened_bundle.metadata

    with pytest.raises(NotImplementedError, match="skeleton"):
        await storage.get_object(MetadataType.CATALOG, "Контрагенты")
    with pytest.raises(NotImplementedError, match="skeleton"):
        await storage.get_objects_by_type(MetadataType.CATALOG)
    with pytest.raises(NotImplementedError, match="skeleton"):
        await storage.search_objects("test")
    with pytest.raises(NotImplementedError, match="skeleton"):
        await storage.get_hash(MetadataType.CATALOG, "X")
    with pytest.raises(NotImplementedError, match="skeleton"):
        await storage.get_subsystems()
    with pytest.raises(NotImplementedError, match="skeleton"):
        await storage.get_stats()
    with pytest.raises(NotImplementedError, match="skeleton"):
        await storage.clear()


@pytest.mark.asyncio
async def test_vector_methods_are_skeleton(opened_bundle) -> None:  # type: ignore[no-untyped-def]
    storage = opened_bundle.vectors

    with pytest.raises(NotImplementedError, match="skeleton"):
        await storage.save_documents([])
    with pytest.raises(NotImplementedError, match="skeleton"):
        await storage.search([0.0] * 4096)
    with pytest.raises(NotImplementedError, match="skeleton"):
        await storage.get_document("doc-id")
    with pytest.raises(NotImplementedError, match="skeleton"):
        await storage.get_existing_ids()
    with pytest.raises(NotImplementedError, match="skeleton"):
        await storage.delete_by_prefix("prefix")
    with pytest.raises(NotImplementedError, match="skeleton"):
        await storage.get_stats()


@pytest.mark.asyncio
async def test_graph_methods_are_skeleton(opened_bundle, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from mcp_1c.domain.graph import KnowledgeGraph

    storage = opened_bundle.graph

    # init_tables is a real (no-op) on PG — not skeleton — because the
    # protocol's contract is "schema is ready after this call" and PG
    # ships its schema via Alembic.
    await storage.init_tables(tmp_path / "ignored.db")

    with pytest.raises(NotImplementedError, match="skeleton"):
        await storage.save_graph(KnowledgeGraph())
    with pytest.raises(NotImplementedError, match="skeleton"):
        await storage.load_graph()
    with pytest.raises(NotImplementedError, match="skeleton"):
        await storage.clear()


@pytest.mark.asyncio
async def test_factory_matches_sqlite_shape(tmp_path: Path) -> None:
    """Factory takes ``workspace_id`` + ``root`` — same as the SQLite one."""

    from mcp_1c.engines.storage.postgres import (
        PostgresStorageBundle,
        postgres_bundle_factory,
    )

    assert _DSN is not None
    factory = postgres_bundle_factory(dsn=_DSN, embedding_dimension=4096)
    bundle = factory(workspace_id="factory-test", root=tmp_path)
    assert isinstance(bundle, PostgresStorageBundle)
    assert bundle.workspace_id == "factory-test"
    assert bundle.root == tmp_path
