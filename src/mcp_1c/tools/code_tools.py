"""
Code tools for MCP-1C.

Provides tools for working with BSL code.
Phase 2: Extended tools for dependency analysis.
Phase 2.3: Validation, linting, formatting, and complexity analysis tools.
"""

from pathlib import Path
from typing import Any, ClassVar

from mcp_1c.domain.metadata import MetadataType, ModuleType
from mcp_1c.engines.code import CodeEngine, DependencyGraphBuilder, BslLanguageServer
from mcp_1c.engines.metadata import MetadataEngine
from mcp_1c.tools.base import BaseTool


class CodeModuleTool(BaseTool):
    """Get module code for a metadata object."""

    name: ClassVar[str] = "code.module"
    description: ClassVar[str] = (
        "Get the full code of a module for a metadata object. "
        "Returns the BSL code with procedure list."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "description": "Metadata type (e.g., Catalog, Document, CommonModule)",
            },
            "name": {
                "type": "string",
                "description": "Object name",
            },
            "module": {
                "type": "string",
                "description": (
                    "Module type: ObjectModule, ManagerModule, FormModule, "
                    "CommonModule (default: ObjectModule)"
                ),
                "default": "ObjectModule",
            },
            "include_code": {
                "type": "boolean",
                "description": "Include full code content (default: true)",
                "default": True,
            },
        },
        "required": ["type", "name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Get module code."""
        type_str = arguments["type"]
        name = arguments["name"]
        module_str = arguments.get("module", "ObjectModule")
        include_code = arguments.get("include_code", True)

        # Parse metadata type
        try:
            metadata_type = MetadataType(type_str)
        except ValueError:
            metadata_type = MetadataType.from_russian(type_str)
            if metadata_type is None:
                return {"error": f"Unknown metadata type: {type_str}"}

        # Parse module type
        try:
            module_type = ModuleType(module_str)
        except ValueError:
            return {"error": f"Unknown module type: {module_str}"}

        # Get module
        engine = CodeEngine.get_instance()
        module = await engine.get_module(metadata_type, name, module_type)

        if module is None:
            return {
                "error": f"Module not found: {type_str}.{name}/{module_str}"
            }

        result = {
            "object": f"{metadata_type.value}.{name}",
            "module_type": module_type.value,
            "path": str(module.path),
            "line_count": module.line_count,
            "procedures": [
                {
                    "name": p.name,
                    "type": "Function" if p.is_function else "Procedure",
                    "export": p.is_export,
                    "directive": p.directive.value if p.directive else None,
                    "line": p.signature_line,
                    "region": p.region,
                }
                for p in module.procedures
            ],
            "regions": [
                {
                    "name": r.name,
                    "start_line": r.start_line,
                    "end_line": r.end_line,
                }
                for r in module.regions
            ],
        }

        if include_code:
            result["code"] = module.content

        return result


class CodeProcedureTool(BaseTool):
    """Get code of a specific procedure or function."""

    name: ClassVar[str] = "code.procedure"
    description: ClassVar[str] = (
        "Get the code of a specific procedure or function from a module. "
        "Returns the procedure code with signature and parameters."
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
            "procedure": {
                "type": "string",
                "description": "Procedure or function name",
            },
            "module": {
                "type": "string",
                "description": "Module type (default: ObjectModule)",
                "default": "ObjectModule",
            },
        },
        "required": ["type", "name", "procedure"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Get procedure code."""
        type_str = arguments["type"]
        obj_name = arguments["name"]
        proc_name = arguments["procedure"]
        module_str = arguments.get("module", "ObjectModule")

        # Parse types
        try:
            metadata_type = MetadataType(type_str)
        except ValueError:
            metadata_type = MetadataType.from_russian(type_str)
            if metadata_type is None:
                return {"error": f"Unknown metadata type: {type_str}"}

        try:
            module_type = ModuleType(module_str)
        except ValueError:
            return {"error": f"Unknown module type: {module_str}"}

        # Get procedure
        engine = CodeEngine.get_instance()
        procedure = await engine.get_procedure(
            metadata_type,
            obj_name,
            proc_name,
            module_type,
        )

        if procedure is None:
            return {
                "error": f"Procedure not found: {proc_name} in {type_str}.{obj_name}"
            }

        return {
            "object": f"{metadata_type.value}.{obj_name}",
            "module_type": module_type.value,
            "name": procedure.name,
            "type": "Function" if procedure.is_function else "Procedure",
            "export": procedure.is_export,
            "directive": procedure.directive.value if procedure.directive else None,
            "signature": procedure.signature,
            "parameters": [
                {
                    "name": p.name,
                    "by_value": p.by_value,
                    "default": p.default_value,
                    "optional": p.is_optional,
                }
                for p in procedure.parameters
            ],
            "start_line": procedure.start_line,
            "end_line": procedure.end_line,
            "region": procedure.region,
            "comment": procedure.comment,
            "code": procedure.body,
        }


class CodeResolveTool(BaseTool):
    """Find definition of a procedure or function."""

    name: ClassVar[str] = "code.resolve"
    description: ClassVar[str] = (
        "Find the definition of a procedure, function, or identifier. "
        "Searches across the configuration for the definition."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "identifier": {
                "type": "string",
                "description": "Name of procedure, function, or identifier to find",
            },
            "path": {
                "type": "string",
                "description": "Optional: limit search to this path",
            },
        },
        "required": ["identifier"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Find definition."""
        identifier = arguments["identifier"]
        path_str = arguments.get("path")

        search_path = Path(path_str) if path_str else None

        engine = CodeEngine.get_instance()
        definitions = await engine.find_definition(identifier, search_path)

        if not definitions:
            return {
                "identifier": identifier,
                "found": False,
                "definitions": [],
            }

        return {
            "identifier": identifier,
            "found": True,
            "count": len(definitions),
            "definitions": [
                {
                    "file": str(d.location.file_path),
                    "line": d.location.line,
                    "context": d.context,
                }
                for d in definitions
            ],
        }


class CodeUsagesTool(BaseTool):
    """Find all usages of a procedure or identifier."""

    name: ClassVar[str] = "code.usages"
    description: ClassVar[str] = (
        "Find all usages (calls) of a procedure, function, or identifier. "
        "Searches across the configuration."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "identifier": {
                "type": "string",
                "description": "Name to search for",
            },
            "path": {
                "type": "string",
                "description": "Optional: limit search to this path",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results (default: 50)",
                "default": 50,
            },
        },
        "required": ["identifier"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Find usages."""
        identifier = arguments["identifier"]
        path_str = arguments.get("path")
        limit = arguments.get("limit", 50)

        search_path = Path(path_str) if path_str else None

        engine = CodeEngine.get_instance()
        usages = await engine.find_usages(identifier, search_path, limit)

        # Group by file
        by_file: dict[str, list] = {}
        for usage in usages:
            file_path = str(usage.location.file_path)
            if file_path not in by_file:
                by_file[file_path] = []
            by_file[file_path].append({
                "line": usage.location.line,
                "column": usage.location.column,
                "context": usage.context,
            })

        return {
            "identifier": identifier,
            "total_usages": len(usages),
            "files_count": len(by_file),
            "usages_by_file": by_file,
        }


# =============================================================================
# Phase 2: Extended code analysis tools
# =============================================================================


class CodeDependenciesTool(BaseTool):
    """Analyze code dependencies."""

    name: ClassVar[str] = "code.dependencies"
    description: ClassVar[str] = (
        "Analyze dependencies for a procedure or module. "
        "Shows what procedures call this one (callers), "
        "what this procedure calls (callees), "
        "and what metadata objects it uses."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "description": "Metadata type (e.g., Catalog, Document, CommonModule)",
            },
            "name": {
                "type": "string",
                "description": "Object name",
            },
            "procedure": {
                "type": "string",
                "description": "Procedure name (optional - if not specified, analyzes whole module)",
            },
            "module": {
                "type": "string",
                "description": "Module type (default: ObjectModule)",
                "default": "ObjectModule",
            },
            "depth": {
                "type": "integer",
                "description": "Depth of dependency tree (default: 1)",
                "default": 1,
            },
            "include_metadata": {
                "type": "boolean",
                "description": "Include metadata references (default: true)",
                "default": True,
            },
        },
        "required": ["type", "name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Analyze dependencies."""
        type_str = arguments["type"]
        obj_name = arguments["name"]
        proc_name = arguments.get("procedure")
        module_str = arguments.get("module", "ObjectModule")
        depth = arguments.get("depth", 1)
        include_metadata = arguments.get("include_metadata", True)

        # Parse types
        try:
            metadata_type = MetadataType(type_str)
        except ValueError:
            metadata_type = MetadataType.from_russian(type_str)
            if metadata_type is None:
                return {"error": f"Unknown metadata type: {type_str}"}

        try:
            module_type = ModuleType(module_str)
        except ValueError:
            return {"error": f"Unknown module type: {module_str}"}

        # Get module path
        code_engine = CodeEngine.get_instance()
        module = await code_engine.get_module(metadata_type, obj_name, module_type)

        if module is None:
            return {"error": f"Module not found: {type_str}.{obj_name}/{module_str}"}

        # Build dependency graph
        builder = DependencyGraphBuilder()
        extended_module = await builder.parser.parse_file_extended(module.path)
        graph = await builder.build_from_module(extended_module)

        result: dict[str, Any] = {
            "object": f"{metadata_type.value}.{obj_name}",
            "module_type": module_type.value,
            "path": str(module.path),
        }

        if proc_name:
            # Analyze specific procedure
            result["procedure"] = proc_name

            # Get calls made by this procedure
            calls = extended_module.get_calls_in_procedure(proc_name)
            result["calls"] = [
                {
                    "name": call.name,
                    "object": call.object_name,
                    "line": call.line,
                    "is_async": call.is_async_call,
                }
                for call in calls
            ]

            # Get metadata used by this procedure
            if include_metadata:
                metadata_refs = extended_module.get_metadata_in_procedure(proc_name)
                result["metadata_references"] = [
                    {
                        "type": ref.reference_type.value,
                        "object": ref.object_name,
                        "full_name": ref.full_name,
                        "access_type": ref.access_type,
                        "line": ref.line,
                    }
                    for ref in metadata_refs
                ]

            # Get dependency tree
            deps = await builder.get_procedure_dependencies(proc_name, graph, depth)
            result["dependency_tree"] = deps
        else:
            # Analyze whole module
            result["total_procedures"] = len(extended_module.procedures)
            result["total_method_calls"] = len(extended_module.method_calls)
            result["total_metadata_references"] = len(extended_module.metadata_references)
            result["total_queries"] = len(extended_module.queries)

            # Unique called methods
            result["unique_methods_called"] = extended_module.get_unique_called_methods()

            # Unique metadata objects
            if include_metadata:
                result["unique_metadata_objects"] = (
                    extended_module.get_unique_metadata_objects()
                )

            # Queries
            result["queries"] = [
                {
                    "start_line": q.start_line,
                    "end_line": q.end_line,
                    "tables": q.tables,
                    "procedure": q.containing_procedure,
                }
                for q in extended_module.queries
            ]

        return result


class CodeAnalyzeTool(BaseTool):
    """Extended code analysis for a module."""

    name: ClassVar[str] = "code.analyze"
    description: ClassVar[str] = (
        "Perform extended analysis of a BSL module. "
        "Extracts method calls, metadata references, queries, and variable usages."
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
            "module": {
                "type": "string",
                "description": "Module type (default: ObjectModule)",
                "default": "ObjectModule",
            },
            "analysis_type": {
                "type": "string",
                "description": (
                    "Type of analysis: 'full', 'calls', 'metadata', 'queries' "
                    "(default: full)"
                ),
                "default": "full",
            },
        },
        "required": ["type", "name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Perform extended analysis."""
        type_str = arguments["type"]
        obj_name = arguments["name"]
        module_str = arguments.get("module", "ObjectModule")
        analysis_type = arguments.get("analysis_type", "full")

        # Parse types
        try:
            metadata_type = MetadataType(type_str)
        except ValueError:
            metadata_type = MetadataType.from_russian(type_str)
            if metadata_type is None:
                return {"error": f"Unknown metadata type: {type_str}"}

        try:
            module_type = ModuleType(module_str)
        except ValueError:
            return {"error": f"Unknown module type: {module_str}"}

        # Get module
        code_engine = CodeEngine.get_instance()
        module = await code_engine.get_module(metadata_type, obj_name, module_type)

        if module is None:
            return {"error": f"Module not found: {type_str}.{obj_name}/{module_str}"}

        # Parse with extended analysis
        builder = DependencyGraphBuilder()
        extended = await builder.parser.parse_file_extended(module.path)

        result: dict[str, Any] = {
            "object": f"{metadata_type.value}.{obj_name}",
            "module_type": module_type.value,
            "path": str(module.path),
            "line_count": extended.line_count,
        }

        if analysis_type in ("full", "calls"):
            # Method calls analysis
            calls_by_procedure: dict[str, list] = {}
            for call in extended.method_calls:
                proc = call.containing_procedure or "__module__"
                if proc not in calls_by_procedure:
                    calls_by_procedure[proc] = []
                calls_by_procedure[proc].append({
                    "name": call.name,
                    "object": call.object_name,
                    "args_count": call.argument_count,
                    "line": call.line,
                    "is_async": call.is_async_call,
                })

            result["method_calls"] = {
                "total": len(extended.method_calls),
                "unique": len(extended.get_unique_called_methods()),
                "by_procedure": calls_by_procedure,
            }

        if analysis_type in ("full", "metadata"):
            # Metadata references analysis
            metadata_by_type: dict[str, list] = {}
            for ref in extended.metadata_references:
                ref_type = ref.reference_type.value
                if ref_type not in metadata_by_type:
                    metadata_by_type[ref_type] = []
                metadata_by_type[ref_type].append({
                    "object": ref.object_name,
                    "full_name": ref.full_name,
                    "access_type": ref.access_type,
                    "line": ref.line,
                    "procedure": ref.containing_procedure,
                })

            result["metadata_references"] = {
                "total": len(extended.metadata_references),
                "unique": len(extended.get_unique_metadata_objects()),
                "by_type": metadata_by_type,
            }

        if analysis_type in ("full", "queries"):
            # Queries analysis
            result["queries"] = {
                "total": len(extended.queries),
                "list": [
                    {
                        "start_line": q.start_line,
                        "end_line": q.end_line,
                        "tables": q.tables,
                        "procedure": q.containing_procedure,
                        "preview": q.query_text[:200] + "..."
                        if len(q.query_text) > 200
                        else q.query_text,
                    }
                    for q in extended.queries
                ],
            }

        return result


class CodeCallGraphTool(BaseTool):
    """Build call graph for procedures."""

    name: ClassVar[str] = "code.callgraph"
    description: ClassVar[str] = (
        "Build a call graph showing which procedures call which. "
        "Can show callers (who calls this) or callees (what this calls)."
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
            "procedure": {
                "type": "string",
                "description": "Procedure name to analyze",
            },
            "module": {
                "type": "string",
                "description": "Module type (default: ObjectModule)",
                "default": "ObjectModule",
            },
            "direction": {
                "type": "string",
                "description": "'callers', 'callees', or 'both' (default: both)",
                "default": "both",
            },
        },
        "required": ["type", "name", "procedure"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Build call graph."""
        type_str = arguments["type"]
        obj_name = arguments["name"]
        proc_name = arguments["procedure"]
        module_str = arguments.get("module", "ObjectModule")
        direction = arguments.get("direction", "both")

        # Parse types
        try:
            metadata_type = MetadataType(type_str)
        except ValueError:
            metadata_type = MetadataType.from_russian(type_str)
            if metadata_type is None:
                return {"error": f"Unknown metadata type: {type_str}"}

        try:
            module_type = ModuleType(module_str)
        except ValueError:
            return {"error": f"Unknown module type: {module_str}"}

        # Get module
        code_engine = CodeEngine.get_instance()
        module = await code_engine.get_module(metadata_type, obj_name, module_type)

        if module is None:
            return {"error": f"Module not found: {type_str}.{obj_name}/{module_str}"}

        # Build graph
        builder = DependencyGraphBuilder()
        graph = await builder.build_from_file(module.path)

        # Get call graph
        call_graph = await builder.get_call_graph(proc_name, graph, direction)

        return {
            "object": f"{metadata_type.value}.{obj_name}",
            "module_type": module_type.value,
            "procedure": proc_name,
            "direction": direction,
            **call_graph,
        }


# =============================================================================
# Phase 2.3: Validation, Linting, Formatting, and Complexity Analysis
# =============================================================================


class CodeValidateTool(BaseTool):
    """Validate BSL code syntax."""

    name: ClassVar[str] = "code.validate"
    description: ClassVar[str] = (
        "Validate BSL code for syntax errors. "
        "Uses BSL Language Server if available, otherwise performs basic validation. "
        "Returns list of errors and warnings."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "description": "Metadata type (e.g., Catalog, Document, CommonModule)",
            },
            "name": {
                "type": "string",
                "description": "Object name",
            },
            "module": {
                "type": "string",
                "description": "Module type (default: ObjectModule)",
                "default": "ObjectModule",
            },
            "path": {
                "type": "string",
                "description": "Alternative: direct path to .bsl file",
            },
        },
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Validate BSL code."""
        path_str = arguments.get("path")

        if path_str:
            # Direct path
            file_path = Path(path_str)
        else:
            # Get from metadata
            type_str = arguments.get("type")
            obj_name = arguments.get("name")
            module_str = arguments.get("module", "ObjectModule")

            if not type_str or not obj_name:
                return {"error": "Either 'path' or 'type'+'name' must be provided"}

            try:
                metadata_type = MetadataType(type_str)
            except ValueError:
                metadata_type = MetadataType.from_russian(type_str)
                if metadata_type is None:
                    return {"error": f"Unknown metadata type: {type_str}"}

            try:
                module_type = ModuleType(module_str)
            except ValueError:
                return {"error": f"Unknown module type: {module_str}"}

            code_engine = CodeEngine.get_instance()
            module = await code_engine.get_module(metadata_type, obj_name, module_type)

            if module is None:
                return {"error": f"Module not found: {type_str}.{obj_name}/{module_str}"}

            file_path = module.path

        # Validate
        bsl_ls = BslLanguageServer.get_instance()
        result = await bsl_ls.validate_file(file_path)

        return {
            "valid": result.valid,
            "file": str(result.file_path),
            "error_count": result.error_count,
            "warning_count": result.warning_count,
            "info_count": result.info_count,
            "diagnostics": [
                {
                    "code": d.code,
                    "message": d.message,
                    "severity": d.severity.value,
                    "line": d.line,
                    "column": d.column,
                }
                for d in result.diagnostics
            ],
        }


class CodeLintTool(BaseTool):
    """Run static analysis on BSL code."""

    name: ClassVar[str] = "code.lint"
    description: ClassVar[str] = (
        "Run static analysis (linting) on BSL code. "
        "Detects code style issues, potential bugs, and best practice violations. "
        "Can analyze single file or entire directory."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "description": "Metadata type (e.g., Catalog, Document, CommonModule)",
            },
            "name": {
                "type": "string",
                "description": "Object name",
            },
            "module": {
                "type": "string",
                "description": "Module type (default: ObjectModule)",
                "default": "ObjectModule",
            },
            "path": {
                "type": "string",
                "description": "Alternative: direct path to .bsl file or directory",
            },
            "severity_filter": {
                "type": "string",
                "description": "Filter by severity: all, error, warning, info (default: all)",
                "default": "all",
            },
        },
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Run linting."""
        path_str = arguments.get("path")
        severity_filter = arguments.get("severity_filter", "all")

        if path_str:
            target_path = Path(path_str)
        else:
            type_str = arguments.get("type")
            obj_name = arguments.get("name")
            module_str = arguments.get("module", "ObjectModule")

            if not type_str or not obj_name:
                return {"error": "Either 'path' or 'type'+'name' must be provided"}

            try:
                metadata_type = MetadataType(type_str)
            except ValueError:
                metadata_type = MetadataType.from_russian(type_str)
                if metadata_type is None:
                    return {"error": f"Unknown metadata type: {type_str}"}

            try:
                module_type = ModuleType(module_str)
            except ValueError:
                return {"error": f"Unknown module type: {module_str}"}

            code_engine = CodeEngine.get_instance()
            module = await code_engine.get_module(metadata_type, obj_name, module_type)

            if module is None:
                return {"error": f"Module not found: {type_str}.{obj_name}/{module_str}"}

            target_path = module.path

        # Run linting
        bsl_ls = BslLanguageServer.get_instance()

        if target_path.is_dir():
            result = await bsl_ls.lint_directory(target_path)
        else:
            result = await bsl_ls.lint_file(target_path)

        # Filter diagnostics by severity
        diagnostics = result.diagnostics
        if severity_filter != "all":
            diagnostics = [d for d in diagnostics if d.severity.value == severity_filter]

        # Group by file
        by_file: dict[str, list] = {}
        for d in diagnostics:
            file_key = str(d.file_path) if d.file_path else "unknown"
            if file_key not in by_file:
                by_file[file_key] = []
            by_file[file_key].append({
                "code": d.code,
                "message": d.message,
                "severity": d.severity.value,
                "line": d.line,
            })

        return {
            "total_issues": len(diagnostics),
            "files_analyzed": result.files_analyzed,
            "by_severity": result.by_severity,
            "by_rule": result.by_rule,
            "issues_by_file": by_file,
        }


class CodeFormatTool(BaseTool):
    """Format BSL code."""

    name: ClassVar[str] = "code.format"
    description: ClassVar[str] = (
        "Format BSL code according to style guidelines. "
        "Uses BSL Language Server if available, otherwise applies basic formatting. "
        "Returns formatted code without modifying the file."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "description": "Metadata type (e.g., Catalog, Document, CommonModule)",
            },
            "name": {
                "type": "string",
                "description": "Object name",
            },
            "module": {
                "type": "string",
                "description": "Module type (default: ObjectModule)",
                "default": "ObjectModule",
            },
            "path": {
                "type": "string",
                "description": "Alternative: direct path to .bsl file",
            },
            "preview_only": {
                "type": "boolean",
                "description": "Only show preview, don't apply (default: true)",
                "default": True,
            },
        },
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Format BSL code."""
        path_str = arguments.get("path")
        preview_only = arguments.get("preview_only", True)

        if path_str:
            file_path = Path(path_str)
        else:
            type_str = arguments.get("type")
            obj_name = arguments.get("name")
            module_str = arguments.get("module", "ObjectModule")

            if not type_str or not obj_name:
                return {"error": "Either 'path' or 'type'+'name' must be provided"}

            try:
                metadata_type = MetadataType(type_str)
            except ValueError:
                metadata_type = MetadataType.from_russian(type_str)
                if metadata_type is None:
                    return {"error": f"Unknown metadata type: {type_str}"}

            try:
                module_type = ModuleType(module_str)
            except ValueError:
                return {"error": f"Unknown module type: {module_str}"}

            code_engine = CodeEngine.get_instance()
            module = await code_engine.get_module(metadata_type, obj_name, module_type)

            if module is None:
                return {"error": f"Module not found: {type_str}.{obj_name}/{module_str}"}

            file_path = module.path

        if not file_path.exists():
            return {"error": f"File not found: {file_path}"}

        # Read original
        with open(file_path, encoding="utf-8-sig") as f:
            original = f.read()

        # Format
        bsl_ls = BslLanguageServer.get_instance()
        formatted = await bsl_ls.format_file(file_path)

        if formatted is None:
            return {"error": "Formatting failed"}

        # Calculate changes
        original_lines = original.splitlines()
        formatted_lines = formatted.splitlines()
        has_changes = original != formatted

        result = {
            "file": str(file_path),
            "has_changes": has_changes,
            "original_lines": len(original_lines),
            "formatted_lines": len(formatted_lines),
            "preview_only": preview_only,
        }

        if has_changes:
            result["formatted_code"] = formatted

            # Apply if not preview only
            if not preview_only:
                with open(file_path, "w", encoding="utf-8-sig") as f:
                    f.write(formatted)
                result["applied"] = True
        else:
            result["message"] = "Code is already properly formatted"

        return result


class CodeComplexityTool(BaseTool):
    """Analyze code complexity."""

    name: ClassVar[str] = "code.complexity"
    description: ClassVar[str] = (
        "Analyze code complexity metrics. "
        "Calculates cyclomatic complexity, cognitive complexity, "
        "lines of code, and identifies high-complexity procedures."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "description": "Metadata type (e.g., Catalog, Document, CommonModule)",
            },
            "name": {
                "type": "string",
                "description": "Object name",
            },
            "module": {
                "type": "string",
                "description": "Module type (default: ObjectModule)",
                "default": "ObjectModule",
            },
            "path": {
                "type": "string",
                "description": "Alternative: direct path to .bsl file",
            },
            "threshold": {
                "type": "integer",
                "description": "Cyclomatic complexity threshold for 'high complexity' (default: 10)",
                "default": 10,
            },
        },
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Analyze complexity."""
        path_str = arguments.get("path")
        threshold = arguments.get("threshold", 10)

        if path_str:
            file_path = Path(path_str)
        else:
            type_str = arguments.get("type")
            obj_name = arguments.get("name")
            module_str = arguments.get("module", "ObjectModule")

            if not type_str or not obj_name:
                return {"error": "Either 'path' or 'type'+'name' must be provided"}

            try:
                metadata_type = MetadataType(type_str)
            except ValueError:
                metadata_type = MetadataType.from_russian(type_str)
                if metadata_type is None:
                    return {"error": f"Unknown metadata type: {type_str}"}

            try:
                module_type = ModuleType(module_str)
            except ValueError:
                return {"error": f"Unknown module type: {module_str}"}

            code_engine = CodeEngine.get_instance()
            module = await code_engine.get_module(metadata_type, obj_name, module_type)

            if module is None:
                return {"error": f"Module not found: {type_str}.{obj_name}/{module_str}"}

            file_path = module.path

        if not file_path.exists():
            return {"error": f"File not found: {file_path}"}

        # Analyze complexity
        bsl_ls = BslLanguageServer.get_instance()
        result = await bsl_ls.analyze_complexity(file_path)

        # Find high complexity procedures based on threshold
        high_complexity = [
            p.name for p in result.procedures if p.cyclomatic > threshold
        ]

        # Sort procedures by complexity
        sorted_procedures = sorted(
            result.procedures,
            key=lambda p: p.cyclomatic,
            reverse=True,
        )

        return {
            "file": str(file_path),
            "module_metrics": {
                "lines_of_code": result.module_metrics.lines_of_code,
                "blank_lines": result.module_metrics.blank_lines,
                "comment_lines": result.module_metrics.comment_lines,
                "procedure_count": result.module_metrics.procedure_count,
                "function_count": result.module_metrics.function_count,
                "total_cyclomatic": result.module_metrics.cyclomatic,
                "total_cognitive": result.module_metrics.cognitive,
                "max_nesting_depth": result.module_metrics.max_nesting_depth,
            },
            "procedures": [
                {
                    "name": p.name,
                    "type": "Function" if p.is_function else "Procedure",
                    "cyclomatic": p.cyclomatic,
                    "cognitive": p.cognitive,
                    "lines": p.lines,
                    "parameters": p.parameters,
                    "nesting_depth": p.nesting_depth,
                    "start_line": p.start_line,
                }
                for p in sorted_procedures
            ],
            "high_complexity_procedures": high_complexity,
            "complexity_threshold": threshold,
            "summary": {
                "total_procedures": len(result.procedures),
                "high_complexity_count": len(high_complexity),
                "avg_cyclomatic": (
                    sum(p.cyclomatic for p in result.procedures) / len(result.procedures)
                    if result.procedures
                    else 0
                ),
            },
        }
