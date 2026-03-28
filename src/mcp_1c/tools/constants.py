"""
Constants for MCP tool names.

Single source of truth for all tool name strings used across the codebase.
Prevents typos and enables IDE refactoring when tool names change.
"""


class ToolNames:
    """Registry of all MCP tool name constants."""

    # Metadata tools
    METADATA_INIT = "metadata-init"
    METADATA_LIST = "metadata-list"
    METADATA_GET = "metadata-get"
    METADATA_SEARCH = "metadata-search"
    METADATA_TREE = "metadata-tree"
    METADATA_ATTRIBUTES = "metadata-attributes"
    METADATA_FORMS = "metadata-forms"
    METADATA_TEMPLATES = "metadata-templates"
    METADATA_REGISTERS = "metadata-registers"
    METADATA_REFERENCES = "metadata-references"

    # Code tools
    CODE_MODULE = "code-module"
    CODE_PROCEDURE = "code-procedure"
    CODE_RESOLVE = "code-resolve"
    CODE_USAGES = "code-usages"
    CODE_DEPENDENCIES = "code-dependencies"
    CODE_ANALYZE = "code-analyze"
    CODE_CALLGRAPH = "code-callgraph"
    CODE_VALIDATE = "code-validate"
    CODE_LINT = "code-lint"
    CODE_FORMAT = "code-format"
    CODE_COMPLEXITY = "code-complexity"

    # Generate tools
    GENERATE_QUERY = "generate-query"
    GENERATE_HANDLER = "generate-handler"
    GENERATE_PRINT = "generate-print"
    GENERATE_MOVEMENT = "generate-movement"
    GENERATE_API = "generate-api"
    GENERATE_FORM_HANDLER = "generate-form_handler"
    GENERATE_SUBSCRIPTION = "generate-subscription"
    GENERATE_SCHEDULED_JOB = "generate-scheduled_job"

    # Query tools
    QUERY_PARSE = "query-parse"
    QUERY_VALIDATE = "query-validate"
    QUERY_OPTIMIZE = "query-optimize"
    QUERY_EXPLAIN = "query-explain"
    QUERY_TABLES = "query-tables"

    # Pattern tools
    PATTERN_LIST = "pattern-list"
    PATTERN_GET = "pattern-get"
    PATTERN_APPLY = "pattern-apply"
    PATTERN_SUGGEST = "pattern-suggest"
    PATTERN_SEARCH = "pattern-search"

    # Template (MXL) tools
    TEMPLATE_GET = "template-get"
    TEMPLATE_PARAMETERS = "template-parameters"
    TEMPLATE_AREAS = "template-areas"
    TEMPLATE_GENERATE_FILL_CODE = "template-generate_fill_code"
    TEMPLATE_FIND = "template-find"

    # Platform knowledge base tools
    PLATFORM_METHOD = "platform-method"
    PLATFORM_TYPE = "platform-type"
    PLATFORM_EVENT = "platform-event"
    PLATFORM_SEARCH = "platform-search"
    PLATFORM_GLOBAL_CONTEXT = "platform-global_context"

    # Config tools
    CONFIG_OPTIONS = "config-options"
    CONFIG_CONSTANTS = "config-constants"
    CONFIG_SCHEDULED_JOBS = "config-scheduled_jobs"
    CONFIG_EVENT_SUBSCRIPTIONS = "config-event_subscriptions"
    CONFIG_EXCHANGES = "config-exchanges"
    CONFIG_HTTP_SERVICES = "config-http_services"

    # Smart generation tools
    SMART_QUERY = "smart-query"
    SMART_PRINT = "smart-print"
    SMART_MOVEMENT = "smart-movement"
