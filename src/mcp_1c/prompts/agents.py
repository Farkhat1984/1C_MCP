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

        prompt = f"""# Задача: Исследование конфигурации 1С

## Параметры
- Путь: {path}
- Фокус: {focus}
- Глубина: {depth}

## План исследования

### Шаг 1: Инициализация
1. Используй `{T.METADATA_INIT}` с path="{path}" для инициализации индекса
2. Дождись завершения индексации

### Шаг 2: Обзор структуры
1. Используй `{T.METADATA_TREE}` для получения дерева подсистем
2. Получи общую статистику по типам объектов через `{T.METADATA_LIST}` для каждого типа:
   - Справочники (Catalogs)
   - Документы (Documents)
   - Регистры сведений (InformationRegisters)
   - Регистры накопления (AccumulationRegisters)
   - Отчёты (Reports)
   - Обработки (DataProcessors)

### Шаг 3: Анализ ключевых объектов
{"Для фокуса " + focus + " выполни детальный анализ:" if focus != "all" else "Для каждого типа объектов:"}

1. Получи список объектов через `{T.METADATA_LIST}`
2. Для каждого значимого объекта:
   - Используй `{T.METADATA_GET}` для базовой информации
   - Используй `{T.METADATA_ATTRIBUTES}` для реквизитов
   - Используй `{T.METADATA_REFERENCES}` для связей

### Шаг 4: Анализ кода (для глубины detailed/deep)
{"Пропустить - режим overview" if depth == "overview" else f'''
1. Для ключевых объектов получи код модулей через `{T.CODE_MODULE}`
2. Проанализируй сложность через `{T.CODE_COMPLEXITY}`
3. Построй граф зависимостей через `{T.CODE_DEPENDENCIES}`
'''}

### Шаг 5: Документирование
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

2. {"Проанализируй объект " + obj + " через `" + T.METADATA_GET + "`" if obj else "Определи затрагиваемые объекты"}

### Шаг 2: Исследование контекста
1. Найди похожую функциональность через `{T.CODE_USAGES}` или `{T.METADATA_SEARCH}`
2. Изучи существующие паттерны через `{T.PATTERN_SUGGEST}`
3. Проверь связи через `{T.METADATA_REFERENCES}`

### Шаг 3: Проектирование
1. Определи необходимые изменения:
   - Новые реквизиты
   - Новые процедуры/функции
   - Изменения форм
   - Движения по регистрам

2. {"Используй стандарты БСП для именования и структуры" if style == "bsp" else "Следуй принятым в конфигурации стандартам"}

### Шаг 4: Генерация кода
Для каждого компонента используй соответствующий инструмент:

1. **Запросы** — `{T.GENERATE_QUERY}` с валидацией через `{T.QUERY_VALIDATE}`
2. **Обработчики** — `{T.GENERATE_HANDLER}` с учётом события через `{T.PLATFORM_EVENT}`
3. **Движения** — `{T.GENERATE_MOVEMENT}` с проверкой структуры регистра
4. **Печатные формы** — `{T.GENERATE_PRINT}` с анализом макета через `{T.TEMPLATE_GET}`
5. **API методы** — `{T.GENERATE_API}` по стандартам

### Шаг 5: Валидация
1. Проверь сгенерированный код через `{T.CODE_VALIDATE}`
2. Выполни статический анализ через `{T.CODE_LINT}`
3. Проверь корректность запросов через `{T.QUERY_VALIDATE}`

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

        prompt = f"""# Задача: Отладка и диагностика 1С

## Описание проблемы
{problem}

{"## Модуль" + chr(10) + module if module else ""}
{"## Текст ошибки" + chr(10) + "```" + chr(10) + error + chr(10) + "```" if error else ""}

## План диагностики

### Шаг 1: Локализация проблемы
{"1. Получи код модуля через `" + T.CODE_MODULE + "` для " + module if module else "1. Определи модуль где возникает проблема"}
2. Проанализируй код через `{T.CODE_ANALYZE}`
3. Проверь синтаксис через `{T.CODE_VALIDATE}`

### Шаг 2: Анализ ошибки
{"Анализ ошибки: " + error if error else "Определи тип проблемы:"}
- Синтаксическая ошибка → `{T.CODE_VALIDATE}`
- Логическая ошибка → анализ алгоритма
- Проблема с данными → проверка запросов через `{T.QUERY_VALIDATE}`
- Проблема производительности → `{T.CODE_COMPLEXITY}`

### Шаг 3: Поиск причины
1. Используй `{T.CODE_USAGES}` для поиска связанного кода
2. Построй граф вызовов через `{T.CODE_CALLGRAPH}`
3. Проверь зависимости через `{T.CODE_DEPENDENCIES}`

### Шаг 4: Анализ метаданных
1. Проверь структуру объектов через `{T.METADATA_GET}`
2. Проверь типы реквизитов через `{T.METADATA_ATTRIBUTES}`
3. Проверь связи через `{T.METADATA_REFERENCES}`

### Шаг 5: Проверка запросов
Если проблема связана с запросами:
1. Извлеки запрос и разбери через `{T.QUERY_PARSE}`
2. Проверь таблицы через `{T.QUERY_TABLES}`
3. Валидируй через `{T.QUERY_VALIDATE}`
4. Проверь оптимизацию через `{T.QUERY_OPTIMIZE}`

### Шаг 6: Формирование решения
1. Определи корневую причину
2. Предложи варианты исправления
3. Сгенерируй исправленный код
4. Проверь исправление через `{T.CODE_VALIDATE}`

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

        prompt = f"""# Задача: Настройка типовой конфигурации 1С

## Цель
{goal}

## Параметры
- Конфигурация: {configuration if configuration else "определить по структуре"}
- Подход: {approach} ({"расширение - без изменения основной конфигурации" if approach == "extension" else "прямые изменения конфигурации"})

## План настройки

### Шаг 1: Анализ конфигурации
1. Используй `{T.METADATA_TREE}` для понимания структуры подсистем
2. Найди функциональные опции через `{T.CONFIG_OPTIONS}`
3. Изучи константы через `{T.CONFIG_CONSTANTS}`
4. Проверь регламентные задания через `{T.CONFIG_SCHEDULED_JOBS}`

### Шаг 2: Поиск точек расширения
1. Найди подписки на события через `{T.CONFIG_EVENT_SUBSCRIPTIONS}`
2. Изучи механизмы переопределения (если БСП)
3. Найди программные интерфейсы через `{T.METADATA_SEARCH}`

### Шаг 3: Анализ существующего функционала
1. Найди объекты связанные с целью через `{T.METADATA_SEARCH}`
2. Изучи их структуру через `{T.METADATA_GET}` и `{T.METADATA_ATTRIBUTES}`
3. Проанализируй код модулей через `{T.CODE_MODULE}`
4. Найди точки вызова через `{T.CODE_USAGES}`

### Шаг 4: Проектирование решения
{"#### Подход: Расширение" if approach == "extension" else "#### Подход: Изменение"}

{"Для расширения:" if approach == "extension" else "Для изменения:"}
{'''
1. Определи объекты для заимствования
2. Спроектируй перехватчики событий
3. Определи дополнительные реквизиты
4. Спланируй дополнительные формы
''' if approach == "extension" else '''
1. Определи минимально необходимые изменения
2. Используй механизмы переопределения БСП
3. Документируй все изменения
4. Планируй обновляемость
'''}

### Шаг 5: Реализация
Для каждого компонента:

1. **Обработчики событий**
   - Используй `{T.PLATFORM_EVENT}` для изучения событий
   - Генерируй через `{T.GENERATE_SUBSCRIPTION}`

2. **Доработка форм**
   - Изучи существующую форму
   - Добавь обработчики через `{T.GENERATE_FORM_HANDLER}`

3. **Регламентные задания**
   - Генерируй через `{T.GENERATE_SCHEDULED_JOB}`

4. **Печатные формы**
   - Анализируй макеты через `{T.TEMPLATE_GET}`
   - Генерируй через `{T.GENERATE_PRINT}`

### Шаг 6: Валидация
1. Проверь код через `{T.CODE_VALIDATE}` и `{T.CODE_LINT}`
2. Проверь запросы через `{T.QUERY_VALIDATE}`
3. Убедись в отсутствии конфликтов

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
