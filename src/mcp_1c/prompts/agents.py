"""
Agents for complex 1C development tasks.

Agents are advanced prompts that guide Claude through multi-step operations
for exploring, implementing, debugging, and configuring 1C solutions.
"""

from typing import ClassVar

from mcp.types import PromptArgument, PromptMessage

from mcp_1c.prompts.base import BasePrompt


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
1. Используй `metadata.init` с path="{path}" для инициализации индекса
2. Дождись завершения индексации

### Шаг 2: Обзор структуры
1. Используй `metadata.tree` для получения дерева подсистем
2. Получи общую статистику по типам объектов через `metadata.list` для каждого типа:
   - Справочники (Catalogs)
   - Документы (Documents)
   - Регистры сведений (InformationRegisters)
   - Регистры накопления (AccumulationRegisters)
   - Отчёты (Reports)
   - Обработки (DataProcessors)

### Шаг 3: Анализ ключевых объектов
{"Для фокуса " + focus + " выполни детальный анализ:" if focus != "all" else "Для каждого типа объектов:"}

1. Получи список объектов через `metadata.list`
2. Для каждого значимого объекта:
   - Используй `metadata.get` для базовой информации
   - Используй `metadata.attributes` для реквизитов
   - Используй `metadata.references` для связей

### Шаг 4: Анализ кода (для глубины detailed/deep)
{"Пропустить - режим overview" if depth == "overview" else '''
1. Для ключевых объектов получи код модулей через `code.module`
2. Проанализируй сложность через `code.complexity`
3. Построй граф зависимостей через `code.dependencies`
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

2. {"Проанализируй объект " + obj + " через `metadata.get`" if obj else "Определи затрагиваемые объекты"}

### Шаг 2: Исследование контекста
1. Найди похожую функциональность через `code.usages` или `metadata.search`
2. Изучи существующие паттерны через `pattern.suggest`
3. Проверь связи через `metadata.references`

### Шаг 3: Проектирование
1. Определи необходимые изменения:
   - Новые реквизиты
   - Новые процедуры/функции
   - Изменения форм
   - Движения по регистрам

2. {"Используй стандарты БСП для именования и структуры" if style == "bsp" else "Следуй принятым в конфигурации стандартам"}

### Шаг 4: Генерация кода
Для каждого компонента используй соответствующий инструмент:

1. **Запросы** — `generate.query` с валидацией через `query.validate`
2. **Обработчики** — `generate.handler` с учётом события через `platform.event`
3. **Движения** — `generate.movement` с проверкой структуры регистра
4. **Печатные формы** — `generate.print` с анализом макета через `template.get`
5. **API методы** — `generate.api` по стандартам

### Шаг 5: Валидация
1. Проверь сгенерированный код через `code.validate`
2. Выполни статический анализ через `code.lint`
3. Проверь корректность запросов через `query.validate`

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
{"1. Получи код модуля через `code.module` для " + module if module else "1. Определи модуль где возникает проблема"}
2. Проанализируй код через `code.analyze`
3. Проверь синтаксис через `code.validate`

### Шаг 2: Анализ ошибки
{"Анализ ошибки: " + error if error else "Определи тип проблемы:"}
- Синтаксическая ошибка → `code.validate`
- Логическая ошибка → анализ алгоритма
- Проблема с данными → проверка запросов через `query.validate`
- Проблема производительности → `code.complexity`

### Шаг 3: Поиск причины
1. Используй `code.usages` для поиска связанного кода
2. Построй граф вызовов через `code.callgraph`
3. Проверь зависимости через `code.dependencies`

### Шаг 4: Анализ метаданных
1. Проверь структуру объектов через `metadata.get`
2. Проверь типы реквизитов через `metadata.attributes`
3. Проверь связи через `metadata.references`

### Шаг 5: Проверка запросов
Если проблема связана с запросами:
1. Извлеки запрос и разбери через `query.parse`
2. Проверь таблицы через `query.tables`
3. Валидируй через `query.validate`
4. Проверь оптимизацию через `query.optimize`

### Шаг 6: Формирование решения
1. Определи корневую причину
2. Предложи варианты исправления
3. Сгенерируй исправленный код
4. Проверь исправление через `code.validate`

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
1. Используй `metadata.tree` для понимания структуры подсистем
2. Найди функциональные опции через `config.options`
3. Изучи константы через `config.constants`
4. Проверь регламентные задания через `config.scheduled_jobs`

### Шаг 2: Поиск точек расширения
1. Найди подписки на события через `config.event_subscriptions`
2. Изучи механизмы переопределения (если БСП)
3. Найди программные интерфейсы через `metadata.search`

### Шаг 3: Анализ существующего функционала
1. Найди объекты связанные с целью через `metadata.search`
2. Изучи их структуру через `metadata.get` и `metadata.attributes`
3. Проанализируй код модулей через `code.module`
4. Найди точки вызова через `code.usages`

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
   - Используй `platform.event` для изучения событий
   - Генерируй через `generate.subscription`

2. **Доработка форм**
   - Изучи существующую форму
   - Добавь обработчики через `generate.form_handler`

3. **Регламентные задания**
   - Генерируй через `generate.scheduled_job`

4. **Печатные формы**
   - Анализируй макеты через `template.get`
   - Генерируй через `generate.print`

### Шаг 6: Валидация
1. Проверь код через `code.validate` и `code.lint`
2. Проверь запросы через `query.validate`
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
