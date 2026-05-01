"""Auto-detector for ConfigurationProfile.

We use the synthetic ``mock_config_path`` fixture for unit-level
checks and gate the QGA (real ZUP dump) test behind ``-m qga`` so it
only runs when the dump is on disk.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from mcp_1c.domain.metadata import (
    Attribute,
    MetadataObject,
    MetadataType,
)
from mcp_1c.engines.metadata import MetadataEngine
from mcp_1c.engines.profile import (
    ConfigurationProfile,
    detect_profile,
    merge_profiles,
)


def _make_obj(
    metadata_type: MetadataType,
    name: str,
    *,
    attributes: list[Attribute] | None = None,
) -> MetadataObject:
    return MetadataObject(
        name=name,
        metadata_type=metadata_type,
        config_path=Path("/tmp"),
        object_path=Path("/tmp"),
        attributes=attributes or [],
    )


def _attr(name: str) -> Attribute:
    return Attribute(name=name, type="String")


# ---------------------------------------------------------------------------
# Detector unit tests with hand-crafted MetadataEngine mocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_language_detection_picks_ru_for_cyrillic_dominant() -> None:
    fake = MagicMock()

    async def _list(md_type):
        if md_type == MetadataType.CATALOG:
            return [
                _make_obj(MetadataType.CATALOG, "Контрагенты"),
                _make_obj(MetadataType.CATALOG, "Товары"),
                _make_obj(MetadataType.CATALOG, "OpenIDProvider"),  # english outlier
            ]
        return []

    fake.list_objects = _list
    profile = await detect_profile(fake)
    assert profile.language == "ru"
    assert profile.naming.language == "ru"


@pytest.mark.asyncio
async def test_language_detection_picks_en_when_majority_ascii() -> None:
    fake = MagicMock()

    async def _list(md_type):
        if md_type == MetadataType.CATALOG:
            return [
                _make_obj(MetadataType.CATALOG, "Counterparties"),
                _make_obj(MetadataType.CATALOG, "Products"),
                _make_obj(MetadataType.CATALOG, "Banks"),
            ]
        return []

    fake.list_objects = _list
    profile = await detect_profile(fake)
    assert profile.language == "en"


@pytest.mark.asyncio
async def test_language_detection_defaults_to_ru_on_empty() -> None:
    """No data → keep historical default."""
    fake = MagicMock()

    async def _list(md_type):
        return []

    fake.list_objects = _list
    profile = await detect_profile(fake)
    assert profile.language == "ru"


@pytest.mark.asyncio
async def test_bsp_used_true_when_marker_module_present() -> None:
    fake = MagicMock()

    async def _list(md_type):
        if md_type == MetadataType.COMMON_MODULE:
            return [_make_obj(MetadataType.COMMON_MODULE, "ОбщегоНазначения")]
        return []

    fake.list_objects = _list
    profile = await detect_profile(fake)
    assert profile.bsp.used is True


@pytest.mark.asyncio
async def test_bsp_used_false_when_no_marker() -> None:
    fake = MagicMock()

    async def _list(md_type):
        if md_type == MetadataType.COMMON_MODULE:
            return [_make_obj(MetadataType.COMMON_MODULE, "НашиОбщие")]
        return []

    fake.list_objects = _list
    profile = await detect_profile(fake)
    assert profile.bsp.used is False


@pytest.mark.asyncio
async def test_obsolete_prefix_discovery_kicks_in_after_threshold() -> None:
    """``_old`` recurring across attributes → detector adds it."""
    fake = MagicMock()
    catalog_with_legacy = _make_obj(
        MetadataType.CATALOG,
        "Контрагенты",
        attributes=[
            _attr(f"_oldField{i}") for i in range(6)
        ] + [_attr("Активный")],
    )

    async def _list(md_type):
        if md_type == MetadataType.CATALOG:
            return [catalog_with_legacy]
        return []

    fake.list_objects = _list
    profile = await detect_profile(fake)
    assert "_old" in profile.naming.obsolete_prefixes
    # Default ``Удалить`` always preserved.
    assert "Удалить" in profile.naming.obsolete_prefixes


@pytest.mark.asyncio
async def test_obsolete_prefix_under_threshold_ignored() -> None:
    """A handful of `_old` attributes is noise — don't surface them."""
    fake = MagicMock()
    obj = _make_obj(
        MetadataType.CATALOG,
        "X",
        attributes=[_attr("_oldA"), _attr("_oldB")],  # only 2
    )

    async def _list(md_type):
        if md_type == MetadataType.CATALOG:
            return [obj]
        return []

    fake.list_objects = _list
    profile = await detect_profile(fake)
    assert "_old" not in profile.naming.obsolete_prefixes


# ---------------------------------------------------------------------------
# merge_profiles
# ---------------------------------------------------------------------------


def test_merge_override_wins_for_non_default_values() -> None:
    base = ConfigurationProfile()  # all defaults
    override = ConfigurationProfile(language="en", bsp={"used": False})
    merged = merge_profiles(base, override)
    assert merged.language == "en"
    assert merged.bsp.used is False
    # Untouched fields keep base defaults:
    assert "Удалить" in merged.naming.obsolete_prefixes


def test_merge_keeps_base_when_override_at_default() -> None:
    """A default override value must not undo a non-default base."""
    base = ConfigurationProfile(bsp={"used": False, "version": "3.1.10"})
    override = ConfigurationProfile()  # all defaults
    merged = merge_profiles(base, override)
    assert merged.bsp.used is False
    assert merged.bsp.version == "3.1.10"


def test_merge_recurses_into_nested_sections() -> None:
    base = ConfigurationProfile(
        naming={"obsolete_prefixes": ["Удалить", "_old"]},
    )
    override = ConfigurationProfile(naming={"language": "en"})
    merged = merge_profiles(base, override)
    assert merged.naming.language == "en"
    assert "_old" in merged.naming.obsolete_prefixes


# ---------------------------------------------------------------------------
# Synthetic mock_config_path integration
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def fresh_engine() -> MetadataEngine:
    import contextlib

    MetadataEngine._instance = None
    engine = MetadataEngine()
    yield engine
    with contextlib.suppress(Exception):
        await engine.shutdown()
    MetadataEngine._instance = None


@pytest.mark.asyncio
async def test_detect_profile_runs_against_mock_config(
    fresh_engine: MetadataEngine, mock_config_path: Path
) -> None:
    """End-to-end on the synthetic config: detect runs without errors,
    produces a non-trivial profile."""
    await fresh_engine.initialize(
        mock_config_path, full_reindex=True, watch=False
    )
    profile = await detect_profile(fresh_engine)
    # Mock config has cyrillic catalog/document names → language=ru.
    assert profile.language == "ru"
    # Has CommonModule.ОбщегоНазначения → bsp.used should be True.
    assert profile.bsp.used is True


# ---------------------------------------------------------------------------
# Real ZUP (QGA) fixture — gated, expensive
# ---------------------------------------------------------------------------


_QGA_PATH = Path("/home/faragj/qga_config/qga")


@pytest.mark.qga
@pytest.mark.asyncio
async def test_detect_profile_against_real_zup(
    fresh_engine: MetadataEngine,
) -> None:
    """Smoke test against the real ZUP (qga) dump.

    Skipped automatically when the dump isn't on disk. Useful as a
    diagnostic when iterating on detector heuristics — run with
    ``pytest -m qga`` to enable.
    """
    if not _QGA_PATH.exists():
        pytest.skip("QGA dump not available")
    await fresh_engine.initialize(_QGA_PATH, full_reindex=False, watch=False)
    profile = await detect_profile(fresh_engine)
    assert profile.language == "ru"  # ZUP is russian-named
    assert profile.bsp.used is True  # Has БСП
    # ZUP doesn't use _old/Obsolete_ broadly — just confirm the
    # default Удалить is preserved.
    assert "Удалить" in profile.naming.obsolete_prefixes
