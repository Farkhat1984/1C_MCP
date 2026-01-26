"""
Metadata tools for MCP-1C.

Provides tools for working with 1C configuration metadata.
"""

from pathlib import Path
from typing import Any, ClassVar
import json

from mcp_1c.tools.base import BaseTool
from mcp_1c.engines.metadata import MetadataEngine
from mcp_1c.domain.metadata import MetadataType


class MetadataInitTool(BaseTool):
    """Initialize metadata index for a configuration."""

    name: ClassVar[str] = "metadata.init"
    description: ClassVar[str] = (
        "Initialize the metadata index for a 1C configuration. "
        "Must be called before using other metadata tools. "
        "Scans the configuration directory and builds a searchable index."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the 1C configuration root directory",
            },
            "full_reindex": {
                "type": "boolean",
                "description": "Force full reindexing (default: false)",
                "default": False,
            },
        },
        "required": ["path"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Execute metadata initialization."""
        config_path = Path(arguments["path"])
        full_reindex = arguments.get("full_reindex", False)

        engine = MetadataEngine.get_instance()
        progress = await engine.initialize(
            config_path,
            full_reindex=full_reindex,
        )

        stats = await engine.get_stats()

        return {
            "status": "success",
            "path": str(config_path),
            "objects_indexed": progress.processed,
            "objects_updated": progress.updated,
            "objects_skipped": progress.skipped,
            "errors": progress.errors[:10] if progress.errors else [],
            "statistics": stats,
        }


class MetadataListTool(BaseTool):
    """List metadata objects by type."""

    name: ClassVar[str] = "metadata.list"
    description: ClassVar[str] = (
        "List all metadata objects of a specific type. "
        "Returns names and synonyms of objects."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "description": (
                    "Metadata type: Catalog, Document, Enum, InformationRegister, "
                    "AccumulationRegister, Report, DataProcessor, CommonModule, etc."
                ),
            },
        },
        "required": ["type"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """List objects of specified type."""
        type_str = arguments["type"]

        try:
            metadata_type = MetadataType(type_str)
        except ValueError:
            # Try Russian name
            metadata_type = MetadataType.from_russian(type_str)
            if metadata_type is None:
                return {"error": f"Unknown metadata type: {type_str}"}

        engine = MetadataEngine.get_instance()
        objects = await engine.list_objects(metadata_type)

        return {
            "type": metadata_type.value,
            "count": len(objects),
            "objects": [
                {
                    "name": obj.name,
                    "synonym": obj.synonym,
                    "full_name": obj.full_name,
                }
                for obj in objects
            ],
        }


class MetadataGetTool(BaseTool):
    """Get detailed information about a metadata object."""

    name: ClassVar[str] = "metadata.get"
    description: ClassVar[str] = (
        "Get full information about a specific metadata object including "
        "attributes, tabular sections, forms, templates, and modules."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "description": "Metadata type (e.g., Catalog, Document)",
            },
            "name": {
                "type": "string",
                "description": "Object name",
            },
        },
        "required": ["type", "name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Get object details."""
        type_str = arguments["type"]
        name = arguments["name"]

        try:
            metadata_type = MetadataType(type_str)
        except ValueError:
            metadata_type = MetadataType.from_russian(type_str)
            if metadata_type is None:
                return {"error": f"Unknown metadata type: {type_str}"}

        engine = MetadataEngine.get_instance()
        obj = await engine.get_object(metadata_type, name)

        if obj is None:
            return {"error": f"Object not found: {type_str}.{name}"}

        return {
            "name": obj.name,
            "synonym": obj.synonym,
            "full_name": obj.full_name,
            "type": obj.metadata_type.value,
            "uuid": obj.uuid,
            "comment": obj.comment,
            "attributes": [
                {
                    "name": attr.name,
                    "synonym": attr.synonym,
                    "type": attr.type,
                    "indexed": attr.indexed,
                }
                for attr in obj.attributes
            ],
            "tabular_sections": [
                {
                    "name": ts.name,
                    "synonym": ts.synonym,
                    "attributes": [
                        {"name": a.name, "type": a.type}
                        for a in ts.attributes
                    ],
                }
                for ts in obj.tabular_sections
            ],
            "forms": [
                {"name": f.name, "synonym": f.synonym}
                for f in obj.forms
            ],
            "templates": [
                {"name": t.name, "synonym": t.synonym}
                for t in obj.templates
            ],
            "modules": [
                {
                    "type": m.module_type.value,
                    "path": str(m.path),
                    "exists": m.exists,
                }
                for m in obj.modules
            ],
            "register_records": obj.register_records,
            "subsystems": obj.subsystems,
        }


class MetadataSearchTool(BaseTool):
    """Search metadata objects by name or synonym."""

    name: ClassVar[str] = "metadata.search"
    description: ClassVar[str] = (
        "Search for metadata objects by name or synonym. "
        "Supports partial matching and optional type filtering."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (partial name or synonym)",
            },
            "type": {
                "type": "string",
                "description": "Optional: filter by metadata type",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results (default: 20)",
                "default": 20,
            },
        },
        "required": ["query"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Search for objects."""
        query = arguments["query"]
        type_str = arguments.get("type")
        limit = arguments.get("limit", 20)

        metadata_type = None
        if type_str:
            try:
                metadata_type = MetadataType(type_str)
            except ValueError:
                metadata_type = MetadataType.from_russian(type_str)

        engine = MetadataEngine.get_instance()
        objects = await engine.search(query, metadata_type, limit)

        return {
            "query": query,
            "count": len(objects),
            "results": [
                {
                    "name": obj.name,
                    "synonym": obj.synonym,
                    "full_name": obj.full_name,
                    "type": obj.metadata_type.value,
                }
                for obj in objects
            ],
        }


class MetadataTreeTool(BaseTool):
    """Get subsystem tree structure."""

    name: ClassVar[str] = "metadata.tree"
    description: ClassVar[str] = (
        "Get the subsystem tree structure of the configuration. "
        "Shows hierarchical organization of objects."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "parent": {
                "type": "string",
                "description": "Parent subsystem name (empty for root level)",
            },
        },
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Get subsystem tree."""
        parent = arguments.get("parent")

        engine = MetadataEngine.get_instance()
        subsystems = await engine.get_subsystem_tree(parent)

        return {
            "parent": parent or "(root)",
            "subsystems": [
                {
                    "name": s.name,
                    "synonym": s.synonym,
                    "children_count": len(s.children),
                    "objects_count": len(s.content),
                    "include_in_command_interface": s.include_in_command_interface,
                }
                for s in subsystems
            ],
        }


class MetadataAttributesTool(BaseTool):
    """Get attributes of a metadata object."""

    name: ClassVar[str] = "metadata.attributes"
    description: ClassVar[str] = (
        "Get detailed list of attributes (requisites) of a metadata object. "
        "For registers, also returns dimensions and resources."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "description": "Metadata type",
            },
            "name": {
                "type": "string",
                "description": "Object name",
            },
            "include_tabular": {
                "type": "boolean",
                "description": "Include tabular section attributes (default: true)",
                "default": True,
            },
        },
        "required": ["type", "name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Get object attributes."""
        type_str = arguments["type"]
        name = arguments["name"]
        include_tabular = arguments.get("include_tabular", True)

        try:
            metadata_type = MetadataType(type_str)
        except ValueError:
            metadata_type = MetadataType.from_russian(type_str)
            if metadata_type is None:
                return {"error": f"Unknown metadata type: {type_str}"}

        engine = MetadataEngine.get_instance()
        obj = await engine.get_object(metadata_type, name)

        if obj is None:
            return {"error": f"Object not found: {type_str}.{name}"}

        result: dict[str, Any] = {
            "object": obj.full_name,
            "attributes": [
                {
                    "name": attr.name,
                    "synonym": attr.synonym,
                    "type": attr.type,
                    "indexed": attr.indexed,
                    "comment": attr.comment,
                }
                for attr in obj.attributes
            ],
        }

        # Add dimensions and resources for registers
        if obj.dimensions:
            result["dimensions"] = [
                {"name": d.name, "synonym": d.synonym, "type": d.type}
                for d in obj.dimensions
            ]

        if obj.resources:
            result["resources"] = [
                {"name": r.name, "synonym": r.synonym, "type": r.type}
                for r in obj.resources
            ]

        # Add tabular sections
        if include_tabular and obj.tabular_sections:
            result["tabular_sections"] = [
                {
                    "name": ts.name,
                    "synonym": ts.synonym,
                    "attributes": [
                        {
                            "name": a.name,
                            "synonym": a.synonym,
                            "type": a.type,
                        }
                        for a in ts.attributes
                    ],
                }
                for ts in obj.tabular_sections
            ]

        return result


class MetadataFormsTool(BaseTool):
    """Get forms of a metadata object."""

    name: ClassVar[str] = "metadata.forms"
    description: ClassVar[str] = (
        "Get list of forms for a metadata object."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "description": "Metadata type",
            },
            "name": {
                "type": "string",
                "description": "Object name",
            },
        },
        "required": ["type", "name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Get object forms."""
        type_str = arguments["type"]
        name = arguments["name"]

        try:
            metadata_type = MetadataType(type_str)
        except ValueError:
            metadata_type = MetadataType.from_russian(type_str)
            if metadata_type is None:
                return {"error": f"Unknown metadata type: {type_str}"}

        engine = MetadataEngine.get_instance()
        obj = await engine.get_object(metadata_type, name)

        if obj is None:
            return {"error": f"Object not found: {type_str}.{name}"}

        return {
            "object": obj.full_name,
            "forms": [
                {
                    "name": f.name,
                    "synonym": f.synonym,
                    "form_type": f.form_type,
                    "is_main": f.is_main,
                }
                for f in obj.forms
            ],
        }


class MetadataTemplatesTool(BaseTool):
    """Get templates (layouts) of a metadata object."""

    name: ClassVar[str] = "metadata.templates"
    description: ClassVar[str] = (
        "Get list of templates (layouts) for a metadata object."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "description": "Metadata type",
            },
            "name": {
                "type": "string",
                "description": "Object name",
            },
        },
        "required": ["type", "name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Get object templates."""
        type_str = arguments["type"]
        name = arguments["name"]

        try:
            metadata_type = MetadataType(type_str)
        except ValueError:
            metadata_type = MetadataType.from_russian(type_str)
            if metadata_type is None:
                return {"error": f"Unknown metadata type: {type_str}"}

        engine = MetadataEngine.get_instance()
        obj = await engine.get_object(metadata_type, name)

        if obj is None:
            return {"error": f"Object not found: {type_str}.{name}"}

        return {
            "object": obj.full_name,
            "templates": [
                {
                    "name": t.name,
                    "synonym": t.synonym,
                    "template_type": t.template_type,
                }
                for t in obj.templates
            ],
        }


class MetadataRegistersTool(BaseTool):
    """Get registers that a document writes to."""

    name: ClassVar[str] = "metadata.registers"
    description: ClassVar[str] = (
        "Get list of registers that a document writes to (register records)."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "document": {
                "type": "string",
                "description": "Document name",
            },
        },
        "required": ["document"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Get document registers."""
        doc_name = arguments["document"]

        engine = MetadataEngine.get_instance()
        obj = await engine.get_object(MetadataType.DOCUMENT, doc_name)

        if obj is None:
            return {"error": f"Document not found: {doc_name}"}

        return {
            "document": obj.full_name,
            "posting": obj.posting,
            "register_records": obj.register_records,
        }


class MetadataReferencesTool(BaseTool):
    """Get references and relations of a metadata object."""

    name: ClassVar[str] = "metadata.references"
    description: ClassVar[str] = (
        "Get references and relations of a metadata object: "
        "subsystems, based_on documents, produced documents."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "description": "Metadata type",
            },
            "name": {
                "type": "string",
                "description": "Object name",
            },
        },
        "required": ["type", "name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Get object references."""
        type_str = arguments["type"]
        name = arguments["name"]

        try:
            metadata_type = MetadataType(type_str)
        except ValueError:
            metadata_type = MetadataType.from_russian(type_str)
            if metadata_type is None:
                return {"error": f"Unknown metadata type: {type_str}"}

        engine = MetadataEngine.get_instance()
        obj = await engine.get_object(metadata_type, name)

        if obj is None:
            return {"error": f"Object not found: {type_str}.{name}"}

        return {
            "object": obj.full_name,
            "subsystems": obj.subsystems,
            "based_on": obj.based_on,
            "produces_documents": obj.produces_documents,
            "register_records": obj.register_records,
        }
