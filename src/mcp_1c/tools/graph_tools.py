"""
Knowledge Graph tools for MCP-1C.

Provides tools for building and querying the metadata knowledge graph.
"""

from __future__ import annotations

from typing import Any, ClassVar

from mcp_1c.domain.graph import RelationshipType
from mcp_1c.engines.knowledge_graph.engine import KnowledgeGraphEngine
from mcp_1c.engines.metadata.engine import MetadataEngine
from mcp_1c.tools.base import BaseTool, ToolError


class GraphBuildTool(BaseTool):
    """Build or rebuild the metadata knowledge graph."""

    name: ClassVar[str] = "graph.build"
    description: ClassVar[str] = (
        "Построить (или перестроить) граф знаний из метаданных конфигурации. "
        "Анализирует все объекты метаданных, извлекает связи между ними "
        "(ссылки реквизитов, движения документов, подсистемы и т.д.) "
        "и сохраняет граф для последующих запросов."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {},
    }

    def __init__(
        self,
        kg_engine: KnowledgeGraphEngine,
        metadata_engine: MetadataEngine,
    ) -> None:
        super().__init__()
        self._kg_engine = kg_engine
        self._metadata_engine = metadata_engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Build the knowledge graph."""
        if not self._metadata_engine.is_initialized:
            raise ToolError(
                "Метаданные не проиндексированы. Сначала вызовите metadata-init.",
                code="NOT_INITIALIZED",
            )

        graph = await self._kg_engine.build(self._metadata_engine)
        stats = graph.stats()

        return {
            "status": "success",
            "message": "Граф знаний успешно построен",
            "statistics": stats,
        }


class GraphImpactTool(BaseTool):
    """Impact analysis: what depends on a given metadata object."""

    name: ClassVar[str] = "graph.impact"
    description: ClassVar[str] = (
        "Анализ влияния: какие объекты метаданных зависят от указанного. "
        "Показывает, что может сломаться при изменении объекта. "
        "Результат группируется по глубине зависимости."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "node_id": {
                "type": "string",
                "description": (
                    "Идентификатор объекта в формате 'Тип.Имя', "
                    "например 'Catalog.Номенклатура' или 'Document.РеализацияТоваров'"
                ),
            },
            "depth": {
                "type": "integer",
                "description": "Глубина анализа (по умолчанию 3)",
                "default": 3,
            },
        },
        "required": ["node_id"],
    }

    def __init__(self, kg_engine: KnowledgeGraphEngine) -> None:
        super().__init__()
        self._kg_engine = kg_engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Run impact analysis."""
        node_id = arguments["node_id"]
        depth = arguments.get("depth", 3)
        return await self._kg_engine.get_impact(node_id, depth)


class GraphRelatedTool(BaseTool):
    """Find related metadata objects."""

    name: ClassVar[str] = "graph.related"
    description: ClassVar[str] = (
        "Найти связанные объекты метаданных. "
        "Можно фильтровать по типу связи: attribute_reference, "
        "register_movement, subsystem_membership и др."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "node_id": {
                "type": "string",
                "description": "Идентификатор объекта, напр. 'Catalog.Контрагенты'",
            },
            "relationship": {
                "type": "string",
                "description": (
                    "Фильтр по типу связи (необязательно). Допустимые значения: "
                    "attribute_reference, tabular_reference, register_movement, "
                    "subsystem_membership, subsystem_hierarchy, based_on, produces, "
                    "dimension_type, resource_type, event_subscription, "
                    "form_ownership, module_ownership, defined_type_contains, "
                    "subscription_handler, scheduled_job_method, common_attribute_usage"
                ),
            },
        },
        "required": ["node_id"],
    }

    def __init__(self, kg_engine: KnowledgeGraphEngine) -> None:
        super().__init__()
        self._kg_engine = kg_engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Find related objects."""
        node_id = arguments["node_id"]
        rel_str = arguments.get("relationship")

        relationship: RelationshipType | None = None
        if rel_str:
            try:
                relationship = RelationshipType(rel_str)
            except ValueError:
                raise ToolError(
                    f"Неизвестный тип связи: {rel_str}",
                    code="INVALID_RELATIONSHIP",
                )

        related = await self._kg_engine.get_related(node_id, relationship)
        return {
            "node_id": node_id,
            "relationship_filter": rel_str,
            "count": len(related),
            "related": related,
        }


class GraphPathTool(BaseTool):
    """Find shortest path between two metadata objects."""

    name: ClassVar[str] = "graph.path"
    description: ClassVar[str] = (
        "Найти кратчайший путь связей между двумя объектами метаданных. "
        "Полезно для понимания, как объекты связаны друг с другом."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "Начальный объект, напр. 'Catalog.Номенклатура'",
            },
            "target": {
                "type": "string",
                "description": "Конечный объект, напр. 'Document.РеализацияТоваров'",
            },
        },
        "required": ["source", "target"],
    }

    def __init__(self, kg_engine: KnowledgeGraphEngine) -> None:
        super().__init__()
        self._kg_engine = kg_engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Find path between objects."""
        source = arguments["source"]
        target = arguments["target"]

        path = await self._kg_engine.find_path(source, target)
        return {
            "source": source,
            "target": target,
            "path_length": len(path),
            "path": path,
            "connected": len(path) > 0,
        }


class GraphContextTool(BaseTool):
    """Get full context for a metadata object (all relationships)."""

    name: ClassVar[str] = "graph.context"
    description: ClassVar[str] = (
        "Получить полный контекст объекта метаданных: "
        "все входящие и исходящие связи, соседние объекты. "
        "Дает полную картину роли объекта в конфигурации."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "node_id": {
                "type": "string",
                "description": "Идентификатор объекта, напр. 'Document.ПоступлениеТоваров'",
            },
        },
        "required": ["node_id"],
    }

    def __init__(self, kg_engine: KnowledgeGraphEngine) -> None:
        super().__init__()
        self._kg_engine = kg_engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Get object context."""
        node_id = arguments["node_id"]
        return await self._kg_engine.get_object_context(node_id)


class GraphStatsTool(BaseTool):
    """Get knowledge graph statistics."""

    name: ClassVar[str] = "graph.stats"
    description: ClassVar[str] = (
        "Получить статистику графа знаний: количество узлов, ребер, "
        "распределение по типам объектов и типам связей."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {},
    }

    def __init__(self, kg_engine: KnowledgeGraphEngine) -> None:
        super().__init__()
        self._kg_engine = kg_engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Get graph stats."""
        return await self._kg_engine.get_stats()
