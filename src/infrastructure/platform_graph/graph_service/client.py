"""Typed HTTP client for the standalone graph service."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, TypeAlias
from uuid import UUID

import httpx
from artana_evidence_db.common_types import ResearchSpaceSettings
from artana_evidence_db.service_contracts import (
    ClaimParticipantBackfillRequest,
    ClaimParticipantBackfillResponse,
    ClaimParticipantCoverageResponse,
    ClaimParticipantListResponse,
    ClaimRelationCreateRequest,
    ClaimRelationListResponse,
    ClaimRelationResponse,
    ClaimRelationReviewUpdateRequest,
    ConceptAliasListResponse,
    ConceptAliasResponse,
    ConceptDecisionListResponse,
    ConceptDecisionResponse,
    ConceptMemberListResponse,
    ConceptMemberResponse,
    ConceptPolicyResponse,
    ConceptSetListResponse,
    ConceptSetResponse,
    CreateManualHypothesisRequest,
    DictionaryChangelogListResponse,
    DictionaryEntityTypeCreateRequest,
    DictionaryEntityTypeListResponse,
    DictionaryEntityTypeResponse,
    DictionaryMergeRequest,
    DictionaryRelationSynonymCreateRequest,
    DictionaryRelationSynonymListResponse,
    DictionaryRelationSynonymResponse,
    DictionaryRelationTypeCreateRequest,
    DictionaryRelationTypeListResponse,
    DictionaryRelationTypeResponse,
    DictionarySearchListResponse,
    EntityResolutionPolicyListResponse,
    HypothesisListResponse,
    HypothesisResponse,
    KernelClaimEvidenceListResponse,
    KernelClaimMechanismChainResponse,
    KernelEntityCreateRequest,
    KernelEntityListResponse,
    KernelEntityResponse,
    KernelEntityUpdateRequest,
    KernelEntityUpsertResponse,
    KernelGraphDocumentRequest,
    KernelGraphDocumentResponse,
    KernelGraphDomainViewResponse,
    KernelGraphExportResponse,
    KernelGraphSubgraphRequest,
    KernelGraphSubgraphResponse,
    KernelObservationCreateRequest,
    KernelObservationListResponse,
    KernelObservationResponse,
    KernelProvenanceListResponse,
    KernelProvenanceResponse,
    KernelReasoningPathDetailResponse,
    KernelReasoningPathListResponse,
    KernelRelationClaimCreateRequest,
    KernelRelationClaimListResponse,
    KernelRelationClaimResponse,
    KernelRelationClaimTriageRequest,
    KernelRelationConflictListResponse,
    KernelRelationCreateRequest,
    KernelRelationCurationUpdateRequest,
    KernelRelationListResponse,
    KernelRelationResponse,
    KernelRelationSuggestionListResponse,
    KernelRelationSuggestionRequest,
    RelationConstraintListResponse,
    RelationConstraintResponse,
    TransformRegistryListResponse,
    TransformRegistryResponse,
    TransformVerificationResponse,
    ValueSetCreateRequest,
    ValueSetItemActiveRequest,
    ValueSetItemCreateRequest,
    ValueSetItemListResponse,
    ValueSetItemResponse,
    ValueSetListResponse,
    ValueSetResponse,
    VariableDefinitionCreateRequest,
    VariableDefinitionListResponse,
    VariableDefinitionResponse,
    VariableDefinitionReviewStatusRequest,
    VariableDefinitionRevokeRequest,
)
from pydantic import BaseModel, ConfigDict, Field

from .errors import GraphServiceClientError


class GraphServiceHealthResponse(BaseModel):
    """Serialized graph-service health payload."""

    model_config = ConfigDict(strict=True)

    status: str
    version: str


class GraphProjectionReadinessSampleResponse(BaseModel):
    """One sampled readiness issue row from the graph service."""

    model_config = ConfigDict(strict=True)

    research_space_id: str
    claim_id: str | None
    relation_id: str | None
    detail: str


class GraphProjectionReadinessIssueResponse(BaseModel):
    """Aggregate readiness issue summary from the graph service."""

    model_config = ConfigDict(strict=True)

    count: int
    samples: list[GraphProjectionReadinessSampleResponse]


class GraphProjectionReadinessReportResponse(BaseModel):
    """Full projection readiness report from the graph service."""

    model_config = ConfigDict(strict=True)

    orphan_relations: GraphProjectionReadinessIssueResponse
    missing_claim_participants: GraphProjectionReadinessIssueResponse
    missing_claim_evidence: GraphProjectionReadinessIssueResponse
    linked_relation_mismatches: GraphProjectionReadinessIssueResponse
    invalid_projection_relations: GraphProjectionReadinessIssueResponse
    ready: bool


class GraphParticipantBackfillGlobalSummaryResponse(BaseModel):
    """Global participant backfill summary emitted by projection repair."""

    model_config = ConfigDict(strict=True)

    scanned_claims: int
    created_participants: int
    skipped_existing: int
    unresolved_endpoints: int
    research_spaces: int
    dry_run: bool


class GraphProjectionRepairSummaryRequest(BaseModel):
    """Projection repair request payload."""

    model_config = ConfigDict(strict=True)

    dry_run: bool = True
    batch_limit: int = 5000


class GraphProjectionRepairSummaryResponse(BaseModel):
    """Projection repair summary emitted by the graph service."""

    model_config = ConfigDict(strict=True)

    operation_run_id: UUID
    participant_backfill: GraphParticipantBackfillGlobalSummaryResponse
    materialized_claims: int
    detached_claims: int
    unresolved_claims: int
    dry_run: bool


class GraphReasoningPathRebuildRequest(BaseModel):
    """Reasoning-path rebuild request payload."""

    model_config = ConfigDict(strict=False)

    space_id: UUID | None = None
    max_depth: int = 4
    replace_existing: bool = True


class GraphReasoningPathRebuildSummaryResponse(BaseModel):
    """One reasoning-path rebuild summary row."""

    model_config = ConfigDict(strict=True)

    research_space_id: str
    eligible_claims: int
    accepted_claim_relations: int
    rebuilt_paths: int
    max_depth: int


class GraphReasoningPathRebuildResponse(BaseModel):
    """Reasoning-path rebuild response payload."""

    model_config = ConfigDict(strict=True)

    operation_run_id: UUID
    summaries: list[GraphReasoningPathRebuildSummaryResponse]


class GraphOperationRunResponse(BaseModel):
    """One recorded graph-service admin operation run."""

    model_config = ConfigDict(strict=False)

    id: UUID
    operation_type: str
    status: str
    research_space_id: UUID | None
    actor_user_id: UUID | None
    actor_email: str | None
    dry_run: bool
    request_payload: dict[str, object]
    summary_payload: dict[str, object]
    failure_detail: str | None
    started_at: datetime
    completed_at: datetime


class GraphOperationRunListResponse(BaseModel):
    """List response for recorded graph-service admin operation runs."""

    model_config = ConfigDict(strict=False)

    runs: list[GraphOperationRunResponse]
    total: int
    offset: int
    limit: int


class GraphSpaceRegistryResponse(BaseModel):
    """One graph-space registry entry."""

    model_config = ConfigDict(strict=True)

    id: UUID
    slug: str
    name: str
    description: str | None
    owner_id: UUID
    status: str
    settings: ResearchSpaceSettings
    sync_source: str | None = None
    sync_fingerprint: str | None = None
    source_updated_at: datetime | None = None
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class GraphSpaceRegistryListResponse(BaseModel):
    """List response for graph-space registry entries."""

    model_config = ConfigDict(strict=True)

    spaces: list[GraphSpaceRegistryResponse]
    total: int


def _empty_space_settings() -> ResearchSpaceSettings:
    return {}


class GraphSpaceRegistryUpsertRequestPayload(BaseModel):
    """Create or update one graph-space registry entry."""

    model_config = ConfigDict(strict=True)

    slug: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=4000)
    owner_id: UUID
    status: Literal["active", "inactive", "archived", "suspended"] = "active"
    settings: ResearchSpaceSettings = Field(default_factory=_empty_space_settings)


class GraphSpaceMembershipResponse(BaseModel):
    """One graph-space membership entry."""

    model_config = ConfigDict(strict=True)

    id: UUID
    space_id: UUID
    user_id: UUID
    role: str
    invited_by: UUID | None
    invited_at: datetime | None
    joined_at: datetime | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class GraphSpaceMembershipListResponse(BaseModel):
    """List response for graph-space memberships."""

    model_config = ConfigDict(strict=True)

    memberships: list[GraphSpaceMembershipResponse]
    total: int


class GraphSpaceMembershipUpsertRequestPayload(BaseModel):
    """Create or update one graph-space membership."""

    model_config = ConfigDict(strict=False)

    role: Literal["owner", "admin", "curator", "researcher", "viewer"]
    invited_by: UUID | None = None
    invited_at: datetime | None = None
    joined_at: datetime | None = None
    is_active: bool = True


class GraphSpaceSyncMembershipPayload(BaseModel):
    """Desired synced membership state for one graph space."""

    model_config = ConfigDict(strict=False)

    user_id: UUID
    role: Literal["owner", "admin", "curator", "researcher", "viewer"]
    invited_by: UUID | None = None
    invited_at: datetime | None = None
    joined_at: datetime | None = None
    is_active: bool = True


class GraphSpaceSyncRequestPayload(BaseModel):
    """Atomic graph-space registry and membership sync payload."""

    model_config = ConfigDict(strict=False)

    slug: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=4000)
    owner_id: UUID
    status: Literal["active", "inactive", "archived", "suspended"] = "active"
    settings: ResearchSpaceSettings = Field(default_factory=_empty_space_settings)
    sync_source: str | None = Field(default="platform_control_plane", max_length=64)
    sync_fingerprint: str | None = Field(default=None, max_length=64)
    source_updated_at: datetime | None = None
    memberships: list[GraphSpaceSyncMembershipPayload] = Field(default_factory=list)


class GraphSpaceSyncResponse(BaseModel):
    """Atomic graph-space sync response."""

    model_config = ConfigDict(strict=True)

    applied: bool
    space: GraphSpaceRegistryResponse
    memberships: list[GraphSpaceMembershipResponse]
    total_memberships: int


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


@dataclass(frozen=True)
class GraphServiceClientConfig:
    """Configuration for one graph service client instance."""

    base_url: str
    timeout_seconds: float = 10.0
    default_headers: dict[str, str] = field(default_factory=dict)


class GraphServiceClient:
    """Typed sync client for graph-service HTTP APIs."""

    def __init__(
        self,
        config: GraphServiceClientConfig,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._config = config
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=config.base_url.rstrip("/"),
            timeout=config.timeout_seconds,
            headers=config.default_headers,
        )

    def close(self) -> None:
        """Close the underlying HTTP client when owned by this wrapper."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> GraphServiceClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        self.close()

    def get_health(self) -> GraphServiceHealthResponse:
        """Fetch the graph-service health payload."""
        return self._request_model(
            "GET",
            "/health",
            response_model=GraphServiceHealthResponse,
        )

    def get_projection_readiness(
        self,
        *,
        sample_limit: int = 10,
        headers: Mapping[str, str] | None = None,
    ) -> GraphProjectionReadinessReportResponse:
        """Fetch the global projection readiness report."""
        return self._request_model(
            "GET",
            "/v1/admin/projections/readiness",
            response_model=GraphProjectionReadinessReportResponse,
            params={"sample_limit": str(sample_limit)},
            headers=headers,
        )

    def repair_projections(
        self,
        *,
        dry_run: bool = True,
        batch_limit: int = 5000,
        headers: Mapping[str, str] | None = None,
    ) -> GraphProjectionRepairSummaryResponse:
        """Request global projection repair through the graph service."""
        return self._request_model(
            "POST",
            "/v1/admin/projections/repair",
            response_model=GraphProjectionRepairSummaryResponse,
            content=GraphProjectionRepairSummaryRequest(
                dry_run=dry_run,
                batch_limit=batch_limit,
            ).model_dump_json(),
            headers=headers,
        )

    def rebuild_reasoning_paths(
        self,
        *,
        space_id: UUID | str | None = None,
        max_depth: int = 4,
        replace_existing: bool = True,
        headers: Mapping[str, str] | None = None,
    ) -> GraphReasoningPathRebuildResponse:
        """Rebuild reasoning paths through the graph service."""
        return self._request_model(
            "POST",
            "/v1/admin/reasoning-paths/rebuild",
            response_model=GraphReasoningPathRebuildResponse,
            content=GraphReasoningPathRebuildRequest(
                space_id=UUID(space_id) if isinstance(space_id, str) else space_id,
                max_depth=max_depth,
                replace_existing=replace_existing,
            ).model_dump_json(),
            headers=headers,
        )

    def list_operation_runs(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        operation_type: str | None = None,
        status: str | None = None,
        space_id: UUID | str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> GraphOperationRunListResponse:
        """List recorded graph-service admin operation runs."""
        params: dict[str, str] = {
            "limit": str(limit),
            "offset": str(offset),
        }
        if operation_type is not None:
            params["operation_type"] = operation_type
        if status is not None:
            params["status"] = status
        if space_id is not None:
            params["space_id"] = str(space_id)
        return self._request_model(
            "GET",
            "/v1/admin/operations/runs",
            response_model=GraphOperationRunListResponse,
            params=params,
            headers=headers,
        )

    def get_operation_run(
        self,
        *,
        run_id: UUID | str,
        headers: Mapping[str, str] | None = None,
    ) -> GraphOperationRunResponse:
        """Fetch one recorded graph-service admin operation run."""
        return self._request_model(
            "GET",
            f"/v1/admin/operations/runs/{run_id}",
            response_model=GraphOperationRunResponse,
            headers=headers,
        )

    def list_spaces(
        self,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> GraphSpaceRegistryListResponse:
        """List graph-space registry entries."""
        return self._request_model(
            "GET",
            "/v1/admin/spaces",
            response_model=GraphSpaceRegistryListResponse,
            headers=headers,
        )

    def get_space(
        self,
        *,
        space_id: UUID | str,
        headers: Mapping[str, str] | None = None,
    ) -> GraphSpaceRegistryResponse:
        """Fetch one graph-space registry entry."""
        return self._request_model(
            "GET",
            f"/v1/admin/spaces/{space_id}",
            response_model=GraphSpaceRegistryResponse,
            headers=headers,
        )

    def upsert_space(
        self,
        *,
        space_id: UUID | str,
        slug: str,
        name: str,
        description: str | None,
        owner_id: UUID,
        status: Literal["active", "inactive", "archived", "suspended"] = "active",
        settings: ResearchSpaceSettings | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> GraphSpaceRegistryResponse:
        """Create or update one graph-space registry entry."""
        return self._request_model(
            "PUT",
            f"/v1/admin/spaces/{space_id}",
            response_model=GraphSpaceRegistryResponse,
            content=GraphSpaceRegistryUpsertRequestPayload(
                slug=slug,
                name=name,
                description=description,
                owner_id=owner_id,
                status=status,
                settings=settings or {},
            ).model_dump_json(),
            headers=headers,
        )

    def list_space_memberships(
        self,
        *,
        space_id: UUID | str,
        headers: Mapping[str, str] | None = None,
    ) -> GraphSpaceMembershipListResponse:
        """List graph-space memberships."""
        return self._request_model(
            "GET",
            f"/v1/admin/spaces/{space_id}/memberships",
            response_model=GraphSpaceMembershipListResponse,
            headers=headers,
        )

    def upsert_space_membership(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        role: Literal["owner", "admin", "curator", "researcher", "viewer"],
        invited_by: UUID | None = None,
        invited_at: datetime | None = None,
        joined_at: datetime | None = None,
        is_active: bool = True,
        headers: Mapping[str, str] | None = None,
    ) -> GraphSpaceMembershipResponse:
        """Create or update one graph-space membership."""
        return self._request_model(
            "PUT",
            f"/v1/admin/spaces/{space_id}/memberships/{user_id}",
            response_model=GraphSpaceMembershipResponse,
            content=GraphSpaceMembershipUpsertRequestPayload(
                role=role,
                invited_by=invited_by,
                invited_at=invited_at,
                joined_at=joined_at,
                is_active=is_active,
            ).model_dump_json(),
            headers=headers,
        )

    def sync_space(
        self,
        *,
        space_id: UUID | str,
        slug: str,
        name: str,
        description: str | None,
        owner_id: UUID,
        status: Literal["active", "inactive", "archived", "suspended"] = "active",
        settings: ResearchSpaceSettings | None = None,
        sync_source: str | None = "platform_control_plane",
        sync_fingerprint: str | None = None,
        source_updated_at: datetime | None = None,
        memberships: list[GraphSpaceSyncMembershipPayload] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> GraphSpaceSyncResponse:
        """Atomically sync one graph space registry entry and membership snapshot."""
        return self._request_model(
            "POST",
            f"/v1/admin/spaces/{space_id}/sync",
            response_model=GraphSpaceSyncResponse,
            content=GraphSpaceSyncRequestPayload(
                slug=slug,
                name=name,
                description=description,
                owner_id=owner_id,
                status=status,
                settings=settings or {},
                sync_source=sync_source,
                sync_fingerprint=sync_fingerprint,
                source_updated_at=source_updated_at,
                memberships=memberships or [],
            ).model_dump_json(),
            headers=headers,
        )

    def list_relations(
        self,
        *,
        space_id: UUID,
        relation_type: str | None = None,
        curation_status: str | None = None,
        validation_state: str | None = None,
        source_document_id: str | None = None,
        certainty_band: str | None = None,
        node_query: str | None = None,
        node_ids: list[str] | None = None,
        offset: int = 0,
        limit: int = 50,
        headers: Mapping[str, str] | None = None,
    ) -> KernelRelationListResponse:
        """List canonical relations for one graph space."""
        params: list[tuple[str, str]] = [
            ("offset", str(offset)),
            ("limit", str(limit)),
        ]
        if relation_type is not None:
            params.append(("relation_type", relation_type))
        if curation_status is not None:
            params.append(("curation_status", curation_status))
        if validation_state is not None:
            params.append(("validation_state", validation_state))
        if source_document_id is not None:
            params.append(("source_document_id", source_document_id))
        if certainty_band is not None:
            params.append(("certainty_band", certainty_band))
        if node_query is not None:
            params.append(("node_query", node_query))
        if node_ids:
            params.extend(("node_ids", node_id) for node_id in node_ids)
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/relations",
            response_model=KernelRelationListResponse,
            params=params,
            headers=headers,
        )

    def create_relation(
        self,
        *,
        space_id: UUID,
        request: KernelRelationCreateRequest,
        headers: Mapping[str, str] | None = None,
    ) -> KernelRelationResponse:
        """Create one canonical relation through the graph service."""
        return self._request_model(
            "POST",
            f"/v1/spaces/{space_id}/relations",
            response_model=KernelRelationResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def suggest_relations(
        self,
        *,
        space_id: UUID,
        request: KernelRelationSuggestionRequest,
        headers: Mapping[str, str] | None = None,
    ) -> KernelRelationSuggestionListResponse:
        """Suggest missing dictionary-constrained relations for one graph space."""
        return self._request_model(
            "POST",
            f"/v1/spaces/{space_id}/relations/suggestions",
            response_model=KernelRelationSuggestionListResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def update_relation_curation_status(
        self,
        *,
        space_id: UUID,
        relation_id: UUID,
        request: KernelRelationCurationUpdateRequest,
        headers: Mapping[str, str] | None = None,
    ) -> KernelRelationResponse:
        """Update one canonical relation curation status."""
        return self._request_model(
            "PUT",
            f"/v1/spaces/{space_id}/relations/{relation_id}",
            response_model=KernelRelationResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def list_entities(
        self,
        *,
        space_id: UUID,
        entity_type: str | None = None,
        q: str | None = None,
        ids: list[str] | None = None,
        offset: int = 0,
        limit: int = 50,
        headers: Mapping[str, str] | None = None,
    ) -> KernelEntityListResponse:
        """List entities for one graph space."""
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
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/entities",
            response_model=KernelEntityListResponse,
            params=params,
            headers=headers,
        )

    def create_entity(
        self,
        *,
        space_id: UUID,
        request: KernelEntityCreateRequest,
        headers: Mapping[str, str] | None = None,
    ) -> KernelEntityUpsertResponse:
        """Create or resolve one entity through the graph service."""
        return self._request_model(
            "POST",
            f"/v1/spaces/{space_id}/entities",
            response_model=KernelEntityUpsertResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def get_entity(
        self,
        *,
        space_id: UUID,
        entity_id: UUID,
        headers: Mapping[str, str] | None = None,
    ) -> KernelEntityResponse:
        """Fetch one entity from the graph service."""
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/entities/{entity_id}",
            response_model=KernelEntityResponse,
            headers=headers,
        )

    def update_entity(
        self,
        *,
        space_id: UUID,
        entity_id: UUID,
        request: KernelEntityUpdateRequest,
        headers: Mapping[str, str] | None = None,
    ) -> KernelEntityResponse:
        """Update one entity through the graph service."""
        return self._request_model(
            "PUT",
            f"/v1/spaces/{space_id}/entities/{entity_id}",
            response_model=KernelEntityResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def delete_entity(
        self,
        *,
        space_id: UUID,
        entity_id: UUID,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """Delete one entity through the graph service."""
        self._request(
            "DELETE",
            f"/v1/spaces/{space_id}/entities/{entity_id}",
            headers=headers,
        )

    def list_observations(
        self,
        *,
        space_id: UUID,
        subject_id: UUID | None = None,
        variable_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
        headers: Mapping[str, str] | None = None,
    ) -> KernelObservationListResponse:
        """List observations for one graph space."""
        params: dict[str, str] = {
            "offset": str(offset),
            "limit": str(limit),
        }
        if subject_id is not None:
            params["subject_id"] = str(subject_id)
        if variable_id is not None:
            params["variable_id"] = variable_id
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/observations",
            response_model=KernelObservationListResponse,
            params=params,
            headers=headers,
        )

    def create_observation(
        self,
        *,
        space_id: UUID,
        request: KernelObservationCreateRequest,
        headers: Mapping[str, str] | None = None,
    ) -> KernelObservationResponse:
        """Create one observation through the graph service."""
        return self._request_model(
            "POST",
            f"/v1/spaces/{space_id}/observations",
            response_model=KernelObservationResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def get_observation(
        self,
        *,
        space_id: UUID,
        observation_id: UUID,
        headers: Mapping[str, str] | None = None,
    ) -> KernelObservationResponse:
        """Fetch one observation from the graph service."""
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/observations/{observation_id}",
            response_model=KernelObservationResponse,
            headers=headers,
        )

    def list_provenance(
        self,
        *,
        space_id: UUID,
        source_type: str | None = None,
        offset: int = 0,
        limit: int = 50,
        headers: Mapping[str, str] | None = None,
    ) -> KernelProvenanceListResponse:
        """List provenance records for one graph space."""
        params: dict[str, str] = {
            "offset": str(offset),
            "limit": str(limit),
        }
        if source_type is not None:
            params["source_type"] = source_type
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/provenance",
            response_model=KernelProvenanceListResponse,
            params=params,
            headers=headers,
        )

    def get_provenance(
        self,
        *,
        space_id: UUID,
        provenance_id: UUID,
        headers: Mapping[str, str] | None = None,
    ) -> KernelProvenanceResponse:
        """Fetch one provenance record from the graph service."""
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/provenance/{provenance_id}",
            response_model=KernelProvenanceResponse,
            headers=headers,
        )

    def list_claims(
        self,
        *,
        space_id: UUID,
        claim_status: str | None = None,
        validation_state: str | None = None,
        persistability: str | None = None,
        polarity: str | None = None,
        source_document_id: str | None = None,
        relation_type: str | None = None,
        linked_relation_id: str | None = None,
        certainty_band: str | None = None,
        offset: int = 0,
        limit: int = 50,
        headers: Mapping[str, str] | None = None,
    ) -> KernelRelationClaimListResponse:
        """List relation claims for one graph space."""
        params: dict[str, str] = {
            "offset": str(offset),
            "limit": str(limit),
        }
        if claim_status is not None:
            params["claim_status"] = claim_status
        if validation_state is not None:
            params["validation_state"] = validation_state
        if persistability is not None:
            params["persistability"] = persistability
        if polarity is not None:
            params["polarity"] = polarity
        if source_document_id is not None:
            params["source_document_id"] = source_document_id
        if relation_type is not None:
            params["relation_type"] = relation_type
        if linked_relation_id is not None:
            params["linked_relation_id"] = linked_relation_id
        if certainty_band is not None:
            params["certainty_band"] = certainty_band
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/claims",
            response_model=KernelRelationClaimListResponse,
            params=params or None,
            headers=headers,
        )

    def create_claim(
        self,
        *,
        space_id: UUID,
        request: KernelRelationClaimCreateRequest,
        headers: Mapping[str, str] | None = None,
    ) -> KernelRelationClaimResponse:
        """Create one unresolved relation claim through the graph service."""
        return self._request_model(
            "POST",
            f"/v1/spaces/{space_id}/claims",
            response_model=KernelRelationClaimResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def list_claims_by_entity(
        self,
        *,
        space_id: UUID,
        entity_id: UUID,
        offset: int = 0,
        limit: int = 50,
        headers: Mapping[str, str] | None = None,
    ) -> KernelRelationClaimListResponse:
        """List relation claims connected to one entity via claim participants."""
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/claims/by-entity/{entity_id}",
            response_model=KernelRelationClaimListResponse,
            params={
                "offset": str(offset),
                "limit": str(limit),
            },
            headers=headers,
        )

    def list_claim_participants(
        self,
        *,
        space_id: UUID,
        claim_id: UUID,
        headers: Mapping[str, str] | None = None,
    ) -> ClaimParticipantListResponse:
        """List structured participants for one claim."""
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/claims/{claim_id}/participants",
            response_model=ClaimParticipantListResponse,
            headers=headers,
        )

    def list_claim_evidence(
        self,
        *,
        space_id: UUID,
        claim_id: UUID,
        headers: Mapping[str, str] | None = None,
    ) -> KernelClaimEvidenceListResponse:
        """List evidence rows for one claim."""
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/claims/{claim_id}/evidence",
            response_model=KernelClaimEvidenceListResponse,
            headers=headers,
        )

    def update_claim_status(
        self,
        *,
        space_id: UUID,
        claim_id: UUID,
        request: KernelRelationClaimTriageRequest,
        headers: Mapping[str, str] | None = None,
    ) -> KernelRelationClaimResponse:
        """Update one claim triage status."""
        return self._request_model(
            "PATCH",
            f"/v1/spaces/{space_id}/claims/{claim_id}",
            response_model=KernelRelationClaimResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def list_relation_conflicts(
        self,
        *,
        space_id: UUID,
        offset: int = 0,
        limit: int = 50,
        headers: Mapping[str, str] | None = None,
    ) -> KernelRelationConflictListResponse:
        """List mixed-polarity canonical relation conflicts."""
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/relations/conflicts",
            response_model=KernelRelationConflictListResponse,
            params={
                "offset": str(offset),
                "limit": str(limit),
            },
            headers=headers,
        )

    def backfill_claim_participants(
        self,
        *,
        space_id: UUID,
        request: ClaimParticipantBackfillRequest,
        headers: Mapping[str, str] | None = None,
    ) -> ClaimParticipantBackfillResponse:
        """Backfill claim participants for one graph space."""
        return self._request_model(
            "POST",
            f"/v1/spaces/{space_id}/claim-participants/backfill",
            response_model=ClaimParticipantBackfillResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def get_claim_participant_coverage(
        self,
        *,
        space_id: UUID,
        limit: int = 500,
        offset: int = 0,
        headers: Mapping[str, str] | None = None,
    ) -> ClaimParticipantCoverageResponse:
        """Fetch claim participant coverage for one graph space."""
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/claim-participants/coverage",
            response_model=ClaimParticipantCoverageResponse,
            params={
                "limit": str(limit),
                "offset": str(offset),
            },
            headers=headers,
        )

    def list_claim_relations(
        self,
        *,
        space_id: UUID,
        relation_type: str | None = None,
        review_status: str | None = None,
        source_claim_id: UUID | None = None,
        target_claim_id: UUID | None = None,
        claim_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
        headers: Mapping[str, str] | None = None,
    ) -> ClaimRelationListResponse:
        """List claim-to-claim relation edges for one graph space."""
        params: dict[str, str] = {
            "offset": str(offset),
            "limit": str(limit),
        }
        if relation_type is not None:
            params["relation_type"] = relation_type
        if review_status is not None:
            params["review_status"] = review_status
        if source_claim_id is not None:
            params["source_claim_id"] = str(source_claim_id)
        if target_claim_id is not None:
            params["target_claim_id"] = str(target_claim_id)
        if claim_id is not None:
            params["claim_id"] = str(claim_id)
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/claim-relations",
            response_model=ClaimRelationListResponse,
            params=params,
            headers=headers,
        )

    def create_claim_relation(
        self,
        *,
        space_id: UUID,
        request: ClaimRelationCreateRequest,
        headers: Mapping[str, str] | None = None,
    ) -> ClaimRelationResponse:
        """Create one claim-to-claim relation edge."""
        return self._request_model(
            "POST",
            f"/v1/spaces/{space_id}/claim-relations",
            response_model=ClaimRelationResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def update_claim_relation_review_status(
        self,
        *,
        space_id: UUID,
        relation_id: UUID,
        request: ClaimRelationReviewUpdateRequest,
        headers: Mapping[str, str] | None = None,
    ) -> ClaimRelationResponse:
        """Update one claim-relation review status."""
        return self._request_model(
            "PATCH",
            f"/v1/spaces/{space_id}/claim-relations/{relation_id}",
            response_model=ClaimRelationResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def get_subgraph(
        self,
        *,
        space_id: UUID,
        request: KernelGraphSubgraphRequest,
        headers: Mapping[str, str] | None = None,
    ) -> KernelGraphSubgraphResponse:
        """Fetch one bounded subgraph for a graph space."""
        return self._request_model(
            "POST",
            f"/v1/spaces/{space_id}/graph/subgraph",
            response_model=KernelGraphSubgraphResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def get_graph_export(
        self,
        *,
        space_id: UUID,
        headers: Mapping[str, str] | None = None,
    ) -> KernelGraphExportResponse:
        """Fetch one graph export payload for a graph space."""
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/graph/export",
            response_model=KernelGraphExportResponse,
            headers=headers,
        )

    def get_neighborhood(
        self,
        *,
        space_id: UUID,
        entity_id: UUID,
        depth: int = 1,
        headers: Mapping[str, str] | None = None,
    ) -> KernelGraphExportResponse:
        """Fetch one entity neighborhood for a graph space."""
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/graph/neighborhood/{entity_id}",
            response_model=KernelGraphExportResponse,
            params={"depth": str(depth)},
            headers=headers,
        )

    def get_graph_document(
        self,
        *,
        space_id: UUID,
        request: KernelGraphDocumentRequest,
        headers: Mapping[str, str] | None = None,
    ) -> KernelGraphDocumentResponse:
        """Fetch one unified graph document for a graph space."""
        return self._request_model(
            "POST",
            f"/v1/spaces/{space_id}/graph/document",
            response_model=KernelGraphDocumentResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def get_graph_view(
        self,
        *,
        space_id: UUID,
        view_type: str,
        resource_id: UUID,
        claim_limit: int = 50,
        relation_limit: int = 50,
        headers: Mapping[str, str] | None = None,
    ) -> KernelGraphDomainViewResponse:
        """Fetch one graph domain view for a graph space."""
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/graph/views/{view_type}/{resource_id}",
            response_model=KernelGraphDomainViewResponse,
            params={
                "claim_limit": str(claim_limit),
                "relation_limit": str(relation_limit),
            },
            headers=headers,
        )

    def get_claim_mechanism_chain(
        self,
        *,
        space_id: UUID,
        claim_id: UUID,
        max_depth: int = 3,
        headers: Mapping[str, str] | None = None,
    ) -> KernelClaimMechanismChainResponse:
        """Fetch one claim-rooted mechanism chain for a graph space."""
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/claims/{claim_id}/mechanism-chain",
            response_model=KernelClaimMechanismChainResponse,
            params={"max_depth": str(max_depth)},
            headers=headers,
        )

    def list_reasoning_paths(
        self,
        *,
        space_id: UUID,
        start_entity_id: UUID | None = None,
        end_entity_id: UUID | None = None,
        status: str | None = None,
        path_kind: str | None = None,
        offset: int = 0,
        limit: int = 50,
        headers: Mapping[str, str] | None = None,
    ) -> KernelReasoningPathListResponse:
        """List reasoning paths for one graph space."""
        params: dict[str, str] = {
            "offset": str(offset),
            "limit": str(limit),
        }
        if start_entity_id is not None:
            params["start_entity_id"] = str(start_entity_id)
        if end_entity_id is not None:
            params["end_entity_id"] = str(end_entity_id)
        if status is not None:
            params["status"] = status
        if path_kind is not None:
            params["path_kind"] = path_kind
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/reasoning-paths",
            response_model=KernelReasoningPathListResponse,
            params=params,
            headers=headers,
        )

    def get_reasoning_path(
        self,
        *,
        space_id: UUID,
        path_id: UUID,
        headers: Mapping[str, str] | None = None,
    ) -> KernelReasoningPathDetailResponse:
        """Fetch one detailed reasoning path from the graph service."""
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/reasoning-paths/{path_id}",
            response_model=KernelReasoningPathDetailResponse,
            headers=headers,
        )

    def list_concept_sets(
        self,
        *,
        space_id: UUID,
        include_inactive: bool = False,
        headers: Mapping[str, str] | None = None,
    ) -> ConceptSetListResponse:
        """List concept sets for one graph space."""
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/concepts/sets",
            response_model=ConceptSetListResponse,
            params={
                "include_inactive": str(include_inactive).lower(),
            },
            headers=headers,
        )

    def create_concept_set(
        self,
        *,
        space_id: UUID,
        name: str,
        slug: str,
        domain_context: str,
        description: str | None = None,
        source_ref: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> ConceptSetResponse:
        """Create one concept set for a graph space."""
        return self._request_model(
            "POST",
            f"/v1/spaces/{space_id}/concepts/sets",
            response_model=ConceptSetResponse,
            content=json.dumps(
                {
                    "name": name,
                    "slug": slug,
                    "domain_context": domain_context,
                    "description": description,
                    "source_ref": source_ref,
                },
            ),
            headers=headers,
        )

    def list_concept_members(
        self,
        *,
        space_id: UUID,
        concept_set_id: str | None = None,
        include_inactive: bool = False,
        offset: int = 0,
        limit: int = 100,
        headers: Mapping[str, str] | None = None,
    ) -> ConceptMemberListResponse:
        """List concept members for one graph space."""
        params: dict[str, str] = {
            "include_inactive": str(include_inactive).lower(),
            "offset": str(offset),
            "limit": str(limit),
        }
        if concept_set_id is not None:
            params["concept_set_id"] = concept_set_id
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/concepts/members",
            response_model=ConceptMemberListResponse,
            params=params,
            headers=headers,
        )

    def create_concept_member(
        self,
        *,
        space_id: UUID,
        concept_set_id: UUID,
        domain_context: str,
        canonical_label: str,
        normalized_label: str,
        sense_key: str = "",
        dictionary_dimension: str | None = None,
        dictionary_entry_id: str | None = None,
        is_provisional: bool = False,
        metadata_payload: Mapping[str, object] | None = None,
        source_ref: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> ConceptMemberResponse:
        """Create one concept member for a graph space."""
        return self._request_model(
            "POST",
            f"/v1/spaces/{space_id}/concepts/members",
            response_model=ConceptMemberResponse,
            content=json.dumps(
                {
                    "concept_set_id": str(concept_set_id),
                    "domain_context": domain_context,
                    "canonical_label": canonical_label,
                    "normalized_label": normalized_label,
                    "sense_key": sense_key,
                    "dictionary_dimension": dictionary_dimension,
                    "dictionary_entry_id": dictionary_entry_id,
                    "is_provisional": is_provisional,
                    "metadata_payload": dict(metadata_payload or {}),
                    "source_ref": source_ref,
                },
            ),
            headers=headers,
        )

    def list_concept_aliases(
        self,
        *,
        space_id: UUID,
        concept_member_id: str | None = None,
        include_inactive: bool = False,
        offset: int = 0,
        limit: int = 100,
        headers: Mapping[str, str] | None = None,
    ) -> ConceptAliasListResponse:
        """List concept aliases for one graph space."""
        params: dict[str, str] = {
            "include_inactive": str(include_inactive).lower(),
            "offset": str(offset),
            "limit": str(limit),
        }
        if concept_member_id is not None:
            params["concept_member_id"] = concept_member_id
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/concepts/aliases",
            response_model=ConceptAliasListResponse,
            params=params,
            headers=headers,
        )

    def create_concept_alias(
        self,
        *,
        space_id: UUID,
        concept_member_id: UUID,
        domain_context: str,
        alias_label: str,
        alias_normalized: str,
        source: str | None = None,
        source_ref: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> ConceptAliasResponse:
        """Create one concept alias for a graph space."""
        return self._request_model(
            "POST",
            f"/v1/spaces/{space_id}/concepts/aliases",
            response_model=ConceptAliasResponse,
            content=json.dumps(
                {
                    "concept_member_id": str(concept_member_id),
                    "domain_context": domain_context,
                    "alias_label": alias_label,
                    "alias_normalized": alias_normalized,
                    "source": source,
                    "source_ref": source_ref,
                },
            ),
            headers=headers,
        )

    def get_active_concept_policy(
        self,
        *,
        space_id: UUID,
        headers: Mapping[str, str] | None = None,
    ) -> ConceptPolicyResponse | None:
        """Fetch the active concept policy for one graph space."""
        response = self._request(
            "GET",
            f"/v1/spaces/{space_id}/concepts/policy",
            headers=headers,
        )
        if response.content in {b"null", b""}:
            return None
        return ConceptPolicyResponse.model_validate_json(response.content)

    def upsert_active_concept_policy(
        self,
        *,
        space_id: UUID,
        mode: str,
        minimum_edge_confidence: float = 0.6,
        minimum_distinct_documents: int = 1,
        allow_generic_relations: bool = True,
        max_edges_per_document: int | None = None,
        policy_payload: Mapping[str, object] | None = None,
        source_ref: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> ConceptPolicyResponse:
        """Upsert the active concept policy for one graph space."""
        return self._request_model(
            "PUT",
            f"/v1/spaces/{space_id}/concepts/policy",
            response_model=ConceptPolicyResponse,
            content=json.dumps(
                {
                    "mode": mode,
                    "minimum_edge_confidence": minimum_edge_confidence,
                    "minimum_distinct_documents": minimum_distinct_documents,
                    "allow_generic_relations": allow_generic_relations,
                    "max_edges_per_document": max_edges_per_document,
                    "policy_payload": dict(policy_payload or {}),
                    "source_ref": source_ref,
                },
            ),
            headers=headers,
        )

    def list_concept_decisions(
        self,
        *,
        space_id: UUID,
        decision_status: str | None = None,
        offset: int = 0,
        limit: int = 100,
        headers: Mapping[str, str] | None = None,
    ) -> ConceptDecisionListResponse:
        """List concept decisions for one graph space."""
        params: dict[str, str] = {
            "offset": str(offset),
            "limit": str(limit),
        }
        if decision_status is not None:
            params["decision_status"] = decision_status
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/concepts/decisions",
            response_model=ConceptDecisionListResponse,
            params=params,
            headers=headers,
        )

    def propose_concept_decision(
        self,
        *,
        space_id: UUID,
        decision_type: str,
        decision_payload: Mapping[str, object] | None = None,
        evidence_payload: Mapping[str, object] | None = None,
        confidence: float | None = None,
        rationale: str | None = None,
        concept_set_id: UUID | None = None,
        concept_member_id: UUID | None = None,
        concept_link_id: UUID | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> ConceptDecisionResponse:
        """Propose one concept decision for a graph space."""
        return self._request_model(
            "POST",
            f"/v1/spaces/{space_id}/concepts/decisions/propose",
            response_model=ConceptDecisionResponse,
            content=json.dumps(
                {
                    "decision_type": decision_type,
                    "decision_payload": dict(decision_payload or {}),
                    "evidence_payload": dict(evidence_payload or {}),
                    "confidence": confidence,
                    "rationale": rationale,
                    "concept_set_id": (
                        str(concept_set_id) if concept_set_id is not None else None
                    ),
                    "concept_member_id": (
                        str(concept_member_id)
                        if concept_member_id is not None
                        else None
                    ),
                    "concept_link_id": (
                        str(concept_link_id) if concept_link_id is not None else None
                    ),
                },
            ),
            headers=headers,
        )

    def set_concept_decision_status(
        self,
        *,
        space_id: UUID,
        decision_id: str,
        decision_status: str,
        headers: Mapping[str, str] | None = None,
    ) -> ConceptDecisionResponse:
        """Set one concept decision status for a graph space."""
        return self._request_model(
            "PATCH",
            f"/v1/spaces/{space_id}/concepts/decisions/{decision_id}/status",
            response_model=ConceptDecisionResponse,
            content=json.dumps({"decision_status": decision_status}),
            headers=headers,
        )

    def list_hypotheses(
        self,
        *,
        space_id: UUID,
        offset: int = 0,
        limit: int = 50,
        headers: Mapping[str, str] | None = None,
    ) -> HypothesisListResponse:
        """List hypotheses for one graph space."""
        return self._request_model(
            "GET",
            f"/v1/spaces/{space_id}/hypotheses",
            response_model=HypothesisListResponse,
            params={
                "offset": str(offset),
                "limit": str(limit),
            },
            headers=headers,
        )

    def create_manual_hypothesis(
        self,
        *,
        space_id: UUID,
        request: CreateManualHypothesisRequest,
        headers: Mapping[str, str] | None = None,
    ) -> HypothesisResponse:
        """Create one manual hypothesis through the graph service."""
        return self._request_model(
            "POST",
            f"/v1/spaces/{space_id}/hypotheses/manual",
            response_model=HypothesisResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def search_dictionary_entries_by_domain(
        self,
        *,
        domain_context: str,
        limit: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> DictionarySearchListResponse:
        """List graph dictionary entries for one domain."""
        return self._request_model(
            "GET",
            f"/v1/dictionary/search/by-domain/{domain_context}",
            response_model=DictionarySearchListResponse,
            params={"limit": str(limit)},
            headers=headers,
        )

    def list_dictionary_changelog_entries(
        self,
        *,
        table_name: str | None = None,
        record_id: str | None = None,
        limit: int = 100,
        headers: Mapping[str, str] | None = None,
    ) -> DictionaryChangelogListResponse:
        """List graph dictionary changelog entries."""
        params: dict[str, str] = {"limit": str(limit)}
        if table_name is not None:
            params["table_name"] = table_name
        if record_id is not None:
            params["record_id"] = record_id
        return self._request_model(
            "GET",
            "/v1/dictionary/changelog",
            response_model=DictionaryChangelogListResponse,
            params=params,
            headers=headers,
        )

    def list_entity_resolution_policies(
        self,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> EntityResolutionPolicyListResponse:
        """List graph dictionary entity resolution policies."""
        return self._request_model(
            "GET",
            "/v1/dictionary/resolution-policies",
            response_model=EntityResolutionPolicyListResponse,
            headers=headers,
        )

    def list_relation_constraints(
        self,
        *,
        source_type: str | None = None,
        relation_type: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> RelationConstraintListResponse:
        """List graph dictionary relation constraints."""
        params: dict[str, str] = {}
        if source_type is not None:
            params["source_type"] = source_type
        if relation_type is not None:
            params["relation_type"] = relation_type
        return self._request_model(
            "GET",
            "/v1/dictionary/relation-constraints",
            response_model=RelationConstraintListResponse,
            params=params or None,
            headers=headers,
        )

    def create_relation_constraint(
        self,
        *,
        source_type: str,
        relation_type: str,
        target_type: str,
        is_allowed: bool = True,
        requires_evidence: bool = True,
        source_ref: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> RelationConstraintResponse:
        """Create one graph dictionary relation constraint."""
        return self._request_model(
            "POST",
            "/v1/dictionary/relation-constraints",
            response_model=RelationConstraintResponse,
            content=json.dumps(
                {
                    "source_type": source_type,
                    "relation_type": relation_type,
                    "target_type": target_type,
                    "is_allowed": is_allowed,
                    "requires_evidence": requires_evidence,
                    "source_ref": source_ref,
                },
            ),
            headers=headers,
        )

    def list_dictionary_variables(
        self,
        *,
        domain_context: str | None = None,
        data_type: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> VariableDefinitionListResponse:
        """List graph dictionary variables."""
        params: dict[str, str] = {}
        if domain_context is not None:
            params["domain_context"] = domain_context
        if data_type is not None:
            params["data_type"] = data_type
        return self._request_model(
            "GET",
            "/v1/dictionary/variables",
            response_model=VariableDefinitionListResponse,
            params=params or None,
            headers=headers,
        )

    def create_dictionary_variable(
        self,
        *,
        request: VariableDefinitionCreateRequest,
        headers: Mapping[str, str] | None = None,
    ) -> VariableDefinitionResponse:
        """Create one graph dictionary variable."""
        return self._request_model(
            "POST",
            "/v1/dictionary/variables",
            response_model=VariableDefinitionResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def set_dictionary_variable_review_status(
        self,
        *,
        variable_id: str,
        request: VariableDefinitionReviewStatusRequest,
        headers: Mapping[str, str] | None = None,
    ) -> VariableDefinitionResponse:
        """Set graph dictionary variable review status."""
        return self._request_model(
            "PATCH",
            f"/v1/dictionary/variables/{variable_id}/review-status",
            response_model=VariableDefinitionResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def revoke_dictionary_variable(
        self,
        *,
        variable_id: str,
        request: VariableDefinitionRevokeRequest,
        headers: Mapping[str, str] | None = None,
    ) -> VariableDefinitionResponse:
        """Revoke one graph dictionary variable."""
        return self._request_model(
            "POST",
            f"/v1/dictionary/variables/{variable_id}/revoke",
            response_model=VariableDefinitionResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def merge_dictionary_variable(
        self,
        *,
        variable_id: str,
        request: DictionaryMergeRequest,
        headers: Mapping[str, str] | None = None,
    ) -> VariableDefinitionResponse:
        """Merge one graph dictionary variable into another."""
        return self._request_model(
            "POST",
            f"/v1/dictionary/variables/{variable_id}/merge",
            response_model=VariableDefinitionResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def list_dictionary_entity_types(
        self,
        *,
        domain_context: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> DictionaryEntityTypeListResponse:
        """List graph dictionary entity types."""
        params: dict[str, str] = {}
        if domain_context is not None:
            params["domain_context"] = domain_context
        return self._request_model(
            "GET",
            "/v1/dictionary/entity-types",
            response_model=DictionaryEntityTypeListResponse,
            params=params or None,
            headers=headers,
        )

    def get_dictionary_entity_type(
        self,
        *,
        entity_type_id: str,
        headers: Mapping[str, str] | None = None,
    ) -> DictionaryEntityTypeResponse:
        """Fetch one graph dictionary entity type."""
        return self._request_model(
            "GET",
            f"/v1/dictionary/entity-types/{entity_type_id}",
            response_model=DictionaryEntityTypeResponse,
            headers=headers,
        )

    def create_dictionary_entity_type(
        self,
        *,
        request: DictionaryEntityTypeCreateRequest,
        headers: Mapping[str, str] | None = None,
    ) -> DictionaryEntityTypeResponse:
        """Create one graph dictionary entity type."""
        return self._request_model(
            "POST",
            "/v1/dictionary/entity-types",
            response_model=DictionaryEntityTypeResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def set_dictionary_entity_type_review_status(
        self,
        *,
        entity_type_id: str,
        request: VariableDefinitionReviewStatusRequest,
        headers: Mapping[str, str] | None = None,
    ) -> DictionaryEntityTypeResponse:
        """Set graph dictionary entity type review status."""
        return self._request_model(
            "PATCH",
            f"/v1/dictionary/entity-types/{entity_type_id}/review-status",
            response_model=DictionaryEntityTypeResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def revoke_dictionary_entity_type(
        self,
        *,
        entity_type_id: str,
        request: VariableDefinitionRevokeRequest,
        headers: Mapping[str, str] | None = None,
    ) -> DictionaryEntityTypeResponse:
        """Revoke one graph dictionary entity type."""
        return self._request_model(
            "POST",
            f"/v1/dictionary/entity-types/{entity_type_id}/revoke",
            response_model=DictionaryEntityTypeResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def merge_dictionary_entity_type(
        self,
        *,
        entity_type_id: str,
        request: DictionaryMergeRequest,
        headers: Mapping[str, str] | None = None,
    ) -> DictionaryEntityTypeResponse:
        """Merge one graph dictionary entity type into another."""
        return self._request_model(
            "POST",
            f"/v1/dictionary/entity-types/{entity_type_id}/merge",
            response_model=DictionaryEntityTypeResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def list_dictionary_relation_types(
        self,
        *,
        domain_context: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> DictionaryRelationTypeListResponse:
        """List graph dictionary relation types."""
        params: dict[str, str] = {}
        if domain_context is not None:
            params["domain_context"] = domain_context
        return self._request_model(
            "GET",
            "/v1/dictionary/relation-types",
            response_model=DictionaryRelationTypeListResponse,
            params=params or None,
            headers=headers,
        )

    def get_dictionary_relation_type(
        self,
        *,
        relation_type_id: str,
        headers: Mapping[str, str] | None = None,
    ) -> DictionaryRelationTypeResponse:
        """Fetch one graph dictionary relation type."""
        return self._request_model(
            "GET",
            f"/v1/dictionary/relation-types/{relation_type_id}",
            response_model=DictionaryRelationTypeResponse,
            headers=headers,
        )

    def create_dictionary_relation_type(
        self,
        *,
        request: DictionaryRelationTypeCreateRequest,
        headers: Mapping[str, str] | None = None,
    ) -> DictionaryRelationTypeResponse:
        """Create one graph dictionary relation type."""
        return self._request_model(
            "POST",
            "/v1/dictionary/relation-types",
            response_model=DictionaryRelationTypeResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def set_dictionary_relation_type_review_status(
        self,
        *,
        relation_type_id: str,
        request: VariableDefinitionReviewStatusRequest,
        headers: Mapping[str, str] | None = None,
    ) -> DictionaryRelationTypeResponse:
        """Set graph dictionary relation type review status."""
        return self._request_model(
            "PATCH",
            f"/v1/dictionary/relation-types/{relation_type_id}/review-status",
            response_model=DictionaryRelationTypeResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def revoke_dictionary_relation_type(
        self,
        *,
        relation_type_id: str,
        request: VariableDefinitionRevokeRequest,
        headers: Mapping[str, str] | None = None,
    ) -> DictionaryRelationTypeResponse:
        """Revoke one graph dictionary relation type."""
        return self._request_model(
            "POST",
            f"/v1/dictionary/relation-types/{relation_type_id}/revoke",
            response_model=DictionaryRelationTypeResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def merge_dictionary_relation_type(
        self,
        *,
        relation_type_id: str,
        request: DictionaryMergeRequest,
        headers: Mapping[str, str] | None = None,
    ) -> DictionaryRelationTypeResponse:
        """Merge one graph dictionary relation type into another."""
        return self._request_model(
            "POST",
            f"/v1/dictionary/relation-types/{relation_type_id}/merge",
            response_model=DictionaryRelationTypeResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def list_dictionary_relation_synonyms(
        self,
        *,
        relation_type_id: str | None = None,
        include_inactive: bool = False,
        headers: Mapping[str, str] | None = None,
    ) -> DictionaryRelationSynonymListResponse:
        """List graph dictionary relation synonyms."""
        params: dict[str, str] = {"include_inactive": str(include_inactive).lower()}
        if relation_type_id is not None:
            params["relation_type_id"] = relation_type_id
        return self._request_model(
            "GET",
            "/v1/dictionary/relation-synonyms",
            response_model=DictionaryRelationSynonymListResponse,
            params=params,
            headers=headers,
        )

    def resolve_dictionary_relation_synonym(
        self,
        *,
        synonym: str,
        include_inactive: bool = False,
        headers: Mapping[str, str] | None = None,
    ) -> DictionaryRelationTypeResponse:
        """Resolve one graph dictionary relation synonym."""
        return self._request_model(
            "GET",
            "/v1/dictionary/relation-synonyms/resolve",
            response_model=DictionaryRelationTypeResponse,
            params={
                "synonym": synonym,
                "include_inactive": str(include_inactive).lower(),
            },
            headers=headers,
        )

    def create_dictionary_relation_synonym(
        self,
        *,
        request: DictionaryRelationSynonymCreateRequest,
        headers: Mapping[str, str] | None = None,
    ) -> DictionaryRelationSynonymResponse:
        """Create one graph dictionary relation synonym."""
        return self._request_model(
            "POST",
            "/v1/dictionary/relation-synonyms",
            response_model=DictionaryRelationSynonymResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def set_dictionary_relation_synonym_review_status(
        self,
        *,
        synonym_id: int,
        request: VariableDefinitionReviewStatusRequest,
        headers: Mapping[str, str] | None = None,
    ) -> DictionaryRelationSynonymResponse:
        """Set graph dictionary relation synonym review status."""
        return self._request_model(
            "PATCH",
            f"/v1/dictionary/relation-synonyms/{synonym_id}/review-status",
            response_model=DictionaryRelationSynonymResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def revoke_dictionary_relation_synonym(
        self,
        *,
        synonym_id: int,
        request: VariableDefinitionRevokeRequest,
        headers: Mapping[str, str] | None = None,
    ) -> DictionaryRelationSynonymResponse:
        """Revoke one graph dictionary relation synonym."""
        return self._request_model(
            "POST",
            f"/v1/dictionary/relation-synonyms/{synonym_id}/revoke",
            response_model=DictionaryRelationSynonymResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def list_dictionary_value_sets(
        self,
        *,
        variable_id: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> ValueSetListResponse:
        """List graph dictionary value sets."""
        params: dict[str, str] = {}
        if variable_id is not None:
            params["variable_id"] = variable_id
        return self._request_model(
            "GET",
            "/v1/dictionary/value-sets",
            response_model=ValueSetListResponse,
            params=params or None,
            headers=headers,
        )

    def create_dictionary_value_set(
        self,
        *,
        request: ValueSetCreateRequest,
        headers: Mapping[str, str] | None = None,
    ) -> ValueSetResponse:
        """Create one graph dictionary value set."""
        return self._request_model(
            "POST",
            "/v1/dictionary/value-sets",
            response_model=ValueSetResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def list_dictionary_value_set_items(
        self,
        *,
        value_set_id: str,
        include_inactive: bool = False,
        headers: Mapping[str, str] | None = None,
    ) -> ValueSetItemListResponse:
        """List graph dictionary value set items."""
        return self._request_model(
            "GET",
            f"/v1/dictionary/value-sets/{value_set_id}/items",
            response_model=ValueSetItemListResponse,
            params={"include_inactive": str(include_inactive).lower()},
            headers=headers,
        )

    def create_dictionary_value_set_item(
        self,
        *,
        value_set_id: str,
        request: ValueSetItemCreateRequest,
        headers: Mapping[str, str] | None = None,
    ) -> ValueSetItemResponse:
        """Create one graph dictionary value set item."""
        return self._request_model(
            "POST",
            f"/v1/dictionary/value-sets/{value_set_id}/items",
            response_model=ValueSetItemResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def set_dictionary_value_set_item_active(
        self,
        *,
        value_set_item_id: int,
        request: ValueSetItemActiveRequest,
        headers: Mapping[str, str] | None = None,
    ) -> ValueSetItemResponse:
        """Set one graph dictionary value set item active state."""
        return self._request_model(
            "PATCH",
            f"/v1/dictionary/value-set-items/{value_set_item_id}/active",
            response_model=ValueSetItemResponse,
            content=request.model_dump_json(),
            headers=headers,
        )

    def list_transform_registry(
        self,
        *,
        status_filter: str = "ACTIVE",
        include_inactive: bool = False,
        production_only: bool = False,
        headers: Mapping[str, str] | None = None,
    ) -> TransformRegistryListResponse:
        """List graph dictionary transform registry entries."""
        return self._request_model(
            "GET",
            "/v1/dictionary/transforms",
            response_model=TransformRegistryListResponse,
            params={
                "status": status_filter,
                "include_inactive": str(include_inactive).lower(),
                "production_only": str(production_only).lower(),
            },
            headers=headers,
        )

    def verify_transform_registry_entry(
        self,
        *,
        transform_id: str,
        headers: Mapping[str, str] | None = None,
    ) -> TransformVerificationResponse:
        """Run graph dictionary transform fixture verification."""
        return self._request_model(
            "POST",
            f"/v1/dictionary/transforms/{transform_id}/verify",
            response_model=TransformVerificationResponse,
            headers=headers,
        )

    def promote_transform_registry_entry(
        self,
        *,
        transform_id: str,
        headers: Mapping[str, str] | None = None,
    ) -> TransformRegistryResponse:
        """Promote one graph dictionary transform to production use."""
        return self._request_model(
            "PATCH",
            f"/v1/dictionary/transforms/{transform_id}/promote",
            response_model=TransformRegistryResponse,
            headers=headers,
        )

    def _request_model[
        ResponseModelT: BaseModel
    ](
        self,
        method: str,
        path: str,
        *,
        response_model: type[ResponseModelT],
        params: GraphServiceRequestParams | None = None,
        headers: Mapping[str, str] | None = None,
        content: str | None = None,
    ) -> ResponseModelT:
        response = self._request(
            method,
            path,
            params=params,
            headers=headers,
            content=content,
        )
        return response_model.model_validate_json(response.content)

    def _request(
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
            response = self._client.request(
                method,
                path,
                params=request_params,
                headers=merged_headers,
                content=content,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text if exc.response is not None else None
            raise GraphServiceClientError(
                f"Graph service request failed: {method} {path}",
                status_code=(
                    exc.response.status_code if exc.response is not None else None
                ),
                detail=detail,
            ) from exc
        except httpx.HTTPError as exc:
            raise GraphServiceClientError(
                f"Graph service request failed: {method} {path}",
            ) from exc
        return response

    def _merge_headers(
        self,
        *,
        headers: Mapping[str, str] | None,
        has_json_body: bool,
    ) -> dict[str, str]:
        merged_headers = dict(self._config.default_headers)
        if headers is not None:
            merged_headers.update(headers)
        if has_json_body and "Content-Type" not in merged_headers:
            merged_headers["Content-Type"] = "application/json"
        return merged_headers


__all__ = [
    "GraphServiceClient",
    "GraphServiceClientConfig",
    "GraphServiceClientError",
    "GraphServiceHealthResponse",
    "GraphProjectionReadinessIssueResponse",
    "GraphProjectionReadinessReportResponse",
    "GraphProjectionReadinessSampleResponse",
    "GraphOperationRunListResponse",
    "GraphOperationRunResponse",
    "GraphProjectionRepairSummaryResponse",
    "GraphReasoningPathRebuildResponse",
    "GraphReasoningPathRebuildSummaryResponse",
    "GraphSpaceMembershipListResponse",
    "GraphSpaceMembershipResponse",
    "GraphSpaceSyncMembershipPayload",
    "GraphSpaceSyncResponse",
    "GraphSpaceMembershipUpsertRequestPayload",
    "GraphSpaceRegistryListResponse",
    "GraphSpaceRegistryResponse",
    "GraphSpaceRegistryUpsertRequestPayload",
    "HypothesisListResponse",
    "HypothesisResponse",
]
