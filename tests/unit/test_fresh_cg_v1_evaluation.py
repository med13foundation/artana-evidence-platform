"""Dual-lane scoring regressions for the fresh-CG experiment."""

from __future__ import annotations

import json

import pytest

from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.agreement import (
    ReferenceBuildInputs,
    ReviewArtifactInput,
    build_two_lane_reference,
    load_reviewer_artifact,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.config import (
    DEFAULT_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.contracts import (
    FreshCGCase,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.evaluation import (
    evaluate_case,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.provider_contract import (
    FreshCGProviderOutput,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.reference_contracts import (
    FreshCGCaseTwoLaneReference,
    ResolutionMetadata,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.review_contracts import (
    FreshCGReviewPacket,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.selection import (
    load_frozen_selection,
)
from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.bindings import (
    OccurrenceBindingError,
)


def _reference_without_tiebreaker() -> tuple[
    FreshCGCase,
    FreshCGCaseTwoLaneReference,
]:
    selection = load_frozen_selection(DEFAULT_PATHS.selection)
    packet = FreshCGReviewPacket.model_validate_json(
        DEFAULT_PATHS.review_packet.read_text(encoding="utf-8")
    )
    reviewer_a = load_reviewer_artifact(DEFAULT_PATHS.reviewer_a)
    reviewer_b = load_reviewer_artifact(DEFAULT_PATHS.reviewer_b)
    reference = build_two_lane_reference(
        ReferenceBuildInputs(
            selection=selection,
            packet=packet,
            selection_artifact_path=DEFAULT_PATHS.selection,
            review_packet_path=DEFAULT_PATHS.review_packet,
            review_prompt_path=DEFAULT_PATHS.review_prompt,
            primary_reviewers=(
                ReviewArtifactInput(reviewer_a, DEFAULT_PATHS.reviewer_a),
                ReviewArtifactInput(reviewer_b, DEFAULT_PATHS.reviewer_b),
            ),
        )
    )
    return selection.cases[0], reference.cases[0]


def _output(
    case: FreshCGCase,
    reference: FreshCGCaseTwoLaneReference,
    *,
    direction: str,
) -> FreshCGProviderOutput:
    context = case.permitted_context
    participant = case.participants[0]
    role = reference.argument_roles[0].value
    polarity = reference.polarity.value
    uncertainty = reference.uncertainty.value
    if role is None or polarity is None or uncertainty is None:
        raise AssertionError("test requires resolved role, polarity, and uncertainty")
    payload = {
        "schema_version": "artana.staged_generalization.fresh_cg_provider.v1",
        "scientific_output": {
            "case_id": case.case_id,
            "inventory": [
                {
                    "event_id": "event-1",
                    "event_type": case.event.artana_event_type,
                    "trigger_text": case.event.trigger.text,
                    "exact_evidence": context.text,
                    "explanation": "The selected event occurrence is explicit.",
                }
            ],
            "participants": [
                {
                    "participant_id": "participant-1",
                    "entity_type": participant.artana_entity_type,
                    "exact_text": participant.mention.text,
                    "exact_evidence": context.text,
                    "explanation": "The selected participant occurrence is explicit.",
                }
            ],
            "links": [
                {
                    "event_id": "event-1",
                    "arguments": [
                        {
                            "role": role,
                            "target_kind": "PARTICIPANT",
                            "target_id": "participant-1",
                            "explanation": "The role follows the resolved semantic reference.",
                        }
                    ],
                }
            ],
            "semantic_axes": [
                {
                    "event_id": "event-1",
                    "direction": direction,
                    "comparison": "NOT_APPLICABLE",
                    "polarity": polarity,
                    "uncertainty": uncertainty,
                    "statistical_observations": [
                        {"observation_type": "NONE", "exact_text": None}
                    ],
                    "author_interpretation": "NOT_CLAIMED",
                    "evidence_items": [case.event.trigger.text],
                    "explanation": "Semantic values are source-grounded.",
                }
            ],
            "root_event_id": "event-1",
            "completeness": "COMPLETE",
            "structure_explanation": "One selected direct event is complete.",
        },
        "occurrence_bindings": {
            "schema_version": "artana.staged_generalization.occurrence_bindings.v2",
            "case_id": case.case_id,
            "event_mentions": [
                {
                    "node_id": "event-1",
                    "identity": {
                        "evidence_span": {"start": context.start, "end": context.end},
                        "mention_span": {
                            "start": case.event.trigger.start,
                            "end": case.event.trigger.end,
                        },
                    },
                }
            ],
            "participant_mentions": [
                {
                    "node_id": "participant-1",
                    "identity": {
                        "evidence_span": {"start": context.start, "end": context.end},
                        "mention_span": {
                            "start": participant.mention.start,
                            "end": participant.mention.end,
                        },
                    },
                }
            ],
            "semantic_evidence": [
                {
                    "event_id": "event-1",
                    "evidence_item_spans": [
                        {
                            "start": case.event.trigger.start,
                            "end": case.event.trigger.end,
                        }
                    ],
                    "statistical_observation_spans": [None],
                }
            ],
        },
    }
    return FreshCGProviderOutput.model_validate_json(json.dumps(payload))


def test_review_only_axis_generates_neither_credit_nor_penalty() -> None:
    case, reference = _reference_without_tiebreaker()
    review_only_direction = reference.direction.model_copy(
        update={
            "resolution": ResolutionMetadata(
                status="REVIEW_ONLY",
                agreeing_reviewer_ids=(),
                reviewer_value_sha256_by_id=(
                    reference.direction.resolution.reviewer_value_sha256_by_id
                ),
                tiebreaker_used=False,
            ),
            "value": None,
            "accepted_evidence": (),
        }
    )
    reference = reference.model_copy(update={"direction": review_only_direction})

    observed = evaluate_case(
        case,
        reference,
        _output(case, reference, direction="OBSERVED"),
    )
    not_applicable = evaluate_case(
        case,
        reference,
        _output(case, reference, direction="NOT_APPLICABLE"),
    )

    observed_direction = next(
        item for item in observed.artana_fields if item.field_id == "direction"
    )
    other_direction = next(
        item for item in not_applicable.artana_fields if item.field_id == "direction"
    )
    assert observed_direction.passed is None
    assert other_direction.passed is None
    assert observed.artana_failed_field_count == not_applicable.artana_failed_field_count
    assert observed.artana_passed_field_count == not_applicable.artana_passed_field_count
    assert observed.passed is False
    assert observed.reference_complete is False


def test_occurrence_binding_failure_precedes_scientific_scoring() -> None:
    case, reference = _reference_without_tiebreaker()
    output = _output(case, reference, direction="OBSERVED")
    binding = output.occurrence_bindings.event_mentions[0]
    bad_identity = binding.identity.model_copy(
        update={
            "mention_span": binding.identity.mention_span.model_copy(
                update={"start": binding.identity.mention_span.start - 1}
            )
        }
    )
    bad_output = output.model_copy(
        update={
            "occurrence_bindings": output.occurrence_bindings.model_copy(
                update={
                    "event_mentions": (
                        binding.model_copy(update={"identity": bad_identity}),
                    )
                }
            )
        }
    )

    with pytest.raises(OccurrenceBindingError, match="do not reproduce"):
        evaluate_case(case, reference, bad_output)


def test_semantic_evidence_cannot_split_a_source_token() -> None:
    case, reference = _reference_without_tiebreaker()
    output = _output(case, reference, direction="OBSERVED")
    axes = output.scientific_output.semantic_axes[0]
    semantic = output.occurrence_bindings.semantic_evidence[0]
    original_span = semantic.evidence_item_spans[0]
    split_text = axes.evidence_items[0][1:]
    split_span = original_span.model_copy(update={"start": original_span.start + 1})
    bad_output = output.model_copy(
        update={
            "scientific_output": output.scientific_output.model_copy(
                update={
                    "semantic_axes": (
                        axes.model_copy(update={"evidence_items": (split_text,)}),
                    )
                }
            ),
            "occurrence_bindings": output.occurrence_bindings.model_copy(
                update={
                    "semantic_evidence": (
                        semantic.model_copy(
                            update={"evidence_item_spans": (split_span,)}
                        ),
                    )
                }
            ),
        }
    )

    with pytest.raises(OccurrenceBindingError, match="semantic evidence.*split"):
        evaluate_case(case, reference, bad_output)
