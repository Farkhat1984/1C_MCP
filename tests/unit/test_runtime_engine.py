"""Unit tests for the runtime engine — focused on configuration semantics
without hitting any real network."""

from __future__ import annotations

import pytest

from mcp_1c.engines.runtime.client import RuntimeClientError
from mcp_1c.engines.runtime.engine import RuntimeConfig, RuntimeEngine


@pytest.fixture(autouse=True)
def _reset_engine() -> None:
    RuntimeEngine._instance = None
    yield
    RuntimeEngine._instance = None


def test_config_unconfigured_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_RUNTIME_BASE_URL", raising=False)
    monkeypatch.delenv("MCP_RUNTIME_TOKEN", raising=False)
    cfg = RuntimeConfig.from_env()
    assert cfg.configured is False


def test_config_picks_up_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_RUNTIME_BASE_URL", "https://1c.example.com/hs/mcp")
    monkeypatch.setenv("MCP_RUNTIME_TOKEN", "secret")
    monkeypatch.setenv("MCP_RUNTIME_RW", "true")
    cfg = RuntimeConfig.from_env()
    assert cfg.configured
    assert cfg.allow_writes is True


@pytest.mark.asyncio
async def test_status_unconfigured_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_RUNTIME_BASE_URL", raising=False)
    monkeypatch.delenv("MCP_RUNTIME_TOKEN", raising=False)
    engine = RuntimeEngine.get_instance()
    with pytest.raises(RuntimeClientError) as ei:
        await engine.status()
    assert "not configured" in ei.value.message.lower()


@pytest.mark.asyncio
async def test_eval_blocks_write_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_RUNTIME_BASE_URL", "https://example.com/hs/mcp")
    monkeypatch.setenv("MCP_RUNTIME_TOKEN", "x")
    monkeypatch.setenv("MCP_RUNTIME_RW", "false")
    engine = RuntimeEngine.get_instance()

    with pytest.raises(RuntimeClientError) as ei:
        await engine.eval_bsl("Записать();", allow_writes=True)
    assert "MCP_RUNTIME_RW" in ei.value.message
