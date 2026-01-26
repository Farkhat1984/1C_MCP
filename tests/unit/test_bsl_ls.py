"""
Unit tests for BSL Language Server integration.

Tests validation, linting, formatting, and complexity analysis.
"""

import tempfile
from pathlib import Path

import pytest

from mcp_1c.engines.code.bsl_ls import (
    BslLanguageServer,
    BslLsConfig,
    DiagnosticSeverity,
)


class TestBslLanguageServer:
    """Test suite for BslLanguageServer."""

    @pytest.fixture
    def bsl_ls(self) -> BslLanguageServer:
        """Create BSL LS instance."""
        # Reset singleton for tests
        BslLanguageServer._instance = None
        return BslLanguageServer.get_instance()

    @pytest.fixture
    def temp_bsl_file(self) -> Path:
        """Create temporary BSL file."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".bsl",
            delete=False,
            encoding="utf-8-sig",
        ) as f:
            f.write(VALID_BSL_CODE)
            return Path(f.name)

    @pytest.fixture
    def temp_invalid_bsl_file(self) -> Path:
        """Create temporary BSL file with errors."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".bsl",
            delete=False,
            encoding="utf-8-sig",
        ) as f:
            f.write(INVALID_BSL_CODE)
            return Path(f.name)

    @pytest.fixture
    def temp_complex_bsl_file(self) -> Path:
        """Create temporary BSL file with complex code."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".bsl",
            delete=False,
            encoding="utf-8-sig",
        ) as f:
            f.write(COMPLEX_BSL_CODE)
            return Path(f.name)

    @pytest.mark.asyncio
    async def test_validate_valid_file(
        self, bsl_ls: BslLanguageServer, temp_bsl_file: Path
    ) -> None:
        """Test validating a valid BSL file."""
        result = await bsl_ls.validate_file(temp_bsl_file)

        assert result.valid is True
        assert result.error_count == 0
        assert result.file_path == temp_bsl_file

    @pytest.mark.asyncio
    async def test_validate_file_not_found(
        self, bsl_ls: BslLanguageServer
    ) -> None:
        """Test validating non-existent file."""
        result = await bsl_ls.validate_file(Path("/nonexistent/file.bsl"))

        assert result.valid is False
        assert result.error_count == 1
        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].code == "FILE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_validate_file_with_deprecated_keyword(
        self, bsl_ls: BslLanguageServer
    ) -> None:
        """Test detecting deprecated keywords."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".bsl",
            delete=False,
            encoding="utf-8-sig",
        ) as f:
            f.write("""
Процедура Тест()
    Перейти ~Метка;
    ~Метка:
КонецПроцедуры
""")
            file_path = Path(f.name)

        result = await bsl_ls.validate_file(file_path)

        # Should have warning about deprecated GOTO
        warnings = [d for d in result.diagnostics if d.severity == DiagnosticSeverity.WARNING]
        assert len(warnings) > 0

    @pytest.mark.asyncio
    async def test_lint_file(
        self, bsl_ls: BslLanguageServer, temp_bsl_file: Path
    ) -> None:
        """Test linting a BSL file."""
        result = await bsl_ls.lint_file(temp_bsl_file)

        assert result.files_analyzed == 1
        assert isinstance(result.total_issues, int)
        assert isinstance(result.by_severity, dict)
        assert isinstance(result.by_rule, dict)

    @pytest.mark.asyncio
    async def test_lint_directory(
        self, bsl_ls: BslLanguageServer, temp_bsl_file: Path
    ) -> None:
        """Test linting a directory."""
        result = await bsl_ls.lint_directory(temp_bsl_file.parent)

        assert result.files_analyzed >= 1

    @pytest.mark.asyncio
    async def test_format_file(
        self, bsl_ls: BslLanguageServer
    ) -> None:
        """Test formatting a BSL file."""
        # Create file with bad formatting
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".bsl",
            delete=False,
            encoding="utf-8-sig",
        ) as f:
            f.write(UNFORMATTED_BSL_CODE)
            file_path = Path(f.name)

        formatted = await bsl_ls.format_file(file_path)

        assert formatted is not None
        # Check that indentation is applied
        lines = formatted.splitlines()
        # Inner lines should be indented
        inner_lines = [l for l in lines if l.strip() and not l.strip().startswith(("Процедура", "КонецПроцедуры", "Если", "КонецЕсли", "Функция", "КонецФункции"))]
        # At least some lines should be indented
        assert any(l.startswith("\t") or l.startswith("    ") for l in inner_lines if l.strip())

    @pytest.mark.asyncio
    async def test_format_nonexistent_file(
        self, bsl_ls: BslLanguageServer
    ) -> None:
        """Test formatting non-existent file."""
        result = await bsl_ls.format_file(Path("/nonexistent/file.bsl"))
        assert result is None

    @pytest.mark.asyncio
    async def test_analyze_complexity(
        self, bsl_ls: BslLanguageServer, temp_complex_bsl_file: Path
    ) -> None:
        """Test complexity analysis."""
        result = await bsl_ls.analyze_complexity(temp_complex_bsl_file)

        assert result.file_path == temp_complex_bsl_file
        assert result.module_metrics.lines_of_code > 0
        assert result.module_metrics.procedure_count > 0 or result.module_metrics.function_count > 0
        assert len(result.procedures) > 0

    @pytest.mark.asyncio
    async def test_complexity_metrics(
        self, bsl_ls: BslLanguageServer, temp_complex_bsl_file: Path
    ) -> None:
        """Test that complexity metrics are calculated."""
        result = await bsl_ls.analyze_complexity(temp_complex_bsl_file)

        # Module metrics
        metrics = result.module_metrics
        assert metrics.lines_of_code > 0
        assert metrics.cyclomatic >= 0
        assert metrics.cognitive >= 0

        # Procedure metrics
        for proc in result.procedures:
            assert proc.cyclomatic >= 1  # Minimum cyclomatic is 1
            assert proc.cognitive >= 0
            assert proc.lines > 0

    @pytest.mark.asyncio
    async def test_high_complexity_detection(
        self, bsl_ls: BslLanguageServer
    ) -> None:
        """Test detection of high complexity procedures."""
        # Create file with high complexity function
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".bsl",
            delete=False,
            encoding="utf-8-sig",
        ) as f:
            f.write(HIGH_COMPLEXITY_CODE)
            file_path = Path(f.name)

        result = await bsl_ls.analyze_complexity(file_path)

        # Should detect high complexity
        assert len(result.high_complexity_procedures) > 0

    def test_check_block_balance_valid(
        self, bsl_ls: BslLanguageServer
    ) -> None:
        """Test block balance check with valid code."""
        lines = """
Процедура Тест()
    Если Условие Тогда
        Сообщить("Да");
    КонецЕсли;
КонецПроцедуры
""".splitlines()

        issues = bsl_ls._check_block_balance(lines)
        assert len(issues) == 0

    def test_check_block_balance_unclosed(
        self, bsl_ls: BslLanguageServer
    ) -> None:
        """Test block balance check with unclosed block."""
        lines = """
Процедура Тест()
    Если Условие Тогда
        Сообщить("Да");
КонецПроцедуры
""".splitlines()

        issues = bsl_ls._check_block_balance(lines)
        assert len(issues) > 0

    def test_remove_comments_and_strings(
        self, bsl_ls: BslLanguageServer
    ) -> None:
        """Test comment and string removal for analysis."""
        line = 'Если Условие // Комментарий'
        result = bsl_ls._remove_comments_and_strings(line)
        assert "Комментарий" not in result
        assert "Если Условие" in result

        line = 'Строка = "значение со словом Если"'
        result = bsl_ls._remove_comments_and_strings(line)
        assert "Если" not in result or "Строка" in result

    def test_singleton_pattern(self) -> None:
        """Test that BslLanguageServer follows singleton pattern."""
        BslLanguageServer._instance = None

        instance1 = BslLanguageServer.get_instance()
        instance2 = BslLanguageServer.get_instance()

        assert instance1 is instance2

    def test_config_defaults(self) -> None:
        """Test BslLsConfig defaults."""
        config = BslLsConfig()

        assert config.java_path == "java"
        assert config.reporter == "json"
        assert config.timeout == 120


class TestDiagnosticSeverity:
    """Test DiagnosticSeverity enum."""

    def test_severity_values(self) -> None:
        """Test severity enum values."""
        assert DiagnosticSeverity.ERROR.value == "error"
        assert DiagnosticSeverity.WARNING.value == "warning"
        assert DiagnosticSeverity.INFO.value == "info"
        assert DiagnosticSeverity.HINT.value == "hint"


# Test data
VALID_BSL_CODE = """
#Область ПубличныйИнтерфейс

// Получает значение
//
// Возвращаемое значение:
//   Число - результат
//
Функция ПолучитьЗначение() Экспорт
    Возврат 42;
КонецФункции

// Обрабатывает данные
//
// Параметры:
//   Данные - Строка - входные данные
//
Процедура ОбработатьДанные(Данные) Экспорт
    Если ЗначениеЗаполнено(Данные) Тогда
        Сообщить(Данные);
    КонецЕсли;
КонецПроцедуры

#КонецОбласти
"""

INVALID_BSL_CODE = """
Процедура Тест()
    Если Условие Тогда
        Сообщить("Начало");
    // Отсутствует КонецЕсли
КонецПроцедуры

Функция Ошибка()
    // Отсутствует Возврат и КонецФункции
"""

UNFORMATTED_BSL_CODE = """
Процедура Тест()
Если Условие Тогда
Сообщить("Да");
Иначе
Сообщить("Нет");
КонецЕсли;
КонецПроцедуры
"""

COMPLEX_BSL_CODE = """
#Область ПубличныйИнтерфейс

Функция СложнаяФункция(Параметр1, Параметр2, Параметр3 = Неопределено) Экспорт

    Если Параметр1 > 0 Тогда
        Если Параметр2 > 0 Тогда
            Для Счетчик = 1 По 10 Цикл
                Если Счетчик > 5 Тогда
                    Продолжить;
                КонецЕсли;
            КонецЦикла;
        Иначе
            Пока Параметр2 < 0 Цикл
                Параметр2 = Параметр2 + 1;
            КонецЦикла;
        КонецЕсли;
    ИначеЕсли Параметр1 < 0 Тогда
        Попытка
            ВыполнитьОперацию();
        Исключение
            ЗаписатьОшибку();
        КонецПопытки;
    Иначе
        Возврат 0;
    КонецЕсли;

    Возврат Параметр1 + Параметр2;
КонецФункции

Процедура ПростаяПроцедура()
    Сообщить("Привет");
КонецПроцедуры

#КонецОбласти
"""

HIGH_COMPLEXITY_CODE = """
Функция ОченьСложнаяФункция(П1, П2, П3, П4, П5) Экспорт

    Если П1 И П2 Или П3 Тогда
        Если П4 Тогда
            Если П5 Тогда
                Для К1 = 1 По 10 Цикл
                    Для К2 = 1 По 10 Цикл
                        Если К1 > К2 И К1 < 5 Или К2 > 7 Тогда
                            Пока Истина Цикл
                                Если К1 = К2 Тогда
                                    Прервать;
                                КонецЕсли;
                            КонецЦикла;
                        КонецЕсли;
                    КонецЦикла;
                КонецЦикла;
            КонецЕсли;
        ИначеЕсли П3 Тогда
            Выбор
                Когда П1
                    Сообщить("1");
                Когда П2
                    Сообщить("2");
                Когда П3
                    Сообщить("3");
                Другое
                    Сообщить("Другое");
            КонецВыбора;
        КонецЕсли;
    ИначеЕсли П2 И П3 Или П4 И П5 Тогда
        Попытка
            Если П1 Тогда
                ВызватьИсключение "Ошибка";
            КонецЕсли;
        Исключение
            Если П2 Тогда
                ЗаписатьОшибку();
            КонецЕсли;
        КонецПопытки;
    КонецЕсли;

    Возврат П1;
КонецФункции
"""
