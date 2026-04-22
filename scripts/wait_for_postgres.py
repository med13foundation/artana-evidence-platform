"""
Utility script for waiting until the Postgres dev instance is ready to accept connections.

It connects using ALEMBIC_DATABASE_URL (or DATABASE_URL as a fallback) so it works
with the same credentials Alembic uses. Intended to be executed via `make postgres-wait`,
which sources .env.postgres before running this script.
"""

from __future__ import annotations

import os
import time
from typing import Final

import psycopg2
from psycopg2 import OperationalError
from sqlalchemy.engine.url import URL, make_url

DEFAULT_TIMEOUT_SECONDS: Final[int] = int(os.getenv("POSTGRES_WAIT_TIMEOUT", "60"))
DEFAULT_INTERVAL_SECONDS: Final[float] = float(os.getenv("POSTGRES_WAIT_INTERVAL", "2"))

# Error messages
_MISSING_DB_VARS_MSG = (
    "Missing ALEMBIC_DATABASE_URL/DATABASE_URL environment variables."
)


def _connection_url() -> URL:
    dsn = (
        os.getenv("ALEMBIC_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("ASYNC_DATABASE_URL")
    )
    if not dsn:
        raise SystemExit(_MISSING_DB_VARS_MSG)
    return make_url(dsn)


def _connection_kwargs() -> dict[str, object]:
    url = _connection_url()
    if not url.drivername.startswith("postgresql"):
        driver_msg = f"Unsupported driver '{url.drivername}'. Expected a Postgres DSN."
        raise SystemExit(driver_msg)

    return {
        "dbname": url.database,
        "user": url.username,
        "password": url.password,
        "host": url.host or "localhost",
        "port": url.port or 5432,
    }


def wait_for_postgres(timeout: int = DEFAULT_TIMEOUT_SECONDS) -> None:
    deadline = time.monotonic() + timeout
    interval = DEFAULT_INTERVAL_SECONDS
    conn_kwargs = _connection_kwargs()
    attempt = 1

    while True:
        try:
            with psycopg2.connect(**conn_kwargs):
                # Connection successful
                return
        except OperationalError as exc:  # pragma: no cover - simple polling loop
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timeout_msg = (
                    f"Postgres did not become ready within {timeout} seconds: {exc}"
                )
                raise SystemExit(timeout_msg) from exc
            # Continue polling
            time.sleep(interval)
            attempt += 1


if __name__ == "__main__":
    wait_for_postgres()
