from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from artana_evidence_db import database as graph_database
from artana_evidence_db.ai_full_mode_persistence_models import (
    ConceptProposalModel,
    ConnectorProposalModel,
    GraphChangeProposalModel,
)
from artana_evidence_db.app import create_app
from artana_evidence_db.claim_relation_persistence_model import ClaimRelationModel
from artana_evidence_db.claim_relation_repository import (
    SqlAlchemyKernelClaimRelationRepository,
)
from artana_evidence_db.kernel_claim_models import (
    GraphClaimEvidenceModel,
    GraphClaimParticipantModel,
    GraphRelationClaimModel,
    RelationProjectionSourceModel,
)
from artana_evidence_db.kernel_dictionary_proposal_models import (
    DictionaryProposalModel,
)
from artana_evidence_db.kernel_relation_models import RelationModel
from artana_evidence_db.kernel_repositories import (
    SqlAlchemyKernelRelationClaimRepository,
)
from artana_evidence_db.provenance_model import ProvenanceModel
from artana_evidence_db.tests.support import (
    build_graph_admin_headers,
    reset_graph_service_database,
)
from artana_evidence_db.workflow_persistence_models import (
    GraphWorkflowEventModel,
    GraphWorkflowModel,
)
from fastapi.testclient import TestClient

_SUPPORTED_ASSESSMENT = {
    "support_band": "SUPPORTED",
    "grounding_level": "SPAN",
    "mapping_status": "RESOLVED",
    "speculation_level": "DIRECT",
    "confidence_rationale": "Synthetic validation evidence supports the relation.",
}
_STRONG_FACT_ASSESSMENT = {
    **_SUPPORTED_ASSESSMENT,
    "support_band": "STRONG",
}
_AI_DECISION_CONFIDENCE_ASSESSMENT = {
    "fact_assessment": _STRONG_FACT_ASSESSMENT,
    "validation_state": "VALID",
    "evidence_state": "ACCEPTED_DIRECT_EVIDENCE",
    "duplicate_conflict_state": "CLEAR",
    "source_reliability": "CURATED",
    "risk_tier": "low",
    "rationale": "Categorical inputs for deterministic policy scoring.",
}


def _assert_ai_persistence_quarantined(response) -> None:
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == (
        "qualified_claim_persistence_not_ready"
    )


@pytest.fixture(scope="function")
def graph_client() -> TestClient:
    reset_graph_service_database()
    with TestClient(create_app()) as client:
        yield client
    reset_graph_service_database()


def _create_space(graph_client: TestClient) -> tuple[str, dict[str, str]]:
    admin_headers = build_graph_admin_headers()
    space_id = str(uuid4())
    response = graph_client.put(
        f"/v1/admin/spaces/{space_id}",
        headers=admin_headers,
        json={
            "slug": f"graph-validation-{space_id[:8]}",
            "name": "Graph Validation Space",
            "description": "Validation coverage space.",
            "owner_id": str(uuid4()),
            "status": "active",
            "settings": {},
        },
    )
    assert response.status_code == 200, response.text
    seed_response = graph_client.post(
        f"/v1/domain-packs/biomedical/spaces/{space_id}/seed",
        headers=admin_headers,
    )
    assert seed_response.status_code == 200, seed_response.text
    return space_id, admin_headers


def _enable_ai_workflows(
    graph_client: TestClient,
    *,
    space_id: str,
    headers: dict[str, str],
    ai_principal: str,
    batch_auto_apply_low_risk: bool,
    allow_ai_evidence_decisions: bool = False,
) -> None:
    response = graph_client.patch(
        f"/v1/spaces/{space_id}/operating-mode",
        headers=headers,
        json={
            "mode": "ai_full_graph",
            "workflow_policy": {
                "allow_ai_graph_repair": True,
                "allow_ai_evidence_decisions": allow_ai_evidence_decisions,
                "batch_auto_apply_low_risk": batch_auto_apply_low_risk,
                "trusted_ai_principals": [ai_principal],
                "min_ai_confidence": 0.85,
            },
        },
    )
    assert response.status_code == 200, response.text


def _create_entity(
    graph_client: TestClient,
    *,
    space_id: str,
    headers: dict[str, str],
    entity_type: str,
    display_label: str,
    aliases: list[str] | None = None,
) -> str:
    response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": entity_type,
            "display_label": display_label,
            "aliases": aliases or [],
            "metadata": {},
            "identifiers": {},
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    return str(payload["entity"]["id"])


def _source_evidence_payload(
    *,
    space_id: str,
    document_id: str,
    source_text: str,
) -> dict[str, object]:
    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    return {
        "upstream": {
            "service": "artana_evidence_api",
            "research_space_id": space_id,
            "document_id": document_id,
            "attested_at": datetime.now(UTC).isoformat(),
        },
        "identity": {
            "source_kind": "pubmed",
            "authoritative_identifier": "PMID:12345678",
            "canonical_url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
            "retrieved_at": datetime.now(UTC).isoformat(),
            "content_sha256": source_hash,
            "pmid": "12345678",
        },
        "canonical_text": source_text,
        "locator": {
            "source_content_sha256": source_hash,
            "char_start": 0,
            "char_end": len(source_text),
            "exact_quote": source_text,
            "quote_sha256": source_hash,
        },
    }


def _graph_mutation_row_counts() -> dict[str, int]:
    with graph_database.SessionLocal() as session:
        return {
            "claims": session.scalar(
                sa.select(sa.func.count()).select_from(GraphRelationClaimModel),
            )
            or 0,
            "evidence": session.scalar(
                sa.select(sa.func.count()).select_from(GraphClaimEvidenceModel),
            )
            or 0,
            "participants": session.scalar(
                sa.select(sa.func.count()).select_from(GraphClaimParticipantModel),
            )
            or 0,
            "projections": session.scalar(
                sa.select(sa.func.count()).select_from(RelationProjectionSourceModel),
            )
            or 0,
            "relations": session.scalar(
                sa.select(sa.func.count()).select_from(RelationModel),
            )
            or 0,
            "claim_relations": session.scalar(
                sa.select(sa.func.count()).select_from(ClaimRelationModel),
            )
            or 0,
        }


def _create_variable(
    graph_client: TestClient,
    *,
    headers: dict[str, str],
    variable_id: str,
    data_type: str = "STRING",
) -> None:
    response = graph_client.post(
        "/v1/dictionary/variables",
        headers=headers,
        json={
            "id": variable_id,
            "canonical_name": variable_id.lower(),
            "display_name": variable_id.replace("_", " ").title(),
            "data_type": data_type,
            "domain_context": "general",
            "sensitivity": "INTERNAL",
            "constraints": {},
            "description": "Validation test variable.",
            "source_ref": "graph-validation:test",
        },
    )
    assert response.status_code == 201, response.text


def _create_provenance_record(*, space_id: str) -> str:
    provenance_id = uuid4()
    with graph_database.SessionLocal() as session:
        session.add(
            ProvenanceModel(
                id=provenance_id,
                research_space_id=UUID(space_id),
                source_type="PUBMED",
                source_ref="pmid:123456",
                extraction_run_id="graph-validation-test",
                mapping_method="manual",
                mapping_confidence=0.94,
                agent_model="gpt-5",
                raw_input={"title": "Graph validation provenance fixture"},
            ),
        )
        session.commit()
    return str(provenance_id)


def _seed_claim(
    *,
    space_id: str,
    source_entity_id: str,
    target_entity_id: str,
    relation_type: str,
    polarity: str,
    claim_text: str,
    source_document_ref: str | None = None,
    source_ref: str | None = None,
    agent_run_id: str | None = None,
) -> str:
    with graph_database.SessionLocal() as session:
        claim = SqlAlchemyKernelRelationClaimRepository(session).create(
            research_space_id=space_id,
            source_document_id=None,
            source_document_ref=source_document_ref,
            source_ref=source_ref,
            agent_run_id=agent_run_id,
            source_type="GENE",
            relation_type=relation_type,
            target_type="PHENOTYPE",
            source_label="MED13",
            target_label="Developmental delay",
            confidence=0.88,
            validation_state="ALLOWED",
            validation_reason=None,
            persistability="PERSISTABLE",
            claim_status="OPEN",
            polarity=polarity,
            claim_text=claim_text,
            claim_section="results",
            linked_relation_id=None,
            metadata={
                "origin": "seed",
                "source_entity_id": source_entity_id,
                "target_entity_id": target_entity_id,
            },
        )
        session.commit()
    return str(claim.id)


def _create_manual_claim(
    graph_client: TestClient,
    *,
    space_id: str,
    headers: dict[str, str],
    source_id: str,
    target_id: str,
    source_ref: str,
) -> str:
    response = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=headers,
        json={
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "relation_type": "ASSOCIATED_WITH",
            "assessment": _SUPPORTED_ASSESSMENT,
            "claim_text": "A curator recorded this relation.",
            "source_ref": source_ref,
            "metadata": {"origin": "curator_import"},
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_production_document_extraction_payloads_fail_closed_without_rows(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    baseline = _graph_mutation_row_counts()
    metadata = {
        "origin": "document_extraction",
        "harness_run_id": "live-agent-run-1",
    }

    claim_response = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        json={
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "relation_type": "ASSOCIATED_WITH",
            "assessment": _SUPPORTED_ASSESSMENT,
            "evidence_sentence": "MED13 is associated with developmental delay.",
            "evidence_sentence_source": "verbatim_span",
            "metadata": metadata,
        },
    )
    relation_response = graph_client.post(
        f"/v1/spaces/{space_id}/relations",
        headers=admin_headers,
        json={
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": "ASSOCIATED_WITH",
            "assessment": _SUPPORTED_ASSESSMENT,
            "evidence_sentence": "MED13 is associated with developmental delay.",
            "evidence_sentence_source": "verbatim_span",
            "metadata": metadata,
        },
    )

    _assert_ai_persistence_quarantined(claim_response)
    _assert_ai_persistence_quarantined(relation_response)
    assert _graph_mutation_row_counts() == baseline


def test_agent_claim_relation_fails_closed_without_relation_row(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    source_claim_id = _create_manual_claim(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        source_id=source_id,
        target_id=target_id,
        source_ref="manual-source-claim",
    )
    second_target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Intellectual disability",
    )
    target_claim_id = _create_manual_claim(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        source_id=source_id,
        target_id=second_target_id,
        source_ref="manual-target-claim",
    )
    baseline = _graph_mutation_row_counts()

    response = graph_client.post(
        f"/v1/spaces/{space_id}/claim-relations",
        headers=admin_headers,
        json={
            "source_claim_id": source_claim_id,
            "target_claim_id": target_claim_id,
            "relation_type": "SUPPORTS",
            "assessment": _SUPPORTED_ASSESSMENT,
            "authorship": "AGENT",
            "agent_run_id": "agent-claim-relation-1",
        },
    )

    _assert_ai_persistence_quarantined(response)
    assert _graph_mutation_row_counts() == baseline


def test_authenticated_ai_principal_quarantines_forged_manual_writes_and_replays(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    ai_headers = {
        **admin_headers,
        "X-TEST-GRAPH-AI-PRINCIPAL": "agent:forged-manual",
        "Idempotency-Key": "forged-manual-replay",
    }
    claim_payload = {
        "source_entity_id": source_id,
        "target_entity_id": target_id,
        "relation_type": "ASSOCIATED_WITH",
        "assessment": _SUPPORTED_ASSESSMENT,
        "authorship": "MANUAL",
        "claim_text": "MED13 is associated with developmental delay.",
        "metadata": {"origin": "curator_import"},
    }
    baseline = _graph_mutation_row_counts()

    first_claim = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=ai_headers,
        json=claim_payload,
    )
    replayed_claim = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=ai_headers,
        json=claim_payload,
    )
    canonical_relation = graph_client.post(
        f"/v1/spaces/{space_id}/relations",
        headers=ai_headers,
        json={
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": "ASSOCIATED_WITH",
            "assessment": _SUPPORTED_ASSESSMENT,
            "authorship": "MANUAL",
            "metadata": {"origin": "curator_import"},
        },
    )

    _assert_ai_persistence_quarantined(first_claim)
    _assert_ai_persistence_quarantined(replayed_claim)
    _assert_ai_persistence_quarantined(canonical_relation)
    assert _graph_mutation_row_counts() == baseline


def test_authenticated_ai_hypothesis_is_quarantined_without_hidden_rows(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    ai_headers = {
        **admin_headers,
        "X-TEST-GRAPH-AI-PRINCIPAL": "agent:mechanism-discovery",
    }
    baseline = _graph_mutation_row_counts()

    response = graph_client.post(
        f"/v1/spaces/{space_id}/hypotheses/manual",
        headers=ai_headers,
        json={
            "statement": "MED13 may regulate CDK8 during development.",
            "authorship": "MANUAL",
            "rationale": "Converging literature suggests this mechanism.",
            "seed_entity_ids": [],
            "source_type": "mechanism_discovery",
        },
    )

    _assert_ai_persistence_quarantined(response)
    assert _graph_mutation_row_counts() == baseline
    listed = graph_client.get(
        f"/v1/spaces/{space_id}/hypotheses",
        headers=admin_headers,
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 0


def test_claim_relation_creation_and_acceptance_quarantine_legacy_ai_endpoints(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    agent_claim_id = _seed_claim(
        space_id=space_id,
        source_entity_id=source_id,
        target_entity_id=target_id,
        relation_type="ASSOCIATED_WITH",
        polarity="SUPPORT",
        claim_text="Legacy agent claim.",
        source_ref="legacy-agent-endpoint",
        agent_run_id="legacy-agent-run",
    )
    manual_claim_id = _seed_claim(
        space_id=space_id,
        source_entity_id=source_id,
        target_entity_id=target_id,
        relation_type="ASSOCIATED_WITH",
        polarity="SUPPORT",
        claim_text="Manual review claim.",
        source_ref="manual-endpoint",
    )
    baseline = _graph_mutation_row_counts()

    create_response = graph_client.post(
        f"/v1/spaces/{space_id}/claim-relations",
        headers=admin_headers,
        json={
            "source_claim_id": agent_claim_id,
            "target_claim_id": manual_claim_id,
            "relation_type": "SUPPORTS",
            "assessment": _SUPPORTED_ASSESSMENT,
            "authorship": "MANUAL",
            "review_status": "PROPOSED",
        },
    )

    _assert_ai_persistence_quarantined(create_response)
    assert _graph_mutation_row_counts() == baseline

    with graph_database.SessionLocal() as session:
        edge = SqlAlchemyKernelClaimRelationRepository(session).create(
            research_space_id=space_id,
            source_claim_id=manual_claim_id,
            target_claim_id=agent_claim_id,
            relation_type="SUPPORTS",
            agent_run_id=None,
            source_document_id=None,
            confidence=0.8,
            review_status="PROPOSED",
            evidence_summary="Legacy edge awaiting review.",
            metadata={"origin": "curator_import"},
        )
        session.commit()
        edge_id = str(edge.id)

    before_acceptance = _graph_mutation_row_counts()
    acceptance_response = graph_client.patch(
        f"/v1/spaces/{space_id}/claim-relations/{edge_id}",
        headers=admin_headers,
        json={"review_status": "ACCEPTED"},
    )

    _assert_ai_persistence_quarantined(acceptance_response)
    assert _graph_mutation_row_counts() == before_acceptance
    with graph_database.SessionLocal() as session:
        unchanged = SqlAlchemyKernelClaimRelationRepository(session).get_by_id(edge_id)
        assert unchanged is not None
        assert unchanged.review_status == "PROPOSED"


def test_ai_principal_review_of_missing_claim_relation_preserves_not_found(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    baseline = _graph_mutation_row_counts()

    response = graph_client.patch(
        f"/v1/spaces/{space_id}/claim-relations/{uuid4()}",
        headers={
            **admin_headers,
            "X-TEST-GRAPH-AI-PRINCIPAL": "agent:missing-edge",
        },
        json={"review_status": "ACCEPTED"},
    )

    assert response.status_code == 404, response.text
    assert _graph_mutation_row_counts() == baseline


@pytest.mark.parametrize("mode", ["manual", "human_evidence_ai_graph"])
def test_agent_workflow_claim_is_blocked_in_review_and_auto_modes(
    graph_client: TestClient,
    mode: str,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    if mode != "manual":
        mode_response = graph_client.patch(
            f"/v1/spaces/{space_id}/operating-mode",
            headers=admin_headers,
            json={"mode": mode, "workflow_policy": {}},
        )
        assert mode_response.status_code == 200, mode_response.text
    baseline = _graph_mutation_row_counts()

    response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers=admin_headers,
        json={
            "kind": "evidence_approval",
            "input_payload": {
                "claim_request": {
                    "source_entity_id": source_id,
                    "target_entity_id": target_id,
                    "relation_type": "ASSOCIATED_WITH",
                    "assessment": _SUPPORTED_ASSESSMENT,
                    "authorship": "AGENT",
                    "agent_run_id": "workflow-agent-1",
                    "metadata": {"origin": "document_extraction"},
                },
            },
            "source_ref": f"workflow-quarantine-{mode}",
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["status"] == "BLOCKED"
    assert payload["explanation_payload"]["validation_code"] == (
        "qualified_claim_persistence_not_ready"
    )
    assert _graph_mutation_row_counts() == baseline


def test_legacy_pending_agent_workflow_is_blocked_on_approval(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    workflow_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers=admin_headers,
        json={
            "kind": "evidence_approval",
            "input_payload": {
                "claim_request": {
                    "source_entity_id": source_id,
                    "target_entity_id": target_id,
                    "relation_type": "ASSOCIATED_WITH",
                    "assessment": _SUPPORTED_ASSESSMENT,
                    "evidence_summary": "A curator reviewed this evidence.",
                    "evidence_sentence": "MED13 is associated with developmental delay.",
                    "metadata": {"origin": "curator_import"},
                },
            },
            "source_ref": "legacy-pending-agent-workflow",
        },
    )
    assert workflow_response.status_code == 201, workflow_response.text
    workflow = workflow_response.json()
    assert workflow["status"] == "PLAN_READY"
    with graph_database.SessionLocal() as session:
        model = session.get(GraphWorkflowModel, UUID(workflow["id"]))
        assert model is not None
        generated = dict(model.generated_resources_payload)
        pending = dict(generated["pending_claim_request"])
        pending["authorship"] = "AGENT"
        pending["agent_run_id"] = "legacy-agent-run"
        generated["pending_claim_request"] = pending
        model.generated_resources_payload = generated
        session.commit()
    baseline = _graph_mutation_row_counts()

    action_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows/{workflow['id']}/actions",
        headers=admin_headers,
        json={
            "action": "approve",
            "input_hash": workflow["workflow_hash"],
            "reason": "Review the legacy pending agent claim.",
        },
    )

    assert action_response.status_code == 200, action_response.text
    action_payload = action_response.json()
    assert action_payload["status"] == "BLOCKED"
    pending_plan = action_payload["generated_resources_payload"]["pending_claim_plan"]
    assert pending_plan["validation"]["code"] == (
        "qualified_claim_persistence_not_ready"
    )
    assert _graph_mutation_row_counts() == baseline


def test_trusted_ai_direct_claim_approval_propagates_quarantine(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    principal = "agent:direct-claim-reviewer"
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    workflow_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers=admin_headers,
        json={
            "kind": "evidence_approval",
            "input_payload": {
                "claim_request": {
                    "source_entity_id": source_id,
                    "target_entity_id": target_id,
                    "relation_type": "ASSOCIATED_WITH",
                    "assessment": _SUPPORTED_ASSESSMENT,
                    "evidence_summary": "A curator reviewed this evidence.",
                    "evidence_sentence": (
                        "MED13 is associated with developmental delay."
                    ),
                    "metadata": {"origin": "curator_import"},
                },
            },
            "source_ref": "trusted-ai-direct-claim-review",
        },
    )
    assert workflow_response.status_code == 201, workflow_response.text
    workflow = workflow_response.json()
    assert workflow["status"] == "PLAN_READY"
    assert "claim_request" in workflow["input_payload"]
    with graph_database.SessionLocal() as session:
        model = session.get(GraphWorkflowModel, UUID(workflow["id"]))
        assert model is not None
        model.generated_resources_payload = {}
        session.commit()
    _enable_ai_workflows(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        ai_principal=principal,
        batch_auto_apply_low_risk=False,
        allow_ai_evidence_decisions=True,
    )
    baseline = _graph_mutation_row_counts()

    action_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows/{workflow['id']}/actions",
        headers={
            **admin_headers,
            "X-TEST-GRAPH-AI-PRINCIPAL": principal,
        },
        json={
            "action": "approve",
            "input_hash": workflow["workflow_hash"],
            "risk_tier": "low",
            "confidence_assessment": _AI_DECISION_CONFIDENCE_ASSESSMENT,
            "ai_decision": {
                "ai_principal": principal,
                "rationale": "Review the human-staged direct claim.",
            },
        },
    )

    assert action_response.status_code == 200, action_response.text
    action_payload = action_response.json()
    assert action_payload["status"] == "BLOCKED"
    assert action_payload["plan_payload"]["validation"]["code"] == (
        "qualified_claim_persistence_not_ready"
    )
    assert action_payload["explanation_payload"]["validation_code"] == (
        "qualified_claim_persistence_not_ready"
    )
    assert action_payload["explanation_payload"]["next_action"] == "defer_to_human"
    assert action_payload["plan_payload"]["next_action"] == "defer_to_human"
    pending_plan = action_payload["generated_resources_payload"][
        "pending_claim_plan"
    ]
    assert pending_plan["validation"]["code"] == (
        "qualified_claim_persistence_not_ready"
    )
    assert _graph_mutation_row_counts() == baseline


def test_legacy_direct_claim_plan_preserves_dictionary_proposal_lineage(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    workflow_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers=admin_headers,
        json={
            "kind": "evidence_approval",
            "input_payload": {
                "claim_request": {
                    "source_entity_id": source_id,
                    "target_entity_id": target_id,
                    "relation_type": "PROTECTS_AGAINST",
                    "assessment": _SUPPORTED_ASSESSMENT,
                    "evidence_summary": "A curator reviewed this evidence.",
                    "evidence_sentence": (
                        "MED13 protects against developmental delay."
                    ),
                    "metadata": {"origin": "curator_import"},
                },
            },
            "source_ref": "legacy-direct-dictionary-plan",
        },
    )
    assert workflow_response.status_code == 201, workflow_response.text
    workflow = workflow_response.json()
    assert workflow["status"] == "PLAN_READY"
    assert workflow["generated_resources_payload"]["dictionary_proposal_ids"]
    with graph_database.SessionLocal() as session:
        model = session.get(GraphWorkflowModel, UUID(workflow["id"]))
        assert model is not None
        model.generated_resources_payload = {}
        session.commit()

    action_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows/{workflow['id']}/actions",
        headers=admin_headers,
        json={
            "action": "approve",
            "input_hash": workflow["workflow_hash"],
            "reason": "Review the legacy direct claim plan.",
        },
    )

    assert action_response.status_code == 200, action_response.text
    action_payload = action_response.json()
    assert action_payload["status"] == "PLAN_READY"
    generated = action_payload["generated_resources_payload"]
    assert generated["dictionary_proposal_ids"]
    assert generated["pending_claim_request"]["relation_type"] == (
        "PROTECTS_AGAINST"
    )
    pending_plan = generated["pending_claim_plan"]
    assert action_payload["plan_payload"]["validation"] == pending_plan["validation"]
    assert action_payload["plan_payload"]["input"] == workflow["plan_payload"]["input"]
    assert action_payload["explanation_payload"]["next_action"] == (
        "review_dictionary_proposals"
    )
    assert action_payload["plan_payload"]["next_action"] == (
        "review_dictionary_proposals"
    )


def test_pending_claim_application_preserves_workflow_governance_plan(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    workflow_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers=admin_headers,
        json={
            "kind": "evidence_approval",
            "input_payload": {
                "claim_request": {
                    "source_entity_id": source_id,
                    "target_entity_id": target_id,
                    "relation_type": "ASSOCIATED_WITH",
                    "assessment": _SUPPORTED_ASSESSMENT,
                    "evidence_summary": "A curator reviewed this evidence.",
                    "evidence_sentence": (
                        "MED13 is associated with developmental delay."
                    ),
                    "metadata": {"origin": "curator_import"},
                },
            },
            "source_ref": "pending-claim-plan-history",
        },
    )
    assert workflow_response.status_code == 201, workflow_response.text
    workflow = workflow_response.json()
    assert workflow["status"] == "PLAN_READY"
    original_plan = workflow["plan_payload"]

    action_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows/{workflow['id']}/actions",
        headers=admin_headers,
        json={
            "action": "approve",
            "input_hash": workflow["workflow_hash"],
            "reason": "Apply the reviewed pending claim.",
        },
    )

    assert action_response.status_code == 200, action_response.text
    action_payload = action_response.json()
    assert action_payload["status"] == "APPLIED"
    assert action_payload["plan_payload"]["input"] == original_plan["input"]
    assert action_payload["plan_payload"]["claim_plan"] == original_plan["claim_plan"]
    assert action_payload["plan_payload"]["next_action"] == "inspect_claim"
    assert action_payload["explanation_payload"]["next_action"] == "inspect_claim"
    assert action_payload["generated_resources_payload"]["claim_ids"]


def test_human_application_clears_superseded_ai_quarantine_instructions(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    principal = "agent:temporary-claim-reviewer"
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    workflow_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers=admin_headers,
        json={
            "kind": "evidence_approval",
            "input_payload": {
                "claim_request": {
                    "source_entity_id": source_id,
                    "target_entity_id": target_id,
                    "relation_type": "ASSOCIATED_WITH",
                    "assessment": _SUPPORTED_ASSESSMENT,
                    "evidence_summary": "A curator reviewed this evidence.",
                    "evidence_sentence": (
                        "MED13 is associated with developmental delay."
                    ),
                    "metadata": {"origin": "curator_import"},
                },
            },
            "source_ref": "ai-quarantine-then-human-application",
        },
    )
    assert workflow_response.status_code == 201, workflow_response.text
    workflow = workflow_response.json()
    assert workflow["status"] == "PLAN_READY"
    _enable_ai_workflows(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        ai_principal=principal,
        batch_auto_apply_low_risk=False,
        allow_ai_evidence_decisions=True,
    )

    blocked_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows/{workflow['id']}/actions",
        headers={
            **admin_headers,
            "X-TEST-GRAPH-AI-PRINCIPAL": principal,
        },
        json={
            "action": "approve",
            "input_hash": workflow["workflow_hash"],
            "risk_tier": "low",
            "confidence_assessment": _AI_DECISION_CONFIDENCE_ASSESSMENT,
            "ai_decision": {
                "ai_principal": principal,
                "rationale": "Attempt the claim review before human approval.",
            },
        },
    )
    assert blocked_response.status_code == 200, blocked_response.text
    blocked = blocked_response.json()
    assert blocked["status"] == "BLOCKED"
    assert blocked["plan_payload"]["next_action"] == "defer_to_human"
    assert blocked["explanation_payload"]["validation_code"] == (
        "qualified_claim_persistence_not_ready"
    )

    applied_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows/{workflow['id']}/actions",
        headers=admin_headers,
        json={
            "action": "approve",
            "input_hash": blocked["workflow_hash"],
            "reason": "A human reviewer approved the grounded claim.",
        },
    )

    assert applied_response.status_code == 200, applied_response.text
    applied = applied_response.json()
    assert applied["status"] == "APPLIED"
    assert applied["plan_payload"]["next_action"] == "inspect_claim"
    assert "next_actions" not in applied["plan_payload"]
    assert applied["explanation_payload"]["next_action"] == "inspect_claim"
    assert "validation_code" not in applied["explanation_payload"]
    assert applied["generated_resources_payload"]["claim_ids"]


def test_authenticated_ai_principal_cannot_forge_manual_workflow_approval(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    workflow_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers=admin_headers,
        json={
            "kind": "evidence_approval",
            "input_payload": {
                "claim_request": {
                    "source_entity_id": source_id,
                    "target_entity_id": target_id,
                    "relation_type": "ASSOCIATED_WITH",
                    "assessment": _SUPPORTED_ASSESSMENT,
                    "evidence_summary": "A curator reviewed this evidence.",
                    "evidence_sentence": (
                        "MED13 is associated with developmental delay."
                    ),
                    "metadata": {"origin": "curator_import"},
                },
            },
            "source_ref": "forged-manual-ai-workflow",
        },
    )
    assert workflow_response.status_code == 201, workflow_response.text
    workflow = workflow_response.json()
    assert workflow["status"] == "PLAN_READY"
    baseline = _graph_mutation_row_counts()

    action_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows/{workflow['id']}/actions",
        headers={
            **admin_headers,
            "X-TEST-GRAPH-AI-PRINCIPAL": "agent:workflow-approver",
        },
        json={
            "action": "approve",
            "input_hash": workflow["workflow_hash"],
            "reason": "Attempt to look like a human curator.",
        },
    )

    assert action_response.status_code == 400, action_response.text
    assert "cannot submit manual workflow actions" in action_response.text
    assert _graph_mutation_row_counts() == baseline


def test_authenticated_ai_principal_cannot_auto_apply_manual_workflow_claim(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    mode_response = graph_client.patch(
        f"/v1/spaces/{space_id}/operating-mode",
        headers=admin_headers,
        json={
            "mode": "human_evidence_ai_graph",
            "workflow_policy": {"allow_ai_graph_repair": True},
        },
    )
    assert mode_response.status_code == 200, mode_response.text
    baseline = _graph_mutation_row_counts()

    response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers={
            **admin_headers,
            "X-TEST-GRAPH-AI-PRINCIPAL": "agent:workflow-creator",
        },
        json={
            "kind": "evidence_approval",
            "input_payload": {
                "claim_request": {
                    "source_entity_id": source_id,
                    "target_entity_id": target_id,
                    "relation_type": "ASSOCIATED_WITH",
                    "assessment": _SUPPORTED_ASSESSMENT,
                    "authorship": "MANUAL",
                    "metadata": {"origin": "curator_import"},
                },
            },
            "source_ref": "forged-manual-ai-workflow-create",
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["status"] == "BLOCKED"
    assert payload["input_payload"]["claim_request"]["authorship"] == "AGENT"
    assert payload["input_payload"]["claim_request"]["agent_run_id"] == (
        "agent:workflow-creator"
    )
    assert payload["explanation_payload"]["validation_code"] == (
        "qualified_claim_persistence_not_ready"
    )
    assert _graph_mutation_row_counts() == baseline


def test_ai_workflow_creation_preserves_user_and_effective_ai_identity(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    principal = "agent:workflow-creator-lineage"

    response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers={
            **admin_headers,
            "X-TEST-GRAPH-AI-PRINCIPAL": principal,
        },
        json={
            "kind": "conflict_resolution",
            "input_payload": {"claim_ids": []},
            "source_ref": "ai-creation-lineage",
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    actor_context = payload["decision_payload"]["actor_context"]
    assert payload["created_by"] == principal
    assert payload["updated_by"] == principal
    assert actor_context["actor_type"] == "AI"
    assert actor_context["effective_actor"] == principal
    assert actor_context["authenticated_ai_principal"] == principal
    assert actor_context["authenticated_user_actor"].startswith("manual:")


def test_ai_batch_application_requires_explicit_space_policy(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    principal = "agent:batch-policy"
    _enable_ai_workflows(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        ai_principal=principal,
        batch_auto_apply_low_risk=False,
    )
    workflow_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers=admin_headers,
        json={
            "kind": "batch_review",
            "input_payload": {"generated_resources": []},
            "source_ref": "batch-policy-disabled",
        },
    )
    assert workflow_response.status_code == 201, workflow_response.text
    workflow = workflow_response.json()

    action_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows/{workflow['id']}/actions",
        headers={
            **admin_headers,
            "X-TEST-GRAPH-AI-PRINCIPAL": principal,
        },
        json={
            "action": "approve",
            "input_hash": workflow["workflow_hash"],
            "risk_tier": "low",
            "confidence_assessment": _AI_DECISION_CONFIDENCE_ASSESSMENT,
            "ai_decision": {
                "ai_principal": principal,
                "rationale": "Apply the low-risk batch.",
            },
        },
    )

    assert action_response.status_code == 400, action_response.text
    assert "batch_auto_apply_low_risk" in action_response.text


def test_ai_batch_fails_closed_for_nested_workflow_and_claim_review(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    principal = "agent:nested-batch"
    _enable_ai_workflows(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        ai_principal=principal,
        batch_auto_apply_low_risk=True,
    )
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    claim_id = _seed_claim(
        space_id=space_id,
        source_entity_id=source_id,
        target_entity_id=target_id,
        relation_type="ASSOCIATED_WITH",
        polarity="SUPPORT",
        claim_text="A persistable claim awaiting a real reviewer.",
    )
    target_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers=admin_headers,
        json={
            "kind": "conflict_resolution",
            "input_payload": {"claim_ids": []},
            "source_ref": "nested-ai-target",
        },
    )
    assert target_response.status_code == 201, target_response.text
    target = target_response.json()
    batch_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers={
            **admin_headers,
            "X-TEST-GRAPH-AI-PRINCIPAL": principal,
        },
        json={
            "kind": "batch_review",
            "input_payload": {
                "generated_resources": [
                    {
                        "resource_type": "workflow",
                        "resource_id": target["id"],
                        "action": "approve",
                        "input_hash": target["workflow_hash"],
                    },
                    {
                        "resource_type": "claim",
                        "resource_id": claim_id,
                        "action": "resolve",
                    },
                ],
            },
            "source_ref": "nested-ai-batch",
        },
    )
    assert batch_response.status_code == 201, batch_response.text
    batch = batch_response.json()

    action_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows/{batch['id']}/actions",
        headers={
            **admin_headers,
            "X-TEST-GRAPH-AI-PRINCIPAL": principal,
        },
        json={
            "action": "approve",
            "input_hash": batch["workflow_hash"],
            "risk_tier": "low",
            "confidence_assessment": _AI_DECISION_CONFIDENCE_ASSESSMENT,
            "ai_decision": {
                "ai_principal": principal,
                "rationale": "Apply only actions allowed for this AI actor.",
            },
        },
    )

    assert action_response.status_code == 200, action_response.text
    applied_batch = action_response.json()
    assert applied_batch["status"] == "CHANGES_REQUESTED"
    failures = applied_batch["generated_resources_payload"]["failed_resource_refs"]
    assert len(failures) == 2
    assert {failure["resource_type"] for failure in failures} == {
        "workflow",
        "claim",
    }
    assert any(
        "distinct AI reviewer identity" in failure["reason"] for failure in failures
    )
    assert not applied_batch["generated_resources_payload"]["applied_resource_refs"]

    target_after = graph_client.get(
        f"/v1/spaces/{space_id}/workflows/{target['id']}",
        headers=admin_headers,
    ).json()
    assert target_after["status"] == "WAITING_REVIEW"
    with graph_database.SessionLocal() as session:
        nested_event = session.scalars(
            sa.select(GraphWorkflowEventModel)
            .where(
                GraphWorkflowEventModel.workflow_id == UUID(target["id"]),
                GraphWorkflowEventModel.action == "approve",
            )
            .order_by(GraphWorkflowEventModel.created_at.desc()),
        ).first()
        assert nested_event is not None
        assert nested_event.actor == principal
        assert nested_event.after_status == "WAITING_REVIEW"
        claim = session.get(GraphRelationClaimModel, UUID(claim_id))
        assert claim is not None
        assert claim.claim_status == "OPEN"
        assert claim.triaged_by is None


def test_ai_cannot_mark_workflow_resolved_without_server_application(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    principal = "agent:mark-resolved"
    _enable_ai_workflows(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        ai_principal=principal,
        batch_auto_apply_low_risk=True,
    )
    workflow_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers=admin_headers,
        json={
            "kind": "conflict_resolution",
            "input_payload": {"claim_ids": []},
            "source_ref": "ai-mark-resolved-blocked",
        },
    )
    assert workflow_response.status_code == 201, workflow_response.text
    workflow = workflow_response.json()

    action_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows/{workflow['id']}/actions",
        headers={
            **admin_headers,
            "X-TEST-GRAPH-AI-PRINCIPAL": principal,
        },
        json={
            "action": "mark_resolved",
            "input_hash": workflow["workflow_hash"],
            "ai_decision": {
                "ai_principal": principal,
                "rationale": "Attempt to resolve without applying evidence.",
            },
        },
    )

    assert action_response.status_code == 400, action_response.text
    assert "cannot mark workflows resolved" in action_response.text


@pytest.mark.parametrize("action", ["approve", "apply_plan"])
def test_ai_cannot_approve_conflict_even_when_low_risk_policy_allows_ai(
    graph_client: TestClient,
    action: str,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    principal = "agent:conflict-policy"
    _enable_ai_workflows(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        ai_principal=principal,
        batch_auto_apply_low_risk=True,
    )
    workflow_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers=admin_headers,
        json={
            "kind": "conflict_resolution",
            "input_payload": {"claim_ids": []},
            "source_ref": "direct-conflict-policy-check",
        },
    )
    assert workflow_response.status_code == 201, workflow_response.text
    workflow = workflow_response.json()
    action_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows/{workflow['id']}/actions",
        headers={
            **admin_headers,
            "X-TEST-GRAPH-AI-PRINCIPAL": principal,
        },
        json={
            "action": action,
            "input_hash": workflow["workflow_hash"],
            "risk_tier": "low",
            "confidence_assessment": _AI_DECISION_CONFIDENCE_ASSESSMENT,
            "ai_decision": {
                "ai_principal": principal,
                "rationale": "Attempt a risk-matched conflict approval.",
            },
        },
    )

    assert action_response.status_code == 400, action_response.text
    assert "cannot resolve conflict workflows" in action_response.text


def test_nested_workflow_risk_is_derived_independently_of_outer_batch(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    principal = "agent:nested-risk"
    _enable_ai_workflows(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        ai_principal=principal,
        batch_auto_apply_low_risk=True,
    )
    target_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers=admin_headers,
        json={
            "kind": "bootstrap_review",
            "input_payload": {},
            "source_ref": "nested-risk-target",
        },
    )
    assert target_response.status_code == 201, target_response.text
    target = target_response.json()
    batch_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers={
            **admin_headers,
            "X-TEST-GRAPH-AI-PRINCIPAL": principal,
        },
        json={
            "kind": "batch_review",
            "input_payload": {
                "generated_resources": [
                    {
                        "resource_type": "workflow",
                        "resource_id": target["id"],
                        "action": "approve",
                        "input_hash": target["workflow_hash"],
                    },
                ],
            },
            "source_ref": "nested-risk-batch",
        },
    )
    assert batch_response.status_code == 201, batch_response.text
    batch = batch_response.json()

    action_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows/{batch['id']}/actions",
        headers={
            **admin_headers,
            "X-TEST-GRAPH-AI-PRINCIPAL": principal,
        },
        json={
            "action": "approve",
            "input_hash": batch["workflow_hash"],
            "risk_tier": "low",
            "confidence_assessment": _AI_DECISION_CONFIDENCE_ASSESSMENT,
            "ai_decision": {
                "ai_principal": principal,
                "rationale": "Apply only genuinely low-risk nested work.",
            },
        },
    )

    assert action_response.status_code == 200, action_response.text
    applied_batch = action_response.json()
    assert applied_batch["status"] == "CHANGES_REQUESTED"
    failures = applied_batch["generated_resources_payload"]["failed_resource_refs"]
    assert len(failures) == 1
    assert "risk_tier" in failures[0]["reason"]
    target_after = graph_client.get(
        f"/v1/spaces/{space_id}/workflows/{target['id']}",
        headers=admin_headers,
    ).json()
    assert target_after["status"] == "PLAN_READY"


def test_ai_batch_persists_canonical_actor_on_official_proposal_reviews(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    principal = "agent:persisted-batch-reviewer"
    _enable_ai_workflows(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        ai_principal=principal,
        batch_auto_apply_low_risk=True,
    )
    suffix = uuid4().hex[:8]
    concept_response = graph_client.post(
        f"/v1/spaces/{space_id}/concepts/proposals",
        headers=admin_headers,
        json={
            "domain_context": "general",
            "entity_type": "PHENOTYPE",
            "canonical_label": f"AI batch lineage concept {suffix}",
            "evidence_payload": {"source": "actor-lineage-test"},
            "source_ref": f"actor-lineage-concept-{suffix}",
        },
    )
    assert concept_response.status_code == 201, concept_response.text
    concept = concept_response.json()
    dictionary_response = graph_client.post(
        "/v1/dictionary/proposals/relation-types",
        headers=admin_headers,
        json={
            "id": f"AI_BATCH_LINEAGE_{suffix.upper()}",
            "display_name": f"AI batch lineage {suffix}",
            "description": "Synthetic relation type for actor-lineage validation.",
            "domain_context": "general",
            "rationale": "Verify canonical AI review persistence.",
            "evidence_payload": {"source": "actor-lineage-test"},
        },
    )
    assert dictionary_response.status_code == 201, dictionary_response.text
    dictionary = dictionary_response.json()
    connector_response = graph_client.post(
        f"/v1/spaces/{space_id}/connector-proposals",
        headers=admin_headers,
        json={
            "connector_slug": f"actor-lineage-{suffix}",
            "display_name": f"Actor Lineage {suffix}",
            "connector_kind": "document_source",
            "domain_context": "general",
            "metadata_payload": {"runtime": "external"},
            "mapping_payload": {
                "field_mappings": [
                    {
                        "source_field": "gene",
                        "target_dimension": "entity_type",
                        "target_id": "GENE",
                    },
                ],
            },
            "evidence_payload": {"source": "actor-lineage-test"},
            "source_ref": f"actor-lineage-connector-{suffix}",
        },
    )
    assert connector_response.status_code == 201, connector_response.text
    connector = connector_response.json()
    graph_change_response = graph_client.post(
        f"/v1/spaces/{space_id}/graph-change-proposals",
        headers=admin_headers,
        json={
            "concepts": [
                {
                    "local_id": f"phenotype-{suffix}",
                    "domain_context": "general",
                    "entity_type": "PHENOTYPE",
                    "canonical_label": f"Actor lineage phenotype {suffix}",
                },
            ],
            "claims": [],
            "source_ref": f"actor-lineage-graph-change-{suffix}",
        },
    )
    assert graph_change_response.status_code == 201, graph_change_response.text
    graph_change = graph_change_response.json()
    batch_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers={
            **admin_headers,
            "X-TEST-GRAPH-AI-PRINCIPAL": principal,
        },
        json={
            "kind": "batch_review",
            "input_payload": {
                "generated_resources": [
                    {
                        "resource_type": "concept_proposal",
                        "resource_id": concept["id"],
                        "action": "reject",
                        "input_hash": concept["proposal_hash"],
                    },
                    {
                        "resource_type": "dictionary_proposal",
                        "resource_id": dictionary["id"],
                        "action": "reject",
                    },
                    {
                        "resource_type": "connector_proposal",
                        "resource_id": connector["id"],
                        "action": "reject",
                    },
                    {
                        "resource_type": "graph_change_proposal",
                        "resource_id": graph_change["id"],
                        "action": "reject",
                        "input_hash": graph_change["proposal_hash"],
                    },
                ],
            },
            "source_ref": f"actor-lineage-batch-{suffix}",
        },
    )
    assert batch_response.status_code == 201, batch_response.text
    batch = batch_response.json()

    action_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows/{batch['id']}/actions",
        headers={
            **admin_headers,
            "X-TEST-GRAPH-AI-PRINCIPAL": principal,
        },
        json={
            "action": "approve",
            "input_hash": batch["workflow_hash"],
            "risk_tier": "low",
            "confidence_assessment": _AI_DECISION_CONFIDENCE_ASSESSMENT,
            "ai_decision": {
                "ai_principal": principal,
                "rationale": "Reject proposals with canonical AI lineage.",
            },
        },
    )

    assert action_response.status_code == 200, action_response.text
    assert action_response.json()["status"] == "APPLIED"
    with graph_database.SessionLocal() as session:
        reviewed_models = (
            session.get(ConceptProposalModel, UUID(concept["id"])),
            session.get(DictionaryProposalModel, dictionary["id"]),
            session.get(ConnectorProposalModel, UUID(connector["id"])),
            session.get(GraphChangeProposalModel, UUID(graph_change["id"])),
        )
        assert all(model is not None for model in reviewed_models)
        assert {
            model.reviewed_by for model in reviewed_models if model is not None
        } == {
            principal,
        }


def test_noncanonical_ai_principal_is_rejected_at_authentication(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)

    response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers={
            **admin_headers,
            "X-TEST-GRAPH-AI-PRINCIPAL": str(uuid4()),
        },
        json={
            "kind": "conflict_resolution",
            "input_payload": {"claim_ids": []},
        },
    )

    assert response.status_code == 401, response.text
    assert "canonical agent:<id>" in response.text


def test_legacy_agent_claim_cannot_be_resolved_or_materialized(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    claim_id = _seed_claim(
        space_id=space_id,
        source_entity_id=source_id,
        target_entity_id=target_id,
        relation_type="ASSOCIATED_WITH",
        polarity="SUPPORT",
        claim_text="Legacy agent claim.",
        agent_run_id="legacy-agent-run",
    )
    baseline = _graph_mutation_row_counts()

    response = graph_client.patch(
        f"/v1/spaces/{space_id}/claims/{claim_id}",
        headers=admin_headers,
        json={"claim_status": "RESOLVED"},
    )

    _assert_ai_persistence_quarantined(response)
    assert _graph_mutation_row_counts() == baseline
    with graph_database.SessionLocal() as session:
        claim = SqlAlchemyKernelRelationClaimRepository(session).get_by_id(claim_id)
        assert claim is not None
        assert claim.claim_status == "OPEN"
        assert claim.linked_relation_id is None


def test_legacy_agent_relation_cannot_be_approved(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    admin_headers["X-TEST-GRAPH-SERVICE-CAPABILITIES"] = "source_provenance_submit"
    admin_headers["X-TEST-GRAPH-SOURCE-ATTESTATION-SERVICE"] = "artana_evidence_api"
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    source_text = "MED13 is associated with developmental delay."
    document_id = str(uuid4())
    create_response = graph_client.post(
        f"/v1/spaces/{space_id}/relations",
        headers=admin_headers,
        json={
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": "ASSOCIATED_WITH",
            "assessment": _SUPPORTED_ASSESSMENT,
            "evidence_sentence": source_text,
            "evidence_sentence_source": "verbatim_span",
            "source_document_id": document_id,
            "source_evidence": _source_evidence_payload(
                space_id=space_id,
                document_id=document_id,
                source_text=source_text,
            ),
            "metadata": {"origin": "curator_import"},
        },
    )
    assert create_response.status_code == 201, create_response.text
    relation_id = create_response.json()["id"]
    with graph_database.SessionLocal() as session:
        projection = session.scalar(
            sa.select(RelationProjectionSourceModel).where(
                RelationProjectionSourceModel.relation_id == UUID(relation_id),
            ),
        )
        assert projection is not None
        projection.agent_run_id = "legacy-agent-run"
        session.commit()
    baseline = _graph_mutation_row_counts()

    response = graph_client.put(
        f"/v1/spaces/{space_id}/relations/{relation_id}",
        headers=admin_headers,
        json={"curation_status": "APPROVED"},
    )

    _assert_ai_persistence_quarantined(response)
    assert _graph_mutation_row_counts() == baseline
    with graph_database.SessionLocal() as session:
        relation = session.get(RelationModel, UUID(relation_id))
        assert relation is not None
        assert relation.curation_status == "DRAFT"


def test_manual_source_binding_supports_aliases_and_rejects_detachment(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    admin_headers["X-TEST-GRAPH-SERVICE-CAPABILITIES"] = "source_provenance_submit"
    admin_headers["X-TEST-GRAPH-SOURCE-ATTESTATION-SERVICE"] = "artana_evidence_api"
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
        aliases=["THRAP1"],
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
        aliases=["global delay"],
    )
    source_text = "THRAP1 is associated with global delay."
    document_id = str(uuid4())
    accepted = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        json={
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "relation_type": "ASSOCIATED_WITH",
            "assessment": _SUPPORTED_ASSESSMENT,
            "source_document_id": document_id,
            "source_evidence": _source_evidence_payload(
                space_id=space_id,
                document_id=document_id,
                source_text=source_text,
            ),
            "metadata": {"origin": "curator_import"},
        },
    )
    assert accepted.status_code == 201, accepted.text
    evidence_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims/{accepted.json()['id']}/evidence",
        headers=admin_headers,
    )
    assert evidence_response.status_code == 200, evidence_response.text
    assert evidence_response.json()["evidence"][0]["sentence"] == source_text
    baseline = _graph_mutation_row_counts()

    detached_text = "MED13 is associated with an unrelated condition."
    detached_document_id = str(uuid4())
    detached = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        json={
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "relation_type": "ASSOCIATED_WITH",
            "assessment": _SUPPORTED_ASSESSMENT,
            "source_document_id": detached_document_id,
            "source_evidence": _source_evidence_payload(
                space_id=space_id,
                document_id=detached_document_id,
                source_text=detached_text,
            ),
            "metadata": {"origin": "curator_import"},
        },
    )

    assert detached.status_code == 400, detached.text
    assert detached.json()["detail"]["code"] == "invalid_source_evidence_binding"
    assert _graph_mutation_row_counts() == baseline


def test_same_label_manual_endpoints_require_distinct_source_spans(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="Alpha",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Alpha",
    )
    source_text = "Alpha is associated with disease."
    document_id = str(uuid4())
    baseline = _graph_mutation_row_counts()

    response = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        json={
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "relation_type": "ASSOCIATED_WITH",
            "assessment": _SUPPORTED_ASSESSMENT,
            "source_document_id": document_id,
            "source_evidence": _source_evidence_payload(
                space_id=space_id,
                document_id=document_id,
                source_text=source_text,
            ),
            "metadata": {"origin": "curator_import"},
        },
    )

    assert response.status_code == 400, response.text
    assert "distinct, non-overlapping" in response.json()["detail"]["message"]
    assert _graph_mutation_row_counts() == baseline


def test_manual_relation_source_detachment_creates_no_graph_rows(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    source_text = "MED13 is associated with an unrelated condition."
    document_id = str(uuid4())
    baseline = _graph_mutation_row_counts()

    response = graph_client.post(
        f"/v1/spaces/{space_id}/relations",
        headers=admin_headers,
        json={
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": "ASSOCIATED_WITH",
            "assessment": _SUPPORTED_ASSESSMENT,
            "source_document_id": document_id,
            "source_evidence": _source_evidence_payload(
                space_id=space_id,
                document_id=document_id,
                source_text=source_text,
            ),
            "metadata": {"origin": "curator_import"},
        },
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "invalid_source_evidence_binding"
    assert _graph_mutation_row_counts() == baseline


def test_manual_workflow_preserves_supplied_source_provenance(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    source_text = "MED13 is associated with developmental delay."
    document_id = str(uuid4())
    source_evidence = _source_evidence_payload(
        space_id=space_id,
        document_id=document_id,
        source_text=source_text,
    )
    workflow_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers=admin_headers,
        json={
            "kind": "evidence_approval",
            "input_payload": {
                "claim_request": {
                    "source_entity_id": source_id,
                    "target_entity_id": target_id,
                    "relation_type": "ASSOCIATED_WITH",
                    "assessment": _SUPPORTED_ASSESSMENT,
                    "source_document_id": document_id,
                    "source_document_ref": "PMID:12345678",
                    "source_evidence": source_evidence,
                    "metadata": {"origin": "curator_import"},
                },
            },
            "source_ref": "manual-source-provenance-workflow",
        },
    )
    assert workflow_response.status_code == 201, workflow_response.text
    workflow = workflow_response.json()
    assert workflow["status"] == "PLAN_READY"

    action_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows/{workflow['id']}/actions",
        headers=admin_headers,
        json={
            "action": "approve",
            "input_hash": workflow["workflow_hash"],
            "reason": "A curator approved the exact source evidence.",
        },
    )

    assert action_response.status_code == 200, action_response.text
    action_payload = action_response.json()
    assert action_payload["status"] == "APPLIED"
    claim_id = action_payload["generated_resources_payload"]["claim_ids"][0]
    claim_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        params={"limit": 100},
    )
    claim = next(
        item for item in claim_response.json()["claims"] if item["id"] == claim_id
    )
    assert claim["source_document_id"] == document_id
    assert claim["source_document_ref"] == "PMID:12345678"
    with graph_database.SessionLocal() as session:
        evidence = session.scalar(
            sa.select(GraphClaimEvidenceModel).where(
                GraphClaimEvidenceModel.claim_id == UUID(claim_id),
            ),
        )
        assert evidence is not None
        assert str(evidence.source_document_id) == document_id
        assert evidence.sentence == source_text
        assert evidence.evidence_locator_payload["exact_quote"] == source_text
        assert evidence.provenance_status == "UNVERIFIED"
        source_identity = evidence.metadata_payload["source_identity"]
        assert isinstance(source_identity, dict)
        assert source_identity["authoritative_identifier"] == "PMID:12345678"


def test_graph_service_entity_list_requires_type_or_query(
    graph_client: TestClient,
) -> None:
    response = graph_client.get(
        f"/v1/spaces/{uuid4()}/entities",
        headers=build_graph_admin_headers(),
    )

    assert response.status_code == 400, response.text
    assert (
        response.json()["detail"]
        == "Provide either 'type' or 'q' when listing entities."
    )


def test_graph_service_protected_route_requires_authentication(
    graph_client: TestClient,
) -> None:
    response = graph_client.get(
        f"/v1/spaces/{uuid4()}/entities",
        params={"type": "GENE"},
    )

    assert response.status_code == 401, response.text
    assert response.json()["detail"] == "Authentication required"


def test_graph_service_entity_list_rejects_invalid_entity_ids(
    graph_client: TestClient,
) -> None:
    response = graph_client.get(
        f"/v1/spaces/{uuid4()}/entities",
        headers=build_graph_admin_headers(),
        params={"type": "GENE", "ids": "not-a-uuid"},
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Invalid entity id(s): not-a-uuid"


def test_graph_service_graph_document_rejects_seed_ids_in_starter_mode(
    graph_client: TestClient,
) -> None:
    response = graph_client.post(
        f"/v1/spaces/{uuid4()}/graph/document",
        headers=build_graph_admin_headers(),
        json={
            "mode": "starter",
            "seed_entity_ids": [str(uuid4())],
            "depth": 2,
            "top_k": 25,
            "max_nodes": 180,
            "max_edges": 260,
            "include_claims": True,
            "include_evidence": True,
            "max_claims": 250,
            "evidence_limit_per_claim": 3,
        },
    )

    assert response.status_code == 400, response.text
    assert (
        response.json()["detail"]
        == "seed_entity_ids must be empty when mode='starter'."
    )


def test_graph_service_graph_document_requires_seed_ids_in_seeded_mode(
    graph_client: TestClient,
) -> None:
    response = graph_client.post(
        f"/v1/spaces/{uuid4()}/graph/document",
        headers=build_graph_admin_headers(),
        json={
            "mode": "seeded",
            "seed_entity_ids": [],
            "depth": 2,
            "top_k": 25,
            "max_nodes": 180,
            "max_edges": 260,
            "include_claims": True,
            "include_evidence": True,
            "max_claims": 250,
            "evidence_limit_per_claim": 3,
        },
    )

    assert response.status_code == 400, response.text
    assert (
        response.json()["detail"] == "seed_entity_ids is required when mode='seeded'."
    )


def test_graph_service_graph_view_rejects_unknown_view_type(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)

    response = graph_client.get(
        f"/v1/spaces/{space_id}/graph/views/unknown/{uuid4()}",
        headers=admin_headers,
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Unsupported graph view type 'unknown'"


def test_graph_service_admin_membership_upsert_rejects_invalid_role(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)

    response = graph_client.put(
        f"/v1/admin/spaces/{space_id}/memberships/{uuid4()}",
        headers=admin_headers,
        json={"role": "invalid-role", "is_active": True},
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["loc"][-1] == "role"


def test_graph_service_relation_create_rejects_numeric_confidence_input(
    graph_client: TestClient,
) -> None:
    response = graph_client.post(
        f"/v1/spaces/{uuid4()}/relations",
        headers=build_graph_admin_headers(),
        json={
            "source_id": str(uuid4()),
            "relation_type": "ASSOCIATED_WITH",
            "target_id": str(uuid4()),
            "assessment": _SUPPORTED_ASSESSMENT,
            "confidence": 1.5,
        },
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert any(
        error["loc"][-1] == "confidence" and error["type"] == "extra_forbidden"
        for error in detail
    )


def test_graph_service_validate_claim_reports_unknown_relation_type(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )

    response = graph_client.post(
        f"/v1/spaces/{space_id}/validate/claim",
        headers=admin_headers,
        json={
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "relation_type": "PROTECTS_AGAINST",
            "assessment": _SUPPORTED_ASSESSMENT,
            "claim_text": "MED13 protects against developmental delay.",
            "metadata": {"origin": "test"},
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["valid"] is False
    assert payload["code"] == "unknown_relation_type"
    assert payload["validation_state"] == "UNDEFINED"
    assert payload["persistability"] == "NON_PERSISTABLE"
    assert payload["next_actions"][0]["proposal_type"] == "RELATION_TYPE"
    assert (
        payload["next_actions"][0]["endpoint"]
        == "/v1/dictionary/proposals/relation-types"
    )


def test_graph_service_validate_claim_next_action_payload_is_postable(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )

    validation_response = graph_client.post(
        f"/v1/spaces/{space_id}/validate/claim",
        headers=admin_headers,
        json={
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "relation_type": "PROTECTS_AGAINST",
            "assessment": _SUPPORTED_ASSESSMENT,
        },
    )
    assert validation_response.status_code == 200, validation_response.text
    next_action = validation_response.json()["next_actions"][0]

    proposal_response = graph_client.post(
        next_action["endpoint"],
        headers=admin_headers,
        json=next_action["payload"],
    )
    assert proposal_response.status_code == 201, proposal_response.text
    assert proposal_response.json()["relation_type"] == "PROTECTS_AGAINST"


def test_graph_service_validate_entity_reports_unknown_entity_type(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)

    response = graph_client.post(
        f"/v1/spaces/{space_id}/validate/entity",
        headers=admin_headers,
        json={
            "entity_type": "PROJECT_GENE",
            "display_label": "Project Gene",
            "aliases": [],
            "metadata": {},
            "identifiers": {},
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["valid"] is False
    assert payload["code"] == "unknown_entity_type"
    assert payload["next_actions"][0]["proposal_type"] == "ENTITY_TYPE"
    assert (
        payload["next_actions"][0]["endpoint"]
        == "/v1/dictionary/proposals/entity-types"
    )


def test_graph_service_validate_entity_next_action_payload_is_postable(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)

    validation_response = graph_client.post(
        f"/v1/spaces/{space_id}/validate/entity",
        headers=admin_headers,
        json={
            "entity_type": "PROJECT_GENE",
            "display_label": "Project Gene",
            "aliases": [],
            "metadata": {},
            "identifiers": {},
        },
    )
    assert validation_response.status_code == 200, validation_response.text
    next_action = validation_response.json()["next_actions"][0]

    proposal_response = graph_client.post(
        next_action["endpoint"],
        headers=admin_headers,
        json=next_action["payload"],
    )
    assert proposal_response.status_code == 201, proposal_response.text
    assert proposal_response.json()["entity_type"] == "PROJECT_GENE"


def test_graph_service_validate_entity_reports_inactive_entity_type(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    create_type_response = graph_client.post(
        "/v1/dictionary/entity-types",
        headers=admin_headers,
        json={
            "id": "PROJECT_GENE",
            "display_name": "Project Gene",
            "description": "Project-specific entity type for validation testing.",
            "domain_context": "general",
            "expected_properties": {},
            "source_ref": "graph-validation:test",
        },
    )
    assert create_type_response.status_code == 201, create_type_response.text
    review_response = graph_client.patch(
        "/v1/dictionary/entity-types/PROJECT_GENE/review-status",
        headers=admin_headers,
        json={"review_status": "PENDING_REVIEW"},
    )
    assert review_response.status_code == 200, review_response.text

    response = graph_client.post(
        f"/v1/spaces/{space_id}/validate/entity",
        headers=admin_headers,
        json={
            "entity_type": "PROJECT_GENE",
            "display_label": "Project Gene",
            "aliases": [],
            "metadata": {},
            "identifiers": {},
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["valid"] is False
    assert payload["code"] == "inactive_entity_type"
    assert payload["next_actions"][0]["action"] == "request_dictionary_review"


def test_graph_service_validate_claim_requires_evidence_for_allowed_triple(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )

    response = graph_client.post(
        f"/v1/spaces/{space_id}/validate/claim",
        headers=admin_headers,
        json={
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "relation_type": "ASSOCIATED_WITH",
            "assessment": _SUPPORTED_ASSESSMENT,
            "claim_text": "MED13 is associated with developmental delay.",
            "metadata": {"origin": "test"},
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["valid"] is False
    assert payload["code"] == "insufficient_evidence"
    assert payload["validation_state"] == "INVALID_COMPONENTS"
    assert payload["persistability"] == "NON_PERSISTABLE"
    assert payload["next_actions"][0]["action"] == "attach_evidence"


def test_graph_service_create_claim_rejects_unknown_relation_type(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )

    response = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        json={
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "relation_type": "PROTECTS_AGAINST",
            "assessment": _SUPPORTED_ASSESSMENT,
            "claim_text": "MED13 protects against developmental delay.",
            "metadata": {"origin": "test"},
        },
    )

    assert response.status_code == 400, response.text
    payload = response.json()
    assert payload["detail"]["code"] == "unknown_relation_type"
    assert payload["detail"]["validation_state"] == "UNDEFINED"
    assert payload["detail"]["persistability"] == "NON_PERSISTABLE"


def test_graph_service_validate_relation_constraint_existing_block_requests_review(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    relation_type_response = graph_client.post(
        "/v1/dictionary/relation-types",
        headers=admin_headers,
        json={
            "id": "PROJECTS_TO",
            "display_name": "Projects To",
            "description": "Validation test relation type.",
            "domain_context": "general",
            "is_directional": True,
            "source_ref": "graph-validation:relation-constraint-projects-to",
        },
    )
    assert relation_type_response.status_code == 201, relation_type_response.text
    forbidden_constraint_response = graph_client.post(
        "/v1/dictionary/relation-constraints",
        headers=admin_headers,
        json={
            "source_type": "GENE",
            "relation_type": "PROJECTS_TO",
            "target_type": "PHENOTYPE",
            "is_allowed": False,
            "requires_evidence": True,
            "profile": "FORBIDDEN",
            "source_ref": "graph-validation:forbidden-projects-to",
        },
    )
    assert forbidden_constraint_response.status_code == 201, (
        forbidden_constraint_response.text
    )

    validation_response = graph_client.post(
        f"/v1/spaces/{space_id}/validate/claim",
        headers=admin_headers,
        json={
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "relation_type": "PROJECTS_TO",
            "assessment": _SUPPORTED_ASSESSMENT,
            "evidence_sentence": "MED13 projects to developmental delay.",
            "source_document_ref": "pmid:12345",
        },
    )
    assert validation_response.status_code == 200, validation_response.text
    payload = validation_response.json()
    assert payload["code"] == "relation_constraint_not_allowed"
    next_action = payload["next_actions"][0]
    assert next_action["action"] == "request_dictionary_review"
    assert next_action["endpoint"] == "/v1/dictionary/relation-constraints"
    assert next_action["payload"] == {
        "source_type": "GENE",
        "relation_type": "PROJECTS_TO",
        "target_type": "PHENOTYPE",
        "current_profile": "FORBIDDEN",
    }


def test_graph_service_create_claim_is_idempotent_with_header_key(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    request_payload = {
        "source_entity_id": source_id,
        "target_entity_id": target_id,
        "relation_type": "ASSOCIATED_WITH",
        "assessment": _SUPPORTED_ASSESSMENT,
        "claim_text": "MED13 is associated with developmental delay.",
        "source_document_ref": "pmid:123456",
        "metadata": {"origin": "test"},
    }
    replay_headers = {
        **admin_headers,
        "Idempotency-Key": f"claim-replay-{uuid4().hex[:12]}",
    }

    first_response = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=replay_headers,
        json=request_payload,
    )
    assert first_response.status_code == 201, first_response.text
    first_payload = first_response.json()

    second_response = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=replay_headers,
        json=request_payload,
    )
    assert second_response.status_code == 201, second_response.text
    second_payload = second_response.json()
    assert second_payload["id"] == first_payload["id"]
    assert second_payload["source_ref"] == first_payload["source_ref"]
    assert second_payload["source_ref"].startswith("idempotency-key:")

    claims_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        params={"relation_type": "ASSOCIATED_WITH"},
    )
    assert claims_response.status_code == 200, claims_response.text
    assert claims_response.json()["total"] == 1


def test_graph_service_ai_claim_requires_provenance_envelope(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    request_payload = {
        "source_entity_id": source_id,
        "target_entity_id": target_id,
        "relation_type": "ASSOCIATED_WITH",
        "assessment": _SUPPORTED_ASSESSMENT,
        "claim_text": "MED13 is associated with developmental delay.",
        "evidence_sentence": "MED13 was associated with developmental delay.",
        "evidence_sentence_source": "artana_generated",
        "source_document_ref": "pmid:123456",
        "agent_run_id": "ai-run-1",
        "metadata": {"origin": "graph_harness"},
    }

    validation_response = graph_client.post(
        f"/v1/spaces/{space_id}/validate/claim",
        headers=admin_headers,
        json=request_payload,
    )
    assert validation_response.status_code == 200, validation_response.text
    validation_payload = validation_response.json()
    assert validation_payload["valid"] is False
    assert validation_payload["code"] == "missing_ai_provenance"
    assert validation_payload["persistability"] == "NON_PERSISTABLE"

    create_response = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        json=request_payload,
    )
    _assert_ai_persistence_quarantined(create_response)

    request_payload["ai_provenance"] = {
        "model_id": "artana-kernel",
        "model_version": "test",
        "prompt_id": "graph-validation-ai-claim",
        "prompt_version": "v1",
        "input_hash": uuid4().hex,
        "rationale": "The sentence supports the relation.",
        "evidence_references": ["pmid:123456"],
    }
    request_payload["metadata"]["evidence_grounding"] = {
        "anchor_start": 0,
        "anchor_end": 47,
        "match_kind": "exact",
        "score": 1.0,
        "subject_present": True,
        "object_present": True,
        "grounded": True,
    }
    request_payload["metadata"]["support_verification"] = {
        "support": "ENTAILS",
        "rationale": "The sentence directly supports the relation.",
        "model_id": "artana-heuristic-support-v1",
        "verification_method": "heuristic",
    }
    accepted_response = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        json=request_payload,
    )
    _assert_ai_persistence_quarantined(accepted_response)


def test_graph_service_ai_claim_requires_entailing_support_verification(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    request_payload = {
        "source_entity_id": source_id,
        "target_entity_id": target_id,
        "relation_type": "ASSOCIATED_WITH",
        "assessment": _SUPPORTED_ASSESSMENT,
        "claim_text": "MED13 is associated with developmental delay.",
        "evidence_sentence": "MED13 was associated with developmental delay.",
        "evidence_sentence_source": "artana_generated",
        "source_document_ref": "pmid:123456",
        "agent_run_id": "ai-run-support-test",
        "ai_provenance": {
            "model_id": "artana-kernel",
            "model_version": "test",
            "prompt_id": "graph-validation-ai-claim",
            "prompt_version": "v1",
            "input_hash": uuid4().hex,
            "rationale": "The sentence supports the relation.",
            "evidence_references": ["pmid:123456"],
        },
        "metadata": {
            "origin": "graph_harness",
            "evidence_grounding": {
                "anchor_start": 0,
                "anchor_end": 47,
                "match_kind": "exact",
                "score": 1.0,
                "subject_present": True,
                "object_present": True,
                "grounded": True,
            },
            "support_verification": {
                "support": "NEUTRAL",
                "rationale": "The sentence co-mentions both endpoints.",
                "model_id": "artana-heuristic-support-v1",
                "verification_method": "heuristic",
            },
        },
    }

    validation_response = graph_client.post(
        f"/v1/spaces/{space_id}/validate/claim",
        headers=admin_headers,
        json=request_payload,
    )

    assert validation_response.status_code == 200, validation_response.text
    validation_payload = validation_response.json()
    assert validation_payload["valid"] is False
    assert validation_payload["code"] == "insufficient_evidence"
    assert validation_payload["message"] == (
        "AI-authored claims require independent agent support verification with "
        "support=ENTAILS and verification_method=agent."
    )


def test_graph_service_rejects_forged_agent_origin_without_server_receipt(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    request_payload = {
        "source_entity_id": source_id,
        "target_entity_id": target_id,
        "relation_type": "ASSOCIATED_WITH",
        "assessment": _SUPPORTED_ASSESSMENT,
        "claim_text": "MED13 is associated with developmental delay.",
        "evidence_sentence": "MED13 was associated with developmental delay.",
        "evidence_sentence_source": "artana_generated",
        "source_document_ref": "pmid:123456",
        "agent_run_id": "ai-run-heuristic-forgery-test",
        "ai_provenance": {
            "model_id": "artana-kernel",
            "model_version": "test",
            "prompt_id": "graph-validation-ai-claim",
            "prompt_version": "v1",
            "input_hash": uuid4().hex,
            "rationale": "The extraction agent proposed the relation.",
            "evidence_references": ["pmid:123456"],
        },
        "metadata": {
            "origin": "graph_harness",
            "agent_extraction_completed": True,
            "fallback_output_used": False,
            "trusted_evidence_eligible": True,
            "trust_tier": "trusted",
            "trust_floor_failures": [],
            "evidence_grounding": {
                "anchor_start": 0,
                "anchor_end": 47,
                "match_kind": "exact",
                "score": 1.0,
                "subject_present": True,
                "object_present": True,
                "grounded": True,
            },
            "support_verification": {
                "support": "ENTAILS",
                "rationale": "A deterministic cue matched both endpoints.",
                "model_id": "openai:gpt-5.6-luna",
                "verification_method": "agent",
            },
            "entity_linking": {
                "subject": {
                    "status": "linked",
                    "curie": "HGNC:22474",
                    "source": "verified_linker",
                    "trusted_identifier": True,
                },
                "object": {
                    "status": "linked",
                    "curie": "HP:0001263",
                    "source": "verified_linker",
                    "trusted_identifier": True,
                },
            },
        },
    }

    validation_response = graph_client.post(
        f"/v1/spaces/{space_id}/validate/claim",
        headers=admin_headers,
        json=request_payload,
    )
    assert validation_response.status_code == 200, validation_response.text
    validation_payload = validation_response.json()
    assert validation_payload["valid"] is False
    assert validation_payload["message"] == (
        "Trusted AI evidence promotion is quarantined until Graph DB can verify "
        "a server-owned agent-verification receipt."
    )
    assert validation_payload["next_actions"][0]["action"] == (
        "route_to_human_review"
    )

    create_response = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        json=request_payload,
    )
    _assert_ai_persistence_quarantined(create_response)


@pytest.mark.parametrize(
    ("metadata_override", "expected_message", "expected_action"),
    [
        (
            {"review_status": "review_only"},
            "Trusted AI evidence cannot use review-only relation evidence.",
            "route_to_human_review",
        ),
        (
            {"review_reason_codes": ["hedged_language", "may_link"]},
            "Trusted AI evidence cannot use weak or hedged review reason codes.",
            "route_to_human_review",
        ),
    ],
)
def test_graph_service_rejects_trusted_ai_claim_with_review_lane_metadata(
    graph_client: TestClient,
    metadata_override: dict[str, object],
    expected_message: str,
    expected_action: str,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    metadata = {
        "origin": "graph_harness",
        "agent_extraction_completed": True,
        "fallback_output_used": False,
        "trusted_evidence_eligible": True,
        "trust_tier": "trusted",
        "trust_floor_failures": [],
        "evidence_grounding": {
            "anchor_start": 0,
            "anchor_end": 47,
            "match_kind": "exact",
            "score": 1.0,
            "subject_present": True,
            "object_present": True,
            "grounded": True,
        },
        "support_verification": {
            "support": "ENTAILS",
            "rationale": "The sentence directly supports the relation.",
            "model_id": "openai:gpt-5.6-luna",
            "verification_method": "agent",
        },
        "entity_linking": {
            "subject": {
                "status": "linked",
                "curie": "HGNC:22474",
                "source": "verified_linker",
                "trusted_identifier": True,
            },
            "object": {
                "status": "linked",
                "curie": "HP:0001263",
                "source": "verified_linker",
                "trusted_identifier": True,
            },
        },
    }
    metadata.update(metadata_override)
    request_payload = {
        "source_entity_id": source_id,
        "target_entity_id": target_id,
        "relation_type": "ASSOCIATED_WITH",
        "assessment": _SUPPORTED_ASSESSMENT,
        "claim_text": "MED13 is associated with developmental delay.",
        "evidence_sentence": "MED13 was associated with developmental delay.",
        "evidence_sentence_source": "artana_generated",
        "source_document_ref": "pmid:123456",
        "agent_run_id": "ai-run-review-lane-test",
        "ai_provenance": {
            "model_id": "artana-kernel",
            "model_version": "test",
            "prompt_id": "graph-validation-ai-claim",
            "prompt_version": "v1",
            "input_hash": uuid4().hex,
            "rationale": "The sentence supports the relation.",
            "evidence_references": ["pmid:123456"],
        },
        "metadata": metadata,
    }

    validation_response = graph_client.post(
        f"/v1/spaces/{space_id}/validate/claim",
        headers=admin_headers,
        json=request_payload,
    )
    assert validation_response.status_code == 200, validation_response.text
    validation_payload = validation_response.json()
    assert validation_payload["valid"] is False
    assert validation_payload["code"] == "insufficient_evidence"
    assert validation_payload["message"] == expected_message
    assert validation_payload["next_actions"][0]["action"] == expected_action

    create_response = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        json=request_payload,
    )
    _assert_ai_persistence_quarantined(create_response)


def test_graph_service_claims_reject_trusted_floor_failure_without_ai_provenance(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    request_payload = {
        "source_entity_id": source_id,
        "target_entity_id": target_id,
        "relation_type": "ASSOCIATED_WITH",
        "assessment": _SUPPORTED_ASSESSMENT,
        "claim_text": "MED13 is associated with developmental delay.",
        "evidence_sentence": "MED13 was associated with developmental delay.",
        "evidence_sentence_source": "pubmed",
        "source_document_ref": "pmid:123456",
        "metadata": {
            "agent_extraction_completed": True,
            "fallback_output_used": False,
            "trusted_evidence_eligible": True,
            "trust_tier": "trusted",
            "trust_floor_failures": [],
            "evidence_grounding": {
                "anchor_start": 0,
                "anchor_end": 47,
                "match_kind": "exact",
                "score": 1.0,
                "subject_present": True,
                "object_present": True,
                "grounded": True,
            },
            "support_verification": {
                "support": "ENTAILS",
                "rationale": "The sentence directly supports the relation.",
                "model_id": "openai:gpt-5.6-luna",
                "verification_method": "agent",
            },
            "entity_linking": {
                "subject": {
                    "status": "linked",
                    "curie": "HGNC:22474",
                    "source": "verified_linker",
                    "trusted_identifier": True,
                },
                "object": {
                    "status": "linked",
                    "curie": "HP:0001263",
                    "source": "verified_linker",
                    "trusted_identifier": True,
                },
            },
            "review_status": "review_only",
        },
    }

    validation_response = graph_client.post(
        f"/v1/spaces/{space_id}/validate/claim",
        headers=admin_headers,
        json=request_payload,
    )
    assert validation_response.status_code == 200, validation_response.text
    validation_payload = validation_response.json()
    assert validation_payload["valid"] is False
    assert validation_payload["code"] == "insufficient_evidence"
    assert validation_payload["next_actions"][0]["action"] == "route_to_human_review"

    create_response = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        json=request_payload,
    )
    assert create_response.status_code == 400, create_response.text
    detail = create_response.json()["detail"]
    assert detail["code"] == "insufficient_evidence"
    assert detail["message"] == (
        "Trusted AI evidence cannot use review-only relation evidence."
    )
    assert detail["next_actions"][0]["action"] == "route_to_human_review"


def test_graph_service_ai_claim_requires_structured_grounding(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    request_payload = {
        "source_entity_id": source_id,
        "target_entity_id": target_id,
        "relation_type": "ASSOCIATED_WITH",
        "assessment": _SUPPORTED_ASSESSMENT,
        "claim_text": "MED13 is associated with developmental delay.",
        "evidence_sentence": "MED13 was associated with developmental delay.",
        "evidence_sentence_source": "artana_generated",
        "source_document_ref": "pmid:123456",
        "agent_run_id": "ai-run-grounding-test",
        "ai_provenance": {
            "model_id": "artana-kernel",
            "model_version": "test",
            "prompt_id": "graph-validation-ai-claim",
            "prompt_version": "v1",
            "input_hash": uuid4().hex,
            "rationale": "The sentence supports the relation.",
            "evidence_references": ["pmid:123456"],
        },
        "metadata": {
            "origin": "graph_harness",
            "evidence_grounding": {
                "anchor_start": 0,
                "anchor_end": 47,
                "match_kind": "exact",
                "score": 1.0,
                "subject_present": True,
                "object_present": False,
                "grounded": False,
            },
        },
    }

    validation_response = graph_client.post(
        f"/v1/spaces/{space_id}/validate/claim",
        headers=admin_headers,
        json=request_payload,
    )

    assert validation_response.status_code == 200, validation_response.text
    validation_payload = validation_response.json()
    assert validation_payload["valid"] is False
    assert validation_payload["code"] == "insufficient_evidence"
    assert validation_payload["message"] == (
        "AI-authored claims require structured evidence grounding with "
        "subject and object present."
    )

    create_response = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        json=request_payload,
    )
    _assert_ai_persistence_quarantined(create_response)


def test_graph_service_create_claim_rejects_duplicate_without_replay_key(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    request_payload = {
        "source_entity_id": source_id,
        "target_entity_id": target_id,
        "relation_type": "ASSOCIATED_WITH",
        "assessment": _SUPPORTED_ASSESSMENT,
        "claim_text": "MED13 is associated with developmental delay.",
        "source_document_ref": "pmid:123456",
        "metadata": {"origin": "test"},
    }

    first_response = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        json=request_payload,
    )
    assert first_response.status_code == 201, first_response.text
    existing_claim_id = first_response.json()["id"]

    second_response = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        json=request_payload,
    )
    assert second_response.status_code == 409, second_response.text
    assert second_response.json()["detail"] == {
        "code": "duplicate_claim",
        "message": "An equivalent support claim already exists in this research space.",
        "claim_ids": [existing_claim_id],
    }


def test_graph_service_validate_claim_reports_duplicate_existing_claim(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    existing_claim_id = _seed_claim(
        space_id=space_id,
        source_entity_id=source_id,
        target_entity_id=target_id,
        relation_type="ASSOCIATED_WITH",
        polarity="SUPPORT",
        claim_text="MED13 is associated with developmental delay.",
        source_document_ref="pmid:123456",
    )

    response = graph_client.post(
        f"/v1/spaces/{space_id}/validate/claim",
        headers=admin_headers,
        json={
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "relation_type": "ASSOCIATED_WITH",
            "assessment": _SUPPORTED_ASSESSMENT,
            "claim_text": "MED13 is associated with developmental delay.",
            "source_document_ref": "pmid:123456",
            "metadata": {"origin": "test"},
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["valid"] is False
    assert payload["code"] == "duplicate_claim"
    assert payload["claim_ids"] == [existing_claim_id]
    assert payload["message"] == (
        "An equivalent support claim already exists in this research space."
    )


def test_graph_service_create_claim_rejects_conflicting_existing_claim(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    conflicting_claim_id = _seed_claim(
        space_id=space_id,
        source_entity_id=source_id,
        target_entity_id=target_id,
        relation_type="ASSOCIATED_WITH",
        polarity="REFUTE",
        claim_text="MED13 is not associated with developmental delay.",
        source_document_ref="pmid:654321",
    )

    response = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        json={
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "relation_type": "ASSOCIATED_WITH",
            "assessment": _SUPPORTED_ASSESSMENT,
            "claim_text": "MED13 is associated with developmental delay.",
            "source_document_ref": "pmid:123456",
            "metadata": {"origin": "test"},
        },
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == {
        "code": "conflicting_claim",
        "message": "An opposing claim already exists for this triple in this research space.",
        "claim_ids": [conflicting_claim_id],
    }


def test_graph_service_validate_claim_reports_conflicting_existing_claim(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    conflicting_claim_id = _seed_claim(
        space_id=space_id,
        source_entity_id=source_id,
        target_entity_id=target_id,
        relation_type="ASSOCIATED_WITH",
        polarity="REFUTE",
        claim_text="MED13 is not associated with developmental delay.",
        source_document_ref="pmid:654321",
    )

    response = graph_client.post(
        f"/v1/spaces/{space_id}/validate/claim",
        headers=admin_headers,
        json={
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "relation_type": "ASSOCIATED_WITH",
            "assessment": _SUPPORTED_ASSESSMENT,
            "claim_text": "MED13 is associated with developmental delay.",
            "source_document_ref": "pmid:123456",
            "metadata": {"origin": "test"},
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["valid"] is False
    assert payload["code"] == "conflicting_claim"
    assert payload["claim_ids"] == [conflicting_claim_id]
    assert payload["message"] == (
        "An opposing claim already exists for this triple in this research space."
    )


def test_graph_service_unknown_relation_type_claim_is_not_persisted(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )

    create_response = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        json={
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "relation_type": "PROTECTS_AGAINST",
            "assessment": _SUPPORTED_ASSESSMENT,
            "claim_text": "MED13 protects against developmental delay.",
            "metadata": {"origin": "test"},
        },
    )
    assert create_response.status_code == 400, create_response.text
    payload = create_response.json()["detail"]
    assert payload["code"] == "unknown_relation_type"
    assert payload["persistability"] == "NON_PERSISTABLE"

    list_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        params={"relation_type": "PROTECTS_AGAINST"},
    )
    assert list_response.status_code == 200, list_response.text
    assert list_response.json()["total"] == 0
    assert list_response.json()["claims"] == []


def test_graph_service_create_relation_rejects_unknown_relation_type(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )

    response = graph_client.post(
        f"/v1/spaces/{space_id}/relations",
        headers=admin_headers,
        json={
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": "PROTECTS_AGAINST",
            "assessment": _SUPPORTED_ASSESSMENT,
            "evidence_sentence": "MED13 protects against developmental delay.",
            "source_document_ref": "pmid:123",
            "metadata": {"origin": "test"},
        },
    )

    assert response.status_code == 400, response.text
    payload = response.json()["detail"]
    assert payload["code"] == "unknown_relation_type"
    assert payload["validation_state"] == "UNDEFINED"
    assert payload["persistability"] == "NON_PERSISTABLE"
    assert payload["next_actions"][0]["proposal_type"] == "RELATION_TYPE"


def test_graph_service_create_relation_rejects_missing_required_evidence(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )

    response = graph_client.post(
        f"/v1/spaces/{space_id}/relations",
        headers=admin_headers,
        json={
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": "ASSOCIATED_WITH",
            "assessment": _SUPPORTED_ASSESSMENT,
            "metadata": {"origin": "test"},
        },
    )

    assert response.status_code == 400, response.text
    payload = response.json()["detail"]
    assert payload["code"] == "insufficient_evidence"
    assert payload["validation_state"] == "INVALID_COMPONENTS"
    assert payload["persistability"] == "NON_PERSISTABLE"
    assert payload["next_actions"][0]["action"] == "attach_evidence"


def test_graph_service_create_relation_rejects_ai_generated_ungrounded_evidence(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )

    response = graph_client.post(
        f"/v1/spaces/{space_id}/relations",
        headers=admin_headers,
        json={
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": "ASSOCIATED_WITH",
            "assessment": _SUPPORTED_ASSESSMENT,
            "evidence_sentence": "MED13 was associated with developmental delay.",
            "evidence_sentence_source": "artana_generated",
            "source_document_ref": "harness_proposal:proposal-1",
            "metadata": {
                "origin": "graph_harness",
                "evidence_grounding": {
                    "anchor_start": 0,
                    "anchor_end": 47,
                    "match_kind": "exact",
                    "score": 1.0,
                    "subject_present": True,
                    "object_present": False,
                    "grounded": False,
                },
            },
        },
    )

    _assert_ai_persistence_quarantined(response)


def test_graph_service_create_relation_rejects_ai_generated_non_entailing_support(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )

    response = graph_client.post(
        f"/v1/spaces/{space_id}/relations",
        headers=admin_headers,
        json={
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": "ASSOCIATED_WITH",
            "assessment": _SUPPORTED_ASSESSMENT,
            "evidence_sentence": "MED13 was associated with developmental delay.",
            "evidence_sentence_source": "artana_generated",
            "source_document_ref": "harness_proposal:proposal-1",
            "metadata": {
                "origin": "graph_harness",
                "evidence_grounding": {
                    "anchor_start": 0,
                    "anchor_end": 47,
                    "match_kind": "exact",
                    "score": 1.0,
                    "subject_present": True,
                    "object_present": True,
                    "grounded": True,
                },
                "support_verification": {
                    "support": "NEUTRAL",
                    "rationale": "The sentence co-mentions both endpoints.",
                    "model_id": "artana-heuristic-support-v1",
                    "verification_method": "heuristic",
                },
            },
        },
    )

    _assert_ai_persistence_quarantined(response)


def test_graph_service_create_relation_rejects_review_only_trusted_ai_evidence(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )

    response = graph_client.post(
        f"/v1/spaces/{space_id}/relations",
        headers=admin_headers,
        json={
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": "ASSOCIATED_WITH",
            "assessment": _SUPPORTED_ASSESSMENT,
            "evidence_sentence": "MED13 was associated with developmental delay.",
            "evidence_sentence_source": "artana_generated",
            "evidence_tier": "trusted",
            "source_document_ref": "harness_proposal:proposal-1",
            "metadata": {
                "origin": "graph_harness",
                "agent_extraction_completed": True,
                "fallback_output_used": False,
                "evidence_grounding": {
                    "anchor_start": 0,
                    "anchor_end": 47,
                    "match_kind": "exact",
                    "score": 1.0,
                    "subject_present": True,
                    "object_present": True,
                    "grounded": True,
                },
                "support_verification": {
                    "support": "ENTAILS",
                    "rationale": "The sentence directly supports the relation.",
                    "model_id": "openai:gpt-5.6-luna",
                    "verification_method": "agent",
                },
                "entity_linking": {
                    "subject": {
                        "status": "linked",
                        "curie": "HGNC:22474",
                        "source": "verified_linker",
                        "trusted_identifier": True,
                    },
                    "object": {
                        "status": "linked",
                        "curie": "HP:0001263",
                        "source": "verified_linker",
                        "trusted_identifier": True,
                    },
                },
                "review_status": "review_only",
                "review_reason_codes": ["hedged_language"],
            },
        },
    )

    _assert_ai_persistence_quarantined(response)


def test_graph_service_create_relation_rejects_weak_reason_trusted_ai_evidence(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )

    response = graph_client.post(
        f"/v1/spaces/{space_id}/relations",
        headers=admin_headers,
        json={
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": "ASSOCIATED_WITH",
            "assessment": _SUPPORTED_ASSESSMENT,
            "evidence_sentence": "MED13 was associated with developmental delay.",
            "evidence_sentence_source": "artana_generated",
            "evidence_tier": "trusted",
            "source_document_ref": "harness_proposal:proposal-1",
            "metadata": {
                "origin": "graph_harness",
                "agent_extraction_completed": True,
                "fallback_output_used": False,
                "evidence_grounding": {
                    "anchor_start": 0,
                    "anchor_end": 47,
                    "match_kind": "exact",
                    "score": 1.0,
                    "subject_present": True,
                    "object_present": True,
                    "grounded": True,
                },
                "support_verification": {
                    "support": "ENTAILS",
                    "rationale": "The sentence directly supports the relation.",
                    "model_id": "openai:gpt-5.6-luna",
                    "verification_method": "agent",
                },
                "entity_linking": {
                    "subject": {
                        "status": "linked",
                        "curie": "HGNC:22474",
                        "source": "verified_linker",
                        "trusted_identifier": True,
                    },
                    "object": {
                        "status": "linked",
                        "curie": "HP:0001263",
                        "source": "verified_linker",
                        "trusted_identifier": True,
                    },
                },
                "review_reason_codes": ["hedged_language"],
            },
        },
    )

    _assert_ai_persistence_quarantined(response)


def test_graph_service_create_relation_rejects_review_only_triple(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )

    relation_type_response = graph_client.post(
        "/v1/dictionary/relation-types",
        headers=admin_headers,
        json={
            "id": "REVIEWS_WITH",
            "display_name": "Reviews With",
            "description": "Review-only relation for validation coverage.",
            "domain_context": "general",
            "is_directional": True,
            "source_ref": "graph-validation:test",
        },
    )
    assert relation_type_response.status_code == 201, relation_type_response.text

    constraint_response = graph_client.post(
        "/v1/dictionary/relation-constraints",
        headers=admin_headers,
        json={
            "source_type": "GENE",
            "relation_type": "REVIEWS_WITH",
            "target_type": "PHENOTYPE",
            "is_allowed": True,
            "requires_evidence": True,
            "profile": "REVIEW_ONLY",
            "source_ref": "graph-validation:test",
        },
    )
    assert constraint_response.status_code == 201, constraint_response.text

    response = graph_client.post(
        f"/v1/spaces/{space_id}/relations",
        headers=admin_headers,
        json={
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": "REVIEWS_WITH",
            "assessment": _SUPPORTED_ASSESSMENT,
            "evidence_sentence": "MED13 reviews with developmental delay.",
            "source_document_ref": "pmid:123",
            "metadata": {"origin": "test"},
        },
    )

    assert response.status_code == 400, response.text
    payload = response.json()["detail"]
    assert payload["code"] == "relation_constraint_review_only"
    assert payload["validation_state"] == "ALLOWED"
    assert payload["persistability"] == "NON_PERSISTABLE"


def test_graph_service_review_only_claim_remains_queryable_but_cannot_promote(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    source_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    target_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="PHENOTYPE",
        display_label="Developmental delay",
    )
    relation_type_response = graph_client.post(
        "/v1/dictionary/relation-types",
        headers=admin_headers,
        json={
            "id": "REVIEW_BLOCKS_PROMOTION",
            "display_name": "Review Blocks Promotion",
            "description": "Review-only relation for claim promotion hardening.",
            "domain_context": "general",
            "is_directional": True,
            "source_ref": f"graph-validation:review-type:{uuid4()}",
        },
    )
    assert relation_type_response.status_code == 201, relation_type_response.text
    constraint_response = graph_client.post(
        "/v1/dictionary/relation-constraints",
        headers=admin_headers,
        json={
            "source_type": "GENE",
            "relation_type": "REVIEW_BLOCKS_PROMOTION",
            "target_type": "PHENOTYPE",
            "is_allowed": True,
            "requires_evidence": True,
            "profile": "REVIEW_ONLY",
            "source_ref": f"graph-validation:review-constraint:{uuid4()}",
        },
    )
    assert constraint_response.status_code == 201, constraint_response.text

    claim_response = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        json={
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "relation_type": "REVIEW_BLOCKS_PROMOTION",
            "assessment": _SUPPORTED_ASSESSMENT,
            "claim_text": "MED13 needs review before canonical projection.",
            "evidence_sentence": "MED13 needs review before projection.",
            "source_document_ref": "pmid:review-only",
            "metadata": {"origin": "test"},
        },
    )
    assert claim_response.status_code == 201, claim_response.text
    claim_payload = claim_response.json()
    assert claim_payload["persistability"] == "NON_PERSISTABLE"
    claim_id = claim_payload["id"]

    claims_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        params={"relation_type": "REVIEW_BLOCKS_PROMOTION"},
    )
    assert claims_response.status_code == 200, claims_response.text
    assert claims_response.json()["total"] == 1

    resolve_response = graph_client.patch(
        f"/v1/spaces/{space_id}/claims/{claim_id}",
        headers=admin_headers,
        json={"claim_status": "RESOLVED"},
    )
    assert resolve_response.status_code == 400, resolve_response.text
    assert "NON_PERSISTABLE" in resolve_response.json()["detail"]

    relations_response = graph_client.get(
        f"/v1/spaces/{space_id}/relations",
        headers=admin_headers,
        params={"relation_type": "REVIEW_BLOCKS_PROMOTION"},
    )
    assert relations_response.status_code == 200, relations_response.text
    assert relations_response.json()["total"] == 0


def test_graph_service_validate_observation_reports_unknown_variable(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    subject_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )

    response = graph_client.post(
        f"/v1/spaces/{space_id}/validate/observation",
        headers=admin_headers,
        json={
            "subject_id": subject_id,
            "variable_id": "VAR_UNKNOWN",
            "value": "hello graph service",
            "observation_origin": "MANUAL",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["valid"] is False
    assert payload["code"] == "unknown_variable"
    assert payload["validation_state"] == "INVALID_COMPONENTS"
    assert payload["persistability"] == "NON_PERSISTABLE"
    assert payload["next_actions"][0]["action"] == "create_dictionary_proposal"
    assert payload["next_actions"][0]["proposal_type"] == "VARIABLE"
    assert (
        payload["next_actions"][0]["endpoint"] == "/v1/dictionary/proposals/variables"
    )
    assert payload["next_actions"][0]["payload"] == {
        "id": "VAR_UNKNOWN",
        "canonical_name": "var_unknown",
        "display_name": "Var Unknown",
        "data_type": "STRING",
        "domain_context": "general",
        "sensitivity": "INTERNAL",
        "constraints": {},
        "description": ("Proposed variable discovered during observation validation."),
        "rationale": (
            "Observation validation found a variable reference that is not yet approved in the dictionary."
        ),
        "evidence_payload": {
            "source": "graph_validation",
            "observation_origin": "MANUAL",
            "value_preview": "hello graph service",
            "inferred_data_type": "STRING",
        },
        "source_ref": "graph-validation:variable:var_unknown",
    }


def test_graph_service_validate_observation_next_action_payload_is_postable(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    subject_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )

    validation_response = graph_client.post(
        f"/v1/spaces/{space_id}/validate/observation",
        headers=admin_headers,
        json={
            "subject_id": subject_id,
            "variable_id": "VAR_UNKNOWN",
            "value": "hello graph service",
            "observation_origin": "MANUAL",
        },
    )
    assert validation_response.status_code == 200, validation_response.text
    next_action = validation_response.json()["next_actions"][0]

    proposal_response = graph_client.post(
        next_action["endpoint"],
        headers=admin_headers,
        json=next_action["payload"],
    )
    assert proposal_response.status_code == 201, proposal_response.text
    assert proposal_response.json()["variable_id"] == "VAR_UNKNOWN"


def test_graph_service_validate_observation_rejects_invalid_value_type(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    subject_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    _create_variable(
        graph_client,
        headers=admin_headers,
        variable_id="VAR_TEST_INTEGER",
        data_type="INTEGER",
    )

    response = graph_client.post(
        f"/v1/spaces/{space_id}/validate/observation",
        headers=admin_headers,
        json={
            "subject_id": subject_id,
            "variable_id": "VAR_TEST_INTEGER",
            "value": "not-a-number",
            "observation_origin": "MANUAL",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["valid"] is False
    assert payload["code"] == "invalid_value_for_variable"
    assert payload["validation_state"] == "INVALID_COMPONENTS"
    assert payload["persistability"] == "NON_PERSISTABLE"


def test_graph_service_validate_observation_rejects_invalid_date_value(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    subject_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    _create_variable(
        graph_client,
        headers=admin_headers,
        variable_id="VAR_TEST_DATE",
        data_type="DATE",
    )

    response = graph_client.post(
        f"/v1/spaces/{space_id}/validate/observation",
        headers=admin_headers,
        json={
            "subject_id": subject_id,
            "variable_id": "VAR_TEST_DATE",
            "value": "2026-99-99",
            "observation_origin": "MANUAL",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["valid"] is False
    assert payload["code"] == "invalid_value_for_variable"
    assert payload["validation_state"] == "INVALID_COMPONENTS"
    assert payload["persistability"] == "NON_PERSISTABLE"


def test_graph_service_create_observation_requires_provenance_for_imported_origin(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    subject_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    _create_variable(
        graph_client,
        headers=admin_headers,
        variable_id="VAR_TEST_NOTE",
    )

    response = graph_client.post(
        f"/v1/spaces/{space_id}/observations",
        headers=admin_headers,
        json={
            "subject_id": subject_id,
            "variable_id": "VAR_TEST_NOTE",
            "value": "hello graph service",
            "observation_origin": "IMPORTED",
        },
    )

    assert response.status_code == 400, response.text
    payload = response.json()["detail"]
    assert payload["code"] == "missing_provenance"
    assert payload["validation_state"] == "INVALID_COMPONENTS"
    assert payload["persistability"] == "NON_PERSISTABLE"


def test_graph_service_validate_observation_accepts_inline_provenance(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    subject_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    _create_variable(
        graph_client,
        headers=admin_headers,
        variable_id="VAR_TEST_NOTE",
    )

    response = graph_client.post(
        f"/v1/spaces/{space_id}/validate/observation",
        headers=admin_headers,
        json={
            "subject_id": subject_id,
            "variable_id": "VAR_TEST_NOTE",
            "value": "source-backed value",
            "observation_origin": "AI_AUTHORED",
            "provenance": {
                "source_type": "document_extraction",
                "mapping_method": "agent_source_measurement",
                "raw_input": {"source_measurement": {"literal_span": "0.125"}},
            },
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["valid"] is True
    assert payload["persistability"] == "PERSISTABLE"


def test_graph_service_create_observation_rejects_cross_space_provenance(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    other_space_id, _ = _create_space(graph_client)
    subject_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    _create_variable(
        graph_client,
        headers=admin_headers,
        variable_id="VAR_TEST_NOTE",
    )
    other_provenance_id = _create_provenance_record(space_id=other_space_id)

    response = graph_client.post(
        f"/v1/spaces/{space_id}/observations",
        headers=admin_headers,
        json={
            "subject_id": subject_id,
            "variable_id": "VAR_TEST_NOTE",
            "value": "hello graph service",
            "observation_origin": "IMPORTED",
            "provenance_id": other_provenance_id,
        },
    )

    assert response.status_code == 400, response.text
    payload = response.json()["detail"]
    assert payload["code"] == "cross_space_provenance"
    assert payload["validation_state"] == "INVALID_COMPONENTS"
    assert payload["persistability"] == "NON_PERSISTABLE"


def test_graph_service_create_observation_accepts_imported_origin_with_provenance(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)
    subject_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=admin_headers,
        entity_type="GENE",
        display_label="MED13",
    )
    _create_variable(
        graph_client,
        headers=admin_headers,
        variable_id="VAR_TEST_NOTE",
    )
    provenance_id = _create_provenance_record(space_id=space_id)

    response = graph_client.post(
        f"/v1/spaces/{space_id}/observations",
        headers=admin_headers,
        json={
            "subject_id": subject_id,
            "variable_id": "VAR_TEST_NOTE",
            "value": "hello graph service",
            "observation_origin": "IMPORTED",
            "provenance_id": provenance_id,
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["value_text"] == "hello graph service"
    assert payload["provenance_id"] == provenance_id
