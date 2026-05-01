"""
Constants for MCP tool names.

Single source of truth for the tool name strings used across prompts and code.
Mirrors the registrations in `tools/registry.py`. Adding a constant here without
registering the underlying tool is caught by `tests/unit/test_prompts_consistency.py`.
"""


class ToolNames:
    """Registry of MCP tool name constants — keep in sync with ToolRegistry."""

    # Metadata
    METADATA_INIT = "metadata-init"
    METADATA_LIST = "metadata-list"
    METADATA_GET = "metadata-get"
    METADATA_SEARCH = "metadata-search"

    # Code
    CODE_MODULE = "code-module"
    CODE_PROCEDURE = "code-procedure"
    CODE_DEPENDENCIES = "code-dependencies"
    CODE_CALLGRAPH = "code-callgraph"
    CODE_VALIDATE = "code-validate"
    CODE_LINT = "code-lint"
    CODE_FORMAT = "code-format"
    CODE_COMPLEXITY = "code-complexity"
    CODE_DEAD_CODE = "code-dead-code"

    # Query
    QUERY_VALIDATE = "query-validate"
    QUERY_OPTIMIZE = "query-optimize"

    # Pattern
    PATTERN_LIST = "pattern-list"
    PATTERN_APPLY = "pattern-apply"
    PATTERN_SUGGEST = "pattern-suggest"

    # Template (MXL)
    TEMPLATE_GET = "template-get"
    TEMPLATE_GENERATE_FILL_CODE = "template-generate_fill_code"
    TEMPLATE_FIND = "template-find"

    # Platform knowledge base
    PLATFORM_SEARCH = "platform-search"
    PLATFORM_GLOBAL_CONTEXT = "platform-global_context"

    # Config
    CONFIG_OBJECTS = "config-objects"
    CONFIG_ROLES = "config-roles"
    CONFIG_ROLE_RIGHTS = "config-role-rights"
    CONFIG_COMPARE = "config-compare"

    # Knowledge graph
    GRAPH_BUILD = "graph.build"
    GRAPH_IMPACT = "graph.impact"
    GRAPH_RELATED = "graph.related"
    GRAPH_STATS = "graph.stats"

    # Embeddings
    EMBEDDING_INDEX = "embedding.index"
    EMBEDDING_SEARCH = "embedding.search"
    EMBEDDING_SIMILAR = "embedding.similar"
    EMBEDDING_STATS = "embedding.stats"

    # Smart generation (metadata-aware)
    SMART_QUERY = "smart-query"
    SMART_PRINT = "smart-print"
    SMART_MOVEMENT = "smart-movement"

    # Forms (managed forms — Form.xml content)
    FORM_GET = "form-get"
    FORM_HANDLERS = "form-handlers"
    FORM_ATTRIBUTES = "form-attributes"

    # Composition (DataCompositionSchema / СКД)
    COMPOSITION_GET = "composition-get"
    COMPOSITION_FIELDS = "composition-fields"
    COMPOSITION_DATASETS = "composition-datasets"
    COMPOSITION_SETTINGS = "composition-settings"

    # Extensions (.cfe)
    EXTENSION_LIST = "extension-list"
    EXTENSION_OBJECTS = "extension-objects"
    EXTENSION_IMPACT = "extension-impact"

    # BSP knowledge base
    BSP_FIND = "bsp-find"
    BSP_HOOK = "bsp-hook"
    BSP_MODULES = "bsp-modules"
    BSP_REVIEW = "bsp-review"

    # Runtime — talks to live 1C base via MCPBridge HTTP service
    RUNTIME_STATUS = "runtime-status"
    RUNTIME_QUERY = "runtime-query"
    RUNTIME_EVAL = "runtime-eval"
    RUNTIME_DATA = "runtime-data"
    RUNTIME_METHOD = "runtime-method"

    # Premium tools (Phase 9)
    DIFF_CONFIGURATIONS = "diff-configurations"
    TEST_DATA_GENERATE = "test-data-generate"

    # Generate (template-based)
    GENERATE_QUERY = "generate-query"
    GENERATE_HANDLER = "generate-handler"
    GENERATE_PRINT = "generate-print"
    GENERATE_MOVEMENT = "generate-movement"
    GENERATE_API = "generate-api"
    GENERATE_FORM_HANDLER = "generate-form_handler"
    GENERATE_SUBSCRIPTION = "generate-subscription"
    GENERATE_SCHEDULED_JOB = "generate-scheduled_job"
