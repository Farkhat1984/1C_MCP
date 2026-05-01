"""
Unit tests for config tools.
"""

import pytest
import pytest_asyncio

from mcp_1c.engines.metadata import MetadataEngine
from mcp_1c.tools.base import ToolError
from mcp_1c.tools.config_tools import (
    ConfigConstantsTool,
    ConfigEventSubscriptionsTool,
    ConfigExchangesTool,
    ConfigHttpServicesTool,
    ConfigOptionsTool,
    ConfigScheduledJobsTool,
)


@pytest_asyncio.fixture
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
        tool = ConfigOptionsTool(initialized_engine)
        result = await tool.execute({})

        assert "count" in result
        assert "options" in result
        assert result["type"] == "FunctionalOption"
        assert result["count"] >= 1
        assert isinstance(result["options"], list)
        assert len(result["options"]) == result["count"]

    @pytest.mark.asyncio
    async def test_get_specific_option(self, initialized_engine):
        """Test getting specific functional option."""
        tool = ConfigOptionsTool(initialized_engine)
        result = await tool.execute({"name": "ИспользоватьВалюты"})

        assert "error" not in result
        assert result["name"] == "ИспользоватьВалюты"
        assert result["full_name"] == "FunctionalOption.ИспользоватьВалюты"
        assert result["synonym"] == "Использовать валюты"
        assert result["comment"] == "Включает многовалютный учет"

    @pytest.mark.asyncio
    async def test_get_option_not_found(self, initialized_engine):
        """Test getting non-existent option."""
        tool = ConfigOptionsTool(initialized_engine)
        with pytest.raises(ToolError, match="not found"):
            await tool.execute({"name": "НесуществующаяОпция"})

    @pytest.mark.asyncio
    async def test_get_option_with_usage(self, initialized_engine):
        """Test getting option with usage info."""
        tool = ConfigOptionsTool(initialized_engine)
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
        tool = ConfigConstantsTool(initialized_engine)
        result = await tool.execute({})

        assert "count" in result
        assert "constants" in result
        assert result["type"] == "Constant"

    @pytest.mark.asyncio
    async def test_get_specific_constant(self, initialized_engine):
        """Test getting specific constant."""
        tool = ConfigConstantsTool(initialized_engine)
        result = await tool.execute({"name": "ОсновнаяВалюта"})

        assert "error" not in result
        assert result["name"] == "ОсновнаяВалюта"
        assert result["full_name"] == "Constant.ОсновнаяВалюта"
        assert result["synonym"] == "Основная валюта"
        assert result["comment"] == "Основная валюта учета"

    @pytest.mark.asyncio
    async def test_get_constant_not_found(self, initialized_engine):
        """Test getting non-existent constant."""
        tool = ConfigConstantsTool(initialized_engine)
        with pytest.raises(ToolError, match="not found"):
            await tool.execute({"name": "НесуществующаяКонстанта"})


class TestConfigScheduledJobsTool:
    """Tests for config.scheduled_jobs tool."""

    @pytest.mark.asyncio
    async def test_list_scheduled_jobs(self, initialized_engine):
        """Test listing all scheduled jobs."""
        tool = ConfigScheduledJobsTool(initialized_engine)
        result = await tool.execute({})

        assert "count" in result
        assert "scheduled_jobs" in result
        assert result["type"] == "ScheduledJob"

    @pytest.mark.asyncio
    async def test_get_specific_job(self, initialized_engine):
        """Test getting specific scheduled job."""
        tool = ConfigScheduledJobsTool(initialized_engine)
        result = await tool.execute({"name": "ОбновлениеКурсовВалют"})

        assert "error" not in result
        assert result["name"] == "ОбновлениеКурсовВалют"
        assert result["full_name"] == "ScheduledJob.ОбновлениеКурсовВалют"
        assert result["synonym"] == "Обновление курсов валют"
        assert result["comment"] == "Ежедневное обновление курсов валют"

    @pytest.mark.asyncio
    async def test_get_job_not_found(self, initialized_engine):
        """Test getting non-existent job."""
        tool = ConfigScheduledJobsTool(initialized_engine)
        with pytest.raises(ToolError, match="not found"):
            await tool.execute({"name": "НесуществующееЗадание"})


class TestConfigEventSubscriptionsTool:
    """Tests for config.event_subscriptions tool."""

    @pytest.mark.asyncio
    async def test_list_subscriptions(self, initialized_engine):
        """Test listing all event subscriptions."""
        tool = ConfigEventSubscriptionsTool(initialized_engine)
        result = await tool.execute({})

        assert "count" in result
        assert "event_subscriptions" in result
        assert result["type"] == "EventSubscription"

    @pytest.mark.asyncio
    async def test_get_specific_subscription(self, initialized_engine):
        """Test getting specific event subscription."""
        tool = ConfigEventSubscriptionsTool(initialized_engine)
        result = await tool.execute({"name": "ПриЗаписиТоваров"})

        assert "error" not in result
        assert result["name"] == "ПриЗаписиТоваров"
        assert result["full_name"] == "EventSubscription.ПриЗаписиТоваров"
        assert result["synonym"] == "При записи товаров"
        assert result["comment"] == "Обработка записи справочника товаров"

    @pytest.mark.asyncio
    async def test_get_subscription_not_found(self, initialized_engine):
        """Test getting non-existent subscription."""
        tool = ConfigEventSubscriptionsTool(initialized_engine)
        with pytest.raises(ToolError, match="not found"):
            await tool.execute({"name": "НесуществующаяПодписка"})

    @pytest.mark.asyncio
    async def test_filter_subscriptions(self, initialized_engine):
        """Test filtering subscriptions by event name."""
        tool = ConfigEventSubscriptionsTool(initialized_engine)
        result = await tool.execute({"filter_event": "Запис"})

        assert "count" in result
        assert result["filter"] == "Запис"


class TestConfigExchangesTool:
    """Tests for config.exchanges tool."""

    @pytest.mark.asyncio
    async def test_list_exchanges(self, initialized_engine):
        """Test listing all exchange plans."""
        tool = ConfigExchangesTool(initialized_engine)
        result = await tool.execute({})

        assert "count" in result
        assert "exchange_plans" in result
        assert result["type"] == "ExchangePlan"

    @pytest.mark.asyncio
    async def test_get_specific_exchange(self, initialized_engine):
        """Test getting specific exchange plan."""
        tool = ConfigExchangesTool(initialized_engine)
        result = await tool.execute({"name": "ОбменСФилиалами"})

        assert "error" not in result
        assert result["name"] == "ОбменСФилиалами"
        assert result["full_name"] == "ExchangePlan.ОбменСФилиалами"
        assert result["synonym"] == "Обмен с филиалами"
        assert result["comment"] == "План обмена с филиалами"
        assert "attributes" in result
        assert len(result["attributes"]) >= 1
        attr_names = [a["name"] for a in result["attributes"]]
        assert "Организация" in attr_names

    @pytest.mark.asyncio
    async def test_get_exchange_not_found(self, initialized_engine):
        """Test getting non-existent exchange plan."""
        tool = ConfigExchangesTool(initialized_engine)
        with pytest.raises(ToolError, match="not found"):
            await tool.execute({"name": "НесуществующийПлан"})


class TestConfigHttpServicesTool:
    """Tests for config.http_services tool."""

    @pytest.mark.asyncio
    async def test_list_http_services(self, initialized_engine):
        """Test listing all HTTP services."""
        tool = ConfigHttpServicesTool(initialized_engine)
        result = await tool.execute({})

        assert "count" in result
        assert "http_services" in result
        assert result["type"] == "HTTPService"

    @pytest.mark.asyncio
    async def test_get_specific_service(self, initialized_engine):
        """Test getting specific HTTP service."""
        tool = ConfigHttpServicesTool(initialized_engine)
        result = await tool.execute({"name": "API"})

        assert "error" not in result
        assert result["name"] == "API"
        assert result["full_name"] == "HTTPService.API"
        assert result["synonym"] == "REST API"
        assert result["comment"] == "REST API сервис"

    @pytest.mark.asyncio
    async def test_get_service_not_found(self, initialized_engine):
        """Test getting non-existent HTTP service."""
        tool = ConfigHttpServicesTool(initialized_engine)
        with pytest.raises(ToolError, match="not found"):
            await tool.execute({"name": "НесуществующийСервис"})
