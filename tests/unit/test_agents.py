"""
Unit tests for Agents (complex prompts).
"""

import pytest

from mcp_1c.prompts.registry import PromptRegistry
from mcp_1c.prompts.agents import (
    ExploreAgent,
    ImplementAgent,
    DebugAgent,
    ConfigureAgent,
)


class TestExploreAgent:
    """Tests for ExploreAgent."""

    def test_has_required_attributes(self) -> None:
        """Test that agent has all required class attributes."""
        agent = ExploreAgent()
        assert agent.name == "1c-explore"
        assert agent.description is not None
        assert len(agent.arguments) > 0

    def test_prompt_definition(self) -> None:
        """Test get_prompt_definition returns correct structure."""
        agent = ExploreAgent()
        definition = agent.get_prompt_definition()

        assert definition.name == "1c-explore"
        assert "path" in [arg.name for arg in definition.arguments]

    def test_validate_arguments_required(self) -> None:
        """Test that validation fails for missing required arguments."""
        agent = ExploreAgent()

        with pytest.raises(ValueError, match="Required argument 'path' is missing"):
            agent.validate_arguments({})

    @pytest.mark.asyncio
    async def test_generate_messages(self) -> None:
        """Test message generation."""
        agent = ExploreAgent()
        messages = await agent.generate_messages({"path": "C:/1C/Configuration"})

        assert len(messages) == 1
        content = messages[0].content.text
        assert "C:/1C/Configuration" in content
        assert "metadata-init" in content
        assert "metadata-tree" in content

    @pytest.mark.asyncio
    async def test_generate_messages_with_focus(self) -> None:
        """Test message generation with focus parameter."""
        agent = ExploreAgent()
        messages = await agent.generate_messages({
            "path": "C:/1C/Configuration",
            "focus": "documents",
            "depth": "detailed",
        })

        assert len(messages) == 1
        content = messages[0].content.text
        assert "documents" in content
        assert "detailed" in content


class TestImplementAgent:
    """Tests for ImplementAgent."""

    def test_has_required_attributes(self) -> None:
        """Test that agent has all required class attributes."""
        agent = ImplementAgent()
        assert agent.name == "1c-implement"
        assert agent.description is not None
        assert len(agent.arguments) > 0

    def test_validate_arguments_required(self) -> None:
        """Test that validation fails for missing required arguments."""
        agent = ImplementAgent()

        with pytest.raises(ValueError, match="Required argument 'task' is missing"):
            agent.validate_arguments({})

    @pytest.mark.asyncio
    async def test_generate_messages(self) -> None:
        """Test message generation."""
        agent = ImplementAgent()
        messages = await agent.generate_messages({
            "task": "Добавить автоматическое заполнение контрагента по ИНН",
        })

        assert len(messages) == 1
        content = messages[0].content.text
        assert "контрагента по ИНН" in content
        assert "generate-query" in content or "generate-handler" in content

    @pytest.mark.asyncio
    async def test_generate_messages_with_object(self) -> None:
        """Test message generation with target object."""
        agent = ImplementAgent()
        messages = await agent.generate_messages({
            "task": "Добавить расчёт скидки",
            "object": "Документ.РеализацияТоваров",
            "style": "bsp",
        })

        assert len(messages) == 1
        content = messages[0].content.text
        assert "Документ.РеализацияТоваров" in content
        assert "bsp" in content.lower() or "БСП" in content


class TestDebugAgent:
    """Tests for DebugAgent."""

    def test_has_required_attributes(self) -> None:
        """Test that agent has all required class attributes."""
        agent = DebugAgent()
        assert agent.name == "1c-debug"
        assert agent.description is not None
        assert len(agent.arguments) > 0

    def test_validate_arguments_required(self) -> None:
        """Test that validation fails for missing required arguments."""
        agent = DebugAgent()

        with pytest.raises(ValueError, match="Required argument 'problem' is missing"):
            agent.validate_arguments({})

    @pytest.mark.asyncio
    async def test_generate_messages(self) -> None:
        """Test message generation."""
        agent = DebugAgent()
        messages = await agent.generate_messages({
            "problem": "Документ не проводится, ошибка при записи движений",
        })

        assert len(messages) == 1
        content = messages[0].content.text
        assert "не проводится" in content
        assert "code-validate" in content

    @pytest.mark.asyncio
    async def test_generate_messages_with_error(self) -> None:
        """Test message generation with error text."""
        agent = DebugAgent()
        messages = await agent.generate_messages({
            "problem": "Ошибка при проведении",
            "module": "Документ.Реализация.МодульОбъекта",
            "error": "Поле 'Номенклатура' не заполнено",
        })

        assert len(messages) == 1
        content = messages[0].content.text
        assert "Документ.Реализация.МодульОбъекта" in content
        assert "Номенклатура" in content


class TestConfigureAgent:
    """Tests for ConfigureAgent."""

    def test_has_required_attributes(self) -> None:
        """Test that agent has all required class attributes."""
        agent = ConfigureAgent()
        assert agent.name == "1c-configure"
        assert agent.description is not None
        assert len(agent.arguments) > 0

    def test_validate_arguments_required(self) -> None:
        """Test that validation fails for missing required arguments."""
        agent = ConfigureAgent()

        with pytest.raises(ValueError, match="Required argument 'goal' is missing"):
            agent.validate_arguments({})

    @pytest.mark.asyncio
    async def test_generate_messages(self) -> None:
        """Test message generation."""
        agent = ConfigureAgent()
        messages = await agent.generate_messages({
            "goal": "Добавить новый вид номенклатуры 'Услуга'",
        })

        assert len(messages) == 1
        content = messages[0].content.text
        assert "Услуга" in content
        assert "config-options" in content or "metadata-search" in content

    @pytest.mark.asyncio
    async def test_generate_messages_with_approach(self) -> None:
        """Test message generation with approach parameter."""
        agent = ConfigureAgent()
        messages = await agent.generate_messages({
            "goal": "Добавить дополнительный реквизит к контрагенту",
            "configuration": "ERP",
            "approach": "extension",
        })

        assert len(messages) == 1
        content = messages[0].content.text
        assert "ERP" in content
        assert "расширен" in content.lower()


class TestPromptRegistryWithAgents:
    """Integration tests for PromptRegistry with agents."""

    def test_registry_includes_agents(self) -> None:
        """Test that registry includes all agents."""
        registry = PromptRegistry()
        prompts = registry.list_prompts()

        # Should have 10 skills + 4 agents = 14 total
        assert len(prompts) == 14

        # Check agents are registered
        agent_names = ["1c-explore", "1c-implement", "1c-debug", "1c-configure"]
        registered_names = [p.name for p in prompts]

        for name in agent_names:
            assert name in registered_names

    def test_registry_get_agent(self) -> None:
        """Test getting agent by name."""
        registry = PromptRegistry()

        explore = registry.get("1c-explore")
        assert explore is not None
        assert isinstance(explore, ExploreAgent)

        implement = registry.get("1c-implement")
        assert implement is not None
        assert isinstance(implement, ImplementAgent)

    @pytest.mark.asyncio
    async def test_get_agent_messages(self) -> None:
        """Test getting agent messages through registry."""
        registry = PromptRegistry()
        messages = await registry.get_prompt_messages(
            "1c-explore",
            {"path": "C:/Configs/MyConfig"},
        )

        assert len(messages) == 1
        assert "C:/Configs/MyConfig" in messages[0].content.text

    @pytest.mark.asyncio
    async def test_get_agent_messages_missing_args(self) -> None:
        """Test error for missing required arguments."""
        registry = PromptRegistry()

        with pytest.raises(ValueError, match="Required argument"):
            await registry.get_prompt_messages("1c-implement", {})
