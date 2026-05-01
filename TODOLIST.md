# MCP-1C: План реализации

> **Реализация на Python** с использованием паттернов проектирования, типизации и чистой архитектуры.

> ## Реальный статус на 2026-04-30
>
> Этот файл — исторический план. Текущее положение дел уточнено отдельно:
>
> - Зарегистрировано **46 tools** (после консолидации; 8 `generate-*` восстановлены).
> - Skills (10) и Agents (4) — **рабочие**, ссылаются только на зарегистрированные tools (`tests/unit/test_prompts_consistency.py` это охраняет).
> - **Не сделано / открыто:**
>   - `runtime.*` (Phase 4.6 ниже) — отсутствует. Запланировано через 1С HTTP-сервис в roadmap.
>   - Парсинг **содержимого** Form.xml (элементы, обработчики, реквизиты) — нет, только список форм.
>   - **Система компоновки данных (СКД)** для отчётов — не парсится.
>   - **Расширения конфигурации** (.cfe / Adopted/Replaced) — не поддерживаются.
>   - **БСП-знания** (модули, хуки, паттерны) — отсутствуют.
>   - PyPI пакет — **не опубликован**.
>   - Реальные тесты с типовыми (УТ/ERP/БП) — нет, фикстуры синтетические.
>   - SQLite-БД пишутся в каталог конфигурации (планируется перенос в `~/.cache/mcp-1c/`).
>   - Web-сервер без аутентификации, default `host=0.0.0.0`.
>
> Полный план улучшений и приоритеты — в файле `docs/ROADMAP.md` (TBD) и в плане агента в `~/.claude/plans/velvet-snacking-sutton.md`.

---

## Фаза 1: Ядро (MVP)

### 1.1 Инициализация проекта
- [x] Создать структуру проекта (pyproject.toml)
- [x] Настроить Ruff, Black, MyPy
- [x] Определить зависимости (MCP SDK, lxml, aiosqlite, watchfiles)
- [x] Создать базовую структуру директорий

### 1.2 MCP Server Core
- [x] Реализовать точку входа (src/mcp_1c/__main__.py)
- [x] Настроить MCP Server с stdio транспортом
- [x] Реализовать регистрацию tools (Registry pattern)
- [x] Реализовать обработку ошибок
- [x] Добавить логирование

### 1.3 Metadata Engine
- [x] XML Parser — парсинг Configuration.xml
- [x] XML Parser — парсинг объектов метаданных (Catalogs, Documents, etc.)
- [x] Indexer — сканирование директорий конфигурации
- [x] Indexer — построение индекса объектов
- [x] Cache — SQLite хранилище индекса
- [x] Cache — инкрементальное обновление
- [x] File Watcher — отслеживание изменений (watchfiles)

### 1.4 Tools: metadata.*
- [x] `metadata.init` — инициализация индекса
- [x] `metadata.list` — список объектов по типу
- [x] `metadata.get` — полная информация об объекте
- [x] `metadata.search` — поиск по имени/синониму
- [x] `metadata.tree` — дерево подсистем
- [x] `metadata.attributes` — реквизиты объекта
- [x] `metadata.forms` — формы объекта
- [x] `metadata.templates` — макеты объекта
- [x] `metadata.registers` — регистры документа
- [x] `metadata.references` — связи объекта

### 1.5 Code Engine (базовый)
- [x] BSL Reader — чтение .bsl файлов
- [x] BSL Parser — извлечение процедур/функций (regex)
- [x] BSL Parser — извлечение директив компиляции
- [x] BSL Parser — извлечение регионов

### 1.6 Tools: code.* (базовые)
- [x] `code-module` — получить код модуля
- [x] `code-procedure` — получить код процедуры
- [ ] `code-resolve` — удалён в консолидации (используй `code-module` + grep / `embedding.search`)
- [ ] `code-usages` — удалён в консолидации (используй `embedding.search` + `code-callgraph`)

### 1.7 Тестирование Фазы 1
- [x] Unit-тесты XML парсера
- [x] Unit-тесты индексатора
- [x] Unit-тесты BSL парсера
- [x] Интеграционный тест на тестовой конфигурации
- [x] Тест MCP протокола с Claude Code

---

## Фаза 2: Анализ кода

### 2.1 BSL Parser (продвинутый)
- [x] Построение AST (regex-based, извлечение структур)
- [x] Извлечение вызовов методов
- [x] Извлечение обращений к метаданным
- [x] Анализ параметров процедур
- [x] Извлечение запросов из кода
- [x] Извлечение использования переменных

### 2.2 Граф зависимостей
- [x] Построение графа вызовов
- [x] Построение графа ссылок на метаданные
- [x] Хранение графа в SQLite
- [x] Инкрементальное обновление графа
- [x] Методы запроса графа (callees, callers, dependencies)

### 2.3 BSL Language Server интеграция
- [x] Запуск BSL LS как subprocess
- [x] Валидация файлов через LSP
- [x] Получение диагностик
- [x] Форматирование кода

### 2.4 Tools: code.* (расширенные)
- [x] `code.dependencies` — граф зависимостей
- [x] `code.analyze` — расширенный анализ модуля
- [x] `code.callgraph` — граф вызовов процедур
- [x] `code.validate` — проверка синтаксиса
- [x] `code.lint` — статический анализ
- [x] `code.format` — форматирование
- [x] `code.complexity` — анализ сложности

### 2.5 Тестирование Фазы 2
- [x] Unit-тесты расширенного BSL парсера
- [x] Unit-тесты графа зависимостей
- [x] Тест интеграции с BSL LS

---

## Фаза 3: Генерация кода

### 3.1 Template Engine
- [x] Загрузка шаблонов из JSON
- [x] Подстановка плейсхолдеров
- [x] Валидация значений плейсхолдеров
- [x] Контекстная генерация (с учётом метаданных)

### 3.2 База шаблонов
- [x] Шаблоны запросов (12 шт.)
- [x] Шаблоны обработчиков событий (10 шт.)
- [x] Шаблоны печатных форм (3 шт.)
- [x] Шаблоны движений по регистрам (7 шт.)
- [x] Шаблоны API-методов (7 шт.)

### 3.3 Tools: generate.*
- [x] `generate.query` — генерация запроса
- [x] `generate.handler` — генерация обработчика
- [x] `generate.print` — генерация печатной формы
- [x] `generate.movement` — генерация движений
- [x] `generate.api` — генерация API-методов
- [x] `generate.form_handler` — обработчики формы
- [x] `generate.subscription` — подписка на событие
- [x] `generate.scheduled_job` — регламентное задание

### 3.4 Tools: query.*
- [x] `query.parse` — разбор запроса
- [x] `query.validate` — валидация с метаданными
- [x] `query.optimize` — оптимизация
- [x] `query.explain` — объяснение запроса
- [x] `query.tables` — таблицы в запросе

### 3.5 Tools: pattern.*
- [x] `pattern.list` — список шаблонов
- [x] `pattern.get` — получить шаблон
- [x] `pattern.apply` — применить шаблон
- [x] `pattern.suggest` — предложить шаблон
- [x] `pattern.search` — поиск шаблонов

### 3.6 Тестирование Фазы 3
- [x] Unit-тесты шаблонизатора
- [x] Тесты генерации кода
- [x] Валидация сгенерированного кода через BSL LS

---

## Фаза 4: Расширенные возможности

### 4.1 Template Engine (макеты)
- [x] Парсинг табличных документов (mxl → xml)
- [x] Извлечение областей макета
- [x] Извлечение параметров [Параметр]

### 4.2 Tools: template.*
- [x] `template.get` — структура макета
- [x] `template.parameters` — параметры макета
- [x] `template.areas` — области макета
- [x] `template.generate_fill_code` — код заполнения
- [x] `template.find` — поиск макетов в конфигурации

### 4.3 Knowledge Base
- [x] Глобальный контекст платформы 8.3.24
- [x] Типы данных платформы
- [x] События объектов
- [x] Методы коллекций

### 4.4 Tools: platform.*
- [x] `platform.method` — описание метода
- [x] `platform.type` — описание типа
- [x] `platform.event` — описание события
- [x] `platform.search` — поиск по API
- [x] `platform.global_context` — глобальный контекст

### 4.5 Tools: config.*
- [x] `config.options` — функциональные опции
- [x] `config.constants` — константы
- [x] `config.scheduled_jobs` — регламентные задания
- [x] `config.event_subscriptions` — подписки на события
- [x] `config.exchanges` — планы обмена
- [x] `config.http_services` — HTTP-сервисы

### 4.6 Runtime Engine (опционально)
- [ ] COM Connector (Windows)
- [ ] HTTP Client для HTTP-сервисов
- [ ] `runtime.connect` — подключение
- [ ] `runtime.query` — выполнение запроса
- [ ] `runtime.eval` — выполнение кода
- [ ] `runtime.call` — вызов метода
- [ ] `runtime.data` — получение данных

### 4.7 Тестирование Фазы 4
- [x] Тесты Knowledge Base
- [x] Тесты парсинга макетов
- [x] Тесты config tools

---

## Фаза 5: Skills и Agents

### 5.1 Skills
- [x] `/1c-query` — генерация запроса
- [x] `/1c-metadata` — информация об объекте
- [x] `/1c-handler` — генерация обработчика
- [x] `/1c-print` — генерация печатной формы
- [x] `/1c-usages` — поиск использований
- [x] `/1c-validate` — проверка синтаксиса
- [x] `/1c-deps` — граф зависимостей
- [x] `/1c-movement` — генерация движений
- [x] `/1c-format` — форматирование
- [x] `/1c-explain` — объяснение кода

### 5.2 Agents
- [x] `1C-Explore` — исследование конфигурации
- [x] `1C-Implement` — реализация функционала
- [x] `1C-Debug` — отладка и диагностика
- [x] `1C-Configure` — настройка типовой

### 5.3 Тестирование Фазы 5
- [x] Тесты Skills
- [x] Тесты Agents на реальных сценариях

---

## Фаза 6: Финализация

### 6.1 Оптимизация
- [x] Профилирование индексации
- [x] Оптимизация запросов к SQLite
- [x] Кэширование частых запросов
- [x] Параллельная индексация

### 6.2 Тестирование на реальных конфигурациях
- [x] Минимальная конфигурация (10-20 объектов)
- [x] Средняя конфигурация (~500 объектов)
- [x] Большая конфигурация (~3000 объектов) — протестировано на ЗУП КОРП (7794 объекта)

### 6.3 Документация
- [x] README.md — установка и настройка
- [x] Примеры использования
- [x] API Reference
- [x] Руководство разработчика

### 6.4 Публикация
- [x] Подготовка PyPI пакета
- [x] Настройка CI/CD
- [ ] Публикация в PyPI — **не опубликовано**, README обещает `pip install mcp-1c`, но пакет недоступен
- [ ] Релиз на GitHub

---

## Структура проекта (Python)

```
mcp-1c/
├── src/
│   └── mcp_1c/
│       ├── __init__.py              # Package init
│       ├── __main__.py              # Entry point
│       ├── server.py                # MCP Server
│       ├── config.py                # Configuration
│       │
│       ├── domain/                  # Domain models (Pydantic)
│       │   ├── __init__.py
│       │   ├── metadata.py          # Metadata models
│       │   └── code.py              # Code models
│       │
│       ├── engines/
│       │   ├── __init__.py
│       │   ├── metadata/
│       │   │   ├── __init__.py
│       │   │   ├── parser.py        # XML parser (lxml)
│       │   │   ├── indexer.py       # Indexer
│       │   │   ├── cache.py         # SQLite cache (aiosqlite)
│       │   │   ├── watcher.py       # File watcher (watchfiles)
│       │   │   └── engine.py        # Facade
│       │   │
│       │   └── code/
│       │       ├── __init__.py
│       │       ├── reader.py        # BSL reader
│       │       ├── parser.py        # BSL parser (regex)
│       │       └── engine.py        # Facade
│       │
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── base.py              # Base tool class
│       │   ├── registry.py          # Tool registry
│       │   ├── metadata_tools.py    # metadata.* tools
│       │   └── code_tools.py        # code.* tools
│       │
│       └── utils/
│           ├── __init__.py
│           ├── logger.py
│           └── helpers.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/                    # Test configurations
│
├── pyproject.toml
├── TODOLIST.md
└── README.md
```

---

## Прогресс

| Фаза | Статус | Задач | Выполнено |
|------|--------|-------|-----------|
| 1. Ядро (MVP) | ✅ Завершено | 32 | 32 |
| 2. Анализ кода | ✅ Завершено | 21 | 21 |
| 3. Генерация | ✅ Завершено | 25 | 25 |
| 4. Расширенные | ✅ Завершено | 28 | 26 |
| 5. Skills/Agents | ✅ Завершено | 17 | 17 |
| 6. Финализация | 🔄 В работе | 12 | 12 |
| **Всего** | | **135** | **134** |

---

## Текущая задача

**Фаза 6: Финализация — 🔄 В РАБОТЕ**

### Выполнено в этой сессии:

**Оптимизация:**
- `src/mcp_1c/utils/profiler.py` — модуль профилирования с декораторами и контекстными менеджерами
- `src/mcp_1c/utils/lru_cache.py` — LRU кэш для асинхронных операций с TTL
- Обновлён `cache.py`:
  - SQLite WAL mode и PRAGMA оптимизации
  - In-memory LRU кэши для объектов, поиска и списков
  - Batch операции для массовой вставки
  - Профилирование операций
- Обновлён `indexer.py`:
  - Параллельная индексация с asyncio.gather
  - Семафор для контроля конкурентности
  - ThreadPoolExecutor для CPU-bound парсинга
  - Hash-based инкрементальные обновления

**Документация:**
- Обновлён `README.md` — полная документация на русском
- `docs/examples.md` — примеры использования всех инструментов
- `docs/api-reference.md` — справочник по API
- `LICENSE` — MIT лицензия
- `CHANGELOG.md` — журнал изменений

**Публикация:**
- Обновлён `pyproject.toml` — метаданные, URLs, классификаторы
- `.github/workflows/ci.yml` — CI workflow (lint, test, build)
- `.github/workflows/publish.yml` — публикация в PyPI
- `MANIFEST.in` — включение JSON-файлов шаблонов
- `.gitignore` — игнорирование временных файлов

### Файлы Фазы 4:

**MXL Engine (макеты табличных документов):**
- `src/mcp_1c/domain/mxl.py` - Модели для макетов:
  - `MxlDocument` - документ макета
  - `MxlArea` - именованная область
  - `MxlCell` - ячейка
  - `TemplateParameter` - параметр макета
  - `FillCodeGenerationOptions` - опции генерации
  - `GeneratedFillCode` - результат генерации

- `src/mcp_1c/engines/mxl/parser.py` - Парсер MXL/XML:
  - Парсинг SpreadsheetDocument
  - Извлечение областей (Header, Row, Footer, etc.)
  - Извлечение параметров [Parameter], <Parameter>, {Expression}
  - Определение типов параметров

- `src/mcp_1c/engines/mxl/generator.py` - Генератор кода заполнения:
  - Генерация кода на русском/английском
  - Поддержка циклов для табличных областей
  - Генерация процедур
  - Комментарии и подсказки

- `src/mcp_1c/engines/mxl/engine.py` - Фасад MXL Engine

**Tools template.* (5 шт.):**
- `template.get` - структура макета
- `template.parameters` - параметры макета
- `template.areas` - области макета
- `template.generate_fill_code` - код заполнения
- `template.find` - поиск макетов

**Тесты:**
- `tests/unit/test_mxl_parser.py` - тесты парсера макетов

---

### Файлы Фазы 3 (справка):

**Модели шаблонов:**
- `src/mcp_1c/domain/templates.py` - Модели для генерации кода:
  - `CodeTemplate` - шаблон генерации
  - `Placeholder` - плейсхолдер шаблона
  - `PlaceholderType` - типы плейсхолдеров
  - `TemplateCategory` - категории шаблонов
  - `GenerationContext` - контекст генерации
  - `GenerationResult` - результат генерации
  - `ParsedQuery` - разобранный запрос
  - `QueryValidationResult` - результат валидации запроса
  - `QueryOptimizationSuggestion` - предложение оптимизации

**Template Engine:**
- `src/mcp_1c/engines/templates/loader.py` - Загрузка шаблонов из JSON
- `src/mcp_1c/engines/templates/generator.py` - Генератор кода:
  - Подстановка плейсхолдеров ${Name}
  - Условные блоки {{#if}}...{{/if}}
  - Циклы {{#each}}...{{/each}}
  - Валидация типов и значений
- `src/mcp_1c/engines/templates/query_parser.py` - Парсер запросов 1С:
  - Парсинг SELECT, FROM, WHERE, GROUP BY, ORDER BY
  - Извлечение таблиц и виртуальных таблиц
  - Извлечение параметров &Parameter
  - Валидация и оптимизация
- `src/mcp_1c/engines/templates/engine.py` - Фасад Template Engine

**База шаблонов (39 шаблонов):**
- `src/mcp_1c/engines/templates/data/queries.json` - 12 шаблонов запросов
- `src/mcp_1c/engines/templates/data/handlers.json` - 10 шаблонов обработчиков
- `src/mcp_1c/engines/templates/data/print_forms.json` - 3 шаблона печатных форм
- `src/mcp_1c/engines/templates/data/movements.json` - 7 шаблонов движений
- `src/mcp_1c/engines/templates/data/api.json` - 7 шаблонов API

**Новые tools (21 шт.):**

*generate.* (8):*
- `generate.query` - генерация запроса
- `generate.handler` - генерация обработчика
- `generate.print` - генерация печатной формы
- `generate.movement` - генерация движений
- `generate.api` - генерация API-методов
- `generate.form_handler` - обработчики формы
- `generate.subscription` - подписка на событие
- `generate.scheduled_job` - регламентное задание

*query.* (5):*
- `query.parse` - разбор запроса
- `query.validate` - валидация запроса
- `query.optimize` - оптимизация запроса
- `query.explain` - объяснение запроса
- `query.tables` - таблицы в запросе

*pattern.* (5):*
- `pattern.list` - список шаблонов
- `pattern.get` - получить шаблон
- `pattern.apply` - применить шаблон
- `pattern.suggest` - предложить шаблон
- `pattern.search` - поиск шаблонов

**Тесты:**
- `tests/unit/test_template_engine.py` - тесты Template Engine
- `tests/unit/test_generation_tools.py` - тесты инструментов генерации

---

## Следующая задача

**Фаза 6: Финализация — ОЖИДАЕТ**

### Завершённые фазы:
1. ✅ Фаза 1: Ядро (MVP)
2. ✅ Фаза 2: Анализ кода
3. ✅ Фаза 3: Генерация кода
4. ✅ Фаза 4: Расширенные возможности
5. ✅ Фаза 5: Skills и Agents

### Созданные файлы Фазы 5 (Skills и Agents):

**Инфраструктура промптов:**
- `src/mcp_1c/prompts/__init__.py` - инициализация модуля
- `src/mcp_1c/prompts/base.py` - базовый класс BasePrompt
- `src/mcp_1c/prompts/registry.py` - PromptRegistry для управления промптами

**Skills (10 шт.):**
- `src/mcp_1c/prompts/skills.py` - реализация всех skills:
  - `1c-query` — генерация запросов
  - `1c-metadata` — информация об объекте
  - `1c-handler` — генерация обработчиков
  - `1c-print` — генерация печатных форм
  - `1c-usages` — поиск использований
  - `1c-validate` — проверка синтаксиса
  - `1c-deps` — граф зависимостей
  - `1c-movement` — генерация движений
  - `1c-format` — форматирование кода
  - `1c-explain` — объяснение кода

**Agents (4 шт.):**
- `src/mcp_1c/prompts/agents.py` - реализация агентов:
  - `1c-explore` — исследование конфигурации
  - `1c-implement` — реализация функционала
  - `1c-debug` — отладка и диагностика
  - `1c-configure` — настройка типовой

**Тесты:**
- `tests/unit/test_skills.py` - тесты Skills
- `tests/unit/test_agents.py` - тесты Agents

**Обновлённые файлы:**
- `src/mcp_1c/server.py` - интеграция prompts в MCP Server
- `src/mcp_1c/__main__.py` - обновлена точка входа

---

### Созданные файлы Knowledge Base:

**Модели:**
- `src/mcp_1c/domain/platform.py` - Модели для Knowledge Base:
  - `PlatformMethod` - метод платформы
  - `PlatformType` - тип данных
  - `ObjectEvent` - событие объекта
  - `GlobalContext` - глобальный контекст
  - `PlatformKnowledgeBase` - полная база знаний

**Engine:**
- `src/mcp_1c/engines/platform/__init__.py`
- `src/mcp_1c/engines/platform/engine.py` - PlatformEngine

**Data (JSON):**
- `src/mcp_1c/engines/platform/data/global_context.json` - 70+ методов глобального контекста
- `src/mcp_1c/engines/platform/data/types.json` - 12 типов с методами и свойствами
- `src/mcp_1c/engines/platform/data/events.json` - 24 события объектов

**Tools platform.* (5 шт.):**
- `platform.method` - описание метода
- `platform.type` - описание типа
- `platform.event` - описание события
- `platform.search` - поиск по API
- `platform.global_context` - глобальный контекст

**Тесты:**
- `tests/unit/test_platform_engine.py` - тесты Knowledge Base

### Созданные файлы Config Tools:

**Tools config.* (6 шт.):**
- `src/mcp_1c/tools/config_tools.py` - инструменты конфигурации:
  - `config.options` - функциональные опции
  - `config.constants` - константы
  - `config.scheduled_jobs` - регламентные задания
  - `config.event_subscriptions` - подписки на события
  - `config.exchanges` - планы обмена
  - `config.http_services` - HTTP-сервисы

**Тесты:**
- `tests/unit/test_config_tools.py` - тесты Config Tools
