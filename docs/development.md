# Руководство разработчика MCP-1C

Это руководство описывает архитектуру проекта, принципы разработки и способы расширения функциональности.

## Содержание

- [Архитектура](#архитектура)
- [Структура проекта](#структура-проекта)
- [Паттерны проектирования](#паттерны-проектирования)
- [Добавление нового инструмента](#добавление-нового-инструмента)
- [Добавление нового шаблона](#добавление-нового-шаблона)
- [Добавление нового промпта (Skill)](#добавление-нового-промпта-skill)
- [Работа с Engines](#работа-с-engines)
- [Тестирование](#тестирование)
- [Отладка](#отладка)

## Архитектура

MCP-1C использует многослойную архитектуру:

```
┌─────────────────────────────────────────────────────────┐
│                    MCP Server                           │
│  (src/mcp_1c/server.py)                                │
├─────────────────────────────────────────────────────────┤
│                    Tools Layer                          │
│  (src/mcp_1c/tools/*.py)                               │
├─────────────────────────────────────────────────────────┤
│                   Engines Layer                         │
│  (src/mcp_1c/engines/*)                                │
│  - metadata/ — работа с метаданными 1С                 │
│  - code/ — анализ BSL кода                             │
│  - templates/ — генерация кода из шаблонов            │
│  - mxl/ — работа с табличными документами             │
├─────────────────────────────────────────────────────────┤
│                   Domain Layer                          │
│  (src/mcp_1c/domain/*.py)                              │
│  - Модели данных (Pydantic)                            │
├─────────────────────────────────────────────────────────┤
│                   Utils Layer                           │
│  (src/mcp_1c/utils/*.py)                               │
│  - Логирование, кэширование, профилирование            │
└─────────────────────────────────────────────────────────┘
```

### Ключевые компоненты

1. **MCP Server** — точка входа, регистрация tools и prompts
2. **Tools** — обёртки над бизнес-логикой для MCP протокола
3. **Engines** — основная бизнес-логика (Singleton)
4. **Domain** — модели данных (Pydantic BaseModel)
5. **Prompts** — Skills и Agents для расширенных сценариев

## Структура проекта

```
src/mcp_1c/
├── __init__.py          # Пакет
├── __main__.py          # Точка входа
├── server.py            # MCP сервер
├── config.py            # Конфигурация (Pydantic Settings)
│
├── tools/               # MCP Tools
│   ├── base.py          # Базовый класс BaseTool
│   ├── registry.py      # ToolRegistry
│   ├── metadata_tools.py
│   ├── code_tools.py
│   ├── generate_tools.py
│   ├── query_tools.py
│   ├── pattern_tools.py
│   ├── template_tools.py
│   ├── platform_tools.py
│   └── config_tools.py
│
├── prompts/             # MCP Prompts (Skills/Agents)
│   ├── base.py          # Базовый класс
│   ├── registry.py      # PromptRegistry
│   ├── skills.py        # Skills (обзор, отладка, рефакторинг)
│   └── agents.py        # Agents (полные workflow)
│
├── engines/             # Бизнес-логика
│   ├── metadata/        # Работа с метаданными
│   │   ├── engine.py    # MetadataEngine (Singleton)
│   │   ├── parser.py    # XML парсер
│   │   ├── indexer.py   # Индексатор
│   │   └── cache.py     # SQLite кэш
│   │
│   ├── code/            # Анализ кода
│   │   ├── engine.py    # CodeEngine (Singleton)
│   │   ├── parser.py    # BslParser
│   │   ├── reader.py    # BslReader
│   │   ├── bsl_ls.py    # BSL Language Server
│   │   └── dependency_graph.py
│   │
│   ├── templates/       # Генерация кода
│   │   ├── engine.py    # TemplateEngine
│   │   ├── generator.py # CodeGenerator
│   │   ├── loader.py    # TemplateLoader
│   │   ├── query_parser.py
│   │   └── data/        # JSON шаблоны
│   │
│   ├── mxl/             # Табличные документы
│   │   └── engine.py    # MxlEngine
│   │
│   └── platform/        # Platform Knowledge Base
│       ├── engine.py    # PlatformEngine
│       └── data/        # JSON данные API
│
├── domain/              # Модели данных
│   ├── metadata.py      # MetadataObject, MetadataType
│   ├── code.py          # BslModule, Procedure
│   └── templates.py     # Template, Placeholder
│
└── utils/               # Утилиты
    ├── logger.py        # Логирование
    ├── lru_cache.py     # Async LRU кэш
    └── profiler.py      # Профилирование
```

## Паттерны проектирования

### Singleton (Engines)

Все Engine-классы реализуют паттерн Singleton:

```python
class MetadataEngine:
    _instance: "MetadataEngine | None" = None

    @classmethod
    def get_instance(cls) -> "MetadataEngine":
        if cls._instance is None:
            cls._instance = MetadataEngine()
        return cls._instance
```

### Template Method (BaseTool)

Базовый класс `BaseTool` реализует шаблонный метод:

```python
class BaseTool(ABC):
    async def run(self, arguments: dict[str, Any]) -> str:
        # 1. Валидация
        validated = self.validate_input(arguments)
        # 2. Выполнение (абстрактный метод)
        result = await self.execute(validated)
        # 3. Форматирование
        return self.format_output(result)

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> Any:
        ...
```

### Registry (Tools, Prompts)

Регистрация компонентов через Registry:

```python
class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)
```

### Factory (шаблоны)

Загрузка шаблонов из JSON через TemplateLoader.

## Добавление нового инструмента

### 1. Создайте класс инструмента

```python
# src/mcp_1c/tools/my_tools.py
from typing import Any, ClassVar
from mcp_1c.tools.base import BaseTool


class MyCustomTool(BaseTool):
    """Мой кастомный инструмент."""

    # Обязательные атрибуты
    name: ClassVar[str] = "my.custom"
    description: ClassVar[str] = """
Описание инструмента для LLM.

Что делает инструмент, какие параметры принимает,
какой результат возвращает.
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "param1": {
                "type": "string",
                "description": "Описание параметра 1",
            },
            "param2": {
                "type": "integer",
                "description": "Описание параметра 2",
                "default": 10,
            },
        },
        "required": ["param1"],
    }

    def __init__(self) -> None:
        super().__init__()  # Важно! Инициализирует logger
        # Инициализация зависимостей
        self._engine = SomeEngine.get_instance()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Основная логика инструмента."""
        param1 = arguments["param1"]
        param2 = arguments.get("param2", 10)

        # Логика
        result = await self._engine.do_something(param1, param2)

        return {
            "success": True,
            "data": result,
        }
```

### 2. Зарегистрируйте инструмент

```python
# src/mcp_1c/tools/registry.py

from mcp_1c.tools.my_tools import MyCustomTool

class ToolRegistry:
    async def initialize(self) -> None:
        # ... существующие инструменты ...

        # Добавьте ваш инструмент
        self.register(MyCustomTool())
```

### 3. Напишите тесты

```python
# tests/unit/test_my_tools.py
import pytest
from mcp_1c.tools.my_tools import MyCustomTool


class TestMyCustomTool:
    @pytest.fixture
    def tool(self) -> MyCustomTool:
        return MyCustomTool()

    @pytest.mark.asyncio
    async def test_execute_success(self, tool: MyCustomTool) -> None:
        result = await tool.execute({
            "param1": "test_value",
        })

        assert result["success"] is True
        assert "data" in result

    @pytest.mark.asyncio
    async def test_execute_with_optional_param(self, tool: MyCustomTool) -> None:
        result = await tool.execute({
            "param1": "test_value",
            "param2": 20,
        })

        assert result["success"] is True
```

## Добавление нового шаблона

### 1. Выберите категорию

Шаблоны хранятся в JSON файлах по категориям:
- `queries.json` — шаблоны запросов
- `handlers.json` — обработчики событий
- `api.json` — API методы
- и т.д.

### 2. Добавьте шаблон в JSON

```json
// src/mcp_1c/engines/templates/data/queries.json
{
  "templates": [
    {
      "id": "query.my_custom",
      "name": "My Custom Query",
      "description": "Описание шаблона",
      "category": "query",
      "template": "ВЫБРАТЬ\n\t{{Fields}}\nИЗ\n\t{{TableName}}\nГДЕ\n\t{{Condition}}",
      "placeholders": [
        {
          "name": "Fields",
          "description": "Поля для выборки",
          "required": true,
          "example": "Ссылка, Наименование"
        },
        {
          "name": "TableName",
          "description": "Имя таблицы",
          "required": true,
          "example": "Справочник.Номенклатура"
        },
        {
          "name": "Condition",
          "description": "Условие WHERE",
          "required": false,
          "default_value": "ИСТИНА",
          "example": "НЕ ПометкаУдаления"
        }
      ],
      "tags": ["select", "custom"]
    }
  ]
}
```

### 3. Протестируйте шаблон

```python
from mcp_1c.engines.templates import TemplateEngine

engine = TemplateEngine()
result = engine.generate("query.my_custom", {
    "Fields": "Ссылка, Наименование",
    "TableName": "Справочник.Номенклатура",
    "Condition": "НЕ ПометкаУдаления",
})

assert result.success
print(result.code)
```

## Добавление нового промпта (Skill)

### 1. Создайте Skill

```python
# src/mcp_1c/prompts/skills.py

from mcp_1c.prompts.base import BasePrompt, PromptArgument


class MyCustomSkill(BasePrompt):
    """Мой кастомный Skill."""

    name = "my-custom-skill"
    description = "Описание skill для LLM"
    arguments = [
        PromptArgument(
            name="input_param",
            description="Входной параметр",
            required=True,
        ),
    ]

    async def get_messages(
        self,
        arguments: dict[str, str] | None = None,
    ) -> list[dict]:
        input_param = arguments.get("input_param", "") if arguments else ""

        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": f"""# My Custom Skill

## Контекст
Пользователь хочет: {input_param}

## Инструкции
1. Сделайте X
2. Сделайте Y
3. Верните результат

## Доступные инструменты
- `my.custom` — описание
"""
                },
            }
        ]
```

### 2. Зарегистрируйте Skill

```python
# src/mcp_1c/prompts/registry.py

from mcp_1c.prompts.skills import MyCustomSkill

class PromptRegistry:
    def __init__(self) -> None:
        # ... существующие промпты ...
        self.register(MyCustomSkill())
```

## Работа с Engines

### MetadataEngine

Работа с метаданными 1С конфигурации:

```python
from mcp_1c.engines.metadata import MetadataEngine

engine = MetadataEngine.get_instance()

# Инициализация
await engine.initialize("/path/to/config")

# Получение объекта
catalog = await engine.get_object("Catalogs", "Номенклатура")

# Поиск
results = await engine.search("Товар")

# Список объектов
catalogs = await engine.list_objects("Catalogs")
```

### CodeEngine

Анализ BSL кода:

```python
from mcp_1c.engines.code import CodeEngine

engine = CodeEngine.get_instance()

# Получение модуля
module = await engine.get_module("Catalogs", "Номенклатура", "ObjectModule")

# Получение процедуры
proc = await engine.get_procedure("Catalogs", "Номенклатура", "ПриЗаписи", "ObjectModule")

# Поиск использований
usages = await engine.find_usages("МояПроцедура")
```

### TemplateEngine

Генерация кода из шаблонов:

```python
from mcp_1c.engines.templates import TemplateEngine

engine = TemplateEngine()

# Список шаблонов
templates = engine.list_templates()

# Генерация
result = engine.generate("query.select_simple", {
    "TableName": "Справочник.Номенклатура",
    "Fields": "Ссылка, Наименование",
})

if result.success:
    print(result.code)
```

### BslLanguageServer

Интеграция с BSL LS для валидации и форматирования:

```python
from mcp_1c.engines.code.bsl_ls import BslLanguageServer

bsl_ls = BslLanguageServer.get_instance()

# Валидация файла
result = await bsl_ls.validate_file(Path("module.bsl"))

# Форматирование
formatted = await bsl_ls.format_file(Path("module.bsl"))

# Анализ сложности
complexity = await bsl_ls.analyze_complexity(Path("module.bsl"))
```

## Тестирование

### Запуск тестов

```bash
# Все тесты
pytest

# С покрытием
pytest --cov=src/mcp_1c --cov-report=html

# Конкретный файл
pytest tests/unit/test_metadata_tools.py -v

# Конкретный тест
pytest tests/unit/test_metadata_tools.py::TestMetadataListTool -v

# Параллельно
pytest -n auto
```

### Структура тестов

```
tests/
├── conftest.py          # Общие фикстуры
├── unit/                # Unit-тесты
│   ├── test_metadata_tools.py
│   ├── test_code_tools.py
│   ├── test_generate_tools.py
│   └── ...
├── integration/         # Интеграционные тесты
│   └── test_full_workflow.py
└── fixtures/            # Тестовые данные
    └── test_config/
```

### Фикстуры

```python
# tests/conftest.py
import pytest
from pathlib import Path

@pytest.fixture
def test_config_path() -> Path:
    return Path(__file__).parent / "fixtures" / "test_config"

@pytest.fixture
async def initialized_metadata_engine(test_config_path):
    from mcp_1c.engines.metadata import MetadataEngine

    engine = MetadataEngine.get_instance()
    await engine.initialize(test_config_path)
    return engine
```

## Отладка

### Логирование

```python
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)

logger.debug("Отладочное сообщение")
logger.info("Информационное сообщение")
logger.warning("Предупреждение")
logger.error("Ошибка")
logger.exception("Ошибка с traceback")
```

### Уровень логирования

```bash
# Через переменную окружения
MCP_1C_LOG_LEVEL=DEBUG python -m mcp_1c

# В конфигурации
# config.yaml
logging:
  level: DEBUG
```

### Профилирование

```python
from mcp_1c.utils.profiler import profile_async, profile_context

# Декоратор
@profile_async
async def my_function():
    ...

# Контекстный менеджер
async with profile_context("operation_name"):
    await do_something()
```

### Проверка MCP сервера

```python
import asyncio
from mcp_1c.server import create_server

async def test_server():
    server, registry, prompt_registry = create_server()
    await registry.initialize()

    # Список инструментов
    tools = registry.list_tools()
    print(f"Tools: {len(tools)}")

    # Вызов инструмента
    result = await registry.call_tool("metadata.list", {"type": "Catalogs"})
    print(result)

asyncio.run(test_server())
```

## Рекомендации

### Код

1. **Типизация** — всегда используйте type hints
2. **Async** — все I/O операции должны быть асинхронными
3. **Pydantic** — используйте для валидации данных
4. **Singleton** — для Engine-классов
5. **Логирование** — логируйте важные операции

### Тесты

1. **Покрытие** — стремитесь к 80%+
2. **Изоляция** — тесты не должны зависеть друг от друга
3. **Фикстуры** — используйте pytest фикстуры
4. **Мокирование** — мокируйте внешние зависимости

### Документация

1. **Docstrings** — документируйте публичные методы
2. **Описания инструментов** — понятные для LLM
3. **Примеры** — добавляйте примеры использования

## Контакты

- GitHub Issues: https://github.com/your-repo/mcp-1c/issues
- Документация: https://github.com/your-repo/mcp-1c/docs
