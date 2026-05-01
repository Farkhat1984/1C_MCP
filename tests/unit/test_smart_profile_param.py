"""F4.4 — smart-builder параметризация через ConfigurationProfile.

Each test isolates one knob:
- language: ru → russian table prefixes; en → English canonical
- obsolete_prefixes: skip Удалить by default; +_old когда профиль велит
- presentation_field_overrides: per-object override beats type default

Builders that don't take a profile arg silently keep historical
behaviour — that's backward compat for any old call site.
"""

from __future__ import annotations

from mcp_1c.domain.metadata import Attribute
from mcp_1c.engines.profile import (
    ConfigurationProfile,
    NamingSection,
)
from mcp_1c.engines.smart.query_builder import _should_skip
from mcp_1c.engines.smart.type_resolver import TypeResolver


def _attr(name: str, type_: str = "String") -> Attribute:
    return Attribute(name=name, type=type_)


# ---------------------------------------------------------------------------
# TypeResolver.to_russian_type_prefix
# ---------------------------------------------------------------------------


def test_to_russian_prefix_default_returns_russian() -> None:
    """No profile → historical "ru" behaviour."""
    assert TypeResolver.to_russian_type_prefix("Catalog") == "Справочник"
    assert TypeResolver.to_russian_type_prefix("Document") == "Документ"


def test_to_russian_prefix_en_profile_returns_english() -> None:
    """`profile.language == "en"` → keep canonical English unchanged."""
    profile = ConfigurationProfile(language="en")
    assert TypeResolver.to_russian_type_prefix("Catalog", profile) == "Catalog"
    assert TypeResolver.to_russian_type_prefix("Document", profile) == "Document"


def test_to_russian_prefix_ru_profile_returns_russian() -> None:
    profile = ConfigurationProfile(language="ru")
    assert TypeResolver.to_russian_type_prefix("Catalog", profile) == "Справочник"


# ---------------------------------------------------------------------------
# TypeResolver.get_presentation_field
# ---------------------------------------------------------------------------


def test_presentation_field_default_for_catalog() -> None:
    """No profile, catalog ref → "Наименование"."""
    assert (
        TypeResolver.get_presentation_field("СправочникСсылка.Контрагенты")
        == "Наименование"
    )


def test_presentation_field_default_for_document() -> None:
    assert (
        TypeResolver.get_presentation_field("ДокументСсылка.РеализацияТоваров")
        == "Номер"
    )


def test_presentation_field_per_object_override_wins() -> None:
    """Override key keys is the *full name* (Catalog.X), not a type."""
    profile = ConfigurationProfile(
        naming=NamingSection(
            presentation_field_overrides={
                "Catalog.Контрагенты": "НаименованиеПолное",
            },
        ),
    )
    assert (
        TypeResolver.get_presentation_field(
            "СправочникСсылка.Контрагенты",
            profile=profile,
            object_full_name="Catalog.Контрагенты",
        )
        == "НаименованиеПолное"
    )


def test_presentation_field_override_misses_falls_through_to_default() -> None:
    """Override for one catalog must NOT leak to another."""
    profile = ConfigurationProfile(
        naming=NamingSection(
            presentation_field_overrides={
                "Catalog.Контрагенты": "НаименованиеПолное",
            },
        ),
    )
    assert (
        TypeResolver.get_presentation_field(
            "СправочникСсылка.Товары",
            profile=profile,
            object_full_name="Catalog.Товары",
        )
        == "Наименование"
    )


def test_presentation_field_no_object_name_uses_type_default() -> None:
    """Without object_full_name we can't apply per-object overrides;
    type default still works."""
    profile = ConfigurationProfile(
        naming=NamingSection(
            presentation_field_overrides={"Catalog.X": "Custom"},
        ),
    )
    # No object_full_name → can't match override → type default.
    assert (
        TypeResolver.get_presentation_field(
            "СправочникСсылка.X", profile=profile
        )
        == "Наименование"
    )


# ---------------------------------------------------------------------------
# query_builder._should_skip
# ---------------------------------------------------------------------------


def test_should_skip_default_drops_удалить() -> None:
    """No profile → drop Удалить-prefixed (legacy default)."""
    assert _should_skip(_attr("УдалитьСтараяПозиция")) is True
    assert _should_skip(_attr("Активный")) is False


def test_should_skip_profile_with_added_prefixes() -> None:
    """Profile may extend the obsolete-prefix list (e.g. _old, Obsolete_)."""
    profile = ConfigurationProfile(
        naming=NamingSection(obsolete_prefixes=["Удалить", "_old"]),
    )
    assert _should_skip(_attr("_oldField"), profile) is True
    assert _should_skip(_attr("УдалитьА"), profile) is True
    assert _should_skip(_attr("Активный"), profile) is False


def test_should_skip_profile_with_only_custom_prefix() -> None:
    """If the profile drops Удалить from the list, we honour it —
    самописная without that convention shouldn't waste fields."""
    profile = ConfigurationProfile(
        naming=NamingSection(obsolete_prefixes=["Obsolete_"]),
    )
    # Удалить is no longer in the list → not skipped any more.
    assert _should_skip(_attr("УдалитьА"), profile) is False
    assert _should_skip(_attr("Obsolete_X"), profile) is True


def test_should_skip_profile_empty_keeps_everything() -> None:
    """Empty obsolete_prefixes → all attrs kept (config without
    legacy markers)."""
    profile = ConfigurationProfile(
        naming=NamingSection(obsolete_prefixes=[]),
    )
    assert _should_skip(_attr("УдалитьА"), profile) is False
    assert _should_skip(_attr("Активный"), profile) is False
