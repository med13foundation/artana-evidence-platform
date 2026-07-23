"""V13 source-semantic nested evaluation with nonblocking CG projection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal

from scripts.validation.public_gold.staged_event.generalization.anchors import (
    GeneralizationAnchorError,
    resolve_evidence,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.evaluation import (
    V12CaseMetrics,
    evaluate_v12_case,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.cg_projection import (
    project_actual_root_dependency_chain,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.contracts import (
    SourceEventKey,
    SourceParticipantKey,
    V13NestedTwoLaneContract,
    frozen_v12_contract,
)
from scripts.validation.public_gold.staged_event.generalization.span_identity import (
    ExactSpan,
    SpanIdentityError,
    resolve_unique_span,
    token_bounded_spans,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.contracts import (
        ParticipantNode,
        StagedGeneralizationOutput,
    )
    from scripts.validation.public_gold.staged_event.generalization.grading.contracts import (
        FrozenCasePolicy,
    )
    from scripts.validation.public_gold.staged_event.generalization.panel import (
        GeneralizationCase,
    )

LaneStatus = Literal["PASS", "FAIL", "NOT_APPLICABLE"]
RootSelectionStatus = Literal["PASS", "FAIL", "NOT_APPLICABLE"]
CompletenessStatus = Literal["COMPLETE", "INCOMPLETE", "CONTRADICTED", "ABSTAIN"]
BenchmarkProjectionScope = Literal[
    "DRUG_FOCUS_EVENT",
    "EXACT_CG_ROOT_DEPENDENCY_CHAIN",
    "NOT_APPLICABLE",
]
FullFocusCgStatus = Literal[
    "NOT_MEASURED_UNREPRESENTABLE",
    "NOT_APPLICABLE",
]
_NESTED_CASE_ID = "generalization-explicit-nested-cause"
_DRUG_CASE_ID = "generalization-drug-sensitivity"
_CG_ONLY_FAILURE = "exact CG focus projection is unavailable"
_ROOT_ONLY_FAILURE_REASONS = frozenset(
    {
        "highlighted sensitivity event is not the source root",
        "root event differs from required core",
    }
)


@dataclass(frozen=True, slots=True)
class V13CaseMetrics:
    case_id: str
    passed: bool
    focus_event_passed: bool
    source_semantic_status: LaneStatus
    benchmark_projection_status: LaneStatus
    benchmark_projection_scope: BenchmarkProjectionScope
    full_focus_cg_status: FullFocusCgStatus
    mandatory_participants_passed: bool
    participant_roles_passed: bool
    semantic_axes_passed: bool
    exact_evidence_grounding: bool
    unsupported_extraction_count: int
    permitted_context_count: int
    benchmark_projection: dict[str, object] | None
    failure_reasons: tuple[str, ...]
    historical_grader_passed: bool | None
    root_selection_status: RootSelectionStatus
    completeness: CompletenessStatus
    source_dimensions_except_root_passed: bool
    root_only_failure: bool
    qualification_credit: bool = False
    graph_writes: int = 0
    trusted_promotion: bool = False

    def as_json(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class _EventMapping:
    by_key: dict[SourceEventKey, str]
    unsupported: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ParticipantMapping:
    by_key: dict[SourceParticipantKey, str]
    unsupported: tuple[str, ...]


def evaluate_v13_case(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    policy: FrozenCasePolicy,
    contract: V13NestedTwoLaneContract,
) -> V13CaseMetrics:
    """Evaluate only the V13 nested boundary; delegate all other cases to V12."""
    if case.case_id != _NESTED_CASE_ID:
        legacy = evaluate_v12_case(
            case,
            output,
            policy,
            frozen_v12_contract(contract),
        )
        return _from_v12(legacy, completeness=output.completeness)
    return _evaluate_nested(case, output, contract)


def resolve_focus_local_occurrence(
    case: GeneralizationCase,
    *,
    exact_evidence: str,
    exact_text: str,
) -> ExactSpan:
    """Resolve an occurrence only when exactly one match lies in the focus."""
    evidence = resolve_unique_span(
        source=case.source,
        scope_start=case.context_start,
        scope_end=case.context_end,
        exact_text=exact_evidence,
    )
    matches = token_bounded_spans(
        source=case.source,
        scope_start=evidence.start,
        scope_end=evidence.end,
        exact_text=exact_text,
    )
    focused = tuple(
        span
        for span in matches
        if case.focus_start <= span.start and span.end <= case.focus_end
    )
    if len(focused) != 1:
        raise SpanIdentityError(
            "child occurrence is absent or ambiguous within the frozen focus"
        )
    return focused[0]


def _evaluate_nested(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    contract: V13NestedTwoLaneContract,
) -> V13CaseMetrics:
    reasons: list[str] = []
    events = _map_events(output, contract, reasons)
    participants = _map_participants(case, output, contract, reasons)
    grounding = _grounding_passes(case, output, contract, reasons)

    events_complete = (
        len(events.by_key) == len(contract.source_lane.events)
        and not events.unsupported
    )
    participants_complete = (
        len(participants.by_key) == len(contract.source_lane.participants)
        and not participants.unsupported
    )
    roles_passed = _roles_pass(
        output,
        events,
        participants,
        contract,
        reasons,
    )
    axes_passed = _axes_pass(output, events, contract, reasons)
    completeness_passed = output.completeness == "COMPLETE"
    expected_root_id = events.by_key.get(contract.source_lane.root_event_key)
    if not completeness_passed:
        root_status: RootSelectionStatus = "NOT_APPLICABLE"
        reasons.append(f"output completeness is {output.completeness}")
    elif expected_root_id is not None and output.root_event_id == expected_root_id:
        root_status = "PASS"
    else:
        root_status = "FAIL"
        reasons.append("source root is not the outer responsible event")
    focus_passed = root_status == "PASS"

    non_root_dimensions_passed = all(
        (
            events_complete,
            participants_complete,
            grounding,
            roles_passed,
            axes_passed,
            completeness_passed,
        )
    )
    source_passed = non_root_dimensions_passed and root_status == "PASS"
    projection = project_actual_root_dependency_chain(
        case,
        output,
        contract,
        resolve_occurrence=resolve_focus_local_occurrence,
    )
    context_count = int("infected_fibroblasts" in participants.by_key)
    return V13CaseMetrics(
        case_id=case.case_id,
        passed=source_passed,
        focus_event_passed=focus_passed,
        source_semantic_status="PASS" if source_passed else "FAIL",
        benchmark_projection_status="PASS" if projection is not None else "FAIL",
        benchmark_projection_scope="EXACT_CG_ROOT_DEPENDENCY_CHAIN",
        full_focus_cg_status=(contract.cg_full_focus_projection.measurement_status),
        mandatory_participants_passed=participants_complete,
        participant_roles_passed=roles_passed,
        semantic_axes_passed=axes_passed,
        exact_evidence_grounding=grounding,
        unsupported_extraction_count=(
            len(events.unsupported) + len(participants.unsupported)
        ),
        permitted_context_count=context_count,
        benchmark_projection=projection,
        failure_reasons=tuple(dict.fromkeys(reasons)),
        historical_grader_passed=None,
        root_selection_status=root_status,
        completeness=output.completeness,
        source_dimensions_except_root_passed=non_root_dimensions_passed,
        root_only_failure=(non_root_dimensions_passed and root_status == "FAIL"),
    )


def _map_events(
    output: StagedGeneralizationOutput,
    contract: V13NestedTwoLaneContract,
    reasons: list[str],
) -> _EventMapping:
    by_key: dict[SourceEventKey, str] = {}
    unsupported: list[str] = []
    for event in output.inventory:
        matches = tuple(
            rule
            for rule in contract.source_lane.events
            if event.event_type in rule.acceptable_event_types
            and event.trigger_text in rule.acceptable_triggers
        )
        if len(matches) != 1 or matches[0].event_key in by_key:
            unsupported.append(f"{event.event_type}/{event.trigger_text}")
            continue
        by_key[matches[0].event_key] = event.event_id
    missing = tuple(
        rule.event_key
        for rule in contract.source_lane.events
        if rule.event_key not in by_key
    )
    if missing:
        reasons.append(f"source events are incomplete: {list(missing)}")
    if unsupported:
        reasons.append(f"unsupported or duplicate events: {unsupported}")
    return _EventMapping(by_key=by_key, unsupported=tuple(unsupported))


def _map_participants(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    contract: V13NestedTwoLaneContract,
    reasons: list[str],
) -> _ParticipantMapping:
    by_key: dict[SourceParticipantKey, str] = {}
    unsupported: list[str] = []
    for participant in output.participants:
        span = _participant_span(case, participant)
        matches = tuple(
            rule
            for rule in contract.source_lane.participants
            if span is not None
            and participant.entity_type == rule.entity_type
            and participant.exact_text == rule.exact_text
            and span.start == rule.start
            and span.end == rule.end
        )
        if len(matches) != 1 or matches[0].participant_key in by_key:
            unsupported.append(f"{participant.entity_type}/{participant.exact_text}")
            continue
        by_key[matches[0].participant_key] = participant.participant_id
    missing = tuple(
        rule.participant_key
        for rule in contract.source_lane.participants
        if rule.participant_key not in by_key
    )
    if missing:
        reasons.append(f"source participants are incomplete: {list(missing)}")
    if unsupported:
        reasons.append(f"unsupported or duplicate participants: {unsupported}")
    return _ParticipantMapping(
        by_key=by_key,
        unsupported=tuple(unsupported),
    )


def _participant_span(
    case: GeneralizationCase,
    participant: ParticipantNode,
) -> ExactSpan | None:
    try:
        return resolve_focus_local_occurrence(
            case,
            exact_evidence=participant.exact_evidence,
            exact_text=participant.exact_text,
        )
    except SpanIdentityError:
        return None


def _grounding_passes(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    contract: V13NestedTwoLaneContract,
    reasons: list[str],
) -> bool:
    evidence = contract.source_lane.exact_evidence
    if (
        case.focus_start != contract.source_lane.focus_start
        or case.focus_end != contract.source_lane.focus_end
        or case.local_context != evidence
    ):
        reasons.append("case focus or evidence differs from adjudicated source lane")
        return False
    try:
        resolve_evidence(
            source=case.source,
            context_start=case.context_start,
            context_end=case.context_end,
            exact_text=evidence,
        )
        for event in output.inventory:
            _require_exact_evidence(event.exact_evidence, evidence, "event")
            resolve_focus_local_occurrence(
                case,
                exact_evidence=event.exact_evidence,
                exact_text=event.trigger_text,
            )
        for participant in output.participants:
            _require_exact_evidence(
                participant.exact_evidence,
                evidence,
                "participant",
            )
            resolve_focus_local_occurrence(
                case,
                exact_evidence=participant.exact_evidence,
                exact_text=participant.exact_text,
            )
        for axes in output.semantic_axes:
            _require_semantic_evidence(
                tuple(axes.evidence_items),
                evidence,
            )
    except (GeneralizationAnchorError, SpanIdentityError) as exc:
        reasons.append(f"exact evidence grounding failed: {exc}")
        return False
    return True


def _require_exact_evidence(
    actual: str,
    expected: str,
    label: str,
) -> None:
    if actual != expected:
        raise GeneralizationAnchorError(
            f"{label} evidence is not the complete adjudicated sentence"
        )


def _require_semantic_evidence(
    actual: tuple[str, ...],
    expected: str,
) -> None:
    if actual != (expected,):
        raise GeneralizationAnchorError(
            "semantic evidence is not the complete adjudicated sentence"
        )


def _roles_pass(
    output: StagedGeneralizationOutput,
    events: _EventMapping,
    participants: _ParticipantMapping,
    contract: V13NestedTwoLaneContract,
    reasons: list[str],
) -> bool:
    event_ids = tuple(item.event_id for item in output.inventory)
    link_ids = tuple(item.event_id for item in output.links)
    if not (
        len(link_ids) == len(event_ids)
        and len(set(link_ids)) == len(link_ids)
        and set(link_ids) == set(event_ids)
    ):
        reasons.append("event link stage cardinality or coverage differs")
        return False
    event_key_by_id = {
        event_id: event_key for event_key, event_id in events.by_key.items()
    }
    participant_key_by_id = {
        participant_id: participant_key
        for participant_key, participant_id in participants.by_key.items()
    }
    actual: list[tuple[str, str, str, str]] = []
    for link in output.links:
        event_key = event_key_by_id.get(link.event_id)
        if event_key is None:
            reasons.append("event links cannot be mapped to source event keys")
            return False
        for argument in link.arguments:
            target_key = (
                participant_key_by_id.get(argument.target_id)
                if argument.target_kind == "PARTICIPANT"
                else event_key_by_id.get(argument.target_id)
            )
            if target_key is None:
                reasons.append("event argument target cannot be mapped to a source key")
                return False
            actual.append(
                (
                    event_key,
                    argument.role,
                    argument.target_kind,
                    target_key,
                )
            )
    expected = [
        (
            item.event_key,
            item.role,
            item.target_kind,
            item.target_key,
        )
        for item in contract.source_lane.links
    ]
    passed = sorted(actual) == sorted(expected)
    if not passed:
        reasons.append("source-semantic event links or roles differ")
    return passed


def _axes_pass(
    output: StagedGeneralizationOutput,
    events: _EventMapping,
    contract: V13NestedTwoLaneContract,
    reasons: list[str],
) -> bool:
    event_ids = tuple(item.event_id for item in output.inventory)
    axes_ids = tuple(item.event_id for item in output.semantic_axes)
    if not (
        len(axes_ids) == len(event_ids)
        and len(set(axes_ids)) == len(axes_ids)
        and set(axes_ids) == set(event_ids)
    ):
        reasons.append("semantic axes stage cardinality or coverage differs")
        return False
    axes_by_id = {item.event_id: item for item in output.semantic_axes}
    for rule in contract.source_lane.axes:
        event_id = events.by_key.get(rule.event_key)
        axes = axes_by_id.get(event_id) if event_id is not None else None
        if axes is None:
            reasons.append(f"semantic axes absent for {rule.event_key}")
            return False
        observations = tuple(
            (item.observation_type, item.exact_text)
            for item in axes.statistical_observations
        )
        if not (
            axes.direction == rule.direction
            and axes.comparison == rule.comparison
            and axes.polarity == rule.polarity
            and axes.uncertainty == rule.uncertainty
            and observations == ((rule.statistics, None),)
            and axes.author_interpretation == rule.author_interpretation
        ):
            reasons.append(f"semantic axes differ for {rule.event_key}")
            return False
    return True


def _from_v12(
    metrics: V12CaseMetrics,
    *,
    completeness: CompletenessStatus,
) -> V13CaseMetrics:
    source_passed = metrics.source_semantic_status == "PASS"
    root_status: RootSelectionStatus
    if completeness != "COMPLETE":
        root_status = "NOT_APPLICABLE"
    else:
        root_status = "PASS" if metrics.focus_event_passed else "FAIL"
    source_reasons = tuple(
        item
        for item in metrics.failure_reasons
        if item != _CG_ONLY_FAILURE
        and not (completeness != "COMPLETE" and item in _ROOT_ONLY_FAILURE_REASONS)
    )
    if metrics.case_id == _DRUG_CASE_ID:
        projection_scope: BenchmarkProjectionScope = "DRUG_FOCUS_EVENT"
        projection_status = metrics.cg_projection_status
        projection = metrics.cg_projection
    else:
        projection_scope = "NOT_APPLICABLE"
        projection_status = "NOT_APPLICABLE"
        projection = None
    return V13CaseMetrics(
        case_id=metrics.case_id,
        passed=source_passed,
        focus_event_passed=root_status == "PASS",
        source_semantic_status=metrics.source_semantic_status,
        benchmark_projection_status=projection_status,
        benchmark_projection_scope=projection_scope,
        full_focus_cg_status="NOT_APPLICABLE",
        mandatory_participants_passed=metrics.mandatory_participants_passed,
        participant_roles_passed=metrics.participant_roles_passed,
        semantic_axes_passed=metrics.semantic_axes_passed,
        exact_evidence_grounding=metrics.exact_evidence_grounding,
        unsupported_extraction_count=metrics.unsupported_extraction_count,
        permitted_context_count=metrics.permitted_context_count,
        benchmark_projection=projection,
        failure_reasons=source_reasons,
        historical_grader_passed=metrics.historical_grader_passed,
        root_selection_status=root_status,
        completeness=completeness,
        source_dimensions_except_root_passed=source_passed,
        root_only_failure=False,
        qualification_credit=metrics.qualification_credit,
        graph_writes=metrics.graph_writes,
        trusted_promotion=metrics.trusted_promotion,
    )


__all__ = [
    "V13CaseMetrics",
    "evaluate_v13_case",
    "resolve_focus_local_occurrence",
]
