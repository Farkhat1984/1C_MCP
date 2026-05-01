"""Adapter from LSP DocumentSymbol payloads to our Procedure model.

bsl-language-server JAR isn't required to run these — we feed in
hand-crafted DocumentSymbol dicts that mirror its actual shape (verified
against bsl-language-server v0.24).
"""

from __future__ import annotations

from mcp_1c.engines.code.lsp.adapter import (
    SYMBOL_KIND_FUNCTION,
    SYMBOL_KIND_METHOD,
    lsp_symbols_to_procedures,
)


def _symbol(
    name: str,
    *,
    kind: int = SYMBOL_KIND_METHOD,
    detail: str = "",
    start: int = 0,
    end: int = 5,
    children: list | None = None,
) -> dict:
    return {
        "name": name,
        "kind": kind,
        "detail": detail,
        "range": {
            "start": {"line": start, "character": 0},
            "end": {"line": end, "character": 0},
        },
        "selectionRange": {
            "start": {"line": start, "character": 0},
            "end": {"line": start, "character": len(name)},
        },
        "children": children or [],
    }


def test_flat_list_of_procedures() -> None:
    payload = [
        _symbol("ОбработкаВыбора", detail="Procedure", start=10, end=20),
        _symbol("ВычислитьСумму", detail="Function", start=30, end=40),
    ]
    procs = lsp_symbols_to_procedures(payload)
    assert [p.name for p in procs] == ["ОбработкаВыбора", "ВычислитьСумму"]
    assert procs[0].is_function is False
    assert procs[1].is_function is True


def test_function_kind_overrides_detail_string() -> None:
    """LSP SymbolKind=Function must always map to is_function=True."""
    payload = [_symbol("F", kind=SYMBOL_KIND_FUNCTION, detail="")]
    procs = lsp_symbols_to_procedures(payload)
    assert procs[0].is_function is True


def test_export_extracted_from_detail() -> None:
    payload = [_symbol("X", detail="Procedure (Export)")]
    procs = lsp_symbols_to_procedures(payload)
    assert procs[0].is_export is True


def test_lines_one_indexed() -> None:
    """LSP is 0-indexed; our Procedure model is 1-indexed."""
    payload = [_symbol("X", start=4, end=9)]
    procs = lsp_symbols_to_procedures(payload)
    assert procs[0].start_line == 5
    assert procs[0].end_line == 10


def test_skips_non_method_kinds() -> None:
    """Variables, constants, etc. must not appear as procedures."""
    payload = [
        _symbol("СтараяПеременная", kind=14, start=1, end=1),  # Variable
        _symbol("Метод", kind=SYMBOL_KIND_METHOD, start=2, end=8),
    ]
    procs = lsp_symbols_to_procedures(payload)
    assert [p.name for p in procs] == ["Метод"]


def test_recurses_into_children() -> None:
    """When the server nests symbols (e.g. inside a region), unwrap."""
    inner = _symbol("Внутренний", start=12, end=14)
    outer = {
        "name": "ОбластьПубличногоИнтерфейса",
        "kind": 19,  # Namespace — region
        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 20, "character": 0}},
        "selectionRange": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 5}},
        "children": [inner],
    }
    procs = lsp_symbols_to_procedures([outer])
    assert [p.name for p in procs] == ["Внутренний"]


def test_parses_simple_parameters_from_detail() -> None:
    payload = [_symbol("Сложить", detail="Function (Знач А, Б = 0, В) Export")]
    procs = lsp_symbols_to_procedures(payload)
    assert [p.name for p in procs[0].parameters] == ["А", "Б", "В"]
    assert procs[0].parameters[0].by_value is True
    assert procs[0].parameters[1].is_optional is True
    assert procs[0].parameters[1].default_value == "0"


def test_parser_handles_nested_parens_in_default_value() -> None:
    """Default values can contain function calls — comma inside Тип("Строка")
    must not split the parameter list."""
    payload = [_symbol("X", detail='Procedure (Знач T = Тип("Строка"), Y)')]
    procs = lsp_symbols_to_procedures(payload)
    names = [p.name for p in procs[0].parameters]
    assert names == ["T", "Y"]


def test_parser_handles_typed_param() -> None:
    """Some BSL-LS builds emit "Name:Type" — strip the type annotation."""
    payload = [_symbol("X", detail="Procedure (Param:Строка)")]
    procs = lsp_symbols_to_procedures(payload)
    assert [p.name for p in procs[0].parameters] == ["Param"]


def test_skips_anonymous_symbols() -> None:
    """A symbol with empty name shouldn't blow up — just drop it."""
    payload = [_symbol("", detail="Procedure")]
    procs = lsp_symbols_to_procedures(payload)
    assert procs == []
