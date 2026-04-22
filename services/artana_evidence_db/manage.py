"""Service-local database operations for the standalone graph API service."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import TypedDict

import psycopg2  # type: ignore[import-untyped]
from artana_evidence_db.schema_support import resolve_graph_db_schema
from psycopg2 import OperationalError
from sqlalchemy.engine.url import URL, make_url

from .config import _require_env

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SERVICE_ROOT = Path(__file__).resolve().parent
_ALEMBIC_CONFIG = _SERVICE_ROOT / "alembic.ini"


def _graph_database_url() -> str:
    return _require_env("GRAPH_DATABASE_URL")


def _connection_url() -> URL:
    dsn = _graph_database_url()
    return make_url(dsn)


class _PostgresConnectionKwargs(TypedDict):
    dbname: str | None
    user: str | None
    password: str | None
    host: str
    port: int


def _connection_kwargs() -> _PostgresConnectionKwargs:
    url = _connection_url()
    if not url.drivername.startswith("postgresql"):
        message = (
            f"Unsupported driver '{url.drivername}'. Expected a Postgres DSN for "
            "graph-service DB operations."
        )
        raise SystemExit(message)

    return {
        "dbname": url.database,
        "user": url.username,
        "password": url.password,
        "host": url.host or "localhost",
        "port": url.port or 5432,
    }


def wait_for_graph_database(*, timeout: int, interval: float) -> None:
    """Wait until the configured graph database accepts Postgres connections."""
    deadline = time.monotonic() + timeout
    conn_kwargs = _connection_kwargs()

    while True:
        try:
            with psycopg2.connect(
                dbname=conn_kwargs["dbname"],
                user=conn_kwargs["user"],
                password=conn_kwargs["password"],
                host=conn_kwargs["host"],
                port=conn_kwargs["port"],
            ):
                return
        except OperationalError as exc:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                message = (
                    f"Graph Postgres database did not become ready within "
                    f"{timeout} seconds: {exc}"
                )
                raise SystemExit(message) from exc
            time.sleep(interval)


def _resolve_alembic_binary() -> str:
    candidate_paths = [
        Path(sys.executable).resolve().parent / "alembic",
        _REPO_ROOT / ".venv" / "bin" / "alembic",
        _REPO_ROOT / "venv" / "bin" / "alembic",
    ]
    for candidate_path in candidate_paths:
        if candidate_path.exists():
            return str(candidate_path)
    resolved = shutil.which("alembic")
    if resolved is not None:
        return resolved
    msg = "Unable to locate alembic executable for graph-service migrations"
    raise SystemExit(msg)


def migrate_graph_database(*, revision: str = "heads") -> None:
    """Run Alembic migrations against the configured graph database URL."""
    env = dict(os.environ)
    env["ALEMBIC_DATABASE_URL"] = _graph_database_url()
    env["GRAPH_DB_SCHEMA"] = resolve_graph_db_schema()
    env["ALEMBIC_GRAPH_DB_SCHEMA"] = resolve_graph_db_schema()
    subprocess.run(  # noqa: S603 - fixed internal migration command
        [_resolve_alembic_binary(), "-c", str(_ALEMBIC_CONFIG), "upgrade", revision],
        check=True,
        cwd=_SERVICE_ROOT,
        env=env,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m artana_evidence_db.manage",
        description="Graph-service database operations",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    wait_parser = subparsers.add_parser(
        "wait-db",
        help="Wait for the graph Postgres database to accept connections",
    )
    wait_parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.getenv("GRAPH_DB_WAIT_TIMEOUT", "60")),
    )
    wait_parser.add_argument(
        "--interval",
        type=float,
        default=float(os.getenv("GRAPH_DB_WAIT_INTERVAL", "2")),
    )

    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Apply Alembic migrations using GRAPH_DATABASE_URL",
    )
    migrate_parser.add_argument(
        "--revision",
        type=str,
        default="heads",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch one graph-service database operation."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "wait-db":
        wait_for_graph_database(timeout=args.timeout, interval=args.interval)
        return 0
    if args.command == "migrate":
        migrate_graph_database(revision=args.revision)
        return 0

    msg = f"Unsupported command: {args.command}"
    raise SystemExit(msg)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
