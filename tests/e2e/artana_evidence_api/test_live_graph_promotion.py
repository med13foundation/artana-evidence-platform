"""Cross-service promotion flow covering Artana Evidence API -> graph service."""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from artana_evidence_api.database import engine as harness_engine
from artana_evidence_api.db_schema import harness_schema_name
from artana_evidence_api.graph_client import GraphTransportBundle, GraphTransportConfig
from artana_evidence_api.graph_integration.context import GraphCallContext
from artana_evidence_api.models.base import Base as HarnessBase
from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.tests.integration.test_runtime_paths import (
    _build_client,
    _build_services,
    _candidate_claim_payload,
)
from artana_evidence_api.tests.support import FakeKernelRuntime, auth_headers
from artana_evidence_db.tests import support as graph_service_support
from artana_evidence_db.tests.support import (
    build_graph_admin_headers,
    build_seeded_space_fixture,
)
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

os.environ["GRAPH_JWT_SECRET"] = graph_service_support._TEST_SECRET  # noqa: SLF001
os.environ["GRAPH_JWT_ISSUER"] = "graph-biomedical"

graph_client = graph_service_support.graph_client


def _drop_and_create_harness_schema() -> None:
    if harness_engine.dialect.name == "sqlite":
        with harness_engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            HarnessBase.metadata.drop_all(bind=connection)
            HarnessBase.metadata.create_all(bind=connection)
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        return
    schema = harness_schema_name()
    with harness_engine.begin() as connection:
        if schema is not None:
            connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        else:
            HarnessBase.metadata.drop_all(bind=connection)
        HarnessBase.metadata.create_all(bind=connection)


def _drop_harness_schema() -> None:
    if harness_engine.dialect.name == "sqlite":
        with harness_engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            HarnessBase.metadata.drop_all(bind=connection)
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        return
    schema = harness_schema_name()
    with harness_engine.begin() as connection:
        if schema is not None:
            connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            return
        HarnessBase.metadata.drop_all(bind=connection)


@pytest.fixture
def db_session() -> Generator[Session]:
    _drop_and_create_harness_schema()
    session_local = sessionmaker(
        bind=harness_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    session = session_local()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        _drop_harness_schema()


def _build_live_graph_gateway(*, graph_client: TestClient) -> GraphTransportBundle:
    return GraphTransportBundle(
        config=GraphTransportConfig(
            base_url="http://testserver",
            default_headers=build_graph_admin_headers(),
        ),
        client=graph_client,
        call_context=GraphCallContext.service(graph_admin=True),
    )


def _create_live_graph_entity(
    *,
    graph_client: TestClient,
    space_id: UUID,
    headers: dict[str, str],
    entity_type: str,
    display_label: str,
    identifiers: dict[str, str],
) -> UUID:
    response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": entity_type,
            "display_label": display_label,
            "identifiers": identifiers,
            "metadata": {"source": "live-graph-promotion-test"},
        },
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["entity"]["id"])


def test_promote_proposal_persists_claim_through_live_graph_service(
    db_session: Session,
    graph_client: TestClient,
) -> None:
    runtime = FakeKernelRuntime()
    services = _build_services(session=db_session, runtime=runtime)
    live_graph_gateway = _build_live_graph_gateway(graph_client=graph_client)
    client = _build_client(
        session=db_session,
        runtime=runtime,
        services=services,
        graph_api_gateway_override=lambda: live_graph_gateway,
    )
    graph_space_fixture = build_seeded_space_fixture(slug_prefix="live-promotion")
    space_id = UUID(str(graph_space_fixture["space_id"]))
    graph_headers = build_graph_admin_headers()
    source_entity_id = _create_live_graph_entity(
        graph_client=graph_client,
        space_id=space_id,
        headers=graph_headers,
        entity_type="GENE",
        display_label="MED13",
        identifiers={"hgnc_id": f"HGNC:{uuid4().hex[:8]}"},
    )
    target_entity_id = _create_live_graph_entity(
        graph_client=graph_client,
        space_id=space_id,
        headers=graph_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
        identifiers={"hpo_id": f"HP:{uuid4().int % 10_000_000:07d}"},
    )
    source_run = services.run_registry.create_run(
        space_id=str(space_id),
        harness_id="hypotheses",
        title="Live Graph Promotion Source",
        input_payload={"seed_entity_ids": [str(source_entity_id)]},
        graph_service_status="ok",
        graph_service_version="live-graph-test",
    )
    services.artifact_store.seed_for_run(run=source_run)
    proposal = services.proposal_store.create_proposals(
        space_id=str(space_id),
        run_id=source_run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="integration_test",
                source_key=f"{source_entity_id}:ASSOCIATED_WITH:{target_entity_id}",
                title="Promote live MED13 phenotype claim",
                summary="Synthetic live graph promotion evidence.",
                confidence=0.91,
                ranking_score=0.98,
                reasoning_path={
                    "reasoning": (
                        "MED13 is associated with developmental delay in the live "
                        "graph test."
                    ),
                },
                evidence_bundle=[
                    {"source_type": "db", "locator": str(source_entity_id)},
                ],
                payload=_candidate_claim_payload(
                    source_entity_id=str(source_entity_id),
                    target_entity_id=str(target_entity_id),
                    relation_type="ASSOCIATED_WITH",
                ),
                metadata={"agent_run_id": "integration-live-graph-promotion"},
            ),
        ),
    )[0]

    response = client.post(
        f"/v1/spaces/{space_id}/proposals/{proposal.id}/promote",
        headers=auth_headers(),
        json={"reason": "Integration live graph promotion"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "promoted"
    graph_relation_id = payload["metadata"].get("graph_relation_id")
    graph_claim_id = payload["metadata"].get("graph_claim_id")
    assert isinstance(graph_relation_id, str)
    assert graph_relation_id != ""
    assert payload["metadata"]["graph_claim_status"] == "RESOLVED"
    assert payload["metadata"]["graph_claim_validation_state"] == "ALLOWED"
    assert payload["metadata"]["graph_claim_persistability"] == "PERSISTABLE"

    workspace = services.artifact_store.get_workspace(
        space_id=str(space_id),
        run_id=source_run.id,
    )
    assert workspace is not None
    assert workspace.snapshot["last_promoted_graph_claim_id"] == graph_claim_id
    assert workspace.snapshot["last_promoted_graph_relation_id"] == graph_relation_id

    # The promotion created a RESOLVED claim AND materialized a canonical relation.
    # Verify the claim exists and is properly linked.
    claims = live_graph_gateway.list_claims(space_id=space_id)
    assert claims.total == 1
    persisted_claim = claims.claims[0]
    assert str(persisted_claim.research_space_id) == str(space_id)
    assert persisted_claim.relation_type == "ASSOCIATED_WITH"
    assert persisted_claim.validation_state == "ALLOWED"
    assert persisted_claim.persistability == "PERSISTABLE"
    assert persisted_claim.claim_status == "RESOLVED"
    assert persisted_claim.source_label == "MED13"
    assert persisted_claim.target_label == "Developmental delay"
    assert persisted_claim.source_document_ref == f"harness_proposal:{proposal.id}"

    participants = live_graph_gateway.list_claim_participants(
        space_id=space_id,
        claim_id=str(persisted_claim.id),
    )
    assert participants.total == 2
    participant_entity_ids = {
        participant.role: str(participant.entity_id)
        for participant in participants.participants
    }
    assert participant_entity_ids == {
        "SUBJECT": str(source_entity_id),
        "OBJECT": str(target_entity_id),
    }

    evidence = live_graph_gateway.list_claim_evidence(
        space_id=space_id,
        claim_id=str(persisted_claim.id),
    )
    assert evidence.total == 1
    persisted_evidence = evidence.evidence[0]
    assert persisted_evidence.source_document_ref == f"harness_proposal:{proposal.id}"
    assert persisted_evidence.metadata["origin"] == "manual_relation_api"
