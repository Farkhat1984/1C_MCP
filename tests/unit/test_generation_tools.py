"""
Unit tests for code generation tools.

Tests generate.*, query.*, and pattern.* tools.
"""

import pytest

from mcp_1c.tools.generate_tools import (
    GenerateHandlerTool,
    GenerateMovementTool,
    GenerateQueryTool,
)
from mcp_1c.tools.pattern_tools import (
    PatternApplyTool,
    PatternGetTool,
    PatternListTool,
    PatternSearchTool,
    PatternSuggestTool,
)
from mcp_1c.tools.query_tools import (
    QueryExplainTool,
    QueryOptimizeTool,
    QueryParseTool,
    QueryTablesTool,
    QueryValidateTool,
)


class TestGenerateQueryTool:
    """Tests for GenerateQueryTool."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.tool = GenerateQueryTool()

    @pytest.mark.asyncio
    async def test_generate_simple_select(self) -> None:
        """Test generating simple SELECT query."""
        result = await self.tool.execute({
            "template_id": "query.select_simple",
            "values": {
                "Fields": "Ссылка, Наименование",
                "TableName": "Справочник.Номенклатура",
                "Alias": "Товары",
            },
        })

        assert result["success"]
        assert "ВЫБРАТЬ" in result["code"]
        assert "Ссылка, Наименование" in result["code"]
        assert "Справочник.Номенклатура" in result["code"]

    @pytest.mark.asyncio
    async def test_generate_grouped_query(self) -> None:
        """Test generating grouped query."""
        result = await self.tool.execute({
            "template_id": "query.select_grouped",
            "values": {
                "GroupFields": "Контрагент",
                "AggregateFunction": "СУММА",
                "AggregateField": "Сумма",
                "AggregateAlias": "Итого",
                "TableName": "Документ.Продажа",
                "Alias": "Продажи",
            },
        })

        assert result["success"]
        assert "СГРУППИРОВАТЬ ПО" in result["code"]
        assert "СУММА" in result["code"]

    @pytest.mark.asyncio
    async def test_generate_query_with_missing_values(self) -> None:
        """Test error handling for missing values."""
        result = await self.tool.execute({
            "template_id": "query.select_simple",
            "values": {
                "Fields": "Наименование",
                # Missing TableName
            },
        })

        assert not result["success"]
        assert "TableName" in result["missing_placeholders"]


class TestGenerateHandlerTool:
    """Tests for GenerateHandlerTool."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.tool = GenerateHandlerTool()

    @pytest.mark.asyncio
    async def test_generate_before_write_handler(self) -> None:
        """Test generating BeforeWrite handler."""
        result = await self.tool.execute({
            "template_id": "handler.before_write",
            "values": {
                "CustomCode": "// Проверка данных",
            },
        })

        assert result["success"]
        assert "Процедура ПередЗаписью" in result["code"]
        assert "Отказ" in result["code"]

    @pytest.mark.asyncio
    async def test_generate_posting_handler(self) -> None:
        """Test generating posting handler."""
        result = await self.tool.execute({
            "template_id": "handler.posting",
            "values": {
                "MovementsInit": "Движения.ТоварыНаСкладах.Записывать = Истина;",
                "QueryText": "ВЫБРАТЬ * ИЗ Документ.Приход.Товары ГДЕ Ссылка = &Ссылка",
                "MovementCode": "// Формирование движений",
            },
        })

        assert result["success"]
        assert "ОбработкаПроведения" in result["code"]
        assert "РежимПроведения" in result["code"]


class TestGenerateMovementTool:
    """Tests for GenerateMovementTool."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.tool = GenerateMovementTool()

    @pytest.mark.asyncio
    async def test_generate_accumulation_income(self) -> None:
        """Test generating accumulation register income movement."""
        result = await self.tool.execute({
            "template_id": "movement.accumulation_income",
            "values": {
                "RegisterName": "ТоварыНаСкладах",
                "Period": "Дата",
                "DimensionsCode": "Движение.Номенклатура = Товар;",
                "ResourcesCode": "Движение.Количество = Количество;",
            },
        })

        assert result["success"]
        assert "ВидДвиженияНакопления.Приход" in result["code"]
        assert "ТоварыНаСкладах" in result["code"]


class TestQueryParseTool:
    """Tests for QueryParseTool."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.tool = QueryParseTool()

    @pytest.mark.asyncio
    async def test_parse_query(self) -> None:
        """Test parsing query."""
        result = await self.tool.execute({
            "query_text": """
                ВЫБРАТЬ
                    Наименование,
                    Код
                ИЗ
                    Справочник.Номенклатура КАК Товары
                ГДЕ
                    ПометкаУдаления = ЛОЖЬ
            """,
        })

        assert len(result["select_fields"]) >= 2
        assert len(result["tables"]) >= 1
        assert result["tables"][0]["alias"] == "Товары"

    @pytest.mark.asyncio
    async def test_parse_query_with_parameters(self) -> None:
        """Test parsing query with parameters."""
        result = await self.tool.execute({
            "query_text": """
                ВЫБРАТЬ * ИЗ Т
                ГДЕ Дата МЕЖДУ &Начало И &Конец
            """,
        })

        assert "Начало" in result["parameters"]
        assert "Конец" in result["parameters"]


class TestQueryValidateTool:
    """Tests for QueryValidateTool."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.tool = QueryValidateTool()

    @pytest.mark.asyncio
    async def test_validate_valid_query(self) -> None:
        """Test validating valid query."""
        result = await self.tool.execute({
            "query_text": """
                ВЫБРАТЬ Наименование
                ИЗ Справочник.Номенклатура
            """,
        })

        assert result["is_valid"]
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_validate_invalid_query(self) -> None:
        """Test validating invalid query."""
        result = await self.tool.execute({
            "query_text": """
                ВЫБРАТЬ
                ИЗ
            """,
        })

        assert not result["is_valid"]
        assert len(result["errors"]) > 0


class TestQueryOptimizeTool:
    """Tests for QueryOptimizeTool."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.tool = QueryOptimizeTool()

    @pytest.mark.asyncio
    async def test_optimize_select_star(self) -> None:
        """Test optimization suggestion for SELECT *."""
        result = await self.tool.execute({
            "query_text": "ВЫБРАТЬ * ИЗ Справочник.Номенклатура",
        })

        assert result["total_suggestions"] > 0
        # Should suggest avoiding SELECT *
        has_star_suggestion = any(
            "*" in s.get("original_fragment", "")
            for s in result["suggestions"]
        )
        assert has_star_suggestion


class TestQueryExplainTool:
    """Tests for QueryExplainTool."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.tool = QueryExplainTool()

    @pytest.mark.asyncio
    async def test_explain_query(self) -> None:
        """Test query explanation."""
        result = await self.tool.execute({
            "query_text": """
                ВЫБРАТЬ Наименование ИЗ Справочник.Номенклатура
            """,
        })

        assert "explanation" in result
        assert "Анализ запроса" in result["explanation"]
        assert "Источники данных" in result["explanation"]


class TestQueryTablesTool:
    """Tests for QueryTablesTool."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.tool = QueryTablesTool()

    @pytest.mark.asyncio
    async def test_get_tables(self) -> None:
        """Test getting tables from query."""
        result = await self.tool.execute({
            "query_text": """
                ВЫБРАТЬ *
                ИЗ Справочник.Номенклатура КАК Н
                ЛЕВОЕ СОЕДИНЕНИЕ Справочник.Контрагенты КАК К
                ПО Истина
            """,
        })

        assert result["count"] >= 2
        assert any("Номенклатура" in t for t in result["tables"])


class TestPatternListTool:
    """Tests for PatternListTool."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.tool = PatternListTool()

    @pytest.mark.asyncio
    async def test_list_all_patterns(self) -> None:
        """Test listing all patterns."""
        result = await self.tool.execute({})

        assert result["total"] >= 20
        assert len(result["templates"]) == result["total"]
        assert len(result["categories"]) >= 4
        # Each template should have required fields
        for t in result["templates"][:5]:
            assert "id" in t
            assert "name" in t
            assert "category" in t

    @pytest.mark.asyncio
    async def test_list_by_category(self) -> None:
        """Test listing patterns by category."""
        result = await self.tool.execute({"category": "query"})

        assert result["total"] > 0
        assert all(t["category"] == "query" for t in result["templates"])


class TestPatternGetTool:
    """Tests for PatternGetTool."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.tool = PatternGetTool()

    @pytest.mark.asyncio
    async def test_get_existing_pattern(self) -> None:
        """Test getting existing pattern."""
        result = await self.tool.execute({
            "template_id": "query.select_simple",
        })

        assert "error" not in result
        assert result["id"] == "query.select_simple"
        assert len(result["placeholders"]) >= 2
        assert "template_code" in result
        assert result["template_code"] != ""
        assert "category" in result
        assert result["category"] == "query"
        # Should have TableName placeholder
        placeholder_names = [p["name"] for p in result["placeholders"]]
        assert "TableName" in placeholder_names

    @pytest.mark.asyncio
    async def test_get_nonexistent_pattern(self) -> None:
        """Test getting non-existent pattern."""
        result = await self.tool.execute({
            "template_id": "nonexistent.pattern",
        })

        assert "error" in result


class TestPatternApplyTool:
    """Tests for PatternApplyTool."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.tool = PatternApplyTool()

    @pytest.mark.asyncio
    async def test_apply_pattern(self) -> None:
        """Test applying pattern."""
        result = await self.tool.execute({
            "template_id": "query.select_simple",
            "values": {
                "Fields": "Код",
                "TableName": "Справочник.Валюты",
                "Alias": "Валюты",
            },
        })

        assert result["success"]
        assert "ВЫБРАТЬ" in result["code"]
        assert "Код" in result["code"]


class TestPatternSearchTool:
    """Tests for PatternSearchTool."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.tool = PatternSearchTool()

    @pytest.mark.asyncio
    async def test_search_by_query(self) -> None:
        """Test searching by query."""
        result = await self.tool.execute({
            "query": "проведение",
        })

        assert result["total"] > 0

    @pytest.mark.asyncio
    async def test_search_by_category(self) -> None:
        """Test searching with category filter."""
        result = await self.tool.execute({
            "query": "select",
            "category": "query",
        })

        assert result["total"] > 0
        assert all(r["category"] == "query" for r in result["results"])


class TestPatternSuggestTool:
    """Tests for PatternSuggestTool."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.tool = PatternSuggestTool()

    @pytest.mark.asyncio
    async def test_suggest_by_task(self) -> None:
        """Test suggesting by task description."""
        result = await self.tool.execute({
            "task_description": "создать запрос для получения остатков",
        })

        assert result["total"] > 0
        # Should suggest query-related templates
        has_query = any(
            "query" in s["category"]
            for s in result["suggestions"]
        )
        assert has_query

    @pytest.mark.asyncio
    async def test_suggest_by_module_type(self) -> None:
        """Test suggesting by module type."""
        result = await self.tool.execute({
            "current_module_type": "ObjectModule",
        })

        assert result["total"] >= 0
