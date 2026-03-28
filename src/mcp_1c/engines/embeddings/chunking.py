"""
Chunking utilities for embedding text preparation.

Splits long 1C BSL code and metadata into sized chunks with context headers,
preserving line boundaries where possible.
"""

from __future__ import annotations


def _find_line_break(text: str, pos: int, lookback: int = 200) -> int:
    """Find the nearest line break before pos, within lookback range.

    Args:
        text: The text to scan.
        pos: Target position.
        lookback: Maximum characters to scan backward.

    Returns:
        Position of the character after the newline, or pos if none found.
    """
    search_start = max(0, pos - lookback)
    idx = text.rfind("\n", search_start, pos)
    if idx == -1:
        return pos
    return idx + 1


def _sliding_window_chunks(
    text: str,
    chunk_size: int,
    overlap: int,
) -> list[tuple[str, int, int]]:
    """Split text into overlapping chunks, preferring line boundaries.

    Args:
        text: Source text to split.
        chunk_size: Maximum characters per chunk.
        overlap: Number of overlapping characters between consecutive chunks.

    Returns:
        List of (chunk_text, start_offset, chunk_index) tuples.
    """
    if not text or chunk_size <= 0:
        return [("", 0, 0)]

    chunks: list[tuple[str, int, int]] = []
    start = 0
    idx = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        # Prefer line-break boundary (unless we're at the very end)
        if end < len(text):
            end = _find_line_break(text, end)

        chunks.append((text[start:end], start, idx))
        idx += 1

        if end >= len(text):
            break

        # Move start forward, leaving overlap
        next_start = end - overlap
        if next_start <= start:
            next_start = end  # Avoid infinite loop
        start = next_start

    return chunks


def chunk_procedure_text(
    obj_full_name: str,
    proc_name: str,
    is_function: bool,
    is_export: bool,
    directive: str,
    proc_comment: str,
    body: str,
    signature: str,
    max_chunk_chars: int = 4000,
    overlap_chars: int = 300,
) -> list[tuple[str, dict[str, str]]]:
    """Chunk a procedure/function for embedding with a context header.

    Args:
        obj_full_name: Full object name (e.g., 'Catalog.Nomenclature').
        proc_name: Procedure/function name.
        is_function: True if function, False if procedure.
        is_export: True if exported.
        directive: Compilation directive.
        proc_comment: Documentation comment.
        body: Procedure body text.
        signature: Procedure signature line.
        max_chunk_chars: Maximum characters per chunk.
        overlap_chars: Overlap between consecutive chunks.

    Returns:
        List of (text, extra_metadata) tuples. extra_metadata contains
        chunk_index and chunk_total as strings.
    """
    header_parts = [
        f"Объект: {obj_full_name}",
        f"{'Функция' if is_function else 'Процедура'}: {proc_name}",
        f"Экспортная: {'да' if is_export else 'нет'}",
    ]
    if directive:
        header_parts.append(f"Директива: {directive}")
    if proc_comment:
        header_parts.append(f"Описание: {proc_comment}")

    header = "\n".join(header_parts) + "\n"
    content = body if body else signature

    # Single chunk if it fits
    if len(header) + len(content) <= max_chunk_chars:
        return [(header + content, {"chunk_index": "0", "chunk_total": "1"})]

    # Sliding window on body
    body_budget = max_chunk_chars - len(header) - len("[...продолжение]\n")
    if body_budget < 100:
        body_budget = 100  # Minimum viable chunk

    raw_chunks = _sliding_window_chunks(content, body_budget, overlap_chars)
    total = len(raw_chunks)

    result: list[tuple[str, dict[str, str]]] = []
    for chunk_text, _offset, chunk_idx in raw_chunks:
        text = (
            header + chunk_text
            if chunk_idx == 0
            else header + "[...продолжение]\n" + chunk_text
        )
        result.append((
            text,
            {"chunk_index": str(chunk_idx), "chunk_total": str(total)},
        ))

    return result


def chunk_module_text(
    obj_full_name: str,
    synonym: str,
    comment: str,
    module_type: str,
    content: str,
    chunk_size: int = 2000,
    overlap: int = 300,
) -> list[tuple[str, dict[str, str]]]:
    """Chunk a BSL module for embedding with a context header.

    Args:
        obj_full_name: Full object name.
        synonym: Object display name.
        comment: Object comment.
        module_type: Module type (e.g., 'ObjectModule').
        content: Module source code.
        chunk_size: Maximum characters per chunk.
        overlap: Overlap between consecutive chunks.

    Returns:
        List of (text, extra_metadata) tuples.
    """
    header_parts = [f"Объект: {obj_full_name}"]
    if synonym:
        header_parts.append(f"Синоним: {synonym}")
    header_parts.append(f"Тип модуля: {module_type}")
    if comment:
        header_parts.append(f"Комментарий: {comment}")

    header = "\n".join(header_parts) + "\n"

    # Single chunk if it fits
    if len(header) + len(content) <= chunk_size:
        return [(header + content, {"chunk_index": "0", "chunk_total": "1"})]

    body_budget = chunk_size - len(header)
    if body_budget < 100:
        body_budget = 100

    raw_chunks = _sliding_window_chunks(content, body_budget, overlap)
    total = len(raw_chunks)

    result: list[tuple[str, dict[str, str]]] = []
    for chunk_text, _offset, chunk_idx in raw_chunks:
        result.append((
            header + chunk_text,
            {"chunk_index": str(chunk_idx), "chunk_total": str(total)},
        ))

    return result


def make_chunk_id(base_id: str, chunk_index: int, chunk_total: int) -> str:
    """Create a chunk-aware document ID.

    Args:
        base_id: Base document identifier.
        chunk_index: Zero-based chunk index.
        chunk_total: Total number of chunks.

    Returns:
        base_id unchanged for single chunks, or '{base_id}.chunk_{index}' for multi-chunks.
    """
    if chunk_total == 1:
        return base_id
    return f"{base_id}.chunk_{chunk_index}"


def prepare_metadata_text(
    obj_full_name: str,
    synonym: str,
    comment: str,
    attributes: list[str],
    tabular_sections: list[str],
) -> str:
    """Create text representation of a metadata object for embedding.

    Args:
        obj_full_name: Full object name.
        synonym: Display name.
        comment: Object comment.
        attributes: List of attribute names.
        tabular_sections: List of tabular section names.

    Returns:
        Formatted text for embedding.
    """
    parts = [f"Объект: {obj_full_name}"]
    if synonym:
        parts.append(f"Синоним: {synonym}")
    if comment:
        parts.append(f"Комментарий: {comment}")
    if attributes:
        parts.append(f"Реквизиты: {', '.join(attributes)}")
    if tabular_sections:
        parts.append(f"Табличные части: {', '.join(tabular_sections)}")
    return "\n".join(parts)
