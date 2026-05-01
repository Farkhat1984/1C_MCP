"""
Domain models for the 1C Data Composition System (DataCompositionSchema, СКД).

A 1C report stores a DataCompositionSchema in
``Reports/<Report>/Templates/<Template>.xml`` (or `MainSchema.xml`).
The schema describes:
- one or more DataSets (queries / objects / unions),
- fields available downstream,
- parameters,
- resources / calculated fields,
- one or more SchemaSettings (variants of the report layout).

These models are the structured representation produced by
``engines/composition/parser.py``.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class DataSetKind(str, Enum):
    QUERY = "Query"
    OBJECT = "Object"
    UNION = "Union"
    UNKNOWN = "Unknown"


class CompositionField(BaseModel):
    """One projected field of a data set or schema."""

    name: str = Field(..., description="Internal field name (DataPath)")
    title: str = Field(default="", description="Synonym shown in the UI")
    type: str = Field(default="")
    role: str = Field(default="", description="Mapping role: dimension/resource/period/...")
    expression: str = Field(default="", description="Expression for calculated fields")


class CompositionParameter(BaseModel):
    """User-supplied or runtime parameter of the schema."""

    name: str
    title: str = Field(default="")
    type: str = Field(default="")
    available_for_user: bool = True
    default_value: str = Field(default="")


class CompositionResource(BaseModel):
    """Aggregated resource (sum/average/count/...)."""

    field: str = Field(..., description="Field name being aggregated")
    expression: str = Field(default="", description="Aggregation expression")
    title: str = Field(default="")


class CompositionDataSet(BaseModel):
    """One data set inside the schema."""

    name: str
    kind: DataSetKind = DataSetKind.UNKNOWN
    query_text: str = Field(default="", description="Query text for Query data sets")
    fields: list[CompositionField] = Field(default_factory=list)

    model_config = ConfigDict(use_enum_values=False)


class CompositionSettings(BaseModel):
    """One variant (preset) of the schema's layout settings."""

    name: str = Field(default="Default")
    title: str = Field(default="")
    selection: list[str] = Field(default_factory=list, description="Selected fields")
    filters: list[dict[str, str]] = Field(default_factory=list)
    order: list[str] = Field(default_factory=list)
    structure: list[str] = Field(
        default_factory=list,
        description="High-level structure description (groups, tables, charts)",
    )


class DataCompositionSchema(BaseModel):
    """Parsed structure of a single DataCompositionSchema XML."""

    object_type: str = Field(..., description="Owner metadata type, normally 'Report'")
    object_name: str
    schema_name: str = Field(default="MainSchema")
    schema_path: Path
    title: str = Field(default="")
    data_sets: list[CompositionDataSet] = Field(default_factory=list)
    parameters: list[CompositionParameter] = Field(default_factory=list)
    resources: list[CompositionResource] = Field(default_factory=list)
    fields: list[CompositionField] = Field(
        default_factory=list,
        description="Top-level fields aggregated across data sets",
    )
    settings: list[CompositionSettings] = Field(default_factory=list)

    @property
    def full_name(self) -> str:
        return f"{self.object_type}.{self.object_name}.{self.schema_name}"
