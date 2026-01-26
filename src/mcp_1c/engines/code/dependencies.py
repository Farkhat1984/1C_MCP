"""
Dependency Graph Builder.

Builds and manages dependency graphs for BSL code analysis.
Tracks:
- Procedure calls (who calls whom)
- Metadata references (which procedures use which metadata)
- Module dependencies (cross-module calls)
"""

from pathlib import Path

import aiosqlite

from mcp_1c.domain.code import (
    CodeLocation,
    DependencyEdge,
    DependencyGraph,
    ExtendedBslModule,
)
from mcp_1c.engines.code.parser import BslParser
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


class DependencyGraphBuilder:
    """
    Builds dependency graphs from parsed BSL modules.

    Supports:
    - In-memory graph building
    - SQLite persistence for incremental updates
    - Cross-module analysis
    """

    def __init__(self, cache_path: Path | None = None) -> None:
        """
        Initialize dependency graph builder.

        Args:
            cache_path: Optional path to SQLite cache for persistence
        """
        self.parser = BslParser()
        self.cache_path = cache_path
        self.graph = DependencyGraph()
        self.logger = get_logger(__name__)

    async def build_from_module(self, module: ExtendedBslModule) -> DependencyGraph:
        """
        Build dependency graph from a single parsed module.

        Args:
            module: Parsed ExtendedBslModule

        Returns:
            DependencyGraph for the module
        """
        graph = DependencyGraph()

        # Add procedure nodes
        for proc in module.procedures:
            node_id = self._make_procedure_node_id(module.path, proc.name)
            graph.add_node(
                node_id,
                "procedure",
                {
                    "name": proc.name,
                    "is_function": proc.is_function,
                    "is_export": proc.is_export,
                    "directive": proc.directive.value if proc.directive else None,
                    "file": str(module.path),
                    "line": proc.start_line,
                },
            )

        # Add call edges
        for call in module.method_calls:
            if call.containing_procedure:
                source = self._make_procedure_node_id(
                    module.path, call.containing_procedure
                )
                # Target could be local or external
                target = call.name  # Simplified - could be qualified later

                location = CodeLocation(
                    file_path=module.path,
                    line=call.line,
                    column=call.column,
                )

                graph.add_edge(source, target, "calls", location)

        # Add metadata reference edges
        for ref in module.metadata_references:
            if ref.containing_procedure:
                source = self._make_procedure_node_id(
                    module.path, ref.containing_procedure
                )
                target = ref.full_name  # e.g., "Справочники.Номенклатура"

                # Add metadata node if not exists
                if target not in graph.nodes:
                    graph.add_node(
                        target,
                        "metadata",
                        {
                            "type": ref.reference_type.value,
                            "object_name": ref.object_name,
                        },
                    )

                location = CodeLocation(
                    file_path=module.path,
                    line=ref.line,
                    column=ref.column,
                )

                graph.add_edge(source, target, "uses_metadata", location)

        return graph

    async def build_from_file(self, path: Path) -> DependencyGraph:
        """
        Build dependency graph from a BSL file.

        Args:
            path: Path to .bsl file

        Returns:
            DependencyGraph
        """
        module = await self.parser.parse_file_extended(path)
        return await self.build_from_module(module)

    async def build_from_files(self, paths: list[Path]) -> DependencyGraph:
        """
        Build combined dependency graph from multiple files.

        Args:
            paths: List of paths to .bsl files

        Returns:
            Combined DependencyGraph
        """
        combined_graph = DependencyGraph()

        for path in paths:
            try:
                module_graph = await self.build_from_file(path)
                self._merge_graphs(combined_graph, module_graph)
            except Exception as e:
                self.logger.warning(f"Failed to build graph for {path}: {e}")

        return combined_graph

    def _merge_graphs(
        self, target: DependencyGraph, source: DependencyGraph
    ) -> None:
        """Merge source graph into target graph."""
        # Merge nodes
        for node_id, node_data in source.nodes.items():
            if node_id not in target.nodes:
                target.nodes[node_id] = node_data

        # Merge edges
        for edge in source.edges:
            target.add_edge(
                edge.source,
                edge.target,
                edge.edge_type,
                edge.locations[0] if edge.locations else None,
            )

    def _make_procedure_node_id(self, file_path: Path, proc_name: str) -> str:
        """Create unique node ID for a procedure."""
        # Use relative path if possible
        return f"{file_path.stem}::{proc_name}"

    # =========================================================================
    # SQLite Persistence (for incremental updates)
    # =========================================================================

    async def init_cache(self) -> None:
        """Initialize SQLite cache for persistence."""
        if not self.cache_path:
            return

        async with aiosqlite.connect(self.cache_path) as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    metadata TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    edge_type TEXT NOT NULL,
                    count INTEGER DEFAULT 1,
                    locations TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(source, target, edge_type)
                );

                CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source);
                CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target);
                CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
                """
            )
            await db.commit()

    async def save_graph(self, graph: DependencyGraph) -> None:
        """Save graph to SQLite cache."""
        if not self.cache_path:
            return

        async with aiosqlite.connect(self.cache_path) as db:
            # Save nodes
            for node_id, node_data in graph.nodes.items():
                import json

                await db.execute(
                    """
                    INSERT OR REPLACE INTO nodes (id, type, metadata)
                    VALUES (?, ?, ?)
                    """,
                    (node_id, node_data["type"], json.dumps(node_data["metadata"])),
                )

            # Save edges
            for edge in graph.edges:
                import json

                locations_json = json.dumps(
                    [
                        {
                            "file": str(loc.file_path),
                            "line": loc.line,
                            "column": loc.column,
                        }
                        for loc in edge.locations
                    ]
                )

                await db.execute(
                    """
                    INSERT INTO edges (source, target, edge_type, count, locations)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(source, target, edge_type) DO UPDATE SET
                        count = count + excluded.count,
                        locations = excluded.locations,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (edge.source, edge.target, edge.edge_type, edge.count, locations_json),
                )

            await db.commit()

    async def load_graph(self) -> DependencyGraph:
        """Load graph from SQLite cache."""
        if not self.cache_path or not self.cache_path.exists():
            return DependencyGraph()

        import json

        graph = DependencyGraph()

        async with aiosqlite.connect(self.cache_path) as db:
            # Load nodes
            async with db.execute("SELECT id, type, metadata FROM nodes") as cursor:
                async for row in cursor:
                    node_id, node_type, metadata_json = row
                    metadata = json.loads(metadata_json) if metadata_json else {}
                    graph.nodes[node_id] = {"type": node_type, "metadata": metadata}

            # Load edges
            async with db.execute(
                "SELECT source, target, edge_type, count, locations FROM edges"
            ) as cursor:
                async for row in cursor:
                    source, target, edge_type, count, locations_json = row
                    locations_data = json.loads(locations_json) if locations_json else []
                    locations = [
                        CodeLocation(
                            file_path=Path(loc["file"]),
                            line=loc["line"],
                            column=loc["column"],
                        )
                        for loc in locations_data
                    ]
                    graph.edges.append(
                        DependencyEdge(
                            source=source,
                            target=target,
                            edge_type=edge_type,
                            count=count,
                            locations=locations,
                        )
                    )

        return graph

    # =========================================================================
    # Query methods
    # =========================================================================

    async def get_procedure_dependencies(
        self,
        procedure_name: str,
        graph: DependencyGraph | None = None,
        depth: int = 1,
    ) -> dict:
        """
        Get dependencies for a procedure.

        Args:
            procedure_name: Name of procedure
            graph: Optional graph to use (loads from cache if None)
            depth: Depth of dependency tree

        Returns:
            Dependency tree dict
        """
        if graph is None:
            graph = await self.load_graph()

        # Find node matching procedure name
        node = None
        for node_id in graph.nodes:
            if node_id.endswith(f"::{procedure_name}"):
                node = node_id
                break

        if not node:
            return {"error": f"Procedure '{procedure_name}' not found"}

        return graph.get_dependencies(node, depth)

    async def get_metadata_usages(
        self,
        metadata_name: str,
        graph: DependencyGraph | None = None,
    ) -> list[dict]:
        """
        Get all procedures that use a metadata object.

        Args:
            metadata_name: Full metadata name (e.g., "Справочники.Номенклатура")
            graph: Optional graph to use

        Returns:
            List of procedure info dicts with usage locations
        """
        if graph is None:
            graph = await self.load_graph()

        usages = []
        for edge in graph.edges:
            if edge.target == metadata_name and edge.edge_type == "uses_metadata":
                source_node = graph.nodes.get(edge.source, {})
                usages.append(
                    {
                        "procedure": edge.source,
                        "metadata": source_node.get("metadata", {}),
                        "count": edge.count,
                        "locations": [
                            {"file": str(loc.file_path), "line": loc.line}
                            for loc in edge.locations
                        ],
                    }
                )

        return usages

    async def get_call_graph(
        self,
        procedure_name: str,
        graph: DependencyGraph | None = None,
        direction: str = "both",
    ) -> dict:
        """
        Get call graph for a procedure.

        Args:
            procedure_name: Name of procedure
            graph: Optional graph to use
            direction: "callees" (outgoing), "callers" (incoming), or "both"

        Returns:
            Call graph dict
        """
        if graph is None:
            graph = await self.load_graph()

        # Find node
        node = None
        for node_id in graph.nodes:
            if node_id.endswith(f"::{procedure_name}"):
                node = node_id
                break

        if not node:
            return {"error": f"Procedure '{procedure_name}' not found"}

        result = {"procedure": node}

        if direction in ("callees", "both"):
            result["callees"] = [
                {
                    "target": e.target,
                    "count": e.count,
                    "locations": [
                        {"file": str(loc.file_path), "line": loc.line}
                        for loc in e.locations
                    ],
                }
                for e in graph.edges
                if e.source == node and e.edge_type == "calls"
            ]

        if direction in ("callers", "both"):
            result["callers"] = [
                {
                    "source": e.source,
                    "count": e.count,
                    "locations": [
                        {"file": str(loc.file_path), "line": loc.line}
                        for loc in e.locations
                    ],
                }
                for e in graph.edges
                if e.target == procedure_name and e.edge_type == "calls"
            ]

        return result

    async def get_statistics(
        self, graph: DependencyGraph | None = None
    ) -> dict:
        """
        Get statistics about the dependency graph.

        Args:
            graph: Optional graph to use

        Returns:
            Statistics dict
        """
        if graph is None:
            graph = await self.load_graph()

        # Count by type
        procedure_count = sum(
            1 for n in graph.nodes.values() if n["type"] == "procedure"
        )
        metadata_count = sum(
            1 for n in graph.nodes.values() if n["type"] == "metadata"
        )

        # Count edges by type
        call_count = sum(1 for e in graph.edges if e.edge_type == "calls")
        metadata_usage_count = sum(
            1 for e in graph.edges if e.edge_type == "uses_metadata"
        )

        # Find most called procedures
        call_counts: dict[str, int] = {}
        for edge in graph.edges:
            if edge.edge_type == "calls":
                call_counts[edge.target] = call_counts.get(edge.target, 0) + edge.count

        most_called = sorted(call_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        # Find most used metadata
        metadata_counts: dict[str, int] = {}
        for edge in graph.edges:
            if edge.edge_type == "uses_metadata":
                metadata_counts[edge.target] = (
                    metadata_counts.get(edge.target, 0) + edge.count
                )

        most_used_metadata = sorted(
            metadata_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]

        return {
            "total_nodes": len(graph.nodes),
            "procedures": procedure_count,
            "metadata_objects": metadata_count,
            "total_edges": len(graph.edges),
            "call_edges": call_count,
            "metadata_usage_edges": metadata_usage_count,
            "most_called_procedures": [
                {"name": name, "count": count} for name, count in most_called
            ],
            "most_used_metadata": [
                {"name": name, "count": count} for name, count in most_used_metadata
            ],
        }
