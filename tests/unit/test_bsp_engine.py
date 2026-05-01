"""Unit tests for the BSP knowledge engine."""

from __future__ import annotations

import pytest

from mcp_1c.engines.bsp.engine import BspEngine


@pytest.fixture
def engine() -> BspEngine:
    # Reset singleton between tests
    BspEngine._instance = None
    eng = BspEngine.get_instance()
    eng._ensure_loaded()
    return eng


def test_loads_modules(engine: BspEngine) -> None:
    modules = engine.list_modules()
    names = {m.name for m in modules}
    assert "ОбщегоНазначения" in names
    assert "УправлениеПечатью" in names
    assert "Пользователи" in names


def test_module_lookup(engine: BspEngine) -> None:
    m = engine.get_module("ОбщегоНазначения")
    assert m is not None
    assert m.kind == "Server"
    proc_names = {p.name for p in m.procedures}
    assert "ЗначениеРеквизитаОбъекта" in proc_names


def test_find_returns_modules_and_procedures(engine: BspEngine) -> None:
    results = engine.find("печать")
    kinds = {r["kind"] for r in results}
    assert "module" in kinds  # УправлениеПечатью should match
    names = [r.get("name", "") for r in results]
    assert any("УправлениеПечатью" in n for n in names) or any(
        "печать" in n.lower() for n in names
    )


def test_find_returns_hooks(engine: BspEngine) -> None:
    results = engine.find("обновлен")
    assert any(r["kind"] == "hook" for r in results)


def test_get_hook(engine: BspEngine) -> None:
    h = engine.get_hook("ПриДобавленииОбработчиковОбновления")
    assert h is not None
    assert "ОбновлениеИнформационнойБазы" in h.template


def test_review_flags_current_date(engine: BspEngine) -> None:
    code = "Дата = ТекущаяДата();"
    findings = engine.review_code(code)
    assert any(f["rule"] == "BSP_TIMEZONE" for f in findings)


def test_filter_by_tag(engine: BspEngine) -> None:
    server_only = engine.list_modules(tag="server")
    assert all("server" in m.tags for m in server_only)
    assert any(m.name == "ОбщегоНазначения" for m in server_only)
