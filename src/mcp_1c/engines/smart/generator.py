"""
Smart code generator facade.

Singleton that delegates to specialized builders, resolving
metadata objects via MetadataEngine before generation.
"""

from __future__ import annotations

from mcp_1c.domain.metadata import MetadataObject, MetadataType
from mcp_1c.engines.smart.movement_builder import MovementBuilder, MovementResult
from mcp_1c.engines.smart.print_builder import PrintFormBuilder
from mcp_1c.engines.smart.query_builder import QueryBuilder
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)

# ── Name parsing helpers ────────────────────────────────────────────────────

# Mapping of Russian singular prefixes to English MetadataType values
_RUSSIAN_TO_ENGLISH: dict[str, str] = {
    "Справочник": "Catalog",
    "Документ": "Document",
    "Перечисление": "Enum",
    "РегистрСведений": "InformationRegister",
    "РегистрНакопления": "AccumulationRegister",
    "РегистрБухгалтерии": "AccountingRegister",
    "РегистрРасчета": "CalculationRegister",
    "ПланВидовХарактеристик": "ChartOfCharacteristicTypes",
    "ПланСчетов": "ChartOfAccounts",
    "ПланВидовРасчета": "ChartOfCalculationTypes",
    "ПланОбмена": "ExchangePlan",
    "БизнесПроцесс": "BusinessProcess",
    "Задача": "Task",
    "Отчет": "Report",
    "Обработка": "DataProcessor",
}


def _parse_object_name(full_name: str) -> tuple[str, str]:
    """Parse 'Type.Name' into (MetadataType.value, object_name).

    Handles both English ('Document.X') and Russian ('Документ.X') prefixes.

    Raises:
        ValueError: If format is invalid.
    """
    parts = full_name.split(".", 1)
    if len(parts) != 2 or not parts[1]:
        raise ValueError(
            f"Invalid object name '{full_name}'. Expected format: 'Type.Name' "
            f"(e.g. 'Document.ПриходТовара' or 'Документ.ПриходТовара')"
        )
    type_part, name_part = parts

    # Try English first
    try:
        MetadataType(type_part)
        return type_part, name_part
    except ValueError:
        pass

    # Try Russian
    eng = _RUSSIAN_TO_ENGLISH.get(type_part)
    if eng:
        return eng, name_part

    raise ValueError(
        f"Unknown metadata type '{type_part}'. "
        f"Use English (Document, Catalog, ...) or Russian (Документ, Справочник, ...)"
    )


class SmartGenerator:
    """Facade for metadata-aware code generation.

    Uses MetadataEngine to fetch object definitions and delegates
    to specialized builders for queries, print forms, and movements.
    """

    _instance: SmartGenerator | None = None

    @classmethod
    def get_instance(cls) -> SmartGenerator:
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def _get_object(self, full_name: str) -> MetadataObject:
        """Resolve a metadata object by full name.

        Args:
            full_name: 'Document.ПриходТовара' or 'Документ.ПриходТовара'

        Raises:
            ValueError: If object not found or not initialized.
        """
        from mcp_1c.engines.metadata import MetadataEngine

        engine = MetadataEngine.get_instance()
        type_value, name = _parse_object_name(full_name)
        obj = await engine.get_object(type_value, name)
        if obj is None:
            raise ValueError(
                f"Metadata object '{full_name}' not found. "
                f"Make sure metadata-init has been called."
            )
        return obj

    async def generate_query(
        self,
        object_name: str,
        *,
        include_tabular: str | None = None,
        fields: list[str] | None = None,
    ) -> dict[str, str]:
        """Generate a 1C query for a metadata object.

        Args:
            object_name: Full name like 'Document.ПриходТовара'.
            include_tabular: Tabular section name to include.
            fields: Specific fields to include.

        Returns:
            Dict with 'query' and 'object_name' keys.
        """
        obj = await self._get_object(object_name)
        query = QueryBuilder.build_object_query(
            obj,
            include_tabular=include_tabular,
            fields=fields,
        )
        return {
            "query": query,
            "object_name": obj.full_name,
            "object_synonym": obj.synonym,
        }

    async def generate_print_form(
        self,
        object_name: str,
        *,
        form_type: str = "with_query",
        include_tabular: bool = True,
        form_name: str | None = None,
    ) -> dict[str, str]:
        """Generate a complete print form for a metadata object.

        Args:
            object_name: Full name like 'Document.ПриходТовара'.
            form_type: Generation style.
            include_tabular: Include first tabular section.
            form_name: Custom form name.

        Returns:
            Dict with print_procedure, manager_module, mxl_template, query.
        """
        obj = await self._get_object(object_name)
        result = PrintFormBuilder.build(
            obj,
            form_type=form_type,
            include_tabular=include_tabular,
            form_name=form_name,
        )
        result["object_name"] = obj.full_name
        return result

    async def generate_movement(
        self,
        document_name: str,
        register_name: str,
        *,
        movement_type: str | None = None,
    ) -> dict[str, str | list[dict[str, str]]]:
        """Generate register movement code for a document.

        Args:
            document_name: Document full name like 'Document.ПриходТовара'.
            register_name: Register full name like 'AccumulationRegister.ОстаткиТоваров'.
            movement_type: 'Приход' or 'Расход'. Auto-detected if None.

        Returns:
            Dict with posting_code, field_mapping, movement_type.
        """
        doc = await self._get_object(document_name)
        reg = await self._get_object(register_name)

        result: MovementResult = MovementBuilder.build(
            doc,
            reg,
            movement_type=movement_type,
        )

        mapping_dicts = [
            {
                "register_field": m.register_field,
                "source_field": m.source_field,
                "source_table": m.source_table,
                "match_type": m.match_type,
            }
            for m in result.field_mapping
        ]

        output: dict[str, str | list[dict[str, str]]] = {
            "posting_code": result.posting_code,
            "field_mapping": mapping_dicts,
            "movement_type": result.movement_type,
            "document": doc.full_name,
            "register": reg.full_name,
        }

        if result.balance_control_code:
            output["balance_control_code"] = result.balance_control_code

        return output
