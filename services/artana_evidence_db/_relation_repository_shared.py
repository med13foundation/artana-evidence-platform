"""Shared utility types for service-local relation repositories."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from artana_evidence_db.relation_autopromotion_policy import (
    DEFAULT_RELATION_AUTOPROMOTION_EVIDENCE_TIER,
    RELATION_AUTOPROMOTION_EVIDENCE_TIER_RANK,
)


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _try_as_uuid(value: str | UUID | None) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return UUID(normalized)
    except ValueError:
        return None


def _clamp_confidence(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _normalize_evidence_tier(value: str | None) -> str:
    if value is None:
        return DEFAULT_RELATION_AUTOPROMOTION_EVIDENCE_TIER
    normalized = value.strip().upper()
    if not normalized:
        return DEFAULT_RELATION_AUTOPROMOTION_EVIDENCE_TIER
    return normalized


def _tier_rank(value: str | None) -> int:
    if value is None:
        return 0
    return RELATION_AUTOPROMOTION_EVIDENCE_TIER_RANK.get(value.strip().upper(), 0)


def _source_family_key(evidence: object) -> str:
    """Derive a source-family key for support-unit collapsing.

    Multiple evidence rows from the same source document collapse into
    one support unit. The priority chain is:
    source_document_id > source_document_ref > provenance_id > agent_run_id > evidence.id
    """
    doc_id = getattr(evidence, "source_document_id", None)
    if doc_id is not None:
        return f"document:{doc_id}"
    doc_ref = getattr(evidence, "source_document_ref", None)
    if doc_ref is not None:
        return f"document_ref:{doc_ref}"
    prov_id = getattr(evidence, "provenance_id", None)
    if prov_id is not None:
        return f"provenance:{prov_id}"
    run_id = getattr(evidence, "agent_run_id", None)
    if run_id is not None:
        return f"run:{run_id}"
    eid = getattr(evidence, "id", None)
    return f"evidence:{eid}"


def _claim_source_family_key(claim: object) -> str:
    """Derive a source-family key for claim-level confidence fallback."""
    doc_id = getattr(claim, "source_document_id", None)
    if doc_id is not None:
        return f"document:{doc_id}"
    doc_ref = getattr(claim, "source_document_ref", None)
    if doc_ref is not None:
        return f"document_ref:{doc_ref}"
    run_id = getattr(claim, "agent_run_id", None)
    if run_id is not None:
        return f"run:{run_id}"
    claim_id = getattr(claim, "id", None)
    return f"claim:{claim_id}"


def _diminishing_confidence(unit_scores: Iterable[float]) -> float:
    """Aggregate independent confidence units with diminishing returns."""
    product = 1.0
    for unit_score in unit_scores:
        product *= 1.0 - _clamp_confidence(float(unit_score))
    return _clamp_confidence(1.0 - product)


__all__ = [
    "_as_uuid",
    "_claim_source_family_key",
    "_clamp_confidence",
    "_diminishing_confidence",
    "_normalize_evidence_tier",
    "_source_family_key",
    "_tier_rank",
    "_try_as_uuid",
]
