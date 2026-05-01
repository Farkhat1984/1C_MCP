# PostgreSQL backend (skeleton)

The MCP-1C storage layer ships two implementations of the
`StorageBundle` protocol:

- **SQLite** (default) — three local DB files per workspace. Handles
  tens of workspaces comfortably; the metadata and graph stores are
  fast and the vector store uses `sqlite-vec`.
- **PostgreSQL + pgvector** (opt-in, **skeleton today**) — a single
  multi-tenant cluster keyed by `workspace_id`. Built for the day the
  team needs more than ~100 workspaces, or wants to share a vector
  index across services.

If you don't have an actual scaling problem, **stay on SQLite**. The
PG path adds a network hop, ops surface, and migration discipline that
small deployments don't need.

## Why is this called a skeleton?

Two layers exist:

| Layer | Status |
|-------|--------|
| Schema (Alembic baseline) | **Real** |
| Connection lifecycle (`open()` / `close()`, asyncpg pool) | **Real** |
| Per-method query implementations | **Stubs** — raise `NotImplementedError("...skeleton...")` |

The split is deliberate. Operators can validate a DSN, pgvector
install, and migration apply *today*; the queries follow when there's
a real workload behind them. That ordering avoids landing speculative
SQL that nobody will execute for six months.

## Bringing up PostgreSQL with pgvector

Any Postgres 14+ with the `vector` extension works. The simplest
local setup is the official `pgvector/pgvector` Docker image:

```bash
docker run -d --name mcp-1c-pg \
    -e POSTGRES_PASSWORD=devpass \
    -e POSTGRES_DB=mcp_1c \
    -p 5432:5432 \
    pgvector/pgvector:pg16
```

For details on enabling pgvector on a managed Postgres (RDS, Cloud
SQL, Neon, Supabase), see the [pgvector
docs](https://github.com/pgvector/pgvector#installation).

## Configuration

Two environment variables drive everything:

```bash
# DSN for asyncpg AND alembic. Required.
export MCP_PG_DSN=postgres://user:pass@host:5432/mcp_1c

# Vector dimension locked at table-create time. Default 4096
# (DeepInfra Qwen3-Embedding-8B). Match this to your embedding model.
export MCP_PG_EMBEDDING_DIM=4096
```

The DSN is **never** baked into `alembic.ini` or any source file —
`migrations/env.py` reads it from the environment so the same repo
can target dev, staging, and prod without edits.

## Install + apply the baseline

```bash
pip install -e ".[postgres]"      # asyncpg, pgvector, alembic
alembic upgrade head              # creates the four tables + HNSW index
```

The baseline (`migrations/versions/0001_baseline.py`) creates:

- `metadata_objects` — keyed by `(workspace_id, full_name)`.
- `vectors` — `vector(N)` column with an HNSW cosine index.
- `graph_nodes`, `graph_edges` — keyed by `(workspace_id, ...)`.
- `CREATE EXTENSION IF NOT EXISTS vector` runs first.

## Wiring it into a workspace

```python
from mcp_1c.engines.storage.postgres import postgres_bundle_factory
from mcp_1c.engines.workspace import WorkspaceRegistry

registry = WorkspaceRegistry(
    storage_factory=postgres_bundle_factory(
        dsn=os.environ["MCP_PG_DSN"],
        embedding_dimension=4096,
    ),
)
```

This is shape-compatible with `sqlite_bundle_factory()`. Today every
storage method raises `NotImplementedError` — you'll see the message
`"Postgres backend skeleton — fill in for production scale; SQLite
covers current needs."` when an engine tries to use the PG bundle.

## Running the integration tests

```bash
export MCP_PG_DSN=postgres://user:pass@host:5432/mcp_1c_test
pytest tests/integration/test_postgres_skeleton.py -m postgres
```

These verify the pool lifecycle and the `NotImplementedError`
messages. Without `MCP_PG_DSN`, they skip cleanly.

## What to do when you hit the SQLite ceiling

1. Open `src/mcp_1c/engines/storage/postgres.py`.
2. Replace the `NotImplementedError` bodies with real asyncpg queries.
3. Keep the method signatures — they're locked to the
   `MetadataStorage` / `VectorStorage` / `GraphStorage` Protocols. If
   you change them, mypy will tell you *and* every other backend will
   need to follow.
4. Add a non-skeleton integration suite that exercises the real
   queries against a temp database.
