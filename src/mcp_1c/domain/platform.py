"""
Platform API domain models.

Models for representing 1C:Enterprise 8.3 platform API:
- Global context methods and properties
- Data types
- Object events
- Collection methods
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PlatformVersion(str, Enum):
    """Supported platform versions."""

    V8_3_20 = "8.3.20"
    V8_3_21 = "8.3.21"
    V8_3_22 = "8.3.22"
    V8_3_23 = "8.3.23"
    V8_3_24 = "8.3.24"
    V8_3_25 = "8.3.25"


class ExecutionContext(str, Enum):
    """Code execution context."""

    SERVER = "server"
    CLIENT = "client"
    EXTERNAL_CONNECTION = "external_connection"
    MOBILE_APP = "mobile_app"
    MOBILE_CLIENT = "mobile_client"
    THICK_CLIENT = "thick_client"
    THIN_CLIENT = "thin_client"
    WEB_CLIENT = "web_client"


class MethodCategory(str, Enum):
    """Method category in global context."""

    # Core
    COMMON = "common"  # Общие методы
    MATH = "math"  # Математические функции
    STRING = "string"  # Строковые функции
    DATE = "date"  # Функции даты и времени
    TYPE = "type"  # Функции работы с типами

    # Data
    QUERY = "query"  # Работа с запросами
    TRANSACTION = "transaction"  # Транзакции
    LOCK = "lock"  # Блокировки

    # Files
    FILE = "file"  # Файловые операции
    XML = "xml"  # XML операции
    JSON = "json"  # JSON операции

    # UI
    DIALOG = "dialog"  # Диалоги
    MESSAGE = "message"  # Сообщения
    NOTIFICATION = "notification"  # Уведомления

    # System
    SYSTEM = "system"  # Системные функции
    SESSION = "session"  # Параметры сеанса
    RIGHTS = "rights"  # Права доступа

    # Objects
    METADATA = "metadata"  # Работа с метаданными
    VALUE_STORAGE = "value_storage"  # Хранилище значений

    # Web
    HTTP = "http"  # HTTP операции
    WEB_SERVICES = "web_services"  # Web-сервисы

    # Other
    CRYPTO = "crypto"  # Криптография
    PRINT = "print"  # Печать
    BACKGROUND = "background"  # Фоновые задания


class TypeCategory(str, Enum):
    """Data type category."""

    PRIMITIVE = "primitive"  # Примитивные типы
    COLLECTION = "collection"  # Коллекции
    REFERENCE = "reference"  # Ссылочные типы
    VALUE_TABLE = "value_table"  # Таблица значений
    VALUE_TREE = "value_tree"  # Дерево значений
    STRUCTURE = "structure"  # Структуры
    QUERY = "query"  # Запросы
    FILE = "file"  # Файлы
    XML = "xml"  # XML
    JSON = "json"  # JSON
    HTTP = "http"  # HTTP
    FORM = "form"  # Формы
    DRAWING = "drawing"  # Рисование
    CRYPTO = "crypto"  # Криптография
    SYSTEM = "system"  # Системные
    OTHER = "other"  # Прочие


class EventCategory(str, Enum):
    """Event category."""

    OBJECT = "object"  # События объектов
    FORM = "form"  # События форм
    MODULE = "module"  # События модулей
    SESSION = "session"  # События сеанса
    SCHEDULED = "scheduled"  # Регламентные задания
    EXCHANGE = "exchange"  # Обмен данными


class ParameterDirection(str, Enum):
    """Parameter passing direction."""

    IN = "in"  # Входной параметр
    OUT = "out"  # Выходной параметр
    IN_OUT = "in_out"  # Входной/выходной


class MethodParameter(BaseModel):
    """Method parameter definition."""

    name: str = Field(..., description="Parameter name")
    name_en: str = Field(default="", description="Parameter name in English")

    description: str = Field(default="", description="Parameter description")
    description_en: str = Field(default="", description="Description in English")

    types: list[str] = Field(default_factory=list, description="Allowed types")
    default_value: Any = Field(default=None, description="Default value")

    required: bool = Field(default=True, description="Is parameter required")
    direction: ParameterDirection = Field(
        default=ParameterDirection.IN, description="Parameter direction"
    )

    # Extended info
    possible_values: list[str] = Field(
        default_factory=list, description="Possible values for enums"
    )


class PlatformMethod(BaseModel):
    """Platform method/function definition."""

    name: str = Field(..., description="Method name in Russian")
    name_en: str = Field(default="", description="Method name in English")

    description: str = Field(default="", description="Method description")
    description_en: str = Field(default="", description="Description in English")

    category: MethodCategory = Field(
        default=MethodCategory.COMMON, description="Method category"
    )

    # Signature
    parameters: list[MethodParameter] = Field(
        default_factory=list, description="Method parameters"
    )
    return_types: list[str] = Field(
        default_factory=list, description="Return value types"
    )
    return_description: str = Field(
        default="", description="Return value description"
    )

    # Execution context
    available_contexts: list[ExecutionContext] = Field(
        default_factory=list, description="Available execution contexts"
    )

    # Versioning
    since_version: str = Field(default="8.0", description="Available since version")
    deprecated_version: str | None = Field(
        default=None, description="Deprecated since version"
    )
    removed_version: str | None = Field(
        default=None, description="Removed in version"
    )

    # Examples
    examples: list[str] = Field(
        default_factory=list, description="Usage examples"
    )

    # Related
    related_methods: list[str] = Field(
        default_factory=list, description="Related method names"
    )
    related_types: list[str] = Field(
        default_factory=list, description="Related type names"
    )

    # Notes
    notes: list[str] = Field(default_factory=list, description="Additional notes")
    warnings: list[str] = Field(default_factory=list, description="Warnings")

    # Search keywords
    keywords: list[str] = Field(
        default_factory=list, description="Search keywords"
    )

    def get_signature(self, lang: str = "ru") -> str:
        """Get method signature string."""
        name = self.name if lang == "ru" else (self.name_en or self.name)
        params = []
        for p in self.parameters:
            p_name = p.name if lang == "ru" else (p.name_en or p.name)
            if p.required:
                params.append(p_name)
            else:
                params.append(f"[{p_name}]")
        return f"{name}({', '.join(params)})"


class PlatformProperty(BaseModel):
    """Platform property definition."""

    name: str = Field(..., description="Property name in Russian")
    name_en: str = Field(default="", description="Property name in English")

    description: str = Field(default="", description="Property description")
    description_en: str = Field(default="", description="Description in English")

    types: list[str] = Field(default_factory=list, description="Property types")

    readable: bool = Field(default=True, description="Can be read")
    writable: bool = Field(default=False, description="Can be written")

    available_contexts: list[ExecutionContext] = Field(
        default_factory=list, description="Available execution contexts"
    )

    since_version: str = Field(default="8.0", description="Available since version")


class PlatformType(BaseModel):
    """Platform data type definition."""

    name: str = Field(..., description="Type name in Russian")
    name_en: str = Field(default="", description="Type name in English")

    description: str = Field(default="", description="Type description")
    description_en: str = Field(default="", description="Description in English")

    category: TypeCategory = Field(
        default=TypeCategory.OTHER, description="Type category"
    )

    # Constructors
    constructors: list[PlatformMethod] = Field(
        default_factory=list, description="Type constructors"
    )

    # Members
    methods: list[PlatformMethod] = Field(
        default_factory=list, description="Type methods"
    )
    properties: list[PlatformProperty] = Field(
        default_factory=list, description="Type properties"
    )

    # Type hierarchy
    base_type: str | None = Field(default=None, description="Base type name")
    derived_types: list[str] = Field(
        default_factory=list, description="Derived type names"
    )

    # Interfaces
    implements: list[str] = Field(
        default_factory=list, description="Implemented interfaces"
    )

    # Context
    available_contexts: list[ExecutionContext] = Field(
        default_factory=list, description="Available execution contexts"
    )

    # Versioning
    since_version: str = Field(default="8.0", description="Available since version")

    # Examples
    examples: list[str] = Field(default_factory=list, description="Usage examples")

    # Related
    related_types: list[str] = Field(
        default_factory=list, description="Related type names"
    )

    # Search
    keywords: list[str] = Field(default_factory=list, description="Search keywords")

    def get_method(self, name: str) -> PlatformMethod | None:
        """Get method by name (case-insensitive)."""
        name_lower = name.lower()
        for m in self.methods:
            if m.name.lower() == name_lower or m.name_en.lower() == name_lower:
                return m
        return None

    def get_property(self, name: str) -> PlatformProperty | None:
        """Get property by name (case-insensitive)."""
        name_lower = name.lower()
        for p in self.properties:
            if p.name.lower() == name_lower or p.name_en.lower() == name_lower:
                return p
        return None


class ObjectEvent(BaseModel):
    """Object event definition."""

    name: str = Field(..., description="Event name in Russian")
    name_en: str = Field(default="", description="Event name in English")

    description: str = Field(default="", description="Event description")
    description_en: str = Field(default="", description="Description in English")

    category: EventCategory = Field(
        default=EventCategory.OBJECT, description="Event category"
    )

    # Applicable to
    object_types: list[str] = Field(
        default_factory=list, description="Object types that have this event"
    )

    # Handler signature
    parameters: list[MethodParameter] = Field(
        default_factory=list, description="Event handler parameters"
    )

    # Execution context
    execution_context: ExecutionContext = Field(
        default=ExecutionContext.SERVER, description="Event execution context"
    )

    # Behavior
    can_cancel: bool = Field(
        default=False, description="Can cancel the operation"
    )
    cancel_parameter: str | None = Field(
        default=None, description="Cancel parameter name"
    )

    # Order
    execution_order: int = Field(
        default=0, description="Typical execution order"
    )

    # Related events
    related_events: list[str] = Field(
        default_factory=list, description="Related event names"
    )

    # Examples
    examples: list[str] = Field(default_factory=list, description="Usage examples")

    # Notes
    notes: list[str] = Field(default_factory=list, description="Additional notes")

    # Versioning
    since_version: str = Field(default="8.0", description="Available since version")

    def get_handler_signature(self, lang: str = "ru") -> str:
        """Get event handler procedure signature."""
        name = self.name if lang == "ru" else (self.name_en or self.name)
        params = []
        for p in self.parameters:
            p_name = p.name if lang == "ru" else (p.name_en or p.name)
            params.append(p_name)
        return f"Процедура {name}({', '.join(params)})"


class GlobalContextSection(BaseModel):
    """Section of global context."""

    name: str = Field(..., description="Section name")
    name_en: str = Field(default="", description="Section name in English")

    description: str = Field(default="", description="Section description")

    methods: list[PlatformMethod] = Field(
        default_factory=list, description="Methods in this section"
    )

    properties: list[PlatformProperty] = Field(
        default_factory=list, description="Properties in this section"
    )


class GlobalContext(BaseModel):
    """Platform global context."""

    platform_version: str = Field(
        default="8.3.24", description="Platform version"
    )

    sections: list[GlobalContextSection] = Field(
        default_factory=list, description="Context sections"
    )

    # All methods (flat list for searching)
    all_methods: list[PlatformMethod] = Field(
        default_factory=list, description="All global methods"
    )

    # All properties (flat list)
    all_properties: list[PlatformProperty] = Field(
        default_factory=list, description="All global properties"
    )

    def get_method(self, name: str) -> PlatformMethod | None:
        """Get method by name (case-insensitive)."""
        name_lower = name.lower()
        for m in self.all_methods:
            if m.name.lower() == name_lower or m.name_en.lower() == name_lower:
                return m
        return None

    def search_methods(self, query: str) -> list[PlatformMethod]:
        """Search methods by name or keywords."""
        query_lower = query.lower()
        results = []
        for m in self.all_methods:
            if (
                query_lower in m.name.lower()
                or query_lower in m.name_en.lower()
                or query_lower in m.description.lower()
                or any(query_lower in kw.lower() for kw in m.keywords)
            ):
                results.append(m)
        return results


class PlatformKnowledgeBase(BaseModel):
    """Complete platform knowledge base."""

    version: str = Field(default="8.3.24", description="Platform version")

    global_context: GlobalContext = Field(
        default_factory=GlobalContext, description="Global context"
    )

    types: list[PlatformType] = Field(
        default_factory=list, description="All platform types"
    )

    events: list[ObjectEvent] = Field(
        default_factory=list, description="All object events"
    )

    # Quick access maps (built on load)
    _types_by_name: dict[str, PlatformType] = {}
    _events_by_name: dict[str, ObjectEvent] = {}

    class Config:
        """Pydantic config."""

        underscore_attrs_are_private = True

    def model_post_init(self, __context: Any) -> None:
        """Build lookup maps after initialization."""
        self._types_by_name = {}
        for t in self.types:
            self._types_by_name[t.name.lower()] = t
            if t.name_en:
                self._types_by_name[t.name_en.lower()] = t

        self._events_by_name = {}
        for e in self.events:
            self._events_by_name[e.name.lower()] = e
            if e.name_en:
                self._events_by_name[e.name_en.lower()] = e

    def get_type(self, name: str) -> PlatformType | None:
        """Get type by name (case-insensitive)."""
        return self._types_by_name.get(name.lower())

    def get_event(self, name: str) -> ObjectEvent | None:
        """Get event by name (case-insensitive)."""
        return self._events_by_name.get(name.lower())

    def search_types(self, query: str) -> list[PlatformType]:
        """Search types by name or keywords."""
        query_lower = query.lower()
        results = []
        for t in self.types:
            if (
                query_lower in t.name.lower()
                or query_lower in t.name_en.lower()
                or query_lower in t.description.lower()
                or any(query_lower in kw.lower() for kw in t.keywords)
            ):
                results.append(t)
        return results

    def search_events(self, query: str) -> list[ObjectEvent]:
        """Search events by name or object type."""
        query_lower = query.lower()
        results = []
        for e in self.events:
            if (
                query_lower in e.name.lower()
                or query_lower in e.name_en.lower()
                or query_lower in e.description.lower()
                or any(query_lower in ot.lower() for ot in e.object_types)
            ):
                results.append(e)
        return results

    def get_events_for_object(self, object_type: str) -> list[ObjectEvent]:
        """Get all events for a specific object type."""
        object_type_lower = object_type.lower()
        return [
            e for e in self.events
            if any(object_type_lower in ot.lower() for ot in e.object_types)
        ]
