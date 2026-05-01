"""Tests for documentSymbol cache — keyed on (path, mtime, sha256)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_1c.engines.code.lsp.cache import DocumentSymbolCache


@pytest.mark.asyncio
async def test_get_returns_none_for_unknown_path(tmp_path: Path) -> None:
    cache = DocumentSymbolCache()
    f = tmp_path / "module.bsl"
    f.write_text("Процедура А() КонецПроцедуры")
    assert await cache.get(f) is None


@pytest.mark.asyncio
async def test_set_then_get_round_trips(tmp_path: Path) -> None:
    cache = DocumentSymbolCache()
    f = tmp_path / "module.bsl"
    f.write_text("Процедура А() КонецПроцедуры")

    payload = [{"name": "А", "kind": 12}]
    await cache.set(f, payload)
    fetched = await cache.get(f)
    assert fetched == payload


@pytest.mark.asyncio
async def test_content_change_invalidates_implicitly(tmp_path: Path) -> None:
    """When the file bytes change, the cache key changes — old entry
    becomes unreachable without explicit invalidate()."""
    cache = DocumentSymbolCache()
    f = tmp_path / "m.bsl"
    f.write_text("v1")

    await cache.set(f, [{"v": 1}])
    f.write_text("v2 — different content, different sha")
    # Same path, but the lookup key now differs.
    assert await cache.get(f) is None


@pytest.mark.asyncio
async def test_explicit_invalidate_drops_all_keys_for_path(tmp_path: Path) -> None:
    cache = DocumentSymbolCache()
    f = tmp_path / "m.bsl"
    f.write_text("v1")
    await cache.set(f, [{"v": 1}])

    # The (path, mtime, sha) key currently lives in cache; invalidate()
    # should clear it even though the file hasn't changed yet.
    await cache.invalidate(f)
    assert await cache.get(f) is None


@pytest.mark.asyncio
async def test_get_handles_missing_file_gracefully(tmp_path: Path) -> None:
    cache = DocumentSymbolCache()
    nonexistent = tmp_path / "nope.bsl"
    # Stat will raise FileNotFoundError; cache must surface as miss, not error.
    assert await cache.get(nonexistent) is None


@pytest.mark.asyncio
async def test_set_on_missing_file_is_noop(tmp_path: Path) -> None:
    cache = DocumentSymbolCache()
    nonexistent = tmp_path / "ghost.bsl"
    # Doesn't crash; nothing stored.
    await cache.set(nonexistent, [{"x": 1}])
    assert cache.stats()["size"] == 0
