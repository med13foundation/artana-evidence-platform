"""Root-cause replay for the exposed V2 case without invoking the frozen grader."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.provider_contract import (
    FreshCGProviderOutput,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v3.contracts import (
    ClassifiedIssue,
    ExposedCaseReferenceV3,
    ExposedCaseReplayV3,
    FieldReplay,
    RootCauseConsensus,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from scripts.validation.public_gold.staged_event.generalization.contracts import (
        EventArgument,
    )


def evaluate_exposed_case(
    *,
    reference_path: Path,
    raw_output_path: Path,
    consensus_path: Path,
    raw_v2_unsupported_count: int,
) -> ExposedCaseReplayV3:
    """Attribute root causes while preserving the sealed V2 score."""

    reference = ExposedCaseReferenceV3.model_validate_json(
        reference_path.read_text(encoding="utf-8")
    )
    output = FreshCGProviderOutput.model_validate_json(
        raw_output_path.read_text(encoding="utf-8")
    )
    consensus = RootCauseConsensus.model_validate_json(
        consensus_path.read_text(encoding="utf-8")
    )
    scientific = output.scientific_output
    bindings = output.occurrence_bindings
    event = reference.direct_cg_event
    expected_participant = reference.direct_cg_participants[0]
    event_type_by_id = {item.event_id: item.event_type for item in scientific.inventory}
    participant_type_by_id = {
        item.participant_id: item.entity_type for item in scientific.participants
    }
    event_ids = {
        item.node_id
        for item in bindings.event_mentions
        if event_type_by_id[item.node_id] == event.artana_event_type
        and _same_span(
            item.identity.mention_span.start,
            item.identity.mention_span.end,
            event.trigger.start,
            event.trigger.end,
        )
    }
    participant_ids = {
        item.node_id
        for item in bindings.participant_mentions
        if participant_type_by_id[item.node_id]
        == expected_participant.artana_entity_type
        and _same_span(
            item.identity.mention_span.start,
            item.identity.mention_span.end,
            expected_participant.mention.start,
            expected_participant.mention.end,
        )
    }
    diagnostic_candidates = {
        item.node_id
        for item in bindings.participant_mentions
        if participant_type_by_id[item.node_id]
        == expected_participant.artana_entity_type
        and (
            item.identity.mention_span.start <= expected_participant.mention.start
            and expected_participant.mention.end <= item.identity.mention_span.end
        )
    }
    event_id = next(iter(event_ids), None)
    diagnostic_participant_id = next(iter(diagnostic_candidates), None)
    axes = next(
        item
        for item in scientific.semantic_axes
        if event_id is not None and item.event_id == event_id
    )
    link = next(
        item
        for item in scientific.links
        if event_id is not None and item.event_id == event_id
    )
    context_match = _context_matches(reference, output)
    role_value_matches = (
        diagnostic_participant_id is not None
        and count_target_role(
            link.arguments,
            target_id=diagnostic_participant_id,
            role=reference.role.value,
        )
        == 1
    )
    if not role_value_matches:
        raise ValueError(
            "diagnostic containment candidate does not preserve role value"
        )
    classifications = {item.issue_id: item for item in consensus.classifications}
    fields = (
        FieldReplay(
            field_id="role:T9",
            status="BLOCKED_BY_OCCURRENCE",
            independent_error=False,
            depends_on=("A_DIRECT_PARTICIPANT_OCCURRENCE",),
        ),
        FieldReplay(
            field_id="direct_attachment",
            status="BLOCKED_BY_OCCURRENCE",
            independent_error=False,
            depends_on=("A_DIRECT_PARTICIPANT_OCCURRENCE",),
        ),
        FieldReplay(
            field_id="contextual_participants",
            status="MATCH" if context_match else "MISMATCH",
            independent_error=False,
            depends_on=(),
        ),
        FieldReplay(
            field_id="direction",
            status="MATCH"
            if axes.direction == reference.direction.value
            else "MISMATCH",
            independent_error=False,
            depends_on=(),
        ),
        FieldReplay(
            field_id="uncertainty",
            status=(
                "MATCH"
                if axes.uncertainty == reference.uncertainty.value
                else "MISMATCH"
            ),
            independent_error=False,
            depends_on=(),
        ),
    )
    model_errors = _classified_ids(classifications, "MODEL_ERROR", independent=True)
    reference_errors = _classified_ids(
        classifications,
        "REFERENCE_ERROR",
        independent=True,
    )
    evaluator_errors = _classified_ids(
        classifications,
        "EVALUATOR_MAPPING_ERROR",
        independent=True,
    )
    ambiguities = _classified_ids(
        classifications,
        "TAXONOMY_AMBIGUITY",
        independent=False,
    )
    return ExposedCaseReplayV3(
        case_id=reference.case_id,
        v3_reference_sha256=_sha256(reference_path),
        v2_raw_output_sha256=_sha256(raw_output_path),
        direct_cg_event_exact=len(event_ids) == 1,
        direct_cg_participant_exact=len(participant_ids) == 1,
        participant_identity_recognized_diagnostic_only=(
            len(diagnostic_candidates) == 1
        ),
        fields=fields,
        genuine_model_error_issue_ids=model_errors,
        reference_error_issue_ids=reference_errors,
        evaluator_mapping_error_issue_ids=evaluator_errors,
        taxonomy_ambiguity_issue_ids=ambiguities,
        raw_v2_unsupported_count=raw_v2_unsupported_count,
        independent_unsupported_root_count=1,
        cascaded_structural_miss_count=raw_v2_unsupported_count - 1,
        contradiction_count=0,
        active_terminal_reason="DIRECT_CG_PARTICIPANT_OCCURRENCE_MISMATCH",
        diagnostic_decision="MODEL_CORRECTION_REQUIRED",
    )


def count_target_attachments_once(
    arguments: tuple[EventArgument, ...],
    *,
    target_id: str,
) -> int:
    """Count one participant target without duplicating the argument traversal."""

    targets = [
        argument.target_id
        for argument in arguments
        if argument.target_kind == "PARTICIPANT"
    ]
    return int(targets.count(target_id) == 1)


def count_target_role(
    arguments: tuple[EventArgument, ...],
    *,
    target_id: str,
    role: str,
) -> int:
    return sum(
        argument.target_kind == "PARTICIPANT"
        and argument.target_id == target_id
        and argument.role == role
        for argument in arguments
    )


def _context_matches(
    reference: ExposedCaseReferenceV3,
    output: FreshCGProviderOutput,
) -> bool:
    if len(reference.contextual_participants) != 1:
        return False
    expected = reference.contextual_participants[0]
    scientific = output.scientific_output
    binding_by_id = {
        item.node_id: item.identity.mention_span
        for item in output.occurrence_bindings.participant_mentions
    }
    matches = [
        item.participant_id
        for item in scientific.participants
        if item.entity_type == expected.entity_type
        and _same_span(
            binding_by_id[item.participant_id].start,
            binding_by_id[item.participant_id].end,
            expected.mention.start,
            expected.mention.end,
        )
    ]
    if len(matches) != 1:
        return False
    target_id = matches[0]
    return (
        sum(
            argument.target_kind == "PARTICIPANT"
            and argument.target_id == target_id
            and argument.role == expected.role
            for link in scientific.links
            for argument in link.arguments
        )
        == 1
    )


def _classified_ids(
    classifications: Mapping[str, ClassifiedIssue],
    expected: str,
    *,
    independent: bool,
) -> tuple[str, ...]:
    return tuple(
        issue_id
        for issue_id, issue in classifications.items()
        if issue.classification == expected and issue.independent_error is independent
    )


def _same_span(
    actual_start: int,
    actual_end: int,
    expected_start: int,
    expected_end: int,
) -> bool:
    return actual_start == expected_start and actual_end == expected_end


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "count_target_attachments_once",
    "count_target_role",
    "evaluate_exposed_case",
]
