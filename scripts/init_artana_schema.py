"""
Initialize the artana schema in PostgreSQL.

This script creates the "artana" schema if it doesn't exist. Artana will
then auto-migrate its tables into this schema on first connection.

Usage:
    python scripts/init_artana_schema.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.database.url_resolver import resolve_sync_database_url


def init_artana_schema() -> None:
    """Create the artana schema if it doesn't exist."""
    db_url = resolve_sync_database_url()

    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS artana"))
            conn.commit()
            print("Schema 'artana' created or already exists.")

            result = conn.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name = 'artana'",
                ),
            )
            if result.fetchone() is None:
                print("Failed to verify schema creation.")
                raise SystemExit(1)
            print("Schema 'artana' verified.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    init_artana_schema()
