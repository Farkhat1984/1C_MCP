"""
Agents for complex 1C development tasks.

Agents are advanced prompts that guide Claude through multi-step operations
for exploring, implementing, debugging, and configuring 1C solutions.
"""

from typing import ClassVar

from mcp.types import PromptArgument, PromptMessage

from mcp_1c.prompts.base import BasePrompt
from mcp_1c.tools.constants import ToolNames as T


class ExploreAgent(BasePrompt):
    """
    Agent for exploring 1C configurations.

    Usage: /1c-explore
    Systematically explores and documents a 1C configuration.
    """

    name: ClassVar[str] = "1c-explore"
    description: ClassVar[str] = (
        "Исследование конфигурации 1С. "
        "Систематически анализирует структуру конфигурации и документирует её."
    )
    arguments: ClassVar[list[PromptArgument]] = [
        PromptArgument(
            name="path",
            description="Путь к корню конфигурации",
            required=True,
        ),
        PromptArgument(
            name="focus",
            description=(
                "Область фокуса: all, documents, catalogs, registers, "
                "reports, subsystems (по умолчанию: all)"
            ),
            required=False,
        ),
        PromptArgument(
            name="depth",
            description="Глубина анализа: overview, detailed, deep (по умолчанию: overview)",
            required=False,
        ),
    ]

    async def generate_messages(
        self, arguments: dict[str, str]
    ) -> list[PromptMessage]:
        path = arguments.get("path", "")
        focus = arguments.get("focus", "all")
        depth = arguments.get("depth", "overview")

        deep_block = (
            "Пропустить — режим overview"
            if depth == "overview"
            else (
                f"1. Для ключевых объектов получи код модулей через `{T.CODE_MODULE}`\n"
                f"2. Проанализируй сложность через `{T.CODE_COMPLEXITY}`\n"
                f"3. Построй граф зависимостей через `{T.CODE_DEPENDENCIES}`\n"
                f"4. Найди мёртвый код через `{T.CODE_DEAD_CODE}`"
            )
        )

        prompt = f"""# Задача: Исследование конфигурации 1С

## Параметры
- Путь: {path}
- Фокус: {focus}
- Глубина: {depth}

## План исследования

### Шаг 1: Инициализация
1. Используй `{T.METADATA_INIT}` с path="{path}" для индексации
2. Дождись завершения индексации
3. Построй граф через `{T.GRAPH_BUILD}` для последующего анализа связей
4. Проверь статистику графа: `{T.GRAPH_STATS}`

### Шаг 2: Обзор структуры
1. Получи список подсистем: `{T.CONFIG_OBJECTS}` с типом Subsystem (или `{T.METADATA_LIST}` type=Subsystem)
2. Получи общую статистику по типам объектов через `{T.METADATA_LIST}` для каждого типа:
   - Справочники (Catalog)
   - Документы (Document)
   - Регистры сведений (InformationRegister)
   - Регистры накопления (AccumulationRegister)
   - Отчёты (Report)
   - Обработки (DataProcessor)

### Шаг 3: Анализ ключевых объектов
{"Для фокуса " + focus + " выполни детальный анализ:" if focus != "all" else "Для каждого типа объектов:"}

1. Получи список объектов через `{T.METADATA_LIST}`
2. Для каждого значимого объекта:
   - Используй `{T.METADATA_GET}` — он вернёт реквизиты, табличные части, формы, макеты, регистры движений в одном вызове.
   - Используй `{T.GRAPH_RELATED}` для связей с другими объектами.

### Шаг 4: Анализ кода (для глубины detailed/deep)
{deep_block}

### Шаг 5: Семантический поиск (опционально)
- Используй `{T.EMBEDDING_STATS}` чтобы понять, проиндексирован ли уже код для семантического поиска.
- Если индекс готов — `{T.EMBEDDING_SEARCH}` с типичными запросами («оплата», «проводки», «остатки») даст быстрый обзор тематических кластеров.

### Шаг 6: Документирование
Сформируй отчёт:
1. **Общая информация** — название, версия, количество объектов
2. **Структура подсистем** — иерархия и назначение
3. **Ключевые объекты** — документы, справочники, регистры
4. **Связи** — как объекты связаны между собой
5. **Код** — статистика, сложность, проблемные места (для detailed/deep)

## Ожидаемый результат
Структурированный отчёт о конфигурации с рекомендациями."""

        return [self.create_user_message(prompt)]


class ImplementAgent(BasePrompt):
    """
    Agent for implementing 1C functionality.

    Usage: /1c-implement
    Guides through implementing new features in 1C.
    """

    name: ClassVar[str] = "1c-implement"
    description: ClassVar[str] = (
        "Реализация функционала 1С. "
        "Помогает пошагово реализовать новую функциональность."
    )
    arguments: ClassVar[list[PromptArgument]] = [
        PromptArgument(
            name="task",
            description="Описание задачи для реализации",
            required=True,
        ),
        PromptArgument(
            name="object",
            description="Целевой объект метаданных (если известен)",
            required=False,
        ),
        PromptArgument(
            name="style",
            description="Стиль кода: bsp (по стандартам БСП) или custom",
            required=False,
        ),
    ]

    async def generate_messages(
        self, arguments: dict[str, str]
    ) -> list[PromptMessage]:
        task = arguments.get("task", "")
        obj = arguments.get("object", "")
        style = arguments.get("style", "bsp")

        target_step = (
            f"Проанализируй объект {obj} через `{T.METADATA_GET}` (включая реквизиты, формы, регистры)"
            if obj
            else "Определи затрагиваемые объекты"
        )
        style_note = (
            "Используй стандарты БСП для именования и структуры"
            if style == "bsp"
            else "Следуй принятым в конфигурации стандартам"
        )

        prompt = f"""# Задача: Реализация функционала 1С

## Описание задачи
{task}

## Параметры
- Целевой объект: {obj if obj else "определить в процессе анализа"}
- Стиль кода: {style}

## План реализации

### Шаг 1: Анализ требований
1. Определи тип задачи:
   - Новый объект метаданных
   - Модификация существующего
   - Добавление обработчика
   - Создание отчёта/обработки
   - Интеграция

2. {target_step}

### Шаг 2: Исследование контекста
1. Найди похожую функциональность через `{T.METADATA_SEARCH}` или `{T.EMBEDDING_SEARCH}`.
2. Изучи существующие паттерны через `{T.PATTERN_SUGGEST}` и список доступных через `{T.PATTERN_LIST}`.
3. Проверь связи через `{T.GRAPH_RELATED}` для целевого объекта.
4. Оцени blast-radius изменений через `{T.GRAPH_IMPACT}`.

### Шаг 3: Проектирование
1. Определи необходимые изменения:
   - Новые реквизиты
   - Новые процедуры/функции
   - Изменения форм
   - Движения по регистрам
2. {style_note}

### Шаг 4: Генерация кода
Для каждого компонента используй соответствующий инструмент:

1. **Запросы** — `{T.SMART_QUERY}` (метаданные-aware) или `{T.GENERATE_QUERY}` (по шаблону) с проверкой через `{T.QUERY_VALIDATE}` и оптимизацией через `{T.QUERY_OPTIMIZE}`.
2. **Обработчики** — `{T.GENERATE_HANDLER}`. Сигнатуру события можно уточнить через `{T.PLATFORM_SEARCH}`.
3. **Движения** — `{T.SMART_MOVEMENT}` (с учётом структуры регистров) или `{T.GENERATE_MOVEMENT}` по шаблону.
4. **Печатные формы** — `{T.SMART_PRINT}` или `{T.GENERATE_PRINT}` с анализом макета через `{T.TEMPLATE_GET}`.
5. **API методы** — `{T.GENERATE_API}` (HTTP/Web service/JSON helper).
6. **Подписки на события** — `{T.GENERATE_SUBSCRIPTION}`.
7. **Регламентные задания** — `{T.GENERATE_SCHEDULED_JOB}`.
8. **Обработчики формы** — `{T.GENERATE_FORM_HANDLER}`.

### Шаг 5: Валидация
1. Проверь сгенерированный код через `{T.CODE_VALIDATE}`.
2. Выполни статический анализ через `{T.CODE_LINT}`.
3. Оцени сложность через `{T.CODE_COMPLEXITY}`.

### Шаг 6: Документирование
1. Добавь комментарии к процедурам
2. Опиши назначение и параметры
3. Укажи зависимости

## Ожидаемый результат
Готовый к использованию код с документацией."""

        return [self.create_user_message(prompt)]


class DebugAgent(BasePrompt):
    """
    Agent for debugging 1C code.

    Usage: /1c-debug
    Helps diagnose and fix issues in 1C code.
    """

    name: ClassVar[str] = "1c-debug"
    description: ClassVar[str] = (
        "Отладка и диагностика 1С. "
        "Помогает найти и исправить ошибки в коде."
    )
    arguments: ClassVar[list[PromptArgument]] = [
        PromptArgument(
            name="problem",
            description="Описание проблемы или ошибки",
            required=True,
        ),
        PromptArgument(
            name="module",
            description="Модуль где возникает проблема (если известен)",
            required=False,
        ),
        PromptArgument(
            name="error",
            description="Текст ошибки (если есть)",
            required=False,
        ),
    ]

    async def generate_messages(
        self, arguments: dict[str, str]
    ) -> list[PromptMessage]:
        problem = arguments.get("problem", "")
        module = arguments.get("module", "")
        error = arguments.get("error", "")

        module_step = (
            f"1. Получи код модуля через `{T.CODE_MODULE}` для {module}"
            if module
            else "1. Определи модуль где возникает проблема (через `"
            + T.EMBEDDING_SEARCH
            + "` или `"
            + T.METADATA_SEARCH
            + "`)"
        )
        error_block = (
            f"## Текст ошибки\n```\n{error}\n```\n"
            if error
            else ""
        )
        module_block = f"## Модуль\n{module}\n" if module else ""

        prompt = f"""# Задача: Отладка и диагностика 1С

## Описание проблемы
{problem}

{module_block}
{error_block}

## План диагностики

### Шаг 1: Локализация проблемы
{module_step}
2. Получи структуру модуля через `{T.CODE_PROCEDURE}` (для интересующей процедуры).
3. Проверь синтаксис через `{T.CODE_VALIDATE}`.

### Шаг 2: Анализ ошибки
{"Анализ ошибки: " + error if error else "Определи тип проблемы:"}
- Синтаксическая ошибка → `{T.CODE_VALIDATE}` + `{T.CODE_LINT}`
- Логическая ошибка → анализ алгоритма (`{T.CODE_PROCEDURE}`, `{T.CODE_CALLGRAPH}`)
- Проблема с данными → проверка запросов через `{T.QUERY_VALIDATE}`
- Проблема производительности → `{T.CODE_COMPLEXITY}` и `{T.QUERY_OPTIMIZE}`

### Шаг 3: Поиск причины
1. Используй `{T.EMBEDDING_SEARCH}` для поиска связанного кода по описанию проблемы.
2. Построй граф вызовов через `{T.CODE_CALLGRAPH}`.
3. Проверь зависимости через `{T.CODE_DEPENDENCIES}`.
4. Оцени blast-radius через `{T.GRAPH_IMPACT}`.

### Шаг 4: Анализ метаданных
1. Проверь структуру объектов через `{T.METADATA_GET}` (реквизиты, типы).
2. Проверь связи через `{T.GRAPH_RELATED}`.

### Шаг 5: Проверка запросов
Если проблема связана с запросами:
1. Извлеки текст запроса из кода (модуля).
2. Валидируй через `{T.QUERY_VALIDATE}`.
3. Проверь оптимизацию через `{T.QUERY_OPTIMIZE}`.

### Шаг 6: Формирование решения
1. Определи корневую причину
2. Предложи варианты исправления
3. Сгенерируй исправленный код (используй соответствующий generate-* tool)
4. Проверь исправление через `{T.CODE_VALIDATE}` и `{T.CODE_LINT}`

## Чеклист диагностики
- [ ] Синтаксис проверен
- [ ] Типы данных корректны
- [ ] Запросы валидны
- [ ] Зависимости разрешены
- [ ] Логика корректна

## Ожидаемый результат
Диагностика с указанием причины и исправленный код."""

        return [self.create_user_message(prompt)]


class ConfigureAgent(BasePrompt):
    """
    Agent for configuring standard 1C solutions.

    Usage: /1c-configure
    Helps configure and customize standard 1C configurations.
    """

    name: ClassVar[str] = "1c-configure"
    description: ClassVar[str] = (
        "Настройка типовой конфигурации 1С. "
        "Помогает настроить и кастомизировать типовые решения."
    )
    arguments: ClassVar[list[PromptArgument]] = [
        PromptArgument(
            name="goal",
            description="Цель настройки (что нужно сделать)",
            required=True,
        ),
        PromptArgument(
            name="configuration",
            description="Название типовой конфигурации (ERP, УТ, БП и др.)",
            required=False,
        ),
        PromptArgument(
            name="approach",
            description="Подход: extension (расширение) или modification (изменение)",
            required=False,
        ),
    ]

    async def generate_messages(
        self, arguments: dict[str, str]
    ) -> list[PromptMessage]:
        goal = arguments.get("goal", "")
        configuration = arguments.get("configuration", "")
        approach = arguments.get("approach", "extension")

        approach_block = (
            "Для расширения:\n"
            "1. Определи объекты для заимствования\n"
            "2. Спроектируй перехватчики событий\n"
            "3. Определи дополнительные реквизиты\n"
            "4. Спланируй дополнительные формы"
            if approach == "extension"
            else "Для изменения:\n"
            "1. Определи минимально необходимые изменения\n"
            "2. Используй механизмы переопределения БСП\n"
            "3. Документируй все изменения\n"
            "4. Планируй обновляемость"
        )

        prompt = f"""# Задача: Настройка типовой конфигурации 1С

## Цель
{goal}

## Параметры
- Конфигурация: {configuration if configuration else "определить по структуре"}
- Подход: {approach}

## План настройки

### Шаг 1: Анализ конфигурации
1. Используй `{T.METADATA_LIST}` type=Subsystem для понимания структуры подсистем.
2. Используй `{T.CONFIG_OBJECTS}` с типами FunctionalOption, Constant, ScheduledJob, EventSubscription, ExchangePlan, HTTPService — для обзора служебных механизмов конфигурации.

### Шаг 2: Поиск точек расширения
1. `{T.CONFIG_OBJECTS}` type=EventSubscription — текущие подписки на события.
2. `{T.METADATA_SEARCH}` для поиска программных интерфейсов (ОбщихМодулей с суффиксом `Переопределяемый`).
3. `{T.EMBEDDING_SEARCH}` с описанием задачи — найдёт семантически близкие места кода.

### Шаг 3: Анализ существующего функционала
1. `{T.METADATA_SEARCH}` для объектов, связанных с целью.
2. `{T.METADATA_GET}` для каждого ключевого объекта (реквизиты, формы, регистры).
3. `{T.CODE_MODULE}` для модулей менеджеров и общих модулей.
4. `{T.GRAPH_RELATED}` и `{T.GRAPH_IMPACT}` — какие объекты затронут изменения.

### Шаг 4: Проектирование решения
{approach_block}

### Шаг 5: Реализация
Для каждого компонента:

1. **Подписки на события** — `{T.GENERATE_SUBSCRIPTION}`. Сигнатуру события уточнить через `{T.PLATFORM_SEARCH}`.
2. **Доработка форм** — `{T.GENERATE_FORM_HANDLER}`.
3. **Регламентные задания** — `{T.GENERATE_SCHEDULED_JOB}`.
4. **Печатные формы** — `{T.SMART_PRINT}` или `{T.GENERATE_PRINT}` (с анализом макета через `{T.TEMPLATE_GET}`).
5. **API** — `{T.GENERATE_API}` для HTTP/Web service.
6. **Запросы** — `{T.SMART_QUERY}` или `{T.GENERATE_QUERY}` с валидацией `{T.QUERY_VALIDATE}`.

### Шаг 6: Валидация
1. Проверь код через `{T.CODE_VALIDATE}` и `{T.CODE_LINT}`.
2. Проверь запросы через `{T.QUERY_VALIDATE}`.
3. Убедись в отсутствии конфликтов: `{T.CONFIG_COMPARE}` для сравнения с эталоном (если применимо).

### Шаг 7: Документирование
1. Опиши внесённые изменения
2. Укажи зависимости
3. Опиши процедуру обновления

## Рекомендации
- Минимизируй изменения типовых объектов
- Используй механизмы БСП для переопределения
- Документируй все доработки
- Планируй обновляемость

## Ожидаемый результат
Пошаговая инструкция по настройке с готовым кодом."""

        return [self.create_user_message(prompt)]
