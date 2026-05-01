"""Extension graph edges (Phase F2).

Verifies that ``KnowledgeGraphEngine._extract_extension_edges`` lifts
``ExtensionEngine`` discoveries into first-class graph nodes/edges and
that ``GraphImpactTool`` surfaces them under
``overridden_by_extensions``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_1c.domain.extension import (
    AdoptionMode,
    Extension,
    ExtensionObject,
    ExtensionPurpose,
)
from mcp_1c.domain.graph import KnowledgeGraph, RelationshipType
from mcp_1c.engines.knowledge_graph.engine import KnowledgeGraphEngine


def _make_extension(
    name: str,
    objects: list[ExtensionObject],
    purpose: ExtensionPurpose = ExtensionPurpose.ADD_ON,
) -> Extension:
    return Extension(
        name=name,
        purpose=purpose,
        target_configuration="МойКонфиг",
        namespace="Префикс",
        config_path=Path("/tmp/fake-extension"),
        objects=objects,
    )


@pytest.mark.asyncio
async def test_extract_extension_edges_emits_extension_nodes(
    tmp_path: Path,
) -> None:
    """Each discovered extension shows up as a graph node + EXTENSION_OWNS edges."""
    ext = _make_extension(
        "МояДоработка",
        [
            ExtensionObject(
                metadata_type="Catalog",
                name="Контрагенты",
                mode=AdoptionMode.ADOPTED,
                parent="Контрагенты",
            ),
            ExtensionObject(
                metadata_type="CommonModule",
                name="МоиОбщие",
                mode=AdoptionMode.OWN,
            ),
        ],
    )
    graph = KnowledgeGraph()
    # The original Catalog.Контрагенты must already be in the graph for
    # adoption resolution.
    graph.nodes["Catalog.Контрагенты"] = MagicMock(id="Catalog.Контрагенты")

    fake_ext_engine = MagicMock()
    fake_ext_engine._main_path = tmp_path  # truthy → enumeration runs
    fake_ext_engine.list_extensions = AsyncMock(return_value=["МояДоработка"])
    fake_ext_engine.get = AsyncMock(return_value=ext)

    engine = KnowledgeGraphEngine()
    with patch(
        "mcp_1c.engines.extensions.ExtensionEngine.get_instance",
        return_value=fake_ext_engine,
    ):
        await engine._extract_extension_edges(graph)

    # Extension node + 2 ExtensionObject nodes.
    assert "Extension.МояДоработка" in graph.nodes
    assert "ExtensionObject.МояДоработка.Catalog.Контрагенты" in graph.nodes
    assert "ExtensionObject.МояДоработка.CommonModule.МоиОбщие" in graph.nodes
    # EXTENSION_OWNS for both contributed objects.
    owns = [
        e for e in graph.edges
        if e.relationship == RelationshipType.EXTENSION_OWNS
    ]
    assert len(owns) == 2


@pytest.mark.asyncio
async def test_adopted_object_links_to_main_config_target(
    tmp_path: Path,
) -> None:
    ext = _make_extension(
        "X",
        [
            ExtensionObject(
                metadata_type="Catalog",
                name="Контрагенты",
                mode=AdoptionMode.ADOPTED,
                parent="Контрагенты",
            )
        ],
    )
    graph = KnowledgeGraph()
    graph.nodes["Catalog.Контрагенты"] = MagicMock(id="Catalog.Контрагенты")

    fake_ext_engine = MagicMock()
    fake_ext_engine._main_path = tmp_path
    fake_ext_engine.list_extensions = AsyncMock(return_value=["X"])
    fake_ext_engine.get = AsyncMock(return_value=ext)

    engine = KnowledgeGraphEngine()
    with patch(
        "mcp_1c.engines.extensions.ExtensionEngine.get_instance",
        return_value=fake_ext_engine,
    ):
        await engine._extract_extension_edges(graph)

    adopts = [
        e for e in graph.edges
        if e.relationship == RelationshipType.EXTENSION_ADOPTS
    ]
    assert len(adopts) == 1
    assert adopts[0].target == "Catalog.Контрагенты"
    assert adopts[0].source == "ExtensionObject.X.Catalog.Контрагенты"


@pytest.mark.asyncio
async def test_replaced_object_emits_extension_replaces_edge(
    tmp_path: Path,
) -> None:
    ext = _make_extension(
        "Y",
        [
            ExtensionObject(
                metadata_type="CommonModule",
                name="ОбщегоНазначения",
                mode=AdoptionMode.REPLACED,
                parent="ОбщегоНазначения",
            )
        ],
    )
    graph = KnowledgeGraph()
    graph.nodes["CommonModule.ОбщегоНазначения"] = MagicMock(
        id="CommonModule.ОбщегоНазначения"
    )

    fake_ext_engine = MagicMock()
    fake_ext_engine._main_path = tmp_path
    fake_ext_engine.list_extensions = AsyncMock(return_value=["Y"])
    fake_ext_engine.get = AsyncMock(return_value=ext)

    engine = KnowledgeGraphEngine()
    with patch(
        "mcp_1c.engines.extensions.ExtensionEngine.get_instance",
        return_value=fake_ext_engine,
    ):
        await engine._extract_extension_edges(graph)

    replaces = [
        e for e in graph.edges
        if e.relationship == RelationshipType.EXTENSION_REPLACES
    ]
    assert len(replaces) == 1
    assert replaces[0].target == "CommonModule.ОбщегоНазначения"


@pytest.mark.asyncio
async def test_unknown_main_target_does_not_emit_edge(tmp_path: Path) -> None:
    """If the main-config target isn't in the graph, the adoption edge
    is dropped — we never invent the original node."""
    ext = _make_extension(
        "Z",
        [
            ExtensionObject(
                metadata_type="Catalog",
                name="ОтсутствующийСправочник",
                mode=AdoptionMode.ADOPTED,
                parent="ОтсутствующийСправочник",
            )
        ],
    )
    graph = KnowledgeGraph()  # main config has nothing in it

    fake_ext_engine = MagicMock()
    fake_ext_engine._main_path = tmp_path
    fake_ext_engine.list_extensions = AsyncMock(return_value=["Z"])
    fake_ext_engine.get = AsyncMock(return_value=ext)

    engine = KnowledgeGraphEngine()
    with patch(
        "mcp_1c.engines.extensions.ExtensionEngine.get_instance",
        return_value=fake_ext_engine,
    ):
        await engine._extract_extension_edges(graph)

    adopts = [
        e for e in graph.edges
        if e.relationship == RelationshipType.EXTENSION_ADOPTS
    ]
    assert adopts == []
    # But the extension itself + its object node must still exist —
    # downstream tools may want to surface "this extension exists".
    assert "Extension.Z" in graph.nodes


@pytest.mark.asyncio
async def test_no_extensions_when_engine_unattached() -> None:
    """When ExtensionEngine has no main_path bound, _extract is a no-op."""
    graph = KnowledgeGraph()

    fake_ext_engine = MagicMock()
    fake_ext_engine._main_path = None
    fake_ext_engine.list_extensions = AsyncMock(side_effect=AssertionError(
        "should not be called"
    ))

    engine = KnowledgeGraphEngine()
    with patch(
        "mcp_1c.engines.extensions.ExtensionEngine.get_instance",
        return_value=fake_ext_engine,
    ):
        await engine._extract_extension_edges(graph)

    assert graph.nodes == {}
    fake_ext_engine.list_extensions.assert_not_called()


# ---------------------------------------------------------------------------
# GraphImpactTool — overridden_by_extensions section
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graph_impact_surfaces_extension_overrides() -> None:
    """When a node is adopted/replaced, GraphImpactTool returns that fact."""
    from mcp_1c.domain.graph import GraphEdge, GraphNode
    from mcp_1c.tools.graph_tools import GraphImpactTool

    graph = KnowledgeGraph()
    graph.add_node(GraphNode(id="Catalog.Контрагенты", node_type="Catalog", name="Контрагенты"))
    graph.add_node(
        GraphNode(
            id="ExtensionObject.МояДоработка.Catalog.Контрагенты",
            node_type="ExtensionObject",
            name="Контрагенты",
            metadata={"extension": "МояДоработка", "mode": "Adopted"},
        )
    )
    graph.add_edge(
        GraphEdge(
            source="ExtensionObject.МояДоработка.Catalog.Контрагенты",
            target="Catalog.Контрагенты",
            relationship=RelationshipType.EXTENSION_ADOPTS,
            label="заимствование",
        )
    )

    fake_kg = MagicMock()
    fake_kg.get_impact = AsyncMock(
        return_value={"node_id": "Catalog.Контрагенты", "total_impacted": 0, "levels": {}}
    )
    fake_kg._load_or_fail = AsyncMock(return_value=graph)

    tool = GraphImpactTool(fake_kg)
    result = await tool.execute({"node_id": "Catalog.Контрагенты"})
    assert "overridden_by_extensions" in result
    assert result["overridden_by_extensions"][0]["extension"] == "МояДоработка"
    assert result["overridden_by_extensions"][0]["mode"] == "Adopted"


@pytest.mark.asyncio
async def test_graph_impact_omits_overrides_when_none() -> None:
    """Clean nodes don't get a ``overridden_by_extensions`` key — keeps
    typical responses small."""
    from mcp_1c.tools.graph_tools import GraphImpactTool

    graph = KnowledgeGraph()
    graph.nodes["Catalog.X"] = MagicMock(id="Catalog.X")

    fake_kg = MagicMock()
    fake_kg.get_impact = AsyncMock(
        return_value={"node_id": "Catalog.X", "total_impacted": 0, "levels": {}}
    )
    fake_kg._load_or_fail = AsyncMock(return_value=graph)

    tool = GraphImpactTool(fake_kg)
    result = await tool.execute({"node_id": "Catalog.X"})
    assert "overridden_by_extensions" not in result
