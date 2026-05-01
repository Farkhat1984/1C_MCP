"""
Pytest configuration and fixtures.

Provides test fixtures for unit and integration tests.
"""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_config_path(temp_dir: Path) -> Path:
    """
    Create mock 1C configuration structure.

    Returns:
        Path to mock configuration root
    """
    config_root = temp_dir / "Configuration"
    config_root.mkdir()

    # Create Configuration.xml
    config_xml = config_root / "Configuration.xml"
    config_xml.write_text(MOCK_CONFIGURATION_XML, encoding="utf-8")

    # Create Catalogs directory
    catalogs_dir = config_root / "Catalogs"
    catalogs_dir.mkdir()

    # Create mock catalog
    catalog_dir = catalogs_dir / "Товары"
    catalog_dir.mkdir()
    catalog_xml = catalog_dir / "Товары.xml"
    catalog_xml.write_text(MOCK_CATALOG_XML, encoding="utf-8")

    # Create Ext folder with module
    ext_dir = catalog_dir / "Ext"
    ext_dir.mkdir()
    module_file = ext_dir / "ObjectModule.bsl"
    module_file.write_text(MOCK_MODULE_BSL, encoding="utf-8")

    # Create Documents directory
    documents_dir = config_root / "Documents"
    documents_dir.mkdir()

    # Create mock document
    doc_dir = documents_dir / "ПриходТовара"
    doc_dir.mkdir()
    doc_xml = doc_dir / "ПриходТовара.xml"
    doc_xml.write_text(MOCK_DOCUMENT_XML, encoding="utf-8")

    # Create CommonModules directory
    common_modules_dir = config_root / "CommonModules"
    common_modules_dir.mkdir()

    # Create mock common module
    common_dir = common_modules_dir / "ОбщегоНазначения"
    common_dir.mkdir()
    common_xml = common_dir / "ОбщегоНазначения.xml"
    common_xml.write_text(MOCK_COMMON_MODULE_XML, encoding="utf-8")

    common_ext = common_dir / "Ext"
    common_ext.mkdir()
    common_bsl = common_ext / "Module.bsl"
    common_bsl.write_text(MOCK_COMMON_MODULE_BSL, encoding="utf-8")

    # Create Subsystems directory
    subsystems_dir = config_root / "Subsystems"
    subsystems_dir.mkdir()

    # Create mock subsystem
    subsystem_dir = subsystems_dir / "Торговля"
    subsystem_dir.mkdir()
    subsystem_xml = subsystem_dir / "Торговля.xml"
    subsystem_xml.write_text(MOCK_SUBSYSTEM_XML, encoding="utf-8")

    # Create InformationRegisters directory
    registers_dir = config_root / "InformationRegisters"
    registers_dir.mkdir()

    register_dir = registers_dir / "ЦеныТоваров"
    register_dir.mkdir()
    register_xml = register_dir / "ЦеныТоваров.xml"
    register_xml.write_text(MOCK_REGISTER_XML, encoding="utf-8")

    # Create Constants directory
    constants_dir = config_root / "Constants"
    constants_dir.mkdir()

    constant_dir = constants_dir / "ОсновнаяВалюта"
    constant_dir.mkdir()
    constant_xml = constant_dir / "ОсновнаяВалюта.xml"
    constant_xml.write_text(MOCK_CONSTANT_XML, encoding="utf-8")

    # Create FunctionalOptions directory
    fo_dir = config_root / "FunctionalOptions"
    fo_dir.mkdir()

    fo_item_dir = fo_dir / "ИспользоватьВалюты"
    fo_item_dir.mkdir()
    fo_xml = fo_item_dir / "ИспользоватьВалюты.xml"
    fo_xml.write_text(MOCK_FUNCTIONAL_OPTION_XML, encoding="utf-8")

    # Create ScheduledJobs directory
    sj_dir = config_root / "ScheduledJobs"
    sj_dir.mkdir()

    sj_item_dir = sj_dir / "ОбновлениеКурсовВалют"
    sj_item_dir.mkdir()
    sj_xml = sj_item_dir / "ОбновлениеКурсовВалют.xml"
    sj_xml.write_text(MOCK_SCHEDULED_JOB_XML, encoding="utf-8")

    # Create EventSubscriptions directory
    es_dir = config_root / "EventSubscriptions"
    es_dir.mkdir()

    es_item_dir = es_dir / "ПриЗаписиТоваров"
    es_item_dir.mkdir()
    es_xml = es_item_dir / "ПриЗаписиТоваров.xml"
    es_xml.write_text(MOCK_EVENT_SUBSCRIPTION_XML, encoding="utf-8")

    # Create second catalog: Контрагенты with BSL module
    kontragenty_dir = catalogs_dir / "Контрагенты"
    kontragenty_dir.mkdir()
    kontragenty_xml = kontragenty_dir / "Контрагенты.xml"
    kontragenty_xml.write_text(MOCK_CATALOG_KONTRAGENTY_XML, encoding="utf-8")

    kontragenty_ext = kontragenty_dir / "Ext"
    kontragenty_ext.mkdir()
    kontragenty_bsl = kontragenty_ext / "ObjectModule.bsl"
    kontragenty_bsl.write_text(MOCK_KONTRAGENTY_BSL, encoding="utf-8")

    # Create DefinedTypes directory
    dt_dir = config_root / "DefinedTypes"
    dt_dir.mkdir()

    dt_item_dir = dt_dir / "ВладелецТовара"
    dt_item_dir.mkdir()
    dt_xml = dt_item_dir / "ВладелецТовара.xml"
    dt_xml.write_text(MOCK_DEFINED_TYPE_XML, encoding="utf-8")

    # Create CommonAttributes directory
    ca_dir = config_root / "CommonAttributes"
    ca_dir.mkdir()

    ca_item_dir = ca_dir / "Организация"
    ca_item_dir.mkdir()
    ca_xml = ca_item_dir / "Организация.xml"
    ca_xml.write_text(MOCK_COMMON_ATTRIBUTE_XML, encoding="utf-8")

    # Create Roles directory
    roles_dir = config_root / "Roles"
    roles_dir.mkdir()

    role_item_dir = roles_dir / "Администратор"
    role_item_dir.mkdir()
    role_xml = role_item_dir / "Администратор.xml"
    role_xml.write_text(MOCK_ROLE_XML, encoding="utf-8")

    # Create ExchangePlans directory
    ep_dir = config_root / "ExchangePlans"
    ep_dir.mkdir()

    ep_item_dir = ep_dir / "ОбменСФилиалами"
    ep_item_dir.mkdir()
    ep_xml = ep_item_dir / "ОбменСФилиалами.xml"
    ep_xml.write_text(MOCK_EXCHANGE_PLAN_XML, encoding="utf-8")

    # Create HTTPServices directory
    http_dir = config_root / "HTTPServices"
    http_dir.mkdir()

    http_item_dir = http_dir / "API"
    http_item_dir.mkdir()
    http_xml = http_item_dir / "API.xml"
    http_xml.write_text(MOCK_HTTP_SERVICE_XML, encoding="utf-8")

    return config_root


# Mock XML content
MOCK_CONFIGURATION_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
    <Configuration>
        <Name>ТестоваяКонфигурация</Name>
        <Synonym>
            <item lang="ru">Тестовая конфигурация</item>
        </Synonym>
        <Catalogs>
            <item>Товары</item>
            <item>Контрагенты</item>
        </Catalogs>
        <Documents>
            <item>ПриходТовара</item>
            <item>РасходТовара</item>
        </Documents>
        <CommonModules>
            <item>ОбщегоНазначения</item>
        </CommonModules>
        <Subsystems>
            <item>Торговля</item>
        </Subsystems>
        <InformationRegisters>
            <item>ЦеныТоваров</item>
        </InformationRegisters>
        <Constants>
            <item>ОсновнаяВалюта</item>
        </Constants>
        <FunctionalOptions>
            <item>ИспользоватьВалюты</item>
        </FunctionalOptions>
        <ScheduledJobs>
            <item>ОбновлениеКурсовВалют</item>
        </ScheduledJobs>
        <EventSubscriptions>
            <item>ПриЗаписиТоваров</item>
        </EventSubscriptions>
        <ExchangePlans>
            <item>ОбменСФилиалами</item>
        </ExchangePlans>
        <HTTPServices>
            <item>API</item>
        </HTTPServices>
        <DefinedTypes>
            <item>ВладелецТовара</item>
        </DefinedTypes>
        <CommonAttributes>
            <item>Организация</item>
        </CommonAttributes>
        <Roles>
            <item>Администратор</item>
        </Roles>
    </Configuration>
</MetaDataObject>
'''

MOCK_CATALOG_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
    <Catalog uuid="a1b2c3d4-e5f6-7890-abcd-ef1234567890">
        <Name>Товары</Name>
        <Synonym>
            <item lang="ru">Товары</item>
        </Synonym>
        <Comment>
            <item lang="ru">Справочник товаров</item>
        </Comment>
        <Attributes>
            <Attribute>
                <Name>Артикул</Name>
                <Synonym>
                    <item lang="ru">Артикул</item>
                </Synonym>
                <Type>String</Type>
                <Indexing>true</Indexing>
            </Attribute>
            <Attribute>
                <Name>ЕдиницаИзмерения</Name>
                <Synonym>
                    <item lang="ru">Единица измерения</item>
                </Synonym>
                <Type>CatalogRef.ЕдиницыИзмерения</Type>
            </Attribute>
        </Attributes>
        <TabularSections>
            <TabularSection>
                <Name>Штрихкоды</Name>
                <Synonym>
                    <item lang="ru">Штрихкоды</item>
                </Synonym>
                <Attributes>
                    <Attribute>
                        <Name>Штрихкод</Name>
                        <Type>String</Type>
                    </Attribute>
                </Attributes>
            </TabularSection>
        </TabularSections>
        <Forms>
            <item>ФормаЭлемента</item>
            <item>ФормаСписка</item>
        </Forms>
        <Templates>
            <item>ЭтикеткаТовара</item>
        </Templates>
    </Catalog>
</MetaDataObject>
'''

MOCK_DOCUMENT_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
    <Document uuid="b2c3d4e5-f6a7-8901-bcde-f12345678901">
        <Name>ПриходТовара</Name>
        <Synonym>
            <item lang="ru">Приход товара</item>
        </Synonym>
        <Posting>true</Posting>
        <RegisterRecords>
            <item>РегистрНакопления.ОстаткиТоваров</item>
        </RegisterRecords>
        <Attributes>
            <Attribute>
                <Name>Склад</Name>
                <Type>CatalogRef.Склады</Type>
            </Attribute>
        </Attributes>
        <TabularSections>
            <TabularSection>
                <Name>Товары</Name>
                <Attributes>
                    <Attribute>
                        <Name>Товар</Name>
                        <Type>CatalogRef.Товары</Type>
                    </Attribute>
                    <Attribute>
                        <Name>Количество</Name>
                        <Type>Number</Type>
                    </Attribute>
                </Attributes>
            </TabularSection>
        </TabularSections>
    </Document>
</MetaDataObject>
'''

MOCK_COMMON_MODULE_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
    <CommonModule uuid="c3d4e5f6-a7b8-9012-cdef-123456789012">
        <Name>ОбщегоНазначения</Name>
        <Synonym>
            <item lang="ru">Общего назначения</item>
        </Synonym>
        <Server>true</Server>
        <Global>false</Global>
    </CommonModule>
</MetaDataObject>
'''

MOCK_COMMON_MODULE_BSL = '''
#Область СлужебныйПрограммныйИнтерфейс

// Получает текущего пользователя
//
// Возвращаемое значение:
//   СправочникСсылка.Пользователи - текущий пользователь
//
&НаСервере
Функция ТекущийПользователь() Экспорт
    Возврат ПараметрыСеанса.ТекущийПользователь;
КонецФункции

// Проверяет право доступа
//
// Параметры:
//   Право - Строка - имя права
//   Объект - Произвольный - объект для проверки
//
// Возвращаемое значение:
//   Булево - результат проверки
//
&НаСервере
Функция ПравоДоступа(Знач Право, Знач Объект = Неопределено) Экспорт
    Если Объект = Неопределено Тогда
        Возврат ПравоДоступа(Право, Метаданные);
    КонецЕсли;
    Возврат Истина;
КонецФункции

#КонецОбласти

#Область СлужебныеПроцедуры

Процедура ЗаписатьВЖурнал(Сообщение)
    ЗаписьЖурналаРегистрации("Событие", УровеньЖурналаРегистрации.Информация, , , Сообщение);
КонецПроцедуры

#КонецОбласти
'''

MOCK_MODULE_BSL = '''
#Область ОбработчикиСобытий

Процедура ПередЗаписью(Отказ)
    // Проверка заполнения
    Если Не ЗначениеЗаполнено(Наименование) Тогда
        Сообщить("Не заполнено наименование");
        Отказ = Истина;
    КонецЕсли;
КонецПроцедуры

&НаКлиенте
Процедура ОбработкаВыбора(ВыбранноеЗначение, ИсточникВыбора)
    // Обработка выбора
КонецПроцедуры

#КонецОбласти

#Область СлужебныеПроцедуры

&НаСервере
Функция ПолучитьЦену(Дата = Неопределено) Экспорт
    Если Дата = Неопределено Тогда
        Дата = ТекущаяДата();
    КонецЕсли;

    Запрос = Новый Запрос;
    Запрос.Текст = "ВЫБРАТЬ Цена ИЗ РегистрСведений.ЦеныТоваров ГДЕ Товар = &Товар";
    Запрос.УстановитьПараметр("Товар", Ссылка);

    Результат = Запрос.Выполнить();
    Если Результат.Пустой() Тогда
        Возврат 0;
    КонецЕсли;

    Возврат Результат.Выгрузить()[0].Цена;
КонецФункции

#КонецОбласти
'''

MOCK_SUBSYSTEM_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
    <Subsystem uuid="d4e5f6a7-b8c9-0123-def0-234567890123">
        <Name>Торговля</Name>
        <Synonym>
            <item lang="ru">Торговля</item>
        </Synonym>
        <IncludeInCommandInterface>true</IncludeInCommandInterface>
        <Content>
            <item>Catalog.Товары</item>
            <item>Document.ПриходТовара</item>
        </Content>
    </Subsystem>
</MetaDataObject>
'''

MOCK_REGISTER_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
    <InformationRegister uuid="e5f6a7b8-c9d0-1234-ef01-345678901234">
        <Name>ЦеныТоваров</Name>
        <Synonym>
            <item lang="ru">Цены товаров</item>
        </Synonym>
        <Dimensions>
            <Dimension>
                <Name>Товар</Name>
                <Type>CatalogRef.Товары</Type>
            </Dimension>
            <Dimension>
                <Name>ТипЦены</Name>
                <Type>CatalogRef.ТипыЦен</Type>
            </Dimension>
        </Dimensions>
        <Resources>
            <Resource>
                <Name>Цена</Name>
                <Type>Number</Type>
            </Resource>
        </Resources>
    </InformationRegister>
</MetaDataObject>
'''

MOCK_CONSTANT_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
    <Constant uuid="f6a7b8c9-d0e1-2345-f012-456789012345">
        <Name>ОсновнаяВалюта</Name>
        <Synonym>
            <item lang="ru">Основная валюта</item>
        </Synonym>
        <Comment>
            <item lang="ru">Основная валюта учета</item>
        </Comment>
        <Type>CatalogRef.Валюты</Type>
    </Constant>
</MetaDataObject>
'''

MOCK_FUNCTIONAL_OPTION_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
    <FunctionalOption uuid="a7b8c9d0-e1f2-3456-0123-567890123456">
        <Name>ИспользоватьВалюты</Name>
        <Synonym>
            <item lang="ru">Использовать валюты</item>
        </Synonym>
        <Comment>
            <item lang="ru">Включает многовалютный учет</item>
        </Comment>
    </FunctionalOption>
</MetaDataObject>
'''

MOCK_SCHEDULED_JOB_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
    <ScheduledJob uuid="b8c9d0e1-f2a3-4567-1234-678901234567">
        <Name>ОбновлениеКурсовВалют</Name>
        <Synonym>
            <item lang="ru">Обновление курсов валют</item>
        </Synonym>
        <Comment>
            <item lang="ru">Ежедневное обновление курсов валют</item>
        </Comment>
        <MethodName>CommonModule.ОбщегоНазначения.ОбновлениеКурсовВалют</MethodName>
    </ScheduledJob>
</MetaDataObject>
'''

MOCK_EVENT_SUBSCRIPTION_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
    <EventSubscription uuid="c9d0e1f2-a3b4-5678-2345-789012345678">
        <Name>ПриЗаписиТоваров</Name>
        <Synonym>
            <item lang="ru">При записи товаров</item>
        </Synonym>
        <Comment>
            <item lang="ru">Обработка записи справочника товаров</item>
        </Comment>
        <Source>
            <Type>DocumentObject.ПриходТовара</Type>
        </Source>
        <Handler>CommonModule.ОбщегоНазначения.ОбработкаПриЗаписиТоваров</Handler>
    </EventSubscription>
</MetaDataObject>
'''

MOCK_EXCHANGE_PLAN_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
    <ExchangePlan uuid="d0e1f2a3-b4c5-6789-3456-890123456789">
        <Name>ОбменСФилиалами</Name>
        <Synonym>
            <item lang="ru">Обмен с филиалами</item>
        </Synonym>
        <Comment>
            <item lang="ru">План обмена с филиалами</item>
        </Comment>
        <Attributes>
            <Attribute>
                <Name>Организация</Name>
                <Synonym>
                    <item lang="ru">Организация</item>
                </Synonym>
                <Type>CatalogRef.Организации</Type>
            </Attribute>
        </Attributes>
    </ExchangePlan>
</MetaDataObject>
'''

MOCK_HTTP_SERVICE_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
    <HTTPService uuid="e1f2a3b4-c5d6-7890-4567-901234567890">
        <Name>API</Name>
        <Synonym>
            <item lang="ru">REST API</item>
        </Synonym>
        <Comment>
            <item lang="ru">REST API сервис</item>
        </Comment>
        <RootURL>api</RootURL>
    </HTTPService>
</MetaDataObject>
'''

MOCK_CATALOG_KONTRAGENTY_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
    <Catalog uuid="f1a2b3c4-d5e6-7890-abcd-ef0123456789">
        <Name>Контрагенты</Name>
        <Synonym>
            <item lang="ru">Контрагенты</item>
        </Synonym>
        <Comment>
            <item lang="ru">Справочник контрагентов</item>
        </Comment>
        <Attributes>
            <Attribute>
                <Name>ИНН</Name>
                <Synonym>
                    <item lang="ru">ИНН</item>
                </Synonym>
                <Type>String</Type>
            </Attribute>
            <Attribute>
                <Name>КПП</Name>
                <Synonym>
                    <item lang="ru">КПП</item>
                </Synonym>
                <Type>String</Type>
            </Attribute>
        </Attributes>
    </Catalog>
</MetaDataObject>
'''

MOCK_KONTRAGENTY_BSL = '''
#Область ОбработчикиСобытий

Процедура ПриЗаписи(Отказ)
    // Обработчик события при записи
    Если Не ЗначениеЗаполнено(Наименование) Тогда
        Отказ = Истина;
    КонецЕсли;
КонецПроцедуры

#КонецОбласти

#Область СлужебныеПроцедуры

// Вызывает процедуру из модуля Товары
Процедура ПолучитьИнформацию()
    Результат = Справочники.Товары.ПолучитьЦену();
КонецПроцедуры

// Эта процедура нигде не используется (мёртвый код)
Процедура НеиспользуемаяПроцедура()
    Сообщить("Это мёртвый код");
КонецПроцедуры

#КонецОбласти
'''

MOCK_DEFINED_TYPE_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
    <DefinedType uuid="a2b3c4d5-e6f7-8901-bcde-f01234567890">
        <Name>ВладелецТовара</Name>
        <Synonym>
            <item lang="ru">Владелец товара</item>
        </Synonym>
        <Comment>
            <item lang="ru">Составной тип - владелец товара</item>
        </Comment>
        <Type>СправочникСсылка.Товары, СправочникСсылка.Контрагенты</Type>
    </DefinedType>
</MetaDataObject>
'''

MOCK_COMMON_ATTRIBUTE_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
    <CommonAttribute uuid="b3c4d5e6-f7a8-9012-cdef-012345678901">
        <Name>Организация</Name>
        <Synonym>
            <item lang="ru">Организация</item>
        </Synonym>
        <Comment>
            <item lang="ru">Общий реквизит Организация</item>
        </Comment>
        <AutoUse>Use</AutoUse>
        <Content>
            <item>Catalog.Товары</item>
            <item>Document.ПриходТовара</item>
        </Content>
        <Type>CatalogRef.Организации</Type>
    </CommonAttribute>
</MetaDataObject>
'''

MOCK_ROLE_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
    <Role uuid="c4d5e6f7-a8b9-0123-def0-123456789012">
        <Name>Администратор</Name>
        <Properties>
            <Synonym>
                <v>Администратор</v>
            </Synonym>
        </Properties>
        <Rights>
            <Object path="Catalog.Товары">
                <Right>
                    <Name>Read</Name>
                    <Value>true</Value>
                </Right>
                <Right>
                    <Name>Update</Name>
                    <Value>true</Value>
                </Right>
                <Right>
                    <Name>Insert</Name>
                    <Value>true</Value>
                </Right>
                <Right>
                    <Name>Delete</Name>
                    <Value>true</Value>
                </Right>
                <Right>
                    <Name>RLS</Name>
                    <Value>true</Value>
                    <Template>ПоОрганизации</Template>
                </Right>
            </Object>
            <Object path="Document.ПриходТовара">
                <Right>
                    <Name>Read</Name>
                    <Value>true</Value>
                </Right>
                <Right>
                    <Name>Posting</Name>
                    <Value>true</Value>
                </Right>
            </Object>
        </Rights>
    </Role>
</MetaDataObject>
'''
