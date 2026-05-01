"""OverlayRoot model + WorkspacePaths.for_config(overlays=...).

The contract verified here is the foundation of multi-root indexing
(Phase F3): overlays land as first-class config citizens, the
workspace id is stable across reordering but changes when the overlay
set itself changes, and the validator catches misconfigured overlays
at configure time.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_1c.config import (
    AppConfig,
    OverlayRoot,
    WorkspacePaths,
    set_overlay_roots,
)

# ---------------------------------------------------------------------------
# OverlayRoot
# ---------------------------------------------------------------------------


def test_overlay_source_label() -> None:
    overlay = OverlayRoot(name="utils", path=Path("/team/utils"))
    assert overlay.source_label == "overlay:utils"


def test_overlay_default_priority() -> None:
    overlay = OverlayRoot(name="x", path=Path("/x"))
    assert overlay.priority == 100


def test_overlay_custom_priority() -> None:
    overlay = OverlayRoot(name="x", path=Path("/x"), priority=10)
    assert overlay.priority == 10


# ---------------------------------------------------------------------------
# WorkspacePaths
# ---------------------------------------------------------------------------


def test_workspace_id_stable_for_same_inputs(tmp_path: Path) -> None:
    config_root = tmp_path / "uta"
    config_root.mkdir()
    overlay_a = OverlayRoot(name="a", path=tmp_path / "lib-a")
    (tmp_path / "lib-a").mkdir()

    paths_1 = WorkspacePaths.for_config(config_root, overlays=[overlay_a])
    paths_2 = WorkspacePaths.for_config(config_root, overlays=[overlay_a])
    assert paths_1.workspace_id == paths_2.workspace_id


def test_workspace_id_independent_of_overlay_order(tmp_path: Path) -> None:
    """Declaring overlays in different orders must yield same workspace id —
    overlays form a *set*, not a sequence."""
    config_root = tmp_path / "uta"
    config_root.mkdir()
    (tmp_path / "lib-a").mkdir()
    (tmp_path / "lib-b").mkdir()
    a = OverlayRoot(name="a", path=tmp_path / "lib-a")
    b = OverlayRoot(name="b", path=tmp_path / "lib-b")

    p1 = WorkspacePaths.for_config(config_root, overlays=[a, b])
    p2 = WorkspacePaths.for_config(config_root, overlays=[b, a])
    assert p1.workspace_id == p2.workspace_id


def test_workspace_id_changes_when_overlay_set_differs(tmp_path: Path) -> None:
    """Adding/removing overlays must invalidate the cache directory —
    otherwise A's objects leak into a B-only run."""
    config_root = tmp_path / "uta"
    config_root.mkdir()
    (tmp_path / "lib-a").mkdir()
    (tmp_path / "lib-b").mkdir()
    a = OverlayRoot(name="a", path=tmp_path / "lib-a")
    b = OverlayRoot(name="b", path=tmp_path / "lib-b")

    just_a = WorkspacePaths.for_config(config_root, overlays=[a])
    just_b = WorkspacePaths.for_config(config_root, overlays=[b])
    both = WorkspacePaths.for_config(config_root, overlays=[a, b])
    plain = WorkspacePaths.for_config(config_root)

    ids = {just_a.workspace_id, just_b.workspace_id, both.workspace_id, plain.workspace_id}
    assert len(ids) == 4  # all distinct


def test_workspace_no_overlay_back_compat(tmp_path: Path) -> None:
    """Old call-sites without overlays still work and produce empty list."""
    config_root = tmp_path / "uta"
    config_root.mkdir()
    paths = WorkspacePaths.for_config(config_root)
    assert paths.overlays == []


# ---------------------------------------------------------------------------
# set_overlay_roots — validation
# ---------------------------------------------------------------------------


def test_set_overlay_roots_rejects_duplicate_names(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    overlays = [
        OverlayRoot(name="utils", path=tmp_path / "a"),
        OverlayRoot(name="utils", path=tmp_path / "b"),
    ]
    with pytest.raises(ValueError, match="Duplicate overlay name"):
        set_overlay_roots(overlays)


def test_set_overlay_roots_rejects_missing_path(tmp_path: Path) -> None:
    overlays = [
        OverlayRoot(name="utils", path=tmp_path / "does-not-exist"),
    ]
    with pytest.raises(ValueError, match="Overlay path does not exist"):
        set_overlay_roots(overlays)


def test_set_overlay_roots_rejects_file_path(tmp_path: Path) -> None:
    """A regular file isn't an overlay root — must be a directory."""
    file_path = tmp_path / "not-a-dir"
    file_path.write_text("nope")
    overlays = [OverlayRoot(name="utils", path=file_path)]
    with pytest.raises(ValueError, match="not a directory"):
        set_overlay_roots(overlays)


def test_set_overlay_roots_persists_to_global_config(tmp_path: Path) -> None:
    """After successful set, ``get_config().overlay_roots`` reflects them."""
    from mcp_1c.config import get_config

    (tmp_path / "u").mkdir()
    (tmp_path / "v").mkdir()
    overlays = [
        OverlayRoot(name="u", path=tmp_path / "u", priority=50),
        OverlayRoot(name="v", path=tmp_path / "v"),
    ]
    set_overlay_roots(overlays)
    cfg = get_config()
    try:
        assert [o.name for o in cfg.overlay_roots] == ["u", "v"]
        assert cfg.overlay_roots[0].priority == 50
    finally:
        # Reset so other tests aren't polluted with our overlays.
        cfg.overlay_roots = []


def test_app_config_default_overlay_roots_is_empty() -> None:
    """No overlays by default — single-root mode stays the historical
    default."""
    cfg = AppConfig()
    assert cfg.overlay_roots == []
