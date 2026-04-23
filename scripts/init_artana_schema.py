#!/usr/bin/env python3
"""Initialize the Artana runtime schema in PostgreSQL."""

from __future__ import annotations

import os

from sqlalchemy import create_engine, text


def _database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url
    msg = "DATABASE_URL is required to initialize the artana schema"
    raise SystemExit(msg)


def init_artana_schema() -> None:
    """Create the artana schema used by the runtime state backend."""
    engine = create_engine(_database_url())
    try:
        with engine.begin() as connection:
            connection.execute(text('CREATE SCHEMA IF NOT EXISTS "artana"'))
            result = connection.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name = 'artana'",
                ),
            )
            if result.fetchone() is None:
                msg = "Failed to verify artana schema creation"
                raise SystemExit(msg)
    finally:
        engine.dispose()

    print("Schema 'artana' created or already exists.")


if __name__ == "__main__":
    init_artana_schema()
