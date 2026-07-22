"""Deterministic dual-role validation and measurement."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, cast

from scripts.validation.public_gold.staged_event.context_experiment.role_alignment.evidence import (
    resolve_evidence_items,
)
from scripts.validation.public_gold.staged_event.context_experiment.role_alignment.policy import (
    CORPUS_INFERENCE_RULES,
    OFFICIAL_POLICY_RULES,
    create_projection,
)

DIRECT_ROLE_MAP = {
    "AFFECTED_ENTITY": "THEME",
    "CAUSAL_AGENT": "CAUSE",
    "INSTRUMENT": "INSTRUMENT",
    "CONTEXTUAL_PARTICIPANT": "OTHER",
    "OTHER_EXPLICIT": "OTHER",
    "STIMULUS_OR_OBJECT": "OTHER",
}
MAX_DISAGREEMENT_RATE = 0.20

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.context_experiment.role_alignment.contracts import (
        BenchmarkRoleDecision,
        BenchmarkRoleReview,
        DualRoleTieBreakReview,
        SourceRoleDecision,
        SourceRoleReview,
    )
    from scripts.validation.public_gold.staged_event.context_experiment.role_alignment.panel import (
        PanelCase,
    )


@dataclass(frozen=True, slots=True)
class _CorpusProfile:
    sensitivity_case_ids: frozenset[str]
    sensitivity_cause_count: int

    @property
    def convention_supported(self) -> bool:
        return self.sensitivity_cause_count == len(self.sensitivity_case_ids)


@dataclass(frozen=True, slots=True)
class _CaseEvaluation:
    detail: dict[str, object]
    projection: dict[str, object]
    grounded_items: int
    total_items: int
    cross_view_disagreement: int
    source_direct_match: int
    benchmark_reviewer_match: int
    benchmark_projected_match: int
    causal_overstatement: int
    unsupported_projection: int
    abstentions: int
    critical_abstentions: int
    official_cause_on_noncausal_source: int


def validate_tiebreak(
    *,
    cases: tuple[PanelCase, ...],
    tie_break: DualRoleTieBreakReview,
    disputed_case_ids: set[str],
) -> dict[str, object]:
    tie_by_id = {item.case_id: item for item in tie_break.decisions}
    if set(tie_by_id) != disputed_case_ids:
        raise RoleEvaluationError("tie-break case inventory changed")
    cases_by_id = {case.case_id: case for case in cases}
    resolved: list[str] = []
    unresolved: list[str] = []
    for case_id, decision in tie_by_id.items():
        case = cases_by_id[case_id]
        if decision.policy_rule_id not in OFFICIAL_POLICY_RULES:
            raise RoleEvaluationError(
                f"unknown tie-break policy rule ID: {decision.policy_rule_id}"
            )
        resolve_evidence_items(
            decision.evidence_items,
            source=case.exact_scope,
            scope_start=0,
            scope_end=len(case.exact_scope),
            required_texts=(case.trigger_text, case.participant_text),
        )
        direct = DIRECT_ROLE_MAP.get(decision.source_semantic_role)
        compatible = direct == decision.benchmark_projection_role
        sensitivity_compatible = (
            case.family in {"TARGET_SENSITIVITY", "SENSITIVITY_OR_RESPONSE_TO_DRUG"}
            and decision.source_semantic_role
            in {"STIMULUS_OR_OBJECT", "OTHER_EXPLICIT"}
            and decision.benchmark_projection_role in {"CAUSE", "OTHER"}
        )
        (resolved if compatible or sensitivity_compatible else unresolved).append(
            case_id
        )
    return {
        "initial_disputed_case_ids": sorted(disputed_case_ids),
        "third_blinded_resolved_case_ids": sorted(resolved),
        "third_blinded_unresolved_case_ids": sorted(unresolved),
        "prior_reviews_overwritten": False,
        "third_call_model_independent": False,
    }


class RoleEvaluationError(ValueError):
    """The adjudication output is incomplete, ungrounded, or unauthorized."""


def evaluate_reviews(
    *,
    cases: tuple[PanelCase, ...],
    source_review: SourceRoleReview,
    benchmark_review: BenchmarkRoleReview,
    corpus_cases: tuple[PanelCase, ...] | None = None,
) -> dict[str, object]:
    case_ids = {case.case_id for case in cases}
    source_by_id = _exact_decisions(source_review.decisions, case_ids, "source")
    benchmark_by_id = _exact_decisions(
        benchmark_review.decisions, case_ids, "benchmark"
    )
    profile = _corpus_profile(corpus_cases or cases)
    evaluated = tuple(
        _evaluate_case(
            case=case,
            source=cast("SourceRoleDecision", source_by_id[case.case_id]),
            benchmark=cast("BenchmarkRoleDecision", benchmark_by_id[case.case_id]),
            profile=profile,
        )
        for case in cases
    )
    details = [item.detail for item in evaluated]
    projections = [item.projection for item in evaluated]
    grounded_items = sum(item.grounded_items for item in evaluated)
    total_items = sum(item.total_items for item in evaluated)
    cross_view_disagreements = sum(item.cross_view_disagreement for item in evaluated)
    source_direct_fidelity = sum(item.source_direct_match for item in evaluated)
    benchmark_reviewer_fidelity = sum(
        item.benchmark_reviewer_match for item in evaluated
    )
    benchmark_after = sum(item.benchmark_projected_match for item in evaluated)
    causal_overstatement = sum(item.causal_overstatement for item in evaluated)
    unsupported_projection = sum(item.unsupported_projection for item in evaluated)
    abstentions = sum(item.abstentions for item in evaluated)
    critical_abstentions = sum(item.critical_abstentions for item in evaluated)
    official_cause_on_noncausal_source = sum(
        item.official_cause_on_noncausal_source for item in evaluated
    )

    target = next(item for item in details if item["family"] == "TARGET_SENSITIVITY")
    sensitivity = [
        item
        for item in details
        if item["family"] in {"TARGET_SENSITIVITY", "SENSITIVITY_OR_RESPONSE_TO_DRUG"}
    ]
    explicit = next(
        item for item in details if item["family"] == "EXPLICIT_CAUSATION_CONTROL"
    )
    panel_size = len(cases)
    disagreement_rate = f"{cross_view_disagreements}/{panel_size}"
    acceptance = (
        target["source_semantic_role"] in {"STIMULUS_OR_OBJECT", "OTHER_EXPLICIT"}
        and target["benchmark_projection_role"] == "CAUSE"
        and target["projection_rule_id"] in CORPUS_INFERENCE_RULES
        and all(item["source_semantic_role"] != "CAUSAL_AGENT" for item in sensitivity)
        and all(item["benchmark_projection_role"] == "CAUSE" for item in sensitivity)
        and explicit["source_semantic_role"] == "CAUSAL_AGENT"
        and explicit["benchmark_projection_role"] == "CAUSE"
        and profile.convention_supported
        and grounded_items == total_items
        and cross_view_disagreements / panel_size <= MAX_DISAGREEMENT_RATE
        and causal_overstatement == 0
        and official_cause_on_noncausal_source == 0
        and unsupported_projection == 0
        and critical_abstentions == 0
    )
    if acceptance:
        terminal_decision = "ADVANCE_DUAL_ROLE_PROJECTION"
    elif (
        cross_view_disagreements / panel_size > MAX_DISAGREEMENT_RATE
        or critical_abstentions
    ):
        terminal_decision = "STOP_ROLE_ADJUDICATION_UNRELIABLE"
    else:
        terminal_decision = "STOP_BENCHMARK_ROLE_NOT_SOURCE_GENERAL"
    return {
        "decision": terminal_decision,
        "panel_case_count": panel_size,
        "exact_evidence_grounding_rate": f"{grounded_items}/{total_items}",
        "evidence_grounding_note": (
            "This metric proves exact local span custody, not semantic correctness; "
            "scientific role judgments remain agent-owned."
        ),
        "cross_axis_compatible_count": panel_size - cross_view_disagreements,
        "cross_axis_disagreement_count": cross_view_disagreements,
        "cross_axis_disagreement_rate": disagreement_rate,
        "reviewer_agreement_note": (
            "Reviewers judge different axes; compatibility is not model-independent agreement."
        ),
        "source_semantic_role_distribution": dict(
            Counter(item.source_semantic_role for item in source_review.decisions)
        ),
        "benchmark_role_distribution": dict(
            Counter(
                item.benchmark_projection_role for item in benchmark_review.decisions
            )
        ),
        "source_direct_benchmark_fidelity": f"{source_direct_fidelity}/{panel_size}",
        "benchmark_fidelity_before_projection": (
            f"{benchmark_reviewer_fidelity}/{panel_size}"
        ),
        "benchmark_fidelity_after_projection": f"{benchmark_after}/{panel_size}",
        "sensitivity_corpus_convention": {
            "eligible_case_count": len(profile.sensitivity_case_ids),
            "cause_role_count": profile.sensitivity_cause_count,
            "unanimous": profile.convention_supported,
            "selection": "complete exposed eligible set regardless of gold role",
        },
        "explicit_causation_preserved": (
            explicit["source_semantic_role"] == "CAUSAL_AGENT"
            and explicit["benchmark_projection_role"] == "CAUSE"
        ),
        "causal_overstatement_count": causal_overstatement,
        "official_cause_assignment_to_noncausal_source_count": (
            official_cause_on_noncausal_source
        ),
        "unsupported_projection_count": unsupported_projection,
        "abstention_count": abstentions,
        "same_model_family_independent_calls": True,
        "model_independent_review": False,
        "all_review_only": True,
        "graph_promotion_allowed": False,
        "details": details,
        "projections": projections,
    }


def _corpus_profile(cases: tuple[PanelCase, ...]) -> _CorpusProfile:
    sensitivity = tuple(
        case
        for case in cases
        if case.family in {"TARGET_SENSITIVITY", "SENSITIVITY_OR_RESPONSE_TO_DRUG"}
    )
    return _CorpusProfile(
        sensitivity_case_ids=frozenset(case.case_id for case in sensitivity),
        sensitivity_cause_count=sum(
            _normalized_gold(case.public_gold_role) == "CAUSE" for case in sensitivity
        ),
    )


def _evaluate_case(
    *,
    case: PanelCase,
    source: SourceRoleDecision,
    benchmark: BenchmarkRoleDecision,
    profile: _CorpusProfile,
) -> _CaseEvaluation:
    if benchmark.policy_rule_id not in OFFICIAL_POLICY_RULES:
        raise RoleEvaluationError(f"unknown policy rule ID: {benchmark.policy_rule_id}")
    grounded = sum(
        len(
            resolve_evidence_items(
                decision.evidence_items,
                source=case.exact_scope,
                scope_start=0,
                scope_end=len(case.exact_scope),
                required_texts=(case.trigger_text, case.participant_text),
            )
        )
        for decision in (source, benchmark)
    )
    total = len(source.evidence_items) + len(benchmark.evidence_items)
    gold = _normalized_gold(case.public_gold_role)
    direct = DIRECT_ROLE_MAP.get(source.source_semantic_role)
    sensitivity_case = case.case_id in profile.sensitivity_case_ids
    use_corpus_projection = (
        sensitivity_case
        and profile.convention_supported
        and source.source_semantic_role in {"STIMULUS_OR_OBJECT", "OTHER_EXPLICIT"}
    )
    projection_rule_id = (
        "CG-CORPUS-SENSITIVITY-OBJECT-AS-CAUSE"
        if use_corpus_projection
        else benchmark.policy_rule_id
    )
    projected_role = (
        "CAUSE" if use_corpus_projection else benchmark.benchmark_projection_role
    )
    projection = create_projection(
        case_id=case.case_id,
        source_semantic_role=source.source_semantic_role,
        benchmark_projection_role=projected_role,
        policy_rule_id=projection_rule_id,
    )
    source_abstained = source.source_semantic_role == "ABSTAIN"
    benchmark_abstained = benchmark.benchmark_projection_role == "ABSTAIN"
    cross_view_compatible = (
        direct == benchmark.benchmark_projection_role or use_corpus_projection
    )
    detail = {
        "case_id": case.case_id,
        "family": case.family,
        "source_semantic_role": source.source_semantic_role,
        "benchmark_reviewer_role": benchmark.benchmark_projection_role,
        "benchmark_projection_role": projected_role,
        "public_gold_role": gold,
        "reviewer_policy_rule_id": benchmark.policy_rule_id,
        "projection_rule_id": projection_rule_id,
        "cross_view_compatible": cross_view_compatible,
        "benchmark_match_before_projection": benchmark.benchmark_projection_role
        == gold,
        "benchmark_match_after_projection": projected_role == gold,
        "projection": asdict(projection),
    }
    return _CaseEvaluation(
        detail=detail,
        projection=asdict(projection),
        grounded_items=grounded,
        total_items=total,
        cross_view_disagreement=int(not cross_view_compatible),
        source_direct_match=int(direct == gold),
        benchmark_reviewer_match=int(benchmark.benchmark_projection_role == gold),
        benchmark_projected_match=int(projected_role == gold),
        causal_overstatement=int(
            source.source_semantic_role != "CAUSAL_AGENT"
            and projected_role == "CAUSE"
            and projection.projection_basis != "EVALUATION_ONLY_CORPUS_INFERENCE"
        ),
        unsupported_projection=int(projected_role != gold),
        abstentions=int(source_abstained) + int(benchmark_abstained),
        critical_abstentions=int(source_abstained)
        + int(benchmark_abstained and not sensitivity_case),
        official_cause_on_noncausal_source=int(
            source.source_semantic_role != "CAUSAL_AGENT"
            and benchmark.benchmark_projection_role == "CAUSE"
        ),
    )


def _exact_decisions(
    decisions: tuple[SourceRoleDecision, ...] | tuple[BenchmarkRoleDecision, ...],
    expected: set[str],
    label: str,
) -> dict[str, SourceRoleDecision | BenchmarkRoleDecision]:
    by_id = {item.case_id: item for item in decisions}
    if set(by_id) != expected:
        raise RoleEvaluationError(f"{label} review case inventory changed")
    return by_id


def _normalized_gold(role: str) -> str:
    if role.startswith("Theme"):
        return "THEME"
    if role.startswith("Cause"):
        return "CAUSE"
    if role.startswith("Instrument"):
        return "INSTRUMENT"
    return "OTHER"


__all__ = ["RoleEvaluationError", "evaluate_reviews", "validate_tiebreak"]
