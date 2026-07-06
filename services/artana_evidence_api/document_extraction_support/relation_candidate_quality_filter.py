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
    "binding_site_shadowed_by_molecular_target",
    "companion_phenotype_shadowed_by_disease",
    "context_relation_shadowed_by_direct_mechanism",
    "dropped_object_modifier",
    "dropped_subject_modifier",
    "missing_relation_arguments",
    "nested_context_object",
    "pathway_effect_shadowed_by_direct_target",
    "process_effect_shadowed_by_pathway_mechanism",
    "cell_context_object",
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
        "phenylketonuria",
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
_BROAD_PROCESS_EFFECT_TOKENS = frozenset(
    {
        "growth",
        "proliferation",
    },
)
_CELL_CONTEXT_TOKENS = frozenset(
    {
        "cell",
        "cells",
        "macrophage",
        "macrophages",
    },
)
_BINDING_SITE_CONTEXT_TOKENS = frozenset(
    {
        "pocket",
        "site",
    },
)
_RESISTANCE_OBJECT_BOUNDARY_AFTER_PATTERN = (
    "after|although|among|and|are|because|before|but|cases|cells|cohort|"
    "despite|did|do|does|during|for|however|in|is|patients|samples|show|"
    "showed|shows|study|that|threshold|through|tumors|tumours|was|were|"
    "whereas|which|while"
)
_BARE_AND_CLAIM_BOUNDARY_PATTERN = (
    r"\band\s+(?="
    r"[A-Z0-9][A-Za-z0-9*.-]*"
    r"(?:\s+[A-Za-z0-9*.-]+){0,5}\s+"
    r"(?:"
    r"activat(?:e|es|ed|ing|ion)|associat(?:e|es|ed|ing|ion)|"
    r"biomarker|confers?|correlat(?:e|es|ed|ing|ion)|"
    r"express(?:es|ed|ing|ion)?|inhibit(?:s|ed|ing)?|is|may|might|"
    r"predic(?:t|ts|ted|ting)|regulat(?:e|es|ed|ing|ion)|"
    r"sensitiz(?:e|es|ed|ing)|target(?:s|ed|ing)?|"
    r"trend(?:ed|s|ing)?|was|were"
    r")\b"
    r")"
)

_UNCERTAIN_RELATION_CUE_RE = re.compile(
    r"\b("
    r"hypothesized|may|might|possible|possibly|putative|speculative|"
    r"suggested|suggestive|suggests|tentative|trend|trended|weakly"
    r")\b",
    re.IGNORECASE,
)
_MOLECULAR_TARGET_TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9.-]{1,}$")
_VARIANT_TOKEN_RE = re.compile(r"^[A-Z][0-9]+[A-Z*]$")


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
    repaired_candidates = tuple(
        _repair_weak_review_candidate(candidate) for candidate in candidates
    )
    for candidate_index, candidate in enumerate(repaired_candidates):
        reason = _quality_filter_reason(candidate)
        if reason is None and _is_context_relation_shadowed(
            candidate=candidate,
            candidates=repaired_candidates,
        ):
            reason = "context_relation_shadowed_by_direct_mechanism"
        if reason is None:
            sibling_decision = _sibling_shadow_decision(
                candidate=candidate,
                candidates=repaired_candidates,
            )
            if sibling_decision.review_only_candidate is not None:
                kept_candidates.append(sibling_decision.review_only_candidate)
                continue
            reason = sibling_decision.reason
        if reason is None and _is_cell_context_object(candidate):
            if _cell_context_shadowed_by_primary_relation(
                candidate=candidate,
                candidates=repaired_candidates,
            ):
                filtered_candidates.append(
                    QualityFilteredRelationCandidate(
                        candidate_index=candidate_index,
                        candidate=candidate,
                        reason="cell_context_object",
                    ),
                )
                continue
            kept_candidates.append(
                _with_review_only_reason(candidate, "cell_context_object"),
            )
            continue
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
        candidates=_merge_duplicate_kept_candidates(kept_candidates),
        filtered_candidates=tuple(filtered_candidates),
    )


def _merge_duplicate_kept_candidates(
    candidates: list[ExtractedRelationCandidate],
) -> tuple[ExtractedRelationCandidate, ...]:
    merged_by_key: dict[tuple[str, str, str, str], ExtractedRelationCandidate] = {}
    ordered_keys: list[tuple[str, str, str, str]] = []
    for candidate in candidates:
        key = (
            candidate.subject_label.casefold(),
            candidate.relation_type,
            candidate.object_label.casefold(),
            candidate.sentence.casefold(),
        )
        existing = merged_by_key.get(key)
        if existing is None:
            merged_by_key[key] = candidate
            ordered_keys.append(key)
            continue
        review_reason_codes = tuple(
            dict.fromkeys(
                (*existing.review_reason_codes, *candidate.review_reason_codes),
            ),
        )
        merged_by_key[key] = replace(
            existing,
            subject_curie=existing.subject_curie or candidate.subject_curie,
            object_curie=existing.object_curie or candidate.object_curie,
            subject_curie_source=(
                existing.subject_curie_source
                if existing.subject_curie is not None
                else candidate.subject_curie_source
            ),
            object_curie_source=(
                existing.object_curie_source
                if existing.object_curie is not None
                else candidate.object_curie_source
            ),
            review_status=(
                "review_only"
                if "review_only"
                in {existing.review_status, candidate.review_status}
                or bool(review_reason_codes)
                else "candidate"
            ),
            review_reason_codes=review_reason_codes,
        )
    return tuple(merged_by_key[key] for key in ordered_keys)


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


def _repair_weak_review_candidate(
    candidate: ExtractedRelationCandidate,
) -> ExtractedRelationCandidate:
    candidate = _repair_trend_response_relation_type(candidate)
    repaired_object = _correlated_resistance_object(candidate)
    if repaired_object is None:
        return candidate
    return replace(
        candidate,
        object_label=repaired_object,
        object_curie=None,
        object_curie_source="none",
    )


def _repair_trend_response_relation_type(
    candidate: ExtractedRelationCandidate,
) -> ExtractedRelationCandidate:
    canonical_relation = canonicalize_extraction_relation_type(candidate.relation_type)
    if canonical_relation != "BIOMARKER_FOR":
        return candidate
    object_label = _normalize_entity_label(candidate.object_label)
    if "response" not in object_label.split():
        return candidate
    claim_scope = _candidate_claim_scope(candidate)
    if claim_scope == "":
        return candidate
    if re.search(r"\btrend(?:ed|s|ing)?\s+with\b", claim_scope) is None:
        return candidate
    return replace(candidate, relation_type="ASSOCIATED_WITH")


def _correlated_resistance_object(
    candidate: ExtractedRelationCandidate,
) -> str | None:
    canonical_relation = canonicalize_extraction_relation_type(candidate.relation_type)
    if canonical_relation != "ASSOCIATED_WITH":
        return None
    object_label = _normalize_entity_label(candidate.object_label)
    if object_label == "" or object_label.startswith("resistance to "):
        return None
    claim_scope = _candidate_claim_scope(candidate)
    if claim_scope == "":
        return None
    object_pattern = _phrase_pattern(object_label)
    if (
        re.search(
            rf"\bresistance\s+to\s+{object_pattern}\b"
            rf"(?=$|\s+(?:{_RESISTANCE_OBJECT_BOUNDARY_AFTER_PATTERN})\b)",
            claim_scope,
        )
        is None
    ):
        return None
    if re.search(r"\bcorrelat(?:e|es|ed|ing|ion)\s+with\b", claim_scope) is None:
        return None
    return f"resistance to {candidate.object_label}"


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
    shadow_actions: tuple[
        tuple[_SiblingShadowAction | None, RelationCandidateQualityFilterReason],
        ...,
    ] = (
        (
            _companion_phenotype_shadow_action(
                candidate=candidate,
                candidates=candidates,
            ),
            "companion_phenotype_shadowed_by_disease",
        ),
        (
            _nested_context_object_shadow_action(
                candidate=candidate,
                candidates=candidates,
            ),
            "nested_context_object",
        ),
        (
            _pathway_effect_shadow_action(
                candidate=candidate,
                candidates=candidates,
            ),
            "pathway_effect_shadowed_by_direct_target",
        ),
        (
            _binding_site_shadow_action(
                candidate=candidate,
                candidates=candidates,
            ),
            "binding_site_shadowed_by_molecular_target",
        ),
        (
            _process_effect_shadow_action(
                candidate=candidate,
                candidates=candidates,
            ),
            "process_effect_shadowed_by_pathway_mechanism",
        ),
    )
    for action, reason in shadow_actions:
        decision = _shadow_decision_from_action(
            action=action,
            candidate=candidate,
            reason=reason,
        )
        if decision is not None:
            return decision
    return _SiblingShadowDecision()


def _shadow_decision_from_action(
    *,
    action: _SiblingShadowAction | None,
    candidate: ExtractedRelationCandidate,
    reason: RelationCandidateQualityFilterReason,
) -> _SiblingShadowDecision | None:
    if action == "filter":
        return _SiblingShadowDecision(reason=reason)
    if action == "review_only":
        return _SiblingShadowDecision(
            review_only_candidate=_with_review_only_reason(candidate, reason),
        )
    return None


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


def _pathway_effect_shadow_action(
    *,
    candidate: ExtractedRelationCandidate,
    candidates: tuple[ExtractedRelationCandidate, ...],
) -> _SiblingShadowAction | None:
    canonical_relation = canonicalize_extraction_relation_type(candidate.relation_type)
    if canonical_relation not in {"INHIBITS", "REGULATES"}:
        return None
    if not _has_broad_pathway_effect_object(candidate.object_label):
        return None
    candidate_subject = _normalize_entity_label(candidate.subject_label)
    candidate_sentence = _normalize_sentence(candidate.sentence)
    shadowed_by_direct_target = any(
        sibling is not candidate
        and canonicalize_extraction_relation_type(sibling.relation_type) == "TARGETS"
        and _normalize_entity_label(sibling.subject_label) == candidate_subject
        and _normalize_sentence(sibling.sentence) == candidate_sentence
        and _sibling_shares_claim_scope(candidate, sibling)
        and _is_specific_molecular_target_object(sibling.object_label)
        and _quality_filter_reason(sibling) is None
        for sibling in candidates
    )
    if not shadowed_by_direct_target:
        return None
    return "filter"


def _binding_site_shadow_action(
    *,
    candidate: ExtractedRelationCandidate,
    candidates: tuple[ExtractedRelationCandidate, ...],
) -> _SiblingShadowAction | None:
    canonical_relation = canonicalize_extraction_relation_type(candidate.relation_type)
    if canonical_relation != "TARGETS":
        return None
    if not _is_binding_site_context_object(candidate):
        return None
    candidate_subject = _normalize_entity_label(candidate.subject_label)
    candidate_object = _normalize_entity_label(candidate.object_label)
    candidate_sentence = _normalize_sentence(candidate.sentence)
    has_surviving_molecular_target_sibling = any(
        sibling is not candidate
        and canonicalize_extraction_relation_type(sibling.relation_type) == "TARGETS"
        and _normalize_entity_label(sibling.subject_label) == candidate_subject
        and _normalize_sentence(sibling.sentence) == candidate_sentence
        and _normalize_entity_label(sibling.object_label) != candidate_object
        and _sibling_shares_claim_scope(candidate, sibling)
        and _is_specific_molecular_target_object(sibling.object_label)
        and not _has_binding_site_context_token(sibling.object_label)
        and _quality_filter_reason(sibling) is None
        for sibling in candidates
    )
    return "filter" if has_surviving_molecular_target_sibling else None


def _is_binding_site_context_object(candidate: ExtractedRelationCandidate) -> bool:
    candidate_object = _normalize_entity_label(candidate.object_label)
    if not _has_binding_site_context_token(candidate_object):
        return False
    object_pattern = _phrase_pattern(candidate_object)
    if object_pattern == "":
        return False
    return (
        re.search(
            rf"\b(?:bind|binds|binding|bound)\b"
            rf".{{0,80}}\b{object_pattern}\b",
            _normalize_entity_label(candidate.sentence),
        )
        is not None
    )


def _has_binding_site_context_token(label: str) -> bool:
    normalized_label = _normalize_entity_label(label)
    return bool(_BINDING_SITE_CONTEXT_TOKENS.intersection(normalized_label.split()))


def _process_effect_shadow_action(
    *,
    candidate: ExtractedRelationCandidate,
    candidates: tuple[ExtractedRelationCandidate, ...],
) -> _SiblingShadowAction | None:
    canonical_relation = canonicalize_extraction_relation_type(candidate.relation_type)
    if canonical_relation not in {"ACTIVATES", "REGULATES"}:
        return None
    if not _has_broad_process_effect_object(candidate.object_label):
        return None
    candidate_subject = _normalize_entity_label(candidate.subject_label)
    candidate_sentence = _normalize_sentence(candidate.sentence)
    shadowed_by_pathway_mechanism = any(
        sibling is not candidate
        and canonicalize_extraction_relation_type(sibling.relation_type)
        in {"ACTIVATES", "INHIBITS", "REGULATES"}
        and _normalize_entity_label(sibling.subject_label) == candidate_subject
        and _normalize_sentence(sibling.sentence) == candidate_sentence
        and _sibling_shares_claim_scope(candidate, sibling)
        and _has_broad_pathway_effect_object(sibling.object_label)
        and _quality_filter_reason(sibling) is None
        for sibling in candidates
    )
    if not shadowed_by_pathway_mechanism:
        return None
    return "filter"


def _is_cell_context_object(candidate: ExtractedRelationCandidate) -> bool:
    canonical_relation = canonicalize_extraction_relation_type(candidate.relation_type)
    if canonical_relation not in {"ACTIVATES", "REGULATES"}:
        return False
    candidate_object = _normalize_entity_label(candidate.object_label)
    if not _CELL_CONTEXT_TOKENS.intersection(candidate_object.split()):
        return False
    subject_pattern = _phrase_pattern(_normalize_entity_label(candidate.subject_label))
    object_pattern = _phrase_pattern(candidate_object)
    if subject_pattern == "" or object_pattern == "":
        return False
    return (
        re.search(
            rf"\b{subject_pattern}\b"
            rf".{{0,80}}\b(?:activation|activity|signaling)\b"
            rf".{{0,80}}\b(?:in|within|among)\s+{object_pattern}\b",
            _normalize_entity_label(candidate.sentence),
        )
        is not None
    )


def _cell_context_shadowed_by_primary_relation(
    *,
    candidate: ExtractedRelationCandidate,
    candidates: tuple[ExtractedRelationCandidate, ...],
) -> bool:
    candidate_sentence = _normalize_sentence(candidate.sentence)
    for sibling in candidates:
        if sibling is candidate:
            continue
        if _normalize_sentence(sibling.sentence) != candidate_sentence:
            continue
        if _quality_filter_reason(sibling) is not None:
            continue
        if not _sibling_shares_claim_scope(candidate, sibling):
            continue
        sibling_relation = canonicalize_extraction_relation_type(sibling.relation_type)
        if sibling_relation not in {"ACTIVATES", "REGULATES"}:
            continue
        if _has_broad_pathway_effect_object(
            sibling.object_label,
        ) or _has_broad_process_effect_object(sibling.object_label):
            return True
    return False


def _has_broad_pathway_effect_object(label: str) -> bool:
    normalized_label = _normalize_entity_label(label)
    return bool(_BROAD_PATHWAY_EFFECT_TOKENS.intersection(normalized_label.split()))


def _has_broad_process_effect_object(label: str) -> bool:
    normalized_label = _normalize_entity_label(label)
    return bool(_BROAD_PROCESS_EFFECT_TOKENS.intersection(normalized_label.split()))


def _is_specific_molecular_target_object(label: str) -> bool:
    if _has_broad_pathway_effect_object(label) or _has_disease_context_token(
        _normalize_entity_label(label),
    ):
        return False
    tokens = re.findall(r"[A-Za-z0-9.*-]+", label)
    return any(
        _MOLECULAR_TARGET_TOKEN_RE.fullmatch(token) is not None
        or _VARIANT_TOKEN_RE.fullmatch(token) is not None
        for token in tokens
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


def _candidate_claim_scope(candidate: ExtractedRelationCandidate) -> str:
    subject = _normalize_entity_label(candidate.subject_label)
    obj = _normalize_entity_label(candidate.object_label)
    if subject == "" or obj == "":
        return ""
    subject_pattern = _phrase_pattern(subject)
    object_pattern = _phrase_pattern(obj)
    clauses = [
        clause
        for clause in _split_candidate_clauses(candidate.sentence)
        if re.search(rf"\b{subject_pattern}\b", clause) is not None
        and re.search(rf"\b{object_pattern}\b", clause) is not None
    ]
    return " ".join(clauses)


def _sibling_shares_claim_scope(
    candidate: ExtractedRelationCandidate,
    sibling: ExtractedRelationCandidate,
) -> bool:
    candidate_scope = _candidate_claim_scope(candidate)
    sibling_scope = _candidate_claim_scope(sibling)
    return (
        candidate_scope != ""
        and sibling_scope != ""
        and candidate_scope == sibling_scope
    )


def _split_candidate_clauses(sentence: str) -> tuple[str, ...]:
    return tuple(
        normalized_clause
        for raw_clause in re.split(
            r"(?:"
            r"[.;:]|"
            r",\s*(?:and|while|whereas|but)\b|"
            r"\b(?:while|whereas|but)\b|"
            rf"{_BARE_AND_CLAIM_BOUNDARY_PATTERN}"
            r")",
            sentence,
            flags=re.IGNORECASE,
        )
        if (normalized_clause := _normalize_entity_label(raw_clause)) != ""
    )


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
        rf"[^.;,]{{0,80}}\b{re.escape(context_subject)}\b"
        rf"\s+(?:{context_cue_pattern})\s+"
        rf"\b{re.escape(context_object)}\b",
    )
    if pattern.search(sentence) is not None:
        return True
    direct_target_context_pattern = re.compile(
        rf"\b{re.escape(direct_subject)}\b"
        rf".{{0,80}}\b(?:{direct_cue_pattern})\b"
        rf"[^.;,]{{0,80}}\b{re.escape(context_subject)}\b"
        rf"[^.;,]{{0,80}}\b(?:{context_cue_pattern})\s+"
        rf"\b{re.escape(context_object)}\b",
    )
    return direct_target_context_pattern.search(sentence) is not None


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
