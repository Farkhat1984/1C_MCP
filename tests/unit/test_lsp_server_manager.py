"""Tests for the BSL-LS server manager — dependency resolution only.

We don't spawn a real JVM; that belongs to the integration suite gated
by ``pytest -m lsp``. Here we cover the logic that decides *what* to
run: env-var precedence, missing-binary errors, the disable switch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_1c.engines.code.lsp.server_manager import (
    ENV_BSL_LS_JAR,
    ENV_BSL_LS_PATH,
    ENV_DISABLE,
    ENV_JAVA,
    BslLspServerManager,
    BslLspUnavailable,
)


@pytest.mark.asyncio
async def test_disable_flag_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_DISABLE, "true")
    manager = BslLspServerManager()
    with pytest.raises(BslLspUnavailable, match=ENV_DISABLE):
        await manager.start()


@pytest.mark.asyncio
async def test_missing_binary_raises_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(ENV_DISABLE, raising=False)
    monkeypatch.delenv(ENV_BSL_LS_JAR, raising=False)
    monkeypatch.delenv(ENV_BSL_LS_PATH, raising=False)
    # Force shutil.which("bsl-language-server") to miss by clearing PATH.
    monkeypatch.setenv("PATH", str(tmp_path))
    # And ensure the conventional cache jar isn't present.
    monkeypatch.setenv("HOME", str(tmp_path))
    manager = BslLspServerManager()
    with pytest.raises(BslLspUnavailable, match="not found"):
        await manager.start()


@pytest.mark.asyncio
async def test_explicit_jar_path_used(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When a jar is given explicitly, _build_command should use it."""
    monkeypatch.delenv(ENV_DISABLE, raising=False)
    fake_jar = tmp_path / "bsl-language-server.jar"
    fake_jar.write_bytes(b"")
    # Pretend java exists by pointing to /bin/sh which always does.
    manager = BslLspServerManager(jar_path=fake_jar, java_path="/bin/sh")
    cmd = manager._build_command()  # internal, but the manager won't actually run yet
    assert cmd[0] == "/bin/sh"
    assert "-jar" in cmd
    assert str(fake_jar) in cmd


@pytest.mark.asyncio
async def test_native_binary_takes_precedence_over_jar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Native build is faster — pick it even if a jar is also configured."""
    monkeypatch.delenv(ENV_DISABLE, raising=False)
    binary = tmp_path / "bsl-language-server"
    binary.write_bytes(b"")
    binary.chmod(0o755)
    jar = tmp_path / "bsl-language-server.jar"
    jar.write_bytes(b"")
    manager = BslLspServerManager(binary_path=binary, jar_path=jar, java_path="/bin/sh")
    cmd = manager._build_command()
    assert cmd == [str(binary)]


@pytest.mark.asyncio
async def test_env_jar_overrides_default_search(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``MCP_BSL_LS_JAR`` env var should be honoured."""
    monkeypatch.delenv(ENV_DISABLE, raising=False)
    monkeypatch.delenv(ENV_BSL_LS_PATH, raising=False)
    fake_jar = tmp_path / "from-env.jar"
    fake_jar.write_bytes(b"")
    monkeypatch.setenv(ENV_BSL_LS_JAR, str(fake_jar))
    monkeypatch.setenv(ENV_JAVA, "/bin/sh")
    manager = BslLspServerManager()
    cmd = manager._build_command()
    assert "-jar" in cmd
    assert str(fake_jar) in cmd


@pytest.mark.asyncio
async def test_missing_java_raises_with_helpful_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(ENV_DISABLE, raising=False)
    fake_jar = tmp_path / "x.jar"
    fake_jar.write_bytes(b"")
    monkeypatch.setenv("PATH", "")  # no java on PATH
    manager = BslLspServerManager(jar_path=fake_jar, java_path="not-installed-java")
    with pytest.raises(BslLspUnavailable, match="Java"):
        manager._build_command()


# ---------------------------------------------------------------------------
# Restart logic — driven by mocked _start_locked / _stop_locked so we
# don't need a JVM. Verifies the storm-detection circuit and the
# listener-notification contract.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restart_storm_circuit_breaker_after_n_restarts() -> None:
    """N+1th restart inside 60s must refuse to start."""
    manager = BslLspServerManager(max_restarts_per_minute=2, healthcheck_interval=0)
    manager._start_locked = _AsyncNoop()  # type: ignore[assignment]
    manager._stop_locked = _AsyncNoop()  # type: ignore[assignment]

    # Three restarts in quick succession should trip the breaker on
    # the third call — the third stops the old one but does NOT spawn
    # a new one (because the manager is now circuit-broken).
    await manager.force_restart(reason="t1")
    await manager.force_restart(reason="t2")
    await manager.force_restart(reason="t3")

    # After this, ``start()`` itself should refuse cleanly.
    with pytest.raises(BslLspUnavailable, match="Restart storm"):
        await manager.start()


@pytest.mark.asyncio
async def test_stop_resets_storm_breaker() -> None:
    """``stop()`` must clear the timestamps so a fresh start works."""
    manager = BslLspServerManager(max_restarts_per_minute=1, healthcheck_interval=0)
    manager._start_locked = _AsyncNoop()  # type: ignore[assignment]
    manager._stop_locked = _AsyncNoop()  # type: ignore[assignment]

    await manager.force_restart(reason="x")
    await manager.force_restart(reason="y")
    assert manager._is_restart_storm()

    await manager.stop()
    assert not manager._is_restart_storm()


@pytest.mark.asyncio
async def test_restart_listeners_fire_after_successful_restart() -> None:
    """Listeners are notified post-restart so callers can drop stale state."""
    manager = BslLspServerManager(max_restarts_per_minute=10, healthcheck_interval=0)
    manager._start_locked = _AsyncNoop()  # type: ignore[assignment]
    manager._stop_locked = _AsyncNoop()  # type: ignore[assignment]

    seen: list[int] = []

    async def listener_a() -> None:
        seen.append(1)

    async def listener_b() -> None:
        seen.append(2)

    manager.on_restart(listener_a)
    manager.on_restart(listener_b)

    await manager.force_restart(reason="test")
    assert seen == [1, 2]


@pytest.mark.asyncio
async def test_failing_listener_does_not_block_others() -> None:
    """A listener that raises must not stop the rest from running."""
    manager = BslLspServerManager(max_restarts_per_minute=10, healthcheck_interval=0)
    manager._start_locked = _AsyncNoop()  # type: ignore[assignment]
    manager._stop_locked = _AsyncNoop()  # type: ignore[assignment]

    seen: list[int] = []

    async def bad() -> None:
        raise RuntimeError("listener exploded")

    async def good() -> None:
        seen.append(1)

    manager.on_restart(bad)
    manager.on_restart(good)
    await manager.force_restart(reason="x")
    assert seen == [1]


class _AsyncNoop:
    """Awaitable no-op used to bypass real subprocess work in tests."""

    async def __call__(self, *args, **kwargs) -> None:
        return None
