"""Unit tests for the harness-local graph API gateway."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from artana_evidence_api.graph_client import (
    GraphRawMutationTransport,
    GraphServiceClientError,
    GraphServiceHealthResponse,
    GraphTransportBundle,
    GraphTransportConfig,
)
from artana_evidence_api.graph_integration.context import GraphCallContext
from artana_evidence_api.graph_integration.preflight import GraphAIPreflightService
from artana_evidence_api.graph_integration.submission import (
    GraphWorkflowSubmissionService,
)
from artana_evidence_api.relation_type_resolver import (
    RelationTypeAction,
    RelationTypeDecision,
)
from artana_evidence_api.request_context import (
    REQUEST_ID_HEADER,
    request_id_context,
)
from artana_evidence_api.types.common import JSONObject
from artana_evidence_api.types.graph_contracts import (
    AIDecisionResponse,
    AIDecisionSubmitRequest,
    ConceptExternalRefRequest,
    ConceptProposalCreateRequest,
    ConceptProposalResponse,
    ConnectorProposalCreateRequest,
    ConnectorProposalResponse,
    ExplanationResponse,
    GraphChangeClaimRequest,
    GraphChangeConceptRequest,
    GraphChangeProposalCreateRequest,
    GraphChangeProposalResponse,
    GraphWorkflowActionRequest,
    GraphWorkflowCreateRequest,
    GraphWorkflowListResponse,
    GraphWorkflowPolicy,
    GraphWorkflowResponse,
    KernelEntityEmbeddingRefreshRequest,
    KernelEntityEmbeddingRefreshResponse,
    KernelEntityEmbeddingStatusListResponse,
    KernelEntityEmbeddingStatusResponse,
    KernelEntityListResponse,
    KernelEntityResponse,
    KernelGraphDocumentCounts,
    KernelGraphDocumentEdge,
    KernelGraphDocumentMeta,
    KernelGraphDocumentNode,
    KernelGraphDocumentRequest,
    KernelGraphDocumentResponse,
    KernelGraphValidationResponse,
    KernelRelationClaimCreateRequest,
    KernelRelationClaimResponse,
    KernelRelationCreateRequest,
    KernelRelationResponse,
    KernelRelationSuggestionRequest,
    OperatingModeCapabilitiesResponse,
    OperatingModeRequest,
    OperatingModeResponse,
)

_SUPPORTED_ASSESSMENT = {
    "support_band": "SUPPORTED",
    "grounding_level": "SPAN",
    "mapping_status": "RESOLVED",
    "speculation_level": "DIRECT",
    "confidence_rationale": "Synthetic test evidence supports the claim.",
}
_STRONG_ASSESSMENT = {
    "support_band": "STRONG",
    "grounding_level": "SPAN",
    "mapping_status": "RESOLVED",
    "speculation_level": "DIRECT",
    "confidence_rationale": "Synthetic test evidence strongly supports the decision.",
}
_DECISION_CONFIDENCE_ASSESSMENT = {
    "fact_assessment": _STRONG_ASSESSMENT,
    "validation_state": "VALID",
    "evidence_state": "ACCEPTED_DIRECT_EVIDENCE",
    "duplicate_conflict_state": "CLEAR",
    "source_reliability": "CURATED",
    "risk_tier": "low",
    "rationale": "Unit-test deterministic decision assessment.",
}


def _dictionary_entity_type_payload(entity_type: str) -> dict[str, object]:
    now = datetime.now(UTC).isoformat()
    return {
        "id": entity_type,
        "display_name": entity_type.replace("_", " ").title(),
        "description": f"{entity_type} description",
        "domain_context": "general",
        "external_ontology_ref": None,
        "expected_properties": {},
        "description_embedding": None,
        "embedded_at": None,
        "embedding_model": None,
        "created_by": "test-user",
        "is_active": True,
        "valid_from": None,
        "valid_to": None,
        "superseded_by": None,
        "source_ref": None,
        "review_status": "APPROVED",
        "reviewed_by": None,
        "reviewed_at": None,
        "revocation_reason": None,
        "created_at": now,
        "updated_at": now,
    }


def _dictionary_relation_type_payload(relation_type: str) -> dict[str, object]:
    now = datetime.now(UTC).isoformat()
    return {
        "id": relation_type,
        "display_name": relation_type.replace("_", " ").title(),
        "description": f"{relation_type} description",
        "domain_context": "general",
        "is_directional": True,
        "inverse_label": None,
        "description_embedding": None,
        "embedded_at": None,
        "embedding_model": None,
        "created_by": "test-user",
        "is_active": True,
        "valid_from": None,
        "valid_to": None,
        "superseded_by": None,
        "source_ref": None,
        "review_status": "APPROVED",
        "reviewed_by": None,
        "reviewed_at": None,
        "revocation_reason": None,
        "created_at": now,
        "updated_at": now,
    }


def _dictionary_relation_synonym_payload(
    *,
    relation_type: str,
    synonym: str,
    synonym_id: int = 1,
) -> dict[str, object]:
    now = datetime.now(UTC).isoformat()
    return {
        "id": synonym_id,
        "relation_type": relation_type,
        "synonym": synonym,
        "source": "test-fixture",
        "created_by": "test-user",
        "is_active": True,
        "valid_from": None,
        "valid_to": None,
        "superseded_by": None,
        "source_ref": None,
        "review_status": "APPROVED",
        "reviewed_by": None,
        "reviewed_at": None,
        "revocation_reason": None,
        "created_at": now,
        "updated_at": now,
    }


def _dictionary_proposal_payload(
    proposal_type: str,
    **overrides: object,
) -> dict[str, object]:
    now = datetime.now(UTC).isoformat()
    payload: dict[str, object] = {
        "id": str(uuid4()),
        "proposal_type": proposal_type,
        "status": "SUBMITTED",
        "entity_type": None,
        "source_type": None,
        "relation_type": None,
        "target_type": None,
        "value_set_id": None,
        "variable_id": None,
        "canonical_name": None,
        "data_type": None,
        "preferred_unit": None,
        "constraints": {},
        "sensitivity": None,
        "code": None,
        "synonym": None,
        "source": None,
        "display_name": None,
        "name": None,
        "display_label": None,
        "description": None,
        "domain_context": "general",
        "external_ontology_ref": None,
        "external_ref": None,
        "expected_properties": {},
        "synonyms": [],
        "is_directional": True,
        "inverse_label": None,
        "is_extensible": None,
        "sort_order": None,
        "is_active_value": None,
        "is_allowed": None,
        "requires_evidence": None,
        "profile": None,
        "rationale": "test rationale",
        "evidence_payload": {},
        "proposed_by": "test-user",
        "reviewed_by": None,
        "reviewed_at": None,
        "decision_reason": None,
        "merge_target_type": None,
        "merge_target_id": None,
        "applied_domain_context_id": None,
        "applied_entity_type_id": None,
        "applied_variable_id": None,
        "applied_relation_type_id": None,
        "applied_constraint_id": None,
        "applied_relation_synonym_id": None,
        "applied_value_set_id": None,
        "applied_value_set_item_id": None,
        "source_ref": None,
        "created_at": now,
        "updated_at": now,
    }
    payload.update(overrides)
    return payload


class _FakeHttpClient:
    def __init__(self) -> None:
        self.last_method: str | None = None
        self.last_path: str | None = None
        self.last_params: object = None
        self.last_headers: dict[str, str] | None = None
        self.last_content: str | None = None
        self.closed = False

    def request(
        self,
        method: str,
        url: str,
        *,
        params: object = None,
        headers: dict[str, str] | None = None,
        content: str | None = None,
    ) -> httpx.Response:
        if self.closed:
            request = httpx.Request(method, f"http://graph.local{url}")
            raise httpx.ConnectError(
                "Cannot send a request, as the client has been closed.", request=request
            )
        self.last_method = method
        self.last_path = url
        self.last_params = params
        self.last_headers = headers
        self.last_content = content
        request = httpx.Request(method, f"http://graph.local{url}")
        if method == "POST":
            post_response = self._post_response(
                url=url, content=content, request=request
            )
            if post_response is not None:
                return post_response
        if method == "GET":
            get_response = self._get_response(url=url, params=params, request=request)
            if get_response is not None:
                return get_response
        return httpx.Response(status_code=404, content="not found", request=request)

    def close(self) -> None:
        self.closed = True

    def _post_response(
        self,
        *,
        url: str,
        content: str | None,
        request: httpx.Request,
    ) -> httpx.Response | None:
        if content is None:
            return None
        if url.endswith("/validate/entity"):
            return self._validate_entity_response(content=content, request=request)
        if url.endswith("/validate/claim"):
            return self._validate_claim_response(content=content, request=request)
        if url.endswith("/claims"):
            return self._create_claim_response(content=content, request=request)
        if url.endswith("/entities"):
            return self._create_entity_response(content=content, request=request)
        if url.endswith("/graph/document"):
            return self._graph_document_response(content=content, request=request)
        if url.endswith("/entities/embeddings/refresh"):
            return self._refresh_embeddings_response(request=request)
        if url == "/v1/dictionary/relation-constraints":
            return httpx.Response(
                status_code=201,
                content=json.dumps({"source_type": "GENE"}),
                request=request,
            )
        return None

    def _get_response(
        self,
        *,
        url: str,
        params: object,
        request: httpx.Request,
    ) -> httpx.Response | None:
        if url.endswith("/entities"):
            return self._list_entities_response(params=params, request=request)
        if url.endswith("/entities/embeddings/status"):
            return self._embedding_status_response(request=request)
        if url == "/health":
            return httpx.Response(
                status_code=200,
                content=GraphServiceHealthResponse(
                    status="ok",
                    version="graph-test",
                ).model_dump_json(),
                request=request,
            )
        return None

    def _validate_entity_response(
        self,
        *,
        content: str,
        request: httpx.Request,
    ) -> httpx.Response:
        payload = json.loads(content)
        return httpx.Response(
            status_code=200,
            content=KernelGraphValidationResponse(
                valid=True,
                code="allowed",
                message="This entity can be created.",
                severity="info",
                next_actions=[],
                normalized_entity_type=str(payload["entity_type"]).strip().upper(),
                validation_state="ALLOWED",
                validation_reason="test",
                persistability="PERSISTABLE",
            ).model_dump_json(),
            request=request,
        )

    def _validate_claim_response(
        self,
        *,
        content: str,
        request: httpx.Request,
    ) -> httpx.Response:
        payload = json.loads(content)
        return httpx.Response(
            status_code=200,
            content=KernelGraphValidationResponse(
                valid=True,
                code="allowed",
                message="This claim can be created.",
                severity="info",
                next_actions=[],
                normalized_relation_type=str(payload["relation_type"]).strip().upper(),
                source_type="GENE",
                target_type="GENE",
                validation_state="ALLOWED",
                validation_reason="test",
                persistability="PERSISTABLE",
            ).model_dump_json(),
            request=request,
        )

    def _create_claim_response(
        self,
        *,
        content: str,
        request: httpx.Request,
    ) -> httpx.Response:
        payload = json.loads(content)
        assert "confidence" not in payload
        now = datetime.now(UTC)
        response_payload = KernelRelationClaimResponse(
            id=uuid4(),
            research_space_id=uuid4(),
            source_document_id=None,
            source_document_ref="pmid:123",
            agent_run_id="graph-harness:test",
            source_type="PUBMED",
            relation_type=str(payload["relation_type"]),
            target_type="GENE",
            source_label="MED13",
            target_label="Mediator complex",
            confidence=0.7,
            validation_state="ALLOWED",
            validation_reason="test",
            persistability="PERSISTABLE",
            claim_status="OPEN",
            polarity="SUPPORT",
            claim_text=str(payload["claim_text"]),
            claim_section=None,
            linked_relation_id=None,
            metadata=payload["metadata"],
            triaged_by=None,
            triaged_at=None,
            created_at=now,
            updated_at=now,
        )
        return httpx.Response(
            status_code=200,
            content=response_payload.model_dump_json(),
            request=request,
        )

    def _create_entity_response(
        self,
        *,
        content: str,
        request: httpx.Request,
    ) -> httpx.Response:
        payload = json.loads(content)
        return httpx.Response(
            status_code=200,
            content=json.dumps(
                {
                    "id": str(uuid4()),
                    "entity_type": payload["entity_type"],
                    "display_label": payload["display_label"],
                    "aliases": payload.get("aliases", []),
                },
            ),
            request=request,
        )

    def _graph_document_response(
        self,
        *,
        content: str,
        request: httpx.Request,
    ) -> httpx.Response:
        payload = json.loads(content)
        now = datetime.now(UTC)
        response_payload = KernelGraphDocumentResponse(
            nodes=[
                KernelGraphDocumentNode(
                    id="entity:1",
                    resource_id=str(payload["seed_entity_ids"][0]),
                    kind="ENTITY",
                    type_label="GENE",
                    label="MED13",
                    confidence=0.9,
                    curation_status="APPROVED",
                    claim_status=None,
                    polarity=None,
                    canonical_relation_id=None,
                    metadata={},
                    created_at=now,
                    updated_at=now,
                ),
            ],
            edges=[
                KernelGraphDocumentEdge(
                    id="edge:1",
                    resource_id=None,
                    kind="CANONICAL_RELATION",
                    source_id="entity:1",
                    target_id="entity:2",
                    type_label="INTERACTS_WITH",
                    label="interacts with",
                    confidence=0.8,
                    curation_status="APPROVED",
                    claim_id=None,
                    canonical_relation_id=None,
                    evidence_id=None,
                    metadata={"source": "fake-http"},
                    created_at=now,
                    updated_at=now,
                ),
            ],
            meta=KernelGraphDocumentMeta(
                mode=str(payload["mode"]),
                seed_entity_ids=[UUID(str(payload["seed_entity_ids"][0]))],
                requested_depth=int(payload["depth"]),
                requested_top_k=int(payload["top_k"]),
                pre_cap_entity_node_count=1,
                pre_cap_canonical_edge_count=1,
                truncated_entity_nodes=False,
                truncated_canonical_edges=False,
                included_claims=bool(payload["include_claims"]),
                included_evidence=bool(payload["include_evidence"]),
                max_claims=int(payload["max_claims"]),
                evidence_limit_per_claim=int(payload["evidence_limit_per_claim"]),
                counts=KernelGraphDocumentCounts(
                    entity_nodes=1,
                    claim_nodes=0,
                    evidence_nodes=0,
                    canonical_edges=1,
                    claim_participant_edges=0,
                    claim_evidence_edges=0,
                ),
            ),
        )
        return httpx.Response(
            status_code=200,
            content=response_payload.model_dump_json(),
            request=request,
        )

    def _list_entities_response(
        self,
        *,
        params: object,
        request: httpx.Request,
    ) -> httpx.Response:
        ids_param = None
        if isinstance(params, dict):
            raw_ids = params.get("ids")
            if isinstance(raw_ids, str):
                ids_param = [value for value in raw_ids.split(",") if value]
        resolved_ids = ids_param or [str(uuid4()), str(uuid4())]
        response_payload = KernelEntityListResponse(
            entities=[
                KernelEntityResponse(
                    id=UUID(resolved_ids[0]),
                    research_space_id=uuid4(),
                    entity_type="GENE",
                    display_label="MED13",
                    aliases=[],
                    metadata={},
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                ),
                KernelEntityResponse(
                    id=UUID(resolved_ids[-1]),
                    research_space_id=uuid4(),
                    entity_type="PROTEIN_COMPLEX",
                    display_label="Mediator complex",
                    aliases=[],
                    metadata={},
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                ),
            ],
            total=2,
            offset=0,
            limit=50,
        )
        return httpx.Response(
            status_code=200,
            content=response_payload.model_dump_json(),
            request=request,
        )

    def _embedding_status_response(
        self,
        *,
        request: httpx.Request,
    ) -> httpx.Response:
        response_payload = KernelEntityEmbeddingStatusListResponse(
            statuses=[
                KernelEntityEmbeddingStatusResponse(
                    entity_id=uuid4(),
                    state="ready",
                    desired_fingerprint="a" * 64,
                    embedding_model="text-embedding-3-small",
                    embedding_version=1,
                    last_requested_at=datetime.now(UTC),
                    last_attempted_at=datetime.now(UTC),
                    last_refreshed_at=datetime.now(UTC),
                    last_error_code=None,
                    last_error_message=None,
                ),
            ],
            total=1,
        )
        return httpx.Response(
            status_code=200,
            content=response_payload.model_dump_json(),
            request=request,
        )

    def _refresh_embeddings_response(
        self,
        *,
        request: httpx.Request,
    ) -> httpx.Response:
        response_payload = KernelEntityEmbeddingRefreshResponse(
            requested=2,
            processed=2,
            refreshed=1,
            unchanged=1,
            failed=0,
            missing_entities=[],
        )
        return httpx.Response(
            status_code=200,
            content=response_payload.model_dump_json(),
            request=request,
        )


class _ErrorStatusHttpClient:
    def __init__(self, *, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        self.last_method: str | None = None
        self.last_path: str | None = None
        self.closed = False

    def request(
        self,
        method: str,
        url: str,
        *,
        params: object = None,
        headers: dict[str, str] | None = None,
        content: str | None = None,
    ) -> httpx.Response:
        del params, headers, content
        self.last_method = method
        self.last_path = url
        request = httpx.Request(method, f"http://graph.local{url}")
        return httpx.Response(
            status_code=self.status_code,
            content=self.body,
            request=request,
        )

    def close(self) -> None:
        self.closed = True


class _TransportFailureHttpClient:
    def __init__(self) -> None:
        self.last_method: str | None = None
        self.last_path: str | None = None
        self.closed = False

    def request(
        self,
        method: str,
        url: str,
        *,
        params: object = None,
        headers: dict[str, str] | None = None,
        content: str | None = None,
    ) -> httpx.Response:
        del params, headers, content
        self.last_method = method
        self.last_path = url
        request = httpx.Request(method, f"http://graph.local{url}")
        raise httpx.ConnectError("graph service unreachable", request=request)

    def close(self) -> None:
        self.closed = True


class _EntityValidationHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.proposal_payload: dict[str, object] | None = None
        self.validation_payload: dict[str, object] | None = None

    def request(
        self,
        method: str,
        url: str,
        *,
        params: object = None,
        headers: dict[str, str] | None = None,
        content: str | None = None,
    ) -> httpx.Response:
        del headers
        self.calls.append((method, url))
        request = httpx.Request(method, f"http://graph.local{url}")
        if (
            method == "POST"
            and url.endswith("/validate/entity")
            and content is not None
        ):
            self.validation_payload = json.loads(content)
            return httpx.Response(
                status_code=200,
                content=KernelGraphValidationResponse(
                    valid=False,
                    code="unknown_entity_type",
                    message="Entity type GENE is not approved.",
                    severity="blocking",
                    next_actions=[],
                ).model_dump_json(),
                request=request,
            )
        if method == "GET" and url == "/v1/dictionary/entity-types":
            return httpx.Response(
                status_code=200,
                content=json.dumps(
                    {
                        "entity_types": [_dictionary_entity_type_payload("DISEASE")],
                        "total": 1,
                    },
                ),
                request=request,
            )
        if (
            method == "POST"
            and url == "/v1/dictionary/proposals/entity-types"
            and content is not None
        ):
            self.proposal_payload = json.loads(content)
            return httpx.Response(
                status_code=201,
                content=json.dumps(
                    _dictionary_proposal_payload(
                        "ENTITY_TYPE",
                        id=str(self.proposal_payload["id"]),
                        entity_type=self.proposal_payload["id"],
                        display_name=self.proposal_payload["display_name"],
                        description=self.proposal_payload["description"],
                        domain_context=self.proposal_payload["domain_context"],
                        rationale=self.proposal_payload["rationale"],
                        evidence_payload=self.proposal_payload["evidence_payload"],
                        expected_properties=self.proposal_payload[
                            "expected_properties"
                        ],
                        external_ontology_ref=self.proposal_payload[
                            "external_ontology_ref"
                        ],
                        source_ref=self.proposal_payload["source_ref"],
                    ),
                ),
                request=request,
            )
        return httpx.Response(status_code=404, content="not found", request=request)

    def close(self) -> None:
        return None


class _InactiveEntityTypeHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        params: object = None,
        headers: dict[str, str] | None = None,
        content: str | None = None,
    ) -> httpx.Response:
        del params, headers, content
        self.calls.append((method, url))
        request = httpx.Request(method, f"http://graph.local{url}")
        if method == "POST" and url.endswith("/validate/entity"):
            return httpx.Response(
                status_code=200,
                content=KernelGraphValidationResponse(
                    valid=False,
                    code="inactive_entity_type",
                    message="Entity type GENE exists but is not active.",
                    severity="blocking",
                    next_actions=[],
                ).model_dump_json(),
                request=request,
            )
        return httpx.Response(status_code=404, content="not found", request=request)

    def close(self) -> None:
        return None


class _RelationValidationHttpClient:
    def __init__(
        self,
        *,
        validation_response: KernelGraphValidationResponse | None = None,
        validation_responses: list[KernelGraphValidationResponse] | None = None,
        known_relation_types: list[str] | None = None,
        relation_synonym_match: str | None = None,
    ) -> None:
        self.calls: list[tuple[str, str]] = []
        self.validation_payload: dict[str, object] | None = None
        self.relation_payload: dict[str, object] | None = None
        self.relation_type_proposal_payload: dict[str, object] | None = None
        self.relation_constraint_proposal_payload: dict[str, object] | None = None
        if validation_responses is not None:
            self._validation_responses = list(validation_responses)
        elif validation_response is not None:
            self._validation_responses = [validation_response]
        else:
            raise ValueError("validation_response or validation_responses is required")
        self._known_relation_types = known_relation_types or ["ASSOCIATED_WITH"]
        self._relation_synonym_match = relation_synonym_match

    def request(
        self,
        method: str,
        url: str,
        *,
        params: object = None,
        headers: dict[str, str] | None = None,
        content: str | None = None,
    ) -> httpx.Response:
        del headers
        self.calls.append((method, url))
        request = httpx.Request(method, f"http://graph.local{url}")
        if (
            method == "POST"
            and url.endswith("/validate/triple")
            and content is not None
        ):
            self.validation_payload = json.loads(content)
            if not self._validation_responses:
                return httpx.Response(
                    status_code=500,
                    content="missing validation fixture",
                    request=request,
                )
            return httpx.Response(
                status_code=200,
                content=self._validation_responses.pop(0).model_dump_json(),
                request=request,
            )
        if method == "GET" and url == "/v1/dictionary/relation-types":
            payload = {
                "relation_types": [
                    _dictionary_relation_type_payload(relation_type)
                    for relation_type in self._known_relation_types
                ],
                "total": len(self._known_relation_types),
            }
            return httpx.Response(
                status_code=200,
                content=json.dumps(payload),
                request=request,
            )
        if method == "GET" and url == "/v1/dictionary/relation-synonyms":
            payload = {
                "relation_synonyms": [
                    _dictionary_relation_synonym_payload(
                        relation_type=self._relation_synonym_match,
                        synonym="GENERATES",
                    ),
                ]
                if self._relation_synonym_match is not None
                else [],
                "total": 1 if self._relation_synonym_match is not None else 0,
            }
            return httpx.Response(
                status_code=200,
                content=json.dumps(payload),
                request=request,
            )
        if method == "GET" and url == "/v1/dictionary/relation-synonyms/resolve":
            synonym = None
            if isinstance(params, dict):
                raw_synonym = params.get("synonym")
                if isinstance(raw_synonym, str):
                    synonym = raw_synonym
            if (
                self._relation_synonym_match is not None
                and isinstance(synonym, str)
                and synonym.strip().upper() == "GENERATES"
            ):
                return httpx.Response(
                    status_code=200,
                    content=json.dumps(
                        _dictionary_relation_type_payload(
                            self._relation_synonym_match,
                        ),
                    ),
                    request=request,
                )
            return httpx.Response(status_code=404, content="not found", request=request)
        if method == "GET" and url.startswith("/v1/dictionary/search/by-domain/"):
            return httpx.Response(
                status_code=200,
                content=json.dumps({"results": [], "total": 0}),
                request=request,
            )
        if (
            method == "POST"
            and url == "/v1/dictionary/proposals/relation-types"
            and content is not None
        ):
            self.relation_type_proposal_payload = json.loads(content)
            return httpx.Response(
                status_code=201,
                content=json.dumps(
                    _dictionary_proposal_payload(
                        "RELATION_TYPE",
                        relation_type=self.relation_type_proposal_payload["id"],
                        display_name=self.relation_type_proposal_payload[
                            "display_name"
                        ],
                        description=self.relation_type_proposal_payload["description"],
                        domain_context=self.relation_type_proposal_payload[
                            "domain_context"
                        ],
                        rationale=self.relation_type_proposal_payload["rationale"],
                        evidence_payload=self.relation_type_proposal_payload[
                            "evidence_payload"
                        ],
                        is_directional=self.relation_type_proposal_payload[
                            "is_directional"
                        ],
                        inverse_label=self.relation_type_proposal_payload[
                            "inverse_label"
                        ],
                        source_ref=self.relation_type_proposal_payload["source_ref"],
                    ),
                ),
                request=request,
            )
        if (
            method == "POST"
            and url == "/v1/dictionary/proposals/relation-constraints"
            and content is not None
        ):
            self.relation_constraint_proposal_payload = json.loads(content)
            return httpx.Response(
                status_code=201,
                content=json.dumps(
                    _dictionary_proposal_payload(
                        "RELATION_CONSTRAINT",
                        source_type=self.relation_constraint_proposal_payload[
                            "source_type"
                        ],
                        relation_type=self.relation_constraint_proposal_payload[
                            "relation_type"
                        ],
                        target_type=self.relation_constraint_proposal_payload[
                            "target_type"
                        ],
                        rationale=self.relation_constraint_proposal_payload[
                            "rationale"
                        ],
                        evidence_payload=self.relation_constraint_proposal_payload[
                            "evidence_payload"
                        ],
                        is_allowed=self.relation_constraint_proposal_payload[
                            "is_allowed"
                        ],
                        requires_evidence=self.relation_constraint_proposal_payload[
                            "requires_evidence"
                        ],
                        profile=self.relation_constraint_proposal_payload["profile"],
                        source_ref=self.relation_constraint_proposal_payload[
                            "source_ref"
                        ],
                    ),
                ),
                request=request,
            )
        if method == "POST" and url.endswith("/relations") and content is not None:
            self.relation_payload = json.loads(content)
            now = datetime.now(UTC)
            response_payload = KernelRelationResponse(
                id=uuid4(),
                research_space_id=uuid4(),
                source_claim_id=uuid4(),
                source_id=UUID(str(self.relation_payload["source_id"])),
                relation_type=str(self.relation_payload["relation_type"]),
                target_id=UUID(str(self.relation_payload["target_id"])),
                confidence=0.7,
                aggregate_confidence=0.7,
                source_count=1,
                highest_evidence_tier="COMPUTATIONAL",
                curation_status="UNDER_REVIEW",
                evidence_summary=self.relation_payload.get("evidence_summary"),
                evidence_sentence=self.relation_payload.get("evidence_sentence"),
                evidence_sentence_source=None,
                evidence_sentence_confidence=None,
                evidence_sentence_rationale=None,
                paper_links=[],
                provenance_id=None,
                reviewed_by=None,
                reviewed_at=None,
                created_at=now,
                updated_at=now,
            )
            return httpx.Response(
                status_code=200,
                content=response_payload.model_dump_json(),
                request=request,
            )
        return httpx.Response(status_code=404, content="not found", request=request)

    def close(self) -> None:
        return None


def _gateway_with_fake_client() -> tuple[GraphTransportBundle, _FakeHttpClient]:
    fake_client = _FakeHttpClient()
    gateway = GraphTransportBundle(
        config=GraphTransportConfig(
            base_url="http://graph.local",
            timeout_seconds=5.0,
            default_headers={"Authorization": "Bearer test-token"},
        ),
        client=fake_client,
    )
    return gateway, fake_client


def _gateway_with_client(client: object) -> GraphTransportBundle:
    return GraphTransportBundle(
        config=GraphTransportConfig(
            base_url="http://graph.local",
            timeout_seconds=5.0,
            default_headers={"Authorization": "Bearer test-token"},
        ),
        client=client,
    )


def _bundle_factory_with_client(
    client: object,
) -> Callable[[GraphCallContext], GraphTransportBundle]:
    def _factory(call_context: GraphCallContext) -> GraphTransportBundle:
        return GraphTransportBundle(
            config=GraphTransportConfig(
                base_url="http://graph.local",
                timeout_seconds=5.0,
                default_headers=call_context.default_headers(),
            ),
            client=client,
            call_context=call_context,
        )

    return _factory


def _raw_transport_with_client(client: object) -> GraphRawMutationTransport:
    bundle = _bundle_factory_with_client(client)(GraphCallContext.service())
    return GraphRawMutationTransport(bundle._runtime)  # noqa: SLF001


def _raw_mutation_transport_factory_with_client(
    client: object,
) -> Callable[[GraphCallContext], GraphRawMutationTransport]:
    def _factory(call_context: GraphCallContext) -> GraphRawMutationTransport:
        bundle = _bundle_factory_with_client(client)(call_context)
        return GraphRawMutationTransport(bundle._runtime)  # noqa: SLF001

    return _factory


def _preflight_services(
    gateway: GraphTransportBundle,
) -> tuple[GraphAIPreflightService, GraphWorkflowSubmissionService]:
    client = gateway._runtime.client  # noqa: SLF001
    return (
        GraphAIPreflightService(
            admin_dictionary_transport_factory=lambda: gateway.dictionary,
        ),
        GraphWorkflowSubmissionService(
            bundle_factory=_bundle_factory_with_client(client),
            raw_mutation_transport_factory=_raw_mutation_transport_factory_with_client(
                client,
            ),
            admin_dictionary_transport_factory=lambda: gateway.dictionary,
        ),
    )


def _stub_kernel_relation_register_new(
    monkeypatch: pytest.MonkeyPatch,
    *,
    canonical_type: str,
    reasoning: str,
) -> None:
    async def _resolver(*_: object, **__: object) -> RelationTypeDecision:
        return RelationTypeDecision(
            action=RelationTypeAction.REGISTER_NEW,
            canonical_type=canonical_type,
            reasoning=reasoning,
        )

    monkeypatch.setattr(
        "artana_evidence_api.graph_integration.preflight.resolve_relation_with_kernel",
        _resolver,
    )


def test_gateway_default_call_context_is_not_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "test-graph-secret-key-with-minimum-length-123456"
    monkeypatch.setenv("GRAPH_JWT_SECRET", secret)
    monkeypatch.setenv("GRAPH_JWT_ISSUER", "graph-biomedical")
    monkeypatch.delenv("GRAPH_SERVICE_AI_PRINCIPAL", raising=False)

    gateway = GraphTransportBundle(
        config=GraphTransportConfig(
            base_url="http://graph.local",
            timeout_seconds=5.0,
            default_headers=GraphCallContext.service().default_headers(),
        ),
        client=_FakeHttpClient(),
    )

    payload = jwt.decode(
        gateway.call_context.authorization_header().removeprefix("Bearer "),
        secret,
        algorithms=["HS256"],
        issuer="graph-biomedical",
    )

    assert payload["graph_admin"] is False
    assert "graph_ai_principal" not in payload


def test_create_entity_posts_raw_transport_payload_without_hidden_preflight() -> None:
    _, fake_client = _gateway_with_fake_client()
    transport = _raw_transport_with_client(fake_client)

    response = transport.upsert_entity_direct(
        space_id=uuid4(),
        entity_type="GENE",
        display_label="MED13",
        aliases=["Mediator complex subunit 13"],
    )

    assert fake_client.last_method == "POST"
    assert fake_client.last_path is not None
    assert fake_client.last_path.endswith("/entities")
    assert fake_client.last_content is not None
    posted_payload = json.loads(fake_client.last_content)
    assert posted_payload == {
        "entity_type": "GENE",
        "display_label": "MED13",
        "aliases": ["Mediator complex subunit 13"],
    }
    assert response["entity_type"] == "GENE"


def test_create_claim_posts_local_contract_payload() -> None:
    _, fake_client = _gateway_with_fake_client()
    transport = _raw_transport_with_client(fake_client)
    source_entity_id = uuid4()
    target_entity_id = uuid4()

    response = transport.create_unresolved_claim_direct(
        space_id=uuid4(),
        request=KernelRelationClaimCreateRequest(
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            relation_type="SUGGESTS",
            assessment=_SUPPORTED_ASSESSMENT,
            claim_text="MED13 suggests a mediator interaction.",
            metadata={"origin": "test"},
        ),
    )

    assert fake_client.last_method == "POST"
    assert fake_client.last_path is not None
    assert fake_client.last_path.endswith("/claims")
    assert fake_client.last_headers is not None
    assert fake_client.last_headers["Content-Type"] == "application/json"
    assert fake_client.last_headers["Authorization"].startswith("Bearer ")
    assert fake_client.last_content is not None
    posted_payload = json.loads(fake_client.last_content)
    assert posted_payload["source_entity_id"] == str(source_entity_id)
    assert posted_payload["target_entity_id"] == str(target_entity_id)
    assert posted_payload["metadata"] == {"origin": "test"}
    assert isinstance(response, KernelRelationClaimResponse)
    assert response.metadata == {"origin": "test"}


def test_get_graph_document_posts_json_and_validates_response() -> None:
    gateway, fake_client = _gateway_with_fake_client()
    seed_entity_id = uuid4()

    response = gateway.get_graph_document(
        space_id=uuid4(),
        request=KernelGraphDocumentRequest(
            mode="seeded",
            seed_entity_ids=[seed_entity_id],
            depth=3,
            top_k=15,
        ),
    )

    assert fake_client.last_method == "POST"
    assert fake_client.last_path is not None
    assert fake_client.last_path.endswith("/graph/document")
    assert fake_client.last_content is not None
    posted_payload = json.loads(fake_client.last_content)
    assert posted_payload["seed_entity_ids"] == [str(seed_entity_id)]
    assert posted_payload["depth"] == 3
    assert isinstance(response, KernelGraphDocumentResponse)
    assert response.meta.mode == "seeded"
    assert response.meta.seed_entity_ids == [seed_entity_id]
    assert response.nodes[0].label == "MED13"
    assert response.edges[0].metadata["source"] == "fake-http"


def test_graph_transport_bundle_merges_call_context_auth_into_custom_config() -> None:
    fake_client = _FakeHttpClient()
    gateway = GraphTransportBundle(
        config=GraphTransportConfig(
            base_url="http://graph.local",
            timeout_seconds=5.0,
            default_headers={"X-Test-Header": "present"},
        ),
        client=fake_client,
        call_context=GraphCallContext.service(graph_admin=True),
    )

    response = gateway.get_health()

    assert response.status == "ok"
    assert fake_client.last_headers is not None
    assert fake_client.last_headers["X-Test-Header"] == "present"
    assert fake_client.last_headers["Authorization"].startswith("Bearer ")


def test_get_graph_document_rejects_seeded_request_without_seed_entity_ids() -> None:
    gateway, fake_client = _gateway_with_fake_client()

    with pytest.raises(GraphServiceClientError) as exc_info:
        gateway.get_graph_document(
            space_id=uuid4(),
            request=KernelGraphDocumentRequest.model_construct(
                mode="seeded",
                seed_entity_ids=[],
                depth=2,
                top_k=10,
            ),
        )

    assert fake_client.last_method is None
    assert exc_info.value.status_code == 422
    assert (
        exc_info.value.detail
        == "seed_entity_ids must contain at least one value when mode='seeded'"
    )


@pytest.mark.parametrize(
    ("status_code", "expected_status_code"),
    [
        (404, 404),
        (422, 422),
        (500, 503),
    ],
)
def test_request_normalizes_graph_status_codes(
    status_code: int,
    expected_status_code: int,
) -> None:
    gateway = GraphTransportBundle(
        config=GraphTransportConfig(
            base_url="http://graph.local",
            timeout_seconds=5.0,
            default_headers={"Authorization": "Bearer test-token"},
        ),
        client=_ErrorStatusHttpClient(
            status_code=status_code,
            body=json.dumps({"detail": f"graph status {status_code}"}),
        ),
    )

    with pytest.raises(GraphServiceClientError) as exc_info:
        gateway.list_claims(space_id=uuid4())

    assert exc_info.value.status_code == expected_status_code
    assert exc_info.value.detail == json.dumps(
        {"detail": f"graph status {status_code}"},
    )


def test_graph_service_client_error_string_includes_upstream_detail() -> None:
    error = GraphServiceClientError(
        "Graph service request failed: GET /v1/spaces/test/claims",
        status_code=400,
        detail='{"detail":"invalid claim_status"}',
    )

    assert (
        str(error)
        == 'Graph service request failed: GET /v1/spaces/test/claims | detail={"detail":"invalid claim_status"}'
    )


def test_suggest_relations_surfaces_constraint_config_error_without_transport_rewrite() -> (
    None
):
    source_entity_id = UUID("11111111-1111-1111-1111-111111111111")
    gateway = GraphTransportBundle(
        config=GraphTransportConfig(
            base_url="http://graph.local",
            timeout_seconds=5.0,
            default_headers={"Authorization": "Bearer test-token"},
        ),
        client=_ErrorStatusHttpClient(
            status_code=400,
            body=json.dumps(
                {
                    "detail": (
                        "No active dictionary constraints available for source "
                        f"entity {source_entity_id} (DISEASE)."
                    ),
                },
            ),
        ),
    )

    with pytest.raises(GraphServiceClientError) as exc_info:
        gateway.suggest_relations(
            space_id=uuid4(),
            request=KernelRelationSuggestionRequest(
                source_entity_ids=[source_entity_id],
                limit_per_source=5,
                min_score=0.2,
            ),
        )

    assert exc_info.value.status_code == 400
    assert "No active dictionary constraints available for source entity" in (
        exc_info.value.detail or ""
    )


def test_suggest_relations_preserves_unmatched_constraint_error() -> None:
    source_entity_id = UUID("11111111-1111-1111-1111-111111111111")
    gateway = GraphTransportBundle(
        config=GraphTransportConfig(
            base_url="http://graph.local",
            timeout_seconds=5.0,
            default_headers={"Authorization": "Bearer test-token"},
        ),
        client=_ErrorStatusHttpClient(
            status_code=400,
            body=json.dumps(
                {
                    "detail": (
                        "No active dictionary constraints available for source "
                        "entity 22222222-2222-2222-2222-222222222222 (DISEASE)."
                    ),
                },
            ),
        ),
    )

    with pytest.raises(GraphServiceClientError) as exc_info:
        gateway.suggest_relations(
            space_id=uuid4(),
            request=KernelRelationSuggestionRequest(
                source_entity_ids=[source_entity_id],
                limit_per_source=5,
                min_score=0.2,
            ),
        )

    assert exc_info.value.status_code == 400


def test_request_normalizes_transport_failures_to_503() -> None:
    gateway = GraphTransportBundle(
        config=GraphTransportConfig(
            base_url="http://graph.local",
            timeout_seconds=5.0,
            default_headers={"Authorization": "Bearer test-token"},
        ),
        client=_TransportFailureHttpClient(),
    )

    with pytest.raises(GraphServiceClientError) as exc_info:
        gateway.list_claims(space_id=uuid4())

    assert exc_info.value.status_code == 503
    assert "graph service unreachable" in (exc_info.value.detail or "")


def test_request_includes_request_id_header_from_context() -> None:
    gateway, fake_client = _gateway_with_fake_client()

    with request_id_context("graph-trace-123"):
        gateway.list_entities(space_id=uuid4())

    assert fake_client.last_headers is not None
    assert fake_client.last_headers[REQUEST_ID_HEADER] == "graph-trace-123"


def test_get_health_uses_local_health_response_model() -> None:
    gateway, fake_client = _gateway_with_fake_client()

    response = gateway.get_health()

    assert fake_client.last_method == "GET"
    assert fake_client.last_path == "/health"
    assert response == GraphServiceHealthResponse(status="ok", version="graph-test")


def test_refresh_entity_embeddings_posts_refresh_payload() -> None:
    gateway, fake_client = _gateway_with_fake_client()

    response = gateway.refresh_entity_embeddings(
        space_id=uuid4(),
        request=KernelEntityEmbeddingRefreshRequest(
            entity_ids=[uuid4(), uuid4()],
            limit=2,
        ),
    )

    assert response.refreshed == 1
    assert fake_client.last_method == "POST"
    assert fake_client.last_path is not None
    assert fake_client.last_path.endswith("/entities/embeddings/refresh")
    assert fake_client.last_content is not None
    payload = json.loads(fake_client.last_content)
    assert payload["limit"] == 2
    assert len(payload["entity_ids"]) == 2


def test_list_entity_embedding_status_uses_status_endpoint() -> None:
    gateway, fake_client = _gateway_with_fake_client()
    entity_ids = [str(uuid4()), str(uuid4())]

    response = gateway.list_entity_embedding_status(
        space_id=uuid4(),
        entity_ids=entity_ids,
    )

    assert response.total == 1
    assert response.statuses[0].state == "ready"
    assert fake_client.last_method == "GET"
    assert fake_client.last_path is not None
    assert fake_client.last_path.endswith("/entities/embeddings/status")
    assert fake_client.last_params == {"entity_ids": ",".join(entity_ids)}


def test_create_entity_proposes_missing_entity_type() -> None:
    fake_client = _EntityValidationHttpClient()
    gateway = _gateway_with_client(fake_client)
    preflight_service, submission_service = _preflight_services(gateway)
    resolved = preflight_service.prepare_entity_create(
        space_id=uuid4(),
        entity_type="GENE",
        display_label="MED13",
        aliases=None,
        graph_transport=gateway,
    )

    with pytest.raises(GraphServiceClientError) as exc_info:
        submission_service.submit_resolved_intent(
            resolved_intent=resolved,
            graph_transport=gateway,
        )

    assert "Entity type GENE is not approved." in str(exc_info.value)
    assert fake_client.calls[0][1].endswith("/validate/entity")
    assert ("GET", "/v1/dictionary/entity-types") in fake_client.calls
    assert ("POST", "/v1/dictionary/proposals/entity-types") in fake_client.calls
    assert fake_client.proposal_payload == {
        "id": "GENE",
        "display_name": "Gene",
        "description": (
            "Proposed entity type discovered during graph entity validation."
        ),
        "domain_context": "general",
        "expected_properties": {},
        "rationale": "Entity preflight found no approved entity type for GENE.",
        "evidence_payload": {
            "source": "graph_preflight",
            "display_label": "MED13",
        },
        "external_ontology_ref": None,
        "source_ref": "graph-preflight:proposal:entity-type:gene",
    }
    assert all(not url.endswith("/entities") for _, url in fake_client.calls)


def test_submit_resolved_intent_does_not_close_parent_gateway_client() -> None:
    fake_client = _FakeHttpClient()
    gateway = GraphTransportBundle(
        config=GraphTransportConfig(
            base_url="http://graph.local",
            timeout_seconds=5.0,
            default_headers={"Authorization": "Bearer test-token"},
        ),
        client=fake_client,
    )
    gateway._runtime.owns_client = True  # noqa: SLF001 - regression harness for ownership bug
    preflight_service, submission_service = _preflight_services(gateway)

    resolved = preflight_service.prepare_entity_create(
        space_id=uuid4(),
        entity_type="GENE",
        display_label="MED13",
        aliases=["Mediator complex subunit 13"],
        graph_transport=gateway,
    )

    created = submission_service.submit_resolved_intent(
        resolved_intent=resolved,
        graph_transport=gateway,
    )
    health = gateway.get_health()

    assert created["display_label"] == "MED13"
    assert health.status == "ok"
    assert fake_client.closed is False


def test_submit_resolved_intent_preserves_entity_metadata_and_identifiers() -> None:
    fake_client = _FakeHttpClient()
    gateway = GraphTransportBundle(
        config=GraphTransportConfig(
            base_url="http://graph.local",
            timeout_seconds=5.0,
            default_headers={"Authorization": "Bearer test-token"},
        ),
        client=fake_client,
    )
    preflight_service, submission_service = _preflight_services(gateway)

    resolved = preflight_service.prepare_entity_create(
        space_id=uuid4(),
        entity_type="VARIANT",
        display_label="c.977C>A",
        aliases=["NM_015335.6:c.977C>A (p.Thr326Lys)"],
        metadata={
            "transcript": "NM_015335.6",
            "source_anchors": {
                "gene_symbol": "MED13",
                "hgvs_notation": "c.977C>A",
            },
        },
        identifiers={
            "gene_symbol": "MED13",
            "hgvs_notation": "c.977C>A",
        },
        graph_transport=gateway,
    )

    created = submission_service.submit_resolved_intent(
        resolved_intent=resolved,
        graph_transport=gateway,
    )

    assert created["display_label"] == "c.977C>A"
    assert fake_client.last_content is not None
    payload = json.loads(fake_client.last_content)
    assert payload["metadata"]["transcript"] == "NM_015335.6"
    assert payload["metadata"]["source_anchors"] == {
        "gene_symbol": "MED13",
        "hgvs_notation": "c.977C>A",
    }
    assert payload["identifiers"] == {
        "gene_symbol": "MED13",
        "hgvs_notation": "c.977C>A",
    }


class _ClaimValidationHttpClient:
    def __init__(
        self,
        *,
        validation_responses: list[KernelGraphValidationResponse],
        known_relation_types: list[str] | None = None,
        relation_types_status_code: int = 200,
    ) -> None:
        self.calls: list[tuple[str, str]] = []
        self.validation_payloads: list[dict[str, object]] = []
        self.claim_payload: dict[str, object] | None = None
        self.relation_type_proposal_payload: dict[str, object] | None = None
        self.relation_constraint_proposal_payload: dict[str, object] | None = None
        self._validation_responses = list(validation_responses)
        self._known_relation_types = known_relation_types or ["ASSOCIATED_WITH"]
        self._relation_types_status_code = relation_types_status_code

    def request(
        self,
        method: str,
        url: str,
        *,
        params: object = None,
        headers: dict[str, str] | None = None,
        content: str | None = None,
    ) -> httpx.Response:
        del params, headers
        self.calls.append((method, url))
        request = httpx.Request(method, f"http://graph.local{url}")

        if method == "POST" and url.endswith("/validate/claim") and content is not None:
            self.validation_payloads.append(json.loads(content))
            if not self._validation_responses:
                return httpx.Response(
                    status_code=500,
                    content="missing validation fixture",
                    request=request,
                )
            response = self._validation_responses.pop(0)
            return httpx.Response(
                status_code=200,
                content=response.model_dump_json(),
                request=request,
            )

        if method == "GET" and url == "/v1/dictionary/relation-types":
            if self._relation_types_status_code != 200:
                return httpx.Response(
                    status_code=self._relation_types_status_code,
                    content="dictionary unavailable",
                    request=request,
                )
            payload = {
                "relation_types": [
                    _dictionary_relation_type_payload(relation_type)
                    for relation_type in self._known_relation_types
                ],
                "total": len(self._known_relation_types),
            }
            return httpx.Response(
                status_code=200,
                content=json.dumps(payload),
                request=request,
            )

        if method == "GET" and url.startswith("/v1/dictionary/search/by-domain/"):
            return httpx.Response(
                status_code=200,
                content=json.dumps({"results": [], "total": 0}),
                request=request,
            )

        if (
            method == "POST"
            and url == "/v1/dictionary/proposals/relation-types"
            and content is not None
        ):
            self.relation_type_proposal_payload = json.loads(content)
            return httpx.Response(
                status_code=201,
                content=json.dumps(
                    _dictionary_proposal_payload(
                        "RELATION_TYPE",
                        relation_type=self.relation_type_proposal_payload["id"],
                        display_name=self.relation_type_proposal_payload[
                            "display_name"
                        ],
                        description=self.relation_type_proposal_payload["description"],
                        domain_context=self.relation_type_proposal_payload[
                            "domain_context"
                        ],
                        rationale=self.relation_type_proposal_payload["rationale"],
                        evidence_payload=self.relation_type_proposal_payload[
                            "evidence_payload"
                        ],
                        is_directional=self.relation_type_proposal_payload[
                            "is_directional"
                        ],
                        inverse_label=self.relation_type_proposal_payload[
                            "inverse_label"
                        ],
                        source_ref=self.relation_type_proposal_payload["source_ref"],
                    ),
                ),
                request=request,
            )

        if (
            method == "POST"
            and url == "/v1/dictionary/proposals/relation-constraints"
            and content is not None
        ):
            self.relation_constraint_proposal_payload = json.loads(content)
            return httpx.Response(
                status_code=201,
                content=json.dumps(
                    _dictionary_proposal_payload(
                        "RELATION_CONSTRAINT",
                        source_type=self.relation_constraint_proposal_payload[
                            "source_type"
                        ],
                        relation_type=self.relation_constraint_proposal_payload[
                            "relation_type"
                        ],
                        target_type=self.relation_constraint_proposal_payload[
                            "target_type"
                        ],
                        rationale=self.relation_constraint_proposal_payload[
                            "rationale"
                        ],
                        evidence_payload=self.relation_constraint_proposal_payload[
                            "evidence_payload"
                        ],
                        is_allowed=self.relation_constraint_proposal_payload[
                            "is_allowed"
                        ],
                        requires_evidence=self.relation_constraint_proposal_payload[
                            "requires_evidence"
                        ],
                        profile=self.relation_constraint_proposal_payload["profile"],
                        source_ref=self.relation_constraint_proposal_payload[
                            "source_ref"
                        ],
                    ),
                ),
                request=request,
            )

        if method == "POST" and url.endswith("/claims") and content is not None:
            self.claim_payload = json.loads(content)
            response_payload = KernelRelationClaimResponse(
                id=uuid4(),
                research_space_id=uuid4(),
                source_document_id=None,
                source_document_ref="harness_proposal:test",
                agent_run_id="graph-harness:test",
                source_type="PUBMED",
                relation_type=str(self.claim_payload["relation_type"]),
                target_type="PHENOTYPE",
                source_label="MED13",
                target_label="DD/ID",
                confidence=0.7,
                validation_state="ALLOWED",
                validation_reason="created_via_claim_api",
                persistability="PERSISTABLE",
                claim_status="OPEN",
                polarity="SUPPORT",
                claim_text=str(self.claim_payload["claim_text"]),
                claim_section=None,
                linked_relation_id=None,
                metadata=self.claim_payload["metadata"],
                triaged_by=None,
                triaged_at=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            return httpx.Response(
                status_code=200,
                content=response_payload.model_dump_json(),
                request=request,
            )

        if method == "POST" and url in {
            "/v1/dictionary/relation-types",
            "/v1/dictionary/relation-constraints",
        }:
            return httpx.Response(
                status_code=500,
                content="unexpected official dictionary mutation",
                request=request,
            )

        return httpx.Response(status_code=404, content="not found", request=request)

    def close(self) -> None:
        return None


def test_create_claim_posts_after_allowed_preflight() -> None:
    fake_client = _ClaimValidationHttpClient(
        validation_responses=[
            KernelGraphValidationResponse(
                valid=True,
                code="allowed",
                message="This claim can be created.",
                severity="info",
                next_actions=[],
                normalized_relation_type="ASSOCIATED_WITH",
                source_type="GENE",
                target_type="PHENOTYPE",
                requires_evidence=True,
                profile="ALLOWED",
                validation_state="ALLOWED",
                validation_reason="created_via_claim_api",
                persistability="PERSISTABLE",
            ),
        ],
    )
    gateway = _gateway_with_client(fake_client)
    preflight_service, submission_service = _preflight_services(gateway)
    resolved = asyncio.run(
        preflight_service.prepare_claim_create(
            space_id=uuid4(),
            request=KernelRelationClaimCreateRequest(
                source_entity_id=UUID("11111111-1111-1111-1111-111111111111"),
                target_entity_id=UUID("22222222-2222-2222-2222-222222222222"),
                relation_type="associated with",
                assessment=_SUPPORTED_ASSESSMENT,
                claim_text="MED13 is associated with DD/ID.",
                evidence_summary="Supported by document evidence.",
                source_document_ref="harness_proposal:test",
                metadata={"origin": "test"},
            ),
            graph_transport=gateway,
        ),
    )
    response = submission_service.submit_resolved_intent(
        resolved_intent=resolved,
        graph_transport=gateway,
    )

    assert fake_client.calls[0][1].endswith("/validate/claim")
    assert fake_client.calls[-1][1].endswith("/claims")
    assert fake_client.claim_payload is not None
    assert fake_client.claim_payload["relation_type"] == "ASSOCIATED_WITH"
    assert response.validation_state == "ALLOWED"
    assert response.persistability == "PERSISTABLE"


def test_create_claim_proposes_missing_relation_type_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_kernel_relation_register_new(
        monkeypatch,
        canonical_type="PROTECTS_AGAINST",
        reasoning="Relation type PROTECTS_AGAINST is not approved.",
    )
    fake_client = _ClaimValidationHttpClient(
        validation_responses=[
            KernelGraphValidationResponse(
                valid=False,
                code="unknown_relation_type",
                message="Relation type PROTECTS_AGAINST is not approved.",
                severity="blocking",
                next_actions=[],
                normalized_relation_type="PROTECTS_AGAINST",
                source_type="GENE",
                target_type="PHENOTYPE",
                validation_state="UNDEFINED",
                validation_reason="relation_type_not_found_in_dictionary",
                persistability="NON_PERSISTABLE",
            ),
        ],
        known_relation_types=["ASSOCIATED_WITH", "INTERACTS_WITH"],
    )
    gateway = _gateway_with_client(fake_client)
    preflight_service, submission_service = _preflight_services(gateway)
    resolved = asyncio.run(
        preflight_service.prepare_claim_create(
            space_id=uuid4(),
            request=KernelRelationClaimCreateRequest(
                source_entity_id=UUID("11111111-1111-1111-1111-111111111111"),
                target_entity_id=UUID("22222222-2222-2222-2222-222222222222"),
                relation_type="PROTECTS_AGAINST",
                assessment=_SUPPORTED_ASSESSMENT,
                claim_text="MED13 protects against developmental delay.",
                evidence_summary="Supported by document evidence.",
                source_document_ref="pmid:123",
                metadata={"origin": "test"},
            ),
            graph_transport=gateway,
        ),
    )

    with pytest.raises(GraphServiceClientError) as exc_info:
        submission_service.submit_resolved_intent(
            resolved_intent=resolved,
            graph_transport=gateway,
        )

    assert "not approved" in str(exc_info.value)
    assert fake_client.calls[0][1].endswith("/validate/claim")
    assert ("POST", "/v1/dictionary/proposals/relation-types") in fake_client.calls
    assert fake_client.relation_type_proposal_payload == {
        "id": "PROTECTS_AGAINST",
        "display_name": "Protects Against",
        "description": (
            "Proposed relation type discovered during graph relation validation."
        ),
        "domain_context": "general",
        "rationale": (
            "Relation preflight found no approved relation type for PROTECTS_AGAINST."
        ),
        "evidence_payload": {
            "source": "graph_preflight",
            "source_document_ref": "pmid:123",
            "claim_text": "MED13 protects against developmental delay.",
        },
        "is_directional": True,
        "inverse_label": None,
        "source_ref": "graph-preflight:proposal:relation-type:protects_against",
    }
    assert all(not url.endswith("/claims") for _, url in fake_client.calls)


def test_create_claim_proposes_missing_constraint_without_mutation() -> None:
    fake_client = _ClaimValidationHttpClient(
        validation_responses=[
            KernelGraphValidationResponse(
                valid=False,
                code="relation_constraint_not_allowed",
                message="This source, relation, and target combination is not approved.",
                severity="blocking",
                next_actions=[],
                normalized_relation_type="ASSOCIATED_WITH",
                source_type="GENE",
                target_type="PHENOTYPE",
                requires_evidence=True,
                profile="REVIEW_ONLY",
                validation_state="REVIEW_ONLY",
                validation_reason="relation_not_allowed_by_active_constraints",
                persistability="NON_PERSISTABLE",
            ),
        ],
    )
    gateway = _gateway_with_client(fake_client)
    preflight_service, submission_service = _preflight_services(gateway)
    resolved = asyncio.run(
        preflight_service.prepare_claim_create(
            space_id=uuid4(),
            request=KernelRelationClaimCreateRequest(
                source_entity_id=UUID("11111111-1111-1111-1111-111111111111"),
                target_entity_id=UUID("22222222-2222-2222-2222-222222222222"),
                relation_type="ASSOCIATED_WITH",
                assessment=_SUPPORTED_ASSESSMENT,
                claim_text="MED13 is associated with DD/ID.",
                evidence_summary="Supported by document evidence.",
                source_document_ref="pmid:123",
                metadata={"origin": "test"},
            ),
            graph_transport=gateway,
        ),
    )

    with pytest.raises(GraphServiceClientError) as exc_info:
        submission_service.submit_resolved_intent(
            resolved_intent=resolved,
            graph_transport=gateway,
        )

    assert "not approved" in str(exc_info.value)
    assert fake_client.calls[0][1].endswith("/validate/claim")
    assert (
        "POST",
        "/v1/dictionary/proposals/relation-constraints",
    ) in fake_client.calls
    assert fake_client.relation_constraint_proposal_payload == {
        "source_type": "GENE",
        "relation_type": "ASSOCIATED_WITH",
        "target_type": "PHENOTYPE",
        "rationale": (
            "Claim preflight found no approved relation constraint for this triple."
        ),
        "evidence_payload": {
            "source": "graph_preflight",
        },
        "is_allowed": True,
        "requires_evidence": True,
        "profile": "REVIEW_ONLY",
        "source_ref": (
            "graph-preflight:proposal:relation-constraint:"
            "gene:associated_with:phenotype"
        ),
    }
    assert all(not url.endswith("/claims") for _, url in fake_client.calls)


def test_create_claim_fuzzy_matches_known_relation_type_before_write() -> None:
    fake_client = _ClaimValidationHttpClient(
        validation_responses=[
            KernelGraphValidationResponse(
                valid=False,
                code="unknown_relation_type",
                message="Relation type REPRESSS is not approved.",
                severity="blocking",
                next_actions=[],
                normalized_relation_type="REPRESSS",
                source_type="GENE",
                target_type="PHENOTYPE",
                validation_state="UNDEFINED",
                validation_reason="relation_type_not_found_in_dictionary",
                persistability="NON_PERSISTABLE",
            ),
            KernelGraphValidationResponse(
                valid=True,
                code="allowed",
                message="This claim can be created.",
                severity="info",
                next_actions=[],
                normalized_relation_type="REPRESSES",
                source_type="GENE",
                target_type="PHENOTYPE",
                requires_evidence=True,
                profile="ALLOWED",
                validation_state="ALLOWED",
                validation_reason="created_via_claim_api",
                persistability="PERSISTABLE",
            ),
        ],
        known_relation_types=["REPRESSES", "INHIBITS"],
    )
    gateway = _gateway_with_client(fake_client)
    preflight_service, submission_service = _preflight_services(gateway)
    resolved = asyncio.run(
        preflight_service.prepare_claim_create(
            space_id=uuid4(),
            request=KernelRelationClaimCreateRequest(
                source_entity_id=UUID("11111111-1111-1111-1111-111111111111"),
                target_entity_id=UUID("22222222-2222-2222-2222-222222222222"),
                relation_type="REPRESSS",
                assessment=_SUPPORTED_ASSESSMENT,
                claim_text="Gene X represses gene Y.",
                evidence_summary="From document analysis.",
                source_document_ref="harness_proposal:test",
                metadata={"origin": "test"},
            ),
            graph_transport=gateway,
        ),
    )
    response = submission_service.submit_resolved_intent(
        resolved_intent=resolved,
        graph_transport=gateway,
    )

    assert fake_client.calls[0][1].endswith("/validate/claim")
    assert fake_client.calls[-1][1].endswith("/claims")
    assert fake_client.claim_payload is not None
    assert fake_client.claim_payload["relation_type"] in {"REPRESSS", "REPRESSES"}
    assert fake_client.relation_type_proposal_payload is None
    assert response.relation_type in {"REPRESSS", "REPRESSES"}


def test_create_claim_dictionary_fetch_failure_proposes_and_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_kernel_relation_register_new(
        monkeypatch,
        canonical_type="PROTECTS_AGAINST",
        reasoning="Relation type PROTECTS_AGAINST is not approved.",
    )
    fake_client = _ClaimValidationHttpClient(
        validation_responses=[
            KernelGraphValidationResponse(
                valid=False,
                code="unknown_relation_type",
                message="Relation type PROTECTS_AGAINST is not approved.",
                severity="blocking",
                next_actions=[],
                normalized_relation_type="PROTECTS_AGAINST",
                source_type="GENE",
                target_type="PHENOTYPE",
                validation_state="UNDEFINED",
                validation_reason="relation_type_not_found_in_dictionary",
                persistability="NON_PERSISTABLE",
            ),
        ],
        relation_types_status_code=500,
    )
    gateway = _gateway_with_client(fake_client)
    preflight_service, submission_service = _preflight_services(gateway)
    resolved = asyncio.run(
        preflight_service.prepare_claim_create(
            space_id=uuid4(),
            request=KernelRelationClaimCreateRequest(
                source_entity_id=UUID("11111111-1111-1111-1111-111111111111"),
                target_entity_id=UUID("22222222-2222-2222-2222-222222222222"),
                relation_type="PROTECTS_AGAINST",
                assessment=_SUPPORTED_ASSESSMENT,
                claim_text="MED13 protects against developmental delay.",
                evidence_summary="Supported by document evidence.",
                source_document_ref="pmid:123",
                metadata={"origin": "test"},
            ),
            graph_transport=gateway,
        ),
    )

    with pytest.raises(GraphServiceClientError) as exc_info:
        submission_service.submit_resolved_intent(
            resolved_intent=resolved,
            graph_transport=gateway,
        )

    assert "not approved" in str(exc_info.value)
    assert fake_client.calls[0][1].endswith("/validate/claim")
    assert fake_client.relation_type_proposal_payload is not None
    assert all(not url.endswith("/claims") for _, url in fake_client.calls)


def test_create_entity_rejects_inactive_entity_type_without_mutation() -> None:
    fake_client = _InactiveEntityTypeHttpClient()
    gateway = _gateway_with_client(fake_client)
    preflight_service, submission_service = _preflight_services(gateway)
    resolved = preflight_service.prepare_entity_create(
        space_id=uuid4(),
        entity_type="GENE",
        display_label="MED13",
        aliases=None,
        graph_transport=gateway,
    )

    with pytest.raises(GraphServiceClientError) as exc_info:
        submission_service.submit_resolved_intent(
            resolved_intent=resolved,
            graph_transport=gateway,
        )

    assert "exists but is not active" in str(exc_info.value)
    assert len(fake_client.calls) == 1
    assert fake_client.calls[0][1].endswith("/validate/entity")


def test_create_relation_posts_after_allowed_preflight() -> None:
    fake_client = _RelationValidationHttpClient(
        validation_response=KernelGraphValidationResponse(
            valid=True,
            code="allowed",
            message="This relation can be created.",
            severity="info",
            next_actions=[],
            normalized_relation_type="ASSOCIATED_WITH",
            source_type="GENE",
            target_type="PHENOTYPE",
            requires_evidence=True,
            profile="ALLOWED",
            validation_state="ALLOWED",
            validation_reason="created_via_claim_api",
            persistability="PERSISTABLE",
        ),
    )
    gateway = _gateway_with_client(fake_client)
    preflight_service, submission_service = _preflight_services(gateway)
    resolved = asyncio.run(
        preflight_service.prepare_relation_create(
            space_id=uuid4(),
            request=KernelRelationCreateRequest(
                source_id=UUID("11111111-1111-1111-1111-111111111111"),
                target_id=UUID("22222222-2222-2222-2222-222222222222"),
                relation_type="associated with",
                assessment=_SUPPORTED_ASSESSMENT,
                evidence_summary="Supported by manual curator evidence.",
                source_document_ref="pmid:123",
                metadata={"origin": "test"},
            ),
            graph_transport=gateway,
        ),
    )
    response = submission_service.submit_resolved_intent(
        resolved_intent=resolved,
        graph_transport=gateway,
    )

    assert fake_client.calls[0][1].endswith("/validate/triple")
    assert fake_client.calls[-1][1].endswith("/relations")
    assert fake_client.relation_payload is not None
    assert fake_client.relation_payload["relation_type"] == "ASSOCIATED_WITH"
    assert response.relation_type == "ASSOCIATED_WITH"


def test_create_relation_proposes_missing_relation_type_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_kernel_relation_register_new(
        monkeypatch,
        canonical_type="PROTECTS_AGAINST",
        reasoning="Relation type PROTECTS_AGAINST is not approved.",
    )
    fake_client = _RelationValidationHttpClient(
        validation_response=KernelGraphValidationResponse(
            valid=False,
            code="unknown_relation_type",
            message="Relation type PROTECTS_AGAINST is not approved.",
            severity="blocking",
            next_actions=[],
            normalized_relation_type="PROTECTS_AGAINST",
            source_type="GENE",
            target_type="PHENOTYPE",
            validation_state="UNDEFINED",
            validation_reason="relation_type_not_found_in_dictionary",
            persistability="NON_PERSISTABLE",
        ),
        known_relation_types=["ASSOCIATED_WITH", "INTERACTS_WITH"],
    )
    gateway = _gateway_with_client(fake_client)
    preflight_service, submission_service = _preflight_services(gateway)
    resolved = asyncio.run(
        preflight_service.prepare_relation_create(
            space_id=uuid4(),
            request=KernelRelationCreateRequest(
                source_id=UUID("11111111-1111-1111-1111-111111111111"),
                target_id=UUID("22222222-2222-2222-2222-222222222222"),
                relation_type="PROTECTS_AGAINST",
                assessment=_SUPPORTED_ASSESSMENT,
                evidence_sentence="MED13 protects against developmental delay.",
                source_document_ref="pmid:123",
                metadata={"origin": "test"},
            ),
            graph_transport=gateway,
        ),
    )

    with pytest.raises(GraphServiceClientError) as exc_info:
        submission_service.submit_resolved_intent(
            resolved_intent=resolved,
            graph_transport=gateway,
        )

    assert "not approved" in str(exc_info.value)
    assert fake_client.calls[0][1].endswith("/validate/triple")
    assert ("POST", "/v1/dictionary/proposals/relation-types") in fake_client.calls
    assert fake_client.relation_type_proposal_payload == {
        "id": "PROTECTS_AGAINST",
        "display_name": "Protects Against",
        "description": (
            "Proposed relation type discovered during graph relation validation."
        ),
        "domain_context": "general",
        "rationale": (
            "Relation preflight found no approved relation type for PROTECTS_AGAINST."
        ),
        "evidence_payload": {
            "source": "graph_preflight",
            "source_document_ref": "pmid:123",
            "claim_text": "MED13 protects against developmental delay.",
        },
        "is_directional": True,
        "inverse_label": None,
        "source_ref": "graph-preflight:proposal:relation-type:protects_against",
    }
    assert all(not url.endswith("/relations") for _, url in fake_client.calls)


def test_preflight_resolves_relation_synonym_before_ai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _RelationValidationHttpClient(
        validation_responses=[
            KernelGraphValidationResponse(
                valid=False,
                code="unknown_relation_type",
                message="Relation type GENERATES is not approved.",
                severity="blocking",
                next_actions=[],
                normalized_relation_type="GENERATES",
                source_type="GENE",
                target_type="PHENOTYPE",
                validation_state="UNDEFINED",
                validation_reason="relation_type_not_found_in_dictionary",
                persistability="NON_PERSISTABLE",
            ),
            KernelGraphValidationResponse(
                valid=True,
                code="allowed",
                message="This relation can be created.",
                severity="info",
                next_actions=[],
                normalized_relation_type="PRODUCES",
                source_type="GENE",
                target_type="PHENOTYPE",
                requires_evidence=True,
                profile="ALLOWED",
                validation_state="ALLOWED",
                validation_reason="created_via_claim_api",
                persistability="PERSISTABLE",
            ),
        ],
        known_relation_types=["PRODUCES"],
        relation_synonym_match="PRODUCES",
    )
    gateway = _gateway_with_client(fake_client)
    preflight_service, submission_service = _preflight_services(gateway)

    async def _unexpected_kernel_call(*_: object, **__: object) -> object:
        raise AssertionError(
            "Artana Kernel should be skipped for deterministic synonym resolution"
        )

    monkeypatch.setattr(
        "artana_evidence_api.graph_integration.preflight.resolve_relation_with_kernel",
        _unexpected_kernel_call,
    )

    resolved = asyncio.run(
        preflight_service.prepare_relation_create(
            space_id=uuid4(),
            request=KernelRelationCreateRequest(
                source_id=UUID("11111111-1111-1111-1111-111111111111"),
                target_id=UUID("22222222-2222-2222-2222-222222222222"),
                relation_type="generates",
                assessment=_SUPPORTED_ASSESSMENT,
                evidence_summary="Supported by manual curator evidence.",
                source_document_ref="pmid:123",
                metadata={"origin": "test"},
            ),
            graph_transport=gateway,
        ),
    )
    response = submission_service.submit_resolved_intent(
        resolved_intent=resolved,
        graph_transport=gateway,
    )

    assert response.relation_type == "PRODUCES"
    assert fake_client.relation_type_proposal_payload is None
    assert ("GET", "/v1/dictionary/relation-synonyms/resolve") in fake_client.calls
    assert ("POST", "/v1/dictionary/proposals/relation-types") not in fake_client.calls
    assert fake_client.calls[-1][1].endswith("/relations")


class _AIFullModeHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.headers: list[dict[str, str] | None] = []
        self.concept_payload: dict[str, object] | None = None
        self.graph_change_payload: dict[str, object] | None = None
        self.ai_decision_payload: dict[str, object] | None = None
        self.connector_payload: dict[str, object] | None = None
        self.operating_mode_payload: dict[str, object] | None = None
        self.workflow_payload: dict[str, object] | None = None
        self.workflow_action_payload: dict[str, object] | None = None
        self.workflow_id = uuid4()

    def request(
        self,
        method: str,
        url: str,
        *,
        params: object = None,
        headers: dict[str, str] | None = None,
        content: str | None = None,
    ) -> httpx.Response:
        del params
        self.calls.append((method, url))
        self.headers.append(headers)
        request = httpx.Request(method, f"http://graph.local{url}")
        now = datetime.now(UTC)
        space_id = url.split("/")[3]

        if method == "GET" and url.endswith("/operating-mode"):
            response_payload = OperatingModeResponse(
                research_space_id=space_id,
                mode="manual",
                workflow_policy=GraphWorkflowPolicy(),
                capabilities={"ai_graph_repair_allowed": False},
            )
            return httpx.Response(
                status_code=200,
                content=response_payload.model_dump_json(),
                request=request,
            )

        if (
            method == "PATCH"
            and url.endswith("/operating-mode")
            and content is not None
        ):
            self.operating_mode_payload = json.loads(content)
            response_payload = OperatingModeResponse(
                research_space_id=space_id,
                mode="ai_full_graph",
                workflow_policy=GraphWorkflowPolicy(
                    allow_ai_graph_repair=True,
                    trusted_ai_principals=["agent:test"],
                ),
                capabilities={"ai_graph_repair_allowed": True},
            )
            return httpx.Response(
                status_code=200,
                content=response_payload.model_dump_json(),
                request=request,
            )

        if method == "GET" and url.endswith("/operating-mode/capabilities"):
            response_payload = OperatingModeCapabilitiesResponse(
                research_space_id=space_id,
                mode="ai_full_graph",
                capabilities={"ai_graph_repair_allowed": True},
            )
            return httpx.Response(
                status_code=200,
                content=response_payload.model_dump_json(),
                request=request,
            )

        if method == "POST" and url.endswith("/workflows") and content is not None:
            self.workflow_payload = json.loads(content)
            response_payload = GraphWorkflowResponse(
                id=str(self.workflow_id),
                research_space_id=space_id,
                kind="evidence_approval",
                status="PLAN_READY",
                operating_mode="ai_full_graph",
                input_payload={"source": "test"},
                plan_payload={"next_action": "approve"},
                generated_resources_payload={"graph_change_proposal_ids": ["p-1"]},
                decision_payload={},
                policy_payload={},
                explanation_payload={"why_this_exists": "test"},
                source_ref="workflow-source-ref",
                workflow_hash="c" * 64,
                created_by="manual:test",
                updated_by="manual:test",
                created_at=now,
                updated_at=now,
            )
            return httpx.Response(
                status_code=201,
                content=response_payload.model_dump_json(),
                request=request,
            )

        if method == "GET" and url.endswith("/workflows"):
            workflow = GraphWorkflowResponse(
                id=str(self.workflow_id),
                research_space_id=space_id,
                kind="evidence_approval",
                status="PLAN_READY",
                operating_mode="ai_full_graph",
                input_payload={"source": "test"},
                plan_payload={},
                generated_resources_payload={},
                decision_payload={},
                policy_payload={},
                explanation_payload={},
                source_ref="workflow-source-ref",
                workflow_hash="c" * 64,
                created_by="manual:test",
                updated_by="manual:test",
                created_at=now,
                updated_at=now,
            )
            response_payload = GraphWorkflowListResponse(
                workflows=[workflow],
                total=1,
                offset=0,
                limit=100,
            )
            return httpx.Response(
                status_code=200,
                content=response_payload.model_dump_json(),
                request=request,
            )

        if method == "GET" and f"/workflows/{self.workflow_id}" in url:
            response_payload = GraphWorkflowResponse(
                id=str(self.workflow_id),
                research_space_id=space_id,
                kind="evidence_approval",
                status="PLAN_READY",
                operating_mode="ai_full_graph",
                input_payload={"source": "test"},
                plan_payload={},
                generated_resources_payload={},
                decision_payload={},
                policy_payload={},
                explanation_payload={},
                source_ref="workflow-source-ref",
                workflow_hash="c" * 64,
                created_by="manual:test",
                updated_by="manual:test",
                created_at=now,
                updated_at=now,
            )
            return httpx.Response(
                status_code=200,
                content=response_payload.model_dump_json(),
                request=request,
            )

        if method == "POST" and url.endswith("/actions") and content is not None:
            self.workflow_action_payload = json.loads(content)
            response_payload = GraphWorkflowResponse(
                id=str(self.workflow_id),
                research_space_id=space_id,
                kind="evidence_approval",
                status="APPLIED",
                operating_mode="ai_full_graph",
                input_payload={"source": "test"},
                plan_payload={},
                generated_resources_payload={},
                decision_payload={"approved": True},
                policy_payload={"outcome": "human_required"},
                explanation_payload={},
                source_ref="workflow-source-ref",
                workflow_hash="d" * 64,
                created_by="manual:test",
                updated_by="manual:test",
                created_at=now,
                updated_at=now,
            )
            return httpx.Response(
                status_code=200,
                content=response_payload.model_dump_json(),
                request=request,
            )

        if method == "GET" and "/explain/workflow/" in url:
            response_payload = ExplanationResponse(
                research_space_id=space_id,
                resource_type="workflow",
                resource_id=str(self.workflow_id),
                why_this_exists="A workflow was created for governed graph review.",
                generated_resources={"graph_change_proposal_ids": ["p-1"]},
            )
            return httpx.Response(
                status_code=200,
                content=response_payload.model_dump_json(),
                request=request,
            )

        if (
            method == "POST"
            and url.endswith("/concepts/proposals")
            and content is not None
        ):
            self.concept_payload = json.loads(content)
            synonyms = cast("list[object]", self.concept_payload["synonyms"])
            response_payload = ConceptProposalResponse(
                id=str(uuid4()),
                research_space_id=space_id,
                status="SUBMITTED",
                candidate_decision="CREATE_NEW",
                domain_context=str(self.concept_payload["domain_context"]),
                entity_type=str(self.concept_payload["entity_type"]),
                canonical_label=str(self.concept_payload["canonical_label"]),
                normalized_label=str(self.concept_payload["canonical_label"]).lower(),
                concept_set_id=None,
                existing_concept_member_id=None,
                applied_concept_member_id=None,
                synonyms_payload=[str(item) for item in synonyms],
                external_refs_payload=[],
                evidence_payload={"source": "test"},
                duplicate_checks_payload={},
                warnings_payload=[],
                decision_payload={},
                rationale=None,
                proposed_by="manual:test",
                reviewed_by=None,
                reviewed_at=None,
                decision_reason=None,
                source_ref=str(self.concept_payload["source_ref"]),
                proposal_hash="a" * 64,
                created_at=now,
                updated_at=now,
            )
            return httpx.Response(
                status_code=201,
                content=response_payload.model_dump_json(),
                request=request,
            )

        if (
            method == "POST"
            and url.endswith("/graph-change-proposals")
            and content is not None
        ):
            self.graph_change_payload = json.loads(content)
            concepts = cast("list[object]", self.graph_change_payload["concepts"])
            response_payload = GraphChangeProposalResponse(
                id=str(uuid4()),
                research_space_id=space_id,
                status="READY_FOR_REVIEW",
                proposal_payload={"concepts": concepts},
                resolution_plan_payload={"errors": []},
                warnings_payload=[],
                error_payload=[],
                applied_concept_member_ids_payload=[],
                applied_claim_ids_payload=[],
                proposed_by="manual:test",
                reviewed_by=None,
                reviewed_at=None,
                decision_reason=None,
                source_ref=str(self.graph_change_payload["source_ref"]),
                proposal_hash="b" * 64,
                created_at=now,
                updated_at=now,
            )
            return httpx.Response(
                status_code=201,
                content=response_payload.model_dump_json(),
                request=request,
            )

        if method == "POST" and url.endswith("/ai-decisions") and content is not None:
            self.ai_decision_payload = json.loads(content)
            response_payload = AIDecisionResponse(
                id=str(uuid4()),
                research_space_id=space_id,
                target_type="graph_change_proposal",
                target_id=str(self.ai_decision_payload["target_id"]),
                action="APPLY_RESOLUTION_PLAN",
                status="APPLIED",
                ai_principal=str(self.ai_decision_payload["ai_principal"]),
                confidence=0.9,
                computed_confidence=0.9,
                confidence_assessment_payload=cast(
                    "JSONObject",
                    self.ai_decision_payload["confidence_assessment"],
                ),
                confidence_model_version="decision_confidence_v1",
                risk_tier="low",
                input_hash=str(self.ai_decision_payload["input_hash"]),
                policy_outcome="ai_allowed_when_low_risk",
                evidence_payload={"source": "test"},
                decision_payload={},
                rejection_reason=None,
                created_by="manual:test",
                applied_at=now,
                created_at=now,
                updated_at=now,
            )
            return httpx.Response(
                status_code=201,
                content=response_payload.model_dump_json(),
                request=request,
            )

        if (
            method == "POST"
            and url.endswith("/connector-proposals")
            and content is not None
        ):
            self.connector_payload = json.loads(content)
            response_payload = ConnectorProposalResponse(
                id=str(uuid4()),
                research_space_id=space_id,
                status="SUBMITTED",
                connector_slug=str(self.connector_payload["connector_slug"]),
                display_name=str(self.connector_payload["display_name"]),
                connector_kind=str(self.connector_payload["connector_kind"]),
                domain_context=str(self.connector_payload["domain_context"]),
                metadata_payload={},
                mapping_payload={"field_mappings": []},
                validation_payload={"valid": True, "errors": []},
                approval_payload={},
                rationale=None,
                evidence_payload={"source": "test"},
                proposed_by="manual:test",
                reviewed_by=None,
                reviewed_at=None,
                decision_reason=None,
                source_ref=str(self.connector_payload["source_ref"]),
                created_at=now,
                updated_at=now,
            )
            return httpx.Response(
                status_code=201,
                content=response_payload.model_dump_json(),
                request=request,
            )

        return httpx.Response(status_code=404, content="not found", request=request)

    def close(self) -> None:
        return None


def test_submission_service_only_attaches_ai_principal_on_ai_authority_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "test-graph-secret-key-with-minimum-length-123456"
    monkeypatch.setenv("GRAPH_JWT_SECRET", secret)
    monkeypatch.setenv("GRAPH_JWT_ISSUER", "graph-biomedical")
    monkeypatch.delenv("GRAPH_SERVICE_AI_PRINCIPAL", raising=False)

    fake_client = _AIFullModeHttpClient()

    def _gateway_factory(call_context: GraphCallContext) -> GraphTransportBundle:
        return GraphTransportBundle(
            config=GraphTransportConfig(
                base_url="http://graph.local",
                timeout_seconds=5.0,
                default_headers=call_context.default_headers(),
            ),
            client=fake_client,
            call_context=call_context,
        )

    submission_service = GraphWorkflowSubmissionService(bundle_factory=_gateway_factory)
    space_id = uuid4()

    submission_service.propose_concept(
        space_id=space_id,
        request=ConceptProposalCreateRequest(
            domain_context="general",
            entity_type="PHENOTYPE",
            canonical_label="Astrocyte activation",
            synonyms=["Reactive astrocytes"],
            external_refs=[],
            evidence_payload={"source": "unit-test"},
            source_ref="concept-source-ref",
        ),
        call_context=GraphCallContext.service(graph_admin=True),
    )
    submission_service.submit_ai_decision(
        space_id=space_id,
        request=AIDecisionSubmitRequest(
            target_type="graph_change_proposal",
            target_id=uuid4(),
            action="APPLY_RESOLUTION_PLAN",
            ai_principal="agent:test",
            confidence_assessment=_DECISION_CONFIDENCE_ASSESSMENT,
            risk_tier="low",
            input_hash="b" * 64,
            evidence_payload={"source": "unit-test"},
        ),
        request_id="req-123",
    )

    concept_headers = cast("dict[str, str]", fake_client.headers[0])
    ai_headers = cast("dict[str, str]", fake_client.headers[1])

    concept_payload = jwt.decode(
        concept_headers["Authorization"].removeprefix("Bearer "),
        secret,
        algorithms=["HS256"],
        issuer="graph-biomedical",
    )
    ai_payload = jwt.decode(
        ai_headers["Authorization"].removeprefix("Bearer "),
        secret,
        algorithms=["HS256"],
        issuer="graph-biomedical",
    )

    assert concept_payload["graph_admin"] is True
    assert "graph_ai_principal" not in concept_payload
    assert ai_payload["role"] == "curator"
    assert ai_payload["graph_admin"] is True
    assert ai_payload["graph_ai_principal"] == "agent:test"
    assert ai_headers[REQUEST_ID_HEADER] == "req-123"


def test_ai_full_mode_gateway_calls_governed_phase9_endpoints() -> None:
    fake_client = _AIFullModeHttpClient()
    gateway = GraphTransportBundle(
        config=GraphTransportConfig(
            base_url="http://graph.local",
            timeout_seconds=5.0,
            default_headers={"Authorization": "Bearer test-token"},
        ),
        client=fake_client,
    )
    space_id = uuid4()

    operating_mode = gateway.get_operating_mode(space_id=space_id)
    updated_mode = gateway.update_operating_mode(
        space_id=space_id,
        request=OperatingModeRequest(
            mode="ai_full_graph",
            workflow_policy=GraphWorkflowPolicy(
                allow_ai_graph_repair=True,
                trusted_ai_principals=["agent:test"],
            ),
        ),
    )
    capabilities = gateway.get_operating_mode_capabilities(space_id=space_id)
    workflow = gateway.create_graph_workflow(
        space_id=space_id,
        request=GraphWorkflowCreateRequest(
            kind="evidence_approval",
            input_payload={"source": "unit-test"},
            source_ref="workflow-source-ref",
        ),
    )
    workflow_list = gateway.list_graph_workflows(
        space_id=space_id,
        kind="evidence_approval",
    )
    workflow_detail = gateway.get_graph_workflow(
        space_id=space_id,
        workflow_id=UUID(workflow.id),
    )
    workflow_action = gateway.act_on_graph_workflow(
        space_id=space_id,
        workflow_id=UUID(workflow.id),
        request=GraphWorkflowActionRequest(
            action="approve",
            input_hash=workflow.workflow_hash,
            reason="Unit test approval.",
        ),
    )
    explanation = gateway.explain_graph_resource(
        space_id=space_id,
        resource_type="workflow",
        resource_id=workflow.id,
    )
    concept = gateway.propose_concept(
        space_id=space_id,
        idempotency_key="concept-key",
        request=ConceptProposalCreateRequest(
            domain_context="general",
            entity_type="PHENOTYPE",
            canonical_label="Astrocyte activation",
            synonyms=["Reactive astrocytes"],
            external_refs=[
                ConceptExternalRefRequest(namespace="mesh", identifier="D000001"),
            ],
            evidence_payload={"source": "unit-test"},
            source_ref="concept-source-ref",
        ),
    )
    graph_change = gateway.propose_graph_change(
        space_id=space_id,
        idempotency_key="graph-change-key",
        request=GraphChangeProposalCreateRequest(
            concepts=[
                GraphChangeConceptRequest(
                    local_id="concept-1",
                    domain_context="general",
                    entity_type="PHENOTYPE",
                    canonical_label="Astrocyte activation",
                ),
            ],
            claims=[
                GraphChangeClaimRequest(
                    source_local_id="concept-1",
                    target_local_id="concept-1",
                    relation_type="ASSOCIATED_WITH",
                    assessment=_SUPPORTED_ASSESSMENT,
                    evidence_payload={"source": "unit-test"},
                ),
            ],
            source_ref="graph-change-source-ref",
        ),
    )
    decision = gateway.submit_ai_decision(
        space_id=space_id,
        request=AIDecisionSubmitRequest(
            target_type="graph_change_proposal",
            target_id=UUID(graph_change.id),
            action="APPLY_RESOLUTION_PLAN",
            ai_principal="agent:test",
            confidence_assessment=_DECISION_CONFIDENCE_ASSESSMENT,
            risk_tier="low",
            input_hash=graph_change.proposal_hash,
            evidence_payload={"source": "unit-test"},
        ),
    )
    connector = gateway.propose_connector_metadata(
        space_id=space_id,
        request=ConnectorProposalCreateRequest(
            connector_slug="pubmed-test",
            display_name="PubMed Test",
            connector_kind="document_source",
            domain_context="genomics",
            mapping_payload={"field_mappings": []},
            evidence_payload={"source": "unit-test"},
            source_ref="connector-source-ref",
        ),
    )

    assert [path for _, path in fake_client.calls] == [
        f"/v1/spaces/{space_id}/operating-mode",
        f"/v1/spaces/{space_id}/operating-mode",
        f"/v1/spaces/{space_id}/operating-mode/capabilities",
        f"/v1/spaces/{space_id}/workflows",
        f"/v1/spaces/{space_id}/workflows",
        f"/v1/spaces/{space_id}/workflows/{workflow.id}",
        f"/v1/spaces/{space_id}/workflows/{workflow.id}/actions",
        f"/v1/spaces/{space_id}/explain/workflow/{workflow.id}",
        f"/v1/spaces/{space_id}/concepts/proposals",
        f"/v1/spaces/{space_id}/graph-change-proposals",
        f"/v1/spaces/{space_id}/ai-decisions",
        f"/v1/spaces/{space_id}/connector-proposals",
    ]
    assert operating_mode.mode == "manual"
    assert updated_mode.mode == "ai_full_graph"
    assert capabilities.capabilities["ai_graph_repair_allowed"] is True
    assert workflow.status == "PLAN_READY"
    assert workflow_list.total == 1
    assert workflow_detail.id == workflow.id
    assert workflow_action.status == "APPLIED"
    assert explanation.resource_type == "workflow"
    assert fake_client.headers[8] is not None
    assert fake_client.headers[8]["Idempotency-Key"] == "concept-key"
    assert fake_client.headers[9] is not None
    assert fake_client.headers[9]["Idempotency-Key"] == "graph-change-key"
    assert fake_client.operating_mode_payload is not None
    assert fake_client.operating_mode_payload["mode"] == "ai_full_graph"
    assert fake_client.workflow_payload is not None
    assert fake_client.workflow_payload["source_ref"] == "workflow-source-ref"
    assert fake_client.workflow_action_payload is not None
    assert fake_client.workflow_action_payload["input_hash"] == "c" * 64
    assert fake_client.concept_payload is not None
    assert fake_client.concept_payload["canonical_label"] == "Astrocyte activation"
    assert concept.proposal_hash == "a" * 64
    assert fake_client.graph_change_payload is not None
    assert fake_client.graph_change_payload["source_ref"] == "graph-change-source-ref"
    assert graph_change.proposal_hash == "b" * 64
    assert fake_client.ai_decision_payload is not None
    assert fake_client.ai_decision_payload["input_hash"] == "b" * 64
    assert "confidence" not in fake_client.ai_decision_payload
    assert "confidence_assessment" in fake_client.ai_decision_payload
    assert decision.status == "APPLIED"
    assert fake_client.connector_payload is not None
    assert fake_client.connector_payload["connector_slug"] == "pubmed-test"
    assert connector.validation_payload["valid"] is True


def test_create_relation_proposes_missing_constraint_without_mutation() -> None:
    fake_client = _RelationValidationHttpClient(
        validation_response=KernelGraphValidationResponse(
            valid=False,
            code="relation_constraint_not_allowed",
            message="This source, relation, and target combination is not approved.",
            severity="blocking",
            next_actions=[],
            normalized_relation_type="ASSOCIATED_WITH",
            source_type="GENE",
            target_type="PHENOTYPE",
            profile="FORBIDDEN",
            validation_state="FORBIDDEN",
            validation_reason="relation_not_allowed_by_active_constraints",
            persistability="NON_PERSISTABLE",
        ),
    )
    gateway = _gateway_with_client(fake_client)
    preflight_service, submission_service = _preflight_services(gateway)
    resolved = asyncio.run(
        preflight_service.prepare_relation_create(
            space_id=uuid4(),
            request=KernelRelationCreateRequest(
                source_id=UUID("11111111-1111-1111-1111-111111111111"),
                target_id=UUID("22222222-2222-2222-2222-222222222222"),
                relation_type="ASSOCIATED_WITH",
                assessment=_SUPPORTED_ASSESSMENT,
                evidence_summary="Supported by a curator note.",
                source_document_ref="pmid:123",
                metadata={"origin": "test"},
            ),
            graph_transport=gateway,
        ),
    )

    with pytest.raises(GraphServiceClientError) as exc_info:
        submission_service.submit_resolved_intent(
            resolved_intent=resolved,
            graph_transport=gateway,
        )

    assert "not approved" in str(exc_info.value)
    assert fake_client.calls[0][1].endswith("/validate/triple")
    assert fake_client.calls[1] == (
        "POST",
        "/v1/dictionary/proposals/relation-constraints",
    )
    assert fake_client.relation_constraint_proposal_payload == {
        "source_type": "GENE",
        "relation_type": "ASSOCIATED_WITH",
        "target_type": "PHENOTYPE",
        "rationale": (
            "Claim preflight found no approved relation constraint for this triple."
        ),
        "evidence_payload": {
            "source": "graph_preflight",
        },
        "is_allowed": True,
        "requires_evidence": False,
        "profile": "REVIEW_ONLY",
        "source_ref": (
            "graph-preflight:proposal:relation-constraint:"
            "gene:associated_with:phenotype"
        ),
    }
    assert all(not url.endswith("/relations") for _, url in fake_client.calls)
