"""Alembic environment for artana-evidence-api-owned schema objects."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from artana_evidence_api.db_schema import (
    harness_postgres_search_path,
    harness_schema_name,
    resolve_harness_db_schema,
)
from artana_evidence_api.models import Base
from sqlalchemy import engine_from_config, pool, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

config = context.config

database_url = (
    os.getenv("ALEMBIC_DATABASE_URL")
    or os.getenv("ARTANA_EVIDENCE_API_DATABASE_URL")
    or os.getenv("DATABASE_URL")
    or config.get_main_option("sqlalchemy.url")
)
config.set_main_option("sqlalchemy.url", database_url)
harness_db_schema = harness_schema_name(
    os.getenv("ALEMBIC_ARTANA_EVIDENCE_API_DB_SCHEMA")
    or os.getenv("ARTANA_EVIDENCE_API_DB_SCHEMA"),
)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
_VERSION_TABLE_NAME = "alembic_version_artana_evidence_api"
_MIN_VERSION_NUM_LENGTH = 255


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type: JSONB, _compiler: object, **_kw: object) -> str:
    """Allow PostgreSQL JSONB columns to compile as JSON on SQLite."""
    return "JSON"


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=harness_db_schema is not None,
        version_table=_VERSION_TABLE_NAME,
        version_table_schema=harness_db_schema,
    )

    with context.begin_transaction():
        context.run_migrations()


def _ensure_version_table_capacity(*, connection: object, schema_name: str) -> None:
    """Widen Alembic's version column before long revision ids are written.

    Older harness databases created the Alembic version table with the default
    ``VARCHAR(32)`` width. Newer revision ids are longer than that, which makes
    Alembic fail while updating its own bookkeeping row even though the target
    migration succeeded. We proactively widen the column so historic databases
    can migrate forward normally.
    """
    if not hasattr(connection, "execute"):
        return

    current_length_result = connection.execute(
        text(
            """
            SELECT character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = :schema_name
              AND table_name = :table_name
              AND column_name = 'version_num'
            """,
        ),
        {
            "schema_name": schema_name,
            "table_name": _VERSION_TABLE_NAME,
        },
    )
    current_length = current_length_result.scalar_one_or_none()
    if current_length is None:
        connection.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS "{schema_name}"."{_VERSION_TABLE_NAME}" (
                    version_num VARCHAR({_MIN_VERSION_NUM_LENGTH}) NOT NULL,
                    CONSTRAINT "{_VERSION_TABLE_NAME}_pk" PRIMARY KEY (version_num)
                )
                """,
            ),
        )
        return

    if current_length >= _MIN_VERSION_NUM_LENGTH:
        return

    connection.execute(
        text(
            f"""
            ALTER TABLE "{schema_name}"."{_VERSION_TABLE_NAME}"
            ALTER COLUMN version_num TYPE VARCHAR({_MIN_VERSION_NUM_LENGTH})
            """,
        ),
    )


def _resolve_version_table_schema(
    *,
    connection: object,
    preferred_schema_name: str,
) -> str:
    """Return the schema that currently owns the Alembic version table.

    Older installs may have created the version table in ``public`` before the
    harness schema became explicit. Newer installs should keep it in the harness
    schema. We detect the existing location and continue using it so upgrades do
    not accidentally create a second version table.
    """
    if not hasattr(connection, "execute"):
        return preferred_schema_name

    result = connection.execute(
        text(
            """
            SELECT table_schema
            FROM information_schema.tables
            WHERE table_name = :table_name
              AND table_schema = ANY(current_schemas(true))
            ORDER BY
              CASE
                WHEN table_schema = :preferred_schema THEN 0
                WHEN table_schema = 'public' THEN 1
                ELSE 2
              END,
              table_schema
            LIMIT 1
            """,
        ),
        {
            "table_name": _VERSION_TABLE_NAME,
            "preferred_schema": preferred_schema_name,
        },
    )
    schema_name = result.scalar_one_or_none()
    return (
        schema_name
        if isinstance(schema_name, str) and schema_name != ""
        else preferred_schema_name
    )


def run_migrations_online() -> None:
    """Run migrations in online mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        if connection.dialect.name == "postgresql":
            schema = os.getenv("ALEMBIC_ARTANA_EVIDENCE_API_DB_SCHEMA") or os.getenv(
                "ARTANA_EVIDENCE_API_DB_SCHEMA",
            )
            resolved_schema = resolve_harness_db_schema(schema)
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{resolved_schema}"'))
            connection.execute(
                text(
                    f"SET search_path TO {harness_postgres_search_path(schema)}",
                ),
            )
            version_table_schema = _resolve_version_table_schema(
                connection=connection,
                preferred_schema_name=resolved_schema,
            )
            _ensure_version_table_capacity(
                connection=connection,
                schema_name=version_table_schema,
            )
            # SQLAlchemy 2 keeps these DDL/search_path statements in an implicit
            # transaction until the connection is committed explicitly.
            if connection.in_transaction():
                connection.commit()
        else:
            version_table_schema = harness_db_schema

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=harness_db_schema is not None,
            version_table=_VERSION_TABLE_NAME,
            version_table_schema=version_table_schema,
        )

        with context.begin_transaction():
            context.run_migrations()
        if connection.in_transaction():
            connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
