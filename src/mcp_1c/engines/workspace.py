"""Workspace — first-class home for one indexed 1C configuration.

Today the codebase glues engines together through ``get_instance()``
singletons. That made sense for a single-config CLI helper but blocks
multi-tenant deployments and contaminates tests. ``Workspace`` is the
incremental fix: a per-config bundle that owns its storage, its LSP
process, its profile.

This module is **opt-in for now**. Existing engines keep working through
``get_instance()`` until they're migrated one at a time. The
:class:`WorkspaceRegistry` will be wired into ``web.py`` in Phase 2 when
the storage migration to PostgreSQL lands; until then it's used by
tests and any new code that wants explicit lifecycle.

Two creation paths::

    # Stdio / single-tenant: one global workspace per process.
    ws = await Workspace.open(config_path=Path("/configs/uta"))

    # Web / multi-tenant: registry owns the lifecycle.
    registry = WorkspaceRegistry(storage_factory=sqlite_bundle_factory())
    ws = await registry.get_or_create("ws-uta", Path("/configs/uta"))
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from mcp_1c.config import WorkspacePaths
from mcp_1c.engines.storage import StorageBundle
from mcp_1c.engines.storage.sqlite import sqlite_bundle_factory
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


class Workspace:
    """One indexed 1C configuration plus everything that depends on it.

    Holds:
    - ``id`` — short identifier (sha256 prefix of config_path).
    - ``config_path`` — root of the 1C configuration on disk.
    - ``storage`` — the StorageBundle (metadata + vectors + graph).
    - ``profile`` — :class:`ConfigurationProfile` describing the
      configuration's conventions (language, БСП, naming, generation
      strategies). Loaded from ``.mcp_1c_project.yaml`` on open;
      defaults to a typical-БСП profile when the file is absent.
    - ``lsp_manager`` (optional) — ``BslLspServerManager`` started lazily.

    Phase 2 will hang the rest of the engines (metadata, code,
    embeddings, kg, smart) off this object so each workspace has its
    own. For now those still use the global singletons; ``profile``
    is the first engine-state we attach properly per-workspace.
    """

    def __init__(
        self,
        *,
        id: str,
        config_path: Path,
        storage: StorageBundle,
        profile: Any = None,
    ) -> None:
        self.id = id
        self.config_path = config_path
        self.storage = storage
        # Imported lazily where used; ``Any`` here keeps the workspace
        # module independent of the profile package's import graph
        # for callers that don't touch profiles.
        self.profile = profile
        self._lsp_manager: Any = None  # BslLspServerManager when started
        self._opened = False
        # Token returned from ``active_profile.set(...)``; stored so
        # ``close()`` can ``reset(token)`` cleanly. ``None`` when no
        # profile is bound (workspace constructed without one).
        self._profile_token: Any = None

    @classmethod
    async def open(
        cls,
        *,
        config_path: Path,
        storage_factory: Any = None,
        embedding_dimension: int = 4096,
    ) -> Workspace:
        """Create and open a workspace for ``config_path``.

        Picks a stable workspace id from the path hash so reopens are
        deterministic. ``storage_factory`` defaults to SQLite; tests
        and the future PG path inject their own.

        Loads the configuration profile from
        ``<config_path>/.mcp_1c_project.yaml`` if present; otherwise
        builds a default profile. A malformed YAML is logged but does
        not break the open — we degrade to the default profile so the
        rest of the workspace still works.
        """
        paths = WorkspacePaths.for_config(config_path)
        factory = storage_factory or sqlite_bundle_factory(
            embedding_dimension=embedding_dimension
        )
        storage = factory(workspace_id=paths.workspace_id, root=paths.root)

        # Load profile (lazy import — the profile package depends on
        # PyYAML and that's an opt-in cost).
        from mcp_1c.engines.profile import (
            ConfigurationProfile,
            load_profile,
        )
        from mcp_1c.engines.profile.loader import ProfileError

        try:
            profile = load_profile(config_path)
        except ProfileError as exc:
            logger.warning(
                f"Profile load failed for {config_path}: {exc}; "
                "using defaults"
            )
            profile = ConfigurationProfile()

        workspace = cls(
            id=paths.workspace_id,
            config_path=config_path,
            storage=storage,
            profile=profile,
        )
        await workspace._open()
        return workspace

    async def _open(self) -> None:
        if self._opened:
            return
        await self.storage.open()
        # Bind the profile so smart-builders consulting the
        # ``active_profile`` ContextVar see this workspace's settings
        # without each call site threading ``profile`` through. The
        # binding is process-global by intent — single-tenant CLI/stdio
        # uses one active profile at a time. Phase 2 multi-tenant web
        # will scope this per request via ``use_active_profile``.
        if self.profile is not None:
            from mcp_1c.engines.smart.context import set_active_profile

            self._profile_token = set_active_profile(self.profile)
        else:
            self._profile_token = None
        self._opened = True
        logger.info(
            f"Workspace {self.id!r} opened (config={self.config_path}, "
            f"storage_root={getattr(self.storage, 'root', '?')})"
        )

    async def close(self) -> None:
        """Tear the workspace down. Idempotent and best-effort."""
        if not self._opened:
            return
        # Unbind the profile so the next workspace doesn't inherit
        # this one's. Reset is no-op when token is None.
        if self._profile_token is not None:
            import contextlib

            from mcp_1c.engines.smart.context import active_profile

            # Token from a different context: per-task ContextVar copy
            # makes reset() noisy but harmless. Suppress and move on.
            with contextlib.suppress(LookupError, ValueError):
                active_profile.reset(self._profile_token)
            self._profile_token = None
        if self._lsp_manager is not None:
            try:
                await self._lsp_manager.stop()
            except Exception as exc:
                logger.debug(f"LSP stop in close() raised: {exc}")
            self._lsp_manager = None
        try:
            await self.storage.close()
        finally:
            self._opened = False
        logger.info(f"Workspace {self.id!r} closed")

    @property
    def opened(self) -> bool:
        return self._opened


class WorkspaceRegistry:
    """Pool of ``Workspace`` instances with bounded concurrency.

    Web mode wants exactly one Workspace per indexed config, shared
    across requests. ``get_or_create`` is the safe entry point —
    coroutine-safe, ensures a single ``open()`` per workspace even
    under racing requests.

    ``max_workspaces`` caps the pool. When exceeded we evict the
    least-recently-touched entry — that workspace's next request will
    re-open. This keeps long-running deployments bounded without
    forcing pre-declaration of every config.
    """

    def __init__(
        self,
        *,
        storage_factory: Any = None,
        max_workspaces: int = 16,
        embedding_dimension: int = 4096,
    ) -> None:
        self._factory = storage_factory or sqlite_bundle_factory(
            embedding_dimension=embedding_dimension
        )
        self._max = max_workspaces
        self._workspaces: dict[str, Workspace] = {}
        self._touch_order: list[str] = []
        self._lock = asyncio.Lock()

    @property
    def size(self) -> int:
        return len(self._workspaces)

    async def get_or_create(
        self, workspace_id: str, config_path: Path
    ) -> Workspace:
        """Return a live workspace for the given path.

        If one with the same id already exists, return it (and bump
        recency). Otherwise create + open. Eviction runs *after*
        admit so the new workspace itself can never be the victim.
        """
        async with self._lock:
            existing = self._workspaces.get(workspace_id)
            if existing is not None and existing.opened:
                self._bump(workspace_id)
                return existing

            ws = await Workspace.open(
                config_path=config_path, storage_factory=self._factory
            )
            self._workspaces[workspace_id] = ws
            self._touch_order.append(workspace_id)
            await self._evict_if_needed(except_id=workspace_id)
            return ws

    async def get(self, workspace_id: str) -> Workspace | None:
        async with self._lock:
            ws = self._workspaces.get(workspace_id)
            if ws is not None:
                self._bump(workspace_id)
            return ws

    async def remove(self, workspace_id: str) -> None:
        """Close and forget a workspace. No-op if not present."""
        async with self._lock:
            ws = self._workspaces.pop(workspace_id, None)
            if workspace_id in self._touch_order:
                self._touch_order.remove(workspace_id)
        if ws is not None:
            await ws.close()

    async def close_all(self) -> None:
        async with self._lock:
            workspaces = list(self._workspaces.values())
            self._workspaces.clear()
            self._touch_order.clear()
        for ws in workspaces:
            try:
                await ws.close()
            except Exception as exc:
                logger.warning(f"Error closing workspace {ws.id}: {exc}")

    def list_ids(self) -> list[str]:
        # Snapshot — caller mutates at their peril.
        return list(self._workspaces.keys())

    # -- internal --------------------------------------------------------

    def _bump(self, workspace_id: str) -> None:
        if workspace_id in self._touch_order:
            self._touch_order.remove(workspace_id)
        self._touch_order.append(workspace_id)

    async def _evict_if_needed(self, *, except_id: str) -> None:
        while len(self._workspaces) > self._max:
            victim_id = next(
                (wid for wid in self._touch_order if wid != except_id),
                None,
            )
            if victim_id is None:
                break
            victim = self._workspaces.pop(victim_id, None)
            self._touch_order.remove(victim_id)
            if victim is not None:
                logger.info(
                    f"Evicting workspace {victim_id!r} "
                    f"(pool over capacity {self._max})"
                )
                try:
                    await victim.close()
                except Exception as exc:
                    logger.warning(f"Error closing evicted workspace: {exc}")


__all__ = ["Workspace", "WorkspaceRegistry"]
