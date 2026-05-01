"""Tests for Workspace + WorkspaceRegistry.

We use a fake storage factory (a stub bundle) so the tests don't
exercise SQLite or filesystem layout — that's covered by
test_storage_protocol. Here we focus on the lifecycle contracts:
idempotent open/close, registry concurrency, eviction policy.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from mcp_1c.engines.workspace import Workspace, WorkspaceRegistry


class _StubBundle:
    """Minimal StorageBundle satisfying the protocol shape for tests."""

    def __init__(self, *, workspace_id: str, root: Path) -> None:
        self.workspace_id = workspace_id
        self.root = root
        self.metadata: Any = object()
        self.vectors: Any = object()
        self.graph: Any = object()
        self.opened_count = 0
        self.closed_count = 0

    async def open(self) -> None:
        self.opened_count += 1

    async def close(self) -> None:
        self.closed_count += 1


def _stub_factory(record: list[_StubBundle] | None = None):
    def factory(*, workspace_id: str, root: Path) -> _StubBundle:
        bundle = _StubBundle(workspace_id=workspace_id, root=root)
        if record is not None:
            record.append(bundle)
        return bundle

    return factory


# ---------------------------------------------------------------------------
# Workspace lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workspace_open_initializes_storage(tmp_path: Path) -> None:
    bundles: list[_StubBundle] = []
    ws = await Workspace.open(
        config_path=tmp_path,
        storage_factory=_stub_factory(bundles),
    )
    try:
        assert ws.opened
        assert ws.id  # stable hash from WorkspacePaths
        assert ws.storage.opened_count == 1  # type: ignore[attr-defined]
    finally:
        await ws.close()


@pytest.mark.asyncio
async def test_workspace_close_is_idempotent(tmp_path: Path) -> None:
    ws = await Workspace.open(
        config_path=tmp_path,
        storage_factory=_stub_factory(),
    )
    await ws.close()
    await ws.close()  # Must not raise.
    assert ws.opened is False


@pytest.mark.asyncio
async def test_workspace_id_is_deterministic_for_same_path(
    tmp_path: Path,
) -> None:
    factory = _stub_factory()
    ws1 = await Workspace.open(config_path=tmp_path, storage_factory=factory)
    ws2 = await Workspace.open(config_path=tmp_path, storage_factory=factory)
    try:
        assert ws1.id == ws2.id  # WorkspacePaths.workspace_id is sha256-derived
    finally:
        await ws1.close()
        await ws2.close()


# ---------------------------------------------------------------------------
# Profile attachment (F4.5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workspace_loads_default_profile_when_yaml_missing(
    tmp_path: Path,
) -> None:
    from mcp_1c.engines.profile import ConfigurationProfile

    ws = await Workspace.open(
        config_path=tmp_path,
        storage_factory=_stub_factory(),
    )
    try:
        assert isinstance(ws.profile, ConfigurationProfile)
        # Default-shaped: ru language, БСП assumed, default skip prefixes.
        assert ws.profile.language == "ru"
        assert ws.profile.bsp.used is True
        assert ws.profile.naming.obsolete_prefixes == ["Удалить"]
    finally:
        await ws.close()


@pytest.mark.asyncio
async def test_workspace_loads_yaml_profile_when_present(tmp_path: Path) -> None:
    """``.mcp_1c_project.yaml`` in config root is read into ``Workspace.profile``."""
    from mcp_1c.engines.profile.loader import PROFILE_FILENAME

    (tmp_path / PROFILE_FILENAME).write_text(
        "language: en\nbsp:\n  used: false\n",
        encoding="utf-8",
    )
    ws = await Workspace.open(
        config_path=tmp_path,
        storage_factory=_stub_factory(),
    )
    try:
        assert ws.profile.language == "en"
        assert ws.profile.bsp.used is False
    finally:
        await ws.close()


@pytest.mark.asyncio
async def test_workspace_falls_back_to_defaults_on_malformed_yaml(
    tmp_path: Path,
) -> None:
    """Malformed YAML must NOT break workspace open — we degrade to
    default profile and log."""
    from mcp_1c.engines.profile import ConfigurationProfile
    from mcp_1c.engines.profile.loader import PROFILE_FILENAME

    (tmp_path / PROFILE_FILENAME).write_text(
        ":this is not valid yaml::\n  ::",
        encoding="utf-8",
    )
    ws = await Workspace.open(
        config_path=tmp_path,
        storage_factory=_stub_factory(),
    )
    try:
        # Defaults applied — workspace usable despite malformed YAML.
        assert ws.profile == ConfigurationProfile()
    finally:
        await ws.close()


# ---------------------------------------------------------------------------
# WorkspaceRegistry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registry_creates_distinct_workspaces(tmp_path: Path) -> None:
    registry = WorkspaceRegistry(storage_factory=_stub_factory(), max_workspaces=8)
    a = await registry.get_or_create("a", tmp_path / "a")
    b = await registry.get_or_create("b", tmp_path / "b")
    assert a is not b
    assert registry.size == 2
    await registry.close_all()


@pytest.mark.asyncio
async def test_registry_returns_existing_workspace(tmp_path: Path) -> None:
    registry = WorkspaceRegistry(storage_factory=_stub_factory(), max_workspaces=8)
    first = await registry.get_or_create("a", tmp_path / "a")
    second = await registry.get_or_create("a", tmp_path / "a")
    assert first is second  # No new workspace created on repeat call.
    await registry.close_all()


@pytest.mark.asyncio
async def test_registry_concurrent_creates_dedup(tmp_path: Path) -> None:
    """Two simultaneous get_or_create calls for the same id must not
    produce two open workspaces."""
    registry = WorkspaceRegistry(storage_factory=_stub_factory(), max_workspaces=8)
    a, b = await asyncio.gather(
        registry.get_or_create("shared", tmp_path / "shared"),
        registry.get_or_create("shared", tmp_path / "shared"),
    )
    assert a is b
    assert registry.size == 1
    await registry.close_all()


@pytest.mark.asyncio
async def test_registry_evicts_lru_when_over_capacity(tmp_path: Path) -> None:
    bundles: list[_StubBundle] = []
    registry = WorkspaceRegistry(
        storage_factory=_stub_factory(bundles), max_workspaces=2
    )
    a = await registry.get_or_create("a", tmp_path / "a")
    b = await registry.get_or_create("b", tmp_path / "b")
    # Touch 'a' so it becomes most-recent; 'b' is now LRU.
    await registry.get("a")
    c = await registry.get_or_create("c", tmp_path / "c")
    # 'b' should have been evicted; 'a' and 'c' remain.
    assert "a" in registry.list_ids()
    assert "c" in registry.list_ids()
    assert "b" not in registry.list_ids()
    assert b.opened is False  # Closed during eviction.
    assert a.opened and c.opened
    await registry.close_all()


@pytest.mark.asyncio
async def test_registry_close_all_releases_everything(tmp_path: Path) -> None:
    bundles: list[_StubBundle] = []
    registry = WorkspaceRegistry(
        storage_factory=_stub_factory(bundles), max_workspaces=4
    )
    await registry.get_or_create("a", tmp_path / "a")
    await registry.get_or_create("b", tmp_path / "b")
    assert registry.size == 2
    await registry.close_all()
    assert registry.size == 0
    assert all(b.closed_count >= 1 for b in bundles)


@pytest.mark.asyncio
async def test_registry_remove_drops_one(tmp_path: Path) -> None:
    registry = WorkspaceRegistry(storage_factory=_stub_factory(), max_workspaces=4)
    ws = await registry.get_or_create("a", tmp_path / "a")
    await registry.remove("a")
    assert registry.size == 0
    assert ws.opened is False
    # Removing again must be a no-op.
    await registry.remove("a")
