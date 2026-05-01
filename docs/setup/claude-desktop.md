# Подключение MCP-1C к Claude Desktop / Claude Code

MCP-1C говорит по протоколу Model Context Protocol через stdio (`mcp-1c`) или HTTP/SSE (`mcp-1c-web`). Эта инструкция — про stdio (проще, не требует серверной части).

## 1. Установка

```bash
git clone https://github.com/Farkhat1984/1C_MCP.git
cd 1C_MCP
pip install -e ".[dev]"

# опционально — локальные embeddings (без облака):
pip install -e ".[local-embeddings]"
```

После установки в PATH должны появиться `mcp-1c` и `mcp-1c-web`. Проверьте:

```bash
which mcp-1c   # Linux/Mac
where mcp-1c   # Windows
```

## 2. Конфигурационный файл

Расположение:

| ОС | Путь |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Linux | `~/.config/claude/mcp_servers.json` *(или путь, на который указывает ваш клиент)* |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

Минимальный рабочий шаблон:

### Linux / macOS

```json
{
  "mcpServers": {
    "mcp-1c": {
      "command": "/usr/bin/env",
      "args": ["mcp-1c"],
      "env": {
        "MCP_LOG_LEVEL": "INFO",
        "MCP_CONFIG_PATH": "/home/me/projects/MyConfig",
        "MCP_EMBEDDING_BACKEND": "local"
      }
    }
  }
}
```

### Windows

```json
{
  "mcpServers": {
    "mcp-1c": {
      "command": "C:\\Python311\\Scripts\\mcp-1c.exe",
      "args": [],
      "env": {
        "MCP_LOG_LEVEL": "INFO",
        "MCP_CONFIG_PATH": "C:\\Projects\\MyConfig",
        "MCP_EMBEDDING_BACKEND": "local"
      }
    }
  }
}
```

> **Пути на Windows:** в JSON каждый обратный слэш экранируется (`\\`). Альтернатива — прямой слэш (`C:/Projects/MyConfig`), он тоже работает.

## 3. Переменные окружения

| Переменная | Назначение | Пример |
|---|---|---|
| `MCP_CONFIG_PATH` | Путь к выгруженной 1С-конфигурации (там, где лежит `Configuration.xml`). Используется `mcp-1c-web` для авто-инициализации. Для stdio — задаётся в Claude через tool `metadata-init`. | `/home/me/cfg` |
| `MCP_LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR` | `INFO` |
| `MCP_CACHE_DIR` | Куда писать кэш и embeddings БД. По умолчанию: `~/.cache/mcp-1c/` (Linux/Mac), `%LOCALAPPDATA%\mcp-1c\` (Windows). | `/var/cache/mcp-1c` |
| `MCP_EMBEDDING_BACKEND` | `api` (DeepInfra/OpenAI-совместимое API) или `local` (sentence-transformers). По умолчанию: `local`, если не задан `MCP_EMBEDDING_API_KEY`. | `local` |
| `MCP_EMBEDDING_API_KEY` | Ключ DeepInfra / OpenAI / совместимого. Игнорируется, если `MCP_EMBEDDING_BACKEND=local`. | `sk-...` |
| `MCP_EMBEDDING_API_URL` | Эндпоинт embeddings API. | `https://api.deepinfra.com/v1/openai/embeddings` |
| `MCP_EMBEDDING_MODEL` | Имя модели. Должно соответствовать `MCP_EMBEDDING_DIMENSION`. | `Qwen/Qwen3-Embedding-8B` |
| `MCP_EMBEDDING_DIMENSION` | Размерность векторов. 4096 для Qwen3-8B, 384 для MiniLM. | `4096` |
| `MCP_RATE_LIMIT` | Запросов в минуту. `0` отключает. | `60` |

## 4. Первый запуск

После старта Claude Desktop откройте новый чат и попросите:

```
/1c-metadata Справочник.Номенклатура
```

или вручную:

```
Используй tool metadata-init с path="/home/me/projects/MyConfig"
```

Сервер проиндексирует конфигурацию (это однократная операция, занимает 5–60 секунд в зависимости от размера). Кэш ляжет в `~/.cache/mcp-1c/<id>/cache.db`.

## 5. Проверка статуса

В Claude Code:

```
list_tools
```

Должно вернуть 46 инструментов с префиксами `metadata-*`, `code-*`, `generate-*`, `smart-*`, `query-*`, `pattern-*`, `template-*`, `platform-*`, `config-*`, `graph.*`, `embedding.*`.

Skills:

```
list_prompts
```

Должно вернуть 14 промптов: 10 Skills (`/1c-*`) и 4 Agents (`/1c-explore`, `/1c-implement`, `/1c-debug`, `/1c-configure`).

## 6. Web-режим (опционально)

Запустить отдельный HTTP/SSE-сервер:

```bash
MCP_CONFIG_PATH=/home/me/cfg \
MCP_LOG_LEVEL=INFO \
mcp-1c-web --host 127.0.0.1 --port 8080
```

> **Безопасность:** на текущий момент web-сервер **без аутентификации**. Не выставляйте его на публичный интерфейс. Связано с задачей Phase 8 (auth).

## 7. Возможные проблемы

См. [docs/troubleshooting.md](../troubleshooting.md).
