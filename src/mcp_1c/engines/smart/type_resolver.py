"""
Type resolver for 1C metadata types.

Converts between cfg: English prefixes, Russian type prefixes,
and 1C query language table names.

F4 parameterization: methods that depend on configuration conventions
(presentation field, query-table language) accept an optional
``profile: ConfigurationProfile`` argument. The legacy zero-arg form
remains for backward-compat — callers without a workspace handle
get the historical "typical-БСП-with-russian-names" behaviour.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_1c.engines.profile import ConfigurationProfile

# ── Reference type prefix → English canonical name ──────────────────────────
# Own copy — do NOT import from knowledge_graph to avoid circular dependencies.

_REF_PREFIX_TO_ENGLISH: dict[str, str] = {
    # Russian reference prefixes
    "СправочникСсылка": "Catalog",
    "ДокументСсылка": "Document",
    "ПеречислениеСсылка": "Enum",
    "ПланВидовХарактеристикСсылка": "ChartOfCharacteristicTypes",
    "ПланСчетовСсылка": "ChartOfAccounts",
    "ПланВидовРасчетаСсылка": "ChartOfCalculationTypes",
    "БизнесПроцессСсылка": "BusinessProcess",
    "ЗадачаСсылка": "Task",
    "ПланОбменаСсылка": "ExchangePlan",
    # English cfg: prefixes
    "cfg:CatalogRef": "Catalog",
    "cfg:DocumentRef": "Document",
    "cfg:EnumRef": "Enum",
    "cfg:ChartOfCharacteristicTypesRef": "ChartOfCharacteristicTypes",
    "cfg:ChartOfAccountsRef": "ChartOfAccounts",
    "cfg:ChartOfCalculationTypesRef": "ChartOfCalculationTypes",
    "cfg:BusinessProcessRef": "BusinessProcess",
    "cfg:TaskRef": "Task",
    "cfg:ExchangePlanRef": "ExchangePlan",
}

# ── English canonical name → Russian query table prefix ─────────────────────

_ENGLISH_TO_RUSSIAN_TABLE: dict[str, str] = {
    "Catalog": "Справочник",
    "Document": "Документ",
    "Enum": "Перечисление",
    "ChartOfCharacteristicTypes": "ПланВидовХарактеристик",
    "ChartOfAccounts": "ПланСчетов",
    "ChartOfCalculationTypes": "ПланВидовРасчета",
    "ExchangePlan": "ПланОбмена",
    "BusinessProcess": "БизнесПроцесс",
    "Task": "Задача",
    "InformationRegister": "РегистрСведений",
    "AccumulationRegister": "РегистрНакопления",
    "AccountingRegister": "РегистрБухгалтерии",
    "CalculationRegister": "РегистрРасчета",
}

# ── Types that use "Наименование" vs "Номер" as presentation field ──────────

_PRESENTATION_FIELD: dict[str, str] = {
    "Catalog": "Наименование",
    "ChartOfCharacteristicTypes": "Наименование",
    "ChartOfAccounts": "Наименование",
    "ChartOfCalculationTypes": "Наименование",
    "ExchangePlan": "Наименование",
    "BusinessProcess": "Номер",
    "Task": "Наименование",
    "Document": "Номер",
}

# Regex: prefix.ObjectName (longest-first for correct matching)
_sorted_prefixes = sorted(_REF_PREFIX_TO_ENGLISH.keys(), key=len, reverse=True)
_REF_PATTERN = re.compile(
    r"^(" + "|".join(re.escape(p) for p in _sorted_prefixes) + r")\.(.+)$"
)

# Primitive types recognized in 1C
_PRIMITIVE_TYPES = frozenset({
    "String", "Number", "Date", "Boolean",
    "Строка", "Число", "Дата", "Булево",
    "ValueStorage", "ХранилищеЗначения",
    "UUID", "УникальныйИдентификатор",
    "Null", "Undefined", "Неопределено",
})


class TypeResolver:
    """Resolves 1C type strings for use in queries and code generation."""

    @staticmethod
    def is_reference_type(type_str: str) -> bool:
        """Check if a type string represents a reference type.

        Args:
            type_str: Type string like "cfg:CatalogRef.Товары" or "СправочникСсылка.Товары"

        Returns:
            True if this is a reference to another metadata object.
        """
        return _REF_PATTERN.match(type_str) is not None

    @staticmethod
    def is_enum_type(type_str: str) -> bool:
        """Check if a type string represents an enum reference."""
        return type_str.startswith(("cfg:EnumRef.", "ПеречислениеСсылка."))

    @staticmethod
    def is_primitive_type(type_str: str) -> bool:
        """Check if a type string is a primitive (non-reference) type."""
        return type_str in _PRIMITIVE_TYPES

    @staticmethod
    def parse_reference(type_str: str) -> tuple[str, str] | None:
        """Parse a reference type string into (english_kind, object_name).

        Args:
            type_str: E.g. "cfg:CatalogRef.Товары" or "СправочникСсылка.Товары"

        Returns:
            Tuple of (english_kind, object_name) or None if not a reference.
        """
        m = _REF_PATTERN.match(type_str)
        if not m:
            return None
        prefix, obj_name = m.group(1), m.group(2)
        english_kind = _REF_PREFIX_TO_ENGLISH[prefix]
        return english_kind, obj_name

    @staticmethod
    def to_query_table(type_str: str) -> str | None:
        """Convert a reference type to its 1C query table name.

        Args:
            type_str: E.g. "cfg:CatalogRef.Товары" → "Справочник.Товары"

        Returns:
            Russian query table name or None if not a reference.
        """
        parsed = TypeResolver.parse_reference(type_str)
        if parsed is None:
            return None
        eng_kind, obj_name = parsed
        rus_prefix = _ENGLISH_TO_RUSSIAN_TABLE.get(eng_kind)
        if rus_prefix is None:
            return None
        return f"{rus_prefix}.{obj_name}"

    @staticmethod
    def to_russian_type_prefix(
        eng_type: str, profile: ConfigurationProfile | None = None
    ) -> str:
        """Convert English metadata type to a query-table prefix.

        For ``profile.language == "ru"`` (default) returns the russian
        prefix (``Справочник`` etc.); for ``en`` returns the English
        canonical name unchanged so generated queries match
        identifiers in EDT/international configurations.

        Resolution order: explicit ``profile`` arg → active profile
        bound via smart-context ContextVar → default "ru".

        Args:
            eng_type: "Catalog", "Document", etc.
            profile: Project profile; falls back to context var.
        """
        if profile is None:
            from mcp_1c.engines.smart.context import get_active_profile

            profile = get_active_profile()
        if profile is not None and profile.effective_language == "en":
            return eng_type
        return _ENGLISH_TO_RUSSIAN_TABLE.get(eng_type, eng_type)

    @staticmethod
    def get_presentation_field(
        type_str: str,
        *,
        profile: ConfigurationProfile | None = None,
        object_full_name: str | None = None,
    ) -> str:
        """Get the presentation field for a reference type.

        Three layers, in priority order:

        1. **Per-object override** (``profile.naming.presentation_field_overrides``)
           keyed by ``object_full_name`` (e.g. ``Catalog.Контрагенты``).
           Highest precedence — wins over both type-defaults and the
           catch-all "Наименование".
        2. **Type defaults** (``Catalog`` → ``Наименование``,
           ``Document`` → ``Номер``, …).
        3. **Final fallback** — ``Наименование``.

        Profile resolution: explicit arg → smart-context ContextVar →
        no profile (defaults only).

        Args:
            type_str: Reference type string.
            profile: Project profile; pass-through unused when ``None``.
            object_full_name: Fully-qualified object name for the
                override lookup. Optional — without it we still apply
                type defaults.
        """
        if profile is None:
            from mcp_1c.engines.smart.context import get_active_profile

            profile = get_active_profile()
        # Per-object override has highest priority — even beats type defaults.
        if profile is not None and object_full_name is not None:
            override = profile.naming.presentation_field_overrides.get(
                object_full_name
            )
            if override:
                return override
        parsed = TypeResolver.parse_reference(type_str)
        if parsed is None:
            return "Наименование"
        eng_kind, _ = parsed
        return _PRESENTATION_FIELD.get(eng_kind, "Наименование")
