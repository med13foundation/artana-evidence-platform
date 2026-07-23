"""Dual-lane evaluator V2 with explicit occurrence identity."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.generalization.evaluation import (
    _benchmark,
)
from scripts.validation.public_gold.staged_event.generalization.grading.evaluation import (
    DualLaneCaseMetrics,
)
from scripts.validation.public_gold.staged_event.generalization.grading.evaluation import (
    aggregate as aggregate_v1,
)
from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.bindings import (
    validate_bindings,
)
from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.mapping import (
    map_events,
    map_participants,
)
from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.semantics import (
    evaluate_axes,
)
from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.structure import (
    evaluate_links,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.contracts import (
        StagedGeneralizationOutput,
    )
    from scripts.validation.public_gold.staged_event.generalization.grading.contracts import (
        FrozenCasePolicy,
    )
    from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.contracts import (
        OccurrenceAwareBindings,
    )
    from scripts.validation.public_gold.staged_event.generalization.panel import (
        GeneralizationCase,
    )

EVALUATOR_VERSION = "artana.staged_generalization.occurrence_evaluator.v2"


def evaluate_case(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    bindings: OccurrenceAwareBindings,
    policy: FrozenCasePolicy,
) -> DualLaneCaseMetrics:
    """Evaluate one case only after complete occurrence validation."""

    validated = validate_bindings(case, output, bindings)
    reasons: list[str] = []
    event_map, unsupported_events = map_events(case, output, validated, reasons)
    participants = map_participants(case, output, policy, validated, reasons)
    links = evaluate_links(
        case,
        output,
        event_map=event_map,
        participants=participants,
        reasons=reasons,
    )
    root_exact = event_map.get(output.root_event_id) == case.reference.root_event_key
    if not root_exact:
        reasons.append("root event differs from required core")
    axes = evaluate_axes(
        case,
        output,
        event_map=event_map,
        validated=validated,
        reasons=reasons,
    )
    event_core_complete = len(event_map) == len(case.reference.events)
    participant_core_complete = len(participants.core) == len(
        case.reference.participants
    )
    required_core_complete = (
        output.completeness == "COMPLETE"
        and event_core_complete
        and participant_core_complete
        and links.core_complete
        and root_exact
    )
    if output.completeness != "COMPLETE":
        reasons.append(f"agent completeness is {output.completeness}")
    unsupported = unsupported_events + participants.unsupported + links.unsupported
    ambiguous = participants.ambiguous_nodes + links.ambiguous_context_links
    contradictions = int(
        output.completeness == "CONTRADICTED" or not all(axes.values())
    )
    permitted = participants.permitted_nodes + links.permitted_context_links
    roles_valid = links.roles_valid and participant_core_complete
    passed = (
        required_core_complete
        and roles_valid
        and links.nested_exact
        and all(axes.values())
        and unsupported == 0
        and ambiguous == 0
        and contradictions == 0
    )
    source_validity = (
        "PASS"
        if passed
        else "REVIEW_ONLY"
        if ambiguous and unsupported == 0 and contradictions == 0
        else "FAIL"
    )
    benchmark_before, benchmark_after, projection_review_only = _benchmark(case, output)
    return DualLaneCaseMetrics(
        case_id=case.case_id,
        family=case.family,
        passed=passed,
        required_core_complete=required_core_complete,
        source_discovery_validity=source_validity,
        complete_event_recovery=required_core_complete and unsupported_events == 0,
        participant_role_fidelity=roles_valid and unsupported == 0 and ambiguous == 0,
        nested_event_structure=links.nested_exact,
        direction_fidelity=axes["direction"],
        comparison_fidelity=axes["comparison"],
        polarity_fidelity=axes["polarity"],
        uncertainty_fidelity=axes["uncertainty"],
        statistical_fidelity=axes["statistics"],
        exact_evidence_grounding=True,
        permitted_context_count=permitted,
        ambiguous_context_count=ambiguous,
        unsupported_claim_count=unsupported,
        contradiction_count=contradictions,
        benchmark_fidelity_before_projection=benchmark_before,
        benchmark_fidelity_after_projection=benchmark_after,
        benchmark_lane_separate=True,
        projection_review_only=projection_review_only,
        failure_reasons=tuple(dict.fromkeys(reasons)),
    )


def aggregate(metrics: tuple[DualLaneCaseMetrics, ...]) -> dict[str, object]:
    """Aggregate with the unchanged rules and an explicit evaluator version."""

    result = aggregate_v1(metrics)
    return {"evaluator_version": EVALUATOR_VERSION, **result}


__all__ = ["EVALUATOR_VERSION", "aggregate", "evaluate_case"]
