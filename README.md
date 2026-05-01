# MCP-1C

**MCP Server для платформы 1C:Предприятие** — анализ метаданных, генерация кода и интеграция с Claude.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Возможности

- **Metadata Engine** — парсинг и индексация метаданных конфигурации 1С
- **Code Engine** — анализ кода на языке BSL (встроенный язык 1С)
- **Template Engine** — генерация кода из шаблонов
- **MXL Engine** — парсинг макетов табличных документов
- **Platform Knowledge Base** — база знаний API платформы 8.3.24
- **BSL Language Server** — интеграция с BSL LS для валидации и форматирования
- **Skills & Agents** — готовые сценарии для Claude Code

## Установка

> **Статус:** пакет на PyPI ещё не опубликован. Текущий способ установки — из git.

### Из git

```bash
git clone https://github.com/Farkhat1984/1C_MCP.git
cd 1C_MCP
pip install -e ".[dev]"
```

### Опциональные зависимости

```bash
# Будущее: локальный fallback embeddings без облака (Phase 1)
# pip install -e ".[local-embeddings]"
```

## Быстрый старт

### 1. Настройка MCP сервера

См. подробную инструкцию: [docs/setup/claude-desktop.md](docs/setup/claude-desktop.md).

Минимальный конфиг для Claude Desktop:

```json
{
  "mcpServers": {
    "mcp-1c": {
      "command": "mcp-1c",
      "args": [],
      "env": {
        "MCP_LOG_LEVEL": "INFO",
        "MCP_EMBEDDING_BACKEND": "local"
      }
    }
  }
}
```

> Без `MCP_EMBEDDING_API_KEY` сервер автоматически переключится на локальные embeddings (требуется `pip install -e ".[local-embeddings]"`).

### 2. Инициализация

В Claude Code выполните:

```
metadata-init path="/home/me/projects/MyConfig"
```

(на Windows — `path="C:/Projects/MyConfig"`).

Проверка:

```
/1c-metadata object="Справочник.Номенклатура"
```

Кэш и embeddings лягут в `~/.cache/mcp-1c/<id>/` (Linux/Mac) или `%LOCALAPPDATA%\mcp-1c\<id>\` (Windows). Каталог конфигурации **не засоряется**.

## Пайплайн работы

### Как работает индексация

```
┌─────────────────────────────────────────────────────────────────────┐
│                        1. ИНИЦИАЛИЗАЦИЯ                             │
├─────────────────────────────────────────────────────────────────────┤
│  metadata.init(config_path)                                         │
│       │                                                             │
│       ▼                                                             │
│  Configuration.xml ──► Парсинг списка объектов                      │
│       │                 (Catalogs, Documents, Registers...)         │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐             │
│  │ Catalog/    │    │ Document/   │    │ Register/   │    ...      │
│  │ Object.xml  │    │ Object.xml  │    │ Object.xml  │             │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘             │
│         │                  │                  │                     │
│         └──────────────────┼──────────────────┘                     │
│                            │                                        │
│                            ▼                                        │
│              Параллельный парсинг (4 потока)                        │
│                            │                                        │
│                            ▼                                        │
│              ┌─────────────────────────┐                            │
│              │   .mcp_1c_cache.db      │  ◄── SQLite база           │
│              │   (в папке конфигурации)│      с WAL режимом         │
│              └─────────────────────────┘                            │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                    2. ИСПОЛЬЗОВАНИЕ КЭША                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  metadata.get("Catalog", "Номенклатура")                           │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────┐     HIT      ┌─────────────────┐              │
│  │  LRU In-Memory  │ ───────────► │  Возврат данных │              │
│  │     Cache       │              └─────────────────┘              │
│  └────────┬────────┘                                               │
│           │ MISS                                                    │
│           ▼                                                         │
│  ┌─────────────────┐     HIT      ┌─────────────────┐              │
│  │  SQLite Cache   │ ───────────► │  Возврат данных │              │
│  │  (проверка MD5) │              │  + обновление   │              │
│  └────────┬────────┘              │  LRU кэша       │              │
│           │ MISS/STALE            └─────────────────┘              │
│           ▼                                                         │
│  ┌─────────────────┐              ┌─────────────────┐              │
│  │  Парсинг XML    │ ───────────► │  Сохранение в   │              │
│  │  файла          │              │  оба кэша       │              │
│  └─────────────────┘              └─────────────────┘              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                   3. ИНКРЕМЕНТАЛЬНОЕ ОБНОВЛЕНИЕ                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  File Watcher (watchfiles)                                          │
│       │                                                             │
│       ▼                                                             │
│  Изменение .xml или .bsl файла                                     │
│       │                                                             │
│       ▼                                                             │
│  Debounce (500ms) ──► Извлечение типа/имени из пути                │
│       │                                                             │
│       ▼                                                             │
│  Перепарсинг только изменённого объекта                            │
│       │                                                             │
│       ▼                                                             │
│  Обновление записи в SQLite + инвалидация LRU кэша                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Структура базы данных

База `.mcp_1c_cache.db` создаётся **в папке конфигурации** и содержит:

| Таблица | Описание |
|---------|----------|
| `metadata_objects` | Основные данные объектов (имя, тип, синоним, UUID) |
| `attributes` | Реквизиты объектов |
| `tabular_sections` | Табличные части |
| `modules` | Пути к модулям (.bsl файлы) |
| `subsystems` | Подсистемы и их содержимое |

### Поддерживаемые форматы выгрузки

| Формат | Источник | Поддержка |
|--------|----------|-----------|
| XML Configurator | Конфигуратор → Выгрузить конфигурацию в файлы | ✅ Полная |
| EDT Project | 1C:EDT → Export | ✅ Полная |

> Формат определяется автоматически по структуре `Configuration.xml`

## Инструменты (Tools)

Зарегистрировано **67 инструментов** (см. `tools/registry.py`). Имена с дефисом, кроме исторических `embedding.*` и `graph.*` (с точкой). Источник истины — `tools/constants.py`.

### Дополнительно (Phase 2–9 расширения):

| Категория | Tools |
|---|---|
| Form (содержимое Form.xml) | `form-get`, `form-handlers`, `form-attributes` |
| СКД / DataCompositionSchema | `composition-get`, `composition-fields`, `composition-datasets`, `composition-settings` |
| Extensions (.cfe) | `extension-list`, `extension-objects`, `extension-impact` |
| BSP knowledge | `bsp-find`, `bsp-hook`, `bsp-modules`, `bsp-review` |
| Runtime via 1С HTTP-сервис (требует настройки MCPBridge.cfe) | `runtime-status`, `runtime-query`, `runtime-eval`, `runtime-data`, `runtime-method` |
| Premium | `diff-configurations`, `test-data-generate` |


### Metadata Tools (4)

| Инструмент | Описание |
|------------|----------|
| `metadata-init` | Инициализация индекса метаданных |
| `metadata-list` | Список объектов по типу |
| `metadata-get` | Полная информация об объекте (реквизиты, формы, макеты, регистры, связи) |
| `metadata-search` | Поиск по имени/синониму |

### Code Tools (9)

| Инструмент | Описание |
|------------|----------|
| `code-module` | Получить код модуля |
| `code-procedure` | Получить код процедуры |
| `code-dependencies` | Граф зависимостей |
| `code-callgraph` | Граф вызовов процедур |
| `code-validate` | Проверка синтаксиса |
| `code-lint` | Статический анализ |
| `code-format` | Форматирование кода |
| `code-complexity` | Анализ сложности |
| `code-dead-code` | Поиск мёртвого кода |

### Generate Tools (8) — генерация по шаблонам

| Инструмент | Описание |
|------------|----------|
| `generate-query` | Генерация запроса (12 шаблонов) |
| `generate-handler` | Обработчик события (10 шаблонов) |
| `generate-print` | Печатная форма (3 шаблона) |
| `generate-movement` | Движения по регистрам (7 шаблонов) |
| `generate-api` | API-методы (HTTP/Web service/JSON) |
| `generate-form_handler` | Обработчик формы |
| `generate-subscription` | Подписка на событие |
| `generate-scheduled_job` | Регламентное задание |

### Smart Tools (3) — генерация с учётом метаданных

| Инструмент | Описание |
|------------|----------|
| `smart-query` | Запрос на основе реальной структуры объекта |
| `smart-print` | Печатная форма с учётом макета и реквизитов |
| `smart-movement` | Движения по структуре регистров документа |

### Query Tools (2)

| Инструмент | Описание |
|------------|----------|
| `query-validate` | Валидация запроса по метаданным |
| `query-optimize` | Подсказки по оптимизации |

### Pattern Tools (3)

| Инструмент | Описание |
|------------|----------|
| `pattern-list` | Список шаблонов |
| `pattern-apply` | Применить шаблон |
| `pattern-suggest` | Предложить шаблон под задачу |

### Template Tools (MXL, 3)

| Инструмент | Описание |
|------------|----------|
| `template-get` | Структура макета (области, параметры) |
| `template-generate_fill_code` | Код заполнения макета по областям |
| `template-find` | Поиск макетов по конфигурации |

### Platform Tools (2)

| Инструмент | Описание |
|------------|----------|
| `platform-search` | Универсальный поиск по API/типам/событиям платформы |
| `platform-global_context` | Глобальный контекст (методы и свойства) |

### Config Tools (4)

| Инструмент | Описание |
|------------|----------|
| `config-objects` | Объекты по типу: FunctionalOption, Constant, ScheduledJob, EventSubscription, ExchangePlan, HTTPService и др. |
| `config-roles` | Список ролей конфигурации |
| `config-role-rights` | Права роли по объектам |
| `config-compare` | Сравнение конфигураций |

### Knowledge Graph Tools (4)

| Инструмент | Описание |
|------------|----------|
| `graph.build` | Построить KG по индексированной конфигурации |
| `graph.related` | Связанные узлы для объекта |
| `graph.impact` | Blast-radius изменений объекта |
| `graph.stats` | Статистика графа |

### Embedding Tools (4)

| Инструмент | Описание |
|------------|----------|
| `embedding.index` | Индексация конфигурации в векторное хранилище |
| `embedding.search` | Семантический поиск |
| `embedding.similar` | Найти похожие фрагменты |
| `embedding.stats` | Статистика индекса |

## Skills & Agents

### Архитектура

Skills и Agents реализованы как MCP Prompts — предопределённые сценарии, которые направляют Claude через последовательность действий с использованием инструментов сервера.

```
┌─────────────────────────────────────────────────────────────────────┐
│                       АРХИТЕКТУРА PROMPTS                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  BasePrompt (base.py)                                               │
│       │                                                             │
│       ├── Skills (skills.py) ─── Простые одношаговые задачи        │
│       │   └── /1c-query, /1c-metadata, /1c-handler...              │
│       │                                                             │
│       ├── Agents (agents.py) ─── Сложные многошаговые workflow     │
│       │   └── /1c-explore, /1c-implement, /1c-debug...             │
│       │                                                             │
│       └── PromptRegistry (registry.py) ─── Регистрация и вызов     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                         КАК ЭТО РАБОТАЕТ                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Пользователь ──► /1c-query object="Справочник.Номенклатура"       │
│       │                                                             │
│       ▼                                                             │
│  PromptRegistry.get_prompt_messages("1c-query", arguments)          │
│       │                                                             │
│       ▼                                                             │
│  QuerySkill.generate_messages(arguments)                            │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │ Промпт с инструкциями для Claude:                       │        │
│  │ 1. Используй metadata.get для получения информации      │        │
│  │ 2. Используй metadata.attributes для реквизитов         │        │
│  │ 3. Используй generate.query для генерации запроса       │        │
│  └─────────────────────────────────────────────────────────┘        │
│       │                                                             │
│       ▼                                                             │
│  Claude выполняет инструкции, вызывая MCP Tools                     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Skills — простые задачи

Skills решают конкретные задачи за несколько шагов. Вызываются через `/` команды.

| Skill | Описание | Аргументы |
|-------|----------|-----------|
| `/1c-query` | Генерация запроса к данным | `object` (обязат.), `fields`, `conditions` |
| `/1c-metadata` | Информация об объекте метаданных | `object` (обязат.) |
| `/1c-handler` | Генерация обработчика события | `object`, `event` (обязат.), `description` |
| `/1c-print` | Генерация печатной формы | `object` (обязат.), `template`, `description` |
| `/1c-usages` | Поиск использований в коде | `name` (обязат.), `scope` |
| `/1c-validate` | Проверка синтаксиса кода | `module` (обязат.) |
| `/1c-deps` | Граф зависимостей модуля | `module` (обязат.), `depth` |
| `/1c-movement` | Генерация движений по регистрам | `document` (обязат.), `register` |
| `/1c-format` | Форматирование кода | `module` (обязат.) |
| `/1c-explain` | Объяснение кода | `module` (обязат.), `procedure` |

### Примеры использования Skills

```
# Генерация запроса с условиями
/1c-query object="Справочник.Номенклатура" fields="Код,Наименование" conditions="Родитель = &Группа"

# Полная информация об объекте
/1c-metadata object="Документ.РеализацияТоваров"

# Генерация обработчика события
/1c-handler object="Документ.ПоступлениеТоваров" event="ПередЗаписью" description="Проверка заполненности склада"

# Генерация печатной формы
/1c-print object="Документ.Счет" description="Печатная форма с таблицей товаров и итогами"

# Поиск использований процедуры
/1c-usages name="ПолучитьЦену" scope="all"

# Генерация движений документа
/1c-movement document="РеализацияТоваров" register="РегистрНакопления.ОстаткиТоваров"

# Анализ зависимостей
/1c-deps module="Документ.РеализацияТоваров.МодульОбъекта" depth="3"

# Объяснение конкретной процедуры
/1c-explain module="ОбщийМодуль.РаботаСТоварами" procedure="РассчитатьЦену"
```

### Agents — сложные многошаговые задачи

Agents — это продвинутые сценарии для комплексных задач. Они содержат детальный план действий с множеством шагов.

| Agent | Описание | Аргументы |
|-------|----------|-----------|
| `/1c-explore` | Исследование конфигурации | `path` (обязат.), `focus`, `depth` |
| `/1c-implement` | Реализация функционала | `task` (обязат.), `object`, `style` |
| `/1c-debug` | Отладка и диагностика | `problem` (обязат.), `module`, `error` |
| `/1c-configure` | Настройка типовой конфигурации | `goal` (обязат.), `configuration`, `approach` |

### Примеры использования Agents

```
# Исследование конфигурации
/1c-explore path="C:\Projects\MyConfig" focus="documents" depth="detailed"

# Реализация нового функционала
/1c-implement task="Добавить автоматический расчёт скидки при проведении документа" object="Документ.РеализацияТоваров" style="bsp"

# Отладка проблемы
/1c-debug problem="Документ не проводится по регистру остатков" module="Документ.РеализацияТоваров.МодульОбъекта" error="Недостаточно остатков на складе"

# Настройка типовой конфигурации
/1c-configure goal="Добавить новый вид цены и настроить его расчёт" configuration="УТ" approach="extension"
```

### Разница между Skills и Agents

| Характеристика | Skills | Agents |
|----------------|--------|--------|
| Сложность | Простые задачи | Комплексные задачи |
| Количество шагов | 3-5 шагов | 10-20+ шагов |
| Область применения | Конкретная операция | Полный workflow |
| Пример | Сгенерировать запрос | Исследовать всю конфигурацию |

### Создание собственных Skills/Agents

Skills и Agents определяются в `src/mcp_1c/prompts/`. Для создания нового:

```python
# src/mcp_1c/prompts/skills.py

class MyCustomSkill(BasePrompt):
    name: ClassVar[str] = "1c-my-skill"
    description: ClassVar[str] = "Описание моего skill"
    arguments: ClassVar[list[PromptArgument]] = [
        PromptArgument(
            name="param",
            description="Описание параметра",
            required=True,
        ),
    ]

    async def generate_messages(
        self, arguments: dict[str, str]
    ) -> list[PromptMessage]:
        param = arguments.get("param", "")

        prompt = f"""Выполни задачу с параметром: {param}

        Шаги:
        1. Используй metadata.get для ...
        2. Используй code.analyze для ...
        3. Сформируй результат
        """

        return [self.create_user_message(prompt)]
```

Затем зарегистрируйте в `PromptRegistry._register_all_prompts()`.

## Примеры использования

Tools вызываются через MCP-протокол (Claude Code/Desktop). Имена приведены в текущей нотации (`tools/constants.py`).

### Анализ метаданных

```text
metadata-get type=Catalog name=Номенклатура
metadata-search query=Продажа type=Document
metadata-list type=AccumulationRegister
```

### Анализ кода

```text
code-module type=Document name=РеализацияТоваров module_type=ObjectModule
code-dependencies type=Document name=РеализацияТоваров
code-callgraph type=CommonModule name=ОбщегоНазначения
code-complexity type=Document name=РеализацияТоваров module_type=ObjectModule
embedding.search query="расчёт скидки"
```

### Генерация кода

```text
# По шаблону
generate-query template_id=query.select_simple values={TableName: "Справочник.Номенклатура", Fields: "Ссылка, Наименование"}
generate-handler template_id=handler.before_write values={...}
generate-movement template_id=movement.accumulation_expense values={...}

# С учётом реальной структуры объекта (smart)
smart-query object="Справочник.Номенклатура"
smart-movement document="РеализацияТоваров"
smart-print object="Документ.Счет"
```

### Граф знаний и связи

```text
graph.build
graph.related node="Document.РеализацияТоваров"
graph.impact node="Catalog.Номенклатура"
```

## Архитектура

```
mcp-1c/
├── src/mcp_1c/
│   ├── __main__.py          # Точка входа
│   ├── server.py             # MCP Server
│   ├── config.py             # Конфигурация
│   │
│   ├── domain/               # Доменные модели (Pydantic)
│   │   ├── metadata.py       # Модели метаданных
│   │   ├── code.py           # Модели кода
│   │   ├── templates.py      # Модели шаблонов
│   │   ├── mxl.py            # Модели макетов
│   │   └── platform.py       # Модели платформы
│   │
│   ├── engines/              # Движки обработки
│   │   ├── metadata/         # Metadata Engine
│   │   ├── code/             # Code Engine
│   │   ├── templates/        # Template Engine
│   │   ├── mxl/              # MXL Engine
│   │   └── platform/         # Platform Engine
│   │
│   ├── tools/                # MCP Tools
│   │   ├── metadata_tools.py
│   │   ├── code_tools.py
│   │   ├── generate_tools.py
│   │   ├── query_tools.py
│   │   ├── pattern_tools.py
│   │   ├── template_tools.py
│   │   ├── platform_tools.py
│   │   └── config_tools.py
│   │
│   ├── prompts/              # Skills & Agents
│   │   ├── skills.py
│   │   └── agents.py
│   │
│   └── utils/                # Утилиты
│       ├── logger.py
│       ├── profiler.py
│       └── lru_cache.py
│
└── tests/                    # Тесты
```

## Оптимизации

MCP-1C оптимизирован для работы с большими конфигурациями:

- **SQLite WAL mode** — улучшенная производительность записи
- **In-memory LRU Cache** — кэширование частых запросов
- **Parallel Indexing** — параллельная индексация объектов
- **Batch Operations** — пакетные операции записи
- **Incremental Updates** — обновление только изменённых файлов

## Разработка

### Запуск тестов

```bash
pytest
pytest --cov=mcp_1c
```

### Проверка кода

```bash
ruff check .
mypy src/mcp_1c
black --check .
```

### Форматирование

```bash
ruff check --fix .
black .
```

## Требования

- Python 3.11+
- MCP SDK 1.0+
- lxml 5.0+
- aiosqlite 0.19+
- watchfiles 0.21+

### Опционально

- BSL Language Server — для валидации и форматирования BSL кода

## Лицензия

MIT License. См. файл [LICENSE](LICENSE).

## Авторы

- MCP-1C Team

## Ссылки

- [MCP Protocol](https://modelcontextprotocol.io/)
- [1C:Enterprise](https://1c.ru/)
- [BSL Language Server](https://github.com/1c-syntax/bsl-language-server)
