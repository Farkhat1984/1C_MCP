"""
Metadata domain models.

Represents 1C:Enterprise configuration metadata objects.
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MetadataType(str, Enum):
    """Types of 1C metadata objects."""

    # Basic objects
    CATALOG = "Catalog"
    DOCUMENT = "Document"
    ENUM = "Enum"
    CHART_OF_CHARACTERISTIC_TYPES = "ChartOfCharacteristicTypes"
    CHART_OF_ACCOUNTS = "ChartOfAccounts"
    CHART_OF_CALCULATION_TYPES = "ChartOfCalculationTypes"
    EXCHANGE_PLAN = "ExchangePlan"
    BUSINESS_PROCESS = "BusinessProcess"
    TASK = "Task"

    # Registers
    INFORMATION_REGISTER = "InformationRegister"
    ACCUMULATION_REGISTER = "AccumulationRegister"
    ACCOUNTING_REGISTER = "AccountingRegister"
    CALCULATION_REGISTER = "CalculationRegister"

    # Other
    REPORT = "Report"
    DATA_PROCESSOR = "DataProcessor"
    CONSTANT = "Constant"
    SEQUENCE = "Sequence"

    # Service objects
    COMMON_MODULE = "CommonModule"
    SESSION_PARAMETER = "SessionParameter"
    ROLE = "Role"
    COMMON_FORM = "CommonForm"
    COMMON_TEMPLATE = "CommonTemplate"
    COMMON_COMMAND = "CommonCommand"
    COMMAND_GROUP = "CommandGroup"
    COMMON_PICTURE = "CommonPicture"
    STYLE_ITEM = "StyleItem"
    STYLE = "Style"
    LANGUAGE = "Language"
    SUBSYSTEM = "Subsystem"
    FUNCTIONAL_OPTION = "FunctionalOption"
    FUNCTIONAL_OPTIONS_PARAMETER = "FunctionalOptionsParameter"
    DEFINED_TYPE = "DefinedType"
    COMMON_ATTRIBUTE = "CommonAttribute"
    EVENT_SUBSCRIPTION = "EventSubscription"
    SCHEDULED_JOB = "ScheduledJob"

    # Web services
    WEB_SERVICE = "WebService"
    HTTP_SERVICE = "HTTPService"
    WS_REFERENCE = "WSReference"

    # Configuration
    CONFIGURATION = "Configuration"

    @classmethod
    def from_russian(cls, name: str) -> "MetadataType | None":
        """Convert Russian name to MetadataType."""
        mapping = {
            "Справочник": cls.CATALOG,
            "Справочники": cls.CATALOG,
            "Документ": cls.DOCUMENT,
            "Документы": cls.DOCUMENT,
            "Перечисление": cls.ENUM,
            "Перечисления": cls.ENUM,
            "ПланВидовХарактеристик": cls.CHART_OF_CHARACTERISTIC_TYPES,
            "ПланыВидовХарактеристик": cls.CHART_OF_CHARACTERISTIC_TYPES,
            "ПланСчетов": cls.CHART_OF_ACCOUNTS,
            "ПланыСчетов": cls.CHART_OF_ACCOUNTS,
            "ПланВидовРасчета": cls.CHART_OF_CALCULATION_TYPES,
            "ПланыВидовРасчета": cls.CHART_OF_CALCULATION_TYPES,
            "ПланОбмена": cls.EXCHANGE_PLAN,
            "ПланыОбмена": cls.EXCHANGE_PLAN,
            "БизнесПроцесс": cls.BUSINESS_PROCESS,
            "БизнесПроцессы": cls.BUSINESS_PROCESS,
            "Задача": cls.TASK,
            "Задачи": cls.TASK,
            "РегистрСведений": cls.INFORMATION_REGISTER,
            "РегистрыСведений": cls.INFORMATION_REGISTER,
            "РегистрНакопления": cls.ACCUMULATION_REGISTER,
            "РегистрыНакопления": cls.ACCUMULATION_REGISTER,
            "РегистрБухгалтерии": cls.ACCOUNTING_REGISTER,
            "РегистрыБухгалтерии": cls.ACCOUNTING_REGISTER,
            "РегистрРасчета": cls.CALCULATION_REGISTER,
            "РегистрыРасчета": cls.CALCULATION_REGISTER,
            "Отчет": cls.REPORT,
            "Отчеты": cls.REPORT,
            "Обработка": cls.DATA_PROCESSOR,
            "Обработки": cls.DATA_PROCESSOR,
            "Константа": cls.CONSTANT,
            "Константы": cls.CONSTANT,
            "Последовательность": cls.SEQUENCE,
            "Последовательности": cls.SEQUENCE,
            "ОбщийМодуль": cls.COMMON_MODULE,
            "ОбщиеМодули": cls.COMMON_MODULE,
            "ПараметрСеанса": cls.SESSION_PARAMETER,
            "ПараметрыСеанса": cls.SESSION_PARAMETER,
            "Роль": cls.ROLE,
            "Роли": cls.ROLE,
            "ОбщаяФорма": cls.COMMON_FORM,
            "ОбщиеФормы": cls.COMMON_FORM,
            "ОбщийМакет": cls.COMMON_TEMPLATE,
            "ОбщиеМакеты": cls.COMMON_TEMPLATE,
            "ОбщаяКоманда": cls.COMMON_COMMAND,
            "ОбщиеКоманды": cls.COMMON_COMMAND,
            "ГруппаКоманд": cls.COMMAND_GROUP,
            "ГруппыКоманд": cls.COMMAND_GROUP,
            "ОбщаяКартинка": cls.COMMON_PICTURE,
            "ОбщиеКартинки": cls.COMMON_PICTURE,
            "ЭлементСтиля": cls.STYLE_ITEM,
            "ЭлементыСтиля": cls.STYLE_ITEM,
            "Стиль": cls.STYLE,
            "Стили": cls.STYLE,
            "Язык": cls.LANGUAGE,
            "Языки": cls.LANGUAGE,
            "Подсистема": cls.SUBSYSTEM,
            "Подсистемы": cls.SUBSYSTEM,
            "ФункциональнаяОпция": cls.FUNCTIONAL_OPTION,
            "ФункциональныеОпции": cls.FUNCTIONAL_OPTION,
            "ПараметрФункциональныхОпций": cls.FUNCTIONAL_OPTIONS_PARAMETER,
            "ПараметрыФункциональныхОпций": cls.FUNCTIONAL_OPTIONS_PARAMETER,
            "ОпределяемыйТип": cls.DEFINED_TYPE,
            "ОпределяемыеТипы": cls.DEFINED_TYPE,
            "ОбщийРеквизит": cls.COMMON_ATTRIBUTE,
            "ОбщиеРеквизиты": cls.COMMON_ATTRIBUTE,
            "ПодпискаНаСобытие": cls.EVENT_SUBSCRIPTION,
            "ПодпискиНаСобытия": cls.EVENT_SUBSCRIPTION,
            "РегламентноеЗадание": cls.SCHEDULED_JOB,
            "РегламентныеЗадания": cls.SCHEDULED_JOB,
            "WebСервис": cls.WEB_SERVICE,
            "WebСервисы": cls.WEB_SERVICE,
            "HTTPСервис": cls.HTTP_SERVICE,
            "HTTPСервисы": cls.HTTP_SERVICE,
            "WSСсылка": cls.WS_REFERENCE,
            "WSСсылки": cls.WS_REFERENCE,
            "Конфигурация": cls.CONFIGURATION,
        }
        return mapping.get(name)

    def to_russian(self, plural: bool = False) -> str:
        """Convert to Russian name."""
        singular_map = {
            self.CATALOG: "Справочник",
            self.DOCUMENT: "Документ",
            self.ENUM: "Перечисление",
            self.CHART_OF_CHARACTERISTIC_TYPES: "ПланВидовХарактеристик",
            self.CHART_OF_ACCOUNTS: "ПланСчетов",
            self.CHART_OF_CALCULATION_TYPES: "ПланВидовРасчета",
            self.EXCHANGE_PLAN: "ПланОбмена",
            self.BUSINESS_PROCESS: "БизнесПроцесс",
            self.TASK: "Задача",
            self.INFORMATION_REGISTER: "РегистрСведений",
            self.ACCUMULATION_REGISTER: "РегистрНакопления",
            self.ACCOUNTING_REGISTER: "РегистрБухгалтерии",
            self.CALCULATION_REGISTER: "РегистрРасчета",
            self.REPORT: "Отчет",
            self.DATA_PROCESSOR: "Обработка",
            self.CONSTANT: "Константа",
            self.COMMON_MODULE: "ОбщийМодуль",
            self.SUBSYSTEM: "Подсистема",
        }
        plural_map = {
            self.CATALOG: "Справочники",
            self.DOCUMENT: "Документы",
            self.ENUM: "Перечисления",
            self.CHART_OF_CHARACTERISTIC_TYPES: "ПланыВидовХарактеристик",
            self.CHART_OF_ACCOUNTS: "ПланыСчетов",
            self.CHART_OF_CALCULATION_TYPES: "ПланыВидовРасчета",
            self.EXCHANGE_PLAN: "ПланыОбмена",
            self.BUSINESS_PROCESS: "БизнесПроцессы",
            self.TASK: "Задачи",
            self.INFORMATION_REGISTER: "РегистрыСведений",
            self.ACCUMULATION_REGISTER: "РегистрыНакопления",
            self.ACCOUNTING_REGISTER: "РегистрыБухгалтерии",
            self.CALCULATION_REGISTER: "РегистрыРасчета",
            self.REPORT: "Отчеты",
            self.DATA_PROCESSOR: "Обработки",
            self.CONSTANT: "Константы",
            self.COMMON_MODULE: "ОбщиеМодули",
            self.SUBSYSTEM: "Подсистемы",
        }
        if plural:
            return plural_map.get(self, self.value)
        return singular_map.get(self, self.value)


class ModuleType(str, Enum):
    """Types of 1C modules."""

    OBJECT_MODULE = "ObjectModule"
    MANAGER_MODULE = "ManagerModule"
    FORM_MODULE = "FormModule"
    COMMAND_MODULE = "CommandModule"
    RECORDSET_MODULE = "RecordSetModule"
    VALUE_MANAGER_MODULE = "ValueManagerModule"
    SESSION_MODULE = "SessionModule"
    EXTERNAL_CONNECTION_MODULE = "ExternalConnectionModule"
    MANAGED_APPLICATION_MODULE = "ManagedApplicationModule"
    ORDINARY_APPLICATION_MODULE = "OrdinaryApplicationModule"
    COMMON_MODULE = "CommonModule"


class Attribute(BaseModel):
    """Attribute (requisite) of a metadata object."""

    name: str = Field(..., description="Attribute name")
    synonym: str = Field(default="", description="Display name")
    type: str = Field(default="String", description="Data type")
    type_description: dict[str, Any] = Field(
        default_factory=dict,
        description="Extended type description",
    )
    comment: str = Field(default="", description="Comment")
    indexed: bool = Field(default=False, description="Is indexed")
    fill_checking: str = Field(default="", description="Fill checking mode")


class TabularSection(BaseModel):
    """Tabular section of a metadata object."""

    name: str = Field(..., description="Tabular section name")
    synonym: str = Field(default="", description="Display name")
    attributes: list[Attribute] = Field(
        default_factory=list,
        description="Tabular section attributes",
    )
    comment: str = Field(default="", description="Comment")


class Form(BaseModel):
    """Form of a metadata object."""

    name: str = Field(..., description="Form name")
    synonym: str = Field(default="", description="Display name")
    form_type: str = Field(default="Managed", description="Form type")
    is_main: bool = Field(default=False, description="Is main form")
    purpose: str = Field(default="", description="Form purpose")


class Template(BaseModel):
    """Template (layout) of a metadata object."""

    name: str = Field(..., description="Template name")
    synonym: str = Field(default="", description="Display name")
    template_type: str = Field(
        default="SpreadsheetDocument",
        description="Template type",
    )


class Module(BaseModel):
    """Module of a metadata object."""

    module_type: ModuleType = Field(..., description="Module type")
    path: Path = Field(..., description="Path to .bsl file")
    exists: bool = Field(default=True, description="File exists")


class Subsystem(BaseModel):
    """Subsystem metadata object."""

    name: str = Field(..., description="Subsystem name")
    synonym: str = Field(default="", description="Display name")
    parent: str | None = Field(default=None, description="Parent subsystem")
    children: list[str] = Field(
        default_factory=list,
        description="Child subsystem names",
    )
    content: list[str] = Field(
        default_factory=list,
        description="Objects in subsystem",
    )
    include_in_command_interface: bool = Field(
        default=True,
        description="Include in command interface",
    )


class MetadataObject(BaseModel):
    """
    Base metadata object model.

    Represents any 1C configuration object (Catalog, Document, etc.).
    """

    uuid: str = Field(default="", description="Object UUID")
    name: str = Field(..., description="Object name")
    synonym: str = Field(default="", description="Display name (synonym)")
    comment: str = Field(default="", description="Comment")
    metadata_type: MetadataType = Field(..., description="Type of metadata")

    # Path information
    config_path: Path = Field(..., description="Path to configuration root")
    object_path: Path = Field(..., description="Path to object directory")

    # Structural elements
    attributes: list[Attribute] = Field(
        default_factory=list,
        description="Object attributes",
    )
    tabular_sections: list[TabularSection] = Field(
        default_factory=list,
        description="Tabular sections",
    )
    forms: list[Form] = Field(default_factory=list, description="Forms")
    templates: list[Template] = Field(
        default_factory=list,
        description="Templates (layouts)",
    )
    modules: list[Module] = Field(default_factory=list, description="Modules")

    # Relations
    subsystems: list[str] = Field(
        default_factory=list,
        description="Subsystems containing this object",
    )
    based_on: list[str] = Field(
        default_factory=list,
        description="Objects this is based on",
    )
    produces_documents: list[str] = Field(
        default_factory=list,
        description="Documents produced by this object",
    )

    # Document-specific
    register_records: list[str] = Field(
        default_factory=list,
        description="Registers this document writes to",
    )
    posting: bool = Field(default=False, description="Is posted document")

    # Register-specific
    dimensions: list[Attribute] = Field(
        default_factory=list,
        description="Register dimensions",
    )
    resources: list[Attribute] = Field(
        default_factory=list,
        description="Register resources",
    )

    # Indexing metadata
    indexed_at: datetime | None = Field(
        default=None,
        description="When object was indexed",
    )
    file_hash: str = Field(default="", description="Hash of XML file")

    @property
    def full_name(self) -> str:
        """Get full object name like 'Catalog.Products'."""
        return f"{self.metadata_type.value}.{self.name}"

    @property
    def full_name_ru(self) -> str:
        """Get full object name in Russian like 'Справочник.Товары'."""
        return f"{self.metadata_type.to_russian()}.{self.name}"

    def get_module_path(self, module_type: ModuleType) -> Path | None:
        """Get path to specific module type."""
        for module in self.modules:
            if module.module_type == module_type:
                return module.path
        return None

    model_config = ConfigDict(use_enum_values=False)
