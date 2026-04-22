"""
Artana database configuration helpers.

Provides PostgreSQL connection configuration for Artana state backend,
using a dedicated "artana" schema to isolate orchestration state from
application data.
"""

from __future__ import annotations

import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.database.url_resolver import resolve_sync_database_url


def resolve_artana_state_uri() -> str:
    """
    Resolve the Artana state backend URI.

    Priority:
    1. ARTANA_STATE_URI environment variable (explicit override)
    2. Derive from DATABASE_URL with artana schema

    Returns:
        PostgreSQL connection string configured for the artana schema.
    """
    explicit_uri = os.getenv("ARTANA_STATE_URI")
    if explicit_uri:
        return explicit_uri

    base_url = resolve_sync_database_url()
    if not base_url.startswith("postgresql"):
        msg = (
            "Artana state backend requires a PostgreSQL DATABASE_URL/ARTANA_STATE_URI. "
            f"Resolved URL: {base_url}"
        )
        raise RuntimeError(msg)

    normalized_url = _normalize_postgres_dsn(base_url)
    return _add_artana_schema(normalized_url)


def _normalize_postgres_dsn(database_url: str) -> str:
    """Ensure asyncpg-compatible DSN (strip SQLAlchemy driver suffixes)."""
    replacements = (
        ("postgresql+psycopg2://", "postgresql://"),
        ("postgresql+psycopg://", "postgresql://"),
        ("postgresql+asyncpg://", "postgresql://"),
    )
    for prefix, replacement in replacements:
        if database_url.startswith(prefix):
            return database_url.replace(prefix, replacement, 1)
    return database_url


def _add_artana_schema(postgres_url: str) -> str:
    """Add artana schema to PostgreSQL connection string."""
    split = urlsplit(postgres_url)
    query_items = parse_qsl(split.query, keep_blank_values=True)

    existing_options = [value for key, value in query_items if key == "options"]
    if existing_options:
        new_options = f"{existing_options[0]} -c search_path=artana,public"
        query_items = [(key, value) for key, value in query_items if key != "options"]
        query_items.append(("options", new_options))
    else:
        query_items.append(("options", "-c search_path=artana,public"))

    rebuilt_query = urlencode(query_items, doseq=True)
    return urlunsplit(
        (
            split.scheme,
            split.netloc,
            split.path,
            rebuilt_query,
            split.fragment,
        ),
    )
