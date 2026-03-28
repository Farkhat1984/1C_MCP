"""
Integration tests using real engines with test data.

Tests full engine workflows: initialization, indexing, querying,
parsing, dependency analysis, and platform knowledge base access.
"""

import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from mcp_1c.domain.code import DependencyEdge, DependencyGraph
from mcp_1c.domain.metadata import MetadataType, ModuleType
from mcp_1c.engines.code.engine import CodeEngine
from mcp_1c.engines.metadata.engine import MetadataEngine
from mcp_1c.engines.platform.engine import PlatformEngine


class TestMetadataEngineIntegration:
    """Integration tests for MetadataEngine with real file parsing."""

    @pytest_asyncio.fixture
    async def engine(self, mock_config_path: Path) -> MetadataEngine:
        """Create and initialize engine with mock configuration."""
        MetadataEngine._instance = None
        engine = MetadataEngine.get_instance()

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        engine.cache.db_path = db_path
        progress = await engine.initialize(mock_config_path, watch=False)

        yield engine

        await engine.cache.close()
        if db_path.exists():
            db_path.unlink()
        MetadataEngine._instance = None

    @pytest.mark.asyncio
    async def test_parse_and_list_catalogs(self, engine: MetadataEngine) -> None:
        """Full cycle: init -> index -> list objects."""
        result = await engine.list_objects("Catalog")

        assert isinstance(result, list)
        assert len(result) >= 1
        names = [obj.name for obj in result]
        assert "Товары" in names

    @pytest.mark.asyncio
    async def test_list_documents(self, engine: MetadataEngine) -> None:
        """List documents returns expected test objects."""
        result = await engine.list_objects(MetadataType.DOCUMENT)

        assert isinstance(result, list)
        assert len(result) >= 1
        names = [obj.name for obj in result]
        assert "ПриходТовара" in names

    @pytest.mark.asyncio
    async def test_list_information_registers(self, engine: MetadataEngine) -> None:
        """List information registers returns ЦеныТоваров."""
        result = await engine.list_objects(MetadataType.INFORMATION_REGISTER)

        assert isinstance(result, list)
        assert len(result) >= 1
        names = [obj.name for obj in result]
        assert "ЦеныТоваров" in names

    @pytest.mark.asyncio
    async def test_get_object_returns_full_structure(
        self, engine: MetadataEngine
    ) -> None:
        """Get object should return complete metadata with attributes."""
        obj = await engine.get_object(MetadataType.CATALOG, "Товары")

        assert obj is not None
        assert obj.name == "Товары"
        assert obj.metadata_type == MetadataType.CATALOG
        assert obj.synonym == "Товары"
        assert obj.comment == "Справочник товаров"
        assert len(obj.attributes) == 2

        attr_names = [a.name for a in obj.attributes]
        assert "Артикул" in attr_names
        assert "ЕдиницаИзмерения" in attr_names

        # Verify attribute details
        article = next(a for a in obj.attributes if a.name == "Артикул")
        assert article.type == "String"
        assert article.indexed is True

    @pytest.mark.asyncio
    async def test_get_object_tabular_sections(
        self, engine: MetadataEngine
    ) -> None:
        """Get object returns tabular sections with nested attributes."""
        obj = await engine.get_object(MetadataType.CATALOG, "Товары")

        assert obj is not None
        assert len(obj.tabular_sections) == 1
        ts = obj.tabular_sections[0]
        assert ts.name == "Штрихкоды"
        assert len(ts.attributes) == 1
        assert ts.attributes[0].name == "Штрихкод"
        assert ts.attributes[0].type == "String"

    @pytest.mark.asyncio
    async def test_get_document_register_records(
        self, engine: MetadataEngine
    ) -> None:
        """Document should have register records and posting flag."""
        obj = await engine.get_object(MetadataType.DOCUMENT, "ПриходТовара")

        assert obj is not None
        assert obj.posting is True
        assert len(obj.register_records) == 1
        assert "РегистрНакопления.ОстаткиТоваров" in obj.register_records

    @pytest.mark.asyncio
    async def test_get_register_structure(self, engine: MetadataEngine) -> None:
        """Register should have dimensions and resources."""
        obj = await engine.get_object(
            MetadataType.INFORMATION_REGISTER, "ЦеныТоваров"
        )

        assert obj is not None
        assert len(obj.dimensions) == 2
        dim_names = [d.name for d in obj.dimensions]
        assert "Товар" in dim_names
        assert "ТипЦены" in dim_names

        assert len(obj.resources) == 1
        assert obj.resources[0].name == "Цена"
        assert obj.resources[0].type == "Number"

    @pytest.mark.asyncio
    async def test_search_finds_objects_by_name(
        self, engine: MetadataEngine
    ) -> None:
        """Search should find objects by name substring."""
        results = await engine.search("Товар")

        assert len(results) >= 1
        names = [r.name for r in results]
        assert any("Товар" in name for name in names)

    @pytest.mark.asyncio
    async def test_search_with_type_filter(self, engine: MetadataEngine) -> None:
        """Search with type filter narrows results."""
        results = await engine.search("Товар", metadata_type=MetadataType.CATALOG)

        assert len(results) >= 1
        for r in results:
            assert r.metadata_type == MetadataType.CATALOG

    @pytest.mark.asyncio
    async def test_subsystem_tree(self, engine: MetadataEngine) -> None:
        """Subsystem tree should include Торговля with content."""
        tree = await engine.get_subsystem_tree()

        assert len(tree) >= 1
        names = [s.name for s in tree]
        assert "Торговля" in names

        торговля = next(s for s in tree if s.name == "Торговля")
        assert len(торговля.content) == 2
        assert "Catalog.Товары" in торговля.content
        assert "Document.ПриходТовара" in торговля.content

    @pytest.mark.asyncio
    async def test_get_stats(self, engine: MetadataEngine) -> None:
        """Stats should return counts per type."""
        stats = await engine.get_stats()

        assert isinstance(stats, dict)
        assert len(stats) > 0


class TestCodeEngineIntegrationExtended:
    """Extended integration tests for CodeEngine with real BSL files."""

    @pytest_asyncio.fixture
    async def engines(self, mock_config_path: Path):
        """Create both metadata and code engines."""
        MetadataEngine._instance = None
        CodeEngine._instance = None

        meta_engine = MetadataEngine.get_instance()
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        meta_engine.cache.db_path = db_path
        await meta_engine.initialize(mock_config_path, watch=False)

        code_engine = CodeEngine.get_instance()

        yield meta_engine, code_engine

        await meta_engine.cache.close()
        if db_path.exists():
            db_path.unlink()
        MetadataEngine._instance = None
        CodeEngine._instance = None

    @pytest.mark.asyncio
    async def test_parse_catalog_module_returns_procedures(self, engines) -> None:
        """Parsing Товары ObjectModule.bsl should extract procedures."""
        _, code_engine = engines
        module = await code_engine.get_module(
            MetadataType.CATALOG, "Товары", ModuleType.OBJECT_MODULE
        )

        assert module is not None
        assert len(module.procedures) >= 3
        proc_names = [p.name for p in module.procedures]
        assert "ПередЗаписью" in proc_names
        assert "ОбработкаВыбора" in proc_names
        assert "ПолучитьЦену" in proc_names

    @pytest.mark.asyncio
    async def test_parse_common_module_returns_exported_functions(
        self, engines
    ) -> None:
        """ОбщегоНазначения module should have exported functions."""
        _, code_engine = engines
        module = await code_engine.get_common_module_code("ОбщегоНазначения")

        assert module is not None
        exported = module.get_exported_procedures()
        assert len(exported) >= 2

        exported_names = [p.name for p in exported]
        assert "ТекущийПользователь" in exported_names
        assert "ПравоДоступа" in exported_names

    @pytest.mark.asyncio
    async def test_common_module_server_procedures(self, engines) -> None:
        """Common module should have server-side procedures."""
        _, code_engine = engines
        module = await code_engine.get_common_module_code("ОбщегоНазначения")

        assert module is not None
        server_procs = module.get_server_procedures()
        assert len(server_procs) >= 2

    @pytest.mark.asyncio
    async def test_find_definition_in_modules(self, engines) -> None:
        """Definition search should find procedure locations."""
        _, code_engine = engines
        definitions = await code_engine.find_definition("ТекущийПользователь")

        assert len(definitions) >= 1
        assert definitions[0].reference_type == "definition"
        assert "ОбщегоНазначения" in str(definitions[0].location.file_path)

    @pytest.mark.asyncio
    async def test_find_usages_across_modules(self, engines) -> None:
        """Find usages should search across all .bsl files."""
        _, code_engine = engines
        usages = await code_engine.find_usages("Наименование")

        # "Наименование" appears in the catalog object module
        assert len(usages) >= 1
        for usage in usages:
            assert usage.reference_type == "usage"
            assert usage.context != ""

    @pytest.mark.asyncio
    async def test_module_regions_parsed(self, engines) -> None:
        """Module regions should be extracted from .bsl files."""
        _, code_engine = engines
        module = await code_engine.get_module(
            MetadataType.CATALOG, "Товары", ModuleType.OBJECT_MODULE
        )

        assert module is not None
        assert len(module.regions) >= 2
        region_names = [r.name for r in module.regions]
        assert "ОбработчикиСобытий" in region_names
        assert "СлужебныеПроцедуры" in region_names

    @pytest.mark.asyncio
    async def test_procedure_directive_detected(self, engines) -> None:
        """Compilation directives should be detected on procedures."""
        _, code_engine = engines
        proc = await code_engine.get_procedure(
            MetadataType.CATALOG, "Товары", "ПолучитьЦену", ModuleType.OBJECT_MODULE
        )

        assert proc is not None
        assert proc.directive is not None
        assert proc.directive.is_server()

    @pytest.mark.asyncio
    async def test_procedure_parameters_parsed(self, engines) -> None:
        """Procedure parameters should be extracted with defaults."""
        _, code_engine = engines
        proc = await code_engine.get_procedure(
            MetadataType.CATALOG, "Товары", "ПолучитьЦену", ModuleType.OBJECT_MODULE
        )

        assert proc is not None
        assert len(proc.parameters) == 1
        param = proc.parameters[0]
        assert param.name == "Дата"
        assert param.default_value == "Неопределено"
        assert param.is_optional is True


class TestDependencyGraphIntegration:
    """Integration tests for DependencyGraph."""

    def test_cycle_detection_prevents_infinite_loop(self) -> None:
        """Circular dependencies should not cause recursion."""
        graph = DependencyGraph()
        graph.add_node("A", "procedure")
        graph.add_node("B", "procedure")
        graph.add_node("C", "procedure")
        graph.add_edge("A", "B", "calls")
        graph.add_edge("B", "C", "calls")
        graph.add_edge("C", "A", "calls")

        # Should NOT raise RecursionError
        deps = graph.get_dependencies("A", depth=10)

        assert isinstance(deps, dict)
        assert deps["node"] == "A"
        # Cycle should be handled by visited set
        assert len(deps["callees"]) == 1
        assert deps["callees"][0]["node"] == "B"

    def test_deep_chain_respects_max_depth(self) -> None:
        """Long dependency chains should be bounded by max_depth."""
        graph = DependencyGraph()
        # Build chain: node_0 -> node_1 -> ... -> node_19
        for i in range(20):
            graph.add_node(f"node_{i}", "procedure")
        for i in range(19):
            graph.add_edge(f"node_{i}", f"node_{i + 1}", "calls")

        # With depth=5, should not traverse beyond 5 levels
        deps = graph.get_dependencies("node_0", depth=5)

        assert deps["node"] == "node_0"
        assert len(deps["callees"]) == 1

        # Walk the chain to verify depth limitation
        current = deps
        depth_count = 0
        while current.get("callees") and len(current["callees"]) > 0:
            current = current["callees"][0]
            depth_count += 1

        # Depth should be at most 5 (depth parameter limits recursion)
        assert depth_count <= 5

    def test_disconnected_nodes(self) -> None:
        """Disconnected nodes should return empty callees/callers."""
        graph = DependencyGraph()
        graph.add_node("isolated", "procedure")
        graph.add_node("other", "procedure")
        graph.add_edge("other", "something", "calls")

        deps = graph.get_dependencies("isolated", depth=3)

        assert deps["node"] == "isolated"
        assert deps["callees"] == []
        assert deps["callers"] == []

    def test_edge_count_tracking(self) -> None:
        """Multiple calls between same pair should increment count."""
        graph = DependencyGraph()
        graph.add_edge("A", "B", "calls")
        graph.add_edge("A", "B", "calls")
        graph.add_edge("A", "B", "calls")

        assert len(graph.edges) == 1
        assert graph.edges[0].count == 3

    def test_different_edge_types_separate(self) -> None:
        """Different edge types between same nodes should be separate."""
        graph = DependencyGraph()
        graph.add_edge("A", "B", "calls")
        graph.add_edge("A", "B", "uses_metadata")

        assert len(graph.edges) == 2
        edge_types = {e.edge_type for e in graph.edges}
        assert "calls" in edge_types
        assert "uses_metadata" in edge_types


class TestPlatformEngineIntegration:
    """Integration tests for PlatformEngine with real JSON data."""

    @pytest_asyncio.fixture
    async def engine(self) -> PlatformEngine:
        """Create and initialize platform engine."""
        engine = PlatformEngine()
        await engine.initialize()
        return engine

    @pytest.mark.asyncio
    async def test_load_and_search_methods(self, engine: PlatformEngine) -> None:
        """Search should find string methods."""
        results = engine.search_methods("СтрДлина")

        assert len(results) >= 1
        assert results[0].name == "СтрДлина"
        assert results[0].name_en == "StrLen"

    @pytest.mark.asyncio
    async def test_get_type_returns_properties(self, engine: PlatformEngine) -> None:
        """Get known type should return properties and methods."""
        t = engine.get_type("ТаблицаЗначений")

        assert t is not None
        assert t.name == "ТаблицаЗначений"
        assert t.name_en == "ValueTable"
        assert t.category is not None

        assert len(t.methods) > 0
        method_names = [m.name for m in t.methods]
        assert "Добавить" in method_names

        assert len(t.properties) > 0
        prop_names = [p.name for p in t.properties]
        assert "Колонки" in prop_names

    @pytest.mark.asyncio
    async def test_get_event_with_details(self, engine: PlatformEngine) -> None:
        """Get event should return full details including parameters."""
        event = engine.get_event("ПередЗаписью")

        assert event is not None
        assert event.name == "ПередЗаписью"
        assert event.name_en == "BeforeWrite"
        assert event.can_cancel is True
        assert len(event.parameters) > 0

    @pytest.mark.asyncio
    async def test_search_all_categories(self, engine: PlatformEngine) -> None:
        """search_all should return results from methods, types, and events."""
        results = engine.search_all("Дата")

        assert "methods" in results
        assert "types" in results
        assert "events" in results
        assert len(results["methods"]) > 0

    @pytest.mark.asyncio
    async def test_global_context_sections(self, engine: PlatformEngine) -> None:
        """Global context should have named sections."""
        sections = engine.get_global_context_sections()

        assert len(sections) > 0
        section_names = [s.name for s in sections]
        assert "Строковые функции" in section_names
        assert "Математические функции" in section_names

    @pytest.mark.asyncio
    async def test_type_method_lookup(self, engine: PlatformEngine) -> None:
        """Get specific method of a type."""
        method = engine.get_type_method("Массив", "Добавить")

        assert method is not None
        assert method.name == "Добавить"
        assert len(method.parameters) > 0

    @pytest.mark.asyncio
    async def test_events_for_object_type(self, engine: PlatformEngine) -> None:
        """Get events for a specific object type (e.g., Документ)."""
        events = engine.get_events_for_object("Документ")

        assert len(events) > 0
        event_names = [e.name for e in events]
        assert "ПередЗаписью" in event_names
        assert "ОбработкаПроведения" in event_names
