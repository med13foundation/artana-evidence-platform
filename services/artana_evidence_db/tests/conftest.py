"""Service-local pytest fixtures for standalone artana-evidence-db tests."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

_TEST_DB_PATH = (
    Path(__file__).resolve().parent
    / f"artana_evidence_db_service_tests_{os.getpid()}.db"
)
_TEST_DATABASE_URL = f"sqlite:///{_TEST_DB_PATH}"
_TEST_ASYNC_DATABASE_URL = f"sqlite+aiosqlite:///{_TEST_DB_PATH}"
_TEST_SECRET = "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz"

os.environ.setdefault("TESTING", "true")
os.environ.setdefault("DATABASE_URL", _TEST_DATABASE_URL)
os.environ.setdefault("ASYNC_DATABASE_URL", _TEST_ASYNC_DATABASE_URL)
os.environ.setdefault("GRAPH_DATABASE_URL", _TEST_DATABASE_URL)
os.environ.setdefault("GRAPH_DB_SCHEMA", "public")
os.environ.setdefault("AUTH_JWT_SECRET", _TEST_SECRET)
os.environ.setdefault("GRAPH_JWT_SECRET", _TEST_SECRET)
os.environ.setdefault("GRAPH_SERVICE_RELOAD", "0")

import artana_evidence_db.ai_full_mode_persistence_models  # noqa: E402, F401
import artana_evidence_db.claim_relation_persistence_model  # noqa: E402, F401
import artana_evidence_db.entity_embedding_model  # noqa: E402, F401
import artana_evidence_db.entity_embedding_status_model  # noqa: E402, F401
import artana_evidence_db.entity_lookup_models  # noqa: E402, F401
import artana_evidence_db.kernel_claim_models  # noqa: E402, F401
import artana_evidence_db.kernel_concept_models  # noqa: E402, F401
import artana_evidence_db.kernel_dictionary_models  # noqa: E402, F401
import artana_evidence_db.kernel_entity_models  # noqa: E402, F401
import artana_evidence_db.kernel_relation_models  # noqa: E402, F401
import artana_evidence_db.observation_persistence_model  # noqa: E402, F401
import artana_evidence_db.operation_run_models  # noqa: E402, F401
import artana_evidence_db.pack_seed_models  # noqa: E402, F401
import artana_evidence_db.provenance_model  # noqa: E402, F401
import artana_evidence_db.read_models  # noqa: E402, F401
import artana_evidence_db.reasoning_path_persistence_models  # noqa: E402, F401
import artana_evidence_db.relation_projection_source_model  # noqa: E402, F401
import artana_evidence_db.source_document_model  # noqa: E402, F401
import artana_evidence_db.space_models  # noqa: E402, F401
import artana_evidence_db.workflow_persistence_models  # noqa: E402, F401
import pytest  # noqa: E402
from artana_evidence_db.database import engine  # noqa: E402
from artana_evidence_db.orm_base import Base  # noqa: E402
from artana_evidence_db.tests.local_support import reset_database  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB, UUID  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):  # noqa: ANN001, ANN202
    del type_, compiler, kw
    return "JSON"


@compiles(UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):  # noqa: ANN001, ANN202
    del type_, compiler, kw
    return "VARCHAR(36)"


@pytest.fixture
def db_session() -> Generator[Session]:
    """Provide a clean SQLite-backed session for service-local persistence tests."""
    reset_database(engine, Base.metadata)
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
        reset_database(engine, Base.metadata)
