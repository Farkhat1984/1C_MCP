# FIX.md — План исправлений MCP-1C

## КРИТИЧЕСКИЕ (P0) — Исправить немедленно

### 1. Массовое дублирование парсинга типов метаданных

**Файлы:** `metadata_tools.py`, `code_tools.py`, `config_tools.py`, `pattern_tools.py`, `template_tools.py`
**Проблема:** Один и тот же блок парсинга `MetadataType` повторяется ~25 раз:

```python
try:
    metadata_type = MetadataType(type_str)
except ValueError:
    metadata_type = MetadataType.from_russian(type_str)
    if metadata_type is None:
        return {"error": f"Unknown metadata type: {type_str}"}
```

**Решение:** Извлечь в `BaseTool` или `tools/base.py`:

```python
def parse_metadata_type(type_str: str) -> tuple[MetadataType | None, dict[str, Any] | None]:
    try:
        return MetadataType(type_str), None
    except ValueError:
        mt = MetadataType.from_russian(type_str)
        if mt is None:
            return None, {"error": f"Unknown metadata type: {type_str}"}
        return mt, None
```

**Эффект:** -150 строк дублирования, баг-фиксы в одном месте.

---

### 2. Хаотичная обработка ошибок — три разных формата

**Файлы:** все `*_tools.py`
**Проблема:** Tools возвращают ошибки в разных форматах:

```python
# Формат 1: dict с ключом error
return {"error": f"Object not found: {type_str}.{name}"}

# Формат 2: dict с found: False
return {"identifier": identifier, "found": False, "definitions": []}

# Формат 3: ToolResult (только platform_tools.py)
return ToolResult(success=False, error=f"...")
```

**Решение:** Стандартизировать все tools на единый формат. Варианты:

- **Вариант A:** Везде `ToolResult(success, data, error)`
- **Вариант B:** Исключения `ToolError`, перехватываемые в `BaseTool.run()`

**Рекомендация:** Вариант B — добавить в `BaseTool`:

```python
class ToolError(Exception):
    def __init__(self, message: str, code: str = "UNKNOWN"):
        self.message = message
        self.code = code

class BaseTool:
    async def run(self, arguments: dict) -> dict:
        try:
            return await self.execute(arguments)
        except ToolError as e:
            return {"error": e.message, "error_code": e.code}
```

---

### 3. Бесконечная рекурсия в DependencyGraph

**Файл:** `src/mcp_1c/domain/code.py`, метод `get_dependencies()`
**Проблема:** Рекурсивный обход графа зависимостей без cycle detection. Циклические зависимости между модулями 1С — обычное дело. Результат: `RecursionError` → crash сервера.

**Решение:**

```python
def get_dependencies(self, node_id: str, max_depth: int = 10, _visited: set | None = None) -> list:
    if _visited is None:
        _visited = set()
    if node_id in _visited or max_depth <= 0:
        return []
    _visited.add(node_id)
    # ... рекурсия с _visited и max_depth - 1
```

---

### 4. XXE-уязвимость в XML-парсерах

**Файлы:** `engines/metadata/parser.py`, `engines/mxl/parser.py`
**Проблема:** Используется `lxml` без отключения external entity processing. При обработке конфигураций из внешних источников — вектор XXE-атаки.

**Решение:**

```python
from lxml import etree

parser = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    dtd_validation=False,
    load_dtd=False,
)
tree = etree.parse(file_path, parser)
```

---

### 5. Утечка памяти в MxlEngine

**Файл:** `src/mcp_1c/engines/mxl/engine.py`
**Проблема:** `self._cache = {}` растёт без ограничений. Каждый распарсенный MXL-файл остаётся в памяти навсегда.

**Решение:** Использовать существующий `utils/lru_cache.py` или `functools.lru_cache`:

```python
from mcp_1c.utils.lru_cache import LRUCache

self._cache = LRUCache(max_size=100)
```

---

### 6. Утечка temp-файлов в generate_tools.py

**Файл:** `src/mcp_1c/tools/generate_tools.py`
**Проблема:** Удаление temp-файлов в `finally` с `except: pass` — молчаливая утечка.

**Решение:**

```python
import tempfile

with tempfile.NamedTemporaryFile(suffix=".bsl", delete=True) as tmp:
    tmp.write(code.encode())
    tmp.flush()
    result = await bsl_ls.validate_file(Path(tmp.name))
```

---

## ВЫСОКИЙ ПРИОРИТЕТ (P1) — Исправить в ближайшем спринте

### 7. Singleton без Dependency Injection

**Файлы:** все `*_tools.py`
**Проблема:** Tools жёстко привязаны к синглтонам через `Engine.get_instance()`:

```python
def __init__(self):
    self._engine = MetadataEngine.get_instance()
```

Нельзя подменить для тестов, нельзя использовать параллельно с разными конфигурациями.

**Решение:** Передавать engine через конструктор:

```python
class MetadataListTool(BaseTool):
    def __init__(self, engine: MetadataEngine):
        super().__init__()
        self._engine = engine
```

Регистрация в `ToolRegistry`:

```python
engine = MetadataEngine.get_instance()
self.register(MetadataListTool(engine))
self.register(MetadataGetTool(engine))
```

---

### 8. Eager initialization PlatformEngine

**Файл:** `src/mcp_1c/tools/registry.py`
**Проблема:** 88 KB JSON загружаются при старте сервера, даже если platform tools не вызываются.

**Решение:** Lazy loading:

```python
class PlatformToolBase(BaseTool):
    _engine: PlatformEngine | None = None

    @classmethod
    def get_engine(cls) -> PlatformEngine:
        if cls._engine is None:
            cls._engine = PlatformEngine()
        return cls._engine
```

---

### 9. God-class в platform_tools.py

**Файл:** `src/mcp_1c/tools/platform_tools.py`
**Проблема:** 5 классов с идентичным `__init__` — 50+ строк дублирования.

**Решение:**

```python
class PlatformBaseTool(BaseTool):
    def __init__(self, engine: PlatformEngine) -> None:
        super().__init__()
        self.engine = engine

class PlatformMethodTool(PlatformBaseTool):
    name = "platform.method"
    # ... только execute()
```

---

### 10. ThreadPoolExecutor не закрывается

**Файл:** `src/mcp_1c/engines/metadata/indexer.py`
**Проблема:** `ThreadPoolExecutor` создаётся, но не закрывается через context manager. При многократной переиндексации — утечка потоков.

**Решение:**

```python
async def index(self, config_path: Path) -> IndexProgress:
    with ThreadPoolExecutor(max_workers=PARSE_WORKERS) as pool:
        # ... логика индексации
```

---

### 11. Невалидированные required-параметры

**Файл:** `src/mcp_1c/tools/platform_tools.py` и другие
**Проблема:** `arguments.get("name", "")` для required-параметра. Передаёт пустую строку вместо ошибки валидации.

**Решение:** В `BaseTool` добавить валидацию по `input_schema.required`:

```python
async def run(self, arguments: dict) -> Any:
    for field in self.input_schema.get("required", []):
        if field not in arguments or not arguments[field]:
            raise ToolError(f"Required parameter missing: {field}")
    return await self.execute(arguments)
```

---

### 12. Несогласованные return types

**Файл:** `src/mcp_1c/tools/query_tools.py`
**Проблема:** `QueryExplainTool.execute()` возвращает `str`, остальные tools — `dict`. Ломает `format_output()`.

**Решение:** Обернуть в dict:

```python
async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
    return {"explanation": self._engine.explain_query(query_text)}
```

---

## СРЕДНИЙ ПРИОРИТЕТ (P2) — Технический долг

### 13. Regex перекомпилируются при каждом вызове

**Файл:** `src/mcp_1c/engines/code/engine.py`
**Проблема:** Паттерны для поиска определений/использований компилируются в `find_definition()` и `find_usages()` при каждом вызове.

**Решение:** Вынести в константы модуля:

```python
_RE_PROCEDURE = re.compile(r"Процедура\s+{name}\s*\(", re.IGNORECASE)
_RE_FUNCTION = re.compile(r"Функция\s+{name}\s*\(", re.IGNORECASE)
```

Или кэшировать через `functools.lru_cache`.

---

### 14. Хардкод лимитов и TTL

**Файлы:**
- `engines/code/engine.py` — лимит 100 файлов при поиске
- `engines/metadata/cache.py` — TTL кэша захардкожен
- `engines/metadata/indexer.py` — `MAX_CONCURRENT_PARSE`, `PARSE_WORKERS`

**Решение:** Вынести в `config.py`:

```python
@dataclass
class ServerConfig:
    max_search_files: int = 100
    cache_ttl_seconds: int = 300
    max_concurrent_parse: int = 4
    parse_workers: int = 4
```

---

### 15. Late import json в base.py

**Файл:** `src/mcp_1c/tools/base.py`, метод `format_output()`
**Проблема:** `import json` внутри метода — при каждом вызове.

**Решение:** Перенести `import json` на уровень модуля.

---

### 16. Batch-операции в MetadataCache не атомарны

**Файл:** `src/mcp_1c/engines/metadata/cache.py`
**Проблема:** Batch-вставки не обёрнуты в транзакцию. Crash посередине = partial state.

**Решение:**

```python
async def flush_batch(self):
    async with self._connection.execute("BEGIN"):
        for item in self._batch:
            await self._insert(item)
        await self._connection.execute("COMMIT")
    self._batch.clear()
```

---

### 18. Hardcoded tool names в промптах

**Файлы:** `src/mcp_1c/prompts/agents.py`, `skills.py`
**Проблема:** Имена tools ('metadata-init', 'code.module' и т.д.) захардкожены в строках промптов. Рефакторинг имён tools сломает промпты молча.

**Решение:** Вынести имена tools в константы и использовать в промптах:

```python
from mcp_1c.tools.registry import ToolNames

TOOLS = f"Use {ToolNames.METADATA_INIT} to initialize..."
```

---

### 18. Lifespan в web.py не обрабатывает исключения

**Файл:** `src/mcp_1c/web.py`
**Проблема:**

```python
async def lifespan(app):
    await registry.initialize()
    async with session_manager.run():
        yield
    # Нет cleanup при исключении
```

**Решение:**

```python
async def lifespan(app):
    try:
        await registry.initialize()
        async with session_manager.run():
            yield
    finally:
        await registry.cleanup()
```

---

### 19. Hardcoded logging level в web.py

**Файл:** `src/mcp_1c/web.py`
**Проблема:** `setup_logging(level="INFO")` — не настраивается.

**Решение:** Читать из переменной окружения или CLI-аргумента:

```python
level = os.environ.get("MCP_LOG_LEVEL", "INFO")
setup_logging(level=level)
```

---

## ТЕСТЫ (P2) — Критические пробелы

### 20. Нет тестов error paths

**Проблема:** ~90% тестов — happy path. Не тестируются:
- Ошибки файловой системы (permission denied, disk full)
- Corrupted XML/JSON
- Пустые входные данные
- Таймауты

**Решение:** Добавить параметризованные тесты с невалидными данными для каждого engine.

---

### 21. Нет тестов безопасности

**Проблема:** Не проверяются:
- SQL injection в query tools (пользователь передаёт текст запроса)
- Path traversal в metadata tools (пользователь передаёт имена объектов)
- XXE в XML-парсерах

**Решение:** Добавить `tests/security/` с целевыми тестами.

---

### 22. Over-mocking — тесты проверяют моки, а не код

**Проблема:** ~80% тестов мокают engine целиком. Тесты проходят, но реальные баги не ловятся (кейс с RegisterRecords — баг был в парсере, а тесты мокали парсер).

**Решение:** Для каждого engine — минимум 5 интеграционных тестов с реальными данными из `conftest.py`.

---

### 23. Нет performance-тестов

**Проблема:** Сервер обслуживает QGA (663 справочника, 1924 модуля, 2.4M LOC), но нет тестов на производительность.

**Решение:** Добавить `tests/performance/`:
- Индексация 1000+ объектов
- Поиск в 1000+ модулях
- Параллельные запросы к 10+ tools

---

### 24. Assertions слишком слабые

**Проблема:**

```python
# Так сейчас — проверяет что что-то вернулось
assert result
assert "name" in result

# Так надо — проверяет что вернулось правильное
assert result["name"] == "Номенклатура"
assert result["type"] == "Catalog"
assert len(result["attributes"]) == 3
```

---

## НИЗКИЙ ПРИОРИТЕТ (P3) — Nice to have

### 25. O(n) поиск в PlatformEngine

**Файл:** `src/mcp_1c/engines/platform/engine.py`
**Проблема:** `search_types()`, `search_events()` — линейный перебор. При текущих 88 KB данных некритично, но при расширении базы будет тормозить.

**Решение:** Построить inverted index при загрузке.

---

### 26. Нет graceful shutdown

**Проблема:** При SIGTERM сервер не закрывает SQLite-соединения, не flush'ит кэш, не останавливает file watcher.

**Решение:** Реализовать `async def shutdown()` с cleanup всех ресурсов.

---

### 27. Нет rate limiting на MCP tools

**Проблема:** Любой клиент может вызвать tools без ограничений. При подключении через SSE (web.py) — потенциальный DoS.

**Решение:** Добавить простой rate limiter в `BaseTool.run()`.

---

### 28. Encoding detection неоптимальна

**Файл:** `src/mcp_1c/engines/code/reader.py`
**Проблема:** Последовательно пробует все кодировки из списка ENCODINGS. На файлах с broken encoding — медленно.

**Решение:** Использовать `chardet` или `charset-normalizer` для быстрого определения.

---

### 29. Нет метрик и observability

**Проблема:** Нет счётчиков вызовов tools, времени выполнения, ошибок. `profiler.py` существует, но не интегрирован.

**Решение:** Интегрировать `profiler.py` в `BaseTool.run()`, добавить Prometheus-метрики или хотя бы structured logging.

---

## Чеклист для отслеживания

- [ ] P0-1: Извлечь `parse_metadata_type()` в base.py
- [ ] P0-2: Единый формат ошибок (ToolResult или ToolError)
- [ ] P0-3: Cycle detection в DependencyGraph
- [ ] P0-4: Отключить XXE в lxml-парсерах
- [ ] P0-5: LRU-кэш в MxlEngine
- [ ] P0-6: Temp-файлы через context manager
- [ ] P1-7: DI вместо singleton в tools
- [ ] P1-8: Lazy loading PlatformEngine
- [ ] P1-9: Base class для platform tools
- [ ] P1-10: Закрытие ThreadPoolExecutor
- [ ] P1-11: Валидация required-параметров в BaseTool
- [ ] P1-12: Единообразные return types
- [ ] P2-13: Кэширование regex
- [ ] P2-14: Конфигурируемые лимиты/TTL
- [ ] P2-15: Import json на уровне модуля
- [ ] P2-16: Атомарные batch-операции в cache
- [ ] P2-17: Константы для tool names в промптах
- [ ] P2-18: Exception handling в lifespan
- [ ] P2-19: Конфигурируемый logging level
- [ ] P2-20: Тесты error paths
- [ ] P2-21: Тесты безопасности
- [ ] P2-22: Интеграционные тесты вместо over-mocking
- [ ] P2-23: Performance-тесты
- [ ] P2-24: Строгие assertions в тестах
- [ ] P3-25: Inverted index в PlatformEngine
- [ ] P3-26: Graceful shutdown
- [ ] P3-27: Rate limiting
- [ ] P3-28: chardet для encoding detection
- [ ] P3-29: Метрики и observability
