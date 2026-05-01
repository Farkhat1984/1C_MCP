"""Pydantic models for the ``.mcp_1c_project.yaml`` schema.

Why split into sections (NamingSection, BspSection, PatternsSection)
instead of one flat model: each section maps to a top-level YAML key,
so the schema reads naturally even with comments interleaved. It also
lets the auto-detector return a partial profile that touches only one
section (e.g. ``ConfigurationProfile(naming=NamingSection(language="en"))``)
without having to spell out the unset sections explicitly — Pydantic
fills them with defaults.

All fields default-valued so an empty YAML or a missing file becomes a
``ConfigurationProfile()`` with sensible defaults that match the
historical "typical-configuration-with-БСП" assumption — no breaking
change for existing single-config deploys.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PrintFormStrategy(StrEnum):
    """How ``smart-print`` lays out the generated print procedure."""

    DEFAULT = "default"
    """Standalone print procedure — no BSP dependencies. Suitable for
    самописных configurations and for legacy code that doesn't import
    БСП.УправлениеПечатью."""

    BSP_PRINT_MANAGEMENT = "bsp_print_management"
    """BSP-style: emit ``Функция Печать(...)`` that returns
    ``ТабличныйДокумент`` and registers via ``УправлениеПечатью``.
    Default for typical БСП configurations (УТ/ERP/БП/ЗУП)."""

    CUSTOM = "custom"
    """Use a Jinja2 template at ``patterns.print_form.custom_path``.
    Reserved for teams with their own house style — F4.5+."""


class MovementStrategy(StrEnum):
    """How ``smart-movement`` shapes the generated movement code."""

    REGISTER_SET = "register_set"
    """``Движения.<Регистр>.Записывать = Истина`` style — the dominant
    БСП pattern. Good default."""

    DIRECT_ASSIGN = "direct_assign"
    """Direct ``Запись = РегистрСведений.<Имя>.СоздатьМенеджерЗаписи()``
    style — used in older code and some самописных configurations."""


class NamingSection(BaseModel):
    """Conventions about how things are *named* in this configuration."""

    language: Literal["ru", "en"] = Field(
        default="ru",
        description=(
            "Language of metadata identifiers. ``ru`` for cyrillic "
            "typical configs (Справочник.Контрагенты), ``en`` for EDT/"
            "international configs (Catalog.Counterparties)."
        ),
    )
    obsolete_prefixes: list[str] = Field(
        default_factory=lambda: ["Удалить"],
        description=(
            "Prefixes that mark legacy/deleted attributes — these are "
            "skipped from generated SELECT lists. Default ``Удалить`` "
            "matches БСП convention. Add e.g. ``_old``, ``Obsolete_`` "
            "for самописные configurations."
        ),
    )
    presentation_field_overrides: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Per-object overrides for the presentation field, keyed by "
            "fully-qualified object name (``Catalog.Контрагенты``). "
            "Useful when a catalog uses a custom field for display "
            "instead of the default ``Наименование``. Example:\n"
            "  Catalog.Контрагенты: НаименованиеПолное"
        ),
    )

    model_config = ConfigDict(extra="forbid")


class BspSection(BaseModel):
    """Library of Standard Subsystems (БСП) usage and version pinning."""

    used: bool = Field(
        default=True,
        description=(
            "Does this configuration use БСП? The auto-detector flips "
            "this off when no Стандартные Подсистемы common modules "
            "exist. ``False`` switches smart-print to standalone "
            "template, smart-* warnings are silenced for missing БСП "
            "hooks, etc."
        ),
    )
    version: str = Field(
        default="",
        description=(
            "БСП version (e.g. ``3.1.10``). Used by BspEngine to pick "
            "the right hook signatures and review rules. Empty = "
            "version-agnostic fallback to bundled JSON. Auto-detected "
            "from Constants.ВерсияБиблиотекиСтандартныхПодсистем if "
            "present."
        ),
    )
    disabled_modules: list[str] = Field(
        default_factory=list,
        description=(
            "Names of БСП common modules the project explicitly disables "
            "or replaces. The detector won't suggest hooks from these."
        ),
    )

    model_config = ConfigDict(extra="forbid")


class PrintFormPatterns(BaseModel):
    """Settings specific to ``smart-print``."""

    template: PrintFormStrategy = Field(
        default=PrintFormStrategy.BSP_PRINT_MANAGEMENT,
        description="Which template the generator uses.",
    )
    custom_path: Path | None = Field(
        default=None,
        description=(
            "Path to a Jinja2 template, used when ``template == custom``. "
            "Resolved relative to the config root."
        ),
    )

    model_config = ConfigDict(extra="forbid")


class MovementPatterns(BaseModel):
    """Settings specific to ``smart-movement``."""

    style: MovementStrategy = Field(
        default=MovementStrategy.REGISTER_SET,
        description="Movement code style.",
    )

    model_config = ConfigDict(extra="forbid")


class PatternsSection(BaseModel):
    """Per-domain generation pattern choices."""

    print_form: PrintFormPatterns = Field(default_factory=PrintFormPatterns)
    movement: MovementPatterns = Field(default_factory=MovementPatterns)

    model_config = ConfigDict(extra="forbid")


class ExtensionDescriptor(BaseModel):
    """Metadata about an extension already known to the project.

    Auto-populated by the detector from ``ExtensionEngine.list_extensions``
    on first run; the developer can override manually (e.g. force a
    purpose tag the parser couldn't infer)."""

    name: str
    purpose: str = Field(default="Unknown")

    model_config = ConfigDict(extra="forbid")


class ConfigurationProfile(BaseModel):
    """Top-level project profile — what gets serialised to YAML.

    Defaults match the typical-configuration-with-БСП assumption so that
    a missing or empty ``.mcp_1c_project.yaml`` produces the same
    behaviour the codebase had before F4. Auto-detect overlays *only*
    fields it confidently identifies; leaves the rest at default for
    the user to review.
    """

    language: Literal["ru", "en"] = Field(
        default="ru",
        description="Shortcut alias for naming.language; kept top-level for ergonomics.",
    )
    naming: NamingSection = Field(default_factory=NamingSection)
    bsp: BspSection = Field(default_factory=BspSection)
    patterns: PatternsSection = Field(default_factory=PatternsSection)
    extensions: list[ExtensionDescriptor] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _sync_language_alias(cls, data: object) -> object:
        """Synchronise top-level ``language`` alias with ``naming.language``.

        Cases handled:
        - Both unset → both stay default (``ru``).
        - Only top-level set → copy it down into ``naming``, **preserving
          any other fields** when ``naming`` is passed as a dict or a
          ``NamingSection`` instance.
        - Both set, different values → ``naming`` wins (it's the
          ground truth; the top-level is a convenience alias).
        - Both set, same value → no-op.

        Runs in ``mode="before"`` so we work on the raw input dict
        rather than the constructed model — that's the only stage
        where "was the field explicitly given?" is observable
        without bookkeeping.

        Critical edge: ``naming`` may arrive as either a dict (YAML
        path) or a ``NamingSection`` instance (programmatic path
        — e.g. the auto-detector mutates a section then passes it).
        We coerce both into a dict for transformation and let Pydantic
        re-validate. Failing to handle the instance case used to drop
        every field in ``naming`` other than ``language`` — caught by
        the regression test ``test_obsolete_prefix_discovery_kicks_in
        _after_threshold``.
        """
        if not isinstance(data, dict):
            return data
        top_level = data.get("language")
        naming = data.get("naming")

        # Coerce naming → dict for uniform handling; remember whether
        # we need to write it back.
        naming_dict: dict | None
        if isinstance(naming, dict):
            naming_dict = dict(naming)
        elif naming is None:
            naming_dict = None
        else:
            # NamingSection instance — round-trip through model_dump
            # so we don't depend on private attributes.
            try:
                naming_dict = naming.model_dump()
            except AttributeError:
                naming_dict = None

        nested = naming_dict.get("language") if naming_dict is not None else None

        if top_level is None and nested is not None:
            data["language"] = nested
        elif top_level is not None and nested is None:
            if naming_dict is None:
                naming_dict = {}
            naming_dict["language"] = top_level
            data["naming"] = naming_dict
        elif top_level is not None and nested is not None and top_level != nested:
            # Nested wins; sync the top-level alias for self-consistency.
            data["language"] = nested
        return data

    @property
    def effective_language(self) -> Literal["ru", "en"]:
        """Single source of truth callers should consult."""
        return self.naming.language


__all__ = [
    "BspSection",
    "ConfigurationProfile",
    "ExtensionDescriptor",
    "MovementPatterns",
    "MovementStrategy",
    "NamingSection",
    "PatternsSection",
    "PrintFormPatterns",
    "PrintFormStrategy",
]
