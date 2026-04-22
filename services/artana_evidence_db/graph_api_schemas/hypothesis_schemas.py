# ruff: noqa: TC001,TC003
"""Pydantic schemas for hypothesis workflow routes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.kernel_domain_models import KernelRelationClaim
from pydantic import BaseModel, ConfigDict, Field


class CreateManualHypothesisRequest(BaseModel):
    """Request payload for manually logging one hypothesis."""

    model_config = ConfigDict(strict=True)

    statement: str = Field(..., min_length=1, max_length=4000)
    rationale: str = Field(..., min_length=1, max_length=4000)
    seed_entity_ids: list[str] = Field(default_factory=list, max_length=100)
    source_type: str = Field(default="manual", min_length=1, max_length=64)


class GenerateHypothesesRequest(BaseModel):
    """Request payload for graph-based hypothesis generation."""

    model_config = ConfigDict(strict=True)

    seed_entity_ids: list[str] | None = Field(default=None, max_length=100)
    source_type: str = Field(default="pubmed", min_length=1, max_length=64)
    relation_types: list[str] | None = Field(default=None, max_length=200)
    max_depth: int = Field(default=2, ge=1, le=4)
    max_hypotheses: int = Field(default=20, ge=1, le=100)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)


class HypothesisResponse(BaseModel):
    """Serialized hypothesis row derived from relation-claim ledger."""

    model_config = ConfigDict(strict=True)

    claim_id: UUID
    polarity: str
    claim_status: str
    validation_state: str
    persistability: str
    confidence: float
    source_label: str | None
    relation_type: str
    target_label: str | None
    claim_text: str | None
    linked_relation_id: UUID | None
    origin: str
    seed_entity_ids: list[str]
    supporting_provenance_ids: list[str]
    reasoning_path_id: UUID | None
    supporting_claim_ids: list[str]
    direct_supporting_claim_ids: list[str]
    transferred_supporting_claim_ids: list[str]
    transferred_from_entities: list[str]
    transfer_basis: list[str]
    contradiction_claim_ids: list[str]
    explanation: str | None
    path_confidence: float | None
    path_length: int | None
    created_at: datetime
    metadata: JSONObject

    @classmethod
    def from_claim(cls, claim: KernelRelationClaim) -> HypothesisResponse:
        metadata_payload = (
            claim.metadata_payload if isinstance(claim.metadata_payload, dict) else {}
        )
        seed_entity_ids = _resolve_seed_entity_ids(metadata_payload)
        supporting_provenance_ids = _resolve_supporting_provenance_ids(
            metadata_payload,
        )
        reasoning_path_id = _resolve_optional_uuid(
            metadata_payload.get("reasoning_path_id"),
        )
        path_confidence = _resolve_optional_float(
            metadata_payload.get("path_confidence"),
        )
        path_length = _resolve_optional_int(metadata_payload.get("path_length"))
        return cls(
            claim_id=_to_uuid(claim.id),
            polarity=str(claim.polarity),
            claim_status=str(claim.claim_status),
            validation_state=str(claim.validation_state),
            persistability=str(claim.persistability),
            confidence=float(claim.confidence),
            source_label=claim.source_label,
            relation_type=str(claim.relation_type),
            target_label=claim.target_label,
            claim_text=claim.claim_text,
            linked_relation_id=(
                _to_uuid(claim.linked_relation_id)
                if claim.linked_relation_id is not None
                else None
            ),
            origin=_resolve_origin(metadata_payload),
            seed_entity_ids=seed_entity_ids,
            supporting_provenance_ids=supporting_provenance_ids,
            reasoning_path_id=reasoning_path_id,
            supporting_claim_ids=_resolve_string_list(
                metadata_payload.get("supporting_claim_ids"),
            ),
            direct_supporting_claim_ids=_resolve_string_list(
                metadata_payload.get("direct_supporting_claim_ids"),
            ),
            transferred_supporting_claim_ids=_resolve_string_list(
                metadata_payload.get("transferred_supporting_claim_ids"),
            ),
            transferred_from_entities=_resolve_string_list(
                metadata_payload.get("transferred_from_entities"),
            ),
            transfer_basis=_resolve_string_list(
                metadata_payload.get("transfer_basis"),
            ),
            contradiction_claim_ids=_resolve_string_list(
                metadata_payload.get("contradiction_claim_ids"),
            ),
            explanation=_resolve_optional_text(metadata_payload.get("explanation")),
            path_confidence=path_confidence,
            path_length=path_length,
            created_at=claim.created_at,
            metadata=dict(metadata_payload),
        )


class HypothesisListResponse(BaseModel):
    """List response for hypotheses in one research space."""

    model_config = ConfigDict(strict=True)

    hypotheses: list[HypothesisResponse]
    total: int
    offset: int
    limit: int


class GenerateHypothesesResponse(BaseModel):
    """Response payload for one hypothesis generation run."""

    model_config = ConfigDict(strict=True)

    run_id: str
    requested_seed_count: int
    used_seed_count: int
    candidates_seen: int
    created_count: int
    deduped_count: int
    errors: list[str]
    hypotheses: list[HypothesisResponse]


def _to_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _resolve_origin(metadata_payload: JSONObject) -> str:
    raw_origin = metadata_payload.get("origin")
    if isinstance(raw_origin, str) and raw_origin.strip():
        return raw_origin.strip()
    return "manual"


def _resolve_seed_entity_ids(metadata_payload: JSONObject) -> list[str]:
    seed_entity_ids = _resolve_string_list(metadata_payload.get("seed_entity_ids"))
    if seed_entity_ids:
        return seed_entity_ids
    seed_entity_id = metadata_payload.get("seed_entity_id")
    if isinstance(seed_entity_id, str) and seed_entity_id.strip():
        return [seed_entity_id.strip()]
    return []


def _resolve_supporting_provenance_ids(metadata_payload: JSONObject) -> list[str]:
    return _resolve_string_list(metadata_payload.get("supporting_provenance_ids"))


def _resolve_optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _resolve_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        trimmed = item.strip()
        if not trimmed:
            continue
        normalized.append(trimmed)
    return normalized


def _resolve_optional_uuid(value: object) -> UUID | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    try:
        return UUID(trimmed)
    except ValueError:
        return None


def _resolve_optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _resolve_optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


__all__ = [
    "CreateManualHypothesisRequest",
    "GenerateHypothesesRequest",
    "GenerateHypothesesResponse",
    "HypothesisListResponse",
    "HypothesisResponse",
]
