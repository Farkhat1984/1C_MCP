"""
Unit tests for Skills (prompts).
"""

import pytest

from mcp_1c.prompts.base import BasePrompt
from mcp_1c.prompts.registry import PromptRegistry
from mcp_1c.prompts.skills import (
    QuerySkill,
    MetadataSkill,
    HandlerSkill,
    PrintSkill,
    UsagesSkill,
    ValidateSkill,
    DepsSkill,
    MovementSkill,
    FormatSkill,
    ExplainSkill,
)


class TestBasePrompt:
    """Tests for BasePrompt class."""

    def test_query_skill_has_required_attributes(self) -> None:
        """Test that QuerySkill has all required class attributes."""
        skill = QuerySkill()
        assert hasattr(skill, "name")
        assert hasattr(skill, "description")
        assert hasattr(skill, "arguments")
        assert skill.name == "1c-query"

    def test_prompt_definition(self) -> None:
        """Test get_prompt_definition returns correct structure."""
        skill = QuerySkill()
        definition = skill.get_prompt_definition()

        assert definition.name == "1c-query"
        assert definition.description is not None
        assert len(definition.arguments) > 0

    def test_validate_arguments_required(self) -> None:
        """Test that validation fails for missing required arguments."""
        skill = QuerySkill()

        with pytest.raises(ValueError, match="Required argument 'object' is missing"):
            skill.validate_arguments({})

    def test_validate_arguments_success(self) -> None:
        """Test that validation passes with required arguments."""
        skill = QuerySkill()
        result = skill.validate_arguments({"object": "Справочник.Номенклатура"})

        assert result["object"] == "Справочник.Номенклатура"

    def test_validate_arguments_with_optional(self) -> None:
        """Test that optional arguments are included when provided."""
        skill = QuerySkill()
        result = skill.validate_arguments({
            "object": "Справочник.Номенклатура",
            "fields": "Код, Наименование",
            "conditions": "ЭтоГруппа = Ложь",
        })

        assert result["object"] == "Справочник.Номенклатура"
        assert result["fields"] == "Код, Наименование"
        assert result["conditions"] == "ЭтоГруппа = Ложь"


class TestPromptRegistry:
    """Tests for PromptRegistry."""

    def test_registry_registers_all_skills(self) -> None:
        """Test that registry registers all 10 skills + 4 agents = 14 prompts."""
        registry = PromptRegistry()
        prompts = registry.list_prompts()

        # 10 skills + 4 agents = 14 total
        assert len(prompts) == 14

    def test_registry_get_existing_prompt(self) -> None:
        """Test getting existing prompt by name."""
        registry = PromptRegistry()
        prompt = registry.get("1c-query")

        assert prompt is not None
        assert prompt.name == "1c-query"

    def test_registry_get_nonexistent_prompt(self) -> None:
        """Test getting non-existent prompt returns None."""
        registry = PromptRegistry()
        prompt = registry.get("nonexistent")

        assert prompt is None

    def test_registry_list_prompts_structure(self) -> None:
        """Test that listed prompts have correct structure."""
        registry = PromptRegistry()
        prompts = registry.list_prompts()

        for prompt in prompts:
            assert prompt.name is not None
            assert prompt.description is not None


class TestQuerySkill:
    """Tests for QuerySkill."""

    @pytest.mark.asyncio
    async def test_generate_messages(self) -> None:
        """Test message generation."""
        skill = QuerySkill()
        messages = await skill.generate_messages({"object": "Справочник.Номенклатура"})

        assert len(messages) == 1
        assert messages[0].role == "user"
        assert "Справочник.Номенклатура" in messages[0].content.text

    @pytest.mark.asyncio
    async def test_generate_messages_with_all_args(self) -> None:
        """Test message generation with all arguments."""
        skill = QuerySkill()
        messages = await skill.generate_messages({
            "object": "Документ.Реализация",
            "fields": "Номер, Дата",
            "conditions": "Проведен = Истина",
        })

        assert len(messages) == 1
        content = messages[0].content.text
        assert "Документ.Реализация" in content
        assert "Номер, Дата" in content
        assert "Проведен = Истина" in content


class TestMetadataSkill:
    """Tests for MetadataSkill."""

    @pytest.mark.asyncio
    async def test_generate_messages(self) -> None:
        """Test message generation."""
        skill = MetadataSkill()
        messages = await skill.generate_messages({"object": "Документ.РеализацияТоваров"})

        assert len(messages) == 1
        assert "Документ.РеализацияТоваров" in messages[0].content.text
        assert "metadata.get" in messages[0].content.text


class TestHandlerSkill:
    """Tests for HandlerSkill."""

    @pytest.mark.asyncio
    async def test_generate_messages(self) -> None:
        """Test message generation."""
        skill = HandlerSkill()
        messages = await skill.generate_messages({
            "object": "Документ.ПриходнаяНакладная",
            "event": "ПриЗаписи",
        })

        assert len(messages) == 1
        content = messages[0].content.text
        assert "Документ.ПриходнаяНакладная" in content
        assert "ПриЗаписи" in content


class TestPrintSkill:
    """Tests for PrintSkill."""

    @pytest.mark.asyncio
    async def test_generate_messages(self) -> None:
        """Test message generation."""
        skill = PrintSkill()
        messages = await skill.generate_messages({"object": "Документ.СчетНаОплату"})

        assert len(messages) == 1
        assert "Документ.СчетНаОплату" in messages[0].content.text
        assert "generate.print" in messages[0].content.text


class TestUsagesSkill:
    """Tests for UsagesSkill."""

    @pytest.mark.asyncio
    async def test_generate_messages(self) -> None:
        """Test message generation."""
        skill = UsagesSkill()
        messages = await skill.generate_messages({"name": "ЗаполнитьТабличнуюЧасть"})

        assert len(messages) == 1
        assert "ЗаполнитьТабличнуюЧасть" in messages[0].content.text
        assert "code.usages" in messages[0].content.text


class TestValidateSkill:
    """Tests for ValidateSkill."""

    @pytest.mark.asyncio
    async def test_generate_messages(self) -> None:
        """Test message generation."""
        skill = ValidateSkill()
        messages = await skill.generate_messages({"module": "Документ.Реализация.МодульОбъекта"})

        assert len(messages) == 1
        assert "Документ.Реализация.МодульОбъекта" in messages[0].content.text
        assert "code.validate" in messages[0].content.text


class TestDepsSkill:
    """Tests for DepsSkill."""

    @pytest.mark.asyncio
    async def test_generate_messages(self) -> None:
        """Test message generation."""
        skill = DepsSkill()
        messages = await skill.generate_messages({"module": "ОбщийМодуль.ОбщегоНазначения"})

        assert len(messages) == 1
        assert "ОбщийМодуль.ОбщегоНазначения" in messages[0].content.text
        assert "code.dependencies" in messages[0].content.text


class TestMovementSkill:
    """Tests for MovementSkill."""

    @pytest.mark.asyncio
    async def test_generate_messages(self) -> None:
        """Test message generation."""
        skill = MovementSkill()
        messages = await skill.generate_messages({"document": "Документ.ПоступлениеТоваров"})

        assert len(messages) == 1
        assert "Документ.ПоступлениеТоваров" in messages[0].content.text
        assert "generate.movement" in messages[0].content.text


class TestFormatSkill:
    """Tests for FormatSkill."""

    @pytest.mark.asyncio
    async def test_generate_messages(self) -> None:
        """Test message generation."""
        skill = FormatSkill()
        messages = await skill.generate_messages({"module": "Документ.Заказ.МодульФормы"})

        assert len(messages) == 1
        assert "Документ.Заказ.МодульФормы" in messages[0].content.text
        assert "code.format" in messages[0].content.text


class TestExplainSkill:
    """Tests for ExplainSkill."""

    @pytest.mark.asyncio
    async def test_generate_messages(self) -> None:
        """Test message generation."""
        skill = ExplainSkill()
        messages = await skill.generate_messages({"module": "ОбщийМодуль.РаботаСФайлами"})

        assert len(messages) == 1
        assert "ОбщийМодуль.РаботаСФайлами" in messages[0].content.text
        assert "code.analyze" in messages[0].content.text

    @pytest.mark.asyncio
    async def test_generate_messages_with_procedure(self) -> None:
        """Test message generation with procedure argument."""
        skill = ExplainSkill()
        messages = await skill.generate_messages({
            "module": "ОбщийМодуль.РаботаСФайлами",
            "procedure": "ПолучитьФайл",
        })

        assert len(messages) == 1
        content = messages[0].content.text
        assert "ОбщийМодуль.РаботаСФайлами" in content
        assert "ПолучитьФайл" in content


class TestPromptRegistryIntegration:
    """Integration tests for PromptRegistry."""

    @pytest.mark.asyncio
    async def test_get_prompt_messages(self) -> None:
        """Test getting prompt messages through registry."""
        registry = PromptRegistry()
        messages = await registry.get_prompt_messages(
            "1c-query",
            {"object": "Справочник.Контрагенты"},
        )

        assert len(messages) == 1
        assert "Справочник.Контрагенты" in messages[0].content.text

    @pytest.mark.asyncio
    async def test_get_prompt_messages_unknown(self) -> None:
        """Test error for unknown prompt."""
        registry = PromptRegistry()

        with pytest.raises(ValueError, match="Unknown prompt"):
            await registry.get_prompt_messages("unknown-skill", {})

    @pytest.mark.asyncio
    async def test_get_prompt_messages_missing_args(self) -> None:
        """Test error for missing required arguments."""
        registry = PromptRegistry()

        with pytest.raises(ValueError, match="Required argument"):
            await registry.get_prompt_messages("1c-query", {})
