"""ConfigurationProfile schema + YAML loader/saver.

The detector lives in a separate test module — there it benefits from
the fully-built mock_config_path fixture which is heavier than what
schema/loader tests need.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_1c.engines.profile import (
    ConfigurationProfile,
    MovementStrategy,
    PrintFormStrategy,
    load_profile,
    save_profile,
)
from mcp_1c.engines.profile.loader import (
    PROFILE_FILENAME,
    ProfileError,
    profile_path,
)

# ---------------------------------------------------------------------------
# Schema defaults + invariants
# ---------------------------------------------------------------------------


def test_default_profile_matches_typical_bsp_config() -> None:
    """Backward compat: an empty profile must produce the same behaviour
    the codebase had pre-F4 (БСП-style assumption)."""
    profile = ConfigurationProfile()
    assert profile.language == "ru"
    assert profile.naming.language == "ru"
    assert profile.bsp.used is True
    assert profile.naming.obsolete_prefixes == ["Удалить"]
    assert profile.patterns.print_form.template == PrintFormStrategy.BSP_PRINT_MANAGEMENT
    assert profile.patterns.movement.style == MovementStrategy.REGISTER_SET


def test_top_level_language_propagates_to_naming() -> None:
    """Setting top-level `language: en` must update `naming.language`."""
    profile = ConfigurationProfile(language="en")
    assert profile.naming.language == "en"
    assert profile.effective_language == "en"


def test_unknown_field_is_rejected() -> None:
    """Schema is closed — typos in the YAML root surface as validation
    errors, not silent data loss."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ConfigurationProfile.model_validate({"langauge": "ru"})  # typo


def test_print_form_strategy_enum_round_trips() -> None:
    profile = ConfigurationProfile.model_validate(
        {"patterns": {"print_form": {"template": "default"}}}
    )
    assert profile.patterns.print_form.template == PrintFormStrategy.DEFAULT


# ---------------------------------------------------------------------------
# Loader / saver
# ---------------------------------------------------------------------------


def test_profile_path_uses_dotfile_convention(tmp_path: Path) -> None:
    assert profile_path(tmp_path).name == PROFILE_FILENAME
    assert profile_path(tmp_path).parent == tmp_path


def test_load_profile_returns_default_when_file_missing(tmp_path: Path) -> None:
    profile = load_profile(tmp_path)
    assert profile == ConfigurationProfile()


def test_load_profile_parses_minimal_yaml(tmp_path: Path) -> None:
    (tmp_path / PROFILE_FILENAME).write_text(
        "language: en\nbsp:\n  used: false\n",
        encoding="utf-8",
    )
    profile = load_profile(tmp_path)
    assert profile.language == "en"
    assert profile.naming.language == "en"
    assert profile.bsp.used is False


def test_load_profile_raises_on_malformed_yaml(tmp_path: Path) -> None:
    (tmp_path / PROFILE_FILENAME).write_text(
        "this: is: not: valid: yaml:\n  ::",
        encoding="utf-8",
    )
    with pytest.raises(ProfileError, match="Malformed YAML"):
        load_profile(tmp_path)


def test_load_profile_raises_on_schema_mismatch(tmp_path: Path) -> None:
    """Unknown top-level key — schema validation fires."""
    (tmp_path / PROFILE_FILENAME).write_text(
        "completely_unknown_key: 1\n", encoding="utf-8"
    )
    with pytest.raises(ProfileError, match="schema mismatch"):
        load_profile(tmp_path)


def test_load_profile_raises_when_root_is_not_mapping(tmp_path: Path) -> None:
    (tmp_path / PROFILE_FILENAME).write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ProfileError, match="must be a mapping"):
        load_profile(tmp_path)


def test_save_profile_round_trips(tmp_path: Path) -> None:
    """Save → load yields the same profile (modulo header comments)."""
    original = ConfigurationProfile(
        language="en",
        naming={
            "language": "en",
            "obsolete_prefixes": ["Удалить", "_old"],
            "presentation_field_overrides": {"Catalog.X": "Display"},
        },
        bsp={"used": False, "version": "3.1.10", "disabled_modules": ["X"]},
    )
    saved_path = save_profile(tmp_path, original)
    assert saved_path.exists()
    reloaded = load_profile(tmp_path)
    assert reloaded == original


def test_save_profile_includes_header_comments(tmp_path: Path) -> None:
    """The saved file must start with the explanatory header so the
    file is self-documenting even without the docs handy."""
    save_profile(tmp_path, ConfigurationProfile())
    content = (tmp_path / PROFILE_FILENAME).read_text(encoding="utf-8")
    assert content.startswith("# .mcp_1c_project.yaml")
    assert "naming" in content
    assert "patterns" in content


def test_save_profile_preserves_unicode(tmp_path: Path) -> None:
    """Cyrillic identifiers in overrides must survive the round-trip."""
    profile = ConfigurationProfile(
        naming={
            "obsolete_prefixes": ["Удалить", "Старый"],
            "presentation_field_overrides": {"Catalog.Контрагенты": "Наименование"},
        }
    )
    save_profile(tmp_path, profile)
    raw = (tmp_path / PROFILE_FILENAME).read_text(encoding="utf-8")
    # Cyrillic must NOT be ASCII-escaped — yaml.safe_dump with allow_unicode=True.
    assert "Удалить" in raw
    assert "Контрагенты" in raw
    reloaded = load_profile(tmp_path)
    assert reloaded == profile
