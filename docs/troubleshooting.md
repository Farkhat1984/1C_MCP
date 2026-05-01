# MCP-1C — Troubleshooting

Краткий справочник частых проблем. Если ваша ошибка здесь не описана — откройте issue с логом.

---

## Установка / запуск

### `mcp-1c: command not found`

Скрипт не попал в `PATH`. Варианты:

```bash
# Запустить через Python напрямую
python -m mcp_1c

# Или указать полный путь в claude_desktop_config.json
which mcp-1c   # узнать путь
```

### `ModuleNotFoundError: No module named 'mcp_1c'`

Пакет не установлен. Вероятно вы запускаете из не того venv:

```bash
which python
pip show mcp-1c
pip install -e ".[dev]"
```

---

## Метаданные / индексация

### `Invalid configuration: Configuration.xml not found at <path>`

В указанной папке нет `Configuration.xml`. Проверьте:

1. Это **выгрузка** конфигурации (Configurator → Конфигурация → Выгрузить в файлы), не папка с `.cf`/`.cfu`.
2. Если выгрузка из EDT — корнем считается папка проекта, в которой лежит `src/Configuration/Configuration.mdo` или `Configuration.xml`.
3. Путь не указывает на подпапку (например, `Catalogs/`) — нужен корень.

### `Configuration path does not exist`

Опечатка в пути. На Windows используйте `C:/path` или экранируйте: `C:\\path`.

### Индексация очень долгая

- Для конфигурации УТ/ERP первичная индексация может занимать 1–3 минуты на CPU.
- При повторных запусках работает hash-based incremental update — обычно секунды.
- Если стабильно >10 минут — проверьте нет ли антивируса, замедляющего I/O.

---

## Кэш / Storage

### `Permission denied: ~/.cache/mcp-1c/...`

Cache root не пишется. Установите альтернативный путь:

```bash
MCP_CACHE_DIR=/tmp/mcp-1c
```

### Старые БД остались в папке конфигурации

В версии 0.2.0 БД переехали в `~/.cache/mcp-1c/<id>/`. Если в `<config>/.mcp_1c_cache.db` уже была БД — она используется (backward-compat). Можно удалить вручную:

```bash
rm <config>/.mcp_1c_cache.db <config>/.mcp_1c_embeddings.db
```

После этого MCP-1C создаст новую БД в `~/.cache/mcp-1c/`.

---

## Embeddings

### `Backend 'api' выбран, но API-ключ не задан`

Не задан `MCP_EMBEDDING_API_KEY`. Варианты:

1. **Получить ключ** на https://deepinfra.com и задать `MCP_EMBEDDING_API_KEY=sk-...`.
2. **Переключиться на локальный backend:**
   ```bash
   pip install -e ".[local-embeddings]"
   export MCP_EMBEDDING_BACKEND=local
   ```

### `Local embeddings backend requires sentence-transformers`

Не установлен опциональный extras:

```bash
pip install -e ".[local-embeddings]"
```

### `Model X produces 384-dim vectors but EmbeddingConfig.dimension=4096`

Размерность модели и схемы БД не совпадает. Это случается, если переключаете `MCP_EMBEDDING_BACKEND` после индексации. Исправление:

1. Удалите embeddings БД: `rm ~/.cache/mcp-1c/<id>/embeddings.db`.
2. Установите правильную размерность: `MCP_EMBEDDING_DIMENSION=384` для MiniLM, `4096` для Qwen3-8B.
3. Запустите `embedding.index` заново.

### `Embedding API error 403: Not authenticated`

Неверный или просроченный API-ключ. Проверьте через curl.

### `Embedding API error 429`

Rate limit DeepInfra. Снизьте `MCP_EMBEDDING_BATCH_SIZE` (если есть) или подождите.

---

## BSL Language Server

### Code-validate / code-lint / code-format не работают

Не установлен BSL Language Server. Это опциональная зависимость:

- Скачайте релиз с https://github.com/1c-syntax/bsl-language-server.
- Поместите jar в PATH или укажите в env.

Без BSL LS остальные tools работают, но валидация/форматирование/линтинг отключены.

---

## Web-сервер

### `Address already in use`

Порт занят:

```bash
mcp-1c-web --port 8081
```

### Запросы возвращают 404 на `/health` или `/mcp`

Проверьте, что обращаетесь к правильному пути и порту. Ожидаемые маршруты:
- `GET /health` — статус
- `GET /health?metrics=1` — статус + метрики tools
- `POST /mcp`, `GET /mcp`, `DELETE /mcp` — Streamable HTTP MCP transport

---

## Skills и Agents

### `Unknown tool: <имя>` при вызове Skill

Если такое случилось — это регрессия. Тест-страж `tests/unit/test_prompts_consistency.py` должен ловить это в CI. Проверьте:

```bash
pytest tests/unit/test_prompts_consistency.py
```

Если тест падает — откройте issue.

---

## Производительность

### Высокое потребление памяти при индексации

- Уменьшите `MCP_PARSE_WORKERS` (по умолчанию 4) и `MCP_MAX_CONCURRENT_PARSE` (10).
- Уменьшите `MCP_MXL_CACHE_SIZE` (по умолчанию 100).

### `OperationalError: database is locked`

Несколько процессов пытаются писать в одну БД. Решения:
- Не запускайте несколько `mcp-1c` для одной конфигурации.
- Или используйте разные `MCP_CACHE_DIR` для разных процессов.
