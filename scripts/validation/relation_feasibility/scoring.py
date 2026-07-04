"""Scoring rules for relation feasibility audits."""

from __future__ import annotations

import re
from dataclasses import dataclass

from artana_evidence_api.document_extraction_relation_taxonomy import (
    LLM_PROPOSE_NEW_RELATION_TYPE,
    LLM_VALID_RELATION_TYPES,
)
from artana_evidence_api.document_extraction_support.evidence_grounding import (
    ground_relation_sentence,
)
from artana_evidence_api.document_extraction_support.evidence_support_verifier import (
    TripleSupport,
    verify_triple_support,
)

from scripts.validation.relation_feasibility.models import (
    BenchmarkCase,
    CandidateAssessment,
    ExtractedRelation,
    ExtractionTrace,
    FeasibilitySummary,
    GoldRelation,
    RelationTypeSurface,
    Verdict,
)

_GENERIC_RELATION_TYPES = frozenset({"ASSOCIATED_WITH"})
_GENERIC_ENTITY_LABELS = frozenset(
    {
        "clinical feature",
        "clinical features",
        "condition",
        "conditions",
        "disease",
        "diseases",
        "finding",
        "findings",
        "feature",
        "features",
        "mechanism",
        "mechanisms",
        "phenotype",
        "phenotypes",
        "process",
        "processes",
        "response",
        "responses",
        "trait",
        "traits",
    },
)
_RELATION_SYNONYMS = {
    "LINKED_TO": "ASSOCIATED_WITH",
    "LINKS_TO": "ASSOCIATED_WITH",
    "CORRELATED_WITH": "ASSOCIATED_WITH",
    "INTERACTS_WITH": "PHYSICALLY_INTERACTS_WITH",
    "BINDS_TO": "PHYSICALLY_INTERACTS_WITH",
    "UPREGULATES": "ACTIVATES",
    "DOWNREGULATES": "INHIBITS",
}
_MAX_SPECIFIC_ENTITY_TOKENS = 6
_RED_MIN_PRECISION = 0.5
_RED_MIN_VALUABLE_RATE = 0.35
_RED_MAX_GENERIC_RELATION_RATE = 0.5
_YELLOW_MIN_PRECISION = 0.8
_YELLOW_MIN_RECALL = 0.6
_YELLOW_MIN_VALUABLE_RATE = 0.7
_YELLOW_MAX_GENERIC_RELATION_RATE = 0.25
_MIN_CURIE_LINKED_GOLD_ENDPOINT_RATE = 0.95
_HIGH_VALUE_LEVELS = frozenset({"high", "medium"})
_LOW_VALUE_LEVELS = frozenset({"low", "reject"})


@dataclass(frozen=True, slots=True)
class _QualityContext:
    supported: bool
    subject_specific: bool
    object_specific: bool
    relation_specific: bool
    grounded_sentence: bool
    subject_in_sentence: bool
    object_in_sentence: bool
    both_arguments_in_sentence: bool
    gold_support_sentence: bool
    known_relation_type: bool
    governed_relation_proposal: bool
    proposal_supported: bool
    requires_entailment: bool
    has_support_verification: bool
    has_entailment_support: bool
    has_subject_curie: bool
    has_object_curie: bool
    has_verified_subject_curie: bool
    has_verified_object_curie: bool
    subject_curie_matches_gold: bool
    object_curie_matches_gold: bool
    matched_gold: GoldRelation | None


@dataclass(frozen=True, slots=True)
class SummaryInputs:
    """Aggregate inputs needed to build a feasibility summary."""

    case_assessments: tuple[tuple[CandidateAssessment, ...], ...]
    extraction_traces: tuple[ExtractionTrace, ...]
    case_gold_relations: tuple[tuple[GoldRelation, ...], ...]
    case_gold_relation_counts: tuple[int, ...]
    case_missed_gold_counts: tuple[int, ...]
    case_categories: tuple[str, ...]
    relation_type_surfaces: tuple[tuple[RelationTypeSurface, ...], ...]
    case_count: int
    gold_relation_count: int
    missed_gold_count: int
    require_agent_completion: bool


@dataclass(frozen=True, slots=True)
class _VerdictContext:
    case_count: int
    precision: float
    recall: float
    trusted_recall: float
    valuable_rate: float
    generic_relation_rate: float
    raw_unknown_relation_type_count: int
    raw_unknown_relation_type_surface_count: int
    gold_curie_endpoint_count: int
    curie_linked_gold_endpoint_rate: float
    negative_control_leakage_count: int
    invalid_agent_case_count: int
    require_agent_completion: bool


def assess_case(
    case: BenchmarkCase,
    candidates: tuple[ExtractedRelation, ...],
) -> tuple[tuple[CandidateAssessment, ...], tuple[int, ...]]:
    """Assess extracted candidates for one benchmark case."""

    matched_gold_indices: set[int] = set()
    assessments: list[CandidateAssessment] = []
    for candidate in candidates:
        matched_index = _matched_gold_index(
            candidate=candidate,
            gold_relations=case.gold_relations,
        )
        if matched_index is not None:
            matched_gold_indices.add(matched_index)
        assessments.append(
            _assess_candidate(
                case=case,
                candidate=candidate,
                matched_gold_index=matched_index,
            ),
        )
    missed_gold_indices = tuple(
        index
        for index in range(len(case.gold_relations))
        if index not in matched_gold_indices
    )
    return tuple(assessments), missed_gold_indices


def build_summary(inputs: SummaryInputs) -> FeasibilitySummary:
    """Build aggregate feasibility metrics."""

    candidates = tuple(
        assessment
        for assessments in inputs.case_assessments
        for assessment in assessments
    )
    candidate_count = len(candidates)
    supported_candidate_count = sum(
        1 for assessment in candidates if assessment.is_supported_by_gold
    )
    valuable_candidate_count = sum(
        1 for assessment in candidates if assessment.is_valuable
    )
    generic_relation_count = sum(
        1 for assessment in candidates if not assessment.is_relation_specific
    )
    pruned_generic_relation_count = sum(
        trace.pruned_generic_relation_count for trace in inputs.extraction_traces
    )
    raw_unknown_relation_type_count = sum(
        1 for assessment in candidates if not assessment.has_known_relation_type
    )
    relation_type_surfaces = tuple(
        surface
        for surfaces in inputs.relation_type_surfaces
        for surface in surfaces
    )
    relation_type_surface_count = len(relation_type_surfaces)
    raw_unknown_relation_type_surface_count = sum(
        1
        for surface in relation_type_surfaces
        if not _is_known_relation_type(surface.relation_type)
    )
    proposal_candidate_count = sum(
        1 for assessment in candidates if assessment.is_governed_relation_proposal
    )
    proposal_gold_match_count = len(
        {
            (case_index, assessment.proposal_matched_gold_index)
            for case_index, assessments in enumerate(inputs.case_assessments)
            for assessment in assessments
            if assessment.proposal_matched_gold_index is not None
        },
    )
    proposal_eligible_gold_count = sum(
        1
        for gold_relations in inputs.case_gold_relations
        for gold_relation in gold_relations
        if not _is_known_relation_type(gold_relation.relation_type)
    )
    gold_curie_endpoint_count = sum(
        1
        for gold_relations in inputs.case_gold_relations
        for gold_relation in gold_relations
        for curie in (gold_relation.subject_curie, gold_relation.object_curie)
        if curie is not None
    )
    candidate_curie_endpoint_count = sum(
        int(assessment.has_subject_curie) + int(assessment.has_object_curie)
        for assessment in candidates
    )
    candidate_curie_present_rate = _ratio(
        candidate_curie_endpoint_count,
        candidate_count * 2,
    )
    curie_linked_gold_endpoints = {
        (case_index, assessment.matched_gold_index, "subject")
        for case_index, assessments in enumerate(inputs.case_assessments)
        for assessment in assessments
        if assessment.matched_gold_index is not None
        and assessment.subject_curie_matches_gold
    } | {
        (case_index, assessment.matched_gold_index, "object")
        for case_index, assessments in enumerate(inputs.case_assessments)
        for assessment in assessments
        if assessment.matched_gold_index is not None
        and assessment.object_curie_matches_gold
    }
    curie_linked_gold_endpoint_count = len(curie_linked_gold_endpoints)
    verified_curie_match_count = curie_linked_gold_endpoint_count
    curie_linked_gold_endpoint_rate = _ratio(
        curie_linked_gold_endpoint_count,
        gold_curie_endpoint_count,
    )
    model_curie_wrong_count = _model_curie_wrong_count(
        inputs.case_assessments,
        inputs.case_gold_relations,
    )
    specific_entity_count = sum(
        1
        for assessment in candidates
        if assessment.has_specific_subject and assessment.has_specific_object
    )
    relation_specific_count = sum(
        1 for assessment in candidates if assessment.is_relation_specific
    )
    grounded_sentence_count = sum(
        1 for assessment in candidates if assessment.has_grounded_sentence
    )
    both_arguments_present_count = sum(
        1 for assessment in candidates if assessment.has_both_arguments_in_sentence
    )
    support_sentence_aligned_count = sum(
        1 for assessment in candidates if assessment.has_gold_support_sentence
    )
    entailment_required_count = sum(
        1 for assessment in candidates if assessment.requires_entailment
    )
    entailment_checked_count = sum(
        1 for assessment in candidates if assessment.has_support_verification
    )
    entailment_supported_count = sum(
        1
        for assessment in candidates
        if assessment.requires_entailment and assessment.has_entailment_support
    )
    precision = _ratio(supported_candidate_count, candidate_count)
    recall = _ratio(
        inputs.gold_relation_count - inputs.missed_gold_count,
        inputs.gold_relation_count,
    )
    high_value_gold_relation_count = sum(
        1
        for gold_relations in inputs.case_gold_relations
        for gold_relation in gold_relations
        if gold_relation.value_level in _HIGH_VALUE_LEVELS
    )
    missed_gold_relations = tuple(
        gold_relations[index]
        for gold_relations, assessments in zip(
            inputs.case_gold_relations,
            inputs.case_assessments,
            strict=True,
        )
        for index in _missed_gold_indices(
            gold_relations=gold_relations,
            assessments=assessments,
        )
    )
    high_value_missed_gold_count = sum(
        1
        for gold_relation in missed_gold_relations
        if gold_relation.value_level in _HIGH_VALUE_LEVELS
    )
    low_value_gold_relation_count = sum(
        1
        for gold_relations in inputs.case_gold_relations
        for gold_relation in gold_relations
        if gold_relation.value_level in _LOW_VALUE_LEVELS
    )
    low_value_missed_gold_count = sum(
        1
        for gold_relation in missed_gold_relations
        if gold_relation.value_level in _LOW_VALUE_LEVELS
    )
    high_value_recall = _ratio(
        high_value_gold_relation_count - high_value_missed_gold_count,
        high_value_gold_relation_count,
    )
    low_value_recall = _ratio(
        low_value_gold_relation_count - low_value_missed_gold_count,
        low_value_gold_relation_count,
    )
    valuable_rate = _ratio(valuable_candidate_count, candidate_count)
    generic_relation_rate = _ratio(generic_relation_count, candidate_count)
    case_agent_completed_flags = tuple(
        _case_agent_completed(trace, len(assessments))
        for assessments, trace in zip(
            inputs.case_assessments,
            inputs.extraction_traces,
            strict=True,
        )
    )
    agent_completed_case_count = sum(1 for completed in case_agent_completed_flags if completed)
    agent_zero_candidate_case_count = sum(
        1
        for completed, trace in zip(
            case_agent_completed_flags,
            inputs.extraction_traces,
            strict=True,
        )
        if completed and trace.llm_candidate_status == "llm_empty"
    )
    negative_control_case_count = sum(
        1 for category in inputs.case_categories if category == "negative_control"
    )
    negative_control_empty_count = sum(
        1
        for category, completed, assessments in zip(
            inputs.case_categories,
            case_agent_completed_flags,
            inputs.case_assessments,
            strict=True,
        )
        if category == "negative_control" and completed and len(assessments) == 0
    )
    negative_control_leakage_count = sum(
        1
        for category, assessments in zip(
            inputs.case_categories,
            inputs.case_assessments,
            strict=True,
        )
        if category == "negative_control" and len(assessments) > 0
    )
    fallback_case_count = sum(
        1 for trace in inputs.extraction_traces if trace.fallback_used
    )
    fallback_candidate_count = sum(
        trace.fallback_candidate_count for trace in inputs.extraction_traces
    )
    completed_agent_assessments = tuple(
        assessment
        for assessments, trace in zip(
            inputs.case_assessments,
            inputs.extraction_traces,
            strict=True,
        )
        if _case_agent_completed(trace, len(assessments))
        for assessment in assessments
    )
    completed_agent_candidate_count = len(completed_agent_assessments)
    completed_agent_supported_candidate_count = sum(
        1
        for assessment in completed_agent_assessments
        if assessment.is_supported_by_gold
    )
    completed_agent_valuable_candidate_count = sum(
        1 for assessment in completed_agent_assessments if assessment.is_valuable
    )
    completed_agent_gold_relation_count = sum(
        gold_count
        for gold_count, trace, assessments in zip(
            inputs.case_gold_relation_counts,
            inputs.extraction_traces,
            inputs.case_assessments,
            strict=True,
        )
        if _case_agent_completed(trace, len(assessments))
    )
    completed_agent_missed_gold_count = sum(
        missed_count
        for missed_count, trace, assessments in zip(
            inputs.case_missed_gold_counts,
            inputs.extraction_traces,
            inputs.case_assessments,
            strict=True,
        )
        if _case_agent_completed(trace, len(assessments))
    )
    fallback_credited_as_agent_count = sum(
        1
        for assessments, trace in zip(
            inputs.case_assessments,
            inputs.extraction_traces,
            strict=True,
        )
        if trace.fallback_used
        for assessment in assessments
        if assessment.is_valuable
    )
    invalid_agent_case_count = (
        sum(1 for completed in case_agent_completed_flags if not completed)
        if inputs.require_agent_completion
        else 0
    )
    verdict, reason, blocking_reasons, warning_reasons = _verdict(
        _VerdictContext(
            case_count=inputs.case_count,
            precision=precision,
            recall=recall,
            trusted_recall=(
                high_value_recall
                if high_value_gold_relation_count > 0
                else recall
            ),
            valuable_rate=valuable_rate,
            generic_relation_rate=generic_relation_rate,
            raw_unknown_relation_type_count=raw_unknown_relation_type_count,
            raw_unknown_relation_type_surface_count=(
                raw_unknown_relation_type_surface_count
            ),
            gold_curie_endpoint_count=gold_curie_endpoint_count,
            curie_linked_gold_endpoint_rate=curie_linked_gold_endpoint_rate,
            negative_control_leakage_count=negative_control_leakage_count,
            invalid_agent_case_count=invalid_agent_case_count,
            require_agent_completion=inputs.require_agent_completion,
        ),
    )
    return FeasibilitySummary(
        case_count=inputs.case_count,
        gold_relation_count=inputs.gold_relation_count,
        candidate_count=candidate_count,
        supported_candidate_count=supported_candidate_count,
        valuable_candidate_count=valuable_candidate_count,
        generic_relation_count=generic_relation_count,
        pruned_generic_relation_count=pruned_generic_relation_count,
        raw_unknown_relation_type_count=raw_unknown_relation_type_count,
        relation_type_surface_count=relation_type_surface_count,
        raw_unknown_relation_type_surface_count=(
            raw_unknown_relation_type_surface_count
        ),
        proposal_candidate_count=proposal_candidate_count,
        proposal_gold_match_count=proposal_gold_match_count,
        proposal_eligible_gold_count=proposal_eligible_gold_count,
        gold_curie_endpoint_count=gold_curie_endpoint_count,
        candidate_curie_endpoint_count=candidate_curie_endpoint_count,
        curie_linked_gold_endpoint_count=curie_linked_gold_endpoint_count,
        verified_curie_match_count=verified_curie_match_count,
        model_curie_wrong_count=model_curie_wrong_count,
        support_sentence_aligned_count=support_sentence_aligned_count,
        both_arguments_present_count=both_arguments_present_count,
        entailment_required_count=entailment_required_count,
        entailment_checked_count=entailment_checked_count,
        entailment_supported_count=entailment_supported_count,
        agent_completed_case_count=agent_completed_case_count,
        agent_zero_candidate_case_count=agent_zero_candidate_case_count,
        fallback_case_count=fallback_case_count,
        fallback_candidate_count=fallback_candidate_count,
        fallback_credited_as_agent_count=fallback_credited_as_agent_count,
        completed_agent_candidate_count=completed_agent_candidate_count,
        completed_agent_supported_candidate_count=completed_agent_supported_candidate_count,
        completed_agent_valuable_candidate_count=completed_agent_valuable_candidate_count,
        completed_agent_gold_relation_count=completed_agent_gold_relation_count,
        completed_agent_missed_gold_count=completed_agent_missed_gold_count,
        invalid_agent_case_count=invalid_agent_case_count,
        high_value_gold_relation_count=high_value_gold_relation_count,
        high_value_missed_gold_count=high_value_missed_gold_count,
        low_value_gold_relation_count=low_value_gold_relation_count,
        low_value_missed_gold_count=low_value_missed_gold_count,
        negative_control_case_count=negative_control_case_count,
        negative_control_empty_count=negative_control_empty_count,
        negative_control_leakage_count=negative_control_leakage_count,
        missed_gold_count=inputs.missed_gold_count,
        precision_against_gold=precision,
        recall_against_gold=recall,
        high_value_recall=high_value_recall,
        low_value_recall=low_value_recall,
        completed_agent_precision_against_gold=_ratio(
            completed_agent_supported_candidate_count,
            completed_agent_candidate_count,
        ),
        completed_agent_recall_against_gold=_ratio(
            completed_agent_gold_relation_count - completed_agent_missed_gold_count,
            completed_agent_gold_relation_count,
        ),
        specificity_rate=_ratio(specific_entity_count, candidate_count),
        relation_specificity_rate=_ratio(relation_specific_count, candidate_count),
        generic_relation_rate=generic_relation_rate,
        raw_unknown_relation_type_rate=_ratio(
            raw_unknown_relation_type_count,
            candidate_count,
        ),
        raw_unknown_relation_type_surface_rate=_ratio(
            raw_unknown_relation_type_surface_count,
            relation_type_surface_count,
        ),
        proposal_recall_against_gold=_ratio(
            proposal_gold_match_count,
            inputs.gold_relation_count,
        ),
        proposal_recall_against_proposal_eligible_gold=_ratio(
            proposal_gold_match_count,
            proposal_eligible_gold_count,
        ),
        candidate_curie_present_rate=candidate_curie_present_rate,
        verified_curie_match_rate=curie_linked_gold_endpoint_rate,
        curie_linked_gold_endpoint_rate=curie_linked_gold_endpoint_rate,
        valuable_candidate_rate=valuable_rate,
        completed_agent_valuable_candidate_rate=_ratio(
            completed_agent_valuable_candidate_count,
            completed_agent_candidate_count,
        ),
        grounded_sentence_rate=_ratio(grounded_sentence_count, candidate_count),
        both_arguments_present_rate=_ratio(
            both_arguments_present_count,
            candidate_count,
        ),
        support_sentence_alignment_rate=_ratio(
            support_sentence_aligned_count,
            candidate_count,
        ),
        entailment_checked_rate=_ratio(
            entailment_checked_count,
            entailment_required_count,
        ),
        entailment_supported_rate=_ratio(
            entailment_supported_count,
            entailment_required_count,
        ),
        verdict=verdict,
        verdict_reason=reason,
        negative_control_empty_rate=_ratio(
            negative_control_empty_count,
            negative_control_case_count,
        ),
        blocking_reasons=blocking_reasons,
        warning_reasons=warning_reasons,
    )


def normalized_relation_key(relation: ExtractedRelation | GoldRelation) -> tuple[str, str, str]:
    """Return the normalized triple key used for support matching."""

    return (
        _normalize_entity(relation.subject),
        _normalize_relation_type(relation.relation_type),
        _normalize_entity(relation.object),
    )


def _missed_gold_indices(
    *,
    gold_relations: tuple[GoldRelation, ...],
    assessments: tuple[CandidateAssessment, ...],
) -> tuple[int, ...]:
    matched_indices = {
        assessment.matched_gold_index
        for assessment in assessments
        if assessment.matched_gold_index is not None
    }
    return tuple(
        index
        for index in range(len(gold_relations))
        if index not in matched_indices
    )


def _assess_candidate(
    *,
    case: BenchmarkCase,
    candidate: ExtractedRelation,
    matched_gold_index: int | None,
) -> CandidateAssessment:
    matched_gold = (
        case.gold_relations[matched_gold_index]
        if matched_gold_index is not None
        else None
    )
    proposal_matched_gold_index = _proposal_matched_gold_index(
        candidate=candidate,
        gold_relations=case.gold_relations,
    )
    governed_relation_proposal = _is_governed_relation_proposal(candidate)
    supported = matched_gold is not None
    subject_specific = _is_specific_entity_label(candidate.subject)
    object_specific = _is_specific_entity_label(candidate.object)
    relation_specific = _is_specific_relation(candidate.relation_type)
    known_relation_type = _is_known_relation_type(candidate.relation_type)
    grounding = ground_relation_sentence(
        source_text=case.text,
        sentence=candidate.sentence,
        subject=candidate.subject,
        object_=candidate.object,
    )
    grounded_sentence = grounding.anchor.match_kind != "none"
    both_arguments_in_sentence = (
        grounding.subject_present and grounding.object_present
    )
    gold_support_sentence = (
        matched_gold is not None
        and _has_matching_support_sentence(
            candidate_sentence=candidate.sentence,
            gold_sentence=matched_gold.support_sentence,
        )
    )
    requires_entailment = (
        matched_gold.requires_entailment if matched_gold is not None else True
    )
    support_verification = _support_verification(
        candidate=candidate,
        requires_entailment=requires_entailment,
        grounded_sentence=grounded_sentence,
        both_arguments_in_sentence=both_arguments_in_sentence,
    )
    has_support_verification = support_verification is not None
    has_entailment_support = (
        not requires_entailment or support_verification == "ENTAILS"
    )
    has_subject_curie = candidate.subject_curie is not None
    has_object_curie = candidate.object_curie is not None
    has_verified_subject_curie = (
        has_subject_curie and candidate.subject_curie_source == "verified_linker"
    )
    has_verified_object_curie = (
        has_object_curie and candidate.object_curie_source == "verified_linker"
    )
    subject_curie_matches_gold = _curie_matches(
        candidate_curie=(
            candidate.subject_curie if has_verified_subject_curie else None
        ),
        gold_curie=matched_gold.subject_curie if matched_gold is not None else None,
    )
    object_curie_matches_gold = _curie_matches(
        candidate_curie=(
            candidate.object_curie if has_verified_object_curie else None
        ),
        gold_curie=matched_gold.object_curie if matched_gold is not None else None,
    )
    value_supported = (
        matched_gold is not None and matched_gold.value_level in {"high", "medium"}
    )
    flags = _quality_flags(
        _QualityContext(
            supported=supported,
            subject_specific=subject_specific,
            object_specific=object_specific,
            relation_specific=relation_specific,
            grounded_sentence=grounded_sentence,
            subject_in_sentence=grounding.subject_present,
            object_in_sentence=grounding.object_present,
            both_arguments_in_sentence=both_arguments_in_sentence,
            gold_support_sentence=gold_support_sentence,
            known_relation_type=known_relation_type,
            governed_relation_proposal=governed_relation_proposal,
            proposal_supported=proposal_matched_gold_index is not None,
            requires_entailment=requires_entailment,
            has_support_verification=has_support_verification,
            has_entailment_support=has_entailment_support,
            has_subject_curie=has_subject_curie,
            has_object_curie=has_object_curie,
            has_verified_subject_curie=has_verified_subject_curie,
            has_verified_object_curie=has_verified_object_curie,
            subject_curie_matches_gold=subject_curie_matches_gold,
            object_curie_matches_gold=object_curie_matches_gold,
            matched_gold=matched_gold,
        ),
    )
    return CandidateAssessment(
        candidate=candidate,
        matched_gold_index=matched_gold_index,
        proposal_matched_gold_index=proposal_matched_gold_index,
        is_supported_by_gold=supported,
        is_governed_relation_proposal=governed_relation_proposal,
        is_trusted_evidence_eligible=candidate.trusted_evidence_eligible
        and not governed_relation_proposal,
        has_specific_subject=subject_specific,
        has_specific_object=object_specific,
        is_relation_specific=relation_specific,
        has_grounded_sentence=grounded_sentence,
        has_subject_in_sentence=grounding.subject_present,
        has_object_in_sentence=grounding.object_present,
        has_both_arguments_in_sentence=both_arguments_in_sentence,
        has_gold_support_sentence=gold_support_sentence,
        has_known_relation_type=known_relation_type,
        requires_entailment=requires_entailment,
        support_verification=support_verification,
        has_support_verification=has_support_verification,
        has_entailment_support=has_entailment_support,
        has_subject_curie=has_subject_curie,
        has_object_curie=has_object_curie,
        has_verified_subject_curie=has_verified_subject_curie,
        has_verified_object_curie=has_verified_object_curie,
        subject_curie_matches_gold=subject_curie_matches_gold,
        object_curie_matches_gold=object_curie_matches_gold,
        is_valuable=(
            supported
            and not governed_relation_proposal
            and value_supported
            and subject_specific
            and object_specific
            and relation_specific
            and grounded_sentence
            and both_arguments_in_sentence
            and gold_support_sentence
            and has_entailment_support
        ),
        quality_flags=flags,
    )


def _support_verification(
    *,
    candidate: ExtractedRelation,
    requires_entailment: bool,
    grounded_sentence: bool,
    both_arguments_in_sentence: bool,
) -> TripleSupport | None:
    if not requires_entailment:
        return None
    if not grounded_sentence or not both_arguments_in_sentence:
        return None
    return verify_triple_support(
        sentence=candidate.sentence,
        subject=candidate.subject,
        relation_type=candidate.relation_type,
        object_=candidate.object,
    ).support


def _matched_gold_index(
    *,
    candidate: ExtractedRelation,
    gold_relations: tuple[GoldRelation, ...],
) -> int | None:
    if _is_governed_relation_proposal(candidate):
        return None
    candidate_key = normalized_relation_key(candidate)
    for index, gold_relation in enumerate(gold_relations):
        if candidate_key == normalized_relation_key(gold_relation):
            return index
    return None


def _proposal_matched_gold_index(
    *,
    candidate: ExtractedRelation,
    gold_relations: tuple[GoldRelation, ...],
) -> int | None:
    if not _is_governed_relation_proposal(candidate):
        return None
    if candidate.proposed_relation_type is None:
        return None
    candidate_key = (
        _normalize_entity(candidate.subject),
        _normalize_relation_type(candidate.proposed_relation_type),
        _normalize_entity(candidate.object),
    )
    for index, gold_relation in enumerate(gold_relations):
        if candidate_key == normalized_relation_key(gold_relation):
            return index
    return None


def _quality_flags(context: _QualityContext) -> tuple[str, ...]:
    flags: list[str] = []
    if not context.supported and not context.proposal_supported:
        flags.append("unsupported_by_gold")
    if context.governed_relation_proposal:
        flags.append("requires_relation_review")
    if context.proposal_supported:
        flags.append("proposal_matches_gold")
    if not context.subject_specific:
        flags.append("generic_subject")
    if not context.object_specific:
        flags.append("generic_object")
    if not context.relation_specific:
        flags.append("generic_relation_type")
    if not context.known_relation_type:
        flags.append("raw_unknown_relation_type")
    if not context.grounded_sentence:
        flags.append("missing_source_sentence")
    if context.grounded_sentence and not context.both_arguments_in_sentence:
        flags.append("missing_relation_arguments")
    if context.supported and not context.gold_support_sentence:
        flags.append("support_sentence_mismatch")
    if context.requires_entailment and not context.has_support_verification:
        flags.append("support_not_checked")
    elif context.requires_entailment and not context.has_entailment_support:
        flags.append("support_not_entailed")
    flags.extend(_curie_quality_flags(context))
    if (
        context.matched_gold is not None
        and context.matched_gold.value_level in {"low", "reject"}
    ):
        flags.append(f"{context.matched_gold.value_level}_gold_value")
    return tuple(flags)


def _curie_quality_flags(context: _QualityContext) -> tuple[str, ...]:
    if context.matched_gold is None:
        return ()
    flags: list[str] = []
    if context.matched_gold.subject_curie is not None:
        flags.append(
            _curie_endpoint_flag(
                has_curie=context.has_subject_curie,
                has_verified_curie=context.has_verified_subject_curie,
                matches_gold=context.subject_curie_matches_gold,
                missing_flag="missing_subject_curie",
                unverified_flag="unverified_subject_curie",
                wrong_flag="wrong_subject_curie",
            ),
        )
    if context.matched_gold.object_curie is not None:
        flags.append(
            _curie_endpoint_flag(
                has_curie=context.has_object_curie,
                has_verified_curie=context.has_verified_object_curie,
                matches_gold=context.object_curie_matches_gold,
                missing_flag="missing_object_curie",
                unverified_flag="unverified_object_curie",
                wrong_flag="wrong_object_curie",
            ),
        )
    return tuple(flag for flag in flags if flag != "")


def _curie_endpoint_flag(
    *,
    has_curie: bool,
    has_verified_curie: bool,
    matches_gold: bool,
    missing_flag: str,
    unverified_flag: str,
    wrong_flag: str,
) -> str:
    if not has_curie:
        return missing_flag
    if not has_verified_curie:
        return unverified_flag
    if not matches_gold:
        return wrong_flag
    return ""


def _normalize_entity(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _normalize_relation_type(value: str) -> str:
    token = re.sub(r"[^A-Z0-9]+", "_", value.strip().upper()).strip("_")
    return _RELATION_SYNONYMS.get(token, token)


def _is_specific_entity_label(label: str) -> bool:
    normalized = _normalize_entity(label)
    if not normalized:
        return False
    if normalized in _GENERIC_ENTITY_LABELS:
        return False
    return len(normalized.split()) <= _MAX_SPECIFIC_ENTITY_TOKENS


def _is_specific_relation(relation_type: str) -> bool:
    return _normalize_relation_type(relation_type) not in _GENERIC_RELATION_TYPES


def _is_known_relation_type(relation_type: str) -> bool:
    normalized = _normalize_relation_type(relation_type)
    return (
        normalized in LLM_VALID_RELATION_TYPES
        or normalized == LLM_PROPOSE_NEW_RELATION_TYPE
    )


def _is_governed_relation_proposal(candidate: ExtractedRelation) -> bool:
    return (
        candidate.relation_governance_status == "requires_relation_review"
        or _normalize_relation_type(candidate.relation_type)
        == LLM_PROPOSE_NEW_RELATION_TYPE
    )


def _curie_matches(
    *,
    candidate_curie: str | None,
    gold_curie: str | None,
) -> bool:
    return (
        gold_curie is not None
        and candidate_curie is not None
        and _normalize_curie(candidate_curie) == _normalize_curie(gold_curie)
    )


def _model_curie_wrong_count(
    case_assessments: tuple[tuple[CandidateAssessment, ...], ...],
    case_gold_relations: tuple[tuple[GoldRelation, ...], ...],
) -> int:
    wrong_count = 0
    for assessments, gold_relations in zip(
        case_assessments,
        case_gold_relations,
        strict=True,
    ):
        for assessment in assessments:
            if assessment.matched_gold_index is None:
                continue
            gold = gold_relations[assessment.matched_gold_index]
            candidate = assessment.candidate
            wrong_count += int(
                _model_curie_is_wrong(
                    candidate_curie=candidate.subject_curie,
                    candidate_source=candidate.subject_curie_source,
                    gold_curie=gold.subject_curie,
                ),
            )
            wrong_count += int(
                _model_curie_is_wrong(
                    candidate_curie=candidate.object_curie,
                    candidate_source=candidate.object_curie_source,
                    gold_curie=gold.object_curie,
                ),
            )
    return wrong_count


def _model_curie_is_wrong(
    *,
    candidate_curie: str | None,
    candidate_source: str,
    gold_curie: str | None,
) -> bool:
    return (
        candidate_source == "model"
        and candidate_curie is not None
        and gold_curie is not None
        and not _curie_matches(
            candidate_curie=candidate_curie,
            gold_curie=gold_curie,
        )
    )


def _normalize_curie(value: str) -> str:
    prefix, separator, local = value.strip().partition(":")
    if separator == "":
        return value.strip().upper()
    return f"{prefix.upper()}:{local}"


def _has_grounded_sentence(*, source_text: str, sentence: str) -> bool:
    normalized_source = _normalize_text_for_sentence_match(source_text)
    normalized_sentence = _normalize_text_for_sentence_match(sentence)
    return normalized_sentence != "" and normalized_sentence in normalized_source


def _has_matching_support_sentence(
    *,
    candidate_sentence: str,
    gold_sentence: str,
) -> bool:
    return _normalize_text_for_sentence_match(
        candidate_sentence,
    ) == _normalize_text_for_sentence_match(gold_sentence)


def _normalize_text_for_sentence_match(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _case_agent_completed(trace: ExtractionTrace, candidate_count: int) -> bool:
    if not trace.agent_completed:
        return False
    if trace.llm_candidate_status == "llm_empty":
        return candidate_count == 0
    return True


def _verdict(context: _VerdictContext) -> tuple[Verdict, str, tuple[str, ...], tuple[str, ...]]:
    red_reasons: list[str] = []
    if context.case_count == 0:
        red_reasons.append("No benchmark cases were provided.")
    if context.require_agent_completion and context.invalid_agent_case_count > 0:
        red_reasons.append(
            f"{context.invalid_agent_case_count}/{context.case_count} cases are invalid because agent extraction did not complete without fallback.",
        )
    if context.raw_unknown_relation_type_count > 0:
        red_reasons.append(
            "At least one extracted candidate kept a raw unknown relation type."
        )
    if context.raw_unknown_relation_type_surface_count > 0:
        red_reasons.append(
            "At least one review, proposal, graph, or dictionary surface kept a raw unknown relation type."
        )
    if (
        context.gold_curie_endpoint_count > 0
        and context.curie_linked_gold_endpoint_rate
        < _MIN_CURIE_LINKED_GOLD_ENDPOINT_RATE
    ):
        red_reasons.append(
            "Too few CURIE-linked gold endpoints were recovered by extraction."
        )
    if context.negative_control_leakage_count > 0:
        red_reasons.append("At least one negative-control case emitted a candidate.")
    if context.precision < _RED_MIN_PRECISION:
        red_reasons.append("Less than half of extracted relations matched the gold set.")
    if context.valuable_rate < _RED_MIN_VALUABLE_RATE:
        red_reasons.append("Too few candidates were specific, supported, and valuable.")
    if context.generic_relation_rate > _RED_MAX_GENERIC_RELATION_RATE:
        red_reasons.append("More than half of candidates used generic relation types.")

    yellow_reasons: list[str] = []
    if (
        context.precision < _YELLOW_MIN_PRECISION
    ):
        yellow_reasons.append("Precision is below trusted graph construction target.")
    if context.trusted_recall < _YELLOW_MIN_RECALL:
        yellow_reasons.append("Trusted high-value recall is below target.")
    if context.valuable_rate < _YELLOW_MIN_VALUABLE_RATE:
        yellow_reasons.append("Valuable candidate rate is below target.")
    if context.generic_relation_rate > _YELLOW_MAX_GENERIC_RELATION_RATE:
        yellow_reasons.append("Generic relation rate is above target.")
    if red_reasons:
        return "RED", red_reasons[0], tuple(red_reasons), tuple(yellow_reasons)
    if yellow_reasons:
        reason = (
            "The method may be useful for triage, but quality is not strong "
            "enough for trusted graph construction without review."
        )
        return "YELLOW", reason, (), tuple(yellow_reasons)
    return (
        "GREEN",
        "The benchmark outputs are mostly supported, specific, and valuable.",
        (),
        (),
    )
