#!/usr/bin/env python3
"""
Full data preparation pipeline for 1C MCP Server.

Usage:
    python scripts/run_pipeline.py <config_path> [--skip-embeddings] [--verbose]

Stages:
    1. Metadata indexing
    2. Knowledge Graph building
    3. Embeddings indexing (requires MCP_EMBEDDING_API_KEY)
    4. Pipeline verification
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# Ensure project root is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from mcp_1c.config import EmbeddingConfig, get_config
from mcp_1c.engines.code.engine import CodeEngine
from mcp_1c.engines.embeddings.engine import EmbeddingEngine
from mcp_1c.engines.knowledge_graph.engine import KnowledgeGraphEngine
from mcp_1c.engines.metadata.engine import MetadataEngine
from mcp_1c.engines.platform.engine import PlatformEngine
from mcp_1c.utils.logger import get_logger

logger = get_logger("pipeline")

# Stage timing helper
_stage_times: dict[str, float] = {}


def _log_stage(name: str, detail: str = "") -> None:
    """Log a pipeline stage header."""
    msg = f"=== Stage: {name} ==="
    if detail:
        msg += f"  ({detail})"
    logger.info(msg)
    print(f"\n{'='*60}")
    print(f"  {name}")
    if detail:
        print(f"  {detail}")
    print(f"{'='*60}")


def _log_stats(label: str, stats: dict) -> None:
    """Pretty-print statistics dict."""
    print(f"\n  {label}:")
    for key, value in stats.items():
        print(f"    {key}: {value}")


async def stage_metadata(config_path: Path) -> MetadataEngine:
    """Stage 1: Index metadata from 1C configuration."""
    _log_stage("1. Metadata Indexing", str(config_path))
    t0 = time.monotonic()

    engine = MetadataEngine.get_instance()
    progress = await engine.initialize(config_path, watch=False)

    stats = await engine.get_stats()
    _log_stats("Objects indexed by type", stats)

    total = sum(stats.values())
    print(f"\n  Total objects indexed: {total}")

    _stage_times["metadata"] = time.monotonic() - t0
    return engine


async def stage_knowledge_graph(
    metadata_engine: MetadataEngine,
) -> KnowledgeGraphEngine:
    """Stage 2: Build Knowledge Graph from metadata relationships."""
    _log_stage("2. Knowledge Graph Building")
    t0 = time.monotonic()

    kg_engine = KnowledgeGraphEngine.get_instance()
    graph = await kg_engine.build(metadata_engine)

    graph_stats = graph.stats()
    _log_stats("Graph statistics", graph_stats)

    _stage_times["knowledge_graph"] = time.monotonic() - t0
    return kg_engine


async def _embedding_progress(info: dict[str, int | str]) -> None:
    """Print embedding progress inline with percentage."""
    total = int(info.get("total", 0))
    processed = int(info.get("processed", 0))
    pct = (processed / total * 100) if total > 0 else 0
    stage = info.get("stage", "?")
    indexed = info.get("indexed", 0)
    skipped = info.get("skipped", 0)
    print(
        f"\r  [{stage}] {processed}/{total} ({pct:.1f}%) "
        f"indexed={indexed} skipped={skipped}",
        end="",
        flush=True,
    )


async def stage_embeddings(
    metadata_engine: MetadataEngine,
    skip: bool = False,
    force_reindex: bool = False,
) -> EmbeddingEngine | None:
    """Stage 3: Index embeddings for semantic search."""
    api_key = os.environ.get("MCP_EMBEDDING_API_KEY", "") or os.environ.get("DEEPINFRA_API_KEY", "")

    if skip:
        print("\n  [SKIPPED] --skip-embeddings flag set")
        return None

    if not api_key:
        print("\n  [SKIPPED] MCP_EMBEDDING_API_KEY not set")
        return None

    mode = "force reindex" if force_reindex else "resume"
    _log_stage("3. Embeddings Indexing", f"mode={mode}")
    t0 = time.monotonic()

    config = EmbeddingConfig.from_env()
    emb_engine = EmbeddingEngine.get_instance()
    db_path = Path(".mcp_1c_embeddings.db")
    await emb_engine.initialize(config, db_path)

    code_engine = CodeEngine.get_instance()

    module_stats = await emb_engine.index_modules(
        metadata_engine, code_engine,
        progress_cb=_embedding_progress,
        force_reindex=force_reindex,
    )
    print()  # newline after progress line
    _log_stats("Module indexing", module_stats)

    proc_stats = await emb_engine.index_procedures(
        metadata_engine, code_engine,
        progress_cb=_embedding_progress,
        force_reindex=force_reindex,
    )
    print()  # newline after progress line
    _log_stats("Procedure indexing", proc_stats)

    meta_stats = await emb_engine.index_metadata_descriptions(
        metadata_engine,
        progress_cb=_embedding_progress,
        force_reindex=force_reindex,
    )
    print()  # newline after progress line
    _log_stats("Metadata description indexing", meta_stats)

    _stage_times["embeddings"] = time.monotonic() - t0
    return emb_engine


async def stage_verification(
    metadata_engine: MetadataEngine,
    kg_engine: KnowledgeGraphEngine,
    emb_engine: EmbeddingEngine | None,
) -> bool:
    """Stage 4: Verify pipeline results."""
    _log_stage("4. Pipeline Verification")
    t0 = time.monotonic()

    checks_passed = 0
    checks_failed = 0

    # Check 1: All metadata objects have graph nodes
    graph_stats = await kg_engine.get_stats()
    meta_stats = await metadata_engine.get_stats()
    total_meta = sum(meta_stats.values())
    total_nodes = graph_stats["total_nodes"]

    if total_nodes >= total_meta:
        print(f"  [PASS] Graph nodes ({total_nodes}) >= metadata objects ({total_meta})")
        checks_passed += 1
    else:
        print(f"  [FAIL] Graph nodes ({total_nodes}) < metadata objects ({total_meta})")
        checks_failed += 1

    # Check 2: Graph has edges
    if graph_stats["total_edges"] > 0:
        print(f"  [PASS] Graph has {graph_stats['total_edges']} edges")
        checks_passed += 1
    else:
        print("  [FAIL] Graph has no edges")
        checks_failed += 1

    # Check 3: Metadata search works
    results = await metadata_engine.search("Товар")
    if results:
        print(f"  [PASS] Metadata search for 'Товар' returned {len(results)} results")
        checks_passed += 1
    else:
        print("  [FAIL] Metadata search for 'Товар' returned no results")
        checks_failed += 1

    # Check 4: Embedding search (if available)
    if emb_engine is not None:
        try:
            emb_results = await emb_engine.search("получить цену товара", limit=5)
            if emb_results:
                print(
                    f"  [PASS] Embedding search returned {len(emb_results)} results"
                )
                checks_passed += 1
            else:
                print("  [FAIL] Embedding search returned no results")
                checks_failed += 1
        except Exception as exc:
            print(f"  [FAIL] Embedding search error: {exc}")
            checks_failed += 1

    _stage_times["verification"] = time.monotonic() - t0

    print(f"\n  Verification: {checks_passed} passed, {checks_failed} failed")
    return checks_failed == 0


def print_summary() -> None:
    """Print final timing summary."""
    print(f"\n{'='*60}")
    print("  Pipeline Summary")
    print(f"{'='*60}")
    total = 0.0
    for stage, elapsed in _stage_times.items():
        print(f"  {stage:.<30} {elapsed:.2f}s")
        total += elapsed
    print(f"  {'TOTAL':.<30} {total:.2f}s")
    print(f"{'='*60}\n")


async def run_pipeline(
    config_path: Path,
    skip_embeddings: bool = False,
    force_reindex: bool = False,
) -> bool:
    """Run the full data preparation pipeline.

    Args:
        config_path: Path to 1C configuration root.
        skip_embeddings: Whether to skip the embeddings stage.
        force_reindex: Whether to force re-embedding of all documents.

    Returns:
        True if all verification checks passed.
    """
    metadata_engine = await stage_metadata(config_path)
    kg_engine = await stage_knowledge_graph(metadata_engine)
    emb_engine = await stage_embeddings(
        metadata_engine, skip=skip_embeddings, force_reindex=force_reindex
    )
    success = await stage_verification(metadata_engine, kg_engine, emb_engine)

    print_summary()

    # Cleanup
    if emb_engine is not None:
        await emb_engine.close()
        EmbeddingEngine._instance = None

    await metadata_engine.shutdown()
    MetadataEngine._instance = None
    KnowledgeGraphEngine._instance = None
    CodeEngine._instance = None

    return success


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Full data preparation pipeline for 1C MCP Server.",
    )
    parser.add_argument(
        "config_path",
        type=Path,
        help="Path to 1C configuration root directory",
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Skip the embeddings indexing stage",
    )
    parser.add_argument(
        "--force-reindex",
        action="store_true",
        help="Force re-embedding of all documents (ignore checkpoint/resume)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point for the pipeline script."""
    args = parse_args()

    if args.verbose:
        import logging

        logging.basicConfig(level=logging.DEBUG)

    config_path = args.config_path.resolve()
    if not config_path.is_dir():
        print(f"Error: Configuration path does not exist: {config_path}")
        sys.exit(1)

    if not (config_path / "Configuration.xml").exists():
        print(f"Error: Configuration.xml not found at {config_path}")
        sys.exit(1)

    # Update global config cache db_path to a sensible location
    app_config = get_config()
    app_config.cache.db_path = config_path.parent / ".mcp_1c_cache.db"

    try:
        success = asyncio.run(
            run_pipeline(
                config_path,
                skip_embeddings=args.skip_embeddings,
                force_reindex=args.force_reindex,
            )
        )
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nPipeline interrupted by user.")
        sys.exit(130)
    except Exception as exc:
        print(f"\nPipeline failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
