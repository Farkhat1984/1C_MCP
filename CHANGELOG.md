# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added (Phase 1–9)
- **Forms (Phase 2):** parse Form.xml content (elements, attributes, commands, handlers). Tools: `form-get`, `form-handlers`, `form-attributes`.
- **DataCompositionSchema / СКД (Phase 3):** parse report schemas (data sets, fields, parameters, resources, setting variants). Tools: `composition-get/fields/datasets/settings`.
- **Configuration extensions (Phase 4):** discover and inspect .cfe extensions. Tools: `extension-list/objects/impact`.
- **BSP knowledge base (Phase 5):** static catalog of top-30 BSP modules, hooks, patterns. Tools: `bsp-find/hook/modules/review`.
- **Runtime via 1С HTTP-service (Phase 6):** Python client + tools for live-base interaction (`runtime-status/query/eval/data/method`). Requires the 1С-side `MCPBridge.cfe` extension; `docs/runtime-setup.md` documents the contract.
- **Bearer auth + safer defaults (Phase 8):** `MCP_AUTH_TOKEN`/`MCP_AUTH_TOKENS`, default bind `127.0.0.1`. Server refuses to start on a public host without an auth token.
- **Per-engine /health:** reports readiness of metadata, KG, embeddings, runtime.
- **Premium tools (Phase 9):** `diff-configurations`, `test-data-generate`.
- **Per-user cache root (Phase 1):** SQLite cache and embeddings DB now go to `~/.cache/mcp-1c/<id>/` (or `%LOCALAPPDATA%\mcp-1c\` on Windows). Override via `MCP_CACHE_DIR`. Legacy DBs in the config folder are still picked up.
- **Local embeddings backend (Phase 1):** `MCP_EMBEDDING_BACKEND=local` uses `sentence-transformers` and works without an API key. Auto-selected when no `MCP_EMBEDDING_API_KEY` is set.
- **Optional `[local-embeddings]` extras** in `pyproject.toml` (sentence-transformers).
- **Setup docs:** `docs/setup/claude-desktop.md`, `docs/troubleshooting.md`, `docs/runtime-setup.md`.

### Changed (BREAKING)
- Tool naming consolidated: registry exposes 67 tools after Phase 1–9 (was 38, +8 generate-* restored, +21 new categories).
- Granular metadata tools (`metadata-attributes`, `metadata-forms`, `metadata-templates`, `metadata-registers`, `metadata-references`, `metadata-tree`) merged into `metadata-get` (returns the full bundle in one call).
- Granular query (`query-parse`, `query-tables`, `query-explain`), pattern (`pattern-get`, `pattern-search`), template (`template-parameters`, `template-areas`), platform (`platform-method`, `platform-type`, `platform-event`) and config (`config-options`, `config-constants`, `config-scheduled_jobs`, `config-event_subscriptions`, `config-exchanges`, `config-http_services`) tools merged into a smaller set of consolidated tools (`platform-search`, `config-objects`, etc.).
- Code introspection tools `code-resolve`, `code-usages`, `code-analyze` removed — substitute with `embedding.search` + grep, `code-module`, `code-complexity` respectively.

### Added
- 8 `generate-*` tools restored to registry (`tools/generate_tools.py` was previously not wired).
- Test guard `tests/unit/test_prompts_consistency.py` — fails CI if any Skill or Agent references a tool that is not registered.
- Skills/Agents prompt text rewritten to use only registered tools; calls to renamed/removed tools fixed.

### Fixed
- Skills (`/1c-query`, `/1c-metadata`, `/1c-handler`, `/1c-print`, `/1c-usages`, `/1c-validate`, `/1c-deps`, `/1c-movement`, `/1c-format`, `/1c-explain`) and Agents (`/1c-explore`, `/1c-implement`, `/1c-debug`, `/1c-configure`) now reference real tools — they were broken since the 38-tool consolidation.

## [0.1.0] - 2024-01-XX

### Added

#### Core
- MCP Server with stdio transport
- Tool registry with automatic registration
- Configuration management
- Logging system

#### Metadata Engine
- XML parser for Configuration.xml and metadata objects
- Metadata indexer with incremental updates
- SQLite cache with WAL mode and LRU caching
- File watcher for automatic reindexing
- Parallel indexing for large configurations

#### Code Engine
- BSL file reader
- BSL parser with regex-based extraction
- Procedure/function extraction
- Region and directive parsing
- Dependency graph builder
- BSL Language Server integration

#### Template Engine
- Template loader from JSON
- Placeholder substitution
- Conditional blocks and loops
- Query parser and validator
- 39 code templates

#### MXL Engine
- MXL/XML parser
- Area and parameter extraction
- Fill code generator

#### Platform Knowledge Base
- Global context (70+ methods)
- Platform types (12 types)
- Object events (24 events)

#### Tools
- 10 metadata tools
- 11 code tools
- 8 generate tools
- 5 query tools
- 5 pattern tools
- 5 template tools
- 5 platform tools
- 6 config tools

#### Skills
- `/1c-query` - Query generation
- `/1c-metadata` - Metadata info
- `/1c-handler` - Handler generation
- `/1c-print` - Print form generation
- `/1c-usages` - Usage search
- `/1c-validate` - Syntax validation
- `/1c-deps` - Dependency graph
- `/1c-movement` - Register movement generation
- `/1c-format` - Code formatting
- `/1c-explain` - Code explanation

#### Agents
- `1c-explore` - Configuration exploration
- `1c-implement` - Feature implementation
- `1c-debug` - Debugging and diagnostics
- `1c-configure` - Standard configuration setup

### Performance
- SQLite WAL mode
- In-memory LRU cache
- Parallel indexing
- Batch database operations
- Hash-based incremental updates

## [Unreleased]

### Planned
- Runtime Engine (COM Connector, HTTP Client)
- Extended BSL AST parser
- More code templates
- Integration tests with real configurations
