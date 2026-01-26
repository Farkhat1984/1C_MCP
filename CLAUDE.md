# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MCP Server for 1C:Enterprise platform - provides metadata analysis, code parsing, and code generation capabilities for 1C configurations. The server exposes tools and prompts via the Model Context Protocol (MCP).

## Commands

```bash
# Install dependencies (development)
pip install -e ".[dev]"

# Run tests
pytest
pytest tests/unit/test_parser.py          # single file
pytest tests/unit/test_parser.py::test_name  # single test
pytest --cov=mcp_1c                        # with coverage

# Linting and formatting
ruff check .                               # lint
ruff check --fix .                         # lint with autofix
mypy src/mcp_1c                            # type checking
black --check .                            # format check
black .                                    # format

# Run the server
mcp-1c
```

## Architecture

### Core Pattern: Engine → Tool → Registry

The codebase follows a layered architecture:

1. **Domain Models** (`src/mcp_1c/domain/`) - Pydantic models for metadata, code, templates, MXL spreadsheets, and platform types
2. **Engines** (`src/mcp_1c/engines/`) - Core logic for each domain:
   - `metadata/` - XML parsing, SQLite caching, file watching, incremental indexing
   - `code/` - BSL parser, dependency analysis, BSL Language Server integration
   - `templates/` - Code generation from JSON template definitions
   - `mxl/` - Spreadsheet template parsing
   - `platform/` - Static JSON knowledge base of 1C platform API (v8.3.24)
3. **Tools** (`src/mcp_1c/tools/`) - MCP tool implementations that wrap engines
4. **Server** (`src/mcp_1c/server.py`) - MCP server setup with ToolRegistry and PromptRegistry

### Adding New Tools

1. Create a tool class inheriting from `BaseTool` in appropriate `*_tools.py` file
2. Define `name`, `description`, and `input_schema` class variables
3. Implement `async def execute(self, arguments: dict) -> Any`
4. Register in `ToolRegistry._register_all_tools()`

```python
class MyTool(BaseTool):
    name = "my.tool"
    description = "Tool description"
    input_schema = {"type": "object", "properties": {...}, "required": [...]}

    async def execute(self, arguments: dict[str, Any]) -> Any:
        # Tool logic
        return result
```

### Key Singletons

- `MetadataEngine.get_instance()` - Singleton for metadata operations, requires `initialize()` with config path
- `PlatformEngine` - Loaded once with static JSON data from `engines/platform/data/`
- `ToolRegistry` - Created once in `server.py`, registers all tools at startup

### Template Data

Code generation templates are JSON files in `engines/templates/data/`:
- `queries.json` - SQL query templates
- `handlers.json` - Event handler templates
- `movements.json` - Register movement templates
- `print_forms.json` - Print form templates
- `api.json` - API method templates

### Prompts/Skills

Skills (`/1c-*` commands) and agents are defined in `src/mcp_1c/prompts/` and registered via `PromptRegistry`. They provide guided workflows for common 1C development tasks.

## Testing

Tests use pytest-asyncio. Mock 1C configuration structures are created in `conftest.py` with `mock_config_path` fixture providing a complete test configuration.

## Language Notes

- The project targets 1C:Enterprise developers (Russian-speaking audience)
- Object names, comments in code examples, and documentation are in Russian
- BSL (Built-in Scripting Language) is the 1C programming language
