"""Cross-service promotion flow covering Artana Evidence API -> graph service."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Generator
from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from artana_evidence_api.database import engine as harness_engine
from artana_evidence_api.db_schema import harness_schema_name
from artana_evidence_api.graph_client import GraphTransportBundle, GraphTransportConfig
from artana_evidence_api.graph_integration.context import GraphCallContext
from artana_evidence_api.graph_integration.source_provenance import (
    bind_source_provenance_to_drafts,
)
from artana_evidence_api.models.base import Base as HarnessBase
from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.sqlalchemy_stores import SqlAlchemyHarnessDocumentStore
from artana_evidence_api.tests.integration.test_runtime_paths import (
    _build_client,
    _build_services,
    _qualified_agent_claim_metadata,
    _qualified_candidate_claim_payload,
    _source_bound_positive_claim_frame,
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
    default_headers = build_graph_admin_headers()
    default_headers["X-TEST-GRAPH-SERVICE-CAPABILITIES"] = "source_provenance_submit"
    default_headers["X-TEST-GRAPH-SOURCE-ATTESTATION-SERVICE"] = "artana_evidence_api"
    return GraphTransportBundle(
        config=GraphTransportConfig(
            base_url="http://testserver",
            default_headers=default_headers,
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


def test_promote_qualified_claim_fails_closed_without_live_graph_writes(
    db_session: Session,
    graph_client: TestClient,
) -> None:
    runtime = FakeKernelRuntime()
    services = replace(
        _build_services(session=db_session, runtime=runtime),
        document_store=SqlAlchemyHarnessDocumentStore(db_session),
    )
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
    source_curie = f"HGNC:{uuid4().int % 100_000:05d}"
    target_curie = f"HP:{uuid4().int % 10_000_000:07d}"
    source_entity_id = _create_live_graph_entity(
        graph_client=graph_client,
        space_id=space_id,
        headers=graph_headers,
        entity_type="GENE",
        display_label="MED13",
        identifiers={"hgnc_id": source_curie},
    )
    target_entity_id = _create_live_graph_entity(
        graph_client=graph_client,
        space_id=space_id,
        headers=graph_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
        identifiers={"hpo_id": target_curie},
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
    source_text = "In a pediatric cohort, MED13 is associated with Developmental delay."
    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    claim_frame = _source_bound_positive_claim_frame(
        source_text=source_text,
        source_locator="normalized_extraction_text",
        subject_label="MED13",
        relation_type="ASSOCIATED_WITH",
        object_label="Developmental delay",
        population="pediatric cohort",
    )
    source_document = services.document_store.create_document(
        space_id=space_id,
        created_by=uuid4(),
        title="PubMed source 12345678",
        source_type="pubmed",
        filename=None,
        media_type="text/plain",
        sha256=source_hash,
        byte_size=len(source_text.encode("utf-8")),
        page_count=None,
        text_content=source_text,
        ingestion_run_id=source_run.id,
        enrichment_status="skipped",
        extraction_status="completed",
        metadata={
            "pubmed": {"pmid": "12345678"},
            "content_source_kind": "pubmed",
            "source_capture": {
                "source_key": "pubmed",
                "external_id": "12345678",
            },
        },
    )
    (proposal_draft,) = bind_source_provenance_to_drafts(
        document=source_document,
        drafts=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="document_extraction",
                source_key=f"{source_entity_id}:ASSOCIATED_WITH:{target_entity_id}",
                document_id=source_document.id,
                title="Promote live MED13 phenotype claim",
                summary=source_text,
                confidence=0.91,
                ranking_score=0.98,
                reasoning_path={"reasoning": source_text},
                evidence_bundle=[
                    {
                        "source_type": "paper",
                        "locator": f"chars=0-{len(source_text)}",
                        "excerpt": source_text,
                    },
                ],
                payload=_qualified_candidate_claim_payload(
                    source_entity_id=str(source_entity_id),
                    target_entity_id=str(target_entity_id),
                    relation_type="ASSOCIATED_WITH",
                    frame=claim_frame,
                ),
                metadata=_qualified_agent_claim_metadata(
                    agent_run_id="integration-live-graph-promotion",
                    frame=claim_frame,
                    subject_curie=source_curie,
                    object_curie=target_curie,
                ),
            ),
        ),
    )
    proposal = services.proposal_store.create_proposals(
        space_id=str(space_id),
        run_id=source_run.id,
        proposals=(proposal_draft,),
    )[0]

    response = client.post(
        f"/v1/spaces/{space_id}/proposals/{proposal.id}/promote",
        headers=auth_headers(),
        json={"reason": "Integration live graph promotion"},
    )
    assert response.status_code == 409, response.text
    payload = response.json()
    assert payload["reason_code"] == "qualified_claim_persistence_not_ready"
    assert "cannot yet persist its complete ClaimFrame" in payload["detail"]

    proposal_response = client.get(
        f"/v1/spaces/{space_id}/proposals/{proposal.id}",
        headers=auth_headers(),
    )
    assert proposal_response.status_code == 200, proposal_response.text
    proposal_payload = proposal_response.json()
    assert proposal_payload["status"] == "pending_review"
    assert proposal_payload["decision_reason"] is None
    assert proposal_payload["decided_at"] is None

    pending_response = client.get(
        f"/v1/spaces/{space_id}/proposals",
        headers=auth_headers(),
        params={"status": "pending_review"},
    )
    assert pending_response.status_code == 200, pending_response.text
    pending_payload = pending_response.json()
    assert pending_payload["total"] == 1
    assert [item["id"] for item in pending_payload["proposals"]] == [proposal.id]

    workspace = services.artifact_store.get_workspace(
        space_id=str(space_id),
        run_id=source_run.id,
    )
    assert workspace is not None
    assert workspace.snapshot.get("last_promoted_graph_claim_id") is None
    assert workspace.snapshot.get("last_promoted_graph_relation_id") is None

    # TG03 must not leave either graph ledger behind while ClaimFrame persistence is absent.
    claims = live_graph_gateway.list_claims(space_id=space_id)
    assert claims.total == 0

    relations_response = graph_client.get(
        f"/v1/spaces/{space_id}/relations",
        headers=graph_headers,
    )
    assert relations_response.status_code == 200, relations_response.text
    relations_payload = relations_response.json()
    assert relations_payload["total"] == 0
    assert relations_payload["relations"] == []
