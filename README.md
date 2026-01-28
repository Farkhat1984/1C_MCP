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

### Из PyPI (рекомендуется)

```bash
pip install mcp-1c
```

### Из исходников

```bash
git clone https://github.com/your-org/mcp-1c.git
cd mcp-1c
pip install -e ".[dev]"
```

## Быстрый старт

### 1. Настройка MCP сервера

#### Глобальная настройка (для Claude Desktop)

Добавьте в `~/.claude/mcp_servers.json` (Linux/Mac) или `%USERPROFILE%\.claude\mcp_servers.json` (Windows):

```json
{
  "mcpServers": {
    "mcp-1c": {
      "command": "mcp-1c",
      "args": []
    }
  }
}
```

#### Локальная настройка (для конкретной конфигурации 1С)

Создайте файл `.mcp.json` в корне выгруженной конфигурации:

```json
{
  "mcpServers": {
    "mcp-1c": {
      "command": "python",
      "args": ["-m", "mcp_1c"]
    }
  }
}
```

> **Примечание:** Локальная настройка удобна для работы с несколькими конфигурациями — каждая использует свой кэш.

### 2. Инициализация

В Claude Code выполните:

```
Инициализируй конфигурацию по пути C:\Projects\MyConfig
```

Или используйте skill:

```
/1c-metadata Справочник.Номенклатура
```

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

### Metadata Tools

| Инструмент | Описание |
|------------|----------|
| `metadata.init` | Инициализация индекса метаданных |
| `metadata.list` | Список объектов по типу |
| `metadata.get` | Полная информация об объекте |
| `metadata.search` | Поиск по имени/синониму |
| `metadata.tree` | Дерево подсистем |
| `metadata.attributes` | Реквизиты объекта |
| `metadata.forms` | Формы объекта |
| `metadata.templates` | Макеты объекта |
| `metadata.registers` | Регистры документа |
| `metadata.references` | Связи объекта |

### Code Tools

| Инструмент | Описание |
|------------|----------|
| `code.module` | Получить код модуля |
| `code.procedure` | Получить код процедуры |
| `code.resolve` | Найти определение |
| `code.usages` | Найти использования |
| `code.dependencies` | Граф зависимостей |
| `code.analyze` | Расширенный анализ модуля |
| `code.callgraph` | Граф вызовов процедур |
| `code.validate` | Проверка синтаксиса |
| `code.lint` | Статический анализ |
| `code.format` | Форматирование кода |
| `code.complexity` | Анализ сложности |

### Generate Tools

| Инструмент | Описание |
|------------|----------|
| `generate.query` | Генерация запроса |
| `generate.handler` | Генерация обработчика события |
| `generate.print` | Генерация печатной формы |
| `generate.movement` | Генерация движений по регистрам |
| `generate.api` | Генерация API-методов |
| `generate.form_handler` | Обработчики формы |
| `generate.subscription` | Подписка на событие |
| `generate.scheduled_job` | Регламентное задание |

### Query Tools

| Инструмент | Описание |
|------------|----------|
| `query.parse` | Разбор запроса |
| `query.validate` | Валидация с метаданными |
| `query.optimize` | Оптимизация запроса |
| `query.explain` | Объяснение запроса |
| `query.tables` | Таблицы в запросе |

### Pattern Tools

| Инструмент | Описание |
|------------|----------|
| `pattern.list` | Список шаблонов |
| `pattern.get` | Получить шаблон |
| `pattern.apply` | Применить шаблон |
| `pattern.suggest` | Предложить шаблон |
| `pattern.search` | Поиск шаблонов |

### Template Tools (MXL)

| Инструмент | Описание |
|------------|----------|
| `template.get` | Структура макета |
| `template.parameters` | Параметры макета |
| `template.areas` | Области макета |
| `template.generate_fill_code` | Код заполнения макета |
| `template.find` | Поиск макетов |

### Platform Tools

| Инструмент | Описание |
|------------|----------|
| `platform.method` | Описание метода платформы |
| `platform.type` | Описание типа данных |
| `platform.event` | Описание события объекта |
| `platform.search` | Поиск по API платформы |
| `platform.global_context` | Глобальный контекст |

### Config Tools

| Инструмент | Описание |
|------------|----------|
| `config.options` | Функциональные опции |
| `config.constants` | Константы |
| `config.scheduled_jobs` | Регламентные задания |
| `config.event_subscriptions` | Подписки на события |
| `config.exchanges` | Планы обмена |
| `config.http_services` | HTTP-сервисы |

## Skills

Skills — это готовые сценарии для Claude Code, которые можно вызывать через `/` команды.

| Skill | Описание |
|-------|----------|
| `/1c-query` | Генерация запроса к данным |
| `/1c-metadata` | Информация об объекте метаданных |
| `/1c-handler` | Генерация обработчика события |
| `/1c-print` | Генерация печатной формы |
| `/1c-usages` | Поиск использований объекта |
| `/1c-validate` | Проверка синтаксиса кода |
| `/1c-deps` | Граф зависимостей |
| `/1c-movement` | Генерация движений по регистрам |
| `/1c-format` | Форматирование кода |
| `/1c-explain` | Объяснение кода |

### Примеры использования Skills

```
/1c-query Справочник.Номенклатура с отбором по Группе

/1c-metadata Документ.РеализацияТоваров

/1c-handler ПередЗаписью для документа ПоступлениеТоваров

/1c-print для документа Счет с таблицей товаров

/1c-movement документ РеализацияТоваров по регистру ОстаткиТоваров
```

## Agents

Agents — это специализированные агенты для сложных задач.

| Agent | Описание |
|-------|----------|
| `1c-explore` | Исследование конфигурации |
| `1c-implement` | Реализация функционала |
| `1c-debug` | Отладка и диагностика |
| `1c-configure` | Настройка типовой конфигурации |

## Примеры использования

### Анализ метаданных

```python
# Получить информацию о справочнике
metadata.get type="Catalog" name="Номенклатура"

# Найти все документы с "Продажа" в названии
metadata.search query="Продажа" type="Document"

# Получить реквизиты документа
metadata.attributes type="Document" name="РеализацияТоваров"
```

### Анализ кода

```python
# Получить код модуля объекта
code.module type="Document" name="РеализацияТоваров" module_type="ObjectModule"

# Найти все использования процедуры
code.usages type="CommonModule" name="ОбщегоНазначения" procedure="ПолучитьЗначение"

# Получить граф зависимостей
code.dependencies type="Document" name="РеализацияТоваров"
```

### Генерация кода

```python
# Сгенерировать запрос
generate.query template="select_with_filter"
  table="Справочник.Номенклатура"
  filter_field="Родитель"

# Сгенерировать обработчик
generate.handler template="before_write"
  object_type="Document"
  object_name="РеализацияТоваров"

# Сгенерировать движения
generate.movement template="expense"
  register="РегистрНакопления.ОстаткиТоваров"
  document="РеализацияТоваров"
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
