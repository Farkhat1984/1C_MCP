"""Integration tests against a real bsl-language-server JVM.

Gated behind ``pytest -m lsp`` so the ordinary unit suite stays
fast and JAR-free. To run:

::

    mcp-1c-install-bsl-ls           # one-time
    pytest -m lsp tests/integration/test_lsp_real.py

These tests prove the LSP foundation actually works end-to-end:
JAR resolved, server starts, ``initialize`` handshake completes,
``did_open`` + ``documentSymbol`` round-trip for real BSL.

When BSL-LS is not installed, every test self-skips. CI never
fails because of a missing jar.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import pytest_asyncio

from mcp_1c.engines.code.engine import CodeEngine
from mcp_1c.engines.code.lsp.server_manager import (
    BslLspServerManager,
    BslLspUnavailable,
)


def _bsl_ls_available() -> bool:
    """Return True when the JAR is on disk in the conventional location.

    We don't probe the JVM here — that's the manager's job. We only
    decide whether to attempt the test at all.
    """
    if os.environ.get("MCP_BSL_LS_DISABLED", "").lower() in ("1", "true", "yes"):
        return False
    env = os.environ.get("MCP_BSL_LS_JAR")
    if env and Path(env).exists():
        return True
    cache = Path.home() / ".cache" / "mcp-1c" / "bsl-language-server.jar"
    return cache.exists()


pytestmark = [
    pytest.mark.lsp,
    pytest.mark.skipif(
        not _bsl_ls_available(),
        reason="bsl-language-server.jar not installed; run mcp-1c-install-bsl-ls",
    ),
]


@pytest_asyncio.fixture
async def fresh_engine() -> CodeEngine:
    """A CodeEngine isolated from the singleton pool, with LSP shut
    down on teardown."""
    import contextlib

    engine = CodeEngine()
    yield engine
    with contextlib.suppress(Exception):
        await engine.shutdown_lsp()


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_server_manager_can_start_and_stop_real_server() -> None:
    """End-to-end: spawn JVM, complete initialize, shut down cleanly."""
    manager = BslLspServerManager(healthcheck_interval=0)
    try:
        client = await manager.start()
        assert client.is_initialized
    finally:
        await manager.stop()


@pytest.mark.asyncio
async def test_server_manager_handles_disabled_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Env-disable bypasses even when JAR exists. Belt-and-suspenders for
    operators who want LSP off without uninstalling the JAR."""
    monkeypatch.setenv("MCP_BSL_LS_DISABLED", "1")
    manager = BslLspServerManager(healthcheck_interval=0)
    with pytest.raises(BslLspUnavailable):
        await manager.start()


# ---------------------------------------------------------------------------
# CodeEngine.get_procedures_lsp on real BSL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lsp_extracts_procedures_from_real_bsl(
    fresh_engine: CodeEngine, tmp_path: Path
) -> None:
    """Three procedures, mixed Procedure/Function/Export — LSP must
    enumerate all three with correct flags."""
    bsl = tmp_path / "module.bsl"
    bsl.write_text(
        """Процедура Раз() Экспорт
КонецПроцедуры

Процедура Два()
КонецПроцедуры

Функция Три(Знач Параметр)
    Возврат Параметр;
КонецФункции
""",
        encoding="utf-8",
    )

    procs = await fresh_engine.get_procedures_lsp(bsl)
    assert procs is not None  # LSP reachable
    names = {p.name for p in procs}
    assert names == {"Раз", "Два", "Три"}
    by_name = {p.name: p for p in procs}
    assert by_name["Три"].is_function is True
    assert by_name["Раз"].is_export is True
    assert by_name["Два"].is_export is False


@pytest.mark.asyncio
async def test_lsp_handles_escaped_quotes_correctly(
    fresh_engine: CodeEngine, tmp_path: Path
) -> None:
    """The regex parser miscounts when strings contain ``""`` escapes —
    LSP must not. This is one of the documented audit findings the
    LSP migration is meant to fix.
    """
    bsl = tmp_path / "tricky.bsl"
    bsl.write_text(
        '''Процедура До()
    Сообщение = "Quote: ""inside""";
КонецПроцедуры

Процедура После()
КонецПроцедуры
''',
        encoding="utf-8",
    )

    procs = await fresh_engine.get_procedures_lsp(bsl)
    assert procs is not None
    names = {p.name for p in procs}
    # The regex parser may or may not survive this; LSP must.
    assert "До" in names
    assert "После" in names


@pytest.mark.asyncio
async def test_lsp_extracts_function_with_constructor_default(
    fresh_engine: CodeEngine, tmp_path: Path
) -> None:
    """Default values containing constructor calls — regex pattern
    stops at the first inner ``)``, LSP handles them correctly.

    We use ``Новый Массив`` rather than ``Тип("Строка")`` because
    bsl-language-server 0.29.0 has a bug where a *function-call*
    default value (any ``Имя(...)`` form) makes ``documentSymbol``
    return an empty list. ``Новый`` is a constructor keyword, not a
    function call, and works fine. The bug is documented in
    :func:`test_lsp_bug_function_call_in_default_xfail`.
    """
    bsl = tmp_path / "params.bsl"
    bsl.write_text(
        """Функция Сложить(Знач Список = Новый Массив)
    Возврат Список;
КонецФункции
""",
        encoding="utf-8",
    )

    procs = await fresh_engine.get_procedures_lsp(bsl)
    assert procs is not None
    assert len(procs) == 1
    assert procs[0].name == "Сложить"
    assert procs[0].is_function is True


@pytest.mark.xfail(
    reason="bsl-language-server 0.29.0 bug: function-call in default value "
    "drops the symbol from documentSymbol output. Watch for fix in newer "
    "BSL-LS releases — when this xfail starts passing, remove the marker.",
    strict=False,
)
@pytest.mark.asyncio
async def test_lsp_bug_function_call_in_default_xfail(
    fresh_engine: CodeEngine, tmp_path: Path
) -> None:
    """Documented BSL-LS bug. xfail rather than skip: when the upstream
    fixes it, this test starts passing and we remove the xfail marker
    plus the workaround in the constructor-default test above."""
    bsl = tmp_path / "params.bsl"
    bsl.write_text(
        '''Функция Тест(Знач П = Тип("Строка"))
    Возврат П;
КонецФункции
''',
        encoding="utf-8",
    )

    procs = await fresh_engine.get_procedures_lsp(bsl)
    assert procs is not None
    assert len(procs) == 1
    assert procs[0].name == "Тест"


@pytest.mark.asyncio
async def test_lsp_returns_empty_list_for_empty_file(
    fresh_engine: CodeEngine, tmp_path: Path
) -> None:
    bsl = tmp_path / "empty.bsl"
    bsl.write_text("// just a comment\n", encoding="utf-8")
    procs = await fresh_engine.get_procedures_lsp(bsl)
    assert procs is not None  # not None — file was parseable
    assert procs == []


# ---------------------------------------------------------------------------
# Cross-validation: LSP vs regex
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lsp_and_regex_agree_on_simple_input(
    fresh_engine: CodeEngine, tmp_path: Path
) -> None:
    """On the happy path (no escaped quotes, no nested parens in
    defaults), the two parsers should produce the same procedure list.

    Differences on adversarial inputs are documented; the simple-input
    test pins the equivalence so a regression in either path surfaces
    here, not in production.
    """
    from mcp_1c.engines.code.parser import BslParser

    bsl = tmp_path / "happy.bsl"
    bsl.write_text(
        """Процедура А() Экспорт
КонецПроцедуры

Функция Б(Знач П) Экспорт
    Возврат П;
КонецФункции
""",
        encoding="utf-8",
    )
    lsp_procs = await fresh_engine.get_procedures_lsp(bsl)
    regex_procs = (await BslParser().parse_file(bsl)).procedures
    assert lsp_procs is not None
    assert {p.name for p in lsp_procs} == {p.name for p in regex_procs}


@pytest.mark.asyncio
async def test_get_procedures_returns_lsp_when_available(
    fresh_engine: CodeEngine, tmp_path: Path
) -> None:
    """``CodeEngine.get_procedures(path)`` is the LSP-first wrapper —
    callers should get LSP output and never see a None."""
    bsl = tmp_path / "x.bsl"
    bsl.write_text("Процедура Х() КонецПроцедуры\n", encoding="utf-8")
    procs = await fresh_engine.get_procedures(bsl)
    assert procs  # always returns a list, never None
    assert procs[0].name == "Х"
