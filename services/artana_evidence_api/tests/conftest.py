"""Service-local pytest fixtures for standalone artana-evidence-api tests."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

_TEST_DB_PATH = (
    Path(__file__).resolve().parent
    / f"artana_evidence_api_service_tests_{os.getpid()}.db"
)
_TEST_DATABASE_URL = f"sqlite:///{_TEST_DB_PATH}"
_TEST_SECRET = "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz"
_ACTIVE_DATABASE_URL = os.environ.get("DATABASE_URL", "")
_USE_POSTGRES = os.environ.get(
    "ARTANA_EVIDENCE_API_TEST_USE_POSTGRES",
    "0",
) == "1" and _ACTIVE_DATABASE_URL.startswith("postgresql")

os.environ.setdefault("TESTING", "true")
if _USE_POSTGRES:
    os.environ.setdefault("ARTANA_EVIDENCE_API_DATABASE_URL", _ACTIVE_DATABASE_URL)
    os.environ.setdefault("ARTANA_EVIDENCE_API_DB_SCHEMA", "artana_evidence_api")
    os.environ.setdefault("GRAPH_DB_SCHEMA", "graph_runtime")
else:
    os.environ.setdefault("DATABASE_URL", _TEST_DATABASE_URL)
    os.environ.setdefault("ARTANA_EVIDENCE_API_DATABASE_URL", _TEST_DATABASE_URL)
    os.environ["ARTANA_EVIDENCE_API_DB_SCHEMA"] = "public"
    os.environ.setdefault("GRAPH_DB_SCHEMA", "public")
os.environ.setdefault("AUTH_JWT_SECRET", _TEST_SECRET)
os.environ.setdefault("GRAPH_JWT_SECRET", _TEST_SECRET)
os.environ.setdefault("GRAPH_SERVICE_RELOAD", "0")
os.environ.setdefault("ARTANA_EVIDENCE_API_SERVICE_RELOAD", "0")

import artana_evidence_api.models.api_key  # noqa: E402, F401
import artana_evidence_api.models.discovery  # noqa: E402, F401
import artana_evidence_api.models.harness  # noqa: E402, F401
import artana_evidence_api.models.research_space  # noqa: E402, F401
import artana_evidence_api.models.user  # noqa: E402, F401
import pytest  # noqa: E402
from artana_evidence_api.database import engine  # noqa: E402
from artana_evidence_api.models.base import Base  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.dialects.postgresql import UUID  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402


@compiles(UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):  # noqa: ANN001, ANN202
    del type_, compiler, kw
    return "VARCHAR(36)"


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    if engine.dialect.name != "sqlite":
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _drop_and_create_schema() -> None:
    if engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            Base.metadata.drop_all(bind=connection)
            Base.metadata.create_all(bind=connection)
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        return
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _drop_schema() -> None:
    if engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            Base.metadata.drop_all(bind=connection)
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        return
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session() -> Generator[Session]:
    """Provide an isolated session for service-local integration tests."""
    _drop_and_create_schema()
    session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    session = session_local()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        _drop_schema()
