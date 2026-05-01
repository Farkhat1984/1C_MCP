"""KG-over-code: build extracts procedure nodes + call/ref edges.

We don't want to spin up the full MetadataEngine here — the KG
extraction logic is pure once it has parsed BSL modules. We feed it a
minimal config-tree so the regex parser produces real ExtendedBslModule
output, and inspect the resulting graph.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_1c.domain.graph import KnowledgeGraph, RelationshipType
from mcp_1c.domain.metadata import (
    MetadataObject,
    MetadataType,
    Module,
    ModuleType,
)
from mcp_1c.engines.knowledge_graph.engine import KnowledgeGraphEngine


def _make_module(path: Path, body: str) -> Module:
    path.write_text(body, encoding="utf-8")
    return Module(
        module_type=ModuleType.OBJECT_MODULE,
        path=path,
        exists=True,
    )


def _make_object(
    metadata_type: MetadataType,
    name: str,
    config_path: Path,
    object_path: Path,
    modules: list[Module] | None = None,
) -> MetadataObject:
    return MetadataObject(
        name=name,
        synonym=name,
        comment="",
        uuid="",
        metadata_type=metadata_type,
        config_path=config_path,
        object_path=object_path,
        attributes=[],
        tabular_sections=[],
        forms=[],
        modules=modules or [],
        templates=[],
        commands=[],
    )


@pytest.mark.asyncio
async def test_extract_code_edges_emits_procedure_nodes(tmp_path: Path) -> None:
    """Procedures from a BSL file appear as graph nodes with PROCEDURE_OWNERSHIP."""
    bsl = _make_module(
        tmp_path / "ObjectModule.bsl",
        """Процедура Создать() Экспорт
КонецПроцедуры

Функция Получить() Экспорт
    Возврат Истина;
КонецФункции
""",
    )
    obj = _make_object(
        MetadataType.CATALOG,
        "Контрагенты",
        config_path=tmp_path,
        object_path=tmp_path,
        modules=[bsl],
    )
    graph = KnowledgeGraph()
    graph.nodes[obj.full_name] = MagicMock(id=obj.full_name)

    engine = KnowledgeGraphEngine()
    fake_code_engine = MagicMock()  # extract uses BslParser directly
    await engine._extract_code_edges(graph, [obj], fake_code_engine)

    proc_nodes = [n for n in graph.nodes.values() if getattr(n, "node_type", "") == "Procedure"]
    assert len(proc_nodes) == 2
    assert {n.name for n in proc_nodes} == {"Создать", "Получить"}

    ownership_edges = [
        e for e in graph.edges
        if e.relationship == RelationshipType.PROCEDURE_OWNERSHIP
    ]
    assert len(ownership_edges) == 2


@pytest.mark.asyncio
async def test_same_module_calls_become_edges(tmp_path: Path) -> None:
    """Procedure A calls B in the same module → PROCEDURE_CALL edge."""
    bsl = _make_module(
        tmp_path / "ObjectModule.bsl",
        """Процедура А() Экспорт
    Б();
КонецПроцедуры

Процедура Б() Экспорт
КонецПроцедуры
""",
    )
    obj = _make_object(
        MetadataType.CATALOG,
        "X",
        config_path=tmp_path,
        object_path=tmp_path,
        modules=[bsl],
    )
    graph = KnowledgeGraph()
    graph.nodes[obj.full_name] = MagicMock(id=obj.full_name)

    engine = KnowledgeGraphEngine()
    await engine._extract_code_edges(graph, [obj], MagicMock())

    calls = [
        e for e in graph.edges
        if e.relationship == RelationshipType.PROCEDURE_CALL
    ]
    assert len(calls) == 1
    assert calls[0].source.endswith(".А")
    assert calls[0].target.endswith(".Б")


@pytest.mark.asyncio
async def test_metadata_references_become_edges(tmp_path: Path) -> None:
    """Catalog reference from BSL → CODE_METADATA_REFERENCE edge."""
    bsl = _make_module(
        tmp_path / "ObjectModule.bsl",
        """Процедура НайтиКонтрагента() Экспорт
    Объект = Справочники.Контрагенты.НайтиПоНаименованию("Тест");
КонецПроцедуры
""",
    )
    obj = _make_object(
        MetadataType.DOCUMENT,
        "РеализацияТоваров",
        config_path=tmp_path,
        object_path=tmp_path,
        modules=[bsl],
    )
    graph = KnowledgeGraph()
    graph.nodes[obj.full_name] = MagicMock(id=obj.full_name)
    # Target metadata must already exist in the graph for resolution.
    graph.nodes["Catalog.Контрагенты"] = MagicMock(id="Catalog.Контрагенты")

    engine = KnowledgeGraphEngine()
    await engine._extract_code_edges(graph, [obj], MagicMock())

    refs = [
        e for e in graph.edges
        if e.relationship == RelationshipType.CODE_METADATA_REFERENCE
    ]
    assert len(refs) == 1
    assert refs[0].target == "Catalog.Контрагенты"


@pytest.mark.asyncio
async def test_query_table_references_become_edges(tmp_path: Path) -> None:
    bsl = _make_module(
        tmp_path / "ObjectModule.bsl",
        """Процедура Загрузить() Экспорт
    Запрос = Новый Запрос("ВЫБРАТЬ * ИЗ Справочник.Контрагенты КАК К");
КонецПроцедуры
""",
    )
    obj = _make_object(
        MetadataType.DOCUMENT,
        "Х",
        config_path=tmp_path,
        object_path=tmp_path,
        modules=[bsl],
    )
    graph = KnowledgeGraph()
    graph.nodes[obj.full_name] = MagicMock(id=obj.full_name)
    graph.nodes["Catalog.Контрагенты"] = MagicMock(id="Catalog.Контрагенты")

    engine = KnowledgeGraphEngine()
    await engine._extract_code_edges(graph, [obj], MagicMock())

    query_refs = [
        e for e in graph.edges
        if e.relationship == RelationshipType.CODE_QUERY_REFERENCE
    ]
    assert len(query_refs) == 1
    assert query_refs[0].target == "Catalog.Контрагенты"


@pytest.mark.asyncio
async def test_ambiguous_cross_module_call_is_dropped(tmp_path: Path) -> None:
    """When two modules both declare ``Помощник``, calls from a third
    module to ``Помощник()`` must NOT pick one — false positives are
    worse than false negatives in code graphs."""
    a = _make_module(
        tmp_path / "a.bsl",
        "Процедура Помощник() Экспорт\nКонецПроцедуры\n",
    )
    b = _make_module(
        tmp_path / "b.bsl",
        "Процедура Помощник() Экспорт\nКонецПроцедуры\n",
    )
    caller = _make_module(
        tmp_path / "c.bsl",
        """Процедура Тест() Экспорт
    Помощник();
КонецПроцедуры
""",
    )

    objs = [
        _make_object(
            MetadataType.COMMON_MODULE, "А", tmp_path, tmp_path, modules=[a]
        ),
        _make_object(
            MetadataType.COMMON_MODULE, "Б", tmp_path, tmp_path, modules=[b]
        ),
        _make_object(
            MetadataType.COMMON_MODULE,
            "Тестовый",
            tmp_path,
            tmp_path,
            modules=[caller],
        ),
    ]
    graph = KnowledgeGraph()
    for obj in objs:
        graph.nodes[obj.full_name] = MagicMock(id=obj.full_name)

    engine = KnowledgeGraphEngine()
    await engine._extract_code_edges(graph, objs, MagicMock())

    calls = [
        e for e in graph.edges
        if e.relationship == RelationshipType.PROCEDURE_CALL
    ]
    # Same-module count: 0 (Тест calls a different module's procedure).
    # Cross-module count: 0 because the name is ambiguous.
    cross_module = [c for c in calls if not c.source.startswith(c.target.rsplit(".", 1)[0])]
    assert len(cross_module) == 0


@pytest.mark.asyncio
async def test_invalidate_node_removes_node_and_edges() -> None:
    """invalidate_node drops the node and every edge touching it."""
    engine = KnowledgeGraphEngine()
    graph = KnowledgeGraph()
    graph.add_node(MagicMock(id="A"))
    graph.add_node(MagicMock(id="B"))
    graph.add_node(MagicMock(id="C"))
    from mcp_1c.domain.graph import GraphEdge

    graph.add_edge(GraphEdge(
        source="A", target="B", relationship=RelationshipType.PROCEDURE_CALL
    ))
    graph.add_edge(GraphEdge(
        source="B", target="C", relationship=RelationshipType.PROCEDURE_CALL
    ))
    engine._graph = graph

    await engine.invalidate_node("B")
    assert "B" not in graph.nodes
    assert all(e.source != "B" and e.target != "B" for e in graph.edges)


@pytest.mark.asyncio
async def test_callers_tool_returns_incoming_calls() -> None:
    """End-to-end: GraphCallersTool reads PROCEDURE_CALL edges in incoming dir."""
    from mcp_1c.tools.graph_tools import GraphCallersTool

    engine = MagicMock()
    graph = KnowledgeGraph()
    proc_a = MagicMock(id="A.Module.x", name="x", metadata={"owner": "A"})
    proc_b = MagicMock(id="B.Module.target", name="target", metadata={"owner": "B"})
    graph.nodes = {proc_a.id: proc_a, proc_b.id: proc_b}
    from mcp_1c.domain.graph import GraphEdge

    graph.edges = [
        GraphEdge(
            source=proc_a.id,
            target=proc_b.id,
            relationship=RelationshipType.PROCEDURE_CALL,
            metadata={"line": 42},
        ),
    ]
    engine._load_or_fail = AsyncMock(return_value=graph)

    tool = GraphCallersTool(engine)
    result = await tool.execute({"node_id": proc_b.id})
    assert result["count"] == 1
    assert result["callers"][0]["line"] == 42
    assert result["callers"][0]["node_id"] == proc_a.id
