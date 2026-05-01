"""
BSL Language Server integration.

Provides integration with BSL Language Server for:
- Code validation and diagnostics
- Static analysis (linting)
- Code formatting
- Complexity analysis
"""

import asyncio
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


class DiagnosticSeverity(str, Enum):
    """Diagnostic severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    HINT = "hint"


class Diagnostic(BaseModel):
    """Single diagnostic from BSL LS."""

    code: str = Field(..., description="Diagnostic rule code")
    message: str = Field(..., description="Diagnostic message")
    severity: DiagnosticSeverity = Field(..., description="Severity level")
    source: str = Field(default="bsl-ls", description="Diagnostic source")
    line: int = Field(..., description="Line number (1-based)")
    column: int = Field(default=0, description="Column number")
    end_line: int | None = Field(default=None, description="End line")
    end_column: int | None = Field(default=None, description="End column")
    file_path: Path | None = Field(default=None, description="File path")


class ValidationResult(BaseModel):
    """Result of code validation."""

    valid: bool = Field(..., description="Whether code is valid")
    error_count: int = Field(default=0, description="Number of errors")
    warning_count: int = Field(default=0, description="Number of warnings")
    info_count: int = Field(default=0, description="Number of info messages")
    diagnostics: list[Diagnostic] = Field(
        default_factory=list,
        description="List of diagnostics",
    )
    file_path: Path | None = Field(default=None, description="Analyzed file")


class LintResult(BaseModel):
    """Result of static analysis (linting)."""

    total_issues: int = Field(default=0, description="Total issues found")
    by_severity: dict[str, int] = Field(
        default_factory=dict,
        description="Issues count by severity",
    )
    by_rule: dict[str, int] = Field(
        default_factory=dict,
        description="Issues count by rule code",
    )
    diagnostics: list[Diagnostic] = Field(
        default_factory=list,
        description="All diagnostics",
    )
    files_analyzed: int = Field(default=0, description="Number of files analyzed")


class ComplexityMetrics(BaseModel):
    """Code complexity metrics."""

    cyclomatic: int = Field(default=0, description="Cyclomatic complexity")
    cognitive: int = Field(default=0, description="Cognitive complexity")
    lines_of_code: int = Field(default=0, description="Lines of code")
    comment_lines: int = Field(default=0, description="Comment lines")
    blank_lines: int = Field(default=0, description="Blank lines")
    procedure_count: int = Field(default=0, description="Number of procedures")
    function_count: int = Field(default=0, description="Number of functions")
    max_nesting_depth: int = Field(default=0, description="Maximum nesting depth")


class ProcedureComplexity(BaseModel):
    """Complexity for a single procedure."""

    name: str = Field(..., description="Procedure name")
    is_function: bool = Field(default=False, description="Is function")
    cyclomatic: int = Field(default=0, description="Cyclomatic complexity")
    cognitive: int = Field(default=0, description="Cognitive complexity")
    lines: int = Field(default=0, description="Lines of code")
    parameters: int = Field(default=0, description="Number of parameters")
    nesting_depth: int = Field(default=0, description="Maximum nesting depth")
    start_line: int = Field(default=0, description="Start line")


class ModuleComplexityResult(BaseModel):
    """Complexity analysis result for a module."""

    file_path: Path | None = Field(default=None, description="File path")
    module_metrics: ComplexityMetrics = Field(
        default_factory=ComplexityMetrics,
        description="Module-level metrics",
    )
    procedures: list[ProcedureComplexity] = Field(
        default_factory=list,
        description="Per-procedure complexity",
    )
    high_complexity_procedures: list[str] = Field(
        default_factory=list,
        description="Procedures with high complexity",
    )


@dataclass
class BslLsConfig:
    """BSL Language Server configuration."""

    bsl_ls_path: str | None = None
    java_path: str = "java"
    configuration_path: Path | None = None
    config_file: Path | None = None  # .bsl-language-server.json
    reporter: str = "json"
    timeout: int = 120  # seconds
    additional_args: list[str] = field(default_factory=list)


class BslLanguageServer:
    """
    Integration with BSL Language Server.

    Uses BSL LS CLI for analysis operations.
    Falls back to internal analysis if BSL LS is not available.
    """

    _instance: "BslLanguageServer | None" = None

    def __init__(self, config: BslLsConfig | None = None) -> None:
        """Initialize BSL LS integration."""
        self.config = config or BslLsConfig()
        self.logger = get_logger(__name__)
        self._bsl_ls_available: bool | None = None
        self._bsl_ls_version: str | None = None

    @classmethod
    def get_instance(cls, config: BslLsConfig | None = None) -> "BslLanguageServer":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = BslLanguageServer(config)
        return cls._instance

    async def check_availability(self) -> bool:
        """Check if BSL Language Server is available."""
        if self._bsl_ls_available is not None:
            return self._bsl_ls_available

        # Try to find BSL LS
        bsl_ls_path = self._find_bsl_ls()
        if bsl_ls_path is None:
            self.logger.warning("BSL Language Server not found")
            self._bsl_ls_available = False
            return False

        # Try to get version
        try:
            version = await self._get_bsl_ls_version(bsl_ls_path)
            if version:
                self.logger.info(f"BSL Language Server found: {version}")
                self._bsl_ls_version = version
                self._bsl_ls_available = True
                self.config.bsl_ls_path = bsl_ls_path
                return True
        except Exception as e:
            self.logger.warning(f"Error checking BSL LS: {e}")

        self._bsl_ls_available = False
        return False

    def _find_bsl_ls(self) -> str | None:
        """Find BSL Language Server executable."""
        # Check configured path
        if self.config.bsl_ls_path:
            if Path(self.config.bsl_ls_path).exists():
                return self.config.bsl_ls_path

        # Common locations
        common_paths = [
            "bsl-language-server",
            "bsl-language-server.jar",
            # Windows
            Path.home() / ".bsl-language-server" / "bsl-language-server.jar",
            Path("C:/") / "bsl-language-server" / "bsl-language-server.jar",
            # Linux/Mac
            Path("/usr/local/bin/bsl-language-server"),
            Path.home() / "bin" / "bsl-language-server.jar",
        ]

        for path in common_paths:
            if isinstance(path, Path):
                if path.exists():
                    return str(path)
            else:
                # Check if in PATH
                found = shutil.which(path)
                if found:
                    return found

        return None

    async def _get_bsl_ls_version(self, bsl_ls_path: str) -> str | None:
        """Get BSL LS version."""
        try:
            cmd = self._build_command(bsl_ls_path, ["--version"])
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=10,
            )
            return stdout.decode("utf-8").strip()
        except Exception:
            return None

    def _build_command(
        self,
        bsl_ls_path: str,
        args: list[str],
    ) -> list[str]:
        """Build command to run BSL LS."""
        if bsl_ls_path.endswith(".jar"):
            return [self.config.java_path, "-jar", bsl_ls_path, *args]
        return [bsl_ls_path, *args]

    async def validate_file(self, file_path: Path) -> ValidationResult:
        """
        Validate a single BSL file.

        Args:
            file_path: Path to .bsl file

        Returns:
            ValidationResult with diagnostics
        """
        if not file_path.exists():
            return ValidationResult(
                valid=False,
                error_count=1,
                diagnostics=[
                    Diagnostic(
                        code="FILE_NOT_FOUND",
                        message=f"File not found: {file_path}",
                        severity=DiagnosticSeverity.ERROR,
                        line=0,
                        file_path=file_path,
                    )
                ],
                file_path=file_path,
            )

        # Check BSL LS availability
        if await self.check_availability():
            return await self._validate_with_bsl_ls(file_path)
        else:
            return await self._validate_internal(file_path)

    async def _validate_with_bsl_ls(self, file_path: Path) -> ValidationResult:
        """Validate using BSL Language Server."""
        try:
            # Create temporary output directory
            with tempfile.TemporaryDirectory() as tmpdir:
                output_file = Path(tmpdir) / "report.json"

                args = [
                    "--analyze",
                    "--srcDir", str(file_path.parent),
                    "--outputDir", tmpdir,
                    "--reporter", "json",
                ]

                if self.config.config_file and self.config.config_file.exists():
                    args.extend(["--configuration", str(self.config.config_file)])

                cmd = self._build_command(self.config.bsl_ls_path, args)

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                _, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.config.timeout,
                )

                # Parse results
                if output_file.exists():
                    return self._parse_bsl_ls_report(output_file, file_path)

                # No report generated - check stderr
                if stderr:
                    self.logger.warning(f"BSL LS stderr: {stderr.decode('utf-8')}")

                return ValidationResult(valid=True, file_path=file_path)

        except TimeoutError:
            return ValidationResult(
                valid=False,
                error_count=1,
                diagnostics=[
                    Diagnostic(
                        code="TIMEOUT",
                        message="Validation timed out",
                        severity=DiagnosticSeverity.ERROR,
                        line=0,
                        file_path=file_path,
                    )
                ],
                file_path=file_path,
            )
        except Exception as e:
            self.logger.error(f"Error validating with BSL LS: {e}")
            return await self._validate_internal(file_path)

    def _parse_bsl_ls_report(
        self,
        report_path: Path,
        target_file: Path,
    ) -> ValidationResult:
        """Parse BSL LS JSON report."""
        try:
            with open(report_path, encoding="utf-8") as f:
                report = json.load(f)

            diagnostics: list[Diagnostic] = []
            target_name = target_file.name.lower()

            for file_report in report.get("fileinfos", []):
                file_uri = file_report.get("fileUri", "")
                if target_name not in file_uri.lower():
                    continue

                for diag in file_report.get("diagnostics", []):
                    severity = self._map_severity(diag.get("severity", 1))
                    range_info = diag.get("range", {})
                    start = range_info.get("start", {})
                    end = range_info.get("end", {})

                    diagnostics.append(
                        Diagnostic(
                            code=diag.get("code", "UNKNOWN"),
                            message=diag.get("message", ""),
                            severity=severity,
                            source=diag.get("source", "bsl-ls"),
                            line=start.get("line", 0) + 1,  # LSP uses 0-based
                            column=start.get("character", 0),
                            end_line=end.get("line", 0) + 1 if end else None,
                            end_column=end.get("character", 0) if end else None,
                            file_path=target_file,
                        )
                    )

            error_count = sum(1 for d in diagnostics if d.severity == DiagnosticSeverity.ERROR)
            warning_count = sum(1 for d in diagnostics if d.severity == DiagnosticSeverity.WARNING)
            info_count = sum(1 for d in diagnostics if d.severity == DiagnosticSeverity.INFO)

            return ValidationResult(
                valid=error_count == 0,
                error_count=error_count,
                warning_count=warning_count,
                info_count=info_count,
                diagnostics=diagnostics,
                file_path=target_file,
            )

        except Exception as e:
            self.logger.error(f"Error parsing BSL LS report: {e}")
            return ValidationResult(valid=True, file_path=target_file)

    def _map_severity(self, lsp_severity: int) -> DiagnosticSeverity:
        """Map LSP severity to our enum."""
        mapping = {
            1: DiagnosticSeverity.ERROR,
            2: DiagnosticSeverity.WARNING,
            3: DiagnosticSeverity.INFO,
            4: DiagnosticSeverity.HINT,
        }
        return mapping.get(lsp_severity, DiagnosticSeverity.INFO)

    async def _validate_internal(self, file_path: Path) -> ValidationResult:
        """Internal validation without BSL LS (basic syntax check)."""
        from mcp_1c.engines.code.parser import BslParser

        parser = BslParser()
        diagnostics: list[Diagnostic] = []

        try:
            # Try to parse the file
            module = await parser.parse_file(file_path)

            # Basic validation checks
            content = module.content
            lines = content.splitlines()

            # Check for unbalanced blocks
            block_balance = self._check_block_balance(lines)
            for issue in block_balance:
                diagnostics.append(
                    Diagnostic(
                        code="UNBALANCED_BLOCK",
                        message=issue["message"],
                        severity=DiagnosticSeverity.ERROR,
                        line=issue["line"],
                        file_path=file_path,
                    )
                )

            # Check for common syntax issues
            syntax_issues = self._check_syntax_issues(lines)
            for issue in syntax_issues:
                diagnostics.append(
                    Diagnostic(
                        code=issue["code"],
                        message=issue["message"],
                        severity=DiagnosticSeverity(issue.get("severity", "warning")),
                        line=issue["line"],
                        file_path=file_path,
                    )
                )

            error_count = sum(1 for d in diagnostics if d.severity == DiagnosticSeverity.ERROR)
            warning_count = sum(1 for d in diagnostics if d.severity == DiagnosticSeverity.WARNING)

            return ValidationResult(
                valid=error_count == 0,
                error_count=error_count,
                warning_count=warning_count,
                diagnostics=diagnostics,
                file_path=file_path,
            )

        except Exception as e:
            return ValidationResult(
                valid=False,
                error_count=1,
                diagnostics=[
                    Diagnostic(
                        code="PARSE_ERROR",
                        message=str(e),
                        severity=DiagnosticSeverity.ERROR,
                        line=0,
                        file_path=file_path,
                    )
                ],
                file_path=file_path,
            )

    def _check_block_balance(self, lines: list[str]) -> list[dict]:
        """Check for balanced blocks (Если/КонецЕсли, etc.)."""
        issues = []
        block_stack: list[tuple[str, int]] = []

        # Block pairs (start, end)
        blocks_ru = {
            "если": "конецесли",
            "для": "конеццикла",
            "пока": "конеццикла",
            "процедура": "конецпроцедуры",
            "функция": "конецфункции",
            "попытка": "конецпопытки",
            "выбор": "конецвыбора",
        }
        blocks_en = {
            "if": "endif",
            "for": "enddo",
            "while": "enddo",
            "procedure": "endprocedure",
            "function": "endfunction",
            "try": "endtry",
            "select": "endselect",
        }

        all_starts = set(blocks_ru.keys()) | set(blocks_en.keys())
        all_ends = set(blocks_ru.values()) | set(blocks_en.values())
        block_map = {**blocks_ru, **blocks_en}

        import re
        for i, line in enumerate(lines, 1):
            # Remove comments and strings for analysis
            clean_line = self._remove_comments_and_strings(line).lower().strip()
            # Extract words (ignoring punctuation)
            words = re.findall(r'\b[a-zа-яё]+\b', clean_line)

            for word in words:
                if word in all_starts:
                    block_stack.append((word, i))
                elif word in all_ends:
                    if not block_stack:
                        issues.append({
                            "message": f"Unexpected '{word}' without matching start",
                            "line": i,
                        })
                    else:
                        start_word, _ = block_stack[-1]
                        expected_end = block_map.get(start_word)
                        if expected_end == word:
                            block_stack.pop()
                        else:
                            issues.append({
                                "message": f"Expected '{expected_end}' but found '{word}'",
                                "line": i,
                            })

        # Check for unclosed blocks
        for word, line in block_stack:
            issues.append({
                "message": f"Unclosed block '{word}'",
                "line": line,
            })

        return issues

    def _check_syntax_issues(self, lines: list[str]) -> list[dict]:
        """Check for common syntax issues."""
        issues = []

        for i, line in enumerate(lines, 1):
            clean_line = self._remove_comments_and_strings(line)

            # Check for missing semicolons (basic heuristic)
            stripped = clean_line.strip()
            if stripped and not stripped.endswith(";"):
                # Skip lines that don't need semicolons
                skip_patterns = [
                    "если", "тогда", "иначе", "иначеесли", "конецесли",
                    "для", "по", "цикл", "пока", "конеццикла",
                    "процедура", "функция", "конецпроцедуры", "конецфункции",
                    "попытка", "исключение", "конецпопытки",
                    "выбор", "когда", "другое", "конецвыбора",
                    "#область", "#конецобласти", "#if", "#endif",
                    "if", "then", "else", "elseif", "endif",
                    "for", "to", "do", "while", "enddo",
                    "procedure", "function", "endprocedure", "endfunction",
                    "try", "except", "endtry",
                    "select", "when", "otherwise", "endselect",
                    "#region", "#endregion",
                    "&", "//",
                ]
                lower_stripped = stripped.lower()
                if not any(lower_stripped.startswith(p) or lower_stripped.endswith(p) for p in skip_patterns):
                    # This is a very basic check - real validation would be more sophisticated
                    pass  # Skip for now to avoid false positives

            # Check for deprecated keywords
            deprecated = {
                "перейти": "GOTO is deprecated, use structured control flow",
                "goto": "GOTO is deprecated, use structured control flow",
            }
            for word, msg in deprecated.items():
                if word in clean_line.lower():
                    issues.append({
                        "code": "DEPRECATED_KEYWORD",
                        "message": msg,
                        "line": i,
                        "severity": "warning",
                    })

        return issues

    def _remove_comments_and_strings(self, line: str) -> str:
        """Remove comments and string literals from line for analysis."""
        result = []
        in_string = False
        string_char = None
        i = 0

        while i < len(line):
            char = line[i]

            if not in_string:
                # Check for comment
                if char == "/" and i + 1 < len(line) and line[i + 1] == "/":
                    break  # Rest is comment

                # Check for string start
                if char in '"\'':
                    in_string = True
                    string_char = char
                    i += 1
                    continue

                result.append(char)
            else:
                # In string - look for end
                if char == string_char:
                    # Check for escaped quote
                    if i + 1 < len(line) and line[i + 1] == string_char:
                        i += 2
                        continue
                    in_string = False

            i += 1

        return "".join(result)

    async def lint_file(self, file_path: Path) -> LintResult:
        """
        Run static analysis on a file.

        Args:
            file_path: Path to .bsl file

        Returns:
            LintResult with all diagnostics
        """
        validation = await self.validate_file(file_path)

        by_severity: dict[str, int] = {}
        by_rule: dict[str, int] = {}

        for diag in validation.diagnostics:
            # Count by severity
            sev = diag.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

            # Count by rule
            by_rule[diag.code] = by_rule.get(diag.code, 0) + 1

        return LintResult(
            total_issues=len(validation.diagnostics),
            by_severity=by_severity,
            by_rule=by_rule,
            diagnostics=validation.diagnostics,
            files_analyzed=1,
        )

    async def lint_directory(self, dir_path: Path) -> LintResult:
        """
        Run static analysis on all BSL files in directory.

        Args:
            dir_path: Path to directory

        Returns:
            LintResult with aggregated diagnostics
        """
        all_diagnostics: list[Diagnostic] = []
        files_analyzed = 0

        for bsl_file in dir_path.rglob("*.bsl"):
            result = await self.lint_file(bsl_file)
            all_diagnostics.extend(result.diagnostics)
            files_analyzed += 1

        by_severity: dict[str, int] = {}
        by_rule: dict[str, int] = {}

        for diag in all_diagnostics:
            sev = diag.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1
            by_rule[diag.code] = by_rule.get(diag.code, 0) + 1

        return LintResult(
            total_issues=len(all_diagnostics),
            by_severity=by_severity,
            by_rule=by_rule,
            diagnostics=all_diagnostics,
            files_analyzed=files_analyzed,
        )

    async def format_file(self, file_path: Path) -> str | None:
        """
        Format a BSL file.

        Args:
            file_path: Path to .bsl file

        Returns:
            Formatted code or None if formatting failed
        """
        if not file_path.exists():
            return None

        # Check BSL LS availability
        if await self.check_availability():
            return await self._format_with_bsl_ls(file_path)
        else:
            return await self._format_internal(file_path)

    async def _format_with_bsl_ls(self, file_path: Path) -> str | None:
        """Format using BSL Language Server."""
        try:
            # BSL LS format command
            args = [
                "--format",
                "--src", str(file_path),
            ]

            if self.config.config_file and self.config.config_file.exists():
                args.extend(["--configuration", str(self.config.config_file)])

            cmd = self._build_command(self.config.bsl_ls_path, args)

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.config.timeout,
            )

            if process.returncode == 0:
                return stdout.decode("utf-8")

            self.logger.warning(f"BSL LS format failed: {stderr.decode('utf-8')}")
            return await self._format_internal(file_path)

        except Exception as e:
            self.logger.error(f"Error formatting with BSL LS: {e}")
            return await self._format_internal(file_path)

    async def _format_internal(self, file_path: Path) -> str | None:
        """Internal formatting (basic)."""
        try:
            with open(file_path, encoding="utf-8-sig") as f:
                content = f.read()

            # Basic formatting rules
            lines = content.splitlines()
            formatted_lines = []
            indent_level = 0
            indent_str = "\t"

            # Keywords that increase indent
            indent_increase = {
                "если", "для", "пока", "попытка", "выбор",
                "процедура", "функция",
                "if", "for", "while", "try", "select",
                "procedure", "function",
            }

            # Keywords that decrease indent
            indent_decrease = {
                "конецесли", "конеццикла", "конецпопытки", "конецвыбора",
                "конецпроцедуры", "конецфункции",
                "endif", "enddo", "endtry", "endselect",
                "endprocedure", "endfunction",
            }

            # Keywords that temporarily decrease (else, except, etc.)
            temp_decrease = {
                "иначе", "иначеесли", "исключение", "когда", "другое",
                "else", "elseif", "except", "when", "otherwise",
            }

            for line in lines:
                stripped = line.strip()
                if not stripped:
                    formatted_lines.append("")
                    continue

                # Get first word
                first_word = stripped.split()[0].lower() if stripped.split() else ""
                # Remove directive prefix
                if first_word.startswith("&"):
                    first_word = stripped.split()[1].lower() if len(stripped.split()) > 1 else ""

                # Adjust indent
                current_indent = indent_level

                if first_word in indent_decrease:
                    indent_level = max(0, indent_level - 1)
                    current_indent = indent_level
                elif first_word in temp_decrease:
                    current_indent = max(0, indent_level - 1)

                # Apply indent
                formatted_lines.append(indent_str * current_indent + stripped)

                # Increase indent for next line
                if first_word in indent_increase:
                    indent_level += 1

            return "\n".join(formatted_lines)

        except Exception as e:
            self.logger.error(f"Error in internal formatting: {e}")
            return None

    async def analyze_complexity(self, file_path: Path) -> ModuleComplexityResult:
        """
        Analyze code complexity.

        Args:
            file_path: Path to .bsl file

        Returns:
            ModuleComplexityResult with complexity metrics
        """
        from mcp_1c.engines.code.parser import BslParser

        parser = BslParser()
        result = ModuleComplexityResult(file_path=file_path)

        try:
            module = await parser.parse_file(file_path)
            content = module.content
            lines = content.splitlines()

            # Module-level metrics
            result.module_metrics.lines_of_code = len(lines)
            result.module_metrics.blank_lines = sum(1 for line in lines if not line.strip())
            result.module_metrics.comment_lines = sum(
                1 for line in lines if line.strip().startswith("//")
            )
            result.module_metrics.procedure_count = sum(
                1 for p in module.procedures if not p.is_function
            )
            result.module_metrics.function_count = sum(
                1 for p in module.procedures if p.is_function
            )

            # Analyze each procedure
            high_complexity_threshold = 10

            for proc in module.procedures:
                proc_complexity = await self._analyze_procedure_complexity(proc, lines)
                result.procedures.append(proc_complexity)

                # Track high complexity
                if proc_complexity.cyclomatic > high_complexity_threshold:
                    result.high_complexity_procedures.append(proc.name)

                # Update module max nesting
                if proc_complexity.nesting_depth > result.module_metrics.max_nesting_depth:
                    result.module_metrics.max_nesting_depth = proc_complexity.nesting_depth

            # Calculate module-level cyclomatic/cognitive
            result.module_metrics.cyclomatic = sum(p.cyclomatic for p in result.procedures)
            result.module_metrics.cognitive = sum(p.cognitive for p in result.procedures)

            return result

        except Exception as e:
            self.logger.error(f"Error analyzing complexity: {e}")
            return result

    async def _analyze_procedure_complexity(
        self,
        procedure,
        all_lines: list[str],
    ) -> ProcedureComplexity:
        """Analyze complexity of a single procedure."""
        # Extract procedure body lines
        start_idx = procedure.start_line - 1
        end_idx = procedure.end_line
        proc_lines = all_lines[start_idx:end_idx]

        # Calculate cyclomatic complexity
        # CC = 1 + number of decision points
        cyclomatic = 1
        decision_keywords = [
            "если", "иначеесли", "для", "пока", "когда",
            "if", "elseif", "for", "while", "when",
            "и", "или", "and", "or",  # Boolean operators
        ]

        for line in proc_lines:
            lower_line = line.lower()
            for keyword in decision_keywords:
                cyclomatic += lower_line.count(f" {keyword} ") + lower_line.count(f"\t{keyword} ")

        # Calculate cognitive complexity
        # Simplified: increments for nesting and structural elements
        cognitive = 0
        nesting = 0
        max_nesting = 0

        nesting_increase = {
            "если", "для", "пока", "попытка", "выбор",
            "if", "for", "while", "try", "select",
        }
        nesting_decrease = {
            "конецесли", "конеццикла", "конецпопытки", "конецвыбора",
            "endif", "enddo", "endtry", "endselect",
        }

        for line in proc_lines:
            words = line.lower().split()
            for word in words:
                if word in nesting_increase:
                    cognitive += 1 + nesting  # Base + nesting penalty
                    nesting += 1
                    max_nesting = max(max_nesting, nesting)
                elif word in nesting_decrease:
                    nesting = max(0, nesting - 1)

        return ProcedureComplexity(
            name=procedure.name,
            is_function=procedure.is_function,
            cyclomatic=cyclomatic,
            cognitive=cognitive,
            lines=len(proc_lines),
            parameters=len(procedure.parameters),
            nesting_depth=max_nesting,
            start_line=procedure.start_line,
        )
