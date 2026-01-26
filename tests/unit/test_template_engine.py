"""
Unit tests for Template Engine.

Tests template loading, code generation, and query parsing.
"""

import pytest

from mcp_1c.engines.templates import TemplateEngine, CodeGenerator, QueryParser
from mcp_1c.domain.templates import (
    CodeTemplate,
    GenerationContext,
    Placeholder,
    PlaceholderType,
    TemplateCategory,
)


class TestCodeGenerator:
    """Tests for CodeGenerator class."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.generator = CodeGenerator()

    def test_simple_substitution(self) -> None:
        """Test simple placeholder substitution."""
        template = CodeTemplate(
            id="test.simple",
            name="Simple Test",
            category=TemplateCategory.QUERY,
            template_code="ВЫБРАТЬ ${Field} ИЗ ${Table}",
            placeholders=[
                Placeholder(
                    name="Field",
                    display_name="Field",
                    placeholder_type=PlaceholderType.STRING,
                    required=True,
                ),
                Placeholder(
                    name="Table",
                    display_name="Table",
                    placeholder_type=PlaceholderType.TABLE_NAME,
                    required=True,
                ),
            ],
        )

        result = self.generator.generate(
            template,
            {"Field": "Наименование", "Table": "Справочник.Номенклатура"},
        )

        assert result.success
        assert "ВЫБРАТЬ Наименование ИЗ Справочник.Номенклатура" in result.code

    def test_default_value_substitution(self) -> None:
        """Test substitution with default values."""
        template = CodeTemplate(
            id="test.default",
            name="Default Test",
            category=TemplateCategory.QUERY,
            template_code="ВЫБРАТЬ ${Fields} ИЗ ${Table} КАК ${Alias}",
            placeholders=[
                Placeholder(
                    name="Fields",
                    display_name="Fields",
                    required=True,
                ),
                Placeholder(
                    name="Table",
                    display_name="Table",
                    required=True,
                ),
                Placeholder(
                    name="Alias",
                    display_name="Alias",
                    required=False,
                    default_value="Т",
                ),
            ],
        )

        result = self.generator.generate(
            template,
            {"Fields": "*", "Table": "Справочник.Контрагенты"},
        )

        assert result.success
        assert "КАК Т" in result.code

    def test_conditional_block(self) -> None:
        """Test conditional block processing."""
        template = CodeTemplate(
            id="test.conditional",
            name="Conditional Test",
            category=TemplateCategory.QUERY,
            template_code="ВЫБРАТЬ * ИЗ Т{{#if HasWhere}}\nГДЕ Условие{{/if}}",
            placeholders=[
                Placeholder(
                    name="HasWhere",
                    display_name="Has WHERE",
                    placeholder_type=PlaceholderType.BOOLEAN,
                    required=False,
                ),
            ],
        )

        # With condition true
        result = self.generator.generate(template, {"HasWhere": "true"})
        assert "ГДЕ Условие" in result.code

        # With condition false
        result = self.generator.generate(template, {"HasWhere": "false"})
        assert "ГДЕ Условие" not in result.code

    def test_missing_required_placeholder(self) -> None:
        """Test validation for missing required placeholder."""
        template = CodeTemplate(
            id="test.required",
            name="Required Test",
            category=TemplateCategory.QUERY,
            template_code="${RequiredField}",
            placeholders=[
                Placeholder(
                    name="RequiredField",
                    display_name="Required Field",
                    required=True,
                ),
            ],
        )

        result = self.generator.generate(template, {})

        assert not result.success
        assert "RequiredField" in result.missing_placeholders

    def test_identifier_validation(self) -> None:
        """Test identifier type validation."""
        template = CodeTemplate(
            id="test.identifier",
            name="Identifier Test",
            category=TemplateCategory.QUERY,
            template_code="${Name}",
            placeholders=[
                Placeholder(
                    name="Name",
                    display_name="Name",
                    placeholder_type=PlaceholderType.IDENTIFIER,
                    required=True,
                ),
            ],
        )

        # Valid identifier
        result = self.generator.generate(template, {"Name": "ВалидноеИмя123"})
        assert result.success

        # Invalid identifier (starts with number)
        result = self.generator.generate(template, {"Name": "123Invalid"})
        assert not result.success
        assert "Name" in result.invalid_values


class TestQueryParser:
    """Tests for QueryParser class."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.parser = QueryParser()

    def test_parse_simple_select(self) -> None:
        """Test parsing simple SELECT query."""
        query = """
        ВЫБРАТЬ
            Ссылка,
            Наименование
        ИЗ
            Справочник.Номенклатура КАК Товары
        """

        parsed = self.parser.parse(query)

        assert len(parsed.select_fields) >= 2
        assert len(parsed.tables) >= 1
        assert parsed.tables[0].table_name == "Справочник.Номенклатура"
        assert parsed.tables[0].alias == "Товары"

    def test_parse_select_with_where(self) -> None:
        """Test parsing SELECT with WHERE clause."""
        query = """
        ВЫБРАТЬ
            Наименование
        ИЗ
            Справочник.Номенклатура КАК Т
        ГДЕ
            Т.ПометкаУдаления = ЛОЖЬ
        """

        parsed = self.parser.parse(query)

        assert len(parsed.conditions) >= 1

    def test_parse_grouped_query(self) -> None:
        """Test parsing query with GROUP BY."""
        query = """
        ВЫБРАТЬ
            Контрагент,
            СУММА(Сумма) КАК Итого
        ИЗ
            Документ.Продажа КАК Продажи
        СГРУППИРОВАТЬ ПО
            Контрагент
        """

        parsed = self.parser.parse(query)

        assert len(parsed.group_by_fields) >= 1
        # Check for aggregate function
        has_aggregate = any(f.is_aggregate for f in parsed.select_fields)
        assert has_aggregate

    def test_parse_query_with_parameters(self) -> None:
        """Test extracting parameters from query."""
        query = """
        ВЫБРАТЬ * ИЗ Т
        ГДЕ Дата >= &НачалоПериода И Дата <= &КонецПериода
        """

        parsed = self.parser.parse(query)

        assert "НачалоПериода" in parsed.parameters
        assert "КонецПериода" in parsed.parameters

    def test_parse_virtual_table(self) -> None:
        """Test parsing query with virtual table."""
        query = """
        ВЫБРАТЬ *
        ИЗ РегистрСведений.ЦеныНоменклатуры.СрезПоследних(&Дата, ) КАК Цены
        """

        parsed = self.parser.parse(query)

        assert len(parsed.tables) >= 1
        # Should detect virtual table
        has_virtual = any(t.is_virtual_table for t in parsed.tables)
        assert has_virtual

    def test_parse_temp_table(self) -> None:
        """Test parsing query with temp table."""
        query = """
        ВЫБРАТЬ Ссылка
        ПОМЕСТИТЬ ВТДанные
        ИЗ Справочник.Номенклатура
        """

        parsed = self.parser.parse(query)

        assert "ВТДанные" in parsed.temporary_tables

    def test_validate_missing_fields(self) -> None:
        """Test validation for missing SELECT fields."""
        query = """
        ВЫБРАТЬ
        ИЗ Справочник.Номенклатура
        """

        parsed = self.parser.parse(query)
        result = self.parser.validate(parsed)

        assert not result.is_valid
        assert any("SELECT" in err or "fields" in err.lower() for err in result.errors)

    def test_explain_query(self) -> None:
        """Test query explanation."""
        query = """
        ВЫБРАТЬ
            Товары.Наименование,
            СУММА(Продажи.Сумма) КАК ИтогоПродаж
        ИЗ
            Документ.Продажа.Товары КАК Продажи
            ЛЕВОЕ СОЕДИНЕНИЕ Справочник.Номенклатура КАК Товары
            ПО Продажи.Номенклатура = Товары.Ссылка
        СГРУППИРОВАТЬ ПО
            Товары.Наименование
        """

        parsed = self.parser.parse(query)
        explanation = self.parser.explain(parsed)

        assert "Источники данных" in explanation
        assert "Выбираемые поля" in explanation
        assert "Группировка" in explanation


class TestTemplateEngine:
    """Tests for TemplateEngine facade."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.engine = TemplateEngine()

    def test_list_templates(self) -> None:
        """Test listing templates."""
        templates = self.engine.list_templates()

        assert len(templates) > 0
        # Check we have different categories
        categories = {t.category for t in templates}
        assert len(categories) > 1

    def test_list_templates_by_category(self) -> None:
        """Test listing templates by category."""
        query_templates = self.engine.list_templates(TemplateCategory.QUERY)

        assert len(query_templates) > 0
        assert all(t.category == TemplateCategory.QUERY for t in query_templates)

    def test_get_template(self) -> None:
        """Test getting template by ID."""
        template = self.engine.get_template("query.select_simple")

        assert template is not None
        assert template.id == "query.select_simple"
        assert len(template.placeholders) > 0

    def test_get_nonexistent_template(self) -> None:
        """Test getting non-existent template."""
        template = self.engine.get_template("nonexistent.template")

        assert template is None

    def test_search_templates(self) -> None:
        """Test searching templates."""
        # Search by Russian term
        results = self.engine.search_templates("запрос")
        assert len(results) > 0

        # Search by English term
        results = self.engine.search_templates("select")
        assert len(results) > 0

    def test_generate_code(self) -> None:
        """Test code generation."""
        result = self.engine.generate(
            "query.select_simple",
            {
                "Fields": "Код, Наименование",
                "TableName": "Справочник.Номенклатура",
                "Alias": "Товары",
            },
        )

        assert result.success
        assert "ВЫБРАТЬ" in result.code
        assert "Код, Наименование" in result.code
        assert "Справочник.Номенклатура" in result.code

    def test_generate_with_context(self) -> None:
        """Test code generation with context."""
        context = GenerationContext(
            current_object_name="ПриходТовара",
            current_object_type="Document",
        )

        result = self.engine.generate(
            "query.select_simple",
            {
                "Fields": "Ссылка",
                "TableName": "Документ.ПриходТовара",
                "Alias": "Док",
            },
            context,
        )

        # Should generate successfully with context
        assert result.success
        assert "Документ.ПриходТовара" in result.code

    def test_parse_and_validate_query(self) -> None:
        """Test query parsing and validation."""
        query = """
        ВЫБРАТЬ
            Наименование,
            Код
        ИЗ
            Справочник.Номенклатура КАК Номенклатура
        """

        # Parse
        parsed = self.engine.parse_query(query)
        assert len(parsed.tables) > 0

        # Validate
        validation = self.engine.validate_query(query)
        assert validation.is_valid

    def test_optimize_query(self) -> None:
        """Test query optimization suggestions."""
        query = """
        ВЫБРАТЬ * ИЗ Справочник.Номенклатура
        """

        suggestions = self.engine.optimize_query(query)

        # Should suggest avoiding SELECT *
        assert len(suggestions) > 0
        assert any("*" in s.original_fragment or "SELECT *" in s.description for s in suggestions)

    def test_explain_query(self) -> None:
        """Test query explanation."""
        query = """
        ВЫБРАТЬ Наименование ИЗ Справочник.Номенклатура
        """

        explanation = self.engine.explain_query(query)

        assert "Анализ запроса" in explanation
        assert "Источники данных" in explanation

    def test_get_query_tables(self) -> None:
        """Test getting tables from query."""
        query = """
        ВЫБРАТЬ *
        ИЗ Справочник.Номенклатура КАК Т
        ЛЕВОЕ СОЕДИНЕНИЕ Справочник.ЕдиницыИзмерения КАК ЕИ
        ПО Т.ЕдиницаИзмерения = ЕИ.Ссылка
        """

        tables = self.engine.get_query_tables(query)

        assert len(tables) >= 2
        assert any("Номенклатура" in t for t in tables)

    def test_get_template_stats(self) -> None:
        """Test getting template statistics."""
        stats = self.engine.get_template_stats()

        assert stats["total_templates"] > 0
        assert len(stats["categories"]) > 0
        assert stats["unique_tags"] > 0


class TestTemplateCategories:
    """Tests for template category coverage."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.engine = TemplateEngine()

    def test_query_templates_exist(self) -> None:
        """Test that query templates exist."""
        templates = self.engine.list_templates(TemplateCategory.QUERY)
        assert len(templates) >= 10  # Should have 10+ query templates

    def test_handler_templates_exist(self) -> None:
        """Test that handler templates exist."""
        templates = self.engine.list_templates(TemplateCategory.HANDLER)
        assert len(templates) >= 5

    def test_print_form_templates_exist(self) -> None:
        """Test that print form templates exist."""
        templates = self.engine.list_templates(TemplateCategory.PRINT_FORM)
        assert len(templates) >= 1

    def test_movement_templates_exist(self) -> None:
        """Test that movement templates exist."""
        templates = self.engine.list_templates(TemplateCategory.MOVEMENT)
        assert len(templates) >= 3

    def test_api_templates_exist(self) -> None:
        """Test that API templates exist."""
        templates = self.engine.list_templates(TemplateCategory.API)
        assert len(templates) >= 3
