"""
Unit tests for Platform Knowledge Base engine.
"""

import pytest

from mcp_1c.engines.platform import PlatformEngine


@pytest.fixture
async def engine():
    """Create and initialize platform engine."""
    eng = PlatformEngine()
    await eng.initialize()
    return eng


class TestPlatformEngine:
    """Tests for PlatformEngine."""

    @pytest.mark.asyncio
    async def test_initialize(self, engine):
        """Test engine initialization."""
        assert engine._loaded is True
        assert engine._knowledge_base is not None

    @pytest.mark.asyncio
    async def test_get_method_russian(self, engine):
        """Test getting method by Russian name."""
        method = engine.get_method("СтрДлина")
        assert method is not None
        assert method.name == "СтрДлина"
        assert method.name_en == "StrLen"
        assert "Строка" in method.return_types

    @pytest.mark.asyncio
    async def test_get_method_english(self, engine):
        """Test getting method by English name."""
        method = engine.get_method("StrLen")
        assert method is not None
        assert method.name == "СтрДлина"

    @pytest.mark.asyncio
    async def test_get_method_not_found(self, engine):
        """Test getting non-existent method."""
        method = engine.get_method("НесуществующийМетод")
        assert method is None

    @pytest.mark.asyncio
    async def test_search_methods(self, engine):
        """Test searching methods."""
        results = engine.search_methods("Стр")
        assert len(results) > 0
        assert all("Стр" in m.name or "Str" in m.name_en for m in results)

    @pytest.mark.asyncio
    async def test_get_type_russian(self, engine):
        """Test getting type by Russian name."""
        t = engine.get_type("Массив")
        assert t is not None
        assert t.name == "Массив"
        assert t.name_en == "Array"
        assert t.category == "collection"

    @pytest.mark.asyncio
    async def test_get_type_english(self, engine):
        """Test getting type by English name."""
        t = engine.get_type("Array")
        assert t is not None
        assert t.name == "Массив"

    @pytest.mark.asyncio
    async def test_get_type_methods(self, engine):
        """Test getting type methods."""
        t = engine.get_type("ТаблицаЗначений")
        assert t is not None
        assert len(t.methods) > 0

        # Check for common methods
        method_names = [m.name for m in t.methods]
        assert "Добавить" in method_names
        assert "Удалить" in method_names
        assert "Найти" in method_names

    @pytest.mark.asyncio
    async def test_get_type_properties(self, engine):
        """Test getting type properties."""
        t = engine.get_type("ТаблицаЗначений")
        assert t is not None
        assert len(t.properties) > 0

        prop_names = [p.name for p in t.properties]
        assert "Колонки" in prop_names

    @pytest.mark.asyncio
    async def test_get_type_method(self, engine):
        """Test getting specific method of a type."""
        method = engine.get_type_method("Массив", "Добавить")
        assert method is not None
        assert method.name == "Добавить"

    @pytest.mark.asyncio
    async def test_search_types(self, engine):
        """Test searching types."""
        results = engine.search_types("Таблица")
        assert len(results) > 0
        assert any("Таблица" in t.name for t in results)

    @pytest.mark.asyncio
    async def test_get_event_russian(self, engine):
        """Test getting event by Russian name."""
        event = engine.get_event("ПередЗаписью")
        assert event is not None
        assert event.name == "ПередЗаписью"
        assert event.name_en == "BeforeWrite"
        assert event.can_cancel is True

    @pytest.mark.asyncio
    async def test_get_event_english(self, engine):
        """Test getting event by English name."""
        event = engine.get_event("BeforeWrite")
        assert event is not None
        assert event.name == "ПередЗаписью"

    @pytest.mark.asyncio
    async def test_get_events_for_object(self, engine):
        """Test getting events for specific object type."""
        events = engine.get_events_for_object("Документ")
        assert len(events) > 0

        event_names = [e.name for e in events]
        assert "ПередЗаписью" in event_names
        assert "ОбработкаПроведения" in event_names

    @pytest.mark.asyncio
    async def test_search_events(self, engine):
        """Test searching events."""
        results = engine.search_events("Запись")
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_get_all_methods(self, engine):
        """Test getting all methods."""
        methods = engine.get_all_methods()
        assert len(methods) > 50  # Should have many methods

    @pytest.mark.asyncio
    async def test_get_all_types(self, engine):
        """Test getting all types."""
        types = engine.get_all_types()
        assert len(types) > 5  # Should have multiple types

    @pytest.mark.asyncio
    async def test_get_all_events(self, engine):
        """Test getting all events."""
        events = engine.get_all_events()
        assert len(events) > 10  # Should have many events

    @pytest.mark.asyncio
    async def test_get_global_context_sections(self, engine):
        """Test getting global context sections."""
        sections = engine.get_global_context_sections()
        assert len(sections) > 0

        section_names = [s.name for s in sections]
        assert "Строковые функции" in section_names
        assert "Математические функции" in section_names

    @pytest.mark.asyncio
    async def test_search_all(self, engine):
        """Test searching all categories."""
        results = engine.search_all("Дата")
        assert "methods" in results
        assert "types" in results
        assert "events" in results
        assert len(results["methods"]) > 0

    @pytest.mark.asyncio
    async def test_method_signature(self, engine):
        """Test method signature generation."""
        method = engine.get_method("СтрНайти")
        assert method is not None

        sig_ru = method.get_signature("ru")
        assert "СтрНайти" in sig_ru
        assert "Строка" in sig_ru

        sig_en = method.get_signature("en")
        assert "StrFind" in sig_en

    @pytest.mark.asyncio
    async def test_event_handler_signature(self, engine):
        """Test event handler signature generation."""
        event = engine.get_event("ПередЗаписью")
        assert event is not None

        sig = event.get_handler_signature("ru")
        assert "Процедура" in sig
        assert "ПередЗаписью" in sig
        assert "Отказ" in sig


class TestPlatformEngineNotInitialized:
    """Tests for uninitialized engine."""

    def test_not_initialized_raises(self):
        """Test that methods raise error if not initialized."""
        engine = PlatformEngine()

        with pytest.raises(RuntimeError):
            engine.get_method("СтрДлина")

        with pytest.raises(RuntimeError):
            engine.get_type("Массив")

        with pytest.raises(RuntimeError):
            engine.get_event("ПередЗаписью")
