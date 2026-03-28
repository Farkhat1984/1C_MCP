"""
Knowledge Graph Engine.

Builds a metadata-level knowledge graph by extracting relationships
between 1C:Enterprise configuration objects from their attribute types,
register records, subsystem membership, and other structural metadata.
"""

from __future__ import annotations

import re
from collections import deque

from mcp_1c.config import get_config
from mcp_1c.domain.graph import (
    GraphEdge,
    GraphNode,
    KnowledgeGraph,
    RelationshipType,
)
from mcp_1c.domain.metadata import MetadataObject, MetadataType, Subsystem
from mcp_1c.engines.knowledge_graph.storage import GraphStorage
from mcp_1c.engines.metadata.engine import MetadataEngine
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)

# ── Russian type-prefix → MetadataType mapping ──────────────────────────────

TYPE_PREFIX_MAP: dict[str, str] = {
    # Russian type prefixes (legacy format)
    "СправочникСсылка": "Catalog",
    "ДокументСсылка": "Document",
    "ПеречислениеСсылка": "Enum",
    "ПланВидовХарактеристикСсылка": "ChartOfCharacteristicTypes",
    "ПланСчетовСсылка": "ChartOfAccounts",
    "ПланВидовРасчетаСсылка": "ChartOfCalculationTypes",
    "БизнесПроцессСсылка": "BusinessProcess",
    "ЗадачаСсылка": "Task",
    "ПланОбменаСсылка": "ExchangePlan",
    "ОпределяемыйТипСсылка": "DefinedType",
    # English cfg: prefixes (Configurator export format)
    "cfg:CatalogRef": "Catalog",
    "cfg:DocumentRef": "Document",
    "cfg:EnumRef": "Enum",
    "cfg:ChartOfCharacteristicTypesRef": "ChartOfCharacteristicTypes",
    "cfg:ChartOfAccountsRef": "ChartOfAccounts",
    "cfg:ChartOfCalculationTypesRef": "ChartOfCalculationTypes",
    "cfg:BusinessProcessRef": "BusinessProcess",
    "cfg:TaskRef": "Task",
    "cfg:ExchangePlanRef": "ExchangePlan",
    "cfg:InformationRegisterRecordKey": "InformationRegister",
    "cfg:AccumulationRegisterRecordKey": "AccumulationRegister",
    "cfg:AccountingRegisterRecordKey": "AccountingRegister",
    "cfg:CalculationRegisterRecordKey": "CalculationRegister",
}

# ── Source-object prefix → MetadataType for EventSubscription ────────────

_SOURCE_OBJECT_PREFIX_MAP: dict[str, str] = {
    "DocumentObject": "Document",
    "CatalogObject": "Catalog",
    "InformationRegisterRecordSet": "InformationRegister",
    "AccumulationRegisterRecordSet": "AccumulationRegister",
    "ExchangePlanObject": "ExchangePlan",
    "BusinessProcessObject": "BusinessProcess",
    "TaskObject": "Task",
    "ChartOfCharacteristicTypesObject": "ChartOfCharacteristicTypes",
    "ChartOfAccountsObject": "ChartOfAccounts",
    "ReportObject": "Report",
    "DataProcessorObject": "DataProcessor",
    # Russian equivalents
    "ДокументОбъект": "Document",
    "СправочникОбъект": "Catalog",
    "РегистрСведенийНаборЗаписей": "InformationRegister",
    "РегистрНакопленияНаборЗаписей": "AccumulationRegister",
    "ПланОбменаОбъект": "ExchangePlan",
    "БизнесПроцессОбъект": "BusinessProcess",
    "ЗадачаОбъект": "Task",
    "ПланВидовХарактеристикОбъект": "ChartOfCharacteristicTypes",
    "ПланСчетовОбъект": "ChartOfAccounts",
    "ОтчетОбъект": "Report",
    "ОбработкаОбъект": "DataProcessor",
}

# Regex to match type strings like "СправочникСсылка.Номенклатура"
# Rebuilt dynamically from TYPE_PREFIX_MAP keys (longest-first for correct matching)
_TYPE_REF_PATTERN = re.compile(
    r"(" + "|".join(
        re.escape(k) for k in sorted(TYPE_PREFIX_MAP, key=len, reverse=True)
    ) + r")\.(\w+)"
)

# Register type name mapping (used when extracting register_records)
_REGISTER_TYPE_PREFIXES: dict[str, str] = {
    "РегистрНакопления": "AccumulationRegister",
    "РегистрСведений": "InformationRegister",
    "РегистрБухгалтерии": "AccountingRegister",
    "РегистрРасчета": "CalculationRegister",
    "AccumulationRegister": "AccumulationRegister",
    "InformationRegister": "InformationRegister",
    "AccountingRegister": "AccountingRegister",
    "CalculationRegister": "CalculationRegister",
}

# Metadata types that carry objects worth graphing
_GRAPHABLE_TYPES: list[MetadataType] = [
    MetadataType.CATALOG,
    MetadataType.DOCUMENT,
    MetadataType.ENUM,
    MetadataType.CHART_OF_CHARACTERISTIC_TYPES,
    MetadataType.CHART_OF_ACCOUNTS,
    MetadataType.CHART_OF_CALCULATION_TYPES,
    MetadataType.EXCHANGE_PLAN,
    MetadataType.BUSINESS_PROCESS,
    MetadataType.TASK,
    MetadataType.INFORMATION_REGISTER,
    MetadataType.ACCUMULATION_REGISTER,
    MetadataType.ACCOUNTING_REGISTER,
    MetadataType.CALCULATION_REGISTER,
    MetadataType.REPORT,
    MetadataType.DATA_PROCESSOR,
    MetadataType.CONSTANT,
    MetadataType.COMMON_MODULE,
    MetadataType.EVENT_SUBSCRIPTION,
    MetadataType.DEFINED_TYPE,
    MetadataType.COMMON_ATTRIBUTE,
    MetadataType.SCHEDULED_JOB,
]


def _parse_type_references(type_str: str) -> list[str]:
    """Extract ALL metadata node ids from a 1C type string.

    A composite type may contain multiple references, e.g.
    "СправочникСсылка.Номенклатура, ДокументСсылка.Заказ".

    Returns:
        List of node id strings (may be empty).
    """
    results: list[str] = []
    for match in _TYPE_REF_PATTERN.finditer(type_str):
        prefix_ru = match.group(1)
        obj_name = match.group(2)
        eng_type = TYPE_PREFIX_MAP.get(prefix_ru)
        if eng_type:
            results.append(f"{eng_type}.{obj_name}")
    return results


def _parse_type_reference(type_str: str) -> str | None:
    """Extract the first metadata node id from a 1C type string.

    E.g. "СправочникСсылка.Номенклатура" -> "Catalog.Номенклатура"

    Returns:
        Node id string or None if not a recognized reference type.
    """
    refs = _parse_type_references(type_str)
    return refs[0] if refs else None


def _parse_register_record(record_name: str) -> str | None:
    """Parse a register record name into a graph node id.

    Handles both Russian and English forms:
        "РегистрНакопления.Продажи" -> "AccumulationRegister.Продажи"
        "AccumulationRegister.Продажи" -> "AccumulationRegister.Продажи"
        "Продажи" -> None (cannot determine register type without prefix)

    Returns:
        Node id string or None.
    """
    for prefix_ru, prefix_en in _REGISTER_TYPE_PREFIXES.items():
        if record_name.startswith(f"{prefix_ru}."):
            obj_name = record_name.split(".", 1)[1]
            return f"{prefix_en}.{obj_name}"
    return None


class KnowledgeGraphEngine:
    """Singleton engine that builds and queries the knowledge graph from metadata.

    Usage:
        engine = KnowledgeGraphEngine.get_instance()
        graph = await engine.build(metadata_engine)
        impact = await engine.get_impact("Catalog.Номенклатура")
    """

    _instance: KnowledgeGraphEngine | None = None

    def __init__(self) -> None:
        self._graph: KnowledgeGraph | None = None
        self._storage = GraphStorage()
        self._initialized = False

    @classmethod
    def get_instance(cls) -> KnowledgeGraphEngine:
        """Get singleton instance.

        Returns:
            KnowledgeGraphEngine instance.
        """
        if cls._instance is None:
            cls._instance = KnowledgeGraphEngine()
        return cls._instance

    @property
    def is_initialized(self) -> bool:
        """Check if the graph has been built or loaded."""
        return self._initialized and self._graph is not None

    async def _ensure_storage(self) -> None:
        """Lazily initialize SQLite storage using the global cache db_path."""
        if self._storage._connection is not None:
            return
        config = get_config()
        db_path = config.cache.db_path
        await self._storage.init_tables(db_path)

    async def build(self, metadata_engine: MetadataEngine) -> KnowledgeGraph:
        """Build complete knowledge graph from all indexed metadata.

        Args:
            metadata_engine: Initialized MetadataEngine to query objects from.

        Returns:
            Populated KnowledgeGraph.
        """
        logger.info("Building knowledge graph from metadata...")
        graph = KnowledgeGraph()

        # 1. Collect all metadata objects as nodes
        all_objects: list[MetadataObject] = []
        for md_type in _GRAPHABLE_TYPES:
            try:
                objects = await metadata_engine.list_objects(md_type)
                all_objects.extend(objects)
            except Exception as exc:
                logger.warning(f"Failed to list {md_type.value}: {exc}")

        for obj in all_objects:
            node = GraphNode(
                id=obj.full_name,
                node_type=obj.metadata_type.value,
                name=obj.name,
                synonym=obj.synonym,
                metadata={
                    "attributes_count": len(obj.attributes),
                    "tabular_sections_count": len(obj.tabular_sections),
                    "forms_count": len(obj.forms),
                    "modules_count": len(obj.modules),
                },
            )
            graph.add_node(node)

        # 2. Add subsystem nodes
        await self._add_subsystem_nodes(graph, metadata_engine)

        # 3. Extract relationships
        for obj in all_objects:
            self._extract_attribute_references(graph, obj)
            self._extract_tabular_references(graph, obj)
            self._extract_register_movements(graph, obj)
            self._extract_subsystem_membership(graph, obj)
            self._extract_based_on_produces(graph, obj)
            self._extract_register_dim_resource_types(graph, obj)
            self._extract_form_module_ownership(graph, obj)
            self._extract_defined_type_edges(graph, obj)
            self._extract_event_subscription_edges(graph, obj)
            self._extract_scheduled_job_edges(graph, obj)
            self._extract_common_attribute_edges(graph, obj)

        # 3b. Post-processing: resolve DefinedType transitive references
        self._resolve_defined_type_transitive(graph)

        # 4. Persist
        await self._ensure_storage()
        await self._storage.save_graph(graph)

        self._graph = graph
        self._initialized = True

        stats = graph.stats()
        logger.info(
            f"Knowledge graph built: {stats['total_nodes']} nodes, "
            f"{stats['total_edges']} edges"
        )
        return graph

    async def _load_or_fail(self) -> KnowledgeGraph:
        """Return the in-memory graph or attempt to load from storage."""
        if self._graph is not None:
            return self._graph

        await self._ensure_storage()
        loaded = await self._storage.load_graph()
        if loaded is None:
            raise RuntimeError(
                "Граф знаний не построен. Вызовите graph.build для построения графа."
            )
        self._graph = loaded
        self._initialized = True
        return self._graph

    # ── Public query methods ─────────────────────────────────────────────

    async def get_impact(self, node_id: str, depth: int = 3) -> dict:
        """Impact analysis: what breaks if this object changes.

        Args:
            node_id: Metadata object id (e.g. "Catalog.Номенклатура").
            depth: Maximum traversal depth.

        Returns:
            Impact analysis dictionary.
        """
        graph = await self._load_or_fail()
        return graph.get_impact(node_id, depth)

    async def get_related(
        self,
        node_id: str,
        relationship: RelationshipType | None = None,
    ) -> list[dict]:
        """Find related objects.

        Args:
            node_id: Metadata object id.
            relationship: Optional relationship filter.

        Returns:
            List of related object descriptors.
        """
        graph = await self._load_or_fail()
        related = graph.get_related(node_id, relationship)
        return [
            {
                "node_id": node.id,
                "node_type": node.node_type,
                "name": node.name,
                "synonym": node.synonym,
                "relationship": edge.relationship.value,
                "direction": "outgoing" if edge.source == node_id else "incoming",
                "label": edge.label,
            }
            for edge, node in related
        ]

    async def find_path(self, source: str, target: str) -> list[dict]:
        """Find shortest relationship path between two objects (BFS).

        Args:
            source: Source node id.
            target: Target node id.

        Returns:
            List of path steps (edges) from source to target.
        """
        graph = await self._load_or_fail()

        if source not in graph.nodes or target not in graph.nodes:
            return []

        # Build undirected adjacency list
        adjacency: dict[str, list[tuple[str, GraphEdge]]] = {}
        for nid in graph.nodes:
            adjacency[nid] = []
        for edge in graph.edges:
            adjacency.setdefault(edge.source, []).append((edge.target, edge))
            adjacency.setdefault(edge.target, []).append((edge.source, edge))

        # BFS
        visited: set[str] = {source}
        queue: deque[tuple[str, list[tuple[str, GraphEdge]]]] = deque()
        queue.append((source, []))

        while queue:
            current, path = queue.popleft()
            for neighbor_id, edge in adjacency.get(current, []):
                if neighbor_id in visited:
                    continue
                new_path = [*path, (neighbor_id, edge)]
                if neighbor_id == target:
                    return [
                        {
                            "from": edge.source,
                            "to": edge.target,
                            "relationship": edge.relationship.value,
                            "label": edge.label,
                        }
                        for _, edge in new_path
                    ]
                visited.add(neighbor_id)
                queue.append((neighbor_id, new_path))

        return []

    async def get_object_context(self, node_id: str) -> dict:
        """Get full context for an object (all relationships, neighbors).

        Args:
            node_id: Metadata object id.

        Returns:
            Dictionary with node info, incoming/outgoing relationships.
        """
        graph = await self._load_or_fail()

        node = graph.get_node(node_id)
        if node is None:
            return {"error": f"Узел не найден: {node_id}"}

        outgoing = graph.get_related(node_id, direction="outgoing")
        incoming = graph.get_related(node_id, direction="incoming")

        return {
            "node": {
                "id": node.id,
                "node_type": node.node_type,
                "name": node.name,
                "synonym": node.synonym,
                "metadata": node.metadata,
            },
            "outgoing": [
                {
                    "target": n.id,
                    "target_type": n.node_type,
                    "target_name": n.name,
                    "relationship": e.relationship.value,
                    "label": e.label,
                }
                for e, n in outgoing
            ],
            "incoming": [
                {
                    "source": n.id,
                    "source_type": n.node_type,
                    "source_name": n.name,
                    "relationship": e.relationship.value,
                    "label": e.label,
                }
                for e, n in incoming
            ],
            "total_connections": len(outgoing) + len(incoming),
        }

    async def get_stats(self) -> dict:
        """Get graph statistics.

        Returns:
            Statistics dictionary.
        """
        graph = await self._load_or_fail()
        return graph.stats()

    # ── Relationship extraction helpers ──────────────────────────────────

    @staticmethod
    def _extract_attribute_references(graph: KnowledgeGraph, obj: MetadataObject) -> None:
        """Extract edges from attribute type references (supports composite types)."""
        for attr in obj.attributes:
            for ref_id in _parse_type_references(attr.type):
                if ref_id in graph.nodes:
                    graph.add_edge(GraphEdge(
                        source=obj.full_name,
                        target=ref_id,
                        relationship=RelationshipType.ATTRIBUTE_REFERENCE,
                        label=f"Реквизит '{attr.name}' ссылается на {ref_id}",
                        metadata={"attribute_name": attr.name},
                    ))

    @staticmethod
    def _extract_tabular_references(graph: KnowledgeGraph, obj: MetadataObject) -> None:
        """Extract edges from tabular section attribute type references (supports composite types)."""
        for ts in obj.tabular_sections:
            for attr in ts.attributes:
                for ref_id in _parse_type_references(attr.type):
                    if ref_id in graph.nodes:
                        graph.add_edge(GraphEdge(
                            source=obj.full_name,
                            target=ref_id,
                            relationship=RelationshipType.TABULAR_REFERENCE,
                            label=f"ТЧ '{ts.name}'.'{attr.name}' ссылается на {ref_id}",
                            metadata={
                                "tabular_section": ts.name,
                                "attribute_name": attr.name,
                            },
                        ))

    @staticmethod
    def _extract_register_movements(graph: KnowledgeGraph, obj: MetadataObject) -> None:
        """Extract document → register movement edges."""
        if obj.metadata_type != MetadataType.DOCUMENT:
            return
        for record_name in obj.register_records:
            reg_id = _parse_register_record(record_name)
            if reg_id and reg_id in graph.nodes:
                graph.add_edge(GraphEdge(
                    source=obj.full_name,
                    target=reg_id,
                    relationship=RelationshipType.REGISTER_MOVEMENT,
                    label=f"Документ '{obj.name}' делает движения в {reg_id}",
                    metadata={"register": record_name},
                ))

    @staticmethod
    def _extract_subsystem_membership(graph: KnowledgeGraph, obj: MetadataObject) -> None:
        """Extract object → subsystem membership edges."""
        for subsystem_name in obj.subsystems:
            subsystem_id = f"Subsystem.{subsystem_name}"
            if subsystem_id in graph.nodes:
                graph.add_edge(GraphEdge(
                    source=obj.full_name,
                    target=subsystem_id,
                    relationship=RelationshipType.SUBSYSTEM_MEMBERSHIP,
                    label=f"'{obj.name}' входит в подсистему '{subsystem_name}'",
                ))

    @staticmethod
    def _extract_based_on_produces(graph: KnowledgeGraph, obj: MetadataObject) -> None:
        """Extract based_on and produces_documents relationships."""
        for based_name in obj.based_on:
            # based_on names may include type prefix or just document names
            based_id = f"Document.{based_name}" if "." not in based_name else based_name
            if based_id in graph.nodes:
                graph.add_edge(GraphEdge(
                    source=obj.full_name,
                    target=based_id,
                    relationship=RelationshipType.BASED_ON,
                    label=f"'{obj.name}' создается на основании '{based_name}'",
                ))

        for produced_name in obj.produces_documents:
            produced_id = f"Document.{produced_name}" if "." not in produced_name else produced_name
            if produced_id in graph.nodes:
                graph.add_edge(GraphEdge(
                    source=obj.full_name,
                    target=produced_id,
                    relationship=RelationshipType.PRODUCES,
                    label=f"'{obj.name}' порождает документ '{produced_name}'",
                ))

    @staticmethod
    def _extract_register_dim_resource_types(
        graph: KnowledgeGraph, obj: MetadataObject,
    ) -> None:
        """Extract edges from register dimension/resource type references."""
        is_register = obj.metadata_type in (
            MetadataType.INFORMATION_REGISTER,
            MetadataType.ACCUMULATION_REGISTER,
            MetadataType.ACCOUNTING_REGISTER,
            MetadataType.CALCULATION_REGISTER,
        )
        if not is_register:
            return

        for dim in obj.dimensions:
            for ref_id in _parse_type_references(dim.type):
                if ref_id in graph.nodes:
                    graph.add_edge(GraphEdge(
                        source=obj.full_name,
                        target=ref_id,
                        relationship=RelationshipType.DIMENSION_TYPE,
                        label=f"Измерение '{dim.name}' типа {ref_id}",
                        metadata={"dimension_name": dim.name},
                    ))

        for res in obj.resources:
            for ref_id in _parse_type_references(res.type):
                if ref_id in graph.nodes:
                    graph.add_edge(GraphEdge(
                        source=obj.full_name,
                        target=ref_id,
                        relationship=RelationshipType.RESOURCE_TYPE,
                        label=f"Ресурс '{res.name}' типа {ref_id}",
                        metadata={"resource_name": res.name},
                    ))

    @staticmethod
    def _extract_form_module_ownership(graph: KnowledgeGraph, obj: MetadataObject) -> None:
        """Extract form and module ownership edges."""
        for form in obj.forms:
            form_id = f"{obj.full_name}.Form.{form.name}"
            graph.add_node(GraphNode(
                id=form_id,
                node_type="Form",
                name=form.name,
                synonym=form.synonym,
                metadata={"owner": obj.full_name, "form_type": form.form_type},
            ))
            graph.add_edge(GraphEdge(
                source=form_id,
                target=obj.full_name,
                relationship=RelationshipType.FORM_OWNERSHIP,
                label=f"Форма '{form.name}' принадлежит '{obj.name}'",
            ))

        for module in obj.modules:
            module_id = f"{obj.full_name}.Module.{module.module_type.value}"
            graph.add_node(GraphNode(
                id=module_id,
                node_type="Module",
                name=module.module_type.value,
                metadata={"owner": obj.full_name, "exists": module.exists},
            ))
            graph.add_edge(GraphEdge(
                source=module_id,
                target=obj.full_name,
                relationship=RelationshipType.MODULE_OWNERSHIP,
                label=f"Модуль '{module.module_type.value}' принадлежит '{obj.name}'",
            ))

    # ── New relationship extractors ─────────────────────────────────────

    @staticmethod
    def _parse_source_object(source_str: str) -> str | None:
        """Parse an event subscription source string into a graph node id.

        E.g. "DocumentObject.ПриходТовара" -> "Document.ПриходТовара"
             "ДокументОбъект.ПриходТовара" -> "Document.ПриходТовара"

        Returns:
            Node id string or None if prefix is unrecognized.
        """
        parts = source_str.split(".", 1)
        if len(parts) != 2:
            return None
        prefix = parts[0]
        obj_name = parts[1]
        eng_type = _SOURCE_OBJECT_PREFIX_MAP.get(prefix)
        if eng_type:
            return f"{eng_type}.{obj_name}"
        return None

    @staticmethod
    def _parse_handler_reference(handler_str: str) -> str | None:
        """Parse a subscription/scheduled-job handler into a module node id.

        E.g. "ОбщийМодуль.МодульОбработки.ПриЗаписи" -> "CommonModule.МодульОбработки"
             "CommonModule.ModuleName.Method" -> "CommonModule.ModuleName"

        Returns:
            Node id string or None if unparseable.
        """
        parts = handler_str.split(".")
        if len(parts) < 2:
            return None
        prefix = parts[0]
        module_name = parts[1]
        # Normalize Russian prefix to English
        if prefix in ("ОбщийМодуль", "CommonModule"):
            return f"CommonModule.{module_name}"
        return None

    @staticmethod
    def _extract_defined_type_edges(graph: KnowledgeGraph, obj: MetadataObject) -> None:
        """Extract DefinedType -> constituent type edges."""
        if obj.metadata_type != MetadataType.DEFINED_TYPE:
            return
        for type_str in obj.type_constituents:
            for ref_id in _parse_type_references(type_str):
                if ref_id in graph.nodes:
                    graph.add_edge(GraphEdge(
                        source=obj.full_name,
                        target=ref_id,
                        relationship=RelationshipType.DEFINED_TYPE_CONTAINS,
                        label=f"ОпределяемыйТип '{obj.name}' включает {ref_id}",
                        metadata={"constituent_type": type_str},
                    ))

    @staticmethod
    def _extract_event_subscription_edges(graph: KnowledgeGraph, obj: MetadataObject) -> None:
        """Extract EventSubscription -> source and handler edges."""
        if obj.metadata_type != MetadataType.EVENT_SUBSCRIPTION:
            return

        for source_str in obj.event_source:
            source_id = KnowledgeGraphEngine._parse_source_object(source_str)
            if source_id and source_id in graph.nodes:
                graph.add_edge(GraphEdge(
                    source=obj.full_name,
                    target=source_id,
                    relationship=RelationshipType.EVENT_SUBSCRIPTION,
                    label=f"Подписка '{obj.name}' на событие {source_id}",
                    metadata={"source_object": source_str},
                ))

        if obj.event_handler:
            handler_id = KnowledgeGraphEngine._parse_handler_reference(obj.event_handler)
            if handler_id and handler_id in graph.nodes:
                graph.add_edge(GraphEdge(
                    source=obj.full_name,
                    target=handler_id,
                    relationship=RelationshipType.SUBSCRIPTION_HANDLER,
                    label=f"Подписка '{obj.name}' обрабатывается в {handler_id}",
                    metadata={"handler": obj.event_handler},
                ))

    @staticmethod
    def _extract_scheduled_job_edges(graph: KnowledgeGraph, obj: MetadataObject) -> None:
        """Extract ScheduledJob -> method handler edges."""
        if obj.metadata_type != MetadataType.SCHEDULED_JOB:
            return
        if not obj.method_name:
            return

        handler_id = KnowledgeGraphEngine._parse_handler_reference(obj.method_name)
        if handler_id and handler_id in graph.nodes:
            graph.add_edge(GraphEdge(
                source=obj.full_name,
                target=handler_id,
                relationship=RelationshipType.SCHEDULED_JOB_METHOD,
                label=f"РегЗадание '{obj.name}' вызывает {handler_id}",
                metadata={"method_name": obj.method_name},
            ))

    @staticmethod
    def _extract_common_attribute_edges(graph: KnowledgeGraph, obj: MetadataObject) -> None:
        """Extract CommonAttribute -> applied object usage edges."""
        if obj.metadata_type != MetadataType.COMMON_ATTRIBUTE:
            return
        for applied in obj.applied_objects:
            # applied is expected in "Type.Name" form already
            if applied in graph.nodes:
                graph.add_edge(GraphEdge(
                    source=obj.full_name,
                    target=applied,
                    relationship=RelationshipType.COMMON_ATTRIBUTE_USAGE,
                    label=f"ОбщийРеквизит '{obj.name}' используется в {applied}",
                    metadata={"applied_object": applied},
                ))

    @staticmethod
    def _resolve_defined_type_transitive(graph: KnowledgeGraph) -> None:
        """Post-processing: add transitive ATTRIBUTE_REFERENCE edges through DefinedTypes.

        If attribute A references DefinedType.X, and DefinedType.X contains
        Catalog.Y and Document.Z, add ATTRIBUTE_REFERENCE edges from A's
        owner to Catalog.Y and Document.Z as well.
        """
        # Collect edges that reference a DefinedType node
        dt_edges: list[GraphEdge] = []
        for edge in graph.edges:
            if edge.relationship in (
                RelationshipType.ATTRIBUTE_REFERENCE,
                RelationshipType.TABULAR_REFERENCE,
                RelationshipType.DIMENSION_TYPE,
                RelationshipType.RESOURCE_TYPE,
            ):
                target_node = graph.get_node(edge.target)
                if target_node and target_node.node_type == "DefinedType":
                    dt_edges.append(edge)

        # For each such edge, find what the DefinedType contains and add transitive edges
        for dt_edge in dt_edges:
            dt_constituents = graph.get_related(
                dt_edge.target,
                relationship=RelationshipType.DEFINED_TYPE_CONTAINS,
                direction="outgoing",
            )
            for _const_edge, const_node in dt_constituents:
                graph.add_edge(GraphEdge(
                    source=dt_edge.source,
                    target=const_node.id,
                    relationship=dt_edge.relationship,
                    label=(
                        f"{dt_edge.label} (через ОпределяемыйТип "
                        f"'{graph.get_node(dt_edge.target).name if graph.get_node(dt_edge.target) else dt_edge.target}')"
                    ),
                    metadata={
                        **dt_edge.metadata,
                        "via_defined_type": dt_edge.target,
                    },
                ))

    async def _add_subsystem_nodes(
        self, graph: KnowledgeGraph, metadata_engine: MetadataEngine,
    ) -> None:
        """Add subsystem nodes and hierarchy edges."""
        await self._add_subsystems_recursive(graph, metadata_engine, parent=None)

    async def _add_subsystems_recursive(
        self,
        graph: KnowledgeGraph,
        metadata_engine: MetadataEngine,
        parent: str | None,
    ) -> None:
        """Recursively add subsystem nodes and parent-child edges."""
        try:
            subsystems: list[Subsystem] = await metadata_engine.get_subsystem_tree(parent)
        except Exception as exc:
            logger.warning(f"Failed to get subsystems (parent={parent}): {exc}")
            return

        for sub in subsystems:
            node_id = f"Subsystem.{sub.name}"
            graph.add_node(GraphNode(
                id=node_id,
                node_type="Subsystem",
                name=sub.name,
                synonym=sub.synonym,
                metadata={
                    "objects_count": len(sub.content),
                    "children_count": len(sub.children),
                },
            ))

            # Parent hierarchy edge
            if parent:
                parent_id = f"Subsystem.{parent}"
                if parent_id in graph.nodes:
                    graph.add_edge(GraphEdge(
                        source=node_id,
                        target=parent_id,
                        relationship=RelationshipType.SUBSYSTEM_HIERARCHY,
                        label=f"'{sub.name}' входит в '{parent}'",
                    ))

            # Recurse into children
            if sub.children:
                await self._add_subsystems_recursive(
                    graph, metadata_engine, parent=sub.name,
                )
