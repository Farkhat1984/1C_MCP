"""
Tests for dependency graph builder (Phase 2).

Tests graph building, edge creation, and query methods.
"""

import pytest
from pathlib import Path

from mcp_1c.engines.code.dependencies import DependencyGraphBuilder
from mcp_1c.engines.code.parser import BslParser
from mcp_1c.domain.code import DependencyGraph, CodeLocation


@pytest.fixture
def builder() -> DependencyGraphBuilder:
    """Create dependency graph builder."""
    return DependencyGraphBuilder()


@pytest.fixture
def sample_bsl_code() -> str:
    """Sample BSL code for testing dependencies."""
    return '''
&НаСервере
Функция ПолучитьДанные(Параметр) Экспорт

    Результат = ОбработатьДанные(Параметр);
    Справочники.Номенклатура.НайтиПоКоду(Параметр);

    Возврат Результат;

КонецФункции

&НаСервере
Функция ОбработатьДанные(Данные)

    Возврат ПреобразоватьДанные(Данные);

КонецФункции

&НаСервере
Функция ПреобразоватьДанные(Данные)

    Возврат Строка(Данные);

КонецФункции
'''


class TestDependencyGraph:
    """Tests for DependencyGraph model."""

    def test_add_node(self):
        """Test adding nodes to graph."""
        graph = DependencyGraph()

        graph.add_node("proc1", "procedure", {"name": "Процедура1"})
        graph.add_node("proc2", "procedure", {"name": "Процедура2"})

        assert len(graph.nodes) == 2
        assert "proc1" in graph.nodes
        assert graph.nodes["proc1"]["type"] == "procedure"

    def test_add_edge(self):
        """Test adding edges to graph."""
        graph = DependencyGraph()

        graph.add_node("proc1", "procedure")
        graph.add_node("proc2", "procedure")

        location = CodeLocation(file_path=Path("test.bsl"), line=10)
        graph.add_edge("proc1", "proc2", "calls", location)

        assert len(graph.edges) == 1
        assert graph.edges[0].source == "proc1"
        assert graph.edges[0].target == "proc2"
        assert graph.edges[0].edge_type == "calls"
        assert graph.edges[0].count == 1

    def test_add_edge_increments_count(self):
        """Test that adding same edge increments count."""
        graph = DependencyGraph()

        graph.add_edge("proc1", "proc2", "calls")
        graph.add_edge("proc1", "proc2", "calls")
        graph.add_edge("proc1", "proc2", "calls")

        assert len(graph.edges) == 1
        assert graph.edges[0].count == 3

    def test_get_callees(self):
        """Test getting callees of a node."""
        graph = DependencyGraph()

        graph.add_edge("proc1", "proc2", "calls")
        graph.add_edge("proc1", "proc3", "calls")
        graph.add_edge("proc2", "proc4", "calls")

        callees = graph.get_callees("proc1")

        assert len(callees) == 2
        assert "proc2" in callees
        assert "proc3" in callees

    def test_get_callers(self):
        """Test getting callers of a node."""
        graph = DependencyGraph()

        graph.add_edge("proc1", "proc3", "calls")
        graph.add_edge("proc2", "proc3", "calls")

        callers = graph.get_callers("proc3")

        assert len(callers) == 2
        assert "proc1" in callers
        assert "proc2" in callers

    def test_get_dependencies(self):
        """Test getting dependency tree."""
        graph = DependencyGraph()

        graph.add_edge("proc1", "proc2", "calls")
        graph.add_edge("proc2", "proc3", "calls")

        deps = graph.get_dependencies("proc1", depth=2)

        assert deps["node"] == "proc1"
        assert len(deps["callees"]) == 1
        assert deps["callees"][0]["node"] == "proc2"


class TestDependencyGraphBuilder:
    """Tests for DependencyGraphBuilder."""

    @pytest.mark.asyncio
    async def test_build_from_module(self, builder: DependencyGraphBuilder, sample_bsl_code: str):
        """Test building graph from parsed module."""
        # Parse the code
        parser = BslParser()
        module = parser.parse_content_extended(sample_bsl_code)

        # Build graph
        graph = await builder.build_from_module(module)

        # Check nodes: should have at least 3 procedures
        assert len(graph.nodes) >= 3

        # Check edges (procedure calls)
        call_edges = [e for e in graph.edges if e.edge_type == "calls"]
        assert len(call_edges) >= 2  # ПолучитьДанные->ОбработатьДанные and ОбработатьДанные->ПреобразоватьДанные

    @pytest.mark.asyncio
    async def test_build_detects_procedure_calls(
        self, builder: DependencyGraphBuilder, sample_bsl_code: str
    ):
        """Test that procedure calls are detected."""
        parser = BslParser()
        module = parser.parse_content_extended(sample_bsl_code)
        graph = await builder.build_from_module(module)

        # Find call from ПолучитьДанные to ОбработатьДанные
        found_call = False
        for edge in graph.edges:
            if (
                "ПолучитьДанные" in edge.source
                and "ОбработатьДанные" in edge.target
                and edge.edge_type == "calls"
            ):
                found_call = True
                break

        assert found_call, "Call from ПолучитьДанные to ОбработатьДанные not found"

    @pytest.mark.asyncio
    async def test_build_detects_metadata_references(
        self, builder: DependencyGraphBuilder, sample_bsl_code: str
    ):
        """Test that metadata references are detected."""
        parser = BslParser()
        module = parser.parse_content_extended(sample_bsl_code)
        graph = await builder.build_from_module(module)

        # Find metadata usage edges
        metadata_edges = [e for e in graph.edges if e.edge_type == "uses_metadata"]

        # Should have metadata reference to Справочники.Номенклатура
        assert len(metadata_edges) > 0

        metadata_targets = {e.target for e in metadata_edges}
        assert any("Номенклатура" in target for target in metadata_targets)

    @pytest.mark.asyncio
    async def test_get_statistics(self, builder: DependencyGraphBuilder, sample_bsl_code: str):
        """Test graph statistics."""
        parser = BslParser()
        module = parser.parse_content_extended(sample_bsl_code)
        graph = await builder.build_from_module(module)

        stats = await builder.get_statistics(graph)

        assert "total_nodes" in stats
        assert "procedures" in stats
        assert "total_edges" in stats
        assert "call_edges" in stats

        assert stats["total_nodes"] >= 3
        assert stats["procedures"] >= 3
        assert stats["total_edges"] >= 2
        assert stats["call_edges"] >= 2


class TestGraphPersistence:
    """Tests for SQLite persistence (optional)."""

    @pytest.mark.asyncio
    async def test_save_and_load_graph(self, tmp_path: Path):
        """Test saving and loading graph from SQLite."""
        cache_path = tmp_path / "deps.db"
        builder = DependencyGraphBuilder(cache_path=cache_path)

        # Initialize cache
        await builder.init_cache()

        # Create a simple graph
        graph = DependencyGraph()
        graph.add_node("proc1", "procedure", {"name": "Процедура1"})
        graph.add_node("proc2", "procedure", {"name": "Процедура2"})

        location = CodeLocation(file_path=Path("test.bsl"), line=10)
        graph.add_edge("proc1", "proc2", "calls", location)

        # Save graph
        await builder.save_graph(graph)

        # Load graph
        loaded_graph = await builder.load_graph()

        # Verify
        assert len(loaded_graph.nodes) == 2
        assert len(loaded_graph.edges) == 1
        assert loaded_graph.edges[0].source == "proc1"
        assert loaded_graph.edges[0].target == "proc2"
