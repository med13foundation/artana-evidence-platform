"""Schema helpers for artana-evidence-api-owned and shared runtime tables."""

from __future__ import annotations

import os
import re

from sqlalchemy.engine import make_url

_DEFAULT_HARNESS_DB_SCHEMA = "artana_evidence_api"
_DEFAULT_GRAPH_DB_SCHEMA = "graph_runtime"
_SCHEMA_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SHARED_PLATFORM_SCHEMA = "public"


def resolve_harness_db_schema(raw_value: str | None = None) -> str:
    """Resolve the configured harness database schema name."""
    candidate = (
        raw_value
        if raw_value is not None
        else os.getenv("ARTANA_EVIDENCE_API_DB_SCHEMA")
    )
    normalized = (candidate or _DEFAULT_HARNESS_DB_SCHEMA).strip()
    if normalized == "":
        normalized = _DEFAULT_HARNESS_DB_SCHEMA
    if not _SCHEMA_NAME_PATTERN.fullmatch(normalized):
        message = (
            "ARTANA_EVIDENCE_API_DB_SCHEMA must be a valid SQL identifier "
            "(letters, digits, underscores; cannot start with a digit)"
        )
        raise ValueError(message)
    return normalized


def _active_database_url() -> str:
    return os.getenv(
        "ARTANA_EVIDENCE_API_DATABASE_URL",
        os.getenv("DATABASE_URL", ""),
    )


def is_postgres_database_url(raw_value: str | None = None) -> bool:
    """Return ``True`` when the configured runtime database is PostgreSQL."""
    candidate = raw_value if raw_value is not None else _active_database_url()
    if candidate.strip() == "":
        return False
    return make_url(candidate).get_backend_name() == "postgresql"


def harness_schema_name(raw_value: str | None = None) -> str | None:
    """Return the harness schema name, or ``None`` when using the default."""
    schema = resolve_harness_db_schema(raw_value)
    if schema == "public":
        return None
    return schema


def shared_platform_schema_name(database_url: str | None = None) -> str | None:
    """Return the schema for shared platform tables.

    Shared auth/tenancy tables live in ``public`` on PostgreSQL. SQLite tests keep
    those tables schema-less so the in-memory harness remains easy to construct.
    """
    if not is_postgres_database_url(database_url):
        return None
    return _SHARED_PLATFORM_SCHEMA


def harness_postgres_search_path(raw_value: str | None = None) -> str:
    """Return the PostgreSQL ``search_path`` for harness-service connections."""
    schema = resolve_harness_db_schema(raw_value)
    if schema == "public":
        return schema
    return f'"{schema}", public'


def _resolve_runtime_graph_schema(raw_value: str | None = None) -> str:
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


def _runtime_graph_schema_name(raw_value: str | None = None) -> str | None:
    schema = _resolve_runtime_graph_schema(raw_value)
    if schema == "public":
        return None
    return schema


def harness_runtime_postgres_search_path(
    *,
    harness_schema: str | None = None,
    graph_schema: str | None = None,
) -> str:
    """Return the runtime search path for harness sessions that touch graph tables."""
    resolved_harness_schema = resolve_harness_db_schema(harness_schema)
    resolved_graph_schema = _runtime_graph_schema_name(graph_schema)

    ordered_schemas: list[str] = []
    if resolved_harness_schema != "public":
        ordered_schemas.append(resolved_harness_schema)
    if (
        resolved_graph_schema is not None
        and resolved_graph_schema not in ordered_schemas
    ):
        ordered_schemas.append(resolved_graph_schema)
    ordered_schemas.append("public")

    return ", ".join(
        "public" if schema_name == "public" else f'"{schema_name}"'
        for schema_name in ordered_schemas
    )


def qualify_harness_table_name(
    table_name: str,
    *,
    schema: str | None = None,
) -> str:
    """Return a schema-qualified table name when the harness schema is non-public."""
    resolved_schema = resolve_harness_db_schema(schema)
    if resolved_schema == "public":
        return table_name
    return f"{resolved_schema}.{table_name}"


def qualify_harness_foreign_key_target(
    target: str,
    *,
    schema: str | None = None,
) -> str:
    """Return a schema-qualified ``table.column`` foreign-key target."""
    table_name, _, column_name = target.partition(".")
    if not column_name:
        return qualify_harness_table_name(table_name, schema=schema)
    return f"{qualify_harness_table_name(table_name, schema=schema)}.{column_name}"


def qualify_shared_platform_foreign_key_target(
    target: str,
    *,
    database_url: str | None = None,
) -> str:
    """Return a schema-qualified shared-platform ``table.column`` target."""
    schema = shared_platform_schema_name(database_url)
    if schema is None:
        return target
    table_name, _, column_name = target.partition(".")
    qualified_table_name = f"{schema}.{table_name}"
    if column_name == "":
        return qualified_table_name
    return f"{qualified_table_name}.{column_name}"


def harness_table_options(*, comment: str) -> dict[str, str]:
    """Build shared table options for harness-owned tables."""
    options: dict[str, str] = {"comment": comment}
    schema = harness_schema_name()
    if schema is not None:
        options["schema"] = schema
    return options


def shared_platform_table_options(*, comment: str) -> dict[str, object]:
    """Build shared table options for platform-owned tables."""
    options: dict[str, object] = {
        "comment": comment,
        "extend_existing": True,
    }
    schema = shared_platform_schema_name()
    if schema is not None:
        options["schema"] = schema
    return options


__all__ = [
    "harness_postgres_search_path",
    "harness_runtime_postgres_search_path",
    "qualify_harness_foreign_key_target",
    "qualify_shared_platform_foreign_key_target",
    "qualify_harness_table_name",
    "harness_schema_name",
    "harness_table_options",
    "is_postgres_database_url",
    "resolve_harness_db_schema",
    "shared_platform_schema_name",
    "shared_platform_table_options",
]
