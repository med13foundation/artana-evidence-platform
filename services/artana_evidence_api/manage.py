"""Service-local database operations for the standalone graph-harness service."""

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
from artana_evidence_api.db_schema import resolve_harness_db_schema
from artana_evidence_api.phase1_compare import (
    Phase1CompareRequest,
    build_phase1_source_preferences,
    format_phase1_comparison_json,
    run_phase1_comparison_sync,
)
from psycopg2 import OperationalError
from sqlalchemy.engine.url import URL, make_url

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SERVICE_ROOT = Path(__file__).resolve().parent
_ALEMBIC_CONFIG = _SERVICE_ROOT / "alembic.ini"


def _harness_database_url() -> str:
    return os.getenv(
        "ARTANA_EVIDENCE_API_DATABASE_URL",
        os.getenv("DATABASE_URL", ""),
    ).strip()


def _connection_url() -> URL:
    dsn = _harness_database_url()
    if dsn == "":
        msg = "ARTANA_EVIDENCE_API_DATABASE_URL or DATABASE_URL must be set"
        raise SystemExit(msg)
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
            "graph-harness DB operations."
        )
        raise SystemExit(message)

    return {
        "dbname": url.database,
        "user": url.username,
        "password": url.password,
        "host": url.host or "localhost",
        "port": url.port or 5432,
    }


def wait_for_harness_database(*, timeout: int, interval: float) -> None:
    """Wait until the configured harness database accepts Postgres connections."""
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
                    "Graph-harness Postgres database did not become ready within "
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
    msg = "Unable to locate alembic executable for graph-harness migrations"
    raise SystemExit(msg)


def migrate_harness_database(*, revision: str = "heads") -> None:
    """Run Alembic migrations against the configured harness database URL."""
    env = dict(os.environ)
    env["ALEMBIC_DATABASE_URL"] = _harness_database_url()
    env["ARTANA_EVIDENCE_API_DB_SCHEMA"] = resolve_harness_db_schema()
    env["ALEMBIC_ARTANA_EVIDENCE_API_DB_SCHEMA"] = resolve_harness_db_schema()
    subprocess.run(
        [_resolve_alembic_binary(), "-c", str(_ALEMBIC_CONFIG), "upgrade", revision],
        check=True,
        cwd=_SERVICE_ROOT,
        env=env,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m artana_evidence_api.manage",
        description="Graph-harness database operations",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    wait_parser = subparsers.add_parser(
        "wait-db",
        help="Wait for the graph-harness Postgres database to accept connections",
    )
    wait_parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.getenv("ARTANA_EVIDENCE_API_DB_WAIT_TIMEOUT", "60")),
    )
    wait_parser.add_argument(
        "--interval",
        type=float,
        default=float(os.getenv("ARTANA_EVIDENCE_API_DB_WAIT_INTERVAL", "2")),
    )

    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Apply Alembic migrations using ARTANA_EVIDENCE_API_DATABASE_URL",
    )
    migrate_parser.add_argument(
        "--revision",
        type=str,
        default="heads",
    )
    compare_parser = subparsers.add_parser(
        "compare-phase1",
        help="Run research-init and Phase 1 orchestrator in-process and compare outputs",
    )
    compare_parser.add_argument("--objective", type=str, required=True)
    compare_parser.add_argument(
        "--seed-term",
        action="append",
        dest="seed_terms",
        required=True,
        help="Repeat for each seed term",
    )
    compare_parser.add_argument(
        "--title",
        type=str,
        default="Phase 1 side-by-side compare",
    )
    compare_parser.add_argument(
        "--sources",
        type=str,
        default="pubmed",
        help="Comma-separated enabled sources",
    )
    compare_parser.add_argument(
        "--max-depth",
        type=int,
        default=2,
    )
    compare_parser.add_argument(
        "--max-hypotheses",
        type=int,
        default=5,
    )
    compare_parser.add_argument(
        "--pubmed-backend",
        choices=("current", "deterministic", "ncbi"),
        default="current",
        help=(
            "Override ARTANA_PUBMED_SEARCH_BACKEND for the compare run. "
            "Use deterministic to isolate orchestrator parity from live source variability."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch one graph-harness database operation."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "wait-db":
        wait_for_harness_database(timeout=args.timeout, interval=args.interval)
        return 0
    if args.command == "migrate":
        migrate_harness_database(revision=args.revision)
        return 0
    if args.command == "compare-phase1":
        if args.pubmed_backend != "current":
            os.environ["ARTANA_PUBMED_SEARCH_BACKEND"] = args.pubmed_backend
        request = Phase1CompareRequest(
            objective=args.objective.strip(),
            seed_terms=tuple(args.seed_terms),
            title=args.title.strip() or "Phase 1 side-by-side compare",
            sources=build_phase1_source_preferences(
                [
                    source.strip()
                    for source in args.sources.split(",")
                    if source.strip() != ""
                ],
            ),
            max_depth=args.max_depth,
            max_hypotheses=args.max_hypotheses,
        )
        sys.stdout.write(
            format_phase1_comparison_json(run_phase1_comparison_sync(request)) + "\n",
        )
        return 0

    msg = f"Unsupported command: {args.command}"
    raise SystemExit(msg)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
