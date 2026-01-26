"""
Main Code Engine.

Facade for code reading, parsing, and analysis operations.
"""

import re
from pathlib import Path

from mcp_1c.domain.code import BslModule, Procedure, CodeLocation, CodeReference
from mcp_1c.domain.metadata import MetadataType, ModuleType
from mcp_1c.engines.code.parser import BslParser
from mcp_1c.engines.code.reader import BslReader
from mcp_1c.engines.metadata import MetadataEngine
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


class CodeEngine:
    """
    Main engine for code operations.

    Provides:
    - Module reading and parsing
    - Procedure extraction
    - Code search and navigation
    - Usage finding
    """

    _instance: "CodeEngine | None" = None

    def __init__(self) -> None:
        """Initialize code engine."""
        self.reader = BslReader()
        self.parser = BslParser()
        self.logger = get_logger(__name__)

    @classmethod
    def get_instance(cls) -> "CodeEngine":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = CodeEngine()
        return cls._instance

    async def get_module(
        self,
        metadata_type: MetadataType | str,
        object_name: str,
        module_type: ModuleType | str = ModuleType.OBJECT_MODULE,
    ) -> BslModule | None:
        """
        Get parsed module for a metadata object.

        Args:
            metadata_type: Type of metadata object
            object_name: Name of object
            module_type: Type of module to get

        Returns:
            Parsed BslModule or None
        """
        if isinstance(metadata_type, str):
            metadata_type = MetadataType(metadata_type)
        if isinstance(module_type, str):
            module_type = ModuleType(module_type)

        # Get metadata object to find module path
        meta_engine = MetadataEngine.get_instance()
        obj = await meta_engine.get_object(metadata_type, object_name)

        if obj is None:
            return None

        # Find module path
        module_path = obj.get_module_path(module_type)
        if module_path is None or not module_path.exists():
            return None

        # Parse and return module
        module = await self.parser.parse_file(module_path)
        module.owner_type = metadata_type.value
        module.owner_name = object_name
        module.module_type = module_type.value

        return module

    async def get_module_by_path(self, path: Path) -> BslModule:
        """
        Get parsed module by direct path.

        Args:
            path: Path to .bsl file

        Returns:
            Parsed BslModule
        """
        return await self.parser.parse_file(path)

    async def get_procedure(
        self,
        metadata_type: MetadataType | str,
        object_name: str,
        procedure_name: str,
        module_type: ModuleType | str = ModuleType.OBJECT_MODULE,
    ) -> Procedure | None:
        """
        Get a specific procedure from a module.

        Args:
            metadata_type: Type of metadata object
            object_name: Name of object
            procedure_name: Name of procedure
            module_type: Type of module

        Returns:
            Procedure or None
        """
        module = await self.get_module(metadata_type, object_name, module_type)
        if module is None:
            return None

        return module.get_procedure(procedure_name)

    async def get_procedure_by_path(
        self,
        path: Path,
        procedure_name: str,
    ) -> Procedure | None:
        """
        Get a specific procedure from a file by path.

        Args:
            path: Path to .bsl file
            procedure_name: Name of procedure

        Returns:
            Procedure or None
        """
        return await self.parser.get_procedure(path, procedure_name)

    async def find_definition(
        self,
        identifier: str,
        search_path: Path | None = None,
    ) -> list[CodeReference]:
        """
        Find definition of an identifier.

        Args:
            identifier: Name to find (procedure, function, variable)
            search_path: Optional path to limit search

        Returns:
            List of found definitions
        """
        definitions: list[CodeReference] = []

        # Determine search scope
        if search_path and search_path.is_file():
            paths = [search_path]
        elif search_path and search_path.is_dir():
            paths = list(search_path.rglob("*.bsl"))
        else:
            # Search in config path
            meta_engine = MetadataEngine.get_instance()
            if meta_engine.config_path:
                paths = list(meta_engine.config_path.rglob("*.bsl"))
            else:
                return definitions

        # Search for procedure/function definitions
        pattern = re.compile(
            rf"^\s*(?:&[^\r\n]+[\r\n]+)?\s*"
            rf"(?:Процедура|Функция|Procedure|Function)\s+"
            rf"({re.escape(identifier)})\s*\(",
            re.MULTILINE | re.IGNORECASE,
        )

        for path in paths[:100]:  # Limit to prevent long searches
            try:
                content = await self.reader.read_file(path)
                for match in pattern.finditer(content):
                    line_num = content[: match.start()].count("\n") + 1
                    lines = content.splitlines()
                    context = lines[line_num - 1] if line_num <= len(lines) else ""

                    definitions.append(
                        CodeReference(
                            location=CodeLocation(
                                file_path=path,
                                line=line_num,
                            ),
                            context=context.strip(),
                            reference_type="definition",
                        )
                    )
            except Exception as e:
                self.logger.debug(f"Error searching {path}: {e}")

        return definitions

    async def find_usages(
        self,
        identifier: str,
        search_path: Path | None = None,
        limit: int = 100,
    ) -> list[CodeReference]:
        """
        Find all usages of an identifier.

        Args:
            identifier: Name to search for
            search_path: Optional path to limit search
            limit: Maximum results

        Returns:
            List of found usages
        """
        usages: list[CodeReference] = []

        # Determine search scope
        if search_path and search_path.is_file():
            paths = [search_path]
        elif search_path and search_path.is_dir():
            paths = list(search_path.rglob("*.bsl"))
        else:
            meta_engine = MetadataEngine.get_instance()
            if meta_engine.config_path:
                paths = list(meta_engine.config_path.rglob("*.bsl"))
            else:
                return usages

        # Search pattern - matches identifier as word
        pattern = re.compile(
            rf"\b{re.escape(identifier)}\b",
            re.IGNORECASE,
        )

        for path in paths:
            if len(usages) >= limit:
                break

            try:
                content = await self.reader.read_file(path)
                lines = content.splitlines()

                for i, line in enumerate(lines, 1):
                    if len(usages) >= limit:
                        break

                    for match in pattern.finditer(line):
                        # Skip if it's a definition
                        if re.match(
                            r"^\s*(?:Процедура|Функция|Procedure|Function)\s+",
                            line,
                            re.IGNORECASE,
                        ):
                            continue

                        usages.append(
                            CodeReference(
                                location=CodeLocation(
                                    file_path=path,
                                    line=i,
                                    column=match.start(),
                                ),
                                context=line.strip(),
                                reference_type="usage",
                            )
                        )
            except Exception as e:
                self.logger.debug(f"Error searching {path}: {e}")

        return usages

    async def get_common_module_code(
        self,
        module_name: str,
    ) -> BslModule | None:
        """
        Get code of a common module.

        Args:
            module_name: Common module name

        Returns:
            Parsed BslModule or None
        """
        return await self.get_module(
            MetadataType.COMMON_MODULE,
            module_name,
            ModuleType.COMMON_MODULE,
        )

    async def list_procedures(
        self,
        metadata_type: MetadataType | str,
        object_name: str,
        module_type: ModuleType | str = ModuleType.OBJECT_MODULE,
    ) -> list[dict]:
        """
        List all procedures in a module.

        Args:
            metadata_type: Type of metadata object
            object_name: Name of object
            module_type: Type of module

        Returns:
            List of procedure info dicts
        """
        module = await self.get_module(metadata_type, object_name, module_type)
        if module is None:
            return []

        return [
            {
                "name": p.name,
                "is_function": p.is_function,
                "is_export": p.is_export,
                "directive": p.directive.value if p.directive else None,
                "line": p.signature_line,
                "signature": p.signature,
                "region": p.region,
                "parameters": [
                    {
                        "name": param.name,
                        "by_value": param.by_value,
                        "default": param.default_value,
                    }
                    for param in p.parameters
                ],
            }
            for p in module.procedures
        ]
