"""Run pytest against an isolated ephemeral Postgres database.

When local Postgres mode is active (via `.postgres-active`), running tests
directly against `ARTANA_POSTGRES_DB` risks mutating developer data and can leave
the database in a drifted state if a test is destructive.

This helper creates a fresh temporary database, runs Alembic migrations, runs
pytest, and then drops the database.

Usage (typically via Makefile):
    python scripts/run_isolated_postgres_tests.py -m "not performance"
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPH_ALEMBIC_CONFIG = REPO_ROOT / "services" / "artana_evidence_db" / "alembic.ini"
_METADATA_BOOTSTRAP_TEMPLATE = """
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

repo_root = Path(os.environ["ARTANA_REPOSITORY_ROOT"]).resolve()
for path in (repo_root, repo_root / "services"):
    resolved = str(path)
    if resolved not in sys.path:
        sys.path.insert(0, resolved)

import artana_evidence_api.models.harness  # noqa: F401
from artana_evidence_api.db_schema import harness_schema_name
from artana_evidence_api.models import Base as HarnessBase
import artana_evidence_db.claim_relation_persistence_model  # noqa: F401
import artana_evidence_db.entity_embedding_model  # noqa: F401
import artana_evidence_db.entity_lookup_models  # noqa: F401
import artana_evidence_db.kernel_claim_models  # noqa: F401
import artana_evidence_db.kernel_concept_models  # noqa: F401
import artana_evidence_db.kernel_dictionary_models  # noqa: F401
import artana_evidence_db.kernel_entity_models  # noqa: F401
import artana_evidence_db.kernel_relation_models  # noqa: F401
import artana_evidence_db.observation_persistence_model  # noqa: F401
import artana_evidence_db.operation_run_models  # noqa: F401
import artana_evidence_db.provenance_model  # noqa: F401
import artana_evidence_db.read_models  # noqa: F401
import artana_evidence_db.reasoning_path_persistence_models  # noqa: F401
import artana_evidence_db.relation_projection_source_model  # noqa: F401
import artana_evidence_db.source_document_model  # noqa: F401
import artana_evidence_db.space_models  # noqa: F401
from artana_evidence_db.orm_base import Base as GraphServiceBase
from artana_evidence_db.schema_support import graph_schema_name

engine = create_engine(os.environ["DATABASE_URL"], future=True)
try:
    with engine.begin() as connection:
        schema = harness_schema_name(os.getenv("ARTANA_EVIDENCE_API_DB_SCHEMA"))
        if schema is not None:
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{graph_schema_name()}"'))
        connection.execute(text('CREATE SCHEMA IF NOT EXISTS "artana"'))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public"))
    HarnessBase.metadata.create_all(bind=engine, checkfirst=True)
    GraphServiceBase.metadata.create_all(bind=engine, checkfirst=True)
finally:
    engine.dispose()
""".strip()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def to_async_database_url(database_url: str) -> str:
    """Convert a sync PostgreSQL URL into the asyncpg form used by tests."""
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql+psycopg2://"):
        return database_url.replace(
            "postgresql+psycopg2://",
            "postgresql+asyncpg://",
            1,
        )
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url


@dataclass(frozen=True)
class PostgresUrls:
    """Connection strings used for test orchestration."""

    sync_url: str
    async_url: str
    alembic_url: str


def _log_progress(message: str) -> None:
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f">> [{timestamp}] {message}", flush=True)


def _quote_ident(identifier: str) -> str:
    # Double-quote escaping per SQL spec.
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def _require_postgres_sync_url(url: str) -> None:
    if not url.startswith("postgresql"):
        msg = (
            "DATABASE_URL must be PostgreSQL; this script only supports Postgres mode."
        )
        raise SystemExit(msg)


def _build_urls_for_database(base_sync_url: str, database_name: str) -> PostgresUrls:
    parsed = make_url(base_sync_url)
    # Use render_as_string to avoid SQLAlchemy's default password masking in `str(url)`.
    sync_url = parsed.set(database=database_name).render_as_string(hide_password=False)
    async_url = to_async_database_url(sync_url)
    return PostgresUrls(
        sync_url=sync_url,
        async_url=async_url,
        alembic_url=sync_url,
    )


def _create_database(admin_sync_url: str, database_name: str) -> None:
    engine = create_engine(admin_sync_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text(f"CREATE DATABASE {_quote_ident(database_name)}"))
    finally:
        engine.dispose()


def _drop_database(admin_sync_url: str, database_name: str) -> None:
    engine = create_engine(admin_sync_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            # Ensure no pooled connections prevent the DROP.
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :db_name AND pid <> pg_backend_pid()",
                ),
                {"db_name": database_name},
            )
            conn.execute(text(f"DROP DATABASE IF EXISTS {_quote_ident(database_name)}"))
    finally:
        engine.dispose()


def _resolve_alembic_binary() -> str:
    candidate_bins = (
        Path(sys.executable).resolve().parent / "alembic",
        REPO_ROOT / ".venv" / "bin" / "alembic",
        REPO_ROOT / "venv" / "bin" / "alembic",
    )
    for bin_path in candidate_bins:
        if bin_path.exists():
            return str(bin_path)
    return "alembic"


def _run_alembic_migrations(env: dict[str, str]) -> None:
    subprocess.run(  # noqa: S603
        [
            _resolve_alembic_binary(),
            "-c",
            str(GRAPH_ALEMBIC_CONFIG),
            "upgrade",
            "heads",
        ],
        check=True,
        env=env,
    )


def _bootstrap_repository_metadata(env: dict[str, str]) -> None:
    subprocess.run(  # noqa: S603
        [sys.executable, "-c", _METADATA_BOOTSTRAP_TEMPLATE],
        check=True,
        cwd=REPO_ROOT,
        env=env,
    )


def _run_pytest(pytest_args: list[str], env: dict[str, str]) -> int:
    runner_module = os.environ.get("ARTANA_TEST_RUNNER", "pytest")
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", runner_module, *pytest_args],
        check=False,
        env=env,
    )
    return result.returncode


def _generate_database_name() -> str:
    # PostgreSQL identifier length limit is 63 bytes. Keep it short and stable.
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    suffix = uuid4().hex[:10]
    return f"artana_test_{stamp}_{suffix}"[:63]


def main(argv: list[str]) -> int:
    base_sync_url = os.environ.get("DATABASE_URL", "")
    if not base_sync_url:
        msg = "DATABASE_URL is required"
        raise SystemExit(msg)
    _require_postgres_sync_url(base_sync_url)

    # Connect to the base database to create/drop the ephemeral one. This avoids
    # assuming the maintenance DB name ('postgres') exists in all environments.
    admin_sync_url = base_sync_url

    test_db_name = _generate_database_name()
    urls = _build_urls_for_database(base_sync_url, test_db_name)

    # Propagate all env vars, overriding only DB URLs for the test subprocesses.
    child_env = dict(os.environ)
    child_env["DATABASE_URL"] = urls.sync_url
    child_env["ASYNC_DATABASE_URL"] = urls.async_url
    child_env["ALEMBIC_DATABASE_URL"] = urls.alembic_url
    child_env["ARTANA_REPOSITORY_ROOT"] = str(REPO_ROOT)
    child_env["PYTHONUNBUFFERED"] = "1"

    _log_progress(f"Creating ephemeral test database: {test_db_name}")
    _create_database(admin_sync_url, test_db_name)
    _log_progress(f"Created ephemeral test database: {test_db_name}")

    try:
        _log_progress("Applying Alembic migrations...")
        _run_alembic_migrations(child_env)
        _log_progress("Finished Alembic migrations.")
        _log_progress("Bootstrapping SQLAlchemy metadata...")
        _bootstrap_repository_metadata(child_env)
        _log_progress("Finished SQLAlchemy metadata bootstrap.")

        _log_progress("Running pytest...")
        return _run_pytest(argv, child_env)
    finally:
        _log_progress(f"Dropping ephemeral test database: {test_db_name}")
        _drop_database(admin_sync_url, test_db_name)
        _log_progress(f"Dropped ephemeral test database: {test_db_name}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
