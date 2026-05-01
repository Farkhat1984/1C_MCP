"""
Main Code Engine.

Facade for code reading, parsing, and analysis operations.
"""

import os
import re
from pathlib import Path
from typing import Any

from mcp_1c.domain.code import BslModule, CodeLocation, CodeReference, Procedure
from mcp_1c.domain.metadata import MetadataType, ModuleType
from mcp_1c.engines.code.lsp import (
    BslLspServerManager,
    BslLspUnavailable,
    DocumentSymbolCache,
    LspError,
    lsp_symbols_to_procedures,
)
from mcp_1c.engines.code.parser import BslParser
from mcp_1c.engines.code.reader import BslReader
from mcp_1c.engines.metadata import MetadataEngine
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)

# Configurable limit for file search scope (FIX 14)
MAX_SEARCH_FILES: int = int(os.environ.get("MCP_MAX_SEARCH_FILES", "100"))

# Regex pattern cache for dynamic patterns (FIX 13)
_REGEX_CACHE: dict[str, re.Pattern[str]] = {}

# Pre-compiled static pattern for definition-line detection
_DEFINITION_LINE_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*(?:Процедура|Функция|Procedure|Function)\s+",
    re.IGNORECASE,
)


def _get_pattern(pattern_str: str, flags: int = 0) -> re.Pattern[str]:
    """Get or compile a cached regex pattern.

    Args:
        pattern_str: Regex pattern string.
        flags: Regex flags.

    Returns:
        Compiled pattern.
    """
    cache_key = f"{pattern_str}:{flags}"
    if cache_key not in _REGEX_CACHE:
        _REGEX_CACHE[cache_key] = re.compile(pattern_str, flags)
    return _REGEX_CACHE[cache_key]


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
        # LSP layer is opt-in: created lazily on first use, ``None`` until
        # then. Failure to start (no JAR, no java, MCP_BSL_LS_DISABLED)
        # is sticky for the process lifetime — we don't probe again on
        # every call.
        self._lsp_manager: BslLspServerManager | None = None
        self._lsp_unavailable: bool = False
        self._symbol_cache = DocumentSymbolCache()

    @classmethod
    def get_instance(cls) -> "CodeEngine":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = CodeEngine()
        return cls._instance

    async def get_procedures_lsp(self, path: Path) -> list[Procedure] | None:
        """Extract procedures via bsl-language-server.

        Returns ``None`` when LSP is unavailable so callers can fall back
        to the regex parser without branching on exceptions. A populated
        list (possibly empty for an empty file) means LSP gave the
        authoritative answer.

        Caches by ``(path, mtime, sha256)`` — same file content never
        round-trips through the JVM twice.
        """
        if self._lsp_unavailable:
            return None
        cached = await self._symbol_cache.get(path)
        if cached is None:
            try:
                client = await self._ensure_lsp()
            except BslLspUnavailable as exc:
                self.logger.info(f"LSP unavailable, falling back to regex: {exc}")
                self._lsp_unavailable = True
                return None
            except Exception as exc:
                # Manager startup failed for an unexpected reason; don't
                # poison the engine permanently — let the next call retry.
                self.logger.warning(f"LSP start failed: {exc}")
                return None
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                uri = path.as_uri()
                await client.did_open(uri, text)
                symbols = await client.document_symbol(uri)
                await client.did_close(uri)
            except LspError as exc:
                self.logger.warning(f"LSP request failed for {path}: {exc}")
                return None
            await self._symbol_cache.set(path, symbols)
            cached = symbols
        # Source-line peek lets the adapter distinguish Procedure
        # vs Function when bsl-language-server reports both as
        # ``kind=Method`` with empty detail (0.29.0 behaviour).
        try:
            source_lines = path.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        except OSError:
            source_lines = None
        return lsp_symbols_to_procedures(cached, source_lines=source_lines)

    async def invalidate_lsp_cache(self, path: Path) -> None:
        """Drop cached LSP symbols for a path. Called by the watcher."""
        await self._symbol_cache.invalidate(path)

    async def shutdown_lsp(self) -> None:
        """Stop the bsl-language-server subprocess if it was started."""
        if self._lsp_manager is not None:
            await self._lsp_manager.stop()
            self._lsp_manager = None

    async def find_references_lsp(
        self, path: Path, line: int, character: int
    ) -> list[dict[str, Any]] | None:
        """LSP ``textDocument/references`` for the symbol at ``(line, character)``.

        Returns the LSP ``Location[]`` payload (each entry has ``uri``
        and ``range``). The caller resolves URIs back to paths and
        builds whatever graph it needs. Coordinates are 1-indexed in
        the public API (matching our ``Procedure`` model); we convert
        to LSP's 0-indexed convention internally.

        Returns ``None`` when LSP is unreachable — same contract as
        :meth:`get_procedures_lsp`. Cross-module call resolution in
        :meth:`KnowledgeGraphEngine._extract_code_edges` upgrades from
        ambiguous-name-drop to precise references via this method.

        Suffixed ``_lsp`` to avoid colliding with the legacy
        :meth:`find_definition` name-based search; we may unify the
        APIs once the LSP path is the default for everyone.
        """
        if self._lsp_unavailable:
            return None
        try:
            client = await self._ensure_lsp()
        except BslLspUnavailable as exc:
            self.logger.info(f"LSP unavailable for find_references: {exc}")
            self._lsp_unavailable = True
            return None
        except Exception as exc:
            self.logger.warning(f"LSP start failed: {exc}")
            return None
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            uri = path.as_uri()
            await client.did_open(uri, text)
            try:
                refs = await client.references(
                    uri,
                    line=max(0, line - 1),
                    character=max(0, character - 1),
                    include_declaration=False,
                )
            finally:
                await client.did_close(uri)
        except LspError as exc:
            self.logger.warning(f"LSP references failed for {path}:{line}: {exc}")
            return None
        return refs

    async def find_definition_lsp(
        self, path: Path, line: int, character: int
    ) -> list[dict[str, Any]] | None:
        """LSP ``textDocument/definition``. Same contract as :meth:`find_references_lsp`.

        Used for resolving a symbol token to its declaration site
        when the regex parser can't (e.g. cross-module method call,
        chained access). Returns LSP ``Location[]``; ``None`` when LSP
        is unreachable.
        """
        if self._lsp_unavailable:
            return None
        try:
            client = await self._ensure_lsp()
        except BslLspUnavailable as exc:
            self.logger.info(f"LSP unavailable for find_definition: {exc}")
            self._lsp_unavailable = True
            return None
        except Exception as exc:
            self.logger.warning(f"LSP start failed: {exc}")
            return None
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            uri = path.as_uri()
            await client.did_open(uri, text)
            try:
                locs = await client.definition(
                    uri,
                    line=max(0, line - 1),
                    character=max(0, character - 1),
                )
            finally:
                await client.did_close(uri)
        except LspError as exc:
            self.logger.warning(f"LSP definition failed for {path}:{line}: {exc}")
            return None
        return locs

    async def _ensure_lsp(self):
        """Start bsl-language-server on first use; reuse afterwards.

        Registers an invalidation hook so the symbol cache drops on
        every restart — symbols may differ across server versions or
        after a crash recovered different state.
        """
        if self._lsp_manager is None:
            self._lsp_manager = BslLspServerManager()
            self._lsp_manager.on_restart(self._symbol_cache.clear)
        if not self._lsp_manager.running:
            await self._lsp_manager.start()
        return self._lsp_manager.client

    async def get_module(
        self,
        metadata_type: MetadataType | str,
        object_name: str,
        module_type: ModuleType | str = ModuleType.OBJECT_MODULE,
    ) -> BslModule | None:
        """
        Get parsed module for a metadata object.

        LSP-first: when bsl-language-server is reachable, the procedure
        list is taken from ``documentSymbol`` (precise across escaped
        quotes and nested-paren defaults). The regex parser still
        populates bodies, regions and comments — we merge the two.

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

        module = await self.get_module_by_path(module_path)
        module.owner_type = metadata_type.value
        module.owner_name = object_name
        module.module_type = module_type.value

        return module

    async def get_module_by_path(self, path: Path) -> BslModule:
        """
        Get parsed module by direct path.

        LSP-first listing, regex-rich content. See :meth:`get_module`
        for the merge strategy.

        Args:
            path: Path to .bsl file

        Returns:
            Parsed BslModule
        """
        module = await self.parser.parse_file(path)
        lsp_procs = await self.get_procedures_lsp(path)
        if lsp_procs is not None:
            module.procedures = self._merge_lsp_with_regex(
                lsp_procs, list(module.procedures)
            )
        return module

    @staticmethod
    def _merge_lsp_with_regex(
        lsp_procs: list[Procedure],
        regex_procs: list[Procedure],
    ) -> list[Procedure]:
        """Use LSP procedure listing as the spine, hydrate body/comment/region from regex.

        LSP gives us the authoritative *what's there* (no false negatives
        from quote-escape miscounting, no false positives from nested
        parens in defaults). Regex gives us the body slice the rest of
        the codebase already expects. Match by name first; on collision
        (same name twice — rare but possible) prefer the regex entry
        whose start_line is closest.
        """
        regex_by_name: dict[str, list[Procedure]] = {}
        for p in regex_procs:
            regex_by_name.setdefault(p.name, []).append(p)

        out: list[Procedure] = []
        for lsp_p in lsp_procs:
            candidates = regex_by_name.get(lsp_p.name) or []
            match = None
            if candidates:
                match = min(
                    candidates,
                    key=lambda r, sl=lsp_p.start_line: abs(r.start_line - sl),
                )
                candidates.remove(match)
            if match is None:
                out.append(lsp_p)
                continue
            # LSP wins on positional/signature flags; regex wins on body.
            out.append(
                match.model_copy(
                    update={
                        "is_function": lsp_p.is_function,
                        "is_export": lsp_p.is_export,
                        "start_line": lsp_p.start_line,
                        "end_line": lsp_p.end_line,
                        "signature_line": lsp_p.signature_line,
                        "parameters": (
                            lsp_p.parameters
                            if lsp_p.parameters
                            else match.parameters
                        ),
                    }
                )
            )
        return out

    async def get_procedures(self, path: Path) -> list[Procedure]:
        """Extract the procedure list from a BSL file.

        LSP-first, regex-fallback. Returns the same shape regardless of
        which path was taken, so callers can flip transparently when a
        bsl-language-server jar becomes available. Used by tools that
        only need the procedure listing (complexity counters, dead-code
        analysis); tools that need the full module body should still go
        through :meth:`get_module_by_path`.
        """
        from_lsp = await self.get_procedures_lsp(path)
        if from_lsp is not None:
            return from_lsp
        # Fallback: full regex parse, return only the procedure list.
        module = await self.parser.parse_file(path)
        return list(module.procedures)

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

        # Search for procedure/function definitions (cached per identifier)
        pattern_str = (
            rf"^\s*(?:&[^\r\n]+[\r\n]+)?\s*"
            rf"(?:Процедура|Функция|Procedure|Function)\s+"
            rf"({re.escape(identifier)})\s*\("
        )
        pattern = _get_pattern(pattern_str, re.MULTILINE | re.IGNORECASE)

        for path in paths[:MAX_SEARCH_FILES]:
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

        # Search pattern - matches identifier as word (cached per identifier)
        pattern = _get_pattern(
            rf"\b{re.escape(identifier)}\b", re.IGNORECASE
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
                        # Skip if it's a definition (use pre-compiled pattern)
                        if _DEFINITION_LINE_PATTERN.match(line):
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
