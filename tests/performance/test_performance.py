"""
Performance tests to ensure acceptable response times.

Tests indexing speed, search throughput, cache bounds, and regex caching.
"""

import re
import tempfile
import time
from pathlib import Path

import pytest

from mcp_1c.engines.code.engine import _REGEX_CACHE, _get_pattern
from mcp_1c.engines.metadata.engine import MetadataEngine
from mcp_1c.engines.metadata.parser import XmlParser
from mcp_1c.engines.mxl.engine import _LRUDict
from mcp_1c.engines.platform.engine import PlatformEngine


class TestIndexingPerformance:
    """Test indexing performance with larger datasets."""

    @pytest.mark.asyncio
    async def test_index_many_objects(self, tmp_path: Path) -> None:
        """Indexing 100+ objects should complete in reasonable time."""
        config_root = tmp_path / "Configuration"
        config_root.mkdir()

        # Build Configuration.xml with 100 catalogs
        catalog_items = "\n".join(
            f"            <item>Catalog{i:03d}</item>" for i in range(100)
        )
        config_xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
    <Configuration>
        <Name>PerfTestConfig</Name>
        <Catalogs>
{catalog_items}
        </Catalogs>
    </Configuration>
</MetaDataObject>"""

        config_xml = config_root / "Configuration.xml"
        config_xml.write_text(config_xml_content, encoding="utf-8")

        # Create corresponding catalog directories and XML files
        catalogs_dir = config_root / "Catalogs"
        catalogs_dir.mkdir()

        for i in range(100):
            name = f"Catalog{i:03d}"
            cat_dir = catalogs_dir / name
            cat_dir.mkdir()
            cat_xml = cat_dir / f"{name}.xml"
            cat_xml.write_text(
                f"""<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
    <Catalog uuid="00000000-0000-0000-0000-{i:012d}">
        <Name>{name}</Name>
        <Synonym><item lang="ru">Каталог {i}</item></Synonym>
        <Attributes>
            <Attribute>
                <Name>Attr1</Name>
                <Type>String</Type>
            </Attribute>
        </Attributes>
    </Catalog>
</MetaDataObject>""",
                encoding="utf-8",
            )

        MetadataEngine._instance = None
        engine = MetadataEngine.get_instance()

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        engine.cache.db_path = db_path

        try:
            start = time.monotonic()
            await engine.initialize(config_root, watch=False)
            elapsed = time.monotonic() - start

            assert elapsed < 10.0, f"Indexing 100 objects took too long: {elapsed:.2f}s"

            # Verify all objects were indexed
            catalogs = await engine.list_objects("Catalog")
            assert len(catalogs) == 100
        finally:
            await engine.cache.close()
            if db_path.exists():
                db_path.unlink()
            MetadataEngine._instance = None


class TestSearchPerformance:
    """Test search performance."""

    @pytest.mark.asyncio
    async def test_platform_search_performance(self) -> None:
        """Platform search across all data should be fast."""
        engine = PlatformEngine()
        await engine.initialize()

        start = time.monotonic()
        for _ in range(100):
            engine.search_methods("Найти")
        elapsed = time.monotonic() - start

        assert elapsed < 2.0, f"100 searches took too long: {elapsed:.2f}s"

    @pytest.mark.asyncio
    async def test_platform_type_search_performance(self) -> None:
        """Type search should be fast."""
        engine = PlatformEngine()
        await engine.initialize()

        start = time.monotonic()
        for _ in range(100):
            engine.search_types("Таблица")
        elapsed = time.monotonic() - start

        assert elapsed < 2.0, f"100 type searches took too long: {elapsed:.2f}s"

    def test_xml_parser_performance(self, mock_config_path: Path) -> None:
        """Parsing Configuration.xml 50 times should be fast."""
        parser = XmlParser()

        start = time.monotonic()
        for _ in range(50):
            parser.parse_configuration(mock_config_path)
        elapsed = time.monotonic() - start

        assert elapsed < 5.0, f"50 parses took too long: {elapsed:.2f}s"


class TestCachePerformance:
    """Test LRU cache performance."""

    def test_mxl_lru_cache_bounded(self) -> None:
        """MXL cache should not grow beyond max_size."""
        cache: _LRUDict = _LRUDict(max_size=10)

        for i in range(100):
            cache[f"key_{i}"] = f"value_{i}"  # type: ignore[assignment]

        assert len(cache) == 10
        # Most recent keys should be present
        assert "key_99" in cache
        assert "key_98" in cache
        # Oldest keys should be evicted
        assert "key_0" not in cache
        assert "key_89" not in cache

    def test_mxl_lru_cache_access_refreshes(self) -> None:
        """Accessing a key should move it to most-recent position."""
        cache: _LRUDict = _LRUDict(max_size=5)

        for i in range(5):
            cache[f"key_{i}"] = f"value_{i}"  # type: ignore[assignment]

        # Access key_0 to make it "recent"
        _ = cache["key_0"]

        # Add 4 more items to evict everything except key_0
        for i in range(5, 9):
            cache[f"key_{i}"] = f"value_{i}"  # type: ignore[assignment]

        assert len(cache) == 5
        # key_0 was accessed recently, so it should survive
        assert "key_0" in cache
        # key_1 was the oldest untouched, should be evicted
        assert "key_1" not in cache

    def test_mxl_lru_cache_overwrite(self) -> None:
        """Overwriting a key should not increase size."""
        cache: _LRUDict = _LRUDict(max_size=5)

        cache["a"] = "v1"  # type: ignore[assignment]
        cache["b"] = "v2"  # type: ignore[assignment]
        cache["a"] = "v3"  # type: ignore[assignment]

        assert len(cache) == 2
        assert cache["a"] == "v3"


class TestRegexCachePerformance:
    """Test regex caching effectiveness."""

    def test_regex_cache_reuses_patterns(self) -> None:
        """Cached regex should return same compiled object."""
        # Clear cache to avoid interference from other tests
        _REGEX_CACHE.clear()

        pattern = r"Процедура\s+ТестоваяПроцедура\s*\("

        p1 = _get_pattern(pattern, re.IGNORECASE)
        p2 = _get_pattern(pattern, re.IGNORECASE)

        assert p1 is p2

    def test_regex_cache_different_flags_separate(self) -> None:
        """Different flags should produce separate cache entries."""
        _REGEX_CACHE.clear()

        pattern = r"Функция\s+Тест"

        p1 = _get_pattern(pattern, 0)
        p2 = _get_pattern(pattern, re.IGNORECASE)

        assert p1 is not p2

    def test_regex_cache_returns_same_object(self) -> None:
        """Cached patterns should return the same compiled object (no recompilation)."""
        _REGEX_CACHE.clear()

        pattern = r"(?:Процедура|Функция|Procedure|Function)\s+\w+\s*\([^)]*\)"
        flags = re.IGNORECASE | re.MULTILINE

        # First call compiles
        p1 = _get_pattern(pattern, flags)

        # Subsequent calls should return the exact same object
        for _ in range(100):
            p = _get_pattern(pattern, flags)
            assert p is p1, "Cache should return the same compiled pattern object"

        # Verify it actually works as a pattern
        text = "Процедура Тест(Параметр)"
        assert p1.search(text) is not None
