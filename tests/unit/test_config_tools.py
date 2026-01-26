"""
Unit tests for config tools.
"""

import pytest

from mcp_1c.engines.metadata import MetadataEngine
from mcp_1c.tools.config_tools import (
    ConfigOptionsTool,
    ConfigConstantsTool,
    ConfigScheduledJobsTool,
    ConfigEventSubscriptionsTool,
    ConfigExchangesTool,
    ConfigHttpServicesTool,
)


@pytest.fixture
async def initialized_engine(mock_config_path):
    """Create and initialize metadata engine with mock config."""
    engine = MetadataEngine.get_instance()
    # Reset singleton state for test isolation
    engine._initialized = False
    engine._config_path = None

    await engine.initialize(mock_config_path, full_reindex=True, watch=False)
    yield engine
    await engine.shutdown()
    MetadataEngine._instance = None


class TestConfigOptionsTool:
    """Tests for config.options tool."""

    @pytest.mark.asyncio
    async def test_list_options(self, initialized_engine):
        """Test listing all functional options."""
        tool = ConfigOptionsTool()
        result = await tool.execute({})

        assert "count" in result
        assert "options" in result
        assert result["type"] == "FunctionalOption"

    @pytest.mark.asyncio
    async def test_get_specific_option(self, initialized_engine):
        """Test getting specific functional option."""
        tool = ConfigOptionsTool()
        result = await tool.execute({"name": "ИспользоватьВалюты"})

        assert "error" not in result
        assert result["name"] == "ИспользоватьВалюты"
        assert result["full_name"] == "FunctionalOption.ИспользоватьВалюты"

    @pytest.mark.asyncio
    async def test_get_option_not_found(self, initialized_engine):
        """Test getting non-existent option."""
        tool = ConfigOptionsTool()
        result = await tool.execute({"name": "НесуществующаяОпция"})

        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_option_with_usage(self, initialized_engine):
        """Test getting option with usage info."""
        tool = ConfigOptionsTool()
        result = await tool.execute({
            "name": "ИспользоватьВалюты",
            "include_usage": True,
        })

        assert "error" not in result
        assert "related_parameters" in result


class TestConfigConstantsTool:
    """Tests for config.constants tool."""

    @pytest.mark.asyncio
    async def test_list_constants(self, initialized_engine):
        """Test listing all constants."""
        tool = ConfigConstantsTool()
        result = await tool.execute({})

        assert "count" in result
        assert "constants" in result
        assert result["type"] == "Constant"

    @pytest.mark.asyncio
    async def test_get_specific_constant(self, initialized_engine):
        """Test getting specific constant."""
        tool = ConfigConstantsTool()
        result = await tool.execute({"name": "ОсновнаяВалюта"})

        assert "error" not in result
        assert result["name"] == "ОсновнаяВалюта"
        assert result["full_name"] == "Constant.ОсновнаяВалюта"

    @pytest.mark.asyncio
    async def test_get_constant_not_found(self, initialized_engine):
        """Test getting non-existent constant."""
        tool = ConfigConstantsTool()
        result = await tool.execute({"name": "НесуществующаяКонстанта"})

        assert "error" in result


class TestConfigScheduledJobsTool:
    """Tests for config.scheduled_jobs tool."""

    @pytest.mark.asyncio
    async def test_list_scheduled_jobs(self, initialized_engine):
        """Test listing all scheduled jobs."""
        tool = ConfigScheduledJobsTool()
        result = await tool.execute({})

        assert "count" in result
        assert "scheduled_jobs" in result
        assert result["type"] == "ScheduledJob"

    @pytest.mark.asyncio
    async def test_get_specific_job(self, initialized_engine):
        """Test getting specific scheduled job."""
        tool = ConfigScheduledJobsTool()
        result = await tool.execute({"name": "ОбновлениеКурсовВалют"})

        assert "error" not in result
        assert result["name"] == "ОбновлениеКурсовВалют"
        assert result["full_name"] == "ScheduledJob.ОбновлениеКурсовВалют"

    @pytest.mark.asyncio
    async def test_get_job_not_found(self, initialized_engine):
        """Test getting non-existent job."""
        tool = ConfigScheduledJobsTool()
        result = await tool.execute({"name": "НесуществующееЗадание"})

        assert "error" in result


class TestConfigEventSubscriptionsTool:
    """Tests for config.event_subscriptions tool."""

    @pytest.mark.asyncio
    async def test_list_subscriptions(self, initialized_engine):
        """Test listing all event subscriptions."""
        tool = ConfigEventSubscriptionsTool()
        result = await tool.execute({})

        assert "count" in result
        assert "event_subscriptions" in result
        assert result["type"] == "EventSubscription"

    @pytest.mark.asyncio
    async def test_get_specific_subscription(self, initialized_engine):
        """Test getting specific event subscription."""
        tool = ConfigEventSubscriptionsTool()
        result = await tool.execute({"name": "ПриЗаписиТоваров"})

        assert "error" not in result
        assert result["name"] == "ПриЗаписиТоваров"
        assert result["full_name"] == "EventSubscription.ПриЗаписиТоваров"

    @pytest.mark.asyncio
    async def test_get_subscription_not_found(self, initialized_engine):
        """Test getting non-existent subscription."""
        tool = ConfigEventSubscriptionsTool()
        result = await tool.execute({"name": "НесуществующаяПодписка"})

        assert "error" in result

    @pytest.mark.asyncio
    async def test_filter_subscriptions(self, initialized_engine):
        """Test filtering subscriptions by event name."""
        tool = ConfigEventSubscriptionsTool()
        result = await tool.execute({"filter_event": "Запис"})

        assert "count" in result
        assert result["filter"] == "Запис"


class TestConfigExchangesTool:
    """Tests for config.exchanges tool."""

    @pytest.mark.asyncio
    async def test_list_exchanges(self, initialized_engine):
        """Test listing all exchange plans."""
        tool = ConfigExchangesTool()
        result = await tool.execute({})

        assert "count" in result
        assert "exchange_plans" in result
        assert result["type"] == "ExchangePlan"

    @pytest.mark.asyncio
    async def test_get_specific_exchange(self, initialized_engine):
        """Test getting specific exchange plan."""
        tool = ConfigExchangesTool()
        result = await tool.execute({"name": "ОбменСФилиалами"})

        assert "error" not in result
        assert result["name"] == "ОбменСФилиалами"
        assert result["full_name"] == "ExchangePlan.ОбменСФилиалами"
        assert "attributes" in result

    @pytest.mark.asyncio
    async def test_get_exchange_not_found(self, initialized_engine):
        """Test getting non-existent exchange plan."""
        tool = ConfigExchangesTool()
        result = await tool.execute({"name": "НесуществующийПлан"})

        assert "error" in result


class TestConfigHttpServicesTool:
    """Tests for config.http_services tool."""

    @pytest.mark.asyncio
    async def test_list_http_services(self, initialized_engine):
        """Test listing all HTTP services."""
        tool = ConfigHttpServicesTool()
        result = await tool.execute({})

        assert "count" in result
        assert "http_services" in result
        assert result["type"] == "HTTPService"

    @pytest.mark.asyncio
    async def test_get_specific_service(self, initialized_engine):
        """Test getting specific HTTP service."""
        tool = ConfigHttpServicesTool()
        result = await tool.execute({"name": "API"})

        assert "error" not in result
        assert result["name"] == "API"
        assert result["full_name"] == "HTTPService.API"

    @pytest.mark.asyncio
    async def test_get_service_not_found(self, initialized_engine):
        """Test getting non-existent HTTP service."""
        tool = ConfigHttpServicesTool()
        result = await tool.execute({"name": "НесуществующийСервис"})

        assert "error" in result
