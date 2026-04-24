# ruff: noqa: TC001,TC003
"""Schemas for derived reasoning-path read APIs."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.graph_api_schemas.claim_graph_schemas import (
    ClaimParticipantResponse,
    ClaimRelationResponse,
)
from artana_evidence_db.graph_api_schemas.kernel_graph_view_schemas import (
    KernelGraphViewCountsResponse,
)
from artana_evidence_db.graph_api_schemas.kernel_schemas import (
    KernelClaimEvidenceResponse,
    KernelRelationClaimResponse,
    KernelRelationResponse,
)
from artana_evidence_db.kernel_domain_models import (
    KernelReasoningPath,
    KernelReasoningPathStep,
)
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from artana_evidence_db.kernel_domain_models import (
        KernelClaimEvidence,
        KernelClaimParticipant,
        KernelClaimRelation,
        KernelRelation,
        KernelRelationClaim,
    )


class ReasoningPathDetailLike(Protocol):
    """Structural contract for reasoning-path detail serialization."""

    @property
    def path(self) -> KernelReasoningPath: ...

    @property
    def steps(self) -> Sequence[KernelReasoningPathStep]: ...

    @property
    def canonical_relations(self) -> Sequence[KernelRelation]: ...

    @property
    def claims(self) -> Sequence[KernelRelationClaim]: ...

    @property
    def claim_relations(self) -> Sequence[KernelClaimRelation]: ...

    @property
    def participants(self) -> Sequence[KernelClaimParticipant]: ...

    @property
    def evidence(self) -> Sequence[KernelClaimEvidence]: ...


def _to_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class KernelReasoningPathResponse(BaseModel):
    """One reasoning path summary row."""

    model_config = ConfigDict(strict=True)

    id: UUID
    research_space_id: UUID
    path_kind: str
    status: str
    start_entity_id: UUID
    end_entity_id: UUID
    root_claim_id: UUID
    path_length: int = Field(ge=1)
    confidence: float = Field(ge=0.0, le=1.0)
    path_signature_hash: str
    generated_by: str | None
    generated_at: datetime
    metadata: JSONObject
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: KernelReasoningPath) -> KernelReasoningPathResponse:
        return cls(
            id=_to_uuid(model.id),
            research_space_id=_to_uuid(model.research_space_id),
            path_kind=str(model.path_kind),
            status=str(model.status),
            start_entity_id=_to_uuid(model.start_entity_id),
            end_entity_id=_to_uuid(model.end_entity_id),
            root_claim_id=_to_uuid(model.root_claim_id),
            path_length=int(model.path_length),
            confidence=float(model.confidence),
            path_signature_hash=str(model.path_signature_hash),
            generated_by=model.generated_by,
            generated_at=model.generated_at,
            metadata=dict(model.metadata_payload),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class KernelReasoningPathStepResponse(BaseModel):
    """One ordered step inside a reasoning path."""

    model_config = ConfigDict(strict=True)

    id: UUID
    path_id: UUID
    step_index: int
    source_claim_id: UUID
    target_claim_id: UUID
    claim_relation_id: UUID
    canonical_relation_id: UUID | None
    metadata: JSONObject
    created_at: datetime

    @classmethod
    def from_model(
        cls,
        model: KernelReasoningPathStep,
    ) -> KernelReasoningPathStepResponse:
        return cls(
            id=_to_uuid(model.id),
            path_id=_to_uuid(model.path_id),
            step_index=int(model.step_index),
            source_claim_id=_to_uuid(model.source_claim_id),
            target_claim_id=_to_uuid(model.target_claim_id),
            claim_relation_id=_to_uuid(model.claim_relation_id),
            canonical_relation_id=(
                _to_uuid(model.canonical_relation_id)
                if model.canonical_relation_id is not None
                else None
            ),
            metadata=dict(model.metadata_payload),
            created_at=model.created_at,
        )


class KernelReasoningPathListResponse(BaseModel):
    """List response for reasoning paths in one space."""

    model_config = ConfigDict(strict=True)

    paths: list[KernelReasoningPathResponse]
    total: int
    offset: int
    limit: int


class KernelReasoningPathDetailResponse(BaseModel):
    """Fully expanded reasoning-path payload."""

    model_config = ConfigDict(strict=True)

    path: KernelReasoningPathResponse
    steps: list[KernelReasoningPathStepResponse]
    canonical_relations: list[KernelRelationResponse]
    claims: list[KernelRelationClaimResponse]
    claim_relations: list[ClaimRelationResponse]
    participants: list[ClaimParticipantResponse]
    evidence: list[KernelClaimEvidenceResponse]
    counts: KernelGraphViewCountsResponse

    @classmethod
    def from_detail(
        cls,
        detail: ReasoningPathDetailLike,
    ) -> KernelReasoningPathDetailResponse:
        steps = [
            KernelReasoningPathStepResponse.from_model(step) for step in detail.steps
        ]
        canonical_relations = [
            KernelRelationResponse.from_model(item)
            for item in detail.canonical_relations
        ]
        claims = [
            KernelRelationClaimResponse.from_model(item) for item in detail.claims
        ]
        claim_relations = [
            ClaimRelationResponse.from_model(item) for item in detail.claim_relations
        ]
        participants = [
            ClaimParticipantResponse.from_model(item) for item in detail.participants
        ]
        evidence = [
            KernelClaimEvidenceResponse.from_model(item) for item in detail.evidence
        ]
        return cls(
            path=KernelReasoningPathResponse.from_model(detail.path),
            steps=steps,
            canonical_relations=canonical_relations,
            claims=claims,
            claim_relations=claim_relations,
            participants=participants,
            evidence=evidence,
            counts=KernelGraphViewCountsResponse(
                canonical_relations=len(canonical_relations),
                claims=len(claims),
                claim_relations=len(claim_relations),
                participants=len(participants),
                evidence=len(evidence),
            ),
        )


__all__ = [
    "KernelReasoningPathDetailResponse",
    "KernelReasoningPathListResponse",
    "KernelReasoningPathResponse",
    "KernelReasoningPathStepResponse",
]
