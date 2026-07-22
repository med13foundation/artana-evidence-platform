"""Deterministic structure, grounding, and frozen-reference evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.context_experiment.role_alignment.policy import (
    create_projection,
)
from scripts.validation.public_gold.staged_event.generalization.anchors import (
    GeneralizationAnchorError,
    resolve_evidence,
    resolve_in_context,
)
from scripts.validation.public_gold.staged_event.generalization.span_identity import (
    source_spans_equivalent,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.contracts import (
        StagedGeneralizationOutput,
    )
    from scripts.validation.public_gold.staged_event.generalization.panel import (
        GeneralizationCase,
    )


@dataclass(frozen=True, slots=True)
class CaseMetrics:
    case_id: str
    family: str
    passed: bool
    complete_event_recovery: bool
    participant_role_fidelity: bool
    nested_event_structure: bool
    direction_fidelity: bool
    comparison_fidelity: bool
    polarity_fidelity: bool
    uncertainty_fidelity: bool
    statistical_fidelity: bool
    exact_evidence_grounding: bool
    unsupported_claim_count: int
    contradiction_count: int
    benchmark_fidelity_before_projection: str
    benchmark_fidelity_after_projection: str
    projection_review_only: bool
    failure_reasons: tuple[str, ...]


def evaluate_case(
    case: GeneralizationCase, output: StagedGeneralizationOutput
) -> CaseMetrics:
    reasons: list[str] = []
    if output.case_id != case.case_id:
        reasons.append("case identity changed")
    grounding = _grounding(case, output, reasons)
    event_map, unsupported_events = _event_mapping(case, output, reasons)
    participant_map, unsupported_participants = _participant_mapping(
        case, output, reasons
    )
    expected_event_count = len(case.reference.events)
    expected_participant_count = len(case.reference.participants)
    event_inventory_exact = (
        len(event_map) == expected_event_count and unsupported_events == 0
    )
    participant_inventory_exact = (
        len(participant_map) == expected_participant_count
        and unsupported_participants == 0
    )
    links_exact, nested_exact, roles_exact, unsupported_links = _links(
        case,
        output,
        event_map=event_map,
        participant_map=participant_map,
        reasons=reasons,
    )
    root_exact = event_map.get(output.root_event_id) == case.reference.root_event_key
    if not root_exact:
        reasons.append("root event differs from reference")
    axes = _axes(case, output, event_map=event_map, reasons=reasons)
    complete = (
        output.completeness == "COMPLETE"
        and event_inventory_exact
        and participant_inventory_exact
        and links_exact
        and root_exact
    )
    if output.completeness != "COMPLETE":
        reasons.append(f"agent completeness is {output.completeness}")
    benchmark_before, benchmark_after, projection_review_only = _benchmark(case, output)
    unsupported = unsupported_events + unsupported_participants + unsupported_links
    contradictions = int(
        output.completeness == "CONTRADICTED" or not all(axes.values())
    )
    passed = (
        complete
        and roles_exact
        and nested_exact
        and all(axes.values())
        and grounding
        and unsupported == 0
        and contradictions == 0
        and projection_review_only
    )
    return CaseMetrics(
        case_id=case.case_id,
        family=case.family,
        passed=passed,
        complete_event_recovery=complete,
        participant_role_fidelity=roles_exact and participant_inventory_exact,
        nested_event_structure=nested_exact,
        direction_fidelity=axes["direction"],
        comparison_fidelity=axes["comparison"],
        polarity_fidelity=axes["polarity"],
        uncertainty_fidelity=axes["uncertainty"],
        statistical_fidelity=axes["statistics"],
        exact_evidence_grounding=grounding,
        unsupported_claim_count=unsupported,
        contradiction_count=contradictions,
        benchmark_fidelity_before_projection=benchmark_before,
        benchmark_fidelity_after_projection=benchmark_after,
        projection_review_only=projection_review_only,
        failure_reasons=tuple(dict.fromkeys(reasons)),
    )


def aggregate(metrics: tuple[CaseMetrics, ...]) -> dict[str, object]:
    passed = sum(item.passed for item in metrics)
    unsupported = sum(item.unsupported_claim_count for item in metrics)
    contradictions = sum(item.contradiction_count for item in metrics)
    decision = (
        "ADVANCE_STAGED_GENERALIZATION"
        if passed == len(metrics) and unsupported == 0 and contradictions == 0
        else "PIVOT_WITH_EVIDENCE"
    )
    return {
        "decision": decision,
        "case_count": len(metrics),
        "passed_case_count": passed,
        "complete_event_recovery": _ratio(metrics, "complete_event_recovery"),
        "participant_role_fidelity": _ratio(metrics, "participant_role_fidelity"),
        "nested_event_structure": _ratio(metrics, "nested_event_structure"),
        "direction_fidelity": _ratio(metrics, "direction_fidelity"),
        "comparison_fidelity": _ratio(metrics, "comparison_fidelity"),
        "polarity_fidelity": _ratio(metrics, "polarity_fidelity"),
        "uncertainty_fidelity": _ratio(metrics, "uncertainty_fidelity"),
        "statistical_fidelity": _ratio(metrics, "statistical_fidelity"),
        "exact_evidence_grounding": _ratio(metrics, "exact_evidence_grounding"),
        "unsupported_claim_count": unsupported,
        "contradiction_count": contradictions,
        "cases": [asdict(item) for item in metrics],
        "qualification_credit": False,
        "review_only": True,
        "trusted_promotion": False,
        "graph_writes": 0,
    }


def _grounding(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    reasons: list[str],
) -> bool:
    try:
        for event in output.inventory:
            resolve_in_context(
                source=case.source,
                context_start=case.context_start,
                context_end=case.context_end,
                exact_evidence=event.exact_evidence,
                exact_text=event.trigger_text,
            )
        for participant in output.participants:
            resolve_in_context(
                source=case.source,
                context_start=case.context_start,
                context_end=case.context_end,
                exact_evidence=participant.exact_evidence,
                exact_text=participant.exact_text,
            )
        for axes in output.semantic_axes:
            for exact_text in axes.evidence_items:
                resolve_evidence(
                    source=case.source,
                    context_start=case.context_start,
                    context_end=case.context_end,
                    exact_text=exact_text,
                )
            for observation in axes.statistical_observations:
                if observation.exact_text is not None:
                    resolve_evidence(
                        source=case.source,
                        context_start=case.context_start,
                        context_end=case.context_end,
                        exact_text=observation.exact_text,
                    )
    except GeneralizationAnchorError as exc:
        reasons.append(f"evidence grounding failed: {exc}")
        return False
    return True


def _event_mapping(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    reasons: list[str],
) -> tuple[dict[str, str], int]:
    mapping: dict[str, str] = {}
    unsupported = 0
    for actual in output.inventory:
        matches = [
            expected
            for expected in case.reference.events
            if actual.event_type == expected.event_type
            and any(
                source_spans_equivalent(
                    source=actual.exact_evidence,
                    scope_start=0,
                    scope_end=len(actual.exact_evidence),
                    actual_text=actual.trigger_text,
                    expected_text=trigger,
                )
                for trigger in expected.acceptable_triggers
            )
        ]
        if len(matches) != 1 or matches[0].event_key in mapping.values():
            unsupported += 1
            reasons.append(
                f"unsupported or duplicate event: {actual.event_type}/{actual.trigger_text}"
            )
            continue
        mapping[actual.event_id] = matches[0].event_key
    missing = {item.event_key for item in case.reference.events} - set(mapping.values())
    if missing:
        reasons.append(f"missing events: {sorted(missing)}")
    return mapping, unsupported


def _participant_mapping(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    reasons: list[str],
) -> tuple[dict[str, str], int]:
    mapping: dict[str, str] = {}
    unsupported = 0
    for actual in output.participants:
        matches = [
            expected
            for expected in case.reference.participants
            if actual.entity_type == expected.entity_type
            and any(
                source_spans_equivalent(
                    source=actual.exact_evidence,
                    scope_start=0,
                    scope_end=len(actual.exact_evidence),
                    actual_text=actual.exact_text,
                    expected_text=acceptable_text,
                )
                for acceptable_text in expected.acceptable_texts
            )
        ]
        if len(matches) != 1 or matches[0].participant_key in mapping.values():
            unsupported += 1
            reasons.append(
                f"unsupported or duplicate participant: {actual.entity_type}/{actual.exact_text}"
            )
            continue
        mapping[actual.participant_id] = matches[0].participant_key
    missing = {item.participant_key for item in case.reference.participants} - set(
        mapping.values()
    )
    if missing:
        reasons.append(f"missing participants: {sorted(missing)}")
    return mapping, unsupported


def _links(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    *,
    event_map: dict[str, str],
    participant_map: dict[str, str],
    reasons: list[str],
) -> tuple[bool, bool, bool, int]:
    actual: set[tuple[str, str, str, str]] = set()
    for event in output.links:
        event_key = event_map.get(event.event_id, f"UNKNOWN:{event.event_id}")
        for argument in event.arguments:
            targets = (
                participant_map if argument.target_kind == "PARTICIPANT" else event_map
            )
            target_key = targets.get(
                argument.target_id, f"UNKNOWN:{argument.target_id}"
            )
            actual.add((event_key, argument.role, argument.target_kind, target_key))
    expected = {
        (item.event_key, item.role, item.target_kind, item.target_key)
        for item in case.reference.arguments
    }
    if actual != expected:
        reasons.append("typed event arguments differ from frozen reference")
    actual_event_edges = {item for item in actual if item[2] == "EVENT"}
    expected_event_edges = {item for item in expected if item[2] == "EVENT"}
    participant_actual = {item for item in actual if item[2] == "PARTICIPANT"}
    participant_expected = {item for item in expected if item[2] == "PARTICIPANT"}
    return (
        actual == expected,
        actual_event_edges == expected_event_edges,
        participant_actual == participant_expected,
        len(actual - expected),
    )


def _axes(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    *,
    event_map: dict[str, str],
    reasons: list[str],
) -> dict[str, bool]:
    actual = {event_map.get(item.event_id): item for item in output.semantic_axes}
    fidelity = {
        "direction": True,
        "comparison": True,
        "polarity": True,
        "uncertainty": True,
        "statistics": True,
    }
    for expected in case.reference.axes:
        item = actual.get(expected.event_key)
        if item is None:
            for key in fidelity:
                fidelity[key] = False
            reasons.append(f"semantic axes absent for {expected.event_key}")
            continue
        fidelity["direction"] &= item.direction == expected.direction
        fidelity["comparison"] &= item.comparison == expected.comparison
        fidelity["polarity"] &= item.polarity == expected.polarity
        fidelity["uncertainty"] &= item.uncertainty == expected.uncertainty
        observation_types = tuple(
            observation.observation_type
            for observation in item.statistical_observations
        )
        observation_texts = tuple(
            observation.exact_text
            for observation in item.statistical_observations
            if observation.exact_text is not None
        )
        statistical_spans_match = (
            not observation_texts and not expected.acceptable_statistical_texts
        ) or (
            len(observation_texts) == 1
            and any(
                source_spans_equivalent(
                    source=case.source,
                    scope_start=case.context_start,
                    scope_end=case.context_end,
                    actual_text=observation_texts[0],
                    expected_text=acceptable_text,
                )
                for acceptable_text in expected.acceptable_statistical_texts
            )
        )
        fidelity["statistics"] &= (
            observation_types == (expected.statistical_type,)
            and statistical_spans_match
            and item.author_interpretation == expected.author_interpretation
        )
    for axis, passed in fidelity.items():
        if not passed:
            reasons.append(f"{axis} fidelity failed")
    return fidelity


def _benchmark(
    case: GeneralizationCase, output: StagedGeneralizationOutput
) -> tuple[str, str, bool]:
    if case.family != "DRUG_SENSITIVITY":
        return "NOT_APPLICABLE", "NOT_APPLICABLE", True
    sensitivity_events = [
        event
        for event in output.inventory
        if event.event_type == "REGULATION" and event.trigger_text == "sensitivity"
    ]
    if len(sensitivity_events) != 1:
        return "0/1", "0/1", True
    sensitivity = sensitivity_events[0]
    links = next(item for item in output.links if item.event_id == sensitivity.event_id)
    drug_ids = {
        item.participant_id
        for item in output.participants
        if item.entity_type == "SIMPLE_CHEMICAL" and item.exact_text == "5-FU"
    }
    source_role = next(
        (item.role for item in links.arguments if item.target_id in drug_ids),
        None,
    )
    if source_role not in {"STIMULUS_OR_OBJECT", "CONTEXTUAL_PARTICIPANT"}:
        return "0/1", "0/1", True
    projection = create_projection(
        case_id=case.case_id,
        source_semantic_role=(
            "STIMULUS_OR_OBJECT"
            if source_role == "STIMULUS_OR_OBJECT"
            else "OTHER_EXPLICIT"
        ),
        benchmark_projection_role="CAUSE",
        policy_rule_id="CG-CORPUS-SENSITIVITY-OBJECT-AS-CAUSE",
    )
    return (
        "0/1",
        "1/1",
        projection.review_only and not projection.graph_promotion_allowed,
    )


def _ratio(metrics: tuple[CaseMetrics, ...], field: str) -> str:
    numerator = sum(bool(getattr(item, field)) for item in metrics)
    return f"{numerator}/{len(metrics)}"


__all__ = ["CaseMetrics", "aggregate", "evaluate_case"]
