"""Synonym proposal support for extraction relation policy."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from artana_evidence_db.semantic_ports import DictionaryPort

logger = logging.getLogger(__name__)

_SYNONYM_PROPOSAL_MIN_CONFIDENCE = 0.70
_POLICY_AGENT_CREATED_BY = "agent:extraction_policy_step"

type RelationSynonymProposalStatus = Literal["created", "skipped", "failed"]


@dataclass(frozen=True)
class RelationSynonymProposalResult:
    """Structured outcome for one relation synonym proposal attempt."""

    status: RelationSynonymProposalStatus
    reason: str
    observed_relation_type: str | None = None
    mapped_relation_type: str | None = None
    confidence: float | None = None
    attempted: bool = False


@dataclass(frozen=True)
class _NormalizedRelationSynonymProposal:
    observed_relation_type: str
    mapped_relation_type: str
    confidence: float


def _normalize_relation_synonym_label(value: str) -> str:
    """Normalize observed and canonical relation labels consistently."""
    return "_".join(value.strip().upper().split())


def propose_relation_synonym_from_mapping(
    mapping: object,
    *,
    dictionary: DictionaryPort | None,
) -> RelationSynonymProposalResult:
    """Queue a synonym proposal when a mapping links an observed label
    to an existing canonical relation type.

    Only proposes when the observed and mapped types differ and the
    mapped type already exists in the dictionary.  Synonyms are created
    with ``review_status="PENDING_REVIEW"`` so they go through human
    review before affecting future extraction normalization.
    """
    if dictionary is None:
        return RelationSynonymProposalResult(
            status="skipped",
            reason="dictionary_unavailable",
        )
    normalized = _normalize_mapping(mapping)
    if isinstance(normalized, RelationSynonymProposalResult):
        return normalized
    existing_result = _existing_synonym_result(
        dictionary=dictionary,
        normalized=normalized,
    )
    if existing_result is not None:
        return existing_result
    return _create_relation_synonym_proposal(
        dictionary=dictionary,
        normalized=normalized,
    )


def _normalize_mapping(
    mapping: object,
) -> _NormalizedRelationSynonymProposal | RelationSynonymProposalResult:
    observed = getattr(mapping, "observed_relation_type", None)
    mapped = getattr(mapping, "mapped_relation_type", None)
    confidence = getattr(mapping, "confidence", 0.0)
    if (
        not isinstance(observed, str)
        or not isinstance(mapped, str)
        or not isinstance(confidence, float | int)
    ):
        return RelationSynonymProposalResult(
            status="skipped",
            reason="invalid_mapping",
        )
    confidence_value = float(confidence)
    normalized_observed = _normalize_relation_synonym_label(observed)
    normalized_mapped = _normalize_relation_synonym_label(mapped)
    if not normalized_observed or not normalized_mapped:
        return RelationSynonymProposalResult(
            status="skipped",
            reason="empty_relation_type",
            observed_relation_type=normalized_observed or None,
            mapped_relation_type=normalized_mapped or None,
            confidence=confidence_value,
        )
    if normalized_observed == normalized_mapped:
        return RelationSynonymProposalResult(
            status="skipped",
            reason="same_relation_type",
            observed_relation_type=normalized_observed,
            mapped_relation_type=normalized_mapped,
            confidence=confidence_value,
        )
    if confidence_value < _SYNONYM_PROPOSAL_MIN_CONFIDENCE:
        return RelationSynonymProposalResult(
            status="skipped",
            reason="low_confidence",
            observed_relation_type=normalized_observed,
            mapped_relation_type=normalized_mapped,
            confidence=confidence_value,
        )
    return _NormalizedRelationSynonymProposal(
        observed_relation_type=normalized_observed,
        mapped_relation_type=normalized_mapped,
        confidence=confidence_value,
    )


def _existing_synonym_result(
    *,
    dictionary: DictionaryPort,
    normalized: _NormalizedRelationSynonymProposal,
) -> RelationSynonymProposalResult | None:
    existing = dictionary.resolve_relation_synonym(
        normalized.observed_relation_type,
        include_inactive=True,
    )
    if existing is not None:
        existing_relation_type = getattr(existing, "id", None)
        if existing_relation_type == normalized.mapped_relation_type:
            logger.info(
                "Relation synonym proposal skipped: %s already maps to %s",
                normalized.observed_relation_type,
                normalized.mapped_relation_type,
            )
            return RelationSynonymProposalResult(
                status="skipped",
                reason="already_exists",
                observed_relation_type=normalized.observed_relation_type,
                mapped_relation_type=normalized.mapped_relation_type,
                confidence=normalized.confidence,
            )
        logger.warning(
            "Relation synonym proposal failed: %s already maps to %s, not %s",
            normalized.observed_relation_type,
            existing_relation_type,
            normalized.mapped_relation_type,
        )
        return RelationSynonymProposalResult(
            status="failed",
            reason="synonym_conflict",
            observed_relation_type=normalized.observed_relation_type,
            mapped_relation_type=normalized.mapped_relation_type,
            confidence=normalized.confidence,
        )
    return None


def _create_relation_synonym_proposal(
    *,
    dictionary: DictionaryPort,
    normalized: _NormalizedRelationSynonymProposal,
) -> RelationSynonymProposalResult:
    try:
        dictionary.create_relation_synonym(
            relation_type_id=normalized.mapped_relation_type,
            synonym=normalized.observed_relation_type,
            source=_POLICY_AGENT_CREATED_BY,
            created_by=_POLICY_AGENT_CREATED_BY,
            research_space_settings={
                "dictionary_agent_creation_policy": "PENDING_REVIEW",
            },
        )
        logger.info(
            "Proposed relation synonym: %s -> %s (confidence=%.2f)",
            normalized.observed_relation_type,
            normalized.mapped_relation_type,
            normalized.confidence,
        )
        return RelationSynonymProposalResult(
            status="created",
            reason="created",
            observed_relation_type=normalized.observed_relation_type,
            mapped_relation_type=normalized.mapped_relation_type,
            confidence=normalized.confidence,
            attempted=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Relation synonym proposal failed for %s -> %s: %s",
            normalized.observed_relation_type,
            normalized.mapped_relation_type,
            exc,
            exc_info=True,
        )
        return RelationSynonymProposalResult(
            status="failed",
            reason="create_failed",
            observed_relation_type=normalized.observed_relation_type,
            mapped_relation_type=normalized.mapped_relation_type,
            confidence=normalized.confidence,
            attempted=True,
        )


__all__ = [
    "RelationSynonymProposalResult",
    "RelationSynonymProposalStatus",
    "propose_relation_synonym_from_mapping",
]
