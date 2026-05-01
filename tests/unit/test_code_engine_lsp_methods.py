"""find_references / find_definition contract tests.

We don't run a real BSL-LS jar — the manager and client are mocked
out. The tests assert what CodeEngine sends down to LSP (1→0 index
conversion, did_open/did_close envelope) and what it returns to the
caller (raw Location[] payload, ``None`` on unavailability).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_1c.engines.code.engine import CodeEngine
from mcp_1c.engines.code.lsp.server_manager import BslLspUnavailable


@pytest.fixture
def fresh_engine() -> CodeEngine:
    """A CodeEngine isolated from the singleton pool."""
    engine = CodeEngine()
    return engine


@pytest.mark.asyncio
async def test_find_references_returns_none_when_lsp_unavailable(
    fresh_engine: CodeEngine, tmp_path: Path
) -> None:
    fresh_engine._lsp_unavailable = True
    f = tmp_path / "x.bsl"
    f.write_text("Процедура А() КонецПроцедуры")
    assert await fresh_engine.find_references_lsp(f, 1, 1) is None


@pytest.mark.asyncio
async def test_find_references_marks_unavailable_on_first_failure(
    fresh_engine: CodeEngine, tmp_path: Path
) -> None:
    """A BslLspUnavailable on _ensure_lsp must stickily disable LSP."""
    f = tmp_path / "x.bsl"
    f.write_text("Процедура А() КонецПроцедуры")
    with patch.object(
        fresh_engine, "_ensure_lsp", AsyncMock(side_effect=BslLspUnavailable("no jar"))
    ):
        result = await fresh_engine.find_references_lsp(f, 1, 1)
    assert result is None
    assert fresh_engine._lsp_unavailable is True


@pytest.mark.asyncio
async def test_find_references_converts_to_zero_indexed_lsp(
    fresh_engine: CodeEngine, tmp_path: Path
) -> None:
    """Caller passes 1-indexed line/char; LSP receives 0-indexed."""
    f = tmp_path / "module.bsl"
    f.write_text("Процедура А() КонецПроцедуры\nПроцедура Б() КонецПроцедуры\n")

    fake_client = MagicMock()
    fake_client.did_open = AsyncMock()
    fake_client.did_close = AsyncMock()
    captured = {}

    async def fake_references(uri, line, character, include_declaration):
        captured["uri"] = uri
        captured["line"] = line
        captured["character"] = character
        captured["include_declaration"] = include_declaration
        return [{"uri": uri, "range": {"start": {"line": 0, "character": 0}}}]

    fake_client.references = AsyncMock(side_effect=fake_references)

    with patch.object(fresh_engine, "_ensure_lsp", AsyncMock(return_value=fake_client)):
        result = await fresh_engine.find_references_lsp(f, line=2, character=11)

    assert captured["line"] == 1
    assert captured["character"] == 10
    assert captured["include_declaration"] is False
    assert isinstance(result, list)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_find_references_clamps_negative_indices(
    fresh_engine: CodeEngine, tmp_path: Path
) -> None:
    """1-indexed inputs at the document head must not produce negatives."""
    f = tmp_path / "x.bsl"
    f.write_text("Процедура А() КонецПроцедуры")
    fake_client = MagicMock()
    fake_client.did_open = AsyncMock()
    fake_client.did_close = AsyncMock()
    captured = {}

    async def cap(uri, line, character, include_declaration):
        captured["line"] = line
        captured["character"] = character
        return []

    fake_client.references = AsyncMock(side_effect=cap)

    with patch.object(fresh_engine, "_ensure_lsp", AsyncMock(return_value=fake_client)):
        await fresh_engine.find_references_lsp(f, line=0, character=0)

    assert captured["line"] == 0
    assert captured["character"] == 0


@pytest.mark.asyncio
async def test_find_references_did_close_runs_after_failure(
    fresh_engine: CodeEngine, tmp_path: Path
) -> None:
    """Even if the references call raises, the document must be closed —
    otherwise the server's open-document set leaks.
    """
    from mcp_1c.engines.code.lsp.client import LspError

    f = tmp_path / "x.bsl"
    f.write_text("Процедура А() КонецПроцедуры")
    fake_client = MagicMock()
    fake_client.did_open = AsyncMock()
    fake_client.did_close = AsyncMock()
    fake_client.references = AsyncMock(side_effect=LspError("server crashed"))

    with patch.object(fresh_engine, "_ensure_lsp", AsyncMock(return_value=fake_client)):
        result = await fresh_engine.find_references_lsp(f, 1, 1)

    assert result is None  # caller sees clean fallback signal
    fake_client.did_close.assert_awaited_once()


@pytest.mark.asyncio
async def test_find_definition_returns_locations(
    fresh_engine: CodeEngine, tmp_path: Path
) -> None:
    f = tmp_path / "x.bsl"
    f.write_text("X = ОбщегоНазначения.Метод();\n")
    fake_client = MagicMock()
    fake_client.did_open = AsyncMock()
    fake_client.did_close = AsyncMock()
    expected = [
        {
            "uri": "file:///cm/общегоназначения.bsl",
            "range": {
                "start": {"line": 4, "character": 0},
                "end": {"line": 4, "character": 5},
            },
        }
    ]
    fake_client.definition = AsyncMock(return_value=expected)

    with patch.object(fresh_engine, "_ensure_lsp", AsyncMock(return_value=fake_client)):
        result = await fresh_engine.find_definition_lsp(f, line=1, character=21)

    assert result == expected


@pytest.mark.asyncio
async def test_lsp_manager_invalidates_symbol_cache_on_restart(
    fresh_engine: CodeEngine, tmp_path: Path
) -> None:
    """_ensure_lsp registers a restart-listener that wipes the cache."""
    fake_manager = MagicMock()
    fake_manager.running = True
    fake_client = MagicMock()
    fake_manager.client = fake_client
    fake_manager.start = AsyncMock()
    listeners = []
    fake_manager.on_restart = lambda listener: listeners.append(listener)

    with patch(
        "mcp_1c.engines.code.engine.BslLspServerManager",
        return_value=fake_manager,
    ):
        await fresh_engine._ensure_lsp()

    # Pre-populate cache; listener fires; cache emptied.
    f = tmp_path / "x.bsl"
    f.write_text("Процедура А() КонецПроцедуры")
    await fresh_engine._symbol_cache.set(f, [{"name": "A"}])
    assert await fresh_engine._symbol_cache.get(f) is not None

    assert listeners, "manager.on_restart was not registered"
    await listeners[0]()  # simulate restart fire

    assert await fresh_engine._symbol_cache.get(f) is None
