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
        self._register_all_tools()

    async def initialize(self) -> None:
        """Initialize async components if needed."""
        pass

    def _register_all_tools(self) -> None:
        """Register all available tools."""
        # Import tools here to avoid circular imports
        from mcp_1c.engines.code import CodeEngine
        from mcp_1c.engines.embeddings import EmbeddingEngine
        from mcp_1c.engines.knowledge_graph import KnowledgeGraphEngine
        from mcp_1c.engines.smart import SmartGenerator
        from mcp_1c.engines.metadata import MetadataEngine
        from mcp_1c.tools.smart_tools import (
            SmartMovementTool,
            SmartPrintTool,
            SmartQueryTool,
        )
        from mcp_1c.tools.analysis_tools import (
            CodeDeadCodeTool,
            ConfigCompareTool,
            ConfigRoleRightsTool,
            ConfigRolesTool,
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
        from mcp_1c.tools.config_tools import ConfigObjectsTool
        from mcp_1c.tools.embedding_tools import (
            EmbeddingIndexTool,
            EmbeddingSearchTool,
            EmbeddingSimilarTool,
            EmbeddingStatsTool,
        )
        from mcp_1c.tools.graph_tools import (
            GraphBuildTool,
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

        # Knowledge Graph tools (4)
        self.register(GraphBuildTool(kg_engine, metadata_engine))
        self.register(GraphImpactTool(kg_engine))
        self.register(GraphRelatedTool(kg_engine))
        self.register(GraphStatsTool(kg_engine))

        # Embedding tools (4)
        self.register(EmbeddingIndexTool(embedding_engine, metadata_engine, code_engine))
        self.register(EmbeddingSearchTool(embedding_engine))
        self.register(EmbeddingSimilarTool(embedding_engine))
        self.register(EmbeddingStatsTool(embedding_engine))

        # Analysis tools (1)
        self.register(CodeDeadCodeTool(code_engine, metadata_engine))

        # Smart generation tools (3)
        smart_generator = SmartGenerator.get_instance()
        self.register(SmartQueryTool())
        self.register(SmartPrintTool())
        self.register(SmartMovementTool())

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
