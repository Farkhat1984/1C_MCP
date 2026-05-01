"""SmartPrint/SmartMovement surface extension overrides as warnings.

When a typical-config object is заимствован or замещён by an
extension, smart-tool output must point that out — editing the
typical source directly is the wrong action in 1С. We verify both
shapes (dict-payload and string-payload) get the warning,
preserving any pre-existing ``warnings`` field.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_1c.domain.graph import (
    GraphEdge,
    GraphNode,
    KnowledgeGraph,
    RelationshipType,
)
from mcp_1c.engines.validation import ValidationResult
from mcp_1c.tools.smart_tools import (
    SmartMovementTool,
    SmartPrintTool,
    _extension_warnings_for,
)


def _kg_with_override(target: str, ext_name: str, mode: str) -> KnowledgeGraph:
    graph = KnowledgeGraph()
    graph.add_node(GraphNode(id=target, node_type="Document", name=target.split(".")[-1]))
    ext_obj_id = f"ExtensionObject.{ext_name}.{target}"
    graph.add_node(
        GraphNode(
            id=ext_obj_id,
            node_type="ExtensionObject",
            name=target.split(".")[-1],
            metadata={"extension": ext_name, "mode": mode},
        )
    )
    rel = (
        RelationshipType.EXTENSION_ADOPTS
        if mode == "Adopted"
        else RelationshipType.EXTENSION_REPLACES
    )
    graph.add_edge(
        GraphEdge(
            source=ext_obj_id,
            target=target,
            relationship=rel,
            label="override",
        )
    )
    return graph


# ---------------------------------------------------------------------------
# _extension_warnings_for
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extension_warnings_returns_messages_for_adopted_object() -> None:
    graph = _kg_with_override("Document.РеализацияТоваров", "МояДоработка", "Adopted")
    fake_kg = MagicMock()
    fake_kg._load_or_fail = AsyncMock(return_value=graph)
    with patch(
        "mcp_1c.engines.knowledge_graph.engine.KnowledgeGraphEngine.get_instance",
        return_value=fake_kg,
    ):
        warnings = await _extension_warnings_for("Document.РеализацияТоваров")
    assert len(warnings) == 1
    assert "заимствован в расширении" in warnings[0]
    assert "МояДоработка" in warnings[0]


@pytest.mark.asyncio
async def test_extension_warnings_returns_messages_for_replaced_object() -> None:
    graph = _kg_with_override("CommonModule.ОбщегоНазначения", "МояДоработка", "Replaced")
    fake_kg = MagicMock()
    fake_kg._load_or_fail = AsyncMock(return_value=graph)
    with patch(
        "mcp_1c.engines.knowledge_graph.engine.KnowledgeGraphEngine.get_instance",
        return_value=fake_kg,
    ):
        warnings = await _extension_warnings_for("CommonModule.ОбщегоНазначения")
    assert len(warnings) == 1
    assert "замещён в расширении" in warnings[0]


@pytest.mark.asyncio
async def test_extension_warnings_empty_for_clean_object() -> None:
    fake_kg = MagicMock()
    fake_kg._load_or_fail = AsyncMock(return_value=KnowledgeGraph())
    with patch(
        "mcp_1c.engines.knowledge_graph.engine.KnowledgeGraphEngine.get_instance",
        return_value=fake_kg,
    ):
        warnings = await _extension_warnings_for("Catalog.Чистый")
    assert warnings == []


@pytest.mark.asyncio
async def test_extension_warnings_skips_when_kg_unavailable() -> None:
    """KG not built → no warnings, no exception."""
    fake_kg = MagicMock()
    fake_kg._load_or_fail = AsyncMock(side_effect=RuntimeError("not built"))
    with patch(
        "mcp_1c.engines.knowledge_graph.engine.KnowledgeGraphEngine.get_instance",
        return_value=fake_kg,
    ):
        warnings = await _extension_warnings_for("Document.X")
    assert warnings == []


@pytest.mark.asyncio
async def test_extension_warnings_skips_malformed_object_name() -> None:
    """A name without ``.`` is invalid; we don't ask KG."""
    warnings = await _extension_warnings_for("Контрагенты")  # missing Type prefix
    assert warnings == []


# ---------------------------------------------------------------------------
# SmartPrintTool integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smart_print_attaches_extension_warning() -> None:
    tool = SmartPrintTool()
    artefacts = {"print_procedure": "Функция Печать() Экспорт КонецФункции"}
    graph = _kg_with_override("Document.Реализация", "Расш1", "Adopted")
    fake_kg = MagicMock()
    fake_kg._load_or_fail = AsyncMock(return_value=graph)

    with patch("mcp_1c.tools.smart_tools.SmartGenerator") as mock_gen, patch(
        "mcp_1c.tools.smart_tools.validate_bsl",
        new=AsyncMock(
            return_value=ValidationResult(validated=True, backend="lsp")
        ),
    ), patch(
        "mcp_1c.engines.knowledge_graph.engine.KnowledgeGraphEngine.get_instance",
        return_value=fake_kg,
    ):
        mock_gen.get_instance.return_value.generate_print_form = AsyncMock(
            return_value=artefacts
        )
        result = await tool.execute({"object_name": "Document.Реализация"})

    assert "warnings" in result
    assert any("Расш1" in w for w in result["warnings"])


@pytest.mark.asyncio
async def test_smart_print_merges_existing_warnings() -> None:
    """Generator-emitted warnings must not be lost when extension warnings
    are appended."""
    tool = SmartPrintTool()
    artefacts = {
        "print_procedure": "Функция X() КонецФункции",
        "warnings": ["Поле X не имеет синонима"],
    }
    graph = _kg_with_override("Document.Y", "Расш", "Adopted")
    fake_kg = MagicMock()
    fake_kg._load_or_fail = AsyncMock(return_value=graph)

    with patch("mcp_1c.tools.smart_tools.SmartGenerator") as mock_gen, patch(
        "mcp_1c.tools.smart_tools.validate_bsl",
        new=AsyncMock(return_value=ValidationResult(validated=True, backend="lsp")),
    ), patch(
        "mcp_1c.engines.knowledge_graph.engine.KnowledgeGraphEngine.get_instance",
        return_value=fake_kg,
    ):
        mock_gen.get_instance.return_value.generate_print_form = AsyncMock(
            return_value=artefacts
        )
        result = await tool.execute({"object_name": "Document.Y"})

    assert len(result["warnings"]) == 2
    assert "не имеет синонима" in result["warnings"][0]
    assert "Расш" in result["warnings"][1]


# ---------------------------------------------------------------------------
# SmartMovementTool integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smart_movement_warns_when_either_target_is_overridden() -> None:
    """Movement touches both document and register; either being
    overridden warrants a warning."""
    tool = SmartMovementTool()
    graph = _kg_with_override("AccumulationRegister.Остатки", "ExtA", "Replaced")
    fake_kg = MagicMock()
    fake_kg._load_or_fail = AsyncMock(return_value=graph)

    with patch("mcp_1c.tools.smart_tools.SmartGenerator") as mock_gen, patch(
        "mcp_1c.tools.smart_tools.validate_bsl",
        new=AsyncMock(return_value=ValidationResult(validated=True, backend="lsp")),
    ), patch(
        "mcp_1c.engines.knowledge_graph.engine.KnowledgeGraphEngine.get_instance",
        return_value=fake_kg,
    ):
        mock_gen.get_instance.return_value.generate_movement = AsyncMock(
            return_value="Процедура ОбработкаПроведения() КонецПроцедуры"
        )
        result = await tool.execute(
            {
                "document_name": "Document.Х",
                "register_name": "AccumulationRegister.Остатки",
            }
        )

    assert isinstance(result, dict)
    assert "warnings" in result
    assert any("замещён" in w for w in result["warnings"])
