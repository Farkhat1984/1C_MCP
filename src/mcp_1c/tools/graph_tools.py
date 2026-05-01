"""
Knowledge Graph tools for MCP-1C.

Provides tools for building and querying the metadata knowledge graph.
"""

from __future__ import annotations

from typing import Any, ClassVar

from mcp_1c.domain.graph import RelationshipType
from mcp_1c.engines.code import CodeEngine
from mcp_1c.engines.knowledge_graph.engine import KnowledgeGraphEngine
from mcp_1c.engines.metadata.engine import MetadataEngine
from mcp_1c.tools.base import BaseTool, ToolError


class GraphBuildTool(BaseTool):
    """Build or rebuild the metadata knowledge graph."""

    name: ClassVar[str] = "graph.build"
    description: ClassVar[str] = (
        "Построить (или перестроить) граф знаний из метаданных конфигурации. "
        "Анализирует все объекты метаданных, извлекает связи между ними "
        "(ссылки реквизитов, движения документов, подсистемы и т.д.). "
        "Если include_code=true (по умолчанию), дополнительно анализирует "
        "BSL-модули и добавляет рёбра уровня кода (вызовы процедур, "
        "ссылки на метаданные из кода, таблицы из запросов)."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "include_code": {
                "type": "boolean",
                "description": (
                    "Включать ли рёбра уровня кода (procedure_call, "
                    "code_metadata_reference). По умолчанию true."
                ),
                "default": True,
            },
        },
    }

    def __init__(
        self,
        kg_engine: KnowledgeGraphEngine,
        metadata_engine: MetadataEngine,
        code_engine: CodeEngine | None = None,
    ) -> None:
        super().__init__()
        self._kg_engine = kg_engine
        self._metadata_engine = metadata_engine
        self._code_engine = code_engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Build the knowledge graph."""
        if not self._metadata_engine.is_initialized:
            raise ToolError(
                "Метаданные не проиндексированы. Сначала вызовите metadata-init.",
                code="NOT_INITIALIZED",
            )

        include_code = arguments.get("include_code", True)
        code_engine = self._code_engine if include_code else None
        graph = await self._kg_engine.build(
            self._metadata_engine, code_engine=code_engine
        )
        stats = graph.stats()

        return {
            "status": "success",
            "message": "Граф знаний успешно построен",
            "include_code": include_code and code_engine is not None,
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
        """Run impact analysis.

        Augments the standard impact result with
        ``overridden_by_extensions`` — extensions that contribute an
        Adopted/Replaced object pointing at this node. Critical for 1С
        refactor decisions: editing a typical-config object that an
        extension has заимствовал must be done via Designer, not via
        the file the developer is looking at.
        """
        node_id = arguments["node_id"]
        depth = arguments.get("depth", 3)
        result = await self._kg_engine.get_impact(node_id, depth)
        if isinstance(result, dict):
            overrides = await self._collect_extension_overrides(node_id)
            if overrides:
                result["overridden_by_extensions"] = overrides
        return result

    async def _collect_extension_overrides(
        self, node_id: str
    ) -> list[dict[str, Any]]:
        """Find ExtensionObject nodes that adopt or replace ``node_id``.

        Walks incoming EXTENSION_ADOPTS and EXTENSION_REPLACES edges and
        returns a flat list ``[{extension, mode, object}]``. Empty list
        when nothing overrides the target.
        """
        from mcp_1c.domain.graph import RelationshipType

        graph = await self._kg_engine._load_or_fail()  # noqa: SLF001
        overrides: list[dict[str, Any]] = []
        for rel in (
            RelationshipType.EXTENSION_ADOPTS,
            RelationshipType.EXTENSION_REPLACES,
        ):
            for edge, neighbor in graph.get_related(
                node_id, relationship=rel, direction="incoming"
            ):
                overrides.append(
                    {
                        "extension": neighbor.metadata.get("extension", ""),
                        "mode": neighbor.metadata.get("mode", ""),
                        "object": neighbor.id,
                        "edge_label": edge.label,
                    }
                )
        return overrides


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
            except ValueError as exc:
                raise ToolError(
                    f"Неизвестный тип связи: {rel_str}",
                    code="INVALID_RELATIONSHIP",
                ) from exc

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

    async def execute(self, arguments: dict[str, Any]) -> Any:  # noqa: ARG002
        """Get graph stats."""
        return await self._kg_engine.get_stats()


# ─────────────────────────────────────────────────────────────────────────
# Code-level edges (Phase 1)
# ─────────────────────────────────────────────────────────────────────────


class GraphCallersTool(BaseTool):
    """Find every procedure that calls a given one.

    Walks ``PROCEDURE_CALL`` edges in the *incoming* direction. Cross-
    module call resolution is best-effort (see
    ``KnowledgeGraphEngine._resolve_global_procedure``) — ambiguous
    names produce no edge rather than a wrong edge. Same-module calls
    are deterministic.
    """

    name: ClassVar[str] = "graph-callers"
    description: ClassVar[str] = (
        "Найти все процедуры, вызывающие указанную. "
        "Работает по графу вызовов BSL — требует, чтобы граф был "
        "построен с code_engine. Идентификатор процедуры в формате "
        "'Тип.Имя.МодульныйТип.ИмяПроцедуры', например "
        "'CommonModule.ОбщегоНазначения.Module.СообщениеПользователю'."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "node_id": {
                "type": "string",
                "description": "Идентификатор процедуры в KG",
            },
        },
        "required": ["node_id"],
    }

    def __init__(self, kg_engine: KnowledgeGraphEngine) -> None:
        super().__init__()
        self._kg_engine = kg_engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        from mcp_1c.domain.graph import RelationshipType

        node_id = arguments["node_id"]
        graph = await self._kg_engine._load_or_fail()  # noqa: SLF001
        callers = [
            {
                "node_id": neighbor.id,
                "owner": neighbor.metadata.get("owner", ""),
                "name": neighbor.name,
                "line": edge.metadata.get("line"),
            }
            for edge, neighbor in graph.get_related(
                node_id,
                relationship=RelationshipType.PROCEDURE_CALL,
                direction="incoming",
            )
        ]
        return {"node_id": node_id, "count": len(callers), "callers": callers}


class GraphCalleesTool(BaseTool):
    """List every procedure called from a given one."""

    name: ClassVar[str] = "graph-callees"
    description: ClassVar[str] = (
        "Найти все процедуры, которые вызывает указанная процедура. "
        "Зеркально к graph-callers."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "node_id": {
                "type": "string",
                "description": "Идентификатор процедуры в KG",
            },
        },
        "required": ["node_id"],
    }

    def __init__(self, kg_engine: KnowledgeGraphEngine) -> None:
        super().__init__()
        self._kg_engine = kg_engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        from mcp_1c.domain.graph import RelationshipType

        node_id = arguments["node_id"]
        graph = await self._kg_engine._load_or_fail()  # noqa: SLF001
        callees = [
            {
                "node_id": neighbor.id,
                "owner": neighbor.metadata.get("owner", ""),
                "name": neighbor.name,
                "line": edge.metadata.get("line"),
            }
            for edge, neighbor in graph.get_related(
                node_id,
                relationship=RelationshipType.PROCEDURE_CALL,
                direction="outgoing",
            )
        ]
        return {"node_id": node_id, "count": len(callees), "callees": callees}


class GraphCodeReferencesTool(BaseTool):
    """Find every procedure that references a metadata object from BSL code.

    Aggregates two edge kinds: explicit metadata access
    (``Справочники.X``, ``CODE_METADATA_REFERENCE``) and queries that
    pull from the object's table (``CODE_QUERY_REFERENCE``).
    """

    name: ClassVar[str] = "graph-code-references"
    description: ClassVar[str] = (
        "Найти все процедуры, которые ссылаются на объект метаданных "
        "из кода — через Справочники.Х, ВЫБРАТЬ ИЗ Справочник.Х и т.п. "
        "Помогает оценить blast-radius при переименовании/удалении."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "node_id": {
                "type": "string",
                "description": (
                    "Идентификатор объекта метаданных, напр. 'Catalog.Номенклатура'"
                ),
            },
        },
        "required": ["node_id"],
    }

    def __init__(self, kg_engine: KnowledgeGraphEngine) -> None:
        super().__init__()
        self._kg_engine = kg_engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        from mcp_1c.domain.graph import RelationshipType

        node_id = arguments["node_id"]
        graph = await self._kg_engine._load_or_fail()  # noqa: SLF001
        references = []
        for rel in (
            RelationshipType.CODE_METADATA_REFERENCE,
            RelationshipType.CODE_QUERY_REFERENCE,
        ):
            for edge, neighbor in graph.get_related(
                node_id, relationship=rel, direction="incoming"
            ):
                references.append(
                    {
                        "procedure": neighbor.id,
                        "owner": neighbor.metadata.get("owner", ""),
                        "name": neighbor.name,
                        "kind": rel.value,
                        "line": edge.metadata.get("line"),
                        "label": edge.label,
                    }
                )
        return {
            "node_id": node_id,
            "count": len(references),
            "references": references,
        }
