"""Unit tests for graph explorer status mapping."""

from __future__ import annotations

from uuid import UUID, uuid4

from artana_evidence_api.app import create_app
from artana_evidence_api.dependencies import (
    get_graph_api_gateway,
    get_research_space_store,
)
from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.research_space_store import HarnessResearchSpaceStore
from fastapi.testclient import TestClient

_TEST_USER_ID = "11111111-1111-1111-1111-111111111111"
_TEST_USER_EMAIL = "graph-harness-graph-explorer@example.com"


def _auth_headers() -> dict[str, str]:
    return {
        "X-TEST-USER-ID": _TEST_USER_ID,
        "X-TEST-USER-EMAIL": _TEST_USER_EMAIL,
        "X-TEST-USER-ROLE": "researcher",
    }


class _MissingReferenceGraphGateway:
    def list_claims_by_entity(
        self,
        *,
        space_id: UUID | str,
        entity_id: UUID | str,
        offset: int = 0,
        limit: int = 50,
    ) -> object:
        del space_id, entity_id, offset, limit
        raise GraphServiceClientError(
            "Graph entity not found.",
            status_code=404,
            detail="Entity not found.",
        )

    def list_claim_evidence(
        self,
        *,
        space_id: UUID | str,
        claim_id: UUID | str,
    ) -> object:
        del space_id, claim_id
        raise GraphServiceClientError(
            "Graph claim not found.",
            status_code=404,
            detail="Claim not found.",
        )

    def get_graph_document(self, *, space_id: UUID | str, request: object) -> object:
        del space_id, request
        raise AssertionError("Seed validation should reject this request first.")


def _build_client() -> tuple[TestClient, str]:
    app = create_app()
    graph_gateway = _MissingReferenceGraphGateway()
    research_space_store = HarnessResearchSpaceStore()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Graph Explorer Space",
        description="Owned test space for graph explorer routes.",
    )
    app.dependency_overrides[get_graph_api_gateway] = lambda: graph_gateway
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    return TestClient(app), space.id


def test_list_claims_by_entity_returns_404_for_missing_entity() -> None:
    client, space_id = _build_client()

    response = client.get(
        f"/v1/spaces/{space_id}/graph-explorer/entities/{uuid4()}/claims",
        headers=_auth_headers(),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Entity not found."


def test_list_claim_evidence_returns_404_for_missing_claim() -> None:
    client, space_id = _build_client()

    response = client.get(
        f"/v1/spaces/{space_id}/graph-explorer/claims/{uuid4()}/evidence",
        headers=_auth_headers(),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Claim not found."


def test_get_graph_document_rejects_seeded_request_without_seeds() -> None:
    client, space_id = _build_client()

    response = client.post(
        f"/v1/spaces/{space_id}/graph-explorer/document",
        headers=_auth_headers(),
        json={
            "mode": "seeded",
            "seed_entity_ids": [],
            "depth": 2,
            "top_k": 25,
            "relation_types": None,
            "curation_statuses": None,
            "max_nodes": 180,
            "max_edges": 260,
            "include_claims": True,
            "include_evidence": True,
            "max_claims": 250,
            "evidence_limit_per_claim": 3,
        },
    )

    assert response.status_code == 422
    assert "seed_entity_ids must not be empty" in response.text
