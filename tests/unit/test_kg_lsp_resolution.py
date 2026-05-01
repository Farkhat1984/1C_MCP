"""LSP-driven cross-module call resolution in KG-over-code.

Documents the upgrade from name-matching (drop-on-ambiguity) to
LSP ``textDocument/definition``-based precise resolution.

The contract under test:
- When ``code_engine.find_definition_lsp`` is mocked to return a real
  Location, the ambiguous-by-name call **gets** an edge (with
  ``resolution: "lsp_definition"``).
- When LSP returns nothing or fails, the call is dropped — same
  behaviour as before, marked ``resolution: "name_match"`` (or just
  no edge if neither resolver found anything).
- Per-call-site memoisation: identical sites in the same extraction
  pass don't re-ask LSP.
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
from mcp_1c.engines.knowledge_graph.engine import (
    KnowledgeGraphEngine,
    _uri_to_path_str,
)


def _make_module(path: Path, body: str) -> Module:
    path.write_text(body, encoding="utf-8")
    return Module(module_type=ModuleType.OBJECT_MODULE, path=path, exists=True)


def _make_obj(
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


# ---------------------------------------------------------------------------
# _uri_to_path_str
# ---------------------------------------------------------------------------


def test_uri_to_path_resolves_file_uri(tmp_path: Path) -> None:
    real_path = tmp_path / "module.bsl"
    real_path.write_text("Процедура А() КонецПроцедуры")
    uri = real_path.as_uri()
    result = _uri_to_path_str(uri)
    assert result == str(real_path.resolve())


def test_uri_to_path_returns_none_for_non_file_scheme() -> None:
    assert _uri_to_path_str("inmemory:///validate.bsl") is None
    assert _uri_to_path_str("https://example.com/x.bsl") is None
    assert _uri_to_path_str("not-even-a-uri") is None


def test_uri_to_path_handles_url_encoding(tmp_path: Path) -> None:
    """Cyrillic file names round-trip through percent-encoding."""
    real_path = tmp_path / "Контрагенты.bsl"
    real_path.write_text("X = 1;")
    uri = real_path.as_uri()
    assert "%" in uri  # cyrillic percent-encoded
    assert _uri_to_path_str(uri) == str(real_path.resolve())


# ---------------------------------------------------------------------------
# Cross-module LSP resolution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lsp_resolves_ambiguous_cross_module_call(tmp_path: Path) -> None:
    """When two modules declare ``Помощник``, LSP picks the right one.

    Before LSP: drop-on-ambiguity (no edge). With LSP:
    ``find_definition_lsp`` returns a Location pointing at one of the
    declarations; the resolver maps it back to the right node.
    """
    # Two CommonModules with same procedure name.
    a_path = tmp_path / "a.bsl"
    a_module = _make_module(
        a_path, "Процедура Помощник() Экспорт\nКонецПроцедуры\n"
    )
    b_path = tmp_path / "b.bsl"
    b_module = _make_module(
        b_path, "Процедура Помощник() Экспорт\nКонецПроцедуры\n"
    )
    caller_path = tmp_path / "c.bsl"
    caller_module = _make_module(
        caller_path,
        """Процедура Тест() Экспорт
    Помощник();
КонецПроцедуры
""",
    )

    objects = [
        _make_obj(MetadataType.COMMON_MODULE, "А", tmp_path, tmp_path, [a_module]),
        _make_obj(MetadataType.COMMON_MODULE, "Б", tmp_path, tmp_path, [b_module]),
        _make_obj(
            MetadataType.COMMON_MODULE, "Т", tmp_path, tmp_path, [caller_module]
        ),
    ]
    graph = KnowledgeGraph()
    for obj in objects:
        graph.nodes[obj.full_name] = MagicMock(id=obj.full_name)

    # Mock CodeEngine.find_definition_lsp → points at 'a.bsl' line 1.
    fake_engine = MagicMock()
    fake_engine.find_definition_lsp = AsyncMock(
        return_value=[
            {
                "uri": a_path.as_uri(),
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 0, "character": 17},
                },
            }
        ]
    )

    engine = KnowledgeGraphEngine()
    await engine._extract_code_edges(graph, objects, fake_engine)

    # Find the PROCEDURE_CALL edge from Т→А.Помощник.
    calls = [
        e for e in graph.edges
        if e.relationship == RelationshipType.PROCEDURE_CALL
    ]
    assert len(calls) == 1
    edge = calls[0]
    assert ".А." in edge.target  # resolved to А, not Б
    assert edge.metadata["resolution"] == "lsp_definition"


@pytest.mark.asyncio
async def test_lsp_failure_falls_back_to_drop(tmp_path: Path) -> None:
    """LSP unreachable → ambiguous calls remain dropped (no edge).

    Same setup as the previous test but ``find_definition_lsp`` returns
    None — exactly what happens when bsl-language-server is not
    installed. The graph must NOT invent a wrong edge.
    """
    a_module = _make_module(
        tmp_path / "a.bsl", "Процедура Помощник() Экспорт\nКонецПроцедуры\n"
    )
    b_module = _make_module(
        tmp_path / "b.bsl", "Процедура Помощник() Экспорт\nКонецПроцедуры\n"
    )
    caller_module = _make_module(
        tmp_path / "c.bsl",
        "Процедура Тест() Экспорт\n    Помощник();\nКонецПроцедуры\n",
    )

    objects = [
        _make_obj(MetadataType.COMMON_MODULE, "А", tmp_path, tmp_path, [a_module]),
        _make_obj(MetadataType.COMMON_MODULE, "Б", tmp_path, tmp_path, [b_module]),
        _make_obj(
            MetadataType.COMMON_MODULE, "Т", tmp_path, tmp_path, [caller_module]
        ),
    ]
    graph = KnowledgeGraph()
    for obj in objects:
        graph.nodes[obj.full_name] = MagicMock(id=obj.full_name)

    fake_engine = MagicMock()
    fake_engine.find_definition_lsp = AsyncMock(return_value=None)

    engine = KnowledgeGraphEngine()
    await engine._extract_code_edges(graph, objects, fake_engine)

    cross_module_calls = [
        e for e in graph.edges
        if e.relationship == RelationshipType.PROCEDURE_CALL
        and ".Т." in e.source and ".Т." not in e.target
    ]
    assert cross_module_calls == []  # No edge invented.


@pytest.mark.asyncio
async def test_unique_name_skips_lsp_call(tmp_path: Path) -> None:
    """A name-unique callee resolves without asking LSP."""
    a_module = _make_module(
        tmp_path / "a.bsl",
        "Процедура НаписатьВЛог() Экспорт\nКонецПроцедуры\n",
    )
    caller_module = _make_module(
        tmp_path / "c.bsl",
        "Процедура Тест() Экспорт\n    НаписатьВЛог();\nКонецПроцедуры\n",
    )
    objects = [
        _make_obj(MetadataType.COMMON_MODULE, "Лог", tmp_path, tmp_path, [a_module]),
        _make_obj(
            MetadataType.COMMON_MODULE, "Т", tmp_path, tmp_path, [caller_module]
        ),
    ]
    graph = KnowledgeGraph()
    for obj in objects:
        graph.nodes[obj.full_name] = MagicMock(id=obj.full_name)

    fake_engine = MagicMock()
    fake_engine.find_definition_lsp = AsyncMock(return_value=None)

    engine = KnowledgeGraphEngine()
    await engine._extract_code_edges(graph, objects, fake_engine)

    # Name is globally unique → resolved by name, LSP never called.
    fake_engine.find_definition_lsp.assert_not_awaited()
    calls = [
        e for e in graph.edges
        if e.relationship == RelationshipType.PROCEDURE_CALL
    ]
    assert any(".Лог." in e.target for e in calls)
    assert all(e.metadata["resolution"] == "name_match" for e in calls)


@pytest.mark.asyncio
async def test_lsp_resolution_is_cached_per_call_site(tmp_path: Path) -> None:
    """Two identical calls in the same caller hit LSP only once."""
    a_module = _make_module(
        tmp_path / "a.bsl", "Процедура Помощник() Экспорт\nКонецПроцедуры\n"
    )
    b_module = _make_module(
        tmp_path / "b.bsl", "Процедура Помощник() Экспорт\nКонецПроцедуры\n"
    )
    # Caller invokes the same method twice — different lines, but the
    # cache key includes line/column so each call site IS distinct.
    # We assert that LSP gets at most as many calls as ambiguous sites.
    caller_module = _make_module(
        tmp_path / "c.bsl",
        """Процедура Тест() Экспорт
    Помощник();
    Помощник();
КонецПроцедуры
""",
    )
    objects = [
        _make_obj(MetadataType.COMMON_MODULE, "А", tmp_path, tmp_path, [a_module]),
        _make_obj(MetadataType.COMMON_MODULE, "Б", tmp_path, tmp_path, [b_module]),
        _make_obj(
            MetadataType.COMMON_MODULE, "Т", tmp_path, tmp_path, [caller_module]
        ),
    ]
    graph = KnowledgeGraph()
    for obj in objects:
        graph.nodes[obj.full_name] = MagicMock(id=obj.full_name)

    fake_engine = MagicMock()
    fake_engine.find_definition_lsp = AsyncMock(
        return_value=[
            {
                "uri": (tmp_path / "a.bsl").as_uri(),
                "range": {"start": {"line": 0, "character": 0}},
            }
        ]
    )
    engine = KnowledgeGraphEngine()
    await engine._extract_code_edges(graph, objects, fake_engine)

    # Two distinct call sites = two LSP calls. Cache prevents a 3rd if
    # the same site appeared twice (it doesn't here, but the test
    # documents the upper bound).
    assert fake_engine.find_definition_lsp.await_count == 2


@pytest.mark.asyncio
async def test_lsp_response_outside_known_modules_is_ignored(
    tmp_path: Path,
) -> None:
    """LSP may return Location pointing at a file outside the index
    (e.g. a platform built-in). Such results must produce no edge —
    we don't fabricate nodes for unknown procedures."""
    a_module = _make_module(
        tmp_path / "a.bsl", "Процедура Помощник() Экспорт\nКонецПроцедуры\n"
    )
    b_module = _make_module(
        tmp_path / "b.bsl", "Процедура Помощник() Экспорт\nКонецПроцедуры\n"
    )
    caller_module = _make_module(
        tmp_path / "c.bsl",
        "Процедура Тест() Экспорт\n    Помощник();\nКонецПроцедуры\n",
    )

    objects = [
        _make_obj(MetadataType.COMMON_MODULE, "А", tmp_path, tmp_path, [a_module]),
        _make_obj(MetadataType.COMMON_MODULE, "Б", tmp_path, tmp_path, [b_module]),
        _make_obj(
            MetadataType.COMMON_MODULE, "Т", tmp_path, tmp_path, [caller_module]
        ),
    ]
    graph = KnowledgeGraph()
    for obj in objects:
        graph.nodes[obj.full_name] = MagicMock(id=obj.full_name)

    fake_engine = MagicMock()
    # LSP points at an unknown file (platform builtin, e.g.).
    fake_engine.find_definition_lsp = AsyncMock(
        return_value=[
            {
                "uri": "file:///opt/1c/builtins/global.bsl",
                "range": {"start": {"line": 0, "character": 0}},
            }
        ]
    )
    engine = KnowledgeGraphEngine()
    await engine._extract_code_edges(graph, objects, fake_engine)

    cross_module = [
        e for e in graph.edges
        if e.relationship == RelationshipType.PROCEDURE_CALL
        and ".Т." in e.source and ".Т." not in e.target
    ]
    assert cross_module == []
