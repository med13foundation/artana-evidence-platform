"""V12 source-semantic evaluation with a separate exact CG projection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal

from scripts.validation.public_gold.staged_event.generalization.anchors import (
    GeneralizationAnchorError,
    resolve_evidence,
    resolve_in_context,
)
from scripts.validation.public_gold.staged_event.generalization.grading.evaluation import (
    evaluate_case as evaluate_frozen_case,
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
    from scripts.validation.public_gold.staged_event.generalization.repair_v12.contracts import (
        RequiredParticipantRule,
        V12TwoLaneContract,
    )

LaneStatus = Literal["PASS", "FAIL", "NOT_APPLICABLE"]


@dataclass(frozen=True, slots=True)
class V12CaseMetrics:
    case_id: str
    passed: bool
    focus_event_passed: bool
    source_semantic_status: LaneStatus
    cg_projection_status: LaneStatus
    mandatory_participants_passed: bool
    participant_roles_passed: bool
    semantic_axes_passed: bool
    exact_evidence_grounding: bool
    unsupported_extraction_count: int
    permitted_context_count: int
    cg_projection: dict[str, object] | None
    failure_reasons: tuple[str, ...]
    historical_grader_passed: bool | None
    qualification_credit: bool = False
    graph_writes: int = 0
    trusted_promotion: bool = False

    def as_json(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class _ParticipantMapping:
    required: dict[str, RequiredParticipantRule]
    context_ids: frozenset[str]
    unsupported: tuple[str, ...]


def evaluate_v12_case(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    policy: FrozenCasePolicy,
    contract: V12TwoLaneContract,
) -> V12CaseMetrics:
    if case.case_id != "generalization-drug-sensitivity":
        return _evaluate_unchanged_case(case, output, policy)
    return _evaluate_drug_sensitivity(case, output, contract)


def _evaluate_unchanged_case(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    policy: FrozenCasePolicy,
) -> V12CaseMetrics:
    legacy = evaluate_frozen_case(case, output, policy)
    return V12CaseMetrics(
        case_id=case.case_id,
        passed=legacy.passed,
        focus_event_passed=legacy.required_core_complete,
        source_semantic_status="PASS" if legacy.passed else "FAIL",
        cg_projection_status="NOT_APPLICABLE",
        mandatory_participants_passed=legacy.required_core_complete,
        participant_roles_passed=legacy.participant_role_fidelity,
        semantic_axes_passed=all(
            (
                legacy.direction_fidelity,
                legacy.comparison_fidelity,
                legacy.polarity_fidelity,
                legacy.uncertainty_fidelity,
                legacy.statistical_fidelity,
            )
        ),
        exact_evidence_grounding=legacy.exact_evidence_grounding,
        unsupported_extraction_count=legacy.unsupported_claim_count,
        permitted_context_count=legacy.permitted_context_count,
        cg_projection=None,
        failure_reasons=legacy.failure_reasons,
        historical_grader_passed=legacy.passed,
    )


def _evaluate_drug_sensitivity(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    contract: V12TwoLaneContract,
) -> V12CaseMetrics:
    lane = contract.source_lane
    reasons: list[str] = []
    root = next(
        (event for event in output.inventory if event.event_id == output.root_event_id),
        None,
    )
    focus_passed = bool(
        root is not None
        and root.trigger_text == lane.root_trigger
        and root.event_type in lane.acceptable_event_types
    )
    if not focus_passed:
        reasons.append("highlighted sensitivity event is not the source root")
    if len(output.inventory) != 1:
        reasons.append("non-focus events were inventoried")

    grounding = _grounding(case, output, lane.exact_evidence, reasons)
    participants = _map_participants(case, output, contract, reasons)
    required_complete = len(participants.required) == len(
        lane.mandatory_participants
    )
    if not required_complete:
        reasons.append("mandatory source-semantic participants are incomplete")
    roles_passed = _roles_pass(
        output,
        root.event_id if root is not None else None,
        participants,
        reasons,
    )
    axes_passed = _axes_pass(
        output,
        root.event_id if root is not None else None,
        contract,
        reasons,
    )
    if output.completeness != "COMPLETE":
        reasons.append(f"output completeness is {output.completeness}")
    source_passed = all(
        (
            focus_passed,
            len(output.inventory) == 1,
            grounding,
            required_complete,
            roles_passed,
            axes_passed,
            not participants.unsupported,
            output.completeness == "COMPLETE",
        )
    )
    projection = _project_cg(
        case,
        root,
        participants,
        roles_passed=roles_passed,
        contract=contract,
    )
    cg_passed = projection is not None
    if not cg_passed:
        reasons.append("exact CG focus projection is unavailable")
    return V12CaseMetrics(
        case_id=case.case_id,
        passed=source_passed and cg_passed,
        focus_event_passed=focus_passed,
        source_semantic_status="PASS" if source_passed else "FAIL",
        cg_projection_status="PASS" if cg_passed else "FAIL",
        mandatory_participants_passed=required_complete,
        participant_roles_passed=roles_passed,
        semantic_axes_passed=axes_passed,
        exact_evidence_grounding=grounding,
        unsupported_extraction_count=len(participants.unsupported)
        + int(len(output.inventory) != 1),
        permitted_context_count=len(participants.context_ids),
        cg_projection=projection,
        failure_reasons=tuple(dict.fromkeys(reasons)),
        historical_grader_passed=None,
    )


def _grounding(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    exact_evidence: str,
    reasons: list[str],
) -> bool:
    try:
        for event in output.inventory:
            _require_equal_evidence(
                event.exact_evidence,
                exact_evidence,
                label="event",
            )
            resolve_in_context(
                source=case.source,
                context_start=case.context_start,
                context_end=case.context_end,
                exact_evidence=event.exact_evidence,
                exact_text=event.trigger_text,
            )
        for participant in output.participants:
            _require_equal_evidence(
                participant.exact_evidence,
                exact_evidence,
                label="participant",
            )
            _resolve_focus_aware_child(
                case,
                participant.exact_evidence,
                participant.exact_text,
            )
        for axes in output.semantic_axes:
            _require_semantic_evidence(
                tuple(axes.evidence_items),
                exact_evidence,
            )
            resolve_evidence(
                source=case.source,
                context_start=case.context_start,
                context_end=case.context_end,
                exact_text=exact_evidence,
            )
    except (GeneralizationAnchorError, SpanIdentityError) as exc:
        reasons.append(f"exact evidence grounding failed: {exc}")
        return False
    return True


def _require_equal_evidence(actual: str, expected: str, *, label: str) -> None:
    if actual != expected:
        raise GeneralizationAnchorError(
            f"{label} evidence is not the frozen sentence"
        )


def _require_semantic_evidence(actual: tuple[str, ...], expected: str) -> None:
    if actual != (expected,):
        raise GeneralizationAnchorError(
            "semantic evidence is not one complete frozen sentence"
        )


def _resolve_focus_aware_child(
    case: GeneralizationCase,
    exact_evidence: str,
    exact_text: str,
) -> ExactSpan:
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
    if len(matches) == 1:
        return matches[0]
    focused = tuple(
        span
        for span in matches
        if case.focus_start <= span.start and span.end <= case.focus_end
    )
    if len(focused) != 1:
        raise SpanIdentityError("child occurrence is absent or ambiguous after focus gating")
    return focused[0]


def _map_participants(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    contract: V12TwoLaneContract,
    reasons: list[str],
) -> _ParticipantMapping:
    required: dict[str, RequiredParticipantRule] = {}
    context_ids: set[str] = set()
    unsupported: list[str] = []
    for participant in output.participants:
        span = _safe_span(case, participant, reasons)
        required_match = next(
            (
                rule
                for rule in contract.source_lane.mandatory_participants
                if span is not None
                and participant.entity_type == rule.entity_type
                and span.start == rule.start
                and span.end == rule.end
            ),
            None,
        )
        if required_match is not None and required_match not in required.values():
            required[participant.participant_id] = required_match
            continue
        context_match = next(
            (
                rule
                for rule in contract.source_lane.permitted_context
                if participant.entity_type == rule.entity_type
                and participant.exact_text in rule.acceptable_texts
            ),
            None,
        )
        if context_match is not None and not any(
            output_participant.exact_text in context_match.acceptable_texts
            for output_participant in output.participants
            if output_participant.participant_id in context_ids
        ):
            context_ids.add(participant.participant_id)
            continue
        unsupported.append(
            f"{participant.entity_type}/{participant.exact_text}"
        )
    if unsupported:
        reasons.append(f"unsupported participant extractions: {unsupported}")
    return _ParticipantMapping(
        required=required,
        context_ids=frozenset(context_ids),
        unsupported=tuple(unsupported),
    )


def _safe_span(
    case: GeneralizationCase,
    participant: ParticipantNode,
    reasons: list[str],
) -> ExactSpan | None:
    try:
        return _resolve_focus_aware_child(
            case,
            participant.exact_evidence,
            participant.exact_text,
        )
    except SpanIdentityError as exc:
        reasons.append(
            f"participant occurrence unresolved for {participant.participant_id}: {exc}"
        )
        return None


def _roles_pass(
    output: StagedGeneralizationOutput,
    root_id: str | None,
    participants: _ParticipantMapping,
    reasons: list[str],
) -> bool:
    if root_id is None:
        return False
    root_links = next((item for item in output.links if item.event_id == root_id), None)
    if root_links is None:
        reasons.append("root event links are absent")
        return False
    actual = {
        (argument.target_id, argument.target_kind, argument.role)
        for argument in root_links.arguments
    }
    expected = {
        (participant_id, "PARTICIPANT", rule.role)
        for participant_id, rule in participants.required.items()
    } | {
        (participant_id, "PARTICIPANT", "CONTEXTUAL_PARTICIPANT")
        for participant_id in participants.context_ids
    }
    passed = actual == expected
    if not passed:
        reasons.append("source-semantic argument roles or attachments differ")
    return passed


def _axes_pass(
    output: StagedGeneralizationOutput,
    root_id: str | None,
    contract: V12TwoLaneContract,
    reasons: list[str],
) -> bool:
    axes = next((item for item in output.semantic_axes if item.event_id == root_id), None)
    if axes is None:
        reasons.append("root semantic axes are absent")
        return False
    observations = tuple(
        (item.observation_type, item.exact_text)
        for item in axes.statistical_observations
    )
    passed = (
        axes.direction in contract.source_lane.acceptable_direction_values
        and axes.comparison == contract.source_lane.comparison
        and axes.polarity == contract.source_lane.polarity
        and axes.uncertainty == contract.source_lane.uncertainty
        and observations == ((contract.source_lane.statistics, None),)
        and axes.author_interpretation == contract.source_lane.author_interpretation
    )
    if not passed:
        reasons.append("source-semantic axes differ from adjudicated values")
    return passed


def _project_cg(
    case: GeneralizationCase,
    root: object,
    participants: _ParticipantMapping,
    *,
    roles_passed: bool,
    contract: V12TwoLaneContract,
) -> dict[str, object] | None:
    if (
        root is None
        or getattr(root, "trigger_text", None) != contract.source_lane.root_trigger
        or not roles_passed
    ):
        return None
    population = next(
        (
            rule
            for rule in participants.required.values()
            if rule.entity_type == "POPULATION"
        ),
        None,
    )
    drug = next(
        (
            rule
            for rule in participants.required.values()
            if rule.entity_type == "SIMPLE_CHEMICAL"
        ),
        None,
    )
    cg_theme = next(
        item
        for item in contract.cg_projection_lane.arguments
        if item.cg_role == "Theme"
    )
    cg_cause = next(
        item
        for item in contract.cg_projection_lane.arguments
        if item.cg_role == "Cause"
    )
    if population is None or drug is None:
        return None
    if not (
        population.start <= cg_theme.start
        and cg_theme.end <= population.end
        and drug.start == cg_cause.start
        and drug.end == cg_cause.end
        and case.source[cg_theme.start : cg_theme.end] == cg_theme.exact_text
        and case.source[cg_cause.start : cg_cause.end] == cg_cause.exact_text
    ):
        return None
    return {
        "scope": contract.cg_projection_lane.projection_scope,
        "event": {
            "type": contract.cg_projection_lane.event_type,
            "trigger": contract.cg_projection_lane.trigger.model_dump(mode="json"),
        },
        "arguments": [
            item.model_dump(mode="json")
            for item in contract.cg_projection_lane.arguments
        ],
        "review_only": True,
        "qualification_credit": False,
        "graph_promotion_allowed": False,
    }


__all__ = ["V12CaseMetrics", "evaluate_v12_case"]
