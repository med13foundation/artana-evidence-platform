"""Dual-lane evaluation with exact core and independently allowed context."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.generalization.evaluation import (
    _axes,
    _benchmark,
    _event_mapping,
    _grounding,
)
from scripts.validation.public_gold.staged_event.generalization.span_identity import (
    source_spans_equivalent,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.contracts import (
        EventArgument,
        StagedGeneralizationOutput,
    )
    from scripts.validation.public_gold.staged_event.generalization.grading.contracts import (
        FrozenCasePolicy,
        FrozenContextParticipant,
    )
    from scripts.validation.public_gold.staged_event.generalization.panel import (
        GeneralizationCase,
    )


@dataclass(frozen=True, slots=True)
class DualLaneCaseMetrics:
    case_id: str
    family: str
    passed: bool
    required_core_complete: bool
    source_discovery_validity: str
    complete_event_recovery: bool
    participant_role_fidelity: bool
    nested_event_structure: bool
    direction_fidelity: bool
    comparison_fidelity: bool
    polarity_fidelity: bool
    uncertainty_fidelity: bool
    statistical_fidelity: bool
    exact_evidence_grounding: bool
    permitted_context_count: int
    ambiguous_context_count: int
    unsupported_claim_count: int
    contradiction_count: int
    benchmark_fidelity_before_projection: str
    benchmark_fidelity_after_projection: str
    benchmark_lane_separate: bool
    projection_review_only: bool
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ParticipantMapping:
    core: dict[str, str]
    context: dict[str, FrozenContextParticipant]
    unsupported: int
    permitted_nodes: int
    ambiguous_nodes: int


@dataclass(frozen=True, slots=True)
class _LinkMetrics:
    core_complete: bool
    nested_exact: bool
    roles_valid: bool
    unsupported: int
    permitted_context_links: int
    ambiguous_context_links: int


def evaluate_case(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    policy: FrozenCasePolicy,
) -> DualLaneCaseMetrics:
    reasons: list[str] = []
    if output.case_id != case.case_id or policy.case_id != case.case_id:
        reasons.append("case identity changed")
    grounding = _grounding(case, output, reasons)
    event_map, unsupported_events = _event_mapping(case, output, reasons)
    participants = _participant_mapping(case, output, policy, reasons)
    links = _links(
        case,
        output,
        event_map=event_map,
        participants=participants,
        reasons=reasons,
    )
    root_exact = event_map.get(output.root_event_id) == case.reference.root_event_key
    if not root_exact:
        reasons.append("root event differs from required core")
    axes = _axes(case, output, event_map=event_map, reasons=reasons)
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
        and grounding
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
        exact_evidence_grounding=grounding,
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
    passed = sum(item.passed for item in metrics)
    unsupported = sum(item.unsupported_claim_count for item in metrics)
    ambiguous = sum(item.ambiguous_context_count for item in metrics)
    contradictions = sum(item.contradiction_count for item in metrics)
    decision = (
        "ADVANCE_STAGED_GENERALIZATION"
        if passed == len(metrics)
        and unsupported == 0
        and ambiguous == 0
        and contradictions == 0
        else "PIVOT_WITH_EVIDENCE"
    )
    return {
        "schema_version": "artana.staged_generalization.dual_lane_result.v1",
        "decision": decision,
        "source_lane_decision": (
            "PASS" if passed == len(metrics) else "FAIL_OR_REVIEW_ONLY"
        ),
        "benchmark_lane": "SEPARATE_EVALUATION_ONLY_REVIEW_ONLY",
        "case_count": len(metrics),
        "passed_case_count": passed,
        "required_core_complete": _ratio(metrics, "required_core_complete"),
        "complete_event_recovery": _ratio(metrics, "complete_event_recovery"),
        "participant_role_fidelity": _ratio(metrics, "participant_role_fidelity"),
        "nested_event_structure": _ratio(metrics, "nested_event_structure"),
        "direction_fidelity": _ratio(metrics, "direction_fidelity"),
        "comparison_fidelity": _ratio(metrics, "comparison_fidelity"),
        "polarity_fidelity": _ratio(metrics, "polarity_fidelity"),
        "uncertainty_fidelity": _ratio(metrics, "uncertainty_fidelity"),
        "statistical_fidelity": _ratio(metrics, "statistical_fidelity"),
        "exact_evidence_grounding": _ratio(metrics, "exact_evidence_grounding"),
        "permitted_context_count": sum(
            item.permitted_context_count for item in metrics
        ),
        "ambiguous_context_count": ambiguous,
        "unsupported_claim_count": unsupported,
        "contradiction_count": contradictions,
        "cases": [asdict(item) for item in metrics],
        "qualification_credit": False,
        "review_only": True,
        "trusted_promotion": False,
        "graph_writes": 0,
    }


def _participant_mapping(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    policy: FrozenCasePolicy,
    reasons: list[str],
) -> _ParticipantMapping:
    core: dict[str, str] = {}
    context: dict[str, FrozenContextParticipant] = {}
    used_context: set[str] = set()
    unsupported = 0
    permitted_nodes = 0
    ambiguous_nodes = 0
    for actual in output.participants:
        core_matches = [
            expected
            for expected in case.reference.participants
            if actual.entity_type == expected.entity_type
            and any(
                _texts_match(actual.exact_evidence, actual.exact_text, acceptable)
                for acceptable in expected.acceptable_texts
            )
        ]
        if (
            len(core_matches) == 1
            and core_matches[0].participant_key not in core.values()
        ):
            core[actual.participant_id] = core_matches[0].participant_key
            continue
        context_matches = [
            expected
            for expected in policy.contextual_participants
            if actual.entity_type == expected.entity_type
            and any(
                _texts_match(actual.exact_evidence, actual.exact_text, acceptable)
                for acceptable in expected.acceptable_texts
            )
        ]
        if len(context_matches) != 1:
            unsupported += 1
            reasons.append(
                "unsupported or duplicate participant: "
                f"{actual.entity_type}/{actual.exact_text}"
            )
            continue
        matched = context_matches[0]
        if matched.judgment_id in used_context:
            unsupported += 1
            reasons.append(f"duplicate contextual participant: {matched.judgment_id}")
            continue
        used_context.add(matched.judgment_id)
        context[actual.participant_id] = matched
        if matched.classification == "PERMITTED_CONTEXT":
            permitted_nodes += 1
        elif matched.classification == "AMBIGUOUS_REVIEW_ONLY":
            ambiguous_nodes += 1
            reasons.append(f"ambiguous contextual participant: {matched.judgment_id}")
        else:
            unsupported += 1
            reasons.append(f"forbidden contextual participant: {matched.judgment_id}")
    missing = {item.participant_key for item in case.reference.participants} - set(
        core.values()
    )
    if missing:
        reasons.append(f"missing required core participants: {sorted(missing)}")
    return _ParticipantMapping(
        core=core,
        context=context,
        unsupported=unsupported,
        permitted_nodes=permitted_nodes,
        ambiguous_nodes=ambiguous_nodes,
    )


def _links(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    *,
    event_map: dict[str, str],
    participants: _ParticipantMapping,
    reasons: list[str],
) -> _LinkMetrics:
    actual_items = _actual_link_items(output, event_map, participants)
    actual = set(actual_items)
    duplicate_links = len(actual_items) - len(actual)
    expected_core = {
        (item.event_key, item.role, item.target_kind, item.target_key)
        for item in case.reference.arguments
    }
    allowed_context = {
        (
            argument.event_key,
            argument.role,
            "PARTICIPANT",
            f"CONTEXT:{participant.judgment_id}",
        )
        for participant in participants.context.values()
        for argument in participant.allowed_arguments
        if participant.classification != "FORBIDDEN"
    }
    missing_core = expected_core - actual
    if missing_core:
        reasons.append("required core event arguments are missing")
    unsupported_items = actual - expected_core - allowed_context
    unsupported = len(unsupported_items) + duplicate_links
    if unsupported_items:
        reasons.append("typed event arguments exceed core-plus-context policy")
    if duplicate_links:
        reasons.append("duplicate typed event arguments are unsupported")
    permitted_context_links = 0
    ambiguous_context_links = 0
    orphaned_context = 0
    for participant_id, participant in participants.context.items():
        context_target = f"CONTEXT:{participant.judgment_id}"
        matching = {item for item in actual if item[3] == context_target}
        if not matching:
            orphaned_context += 1
            reasons.append(f"context participant is unlinked: {participant_id}")
        elif participant.classification == "PERMITTED_CONTEXT":
            permitted_context_links += len(matching & allowed_context)
        elif participant.classification == "AMBIGUOUS_REVIEW_ONLY":
            ambiguous_context_links += len(matching & allowed_context)
    unsupported += orphaned_context
    actual_event_edges = {item for item in actual if item[2] == "EVENT"}
    expected_event_edges = {item for item in expected_core if item[2] == "EVENT"}
    nested_exact = actual_event_edges == expected_event_edges
    if not nested_exact:
        reasons.append("nested event structure differs from required core")
    roles_valid = not missing_core and unsupported == 0
    return _LinkMetrics(
        core_complete=not missing_core,
        nested_exact=nested_exact,
        roles_valid=roles_valid,
        unsupported=unsupported,
        permitted_context_links=permitted_context_links,
        ambiguous_context_links=ambiguous_context_links,
    )


def _actual_link_items(
    output: StagedGeneralizationOutput,
    event_map: dict[str, str],
    participants: _ParticipantMapping,
) -> list[tuple[str, str, str, str]]:
    actual_items: list[tuple[str, str, str, str]] = []
    for event in output.links:
        event_key = event_map.get(event.event_id, f"UNKNOWN:{event.event_id}")
        actual_items.extend(
            (
                event_key,
                argument.role,
                argument.target_kind,
                _target_key(argument, event_map, participants),
            )
            for argument in event.arguments
        )
    return actual_items


def _target_key(
    argument: EventArgument,
    event_map: dict[str, str],
    participants: _ParticipantMapping,
) -> str:
    if argument.target_kind == "EVENT":
        return event_map.get(
            argument.target_id,
            f"UNKNOWN:{argument.target_id}",
        )
    if argument.target_id in participants.core:
        return participants.core[argument.target_id]
    if argument.target_id in participants.context:
        judgment = participants.context[argument.target_id]
        return f"CONTEXT:{judgment.judgment_id}"
    return f"UNKNOWN:{argument.target_id}"


def _texts_match(evidence: str, actual: str, expected: str) -> bool:
    return source_spans_equivalent(
        source=evidence,
        scope_start=0,
        scope_end=len(evidence),
        actual_text=actual,
        expected_text=expected,
    )


def _ratio(metrics: tuple[DualLaneCaseMetrics, ...], field: str) -> str:
    numerator = sum(bool(getattr(item, field)) for item in metrics)
    return f"{numerator}/{len(metrics)}"


__all__ = ["DualLaneCaseMetrics", "aggregate", "evaluate_case"]
