"""Evidence/value filtering for agent-extracted relation candidates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from artana_evidence_api.document_extraction_contracts import (
    ExtractedRelationCandidate,
)
from artana_evidence_api.document_extraction_relation_taxonomy import (
    canonicalize_extraction_relation_type,
)
from artana_evidence_api.document_extraction_support.evidence_grounding import (
    ground_relation_sentence,
)
from artana_evidence_api.document_extraction_support.evidence_support_verifier import (
    verify_triple_support,
)
from artana_evidence_api.document_extraction_support.relation_specificity_pruning import (
    has_broadened_entity_label,
)

RelationCandidateQualityFilterReason = Literal[
    "context_relation_shadowed_by_direct_mechanism",
    "dropped_object_modifier",
    "dropped_subject_modifier",
    "missing_relation_arguments",
    "support_not_entailed",
    "uncertain_relation_claim",
]
_CONTEXT_RELATION_TYPES = frozenset({"DOWNSTREAM_OF", "UPSTREAM_OF"})
_DIRECT_MECHANISM_RELATION_TYPES = frozenset(
    {
        "ACTIVATES",
        "CONFERS_RESISTANCE_TO",
        "INHIBITS",
        "REGULATES",
        "SENSITIZES_TO",
        "TARGETS",
    },
)
_DIRECT_MECHANISM_CUES_BY_RELATION = {
    "ACTIVATES": ("activate", "activates", "activated", "activation"),
    "CONFERS_RESISTANCE_TO": (
        "confers resistance to",
        "causes resistance to",
        "renders resistant to",
    ),
    "INHIBITS": ("inhibits", "inhibit", "inhibited", "suppresses", "suppressed"),
    "REGULATES": ("regulates", "regulated", "regulation"),
    "SENSITIZES_TO": ("sensitizes", "sensitizes to", "sensitive to"),
    "TARGETS": ("targets", "targeted", "binds"),
}
_CONTEXT_CUES_BY_RELATION = {
    "DOWNSTREAM_OF": ("downstream of", "downstream"),
    "UPSTREAM_OF": ("upstream of", "upstream"),
}

_UNCERTAIN_RELATION_CUE_RE = re.compile(
    r"\b("
    r"hypothesized|may|might|possible|possibly|putative|speculative|"
    r"suggested|suggestive|suggests|tentative|trend|trended|weakly"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class QualityFilteredRelationCandidate:
    """One candidate removed by evidence/value filtering."""

    candidate_index: int
    candidate: ExtractedRelationCandidate
    reason: RelationCandidateQualityFilterReason


@dataclass(frozen=True, slots=True)
class RelationCandidateQualityFilterResult:
    """Candidate list plus evidence/value filtering telemetry."""

    candidates: tuple[ExtractedRelationCandidate, ...]
    filtered_candidates: tuple[QualityFilteredRelationCandidate, ...]

    @property
    def filtered_count(self) -> int:
        """Return the number of candidates removed by quality filtering."""

        return len(self.filtered_candidates)


def filter_low_value_relation_candidates(
    candidates: tuple[ExtractedRelationCandidate, ...],
) -> RelationCandidateQualityFilterResult:
    """Remove agent candidates that fail evidence/value floors."""

    kept_candidates: list[ExtractedRelationCandidate] = []
    filtered_candidates: list[QualityFilteredRelationCandidate] = []
    for candidate_index, candidate in enumerate(candidates):
        reason = _quality_filter_reason(candidate)
        if reason is None and _is_context_relation_shadowed(
            candidate=candidate,
            candidates=candidates,
        ):
            reason = "context_relation_shadowed_by_direct_mechanism"
        if reason is None:
            kept_candidates.append(candidate)
            continue
        filtered_candidates.append(
            QualityFilteredRelationCandidate(
                candidate_index=candidate_index,
                candidate=candidate,
                reason=reason,
            ),
        )
    return RelationCandidateQualityFilterResult(
        candidates=tuple(kept_candidates),
        filtered_candidates=tuple(filtered_candidates),
    )


def _quality_filter_reason(
    candidate: ExtractedRelationCandidate,
) -> RelationCandidateQualityFilterReason | None:
    reason: RelationCandidateQualityFilterReason | None = None
    if candidate.relation_governance_status != "canonical":
        return reason
    if canonicalize_extraction_relation_type(candidate.relation_type) is not None:
        reason = _dropped_modifier_reason(candidate)
        if reason is None:
            reason = _single_candidate_support_reason(candidate)
    return reason


def _single_candidate_support_reason(
    candidate: ExtractedRelationCandidate,
) -> RelationCandidateQualityFilterReason | None:
    if _UNCERTAIN_RELATION_CUE_RE.search(candidate.sentence) is not None:
        return "uncertain_relation_claim"
    grounding = ground_relation_sentence(
        source_text=candidate.sentence,
        sentence=candidate.sentence,
        subject=candidate.subject_label,
        object_=candidate.object_label,
    )
    if not (grounding.subject_present and grounding.object_present):
        return "missing_relation_arguments"
    support = verify_triple_support(
        sentence=candidate.sentence,
        subject=candidate.subject_label,
        relation_type=candidate.relation_type,
        object_=candidate.object_label,
    )
    if support.support != "ENTAILS":
        return "support_not_entailed"
    return None


def _dropped_modifier_reason(
    candidate: ExtractedRelationCandidate,
) -> RelationCandidateQualityFilterReason | None:
    if has_broadened_entity_label(
        label=candidate.subject_label,
        sentence=candidate.sentence,
        counterpart_label=candidate.object_label,
    ):
        return "dropped_subject_modifier"
    if has_broadened_entity_label(
        label=candidate.object_label,
        sentence=candidate.sentence,
        counterpart_label=candidate.subject_label,
    ):
        return "dropped_object_modifier"
    return None


def _is_context_relation_shadowed(
    *,
    candidate: ExtractedRelationCandidate,
    candidates: tuple[ExtractedRelationCandidate, ...],
) -> bool:
    canonical_relation = canonicalize_extraction_relation_type(candidate.relation_type)
    if canonical_relation not in _CONTEXT_RELATION_TYPES:
        return False
    candidate_subject = _normalize_entity_label(candidate.subject_label)
    candidate_sentence = _normalize_sentence(candidate.sentence)
    for sibling in candidates:
        if sibling is candidate:
            continue
        sibling_relation = canonicalize_extraction_relation_type(sibling.relation_type)
        if sibling_relation not in _DIRECT_MECHANISM_RELATION_TYPES:
            continue
        if _quality_filter_reason(sibling) is not None:
            continue
        if _normalize_sentence(sibling.sentence) != candidate_sentence:
            continue
        if _normalize_entity_label(sibling.object_label) == candidate_subject:
            return _context_edge_is_direct_mechanism_modifier(
                context_candidate=candidate,
                direct_candidate=sibling,
                direct_relation=sibling_relation,
            )
    return False


def _context_edge_is_direct_mechanism_modifier(
    *,
    context_candidate: ExtractedRelationCandidate,
    direct_candidate: ExtractedRelationCandidate,
    direct_relation: str,
) -> bool:
    context_relation = canonicalize_extraction_relation_type(
        context_candidate.relation_type,
    )
    if context_relation is None:
        return False
    direct_cues = _DIRECT_MECHANISM_CUES_BY_RELATION.get(direct_relation, ())
    context_cues = _CONTEXT_CUES_BY_RELATION.get(context_relation, ())
    if not direct_cues or not context_cues:
        return False
    sentence = _normalize_sentence(context_candidate.sentence)
    direct_subject = _normalize_entity_label(direct_candidate.subject_label)
    context_subject = _normalize_entity_label(context_candidate.subject_label)
    context_object = _normalize_entity_label(context_candidate.object_label)
    direct_cue_pattern = _phrase_alternation(direct_cues)
    context_cue_pattern = _phrase_alternation(context_cues)
    pattern = re.compile(
        rf"\b{re.escape(direct_subject)}\b"
        rf".{{0,80}}\b(?:{direct_cue_pattern})\b"
        rf".{{0,80}}\b{re.escape(context_subject)}\b"
        rf"\s+(?:{context_cue_pattern})\s+"
        rf"\b{re.escape(context_object)}\b",
    )
    return pattern.search(sentence) is not None


def _phrase_alternation(phrases: tuple[str, ...]) -> str:
    return "|".join(
        r"\s+".join(re.escape(token) for token in phrase.split())
        for phrase in sorted(phrases, key=len, reverse=True)
    )


def _normalize_entity_label(value: str) -> str:
    return re.sub(r"[^a-z0-9*]+", " ", value.casefold()).strip()


def _normalize_sentence(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


__all__ = [
    "QualityFilteredRelationCandidate",
    "RelationCandidateQualityFilterResult",
    "filter_low_value_relation_candidates",
]
