# ruff: noqa: TC001,TC003
"""Provenance and graph document schemas for kernel graph routes."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.graph_api_schemas.kernel_entity_schemas import (
    KernelEntityResponse,
)
from artana_evidence_db.graph_api_schemas.kernel_relation_schemas import (
    KernelRelationResponse,
)
from artana_evidence_db.graph_api_schemas.kernel_schema_common import (
    _to_required_utc_datetime,
    _to_uuid,
)
from artana_evidence_db.kernel_domain_models import KernelProvenanceRecord
from pydantic import BaseModel, ConfigDict, Field


class KernelProvenanceResponse(BaseModel):
    """Response model for a provenance record."""

    model_config = ConfigDict(strict=True)

    id: UUID
    research_space_id: UUID
    source_type: str
    source_ref: str | None
    extraction_run_id: str | None
    mapping_method: str | None
    mapping_confidence: float | None
    agent_model: str | None
    raw_input: JSONObject | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: KernelProvenanceRecord) -> KernelProvenanceResponse:
        return cls(
            id=_to_uuid(model.id),
            research_space_id=_to_uuid(model.research_space_id),
            source_type=str(model.source_type),
            source_ref=model.source_ref,
            extraction_run_id=model.extraction_run_id,
            mapping_method=model.mapping_method,
            mapping_confidence=model.mapping_confidence,
            agent_model=model.agent_model,
            raw_input=dict(model.raw_input) if model.raw_input else None,
            created_at=_to_required_utc_datetime(
                model.created_at,
                field_name="provenance.created_at",
            ),
            updated_at=_to_required_utc_datetime(
                model.updated_at or model.created_at,
                field_name="provenance.updated_at",
            ),
        )


class KernelProvenanceListResponse(BaseModel):
    """List response for provenance records."""

    model_config = ConfigDict(strict=True)

    provenance: list[KernelProvenanceResponse]
    total: int
    offset: int
    limit: int


class KernelGraphExportResponse(BaseModel):
    """Graph export response for a research space (nodes + edges)."""

    model_config = ConfigDict(strict=True)

    nodes: list[KernelEntityResponse]
    edges: list[KernelRelationResponse]


class KernelGraphSubgraphRequest(BaseModel):
    """Request payload for bounded subgraph retrieval."""

    model_config = ConfigDict(strict=False)

    mode: Literal["starter", "seeded"]
    seed_entity_ids: list[UUID] = Field(default_factory=list)
    depth: int = Field(default=2, ge=1, le=4)
    top_k: int = Field(default=25, ge=1, le=100)
    relation_types: list[str] | None = None
    curation_statuses: list[str] | None = None
    max_nodes: int = Field(default=180, ge=20, le=500)
    max_edges: int = Field(default=260, ge=20, le=1000)


class KernelGraphSubgraphMeta(BaseModel):
    """Metadata describing bounded-subgraph execution and truncation."""

    model_config = ConfigDict(strict=True)

    mode: Literal["starter", "seeded"]
    seed_entity_ids: list[UUID]
    requested_depth: int
    requested_top_k: int
    pre_cap_node_count: int
    pre_cap_edge_count: int
    truncated_nodes: bool
    truncated_edges: bool


class KernelGraphSubgraphResponse(BaseModel):
    """Bounded subgraph response for interactive graph rendering."""

    model_config = ConfigDict(strict=True)

    nodes: list[KernelEntityResponse]
    edges: list[KernelRelationResponse]
    meta: KernelGraphSubgraphMeta


class KernelGraphDocumentRequest(BaseModel):
    """Request payload for unified graph documents with claim/evidence overlays."""

    model_config = ConfigDict(strict=False)

    mode: Literal["starter", "seeded"]
    seed_entity_ids: list[UUID] = Field(default_factory=list)
    depth: int = Field(default=2, ge=1, le=4)
    top_k: int = Field(default=25, ge=1, le=100)
    relation_types: list[str] | None = None
    curation_statuses: list[str] | None = None
    max_nodes: int = Field(default=180, ge=20, le=500)
    max_edges: int = Field(default=260, ge=20, le=1000)
    include_claims: bool = True
    include_evidence: bool = True
    max_claims: int = Field(default=250, ge=1, le=1000)
    evidence_limit_per_claim: int = Field(default=3, ge=1, le=10)


class KernelGraphDocumentNode(BaseModel):
    """One typed graph node in the unified graph document."""

    model_config = ConfigDict(strict=True)

    id: str = Field(min_length=1, max_length=255)
    resource_id: str = Field(min_length=1, max_length=255)
    kind: Literal["ENTITY", "CLAIM", "EVIDENCE"]
    type_label: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=512)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    curation_status: str | None = Field(default=None, max_length=32)
    claim_status: str | None = Field(default=None, max_length=32)
    polarity: str | None = Field(default=None, max_length=32)
    canonical_relation_id: UUID | None = None
    metadata: JSONObject = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class KernelGraphDocumentEdge(BaseModel):
    """One typed graph edge in the unified graph document."""

    model_config = ConfigDict(strict=True)

    id: str = Field(min_length=1, max_length=255)
    resource_id: str | None = Field(default=None, max_length=255)
    kind: Literal["CANONICAL_RELATION", "CLAIM_PARTICIPANT", "CLAIM_EVIDENCE"]
    source_id: str = Field(min_length=1, max_length=255)
    target_id: str = Field(min_length=1, max_length=255)
    type_label: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=512)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    curation_status: str | None = Field(default=None, max_length=32)
    claim_id: UUID | None = None
    canonical_relation_id: UUID | None = None
    evidence_id: UUID | None = None
    metadata: JSONObject = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class KernelGraphDocumentCounts(BaseModel):
    """Per-kind counts returned with a unified graph document."""

    model_config = ConfigDict(strict=True)

    entity_nodes: int = Field(ge=0)
    claim_nodes: int = Field(ge=0)
    evidence_nodes: int = Field(ge=0)
    canonical_edges: int = Field(ge=0)
    claim_participant_edges: int = Field(ge=0)
    claim_evidence_edges: int = Field(ge=0)


class KernelGraphDocumentMeta(BaseModel):
    """Metadata describing graph-document scope and included overlays."""

    model_config = ConfigDict(strict=True)

    mode: Literal["starter", "seeded"]
    seed_entity_ids: list[UUID]
    requested_depth: int
    requested_top_k: int
    pre_cap_entity_node_count: int
    pre_cap_canonical_edge_count: int
    truncated_entity_nodes: bool
    truncated_canonical_edges: bool
    included_claims: bool
    included_evidence: bool
    max_claims: int
    evidence_limit_per_claim: int
    counts: KernelGraphDocumentCounts


class KernelGraphDocumentResponse(BaseModel):
    """Unified graph document containing canonical, claim, and evidence elements."""

    model_config = ConfigDict(strict=True)

    nodes: list[KernelGraphDocumentNode]
    edges: list[KernelGraphDocumentEdge]
    meta: KernelGraphDocumentMeta
