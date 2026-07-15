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


def _source_family_key(evidence: object) -> str | None:
    """Return one authoritative publication/record family for source counting."""
    snapshot = getattr(evidence, "source_snapshot", None)
    if snapshot is None:
        return None
    source_kind = getattr(snapshot, "source_kind", None)
    authoritative_identifier = getattr(snapshot, "authoritative_identifier", None)
    if not isinstance(source_kind, str) or not isinstance(
        authoritative_identifier,
        str,
    ):
        return None
    normalized_kind = source_kind.strip().casefold()
    normalized_identifier = authoritative_identifier.strip().casefold()
    if not normalized_kind or not normalized_identifier:
        return None
    return f"{normalized_kind}:{normalized_identifier}"


def _claim_source_family_key(_claim: object) -> None:
    """Claims without eligible snapshot evidence never form a source family."""
    return


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
