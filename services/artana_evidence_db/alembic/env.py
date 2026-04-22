import os
from logging.config import fileConfig

from alembic import context
from artana_evidence_db.database_url import resolve_sync_database_url
from artana_evidence_db.orm_base import Base
from artana_evidence_db.schema_support import (
    graph_postgres_search_path,
    graph_schema_name,
)
from sqlalchemy import engine_from_config, pool, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

# Import our models for autogenerate support

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Allow DATABASE_URL/ALEMBIC_DATABASE_URL to override default
database_url = os.getenv("ALEMBIC_DATABASE_URL") or resolve_sync_database_url()
config.set_main_option("sqlalchemy.url", database_url)
if database_url.startswith("sqlite:"):
    os.environ["GRAPH_DB_SCHEMA"] = "public"
    os.environ["ALEMBIC_GRAPH_DB_SCHEMA"] = "public"

# Import models only after the SQLite schema override is in place so table
# metadata is built without a non-SQLite schema prefix.
import artana_evidence_db.ai_full_mode_persistence_models  # noqa: E402, F401
import artana_evidence_db.claim_relation_persistence_model  # noqa: E402, F401
import artana_evidence_db.entity_embedding_model  # noqa: E402, F401
import artana_evidence_db.entity_embedding_status_model  # noqa: E402, F401
import artana_evidence_db.entity_lookup_models  # noqa: E402, F401
import artana_evidence_db.kernel_claim_models  # noqa: E402, F401
import artana_evidence_db.kernel_concept_models  # noqa: E402, F401
import artana_evidence_db.kernel_dictionary_models  # noqa: E402, F401
import artana_evidence_db.kernel_entity_models  # noqa: E402, F401
import artana_evidence_db.kernel_relation_models  # noqa: E402, F401
import artana_evidence_db.observation_persistence_model  # noqa: E402, F401
import artana_evidence_db.operation_run_models  # noqa: E402, F401
import artana_evidence_db.pack_seed_models  # noqa: E402, F401
import artana_evidence_db.provenance_model  # noqa: E402, F401
import artana_evidence_db.read_models  # noqa: E402, F401
import artana_evidence_db.reasoning_path_persistence_models  # noqa: E402, F401
import artana_evidence_db.source_document_model  # noqa: E402, F401
import artana_evidence_db.space_models  # noqa: E402, F401
import artana_evidence_db.workflow_persistence_models  # noqa: E402, F401

graph_db_schema = graph_schema_name(
    os.getenv("ALEMBIC_GRAPH_DB_SCHEMA") or os.getenv("GRAPH_DB_SCHEMA"),
)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type: JSONB, _compiler: object, **_kw: object) -> str:
    """Allow PostgreSQL JSONB columns to compile as JSON on SQLite."""
    return "JSON"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=graph_db_schema is not None,
        version_table="alembic_version_graph_api",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        if connection.dialect.name == "postgresql" and graph_db_schema is not None:
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{graph_db_schema}"'))
            connection.execute(
                text(
                    f"SET search_path TO {graph_postgres_search_path(graph_db_schema)}",
                ),
            )
            # SQLAlchemy 2 keeps these DDL/search_path statements in an implicit
            # transaction until the connection is committed explicitly.
            if connection.in_transaction():
                connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=graph_db_schema is not None,
            version_table="alembic_version_graph_api",
        )

        with context.begin_transaction():
            context.run_migrations()
        if connection.in_transaction():
            connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
