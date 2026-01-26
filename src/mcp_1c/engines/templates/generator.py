"""
Code generator for generating 1C code from templates.

Handles placeholder substitution, validation, and context-aware generation.
"""

import re
from typing import Any

from mcp_1c.domain.templates import (
    CodeTemplate,
    GenerationContext,
    GenerationResult,
    Placeholder,
    PlaceholderType,
)
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


class CodeGenerator:
    """
    Generates 1C code from templates.

    Handles:
    - Placeholder substitution
    - Value validation
    - Context-aware generation
    - Code formatting
    """

    # Placeholder pattern: ${PlaceholderName} or ${PlaceholderName:default}
    PLACEHOLDER_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]*))?\}")

    # Conditional block pattern: {{#if Condition}}...{{/if}}
    CONDITIONAL_PATTERN = re.compile(
        r"\{\{#if\s+([A-Za-z_][A-Za-z0-9_]*)\}\}(.*?)\{\{/if\}\}",
        re.DOTALL,
    )

    # Loop pattern: {{#each Items}}...{{/each}}
    LOOP_PATTERN = re.compile(
        r"\{\{#each\s+([A-Za-z_][A-Za-z0-9_]*)\}\}(.*?)\{\{/each\}\}",
        re.DOTALL,
    )

    # 1C identifier pattern
    IDENTIFIER_PATTERN = re.compile(r"^[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*$")

    def __init__(self) -> None:
        """Initialize code generator."""
        pass

    def generate(
        self,
        template: CodeTemplate,
        values: dict[str, Any],
        context: GenerationContext | None = None,
    ) -> GenerationResult:
        """
        Generate code from template.

        Args:
            template: Template to use
            values: Placeholder values
            context: Optional generation context

        Returns:
            GenerationResult with generated code or errors
        """
        # Validate values
        validation = self._validate_values(template, values)
        if not validation["is_valid"]:
            return GenerationResult(
                success=False,
                template_id=template.id,
                error="Validation failed",
                missing_placeholders=validation["missing"],
                invalid_values=validation["invalid"],
            )

        # Merge with defaults
        merged_values = self._merge_with_defaults(template, values)

        # Add context values if available
        if context:
            merged_values = self._add_context_values(merged_values, template, context)

        # Generate code
        try:
            code = self._substitute(template.template_code, merged_values)

            # Process conditionals
            code = self._process_conditionals(code, merged_values)

            # Process loops
            code = self._process_loops(code, merged_values)

            # Clean up
            code = self._cleanup_code(code)

            return GenerationResult(
                success=True,
                code=code,
                template_id=template.id,
                warnings=validation.get("warnings", []),
                suggestions=self._generate_suggestions(template, merged_values, context),
            )

        except Exception as e:
            logger.error(f"Error generating code: {e}")
            return GenerationResult(
                success=False,
                template_id=template.id,
                error=str(e),
            )

    def _validate_values(
        self,
        template: CodeTemplate,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Validate placeholder values.

        Args:
            template: Template with placeholder definitions
            values: Values to validate

        Returns:
            Validation result dictionary
        """
        result = {
            "is_valid": True,
            "missing": [],
            "invalid": {},
            "warnings": [],
        }

        for placeholder in template.placeholders:
            value = values.get(placeholder.name)

            # Check required
            if placeholder.required and value is None:
                if placeholder.default_value is None:
                    result["is_valid"] = False
                    result["missing"].append(placeholder.name)
                    continue

            if value is not None:
                # Validate type
                type_error = self._validate_type(placeholder, value)
                if type_error:
                    result["is_valid"] = False
                    result["invalid"][placeholder.name] = type_error
                    continue

                # Validate pattern
                if placeholder.validation_pattern:
                    if not re.match(placeholder.validation_pattern, str(value)):
                        result["is_valid"] = False
                        result["invalid"][placeholder.name] = (
                            f"Value does not match pattern: {placeholder.validation_pattern}"
                        )
                        continue

                # Validate allowed values
                if placeholder.allowed_values:
                    if str(value) not in placeholder.allowed_values:
                        result["is_valid"] = False
                        result["invalid"][placeholder.name] = (
                            f"Value must be one of: {', '.join(placeholder.allowed_values)}"
                        )
                        continue

        return result

    def _validate_type(self, placeholder: Placeholder, value: Any) -> str | None:
        """
        Validate value type against placeholder type.

        Args:
            placeholder: Placeholder definition
            value: Value to validate

        Returns:
            Error message or None if valid
        """
        ptype = placeholder.placeholder_type

        if ptype == PlaceholderType.IDENTIFIER:
            if not self.IDENTIFIER_PATTERN.match(str(value)):
                return "Invalid 1C identifier format"

        elif ptype == PlaceholderType.INTEGER:
            try:
                int(value)
            except (ValueError, TypeError):
                return "Value must be an integer"

        elif ptype == PlaceholderType.BOOLEAN:
            if str(value).lower() not in ("true", "false", "истина", "ложь", "1", "0"):
                return "Value must be a boolean"

        elif ptype == PlaceholderType.METADATA_NAME:
            # Basic validation - more detailed would need metadata context
            if not self.IDENTIFIER_PATTERN.match(str(value)):
                return "Invalid metadata object name"

        elif ptype == PlaceholderType.TABLE_NAME:
            # Allow dotted names like "Справочник.Номенклатура"
            parts = str(value).split(".")
            for part in parts:
                if not self.IDENTIFIER_PATTERN.match(part):
                    return "Invalid table name format"

        return None

    def _merge_with_defaults(
        self,
        template: CodeTemplate,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Merge provided values with defaults.

        Args:
            template: Template with defaults
            values: Provided values

        Returns:
            Merged values dictionary
        """
        merged = dict(values)

        for placeholder in template.placeholders:
            if placeholder.name not in merged and placeholder.default_value is not None:
                merged[placeholder.name] = placeholder.default_value

        return merged

    def _add_context_values(
        self,
        values: dict[str, Any],
        template: CodeTemplate,
        context: GenerationContext,
    ) -> dict[str, Any]:
        """
        Add context-derived values to the values dictionary.

        Args:
            values: Current values
            template: Template being used
            context: Generation context

        Returns:
            Values with context additions
        """
        result = dict(values)

        # Add object info if available and not already set
        if context.current_object_name and "ObjectName" not in result:
            result["ObjectName"] = context.current_object_name

        if context.current_object_type and "ObjectType" not in result:
            result["ObjectType"] = context.current_object_type

        return result

    def _substitute(self, template_code: str, values: dict[str, Any]) -> str:
        """
        Substitute placeholders with values.

        Args:
            template_code: Template code with placeholders
            values: Values to substitute

        Returns:
            Code with substituted values
        """
        def replace_placeholder(match: re.Match) -> str:
            name = match.group(1)
            default = match.group(2)

            if name in values:
                return str(values[name])
            elif default is not None:
                return default
            else:
                # Keep placeholder if no value and no default
                return match.group(0)

        return self.PLACEHOLDER_PATTERN.sub(replace_placeholder, template_code)

    def _process_conditionals(self, code: str, values: dict[str, Any]) -> str:
        """
        Process conditional blocks.

        Args:
            code: Code with conditional blocks
            values: Values for condition evaluation

        Returns:
            Code with processed conditionals
        """
        def replace_conditional(match: re.Match) -> str:
            condition_var = match.group(1)
            content = match.group(2)

            # Check if condition is truthy
            value = values.get(condition_var)
            is_truthy = bool(value) and str(value).lower() not in ("false", "ложь", "0", "")

            return content if is_truthy else ""

        return self.CONDITIONAL_PATTERN.sub(replace_conditional, code)

    def _process_loops(self, code: str, values: dict[str, Any]) -> str:
        """
        Process loop blocks.

        Args:
            code: Code with loop blocks
            values: Values containing lists for loops

        Returns:
            Code with processed loops
        """
        def replace_loop(match: re.Match) -> str:
            list_var = match.group(1)
            content = match.group(2)

            items = values.get(list_var, [])
            if not isinstance(items, (list, tuple)):
                return ""

            results = []
            for i, item in enumerate(items):
                # Create item-specific values
                item_values = dict(values)
                if isinstance(item, dict):
                    item_values.update(item)
                else:
                    item_values["item"] = item
                item_values["index"] = i
                item_values["first"] = i == 0
                item_values["last"] = i == len(items) - 1

                # Substitute in content
                item_code = self._substitute(content, item_values)
                results.append(item_code)

            return "".join(results)

        return self.LOOP_PATTERN.sub(replace_loop, code)

    def _cleanup_code(self, code: str) -> str:
        """
        Clean up generated code.

        Args:
            code: Generated code

        Returns:
            Cleaned code
        """
        # Remove multiple empty lines
        code = re.sub(r"\n{3,}", "\n\n", code)

        # Remove trailing whitespace
        lines = [line.rstrip() for line in code.split("\n")]
        code = "\n".join(lines)

        # Ensure single newline at end
        code = code.strip() + "\n"

        return code

    def _generate_suggestions(
        self,
        template: CodeTemplate,
        values: dict[str, Any],
        context: GenerationContext | None,
    ) -> list[str]:
        """
        Generate usage suggestions for the generated code.

        Args:
            template: Used template
            values: Used values
            context: Generation context

        Returns:
            List of suggestions
        """
        suggestions = []

        # Add template-specific suggestions
        if template.use_cases:
            suggestions.append(f"Типичные применения: {', '.join(template.use_cases)}")

        return suggestions

    def preview(
        self,
        template: CodeTemplate,
        values: dict[str, Any],
    ) -> str:
        """
        Generate a preview of the code without full validation.

        Args:
            template: Template to use
            values: Placeholder values

        Returns:
            Preview code string
        """
        # Merge with defaults
        merged_values = self._merge_with_defaults(template, values)

        # Generate code
        code = self._substitute(template.template_code, merged_values)
        code = self._process_conditionals(code, merged_values)
        code = self._process_loops(code, merged_values)
        code = self._cleanup_code(code)

        return code

    def get_placeholders_from_code(self, code: str) -> list[str]:
        """
        Extract placeholder names from template code.

        Args:
            code: Template code

        Returns:
            List of placeholder names found in code
        """
        matches = self.PLACEHOLDER_PATTERN.findall(code)
        return list({m[0] for m in matches})
