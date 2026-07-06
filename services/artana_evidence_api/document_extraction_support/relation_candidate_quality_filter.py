"""Evidence/value filtering for agent-extracted relation candidates."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
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
from artana_evidence_api.document_extraction_support.review_policy.review_only_candidate_policy import (
    classify_review_only_candidate,
)

RelationCandidateQualityFilterReason = Literal[
    "companion_phenotype_shadowed_by_disease",
    "context_relation_shadowed_by_direct_mechanism",
    "dropped_object_modifier",
    "dropped_subject_modifier",
    "missing_relation_arguments",
    "nested_context_object",
    "pathway_effect_shadowed_by_direct_target",
    "support_not_entailed",
    "uncertain_relation_claim",
]
_SiblingShadowAction = Literal["filter", "review_only"]
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
_DISEASE_CONTEXT_TOKENS = frozenset(
    {
        "adenocarcinoma",
        "cancer",
        "cancers",
        "carcinoma",
        "disease",
        "hypercholesterolemia",
        "leukemia",
        "lymphoma",
        "melanoma",
        "neoplasm",
        "neoplasms",
        "polyposis",
        "syndrome",
        "tumor",
        "tumors",
    },
)
_PHENOTYPE_CONTEXT_TOKENS = frozenset(
    {
        "dilation",
        "elevated",
        "phenylalanine",
        "regression",
    },
)
_BROAD_PATHWAY_EFFECT_TOKENS = frozenset(
    {
        "pathway",
        "pathways",
        "program",
        "programs",
        "signaling",
    },
)

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


@dataclass(frozen=True, slots=True)
class _SiblingShadowDecision:
    reason: RelationCandidateQualityFilterReason | None = None
    review_only_candidate: ExtractedRelationCandidate | None = None


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
            sibling_decision = _sibling_shadow_decision(
                candidate=candidate,
                candidates=candidates,
            )
            if sibling_decision.review_only_candidate is not None:
                kept_candidates.append(sibling_decision.review_only_candidate)
                continue
            reason = sibling_decision.reason
        if reason is None and _is_pathway_effect_shadowed_by_direct_target(
            candidate=candidate,
            candidates=candidates,
        ):
            reason = "pathway_effect_shadowed_by_direct_target"
        review_only_candidate = _review_only_candidate(candidate)
        if review_only_candidate is not None and reason in {
            None,
            "uncertain_relation_claim",
        }:
            kept_candidates.append(review_only_candidate)
            continue
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


def _review_only_candidate(
    candidate: ExtractedRelationCandidate,
) -> ExtractedRelationCandidate | None:
    if candidate.review_status == "review_only":
        return candidate
    decision = classify_review_only_candidate(
        relation_type=candidate.relation_type,
        support_sentence=candidate.sentence,
        subject_label=candidate.subject_label,
        object_label=candidate.object_label,
    )
    if not decision.review_only:
        return None
    return replace(
        candidate,
        review_status="review_only",
        review_reason_codes=decision.reason_codes,
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
    review_decision = classify_review_only_candidate(
        relation_type=candidate.relation_type,
        support_sentence=candidate.sentence,
        subject_label=candidate.subject_label,
        object_label=candidate.object_label,
    )
    if review_decision.review_only:
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


def _sibling_shadow_decision(
    *,
    candidate: ExtractedRelationCandidate,
    candidates: tuple[ExtractedRelationCandidate, ...],
) -> _SiblingShadowDecision:
    companion_action = _companion_phenotype_shadow_action(
        candidate=candidate,
        candidates=candidates,
    )
    if companion_action == "filter":
        return _SiblingShadowDecision(
            reason="companion_phenotype_shadowed_by_disease",
        )
    if companion_action == "review_only":
        return _SiblingShadowDecision(
            review_only_candidate=_with_review_only_reason(
                candidate,
                "companion_phenotype_shadowed_by_disease",
            ),
        )
    nested_action = _nested_context_object_shadow_action(
        candidate=candidate,
        candidates=candidates,
    )
    if nested_action == "filter":
        return _SiblingShadowDecision(reason="nested_context_object")
    if nested_action == "review_only":
        return _SiblingShadowDecision(
            review_only_candidate=_with_review_only_reason(
                candidate,
                "nested_context_object",
            ),
        )
    return _SiblingShadowDecision()


def _companion_phenotype_shadow_action(
    *,
    candidate: ExtractedRelationCandidate,
    candidates: tuple[ExtractedRelationCandidate, ...],
) -> _SiblingShadowAction | None:
    canonical_relation = canonicalize_extraction_relation_type(candidate.relation_type)
    if canonical_relation != "ASSOCIATED_WITH":
        return None
    candidate_object = _normalize_entity_label(candidate.object_label)
    if _has_disease_context_token(candidate_object):
        return None
    if not _PHENOTYPE_CONTEXT_TOKENS.intersection(candidate_object.split()):
        return None
    candidate_subject = _normalize_entity_label(candidate.subject_label)
    candidate_sentence = _normalize_sentence(candidate.sentence)
    has_companion_shape = _sentence_has_disease_then_companion_phenotype(
        sentence=_normalize_entity_label(candidate.sentence),
        object_label=candidate_object,
    )
    if not has_companion_shape:
        return None
    has_surviving_disease_sibling = any(
        sibling is not candidate
        and canonicalize_extraction_relation_type(sibling.relation_type)
        == "ASSOCIATED_WITH"
        and _normalize_entity_label(sibling.subject_label) == candidate_subject
        and _normalize_sentence(sibling.sentence) == candidate_sentence
        and _has_disease_context_token(_normalize_entity_label(sibling.object_label))
        and _quality_filter_reason(sibling) is None
        for sibling in candidates
    )
    return "filter" if has_surviving_disease_sibling else "review_only"


def _nested_context_object_shadow_action(
    *,
    candidate: ExtractedRelationCandidate,
    candidates: tuple[ExtractedRelationCandidate, ...],
) -> _SiblingShadowAction | None:
    if not _is_nested_context_object(candidate):
        return None
    candidate_subject = _normalize_entity_label(candidate.subject_label)
    candidate_sentence = _normalize_sentence(candidate.sentence)
    has_surviving_response_sibling = any(
        sibling is not candidate
        and canonicalize_extraction_relation_type(sibling.relation_type)
        == "BIOMARKER_FOR"
        and _normalize_entity_label(sibling.subject_label) == candidate_subject
        and _normalize_sentence(sibling.sentence) == candidate_sentence
        and _is_specific_biomarker_response_object(sibling.object_label)
        and _quality_filter_reason(sibling) is None
        for sibling in candidates
    )
    return "filter" if has_surviving_response_sibling else "review_only"


def _is_nested_context_object(candidate: ExtractedRelationCandidate) -> bool:
    canonical_relation = canonicalize_extraction_relation_type(candidate.relation_type)
    if canonical_relation != "BIOMARKER_FOR":
        return False
    normalized_object = _normalize_entity_label(candidate.object_label)
    if not normalized_object:
        return False
    object_pattern = _phrase_pattern(normalized_object)
    sentence = _normalize_entity_label(candidate.sentence)
    return (
        re.search(
            rf"\b(?:response|sensitivity|benefit)\b"
            rf".{{0,120}}\b(?:in|among|for)\s+{object_pattern}\b",
            sentence,
        )
        is not None
    )


def _is_pathway_effect_shadowed_by_direct_target(
    *,
    candidate: ExtractedRelationCandidate,
    candidates: tuple[ExtractedRelationCandidate, ...],
) -> bool:
    canonical_relation = canonicalize_extraction_relation_type(candidate.relation_type)
    if canonical_relation not in {"INHIBITS", "REGULATES"}:
        return False
    candidate_object = _normalize_entity_label(candidate.object_label)
    if not _BROAD_PATHWAY_EFFECT_TOKENS.intersection(candidate_object.split()):
        return False
    if _candidate_relation_cue_present(candidate):
        return False
    candidate_subject = _normalize_entity_label(candidate.subject_label)
    candidate_sentence = _normalize_sentence(candidate.sentence)
    return any(
        sibling is not candidate
        and canonicalize_extraction_relation_type(sibling.relation_type) == "TARGETS"
        and _normalize_entity_label(sibling.subject_label) == candidate_subject
        and _normalize_sentence(sibling.sentence) == candidate_sentence
        for sibling in candidates
    )


def _is_specific_biomarker_response_object(label: str) -> bool:
    return re.search(
        r"\b(response|sensitivity|benefit)\b",
        _normalize_entity_label(label),
    ) is not None


def _candidate_relation_cue_present(candidate: ExtractedRelationCandidate) -> bool:
    canonical_relation = canonicalize_extraction_relation_type(candidate.relation_type)
    if canonical_relation is None:
        return False
    cues = _DIRECT_MECHANISM_CUES_BY_RELATION.get(canonical_relation, ())
    if not cues:
        return False
    cue_pattern = _phrase_alternation(cues)
    object_pattern = _phrase_pattern(_normalize_entity_label(candidate.object_label))
    if object_pattern == "":
        return False
    return (
        re.search(
            rf"\b(?:{cue_pattern})\b.{{0,80}}\b{object_pattern}\b",
            _normalize_sentence(candidate.sentence),
        )
        is not None
    )


def _with_review_only_reason(
    candidate: ExtractedRelationCandidate,
    reason_code: str,
) -> ExtractedRelationCandidate:
    return replace(
        candidate,
        review_status="review_only",
        review_reason_codes=tuple(
            dict.fromkeys((*candidate.review_reason_codes, reason_code)),
        ),
    )


def _has_disease_context_token(normalized_label: str) -> bool:
    return bool(_DISEASE_CONTEXT_TOKENS.intersection(normalized_label.split()))


def _sentence_has_disease_then_companion_phenotype(
    *,
    sentence: str,
    object_label: str,
) -> bool:
    object_pattern = _phrase_pattern(object_label)
    if "elevated" in object_label.split():
        return (
            re.search(
                rf"\bassociated\s+with\b"
                rf".{{1,100}}\band\s+{object_pattern}\b",
                sentence,
            )
            is not None
        )
    disease_pattern = "|".join(
        re.escape(token)
        for token in sorted(_DISEASE_CONTEXT_TOKENS, key=len, reverse=True)
    )
    return (
        re.search(
            rf"\bassociated\s+with\b"
            rf".{{0,100}}\b(?:{disease_pattern})\b"
            rf".{{0,40}}\band\s+{object_pattern}\b",
            sentence,
        )
        is not None
    )


def _phrase_pattern(normalized_label: str) -> str:
    return r"\s+".join(re.escape(token) for token in normalized_label.split())


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
