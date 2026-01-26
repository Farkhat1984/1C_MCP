"""
Tool registry for managing MCP tools.

Implements Registry pattern for tool discovery and invocation.
"""

from typing import Any

from mcp.types import Tool

from mcp_1c.tools.base import BaseTool
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


class ToolRegistry:
    """
    Registry for MCP tools.

    Provides tool registration, discovery, and invocation.
    Uses lazy loading for tool instances.
    """

    def __init__(self) -> None:
        """Initialize registry and register all tools."""
        self._tools: dict[str, BaseTool] = {}
        self._platform_engine: Any = None
        self._register_all_tools()

    async def initialize(self) -> None:
        """Initialize async components (platform engine, etc.)."""
        if self._platform_engine:
            await self._platform_engine.initialize()
            logger.info("Platform engine initialized")

    def _register_all_tools(self) -> None:
        """Register all available tools."""
        # Import tools here to avoid circular imports
        from mcp_1c.tools.metadata_tools import (
            MetadataInitTool,
            MetadataListTool,
            MetadataGetTool,
            MetadataSearchTool,
            MetadataTreeTool,
            MetadataAttributesTool,
            MetadataFormsTool,
            MetadataTemplatesTool,
            MetadataRegistersTool,
            MetadataReferencesTool,
        )
        from mcp_1c.tools.code_tools import (
            CodeAnalyzeTool,
            CodeCallGraphTool,
            CodeComplexityTool,
            CodeDependenciesTool,
            CodeFormatTool,
            CodeLintTool,
            CodeModuleTool,
            CodeProcedureTool,
            CodeResolveTool,
            CodeUsagesTool,
            CodeValidateTool,
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
        from mcp_1c.tools.query_tools import (
            QueryExplainTool,
            QueryOptimizeTool,
            QueryParseTool,
            QueryTablesTool,
            QueryValidateTool,
        )
        from mcp_1c.tools.pattern_tools import (
            PatternApplyTool,
            PatternGetTool,
            PatternListTool,
            PatternSearchTool,
            PatternSuggestTool,
        )
        from mcp_1c.tools.template_tools import (
            TemplateGetTool,
            TemplateParametersTool,
            TemplateAreasTool,
            TemplateGenerateFillCodeTool,
            TemplateFindTool,
        )
        from mcp_1c.tools.platform_tools import (
            PlatformMethodTool,
            PlatformTypeTool,
            PlatformEventTool,
            PlatformSearchTool,
            PlatformGlobalContextTool,
        )
        from mcp_1c.tools.config_tools import (
            ConfigOptionsTool,
            ConfigConstantsTool,
            ConfigScheduledJobsTool,
            ConfigEventSubscriptionsTool,
            ConfigExchangesTool,
            ConfigHttpServicesTool,
        )
        from mcp_1c.engines.platform import PlatformEngine

        # Metadata tools
        self.register(MetadataInitTool())
        self.register(MetadataListTool())
        self.register(MetadataGetTool())
        self.register(MetadataSearchTool())
        self.register(MetadataTreeTool())
        self.register(MetadataAttributesTool())
        self.register(MetadataFormsTool())
        self.register(MetadataTemplatesTool())
        self.register(MetadataRegistersTool())
        self.register(MetadataReferencesTool())

        # Code tools (Phase 1)
        self.register(CodeModuleTool())
        self.register(CodeProcedureTool())
        self.register(CodeResolveTool())
        self.register(CodeUsagesTool())

        # Code tools (Phase 2 - Extended analysis)
        self.register(CodeDependenciesTool())
        self.register(CodeAnalyzeTool())
        self.register(CodeCallGraphTool())

        # Code tools (Phase 2.3 - BSL LS integration)
        self.register(CodeValidateTool())
        self.register(CodeLintTool())
        self.register(CodeFormatTool())
        self.register(CodeComplexityTool())

        # Generate tools (Phase 3)
        self.register(GenerateQueryTool())
        self.register(GenerateHandlerTool())
        self.register(GeneratePrintTool())
        self.register(GenerateMovementTool())
        self.register(GenerateApiTool())
        self.register(GenerateFormHandlerTool())
        self.register(GenerateSubscriptionTool())
        self.register(GenerateScheduledJobTool())

        # Query tools (Phase 3)
        self.register(QueryParseTool())
        self.register(QueryValidateTool())
        self.register(QueryOptimizeTool())
        self.register(QueryExplainTool())
        self.register(QueryTablesTool())

        # Pattern tools (Phase 3)
        self.register(PatternListTool())
        self.register(PatternGetTool())
        self.register(PatternApplyTool())
        self.register(PatternSuggestTool())
        self.register(PatternSearchTool())

        # Template (MXL) tools (Phase 4)
        self.register(TemplateGetTool())
        self.register(TemplateParametersTool())
        self.register(TemplateAreasTool())
        self.register(TemplateGenerateFillCodeTool())
        self.register(TemplateFindTool())

        # Platform tools (Phase 4 - Knowledge Base)
        self._platform_engine = PlatformEngine()
        self.register(PlatformMethodTool(self._platform_engine))
        self.register(PlatformTypeTool(self._platform_engine))
        self.register(PlatformEventTool(self._platform_engine))
        self.register(PlatformSearchTool(self._platform_engine))
        self.register(PlatformGlobalContextTool(self._platform_engine))

        # Config tools (Phase 4 - Configuration objects)
        self.register(ConfigOptionsTool())
        self.register(ConfigConstantsTool())
        self.register(ConfigScheduledJobsTool())
        self.register(ConfigEventSubscriptionsTool())
        self.register(ConfigExchangesTool())
        self.register(ConfigHttpServicesTool())

        logger.info(f"Registered {len(self._tools)} tools")

    def register(self, tool: BaseTool) -> None:
        """
        Register a tool.

        Args:
            tool: Tool instance to register
        """
        if tool.name in self._tools:
            logger.warning(f"Tool '{tool.name}' already registered, overwriting")
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

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
