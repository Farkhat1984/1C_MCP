"""
Print form builder for 1C metadata objects.

Generates complete BSP-compliant print form artifacts:
procedure code, manager module, MXL template XML, and query text.
"""

from __future__ import annotations

from mcp_1c.domain.metadata import Attribute, MetadataObject, TabularSection
from mcp_1c.engines.smart.query_builder import QueryBuilder, _should_skip
from mcp_1c.engines.smart.type_resolver import TypeResolver


def _sanitize_form_name(name: str) -> str:
    """Ensure form name is a valid 1C identifier (no spaces/special chars)."""
    return "".join(ch for ch in name if ch.isalnum() or ch == "_")


class PrintFormBuilder:
    """Generates complete print form artifacts from metadata."""

    @staticmethod
    def build(
        obj: MetadataObject,
        *,
        form_type: str = "with_query",  # noqa: ARG004
        include_tabular: bool = True,
        form_name: str | None = None,
    ) -> dict[str, str]:
        """Build all print form artifacts for a metadata object.

        Args:
            obj: Metadata object (typically a Document).
            form_type: Generation style ("with_query" is the standard BSP pattern).
            include_tabular: Whether to include the first tabular section.
            form_name: Custom form name. Defaults to obj.synonym or obj.name.

        Returns:
            Dict with keys: print_procedure, manager_module, mxl_template, query.
        """
        safe_name = _sanitize_form_name(form_name or obj.name)
        display_name = form_name or obj.synonym or obj.name

        ts_name: str | None = None
        if include_tabular and obj.tabular_sections:
            ts_name = obj.tabular_sections[0].name

        query_text = QueryBuilder.build_object_query(
            obj,
            include_tabular=ts_name,
            for_print=True,
        )

        procedure = PrintFormBuilder._build_procedure(obj, safe_name, display_name, query_text, ts_name)
        manager = PrintFormBuilder._build_manager_module(obj, safe_name, display_name)
        mxl = PrintFormBuilder._build_mxl_template(obj, safe_name, ts_name)

        return {
            "print_procedure": procedure,
            "manager_module": manager,
            "mxl_template": mxl,
            "query": query_text,
        }

    @staticmethod
    def _get_header_attrs(obj: MetadataObject) -> list[Attribute]:
        """Get non-deleted header attributes."""
        return [a for a in obj.attributes if not _should_skip(a)]

    @staticmethod
    def _get_ts_attrs(obj: MetadataObject, ts_name: str | None) -> list[Attribute]:
        """Get non-deleted tabular section attributes."""
        if ts_name is None:
            return []
        for ts in obj.tabular_sections:
            if ts.name == ts_name:
                return [a for a in ts.attributes if not _should_skip(a)]
        return []

    @staticmethod
    def _get_ts(obj: MetadataObject, ts_name: str | None) -> TabularSection | None:
        if ts_name is None:
            return None
        for ts in obj.tabular_sections:
            if ts.name == ts_name:
                return ts
        return None

    @staticmethod
    def _build_procedure(
        obj: MetadataObject,
        safe_name: str,
        display_name: str,  # noqa: ARG004
        query_text: str,
        ts_name: str | None,
    ) -> str:
        """Build the BSP-compliant print procedure."""
        rus_prefix = TypeResolver.to_russian_type_prefix(obj.metadata_type.value)
        header_attrs = PrintFormBuilder._get_header_attrs(obj)
        ts_attrs = PrintFormBuilder._get_ts_attrs(obj, ts_name)
        ts = PrintFormBuilder._get_ts(obj, ts_name)

        # Indent query for embedding in string literal
        query_indented = query_text.replace('"', '""')

        lines: list[str] = []
        lines.append(f"Функция Печать{safe_name}(МассивОбъектов, ОбъектыПечати) Экспорт")
        lines.append("")
        lines.append("    ТабличныйДокумент = Новый ТабличныйДокумент;")
        lines.append(f'    ТабличныйДокумент.КлючПараметровПечати = "ПФ_MXL_{safe_name}";')
        lines.append("")
        lines.append("    Макет = УправлениеПечатью.МакетПечатнойФормы(")
        lines.append(f'        "{rus_prefix}.{obj.name}.ПФ_MXL_{safe_name}");')
        lines.append("")
        lines.append('    ОбластьШапка = Макет.ПолучитьОбласть("Шапка");')

        if ts_name:
            lines.append('    ОбластьШапкаТаблицы = Макет.ПолучитьОбласть("ШапкаТаблицы");')
            lines.append('    ОбластьСтрока = Макет.ПолучитьОбласть("Строка");')

        lines.append('    ОбластьПодвал = Макет.ПолучитьОбласть("Подвал");')
        lines.append("")
        lines.append("    Запрос = Новый Запрос;")
        lines.append(f'    Запрос.Текст = "{query_indented}";')
        lines.append('    Запрос.УстановитьПараметр("МассивОбъектов", МассивОбъектов);')
        lines.append("")
        lines.append("    Результат = Запрос.Выполнить();")
        lines.append("    ВыборкаДокументы = Результат.Выбрать(ОбходРезультатаЗапроса.ПоГруппировкам);")
        lines.append("")
        lines.append("    Пока ВыборкаДокументы.Следующий() Цикл")
        lines.append("        НомерСтрокиНачало = ТабличныйДокумент.ВысотаТаблицы + 1;")
        lines.append("")

        # Fill header parameters
        if obj.metadata_type.value == "Document":
            lines.append("        ОбластьШапка.Параметры.Номер = ВыборкаДокументы.Номер;")
            lines.append('        ОбластьШапка.Параметры.Дата = Формат(ВыборкаДокументы.Дата, "ДЛФ=DD");')

        for attr in header_attrs:
            if attr.name in ("Номер", "Дата"):
                continue
            field_name = attr.name
            if TypeResolver.is_reference_type(attr.type) and not TypeResolver.is_enum_type(attr.type):
                field_name = attr.name
            lines.append(f"        ОбластьШапка.Параметры.{attr.name} = ВыборкаДокументы.{field_name};")

        lines.append("        ТабличныйДокумент.Вывести(ОбластьШапка);")

        if ts_name:
            lines.append("")
            lines.append("        ТабличныйДокумент.Вывести(ОбластьШапкаТаблицы);")
            lines.append("")
            lines.append("        НомерСтроки = 0;")
            lines.append("        ВыборкаСтроки = ВыборкаДокументы.Выбрать();")
            lines.append("        Пока ВыборкаСтроки.Следующий() Цикл")
            lines.append("            НомерСтроки = НомерСтроки + 1;")
            lines.append("            ОбластьСтрока.Параметры.НомерСтроки = НомерСтроки;")

            for attr in ts_attrs:
                lines.append(f"            ОбластьСтрока.Параметры.{attr.name} = ВыборкаСтроки.{attr.name};")

            lines.append("            ТабличныйДокумент.Вывести(ОбластьСтрока);")
            lines.append("        КонецЦикла;")

        # Footer with totals (sum numeric fields from TS)
        lines.append("")
        if ts and ts_name:
            numeric_attrs = QueryBuilder.get_numeric_attributes(ts)
            for attr in numeric_attrs:
                lines.append(f"        ОбластьПодвал.Параметры.Итого{attr.name} = ВыборкаДокументы.{attr.name};")

        lines.append("        ТабличныйДокумент.Вывести(ОбластьПодвал);")
        lines.append("")
        lines.append("        УправлениеПечатью.ЗадатьОбластьПечатиДокумента(")
        lines.append("            ТабличныйДокумент, НомерСтрокиНачало, ОбъектыПечати, ВыборкаДокументы.Ссылка);")
        lines.append("    КонецЦикла;")
        lines.append("")
        lines.append("    Возврат ТабличныйДокумент;")
        lines.append("")
        lines.append("КонецФункции")

        return "\n".join(lines)

    @staticmethod
    def _build_manager_module(
        obj: MetadataObject,
        safe_name: str,
        display_name: str,
    ) -> str:
        """Build BSP manager module registration code."""
        posting_check = "Истина" if obj.posting else "Ложь"

        lines: list[str] = []
        lines.append("Процедура ДобавитьКомандыПечати(КомандыПечати) Экспорт")
        lines.append("    КомандаПечати = КомандыПечати.Добавить();")
        lines.append(f'    КомандаПечати.Идентификатор = "{safe_name}";')
        lines.append(f"    КомандаПечати.Представление = НСтр(\"ru = '{display_name}'\");")
        lines.append(f"    КомандаПечати.ПроверкаПроведения = {posting_check};")
        lines.append("КонецПроцедуры")
        lines.append("")
        lines.append("Процедура Печать(МассивОбъектов, КоллекцияПечатныхФорм, ОбъектыПечати, ПараметрыВывода) Экспорт")
        lines.append(f'    Если УправлениеПечатью.НужноПечататьМакет(КоллекцияПечатныхФорм, "{safe_name}") Тогда')
        lines.append("        УправлениеПечатью.ВывестиТабличныйДокументВКоллекцию(")
        lines.append(f'            КоллекцияПечатныхФорм, "{safe_name}",')
        lines.append(f"            НСтр(\"ru = '{display_name}'\"),")
        lines.append(f"            Печать{safe_name}(МассивОбъектов, ОбъектыПечати));")
        lines.append("    КонецЕсли;")
        lines.append("КонецПроцедуры")

        return "\n".join(lines)

    @staticmethod
    def _build_mxl_template(
        obj: MetadataObject,
        safe_name: str,  # noqa: ARG004
        ts_name: str | None,
    ) -> str:
        """Build simplified MXL XML template with named areas and parameters."""
        header_attrs = PrintFormBuilder._get_header_attrs(obj)
        ts_attrs = PrintFormBuilder._get_ts_attrs(obj, ts_name)
        ts = PrintFormBuilder._get_ts(obj, ts_name)

        lines: list[str] = []
        lines.append('<?xml version="1.0" encoding="UTF-8"?>')
        lines.append("<SpreadsheetDocument>")

        # Area: Шапка
        lines.append('  <Area Name="Шапка">')
        lines.append("    <Row>")

        if obj.metadata_type.value == "Document":
            lines.append('      <Cell><Parameter Name="Номер"/></Cell>')
            lines.append('      <Cell><Parameter Name="Дата"/></Cell>')

        for attr in header_attrs:
            if attr.name in ("Номер", "Дата"):
                continue
            lines.append(f'      <Cell><Parameter Name="{attr.name}"/></Cell>')

        lines.append("    </Row>")
        lines.append("  </Area>")

        if ts_name and ts_attrs:
            # Area: ШапкаТаблицы
            lines.append('  <Area Name="ШапкаТаблицы">')
            lines.append("    <Row>")
            lines.append('      <Cell><Text>№</Text></Cell>')
            for attr in ts_attrs:
                label = attr.synonym or attr.name
                lines.append(f'      <Cell><Text>{label}</Text></Cell>')
            lines.append("    </Row>")
            lines.append("  </Area>")

            # Area: Строка
            lines.append('  <Area Name="Строка">')
            lines.append("    <Row>")
            lines.append('      <Cell><Parameter Name="НомерСтроки"/></Cell>')
            for attr in ts_attrs:
                lines.append(f'      <Cell><Parameter Name="{attr.name}"/></Cell>')
            lines.append("    </Row>")
            lines.append("  </Area>")

        # Area: Подвал
        lines.append('  <Area Name="Подвал">')
        lines.append("    <Row>")
        if ts and ts_name:
            numeric = QueryBuilder.get_numeric_attributes(ts)
            for attr in numeric:
                lines.append(f'      <Cell><Parameter Name="Итого{attr.name}"/></Cell>')
        lines.append("    </Row>")
        lines.append("  </Area>")

        lines.append("</SpreadsheetDocument>")

        return "\n".join(lines)
