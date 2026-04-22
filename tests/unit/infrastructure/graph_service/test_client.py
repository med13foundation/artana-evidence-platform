"""Unit tests for the standalone graph-service HTTP client."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from artana_evidence_db.graph_api_schemas.claim_graph_schemas import (
    ClaimParticipantBackfillRequest,
    ClaimRelationCreateRequest,
    ClaimRelationReviewUpdateRequest,
)
from artana_evidence_db.graph_api_schemas.concept_schemas import (
    ConceptDecisionResponse,
    ConceptSetListResponse,
    ConceptSetResponse,
)
from artana_evidence_db.graph_api_schemas.hypothesis_schemas import (
    CreateManualHypothesisRequest,
)
from artana_evidence_db.graph_api_schemas.kernel_graph_view_schemas import (
    KernelClaimMechanismChainResponse,
    KernelGraphDomainViewResponse,
)
from artana_evidence_db.graph_api_schemas.kernel_schemas import (
    KernelEntityCreateRequest,
    KernelEntityUpdateRequest,
    KernelGraphDocumentRequest,
    KernelGraphSubgraphRequest,
    KernelObservationCreateRequest,
    KernelRelationClaimCreateRequest,
    KernelRelationClaimTriageRequest,
    KernelRelationCreateRequest,
    KernelRelationCurationUpdateRequest,
    KernelRelationSuggestionRequest,
)

from src.infrastructure.platform_graph.graph_service import (
    GraphServiceClient,
    GraphServiceClientConfig,
    GraphServiceClientError,
)
from src.infrastructure.platform_graph.graph_service.client import (
    GraphSpaceSyncMembershipPayload,
)

_SUPPORTED_ASSESSMENT = {
    "support_band": "SUPPORTED",
    "grounding_level": "SPAN",
    "mapping_status": "RESOLVED",
    "speculation_level": "DIRECT",
    "confidence_rationale": "Synthetic client evidence supports the graph write.",
}


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def test_graph_service_client_lists_relations_with_auth_header() -> None:
    space_id = uuid4()
    relation_id = uuid4()
    source_id = uuid4()
    target_id = uuid4()
    timestamp = _iso_now()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == f"/v1/spaces/{space_id}/relations"
        assert request.headers["Authorization"] == "Bearer test-token"
        payload = {
            "relations": [
                {
                    "id": str(relation_id),
                    "research_space_id": str(space_id),
                    "source_id": str(source_id),
                    "relation_type": "ASSOCIATED_WITH",
                    "target_id": str(target_id),
                    "confidence": 0.91,
                    "aggregate_confidence": 0.91,
                    "source_count": 1,
                    "highest_evidence_tier": "LITERATURE",
                    "curation_status": "ACCEPTED",
                    "evidence_summary": "Client test relation",
                    "evidence_sentence": None,
                    "evidence_sentence_source": None,
                    "evidence_sentence_confidence": None,
                    "evidence_sentence_rationale": None,
                    "paper_links": [],
                    "provenance_id": None,
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            ],
            "total": 1,
            "offset": 0,
            "limit": 100,
        }
        return httpx.Response(status_code=200, json=payload)

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://graph-service.test",
        transport=transport,
    )
    client = GraphServiceClient(
        GraphServiceClientConfig(
            base_url="https://graph-service.test",
            default_headers={"Authorization": "Bearer test-token"},
        ),
        client=http_client,
    )

    response = client.list_relations(space_id=space_id)

    assert response.total == 1
    assert response.relations[0].id == relation_id
    http_client.close()


def test_graph_service_client_posts_relation_suggestion_request() -> None:
    space_id = uuid4()
    source_entity_id = uuid4()
    target_entity_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/spaces/{space_id}/relations/suggestions"
        assert request.headers["Authorization"] == "Bearer test-token"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["source_entity_ids"] == [str(source_entity_id)]
        assert payload["limit_per_source"] == 3
        assert payload["min_score"] == 0.75
        assert payload["exclude_existing_relations"] is True
        return httpx.Response(
            status_code=200,
            json={
                "suggestions": [
                    {
                        "source_entity_id": str(source_entity_id),
                        "target_entity_id": str(target_entity_id),
                        "relation_type": "SUGGESTS",
                        "final_score": 0.86,
                        "score_breakdown": {
                            "vector_score": 0.84,
                            "graph_overlap_score": 0.78,
                            "relation_prior_score": 0.65,
                        },
                        "constraint_check": {
                            "passed": True,
                            "source_entity_type": "GENE",
                            "relation_type": "SUGGESTS",
                            "target_entity_type": "GENE",
                        },
                    },
                ],
                "total": 1,
                "limit_per_source": 3,
                "min_score": 0.75,
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://graph-service.test",
        transport=transport,
    )
    client = GraphServiceClient(
        GraphServiceClientConfig(
            base_url="https://graph-service.test",
            default_headers={"Authorization": "Bearer test-token"},
        ),
        client=http_client,
    )

    response = client.suggest_relations(
        space_id=space_id,
        request=KernelRelationSuggestionRequest(
            source_entity_ids=[source_entity_id],
            limit_per_source=3,
            min_score=0.75,
            exclude_existing_relations=True,
        ),
    )

    assert response.total == 1
    assert response.suggestions[0].source_entity_id == source_entity_id
    assert response.suggestions[0].target_entity_id == target_entity_id
    http_client.close()


def test_graph_service_client_manages_graph_space_registry() -> None:
    space_id = uuid4()
    owner_id = uuid4()
    timestamp = _iso_now()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            payload = json.loads(request.content.decode("utf-8"))
            assert request.url.path == f"/v1/admin/spaces/{space_id}"
            assert payload == {
                "slug": "graph-space",
                "name": "Graph Space",
                "description": "Graph registry entry",
                "owner_id": str(owner_id),
                "status": "active",
                "settings": {"review_threshold": 0.73},
            }
            return httpx.Response(
                status_code=200,
                json={
                    "id": str(space_id),
                    "slug": "graph-space",
                    "name": "Graph Space",
                    "description": "Graph registry entry",
                    "owner_id": str(owner_id),
                    "status": "active",
                    "settings": {"review_threshold": 0.73},
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            )

        if request.url.path == "/v1/admin/spaces":
            assert request.method == "GET"
            return httpx.Response(
                status_code=200,
                json={
                    "spaces": [
                        {
                            "id": str(space_id),
                            "slug": "graph-space",
                            "name": "Graph Space",
                            "description": "Graph registry entry",
                            "owner_id": str(owner_id),
                            "status": "active",
                            "settings": {"review_threshold": 0.73},
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        },
                    ],
                    "total": 1,
                },
            )

        assert request.method == "GET"
        assert request.url.path == f"/v1/admin/spaces/{space_id}"
        return httpx.Response(
            status_code=200,
            json={
                "id": str(space_id),
                "slug": "graph-space",
                "name": "Graph Space",
                "description": "Graph registry entry",
                "owner_id": str(owner_id),
                "status": "active",
                "settings": {"review_threshold": 0.73},
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://graph-service.test",
        transport=transport,
    )
    client = GraphServiceClient(
        GraphServiceClientConfig(base_url="https://graph-service.test"),
        client=http_client,
    )

    created = client.upsert_space(
        space_id=space_id,
        slug="graph-space",
        name="Graph Space",
        description="Graph registry entry",
        owner_id=owner_id,
        settings={"review_threshold": 0.73},
    )
    listed = client.list_spaces()
    fetched = client.get_space(space_id=space_id)

    assert created.id == space_id
    assert listed.total == 1
    assert listed.spaces[0].id == space_id
    assert fetched.owner_id == owner_id
    http_client.close()


def test_graph_service_client_manages_graph_space_memberships() -> None:
    space_id = uuid4()
    user_id = uuid4()
    timestamp = _iso_now()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            payload = json.loads(request.content.decode("utf-8"))
            assert (
                request.url.path == f"/v1/admin/spaces/{space_id}/memberships/{user_id}"
            )
            assert payload == {
                "role": "curator",
                "invited_by": None,
                "invited_at": None,
                "joined_at": None,
                "is_active": True,
            }
            return httpx.Response(
                status_code=200,
                json={
                    "id": str(uuid4()),
                    "space_id": str(space_id),
                    "user_id": str(user_id),
                    "role": "curator",
                    "invited_by": None,
                    "invited_at": None,
                    "joined_at": None,
                    "is_active": True,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            )

        assert request.method == "GET"
        assert request.url.path == f"/v1/admin/spaces/{space_id}/memberships"
        return httpx.Response(
            status_code=200,
            json={
                "memberships": [
                    {
                        "id": str(uuid4()),
                        "space_id": str(space_id),
                        "user_id": str(user_id),
                        "role": "curator",
                        "invited_by": None,
                        "invited_at": None,
                        "joined_at": None,
                        "is_active": True,
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    },
                ],
                "total": 1,
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://graph-service.test",
        transport=transport,
    )
    client = GraphServiceClient(
        GraphServiceClientConfig(base_url="https://graph-service.test"),
        client=http_client,
    )

    created = client.upsert_space_membership(
        space_id=space_id,
        user_id=user_id,
        role="curator",
    )
    listed = client.list_space_memberships(space_id=space_id)

    assert created.user_id == user_id
    assert listed.total == 1
    assert listed.memberships[0].role == "curator"
    http_client.close()


def test_graph_service_client_manages_admin_concept_routes() -> None:
    space_id = uuid4()
    concept_set_id = uuid4()
    timestamp = _iso_now()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            assert request.url.path == f"/v1/spaces/{space_id}/concepts/sets"
            assert request.url.params["include_inactive"] == "true"
            return httpx.Response(
                status_code=200,
                json={
                    "concept_sets": [
                        {
                            "id": str(concept_set_id),
                            "research_space_id": str(space_id),
                            "name": "Mechanism Concepts",
                            "slug": "mechanism-concepts",
                            "domain_context": "general",
                            "description": "Concept client test",
                            "review_status": "ACTIVE",
                            "is_active": True,
                            "created_by": "manual:test",
                            "source_ref": "test:concept-client",
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        },
                    ],
                    "total": 1,
                },
            )

        if request.method == "POST":
            payload = json.loads(request.content.decode("utf-8"))
            assert request.url.path == f"/v1/spaces/{space_id}/concepts/sets"
            assert payload == {
                "name": "Mechanism Concepts",
                "slug": "mechanism-concepts",
                "domain_context": "general",
                "description": "Concept client test",
                "source_ref": "test:concept-client",
            }
            return httpx.Response(
                status_code=201,
                json={
                    "id": str(concept_set_id),
                    "research_space_id": str(space_id),
                    "name": "Mechanism Concepts",
                    "slug": "mechanism-concepts",
                    "domain_context": "general",
                    "description": "Concept client test",
                    "review_status": "ACTIVE",
                    "is_active": True,
                    "created_by": "manual:test",
                    "source_ref": "test:concept-client",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            )

        payload = json.loads(request.content.decode("utf-8"))
        assert request.method == "PATCH"
        assert (
            request.url.path
            == f"/v1/spaces/{space_id}/concepts/decisions/decision-123/status"
        )
        assert payload == {"decision_status": "APPROVED"}
        return httpx.Response(
            status_code=200,
            json={
                "id": "decision-123",
                "research_space_id": str(space_id),
                "concept_set_id": None,
                "concept_member_id": None,
                "concept_link_id": None,
                "decision_type": "CREATE",
                "decision_status": "APPROVED",
                "proposed_by": "manual:test",
                "decided_by": "manual:test",
                "confidence": 0.83,
                "rationale": "Concept client test",
                "evidence_payload": {},
                "decision_payload": {},
                "harness_outcome": "PASS",
                "decided_at": timestamp,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://graph-service.test",
        transport=transport,
    )
    client = GraphServiceClient(
        GraphServiceClientConfig(base_url="https://graph-service.test"),
        client=http_client,
    )

    listed = client.list_concept_sets(space_id=space_id, include_inactive=True)
    created = client.create_concept_set(
        space_id=space_id,
        name="Mechanism Concepts",
        slug="mechanism-concepts",
        domain_context="general",
        description="Concept client test",
        source_ref="test:concept-client",
    )
    updated = client.set_concept_decision_status(
        space_id=space_id,
        decision_id="decision-123",
        decision_status="APPROVED",
    )

    assert isinstance(listed, ConceptSetListResponse)
    assert listed.total == 1
    assert isinstance(created, ConceptSetResponse)
    assert created.id == str(concept_set_id)
    assert isinstance(updated, ConceptDecisionResponse)
    assert updated.id == "decision-123"
    http_client.close()


def test_graph_service_client_syncs_graph_space_snapshot() -> None:
    space_id = uuid4()
    owner_id = uuid4()
    member_id = uuid4()
    timestamp = _iso_now()
    serialized_timestamp = (
        datetime.fromisoformat(timestamp)
        .astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/admin/spaces/{space_id}/sync"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload == {
            "slug": "graph-sync-space",
            "name": "Graph Sync Space",
            "description": "Atomic graph sync",
            "owner_id": str(owner_id),
            "status": "active",
            "settings": {"review_threshold": 0.82},
            "sync_source": "platform_control_plane",
            "sync_fingerprint": "abc123",
            "source_updated_at": serialized_timestamp,
            "memberships": [
                {
                    "user_id": str(member_id),
                    "role": "researcher",
                    "invited_by": None,
                    "invited_at": None,
                    "joined_at": None,
                    "is_active": True,
                },
            ],
        }
        return httpx.Response(
            status_code=200,
            json={
                "applied": True,
                "space": {
                    "id": str(space_id),
                    "slug": "graph-sync-space",
                    "name": "Graph Sync Space",
                    "description": "Atomic graph sync",
                    "owner_id": str(owner_id),
                    "status": "active",
                    "settings": {"review_threshold": 0.82},
                    "sync_source": "platform_control_plane",
                    "sync_fingerprint": "abc123",
                    "source_updated_at": timestamp,
                    "last_synced_at": timestamp,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
                "memberships": [
                    {
                        "id": str(uuid4()),
                        "space_id": str(space_id),
                        "user_id": str(member_id),
                        "role": "researcher",
                        "invited_by": None,
                        "invited_at": None,
                        "joined_at": None,
                        "is_active": True,
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    },
                ],
                "total_memberships": 1,
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://graph-service.test",
        transport=transport,
    )
    client = GraphServiceClient(
        GraphServiceClientConfig(base_url="https://graph-service.test"),
        client=http_client,
    )

    synced = client.sync_space(
        space_id=space_id,
        slug="graph-sync-space",
        name="Graph Sync Space",
        description="Atomic graph sync",
        owner_id=owner_id,
        settings={"review_threshold": 0.82},
        sync_fingerprint="abc123",
        source_updated_at=datetime.fromisoformat(timestamp),
        memberships=[
            GraphSpaceSyncMembershipPayload(
                user_id=member_id,
                role="researcher",
            ),
        ],
    )

    assert synced.applied is True
    assert synced.space.id == space_id
    assert synced.total_memberships == 1
    assert synced.memberships[0].user_id == member_id
    http_client.close()


def test_graph_service_client_creates_and_curates_relations() -> None:
    space_id = uuid4()
    relation_id = uuid4()
    source_id = uuid4()
    target_id = uuid4()
    timestamp = _iso_now()

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        if request.method == "POST":
            assert request.url.path == f"/v1/spaces/{space_id}/relations"
            assert payload["source_id"] == str(source_id)
            assert payload["relation_type"] == "ASSOCIATED_WITH"
            assert payload["target_id"] == str(target_id)
            assert "confidence" not in payload
            assert payload["assessment"] == _SUPPORTED_ASSESSMENT
            assert payload["evidence_summary"] == "Manual edge"
            assert (
                payload["evidence_sentence"]
                == "MED13 is associated with developmental delay."
            )
            assert payload["evidence_sentence_source"] == "verbatim_span"
            assert payload["evidence_sentence_confidence"] == "high"
            assert payload["evidence_sentence_rationale"] is None
            assert payload["evidence_tier"] == "COMPUTATIONAL"
            assert payload["provenance_id"] is None
            assert payload["source_document_ref"] is None
            return httpx.Response(
                status_code=201,
                json={
                    "id": str(relation_id),
                    "research_space_id": str(space_id),
                    "source_id": str(source_id),
                    "relation_type": "ASSOCIATED_WITH",
                    "target_id": str(target_id),
                    "confidence": 0.88,
                    "aggregate_confidence": 0.88,
                    "source_count": 1,
                    "highest_evidence_tier": "COMPUTATIONAL",
                    "curation_status": "DRAFT",
                    "evidence_summary": "Manual edge",
                    "evidence_sentence": "MED13 is associated with developmental delay.",
                    "evidence_sentence_source": "verbatim_span",
                    "evidence_sentence_confidence": "high",
                    "evidence_sentence_rationale": None,
                    "paper_links": [],
                    "provenance_id": None,
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            )

        assert request.method == "PUT"
        assert request.url.path == f"/v1/spaces/{space_id}/relations/{relation_id}"
        assert payload == {"curation_status": "APPROVED"}
        return httpx.Response(
            status_code=200,
            json={
                "id": str(relation_id),
                "research_space_id": str(space_id),
                "source_id": str(source_id),
                "relation_type": "ASSOCIATED_WITH",
                "target_id": str(target_id),
                "confidence": 0.88,
                "aggregate_confidence": 0.88,
                "source_count": 1,
                "highest_evidence_tier": "COMPUTATIONAL",
                "curation_status": "APPROVED",
                "evidence_summary": "Manual edge",
                "evidence_sentence": "MED13 is associated with developmental delay.",
                "evidence_sentence_source": "verbatim_span",
                "evidence_sentence_confidence": "high",
                "evidence_sentence_rationale": None,
                "paper_links": [],
                "provenance_id": None,
                "reviewed_by": None,
                "reviewed_at": None,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://graph-service.test",
        transport=transport,
    )
    client = GraphServiceClient(
        GraphServiceClientConfig(base_url="https://graph-service.test"),
        client=http_client,
    )

    created = client.create_relation(
        space_id=space_id,
        request=KernelRelationCreateRequest(
            source_id=source_id,
            relation_type="ASSOCIATED_WITH",
            target_id=target_id,
            assessment=_SUPPORTED_ASSESSMENT,
            evidence_summary="Manual edge",
            evidence_sentence="MED13 is associated with developmental delay.",
            evidence_sentence_source="verbatim_span",
            evidence_sentence_confidence="high",
            evidence_tier="COMPUTATIONAL",
        ),
    )
    updated = client.update_relation_curation_status(
        space_id=space_id,
        relation_id=relation_id,
        request=KernelRelationCurationUpdateRequest(curation_status="APPROVED"),
    )

    assert created.id == relation_id
    assert updated.curation_status == "APPROVED"
    http_client.close()


def test_graph_service_client_lists_and_gets_provenance() -> None:
    space_id = uuid4()
    provenance_id = uuid4()
    timestamp = _iso_now()

    def handler(request: httpx.Request) -> httpx.Response:
        if (
            request.method == "GET"
            and request.url.path == f"/v1/spaces/{space_id}/provenance"
        ):
            assert request.url.params["source_type"] == "PUBMED"
            return httpx.Response(
                status_code=200,
                json={
                    "provenance": [
                        {
                            "id": str(provenance_id),
                            "research_space_id": str(space_id),
                            "source_type": "PUBMED",
                            "source_ref": "pmid:123456",
                            "extraction_run_id": "run-123",
                            "mapping_method": "manual",
                            "mapping_confidence": 0.94,
                            "agent_model": "gpt-5",
                            "raw_input": {"title": "Graph provenance fixture"},
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        },
                    ],
                    "total": 1,
                    "offset": 0,
                    "limit": 50,
                },
            )

        assert request.method == "GET"
        assert request.url.path == f"/v1/spaces/{space_id}/provenance/{provenance_id}"
        return httpx.Response(
            status_code=200,
            json={
                "id": str(provenance_id),
                "research_space_id": str(space_id),
                "source_type": "PUBMED",
                "source_ref": "pmid:123456",
                "extraction_run_id": "run-123",
                "mapping_method": "manual",
                "mapping_confidence": 0.94,
                "agent_model": "gpt-5",
                "raw_input": {"title": "Graph provenance fixture"},
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://graph-service.test",
        transport=transport,
    )
    client = GraphServiceClient(
        GraphServiceClientConfig(base_url="https://graph-service.test"),
        client=http_client,
    )

    records = client.list_provenance(space_id=space_id, source_type="PUBMED")
    record = client.get_provenance(space_id=space_id, provenance_id=provenance_id)

    assert records.total == 1
    assert records.provenance[0].id == provenance_id
    assert record.id == provenance_id
    assert record.source_ref == "pmid:123456"
    http_client.close()


def test_graph_service_client_posts_subgraph_request() -> None:
    space_id = uuid4()
    source_id = uuid4()
    target_id = uuid4()
    relation_id = uuid4()
    timestamp = _iso_now()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/spaces/{space_id}/graph/subgraph"
        assert request.headers["Content-Type"] == "application/json"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["mode"] == "seeded"
        assert payload["seed_entity_ids"] == [str(source_id)]
        response_payload = {
            "nodes": [
                {
                    "id": str(source_id),
                    "research_space_id": str(space_id),
                    "entity_type": "GENE",
                    "display_label": "MED13",
                    "metadata": {},
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
                {
                    "id": str(target_id),
                    "research_space_id": str(space_id),
                    "entity_type": "PHENOTYPE",
                    "display_label": "Developmental delay",
                    "metadata": {},
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            ],
            "edges": [
                {
                    "id": str(relation_id),
                    "research_space_id": str(space_id),
                    "source_id": str(source_id),
                    "relation_type": "ASSOCIATED_WITH",
                    "target_id": str(target_id),
                    "confidence": 0.88,
                    "aggregate_confidence": 0.88,
                    "source_count": 1,
                    "highest_evidence_tier": "LITERATURE",
                    "curation_status": "ACCEPTED",
                    "evidence_summary": "Client test relation",
                    "evidence_sentence": None,
                    "evidence_sentence_source": None,
                    "evidence_sentence_confidence": None,
                    "evidence_sentence_rationale": None,
                    "paper_links": [],
                    "provenance_id": None,
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            ],
            "meta": {
                "mode": "seeded",
                "seed_entity_ids": [str(source_id)],
                "requested_depth": 1,
                "requested_top_k": 10,
                "pre_cap_node_count": 2,
                "pre_cap_edge_count": 1,
                "truncated_nodes": False,
                "truncated_edges": False,
            },
        }
        return httpx.Response(status_code=200, json=response_payload)

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://graph-service.test",
        transport=transport,
    )
    client = GraphServiceClient(
        GraphServiceClientConfig(base_url="https://graph-service.test"),
        client=http_client,
    )

    response = client.get_subgraph(
        space_id=space_id,
        request=KernelGraphSubgraphRequest(
            mode="seeded",
            seed_entity_ids=[source_id],
            depth=1,
            top_k=10,
            max_nodes=20,
            max_edges=20,
        ),
    )

    assert len(response.nodes) == 2
    assert len(response.edges) == 1
    http_client.close()


def test_graph_service_client_fetches_neighborhood() -> None:
    space_id = uuid4()
    source_id = uuid4()
    target_id = uuid4()
    relation_id = uuid4()
    timestamp = _iso_now()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert (
            request.url.path == f"/v1/spaces/{space_id}/graph/neighborhood/{source_id}"
        )
        assert request.url.params["depth"] == "2"
        return httpx.Response(
            status_code=200,
            json={
                "nodes": [
                    {
                        "id": str(source_id),
                        "research_space_id": str(space_id),
                        "entity_type": "GENE",
                        "display_label": "MED13",
                        "metadata": {},
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    },
                    {
                        "id": str(target_id),
                        "research_space_id": str(space_id),
                        "entity_type": "PHENOTYPE",
                        "display_label": "Cardiomyopathy",
                        "metadata": {},
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    },
                ],
                "edges": [
                    {
                        "id": str(relation_id),
                        "research_space_id": str(space_id),
                        "source_id": str(source_id),
                        "relation_type": "ASSOCIATED_WITH",
                        "target_id": str(target_id),
                        "confidence": 0.8,
                        "aggregate_confidence": 0.8,
                        "source_count": 1,
                        "highest_evidence_tier": "LITERATURE",
                        "curation_status": "DRAFT",
                        "evidence_summary": None,
                        "evidence_sentence": None,
                        "evidence_sentence_source": None,
                        "evidence_sentence_confidence": None,
                        "evidence_sentence_rationale": None,
                        "paper_links": [],
                        "provenance_id": None,
                        "reviewed_by": None,
                        "reviewed_at": None,
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    },
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://graph-service.test",
        transport=transport,
    )
    client = GraphServiceClient(
        GraphServiceClientConfig(base_url="https://graph-service.test"),
        client=http_client,
    )

    response = client.get_neighborhood(
        space_id=space_id,
        entity_id=source_id,
        depth=2,
    )

    assert len(response.nodes) == 2
    assert len(response.edges) == 1
    http_client.close()


def test_graph_service_client_lists_relations_with_extended_filters() -> None:
    space_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == f"/v1/spaces/{space_id}/relations"
        params = request.url.params
        assert params["relation_type"] == "ASSOCIATED_WITH"
        assert params["curation_status"] == "DRAFT"
        assert params["validation_state"] == "ALLOWED"
        assert params["source_document_id"] == "doc-123"
        assert params["certainty_band"] == "HIGH"
        assert params["node_query"] == "MED13"
        assert params.get_list("node_ids") == [
            "11111111-1111-1111-1111-111111111111",
            "22222222-2222-2222-2222-222222222222",
        ]
        assert params["offset"] == "4"
        assert params["limit"] == "9"
        return httpx.Response(
            status_code=200,
            json={"relations": [], "total": 0, "offset": 4, "limit": 9},
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://graph-service.test",
        transport=transport,
    )
    client = GraphServiceClient(
        GraphServiceClientConfig(base_url="https://graph-service.test"),
        client=http_client,
    )

    response = client.list_relations(
        space_id=space_id,
        relation_type="ASSOCIATED_WITH",
        curation_status="DRAFT",
        validation_state="ALLOWED",
        source_document_id="doc-123",
        certainty_band="HIGH",
        node_query="MED13",
        node_ids=[
            "11111111-1111-1111-1111-111111111111",
            "22222222-2222-2222-2222-222222222222",
        ],
        offset=4,
        limit=9,
    )

    assert response.total == 0
    http_client.close()


def test_graph_service_client_supports_claim_workflows() -> None:
    space_id = uuid4()
    claim_id = uuid4()
    relation_id = uuid4()
    timestamp = _iso_now()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == f"/v1/spaces/{space_id}/claims":
            if request.method == "GET":
                assert request.url.params["claim_status"] == "OPEN"
                assert request.url.params["validation_state"] == "ALLOWED"
                assert request.url.params["persistability"] == "PERSISTABLE"
                assert request.url.params["polarity"] == "SUPPORT"
                assert request.url.params["certainty_band"] == "MEDIUM"
                return httpx.Response(
                    status_code=200,
                    json={
                        "claims": [
                            {
                                "id": str(claim_id),
                                "research_space_id": str(space_id),
                                "source_document_id": None,
                                "agent_run_id": None,
                                "source_type": "GENE",
                                "relation_type": "ASSOCIATED_WITH",
                                "target_type": "PHENOTYPE",
                                "source_label": "MED13",
                                "target_label": "Developmental delay",
                                "confidence": 0.77,
                                "validation_state": "ALLOWED",
                                "validation_reason": None,
                                "persistability": "PERSISTABLE",
                                "claim_status": "OPEN",
                                "polarity": "SUPPORT",
                                "claim_text": "Claim text",
                                "claim_section": None,
                                "linked_relation_id": None,
                                "metadata": {},
                                "triaged_by": None,
                                "triaged_at": None,
                                "created_at": timestamp,
                                "updated_at": timestamp,
                            },
                        ],
                        "total": 1,
                        "offset": 0,
                        "limit": 25,
                    },
                )
            payload = json.loads(request.content.decode("utf-8"))
            assert request.method == "POST"
            assert payload["relation_type"] == "SUGGESTS"
            return httpx.Response(
                status_code=201,
                json={
                    "id": str(claim_id),
                    "research_space_id": str(space_id),
                    "source_document_id": None,
                    "source_document_ref": "harness_proposal:test",
                    "agent_run_id": "graph_connection:test-run",
                    "source_type": "GENE",
                    "relation_type": "SUGGESTS",
                    "target_type": "GENE",
                    "source_label": "MED13",
                    "target_label": "Cyclin C",
                    "confidence": 0.73,
                    "validation_state": "ALLOWED",
                    "validation_reason": "created_via_claim_api",
                    "persistability": "PERSISTABLE",
                    "claim_status": "OPEN",
                    "polarity": "SUPPORT",
                    "claim_text": "Synthetic promoted claim",
                    "claim_section": None,
                    "linked_relation_id": None,
                    "metadata": {"proposal_id": "proposal-1"},
                    "triaged_by": None,
                    "triaged_at": None,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            )
        if path == f"/v1/spaces/{space_id}/claims/by-entity/{claim_id}":
            assert request.method == "GET"
            return httpx.Response(
                status_code=200,
                json={"claims": [], "total": 0, "offset": 2, "limit": 3},
            )
        if path == f"/v1/spaces/{space_id}/claims/{claim_id}/participants":
            assert request.method == "GET"
            return httpx.Response(
                status_code=200,
                json={
                    "claim_id": str(claim_id),
                    "participants": [],
                    "total": 0,
                },
            )
        if path == f"/v1/spaces/{space_id}/claims/{claim_id}/evidence":
            assert request.method == "GET"
            return httpx.Response(
                status_code=200,
                json={
                    "claim_id": str(claim_id),
                    "evidence": [],
                    "total": 0,
                },
            )
        if (
            path == f"/v1/spaces/{space_id}/claims/{claim_id}"
            and request.method == "PATCH"
        ):
            payload = json.loads(request.content.decode("utf-8"))
            assert payload == {"claim_status": "RESOLVED"}
            return httpx.Response(
                status_code=200,
                json={
                    "id": str(claim_id),
                    "research_space_id": str(space_id),
                    "source_document_id": None,
                    "agent_run_id": None,
                    "source_type": "GENE",
                    "relation_type": "ASSOCIATED_WITH",
                    "target_type": "PHENOTYPE",
                    "source_label": "MED13",
                    "target_label": "Developmental delay",
                    "confidence": 0.77,
                    "validation_state": "ALLOWED",
                    "validation_reason": None,
                    "persistability": "PERSISTABLE",
                    "claim_status": "RESOLVED",
                    "polarity": "SUPPORT",
                    "claim_text": "Claim text",
                    "claim_section": None,
                    "linked_relation_id": None,
                    "metadata": {},
                    "triaged_by": None,
                    "triaged_at": None,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            )
        if path == f"/v1/spaces/{space_id}/relations/conflicts":
            assert request.method == "GET"
            return httpx.Response(
                status_code=200,
                json={
                    "conflicts": [
                        {
                            "relation_id": str(relation_id),
                            "support_count": 1,
                            "refute_count": 1,
                            "support_claim_ids": [str(claim_id)],
                            "refute_claim_ids": [str(uuid4())],
                        },
                    ],
                    "total": 1,
                    "offset": 0,
                    "limit": 50,
                },
            )
        if path == f"/v1/spaces/{space_id}/claim-participants/backfill":
            assert request.method == "POST"
            payload = json.loads(request.content.decode("utf-8"))
            assert payload == {"dry_run": True, "limit": 200, "offset": 4}
            return httpx.Response(
                status_code=200,
                json={
                    "operation_run_id": str(uuid4()),
                    "scanned_claims": 10,
                    "created_participants": 5,
                    "skipped_existing": 5,
                    "unresolved_endpoints": 1,
                    "dry_run": True,
                },
            )
        if path == f"/v1/spaces/{space_id}/claim-participants/coverage":
            assert request.method == "GET"
            assert request.url.params["limit"] == "200"
            assert request.url.params["offset"] == "4"
            return httpx.Response(
                status_code=200,
                json={
                    "total_claims": 10,
                    "claims_with_any_participants": 9,
                    "claims_with_subject": 9,
                    "claims_with_object": 8,
                    "unresolved_subject_endpoints": 1,
                    "unresolved_object_endpoints": 2,
                    "unresolved_endpoint_rate": 0.15,
                },
            )
        if path == f"/v1/spaces/{space_id}/claim-relations" and request.method == "GET":
            assert request.url.params["relation_type"] == "SUPPORTS"
            return httpx.Response(
                status_code=200,
                json={
                    "claim_relations": [],
                    "total": 0,
                    "offset": 1,
                    "limit": 2,
                },
            )
        if (
            path == f"/v1/spaces/{space_id}/claim-relations"
            and request.method == "POST"
        ):
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["relation_type"] == "SUPPORTS"
            return httpx.Response(
                status_code=200,
                json={
                    "id": str(relation_id),
                    "research_space_id": str(space_id),
                    "source_claim_id": str(claim_id),
                    "target_claim_id": str(uuid4()),
                    "relation_type": "SUPPORTS",
                    "agent_run_id": None,
                    "source_document_id": None,
                    "confidence": 0.6,
                    "review_status": "PROPOSED",
                    "evidence_summary": None,
                    "metadata": {},
                    "created_at": timestamp,
                },
            )
        if (
            path == f"/v1/spaces/{space_id}/claim-relations/{relation_id}"
            and request.method == "PATCH"
        ):
            payload = json.loads(request.content.decode("utf-8"))
            assert payload == {"review_status": "ACCEPTED"}
            return httpx.Response(
                status_code=200,
                json={
                    "id": str(relation_id),
                    "research_space_id": str(space_id),
                    "source_claim_id": str(claim_id),
                    "target_claim_id": str(uuid4()),
                    "relation_type": "SUPPORTS",
                    "agent_run_id": None,
                    "source_document_id": None,
                    "confidence": 0.6,
                    "review_status": "ACCEPTED",
                    "evidence_summary": None,
                    "metadata": {},
                    "created_at": timestamp,
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://graph-service.test",
        transport=transport,
    )
    client = GraphServiceClient(
        GraphServiceClientConfig(base_url="https://graph-service.test"),
        client=http_client,
    )

    claims = client.list_claims(
        space_id=space_id,
        claim_status="OPEN",
        validation_state="ALLOWED",
        persistability="PERSISTABLE",
        polarity="SUPPORT",
        certainty_band="MEDIUM",
        offset=0,
        limit=25,
    )
    created_claim = client.create_claim(
        space_id=space_id,
        request=KernelRelationClaimCreateRequest(
            source_entity_id=uuid4(),
            target_entity_id=uuid4(),
            relation_type="SUGGESTS",
            assessment=_SUPPORTED_ASSESSMENT,
            claim_text="Synthetic promoted claim",
            evidence_summary="Synthetic hypothesis evidence",
            source_document_ref="harness_proposal:test",
            agent_run_id="graph_connection:test-run",
            metadata={"proposal_id": "proposal-1"},
        ),
    )
    claims_by_entity = client.list_claims_by_entity(
        space_id=space_id,
        entity_id=claim_id,
        offset=2,
        limit=3,
    )
    participants = client.list_claim_participants(space_id=space_id, claim_id=claim_id)
    evidence = client.list_claim_evidence(space_id=space_id, claim_id=claim_id)
    updated_claim = client.update_claim_status(
        space_id=space_id,
        claim_id=claim_id,
        request=KernelRelationClaimTriageRequest(claim_status="RESOLVED"),
    )
    conflicts = client.list_relation_conflicts(space_id=space_id)
    backfill = client.backfill_claim_participants(
        space_id=space_id,
        request=ClaimParticipantBackfillRequest(dry_run=True, limit=200, offset=4),
    )
    coverage = client.get_claim_participant_coverage(
        space_id=space_id,
        limit=200,
        offset=4,
    )
    claim_relations = client.list_claim_relations(
        space_id=space_id,
        relation_type="SUPPORTS",
        offset=1,
        limit=2,
    )
    created_claim_relation = client.create_claim_relation(
        space_id=space_id,
        request=ClaimRelationCreateRequest(
            source_claim_id=claim_id,
            target_claim_id=uuid4(),
            relation_type="SUPPORTS",
            assessment=_SUPPORTED_ASSESSMENT,
        ),
    )
    updated_claim_relation = client.update_claim_relation_review_status(
        space_id=space_id,
        relation_id=relation_id,
        request=ClaimRelationReviewUpdateRequest(review_status="ACCEPTED"),
    )

    assert claims.total == 1
    assert created_claim.claim_status == "OPEN"
    assert created_claim.relation_type == "SUGGESTS"
    assert claims_by_entity.total == 0
    assert participants.total == 0
    assert evidence.total == 0
    assert updated_claim.claim_status == "RESOLVED"
    assert conflicts.total == 1
    assert backfill.created_participants == 5
    assert coverage.total_claims == 10
    assert claim_relations.total == 0
    assert created_claim_relation.id == relation_id
    assert updated_claim_relation.review_status == "ACCEPTED"
    http_client.close()


def test_graph_service_client_manages_entities_and_observations() -> None:
    space_id = uuid4()
    entity_id = uuid4()
    observation_id = uuid4()
    timestamp = _iso_now()

    def handler(request: httpx.Request) -> httpx.Response:
        if (
            request.method == "GET"
            and request.url.path == f"/v1/spaces/{space_id}/entities"
        ):
            assert request.url.params["type"] == "GENE"
            return httpx.Response(
                status_code=200,
                json={
                    "entities": [
                        {
                            "id": str(entity_id),
                            "research_space_id": str(space_id),
                            "entity_type": "GENE",
                            "display_label": "MED13",
                            "metadata": {},
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        },
                    ],
                    "total": 1,
                    "offset": 0,
                    "limit": 50,
                },
            )
        if (
            request.method == "POST"
            and request.url.path == f"/v1/spaces/{space_id}/entities"
        ):
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["entity_type"] == "GENE"
            return httpx.Response(
                status_code=201,
                json={
                    "entity": {
                        "id": str(entity_id),
                        "research_space_id": str(space_id),
                        "entity_type": "GENE",
                        "display_label": "MED13",
                        "metadata": {},
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    },
                    "created": True,
                },
            )
        if (
            request.method == "GET"
            and request.url.path == f"/v1/spaces/{space_id}/entities/{entity_id}"
        ):
            return httpx.Response(
                status_code=200,
                json={
                    "id": str(entity_id),
                    "research_space_id": str(space_id),
                    "entity_type": "GENE",
                    "display_label": "MED13",
                    "metadata": {},
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            )
        if (
            request.method == "PUT"
            and request.url.path == f"/v1/spaces/{space_id}/entities/{entity_id}"
        ):
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["display_label"] == "MED13 updated"
            return httpx.Response(
                status_code=200,
                json={
                    "id": str(entity_id),
                    "research_space_id": str(space_id),
                    "entity_type": "GENE",
                    "display_label": "MED13 updated",
                    "metadata": {"source": "test"},
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            )
        if (
            request.method == "POST"
            and request.url.path == f"/v1/spaces/{space_id}/observations"
        ):
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["variable_id"] == "VAR_TEST_NOTE"
            return httpx.Response(
                status_code=201,
                json={
                    "id": str(observation_id),
                    "research_space_id": str(space_id),
                    "subject_id": str(entity_id),
                    "variable_id": "VAR_TEST_NOTE",
                    "value_numeric": None,
                    "value_text": "hello graph service",
                    "value_date": None,
                    "value_coded": None,
                    "value_boolean": None,
                    "value_json": None,
                    "unit": None,
                    "observed_at": None,
                    "provenance_id": None,
                    "confidence": 1.0,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            )
        if (
            request.method == "GET"
            and request.url.path == f"/v1/spaces/{space_id}/observations"
        ):
            assert request.url.params["subject_id"] == str(entity_id)
            return httpx.Response(
                status_code=200,
                json={
                    "observations": [
                        {
                            "id": str(observation_id),
                            "research_space_id": str(space_id),
                            "subject_id": str(entity_id),
                            "variable_id": "VAR_TEST_NOTE",
                            "value_numeric": None,
                            "value_text": "hello graph service",
                            "value_date": None,
                            "value_coded": None,
                            "value_boolean": None,
                            "value_json": None,
                            "unit": None,
                            "observed_at": None,
                            "provenance_id": None,
                            "confidence": 1.0,
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        },
                    ],
                    "total": 1,
                    "offset": 0,
                    "limit": 50,
                },
            )
        if (
            request.method == "GET"
            and request.url.path
            == f"/v1/spaces/{space_id}/observations/{observation_id}"
        ):
            return httpx.Response(
                status_code=200,
                json={
                    "id": str(observation_id),
                    "research_space_id": str(space_id),
                    "subject_id": str(entity_id),
                    "variable_id": "VAR_TEST_NOTE",
                    "value_numeric": None,
                    "value_text": "hello graph service",
                    "value_date": None,
                    "value_coded": None,
                    "value_boolean": None,
                    "value_json": None,
                    "unit": None,
                    "observed_at": None,
                    "provenance_id": None,
                    "confidence": 1.0,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            )
        if (
            request.method == "DELETE"
            and request.url.path == f"/v1/spaces/{space_id}/entities/{entity_id}"
        ):
            return httpx.Response(status_code=204)
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://graph-service.test",
        transport=transport,
    )
    client = GraphServiceClient(
        GraphServiceClientConfig(base_url="https://graph-service.test"),
        client=http_client,
    )

    entities = client.list_entities(space_id=space_id, entity_type="GENE")
    created_entity = client.create_entity(
        space_id=space_id,
        request=KernelEntityCreateRequest(
            entity_type="GENE",
            display_label="MED13",
            metadata={},
            identifiers={"hgnc_id": "HGNC:5241"},
        ),
    )
    fetched_entity = client.get_entity(space_id=space_id, entity_id=entity_id)
    updated_entity = client.update_entity(
        space_id=space_id,
        entity_id=entity_id,
        request=KernelEntityUpdateRequest(
            display_label="MED13 updated",
            metadata={"source": "test"},
        ),
    )
    created_observation = client.create_observation(
        space_id=space_id,
        request=KernelObservationCreateRequest(
            subject_id=entity_id,
            variable_id="VAR_TEST_NOTE",
            value="hello graph service",
            unit=None,
            observed_at=None,
            provenance_id=None,
            confidence=1.0,
        ),
    )
    observations = client.list_observations(space_id=space_id, subject_id=entity_id)
    fetched_observation = client.get_observation(
        space_id=space_id,
        observation_id=observation_id,
    )
    client.delete_entity(space_id=space_id, entity_id=entity_id)

    assert entities.total == 1
    assert created_entity.entity.id == entity_id
    assert fetched_entity.id == entity_id
    assert updated_entity.display_label == "MED13 updated"
    assert created_observation.id == observation_id
    assert observations.total == 1
    assert fetched_observation.id == observation_id
    http_client.close()


def test_graph_service_client_fetches_graph_export_and_document() -> None:
    space_id = uuid4()
    source_id = uuid4()
    target_id = uuid4()
    relation_id = uuid4()
    claim_id = uuid4()
    evidence_id = uuid4()
    timestamp = _iso_now()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            assert request.url.path == f"/v1/spaces/{space_id}/graph/export"
            return httpx.Response(
                status_code=200,
                json={
                    "nodes": [
                        {
                            "id": str(source_id),
                            "research_space_id": str(space_id),
                            "entity_type": "GENE",
                            "display_label": "MED13",
                            "metadata": {},
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        },
                        {
                            "id": str(target_id),
                            "research_space_id": str(space_id),
                            "entity_type": "PHENOTYPE",
                            "display_label": "Developmental delay",
                            "metadata": {},
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        },
                    ],
                    "edges": [
                        {
                            "id": str(relation_id),
                            "research_space_id": str(space_id),
                            "source_id": str(source_id),
                            "relation_type": "ASSOCIATED_WITH",
                            "target_id": str(target_id),
                            "confidence": 0.88,
                            "aggregate_confidence": 0.88,
                            "source_count": 1,
                            "highest_evidence_tier": "LITERATURE",
                            "curation_status": "ACCEPTED",
                            "evidence_summary": "Export relation",
                            "evidence_sentence": None,
                            "evidence_sentence_source": None,
                            "evidence_sentence_confidence": None,
                            "evidence_sentence_rationale": None,
                            "paper_links": [],
                            "provenance_id": None,
                            "reviewed_by": None,
                            "reviewed_at": None,
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        },
                    ],
                },
            )

        assert request.method == "POST"
        assert request.url.path == f"/v1/spaces/{space_id}/graph/document"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["include_claims"] is True
        return httpx.Response(
            status_code=200,
            json={
                "nodes": [
                    {
                        "id": str(source_id),
                        "resource_id": str(source_id),
                        "kind": "ENTITY",
                        "type_label": "GENE",
                        "label": "MED13",
                        "confidence": None,
                        "curation_status": None,
                        "claim_status": None,
                        "polarity": None,
                        "canonical_relation_id": None,
                        "metadata": {},
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    },
                    {
                        "id": f"claim:{claim_id}",
                        "resource_id": str(claim_id),
                        "kind": "CLAIM",
                        "type_label": "CLAIM",
                        "label": "Claim label",
                        "confidence": 0.75,
                        "curation_status": None,
                        "claim_status": "RESOLVED",
                        "polarity": "SUPPORT",
                        "canonical_relation_id": str(relation_id),
                        "metadata": {},
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    },
                    {
                        "id": f"evidence:{evidence_id}",
                        "resource_id": str(evidence_id),
                        "kind": "EVIDENCE",
                        "type_label": "PAPER_EVIDENCE",
                        "label": "Evidence label",
                        "confidence": 0.9,
                        "curation_status": None,
                        "claim_status": None,
                        "polarity": None,
                        "canonical_relation_id": str(relation_id),
                        "metadata": {},
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    },
                ],
                "edges": [
                    {
                        "id": str(relation_id),
                        "resource_id": str(relation_id),
                        "kind": "CANONICAL_RELATION",
                        "source_id": str(source_id),
                        "target_id": str(target_id),
                        "type_label": "ASSOCIATED_WITH",
                        "label": "ASSOCIATED_WITH",
                        "confidence": 0.88,
                        "curation_status": "ACCEPTED",
                        "claim_id": None,
                        "canonical_relation_id": str(relation_id),
                        "evidence_id": None,
                        "metadata": {},
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    },
                ],
                "meta": {
                    "mode": "seeded",
                    "seed_entity_ids": [str(source_id)],
                    "requested_depth": 1,
                    "requested_top_k": 10,
                    "pre_cap_entity_node_count": 2,
                    "pre_cap_canonical_edge_count": 1,
                    "truncated_entity_nodes": False,
                    "truncated_canonical_edges": False,
                    "included_claims": True,
                    "included_evidence": True,
                    "max_claims": 10,
                    "evidence_limit_per_claim": 2,
                    "counts": {
                        "entity_nodes": 1,
                        "claim_nodes": 1,
                        "evidence_nodes": 1,
                        "canonical_edges": 1,
                        "claim_participant_edges": 0,
                        "claim_evidence_edges": 0,
                    },
                },
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://graph-service.test",
        transport=transport,
    )
    client = GraphServiceClient(
        GraphServiceClientConfig(base_url="https://graph-service.test"),
        client=http_client,
    )

    export_response = client.get_graph_export(space_id=space_id)
    document_response = client.get_graph_document(
        space_id=space_id,
        request=KernelGraphDocumentRequest(
            mode="seeded",
            seed_entity_ids=[source_id],
            depth=1,
            top_k=10,
            max_nodes=20,
            max_edges=20,
            include_claims=True,
            include_evidence=True,
            max_claims=10,
            evidence_limit_per_claim=2,
        ),
    )

    assert len(export_response.nodes) == 2
    assert len(export_response.edges) == 1
    assert document_response.meta.counts.claim_nodes == 1
    assert any(node.kind == "CLAIM" for node in document_response.nodes)
    http_client.close()


def test_graph_service_client_lists_dictionary_and_concepts() -> None:
    space_id = uuid4()
    timestamp = _iso_now()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/dictionary/entity-types":
            return httpx.Response(
                status_code=200,
                json={
                    "entity_types": [
                        {
                            "id": "GENE",
                            "display_name": "Gene",
                            "description": "Gene entity type",
                            "domain_context": "general",
                            "external_ontology_ref": None,
                            "expected_properties": {},
                            "description_embedding": None,
                            "embedded_at": None,
                            "embedding_model": None,
                            "created_by": "system",
                            "is_active": True,
                            "valid_from": None,
                            "valid_to": None,
                            "superseded_by": None,
                            "source_ref": None,
                            "review_status": "ACTIVE",
                            "reviewed_by": None,
                            "reviewed_at": None,
                            "revocation_reason": None,
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        },
                    ],
                    "total": 1,
                },
            )
        if request.url.path == f"/v1/spaces/{space_id}/concepts/sets":
            return httpx.Response(
                status_code=200,
                json={
                    "concept_sets": [
                        {
                            "id": str(uuid4()),
                            "research_space_id": str(space_id),
                            "name": "Mechanism Concepts",
                            "slug": "mechanism-concepts",
                            "domain_context": "general",
                            "description": "Concept set",
                            "review_status": "ACTIVE",
                            "is_active": True,
                            "created_by": "manual:test",
                            "source_ref": None,
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        },
                    ],
                    "total": 1,
                },
            )
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://graph-service.test",
        transport=transport,
    )
    client = GraphServiceClient(
        GraphServiceClientConfig(base_url="https://graph-service.test"),
        client=http_client,
    )

    entity_types = client.list_dictionary_entity_types()
    concept_sets = client.list_concept_sets(space_id=space_id)

    assert entity_types.total == 1
    assert entity_types.entity_types[0].id == "GENE"
    assert concept_sets.total == 1
    assert concept_sets.concept_sets[0].research_space_id == str(space_id)
    http_client.close()


def test_graph_service_client_raises_typed_error_on_http_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=404, text="missing")

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://graph-service.test",
        transport=transport,
    )
    client = GraphServiceClient(
        GraphServiceClientConfig(base_url="https://graph-service.test"),
        client=http_client,
    )

    try:
        client.get_health()
    except GraphServiceClientError as exc:
        assert exc.status_code == 404
        assert exc.detail == "missing"
    else:
        raise AssertionError("Expected GraphServiceClientError")
    finally:
        http_client.close()


def test_graph_service_client_calls_admin_operations() -> None:
    space_id = uuid4()
    repair_run_id = uuid4()
    rebuild_run_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/admin/projections/readiness":
            assert request.url.params["sample_limit"] == "7"
            return httpx.Response(
                status_code=200,
                json={
                    "orphan_relations": {"count": 0, "samples": []},
                    "missing_claim_participants": {"count": 0, "samples": []},
                    "missing_claim_evidence": {"count": 0, "samples": []},
                    "linked_relation_mismatches": {"count": 0, "samples": []},
                    "invalid_projection_relations": {"count": 0, "samples": []},
                    "ready": True,
                },
            )
        if request.url.path == "/v1/admin/projections/repair":
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["dry_run"] is True
            assert payload["batch_limit"] == 40
            return httpx.Response(
                status_code=200,
                json={
                    "operation_run_id": str(repair_run_id),
                    "participant_backfill": {
                        "scanned_claims": 10,
                        "created_participants": 2,
                        "skipped_existing": 8,
                        "unresolved_endpoints": 1,
                        "research_spaces": 1,
                        "dry_run": True,
                    },
                    "materialized_claims": 3,
                    "detached_claims": 0,
                    "unresolved_claims": 1,
                    "dry_run": True,
                },
            )
        if request.url.path == "/v1/admin/reasoning-paths/rebuild":
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["space_id"] == str(space_id)
            assert payload["max_depth"] == 3
            assert payload["replace_existing"] is True
            return httpx.Response(
                status_code=200,
                json={
                    "operation_run_id": str(rebuild_run_id),
                    "summaries": [
                        {
                            "research_space_id": str(space_id),
                            "eligible_claims": 5,
                            "accepted_claim_relations": 4,
                            "rebuilt_paths": 2,
                            "max_depth": 3,
                        },
                    ],
                },
            )
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://graph-service.test",
        transport=transport,
    )
    client = GraphServiceClient(
        GraphServiceClientConfig(base_url="https://graph-service.test"),
        client=http_client,
    )

    readiness = client.get_projection_readiness(sample_limit=7)
    repair = client.repair_projections(dry_run=True, batch_limit=40)
    rebuild = client.rebuild_reasoning_paths(
        space_id=space_id,
        max_depth=3,
        replace_existing=True,
    )

    assert readiness.ready is True
    assert repair.operation_run_id == repair_run_id
    assert rebuild.summaries[0].rebuilt_paths == 2
    http_client.close()


def test_graph_service_client_reads_operation_run_history() -> None:
    run_id = uuid4()
    started_at = _iso_now()
    completed_at = _iso_now()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/admin/operations/runs":
            assert request.url.params["limit"] == "25"
            assert request.url.params["offset"] == "5"
            assert request.url.params["operation_type"] == "projection_repair"
            assert request.url.params["status"] == "succeeded"
            return httpx.Response(
                status_code=200,
                json={
                    "runs": [
                        {
                            "id": str(run_id),
                            "operation_type": "projection_repair",
                            "status": "succeeded",
                            "research_space_id": None,
                            "actor_user_id": str(uuid4()),
                            "actor_email": "graph-admin@example.com",
                            "dry_run": True,
                            "request_payload": {"dry_run": True, "batch_limit": 100},
                            "summary_payload": {"materialized_claims": 3},
                            "failure_detail": None,
                            "started_at": started_at,
                            "completed_at": completed_at,
                        },
                    ],
                    "total": 1,
                    "offset": 5,
                    "limit": 25,
                },
            )
        if request.url.path == f"/v1/admin/operations/runs/{run_id}":
            return httpx.Response(
                status_code=200,
                json={
                    "id": str(run_id),
                    "operation_type": "projection_repair",
                    "status": "succeeded",
                    "research_space_id": None,
                    "actor_user_id": str(uuid4()),
                    "actor_email": "graph-admin@example.com",
                    "dry_run": True,
                    "request_payload": {"dry_run": True, "batch_limit": 100},
                    "summary_payload": {"materialized_claims": 3},
                    "failure_detail": None,
                    "started_at": started_at,
                    "completed_at": completed_at,
                },
            )
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://graph-service.test",
        transport=transport,
    )
    client = GraphServiceClient(
        GraphServiceClientConfig(base_url="https://graph-service.test"),
        client=http_client,
    )

    runs = client.list_operation_runs(
        limit=25,
        offset=5,
        operation_type="projection_repair",
        status="succeeded",
    )
    run = client.get_operation_run(run_id=run_id)

    assert runs.total == 1
    assert runs.runs[0].id == run_id
    assert run.status == "succeeded"
    http_client.close()


def test_graph_service_client_reads_graph_views_and_mechanism_chains() -> None:
    space_id = uuid4()
    resource_id = uuid4()
    claim_id = uuid4()
    timestamp = _iso_now()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/v1/spaces/{space_id}/graph/views/gene/{resource_id}":
            assert request.method == "GET"
            assert request.url.params["claim_limit"] == "12"
            assert request.url.params["relation_limit"] == "18"
            return httpx.Response(
                status_code=200,
                json={
                    "view_type": "gene",
                    "resource_id": str(resource_id),
                    "entity": None,
                    "claim": None,
                    "paper": None,
                    "canonical_relations": [],
                    "claims": [],
                    "claim_relations": [],
                    "participants": [],
                    "evidence": [],
                    "counts": {
                        "canonical_relations": 0,
                        "claims": 0,
                        "claim_relations": 0,
                        "participants": 0,
                        "evidence": 0,
                    },
                },
            )

        assert request.method == "GET"
        assert request.url.path == (
            f"/v1/spaces/{space_id}/claims/{claim_id}/mechanism-chain"
        )
        assert request.url.params["max_depth"] == "4"
        return httpx.Response(
            status_code=200,
            json={
                "root_claim": {
                    "id": str(claim_id),
                    "research_space_id": str(space_id),
                    "source_document_id": None,
                    "agent_run_id": None,
                    "source_type": "GENE",
                    "relation_type": "ASSOCIATED_WITH",
                    "target_type": "PHENOTYPE",
                    "source_label": "MED13",
                    "target_label": "Phenotype",
                    "confidence": 0.88,
                    "validation_state": "VALID",
                    "validation_reason": None,
                    "persistability": "PERSISTABLE",
                    "claim_status": "RESOLVED",
                    "polarity": "SUPPORT",
                    "claim_text": "MED13 is associated with phenotype",
                    "claim_section": None,
                    "linked_relation_id": None,
                    "metadata": {},
                    "triaged_by": None,
                    "triaged_at": None,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
                "max_depth": 4,
                "canonical_relations": [],
                "claims": [],
                "claim_relations": [],
                "participants": [],
                "evidence": [],
                "counts": {
                    "canonical_relations": 0,
                    "claims": 0,
                    "claim_relations": 0,
                    "participants": 0,
                    "evidence": 0,
                },
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://graph-service.test",
        transport=transport,
    )
    client = GraphServiceClient(
        GraphServiceClientConfig(base_url="https://graph-service.test"),
        client=http_client,
    )

    graph_view = client.get_graph_view(
        space_id=space_id,
        view_type="gene",
        resource_id=resource_id,
        claim_limit=12,
        relation_limit=18,
    )
    chain = client.get_claim_mechanism_chain(
        space_id=space_id,
        claim_id=claim_id,
        max_depth=4,
    )

    assert isinstance(graph_view, KernelGraphDomainViewResponse)
    assert graph_view.view_type == "gene"
    assert isinstance(chain, KernelClaimMechanismChainResponse)
    assert chain.root_claim.id == claim_id
    http_client.close()


def test_graph_service_client_hypothesis_workflows() -> None:
    space_id = uuid4()
    hypothesis_id = uuid4()
    timestamp = _iso_now()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            assert request.url.path == f"/v1/spaces/{space_id}/hypotheses"
            assert request.url.params["offset"] == "3"
            assert request.url.params["limit"] == "7"
            return httpx.Response(
                status_code=200,
                json={
                    "hypotheses": [],
                    "total": 0,
                    "offset": 3,
                    "limit": 7,
                },
            )
        if request.url.path == f"/v1/spaces/{space_id}/hypotheses/manual":
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["statement"] == "Manual hypothesis"
            return httpx.Response(
                status_code=200,
                json={
                    "claim_id": str(hypothesis_id),
                    "polarity": "HYPOTHESIS",
                    "claim_status": "OPEN",
                    "validation_state": "UNDEFINED",
                    "persistability": "NON_PERSISTABLE",
                    "confidence": 0.5,
                    "source_label": "Manual hypothesis",
                    "relation_type": "PROPOSES",
                    "target_label": None,
                    "claim_text": "Manual hypothesis",
                    "linked_relation_id": None,
                    "origin": "manual",
                    "seed_entity_ids": [],
                    "supporting_provenance_ids": [],
                    "reasoning_path_id": None,
                    "supporting_claim_ids": [],
                    "direct_supporting_claim_ids": [],
                    "transferred_supporting_claim_ids": [],
                    "transferred_from_entities": [],
                    "transfer_basis": [],
                    "contradiction_claim_ids": [],
                    "explanation": None,
                    "path_confidence": None,
                    "path_length": None,
                    "created_at": timestamp,
                    "metadata": {},
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://graph-service.test",
        transport=transport,
    )
    client = GraphServiceClient(
        GraphServiceClientConfig(base_url="https://graph-service.test"),
        client=http_client,
    )

    list_response = client.list_hypotheses(space_id=space_id, offset=3, limit=7)
    manual_response = client.create_manual_hypothesis(
        space_id=space_id,
        request=CreateManualHypothesisRequest(
            statement="Manual hypothesis",
            rationale="Needs validation",
        ),
    )
    assert list_response.total == 0
    assert list_response.offset == 3
    assert list_response.limit == 7
    assert manual_response.claim_id == hypothesis_id
    http_client.close()
