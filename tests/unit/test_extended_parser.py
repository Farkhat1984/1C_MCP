"""
Tests for extended BSL parser (Phase 2).

Tests method call extraction, metadata reference detection,
query extraction, and variable usage analysis.
"""

import pytest
from pathlib import Path

from mcp_1c.engines.code.parser import BslParser
from mcp_1c.domain.code import MetadataReferenceType


@pytest.fixture
def parser() -> BslParser:
    """Create parser instance."""
    return BslParser()


@pytest.fixture
def sample_bsl_code() -> str:
    """Sample BSL code for testing extended parsing."""
    return '''
#Область ПрограммныйИнтерфейс

// Получает данные номенклатуры
//
// Параметры:
//  НоменклатураСсылка - СправочникСсылка.Номенклатура - ссылка на номенклатуру
//
// Возвращаемое значение:
//  Структура - данные номенклатуры
//
&НаСервереБезКонтекста
Функция ПолучитьДанныеНоменклатуры(НоменклатураСсылка) Экспорт

    Результат = Новый Структура;

    // Получаем объект
    Объект = НоменклатураСсылка.ПолучитьОбъект();

    // Запрос к справочнику
    Запрос = Новый Запрос;
    Запрос.Текст = "ВЫБРАТЬ
        |   Номенклатура.Наименование,
        |   Номенклатура.Артикул,
        |   Номенклатура.Цена
        |ИЗ
        |   Справочник.Номенклатура КАК Номенклатура
        |ГДЕ
        |   Номенклатура.Ссылка = &Ссылка";

    Запрос.УстановитьПараметр("Ссылка", НоменклатураСсылка);

    Выборка = Запрос.Выполнить().Выбрать();
    Если Выборка.Следующий() Тогда
        Результат.Вставить("Наименование", Выборка.Наименование);
        Результат.Вставить("Артикул", Выборка.Артикул);
    КонецЕсли;

    // Получаем остатки из регистра
    Остатки = РегистрыНакопления.ОстаткиТоваров.Остатки(
        ТекущаяДата(),
        Новый Структура("Номенклатура", НоменклатураСсылка)
    );

    Если Остатки.Количество() > 0 Тогда
        Результат.Вставить("Остаток", Остатки[0].КоличествоОстаток);
    КонецЕсли;

    ОбщийМодуль.ЗаписатьВЛог("Получены данные номенклатуры");

    Возврат Результат;

КонецФункции

// Создаёт новый документ
&НаСервере
Процедура СоздатьДокумент(ДанныеДокумента)

    НовыйДокумент = Документы.РеализацияТоваров.СоздатьДокумент();
    НовыйДокумент.Дата = ТекущаяДата();
    НовыйДокумент.Контрагент = Справочники.Контрагенты.НайтиПоКоду(ДанныеДокумента.КодКонтрагента);

    Для Каждого СтрокаТовара Из ДанныеДокумента.Товары Цикл
        НоваяСтрока = НовыйДокумент.Товары.Добавить();
        НоваяСтрока.Номенклатура = Справочники.Номенклатура.НайтиПоКоду(СтрокаТовара.Код);
        НоваяСтрока.Количество = СтрокаТовара.Количество;
        НоваяСтрока.Цена = ПолучитьДанныеНоменклатуры(НоваяСтрока.Номенклатура).Цена;
    КонецЦикла;

    НовыйДокумент.Записать();

КонецПроцедуры

#КонецОбласти

#Область СлужебныеПроцедуры

&НаКлиенте
Асинх Процедура ЗагрузитьДанныеАсинх()

    Данные = Ждать ПолучитьДанныеСервера();
    ОбновитьФорму(Данные);

КонецПроцедуры

#КонецОбласти
'''


class TestExtendedParser:
    """Tests for extended BSL parsing."""

    def test_extract_method_calls(self, parser: BslParser, sample_bsl_code: str):
        """Test method call extraction."""
        module = parser.parse_content_extended(sample_bsl_code)

        # Check that method calls are extracted
        assert len(module.method_calls) > 0

        # Find specific calls
        call_names = {call.name for call in module.method_calls}

        # Should find these method calls
        assert "ПолучитьОбъект" in call_names
        assert "Выполнить" in call_names
        assert "Выбрать" in call_names
        assert "УстановитьПараметр" in call_names
        assert "Вставить" in call_names
        assert "ЗаписатьВЛог" in call_names
        assert "СоздатьДокумент" in call_names
        assert "НайтиПоКоду" in call_names
        assert "Записать" in call_names
        assert "Количество" in call_names

    def test_extract_method_calls_with_objects(self, parser: BslParser, sample_bsl_code: str):
        """Test that method calls capture object names."""
        module = parser.parse_content_extended(sample_bsl_code)

        # Find calls with object names
        calls_with_objects = [c for c in module.method_calls if c.object_name]
        assert len(calls_with_objects) > 0

        # Check specific object.method patterns
        object_method_pairs = {
            (c.object_name, c.name) for c in calls_with_objects
        }

        # Should find Запрос.Выполнить, etc.
        assert ("Запрос", "УстановитьПараметр") in object_method_pairs
        assert ("НовыйДокумент", "Записать") in object_method_pairs

    def test_extract_method_calls_containing_procedure(
        self, parser: BslParser, sample_bsl_code: str
    ):
        """Test that method calls are associated with containing procedure."""
        module = parser.parse_content_extended(sample_bsl_code)

        # Check that calls have containing procedure
        calls_in_get_data = [
            c for c in module.method_calls
            if c.containing_procedure == "ПолучитьДанныеНоменклатуры"
        ]

        assert len(calls_in_get_data) > 0

    def test_extract_metadata_references(self, parser: BslParser, sample_bsl_code: str):
        """Test metadata reference extraction."""
        module = parser.parse_content_extended(sample_bsl_code)

        # Check metadata references
        assert len(module.metadata_references) > 0

        # Find by full name
        full_names = {ref.full_name for ref in module.metadata_references}

        # Should find catalog references
        assert any("Номенклатура" in name for name in full_names)
        assert any("Контрагенты" in name for name in full_names)

        # Should find document references
        assert any("РеализацияТоваров" in name for name in full_names)

        # Should find register references
        assert any("ОстаткиТоваров" in name for name in full_names)

    def test_metadata_reference_types(self, parser: BslParser, sample_bsl_code: str):
        """Test that metadata reference types are detected correctly."""
        module = parser.parse_content_extended(sample_bsl_code)

        # Get reference types
        ref_types = {ref.reference_type for ref in module.metadata_references}

        # Should detect different types
        assert MetadataReferenceType.CATALOG in ref_types
        assert MetadataReferenceType.DOCUMENT in ref_types
        assert MetadataReferenceType.ACCUMULATION_REGISTER in ref_types

    def test_extract_queries(self, parser: BslParser, sample_bsl_code: str):
        """Test query extraction."""
        module = parser.parse_content_extended(sample_bsl_code)

        # Check queries
        assert len(module.queries) > 0

        query = module.queries[0]

        # Check query properties
        assert "ВЫБРАТЬ" in query.query_text or "SELECT" in query.query_text.upper()
        assert query.containing_procedure == "ПолучитьДанныеНоменклатуры"

    def test_extract_query_tables(self, parser: BslParser, sample_bsl_code: str):
        """Test that query tables are extracted."""
        module = parser.parse_content_extended(sample_bsl_code)

        if module.queries:
            query = module.queries[0]
            # Tables should be extracted
            assert len(query.tables) > 0
            # Should find Справочник.Номенклатура
            assert any("Номенклатура" in table for table in query.tables)

    def test_async_call_detection(self, parser: BslParser, sample_bsl_code: str):
        """Test async call detection."""
        module = parser.parse_content_extended(sample_bsl_code)

        # Find async calls (using Ждать/Await)
        async_calls = [c for c in module.method_calls if c.is_async_call]

        # Should detect async call with Ждать
        assert len(async_calls) > 0

    def test_module_helper_methods(self, parser: BslParser, sample_bsl_code: str):
        """Test extended module helper methods."""
        module = parser.parse_content_extended(sample_bsl_code)

        # Test get_unique_called_methods
        unique_methods = module.get_unique_called_methods()
        assert isinstance(unique_methods, list)
        assert len(unique_methods) > 0

        # Test get_unique_metadata_objects
        unique_metadata = module.get_unique_metadata_objects()
        assert isinstance(unique_metadata, list)
        assert len(unique_metadata) > 0

        # Test get_calls_in_procedure
        calls = module.get_calls_in_procedure("СоздатьДокумент")
        assert isinstance(calls, list)

        # Test get_metadata_in_procedure
        metadata = module.get_metadata_in_procedure("СоздатьДокумент")
        assert isinstance(metadata, list)


class TestEnglishSyntax:
    """Tests for English BSL syntax parsing."""

    @pytest.fixture
    def english_bsl_code(self) -> str:
        """Sample BSL code in English."""
        return '''
&AtServerNoContext
Function GetProductData(ProductRef) Export

    Query = New Query;
    Query.Text = "SELECT
        |   Products.Description,
        |   Products.Code
        |FROM
        |   Catalog.Products AS Products
        |WHERE
        |   Products.Ref = &Ref";

    Query.SetParameter("Ref", ProductRef);
    Result = Query.Execute().Select();

    Return Result;

EndFunction
'''

    def test_english_metadata_references(self, parser: BslParser, english_bsl_code: str):
        """Test English metadata reference detection."""
        module = parser.parse_content_extended(english_bsl_code)

        # Should detect Catalog.Products
        assert len(module.metadata_references) > 0

        ref_types = {ref.reference_type for ref in module.metadata_references}
        assert MetadataReferenceType.CATALOG in ref_types

    def test_english_method_calls(self, parser: BslParser, english_bsl_code: str):
        """Test English method call detection."""
        module = parser.parse_content_extended(english_bsl_code)

        call_names = {call.name for call in module.method_calls}

        assert "SetParameter" in call_names
        assert "Execute" in call_names
        assert "Select" in call_names
