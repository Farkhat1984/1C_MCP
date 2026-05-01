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

Параметры запроса:
- Объект: {obj}
- Поля: {fields if fields else "все основные поля"}
- Условия: {conditions if conditions else "без условий"}

План:
1. Используй `{T.METADATA_GET}` для получения информации об объекте {obj} вместе с реквизитами и табличными частями.
2. Сгенерируй запрос:
   - Если объект известен и нужен «умный» запрос с учётом метаданных — используй `{T.SMART_QUERY}`.
   - Если нужен запрос по шаблону (срез последних, остатки, обороты, JOIN, GROUP BY) — используй `{T.GENERATE_QUERY}` с подходящим `template_id`.
3. Проверь корректность запроса через `{T.QUERY_VALIDATE}`.
4. По возможности предложи оптимизации через `{T.QUERY_OPTIMIZE}`."""

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
1. Используй `{T.METADATA_GET}` — он вернёт реквизиты, табличные части, формы, макеты, регистры (для документов) и связи в одном ответе.
2. Если нужно посмотреть граф связей с другими объектами, используй `{T.GRAPH_RELATED}` для {obj}.

Сформируй структурированный отчёт:
- Имя и синоним
- Тип объекта
- Реквизиты (имя, тип, синоним)
- Табличные части и их реквизиты
- Формы
- Макеты
- Регистры движений (для документов)
- Связи с другими объектами"""

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
1. Используй `{T.PLATFORM_SEARCH}` чтобы найти описание события «{event}» в базе платформы (сигнатура параметров, контекст вызова).
2. Используй `{T.METADATA_GET}` для получения реквизитов объекта {obj}.
3. Используй `{T.GENERATE_HANDLER}` с подходящим `template_id` (например `handler.before_write`, `handler.on_write`, `handler.filling`, `handler.posting`, `handler.before_delete`, `handler.filling_check`).
4. Проверь сгенерированный код через `{T.CODE_VALIDATE}`.

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
1. Используй `{T.METADATA_GET}` для получения реквизитов и списка макетов объекта {obj}.
2. Если указан макет, используй `{T.TEMPLATE_GET}` для получения его структуры (области, параметры).
3. Если макет полностью определён — `{T.TEMPLATE_GENERATE_FILL_CODE}` сгенерирует код заполнения по областям.
4. Для метаданных-aware генерации используй `{T.SMART_PRINT}`.
5. Для генерации по шаблону — `{T.GENERATE_PRINT}` с template_id из набора (`print.basic`, `print.with_query`, `print.commands_module`).
6. Проверь код через `{T.CODE_VALIDATE}`.

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
1. Используй `{T.EMBEDDING_SEARCH}` с запросом «{name}» — это даст семантически близкий код, в том числе непрямые вызовы.
2. Дополнительно используй встроенный grep по корню конфигурации с регуляркой `\\b{name}\\b` для точного поиска по имени — индексированные embeddings могут пропустить редкие совпадения.
3. Для каждой обнаруженной точки получи код модуля через `{T.CODE_MODULE}` и контекст процедуры через `{T.CODE_PROCEDURE}`.
4. Построй обратный граф: `{T.CODE_CALLGRAPH}` для модулей, где определена «{name}».
5. Используй `{T.GRAPH_RELATED}` для понимания, какие объекты метаданных связаны с этими модулями.

Выведи структурированный отчёт:
- Определение (модуль/строка)
- Список использований с контекстом и типом (вызов, присваивание, параметр)
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
4. Получи метрики сложности через `{T.CODE_COMPLEXITY}`

Выведи отчёт:
- Синтаксические ошибки (строка, описание)
- Предупреждения линтера
- Метрики сложности (цикломатика, длина процедур)
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
3. Используй `{T.GRAPH_RELATED}` для связей на уровне метаданных
4. Используй `{T.GRAPH_IMPACT}` чтобы оценить blast-radius изменений в этом модуле
5. Найди мёртвый код в связанных модулях через `{T.CODE_DEAD_CODE}`

Выведи:
- Список зависимостей (какие модули/процедуры использует)
- Список зависимых (кто использует этот модуль)
- Граф вызовов в текстовом виде
- Циклические зависимости (если есть)
- Потенциально мёртвый код"""

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
1. Используй `{T.METADATA_GET}` для документа {document} — он вернёт список регистров движений.
2. Для каждого регистра используй `{T.METADATA_GET}` для получения структуры (измерения, ресурсы, реквизиты).
3. Используй `{T.SMART_MOVEMENT}` для метаданных-aware генерации с учётом реальной структуры регистров.
4. Альтернатива: `{T.GENERATE_MOVEMENT}` по шаблону (`movement.accumulation_income`, `movement.accumulation_expense`, `movement.posting_full`, и т.д.).
5. Проверь сгенерированный код через `{T.CODE_VALIDATE}`.

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

        proc_step = (
            f"Используй `{T.CODE_PROCEDURE}` для получения кода процедуры {procedure}"
            if procedure
            else "Проанализируй весь модуль"
        )

        prompt = f"""Объясни код: {target}

Выполни следующие шаги:
1. Используй `{T.CODE_MODULE}` для получения кода модуля {module}
2. {proc_step}
3. Получи граф вызовов через `{T.CODE_CALLGRAPH}` — кого вызывает, кто вызывает
4. Получи зависимости через `{T.CODE_DEPENDENCIES}`
5. Оцени сложность через `{T.CODE_COMPLEXITY}`
6. Если код упоминает объекты метаданных — `{T.GRAPH_RELATED}` для них

Объясни:
- Общее назначение кода
- Логику работы пошагово
- Используемые объекты метаданных
- Вызываемые процедуры и их назначение
- Потенциальные проблемы или улучшения"""

        return [self.create_user_message(prompt)]
