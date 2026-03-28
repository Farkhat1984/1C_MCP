"""
Embedding domain models.

Represents documents and search results for semantic search
over 1C configuration code and metadata.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EmbeddingDocument(BaseModel):
    """A document with its embedding vector."""

    id: str = Field(..., description="Unique identifier (e.g., 'Catalog.Nomenclature.ObjectModule')")
    content: str = Field(..., description="The text that was embedded")
    doc_type: str = Field(
        ...,
        description="Document type: 'module', 'procedure', 'metadata_description', 'comment'",
    )
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Extra info (object_name, module_type, etc.)",
    )
    embedding: list[float] = Field(
        default_factory=list,
        description="The embedding vector",
    )


class SearchResult(BaseModel):
    """A search result with similarity score."""

    document: EmbeddingDocument = Field(..., description="The matched document")
    score: float = Field(..., description="Cosine similarity score (0.0 to 1.0)")


class EmbeddingStats(BaseModel):
    """Statistics about the embedding index."""

    total_documents: int = Field(default=0, description="Total number of indexed documents")
    by_type: dict[str, int] = Field(
        default_factory=dict,
        description="Document count by type",
    )
    dimension: int = Field(default=0, description="Embedding vector dimension")
    index_size_bytes: int = Field(default=0, description="Approximate storage size in bytes")
