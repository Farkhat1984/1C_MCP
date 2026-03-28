"""
Embeddings Engine.

Provides semantic search over 1C configuration code and metadata
using vector embeddings from DeepInfra API.
"""

from mcp_1c.engines.embeddings.chunking import (
    chunk_module_text,
    chunk_procedure_text,
    make_chunk_id,
    prepare_metadata_text,
)
from mcp_1c.engines.embeddings.client import EmbeddingClient
from mcp_1c.engines.embeddings.engine import EmbeddingEngine
from mcp_1c.engines.embeddings.storage import VectorStorage

__all__ = [
    "EmbeddingClient",
    "EmbeddingEngine",
    "VectorStorage",
    "chunk_module_text",
    "chunk_procedure_text",
    "make_chunk_id",
    "prepare_metadata_text",
]
