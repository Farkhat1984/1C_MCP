"""
End-to-end tests for the full data preparation pipeline.

These tests verify that all engines work together correctly
on a realistic mock 1C configuration.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import NamedTuple

import pytest
import pytest_asyncio

from mcp_1c.config import EmbeddingConfig, get_config
from mcp_1c.domain.graph import RelationshipType
from mcp_1c.domain.metadata import MetadataType, ModuleType
from mcp_1c.engines.code.engine import CodeEngine
from mcp_1c.engines.embeddings.engine import EmbeddingEngine
from mcp_1c.engines.knowledge_graph.engine import KnowledgeGraphEngine
from mcp_1c.engines.metadata.engine import MetadataEngine
from mcp_1c.engines.platform.engine import PlatformEngine


class PipelineEngines(NamedTuple):
    """Container for all pipeline engine instances."""

    metadata: MetadataEngine
    code: CodeEngine
    knowledge_graph: KnowledgeGraphEngine
    embedding: EmbeddingEngine | None
    platform: PlatformEngine


# ---------------------------------------------------------------------------
# Shared pipeline fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def full_pipeline(mock_config_path: Path) -> PipelineEngines:
    """Initialize all engines in pipeline order and clean up after."""
    # Reset singletons
    MetadataEngine._instance = None
    CodeEngine._instance = None
    KnowledgeGraphEngine._instance = None
    EmbeddingEngine._instance = None

    # Create temp DB paths
    meta_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    meta_db_path = Path(meta_db_file.name)
    meta_db_file.close()

    emb_db_file = tempfile.NamedTemporaryFile(suffix=".emb.db", delete=False)
    emb_db_path = Path(emb_db_file.name)
    emb_db_file.close()

    # Adjust global config so graph storage reuses the same DB
    app_config = get_config()
    app_config.cache.db_path = meta_db_path

    # Stage 1: Metadata
    meta_engine = MetadataEngine.get_instance()
    meta_engine.cache.db_path = meta_db_path
    await meta_engine.initialize(mock_config_path, watch=False)

    # Stage 2: Code (no async init needed)
    code_engine = CodeEngine.get_instance()

    # Stage 3: Knowledge Graph
    kg_engine = KnowledgeGraphEngine.get_instance()
    await kg_engine.build(meta_engine)

    # Stage 4: Embeddings (conditional)
    emb_engine: EmbeddingEngine | None = None
    api_key = os.environ.get("MCP_EMBEDDING_API_KEY", "")
    if api_key:
        emb_config = EmbeddingConfig.from_env()
        emb_engine = EmbeddingEngine.get_instance()
        await emb_engine.initialize(emb_config, emb_db_path)
        await emb_engine.index_modules(meta_engine, code_engine)
        await emb_engine.index_procedures(meta_engine, code_engine)
        await emb_engine.index_metadata_descriptions(meta_engine)

    # Stage 5: Platform
    platform_engine = PlatformEngine()
    await platform_engine.initialize()

    yield PipelineEngines(
        metadata=meta_engine,
        code=code_engine,
        knowledge_graph=kg_engine,
        embedding=emb_engine,
        platform=platform_engine,
    )

    # Cleanup
    if emb_engine is not None:
        await emb_engine.close()
        EmbeddingEngine._instance = None

    await meta_engine.cache.close()
    MetadataEngine._instance = None
    CodeEngine._instance = None
    KnowledgeGraphEngine._instance = None

    for db in (meta_db_path, emb_db_path):
        if db.exists():
            db.unlink()


# ===================================================================
# Test classes
# ===================================================================


class TestMetadataPipeline:
    """Tests that metadata was fully indexed."""

    @pytest.mark.asyncio
    async def test_all_object_types_indexed(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """All core object types should appear in the index."""
        engine = full_pipeline.metadata
        stats = await engine.get_stats()

        expected_types = {
            "Catalog",
            "Document",
            "InformationRegister",
            "CommonModule",
            "Constant",
        }
        for t in expected_types:
            assert stats.get(t, 0) > 0, f"No objects of type {t} indexed"

    @pytest.mark.asyncio
    async def test_catalog_has_attributes(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Товары should have expected attributes."""
        obj = await full_pipeline.metadata.get_object(
            MetadataType.CATALOG, "Товары"
        )
        assert obj is not None
        attr_names = [a.name for a in obj.attributes]
        assert "Артикул" in attr_names
        assert "ЕдиницаИзмерения" in attr_names

    @pytest.mark.asyncio
    async def test_document_has_register_records(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """ПриходТовара should have register records."""
        obj = await full_pipeline.metadata.get_object(
            MetadataType.DOCUMENT, "ПриходТовара"
        )
        assert obj is not None
        assert obj.posting is True
        assert len(obj.register_records) >= 1

    @pytest.mark.asyncio
    async def test_search_finds_objects(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Search by name and by type filter should work."""
        results = await full_pipeline.metadata.search("Товар")
        assert len(results) >= 1
        names = [r.name for r in results]
        assert any("Товар" in n for n in names)

        # Search with type filter
        filtered = await full_pipeline.metadata.search(
            "Товар", metadata_type=MetadataType.CATALOG
        )
        for r in filtered:
            assert r.metadata_type == MetadataType.CATALOG

    @pytest.mark.asyncio
    async def test_subsystem_tree(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Торговля subsystem should have content."""
        tree = await full_pipeline.metadata.get_subsystem_tree()
        assert len(tree) >= 1
        names = [s.name for s in tree]
        assert "Торговля" in names

        торговля = next(s for s in tree if s.name == "Торговля")
        assert "Catalog.Товары" in торговля.content
        assert "Document.ПриходТовара" in торговля.content

    @pytest.mark.asyncio
    async def test_new_types_indexed(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """DefinedType, CommonAttribute, ScheduledJob should be indexed."""
        engine = full_pipeline.metadata

        dt_objects = await engine.list_objects(MetadataType.DEFINED_TYPE)
        assert any(o.name == "ВладелецТовара" for o in dt_objects)

        ca_objects = await engine.list_objects(MetadataType.COMMON_ATTRIBUTE)
        assert any(o.name == "Организация" for o in ca_objects)

        sj_objects = await engine.list_objects(MetadataType.SCHEDULED_JOB)
        assert any(o.name == "ОбновлениеКурсовВалют" for o in sj_objects)

    @pytest.mark.asyncio
    async def test_event_subscription_has_source_and_handler(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """EventSubscription should have parsed Source and Handler."""
        es_objects = await full_pipeline.metadata.list_objects(
            MetadataType.EVENT_SUBSCRIPTION
        )
        es = next((o for o in es_objects if o.name == "ПриЗаписиТоваров"), None)
        assert es is not None
        assert len(es.event_source) >= 1
        assert "DocumentObject.ПриходТовара" in es.event_source
        assert "ОбщегоНазначения" in es.event_handler

    @pytest.mark.asyncio
    async def test_scheduled_job_has_method_name(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """ScheduledJob should have parsed MethodName."""
        sj_objects = await full_pipeline.metadata.list_objects(
            MetadataType.SCHEDULED_JOB
        )
        sj = next(
            (o for o in sj_objects if o.name == "ОбновлениеКурсовВалют"), None
        )
        assert sj is not None
        assert "ОбщегоНазначения" in sj.method_name


class TestKnowledgeGraphPipeline:
    """Tests that the graph was built correctly with all relationship types."""

    @pytest.mark.asyncio
    async def test_graph_has_all_nodes(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """All metadata objects should appear as graph nodes."""
        stats = await full_pipeline.knowledge_graph.get_stats()
        assert stats["total_nodes"] > 0

        # Core objects should be nodes
        graph = full_pipeline.knowledge_graph._graph
        assert graph is not None
        assert "Catalog.Товары" in graph.nodes
        assert "Document.ПриходТовара" in graph.nodes
        assert "InformationRegister.ЦеныТоваров" in graph.nodes
        assert "CommonModule.ОбщегоНазначения" in graph.nodes

    @pytest.mark.asyncio
    async def test_attribute_references(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Attribute type references should create edges."""
        graph = full_pipeline.knowledge_graph._graph
        assert graph is not None

        # ЦеныТоваров dimension Товар references Catalog.Товары
        related = graph.get_related(
            "InformationRegister.ЦеныТоваров", direction="outgoing"
        )
        target_ids = [n.id for _, n in related]
        assert "Catalog.Товары" in target_ids

    @pytest.mark.asyncio
    async def test_subsystem_membership(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Objects should have subsystem membership edges."""
        graph = full_pipeline.knowledge_graph._graph
        assert graph is not None
        assert "Subsystem.Торговля" in graph.nodes

    @pytest.mark.asyncio
    async def test_event_subscription_edges(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """EventSubscription should have edges to source and handler."""
        graph = full_pipeline.knowledge_graph._graph
        assert graph is not None

        es_id = "EventSubscription.ПриЗаписиТоваров"
        if es_id not in graph.nodes:
            pytest.skip("EventSubscription node not in graph")

        related = graph.get_related(es_id, direction="outgoing")
        target_ids = [n.id for _, n in related]

        # Should reference Document.ПриходТовара (source)
        assert "Document.ПриходТовара" in target_ids

        # Should reference CommonModule.ОбщегоНазначения (handler)
        assert "CommonModule.ОбщегоНазначения" in target_ids

    @pytest.mark.asyncio
    async def test_scheduled_job_edges(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """ScheduledJob should have edge to handler module."""
        graph = full_pipeline.knowledge_graph._graph
        assert graph is not None

        sj_id = "ScheduledJob.ОбновлениеКурсовВалют"
        if sj_id not in graph.nodes:
            pytest.skip("ScheduledJob node not in graph")

        related = graph.get_related(sj_id, direction="outgoing")
        target_ids = [n.id for _, n in related]
        assert "CommonModule.ОбщегоНазначения" in target_ids

    @pytest.mark.asyncio
    async def test_defined_type_edges(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """DefinedType should have edges to constituent types."""
        graph = full_pipeline.knowledge_graph._graph
        assert graph is not None

        dt_id = "DefinedType.ВладелецТовара"
        if dt_id not in graph.nodes:
            pytest.skip("DefinedType node not in graph")

        related = graph.get_related(
            dt_id,
            relationship=RelationshipType.DEFINED_TYPE_CONTAINS,
            direction="outgoing",
        )
        target_ids = [n.id for _, n in related]
        assert "Catalog.Товары" in target_ids
        assert "Catalog.Контрагенты" in target_ids

    @pytest.mark.asyncio
    async def test_common_attribute_edges(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """CommonAttribute should have edges to applied objects."""
        graph = full_pipeline.knowledge_graph._graph
        assert graph is not None

        ca_id = "CommonAttribute.Организация"
        if ca_id not in graph.nodes:
            pytest.skip("CommonAttribute node not in graph")

        related = graph.get_related(
            ca_id,
            relationship=RelationshipType.COMMON_ATTRIBUTE_USAGE,
            direction="outgoing",
        )
        target_ids = [n.id for _, n in related]
        assert "Catalog.Товары" in target_ids
        assert "Document.ПриходТовара" in target_ids

    @pytest.mark.asyncio
    async def test_impact_analysis(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Changing Товары should show impact on related objects."""
        impact = await full_pipeline.knowledge_graph.get_impact(
            "Catalog.Товары", depth=2
        )
        assert impact["node_id"] == "Catalog.Товары"
        assert impact["total_impacted"] >= 1

    @pytest.mark.asyncio
    async def test_shortest_path(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Path from catalog to register should exist via edges."""
        path = await full_pipeline.knowledge_graph.find_path(
            "Catalog.Товары", "InformationRegister.ЦеныТоваров"
        )
        # There should be a path (via dimension_type edge)
        assert len(path) >= 1

    @pytest.mark.asyncio
    async def test_graph_stats(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Graph stats should report sane node/edge counts."""
        stats = await full_pipeline.knowledge_graph.get_stats()
        assert stats["total_nodes"] >= 5
        assert stats["total_edges"] >= 1
        assert len(stats["node_types"]) >= 3
        assert len(stats["relationship_types"]) >= 1


class TestCodePipeline:
    """Tests code engine with real BSL parsing."""

    @pytest.mark.asyncio
    async def test_get_module_content(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Read catalog module BSL code."""
        module = await full_pipeline.code.get_module(
            MetadataType.CATALOG, "Товары", ModuleType.OBJECT_MODULE
        )
        assert module is not None
        assert len(module.content) > 0

    @pytest.mark.asyncio
    async def test_parse_procedures(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """All procedures should be extracted from Товары module."""
        module = await full_pipeline.code.get_module(
            MetadataType.CATALOG, "Товары", ModuleType.OBJECT_MODULE
        )
        assert module is not None
        proc_names = [p.name for p in module.procedures]
        assert "ПередЗаписью" in proc_names
        assert "ПолучитьЦену" in proc_names

    @pytest.mark.asyncio
    async def test_find_definition(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Locate procedure definition in modules."""
        definitions = await full_pipeline.code.find_definition(
            "ТекущийПользователь"
        )
        assert len(definitions) >= 1
        assert definitions[0].reference_type == "definition"

    @pytest.mark.asyncio
    async def test_find_usages(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Find all usages of an identifier across modules."""
        usages = await full_pipeline.code.find_usages("Наименование")
        assert len(usages) >= 1
        for usage in usages:
            assert usage.reference_type == "usage"

    @pytest.mark.asyncio
    async def test_kontragenty_module_parsed(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Контрагенты module should have procedures including ПриЗаписи."""
        module = await full_pipeline.code.get_module(
            MetadataType.CATALOG, "Контрагенты", ModuleType.OBJECT_MODULE
        )
        assert module is not None
        proc_names = [p.name for p in module.procedures]
        assert "ПриЗаписи" in proc_names
        assert "ПолучитьИнформацию" in proc_names
        assert "НеиспользуемаяПроцедура" in proc_names


class TestEmbeddingsPipeline:
    """Tests for embeddings engine. Skipped without API key."""

    pytestmark = pytest.mark.skipif(
        not os.environ.get("MCP_EMBEDDING_API_KEY"),
        reason="No embedding API key set (MCP_EMBEDDING_API_KEY)",
    )

    @pytest.mark.asyncio
    async def test_modules_indexed(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """All modules should have embeddings."""
        assert full_pipeline.embedding is not None
        stats = await full_pipeline.embedding.get_stats()
        assert stats.total_documents > 0

    @pytest.mark.asyncio
    async def test_procedures_indexed(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Individual procedures should have embeddings."""
        assert full_pipeline.embedding is not None
        stats = await full_pipeline.embedding.get_stats()
        by_type = stats.by_doc_type
        assert by_type.get("procedure", 0) > 0

    @pytest.mark.asyncio
    async def test_metadata_indexed(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Metadata descriptions should have embeddings."""
        assert full_pipeline.embedding is not None
        stats = await full_pipeline.embedding.get_stats()
        by_type = stats.by_doc_type
        assert by_type.get("metadata_description", 0) > 0

    @pytest.mark.asyncio
    async def test_semantic_search(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Search should return relevant results."""
        assert full_pipeline.embedding is not None
        results = await full_pipeline.embedding.search(
            "получить цену товара", limit=5
        )
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_with_type_filter(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Filter by object_type should work."""
        assert full_pipeline.embedding is not None
        results = await full_pipeline.embedding.search(
            "товар", object_type="Catalog", limit=5
        )
        for r in results:
            assert r.document.metadata.get("object_type") == "Catalog"

    @pytest.mark.asyncio
    async def test_search_with_module_filter(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Filter by module_type should work."""
        assert full_pipeline.embedding is not None
        results = await full_pipeline.embedding.search(
            "записать", module_type="ObjectModule", limit=5
        )
        for r in results:
            assert r.document.metadata.get("module_type") == "ObjectModule"

    @pytest.mark.asyncio
    async def test_stats(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Stats should match expected counts."""
        assert full_pipeline.embedding is not None
        stats = await full_pipeline.embedding.get_stats()
        assert stats.total_documents > 0
        assert len(stats.by_doc_type) >= 1


class TestAnalysisTools:
    """Tests for the new analysis tools end-to-end."""

    @pytest.mark.asyncio
    async def test_roles_list(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """config-roles should return the Администратор role."""
        from mcp_1c.tools.analysis_tools import _list_role_names

        config_path = full_pipeline.metadata.config_path
        assert config_path is not None

        role_names = _list_role_names(config_path)
        assert "Администратор" in role_names

    @pytest.mark.asyncio
    async def test_role_rights_detail(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Detailed rights for Администратор should include catalog rights."""
        from mcp_1c.tools.analysis_tools import _find_role_xml, _parse_role_xml

        config_path = full_pipeline.metadata.config_path
        assert config_path is not None

        role_xml = _find_role_xml(config_path, "Администратор")
        assert role_xml is not None

        parsed = _parse_role_xml(role_xml)
        assert parsed["name"] == "Администратор"
        assert parsed["objects_count"] >= 1

        # Should have rights for Catalog.Товары
        obj_paths = [o["object"] for o in parsed["objects"]]
        assert "Catalog.Товары" in obj_paths

    @pytest.mark.asyncio
    async def test_role_rights_for_object(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Which roles have access to Catalog.Товары."""
        from mcp_1c.tools.analysis_tools import (
            _find_role_xml,
            _list_role_names,
            _parse_role_xml,
        )

        config_path = full_pipeline.metadata.config_path
        assert config_path is not None

        # Manually check which roles have Catalog.Товары
        matching_roles: list[str] = []
        for rn in _list_role_names(config_path):
            role_xml = _find_role_xml(config_path, rn)
            if role_xml is None:
                continue
            parsed = _parse_role_xml(role_xml)
            for obj_entry in parsed["objects"]:
                if obj_entry["object"] == "Catalog.Товары":
                    matching_roles.append(rn)

        assert "Администратор" in matching_roles

    @pytest.mark.asyncio
    async def test_config_compare_identical(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Compare config to itself should show no changes."""
        from mcp_1c.tools.analysis_tools import ConfigCompareTool

        config_path = full_pipeline.metadata.config_path
        assert config_path is not None

        tool = ConfigCompareTool()
        result = await tool.execute({
            "path_a": str(config_path),
            "path_b": str(config_path),
        })

        assert result["summary"]["added"] == 0
        assert result["summary"]["removed"] == 0
        assert result["summary"]["modified"] == 0


class TestCrossEnginePipeline:
    """Tests that verify cross-engine consistency."""

    @pytest.mark.asyncio
    async def test_all_metadata_objects_in_graph(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """Every MetadataEngine object should have a graph node."""
        graph = full_pipeline.knowledge_graph._graph
        assert graph is not None

        # Check a representative set of types
        check_types = [
            MetadataType.CATALOG,
            MetadataType.DOCUMENT,
            MetadataType.INFORMATION_REGISTER,
            MetadataType.COMMON_MODULE,
            MetadataType.CONSTANT,
        ]
        missing: list[str] = []
        for mt in check_types:
            objects = await full_pipeline.metadata.list_objects(mt)
            for obj in objects:
                if obj.full_name not in graph.nodes:
                    missing.append(obj.full_name)

        assert missing == [], f"Objects missing from graph: {missing}"

    @pytest.mark.asyncio
    async def test_graph_references_resolve(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """All graph edges should point to existing nodes."""
        graph = full_pipeline.knowledge_graph._graph
        assert graph is not None

        broken_edges: list[str] = []
        for edge in graph.edges:
            if edge.source not in graph.nodes:
                broken_edges.append(f"source={edge.source}")
            if edge.target not in graph.nodes:
                broken_edges.append(f"target={edge.target}")

        assert broken_edges == [], f"Broken edge refs: {broken_edges}"

    @pytest.mark.asyncio
    async def test_platform_types_available(
        self, full_pipeline: PipelineEngines
    ) -> None:
        """PlatformEngine should have types for 8.3.24."""
        types = full_pipeline.platform.get_all_types()
        assert len(types) > 0

        # Should have ТаблицаЗначений
        type_names = [t.name for t in types]
        assert "ТаблицаЗначений" in type_names
