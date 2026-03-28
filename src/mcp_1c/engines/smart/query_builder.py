"""
Query builder for 1C metadata objects.

Builds syntactically correct 1C query language text
from MetadataObject definitions.
"""

from __future__ import annotations

from mcp_1c.domain.metadata import Attribute, MetadataObject, TabularSection
from mcp_1c.engines.smart.type_resolver import TypeResolver

# Attributes to always skip in generated queries
_SKIP_PREFIXES = ("Удалить",)

# Numeric types in 1C (for totals detection)
_NUMERIC_TYPES = frozenset({"Number", "Число"})


def _should_skip(attr: Attribute) -> bool:
    """Return True if attribute should be excluded from generated queries."""
    return any(attr.name.startswith(p) for p in _SKIP_PREFIXES)


def _build_field_expression(
    attr: Attribute,
    table_alias: str,
) -> tuple[str, str]:
    """Build a SELECT field expression for an attribute.

    Returns:
        Tuple of (expression, alias). For reference types, dereferences via dot
        to the presentation field. For primitives, uses direct access.
    """
    if TypeResolver.is_reference_type(attr.type) and not TypeResolver.is_enum_type(attr.type):
        pres_field = TypeResolver.get_presentation_field(attr.type)
        expr = f"{table_alias}.{attr.name}.{pres_field}"
        alias = f"{attr.name}Представление"
        return expr, alias

    if TypeResolver.is_enum_type(attr.type):
        expr = f"{table_alias}.{attr.name}"
        return expr, attr.name

    expr = f"{table_alias}.{attr.name}"
    return expr, attr.name


class QueryBuilder:
    """Builds 1C query language text from MetadataObject definitions."""

    @staticmethod
    def build_object_query(
        obj: MetadataObject,
        *,
        include_tabular: str | None = None,
        fields: list[str] | None = None,
        for_print: bool = False,
    ) -> str:
        """Build a query for a metadata object.

        For print forms (for_print=True), uses the flat pattern: query FROM
        tabular section directly, access header fields via .Ссылка.

        Args:
            obj: Metadata object with attributes and tabular sections.
            include_tabular: Name of tabular section to include.
            fields: Specific field names to include (None = all).
            for_print: If True, build print-form-style query with WHERE and ИТОГИ.

        Returns:
            Complete 1C query text.
        """
        if for_print and include_tabular:
            return QueryBuilder._build_print_query(obj, include_tabular, fields)
        return QueryBuilder._build_standard_query(obj, include_tabular, fields, for_print)

    @staticmethod
    def _find_tabular_section(obj: MetadataObject, name: str) -> TabularSection | None:
        """Find a tabular section by name."""
        for ts in obj.tabular_sections:
            if ts.name == name:
                return ts
        return None

    @staticmethod
    def get_numeric_attributes(ts: TabularSection) -> list[Attribute]:
        """Get numeric attributes from a tabular section (for totals)."""
        return [a for a in ts.attributes if a.type in _NUMERIC_TYPES and not _should_skip(a)]

    @staticmethod
    def _build_print_query(
        obj: MetadataObject,
        tabular_name: str,
        fields: list[str] | None,
    ) -> str:
        """Build print-form query (FROM tabular section, header via .Ссылка).

        Pattern:
            SELECT ДокТЧ.Ссылка.Номер, ДокТЧ.Ссылка.Дата, ДокТЧ.Field, ...
            FROM Документ.X.ТЧ AS ДокТЧ
            WHERE ДокТЧ.Ссылка IN (&МассивОбъектов)
            ИТОГИ BY ДокТЧ.Ссылка
        """
        ts = QueryBuilder._find_tabular_section(obj, tabular_name)
        if ts is None:
            return QueryBuilder._build_standard_query(obj, None, fields, True)

        rus_prefix = TypeResolver.to_russian_type_prefix(obj.metadata_type.value)
        table_full = f"{rus_prefix}.{obj.name}.{tabular_name}"
        alias = "ДокТЧ"

        select_parts: list[str] = []

        # Header fields via .Ссылка
        header_attrs = [a for a in obj.attributes if not _should_skip(a)]
        if fields:
            header_attrs = [a for a in header_attrs if a.name in fields]

        # Always include Номер and Дата for documents
        if obj.metadata_type.value == "Document":
            select_parts.append(f"    {alias}.Ссылка.Номер КАК Номер")
            select_parts.append(f"    {alias}.Ссылка.Дата КАК Дата")

        for attr in header_attrs:
            if attr.name in ("Номер", "Дата"):
                continue
            if TypeResolver.is_reference_type(attr.type) and not TypeResolver.is_enum_type(attr.type):
                pres = TypeResolver.get_presentation_field(attr.type)
                select_parts.append(f"    {alias}.Ссылка.{attr.name}.{pres} КАК {attr.name}")
            else:
                select_parts.append(f"    {alias}.Ссылка.{attr.name} КАК {attr.name}")

        # Tabular section fields
        ts_attrs = [a for a in ts.attributes if not _should_skip(a)]
        if fields:
            ts_attrs = [a for a in ts_attrs if a.name in fields]

        for attr in ts_attrs:
            if TypeResolver.is_reference_type(attr.type) and not TypeResolver.is_enum_type(attr.type):
                pres = TypeResolver.get_presentation_field(attr.type)
                select_parts.append(f"    {alias}.{attr.name}.{pres} КАК {attr.name}")
            else:
                select_parts.append(f"    {alias}.{attr.name} КАК {attr.name}")

        lines = ["ВЫБРАТЬ"]
        lines.append(",\n".join(select_parts))
        lines.append("ИЗ")
        lines.append(f"    {table_full} КАК {alias}")
        lines.append("ГДЕ")
        lines.append(f"    {alias}.Ссылка В (&МассивОбъектов)")
        lines.append("ИТОГИ ПО")
        lines.append(f"    {alias}.Ссылка")

        return "\n".join(lines)

    @staticmethod
    def _build_standard_query(
        obj: MetadataObject,
        include_tabular: str | None,
        fields: list[str] | None,
        for_print: bool,
    ) -> str:
        """Build standard query with optional LEFT JOIN for tabular section."""
        rus_prefix = TypeResolver.to_russian_type_prefix(obj.metadata_type.value)
        main_table = f"{rus_prefix}.{obj.name}"
        main_alias = "Док"

        select_parts: list[str] = [f"    {main_alias}.Ссылка"]

        # Header attributes
        header_attrs = [a for a in obj.attributes if not _should_skip(a)]
        if fields:
            header_attrs = [a for a in header_attrs if a.name in fields]

        for attr in header_attrs:
            expr, alias = _build_field_expression(attr, main_alias)
            if alias != attr.name:
                select_parts.append(f"    {expr} КАК {alias}")
            else:
                select_parts.append(f"    {expr}")

        # Tabular section via LEFT JOIN
        ts: TabularSection | None = None
        if include_tabular:
            ts = QueryBuilder._find_tabular_section(obj, include_tabular)
            if ts is not None:
                ts_alias = "ТЧ"
                ts_attrs = [a for a in ts.attributes if not _should_skip(a)]
                if fields:
                    ts_attrs = [a for a in ts_attrs if a.name in fields]
                for attr in ts_attrs:
                    expr, alias = _build_field_expression(attr, ts_alias)
                    if alias != attr.name:
                        select_parts.append(f"    {expr} КАК {alias}")
                    else:
                        select_parts.append(f"    {expr}")

        lines = ["ВЫБРАТЬ"]
        lines.append(",\n".join(select_parts))
        lines.append("ИЗ")
        lines.append(f"    {main_table} КАК {main_alias}")

        if ts is not None and include_tabular:
            lines.append(
                f"    ЛЕВОЕ СОЕДИНЕНИЕ {main_table}.{include_tabular} КАК ТЧ"
                f"\n    ПО ТЧ.Ссылка = {main_alias}.Ссылка"
            )

        if for_print:
            lines.append("ГДЕ")
            lines.append(f"    {main_alias}.Ссылка В (&МассивОбъектов)")
            lines.append("ИТОГИ ПО")
            lines.append(f"    {main_alias}.Ссылка")

        return "\n".join(lines)
