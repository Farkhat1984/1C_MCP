"""
Analysis tools for MCP-1C.

Provides tools for dead code detection, role/RLS analysis,
and configuration comparison.

Phase 7: Analysis tools.
"""

import hashlib
from pathlib import Path
from typing import Any, ClassVar

from lxml import etree

from mcp_1c.engines.code import CodeEngine, DependencyGraphBuilder
from mcp_1c.engines.metadata import MetadataEngine
from mcp_1c.engines.metadata.parser import _SECURE_PARSER, XmlParser
from mcp_1c.tools.base import BaseTool, ToolError

# Event handler names that should never be flagged as dead code.
# These are called by the platform, not by user code.
_EVENT_HANDLER_NAMES: frozenset[str] = frozenset({
    # Russian
    "присозданиинасервере",
    "приоткрытии",
    "передзаписью",
    "призаписи",
    "послезаписи",
    "обработкапроведения",
    "обработказаполнения",
    "обработкаполученияформы",
    "обработкапроверкизаполнения",
    "передудалением",
    "прикопировании",
    "обработкавыбора",
    "приизменении",
    "приначалеработысистемы",
    "призавершенииработысистемы",
    "обработкаоповещения",
    "обработкавнешнегособытия",
    "передзаписьюнасервере",
    "призаписинасервере",
    "послезаписинасервере",
    "обработкаполученияданныхвыбора",
    "обработкарезультатавыбора",
    "передначаломдобавления",
    "обработканавигационнойссылки",
    "обработкаформирования",
    "принажатии",
    "обработкаактивизациистроки",
    # English
    "oncreatenatserver",
    "onopen",
    "beforewrite",
    "onwrite",
    "afterwrite",
    "posting",
    "filling",
    "ongetform",
    "fillcheckprocessing",
    "beforedelete",
    "oncopy",
    "choiceprocessing",
    "onchange",
    "onstartup",
    "onexit",
    "notificationprocessing",
    "externaleventprocessing",
    "beforewriteatserver",
    "onwriteatserver",
    "afterwriteatserver",
    "choicedatagetprocessing",
    "choiceresultprocessing",
})


class CodeDeadCodeTool(BaseTool):
    """Find unused (dead) code in the configuration."""

    name: ClassVar[str] = "code-dead-code"
    description: ClassVar[str] = (
        "Поиск неиспользуемого кода (мёртвый код). "
        "Находит процедуры и функции, которые нигде не вызываются."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "metadata_type": {
                "type": "string",
                "description": (
                    "Фильтр по типу метаданных "
                    "(Catalog, Document, CommonModule и т.д.)"
                ),
            },
            "include_exports": {
                "type": "boolean",
                "description": "Включать экспортные процедуры (по умолчанию: false)",
                "default": False,
            },
        },
    }

    def __init__(
        self, code_engine: CodeEngine, metadata_engine: MetadataEngine
    ) -> None:
        super().__init__()
        self._code_engine = code_engine
        self._metadata_engine = metadata_engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Detect dead code across BSL files."""
        metadata_type_filter = arguments.get("metadata_type")
        include_exports = arguments.get("include_exports", False)

        config_path = self._metadata_engine.config_path
        if config_path is None:
            raise ToolError(
                "Metadata engine not initialized. Call metadata.init first.",
                code="NOT_INITIALIZED",
            )

        # Collect BSL files, optionally filtered by metadata type folder
        bsl_files = self._collect_bsl_files(config_path, metadata_type_filter)
        if not bsl_files:
            return {"dead_code": [], "total_procedures": 0, "dead_count": 0}

        # Build combined dependency graph across all files
        builder = DependencyGraphBuilder()
        graph = await builder.build_from_files(bsl_files)

        # Build a reverse index: lowercase proc name -> set of node IDs
        # This is needed because call targets are bare names ("ProcName")
        # while node IDs are "ModuleStem::ProcName"
        name_to_nodes: dict[str, set[str]] = {}
        for node_id, node_data in graph.nodes.items():
            if node_data["type"] != "procedure":
                continue
            proc_name = node_data["metadata"].get("name", "")
            name_to_nodes.setdefault(proc_name.lower(), set()).add(node_id)

        # Build caller counts: count how many edges target each procedure
        # Edges have target = bare name (from method_calls), so we must
        # match by lowercase name
        called_names: set[str] = set()
        for edge in graph.edges:
            if edge.edge_type == "calls":
                called_names.add(edge.target.lower())

        # Find dead procedures
        dead_code: list[dict[str, Any]] = []
        for node_id, node_data in graph.nodes.items():
            if node_data["type"] != "procedure":
                continue

            meta = node_data["metadata"]
            proc_name: str = meta.get("name", "")
            is_export: bool = meta.get("is_export", False)
            is_function: bool = meta.get("is_function", False)

            # Skip event handlers
            if proc_name.lower() in _EVENT_HANDLER_NAMES:
                continue

            # Skip exports unless explicitly included
            if is_export and not include_exports:
                continue

            # Check if this procedure is called anywhere
            # Match by bare name (case-insensitive) or by full node ID
            if proc_name.lower() in called_names:
                continue

            # Also check if node_id itself appears as a target
            is_called_by_id = any(
                e.target == node_id
                for e in graph.edges
                if e.edge_type == "calls"
            )
            if is_called_by_id:
                continue

            # Extract module name from node_id ("ModuleStem::ProcName")
            module_name = node_id.split("::")[0] if "::" in node_id else ""

            dead_code.append({
                "name": proc_name,
                "file": meta.get("file", ""),
                "line": meta.get("line", 0),
                "is_export": is_export,
                "is_function": is_function,
                "module_name": module_name,
            })

        # Sort by file then line
        dead_code.sort(key=lambda d: (d["file"], d["line"]))

        return {
            "dead_code": dead_code,
            "total_procedures": sum(
                1 for n in graph.nodes.values() if n["type"] == "procedure"
            ),
            "dead_count": len(dead_code),
            "files_analyzed": len(bsl_files),
        }

    def _collect_bsl_files(
        self, config_path: Path, metadata_type_filter: str | None
    ) -> list[Path]:
        """Collect .bsl files, optionally filtered by metadata type folder."""
        if metadata_type_filter:
            # Map common type names to folder names
            parser = XmlParser()
            from mcp_1c.tools.base import parse_metadata_type

            try:
                mt = parse_metadata_type(metadata_type_filter)
                folder_name = parser._get_type_folder(mt)
            except ToolError:
                # Try as literal folder name
                folder_name = metadata_type_filter

            search_root = config_path / folder_name
            if not search_root.is_dir():
                return []
            return sorted(search_root.rglob("*.bsl"))

        return sorted(config_path.rglob("*.bsl"))


# =========================================================================
# Role / RLS Analysis
# =========================================================================


def _parse_role_xml(role_xml_path: Path) -> dict[str, Any]:
    """Parse a role XML file and extract rights information.

    Args:
        role_xml_path: Path to the role XML file.

    Returns:
        Dict with role name, synonym, and list of object rights.
    """
    tree = etree.parse(str(role_xml_path), _SECURE_PARSER)
    root = tree.getroot()

    # Extract role name
    name_elem = root.xpath(".//*[local-name()='Name']")
    role_name = name_elem[0].text.strip() if name_elem and name_elem[0].text else ""

    synonym_elem = root.xpath(
        ".//*[local-name()='Properties']/*[local-name()='Synonym']"
        "/*[local-name()='v']"
    )
    synonym = ""
    if synonym_elem and synonym_elem[0].text:
        synonym = synonym_elem[0].text.strip()

    # Parse rights
    objects_rights: list[dict[str, Any]] = []
    rights_section = root.xpath(".//*[local-name()='Rights']")

    for rights_elem in rights_section:
        object_elems = rights_elem.xpath("./*[local-name()='Object']")
        for obj_elem in object_elems:
            # Object path — could be an attribute or child element
            obj_path = obj_elem.get("path", "")
            if not obj_path:
                path_child = obj_elem.xpath("./*[local-name()='Name']")
                if path_child and path_child[0].text:
                    obj_path = path_child[0].text.strip()

            rights_list: list[dict[str, Any]] = []
            right_elems = obj_elem.xpath("./*[local-name()='Right']")
            for right_elem in right_elems:
                right_name_el = right_elem.xpath("./*[local-name()='Name']")
                right_value_el = right_elem.xpath("./*[local-name()='Value']")

                right_name = ""
                if right_name_el and right_name_el[0].text:
                    right_name = right_name_el[0].text.strip()
                elif right_elem.get("name"):
                    right_name = right_elem.get("name", "")

                right_value = False
                if right_value_el and right_value_el[0].text:
                    right_value = right_value_el[0].text.strip().lower() == "true"
                elif right_elem.get("value"):
                    right_value = right_elem.get("value", "").lower() == "true"

                # Check for RLS template
                rls_templates: list[str] = []
                if right_name.upper() == "RLS":
                    template_elems = right_elem.xpath(
                        "./*[local-name()='Template']"
                    )
                    for tpl in template_elems:
                        if tpl.text:
                            rls_templates.append(tpl.text.strip())

                right_entry: dict[str, Any] = {
                    "name": right_name,
                    "value": right_value,
                }
                if rls_templates:
                    right_entry["rls_templates"] = rls_templates

                rights_list.append(right_entry)

            if rights_list:
                objects_rights.append({
                    "object": obj_path,
                    "rights": rights_list,
                })

    return {
        "name": role_name,
        "synonym": synonym,
        "objects_count": len(objects_rights),
        "objects": objects_rights,
    }


def _find_role_xml(config_path: Path, role_name: str) -> Path | None:
    """Find XML file for a role by name.

    Supports both directory structures:
    1. Configurator export: Roles/RoleName.xml
    2. Legacy/EDT: Roles/RoleName/RoleName.xml
    """
    roles_dir = config_path / "Roles"
    if not roles_dir.is_dir():
        return None

    # Configurator export
    candidate = roles_dir / f"{role_name}.xml"
    if candidate.exists():
        return candidate

    # Legacy/EDT
    candidate = roles_dir / role_name / f"{role_name}.xml"
    if candidate.exists():
        return candidate

    return None


def _list_role_names(config_path: Path) -> list[str]:
    """List all role names from the configuration."""
    roles_dir = config_path / "Roles"
    if not roles_dir.is_dir():
        return []

    names: set[str] = set()
    for item in sorted(roles_dir.iterdir()):
        if item.is_file() and item.suffix == ".xml":
            names.add(item.stem)
        elif item.is_dir():
            names.add(item.name)
    return sorted(names)


class ConfigRolesTool(BaseTool):
    """Get roles and their access rights."""

    name: ClassVar[str] = "config-roles"
    description: ClassVar[str] = (
        "Получение списка ролей и их прав доступа. "
        "Показывает какие роли существуют и какие права они дают."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Имя роли для детального просмотра. "
                    "Без указания — список всех ролей."
                ),
            },
        },
    }

    def __init__(self, metadata_engine: MetadataEngine) -> None:
        super().__init__()
        self._metadata_engine = metadata_engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Get role information."""
        name = arguments.get("name")

        config_path = self._metadata_engine.config_path
        if config_path is None:
            raise ToolError(
                "Metadata engine not initialized. Call metadata.init first.",
                code="NOT_INITIALIZED",
            )

        if name:
            role_xml = _find_role_xml(config_path, name)
            if role_xml is None:
                return {"error": f"Role '{name}' not found"}

            try:
                return _parse_role_xml(role_xml)
            except etree.XMLSyntaxError as exc:
                raise ToolError(
                    f"Failed to parse role XML: {exc}", code="XML_PARSE_ERROR"
                ) from exc
        else:
            role_names = _list_role_names(config_path)
            roles_summary: list[dict[str, Any]] = []

            for rn in role_names:
                role_xml = _find_role_xml(config_path, rn)
                if role_xml is None:
                    roles_summary.append({"name": rn, "objects_count": 0})
                    continue
                try:
                    parsed = _parse_role_xml(role_xml)
                    roles_summary.append({
                        "name": parsed["name"] or rn,
                        "synonym": parsed.get("synonym", ""),
                        "objects_count": parsed["objects_count"],
                    })
                except Exception:
                    roles_summary.append({"name": rn, "objects_count": 0})

            return {
                "type": "Role",
                "count": len(roles_summary),
                "roles": roles_summary,
            }


class ConfigRoleRightsTool(BaseTool):
    """Analyze access rights for a specific metadata object."""

    name: ClassVar[str] = "config-role-rights"
    description: ClassVar[str] = (
        "Анализ прав доступа для конкретного объекта метаданных. "
        "Показывает какие роли имеют доступ к объекту."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "object_name": {
                "type": "string",
                "description": "Полное имя объекта (например, Catalog.Номенклатура)",
            },
            "right_type": {
                "type": "string",
                "description": (
                    "Фильтр по типу права (Read, Update, Insert, Delete и т.д.)"
                ),
            },
        },
        "required": ["object_name"],
    }

    def __init__(self, metadata_engine: MetadataEngine) -> None:
        super().__init__()
        self._metadata_engine = metadata_engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Find all roles that grant rights to a specific object."""
        object_name = arguments["object_name"]
        right_type_filter = arguments.get("right_type")

        config_path = self._metadata_engine.config_path
        if config_path is None:
            raise ToolError(
                "Metadata engine not initialized. Call metadata.init first.",
                code="NOT_INITIALIZED",
            )

        role_names = _list_role_names(config_path)
        object_name_lower = object_name.lower()

        roles_with_access: list[dict[str, Any]] = []

        for rn in role_names:
            role_xml = _find_role_xml(config_path, rn)
            if role_xml is None:
                continue

            try:
                parsed = _parse_role_xml(role_xml)
            except Exception:
                continue

            for obj_entry in parsed["objects"]:
                if obj_entry["object"].lower() != object_name_lower:
                    continue

                rights = obj_entry["rights"]
                if right_type_filter:
                    rights = [
                        r for r in rights
                        if r["name"].lower() == right_type_filter.lower()
                    ]

                if rights:
                    roles_with_access.append({
                        "role": parsed["name"] or rn,
                        "rights": rights,
                    })

        return {
            "object": object_name,
            "right_type_filter": right_type_filter,
            "roles_count": len(roles_with_access),
            "roles": roles_with_access,
        }


# =========================================================================
# Configuration Comparison
# =========================================================================


class ConfigCompareTool(BaseTool):
    """Compare two 1C configurations."""

    name: ClassVar[str] = "config-compare"
    description: ClassVar[str] = (
        "Сравнение двух конфигураций. "
        "Находит добавленные, удалённые и изменённые объекты метаданных."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path_a": {
                "type": "string",
                "description": "Путь к базовой (эталонной) конфигурации",
            },
            "path_b": {
                "type": "string",
                "description": "Путь к сравниваемой конфигурации",
            },
            "include_modules": {
                "type": "boolean",
                "description": "Включать сравнение модулей (BSL-файлов)",
                "default": True,
            },
            "metadata_type": {
                "type": "string",
                "description": "Фильтр по типу метаданных",
            },
        },
        "required": ["path_a", "path_b"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Compare two configurations."""
        path_a = Path(arguments["path_a"])
        path_b = Path(arguments["path_b"])
        include_modules = arguments.get("include_modules", True)
        metadata_type_filter = arguments.get("metadata_type")

        # Validate paths
        for _label, path in [("path_a", path_a), ("path_b", path_b)]:
            if not path.is_dir():
                raise ToolError(
                    f"Directory not found: {path}", code="PATH_NOT_FOUND"
                )
            if not (path / "Configuration.xml").exists():
                raise ToolError(
                    f"Configuration.xml not found in {path}",
                    code="INVALID_CONFIG",
                )

        parser = XmlParser()
        objects_a = parser.parse_configuration(path_a)
        objects_b = parser.parse_configuration(path_b)

        # Optionally filter by metadata type
        if metadata_type_filter:
            from mcp_1c.tools.base import parse_metadata_type

            try:
                mt = parse_metadata_type(metadata_type_filter)
                filter_key = mt.value
            except ToolError:
                filter_key = metadata_type_filter

            objects_a = {
                k: v for k, v in objects_a.items() if k == filter_key
            }
            objects_b = {
                k: v for k, v in objects_b.items() if k == filter_key
            }

        # Compare object lists by type
        all_types = sorted(set(objects_a.keys()) | set(objects_b.keys()))

        added: list[dict[str, str]] = []
        removed: list[dict[str, str]] = []
        modified: list[dict[str, Any]] = []
        unchanged_count = 0

        for obj_type in all_types:
            names_a = set(objects_a.get(obj_type, []))
            names_b = set(objects_b.get(obj_type, []))

            for name in sorted(names_b - names_a):
                added.append({"type": obj_type, "name": name})

            for name in sorted(names_a - names_b):
                removed.append({"type": obj_type, "name": name})

            # For common objects, compare file hashes
            common_names = sorted(names_a & names_b)
            for name in common_names:
                changes = self._compare_object_files(
                    path_a, path_b, obj_type, name, include_modules
                )
                if changes:
                    modified.append({
                        "type": obj_type,
                        "name": name,
                        "changes": changes,
                    })
                else:
                    unchanged_count += 1

        return {
            "summary": {
                "added": len(added),
                "removed": len(removed),
                "modified": len(modified),
                "unchanged": unchanged_count,
                "types_compared": len(all_types),
            },
            "added": added,
            "removed": removed,
            "modified": modified,
        }

    def _compare_object_files(
        self,
        path_a: Path,
        path_b: Path,
        obj_type: str,
        obj_name: str,
        include_modules: bool,
    ) -> list[str]:
        """Compare XML and BSL files for a single object between two configs.

        Returns a list of change descriptions, empty if identical.
        """
        parser = XmlParser()

        # Resolve type to folder name
        from mcp_1c.tools.base import parse_metadata_type

        try:
            mt = parse_metadata_type(obj_type)
            folder = parser._get_type_folder(mt)
        except ToolError:
            folder = obj_type + "s"

        changes: list[str] = []

        # Compare XML files
        xml_paths = [
            Path(folder) / f"{obj_name}.xml",
            Path(folder) / obj_name / f"{obj_name}.xml",
        ]
        for rel in xml_paths:
            file_a = path_a / rel
            file_b = path_b / rel
            if file_a.exists() and file_b.exists():
                if _file_md5(file_a) != _file_md5(file_b):
                    changes.append(f"XML changed: {rel}")
                break
            elif file_a.exists() != file_b.exists():
                changes.append(f"XML structure differs: {rel}")
                break

        # Compare BSL modules
        if include_modules:
            bsl_dir_a = path_a / folder / obj_name
            bsl_dir_b = path_b / folder / obj_name

            bsl_a = (
                {p.relative_to(bsl_dir_a) for p in bsl_dir_a.rglob("*.bsl")}
                if bsl_dir_a.is_dir()
                else set()
            )
            bsl_b = (
                {p.relative_to(bsl_dir_b) for p in bsl_dir_b.rglob("*.bsl")}
                if bsl_dir_b.is_dir()
                else set()
            )

            for rel_bsl in sorted(bsl_b - bsl_a):
                changes.append(f"BSL added: {rel_bsl}")
            for rel_bsl in sorted(bsl_a - bsl_b):
                changes.append(f"BSL removed: {rel_bsl}")
            for rel_bsl in sorted(bsl_a & bsl_b):
                fa = bsl_dir_a / rel_bsl
                fb = bsl_dir_b / rel_bsl
                if _file_md5(fa) != _file_md5(fb):
                    changes.append(f"BSL changed: {rel_bsl}")

        return changes


def _file_md5(path: Path) -> str:
    """Compute MD5 hex digest of a file."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
