"""
Query parser for 1C Enterprise queries.

Parses, validates, and analyzes 1C query language.
"""

import re
from typing import Any

from mcp_1c.domain.templates import (
    ParsedQuery,
    QueryCondition,
    QueryField,
    QueryOptimizationSuggestion,
    QueryTableReference,
    QueryValidationResult,
)
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


class QueryParser:
    """
    Parser for 1C Enterprise query language.

    Parses queries into structured representation and provides
    validation and optimization suggestions.
    """

    # Table name patterns (Russian and English)
    TABLE_PATTERNS = {
        "Catalog": (r"Справочник\.(\w+)", r"Catalog\.(\w+)"),
        "Document": (r"Документ\.(\w+)", r"Document\.(\w+)"),
        "InformationRegister": (r"РегистрСведений\.(\w+)", r"InformationRegister\.(\w+)"),
        "AccumulationRegister": (r"РегистрНакопления\.(\w+)", r"AccumulationRegister\.(\w+)"),
        "AccountingRegister": (r"РегистрБухгалтерии\.(\w+)", r"AccountingRegister\.(\w+)"),
        "CalculationRegister": (r"РегистрРасчета\.(\w+)", r"CalculationRegister\.(\w+)"),
        "Enum": (r"Перечисление\.(\w+)", r"Enum\.(\w+)"),
        "ChartOfAccounts": (r"ПланСчетов\.(\w+)", r"ChartOfAccounts\.(\w+)"),
        "ChartOfCharacteristicTypes": (r"ПланВидовХарактеристик\.(\w+)", r"ChartOfCharacteristicTypes\.(\w+)"),
        "ExchangePlan": (r"ПланОбмена\.(\w+)", r"ExchangePlan\.(\w+)"),
        "Constant": (r"Константа\.(\w+)", r"Constant\.(\w+)"),
        "Sequence": (r"Последовательность\.(\w+)", r"Sequence\.(\w+)"),
        "BusinessProcess": (r"БизнесПроцесс\.(\w+)", r"BusinessProcess\.(\w+)"),
        "Task": (r"Задача\.(\w+)", r"Task\.(\w+)"),
    }

    # Virtual table patterns
    VIRTUAL_TABLE_PATTERNS = {
        "SliceLast": (r"СрезПоследних", r"SliceLast"),
        "SliceFirst": (r"СрезПервых", r"SliceFirst"),
        "Balance": (r"Остатки", r"Balance"),
        "Turnovers": (r"Обороты", r"Turnovers"),
        "BalanceAndTurnovers": (r"ОстаткиИОбороты", r"BalanceAndTurnovers"),
    }

    # Aggregate functions
    AGGREGATE_FUNCTIONS = {
        "SUM": ("СУММА", "SUM"),
        "COUNT": ("КОЛИЧЕСТВО", "COUNT"),
        "AVG": ("СРЕДНЕЕ", "AVG"),
        "MIN": ("МИНИМУМ", "MIN"),
        "MAX": ("МАКСИМУМ", "MAX"),
    }

    # Query keywords (Russian/English)
    KEYWORDS = {
        "SELECT": ("ВЫБРАТЬ", "SELECT"),
        "DISTINCT": ("РАЗЛИЧНЫЕ", "DISTINCT"),
        "TOP": ("ПЕРВЫЕ", "TOP"),
        "FROM": ("ИЗ", "FROM"),
        "WHERE": ("ГДЕ", "WHERE"),
        "GROUP_BY": ("СГРУППИРОВАТЬ ПО", "GROUP BY"),
        "HAVING": ("ИМЕЮЩИЕ", "HAVING"),
        "ORDER_BY": ("УПОРЯДОЧИТЬ ПО", "ORDER BY"),
        "ASC": ("ВОЗР", "ASC"),
        "DESC": ("УБЫВ", "DESC"),
        "JOIN": ("СОЕДИНЕНИЕ", "JOIN"),
        "LEFT_JOIN": ("ЛЕВОЕ СОЕДИНЕНИЕ", "LEFT JOIN"),
        "RIGHT_JOIN": ("ПРАВОЕ СОЕДИНЕНИЕ", "RIGHT JOIN"),
        "FULL_JOIN": ("ПОЛНОЕ СОЕДИНЕНИЕ", "FULL JOIN"),
        "INNER_JOIN": ("ВНУТРЕННЕЕ СОЕДИНЕНИЕ", "INNER JOIN"),
        "ON": ("ПО", "ON"),
        "AND": ("И", "AND"),
        "OR": ("ИЛИ", "OR"),
        "NOT": ("НЕ", "NOT"),
        "IN": ("В", "IN"),
        "BETWEEN": ("МЕЖДУ", "BETWEEN"),
        "LIKE": ("ПОДОБНО", "LIKE"),
        "IS_NULL": ("ЕСТЬ NULL", "IS NULL"),
        "AS": ("КАК", "AS"),
        "INTO": ("ПОМЕСТИТЬ", "INTO"),
        "UNION": ("ОБЪЕДИНИТЬ", "UNION"),
        "UNION_ALL": ("ОБЪЕДИНИТЬ ВСЕ", "UNION ALL"),
    }

    # Parameter pattern (supports Cyrillic identifiers)
    PARAMETER_PATTERN = re.compile(r"&([A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*)")

    def __init__(self) -> None:
        """Initialize query parser."""
        pass

    def parse(self, query_text: str) -> ParsedQuery:
        """
        Parse 1C query into structured representation.

        Args:
            query_text: Query text to parse

        Returns:
            ParsedQuery with parsed structure
        """
        # Clean up query
        query = self._normalize_query(query_text)

        result = ParsedQuery(
            query_text=query_text,
        )

        try:
            # Extract SELECT clause
            result.select_fields = self._parse_select(query)
            result.is_distinct = self._has_distinct(query)
            result.top_count = self._get_top_count(query)

            # Extract tables
            result.tables = self._parse_tables(query)

            # Extract WHERE conditions
            result.conditions = self._parse_conditions(query)

            # Extract GROUP BY
            result.group_by_fields = self._parse_group_by(query)

            # Extract ORDER BY
            result.order_by_fields = self._parse_order_by(query)

            # Extract parameters
            result.parameters = self._extract_parameters(query)

            # Extract temporary tables
            result.temporary_tables = self._extract_temp_tables(query)

            # Check for subqueries
            result.has_subqueries = self._has_subqueries(query)

        except Exception as e:
            logger.error(f"Error parsing query: {e}")

        return result

    def _normalize_query(self, query: str) -> str:
        """Normalize query text for parsing."""
        # Remove excessive whitespace
        query = re.sub(r"\s+", " ", query)
        return query.strip()

    def _has_distinct(self, query: str) -> bool:
        """Check if query has DISTINCT."""
        pattern = r"\b(ВЫБРАТЬ\s+РАЗЛИЧНЫЕ|SELECT\s+DISTINCT)\b"
        return bool(re.search(pattern, query, re.IGNORECASE))

    def _get_top_count(self, query: str) -> int | None:
        """Extract TOP count if present."""
        pattern = r"\b(?:ПЕРВЫЕ|TOP)\s+(\d+)\b"
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None

    def _parse_select(self, query: str) -> list[QueryField]:
        """Parse SELECT fields."""
        fields = []

        # Find SELECT ... FROM section
        select_match = re.search(
            r"\b(?:ВЫБРАТЬ|SELECT)\s+(?:РАЗЛИЧНЫЕ\s+|DISTINCT\s+)?(?:ПЕРВЫЕ\s+\d+\s+|TOP\s+\d+\s+)?(.*?)\s+(?:ИЗ|FROM)\b",
            query,
            re.IGNORECASE | re.DOTALL,
        )

        if not select_match:
            return fields

        select_clause = select_match.group(1)

        # Split by commas (but not inside parentheses)
        field_texts = self._split_by_comma(select_clause)

        for field_text in field_texts:
            field = self._parse_field(field_text.strip())
            if field:
                fields.append(field)

        return fields

    def _parse_field(self, field_text: str) -> QueryField | None:
        """Parse a single field expression."""
        if not field_text:
            return None

        # Check for alias
        alias_match = re.search(r"\s+(?:КАК|AS)\s+(\w+)\s*$", field_text, re.IGNORECASE)
        alias = alias_match.group(1) if alias_match else None

        if alias_match:
            expression = field_text[: alias_match.start()].strip()
        else:
            expression = field_text.strip()

        # Check for aggregate function
        is_aggregate = False
        aggregate_function = None

        for func, (ru, en) in self.AGGREGATE_FUNCTIONS.items():
            if re.match(rf"\b({ru}|{en})\s*\(", expression, re.IGNORECASE):
                is_aggregate = True
                aggregate_function = func
                break

        return QueryField(
            expression=expression,
            alias=alias,
            is_aggregate=is_aggregate,
            aggregate_function=aggregate_function,
        )

    def _split_by_comma(self, text: str) -> list[str]:
        """Split text by commas, respecting parentheses."""
        result = []
        current = ""
        depth = 0

        for char in text:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                result.append(current)
                current = ""
                continue

            current += char

        if current:
            result.append(current)

        return result

    def _parse_tables(self, query: str) -> list[QueryTableReference]:
        """Parse tables from query."""
        tables = []

        # Find FROM ... WHERE/GROUP/ORDER/; section
        from_match = re.search(
            r"\b(?:ИЗ|FROM)\b\s+(.*?)(?:\s+(?:ГДЕ|WHERE|СГРУППИРОВАТЬ|GROUP|УПОРЯДОЧИТЬ|ORDER|ОБЪЕДИНИТЬ|UNION)|;|$)",
            query,
            re.IGNORECASE | re.DOTALL,
        )

        if not from_match:
            return tables

        from_clause = from_match.group(1)

        # Table type prefixes (Russian and English)
        table_prefixes = [
            ("Справочник", "Catalog"),
            ("Документ", "Document"),
            ("РегистрСведений", "InformationRegister"),
            ("РегистрНакопления", "AccumulationRegister"),
            ("РегистрБухгалтерии", "AccountingRegister"),
            ("РегистрРасчета", "CalculationRegister"),
            ("Перечисление", "Enum"),
            ("ПланСчетов", "ChartOfAccounts"),
            ("ПланВидовХарактеристик", "ChartOfCharacteristicTypes"),
            ("ПланОбмена", "ExchangePlan"),
            ("Константа", "Constant"),
            ("Последовательность", "Sequence"),
            ("БизнесПроцесс", "BusinessProcess"),
            ("Задача", "Task"),
        ]

        # Build pattern for all table types
        for ru_prefix, en_prefix in table_prefixes:
            # Pattern: Prefix.ObjectName[.VirtualTable][(params)] AS Alias
            pattern = rf"({ru_prefix}|{en_prefix})\.(\w+)(?:\.(\w+))?(?:\s*\([^)]*\))?\s*(?:(?:КАК|AS)\s+(\w+))?"
            for match in re.finditer(pattern, from_clause, re.IGNORECASE):
                prefix = match.group(1)
                object_name = match.group(2)
                virtual_table = match.group(3)
                alias = match.group(4)

                table_name = f"{prefix}.{object_name}"
                if virtual_table:
                    table_name = f"{table_name}.{virtual_table}"

                is_virtual = False
                virtual_type = None

                if virtual_table:
                    for vt_name, vt_patterns in self.VIRTUAL_TABLE_PATTERNS.items():
                        if virtual_table.lower() in (p.lower() for p in vt_patterns):
                            is_virtual = True
                            virtual_type = vt_name
                            break

                tables.append(
                    QueryTableReference(
                        table_name=table_name,
                        alias=alias,
                        is_virtual_table=is_virtual,
                        virtual_table_type=virtual_type,
                    )
                )

        return tables

    def _parse_conditions(self, query: str) -> list[QueryCondition]:
        """Parse WHERE conditions."""
        conditions = []

        where_match = re.search(
            r"\b(?:ГДЕ|WHERE)\b\s+(.*?)(?:\s+(?:СГРУППИРОВАТЬ|GROUP|УПОРЯДОЧИТЬ|ORDER|ОБЪЕДИНИТЬ|UNION)|;|$)",
            query,
            re.IGNORECASE | re.DOTALL,
        )

        if not where_match:
            return conditions

        where_clause = where_match.group(1)

        # Simple condition extraction (basic)
        comparison_pattern = r"(\S+)\s*(=|<>|!=|>=|<=|>|<|(?:ПОДОБНО|LIKE))\s*(\S+)"
        for match in re.finditer(comparison_pattern, where_clause, re.IGNORECASE):
            left = match.group(1)
            operator = match.group(2)
            right = match.group(3)

            is_parameter = right.startswith("&")

            conditions.append(
                QueryCondition(
                    left_operand=left,
                    operator=operator,
                    right_operand=right,
                    is_parameter=is_parameter,
                )
            )

        return conditions

    def _parse_group_by(self, query: str) -> list[str]:
        """Parse GROUP BY fields."""
        pattern = r"\b(?:СГРУППИРОВАТЬ\s+ПО|GROUP\s+BY)\b\s+(.*?)(?:\s+(?:ИМЕЮЩИЕ|HAVING|УПОРЯДОЧИТЬ|ORDER|ОБЪЕДИНИТЬ|UNION)|;|$)"
        match = re.search(pattern, query, re.IGNORECASE | re.DOTALL)

        if not match:
            return []

        group_clause = match.group(1)
        fields = self._split_by_comma(group_clause)
        return [f.strip() for f in fields if f.strip()]

    def _parse_order_by(self, query: str) -> list[dict[str, Any]]:
        """Parse ORDER BY fields."""
        pattern = r"\b(?:УПОРЯДОЧИТЬ\s+ПО|ORDER\s+BY)\b\s+(.*?)(?:\s+(?:ОБЪЕДИНИТЬ|UNION)|;|$)"
        match = re.search(pattern, query, re.IGNORECASE | re.DOTALL)

        if not match:
            return []

        order_clause = match.group(1)
        fields = self._split_by_comma(order_clause)

        result = []
        for field in fields:
            field = field.strip()
            direction = "ASC"

            if re.search(r"\s+(?:УБЫВ|DESC)\s*$", field, re.IGNORECASE):
                direction = "DESC"
                field = re.sub(r"\s+(?:УБЫВ|DESC)\s*$", "", field, flags=re.IGNORECASE)
            elif re.search(r"\s+(?:ВОЗР|ASC)\s*$", field, re.IGNORECASE):
                field = re.sub(r"\s+(?:ВОЗР|ASC)\s*$", "", field, flags=re.IGNORECASE)

            result.append({"field": field.strip(), "direction": direction})

        return result

    def _extract_parameters(self, query: str) -> list[str]:
        """Extract query parameters."""
        matches = self.PARAMETER_PATTERN.findall(query)
        return list(set(matches))

    def _extract_temp_tables(self, query: str) -> list[str]:
        """Extract temporary table definitions."""
        pattern = r"\b(?:ПОМЕСТИТЬ|INTO)\s+(\w+)"
        matches = re.findall(pattern, query, re.IGNORECASE)
        return list(set(matches))

    def _has_subqueries(self, query: str) -> bool:
        """Check if query contains subqueries."""
        # Count SELECT keywords (more than one indicates subquery)
        select_count = len(re.findall(r"\b(?:ВЫБРАТЬ|SELECT)\b", query, re.IGNORECASE))
        return select_count > 1

    def validate(
        self,
        parsed_query: ParsedQuery,
        available_tables: list[str] | None = None,
    ) -> QueryValidationResult:
        """
        Validate parsed query.

        Args:
            parsed_query: Parsed query to validate
            available_tables: Optional list of valid table names

        Returns:
            Validation result
        """
        errors = []
        warnings = []
        suggestions = []
        unknown_tables = []
        unknown_fields = []

        # Check for common issues
        if not parsed_query.select_fields:
            errors.append("No fields in SELECT clause")

        if not parsed_query.tables:
            errors.append("No tables in FROM clause")

        # Check GROUP BY consistency
        if parsed_query.group_by_fields:
            non_aggregate_selects = [
                f.expression
                for f in parsed_query.select_fields
                if not f.is_aggregate
            ]
            for field in non_aggregate_selects:
                if field not in parsed_query.group_by_fields and field != "*":
                    warnings.append(
                        f"Field '{field}' is in SELECT but not in GROUP BY"
                    )

        # Check tables against available tables
        if available_tables:
            for table in parsed_query.tables:
                if table.table_name not in available_tables:
                    unknown_tables.append(table.table_name)

        # Performance suggestions
        if parsed_query.has_subqueries:
            suggestions.append(
                "Consider using temporary tables instead of subqueries for better performance"
            )

        if len(parsed_query.tables) > 3 and not parsed_query.conditions:
            warnings.append("Multiple tables without WHERE conditions may result in large result set")

        is_valid = len(errors) == 0

        return QueryValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions,
            unknown_tables=unknown_tables,
            unknown_fields=unknown_fields,
        )

    def suggest_optimizations(
        self,
        parsed_query: ParsedQuery,
    ) -> list[QueryOptimizationSuggestion]:
        """
        Suggest optimizations for the query.

        Args:
            parsed_query: Parsed query to analyze

        Returns:
            List of optimization suggestions
        """
        suggestions = []

        # Check for SELECT *
        for field in parsed_query.select_fields:
            if field.expression.strip() == "*":
                suggestions.append(
                    QueryOptimizationSuggestion(
                        category="performance",
                        description="Avoid using SELECT * - specify required fields explicitly",
                        description_ru="Избегайте использования SELECT * - указывайте поля явно",
                        original_fragment="*",
                        suggested_fragment="Field1, Field2, ...",
                        impact="medium",
                    )
                )

        # Check for missing indexes (virtual table params)
        for table in parsed_query.tables:
            if table.is_virtual_table and table.virtual_table_type in ("SliceLast", "SliceFirst"):
                has_period_param = any(
                    cond.left_operand.lower() == "период" or
                    cond.left_operand.lower() == "period"
                    for cond in parsed_query.conditions
                )
                if not has_period_param:
                    suggestions.append(
                        QueryOptimizationSuggestion(
                            category="index",
                            description=f"Consider adding period parameter to {table.virtual_table_type} for better performance",
                            description_ru=f"Рекомендуется добавить параметр периода для {table.table_name} для повышения производительности",
                            impact="high",
                        )
                    )

        # Check for subqueries
        if parsed_query.has_subqueries:
            suggestions.append(
                QueryOptimizationSuggestion(
                    category="structure",
                    description="Consider replacing subqueries with temporary tables or JOINs",
                    description_ru="Рассмотрите замену вложенных запросов на временные таблицы или соединения",
                    impact="medium",
                )
            )

        # Check for DISTINCT without need
        if parsed_query.is_distinct and parsed_query.group_by_fields:
            suggestions.append(
                QueryOptimizationSuggestion(
                    category="structure",
                    description="DISTINCT with GROUP BY may be redundant",
                    description_ru="РАЗЛИЧНЫЕ с группировкой может быть избыточным",
                    impact="low",
                )
            )

        return suggestions

    def explain(self, parsed_query: ParsedQuery) -> str:
        """
        Generate human-readable explanation of the query.

        Args:
            parsed_query: Parsed query

        Returns:
            Explanation text
        """
        lines = []

        lines.append("=== Анализ запроса ===")
        lines.append("")

        # Tables
        if parsed_query.tables:
            lines.append("Источники данных:")
            for table in parsed_query.tables:
                table_desc = f"  - {table.table_name}"
                if table.alias:
                    table_desc += f" (псевдоним: {table.alias})"
                if table.is_virtual_table:
                    table_desc += f" [виртуальная таблица: {table.virtual_table_type}]"
                lines.append(table_desc)
            lines.append("")

        # Fields
        if parsed_query.select_fields:
            lines.append("Выбираемые поля:")
            for field in parsed_query.select_fields:
                field_desc = f"  - {field.expression}"
                if field.alias:
                    field_desc += f" как {field.alias}"
                if field.is_aggregate:
                    field_desc += f" (агрегат: {field.aggregate_function})"
                lines.append(field_desc)
            lines.append("")

        # Conditions
        if parsed_query.conditions:
            lines.append("Условия отбора:")
            for cond in parsed_query.conditions:
                cond_desc = f"  - {cond.left_operand} {cond.operator} {cond.right_operand}"
                if cond.is_parameter:
                    cond_desc += " (параметр)"
                lines.append(cond_desc)
            lines.append("")

        # Grouping
        if parsed_query.group_by_fields:
            lines.append(f"Группировка: {', '.join(parsed_query.group_by_fields)}")
            lines.append("")

        # Ordering
        if parsed_query.order_by_fields:
            order_desc = ", ".join(
                f"{o['field']} {o['direction']}" for o in parsed_query.order_by_fields
            )
            lines.append(f"Сортировка: {order_desc}")
            lines.append("")

        # Parameters
        if parsed_query.parameters:
            lines.append(f"Параметры: {', '.join(parsed_query.parameters)}")
            lines.append("")

        # Modifiers
        modifiers = []
        if parsed_query.is_distinct:
            modifiers.append("РАЗЛИЧНЫЕ")
        if parsed_query.top_count:
            modifiers.append(f"ПЕРВЫЕ {parsed_query.top_count}")
        if modifiers:
            lines.append(f"Модификаторы: {', '.join(modifiers)}")

        return "\n".join(lines)
