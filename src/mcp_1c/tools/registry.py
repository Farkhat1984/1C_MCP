"""
Tool registry for managing MCP tools.

Implements Registry pattern for tool discovery and invocation. On
registration, every tool gets its ``required_scope`` populated from
:func:`mcp_1c.auth.default_tool_scopes` — that closes the RBAC loop:
JWT identity → scope check inside ``BaseTool._check_scope`` → tool
either runs or returns FORBIDDEN. Stdio (no identity) keeps the
permissive path; the scope check only fires when both sides opted in.
"""

from typing import Any

from mcp.types import Tool

from mcp_1c.auth import default_tool_scopes
from mcp_1c.tools.base import BaseTool
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)

# Cached once at module import — every ToolRegistry shares the same map.
_TOOL_SCOPES = default_tool_scopes()


class ToolRegistry:
    """
    Registry for MCP tools.

    Provides tool registration, discovery, and invocation.
    Uses lazy loading for tool instances.
    """

    def __init__(self) -> None:
        """Initialize registry and register all tools."""
        self._tools: dict[str, BaseTool] = {}
        self._register_all_tools()

    async def initialize(self) -> None:
        """Initialize async components if needed."""
        pass

    def _register_all_tools(self) -> None:
        """Register all available tools."""
        # Import tools here to avoid circular imports
        from mcp_1c.engines.bsp import BspEngine
        from mcp_1c.engines.code import CodeEngine
        from mcp_1c.engines.composition import CompositionEngine
        from mcp_1c.engines.embeddings import EmbeddingEngine
        from mcp_1c.engines.extensions import ExtensionEngine
        from mcp_1c.engines.forms import FormEngine
        from mcp_1c.engines.knowledge_graph import KnowledgeGraphEngine
        from mcp_1c.engines.metadata import MetadataEngine
        from mcp_1c.engines.runtime import RuntimeEngine
        from mcp_1c.engines.smart import SmartGenerator
        from mcp_1c.tools.analysis_tools import (
            CodeDeadCodeTool,
            ConfigCompareTool,
            ConfigRoleRightsTool,
            ConfigRolesTool,
        )
        from mcp_1c.tools.bsp_tools import (
            BspFindTool,
            BspHookTool,
            BspModulesTool,
            BspReviewTool,
        )
        from mcp_1c.tools.code_tools import (
            CodeCallGraphTool,
            CodeComplexityTool,
            CodeDependenciesTool,
            CodeFormatTool,
            CodeLintTool,
            CodeModuleTool,
            CodeProcedureTool,
            CodeValidateTool,
        )
        from mcp_1c.tools.composition_tools import (
            CompositionDatasetsTool,
            CompositionFieldsTool,
            CompositionGetTool,
            CompositionSettingsTool,
        )
        from mcp_1c.tools.config_tools import ConfigObjectsTool
        from mcp_1c.tools.diff_tools import (
            ConfigurationDiffTool,
            TestDataGenerateTool,
        )
        from mcp_1c.tools.embedding_tools import (
            EmbeddingIndexTool,
            EmbeddingSearchTool,
            EmbeddingSimilarTool,
            EmbeddingStatsTool,
        )
        from mcp_1c.tools.extension_tools import (
            ExtensionImpactTool,
            ExtensionListTool,
            ExtensionObjectsTool,
        )
        from mcp_1c.tools.form_tools import (
            FormAttributesTool,
            FormGetTool,
            FormHandlersTool,
        )
        from mcp_1c.tools.generate_tools import (
            GenerateApiTool,
            GenerateFormHandlerTool,
            GenerateHandlerTool,
            GenerateMovementTool,
            GeneratePrintTool,
            GenerateQueryTool,
            GenerateScheduledJobTool,
            GenerateSubscriptionTool,
        )
        from mcp_1c.tools.graph_tools import (
            GraphBuildTool,
            GraphCalleesTool,
            GraphCallersTool,
            GraphCodeReferencesTool,
            GraphImpactTool,
            GraphRelatedTool,
            GraphStatsTool,
        )
        from mcp_1c.tools.metadata_tools import (
            MetadataGetTool,
            MetadataInitTool,
            MetadataListTool,
            MetadataSearchTool,
        )
        from mcp_1c.tools.pattern_tools import (
            PatternApplyTool,
            PatternListTool,
            PatternSuggestTool,
        )
        from mcp_1c.tools.platform_tools import (
            PlatformGlobalContextTool,
            PlatformSearchTool,
        )
        from mcp_1c.tools.query_tools import (
            QueryOptimizeTool,
            QueryValidateTool,
        )
        from mcp_1c.tools.runtime_tools import (
            RuntimeDataTool,
            RuntimeEvalTool,
            RuntimeMethodTool,
            RuntimeQueryTool,
            RuntimeStatusTool,
        )
        from mcp_1c.tools.smart_tools import (
            SmartMovementTool,
            SmartPrintTool,
            SmartQueryTool,
        )
        from mcp_1c.tools.template_tools import (
            TemplateFindTool,
            TemplateGenerateFillCodeTool,
            TemplateGetTool,
        )

        # Create shared engine instances once
        metadata_engine = MetadataEngine.get_instance()
        code_engine = CodeEngine.get_instance()
        kg_engine = KnowledgeGraphEngine.get_instance()
        embedding_engine = EmbeddingEngine.get_instance()

        # Metadata tools (4)
        self.register(MetadataInitTool(metadata_engine))
        self.register(MetadataListTool(metadata_engine))
        self.register(MetadataGetTool(metadata_engine))
        self.register(MetadataSearchTool(metadata_engine))

        # Code tools (8)
        self.register(CodeModuleTool(code_engine))
        self.register(CodeProcedureTool(code_engine))
        self.register(CodeDependenciesTool(code_engine))
        self.register(CodeCallGraphTool(code_engine))
        self.register(CodeValidateTool(code_engine))
        self.register(CodeLintTool(code_engine))
        self.register(CodeFormatTool(code_engine))
        self.register(CodeComplexityTool(code_engine))

        # Query tools (2)
        self.register(QueryValidateTool())
        self.register(QueryOptimizeTool())

        # Pattern tools (3)
        self.register(PatternListTool())
        self.register(PatternApplyTool())
        self.register(PatternSuggestTool())

        # Template (MXL) tools (3)
        self.register(TemplateGetTool())
        self.register(TemplateGenerateFillCodeTool())
        self.register(TemplateFindTool())

        # Platform tools (2)
        self.register(PlatformSearchTool())
        self.register(PlatformGlobalContextTool())

        # Config tools (4 — 1 consolidated + 3 analysis)
        self.register(ConfigObjectsTool(metadata_engine))
        self.register(ConfigRolesTool(metadata_engine))
        self.register(ConfigRoleRightsTool(metadata_engine))
        self.register(ConfigCompareTool())

        # Knowledge Graph tools (4 metadata + 3 code-level)
        self.register(GraphBuildTool(kg_engine, metadata_engine, code_engine))
        self.register(GraphImpactTool(kg_engine))
        self.register(GraphRelatedTool(kg_engine))
        self.register(GraphStatsTool(kg_engine))
        self.register(GraphCallersTool(kg_engine))
        self.register(GraphCalleesTool(kg_engine))
        self.register(GraphCodeReferencesTool(kg_engine))

        # Embedding tools (4)
        self.register(EmbeddingIndexTool(embedding_engine, metadata_engine, code_engine))
        self.register(EmbeddingSearchTool(embedding_engine))
        self.register(EmbeddingSimilarTool(embedding_engine))
        self.register(EmbeddingStatsTool(embedding_engine))

        # Analysis tools (1)
        self.register(CodeDeadCodeTool(code_engine, metadata_engine))

        # Smart generation tools (3) — pull SmartGenerator into module
        # cache so the first tool call doesn't pay the singleton-init
        # latency. Tools themselves grab the same instance via
        # ``SmartGenerator.get_instance()``.
        SmartGenerator.get_instance()
        self.register(SmartQueryTool())
        self.register(SmartPrintTool())
        self.register(SmartMovementTool())

        # Generate tools (template-based, 8)
        self.register(GenerateQueryTool())
        self.register(GenerateHandlerTool())
        self.register(GeneratePrintTool())
        self.register(GenerateMovementTool())
        self.register(GenerateApiTool())
        self.register(GenerateFormHandlerTool())
        self.register(GenerateSubscriptionTool())
        self.register(GenerateScheduledJobTool())

        # Form tools (managed-form structure, 3)
        form_engine = FormEngine.get_instance()
        self.register(FormGetTool(form_engine, metadata_engine))
        self.register(FormHandlersTool(form_engine, metadata_engine))
        self.register(FormAttributesTool(form_engine, metadata_engine))

        # Composition tools (DataCompositionSchema / СКД, 4)
        composition_engine = CompositionEngine.get_instance()
        self.register(CompositionGetTool(composition_engine, metadata_engine))
        self.register(CompositionFieldsTool(composition_engine, metadata_engine))
        self.register(CompositionDatasetsTool(composition_engine, metadata_engine))
        self.register(CompositionSettingsTool(composition_engine, metadata_engine))

        # Extension tools (.cfe, 3)
        extension_engine = ExtensionEngine.get_instance()
        self.register(ExtensionListTool(extension_engine, metadata_engine))
        self.register(ExtensionObjectsTool(extension_engine, metadata_engine))
        self.register(ExtensionImpactTool(extension_engine, metadata_engine))

        # BSP knowledge tools (4)
        bsp_engine = BspEngine.get_instance()
        self.register(BspFindTool(bsp_engine))
        self.register(BspHookTool(bsp_engine))
        self.register(BspModulesTool(bsp_engine))
        self.register(BspReviewTool(bsp_engine))

        # Runtime tools (5) — operate against live 1C base via MCPBridge
        runtime_engine = RuntimeEngine.get_instance()
        self.register(RuntimeStatusTool(runtime_engine))
        self.register(RuntimeQueryTool(runtime_engine))
        self.register(RuntimeEvalTool(runtime_engine))
        self.register(RuntimeDataTool(runtime_engine))
        self.register(RuntimeMethodTool(runtime_engine))

        # Premium tools (2) — config diff & test data
        self.register(ConfigurationDiffTool())
        self.register(TestDataGenerateTool(metadata_engine))

        logger.info(f"Registered {len(self._tools)} tools")

    def register(self, tool: BaseTool) -> None:
        """
        Register a tool and bind its required scope from the canonical map.

        ``required_scope`` is set on the *instance* (not the class) so two
        registries can in principle hold the same class with different
        scopes — useful for multi-tenant policies down the line. Tools
        without an entry in :func:`default_tool_scopes` keep
        ``required_scope=None`` (permissive); the warning below catches
        the typical regression: someone added a tool but forgot the
        scope mapping.
        """
        if tool.name in self._tools:
            logger.warning(f"Tool '{tool.name}' already registered, overwriting")
        scope = _TOOL_SCOPES.get(tool.name)
        if scope is not None:
            tool.required_scope = scope
        elif tool.required_scope is None:
            logger.debug(
                f"Tool {tool.name!r} has no scope mapping; "
                "registered as unscoped (permissive)."
            )
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name} (scope={tool.required_scope})")

    def get(self, name: str) -> BaseTool | None:
        """
        Get tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None
        """
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        """
        List all registered tools.

        Returns:
            List of Tool definitions
        """
        return [tool.get_tool_definition() for tool in self._tools.values()]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """
        Call a tool by name.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            Tool execution result

        Raises:
            ValueError: If tool not found
        """
        tool = self.get(name)
        if tool is None:
            raise ValueError(f"Unknown tool: {name}")

        return await tool.run(arguments)
