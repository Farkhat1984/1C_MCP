"""
Knowledge Graph domain models.

Represents relationships between 1C:Enterprise metadata objects
at the configuration level (not code-level dependencies).
"""

from __future__ import annotations

from collections import defaultdict
from enum import Enum

from pydantic import BaseModel, Field


class RelationshipType(str, Enum):
    """Types of relationships between metadata objects."""

    ATTRIBUTE_REFERENCE = "attribute_reference"
    TABULAR_REFERENCE = "tabular_reference"
    REGISTER_MOVEMENT = "register_movement"
    SUBSYSTEM_MEMBERSHIP = "subsystem_membership"
    SUBSYSTEM_HIERARCHY = "subsystem_hierarchy"
    BASED_ON = "based_on"
    PRODUCES = "produces"
    DIMENSION_TYPE = "dimension_type"
    RESOURCE_TYPE = "resource_type"
    EVENT_SUBSCRIPTION = "event_subscription"
    FORM_OWNERSHIP = "form_ownership"
    MODULE_OWNERSHIP = "module_ownership"
    DEFINED_TYPE_CONTAINS = "defined_type_contains"
    SUBSCRIPTION_HANDLER = "subscription_handler"
    SCHEDULED_JOB_METHOD = "scheduled_job_method"
    COMMON_ATTRIBUTE_USAGE = "common_attribute_usage"


class GraphNode(BaseModel):
    """Node in the knowledge graph representing a metadata object."""

    id: str = Field(..., description="Уникальный идентификатор, напр. 'Catalog.Номенклатура'")
    node_type: str = Field(..., description="Тип метаданных, напр. 'Catalog', 'Document'")
    name: str = Field(..., description="Имя объекта, напр. 'Номенклатура'")
    synonym: str = Field(default="", description="Синоним (отображаемое имя)")
    metadata: dict = Field(default_factory=dict, description="Дополнительные метаданные")


class GraphEdge(BaseModel):
    """Edge in the knowledge graph representing a relationship."""

    source: str = Field(..., description="Идентификатор узла-источника")
    target: str = Field(..., description="Идентификатор узла-цели")
    relationship: RelationshipType = Field(..., description="Тип связи")
    label: str = Field(default="", description="Человекочитаемое описание связи")
    metadata: dict = Field(default_factory=dict, description="Дополнительная информация")


class KnowledgeGraph(BaseModel):
    """
    Knowledge graph of metadata object relationships.

    Stores nodes (metadata objects) and edges (relationships between them).
    Provides traversal, impact analysis, and subgraph extraction.
    """

    nodes: dict[str, GraphNode] = Field(default_factory=dict)
    edges: list[GraphEdge] = Field(default_factory=list)

    def add_node(self, node: GraphNode) -> None:
        """Add a node to the graph (upsert by id)."""
        self.nodes[node.id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        """Add an edge to the graph."""
        self.edges.append(edge)

    def get_node(self, node_id: str) -> GraphNode | None:
        """Get node by id."""
        return self.nodes.get(node_id)

    def get_related(
        self,
        node_id: str,
        relationship: RelationshipType | None = None,
        direction: str = "both",
    ) -> list[tuple[GraphEdge, GraphNode]]:
        """Get related nodes with their edges.

        Args:
            node_id: Node identifier.
            relationship: Optional filter by relationship type.
            direction: 'outgoing', 'incoming', or 'both'.

        Returns:
            List of (edge, node) tuples for each related node.
        """
        results: list[tuple[GraphEdge, GraphNode]] = []

        for edge in self.edges:
            if relationship and edge.relationship != relationship:
                continue

            neighbor_id: str | None = None
            if direction in ("outgoing", "both") and edge.source == node_id:
                neighbor_id = edge.target
            elif direction in ("incoming", "both") and edge.target == node_id:
                neighbor_id = edge.source

            if neighbor_id is not None:
                neighbor = self.nodes.get(neighbor_id)
                if neighbor:
                    results.append((edge, neighbor))

        return results

    def get_impact(self, node_id: str, depth: int = 3) -> dict:
        """Impact analysis: what objects depend on the given node.

        Performs BFS over incoming edges (objects that reference this node).

        Args:
            node_id: Starting node identifier.
            depth: Maximum traversal depth.

        Returns:
            Dictionary with impacted nodes grouped by depth level.
        """
        # Build incoming adjacency index for efficient traversal
        incoming: dict[str, list[tuple[GraphEdge, str]]] = defaultdict(list)
        for edge in self.edges:
            incoming[edge.target].append((edge, edge.source))

        visited: set[str] = {node_id}
        current_level: set[str] = {node_id}
        impact: dict[str, list[dict]] = {}

        for level in range(1, depth + 1):
            next_level: set[str] = set()
            level_results: list[dict] = []

            for nid in current_level:
                for edge, source_id in incoming.get(nid, []):
                    if source_id in visited:
                        continue
                    visited.add(source_id)
                    next_level.add(source_id)
                    source_node = self.nodes.get(source_id)
                    level_results.append({
                        "node_id": source_id,
                        "node_type": source_node.node_type if source_node else "",
                        "name": source_node.name if source_node else source_id,
                        "relationship": edge.relationship.value,
                        "via": nid,
                    })

            if level_results:
                impact[f"depth_{level}"] = level_results
            current_level = next_level
            if not current_level:
                break

        return {
            "node_id": node_id,
            "total_impacted": sum(len(v) for v in impact.values()),
            "levels": impact,
        }

    def get_subgraph(self, node_ids: list[str]) -> KnowledgeGraph:
        """Extract a subgraph containing only the specified nodes and edges between them.

        Args:
            node_ids: List of node identifiers to include.

        Returns:
            New KnowledgeGraph with only the specified nodes and their connecting edges.
        """
        id_set = set(node_ids)
        sub_nodes = {nid: node for nid, node in self.nodes.items() if nid in id_set}
        sub_edges = [
            edge for edge in self.edges
            if edge.source in id_set and edge.target in id_set
        ]
        return KnowledgeGraph(nodes=sub_nodes, edges=sub_edges)

    def to_dict(self) -> dict:
        """Serialize graph to a plain dictionary."""
        return {
            "nodes": [
                {
                    "id": node.id,
                    "node_type": node.node_type,
                    "name": node.name,
                    "synonym": node.synonym,
                    "metadata": node.metadata,
                }
                for node in self.nodes.values()
            ],
            "edges": [
                {
                    "source": edge.source,
                    "target": edge.target,
                    "relationship": edge.relationship.value,
                    "label": edge.label,
                    "metadata": edge.metadata,
                }
                for edge in self.edges
            ],
            "stats": self.stats(),
        }

    def stats(self) -> dict:
        """Get graph statistics."""
        type_counts: dict[str, int] = defaultdict(int)
        for node in self.nodes.values():
            type_counts[node.node_type] += 1

        rel_counts: dict[str, int] = defaultdict(int)
        for edge in self.edges:
            rel_counts[edge.relationship.value] += 1

        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "node_types": dict(type_counts),
            "relationship_types": dict(rel_counts),
        }
