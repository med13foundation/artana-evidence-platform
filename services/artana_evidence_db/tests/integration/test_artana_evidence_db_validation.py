from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from artana_evidence_db import database as graph_database
from artana_evidence_db.app import create_app
from artana_evidence_db.kernel_repositories import (
    SqlAlchemyKernelRelationClaimRepository,
)
from artana_evidence_db.provenance_model import ProvenanceModel
from artana_evidence_db.tests.support import (
    build_graph_admin_headers,
    reset_graph_service_database,
)
from fastapi.testclient import TestClient

_SUPPORTED_ASSESSMENT = {
    "support_band": "SUPPORTED",
    "grounding_level": "SPAN",
    "mapping_status": "RESOLVED",
    "speculation_level": "DIRECT",
    "confidence_rationale": "Synthetic validation evidence supports the relation.",
}


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


def _create_entity(
    graph_client: TestClient,
    *,
    space_id: str,
    headers: dict[str, str],
    entity_type: str,
    display_label: str,
) -> str:
    response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": entity_type,
            "display_label": display_label,
            "aliases": [],
            "metadata": {},
            "identifiers": {},
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    return str(payload["entity"]["id"])


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
) -> str:
    with graph_database.SessionLocal() as session:
        claim = SqlAlchemyKernelRelationClaimRepository(session).create(
            research_space_id=space_id,
            source_document_id=None,
            source_document_ref=source_document_ref,
            source_ref=source_ref,
            agent_run_id="graph-validation-seed",
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


def test_graph_service_create_claim_uses_validator_for_unknown_relation_type(
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

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["relation_type"] == "PROTECTS_AGAINST"
    assert payload["validation_state"] == "UNDEFINED"
    assert payload["validation_reason"] == "relation_type_not_found_in_dictionary"
    assert payload["persistability"] == "NON_PERSISTABLE"


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
    assert (
        forbidden_constraint_response.status_code == 201
    ), forbidden_constraint_response.text

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
    assert create_response.status_code == 400, create_response.text
    assert create_response.json()["detail"]["code"] == "missing_ai_provenance"

    request_payload["ai_provenance"] = {
        "model_id": "artana-kernel",
        "model_version": "test",
        "prompt_id": "graph-validation-ai-claim",
        "prompt_version": "v1",
        "input_hash": uuid4().hex,
        "rationale": "The sentence supports the relation.",
        "evidence_references": ["pmid:123456"],
    }
    accepted_response = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        json=request_payload,
    )
    assert accepted_response.status_code == 201, accepted_response.text
    accepted_payload = accepted_response.json()
    assert accepted_payload["metadata"]["ai_provenance"]["model_id"] == "artana-kernel"


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


def test_graph_service_non_persistable_claim_is_queryable_but_not_promotable(
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
    assert create_response.status_code == 201, create_response.text
    claim_id = create_response.json()["id"]
    assert create_response.json()["persistability"] == "NON_PERSISTABLE"

    list_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims",
        headers=admin_headers,
        params={"relation_type": "PROTECTS_AGAINST"},
    )
    assert list_response.status_code == 200, list_response.text
    assert list_response.json()["total"] == 1
    assert list_response.json()["claims"][0]["id"] == claim_id

    resolve_response = graph_client.patch(
        f"/v1/spaces/{space_id}/claims/{claim_id}",
        headers=admin_headers,
        json={"claim_status": "RESOLVED"},
    )
    assert resolve_response.status_code == 400, resolve_response.text
    assert (
        resolve_response.json()["detail"]
        == "Claim cannot be resolved yet because it is NON_PERSISTABLE. Use Needs Mapping or Reject."
    )


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
        payload["next_actions"][0]["endpoint"]
        == "/v1/dictionary/proposals/variables"
    )
    assert payload["next_actions"][0]["payload"] == {
        "id": "VAR_UNKNOWN",
        "canonical_name": "var_unknown",
        "display_name": "Var Unknown",
        "data_type": "STRING",
        "domain_context": "general",
        "sensitivity": "INTERNAL",
        "constraints": {},
        "description": (
            "Proposed variable discovered during observation validation."
        ),
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
