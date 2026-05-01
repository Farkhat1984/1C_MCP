"""Alembic environment for the MCP-1C Postgres backend (skeleton).

Reads the DSN from ``MCP_PG_DSN`` at runtime — never from
``alembic.ini``. This keeps secrets out of the repo and lets ops point
the same migrations at dev / staging / prod.

Online mode only. We don't ship offline (SQL-script) migrations because
the schema uses pgvector's ``vector`` type, which is not portable to
plain SQL targets.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Alembic Config object — provides access to the values within the
# .ini file in use.
config = context.config

# Set up Python logging from the .ini if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _resolve_dsn() -> str:
    """Pull the DSN from ``MCP_PG_DSN``; fail loudly if it's missing.

    We refuse to fall back to a default — running migrations against an
    unintended database is the kind of mistake that costs an evening,
    so we make the operator name the target explicitly.
    """

    dsn = os.environ.get("MCP_PG_DSN")
    if not dsn:
        raise RuntimeError(
            "MCP_PG_DSN is not set. Export the target Postgres DSN "
            "before running alembic, e.g.:\n"
            "    export MCP_PG_DSN=postgres://user:pass@host:5432/mcp_1c"
        )
    return dsn


# We don't define SQLAlchemy MetaData here because the schema is pure
# raw-SQL DDL inside the migration file (pgvector types aren't
# first-class in plain SQLAlchemy without the ``pgvector`` package's
# adapter). Alembic still works fine with ``target_metadata=None``;
# autogenerate is just disabled.
target_metadata = None


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against the resolved DSN."""

    dsn = _resolve_dsn()
    cfg_section = config.get_section(config.config_ini_section) or {}
    cfg_section["sqlalchemy.url"] = dsn

    connectable = engine_from_config(
        cfg_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Compare types so ``vector(N)`` migrations are picked up
            # correctly if/when we ever wire autogenerate.
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError(
        "Offline migrations are not supported — the schema uses "
        "pgvector's vector type. Run with a live DSN instead."
    )
run_migrations_online()
