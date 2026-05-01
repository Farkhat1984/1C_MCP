"""Watcher cascades: re-index → invalidate downstream caches.

End-to-end-style on the metadata side, but every external engine is
either mocked or proven to no-op when unitialised. We're not testing
that watchfiles fires events — that's library-level. We test the
contract of ``MetadataEngine._invalidate_downstream``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_1c.domain.metadata import MetadataType


@pytest.mark.asyncio
async def test_invalidate_downstream_drops_lsp_cache_for_bsl(
    tmp_path: Path,
) -> None:
    from mcp_1c.engines.metadata.engine import MetadataEngine

    engine = MetadataEngine()
    bsl_path = tmp_path / "ObjectModule.bsl"
    bsl_path.write_text("Процедура А() КонецПроцедуры")

    fake_code_engine = MagicMock()
    fake_code_engine.invalidate_lsp_cache = AsyncMock()

    with patch(
        "mcp_1c.engines.code.CodeEngine.get_instance",
        return_value=fake_code_engine,
    ):
        await engine._invalidate_downstream(
            MetadataType.CATALOG, "Контрагенты", bsl_path
        )

    fake_code_engine.invalidate_lsp_cache.assert_awaited_once_with(bsl_path)


@pytest.mark.asyncio
async def test_invalidate_downstream_skips_lsp_cache_for_xml(
    tmp_path: Path,
) -> None:
    """XML files are not BSL — LSP cache key is by .bsl path, no point dropping."""
    from mcp_1c.engines.metadata.engine import MetadataEngine

    engine = MetadataEngine()
    xml_path = tmp_path / "Catalog.xml"
    xml_path.write_text("<MetaDataObject/>")

    fake_code_engine = MagicMock()
    fake_code_engine.invalidate_lsp_cache = AsyncMock()

    with patch(
        "mcp_1c.engines.code.CodeEngine.get_instance",
        return_value=fake_code_engine,
    ):
        await engine._invalidate_downstream(
            MetadataType.CATALOG, "Контрагенты", xml_path
        )

    fake_code_engine.invalidate_lsp_cache.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalidate_downstream_calls_embeddings_when_initialized(
    tmp_path: Path,
) -> None:
    from mcp_1c.engines.metadata.engine import MetadataEngine

    engine = MetadataEngine()
    fake_emb = MagicMock()
    fake_emb.initialized = True
    fake_emb.invalidate_object = AsyncMock(return_value=3)

    with patch(
        "mcp_1c.engines.embeddings.engine.EmbeddingEngine.get_instance",
        return_value=fake_emb,
    ):
        await engine._invalidate_downstream(
            MetadataType.DOCUMENT,
            "РеализацияТоваров",
            tmp_path / "ObjectModule.bsl",
        )

    fake_emb.invalidate_object.assert_awaited_once_with(
        "Document.РеализацияТоваров"
    )


@pytest.mark.asyncio
async def test_invalidate_downstream_skips_embeddings_when_uninitialised(
    tmp_path: Path,
) -> None:
    from mcp_1c.engines.metadata.engine import MetadataEngine

    engine = MetadataEngine()
    fake_emb = MagicMock()
    fake_emb.initialized = False
    fake_emb.invalidate_object = AsyncMock()

    with patch(
        "mcp_1c.engines.embeddings.engine.EmbeddingEngine.get_instance",
        return_value=fake_emb,
    ):
        await engine._invalidate_downstream(
            MetadataType.CATALOG, "X", tmp_path / "x.bsl"
        )

    fake_emb.invalidate_object.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalidate_downstream_swallows_engine_failures(
    tmp_path: Path,
) -> None:
    """A failing downstream invalidation must not break the watcher."""
    from mcp_1c.engines.metadata.engine import MetadataEngine

    engine = MetadataEngine()

    fake_code = MagicMock()
    fake_code.invalidate_lsp_cache = AsyncMock(side_effect=RuntimeError("boom"))

    with patch(
        "mcp_1c.engines.code.CodeEngine.get_instance",
        return_value=fake_code,
    ):
        # Must complete without raising — swallowed inside the engine.
        await engine._invalidate_downstream(
            MetadataType.CATALOG, "X", tmp_path / "x.bsl"
        )


@pytest.mark.asyncio
async def test_embedding_invalidate_object_returns_count(
    tmp_path: Path,
) -> None:
    """``EmbeddingEngine.invalidate_object`` calls delete_by_prefix and
    returns the count, while remaining safe when uninitialised."""
    from mcp_1c.engines.embeddings.engine import EmbeddingEngine

    engine = EmbeddingEngine()
    # Not initialised: must return 0 cleanly.
    assert await engine.invalidate_object("Catalog.X") == 0

    fake_storage = MagicMock()
    fake_storage.delete_by_prefix = AsyncMock(return_value=7)
    engine._initialized = True
    engine._storage = fake_storage

    n = await engine.invalidate_object("Catalog.Контрагенты")
    assert n == 7
    fake_storage.delete_by_prefix.assert_awaited_once_with(
        "Catalog.Контрагенты."
    )


@pytest.mark.asyncio
async def test_embedding_invalidate_passes_through_existing_dot_suffix() -> None:
    """If caller already supplied a trailing dot, don't duplicate it."""
    from mcp_1c.engines.embeddings.engine import EmbeddingEngine

    engine = EmbeddingEngine()
    fake_storage = MagicMock()
    fake_storage.delete_by_prefix = AsyncMock(return_value=0)
    engine._initialized = True
    engine._storage = fake_storage

    await engine.invalidate_object("Catalog.X.")
    fake_storage.delete_by_prefix.assert_awaited_once_with("Catalog.X.")
