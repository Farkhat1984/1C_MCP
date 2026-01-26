"""
Unit tests for BSL Parser.

Tests BSL code parsing: procedures, functions, regions, directives.
"""

from pathlib import Path

import pytest

from mcp_1c.engines.code.parser import BslParser
from mcp_1c.domain.code import CompilationDirective


class TestBslParser:
    """Test suite for BslParser."""

    @pytest.fixture
    def parser(self) -> BslParser:
        """Create parser instance."""
        return BslParser()

    def test_parse_simple_procedure(self, parser: BslParser) -> None:
        """Test parsing a simple procedure."""
        code = """
Процедура ТестоваяПроцедура()
    // Код процедуры
КонецПроцедуры
"""
        module = parser.parse_content(code)

        assert len(module.procedures) == 1
        proc = module.procedures[0]
        assert proc.name == "ТестоваяПроцедура"
        assert proc.is_function is False
        assert proc.is_export is False

    def test_parse_export_procedure(self, parser: BslParser) -> None:
        """Test parsing an export procedure."""
        code = """
Процедура ЭкспортнаяПроцедура() Экспорт
    // Код
КонецПроцедуры
"""
        module = parser.parse_content(code)

        assert len(module.procedures) == 1
        proc = module.procedures[0]
        assert proc.name == "ЭкспортнаяПроцедура"
        assert proc.is_export is True

    def test_parse_function(self, parser: BslParser) -> None:
        """Test parsing a function."""
        code = """
Функция ТестоваяФункция()
    Возврат 42;
КонецФункции
"""
        module = parser.parse_content(code)

        assert len(module.procedures) == 1
        proc = module.procedures[0]
        assert proc.name == "ТестоваяФункция"
        assert proc.is_function is True

    def test_parse_export_function(self, parser: BslParser) -> None:
        """Test parsing an export function."""
        code = """
Функция ПолучитьЗначение() Экспорт
    Возврат Значение;
КонецФункции
"""
        module = parser.parse_content(code)

        proc = module.procedures[0]
        assert proc.is_function is True
        assert proc.is_export is True

    def test_parse_english_keywords(self, parser: BslParser) -> None:
        """Test parsing with English keywords."""
        code = """
Function GetValue() Export
    Return 42;
EndFunction
"""
        module = parser.parse_content(code)

        assert len(module.procedures) == 1
        proc = module.procedures[0]
        assert proc.name == "GetValue"
        assert proc.is_function is True
        assert proc.is_export is True

    def test_parse_procedure_with_parameters(self, parser: BslParser) -> None:
        """Test parsing procedure with parameters."""
        code = """
Процедура УстановитьЗначение(Параметр1, Параметр2)
    // Код
КонецПроцедуры
"""
        module = parser.parse_content(code)

        proc = module.procedures[0]
        assert len(proc.parameters) == 2
        assert proc.parameters[0].name == "Параметр1"
        assert proc.parameters[1].name == "Параметр2"

    def test_parse_parameter_by_value(self, parser: BslParser) -> None:
        """Test parsing parameter passed by value."""
        code = """
Процедура Тест(Знач Параметр)
    // Код
КонецПроцедуры
"""
        module = parser.parse_content(code)

        proc = module.procedures[0]
        assert len(proc.parameters) == 1
        assert proc.parameters[0].name == "Параметр"
        assert proc.parameters[0].by_value is True

    def test_parse_parameter_with_default(self, parser: BslParser) -> None:
        """Test parsing parameter with default value."""
        code = """
Функция Тест(Параметр = Неопределено)
    Возврат Параметр;
КонецФункции
"""
        module = parser.parse_content(code)

        proc = module.procedures[0]
        param = proc.parameters[0]
        assert param.name == "Параметр"
        assert param.default_value == "Неопределено"
        assert param.is_optional is True

    def test_parse_multiple_parameters(self, parser: BslParser) -> None:
        """Test parsing multiple parameters with different modifiers."""
        code = """
Функция СложнаяФункция(Знач Параметр1, Параметр2, Параметр3 = "")
    Возврат Истина;
КонецФункции
"""
        module = parser.parse_content(code)

        proc = module.procedures[0]
        assert len(proc.parameters) == 3

        assert proc.parameters[0].name == "Параметр1"
        assert proc.parameters[0].by_value is True

        assert proc.parameters[1].name == "Параметр2"
        assert proc.parameters[1].by_value is False

        assert proc.parameters[2].name == "Параметр3"
        assert proc.parameters[2].default_value == '""'
        assert proc.parameters[2].is_optional is True

    def test_parse_server_directive(self, parser: BslParser) -> None:
        """Test parsing server compilation directive."""
        code = """
&НаСервере
Процедура СерверныйМетод()
    // Код
КонецПроцедуры
"""
        module = parser.parse_content(code)

        proc = module.procedures[0]
        assert proc.directive == CompilationDirective.AT_SERVER

    def test_parse_client_directive(self, parser: BslParser) -> None:
        """Test parsing client compilation directive."""
        code = """
&НаКлиенте
Процедура КлиентскийМетод()
    // Код
КонецПроцедуры
"""
        module = parser.parse_content(code)

        proc = module.procedures[0]
        assert proc.directive == CompilationDirective.AT_CLIENT

    def test_parse_server_no_context_directive(self, parser: BslParser) -> None:
        """Test parsing server without context directive."""
        code = """
&НаСервереБезКонтекста
Функция СерверныйМетодБезКонтекста()
    Возврат 1;
КонецФункции
"""
        module = parser.parse_content(code)

        proc = module.procedures[0]
        assert proc.directive == CompilationDirective.AT_SERVER_WITHOUT_CONTEXT

    def test_parse_client_at_server_directive(self, parser: BslParser) -> None:
        """Test parsing client at server directive."""
        code = """
&НаКлиентеНаСервереБезКонтекста
Функция УниверсальнаяФункция()
    Возврат 1;
КонецФункции
"""
        module = parser.parse_content(code)

        proc = module.procedures[0]
        assert proc.directive == CompilationDirective.AT_CLIENT_AT_SERVER_WITHOUT_CONTEXT

    def test_parse_region(self, parser: BslParser) -> None:
        """Test parsing regions."""
        code = """
#Область ПубличныйИнтерфейс

Процедура Тест() Экспорт
КонецПроцедуры

#КонецОбласти
"""
        module = parser.parse_content(code)

        assert len(module.regions) == 1
        region = module.regions[0]
        assert region.name == "ПубличныйИнтерфейс"
        assert region.start_line == 2
        assert region.end_line == 7

    def test_parse_nested_regions(self, parser: BslParser) -> None:
        """Test parsing nested regions."""
        code = """
#Область Внешняя

#Область Внутренняя
Процедура Тест()
КонецПроцедуры
#КонецОбласти

#КонецОбласти
"""
        module = parser.parse_content(code)

        assert len(module.regions) == 2
        region_names = [r.name for r in module.regions]
        assert "Внешняя" in region_names
        assert "Внутренняя" in region_names

    def test_parse_procedure_in_region(self, parser: BslParser) -> None:
        """Test that procedure knows its containing region."""
        code = """
#Область ОбработчикиСобытий

Процедура ПередЗаписью()
КонецПроцедуры

#КонецОбласти
"""
        module = parser.parse_content(code)

        proc = module.procedures[0]
        assert proc.region == "ОбработчикиСобытий"

    def test_parse_english_region(self, parser: BslParser) -> None:
        """Test parsing regions with English keywords."""
        code = """
#Region Public

Function Test() Export
EndFunction

#EndRegion
"""
        module = parser.parse_content(code)

        assert len(module.regions) == 1
        assert module.regions[0].name == "Public"

    def test_parse_multiple_procedures(self, parser: BslParser) -> None:
        """Test parsing multiple procedures."""
        code = """
Процедура Первая()
КонецПроцедуры

Функция Вторая() Экспорт
    Возврат 1;
КонецФункции

&НаСервере
Процедура Третья(Параметр)
КонецПроцедуры
"""
        module = parser.parse_content(code)

        assert len(module.procedures) == 3

        assert module.procedures[0].name == "Первая"
        assert module.procedures[0].is_function is False

        assert module.procedures[1].name == "Вторая"
        assert module.procedures[1].is_function is True
        assert module.procedures[1].is_export is True

        assert module.procedures[2].name == "Третья"
        assert module.procedures[2].directive == CompilationDirective.AT_SERVER

    def test_parse_procedure_body(self, parser: BslParser) -> None:
        """Test that procedure body is extracted."""
        code = """
Процедура Тест()
    Переменная = 1;
    Результат = Переменная + 2;
КонецПроцедуры
"""
        module = parser.parse_content(code)

        proc = module.procedures[0]
        assert "Переменная = 1" in proc.body
        assert "Результат = Переменная + 2" in proc.body
        assert "КонецПроцедуры" in proc.body

    def test_parse_procedure_signature(self, parser: BslParser) -> None:
        """Test procedure signature extraction."""
        code = """
Функция МояФункция(Параметр1, Знач Параметр2 = Неопределено) Экспорт
    Возврат Параметр1;
КонецФункции
"""
        module = parser.parse_content(code)

        proc = module.procedures[0]
        assert "Функция МояФункция" in proc.signature
        assert "Параметр1" in proc.signature

    def test_parse_documentation_comment(self, parser: BslParser) -> None:
        """Test parsing documentation comments."""
        code = """
// Описание функции
// Параметры:
//   Значение - число для обработки
//
Функция ОбработатьЗначение(Значение)
    Возврат Значение * 2;
КонецФункции
"""
        module = parser.parse_content(code)

        proc = module.procedures[0]
        assert proc.comment is not None
        assert "Описание функции" in proc.comment

    def test_parse_line_count(self, parser: BslParser) -> None:
        """Test line count is correct."""
        code = "Строка1\nСтрока2\nСтрока3\nСтрока4\n"
        module = parser.parse_content(code)

        assert module.line_count == 4

    def test_parse_empty_file(self, parser: BslParser) -> None:
        """Test parsing empty file."""
        module = parser.parse_content("")

        assert len(module.procedures) == 0
        assert len(module.regions) == 0
        assert module.line_count == 0

    def test_parse_file_without_procedures(self, parser: BslParser) -> None:
        """Test parsing file with only comments and regions."""
        code = """
// Модуль констант

#Область Константы

Перем Константа1;
Перем Константа2;

#КонецОбласти
"""
        module = parser.parse_content(code)

        assert len(module.procedures) == 0
        assert len(module.regions) == 1

    def test_get_procedure_by_name(self, parser: BslParser) -> None:
        """Test getting procedure by name from module."""
        code = """
Процедура Первая()
КонецПроцедуры

Функция Вторая()
    Возврат 1;
КонецФункции
"""
        module = parser.parse_content(code)

        proc = module.get_procedure("Вторая")
        assert proc is not None
        assert proc.name == "Вторая"
        assert proc.is_function is True

    def test_get_procedure_case_insensitive(self, parser: BslParser) -> None:
        """Test that procedure lookup is case-insensitive."""
        code = """
Функция МояФункция()
    Возврат 1;
КонецФункции
"""
        module = parser.parse_content(code)

        # Should find with different case
        proc = module.get_procedure("мояфункция")
        assert proc is not None
        assert proc.name == "МояФункция"

    def test_get_nonexistent_procedure(self, parser: BslParser) -> None:
        """Test getting non-existent procedure returns None."""
        code = """
Процедура Существует()
КонецПроцедуры
"""
        module = parser.parse_content(code)

        proc = module.get_procedure("НеСуществует")
        assert proc is None

    def test_procedure_line_numbers(self, parser: BslParser) -> None:
        """Test procedure start and end line numbers."""
        code = """
// Комментарий
Процедура Тест()
    Строка1;
    Строка2;
КонецПроцедуры
"""
        module = parser.parse_content(code)

        proc = module.procedures[0]
        assert proc.start_line == 3  # Line with Процедура
        assert proc.end_line == 6  # Line with КонецПроцедуры
