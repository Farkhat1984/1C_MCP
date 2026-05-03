"""
BSL Parser.

Parses BSL code to extract procedures, functions, regions, and directives.
Uses regex-based parsing for efficiency.

Phase 2: Extended parsing for method calls, metadata references, and queries.
"""

import asyncio
import re
from pathlib import Path

from mcp_1c.domain.code import (
    BslModule,
    CompilationDirective,
    ExtendedBslModule,
    MetadataReference,
    MetadataReferenceType,
    MethodCall,
    Parameter,
    Procedure,
    QueryReference,
    Region,
    VariableUsage,
)
from mcp_1c.engines.code.reader import BslReader
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


# Regex patterns for BSL parsing
PATTERNS = {
    # Procedure/Function signature
    "procedure": re.compile(
        r"^(?P<directive>&[^\r\n]+[\r\n]+)?\s*"
        r"(?P<async>Асинх\s+|Async\s+)?"
        r"(?P<type>Процедура|Функция|Procedure|Function)\s+"
        r"(?P<name>[a-zA-Zа-яА-ЯёЁ_][a-zA-Zа-яА-ЯёЁ0-9_]*)\s*"
        r"\((?P<params>[^)]*)\)"
        r"(?:\s+Экспорт|\s+Export)?",
        re.MULTILINE | re.IGNORECASE,
    ),
    # End of procedure/function
    "end_procedure": re.compile(
        r"^\s*(?:КонецПроцедуры|КонецФункции|EndProcedure|EndFunction)\s*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    # Region start
    "region_start": re.compile(
        r"^\s*#(?:Область|Region)\s+(?P<name>\S+)",
        re.MULTILINE | re.IGNORECASE,
    ),
    # Region end
    "region_end": re.compile(
        r"^\s*#(?:КонецОбласти|EndRegion)",
        re.MULTILINE | re.IGNORECASE,
    ),
    # Compilation directive
    "directive": re.compile(
        r"^&(?P<directive>[a-zA-Zа-яА-ЯёЁ]+(?:[a-zA-Zа-яА-ЯёЁ]+)*)\s*$",
        re.MULTILINE,
    ),
    # Export keyword
    "export": re.compile(
        r"\bЭкспорт\b|\bExport\b",
        re.IGNORECASE,
    ),
    # Parameter with Знач/Val
    "param_by_val": re.compile(
        r"(?:Знач|Val)\s+([a-zA-Zа-яА-ЯёЁ_][a-zA-Zа-яА-ЯёЁ0-9_]*)",
        re.IGNORECASE,
    ),
    # Comment before procedure
    "doc_comment": re.compile(
        r"(?:^[ \t]*//[^\r\n]*[\r\n]+)+",
        re.MULTILINE,
    ),
}

# Phase 2: Advanced parsing patterns
EXTENDED_PATTERNS = {
    # Method call: MethodName(args) or Object.MethodName(args)
    "method_call": re.compile(
        r"(?:(?P<object>[a-zA-Zа-яА-ЯёЁ_][a-zA-Zа-яА-ЯёЁ0-9_]*)\s*\.\s*)?"
        r"(?P<name>[a-zA-Zа-яА-ЯёЁ_][a-zA-Zа-яА-ЯёЁ0-9_]*)\s*\((?P<args>[^)]*)\)",
        re.IGNORECASE,
    ),
    # Chain method call: ).MethodName(args) - for calls like obj.Method1().Method2()
    "chain_method_call": re.compile(
        r"\)\s*\.\s*(?P<name>[a-zA-Zа-яА-ЯёЁ_][a-zA-Zа-яА-ЯёЁ0-9_]*)\s*\((?P<args>[^)]*)\)",
        re.IGNORECASE,
    ),
    # Async call: Ждать/Await
    "async_call": re.compile(
        r"(?:Ждать|Await)\s+(?P<call>[a-zA-Zа-яА-ЯёЁ_][a-zA-Zа-яА-ЯёЁ0-9_.]*\s*\([^)]*\))",
        re.IGNORECASE,
    ),
    # Query text (multiline): ВЫБРАТЬ ... ИЗ ... or SELECT ... FROM ...
    "query_text": re.compile(
        r'"\s*(?:ВЫБРАТЬ|SELECT)\s+[\s\S]*?(?:;|"\s*(?:\)|;|$))',
        re.IGNORECASE | re.MULTILINE,
    ),
    # Variable assignment: Var = ...
    "assignment": re.compile(
        r"^\s*(?P<var>[a-zA-Zа-яА-ЯёЁ_][a-zA-Zа-яА-ЯёЁ0-9_]*)\s*=",
        re.MULTILINE | re.IGNORECASE,
    ),
    # Comment line
    "comment_line": re.compile(r"^\s*//", re.MULTILINE),
    # String literal (to skip)
    "string_literal": re.compile(r'"[^"]*"'),
}

# Metadata type mappings (Russian and English)
METADATA_TYPE_MAPPING: dict[str, MetadataReferenceType] = {
    # Russian
    "справочники": MetadataReferenceType.CATALOG,
    "справочник": MetadataReferenceType.CATALOG,
    "документы": MetadataReferenceType.DOCUMENT,
    "документ": MetadataReferenceType.DOCUMENT,
    "перечисления": MetadataReferenceType.ENUM,
    "перечисление": MetadataReferenceType.ENUM,
    "отчеты": MetadataReferenceType.REPORT,
    "отчёты": MetadataReferenceType.REPORT,
    "отчет": MetadataReferenceType.REPORT,
    "отчёт": MetadataReferenceType.REPORT,
    "обработки": MetadataReferenceType.DATA_PROCESSOR,
    "обработка": MetadataReferenceType.DATA_PROCESSOR,
    "регистрысведений": MetadataReferenceType.INFORMATION_REGISTER,
    "регистрсведений": MetadataReferenceType.INFORMATION_REGISTER,
    "регистрынакопления": MetadataReferenceType.ACCUMULATION_REGISTER,
    "регистрнакопления": MetadataReferenceType.ACCUMULATION_REGISTER,
    "регистрырасчета": MetadataReferenceType.CALCULATION_REGISTER,
    "регистррасчета": MetadataReferenceType.CALCULATION_REGISTER,
    "регистрыбухгалтерии": MetadataReferenceType.ACCOUNTING_REGISTER,
    "регистрбухгалтерии": MetadataReferenceType.ACCOUNTING_REGISTER,
    "бизнеспроцессы": MetadataReferenceType.BUSINESS_PROCESS,
    "бизнеспроцесс": MetadataReferenceType.BUSINESS_PROCESS,
    "задачи": MetadataReferenceType.TASK,
    "задача": MetadataReferenceType.TASK,
    "планысчетов": MetadataReferenceType.CHART_OF_ACCOUNTS,
    "плансчетов": MetadataReferenceType.CHART_OF_ACCOUNTS,
    "планывидовхарактеристик": MetadataReferenceType.CHART_OF_CHARACTERISTIC_TYPES,
    "планвидовхарактеристик": MetadataReferenceType.CHART_OF_CHARACTERISTIC_TYPES,
    "планывидоврасчета": MetadataReferenceType.CHART_OF_CALCULATION_TYPES,
    "планвидоврасчета": MetadataReferenceType.CHART_OF_CALCULATION_TYPES,
    "планыобмена": MetadataReferenceType.EXCHANGE_PLAN,
    "планобмена": MetadataReferenceType.EXCHANGE_PLAN,
    "константы": MetadataReferenceType.CONSTANT,
    "константа": MetadataReferenceType.CONSTANT,
    "последовательности": MetadataReferenceType.SEQUENCE,
    "последовательность": MetadataReferenceType.SEQUENCE,
    "webсервисы": MetadataReferenceType.WEB_SERVICE,
    "webсервис": MetadataReferenceType.WEB_SERVICE,
    "httpсервисы": MetadataReferenceType.HTTP_SERVICE,
    "httpсервис": MetadataReferenceType.HTTP_SERVICE,
    "общиемодули": MetadataReferenceType.COMMON_MODULE,
    "общиймодуль": MetadataReferenceType.COMMON_MODULE,
    "параметрысеанса": MetadataReferenceType.SESSION_PARAMETER,
    "параметрсеанса": MetadataReferenceType.SESSION_PARAMETER,
    "функциональныеопции": MetadataReferenceType.FUNCTIONAL_OPTION,
    "функциональнаяопция": MetadataReferenceType.FUNCTIONAL_OPTION,
    "определяемыетипы": MetadataReferenceType.DEFINED_TYPE,
    "определяемыйтип": MetadataReferenceType.DEFINED_TYPE,
    "общиереквизиты": MetadataReferenceType.COMMON_ATTRIBUTE,
    "общийреквизит": MetadataReferenceType.COMMON_ATTRIBUTE,
    "подсистемы": MetadataReferenceType.SUBSYSTEM,
    "подсистема": MetadataReferenceType.SUBSYSTEM,
    # English
    "catalogs": MetadataReferenceType.CATALOG,
    "catalog": MetadataReferenceType.CATALOG,
    "documents": MetadataReferenceType.DOCUMENT,
    "document": MetadataReferenceType.DOCUMENT,
    "enums": MetadataReferenceType.ENUM,
    "enum": MetadataReferenceType.ENUM,
    "reports": MetadataReferenceType.REPORT,
    "report": MetadataReferenceType.REPORT,
    "dataprocessors": MetadataReferenceType.DATA_PROCESSOR,
    "dataprocessor": MetadataReferenceType.DATA_PROCESSOR,
    "informationregisters": MetadataReferenceType.INFORMATION_REGISTER,
    "informationregister": MetadataReferenceType.INFORMATION_REGISTER,
    "accumulationregisters": MetadataReferenceType.ACCUMULATION_REGISTER,
    "accumulationregister": MetadataReferenceType.ACCUMULATION_REGISTER,
    "calculationregisters": MetadataReferenceType.CALCULATION_REGISTER,
    "calculationregister": MetadataReferenceType.CALCULATION_REGISTER,
    "accountingregisters": MetadataReferenceType.ACCOUNTING_REGISTER,
    "accountingregister": MetadataReferenceType.ACCOUNTING_REGISTER,
    "businessprocesses": MetadataReferenceType.BUSINESS_PROCESS,
    "businessprocess": MetadataReferenceType.BUSINESS_PROCESS,
    "tasks": MetadataReferenceType.TASK,
    "task": MetadataReferenceType.TASK,
    "chartsofaccounts": MetadataReferenceType.CHART_OF_ACCOUNTS,
    "chartofaccounts": MetadataReferenceType.CHART_OF_ACCOUNTS,
    "chartsofcharacteristictypes": MetadataReferenceType.CHART_OF_CHARACTERISTIC_TYPES,
    "chartofcharacteristictypes": MetadataReferenceType.CHART_OF_CHARACTERISTIC_TYPES,
    "chartsofcalculationtypes": MetadataReferenceType.CHART_OF_CALCULATION_TYPES,
    "chartofcalculationtypes": MetadataReferenceType.CHART_OF_CALCULATION_TYPES,
    "exchangeplans": MetadataReferenceType.EXCHANGE_PLAN,
    "exchangeplan": MetadataReferenceType.EXCHANGE_PLAN,
    "constants": MetadataReferenceType.CONSTANT,
    "constant": MetadataReferenceType.CONSTANT,
    "sequences": MetadataReferenceType.SEQUENCE,
    "sequence": MetadataReferenceType.SEQUENCE,
    "webservices": MetadataReferenceType.WEB_SERVICE,
    "webservice": MetadataReferenceType.WEB_SERVICE,
    "httpservices": MetadataReferenceType.HTTP_SERVICE,
    "httpservice": MetadataReferenceType.HTTP_SERVICE,
    "commonmodules": MetadataReferenceType.COMMON_MODULE,
    "commonmodule": MetadataReferenceType.COMMON_MODULE,
    "sessionparameters": MetadataReferenceType.SESSION_PARAMETER,
    "sessionparameter": MetadataReferenceType.SESSION_PARAMETER,
    "functionaloptions": MetadataReferenceType.FUNCTIONAL_OPTION,
    "functionaloption": MetadataReferenceType.FUNCTIONAL_OPTION,
    "definedtypes": MetadataReferenceType.DEFINED_TYPE,
    "definedtype": MetadataReferenceType.DEFINED_TYPE,
    "commonattributes": MetadataReferenceType.COMMON_ATTRIBUTE,
    "commonattribute": MetadataReferenceType.COMMON_ATTRIBUTE,
    "subsystems": MetadataReferenceType.SUBSYSTEM,
    "subsystem": MetadataReferenceType.SUBSYSTEM,
}

# Metadata reference pattern: Справочники.Номенклатура or Catalogs.Products
METADATA_REFERENCE_PATTERN = re.compile(
    r"\b(?P<type>" + "|".join(METADATA_TYPE_MAPPING.keys()) + r")"
    r"\s*\.\s*(?P<name>[a-zA-Zа-яА-ЯёЁ_][a-zA-Zа-яА-ЯёЁ0-9_]*)",
    re.IGNORECASE,
)


class BslParser:
    """
    Parser for BSL (1C:Enterprise Script) code.

    Extracts:
    - Procedures and functions with signatures
    - Compilation directives
    - Code regions
    - Documentation comments
    """

    def __init__(self) -> None:
        """Initialize parser."""
        self.reader = BslReader()
        self.logger = get_logger(__name__)

    async def parse_file(self, path: Path) -> BslModule:
        """
        Parse BSL file and extract all elements.

        Args:
            path: Path to .bsl file

        Returns:
            Parsed BslModule
        """
        content = await self.reader.read_file(path)
        return await asyncio.to_thread(self.parse_content, content, path)

    def parse_content(self, content: str, path: Path | None = None) -> BslModule:
        """
        Parse BSL content string.

        Args:
            content: BSL code content
            path: Optional source path

        Returns:
            Parsed BslModule
        """
        lines = content.splitlines()
        line_count = len(lines)

        # Parse regions
        regions = self._parse_regions(content, lines)

        # Parse procedures
        procedures = self._parse_procedures(content, lines, regions)

        return BslModule(
            path=path or Path("unknown.bsl"),
            content=content,
            procedures=procedures,
            regions=regions,
            line_count=line_count,
        )

    # Compiled per-line pattern for procedure/function headers — O(line_len) each call
    _PROC_LINE_RE = re.compile(
        r"^\s*(?:Асинх\s+|Async\s+)?"
        r"(?P<type>Процедура|Функция|Procedure|Function)\s+"
        r"(?P<name>[a-zA-Zа-яА-ЯёЁ_][a-zA-Zа-яА-ЯёЁ0-9_]*)\s*"
        r"\((?P<params>[^)]*)\)"
        r"(?P<export>\s+Экспорт|\s+Export)?",
        re.IGNORECASE,
    )
    _PROC_OPEN_RE = re.compile(
        r"^\s*(?:Асинх\s+|Async\s+)?(?:Процедура|Функция|Procedure|Function)\s+\S",
        re.IGNORECASE,
    )
    _DIRECTIVE_RE = re.compile(r"^\s*&\S+", re.IGNORECASE)

    def _parse_procedures(
        self,
        content: str,
        lines: list[str],
        regions: list[Region],
    ) -> list[Procedure]:
        """Parse procedures/functions using a line-by-line scanner (no full-file regex)."""
        procedures: list[Procedure] = []
        n = len(lines)
        i = 0
        while i < n:
            line = lines[i]
            m = self._PROC_LINE_RE.match(line)

            # Handle multi-line parameter lists (params split across lines)
            if m is None and self._PROC_OPEN_RE.match(line):
                combined = line.rstrip()
                j = i + 1
                while j < min(i + 10, n) and ")" not in combined:
                    combined += " " + lines[j].strip()
                    j += 1
                m = self._PROC_LINE_RE.match(combined)

            if m is None:
                i += 1
                continue

            start_line = i + 1  # 1-based

            # Look back for directive on the immediately preceding line
            directive = None
            directive_line_idx = i - 1
            if directive_line_idx >= 0 and self._DIRECTIVE_RE.match(lines[directive_line_idx]):
                directive = self._parse_directive(lines[directive_line_idx].strip())

            # Look back for doc-comment block (consecutive // lines before directive/proc)
            comment = ""
            comment_scan = directive_line_idx if directive is None else directive_line_idx - 1
            comment_lines: list[str] = []
            while comment_scan >= 0 and lines[comment_scan].strip().startswith("//"):
                comment_lines.insert(0, lines[comment_scan])
                comment_scan -= 1
            if comment_lines:
                comment = self._clean_comment("\n".join(comment_lines))

            # Find end of procedure
            end_line = self._find_procedure_end(lines, start_line)

            params = self._parse_parameters(m.group("params"))
            proc_type = m.group("type").lower()
            is_function = proc_type in ("функция", "function")
            is_export = bool(m.group("export"))
            region_name = self._find_containing_region(start_line, regions)

            # Body: from start_line (0-indexed i) to end_line (exclusive, 0-indexed)
            body = "\n".join(lines[i:end_line])
            signature = line.strip()

            procedures.append(
                Procedure(
                    name=m.group("name"),
                    is_function=is_function,
                    is_export=is_export,
                    directive=directive,
                    parameters=params,
                    start_line=start_line,
                    end_line=end_line,
                    signature_line=start_line,
                    body=body,
                    signature=signature,
                    comment=comment,
                    region=region_name,
                )
            )

            # Jump past the end of this procedure
            i = end_line

        return procedures

    def _find_procedure_end(self, lines: list[str], start_line: int) -> int:
        """Find the end line of a procedure/function (1-based start_line)."""
        end_keywords = {"конецпроцедуры", "конецфункции", "endprocedure", "endfunction"}
        for i in range(start_line, len(lines)):
            # Strip semicolons (КонецПроцедуры; is valid BSL)
            clean = lines[i].strip().rstrip(";").strip().lower()
            if clean in end_keywords:
                return i + 1
        return len(lines)

    def _parse_directive(self, directive_str: str) -> CompilationDirective | None:
        """Parse compilation directive string."""
        # Remove & prefix if present
        clean = directive_str.strip()
        if not clean.startswith("&"):
            clean = "&" + clean

        return CompilationDirective.from_string(clean)

    def _parse_parameters(self, params_str: str) -> list[Parameter]:
        """Parse procedure parameters."""
        params: list[Parameter] = []

        if not params_str.strip():
            return params

        for param in params_str.split(","):
            param = param.strip()
            if not param:
                continue

            by_value = False
            default_value = None

            # Check for Знач/Val
            if re.match(r"(?:Знач|Val)\s+", param, re.IGNORECASE):
                by_value = True
                param = re.sub(r"(?:Знач|Val)\s+", "", param, flags=re.IGNORECASE)

            # Check for default value
            if "=" in param:
                parts = param.split("=", 1)
                param = parts[0].strip()
                default_value = parts[1].strip()

            # Extract name
            name_match = re.match(r"([a-zA-Zа-яА-ЯёЁ_][a-zA-Zа-яА-ЯёЁ0-9_]*)", param)
            if name_match:
                params.append(
                    Parameter(
                        name=name_match.group(1),
                        by_value=by_value,
                        default_value=default_value,
                        is_optional=default_value is not None,
                    )
                )

        return params

    def _parse_regions(self, content: str, lines: list[str]) -> list[Region]:
        """Parse code regions."""
        regions: list[Region] = []
        region_stack: list[tuple[str, int]] = []

        for i, line in enumerate(lines, 1):
            # Check for region start
            start_match = PATTERNS["region_start"].match(line)
            if start_match:
                region_stack.append((start_match.group("name"), i))
                continue

            # Check for region end
            if PATTERNS["region_end"].match(line):
                if region_stack:
                    name, start_line = region_stack.pop()
                    regions.append(
                        Region(
                            name=name,
                            start_line=start_line,
                            end_line=i,
                        )
                    )

        return regions

    def _find_containing_region(
        self,
        line: int,
        regions: list[Region],
    ) -> str | None:
        """Find the region containing a line."""
        for region in regions:
            if region.start_line <= line <= region.end_line:
                return region.name
        return None

    def _clean_comment(self, comment: str) -> str:
        """Clean documentation comment."""
        lines = comment.strip().splitlines()
        cleaned = []
        for line in lines:
            # Remove leading // and whitespace
            line = re.sub(r"^\s*//\s?", "", line)
            cleaned.append(line)
        return "\n".join(cleaned)

    async def get_procedure(
        self,
        path: Path,
        procedure_name: str,
    ) -> Procedure | None:
        """
        Get a specific procedure from file.

        Args:
            path: Path to .bsl file
            procedure_name: Procedure name

        Returns:
            Procedure or None
        """
        module = await self.parse_file(path)
        return module.get_procedure(procedure_name)

    async def get_procedures_list(self, path: Path) -> list[dict[str, str]]:
        """
        Get list of procedures with basic info.

        Args:
            path: Path to .bsl file

        Returns:
            List of procedure info dicts
        """
        module = await self.parse_file(path)
        return [
            {
                "name": p.name,
                "type": "Function" if p.is_function else "Procedure",
                "export": p.is_export,
                "directive": p.directive.value if p.directive else None,
                "line": p.signature_line,
            }
            for p in module.procedures
        ]

    # =========================================================================
    # Phase 2: Extended parsing methods
    # =========================================================================

    async def parse_file_extended(self, path: Path) -> ExtendedBslModule:
        """
        Parse BSL file with extended analysis (Phase 2).

        Args:
            path: Path to .bsl file

        Returns:
            ExtendedBslModule with method calls, metadata references, etc.
        """
        content = await self.reader.read_file(path)
        return self.parse_content_extended(content, path)

    def parse_content_extended(
        self, content: str, path: Path | None = None
    ) -> ExtendedBslModule:
        """
        Parse BSL content with extended analysis.

        Args:
            content: BSL code content
            path: Optional source path

        Returns:
            ExtendedBslModule
        """
        # First, do basic parsing
        basic_module = self.parse_content(content, path)

        # Extended parsing
        lines = content.splitlines()
        procedures = basic_module.procedures

        # Extract method calls
        method_calls = self._extract_method_calls(content, lines, procedures)

        # Extract metadata references
        metadata_refs = self._extract_metadata_references(content, lines, procedures)

        # Extract queries
        queries = self._extract_queries(content, lines, procedures)

        # Extract variable usages
        variable_usages = self._extract_variable_usages(content, lines, procedures)

        return ExtendedBslModule(
            path=basic_module.path,
            content=basic_module.content,
            procedures=basic_module.procedures,
            regions=basic_module.regions,
            line_count=basic_module.line_count,
            encoding=basic_module.encoding,
            owner_type=basic_module.owner_type,
            owner_name=basic_module.owner_name,
            module_type=basic_module.module_type,
            method_calls=method_calls,
            metadata_references=metadata_refs,
            queries=queries,
            variable_usages=variable_usages,
        )

    def _extract_method_calls(
        self,
        content: str,
        lines: list[str],
        procedures: list[Procedure],
    ) -> list[MethodCall]:
        """Extract all method calls from code."""
        method_calls: list[MethodCall] = []

        # Create a set of procedure names to exclude
        procedure_names = {p.name.lower() for p in procedures}

        # Keywords to exclude (not method calls)
        # Note: "выполнить/execute" are NOT keywords - they are methods of Query object
        keywords = {
            "если", "тогда", "иначе", "иначеесли", "конецесли",
            "для", "каждого", "из", "по", "цикл", "конеццикла", "пока",
            "попытка", "исключение", "конецпопытки",
            "возврат", "перейти", "продолжить", "прервать",
            "новый", "new",
            "if", "then", "else", "elseif", "endif",
            "for", "each", "in", "to", "do", "enddo", "while",
            "try", "except", "endtry",
            "return", "goto", "continue", "break",
            "процедура", "функция", "procedure", "function",
            "конецпроцедуры", "конецфункции", "endprocedure", "endfunction",
            "и", "или", "не", "and", "or", "not",
            "истина", "ложь", "true", "false", "неопределено", "undefined", "null",
        }

        for i, line in enumerate(lines, 1):
            # Skip comment lines
            stripped = line.strip()
            if stripped.startswith("//"):
                continue

            # Remove string literals to avoid false positives
            line_no_strings = EXTENDED_PATTERNS["string_literal"].sub('""', line)

            # Remove comments at end of line
            comment_pos = line_no_strings.find("//")
            if comment_pos >= 0:
                line_no_strings = line_no_strings[:comment_pos]

            # Find containing procedure (computed once per line)
            containing_proc = self._find_containing_procedure(i, procedures)

            # Find all method calls in line
            for match in EXTENDED_PATTERNS["method_call"].finditer(line_no_strings):
                method_name = match.group("name")
                method_name_lower = method_name.lower()

                # Skip keywords
                if method_name_lower in keywords:
                    continue

                # Skip procedure definitions (not calls)
                if method_name_lower in procedure_names:
                    # Check if this is a definition line
                    if re.search(
                        r"(?:процедура|функция|procedure|function)\s+" + method_name,
                        line,
                        re.IGNORECASE,
                    ):
                        continue

                object_name = match.group("object")
                args_text = match.group("args")

                # Count arguments
                arg_count = 0
                if args_text.strip():
                    # Simple counting by commas (not 100% accurate for nested calls)
                    arg_count = args_text.count(",") + 1

                # Check if async call
                is_async = bool(
                    re.search(
                        r"(?:Ждать|Await)\s+" + re.escape(method_name),
                        line,
                        re.IGNORECASE,
                    )
                )

                method_calls.append(
                    MethodCall(
                        name=method_name,
                        object_name=object_name,
                        arguments_text=args_text.strip(),
                        argument_count=arg_count,
                        line=i,
                        column=match.start(),
                        containing_procedure=containing_proc,
                        is_async_call=is_async,
                    )
                )

            # Find chain method calls: ).Method(args) patterns
            for match in EXTENDED_PATTERNS["chain_method_call"].finditer(line_no_strings):
                method_name = match.group("name")
                method_name_lower = method_name.lower()

                # Skip keywords
                if method_name_lower in keywords:
                    continue

                args_text = match.group("args")

                # Count arguments
                arg_count = 0
                if args_text.strip():
                    arg_count = args_text.count(",") + 1

                # Check if async call
                is_async = bool(
                    re.search(
                        r"(?:Ждать|Await)\s+" + re.escape(method_name),
                        line,
                        re.IGNORECASE,
                    )
                )

                method_calls.append(
                    MethodCall(
                        name=method_name,
                        object_name=None,  # Chain calls don't have explicit object
                        arguments_text=args_text.strip(),
                        argument_count=arg_count,
                        line=i,
                        column=match.start(),
                        containing_procedure=containing_proc,
                        is_async_call=is_async,
                    )
                )

        return method_calls

    def _extract_metadata_references(
        self,
        content: str,
        lines: list[str],
        procedures: list[Procedure],
    ) -> list[MetadataReference]:
        """Extract all metadata references from code."""
        metadata_refs: list[MetadataReference] = []

        for i, line in enumerate(lines, 1):
            # Skip comment lines
            stripped = line.strip()
            if stripped.startswith("//"):
                continue

            # Remove string literals (but we want to find metadata in queries too)
            line_to_search = line

            # Remove comments at end of line
            comment_pos = line_to_search.find("//")
            if comment_pos >= 0:
                line_to_search = line_to_search[:comment_pos]

            # Find metadata references
            for match in METADATA_REFERENCE_PATTERN.finditer(line_to_search):
                type_str = match.group("type").lower()
                object_name = match.group("name")

                # Get metadata type
                ref_type = METADATA_TYPE_MAPPING.get(
                    type_str, MetadataReferenceType.UNKNOWN
                )

                # Determine access type from context
                access_type = self._determine_access_type(line, match.end())

                # Full name
                full_name = f"{match.group('type')}.{object_name}"

                # Find containing procedure
                containing_proc = self._find_containing_procedure(i, procedures)

                metadata_refs.append(
                    MetadataReference(
                        reference_type=ref_type,
                        object_name=object_name,
                        full_name=full_name,
                        access_type=access_type,
                        line=i,
                        column=match.start(),
                        containing_procedure=containing_proc,
                    )
                )

        return metadata_refs

    def _determine_access_type(self, line: str, match_end: int) -> str:
        """Determine how metadata is accessed (manager, ref, selection, object)."""
        # Look at what follows the metadata reference
        rest = line[match_end:].strip()

        if rest.startswith("."):
            # Check for common patterns
            rest_lower = rest.lower()
            if any(
                rest_lower.startswith(f".{method}")
                for method in [
                    "создатьэлемент",
                    "createitem",
                    "создатьдокумент",
                    "createdocument",
                    "создатьгруппу",
                    "creategroup",
                    "получить",
                    "get",
                    "найти",
                    "find",
                    "выбрать",
                    "select",
                ]
            ):
                return "manager"
            elif any(
                rest_lower.startswith(f".{method}")
                for method in ["выбрать", "select", "выбратьпоссылке", "selectbyref"]
            ):
                return "selection"
            elif any(
                rest_lower.startswith(f".{method}")
                for method in ["получитьобъект", "getobject"]
            ):
                return "object"
            elif any(
                rest_lower.startswith(f".{method}")
                for method in ["пустаяссылка", "emptyref", "ссылка", "ref"]
            ):
                return "ref"
            else:
                return "manager"
        elif rest.startswith("("):
            # Called as constructor or function
            return "manager"
        else:
            return "manager"

    def _extract_queries(
        self,
        content: str,
        lines: list[str],
        procedures: list[Procedure],
    ) -> list[QueryReference]:
        """Extract query texts from code."""
        queries: list[QueryReference] = []

        # Pattern for query start
        query_start_pattern = re.compile(
            r'(?:Текст|Text|Запрос\.Текст|Query\.Text)\s*=\s*"',
            re.IGNORECASE,
        )

        # Also look for Новый Запрос patterns
        new_query_pattern = re.compile(
            r'(?:Новый\s+Запрос|New\s+Query)\s*\(\s*"',
            re.IGNORECASE,
        )

        i = 0
        while i < len(lines):
            line = lines[i]

            # Check if this line starts a query
            query_start = query_start_pattern.search(line) or new_query_pattern.search(
                line
            )
            if query_start:
                # Find the query text (may span multiple lines)
                query_text, end_line = self._extract_query_text(lines, i)
                if query_text:
                    # Extract table names from query
                    tables = self._extract_tables_from_query(query_text)

                    # Find containing procedure
                    containing_proc = self._find_containing_procedure(i + 1, procedures)

                    queries.append(
                        QueryReference(
                            query_text=query_text,
                            start_line=i + 1,
                            end_line=end_line + 1,
                            tables=tables,
                            containing_procedure=containing_proc,
                        )
                    )
                    i = end_line
            i += 1

        return queries

    def _extract_query_text(
        self, lines: list[str], start_line: int
    ) -> tuple[str, int]:
        """Extract multiline query text starting from given line."""
        query_parts: list[str] = []
        current_line = start_line

        # Find the opening quote
        line = lines[current_line]
        quote_start = line.find('"')
        if quote_start < 0:
            return "", start_line

        # Start from after the quote
        remaining = line[quote_start + 1 :]

        while current_line < len(lines):
            # Check for closing quote
            quote_end = remaining.find('"')

            if quote_end >= 0:
                # Found closing quote
                query_parts.append(remaining[:quote_end])
                break
            else:
                # No closing quote, continue to next line
                query_parts.append(remaining)

                # Check for line continuation
                current_line += 1
                if current_line < len(lines):
                    next_line = lines[current_line].strip()

                    # Handle line continuation with |
                    if next_line.startswith("|"):
                        remaining = next_line[1:]
                    elif next_line.startswith('"'):
                        # Concatenated string
                        remaining = next_line[1:]
                    else:
                        # Query ended
                        break
                else:
                    break

        return "\n".join(query_parts), current_line

    def _extract_tables_from_query(self, query_text: str) -> list[str]:
        """Extract table names from query text."""
        tables: list[str] = []

        # Pattern for table references in query
        # Matches: Справочник.Номенклатура, Документ.РеализацияТоваров, etc.
        table_pattern = re.compile(
            r"(?:ИЗ|FROM|СОЕДИНЕНИЕ|JOIN|В|IN)\s+"
            r"(?P<table>[a-zA-Zа-яА-ЯёЁ]+\s*\.\s*[a-zA-Zа-яА-ЯёЁ0-9_]+)",
            re.IGNORECASE,
        )

        for match in table_pattern.finditer(query_text):
            table = match.group("table").replace(" ", "")
            if table not in tables:
                tables.append(table)

        return tables

    def _extract_variable_usages(
        self,
        content: str,
        lines: list[str],
        procedures: list[Procedure],
    ) -> list[VariableUsage]:
        """Extract variable usages from code."""
        variable_usages: list[VariableUsage] = []

        # Variable pattern
        var_pattern = re.compile(
            r"\b(?P<name>[a-zA-Zа-яА-ЯёЁ_][a-zA-Zа-яА-ЯёЁ0-9_]*)\b",
            re.IGNORECASE,
        )

        # Keywords to exclude
        keywords = {
            "если", "тогда", "иначе", "иначеесли", "конецесли",
            "для", "каждого", "из", "по", "цикл", "конеццикла", "пока",
            "попытка", "исключение", "конецпопытки",
            "возврат", "перейти", "продолжить", "прервать",
            "новый", "new", "выполнить", "execute",
            "if", "then", "else", "elseif", "endif",
            "for", "each", "in", "to", "do", "enddo", "while",
            "try", "except", "endtry",
            "return", "goto", "continue", "break",
            "процедура", "функция", "procedure", "function",
            "конецпроцедуры", "конецфункции", "endprocedure", "endfunction",
            "и", "или", "не", "and", "or", "not",
            "истина", "ложь", "true", "false", "неопределено", "undefined", "null",
            "знач", "val", "экспорт", "export",
        }

        for i, line in enumerate(lines, 1):
            # Skip comment lines
            stripped = line.strip()
            if stripped.startswith("//"):
                continue

            # Check if this is an assignment line
            assignment_match = EXTENDED_PATTERNS["assignment"].match(line)
            assigned_var = assignment_match.group("var") if assignment_match else None

            # Remove string literals
            line_no_strings = EXTENDED_PATTERNS["string_literal"].sub('""', line)

            # Remove comments
            comment_pos = line_no_strings.find("//")
            if comment_pos >= 0:
                line_no_strings = line_no_strings[:comment_pos]

            # Find containing procedure
            containing_proc = self._find_containing_procedure(i, procedures)

            # Find all variable usages
            for match in var_pattern.finditer(line_no_strings):
                var_name = match.group("name")
                var_name_lower = var_name.lower()

                # Skip keywords
                if var_name_lower in keywords:
                    continue

                # Skip metadata type names
                if var_name_lower in METADATA_TYPE_MAPPING:
                    continue

                is_assignment = (
                    assigned_var is not None
                    and var_name.lower() == assigned_var.lower()
                    and match.start() == line.find(var_name)
                )

                variable_usages.append(
                    VariableUsage(
                        name=var_name,
                        line=i,
                        column=match.start(),
                        is_assignment=is_assignment,
                        containing_procedure=containing_proc,
                    )
                )

        return variable_usages

    def _find_containing_procedure(
        self, line: int, procedures: list[Procedure]
    ) -> str | None:
        """Find the procedure containing a given line."""
        for proc in procedures:
            if proc.start_line <= line <= proc.end_line:
                return proc.name
        return None
