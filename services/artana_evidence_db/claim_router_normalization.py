"""Normalization helpers for claim router request filters."""

from __future__ import annotations

from typing import Literal

from artana_evidence_db.relation_claim_models import KernelRelationClaim

_CLAIM_STATUSES = frozenset({"OPEN", "NEEDS_MAPPING", "REJECTED", "RESOLVED"})
_CLAIM_VALIDATION_STATES = frozenset(
    {
        "ALLOWED",
        "FORBIDDEN",
        "UNDEFINED",
        "INVALID_COMPONENTS",
        "ENDPOINT_UNRESOLVED",
        "SELF_LOOP",
    },
)
_CLAIM_PERSISTABILITY = frozenset({"PERSISTABLE", "NON_PERSISTABLE"})
_CLAIM_POLARITIES = frozenset({"SUPPORT", "REFUTE", "UNCERTAIN", "HYPOTHESIS"})
_CERTAINTY_BANDS = frozenset({"HIGH", "MEDIUM", "LOW"})
_ClaimStatus = Literal["OPEN", "NEEDS_MAPPING", "REJECTED", "RESOLVED"]
_ClaimValidationState = Literal[
    "ALLOWED",
    "FORBIDDEN",
    "UNDEFINED",
    "INVALID_COMPONENTS",
    "ENDPOINT_UNRESOLVED",
    "SELF_LOOP",
]
_ClaimPersistability = Literal["PERSISTABLE", "NON_PERSISTABLE"]
_ClaimPolarity = Literal["SUPPORT", "REFUTE", "UNCERTAIN", "HYPOTHESIS"]
_CertaintyBand = Literal["HIGH", "MEDIUM", "LOW"]
_CLAIM_VALIDATION_STATE_MAP: dict[str, _ClaimValidationState] = {
    "ALLOWED": "ALLOWED",
    "FORBIDDEN": "FORBIDDEN",
    "UNDEFINED": "UNDEFINED",
    "INVALID_COMPONENTS": "INVALID_COMPONENTS",
    "ENDPOINT_UNRESOLVED": "ENDPOINT_UNRESOLVED",
    "SELF_LOOP": "SELF_LOOP",
}


_ASSERTION_CLASSES = {"SOURCE_BACKED", "CURATED", "COMPUTATIONAL"}


def _normalize_assertion_class(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    if normalized not in _ASSERTION_CLASSES:
        msg = "assertion_class must be one of: SOURCE_BACKED, CURATED, COMPUTATIONAL"
        raise ValueError(msg)
    return normalized


def _normalize_claim_status_filter(status_value: str | None) -> _ClaimStatus | None:
    if status_value is None:
        return None
    normalized = status_value.strip().upper()
    if not normalized:
        return None
    if normalized not in _CLAIM_STATUSES:
        msg = "claim_status must be one of: OPEN, NEEDS_MAPPING, REJECTED, RESOLVED"
        raise ValueError(msg)
    if normalized == "OPEN":
        return "OPEN"
    if normalized == "NEEDS_MAPPING":
        return "NEEDS_MAPPING"
    if normalized == "REJECTED":
        return "REJECTED"
    return "RESOLVED"


def _normalize_claim_validation_state(
    value: str | None,
) -> _ClaimValidationState | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    normalized_state = _CLAIM_VALIDATION_STATE_MAP.get(normalized)
    if normalized_state is None:
        msg = (
            "validation_state must be one of: ALLOWED, FORBIDDEN, UNDEFINED, "
            "INVALID_COMPONENTS, ENDPOINT_UNRESOLVED, SELF_LOOP"
        )
        raise ValueError(msg)
    return normalized_state


def _normalize_claim_persistability(
    value: str | None,
) -> _ClaimPersistability | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    if normalized not in _CLAIM_PERSISTABILITY:
        msg = "persistability must be one of: PERSISTABLE, NON_PERSISTABLE"
        raise ValueError(msg)
    if normalized == "PERSISTABLE":
        return "PERSISTABLE"
    return "NON_PERSISTABLE"


def _normalize_claim_polarity(value: str | None) -> _ClaimPolarity | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    if normalized not in _CLAIM_POLARITIES:
        msg = "polarity must be one of: SUPPORT, REFUTE, UNCERTAIN, HYPOTHESIS"
        raise ValueError(msg)
    if normalized == "SUPPORT":
        return "SUPPORT"
    if normalized == "REFUTE":
        return "REFUTE"
    if normalized == "UNCERTAIN":
        return "UNCERTAIN"
    return "HYPOTHESIS"


def _normalize_certainty_band(value: str | None) -> _CertaintyBand | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    if normalized not in _CERTAINTY_BANDS:
        msg = "certainty_band must be one of: HIGH, MEDIUM, LOW"
        raise ValueError(msg)
    if normalized == "HIGH":
        return "HIGH"
    if normalized == "MEDIUM":
        return "MEDIUM"
    return "LOW"


def _normalize_claim_evidence_sentence_source(
    value: str | None,
) -> Literal["verbatim_span", "artana_generated"] | None:
    if value == "verbatim_span":
        return "verbatim_span"
    if value == "artana_generated":
        return "artana_generated"
    return None


def _normalize_claim_evidence_sentence_confidence(
    value: str | None,
) -> Literal["low", "medium", "high"] | None:
    if value == "low":
        return "low"
    if value == "medium":
        return "medium"
    if value == "high":
        return "high"
    return None


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _resolve_claim_source_ref(
    *,
    request_source_ref: str | None,
    idempotency_key: str | None,
) -> str | None:
    normalized_source_ref = _normalize_optional_text(request_source_ref)
    normalized_idempotency_key = _normalize_optional_text(idempotency_key)
    if normalized_source_ref is not None and normalized_idempotency_key is not None:
        msg = "Provide either source_ref or Idempotency-Key, not both"
        raise ValueError(msg)
    if normalized_source_ref is not None:
        return normalized_source_ref
    if normalized_idempotency_key is not None:
        return f"idempotency-key:{normalized_idempotency_key}"
    return None


def _claim_matches_request(
    claim: KernelRelationClaim,
    *,
    source_entity_id: str,
    target_entity_id: str,
    relation_type: str,
) -> bool:
    metadata = dict(claim.metadata_payload)
    return (
        str(claim.relation_type) == relation_type
        and str(metadata.get("source_entity_id", "")) == source_entity_id
        and str(metadata.get("target_entity_id", "")) == target_entity_id
    )


def _claim_duplicate_matches_request(
    claim: KernelRelationClaim,
    *,
    source_entity_id: str,
    target_entity_id: str,
    relation_type: str,
    polarity: str,
    claim_text: str | None,
    source_document_ref: str | None,
) -> bool:
    return (
        _claim_matches_request(
            claim,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            relation_type=relation_type,
        )
        and str(claim.polarity) == polarity
        and _normalize_optional_text(claim.claim_text) == claim_text
        and _normalize_optional_text(claim.source_document_ref) == source_document_ref
    )


def _claim_conflict_detail(
    *,
    code: str,
    message: str,
    claim_ids: list[str],
) -> dict[str, object]:
    return {
        "code": code,
        "message": message,
        "claim_ids": claim_ids,
    }

__all__ = [
    "_CLAIM_VALIDATION_STATE_MAP",
    "_ClaimPersistability",
    "_claim_conflict_detail",
    "_claim_duplicate_matches_request",
    "_normalize_assertion_class",
    "_normalize_certainty_band",
    "_normalize_claim_evidence_sentence_confidence",
    "_normalize_claim_evidence_sentence_source",
    "_normalize_claim_persistability",
    "_normalize_claim_polarity",
    "_normalize_claim_status_filter",
    "_normalize_claim_validation_state",
    "_normalize_optional_text",
    "_resolve_claim_source_ref",
]
