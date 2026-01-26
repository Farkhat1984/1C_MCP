"""
Fill Code Generator for MXL templates.

Generates BSL code for filling tabular document templates.
"""

from mcp_1c.domain.mxl import (
    AreaType,
    FillCodeGenerationOptions,
    GeneratedFillCode,
    MxlArea,
    MxlDocument,
    ParameterType,
    TemplateParameter,
)
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


class FillCodeGenerator:
    """Generator for template fill code."""

    def __init__(self) -> None:
        """Initialize generator."""
        pass

    def generate(
        self,
        document: MxlDocument,
        options: FillCodeGenerationOptions | None = None,
    ) -> GeneratedFillCode:
        """Generate fill code for MXL document.

        Args:
            document: Parsed MXL document
            options: Generation options

        Returns:
            Generated code with breakdown
        """
        if options is None:
            options = FillCodeGenerationOptions()

        result = GeneratedFillCode(
            code="",
            parameters_used=[],
            areas_used=[],
            suggestions=[],
        )

        # Generate initialization code
        result.initialization_code = self._generate_initialization(document, options)

        # Generate area fill code
        for area in document.areas:
            area_code = self._generate_area_code(area, options)
            result.area_fill_code[area.name] = area_code
            result.areas_used.append(area.name)

        # Generate output code
        result.output_code = self._generate_output_code(document, options)

        # Collect all parameters
        result.parameters_used = document.get_unique_parameter_names()

        # Combine all code
        result.code = self._combine_code(result, options)

        # Add suggestions
        result.suggestions = self._generate_suggestions(document, options)

        return result

    def _generate_initialization(
        self, document: MxlDocument, options: FillCodeGenerationOptions
    ) -> str:
        """Generate template initialization code."""
        lines: list[str] = []
        var_name = options.variable_name
        tmpl_var = options.template_variable

        lang = options.language

        if options.generate_comments:
            comment = (
                "// Получение макета и создание табличного документа"
                if lang == "ru"
                else "// Get template and create spreadsheet document"
            )
            lines.append(comment)

        # Get template
        if document.object_type and document.object_name and document.template_name:
            if lang == "ru":
                lines.append(
                    f'{tmpl_var} = ПолучитьМакет("{document.template_name}");'
                )
            else:
                lines.append(
                    f'{tmpl_var} = GetTemplate("{document.template_name}");'
                )
        else:
            if lang == "ru":
                lines.append(f'{tmpl_var} = ПолучитьМакет("ИмяМакета");')
            else:
                lines.append(f'{tmpl_var} = GetTemplate("TemplateName");')

        # Create spreadsheet document
        if lang == "ru":
            lines.append(f"{var_name} = Новый ТабличныйДокумент;")
        else:
            lines.append(f"{var_name} = New SpreadsheetDocument;")

        lines.append("")

        return "\n".join(lines)

    def _generate_area_code(
        self, area: MxlArea, options: FillCodeGenerationOptions
    ) -> str:
        """Generate code for filling a single area."""
        lines: list[str] = []
        var_name = options.variable_name
        tmpl_var = options.template_variable
        lang = options.language

        # Comment for area
        if options.generate_comments:
            area_type_comment = self._get_area_type_comment(area.area_type, lang)
            lines.append(f"// {area_type_comment}: {area.name}")

        # Get area
        if options.use_areas:
            if lang == "ru":
                lines.append(f'Область{area.name} = {tmpl_var}.ПолучитьОбласть("{area.name}");')
            else:
                lines.append(f'Area{area.name} = {tmpl_var}.GetArea("{area.name}");')

        # Fill parameters
        if area.parameters:
            if options.generate_comments and area.parameters:
                comment = (
                    "// Заполнение параметров"
                    if lang == "ru"
                    else "// Fill parameters"
                )
                lines.append(comment)

            for param in area.parameters:
                param_code = self._generate_parameter_code(
                    param, f"Область{area.name}" if lang == "ru" else f"Area{area.name}",
                    options
                )
                lines.append(param_code)

        # Output area
        lines.append("")
        if options.use_areas:
            if lang == "ru":
                lines.append(f"{var_name}.Вывести(Область{area.name});")
            else:
                lines.append(f"{var_name}.Put(Area{area.name});")

        # For table areas, add loop structure
        if area.is_table_area:
            lines = self._wrap_in_loop(lines, area, options)

        lines.append("")

        return "\n".join(lines)

    def _generate_parameter_code(
        self,
        param: TemplateParameter,
        area_var: str,
        options: FillCodeGenerationOptions,
    ) -> str:
        """Generate code for filling a single parameter."""
        lang = options.language
        data_var = options.data_variable

        # Determine value expression
        if param.data_path:
            value_expr = f"{data_var}.{param.data_path}"
        elif param.parameter_type == ParameterType.DATE:
            value_expr = (
                'Формат(ТекущаяДата(), "ДЛФ=Д")'
                if lang == "ru"
                else 'Format(CurrentDate(), "DLF=D")'
            )
        elif param.parameter_type == ParameterType.NUMBER:
            value_expr = "0"
        else:
            # Default - use data variable with parameter name
            value_expr = f"{data_var}.{param.name}"

        if options.use_parameters_collection:
            if lang == "ru":
                return f'{area_var}.Параметры.{param.name} = {value_expr};'
            else:
                return f'{area_var}.Parameters.{param.name} = {value_expr};'
        else:
            if lang == "ru":
                return f'{area_var}.Параметры["{param.name}"] = {value_expr};'
            else:
                return f'{area_var}.Parameters["{param.name}"] = {value_expr};'

    def _wrap_in_loop(
        self, lines: list[str], area: MxlArea, options: FillCodeGenerationOptions
    ) -> list[str]:
        """Wrap area code in a loop for table areas."""
        lang = options.language
        data_var = options.data_variable

        wrapped: list[str] = []

        if options.generate_comments:
            comment = (
                "// Вывод строк таблицы"
                if lang == "ru"
                else "// Output table rows"
            )
            wrapped.append(comment)

        # Loop start
        if lang == "ru":
            wrapped.append(f"Для Каждого Строка Из {data_var}.Строки Цикл")
        else:
            wrapped.append(f"For Each Row In {data_var}.Rows Do")

        # Indent and add original lines
        for line in lines:
            if line.strip():
                wrapped.append(f"\t{line}")
            else:
                wrapped.append("")

        # Loop end
        if lang == "ru":
            wrapped.append("КонецЦикла;")
        else:
            wrapped.append("EndDo;")

        return wrapped

    def _generate_output_code(
        self, document: MxlDocument, options: FillCodeGenerationOptions
    ) -> str:
        """Generate final output code."""
        lines: list[str] = []
        var_name = options.variable_name
        lang = options.language

        if options.generate_comments:
            comment = (
                "// Вывод документа"
                if lang == "ru"
                else "// Output document"
            )
            lines.append(comment)

        if lang == "ru":
            lines.append(f"{var_name}.Показать();")
        else:
            lines.append(f"{var_name}.Show();")

        return "\n".join(lines)

    def _combine_code(
        self, result: GeneratedFillCode, options: FillCodeGenerationOptions
    ) -> str:
        """Combine all code parts into final code."""
        parts: list[str] = []

        # Initialization
        parts.append(result.initialization_code)

        # Areas in order
        for area_name in result.areas_used:
            if area_name in result.area_fill_code:
                parts.append(result.area_fill_code[area_name])

        # Output
        parts.append(result.output_code)

        return "\n".join(parts)

    def _generate_suggestions(
        self, document: MxlDocument, options: FillCodeGenerationOptions
    ) -> list[str]:
        """Generate code improvement suggestions."""
        suggestions: list[str] = []
        lang = options.language

        # Check for table areas without loops
        table_areas = document.get_table_areas()
        if table_areas:
            if lang == "ru":
                suggestions.append(
                    "Обнаружены табличные области. Код включает цикл для вывода строк."
                )
            else:
                suggestions.append(
                    "Table areas detected. Code includes loop for row output."
                )

        # Check for many parameters
        if len(document.parameters) > 10:
            if lang == "ru":
                suggestions.append(
                    f"Макет содержит {len(document.parameters)} параметров. "
                    "Рассмотрите использование структуры данных для передачи значений."
                )
            else:
                suggestions.append(
                    f"Template contains {len(document.parameters)} parameters. "
                    "Consider using a data structure to pass values."
                )

        # Check for date parameters
        date_params = [
            p for p in document.parameters
            if p.parameter_type == ParameterType.DATE
        ]
        if date_params:
            if lang == "ru":
                suggestions.append(
                    "Для параметров дат используйте функцию Формат() для правильного отображения."
                )
            else:
                suggestions.append(
                    "For date parameters, use Format() function for proper display."
                )

        # Check for number parameters
        number_params = [
            p for p in document.parameters
            if p.parameter_type == ParameterType.NUMBER
        ]
        if number_params:
            if lang == "ru":
                suggestions.append(
                    "Для числовых параметров используйте функцию Формат() для форматирования."
                )
            else:
                suggestions.append(
                    "For number parameters, use Format() function for formatting."
                )

        return suggestions

    def _get_area_type_comment(self, area_type: AreaType, lang: str) -> str:
        """Get comment text for area type."""
        if lang == "ru":
            mapping = {
                AreaType.HEADER: "Шапка",
                AreaType.FOOTER: "Подвал",
                AreaType.TABLE_HEADER: "Шапка таблицы",
                AreaType.TABLE_ROW: "Строка таблицы",
                AreaType.TABLE_FOOTER: "Подвал таблицы",
                AreaType.DETAIL: "Детали",
                AreaType.GROUP_HEADER: "Шапка группы",
                AreaType.GROUP_FOOTER: "Подвал группы",
                AreaType.CUSTOM: "Область",
            }
        else:
            mapping = {
                AreaType.HEADER: "Header",
                AreaType.FOOTER: "Footer",
                AreaType.TABLE_HEADER: "Table header",
                AreaType.TABLE_ROW: "Table row",
                AreaType.TABLE_FOOTER: "Table footer",
                AreaType.DETAIL: "Detail",
                AreaType.GROUP_HEADER: "Group header",
                AreaType.GROUP_FOOTER: "Group footer",
                AreaType.CUSTOM: "Area",
            }
        return mapping.get(area_type, "Area" if lang == "en" else "Область")

    def generate_simple_fill(
        self,
        document: MxlDocument,
        data_mapping: dict[str, str] | None = None,
        language: str = "ru",
    ) -> str:
        """Generate simple fill code without options.

        Args:
            document: Parsed MXL document
            data_mapping: Mapping of parameter names to data expressions
            language: Code language (ru/en)

        Returns:
            Generated BSL code
        """
        options = FillCodeGenerationOptions(
            language=language,
            generate_comments=True,
        )

        result = self.generate(document, options)

        # Apply data mapping if provided
        if data_mapping:
            code = result.code
            for param_name, data_expr in data_mapping.items():
                # Replace default data references
                old_pattern = f"Data.{param_name}"
                code = code.replace(old_pattern, data_expr)
            return code

        return result.code

    def generate_procedure(
        self,
        document: MxlDocument,
        procedure_name: str = "ЗаполнитьМакет",
        parameter_name: str = "Данные",
        language: str = "ru",
    ) -> str:
        """Generate a complete procedure for filling template.

        Args:
            document: Parsed MXL document
            procedure_name: Name for the procedure
            parameter_name: Name for the data parameter
            language: Code language (ru/en)

        Returns:
            Complete procedure code
        """
        options = FillCodeGenerationOptions(
            language=language,
            data_variable=parameter_name,
            generate_comments=True,
        )

        result = self.generate(document, options)

        # Build procedure
        lines: list[str] = []

        if language == "ru":
            lines.append(f"Процедура {procedure_name}({parameter_name}) Экспорт")
        else:
            lines.append(f"Procedure {procedure_name}({parameter_name}) Export")

        # Indent procedure body
        for line in result.code.split("\n"):
            if line.strip():
                lines.append(f"\t{line}")
            else:
                lines.append("")

        if language == "ru":
            lines.append("КонецПроцедуры")
        else:
            lines.append("EndProcedure")

        return "\n".join(lines)
