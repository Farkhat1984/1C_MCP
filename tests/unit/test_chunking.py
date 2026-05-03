"""Regression tests for embedding chunking.

The most important property is *termination* — these helpers run on
hundreds of thousands of procedures during bulk indexing, and a single
infinite loop stalls the whole pipeline.
"""

from mcp_1c.engines.embeddings.chunking import (
    _sliding_window_chunks,
    chunk_procedure_text,
)


def test_sliding_window_terminates_when_overlap_exceeds_chunk_size() -> None:
    """If overlap >= chunk_size, the window must still advance.

    Used to spin forever: _find_line_break could return a position <=
    start, so end == start, the chunk was empty, next_start fell back
    to end == start, and the loop never moved.
    """
    text = "first line\n" + ("x" * 1000)
    chunks = _sliding_window_chunks(text, chunk_size=100, overlap=300)
    # Should produce a finite, reasonable number of chunks
    assert 1 <= len(chunks) <= 50
    # Every chunk must have non-zero offset progress
    offsets = [c[1] for c in chunks]
    assert offsets == sorted(offsets)
    assert len(set(offsets)) == len(offsets)


def test_sliding_window_terminates_with_only_early_newline() -> None:
    """A newline at position 50 followed by 1000 chars without \\n.

    Causes _find_line_break to return 51 every iteration once start
    reaches 51 (the newline is always inside the lookback window).
    """
    text = ("a" * 50) + "\n" + ("b" * 2000)
    chunks = _sliding_window_chunks(text, chunk_size=100, overlap=300)
    assert len(chunks) < 100  # finite
    # Must cover the full text
    assert chunks[-1][1] + len(chunks[-1][0]) >= len(text) - 10


def test_sliding_window_normal_case() -> None:
    text = "\n".join([f"line {i}" * 20 for i in range(50)])
    chunks = _sliding_window_chunks(text, chunk_size=200, overlap=50)
    assert len(chunks) >= 2
    assert all(len(c[0]) <= 200 + 200 for c in chunks)  # +lookback budget


def test_chunk_procedure_text_terminates_with_huge_header() -> None:
    """When header consumes most of the budget, body_budget collapses
    to 100 and overlap_chars (300) > body_budget. Must not hang."""
    huge_name = "X" * 2000
    huge_comment = "Y" * 2000
    body = ("z" * 50) + "\n" + ("z" * 5000)

    chunks = chunk_procedure_text(
        obj_full_name=huge_name,
        proc_name="Test",
        is_function=False,
        is_export=False,
        directive="",
        proc_comment=huge_comment,
        body=body,
        signature="Процедура Test()",
        max_chunk_chars=4000,
        overlap_chars=300,
    )
    assert 1 <= len(chunks) <= 200
