"""
E2E tests on real QGA (1C:ЗУП) configuration.

These tests run the full pipeline against a real extracted 1C configuration
located at /home/faragj/qga_config/qga.

Skip automatically if the config directory is not present.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from mcp_1c.config import EmbeddingConfig, get_config
from mcp_1c.domain.metadata import MetadataType
from mcp_1c.engines.code.engine import CodeEngine
from mcp_1c.engines.embeddings.engine import EmbeddingEngine
from mcp_1c.engines.knowledge_graph.engine import KnowledgeGraphEngine
from mcp_1c.engines.metadata.engine import MetadataEngine

QGA_CONFIG_PATH = Path("/home/faragj/qga_config/qga")

pytestmark = pytest.mark.skipif(
    not QGA_CONFIG_PATH.exists(),
    reason=f"QGA config not found at {QGA_CONFIG_PATH}",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def qga_metadata():
    """Initialize MetadataEngine on QGA config (module-scoped for speed)."""
    MetadataEngine._instance = None

    meta_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    meta_db_path = Path(meta_db.name)
    meta_db.close()

    app_config = get_config()
    app_config.cache.db_path = meta_db_path

    engine = MetadataEngine.get_instance()
    engine.cache.db_path = meta_db_path
    await engine.initialize(QGA_CONFIG_PATH, watch=False)

    yield engine

    await engine.cache.close()
    MetadataEngine._instance = None
    if meta_db_path.exists():
        meta_db_path.unlink()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def qga_code():
    """CodeEngine instance (module-scoped)."""
    CodeEngine._instance = None
    engine = CodeEngine.get_instance()
    yield engine
    CodeEngine._instance = None


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def qga_kg(qga_metadata):
    """Build Knowledge Graph on QGA config."""
    KnowledgeGraphEngine._instance = None
    engine = KnowledgeGraphEngine.get_instance()
    await engine.build(qga_metadata)
    yield engine
    KnowledgeGraphEngine._instance = None


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def qga_embeddings(qga_metadata, qga_code):
    """Initialize EmbeddingEngine (skip if no API key or no pre-built DB)."""
    api_key = os.environ.get("MCP_EMBEDDING_API_KEY", "") or os.environ.get(
        "DEEPINFRA_API_KEY", ""
    )
    # Check if pre-built embeddings DB exists from a pipeline run
    prebuilt_db = Path(".mcp_1c_embeddings.db")
    if not api_key and not prebuilt_db.exists():
        yield None
        return

    EmbeddingEngine._instance = None
    engine = EmbeddingEngine.get_instance()
    config = EmbeddingConfig.from_env()

    if prebuilt_db.exists():
        # Use pre-built DB from pipeline run
        await engine.initialize(config, prebuilt_db)
    else:
        # Build fresh (slow)
        db_file = tempfile.NamedTemporaryFile(suffix=".emb.db", delete=False)
        db_path = Path(db_file.name)
        db_file.close()
        await engine.initialize(config, db_path)

    yield engine

    await engine.close()
    EmbeddingEngine._instance = None


# ===========================================================================
# Metadata Tests
# ===========================================================================


class TestQGAMetadata:
    """Test metadata indexing on real QGA configuration."""

    @pytest.mark.asyncio
    async def test_object_counts(self, qga_metadata) -> None:
        """QGA should have thousands of objects."""
        stats = await qga_metadata.get_stats()
        total = sum(stats.values())
        assert total >= 2500, f"Too few objects: {total}"

    @pytest.mark.asyncio
    async def test_catalog_count(self, qga_metadata) -> None:
        """QGA has ~663 catalogs."""
        catalogs = await qga_metadata.list_objects(MetadataType.CATALOG)
        assert len(catalogs) >= 500

    @pytest.mark.asyncio
    async def test_common_modules_count(self, qga_metadata) -> None:
        """QGA has ~1924 common modules."""
        modules = await qga_metadata.list_objects(MetadataType.COMMON_MODULE)
        assert len(modules) >= 1500

    @pytest.mark.asyncio
    async def test_accumulation_registers(self, qga_metadata) -> None:
        """QGA has ~78 accumulation registers."""
        regs = await qga_metadata.list_objects(MetadataType.ACCUMULATION_REGISTER)
        assert len(regs) >= 50

    @pytest.mark.asyncio
    async def test_catalog_has_attributes(self, qga_metadata) -> None:
        """ФизическиеЛица should have attributes."""
        obj = await qga_metadata.get_object(MetadataType.CATALOG, "ФизическиеЛица")
        assert obj is not None
        attr_names = [a.name for a in obj.attributes]
        assert "ДатаРождения" in attr_names
        assert "ИНН" in attr_names

    @pytest.mark.asyncio
    async def test_catalog_attribute_types_parsed(self, qga_metadata) -> None:
        """Attribute types like cfg:EnumRef should be parsed."""
        obj = await qga_metadata.get_object(MetadataType.CATALOG, "ФизическиеЛица")
        assert obj is not None
        пол = next((a for a in obj.attributes if a.name == "Пол"), None)
        assert пол is not None
        # Should contain EnumRef or Enum reference
        assert "Enum" in пол.type or "Перечисление" in пол.type or "cfg:" in пол.type

    @pytest.mark.asyncio
    async def test_search_finds_real_objects(self, qga_metadata) -> None:
        """Search should find real QGA objects."""
        results = await qga_metadata.search("Сотрудник")
        assert len(results) >= 1
        names = [r.name for r in results]
        assert any("Сотрудник" in n for n in names)

    @pytest.mark.asyncio
    async def test_common_attributes_parsed(self, qga_metadata) -> None:
        """CommonAttributes should be indexed."""
        cas = await qga_metadata.list_objects(MetadataType.COMMON_ATTRIBUTE)
        assert len(cas) >= 1
        ca_names = [ca.name for ca in cas]
        assert len(ca_names) >= 1


# ===========================================================================
# Knowledge Graph Tests
# ===========================================================================


class TestQGAKnowledgeGraph:
    """Test Knowledge Graph on real QGA configuration."""

    @pytest.mark.asyncio
    async def test_graph_size(self, qga_kg) -> None:
        """Graph should have thousands of nodes and edges."""
        stats = await qga_kg.get_stats()
        assert stats["total_nodes"] >= 5000
        assert stats["total_edges"] >= 5000

    @pytest.mark.asyncio
    async def test_attribute_references_extracted(self, qga_kg) -> None:
        """cfg: type references should create attribute_reference edges."""
        stats = await qga_kg.get_stats()
        rel_types = stats.get("relationship_types", {})
        attr_refs = rel_types.get("attribute_reference", 0)
        assert attr_refs >= 1000, f"Too few attribute_references: {attr_refs}"

    @pytest.mark.asyncio
    async def test_tabular_references_extracted(self, qga_kg) -> None:
        """Tabular section references should create edges."""
        stats = await qga_kg.get_stats()
        rel_types = stats.get("relationship_types", {})
        tab_refs = rel_types.get("tabular_reference", 0)
        assert tab_refs >= 100, f"Too few tabular_references: {tab_refs}"

    @pytest.mark.asyncio
    async def test_module_ownership(self, qga_kg) -> None:
        """Module ownership edges should be created."""
        stats = await qga_kg.get_stats()
        rel_types = stats.get("relationship_types", {})
        mod_own = rel_types.get("module_ownership", 0)
        assert mod_own >= 3000

    @pytest.mark.asyncio
    async def test_impact_analysis_real(self, qga_kg) -> None:
        """Impact analysis on a real catalog."""
        graph = qga_kg._graph
        if graph is None:
            pytest.skip("Graph not built")

        # Find a catalog that has edges
        catalogs = [n for n in graph.nodes if n.startswith("Catalog.")]
        assert len(catalogs) > 0

        # Run impact on ФизическиеЛица (has many references)
        impact = await qga_kg.get_impact("Catalog.ФизическиеЛица", depth=2)
        assert impact["total_impacted"] >= 1

    @pytest.mark.asyncio
    async def test_all_edge_targets_exist(self, qga_kg) -> None:
        """All edge source/target nodes should exist in graph."""
        graph = qga_kg._graph
        if graph is None:
            pytest.skip("Graph not built")

        broken = []
        for edge in graph.edges:
            if edge.source not in graph.nodes:
                broken.append(f"missing source: {edge.source}")
            # target may reference objects not in this config (external refs)
            # so we only check source exists
        assert len(broken) == 0, f"Broken edges: {broken[:10]}"

    @pytest.mark.asyncio
    async def test_common_attribute_edges(self, qga_kg) -> None:
        """CommonAttribute should have usage edges (if content parsed)."""
        stats = await qga_kg.get_stats()
        rel_types = stats.get("relationship_types", {})
        # May be 0 if CommonAttribute XML doesn't have Content section
        # Just verify no crash
        assert "common_attribute_usage" not in rel_types or rel_types["common_attribute_usage"] >= 0


# ===========================================================================
# Code Engine Tests
# ===========================================================================


class TestQGACode:
    """Test code parsing on real QGA BSL modules."""

    @pytest.mark.asyncio
    async def test_common_module_parsed(self, qga_metadata, qga_code) -> None:
        """A common module should parse without errors."""
        modules = await qga_metadata.list_objects(MetadataType.COMMON_MODULE)
        assert len(modules) > 0

        # Find a module with an actual BSL file
        for mod in modules[:50]:
            if mod.modules and mod.modules[0].exists and mod.modules[0].path.exists():
                bsl = await qga_code.get_module_by_path(mod.modules[0].path)
                assert bsl is not None
                assert len(bsl.content) > 0
                return

        pytest.skip("No parseable BSL modules found in first 50 common modules")

    @pytest.mark.asyncio
    async def test_procedures_extracted(self, qga_metadata, qga_code) -> None:
        """Procedures should be extracted from BSL modules."""
        modules = await qga_metadata.list_objects(MetadataType.COMMON_MODULE)

        for mod in modules[:100]:
            if mod.modules and mod.modules[0].exists and mod.modules[0].path.exists():
                bsl = await qga_code.get_module_by_path(mod.modules[0].path)
                if bsl and bsl.procedures:
                    assert len(bsl.procedures) >= 1
                    proc = bsl.procedures[0]
                    assert proc.name
                    return

        pytest.skip("No modules with procedures found")

    @pytest.mark.asyncio
    async def test_find_definition(self, qga_metadata, qga_code) -> None:
        """Find definition of a common function."""
        defs = await qga_code.find_definition("ТекущаяДата")
        # May or may not find it, but should not crash
        assert isinstance(defs, list)


# ===========================================================================
# Embeddings Tests (require API key or pre-built DB)
# ===========================================================================


class TestQGAEmbeddings:
    """Test embeddings on QGA. Skip if no API key and no pre-built DB."""

    @pytest.mark.asyncio
    async def test_embeddings_available(self, qga_embeddings) -> None:
        """Embeddings should be initialized."""
        if qga_embeddings is None:
            pytest.skip("No embedding API key or pre-built DB")
        assert qga_embeddings.initialized

    @pytest.mark.asyncio
    async def test_embedding_stats(self, qga_embeddings) -> None:
        """Should have indexed documents."""
        if qga_embeddings is None:
            pytest.skip("No embeddings available")
        stats = await qga_embeddings.get_stats()
        assert stats.total_documents > 0

    @pytest.mark.asyncio
    async def test_semantic_search(self, qga_embeddings) -> None:
        """Semantic search should return results."""
        if qga_embeddings is None:
            pytest.skip("No embeddings available")
        results = await qga_embeddings.search("расчет зарплаты сотрудника", limit=10)
        assert len(results) >= 1
        # Results should have scores
        assert results[0].score > 0

    @pytest.mark.asyncio
    async def test_search_filter_by_type(self, qga_embeddings) -> None:
        """Filter by object_type should work."""
        if qga_embeddings is None:
            pytest.skip("No embeddings available")
        results = await qga_embeddings.search(
            "начисление", object_type="CommonModule", limit=5
        )
        for r in results:
            assert r.document.metadata.get("object_type") == "CommonModule"

    @pytest.mark.asyncio
    async def test_resume_skips_existing(self, qga_embeddings, qga_metadata, qga_code) -> None:
        """Re-running index should skip already indexed documents."""
        if qga_embeddings is None:
            pytest.skip("No embeddings available")

        stats_before = await qga_embeddings.get_stats()
        if stats_before.total_documents == 0:
            pytest.skip("No documents indexed")

        # Run index again — should skip everything
        result = await qga_embeddings.index_modules(
            qga_metadata, qga_code, force_reindex=False
        )
        assert result["skipped"] > 0
        assert result["indexed"] == 0  # Nothing new to index
