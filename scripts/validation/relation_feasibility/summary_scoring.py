"""Aggregate summary scoring for relation feasibility audits."""

from __future__ import annotations

from dataclasses import dataclass

from scripts.validation.relation_feasibility.endpoint_metrics import (
    EndpointMetricSummary,
    build_endpoint_metric_summary,
)
from scripts.validation.relation_feasibility.models import (
    CandidateAssessment,
    ExtractionTrace,
    FeasibilitySummary,
    GoldRelation,
    RelationTypeSurface,
    Verdict,
)
from scripts.validation.relation_feasibility.scoring import (
    _is_known_relation_type,
    _is_known_relation_type_surface,
    _model_curie_wrong_count,
    _wrong_verified_curie_link_count,
)
from scripts.validation.relation_feasibility.trusted_metric_rules import (
    HIGH_VALUE_LEVELS,
    LOW_VALUE_LEVELS,
    is_trusted_high_value_match,
    low_value_review_gold_index,
)

_RED_MIN_PRECISION = 0.5
_RED_MIN_VALUABLE_RATE = 0.35
_RED_MAX_GENERIC_RELATION_RATE = 0.5
_YELLOW_MIN_PRECISION = 0.8
_YELLOW_MIN_RECALL = 0.6
_YELLOW_MIN_VALUABLE_RATE = 0.7
_YELLOW_MAX_GENERIC_RELATION_RATE = 0.25
_MIN_CURIE_LINKED_GOLD_ENDPOINT_RATE = 0.95


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
    trusted_eligible_gold_curie_endpoint_count: int
    trusted_eligible_curie_linked_gold_endpoint_rate: float
    weak_claim_trusted_leakage_count: int
    wrong_verified_curie_link_count: int
    negative_control_leakage_count: int
    invalid_agent_case_count: int
    require_agent_completion: bool


@dataclass(frozen=True, slots=True)
class _CandidateMetricCounts:
    candidate_count: int
    supported_candidate_count: int
    valuable_candidate_count: int
    generic_relation_count: int
    specific_entity_count: int
    relation_specific_count: int
    grounded_sentence_count: int
    both_arguments_present_count: int
    support_sentence_aligned_count: int
    entailment_required_count: int
    entailment_checked_count: int
    entailment_supported_count: int
    precision: float
    valuable_rate: float
    generic_relation_rate: float


@dataclass(frozen=True, slots=True)
class _TraceMetricCounts:
    pruned_generic_relation_count: int
    quality_filtered_candidate_count: int
    fallback_case_count: int
    fallback_candidate_count: int


@dataclass(frozen=True, slots=True)
class _RelationTypeMetricCounts:
    raw_unknown_relation_type_count: int
    relation_type_surface_count: int
    raw_unknown_relation_type_surface_count: int


@dataclass(frozen=True, slots=True)
class _ProposalMetricCounts:
    proposal_candidate_count: int
    proposal_gold_match_count: int
    proposal_eligible_gold_count: int


@dataclass(frozen=True, slots=True)
class _CurieMetricCounts:
    gold_curie_endpoint_count: int
    candidate_curie_endpoint_count: int
    candidate_curie_present_rate: float
    curie_linked_gold_endpoint_count: int
    verified_curie_match_count: int
    curie_linked_gold_endpoint_rate: float
    model_curie_wrong_count: int
    wrong_verified_curie_link_count: int


@dataclass(frozen=True, slots=True)
class _ValueMetricCounts:
    high_value_gold_relation_count: int
    high_value_missed_gold_count: int
    high_value_recall: float
    low_value_gold_relation_count: int
    low_value_missed_gold_count: int
    low_value_recall: float


@dataclass(frozen=True, slots=True)
class _TrustLaneMetricCounts:
    trusted_high_value_match_count: int
    trusted_high_value_recall: float
    low_value_review_candidate_count: int
    low_value_review_gold_match_count: int
    low_value_review_recall: float


@dataclass(frozen=True, slots=True)
class _AgentMetricCounts:
    agent_completed_case_count: int
    agent_zero_candidate_case_count: int
    completed_agent_candidate_count: int
    completed_agent_supported_candidate_count: int
    completed_agent_valuable_candidate_count: int
    completed_agent_gold_relation_count: int
    completed_agent_missed_gold_count: int
    fallback_credited_as_agent_count: int
    invalid_agent_case_count: int


@dataclass(frozen=True, slots=True)
class _NegativeControlMetricCounts:
    negative_control_case_count: int
    negative_control_empty_count: int
    negative_control_leakage_count: int


@dataclass(frozen=True, slots=True)
class _SummaryMetricGroups:
    candidate: _CandidateMetricCounts
    relation_type: _RelationTypeMetricCounts
    curie: _CurieMetricCounts
    value: _ValueMetricCounts
    trust_lane: _TrustLaneMetricCounts
    negative_control: _NegativeControlMetricCounts
    agent: _AgentMetricCounts


def build_summary(inputs: SummaryInputs) -> FeasibilitySummary:
    """Build aggregate feasibility metrics."""

    candidates = _all_candidate_assessments(inputs)
    candidate_metrics = _candidate_metric_counts(candidates)
    trace_metrics = _trace_metric_counts(inputs)
    relation_type_metrics = _relation_type_metric_counts(inputs, candidates)
    proposal_metrics = _proposal_metric_counts(inputs, candidates)
    curie_metrics = _curie_metric_counts(inputs, candidates)
    value_metrics = _value_metric_counts(inputs)
    case_agent_completed_flags = _case_agent_completed_flags(inputs)
    trust_lane_metrics = _trust_lane_metric_counts(
        inputs,
        case_agent_completed_flags=case_agent_completed_flags,
        value_metrics=value_metrics,
    )
    endpoint_metric_summary = build_endpoint_metric_summary(
        case_assessments=inputs.case_assessments,
        case_gold_relations=inputs.case_gold_relations,
        case_agent_completed_flags=case_agent_completed_flags,
    )
    negative_control_metrics = _negative_control_metric_counts(
        inputs,
        case_agent_completed_flags=case_agent_completed_flags,
    )
    agent_metrics = _agent_metric_counts(
        inputs,
        case_agent_completed_flags=case_agent_completed_flags,
    )
    metric_groups = _SummaryMetricGroups(
        candidate=candidate_metrics,
        relation_type=relation_type_metrics,
        curie=curie_metrics,
        value=value_metrics,
        trust_lane=trust_lane_metrics,
        negative_control=negative_control_metrics,
        agent=agent_metrics,
    )
    recall = _ratio(
        inputs.gold_relation_count - inputs.missed_gold_count,
        inputs.gold_relation_count,
    )
    verdict, reason, blocking_reasons, warning_reasons = _verdict(
        _verdict_context(
            inputs=inputs,
            metric_groups=metric_groups,
            endpoint_metric_summary=endpoint_metric_summary,
            recall=recall,
        ),
    )
    return FeasibilitySummary(
        case_count=inputs.case_count,
        gold_relation_count=inputs.gold_relation_count,
        candidate_count=candidate_metrics.candidate_count,
        supported_candidate_count=candidate_metrics.supported_candidate_count,
        valuable_candidate_count=candidate_metrics.valuable_candidate_count,
        generic_relation_count=candidate_metrics.generic_relation_count,
        pruned_generic_relation_count=trace_metrics.pruned_generic_relation_count,
        quality_filtered_candidate_count=trace_metrics.quality_filtered_candidate_count,
        raw_unknown_relation_type_count=(
            relation_type_metrics.raw_unknown_relation_type_count
        ),
        relation_type_surface_count=relation_type_metrics.relation_type_surface_count,
        raw_unknown_relation_type_surface_count=(
            relation_type_metrics.raw_unknown_relation_type_surface_count
        ),
        proposal_candidate_count=proposal_metrics.proposal_candidate_count,
        proposal_gold_match_count=proposal_metrics.proposal_gold_match_count,
        proposal_eligible_gold_count=proposal_metrics.proposal_eligible_gold_count,
        gold_curie_endpoint_count=curie_metrics.gold_curie_endpoint_count,
        candidate_curie_endpoint_count=curie_metrics.candidate_curie_endpoint_count,
        curie_linked_gold_endpoint_count=curie_metrics.curie_linked_gold_endpoint_count,
        verified_curie_match_count=curie_metrics.verified_curie_match_count,
        model_curie_wrong_count=curie_metrics.model_curie_wrong_count,
        wrong_verified_curie_link_count=curie_metrics.wrong_verified_curie_link_count,
        support_sentence_aligned_count=(
            candidate_metrics.support_sentence_aligned_count
        ),
        both_arguments_present_count=candidate_metrics.both_arguments_present_count,
        entailment_required_count=candidate_metrics.entailment_required_count,
        entailment_checked_count=candidate_metrics.entailment_checked_count,
        entailment_supported_count=candidate_metrics.entailment_supported_count,
        agent_completed_case_count=agent_metrics.agent_completed_case_count,
        agent_zero_candidate_case_count=agent_metrics.agent_zero_candidate_case_count,
        fallback_case_count=trace_metrics.fallback_case_count,
        fallback_candidate_count=trace_metrics.fallback_candidate_count,
        fallback_credited_as_agent_count=agent_metrics.fallback_credited_as_agent_count,
        completed_agent_candidate_count=agent_metrics.completed_agent_candidate_count,
        completed_agent_supported_candidate_count=(
            agent_metrics.completed_agent_supported_candidate_count
        ),
        completed_agent_valuable_candidate_count=(
            agent_metrics.completed_agent_valuable_candidate_count
        ),
        completed_agent_gold_relation_count=(
            agent_metrics.completed_agent_gold_relation_count
        ),
        completed_agent_missed_gold_count=(
            agent_metrics.completed_agent_missed_gold_count
        ),
        invalid_agent_case_count=agent_metrics.invalid_agent_case_count,
        high_value_gold_relation_count=value_metrics.high_value_gold_relation_count,
        high_value_missed_gold_count=value_metrics.high_value_missed_gold_count,
        trusted_high_value_match_count=(
            trust_lane_metrics.trusted_high_value_match_count
        ),
        trusted_high_value_recall=trust_lane_metrics.trusted_high_value_recall,
        low_value_gold_relation_count=value_metrics.low_value_gold_relation_count,
        low_value_missed_gold_count=value_metrics.low_value_missed_gold_count,
        low_value_review_candidate_count=(
            trust_lane_metrics.low_value_review_candidate_count
        ),
        low_value_review_gold_match_count=(
            trust_lane_metrics.low_value_review_gold_match_count
        ),
        low_value_review_recall=trust_lane_metrics.low_value_review_recall,
        trusted_eligible_gold_curie_endpoint_count=(
            endpoint_metric_summary.trusted_eligible_gold_curie_endpoint_count
        ),
        trusted_eligible_curie_linked_gold_endpoint_count=(
            endpoint_metric_summary.trusted_eligible_curie_linked_gold_endpoint_count
        ),
        trusted_eligible_curie_linked_gold_endpoint_rate=(
            endpoint_metric_summary.trusted_eligible_curie_linked_gold_endpoint_rate
        ),
        low_value_review_gold_curie_endpoint_count=(
            endpoint_metric_summary.low_value_review_gold_curie_endpoint_count
        ),
        low_value_review_curie_linked_gold_endpoint_count=(
            endpoint_metric_summary.low_value_review_curie_linked_gold_endpoint_count
        ),
        low_value_review_curie_endpoint_capture_rate=(
            endpoint_metric_summary.low_value_review_curie_endpoint_capture_rate
        ),
        weak_claim_trusted_leakage_count=(
            endpoint_metric_summary.weak_claim_trusted_leakage_count
        ),
        negative_control_case_count=(
            negative_control_metrics.negative_control_case_count
        ),
        negative_control_empty_count=(
            negative_control_metrics.negative_control_empty_count
        ),
        negative_control_leakage_count=(
            negative_control_metrics.negative_control_leakage_count
        ),
        missed_gold_count=inputs.missed_gold_count,
        precision_against_gold=candidate_metrics.precision,
        recall_against_gold=recall,
        high_value_recall=value_metrics.high_value_recall,
        low_value_recall=value_metrics.low_value_recall,
        completed_agent_precision_against_gold=_ratio(
            agent_metrics.completed_agent_supported_candidate_count,
            agent_metrics.completed_agent_candidate_count,
        ),
        completed_agent_recall_against_gold=_ratio(
            agent_metrics.completed_agent_gold_relation_count
            - agent_metrics.completed_agent_missed_gold_count,
            agent_metrics.completed_agent_gold_relation_count,
        ),
        specificity_rate=_ratio(
            candidate_metrics.specific_entity_count,
            candidate_metrics.candidate_count,
        ),
        relation_specificity_rate=_ratio(
            candidate_metrics.relation_specific_count,
            candidate_metrics.candidate_count,
        ),
        generic_relation_rate=candidate_metrics.generic_relation_rate,
        raw_unknown_relation_type_rate=_ratio(
            relation_type_metrics.raw_unknown_relation_type_count,
            candidate_metrics.candidate_count,
        ),
        raw_unknown_relation_type_surface_rate=_ratio(
            relation_type_metrics.raw_unknown_relation_type_surface_count,
            relation_type_metrics.relation_type_surface_count,
        ),
        proposal_recall_against_gold=_ratio(
            proposal_metrics.proposal_gold_match_count,
            inputs.gold_relation_count,
        ),
        proposal_recall_against_proposal_eligible_gold=_ratio(
            proposal_metrics.proposal_gold_match_count,
            proposal_metrics.proposal_eligible_gold_count,
        ),
        candidate_curie_present_rate=curie_metrics.candidate_curie_present_rate,
        verified_curie_match_rate=curie_metrics.curie_linked_gold_endpoint_rate,
        curie_linked_gold_endpoint_rate=curie_metrics.curie_linked_gold_endpoint_rate,
        valuable_candidate_rate=candidate_metrics.valuable_rate,
        completed_agent_valuable_candidate_rate=_ratio(
            agent_metrics.completed_agent_valuable_candidate_count,
            agent_metrics.completed_agent_candidate_count,
        ),
        grounded_sentence_rate=_ratio(
            candidate_metrics.grounded_sentence_count,
            candidate_metrics.candidate_count,
        ),
        both_arguments_present_rate=_ratio(
            candidate_metrics.both_arguments_present_count,
            candidate_metrics.candidate_count,
        ),
        support_sentence_alignment_rate=_ratio(
            candidate_metrics.support_sentence_aligned_count,
            candidate_metrics.candidate_count,
        ),
        entailment_checked_rate=_ratio(
            candidate_metrics.entailment_checked_count,
            candidate_metrics.entailment_required_count,
        ),
        entailment_supported_rate=_ratio(
            candidate_metrics.entailment_supported_count,
            candidate_metrics.entailment_required_count,
        ),
        verdict=verdict,
        verdict_reason=reason,
        negative_control_empty_rate=_ratio(
            negative_control_metrics.negative_control_empty_count,
            negative_control_metrics.negative_control_case_count,
        ),
        blocking_reasons=blocking_reasons,
        warning_reasons=warning_reasons,
    )


def _all_candidate_assessments(
    inputs: SummaryInputs,
) -> tuple[CandidateAssessment, ...]:
    return tuple(
        assessment
        for assessments in inputs.case_assessments
        for assessment in assessments
    )


def _candidate_metric_counts(
    candidates: tuple[CandidateAssessment, ...],
) -> _CandidateMetricCounts:
    candidate_count = len(candidates)
    supported_count = sum(1 for assessment in candidates if assessment.is_supported_by_gold)
    valuable_count = sum(1 for assessment in candidates if assessment.is_valuable)
    generic_count = sum(
        1 for assessment in candidates if not assessment.is_relation_specific
    )
    specific_entity_count = sum(
        1
        for assessment in candidates
        if assessment.has_specific_subject and assessment.has_specific_object
    )
    relation_specific_count = sum(
        1 for assessment in candidates if assessment.is_relation_specific
    )
    grounded_count = sum(
        1 for assessment in candidates if assessment.has_grounded_sentence
    )
    both_args_count = sum(
        1 for assessment in candidates if assessment.has_both_arguments_in_sentence
    )
    support_aligned_count = sum(
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
    return _CandidateMetricCounts(
        candidate_count=candidate_count,
        supported_candidate_count=supported_count,
        valuable_candidate_count=valuable_count,
        generic_relation_count=generic_count,
        specific_entity_count=specific_entity_count,
        relation_specific_count=relation_specific_count,
        grounded_sentence_count=grounded_count,
        both_arguments_present_count=both_args_count,
        support_sentence_aligned_count=support_aligned_count,
        entailment_required_count=entailment_required_count,
        entailment_checked_count=entailment_checked_count,
        entailment_supported_count=entailment_supported_count,
        precision=_ratio(supported_count, candidate_count),
        valuable_rate=_ratio(valuable_count, candidate_count),
        generic_relation_rate=_ratio(generic_count, candidate_count),
    )


def _trace_metric_counts(inputs: SummaryInputs) -> _TraceMetricCounts:
    return _TraceMetricCounts(
        pruned_generic_relation_count=sum(
            trace.pruned_generic_relation_count for trace in inputs.extraction_traces
        ),
        quality_filtered_candidate_count=sum(
            trace.quality_filtered_candidate_count for trace in inputs.extraction_traces
        ),
        fallback_case_count=sum(
            1 for trace in inputs.extraction_traces if trace.fallback_used
        ),
        fallback_candidate_count=sum(
            trace.fallback_candidate_count for trace in inputs.extraction_traces
        ),
    )


def _relation_type_metric_counts(
    inputs: SummaryInputs,
    candidates: tuple[CandidateAssessment, ...],
) -> _RelationTypeMetricCounts:
    relation_type_surfaces = tuple(
        surface
        for surfaces in inputs.relation_type_surfaces
        for surface in surfaces
    )
    return _RelationTypeMetricCounts(
        raw_unknown_relation_type_count=sum(
            1 for assessment in candidates if not assessment.has_known_relation_type
        ),
        relation_type_surface_count=len(relation_type_surfaces),
        raw_unknown_relation_type_surface_count=sum(
            1
            for surface in relation_type_surfaces
            if not _is_known_relation_type_surface(surface)
        ),
    )


def _proposal_metric_counts(
    inputs: SummaryInputs,
    candidates: tuple[CandidateAssessment, ...],
) -> _ProposalMetricCounts:
    return _ProposalMetricCounts(
        proposal_candidate_count=sum(
            1 for assessment in candidates if assessment.is_governed_relation_proposal
        ),
        proposal_gold_match_count=len(
            {
                (case_index, assessment.proposal_matched_gold_index)
                for case_index, assessments in enumerate(inputs.case_assessments)
                for assessment in assessments
                if assessment.proposal_matched_gold_index is not None
            },
        ),
        proposal_eligible_gold_count=sum(
            1
            for gold_relations in inputs.case_gold_relations
            for gold_relation in gold_relations
            if not _is_known_relation_type(gold_relation.relation_type)
        ),
    )


def _curie_metric_counts(
    inputs: SummaryInputs,
    candidates: tuple[CandidateAssessment, ...],
) -> _CurieMetricCounts:
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
    linked_gold_endpoint_count = len(_curie_linked_gold_endpoints(inputs))
    return _CurieMetricCounts(
        gold_curie_endpoint_count=gold_curie_endpoint_count,
        candidate_curie_endpoint_count=candidate_curie_endpoint_count,
        candidate_curie_present_rate=_ratio(
            candidate_curie_endpoint_count,
            len(candidates) * 2,
        ),
        curie_linked_gold_endpoint_count=linked_gold_endpoint_count,
        verified_curie_match_count=linked_gold_endpoint_count,
        curie_linked_gold_endpoint_rate=_ratio(
            linked_gold_endpoint_count,
            gold_curie_endpoint_count,
        ),
        model_curie_wrong_count=_model_curie_wrong_count(
            inputs.case_assessments,
            inputs.case_gold_relations,
        ),
        wrong_verified_curie_link_count=_wrong_verified_curie_link_count(
            inputs.case_assessments,
            inputs.case_gold_relations,
        ),
    )


def _curie_linked_gold_endpoints(inputs: SummaryInputs) -> set[tuple[int, int, str]]:
    return {
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


def _value_metric_counts(inputs: SummaryInputs) -> _ValueMetricCounts:
    high_value_gold_count = _gold_relation_count_by_value(
        inputs,
        value_levels=HIGH_VALUE_LEVELS,
    )
    low_value_gold_count = _gold_relation_count_by_value(
        inputs,
        value_levels=LOW_VALUE_LEVELS,
    )
    missed_gold_relations = _missed_gold_relations(inputs)
    high_value_missed_count = sum(
        1
        for gold_relation in missed_gold_relations
        if gold_relation.value_level in HIGH_VALUE_LEVELS
    )
    low_value_missed_count = sum(
        1
        for gold_relation in missed_gold_relations
        if gold_relation.value_level in LOW_VALUE_LEVELS
    )
    return _ValueMetricCounts(
        high_value_gold_relation_count=high_value_gold_count,
        high_value_missed_gold_count=high_value_missed_count,
        high_value_recall=_ratio(
            high_value_gold_count - high_value_missed_count,
            high_value_gold_count,
        ),
        low_value_gold_relation_count=low_value_gold_count,
        low_value_missed_gold_count=low_value_missed_count,
        low_value_recall=_ratio(
            low_value_gold_count - low_value_missed_count,
            low_value_gold_count,
        ),
    )


def _gold_relation_count_by_value(
    inputs: SummaryInputs,
    *,
    value_levels: frozenset[str],
) -> int:
    return sum(
        1
        for gold_relations in inputs.case_gold_relations
        for gold_relation in gold_relations
        if gold_relation.value_level in value_levels
    )


def _missed_gold_relations(inputs: SummaryInputs) -> tuple[GoldRelation, ...]:
    return tuple(
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


def _case_agent_completed_flags(inputs: SummaryInputs) -> tuple[bool, ...]:
    return tuple(
        _case_agent_completed(trace, len(assessments))
        for assessments, trace in zip(
            inputs.case_assessments,
            inputs.extraction_traces,
            strict=True,
        )
    )


def _trust_lane_metric_counts(
    inputs: SummaryInputs,
    *,
    case_agent_completed_flags: tuple[bool, ...],
    value_metrics: _ValueMetricCounts,
) -> _TrustLaneMetricCounts:
    trusted_high_value_matches: set[tuple[int, int]] = set()
    low_value_review_matches: set[tuple[int, int]] = set()
    low_value_review_candidate_count = 0
    for case_index, (gold_relations, assessments, agent_completed) in enumerate(
        zip(
            inputs.case_gold_relations,
            inputs.case_assessments,
            case_agent_completed_flags,
            strict=True,
        ),
    ):
        for assessment in assessments:
            if is_trusted_high_value_match(
                assessment=assessment,
                gold_relations=gold_relations,
                agent_completed=agent_completed,
            ):
                trusted_high_value_matches.add(
                    (case_index, assessment.matched_gold_index or 0),
                )
            low_value_review_index = low_value_review_gold_index(
                assessment=assessment,
                gold_relations=gold_relations,
            )
            if agent_completed and low_value_review_index is not None:
                low_value_review_candidate_count += 1
                low_value_review_matches.add((case_index, low_value_review_index))
    return _TrustLaneMetricCounts(
        trusted_high_value_match_count=len(trusted_high_value_matches),
        trusted_high_value_recall=_ratio(
            len(trusted_high_value_matches),
            value_metrics.high_value_gold_relation_count,
        ),
        low_value_review_candidate_count=low_value_review_candidate_count,
        low_value_review_gold_match_count=len(low_value_review_matches),
        low_value_review_recall=_ratio(
            len(low_value_review_matches),
            value_metrics.low_value_gold_relation_count,
        ),
    )


def _negative_control_metric_counts(
    inputs: SummaryInputs,
    *,
    case_agent_completed_flags: tuple[bool, ...],
) -> _NegativeControlMetricCounts:
    return _NegativeControlMetricCounts(
        negative_control_case_count=sum(
            1 for category in inputs.case_categories if category == "negative_control"
        ),
        negative_control_empty_count=sum(
            1
            for category, completed, assessments in zip(
                inputs.case_categories,
                case_agent_completed_flags,
                inputs.case_assessments,
                strict=True,
            )
            if category == "negative_control" and completed and len(assessments) == 0
        ),
        negative_control_leakage_count=sum(
            1
            for category, assessments in zip(
                inputs.case_categories,
                inputs.case_assessments,
                strict=True,
            )
            if category == "negative_control" and len(assessments) > 0
        ),
    )


def _agent_metric_counts(
    inputs: SummaryInputs,
    *,
    case_agent_completed_flags: tuple[bool, ...],
) -> _AgentMetricCounts:
    completed_agent_assessments = _completed_agent_assessments(inputs)
    return _AgentMetricCounts(
        agent_completed_case_count=sum(
            1 for completed in case_agent_completed_flags if completed
        ),
        agent_zero_candidate_case_count=sum(
            1
            for completed, trace in zip(
                case_agent_completed_flags,
                inputs.extraction_traces,
                strict=True,
            )
            if completed and trace.llm_candidate_status == "llm_empty"
        ),
        completed_agent_candidate_count=len(completed_agent_assessments),
        completed_agent_supported_candidate_count=sum(
            1
            for assessment in completed_agent_assessments
            if assessment.is_supported_by_gold
        ),
        completed_agent_valuable_candidate_count=sum(
            1 for assessment in completed_agent_assessments if assessment.is_valuable
        ),
        completed_agent_gold_relation_count=_completed_agent_gold_relation_count(
            inputs,
        ),
        completed_agent_missed_gold_count=_completed_agent_missed_gold_count(inputs),
        fallback_credited_as_agent_count=_fallback_credited_as_agent_count(inputs),
        invalid_agent_case_count=(
            sum(1 for completed in case_agent_completed_flags if not completed)
            if inputs.require_agent_completion
            else 0
        ),
    )


def _completed_agent_assessments(
    inputs: SummaryInputs,
) -> tuple[CandidateAssessment, ...]:
    return tuple(
        assessment
        for assessments, trace in zip(
            inputs.case_assessments,
            inputs.extraction_traces,
            strict=True,
        )
        if _case_agent_completed(trace, len(assessments))
        for assessment in assessments
    )


def _completed_agent_gold_relation_count(inputs: SummaryInputs) -> int:
    return sum(
        gold_count
        for gold_count, trace, assessments in zip(
            inputs.case_gold_relation_counts,
            inputs.extraction_traces,
            inputs.case_assessments,
            strict=True,
        )
        if _case_agent_completed(trace, len(assessments))
    )


def _completed_agent_missed_gold_count(inputs: SummaryInputs) -> int:
    return sum(
        missed_count
        for missed_count, trace, assessments in zip(
            inputs.case_missed_gold_counts,
            inputs.extraction_traces,
            inputs.case_assessments,
            strict=True,
        )
        if _case_agent_completed(trace, len(assessments))
    )


def _fallback_credited_as_agent_count(inputs: SummaryInputs) -> int:
    return sum(
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


def _verdict_context(
    *,
    inputs: SummaryInputs,
    metric_groups: _SummaryMetricGroups,
    endpoint_metric_summary: EndpointMetricSummary,
    recall: float,
) -> _VerdictContext:
    return _VerdictContext(
        case_count=inputs.case_count,
        precision=metric_groups.candidate.precision,
        recall=recall,
        trusted_recall=(
            metric_groups.trust_lane.trusted_high_value_recall
            if metric_groups.value.high_value_gold_relation_count > 0
            else recall
        ),
        valuable_rate=metric_groups.candidate.valuable_rate,
        generic_relation_rate=metric_groups.candidate.generic_relation_rate,
        raw_unknown_relation_type_count=(
            metric_groups.relation_type.raw_unknown_relation_type_count
        ),
        raw_unknown_relation_type_surface_count=(
            metric_groups.relation_type.raw_unknown_relation_type_surface_count
        ),
        gold_curie_endpoint_count=metric_groups.curie.gold_curie_endpoint_count,
        curie_linked_gold_endpoint_rate=(
            metric_groups.curie.curie_linked_gold_endpoint_rate
        ),
        trusted_eligible_gold_curie_endpoint_count=(
            endpoint_metric_summary.trusted_eligible_gold_curie_endpoint_count
        ),
        trusted_eligible_curie_linked_gold_endpoint_rate=(
            endpoint_metric_summary.trusted_eligible_curie_linked_gold_endpoint_rate
        ),
        weak_claim_trusted_leakage_count=(
            endpoint_metric_summary.weak_claim_trusted_leakage_count
        ),
        wrong_verified_curie_link_count=(
            metric_groups.curie.wrong_verified_curie_link_count
        ),
        negative_control_leakage_count=(
            metric_groups.negative_control.negative_control_leakage_count
        ),
        invalid_agent_case_count=metric_groups.agent.invalid_agent_case_count,
        require_agent_completion=inputs.require_agent_completion,
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


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _case_agent_completed(trace: ExtractionTrace, candidate_count: int) -> bool:
    if not trace.agent_completed:
        return False
    if trace.llm_candidate_status == "llm_empty":
        return candidate_count == 0
    return True


def _verdict(context: _VerdictContext) -> tuple[Verdict, str, tuple[str, ...], tuple[str, ...]]:
    red_reasons = _red_verdict_reasons(context)
    yellow_reasons = _yellow_verdict_reasons(context)
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


def _red_verdict_reasons(context: _VerdictContext) -> tuple[str, ...]:
    return tuple(
        reason
        for active, reason in (
            (context.case_count == 0, "No benchmark cases were provided."),
            (_invalid_agent_blocked(context), _invalid_agent_reason(context)),
            (
                context.raw_unknown_relation_type_count > 0,
                "At least one extracted candidate kept a raw unknown relation type.",
            ),
            (
                context.raw_unknown_relation_type_surface_count > 0,
                "At least one review, proposal, graph, or dictionary surface kept a raw unknown relation type.",
            ),
            (
                context.wrong_verified_curie_link_count > 0,
                "Wrong verified CURIE links were emitted.",
            ),
            (
                _trusted_eligible_endpoint_rate_blocked(context),
                "Too few trusted-eligible CURIE-linked gold endpoints were recovered by extraction.",
            ),
            (
                context.weak_claim_trusted_leakage_count > 0,
                "Weak low-value claims leaked into trusted evidence.",
            ),
            (
                context.negative_control_leakage_count > 0,
                "At least one negative-control case emitted a candidate.",
            ),
            (
                context.precision < _RED_MIN_PRECISION,
                "Less than half of extracted relations matched the gold set.",
            ),
            (
                context.valuable_rate < _RED_MIN_VALUABLE_RATE,
                "Too few candidates were specific, supported, and valuable.",
            ),
            (
                context.generic_relation_rate > _RED_MAX_GENERIC_RELATION_RATE,
                "More than half of candidates used generic relation types.",
            ),
        )
        if active
    )


def _yellow_verdict_reasons(context: _VerdictContext) -> tuple[str, ...]:
    return tuple(
        reason
        for active, reason in (
            (
                context.precision < _YELLOW_MIN_PRECISION,
                "Precision is below trusted graph construction target.",
            ),
            (
                context.trusted_recall < _YELLOW_MIN_RECALL,
                "Trusted high-value recall is below target.",
            ),
            (
                context.valuable_rate < _YELLOW_MIN_VALUABLE_RATE,
                "Valuable candidate rate is below target.",
            ),
            (
                context.generic_relation_rate > _YELLOW_MAX_GENERIC_RELATION_RATE,
                "Generic relation rate is above target.",
            ),
        )
        if active
    )


def _invalid_agent_blocked(context: _VerdictContext) -> bool:
    return context.require_agent_completion and context.invalid_agent_case_count > 0


def _invalid_agent_reason(context: _VerdictContext) -> str:
    return (
        f"{context.invalid_agent_case_count}/{context.case_count} cases are invalid "
        "because agent extraction did not complete without fallback."
    )


def _trusted_eligible_endpoint_rate_blocked(context: _VerdictContext) -> bool:
    return (
        context.trusted_eligible_gold_curie_endpoint_count > 0
        and context.trusted_eligible_curie_linked_gold_endpoint_rate
        < _MIN_CURIE_LINKED_GOLD_ENDPOINT_RATE
    )
