# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
