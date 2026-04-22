"""Schema helpers for graph-owned runtime and migrations."""

from __future__ import annotations

import os
import re

_DEFAULT_GRAPH_DB_SCHEMA = "public"
_SCHEMA_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def resolve_graph_db_schema(raw_value: str | None = None) -> str:
    """Resolve the configured graph database schema name."""
    candidate = raw_value if raw_value is not None else os.getenv("GRAPH_DB_SCHEMA")
    normalized = (candidate or _DEFAULT_GRAPH_DB_SCHEMA).strip()
    if normalized == "":
        normalized = _DEFAULT_GRAPH_DB_SCHEMA
    if not _SCHEMA_NAME_PATTERN.fullmatch(normalized):
        message = (
            "GRAPH_DB_SCHEMA must be a valid SQL identifier "
            "(letters, digits, underscores; cannot start with a digit)"
        )
        raise ValueError(message)
    return normalized


def is_default_graph_db_schema(raw_value: str | None = None) -> bool:
    """Return whether the graph DB schema resolves to the shared public schema."""
    return resolve_graph_db_schema(raw_value) == _DEFAULT_GRAPH_DB_SCHEMA


def graph_schema_name(raw_value: str | None = None) -> str | None:
    """Return the graph schema name, or ``None`` when using the default schema."""
    schema = resolve_graph_db_schema(raw_value)
    if schema == _DEFAULT_GRAPH_DB_SCHEMA:
        return None
    return schema


def qualify_graph_table_name(
    table_name: str,
    *,
    schema: str | None = None,
) -> str:
    """Return a schema-qualified table name when the graph schema is non-default."""
    resolved_schema = resolve_graph_db_schema(schema)
    if resolved_schema == _DEFAULT_GRAPH_DB_SCHEMA:
        return table_name
    return f"{resolved_schema}.{table_name}"


def qualify_graph_foreign_key_target(
    target: str,
    *,
    schema: str | None = None,
) -> str:
    """Return a schema-qualified ``table.column`` foreign-key target."""
    table_name, _, column_name = target.partition(".")
    if not column_name:
        return qualify_graph_table_name(table_name, schema=schema)
    return f"{qualify_graph_table_name(table_name, schema=schema)}.{column_name}"


def graph_table_options(*, comment: str) -> dict[str, str]:
    """Build shared table options for graph-owned standalone-service tables."""
    options: dict[str, str] = {"comment": comment}
    schema = graph_schema_name()
    if schema is not None:
        options["schema"] = schema
    return options


def graph_postgres_search_path(raw_value: str | None = None) -> str:
    """Return the PostgreSQL ``search_path`` for graph-service connections."""
    schema = resolve_graph_db_schema(raw_value)
    if schema == _DEFAULT_GRAPH_DB_SCHEMA:
        return _DEFAULT_GRAPH_DB_SCHEMA
    return f'"{schema}", public'


__all__ = [
    "graph_postgres_search_path",
    "graph_schema_name",
    "graph_table_options",
    "is_default_graph_db_schema",
    "qualify_graph_foreign_key_target",
    "qualify_graph_table_name",
    "resolve_graph_db_schema",
]
