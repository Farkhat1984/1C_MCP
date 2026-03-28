"""
Movement builder for 1C register postings.

Generates register movement (posting) code by auto-matching
document attributes to register dimensions and resources.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mcp_1c.domain.metadata import Attribute, MetadataObject, TabularSection
from mcp_1c.engines.smart.type_resolver import TypeResolver


@dataclass(frozen=True)
class FieldMapping:
    """Mapping from a register field to a document source field."""

    register_field: str
    source_field: str
    source_table: str
    match_type: str  # "type_match", "name_match", "manual"


@dataclass
class MovementResult:
    """Result of movement code generation."""

    posting_code: str
    field_mapping: list[FieldMapping] = field(default_factory=list)
    movement_type: str = "Приход"
    balance_control_code: str = ""


def _find_best_tabular_section(
    doc: MetadataObject,
    register: MetadataObject,
) -> TabularSection | None:
    """Find the tabular section with the most type matches to register fields.

    Compares types of register dimensions+resources against TS attributes.
    """
    reg_types = {a.type for a in register.dimensions + register.resources if a.type}

    best_ts: TabularSection | None = None
    best_score = 0

    for ts in doc.tabular_sections:
        ts_types = {a.type for a in ts.attributes if a.type}
        score = len(reg_types & ts_types)
        if score > best_score:
            best_score = score
            best_ts = ts

    return best_ts


def _match_field(
    reg_attr: Attribute,
    doc_attrs: list[Attribute],
    ts_attrs: list[Attribute],
    ts_name: str,
) -> FieldMapping | None:
    """Find the best matching document field for a register dimension/resource.

    Priority: 1) same type in TS, 2) same name in TS, 3) same type in header, 4) same name in header.
    """
    # Try type match in tabular section first
    for attr in ts_attrs:
        if attr.type == reg_attr.type and attr.type:
            return FieldMapping(
                register_field=reg_attr.name,
                source_field=attr.name,
                source_table=f"ТекСтрока{ts_name}",
                match_type="type_match",
            )

    # Try name match in tabular section
    for attr in ts_attrs:
        if attr.name == reg_attr.name:
            return FieldMapping(
                register_field=reg_attr.name,
                source_field=attr.name,
                source_table=f"ТекСтрока{ts_name}",
                match_type="name_match",
            )

    # Try type match in header
    for attr in doc_attrs:
        if attr.type == reg_attr.type and attr.type:
            return FieldMapping(
                register_field=reg_attr.name,
                source_field=attr.name,
                source_table="",
                match_type="type_match",
            )

    # Try name match in header
    for attr in doc_attrs:
        if attr.name == reg_attr.name:
            return FieldMapping(
                register_field=reg_attr.name,
                source_field=attr.name,
                source_table="",
                match_type="name_match",
            )

    return None


def _detect_movement_type(register: MetadataObject, movement_type: str | None) -> str:
    """Detect movement type from register name if not specified."""
    if movement_type:
        return movement_type
    name_lower = register.name.lower()
    if "расход" in name_lower or "выбытие" in name_lower:
        return "Расход"
    return "Приход"


def _should_include_balance_control(register: MetadataObject, include: bool | None) -> bool:
    """Auto-detect whether to include balance control code."""
    if include is not None:
        return include
    name_lower = register.name.lower()
    return "остатк" in name_lower or "остаток" in name_lower


class MovementBuilder:
    """Generates register movement (posting) code from metadata."""

    @staticmethod
    def build(
        doc: MetadataObject,
        register: MetadataObject,
        *,
        movement_type: str | None = None,
        include_balance_control: bool | None = None,
    ) -> MovementResult:
        """Generate register movement code.

        Auto-matches document fields to register dimensions/resources
        by type, then by name.

        Args:
            doc: Document metadata object.
            register: Register metadata object.
            movement_type: "Приход" or "Расход". Auto-detected if None.
            include_balance_control: Generate balance control query. Auto-detected if None.

        Returns:
            MovementResult with posting code and field mappings.
        """
        mv_type = _detect_movement_type(register, movement_type)
        ts = _find_best_tabular_section(doc, register)
        ts_name = ts.name if ts else ""
        ts_attrs = ts.attributes if ts else []

        mappings: list[FieldMapping] = []
        for reg_attr in register.dimensions + register.resources:
            mapping = _match_field(reg_attr, doc.attributes, ts_attrs, ts_name)
            if mapping:
                mappings.append(mapping)

        posting_code = MovementBuilder._generate_code(
            register, mv_type, mappings, ts_name,
        )

        balance_code = ""
        if _should_include_balance_control(register, include_balance_control):
            balance_code = MovementBuilder._generate_balance_control(
                register, doc, ts_name,
            )

        return MovementResult(
            posting_code=posting_code,
            field_mapping=mappings,
            movement_type=mv_type,
            balance_control_code=balance_code,
        )

    @staticmethod
    def _generate_code(
        register: MetadataObject,
        movement_type: str,
        mappings: list[FieldMapping],
        ts_name: str,
    ) -> str:
        """Generate the BSL movement code block."""
        reg_name = register.name
        is_accumulation = register.metadata_type.value == "AccumulationRegister"

        lines: list[str] = []
        lines.append(f"Движения.{reg_name}.Записывать = Истина;")

        if ts_name:
            lines.append(f"Для Каждого ТекСтрока{ts_name} Из {ts_name} Цикл")
            indent = "    "
        else:
            indent = ""

        lines.append(f"{indent}Движение = Движения.{reg_name}.Добавить();")

        if is_accumulation:
            lines.append(f"{indent}Движение.ВидДвижения = ВидДвиженияНакопления.{movement_type};")

        lines.append(f"{indent}Движение.Период = Дата;")

        for m in mappings:
            source = f"{m.source_table}.{m.source_field}" if m.source_table else m.source_field
            lines.append(f"{indent}Движение.{m.register_field} = {source};")

        if ts_name:
            lines.append("КонецЦикла;")

        return "\n".join(lines)

    @staticmethod
    def _generate_balance_control(
        register: MetadataObject,
        doc: MetadataObject,  # noqa: ARG004
        ts_name: str,  # noqa: ARG004
    ) -> str:
        """Generate balance control query code."""
        rus_prefix = TypeResolver.to_russian_type_prefix(register.metadata_type.value)
        reg_name = register.name

        dim_names = [d.name for d in register.dimensions]
        res_names = [r.name for r in register.resources]

        select_fields = ", ".join(
            [f"Остатки.{d}Остаток" for d in dim_names]
            + [f"Остатки.{r}Остаток" for r in res_names]
        )

        lines: list[str] = []
        lines.append("// Контроль остатков")
        lines.append("Запрос = Новый Запрос;")
        lines.append(f'Запрос.Текст = "ВЫБРАТЬ {select_fields}')
        lines.append(f'    |ИЗ {rus_prefix}.{reg_name}.Остатки КАК Остатки";')
        lines.append("")
        lines.append("РезультатЗапроса = Запрос.Выполнить();")
        lines.append("Если Не РезультатЗапроса.Пустой() Тогда")
        lines.append("    Выборка = РезультатЗапроса.Выбрать();")
        lines.append("    Пока Выборка.Следующий() Цикл")
        for r in res_names:
            lines.append(f'        Если Выборка.{r}Остаток < 0 Тогда')
            lines.append(f'            Сообщить("Недостаточно: " + Строка(Выборка.{r}Остаток));')
            lines.append("            Отказ = Истина;")
            lines.append("        КонецЕсли;")
        lines.append("    КонецЦикла;")
        lines.append("КонецЕсли;")

        return "\n".join(lines)
