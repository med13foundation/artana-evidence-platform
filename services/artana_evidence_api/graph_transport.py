"""Typed HTTP transports for the standalone graph API."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, Self, TypeAlias, TypeVar
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict

from .graph_integration.context import GraphCallContext
from .request_context import REQUEST_ID_HEADER, build_request_id_headers
from .space_sync_types import GraphSyncMembership, GraphSyncSpace
from .types.common import JSONObject, json_object_or_empty
from .types.graph_contracts import (
    AIDecisionResponse,
    AIDecisionSubmitRequest,
    ClaimParticipantListResponse,
    ConceptProposalCreateRequest,
    ConceptProposalResponse,
    ConnectorProposalCreateRequest,
    ConnectorProposalResponse,
    CreateManualHypothesisRequest,
    DictionaryEntityTypeListResponse,
    DictionaryEntityTypeProposalCreateRequest,
    DictionaryProposalResponse,
    DictionaryRelationConstraintProposalCreateRequest,
    DictionaryRelationSynonymListResponse,
    DictionaryRelationTypeListResponse,
    DictionaryRelationTypeProposalCreateRequest,
    DictionaryRelationTypeResponse,
    DictionarySearchListResponse,
    ExplanationResponse,
    GraphChangeProposalCreateRequest,
    GraphChangeProposalResponse,
    GraphWorkflowActionRequest,
    GraphWorkflowCreateRequest,
    GraphWorkflowKind,
    GraphWorkflowListResponse,
    GraphWorkflowResponse,
    GraphWorkflowStatus,
    HypothesisListResponse,
    HypothesisResponse,
    KernelClaimEvidenceListResponse,
    KernelEntityEmbeddingRefreshRequest,
    KernelEntityEmbeddingRefreshResponse,
    KernelEntityEmbeddingStatusListResponse,
    KernelEntityListResponse,
    KernelGraphDocumentRequest,
    KernelGraphDocumentResponse,
    KernelGraphValidationResponse,
    KernelObservationCreateRequest,
    KernelObservationListResponse,
    KernelObservationResponse,
    KernelReasoningPathDetailResponse,
    KernelReasoningPathListResponse,
    KernelRelationClaimCreateRequest,
    KernelRelationClaimListResponse,
    KernelRelationClaimResponse,
    KernelRelationConflictListResponse,
    KernelRelationCreateRequest,
    KernelRelationResponse,
    KernelRelationSuggestionListResponse,
    KernelRelationSuggestionRequest,
    OperatingModeCapabilitiesResponse,
    OperatingModeRequest,
    OperatingModeResponse,
    ValidationExplanationRequest,
)

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)
GraphServiceRequestPrimitive: TypeAlias = str | int | float | bool | None
GraphServiceRequestParams: TypeAlias = (
    Mapping[str, GraphServiceRequestPrimitive | Sequence[GraphServiceRequestPrimitive]]
    | Sequence[tuple[str, GraphServiceRequestPrimitive]]
)
GraphServiceHttpxParams: TypeAlias = (
    Mapping[str, GraphServiceRequestPrimitive | Sequence[GraphServiceRequestPrimitive]]
    | list[tuple[str, GraphServiceRequestPrimitive]]
    | tuple[tuple[str, GraphServiceRequestPrimitive], ...]
    | str
    | bytes
    | None
)

_UPSTREAM_SERVER_ERROR_STATUS = 500
_SERVICE_UNAVAILABLE_STATUS = 503
_SEEDED_GRAPH_DOCUMENT_SEEDS_REQUIRED_DETAIL = (
    "seed_entity_ids must contain at least one value when mode='seeded'"
)


class SupportsGraphApiHttpClient(Protocol):
    """Minimal sync HTTP client contract used by graph transports."""

    def request(
        self,
        method: str,
        url: str,
        *,
        params: GraphServiceHttpxParams = None,
        headers: Mapping[str, str] | None = None,
        content: str | None = None,
    ) -> httpx.Response: ...

    def close(self) -> None: ...


class GraphServiceHealthResponse(BaseModel):
    """Serialized graph API health payload."""

    model_config = ConfigDict(strict=True)

    status: str
    version: str


class GraphSpaceSyncMembershipRequest(BaseModel):
    """Serialized desired membership state for one graph-space sync."""

    model_config = ConfigDict(strict=False)

    user_id: UUID
    role: str
    invited_by: UUID | None = None
    invited_at: datetime | None = None
    joined_at: datetime | None = None
    is_active: bool = True


class GraphSpaceSyncRequest(BaseModel):
    """Serialized graph-space sync payload."""

    model_config = ConfigDict(strict=False)

    slug: str
    name: str
    description: str | None
    owner_id: UUID
    status: str
    settings: JSONObject
    sync_source: str | None = "platform_control_plane"
    sync_fingerprint: str | None = None
    source_updated_at: datetime | None = None
    memberships: list[GraphSpaceSyncMembershipRequest]


class GraphServiceClientError(Exception):
    """Graph API request failure."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail

    def __str__(self) -> str:
        base = super().__str__()
        if self.detail is None or self.detail == "":
            return base
        return f"{base} | detail={self.detail}"


@dataclass(frozen=True)
class GraphTransportConfig:
    """Configuration for one graph transport runtime."""

    base_url: str
    timeout_seconds: float = 10.0
    default_headers: dict[str, str] = field(default_factory=dict)


def _normalize_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _json_content(payload: object) -> str:
    if isinstance(payload, BaseModel):
        return payload.model_dump_json()
    return json.dumps(payload)


@dataclass
class _GraphTransportRuntime:
    """Shared runtime used by all graph transport clients in one bundle."""

    config: GraphTransportConfig
    call_context: GraphCallContext
    client: SupportsGraphApiHttpClient
    owns_client: bool

    def close(self) -> None:
        if self.owns_client:
            self.client.close()

    def request_model(
        self,
        method: str,
        path: str,
        *,
        response_model: type[ResponseModelT],
        params: GraphServiceRequestParams | None = None,
        headers: Mapping[str, str] | None = None,
        content: str | None = None,
    ) -> ResponseModelT:
        response = self.request(
            method,
            path,
            params=params,
            headers=headers,
            content=content,
        )
        return response_model.model_validate_json(response.content)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: GraphServiceRequestParams | None = None,
        headers: Mapping[str, str] | None = None,
        content: str | None = None,
    ) -> httpx.Response:
        merged_headers = self._merge_headers(
            headers=headers,
            has_json_body=content is not None,
        )
        request_params: GraphServiceHttpxParams
        if params is None or isinstance(params, str | bytes | list | tuple | Mapping):
            request_params = params
        else:
            request_params = list(params)
        try:
            response = self.client.request(
                method,
                path,
                params=request_params,
                headers=merged_headers,
                content=content,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text if exc.response is not None else None
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code is not None and status_code >= _UPSTREAM_SERVER_ERROR_STATUS:
                status_code = _SERVICE_UNAVAILABLE_STATUS
            raise GraphServiceClientError(
                f"Graph service request failed: {method} {path}",
                status_code=status_code,
                detail=detail,
            ) from exc
        except httpx.HTTPError as exc:
            raise GraphServiceClientError(
                f"Graph service request failed: {method} {path}",
                status_code=_SERVICE_UNAVAILABLE_STATUS,
                detail=str(exc),
            ) from exc
        return response

    def _merge_headers(
        self,
        *,
        headers: Mapping[str, str] | None,
        has_json_body: bool,
    ) -> dict[str, str]:
        merged_headers = dict(self.config.default_headers)
        if headers is not None:
            merged_headers.update(headers)
        if (
            self.call_context.request_id is not None
            and self.call_context.request_id.strip()
            and REQUEST_ID_HEADER not in merged_headers
        ):
            merged_headers[REQUEST_ID_HEADER] = self.call_context.request_id.strip()
        if has_json_body and "Content-Type" not in merged_headers:
            merged_headers["Content-Type"] = "application/json"
        return build_request_id_headers(merged_headers)


class _GraphTransportBase:
    """Shared base for typed graph transport clients."""

    def __init__(self, runtime: _GraphTransportRuntime) -> None:
        self._runtime = runtime

    @property
    def call_context(self) -> GraphCallContext:
        return self._runtime.call_context

    def close(self) -> None:
        self._runtime.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        del exc_type, exc, traceback
        self.close()


class GraphQueryTransport(_GraphTransportBase):
    """Read/query transport for graph explorer and runtime reads."""

    def get_health(self) -> GraphServiceHealthResponse:
        return self._runtime.request_model(
            "GET",
            "/health",
            response_model=GraphServiceHealthResponse,
        )

    def refresh_entity_embeddings(
        self,
        *,
        space_id: UUID | str,
        request: KernelEntityEmbeddingRefreshRequest,
    ) -> KernelEntityEmbeddingRefreshResponse:
        return self._runtime.request_model(
            "POST",
            f"/v1/spaces/{_normalize_uuid(space_id)}/entities/embeddings/refresh",
            response_model=KernelEntityEmbeddingRefreshResponse,
            content=request.model_dump_json(),
        )

    def list_entity_embedding_status(
        self,
        *,
        space_id: UUID | str,
        entity_ids: list[str] | None = None,
    ) -> KernelEntityEmbeddingStatusListResponse:
        params: dict[str, str] | None = None
        if entity_ids:
            params = {"entity_ids": ",".join(entity_ids)}
        return self._runtime.request_model(
            "GET",
            f"/v1/spaces/{_normalize_uuid(space_id)}/entities/embeddings/status",
            response_model=KernelEntityEmbeddingStatusListResponse,
            params=params,
        )

    def suggest_relations(
        self,
        *,
        space_id: UUID | str,
        request: KernelRelationSuggestionRequest,
    ) -> KernelRelationSuggestionListResponse:
        return self._runtime.request_model(
            "POST",
            f"/v1/spaces/{_normalize_uuid(space_id)}/relations/suggestions",
            response_model=KernelRelationSuggestionListResponse,
            content=request.model_dump_json(),
        )

    def list_entities(
        self,
        *,
        space_id: UUID | str,
        q: str | None = None,
        entity_type: str | None = None,
        ids: list[str] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelEntityListResponse:
        params: dict[str, str] = {
            "offset": str(offset),
            "limit": str(limit),
        }
        if entity_type is not None:
            params["type"] = entity_type
        if q is not None:
            params["q"] = q
        if ids:
            params["ids"] = ",".join(ids)
        return self._runtime.request_model(
            "GET",
            f"/v1/spaces/{_normalize_uuid(space_id)}/entities",
            response_model=KernelEntityListResponse,
            params=params,
        )

    def list_claims(
        self,
        *,
        space_id: UUID | str,
        claim_status: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelRelationClaimListResponse:
        params: dict[str, str] = {
            "offset": str(offset),
            "limit": str(limit),
        }
        if claim_status is not None:
            params["claim_status"] = claim_status
        return self._runtime.request_model(
            "GET",
            f"/v1/spaces/{_normalize_uuid(space_id)}/claims",
            response_model=KernelRelationClaimListResponse,
            params=params,
        )

    def list_observations(
        self,
        *,
        space_id: UUID | str,
        subject_id: UUID | str | None = None,
        variable_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelObservationListResponse:
        params: dict[str, str] = {
            "offset": str(offset),
            "limit": str(limit),
        }
        if subject_id is not None:
            params["subject_id"] = str(_normalize_uuid(subject_id))
        if variable_id is not None:
            params["variable_id"] = variable_id
        return self._runtime.request_model(
            "GET",
            f"/v1/spaces/{_normalize_uuid(space_id)}/observations",
            response_model=KernelObservationListResponse,
            params=params,
        )

    def get_observation(
        self,
        *,
        space_id: UUID | str,
        observation_id: UUID | str,
    ) -> KernelObservationResponse:
        return self._runtime.request_model(
            "GET",
            f"/v1/spaces/{_normalize_uuid(space_id)}/observations/"
            f"{_normalize_uuid(observation_id)}",
            response_model=KernelObservationResponse,
        )

    def get_graph_document(
        self,
        *,
        space_id: UUID | str,
        request: KernelGraphDocumentRequest,
    ) -> KernelGraphDocumentResponse:
        if request.mode == "seeded" and not request.seed_entity_ids:
            raise GraphServiceClientError(
                "Graph document requests in seeded mode require at least one seed entity ID.",
                status_code=422,
                detail=_SEEDED_GRAPH_DOCUMENT_SEEDS_REQUIRED_DETAIL,
            )
        return self._runtime.request_model(
            "POST",
            f"/v1/spaces/{_normalize_uuid(space_id)}/graph/document",
            response_model=KernelGraphDocumentResponse,
            content=request.model_dump_json(),
        )

    def list_claims_by_entity(
        self,
        *,
        space_id: UUID | str,
        entity_id: UUID | str,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelRelationClaimListResponse:
        return self._runtime.request_model(
            "GET",
            f"/v1/spaces/{_normalize_uuid(space_id)}/claims/by-entity/"
            f"{_normalize_uuid(entity_id)}",
            response_model=KernelRelationClaimListResponse,
            params={"offset": str(offset), "limit": str(limit)},
        )

    def list_claim_participants(
        self,
        *,
        space_id: UUID | str,
        claim_id: UUID | str,
    ) -> ClaimParticipantListResponse:
        return self._runtime.request_model(
            "GET",
            f"/v1/spaces/{_normalize_uuid(space_id)}/claims/"
            f"{_normalize_uuid(claim_id)}/participants",
            response_model=ClaimParticipantListResponse,
        )

    def list_claim_evidence(
        self,
        *,
        space_id: UUID | str,
        claim_id: UUID | str,
    ) -> KernelClaimEvidenceListResponse:
        return self._runtime.request_model(
            "GET",
            f"/v1/spaces/{_normalize_uuid(space_id)}/claims/"
            f"{_normalize_uuid(claim_id)}/evidence",
            response_model=KernelClaimEvidenceListResponse,
        )

    def list_relation_conflicts(
        self,
        *,
        space_id: UUID | str,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelRelationConflictListResponse:
        return self._runtime.request_model(
            "GET",
            f"/v1/spaces/{_normalize_uuid(space_id)}/relations/conflicts",
            response_model=KernelRelationConflictListResponse,
            params={"offset": str(offset), "limit": str(limit)},
        )

    def list_reasoning_paths(
        self,
        *,
        space_id: UUID | str,
        start_entity_id: UUID | str | None = None,
        end_entity_id: UUID | str | None = None,
        status: str | None = None,
        path_kind: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelReasoningPathListResponse:
        params: dict[str, str] = {"offset": str(offset), "limit": str(limit)}
        if start_entity_id is not None:
            params["start_entity_id"] = str(_normalize_uuid(start_entity_id))
        if end_entity_id is not None:
            params["end_entity_id"] = str(_normalize_uuid(end_entity_id))
        if status is not None:
            params["status"] = status
        if path_kind is not None:
            params["path_kind"] = path_kind
        return self._runtime.request_model(
            "GET",
            f"/v1/spaces/{_normalize_uuid(space_id)}/reasoning-paths",
            response_model=KernelReasoningPathListResponse,
            params=params,
        )

    def get_reasoning_path(
        self,
        *,
        space_id: UUID | str,
        path_id: UUID | str,
    ) -> KernelReasoningPathDetailResponse:
        return self._runtime.request_model(
            "GET",
            f"/v1/spaces/{_normalize_uuid(space_id)}/reasoning-paths/"
            f"{_normalize_uuid(path_id)}",
            response_model=KernelReasoningPathDetailResponse,
        )

    def create_manual_hypothesis(
        self,
        *,
        space_id: UUID | str,
        request: CreateManualHypothesisRequest,
    ) -> HypothesisResponse:
        return self._runtime.request_model(
            "POST",
            f"/v1/spaces/{_normalize_uuid(space_id)}/hypotheses/manual",
            response_model=HypothesisResponse,
            content=request.model_dump_json(),
        )

    def list_hypotheses(
        self,
        *,
        space_id: UUID | str,
        offset: int = 0,
        limit: int = 50,
    ) -> HypothesisListResponse:
        return self._runtime.request_model(
            "GET",
            f"/v1/spaces/{_normalize_uuid(space_id)}/hypotheses",
            response_model=HypothesisListResponse,
            params={"offset": str(offset), "limit": str(limit)},
        )


class GraphValidationTransport(_GraphTransportBase):
    """Validation and explainable preflight transport."""

    def validate_entity_create(
        self,
        *,
        space_id: UUID | str,
        payload: JSONObject,
    ) -> KernelGraphValidationResponse:
        return self._runtime.request_model(
            "POST",
            f"/v1/spaces/{_normalize_uuid(space_id)}/validate/entity",
            response_model=KernelGraphValidationResponse,
            content=_json_content(payload),
        )

    def validate_relation_materialization(
        self,
        *,
        space_id: UUID | str,
        payload: JSONObject,
    ) -> KernelGraphValidationResponse:
        return self._runtime.request_model(
            "POST",
            f"/v1/spaces/{_normalize_uuid(space_id)}/validate/triple",
            response_model=KernelGraphValidationResponse,
            content=_json_content(payload),
        )

    def validate_claim_create(
        self,
        *,
        space_id: UUID | str,
        request: KernelRelationClaimCreateRequest,
    ) -> KernelGraphValidationResponse:
        return self._runtime.request_model(
            "POST",
            f"/v1/spaces/{_normalize_uuid(space_id)}/validate/claim",
            response_model=KernelGraphValidationResponse,
            content=request.model_dump_json(),
        )

    def validate_observation_create(
        self,
        *,
        space_id: UUID | str,
        request: KernelObservationCreateRequest,
    ) -> KernelGraphValidationResponse:
        return self._runtime.request_model(
            "POST",
            f"/v1/spaces/{_normalize_uuid(space_id)}/validate/observation",
            response_model=KernelGraphValidationResponse,
            content=request.model_dump_json(),
        )

    def explain_graph_validation(
        self,
        *,
        space_id: UUID | str,
        request: ValidationExplanationRequest,
    ) -> ExplanationResponse:
        return self._runtime.request_model(
            "POST",
            f"/v1/spaces/{_normalize_uuid(space_id)}/validate/explain",
            response_model=ExplanationResponse,
            content=request.model_dump_json(),
        )


class GraphDictionaryTransport(_GraphTransportBase):
    """Dictionary read and governed dictionary-proposal transport."""

    def list_dictionary_relation_types(
        self,
        *,
        domain_context: str | None = None,
    ) -> DictionaryRelationTypeListResponse:
        params = (
            {"domain_context": domain_context} if domain_context is not None else None
        )
        return self._runtime.request_model(
            "GET",
            "/v1/dictionary/relation-types",
            response_model=DictionaryRelationTypeListResponse,
            params=params,
        )

    def list_dictionary_entity_types(
        self,
        *,
        domain_context: str | None = None,
    ) -> DictionaryEntityTypeListResponse:
        params = (
            {"domain_context": domain_context} if domain_context is not None else None
        )
        return self._runtime.request_model(
            "GET",
            "/v1/dictionary/entity-types",
            response_model=DictionaryEntityTypeListResponse,
            params=params,
        )

    def list_dictionary_relation_synonyms(
        self,
        *,
        relation_type_id: str | None = None,
        review_status: str | None = None,
        include_inactive: bool = False,
    ) -> DictionaryRelationSynonymListResponse:
        params: dict[str, str] = {
            "include_inactive": "true" if include_inactive else "false",
        }
        if relation_type_id is not None:
            params["relation_type_id"] = relation_type_id
        if review_status is not None:
            params["review_status"] = review_status
        return self._runtime.request_model(
            "GET",
            "/v1/dictionary/relation-synonyms",
            response_model=DictionaryRelationSynonymListResponse,
            params=params,
        )

    def resolve_dictionary_relation_synonym(
        self,
        *,
        synonym: str,
        include_inactive: bool = False,
    ) -> DictionaryRelationTypeResponse:
        return self._runtime.request_model(
            "GET",
            "/v1/dictionary/relation-synonyms/resolve",
            response_model=DictionaryRelationTypeResponse,
            params={
                "synonym": synonym,
                "include_inactive": "true" if include_inactive else "false",
            },
        )

    def search_dictionary_entries_by_domain(
        self,
        *,
        domain_context: str,
        limit: int = 200,
    ) -> DictionarySearchListResponse:
        return self._runtime.request_model(
            "GET",
            f"/v1/dictionary/search/by-domain/{domain_context}",
            response_model=DictionarySearchListResponse,
            params={"limit": str(limit)},
        )

    def submit_entity_type_proposal(
        self,
        *,
        request: DictionaryEntityTypeProposalCreateRequest,
    ) -> DictionaryProposalResponse:
        return self._runtime.request_model(
            "POST",
            "/v1/dictionary/proposals/entity-types",
            response_model=DictionaryProposalResponse,
            content=request.model_dump_json(),
        )

    def submit_relation_type_proposal(
        self,
        *,
        request: DictionaryRelationTypeProposalCreateRequest,
    ) -> DictionaryProposalResponse:
        return self._runtime.request_model(
            "POST",
            "/v1/dictionary/proposals/relation-types",
            response_model=DictionaryProposalResponse,
            content=request.model_dump_json(),
        )

    def submit_relation_constraint_proposal(
        self,
        *,
        request: DictionaryRelationConstraintProposalCreateRequest,
    ) -> DictionaryProposalResponse:
        return self._runtime.request_model(
            "POST",
            "/v1/dictionary/proposals/relation-constraints",
            response_model=DictionaryProposalResponse,
            content=request.model_dump_json(),
        )


class GraphWorkflowTransport(_GraphTransportBase):
    """Workflow, proposal, and explain transport."""

    def get_operating_mode(
        self,
        *,
        space_id: UUID | str,
    ) -> OperatingModeResponse:
        return self._runtime.request_model(
            "GET",
            f"/v1/spaces/{_normalize_uuid(space_id)}/operating-mode",
            response_model=OperatingModeResponse,
        )

    def update_operating_mode(
        self,
        *,
        space_id: UUID | str,
        request: OperatingModeRequest,
    ) -> OperatingModeResponse:
        return self._runtime.request_model(
            "PATCH",
            f"/v1/spaces/{_normalize_uuid(space_id)}/operating-mode",
            response_model=OperatingModeResponse,
            content=request.model_dump_json(),
        )

    def get_operating_mode_capabilities(
        self,
        *,
        space_id: UUID | str,
    ) -> OperatingModeCapabilitiesResponse:
        return self._runtime.request_model(
            "GET",
            f"/v1/spaces/{_normalize_uuid(space_id)}/operating-mode/capabilities",
            response_model=OperatingModeCapabilitiesResponse,
        )

    def create_graph_workflow(
        self,
        *,
        space_id: UUID | str,
        request: GraphWorkflowCreateRequest,
    ) -> GraphWorkflowResponse:
        return self._runtime.request_model(
            "POST",
            f"/v1/spaces/{_normalize_uuid(space_id)}/workflows",
            response_model=GraphWorkflowResponse,
            content=request.model_dump_json(),
        )

    def list_graph_workflows(
        self,
        *,
        space_id: UUID | str,
        kind: GraphWorkflowKind | None = None,
        status: GraphWorkflowStatus | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> GraphWorkflowListResponse:
        params: dict[str, str] = {"offset": str(offset), "limit": str(limit)}
        if kind is not None:
            params["kind"] = kind
        if status is not None:
            params["status"] = status
        return self._runtime.request_model(
            "GET",
            f"/v1/spaces/{_normalize_uuid(space_id)}/workflows",
            response_model=GraphWorkflowListResponse,
            params=params,
        )

    def get_graph_workflow(
        self,
        *,
        space_id: UUID | str,
        workflow_id: UUID | str,
    ) -> GraphWorkflowResponse:
        return self._runtime.request_model(
            "GET",
            f"/v1/spaces/{_normalize_uuid(space_id)}/workflows/"
            f"{_normalize_uuid(workflow_id)}",
            response_model=GraphWorkflowResponse,
        )

    def act_on_graph_workflow(
        self,
        *,
        space_id: UUID | str,
        workflow_id: UUID | str,
        request: GraphWorkflowActionRequest,
    ) -> GraphWorkflowResponse:
        return self._runtime.request_model(
            "POST",
            f"/v1/spaces/{_normalize_uuid(space_id)}/workflows/"
            f"{_normalize_uuid(workflow_id)}/actions",
            response_model=GraphWorkflowResponse,
            content=request.model_dump_json(),
        )

    def explain_graph_resource(
        self,
        *,
        space_id: UUID | str,
        resource_type: str,
        resource_id: UUID | str,
    ) -> ExplanationResponse:
        return self._runtime.request_model(
            "GET",
            f"/v1/spaces/{_normalize_uuid(space_id)}/explain/"
            f"{resource_type}/{resource_id}",
            response_model=ExplanationResponse,
        )

    def propose_concept(
        self,
        *,
        space_id: UUID | str,
        request: ConceptProposalCreateRequest,
        idempotency_key: str | None = None,
    ) -> ConceptProposalResponse:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self._runtime.request_model(
            "POST",
            f"/v1/spaces/{_normalize_uuid(space_id)}/concepts/proposals",
            response_model=ConceptProposalResponse,
            headers=headers,
            content=request.model_dump_json(),
        )

    def propose_graph_change(
        self,
        *,
        space_id: UUID | str,
        request: GraphChangeProposalCreateRequest,
        idempotency_key: str | None = None,
    ) -> GraphChangeProposalResponse:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self._runtime.request_model(
            "POST",
            f"/v1/spaces/{_normalize_uuid(space_id)}/graph-change-proposals",
            response_model=GraphChangeProposalResponse,
            headers=headers,
            content=request.model_dump_json(),
        )

    def submit_ai_decision(
        self,
        *,
        space_id: UUID | str,
        request: AIDecisionSubmitRequest,
    ) -> AIDecisionResponse:
        return self._runtime.request_model(
            "POST",
            f"/v1/spaces/{_normalize_uuid(space_id)}/ai-decisions",
            response_model=AIDecisionResponse,
            content=request.model_dump_json(),
        )

    def propose_connector_metadata(
        self,
        *,
        space_id: UUID | str,
        request: ConnectorProposalCreateRequest,
    ) -> ConnectorProposalResponse:
        return self._runtime.request_model(
            "POST",
            f"/v1/spaces/{_normalize_uuid(space_id)}/connector-proposals",
            response_model=ConnectorProposalResponse,
            content=request.model_dump_json(),
        )


class GraphRawMutationTransport(_GraphTransportBase):
    """Internal-only direct mutation transport for allowlisted system flows."""

    def sync_space(
        self,
        *,
        space: GraphSyncSpace,
        memberships: Sequence[GraphSyncMembership],
    ) -> JSONObject:
        payload = GraphSpaceSyncRequest(
            slug=space.slug,
            name=space.name,
            description=space.description,
            owner_id=space.owner_id,
            status=space.status.value,
            settings=json_object_or_empty(space.settings),
            source_updated_at=space.updated_at,
            memberships=[
                GraphSpaceSyncMembershipRequest(
                    user_id=membership.user_id,
                    role=membership.role.value,
                    invited_by=membership.invited_by,
                    invited_at=membership.invited_at,
                    joined_at=membership.joined_at,
                    is_active=membership.is_active,
                )
                for membership in memberships
            ],
        )
        response = self._runtime.request(
            "POST",
            f"/v1/admin/spaces/{_normalize_uuid(space.id)}/sync",
            content=payload.model_dump_json(),
        )
        return json_object_or_empty(response.json())

    def upsert_entity_direct(
        self,
        *,
        space_id: UUID | str,
        entity_type: str,
        display_label: str,
        aliases: list[str] | None = None,
        metadata: JSONObject | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> JSONObject:
        payload: dict[str, object] = {
            "entity_type": entity_type,
            "display_label": display_label,
        }
        if aliases is not None:
            payload["aliases"] = aliases
        if metadata is not None:
            payload["metadata"] = metadata
        if identifiers is not None:
            payload["identifiers"] = identifiers
        response = self._runtime.request(
            "POST",
            f"/v1/spaces/{_normalize_uuid(space_id)}/entities",
            content=_json_content(payload),
        )
        return json_object_or_empty(response.json())

    def update_entity_direct(
        self,
        *,
        space_id: UUID | str,
        entity_id: UUID | str,
        display_label: str | None = None,
        aliases: list[str] | None = None,
        metadata: JSONObject | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> JSONObject:
        payload: dict[str, object] = {}
        if display_label is not None:
            payload["display_label"] = display_label
        if aliases is not None:
            payload["aliases"] = aliases
        if metadata is not None:
            payload["metadata"] = metadata
        if identifiers is not None:
            payload["identifiers"] = identifiers
        response = self._runtime.request(
            "PUT",
            f"/v1/spaces/{_normalize_uuid(space_id)}/entities/"
            f"{_normalize_uuid(entity_id)}",
            content=_json_content(payload),
        )
        return json_object_or_empty(response.json())

    def create_entities_batch_direct(
        self,
        *,
        space_id: UUID | str,
        entities: list[dict[str, object]],
    ) -> JSONObject:
        response = self._runtime.request(
            "POST",
            f"/v1/spaces/{_normalize_uuid(space_id)}/entities/batch",
            content=_json_content({"entities": entities}),
        )
        return json_object_or_empty(response.json())

    def create_unresolved_claim_direct(
        self,
        *,
        space_id: UUID | str,
        request: KernelRelationClaimCreateRequest,
    ) -> KernelRelationClaimResponse:
        return self._runtime.request_model(
            "POST",
            f"/v1/spaces/{_normalize_uuid(space_id)}/claims",
            response_model=KernelRelationClaimResponse,
            content=request.model_dump_json(),
        )

    def materialize_relation_direct(
        self,
        *,
        space_id: UUID | str,
        request: KernelRelationCreateRequest,
    ) -> KernelRelationResponse:
        return self._runtime.request_model(
            "POST",
            f"/v1/spaces/{_normalize_uuid(space_id)}/relations",
            response_model=KernelRelationResponse,
            content=request.model_dump_json(),
        )

    def create_observation_direct(
        self,
        *,
        space_id: UUID | str,
        request: KernelObservationCreateRequest,
    ) -> KernelObservationResponse:
        return self._runtime.request_model(
            "POST",
            f"/v1/spaces/{_normalize_uuid(space_id)}/observations",
            response_model=KernelObservationResponse,
            content=request.model_dump_json(),
        )


GraphRawMutationTransportT: TypeAlias = GraphRawMutationTransport


def build_graph_raw_mutation_transport(
    runtime: _GraphTransportRuntime,
) -> GraphRawMutationTransportT:
    return GraphRawMutationTransport(runtime)


from .graph_transport_bundle import GraphTransportBundle  # noqa: E402,I001


__all__ = [
    "GraphDictionaryTransport",
    "GraphQueryTransport",
    "GraphRawMutationTransport",
    "GraphRawMutationTransportT",
    "GraphServiceClientError",
    "GraphServiceHealthResponse",
    "GraphTransportBundle",
    "GraphTransportConfig",
    "GraphValidationTransport",
    "GraphWorkflowTransport",
    "build_graph_raw_mutation_transport",
]
