"""
Integration tests for Code Engine.

Tests full workflow: reading, parsing, searching code.
"""

import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from mcp_1c.domain.metadata import MetadataType, ModuleType
from mcp_1c.engines.code.engine import CodeEngine
from mcp_1c.engines.metadata.engine import MetadataEngine


class TestCodeEngineIntegration:
    """Integration tests for CodeEngine."""

    @pytest_asyncio.fixture
    async def meta_engine(self, mock_config_path: Path) -> MetadataEngine:
        """Create and initialize metadata engine."""
        MetadataEngine._instance = None

        engine = MetadataEngine.get_instance()

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        engine.cache.db_path = db_path
        await engine.initialize(mock_config_path, watch=False)

        yield engine

        await engine.cache.close()
        if db_path.exists():
            db_path.unlink()
        MetadataEngine._instance = None

    @pytest.fixture
    def code_engine(self) -> CodeEngine:
        """Create code engine instance."""
        CodeEngine._instance = None
        engine = CodeEngine.get_instance()
        yield engine
        CodeEngine._instance = None

    @pytest.mark.asyncio
    async def test_get_module(
        self,
        meta_engine: MetadataEngine,
        code_engine: CodeEngine,
    ) -> None:
        """Test getting module code."""
        module = await code_engine.get_module(
            MetadataType.CATALOG,
            "Товары",
            ModuleType.OBJECT_MODULE,
        )

        assert module is not None
        assert len(module.content) > 0
        assert len(module.procedures) >= 3

        proc_names = [p.name for p in module.procedures]
        assert "ПередЗаписью" in proc_names
        assert "ОбработкаВыбора" in proc_names
        assert "ПолучитьЦену" in proc_names

        assert module.owner_type == MetadataType.CATALOG.value
        assert module.owner_name == "Товары"

    @pytest.mark.asyncio
    async def test_get_common_module(
        self,
        meta_engine: MetadataEngine,
        code_engine: CodeEngine,
    ) -> None:
        """Test getting common module code."""
        module = await code_engine.get_common_module_code("ОбщегоНазначения")

        assert module is not None
        assert len(module.procedures) >= 3

        # Check exported functions exist
        exported = module.get_exported_procedures()
        assert len(exported) >= 2
        exported_names = [p.name for p in exported]
        assert "ТекущийПользователь" in exported_names
        assert "ПравоДоступа" in exported_names

        # Non-exported procedure should exist but not in exported list
        all_names = [p.name for p in module.procedures]
        assert "ЗаписатьВЖурнал" in all_names
        assert "ЗаписатьВЖурнал" not in exported_names

    @pytest.mark.asyncio
    async def test_get_procedure(
        self,
        meta_engine: MetadataEngine,
        code_engine: CodeEngine,
    ) -> None:
        """Test getting specific procedure."""
        procedure = await code_engine.get_procedure(
            MetadataType.CATALOG,
            "Товары",
            "ПередЗаписью",
            ModuleType.OBJECT_MODULE,
        )

        assert procedure is not None
        assert procedure.name == "ПередЗаписью"
        assert procedure.is_function is False

    @pytest.mark.asyncio
    async def test_get_function_with_export(
        self,
        meta_engine: MetadataEngine,
        code_engine: CodeEngine,
    ) -> None:
        """Test getting exported function."""
        procedure = await code_engine.get_procedure(
            MetadataType.CATALOG,
            "Товары",
            "ПолучитьЦену",
            ModuleType.OBJECT_MODULE,
        )

        assert procedure is not None
        assert procedure.name == "ПолучитьЦену"
        assert procedure.is_function is True
        assert procedure.is_export is True

    @pytest.mark.asyncio
    async def test_find_definition(
        self,
        meta_engine: MetadataEngine,
        code_engine: CodeEngine,
    ) -> None:
        """Test finding procedure definition."""
        definitions = await code_engine.find_definition("ТекущийПользователь")

        assert len(definitions) >= 1
        defn = definitions[0]
        assert defn.reference_type == "definition"
        assert "ОбщегоНазначения" in str(defn.location.file_path)
        assert defn.location.line > 0
        assert defn.context != ""

    @pytest.mark.asyncio
    async def test_find_usages(
        self,
        meta_engine: MetadataEngine,
        code_engine: CodeEngine,
    ) -> None:
        """Test finding identifier usages."""
        usages = await code_engine.find_usages("Ссылка")

        # Should find usages in catalog module
        assert len(usages) >= 1

    @pytest.mark.asyncio
    async def test_list_procedures(
        self,
        meta_engine: MetadataEngine,
        code_engine: CodeEngine,
    ) -> None:
        """Test listing all procedures in a module."""
        procedures = await code_engine.list_procedures(
            MetadataType.CATALOG,
            "Товары",
            ModuleType.OBJECT_MODULE,
        )

        assert len(procedures) >= 3
        # Check structure of each procedure dict
        for proc in procedures:
            assert "name" in proc
            assert "is_function" in proc
            assert "is_export" in proc
            assert "signature" in proc
            assert "line" in proc
            assert "parameters" in proc

        proc_names = [p["name"] for p in procedures]
        assert "ПередЗаписью" in proc_names
        assert "ПолучитьЦену" in proc_names

        # Verify ПолучитьЦену is a function and exported
        get_price = next(p for p in procedures if p["name"] == "ПолучитьЦену")
        assert get_price["is_function"] is True
        assert get_price["is_export"] is True
        assert get_price["directive"] is not None

    @pytest.mark.asyncio
    async def test_module_regions(
        self,
        meta_engine: MetadataEngine,
        code_engine: CodeEngine,
    ) -> None:
        """Test that module regions are parsed."""
        module = await code_engine.get_module(
            MetadataType.CATALOG,
            "Товары",
            ModuleType.OBJECT_MODULE,
        )

        assert module is not None
        assert len(module.regions) >= 2
        region_names = [r.name for r in module.regions]
        assert "ОбработчикиСобытий" in region_names
        assert "СлужебныеПроцедуры" in region_names

        # Verify region line ranges are valid
        for region in module.regions:
            assert region.start_line > 0
            assert region.end_line >= region.start_line

    @pytest.mark.asyncio
    async def test_procedure_in_region(
        self,
        meta_engine: MetadataEngine,
        code_engine: CodeEngine,
    ) -> None:
        """Test that procedure knows its containing region."""
        procedure = await code_engine.get_procedure(
            MetadataType.CATALOG,
            "Товары",
            "ПередЗаписью",
            ModuleType.OBJECT_MODULE,
        )

        assert procedure is not None
        assert procedure.region == "ОбработчикиСобытий"

    @pytest.mark.asyncio
    async def test_singleton_pattern(self) -> None:
        """Test that code engine uses singleton pattern."""
        CodeEngine._instance = None

        engine1 = CodeEngine.get_instance()
        engine2 = CodeEngine.get_instance()

        assert engine1 is engine2

        CodeEngine._instance = None

    @pytest.mark.asyncio
    async def test_get_nonexistent_module(
        self,
        meta_engine: MetadataEngine,
        code_engine: CodeEngine,
    ) -> None:
        """Test getting non-existent module returns None."""
        module = await code_engine.get_module(
            MetadataType.CATALOG,
            "НеСуществующий",
            ModuleType.OBJECT_MODULE,
        )

        assert module is None

    @pytest.mark.asyncio
    async def test_get_nonexistent_procedure(
        self,
        meta_engine: MetadataEngine,
        code_engine: CodeEngine,
    ) -> None:
        """Test getting non-existent procedure returns None."""
        procedure = await code_engine.get_procedure(
            MetadataType.CATALOG,
            "Товары",
            "НеСуществующаяПроцедура",
            ModuleType.OBJECT_MODULE,
        )

        assert procedure is None
