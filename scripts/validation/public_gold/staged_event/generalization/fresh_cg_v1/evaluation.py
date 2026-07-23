"""Fresh-CG dual-lane scoring after occurrence evaluator V2 validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, cast

from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.bindings import (
    OccurrenceBindingError,
    ValidatedBindings,
    validate_bindings,
)
from scripts.validation.public_gold.staged_event.generalization.panel import (
    GeneralizationCase,
    GeneralizationReference,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.contracts import (
        EventArgument,
        SemanticAxes,
    )
    from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.contracts import (
        FreshCGCase,
    )
    from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.provider_contract import (
        FreshCGProviderOutput,
    )
    from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.reference_contracts import (
        CategoricalReference,
        FreshCGCaseTwoLaneReference,
    )


@dataclass(frozen=True, slots=True)
class FieldMetric:
    field_id: str
    reference_status: str
    passed: bool | None


@dataclass(frozen=True, slots=True)
class DirectCGMetrics:
    required_event_type_and_occurrence: bool
    required_participant_type_and_occurrence: str
    required_argument_target_attachments: str
    source_roles_preserved_in_reference: tuple[str, ...]
    source_role_fidelity: str
    unprojected_addition_count: int
    passed: bool


@dataclass(frozen=True, slots=True)
class FreshCaseMetrics:
    case_id: str
    passed: bool
    reference_complete: bool
    occurrence_binding_valid: bool
    direct_cg: DirectCGMetrics
    artana_fields: tuple[FieldMetric, ...]
    artana_scored_field_count: int
    artana_passed_field_count: int
    artana_failed_field_count: int
    artana_review_only_field_count: int
    required_core_complete: bool
    exact_nested_event_structure: bool
    unsupported_claim_count: int
    contradiction_count: int
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _EvaluationMapping:
    event_id: str | None
    participant_ids: dict[str, str]
    context_ids: dict[int, str]


def evaluate_case(
    case: FreshCGCase,
    reference: FreshCGCaseTwoLaneReference,
    output: FreshCGProviderOutput,
) -> FreshCaseMetrics:
    """Keep direct-CG fidelity separate from source-semantic fidelity."""

    if case.case_id != reference.case_id:
        raise ValueError("fresh case and reference identity differ")
    scientific = output.scientific_output
    validated = validate_bindings(
        _binding_case(case),
        scientific,
        output.occurrence_bindings,
    )
    _require_semantic_evidence_token_boundaries(case, validated)
    reasons: list[str] = []
    event_id = _required_event_id(case, scientific, validated)
    participant_ids = _required_participant_ids(case, scientific, validated)
    event_exact = event_id is not None and len(scientific.inventory) == 1
    if not event_exact:
        reasons.append("direct CG event type or occurrence differs")
    participant_exact_count = len(participant_ids)
    participant_total = len(case.participants)
    if participant_exact_count != participant_total:
        reasons.append("direct CG participant type or occurrence differs")
    direct_attachments, direct_attachment_total = _direct_attachments(
        case,
        scientific,
        event_id=event_id,
        participant_ids=participant_ids,
    )
    if direct_attachments != direct_attachment_total:
        reasons.append("direct CG argument target attachment differs")
    context_ids, context_failures = _context_participants(
        reference,
        scientific,
        validated,
    )
    reasons.extend(context_failures)
    additions = len(scientific.inventory) - int(event_id is not None)
    additions += len(scientific.participants) - len(participant_ids)
    direct_pass = (
        event_exact
        and participant_exact_count == participant_total
        and direct_attachments == direct_attachment_total
    )
    direct = DirectCGMetrics(
        required_event_type_and_occurrence=event_exact,
        required_participant_type_and_occurrence=(
            f"{participant_exact_count}/{participant_total}"
        ),
        required_argument_target_attachments=(
            f"{direct_attachments}/{direct_attachment_total}"
        ),
        source_roles_preserved_in_reference=tuple(
            argument.source_role for argument in case.event.arguments
        ),
        source_role_fidelity="NOT_EXPRESSED_BY_V9_ARTANA_SCHEMA",
        unprojected_addition_count=max(additions, 0),
        passed=direct_pass,
    )
    mapping = _EvaluationMapping(event_id, participant_ids, context_ids)
    fields = _field_metrics(reference, scientific, validated, mapping)
    scored = tuple(item for item in fields if item.passed is not None)
    passed_fields = sum(item.passed is True for item in scored)
    failed_fields = sum(item.passed is False for item in scored)
    review_only = len(fields) - len(scored)
    if failed_fields:
        reasons.append("one or more resolved Artana semantic fields differ")
    reference_complete = review_only == 0
    if not reference_complete:
        reasons.append("reference contains review-only fields; model is not scored on them")
    unsupported = _unsupported_claim_count(
        reference,
        scientific,
        mapping,
    )
    if unsupported:
        reasons.append("output contains unsupported events, participants, or links")
    complete = scientific.completeness == "COMPLETE" and direct_pass
    if scientific.completeness != "COMPLETE":
        reasons.append(f"agent completeness is {scientific.completeness}")
    nested_exact = not any(
        argument.target_kind == "EVENT"
        for link in scientific.links
        for argument in link.arguments
    )
    if not nested_exact:
        reasons.append("fresh direct event unexpectedly contains nested event links")
    contradictions = int(scientific.completeness == "CONTRADICTED")
    passed = (
        reference_complete
        and complete
        and nested_exact
        and failed_fields == 0
        and unsupported == 0
        and contradictions == 0
    )
    return FreshCaseMetrics(
        case_id=case.case_id,
        passed=passed,
        reference_complete=reference_complete,
        occurrence_binding_valid=True,
        direct_cg=direct,
        artana_fields=fields,
        artana_scored_field_count=len(scored),
        artana_passed_field_count=passed_fields,
        artana_failed_field_count=failed_fields,
        artana_review_only_field_count=review_only,
        required_core_complete=complete,
        exact_nested_event_structure=nested_exact,
        unsupported_claim_count=unsupported,
        contradiction_count=contradictions,
        failure_reasons=tuple(dict.fromkeys(reasons)),
    )


def aggregate(metrics: tuple[FreshCaseMetrics, ...]) -> dict[str, object]:
    """Aggregate direct benchmark and Artana semantics as distinct lanes."""

    direct_passed = sum(item.direct_cg.passed for item in metrics)
    semantic_passed = sum(item.passed for item in metrics)
    return {
        "schema_version": "artana.staged_generalization.fresh_cg_result.v1",
        "decision": (
            "FRESH_EVIDENCE_PASS"
            if metrics and semantic_passed == len(metrics)
            else "FRESH_EVIDENCE_FAIL_FAST"
        ),
        "case_count": len(metrics),
        "direct_cg_required_fidelity": f"{direct_passed}/{len(metrics)}",
        "artana_source_semantic_fidelity": f"{semantic_passed}/{len(metrics)}",
        "occurrence_binding_fidelity": (
            f"{sum(item.occurrence_binding_valid for item in metrics)}/{len(metrics)}"
        ),
        "artana_scored_field_count": sum(
            item.artana_scored_field_count for item in metrics
        ),
        "artana_passed_field_count": sum(
            item.artana_passed_field_count for item in metrics
        ),
        "artana_failed_field_count": sum(
            item.artana_failed_field_count for item in metrics
        ),
        "review_only_field_count": sum(
            item.artana_review_only_field_count for item in metrics
        ),
        "unsupported_claim_count": sum(item.unsupported_claim_count for item in metrics),
        "contradiction_count": sum(item.contradiction_count for item in metrics),
        "cases": [asdict(item) for item in metrics],
        "qualification_credit": False,
        "trusted_graph_ready": False,
        "graph_writes": 0,
    }


def _binding_case(case: FreshCGCase) -> GeneralizationCase:
    return GeneralizationCase(
        case_id=case.case_id,
        family="FRESH_CG",
        source_id=case.document_id,
        source_sha256=case.source_sha256,
        source=case.source_text,
        context_start=case.permitted_context.start,
        context_end=case.permitted_context.end,
        local_context=case.permitted_context.text,
        focus_start=case.event.trigger.start,
        focus_end=case.event.trigger.end,
        focus_passage=case.event.trigger.text,
        reference=GeneralizationReference(
            events=(),
            participants=(),
            arguments=(),
            axes=(),
            root_event_key=case.event.event_id,
            reference_basis="direct CG lane plus independent Artana semantics",
        ),
    )


def _required_event_id(
    case: FreshCGCase,
    scientific: object,
    validated: ValidatedBindings,
) -> str | None:
    from scripts.validation.public_gold.staged_event.generalization.contracts import (
        StagedGeneralizationOutput,
    )

    if not isinstance(scientific, StagedGeneralizationOutput):
        raise TypeError("scientific output has an unexpected contract")
    matches = [
        item.event_id
        for item in scientific.inventory
        if item.event_type == case.event.artana_event_type
        and _same_span(validated.events[item.event_id].mention, case.event.trigger)
    ]
    return matches[0] if len(matches) == 1 else None


def _required_participant_ids(
    case: FreshCGCase,
    scientific: object,
    validated: ValidatedBindings,
) -> dict[str, str]:
    from scripts.validation.public_gold.staged_event.generalization.contracts import (
        StagedGeneralizationOutput,
    )

    if not isinstance(scientific, StagedGeneralizationOutput):
        raise TypeError("scientific output has an unexpected contract")
    result: dict[str, str] = {}
    for expected in case.participants:
        matches = [
            item.participant_id
            for item in scientific.participants
            if item.entity_type == expected.artana_entity_type
            and _same_span(validated.participants[item.participant_id].mention, expected.mention)
        ]
        if len(matches) == 1:
            result[expected.annotation_id] = matches[0]
    return result


def _direct_attachments(
    case: FreshCGCase,
    scientific: object,
    *,
    event_id: str | None,
    participant_ids: dict[str, str],
) -> tuple[int, int]:
    from scripts.validation.public_gold.staged_event.generalization.contracts import (
        StagedGeneralizationOutput,
    )

    if not isinstance(scientific, StagedGeneralizationOutput) or event_id is None:
        return 0, len(case.event.arguments)
    link = next(item for item in scientific.links if item.event_id == event_id)
    targets = [
        argument.target_id
        for argument in link.arguments
        if argument.target_kind == "PARTICIPANT"
    ]
    matched = sum(
        targets.count(participant_ids.get(argument.target_annotation_id, "")) == 1
        for argument in case.event.arguments
    )
    return matched, len(case.event.arguments)


def _context_participants(
    reference: FreshCGCaseTwoLaneReference,
    scientific: object,
    validated: ValidatedBindings,
) -> tuple[dict[int, str], tuple[str, ...]]:
    from scripts.validation.public_gold.staged_event.generalization.contracts import (
        StagedGeneralizationOutput,
    )

    if not isinstance(scientific, StagedGeneralizationOutput):
        raise TypeError("scientific output has an unexpected contract")
    context = reference.contextual_participants
    if context.status == "REVIEW_ONLY" or context.value is None:
        return {}, ()
    result: dict[int, str] = {}
    failures: list[str] = []
    for index, expected in enumerate(context.value.participants):
        matches = [
            item.participant_id
            for item in scientific.participants
            if item.entity_type == expected.entity_type
            and _same_span(validated.participants[item.participant_id].mention, expected.mention)
        ]
        if len(matches) == 1:
            result[index] = matches[0]
        else:
            failures.append("resolved contextual participant differs")
    return result, tuple(failures)


def _field_metrics(
    reference: FreshCGCaseTwoLaneReference,
    scientific: object,
    validated: ValidatedBindings,
    mapping: _EvaluationMapping,
) -> tuple[FieldMetric, ...]:
    from scripts.validation.public_gold.staged_event.generalization.contracts import (
        StagedGeneralizationOutput,
    )

    if not isinstance(scientific, StagedGeneralizationOutput):
        raise TypeError("scientific output has an unexpected contract")
    link_arguments: tuple[EventArgument, ...] = ()
    axes: SemanticAxes | None = None
    if mapping.event_id is not None:
        link_arguments = next(
            item.arguments
            for item in scientific.links
            if item.event_id == mapping.event_id
        )
        axes = next(
            item
            for item in scientific.semantic_axes
            if item.event_id == mapping.event_id
        )
    result = [
        _role_metric(item, link_arguments, mapping.participant_ids)
        for item in reference.argument_roles
    ]
    result.extend(
        _axis_metric(item, axes)
        for item in (
            reference.direction,
            reference.comparison,
            reference.polarity,
            reference.uncertainty,
        )
    )
    result.append(_statistics_metric(reference, axes, validated, mapping.event_id))
    result.append(_context_metric(reference, link_arguments, mapping.context_ids))
    return tuple(result)


def _role_metric(
    reference: CategoricalReference,
    arguments: tuple[EventArgument, ...],
    participant_ids: dict[str, str],
) -> FieldMetric:
    if reference.resolution.status == "REVIEW_ONLY":
        return FieldMetric(reference.field_id, "REVIEW_ONLY", None)
    target_id = participant_ids.get(cast("str", reference.target_anchor_id))
    matches = [
        item
        for item in arguments
        if item.target_kind == "PARTICIPANT" and item.target_id == target_id
    ]
    passed = len(matches) == 1 and matches[0].role == reference.value
    return FieldMetric(reference.field_id, "RESOLVED", passed)


def _axis_metric(
    reference: CategoricalReference,
    axes: SemanticAxes | None,
) -> FieldMetric:
    if reference.resolution.status == "REVIEW_ONLY":
        return FieldMetric(reference.field_id, "REVIEW_ONLY", None)
    actual = getattr(axes, reference.field_id) if axes is not None else None
    return FieldMetric(reference.field_id, "RESOLVED", actual == reference.value)


def _statistics_metric(
    reference: FreshCGCaseTwoLaneReference,
    axes: SemanticAxes | None,
    validated: ValidatedBindings,
    event_id: str | None,
) -> FieldMetric:
    expected = reference.statistics
    if expected.resolution.status == "REVIEW_ONLY":
        return FieldMetric(expected.field_id, "REVIEW_ONLY", None)
    if axes is None or event_id is None or expected.value is None:
        return FieldMetric(
            field_id=expected.field_id,
            reference_status="RESOLVED",
            passed=False,
        )
    expected_types = tuple(
        item.observation_type for item in expected.value.observations
    ) or ("NONE",)
    actual_types = tuple(
        item.observation_type for item in axes.statistical_observations
    )
    actual_spans = tuple(
        (item.start, item.end, item.exact_text)
        for item in validated.semantic[event_id].statistical_observations
        if item is not None
    )
    expected_spans = tuple(
        (item.evidence.start, item.evidence.end, item.evidence.text)
        for item in expected.value.observations
    )
    passed = (
        actual_types == expected_types
        and actual_spans == expected_spans
        and axes.author_interpretation == expected.value.author_interpretation
    )
    return FieldMetric(expected.field_id, "RESOLVED", passed)


def _context_metric(
    reference: FreshCGCaseTwoLaneReference,
    arguments: tuple[EventArgument, ...],
    context_ids: dict[int, str],
) -> FieldMetric:
    expected = reference.contextual_participants
    if expected.status == "REVIEW_ONLY":
        return FieldMetric(expected.field_id, "REVIEW_ONLY", None)
    if expected.value is None:
        return FieldMetric(
            field_id=expected.field_id,
            reference_status="RESOLVED",
            passed=False,
        )
    passed = len(context_ids) == len(expected.value.participants)
    for index, participant in enumerate(expected.value.participants):
        target_id = context_ids.get(index)
        passed &= sum(
            item.target_kind == "PARTICIPANT"
            and item.target_id == target_id
            and item.role == participant.role
            for item in arguments
        ) == 1
    return FieldMetric(expected.field_id, "RESOLVED", passed)


def _unsupported_claim_count(
    reference: FreshCGCaseTwoLaneReference,
    scientific: object,
    mapping: _EvaluationMapping,
) -> int:
    from scripts.validation.public_gold.staged_event.generalization.contracts import (
        StagedGeneralizationOutput,
    )

    if not isinstance(scientific, StagedGeneralizationOutput):
        raise TypeError("scientific output has an unexpected contract")
    unsupported = len(scientific.inventory) - int(mapping.event_id is not None)
    known_participants = set(mapping.participant_ids.values()) | set(
        mapping.context_ids.values()
    )
    unknown_participants = {
        item.participant_id
        for item in scientific.participants
        if item.participant_id not in known_participants
    }
    if reference.contextual_participants.status == "RESOLVED":
        unsupported += len(unknown_participants)
    if mapping.event_id is None:
        return unsupported + sum(len(item.arguments) for item in scientific.links)
    expected_targets = set(mapping.participant_ids.values()) | set(
        mapping.context_ids.values()
    )
    selected_links = next(
        item for item in scientific.links if item.event_id == mapping.event_id
    )
    unsupported += sum(
        item.target_kind != "PARTICIPANT" or item.target_id not in expected_targets
        for item in selected_links.arguments
    )
    unsupported += sum(
        len(item.arguments)
        for item in scientific.links
        if item.event_id != mapping.event_id
    )
    return max(unsupported, 0)


def _same_span(actual: object, expected: object) -> bool:
    from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.contracts import (
        ExactSourceSpan,
    )
    from scripts.validation.public_gold.staged_event.generalization.span_identity import (
        ExactSpan,
    )

    if not isinstance(actual, ExactSpan) or not isinstance(expected, ExactSourceSpan):
        return False
    return (
        actual.start == expected.start
        and actual.end == expected.end
        and actual.exact_text == expected.text
    )


def _require_semantic_evidence_token_boundaries(
    case: FreshCGCase,
    validated: ValidatedBindings,
) -> None:
    from scripts.validation.public_gold.staged_event.generalization.span_identity import (
        token_bounded_spans,
    )

    for semantic in validated.semantic.values():
        for evidence in semantic.evidence_items:
            candidates = token_bounded_spans(
                source=case.source_text,
                scope_start=case.permitted_context.start,
                scope_end=case.permitted_context.end,
                exact_text=evidence.exact_text,
            )
            if evidence not in candidates:
                raise OccurrenceBindingError(
                    "semantic evidence offsets split a source token"
                )


__all__ = [
    "DirectCGMetrics",
    "FieldMetric",
    "FreshCaseMetrics",
    "aggregate",
    "evaluate_case",
]
