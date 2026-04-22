"""Shared test support for standalone graph-service flows."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

_TEST_DB_PATH = (
    Path(__file__).resolve().parent
    / f"artana_evidence_db_support_tests_{os.getpid()}.db"
)
_TEST_DATABASE_URL = f"sqlite:///{_TEST_DB_PATH}"
_TEST_SECRET = "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz"

os.environ.setdefault("TESTING", "true")
os.environ.setdefault("DATABASE_URL", _TEST_DATABASE_URL)
os.environ.setdefault("GRAPH_DATABASE_URL", _TEST_DATABASE_URL)
os.environ.setdefault("GRAPH_DB_SCHEMA", "public")
os.environ.setdefault("AUTH_JWT_SECRET", _TEST_SECRET)
os.environ.setdefault("GRAPH_JWT_SECRET", _TEST_SECRET)
os.environ.setdefault("GRAPH_SERVICE_RELOAD", "0")

import artana_evidence_db.claim_relation_persistence_model  # noqa: E402, F401
import artana_evidence_db.entity_embedding_model  # noqa: F401
import artana_evidence_db.entity_embedding_status_model  # noqa: F401
import artana_evidence_db.entity_lookup_models  # noqa: F401
import artana_evidence_db.kernel_claim_models  # noqa: F401
import artana_evidence_db.kernel_concept_models  # noqa: F401
import artana_evidence_db.kernel_dictionary_models  # noqa: F401
import artana_evidence_db.kernel_entity_models  # noqa: F401
import artana_evidence_db.kernel_relation_models  # noqa: F401
import artana_evidence_db.observation_persistence_model  # noqa: F401
import artana_evidence_db.operation_run_models  # noqa: F401
import artana_evidence_db.pack_seed_models  # noqa: F401
import artana_evidence_db.provenance_model  # noqa: F401
import artana_evidence_db.read_models  # noqa: F401
import artana_evidence_db.reasoning_path_persistence_models  # noqa: F401
import artana_evidence_db.relation_projection_source_model  # noqa: E402, F401
import artana_evidence_db.source_document_model  # noqa: E402, F401
import artana_evidence_db.space_models  # noqa: F401
import pytest
import sqlalchemy as sa
from artana_evidence_db import database as graph_database
from artana_evidence_db.app import create_app
from artana_evidence_db.orm_base import Base
from artana_evidence_db.space_models import GraphSpaceModel, GraphSpaceStatusEnum
from artana_evidence_db.tests.local_support import (
    reset_database,
    seed_entity_resolution_policies,
    seed_relation_constraints,
)
from artana_evidence_db.user_models import UserRole
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def build_graph_auth_headers(
    *,
    user_id: UUID,
    email: str,
    role: UserRole = UserRole.RESEARCHER,
    graph_admin: bool = False,
    graph_ai_principal: str | None = None,
    graph_service_capabilities: tuple[str, ...] | list[str] | None = None,
) -> dict[str, str]:
    headers = {
        "X-TEST-USER-ID": str(user_id),
        "X-TEST-USER-EMAIL": email,
        "X-TEST-USER-ROLE": role.value,
        "X-TEST-GRAPH-ADMIN": "true" if graph_admin else "false",
    }
    if graph_ai_principal is not None:
        headers["X-TEST-GRAPH-AI-PRINCIPAL"] = graph_ai_principal
    if graph_service_capabilities:
        headers["X-TEST-GRAPH-SERVICE-CAPABILITIES"] = ",".join(
            capability.strip()
            for capability in graph_service_capabilities
            if capability.strip()
        )
    return headers


def auth_headers(
    *,
    user_id: UUID,
    email: str,
    role: UserRole = UserRole.RESEARCHER,
    graph_admin: bool = False,
    graph_ai_principal: str | None = None,
    graph_service_capabilities: tuple[str, ...] | list[str] | None = None,
) -> dict[str, str]:
    return build_graph_auth_headers(
        user_id=user_id,
        email=email,
        role=role,
        graph_admin=graph_admin,
        graph_ai_principal=graph_ai_principal,
        graph_service_capabilities=graph_service_capabilities,
    )


def build_graph_admin_headers() -> dict[str, str]:
    return build_graph_auth_headers(
        user_id=uuid4(),
        email=f"graph-admin-{uuid4().hex[:12]}@example.com",
        role=UserRole.VIEWER,
        graph_admin=True,
    )


def admin_headers() -> dict[str, str]:
    return build_graph_admin_headers()


def _graph_runtime_metadata() -> sa.MetaData:
    metadata = Base.metadata
    runtime_metadata = sa.MetaData(naming_convention=metadata.naming_convention)
    excluded_tables = {
        "source_documents",
        "reasoning_paths",
        "reasoning_path_steps",
        "entity_mechanism_paths",
    }
    for table in metadata.tables.values():
        if table.name in excluded_tables:
            continue
        table.to_metadata(runtime_metadata)
    return runtime_metadata


def reset_graph_service_database() -> None:
    reset_database(graph_database.engine, _graph_runtime_metadata())


def seed_graph_service_dictionary_primitives() -> None:
    with graph_database.SessionLocal() as session:
        seed_entity_resolution_policies(session)
        seed_relation_constraints(session)
        session.commit()


def seed_graph_space(
    session: Session,
    *,
    owner_id: UUID,
    space_id: UUID,
    slug: str,
    name: str,
    description: str,
) -> None:
    session.add(
        GraphSpaceModel(
            id=space_id,
            slug=slug,
            name=name,
            description=description,
            owner_id=owner_id,
            status=GraphSpaceStatusEnum.ACTIVE,
            settings={},
        ),
    )
    seed_entity_resolution_policies(session)
    seed_relation_constraints(session)


def build_seeded_space_fixture(
    *,
    slug_prefix: str = "graph-space",
) -> dict[str, object]:
    suffix = uuid4().hex[:8]
    owner_id = uuid4()
    space_id = uuid4()
    with graph_database.SessionLocal() as session:
        seed_graph_space(
            session,
            owner_id=owner_id,
            space_id=space_id,
            slug=f"{slug_prefix}-{suffix}",
            name="Graph Service Test Space",
            description="Standalone graph-service deterministic-resolution test space",
        )
        session.commit()
    return {
        "owner_id": owner_id,
        "space_id": space_id,
        "headers": auth_headers(
            user_id=owner_id,
            email=f"graph-owner-{suffix}@example.org",
        ),
    }


@pytest.fixture
def graph_client() -> TestClient:
    reset_graph_service_database()
    with TestClient(create_app()) as client:
        yield client
    reset_graph_service_database()


__all__ = [
    "admin_headers",
    "auth_headers",
    "build_graph_admin_headers",
    "build_graph_auth_headers",
    "build_seeded_space_fixture",
    "graph_client",
    "reset_graph_service_database",
    "seed_graph_service_dictionary_primitives",
    "seed_graph_space",
]
