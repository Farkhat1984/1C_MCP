"""
Unit tests for code generation tools with BSL LS validation.

Tests generate.* tools with validation integration.
"""

import pytest

from mcp_1c.tools.generate_tools import (
    GenerateApiTool,
    GenerateHandlerTool,
    GenerateMovementTool,
    GeneratePrintTool,
    GenerateQueryTool,
    GenerateScheduledJobTool,
    GenerateSubscriptionTool,
    validate_generated_code,
)


class TestValidateGeneratedCode:
    """Test the validate_generated_code function."""

    @pytest.mark.asyncio
    async def test_validate_valid_code(self) -> None:
        """Test validation of valid BSL code."""
        code = """
Процедура Тест()
    Сообщить("Привет");
КонецПроцедуры
"""
        result = await validate_generated_code(code)

        assert "valid" in result
        assert "error_count" in result
        assert "warning_count" in result
        assert "diagnostics" in result
        assert result["valid"] is True
        assert result["error_count"] == 0

    @pytest.mark.asyncio
    async def test_validate_code_with_issues(self) -> None:
        """Test validation of code with issues."""
        code = """
Процедура Тест()
    Перейти ~Метка;
    ~Метка:
КонецПроцедуры
"""
        result = await validate_generated_code(code)

        assert "valid" in result
        # Should have warning about deprecated GOTO
        assert result["warning_count"] > 0 or len(result["diagnostics"]) > 0


class TestGenerateQueryTool:
    """Test GenerateQueryTool with validation."""

    @pytest.fixture
    def tool(self) -> GenerateQueryTool:
        """Create tool instance."""
        return GenerateQueryTool()

    @pytest.mark.asyncio
    async def test_generate_without_validation(self, tool: GenerateQueryTool) -> None:
        """Test generation without validation."""
        result = await tool.execute({
            "template_id": "query.select_simple",
            "values": {
                "TableName": "Справочник.Номенклатура",
                "Fields": "Ссылка, Наименование",
            },
        })

        assert result["success"] is True
        assert result["code"] is not None
        assert "validation" not in result

    @pytest.mark.asyncio
    async def test_generate_with_validation(self, tool: GenerateQueryTool) -> None:
        """Test generation with validation enabled."""
        result = await tool.execute({
            "template_id": "query.select_simple",
            "values": {
                "TableName": "Справочник.Номенклатура",
                "Fields": "Ссылка, Наименование",
            },
            "validate": True,
        })

        assert result["success"] is True
        assert result["code"] is not None
        assert "validation" in result
        assert "valid" in result["validation"]


class TestGenerateHandlerTool:
    """Test GenerateHandlerTool with validation."""

    @pytest.fixture
    def tool(self) -> GenerateHandlerTool:
        """Create tool instance."""
        return GenerateHandlerTool()

    @pytest.mark.asyncio
    async def test_generate_handler_with_validation(
        self, tool: GenerateHandlerTool
    ) -> None:
        """Test handler generation with validation."""
        result = await tool.execute({
            "template_id": "handler.before_write",
            "values": {
                "Cancel": "Отказ",
                "CheckCode": "Если Отказ Тогда Возврат; КонецЕсли;",
            },
            "validate": True,
        })

        assert result["success"] is True
        assert "validation" in result
        assert result["validation"]["valid"] is True


class TestGenerateMovementTool:
    """Test GenerateMovementTool with validation."""

    @pytest.fixture
    def tool(self) -> GenerateMovementTool:
        """Create tool instance."""
        return GenerateMovementTool()

    @pytest.mark.asyncio
    async def test_generate_movement_with_validation(
        self, tool: GenerateMovementTool
    ) -> None:
        """Test movement generation with validation."""
        result = await tool.execute({
            "template_id": "movement.accumulation_income",
            "values": {
                "RegisterName": "ОстаткиТоваров",
                "Period": "Дата",
                "DimensionsCode": "Движение.Номенклатура = Товар;",
                "ResourcesCode": "Движение.Количество = Количество;",
                "HasAttributes": False,
                "AttributesCode": "",
            },
            "validate": True,
        })

        assert result["success"] is True
        assert "validation" in result


class TestGenerateApiTool:
    """Test GenerateApiTool with validation."""

    @pytest.fixture
    def tool(self) -> GenerateApiTool:
        """Create tool instance."""
        return GenerateApiTool()

    @pytest.mark.asyncio
    async def test_generate_api_with_validation(self, tool: GenerateApiTool) -> None:
        """Test API generation with validation."""
        result = await tool.execute({
            "template_id": "api.http_service_get",
            "values": {
                "MethodName": "ПолучитьДанные",
                "HasParameter": True,
                "ParameterName": "ИдентификаторОбъекта",
                "ParameterUrlName": "id",
                "BusinessLogic": "Данные = Новый Структура;",
                "ResultCode": "Возврат Данные;",
            },
            "validate": True,
        })

        assert result["success"] is True
        assert "validation" in result


class TestGeneratePrintTool:
    """Test GeneratePrintTool with validation."""

    @pytest.fixture
    def tool(self) -> GeneratePrintTool:
        """Create tool instance."""
        return GeneratePrintTool()

    @pytest.mark.asyncio
    async def test_generate_print_with_validation(
        self, tool: GeneratePrintTool
    ) -> None:
        """Test print form generation with validation."""
        result = await tool.execute({
            "template_id": "print.basic",
            "values": {
                "FormName": "ПечатнаяФорма",
                "ObjectType": "ДокументСсылка.ПриходнаяНакладная",
                "TemplateName": "ПФ_MXL_Основная",
                "HasHeader": True,
                "HasFooter": False,
                "HeaderParams": 'ОбластьШапка.Параметры.Заполнить(ДанныеОбъекта);',
                "TabularSectionName": "Товары",
                "RowParams": 'ОбластьСтрока.Параметры.Заполнить(СтрокаТовары);',
                "FooterParams": "",
            },
            "validate": True,
        })

        assert result["success"] is True
        assert "validation" in result


class TestGenerateSubscriptionTool:
    """Test GenerateSubscriptionTool with validation."""

    @pytest.fixture
    def tool(self) -> GenerateSubscriptionTool:
        """Create tool instance."""
        return GenerateSubscriptionTool()

    @pytest.mark.asyncio
    async def test_generate_subscription_with_validation(
        self, tool: GenerateSubscriptionTool
    ) -> None:
        """Test subscription handler generation with validation."""
        result = await tool.execute({
            "values": {
                "SubscriptionName": "ПриЗаписиДокумента",
                "Sources": "ДокументОбъект.*",
                "EventName": "ПриЗаписи",
                "HandlerName": "ОбработчикПриЗаписи",
                "HandlerCode": "// Обработка",
            },
            "validate": True,
        })

        assert result["success"] is True
        assert "validation" in result


class TestGenerateScheduledJobTool:
    """Test GenerateScheduledJobTool with validation."""

    @pytest.fixture
    def tool(self) -> GenerateScheduledJobTool:
        """Create tool instance."""
        return GenerateScheduledJobTool()

    @pytest.mark.asyncio
    async def test_generate_scheduled_job_with_validation(
        self, tool: GenerateScheduledJobTool
    ) -> None:
        """Test scheduled job handler generation with validation."""
        result = await tool.execute({
            "values": {
                "JobName": "ОбновлениеДанных",
                "HandlerName": "ОбновитьДанные",
                "JobCode": "// Код задания",
                "HasLogging": True,
                "LogEventName": "ОбновлениеДанных",
            },
            "validate": True,
        })

        assert result["success"] is True
        assert "validation" in result
