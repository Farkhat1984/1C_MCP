"""ContextVar-based active profile for smart-builders.

This is the F4-tail piece that connects ``Workspace.profile`` to the
smart-builder helpers without threading a parameter through every
call site. Tests verify both the manual context manager (``use_active
_profile``) and the implicit binding done by ``Workspace.open()``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcp_1c.domain.metadata import Attribute
from mcp_1c.engines.profile import ConfigurationProfile, NamingSection
from mcp_1c.engines.smart.context import (
    get_active_profile,
    use_active_profile,
)
from mcp_1c.engines.smart.query_builder import _should_skip
from mcp_1c.engines.smart.type_resolver import TypeResolver

# ---------------------------------------------------------------------------
# Default — unbound — preserves historical behaviour
# ---------------------------------------------------------------------------


def test_active_profile_default_is_none() -> None:
    """No bind anywhere → readers see None."""
    assert get_active_profile() is None


def test_should_skip_with_no_binding_uses_default() -> None:
    """Backward compat: no profile arg, no context → default ``Удалить``."""
    assert _should_skip(Attribute(name="УдалитьФ", type="String")) is True
    assert _should_skip(Attribute(name="Активный", type="String")) is False


def test_to_russian_prefix_with_no_binding_returns_russian() -> None:
    assert TypeResolver.to_russian_type_prefix("Catalog") == "Справочник"


# ---------------------------------------------------------------------------
# Manual binding via ``use_active_profile``
# ---------------------------------------------------------------------------


def test_use_active_profile_binds_for_block() -> None:
    """Inside the block readers see the bound profile."""
    profile = ConfigurationProfile(language="en")
    with use_active_profile(profile):
        assert get_active_profile() is profile
    assert get_active_profile() is None


def test_use_active_profile_resets_on_exception() -> None:
    """Even when the body raises, the binding is reset."""
    with pytest.raises(RuntimeError):
        with use_active_profile(ConfigurationProfile(language="en")):
            raise RuntimeError("kaboom")
    assert get_active_profile() is None


def test_should_skip_picks_up_context_binding() -> None:
    """The whole point of F4-tail: smart helpers read the active
    profile when the caller didn't pass one explicitly."""
    profile = ConfigurationProfile(
        naming=NamingSection(obsolete_prefixes=["Удалить", "_old"]),
    )
    with use_active_profile(profile):
        assert _should_skip(Attribute(name="_oldF", type="String")) is True
        assert _should_skip(Attribute(name="УдалитьА", type="String")) is True
    # Outside the block the default returns.
    assert _should_skip(Attribute(name="_oldF", type="String")) is False


def test_to_russian_prefix_picks_up_context_binding() -> None:
    profile = ConfigurationProfile(language="en")
    with use_active_profile(profile):
        assert TypeResolver.to_russian_type_prefix("Catalog") == "Catalog"
    assert TypeResolver.to_russian_type_prefix("Catalog") == "Справочник"


def test_get_presentation_field_picks_up_context_binding() -> None:
    profile = ConfigurationProfile(
        naming=NamingSection(
            presentation_field_overrides={"Catalog.Контрагенты": "ПолноеИмя"},
        ),
    )
    with use_active_profile(profile):
        result = TypeResolver.get_presentation_field(
            "СправочникСсылка.Контрагенты",
            object_full_name="Catalog.Контрагенты",
        )
    assert result == "ПолноеИмя"


def test_explicit_profile_arg_wins_over_context() -> None:
    """If a caller passes ``profile=`` explicitly, it must override
    whatever the context has — explicit always wins implicit."""
    ctx_profile = ConfigurationProfile(language="ru")
    explicit_profile = ConfigurationProfile(language="en")
    with use_active_profile(ctx_profile):
        # Explicit en wins over context ru.
        assert (
            TypeResolver.to_russian_type_prefix("Catalog", explicit_profile)
            == "Catalog"
        )


# ---------------------------------------------------------------------------
# Workspace.open binds the profile
# ---------------------------------------------------------------------------


class _StubBundle:
    def __init__(self, *, workspace_id: str, root: Path) -> None:
        self.workspace_id = workspace_id
        self.root = root
        self.metadata: Any = object()
        self.vectors: Any = object()
        self.graph: Any = object()

    async def open(self) -> None:
        pass

    async def close(self) -> None:
        pass


def _stub_factory():
    def factory(*, workspace_id: str, root: Path) -> _StubBundle:
        return _StubBundle(workspace_id=workspace_id, root=root)

    return factory


@pytest.mark.asyncio
async def test_workspace_open_binds_active_profile(tmp_path: Path) -> None:
    """After Workspace.open the smart-context sees the workspace's profile."""
    from mcp_1c.engines.profile.loader import PROFILE_FILENAME
    from mcp_1c.engines.workspace import Workspace

    (tmp_path / PROFILE_FILENAME).write_text(
        "language: en\n", encoding="utf-8"
    )
    assert get_active_profile() is None  # baseline

    ws = await Workspace.open(
        config_path=tmp_path, storage_factory=_stub_factory()
    )
    try:
        active = get_active_profile()
        assert active is not None
        assert active.language == "en"
    finally:
        await ws.close()

    # After close — back to None (or whatever was bound before).
    # Note: ContextVar.reset may no-op silently when the token is from
    # a different async task, but in this synchronous test it must clear.
    assert get_active_profile() is None


@pytest.mark.asyncio
async def test_workspace_close_resets_active_profile(tmp_path: Path) -> None:
    from mcp_1c.engines.workspace import Workspace

    ws = await Workspace.open(
        config_path=tmp_path, storage_factory=_stub_factory()
    )
    assert get_active_profile() is not None
    await ws.close()
    assert get_active_profile() is None


@pytest.mark.asyncio
async def test_workspace_with_no_profile_does_not_break(tmp_path: Path) -> None:
    """Workspace constructed directly without a profile → no binding,
    no errors. Used by tests that pass profile=None explicitly."""
    from mcp_1c.engines.workspace import Workspace

    storage = _StubBundle(workspace_id="x", root=tmp_path)
    await storage.open()
    ws = Workspace(
        id="x", config_path=tmp_path, storage=storage, profile=None
    )
    await ws._open()
    try:
        assert get_active_profile() is None
    finally:
        await ws.close()
