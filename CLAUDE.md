# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MCP Server for 1C:Enterprise platform — provides metadata indexing, BSL code analysis, code generation, semantic search, and a metadata knowledge graph for 1C configurations. Tools and prompts are exposed via the Model Context Protocol over stdio (`mcp-1c`) or as a web service (`mcp-1c-web`).

Audience is 1C:Enterprise developers; object names, prompts, and example code are in Russian. BSL (Built-in Scripting Language) is the 1C programming language.

## Commands

```bash
# Install (development)
pip install -e ".[dev]"

# Run tests
pytest
pytest tests/unit/test_parser.py                # single file
pytest tests/unit/test_parser.py::test_name     # single test
pytest --cov=mcp_1c                             # with coverage

# Lint / type-check / format
ruff check .
ruff check --fix .
mypy src/mcp_1c
black --check .
black .

# Run servers
mcp-1c          # stdio MCP server (entrypoint in src/mcp_1c/__main__.py)
mcp-1c-web      # HTTP/SSE server  (entrypoint in src/mcp_1c/web.py)
```

`pyproject.toml` configures ruff (line-length 100, py311 target), mypy (`strict = true`, `disallow_untyped_defs`), and pytest-asyncio (function-scoped event loop).

## Architecture

### Core pattern: Engine → Tool → Registry

1. **Domain models** (`src/mcp_1c/domain/`) — Pydantic models for metadata, code, templates, MXL spreadsheets, and platform types.
2. **Engines** (`src/mcp_1c/engines/`) — core logic per domain:
   - `metadata/` — XML parsing, SQLite cache, file watcher, incremental indexing
   - `code/` — BSL parser, dependency analysis, BSL Language Server integration
   - `templates/` — code generation from JSON template definitions
   - `mxl/` — spreadsheet (MXL) template parsing
   - `platform/` — static JSON knowledge base of 1C platform API (v8.3.24)
   - `embeddings/` — vector embeddings via DeepInfra (Qwen3) stored in `sqlite-vec`; chunking, client, storage, engine
   - `knowledge_graph/` — metadata-level KG built from indexed configuration objects
   - `smart/` — metadata-aware code generators (queries, print forms, register movements) that read real metadata to produce syntactically correct BSL
3. **Tools** (`src/mcp_1c/tools/`) — thin MCP wrappers around engines. All inherit from `BaseTool` (`tools/base.py`), which adds input validation, rate limiting (opt-in via `MCP_RATE_LIMIT`), metrics, and consistent error formatting via the Template Method pattern.
4. **Server** (`src/mcp_1c/server.py`) — wires `ToolRegistry` and `PromptRegistry` to MCP `list_tools` / `call_tool` / `list_prompts` / `get_prompt` handlers; installs SIGINT/SIGTERM handlers that call `shutdown_engines()`.

### Singletons / shared state

- `MetadataEngine.get_instance()` — requires `initialize(config_path)` before use; owns SQLite cache and file watcher.
- `CodeEngine.get_instance()`, `KnowledgeGraphEngine.get_instance()`, `EmbeddingEngine.get_instance()`, `SmartGenerator.get_instance()` — all singletons created once in `ToolRegistry._register_all_tools()` and shared across tools.
- `PlatformEngine` — loaded once from static JSON in `engines/platform/data/`.
- `tool_metrics` (module-level in `tools/base.py`) — aggregates per-tool call counts, errors, and latency.

### Adding a new tool

1. Create a class inheriting `BaseTool` in the appropriate `tools/*_tools.py`.
2. Define `name`, `description`, and `input_schema` (or override `get_input_schema()`); implement `async def execute(self, arguments)`.
3. Register the instance in `ToolRegistry._register_all_tools()` (`src/mcp_1c/tools/registry.py`). Tools are grouped there by domain — metadata, code, query, pattern, template (MXL), platform, config, knowledge graph, embeddings, analysis, smart generation.

### Template data

Code generation templates are JSON files in `engines/templates/data/`:
`queries.json`, `handlers.json`, `movements.json`, `print_forms.json`, `api.json`. The smart generators (`engines/smart/`) layer real metadata on top of these templates.

### Prompts (Skills & Agents)

Skills (single-step `/1c-*` commands) and Agents (multi-step workflows) live in `src/mcp_1c/prompts/skills.py` and `prompts/agents.py`, both inheriting from `BasePrompt` (`prompts/base.py`) and registered via `PromptRegistry`. They emit MCP prompts that instruct Claude to call the appropriate tools — they are not tools themselves.

## Configuration

`src/mcp_1c/config.py` defines `AppConfig` with sub-models `ServerConfig`, `CacheConfig`, `WatcherConfig`, `EmbeddingConfig`. `get_config()` returns the global instance; `set_config_root(path)` sets the active 1C configuration directory at runtime.

Environment variables (all optional):

- `MCP_LOG_LEVEL`, `MCP_MAX_SEARCH_FILES`, `MCP_CACHE_TTL`, `MCP_MAX_CONCURRENT_PARSE`, `MCP_PARSE_WORKERS`, `MCP_MXL_CACHE_SIZE`
- `MCP_RATE_LIMIT` (calls/min; `0` disables)
- `MCP_EMBEDDING_API_KEY` (or `DEEPINFRA_API_KEY`), `MCP_EMBEDDING_API_URL`, `MCP_EMBEDDING_MODEL` — embeddings backend defaults to DeepInfra `Qwen/Qwen3-Embedding-8B` (4096-dim).

The metadata cache (`.mcp_1c_cache.db`) and embeddings DB (`.mcp_1c_embeddings.db`) are written **inside the 1C configuration directory**, not the repo. Both use SQLite WAL; the embeddings store uses the `sqlite-vec` extension.

## Testing

Tests use `pytest` with `pytest-asyncio`. `tests/conftest.py` provides a `mock_config_path` fixture that builds a complete fake 1C configuration tree on disk. Test layout: `tests/unit/`, `tests/integration/`, `tests/e2e/`, `tests/performance/`, `tests/security/`.
