"""
Integration tests for Code Engine.

Tests full workflow: reading, parsing, searching code.
"""

import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from mcp_1c.engines.code.engine import CodeEngine
from mcp_1c.engines.metadata.engine import MetadataEngine
from mcp_1c.domain.metadata import MetadataType, ModuleType


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
        assert len(module.procedures) > 0

    @pytest.mark.asyncio
    async def test_get_common_module(
        self,
        meta_engine: MetadataEngine,
        code_engine: CodeEngine,
    ) -> None:
        """Test getting common module code."""
        module = await code_engine.get_common_module_code("ОбщегоНазначения")

        assert module is not None
        assert len(module.procedures) > 0

        # Check exported functions exist
        exported = module.get_exported_procedures()
        assert len(exported) >= 1

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
        # Should find in ОбщегоНазначения module
        paths = [str(d.location.file_path) for d in definitions]
        assert any("ОбщегоНазначения" in p for p in paths)

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

        assert len(procedures) >= 1
        # Check structure
        proc = procedures[0]
        assert "name" in proc
        assert "is_function" in proc
        assert "signature" in proc

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
        assert len(module.regions) >= 1
        region_names = [r.name for r in module.regions]
        assert "ОбработчикиСобытий" in region_names

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
