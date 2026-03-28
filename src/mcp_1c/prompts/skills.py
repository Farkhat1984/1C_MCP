"""
Skills (prompts) for 1C development tasks.

Each skill provides a predefined prompt for common 1C development operations.
"""

from typing import ClassVar

from mcp.types import PromptArgument, PromptMessage

from mcp_1c.prompts.base import BasePrompt
from mcp_1c.tools.constants import ToolNames as T


class QuerySkill(BasePrompt):
    """
    Skill for generating 1C queries.

    Usage: /1c-query
    Helps generate SELECT queries for 1C metadata objects.
    """

    name: ClassVar[str] = "1c-query"
    description: ClassVar[str] = (
        "Генерация запросов 1С. "
        "Помогает создать SELECT запрос для работы с метаданными конфигурации."
    )
    arguments: ClassVar[list[PromptArgument]] = [
        PromptArgument(
            name="object",
            description="Имя объекта метаданных (например: Справочник.Номенклатура)",
            required=True,
        ),
        PromptArgument(
            name="fields",
            description="Поля для выборки через запятую (опционально)",
            required=False,
        ),
        PromptArgument(
            name="conditions",
            description="Условия отбора (опционально)",
            required=False,
        ),
    ]

    async def generate_messages(
        self, arguments: dict[str, str]
    ) -> list[PromptMessage]:
        obj = arguments.get("object", "")
        fields = arguments.get("fields", "")
        conditions = arguments.get("conditions", "")

        prompt = f"""Сгенерируй запрос 1С для объекта: {obj}

Требования:
1. Используй инструмент `{T.METADATA_GET}` для получения информации об объекте {obj}
2. Используй инструмент `{T.METADATA_ATTRIBUTES}` для получения списка реквизитов
3. На основе полученных данных сгенерируй запрос

Параметры запроса:
- Объект: {obj}
- Поля: {fields if fields else "все основные поля"}
- Условия: {conditions if conditions else "без условий"}

Используй инструмент `{T.GENERATE_QUERY}` для генерации финального запроса с правильным синтаксисом 1С.
После генерации используй `{T.QUERY_VALIDATE}` для проверки корректности запроса."""

        return [self.create_user_message(prompt)]


class MetadataSkill(BasePrompt):
    """
    Skill for getting metadata information.

    Usage: /1c-metadata
    Provides comprehensive information about 1C metadata objects.
    """

    name: ClassVar[str] = "1c-metadata"
    description: ClassVar[str] = (
        "Информация об объекте метаданных 1С. "
        "Выводит полную информацию о справочнике, документе или другом объекте."
    )
    arguments: ClassVar[list[PromptArgument]] = [
        PromptArgument(
            name="object",
            description="Имя объекта метаданных (например: Документ.РеализацияТоваров)",
            required=True,
        ),
    ]

    async def generate_messages(
        self, arguments: dict[str, str]
    ) -> list[PromptMessage]:
        obj = arguments.get("object", "")

        prompt = f"""Получи полную информацию об объекте метаданных: {obj}

Выполни следующие шаги:
1. Используй `{T.METADATA_GET}` для получения базовой информации об объекте
2. Используй `{T.METADATA_ATTRIBUTES}` для получения списка реквизитов
3. Используй `{T.METADATA_FORMS}` для получения списка форм
4. Используй `{T.METADATA_TEMPLATES}` для получения списка макетов
5. Если это документ, используй `{T.METADATA_REGISTERS}` для получения регистров движений
6. Используй `{T.METADATA_REFERENCES}` для получения связей с другими объектами

Выведи структурированную информацию:
- Имя и синоним
- Тип объекта
- Реквизиты (имя, тип, синоним)
- Табличные части и их реквизиты
- Формы
- Макеты
- Связи"""

        return [self.create_user_message(prompt)]


class HandlerSkill(BasePrompt):
    """
    Skill for generating event handlers.

    Usage: /1c-handler
    Generates event handler code for 1C objects.
    """

    name: ClassVar[str] = "1c-handler"
    description: ClassVar[str] = (
        "Генерация обработчиков событий 1С. "
        "Создаёт код обработчика для события объекта метаданных."
    )
    arguments: ClassVar[list[PromptArgument]] = [
        PromptArgument(
            name="object",
            description="Имя объекта метаданных",
            required=True,
        ),
        PromptArgument(
            name="event",
            description="Имя события (ПриЗаписи, ПередЗаписью, ОбработкаЗаполнения и др.)",
            required=True,
        ),
        PromptArgument(
            name="description",
            description="Описание логики обработчика",
            required=False,
        ),
    ]

    async def generate_messages(
        self, arguments: dict[str, str]
    ) -> list[PromptMessage]:
        obj = arguments.get("object", "")
        event = arguments.get("event", "")
        description = arguments.get("description", "")

        prompt = f"""Сгенерируй обработчик события для объекта 1С.

Параметры:
- Объект: {obj}
- Событие: {event}
- Логика: {description if description else "стандартная обработка"}

Выполни следующие шаги:
1. Используй `{T.PLATFORM_EVENT}` для получения информации о событии {event}
2. Используй `{T.METADATA_GET}` для получения информации об объекте {obj}
3. Используй `{T.METADATA_ATTRIBUTES}` для получения реквизитов объекта
4. Используй `{T.GENERATE_HANDLER}` для генерации кода обработчика

Обработчик должен:
- Иметь правильную сигнатуру для события
- Содержать комментарии с описанием
- Использовать правильные имена реквизитов объекта"""

        return [self.create_user_message(prompt)]


class PrintSkill(BasePrompt):
    """
    Skill for generating print forms.

    Usage: /1c-print
    Generates print form code for 1C documents.
    """

    name: ClassVar[str] = "1c-print"
    description: ClassVar[str] = (
        "Генерация печатной формы 1С. "
        "Создаёт код печатной формы для документа или справочника."
    )
    arguments: ClassVar[list[PromptArgument]] = [
        PromptArgument(
            name="object",
            description="Имя объекта метаданных (документ или справочник)",
            required=True,
        ),
        PromptArgument(
            name="template",
            description="Имя макета печатной формы (если есть)",
            required=False,
        ),
        PromptArgument(
            name="description",
            description="Описание содержимого печатной формы",
            required=False,
        ),
    ]

    async def generate_messages(
        self, arguments: dict[str, str]
    ) -> list[PromptMessage]:
        obj = arguments.get("object", "")
        template = arguments.get("template", "")
        description = arguments.get("description", "")

        prompt = f"""Сгенерируй печатную форму для объекта 1С.

Параметры:
- Объект: {obj}
- Макет: {template if template else "создать новый"}
- Описание: {description if description else "стандартная печатная форма"}

Выполни следующие шаги:
1. Используй `{T.METADATA_GET}` для получения информации об объекте {obj}
2. Используй `{T.METADATA_ATTRIBUTES}` для получения реквизитов
3. Используй `{T.METADATA_TEMPLATES}` для получения существующих макетов
4. Если указан макет, используй `{T.TEMPLATE_GET}` и `{T.TEMPLATE_PARAMETERS}` для анализа
5. Используй `{T.GENERATE_PRINT}` для генерации кода печатной формы

Печатная форма должна включать:
- Процедуру Печать() с параметром МассивОбъектов
- Формирование табличного документа
- Заполнение параметров из данных объекта
- Вывод табличного документа"""

        return [self.create_user_message(prompt)]


class UsagesSkill(BasePrompt):
    """
    Skill for finding code usages.

    Usage: /1c-usages
    Finds all usages of a procedure, function, or variable.
    """

    name: ClassVar[str] = "1c-usages"
    description: ClassVar[str] = (
        "Поиск использований в коде 1С. "
        "Находит все места использования процедуры, функции или переменной."
    )
    arguments: ClassVar[list[PromptArgument]] = [
        PromptArgument(
            name="name",
            description="Имя процедуры, функции или переменной для поиска",
            required=True,
        ),
        PromptArgument(
            name="scope",
            description="Область поиска: all, module, object (по умолчанию: all)",
            required=False,
        ),
    ]

    async def generate_messages(
        self, arguments: dict[str, str]
    ) -> list[PromptMessage]:
        name = arguments.get("name", "")
        scope = arguments.get("scope", "all")

        prompt = f"""Найди все использования: {name}

Параметры:
- Имя: {name}
- Область поиска: {scope}

Выполни следующие шаги:
1. Используй `{T.CODE_USAGES}` для поиска всех использований идентификатора "{name}"
2. Используй `{T.CODE_RESOLVE}` для нахождения определения
3. Для каждого найденного использования:
   - Укажи файл и номер строки
   - Покажи контекст (несколько строк вокруг)
   - Определи тип использования (вызов, присваивание, параметр)

Выведи структурированный отчёт:
- Определение (где объявлено)
- Список использований с контекстом
- Общее количество использований"""

        return [self.create_user_message(prompt)]


class ValidateSkill(BasePrompt):
    """
    Skill for validating 1C code.

    Usage: /1c-validate
    Validates BSL code syntax and reports errors.
    """

    name: ClassVar[str] = "1c-validate"
    description: ClassVar[str] = (
        "Проверка синтаксиса кода 1С. "
        "Валидирует код модуля и выводит найденные ошибки."
    )
    arguments: ClassVar[list[PromptArgument]] = [
        PromptArgument(
            name="module",
            description="Путь к модулю или имя объекта.модуль",
            required=True,
        ),
    ]

    async def generate_messages(
        self, arguments: dict[str, str]
    ) -> list[PromptMessage]:
        module = arguments.get("module", "")

        prompt = f"""Проверь синтаксис кода модуля: {module}

Выполни следующие шаги:
1. Используй `{T.CODE_MODULE}` для получения кода модуля {module}
2. Используй `{T.CODE_VALIDATE}` для синтаксической проверки
3. Используй `{T.CODE_LINT}` для статического анализа

Выведи отчёт:
- Синтаксические ошибки (строка, описание)
- Предупреждения линтера
- Рекомендации по улучшению кода

Если ошибок нет, сообщи что код валиден."""

        return [self.create_user_message(prompt)]


class DepsSkill(BasePrompt):
    """
    Skill for analyzing code dependencies.

    Usage: /1c-deps
    Builds and displays dependency graph for code.
    """

    name: ClassVar[str] = "1c-deps"
    description: ClassVar[str] = (
        "Анализ зависимостей кода 1С. "
        "Строит граф зависимостей для модуля или процедуры."
    )
    arguments: ClassVar[list[PromptArgument]] = [
        PromptArgument(
            name="module",
            description="Путь к модулю или имя объекта.модуль",
            required=True,
        ),
        PromptArgument(
            name="depth",
            description="Глубина анализа (по умолчанию: 2)",
            required=False,
        ),
    ]

    async def generate_messages(
        self, arguments: dict[str, str]
    ) -> list[PromptMessage]:
        module = arguments.get("module", "")
        depth = arguments.get("depth", "2")

        prompt = f"""Построй граф зависимостей для модуля: {module}

Параметры:
- Модуль: {module}
- Глубина: {depth}

Выполни следующие шаги:
1. Используй `{T.CODE_DEPENDENCIES}` для получения зависимостей модуля
2. Используй `{T.CODE_CALLGRAPH}` для построения графа вызовов
3. Используй `{T.CODE_ANALYZE}` для расширенного анализа

Выведи:
- Список зависимостей (какие модули/процедуры использует)
- Список зависимых (кто использует этот модуль)
- Граф вызовов в текстовом виде
- Циклические зависимости (если есть)"""

        return [self.create_user_message(prompt)]


class MovementSkill(BasePrompt):
    """
    Skill for generating register movements.

    Usage: /1c-movement
    Generates register movement code for documents.
    """

    name: ClassVar[str] = "1c-movement"
    description: ClassVar[str] = (
        "Генерация движений по регистрам 1С. "
        "Создаёт код формирования движений документа по регистрам."
    )
    arguments: ClassVar[list[PromptArgument]] = [
        PromptArgument(
            name="document",
            description="Имя документа",
            required=True,
        ),
        PromptArgument(
            name="register",
            description="Имя регистра (опционально, если не указан - все регистры)",
            required=False,
        ),
    ]

    async def generate_messages(
        self, arguments: dict[str, str]
    ) -> list[PromptMessage]:
        document = arguments.get("document", "")
        register = arguments.get("register", "")

        prompt = f"""Сгенерируй код движений по регистрам для документа: {document}

Параметры:
- Документ: {document}
- Регистр: {register if register else "все связанные регистры"}

Выполни следующие шаги:
1. Используй `{T.METADATA_GET}` для получения информации о документе {document}
2. Используй `{T.METADATA_REGISTERS}` для получения регистров движений
3. Для каждого регистра получи структуру через `{T.METADATA_GET}`
4. Используй `{T.GENERATE_MOVEMENT}` для генерации кода движений

Код должен включать:
- Процедуру ОбработкаПроведения
- Очистку движений
- Формирование записей регистра из данных документа
- Обработку табличных частей"""

        return [self.create_user_message(prompt)]


class FormatSkill(BasePrompt):
    """
    Skill for formatting 1C code.

    Usage: /1c-format
    Formats BSL code according to standards.
    """

    name: ClassVar[str] = "1c-format"
    description: ClassVar[str] = (
        "Форматирование кода 1С. "
        "Приводит код модуля к стандартам оформления."
    )
    arguments: ClassVar[list[PromptArgument]] = [
        PromptArgument(
            name="module",
            description="Путь к модулю или имя объекта.модуль",
            required=True,
        ),
    ]

    async def generate_messages(
        self, arguments: dict[str, str]
    ) -> list[PromptMessage]:
        module = arguments.get("module", "")

        prompt = f"""Отформатируй код модуля: {module}

Выполни следующие шаги:
1. Используй `{T.CODE_MODULE}` для получения текущего кода
2. Используй `{T.CODE_FORMAT}` для форматирования кода
3. Покажи различия между исходным и отформатированным кодом

Форматирование включает:
- Правильные отступы (табуляция)
- Пустые строки между процедурами
- Выравнивание операторов
- Правильное оформление комментариев"""

        return [self.create_user_message(prompt)]


class ExplainSkill(BasePrompt):
    """
    Skill for explaining 1C code.

    Usage: /1c-explain
    Provides detailed explanation of 1C code.
    """

    name: ClassVar[str] = "1c-explain"
    description: ClassVar[str] = (
        "Объяснение кода 1С. "
        "Анализирует и подробно объясняет что делает код."
    )
    arguments: ClassVar[list[PromptArgument]] = [
        PromptArgument(
            name="module",
            description="Путь к модулю или имя объекта.модуль",
            required=True,
        ),
        PromptArgument(
            name="procedure",
            description="Имя процедуры/функции для объяснения (опционально)",
            required=False,
        ),
    ]

    async def generate_messages(
        self, arguments: dict[str, str]
    ) -> list[PromptMessage]:
        module = arguments.get("module", "")
        procedure = arguments.get("procedure", "")

        target = f"{module}.{procedure}" if procedure else module

        prompt = f"""Объясни код: {target}

Выполни следующие шаги:
1. Используй `{T.CODE_MODULE}` для получения кода модуля {module}
2. {"Используй `" + T.CODE_PROCEDURE + "` для получения кода процедуры " + procedure if procedure else "Проанализируй весь модуль"}
3. Используй `{T.CODE_ANALYZE}` для получения структуры кода
4. Используй `{T.CODE_COMPLEXITY}` для оценки сложности

Объясни:
- Общее назначение кода
- Логику работы пошагово
- Используемые объекты метаданных
- Вызываемые процедуры и их назначение
- Потенциальные проблемы или улучшения"""

        return [self.create_user_message(prompt)]
