"""Forward-only Fresh-CG V3 and V10 root-cause regressions."""

from __future__ import annotations

import inspect

from scripts.validation.public_gold.staged_event.generalization.contracts import (
    EventArgument,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v3.config import (
    DEFAULT_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v3.contracts import (
    ExposedCaseReferenceV3,
    ExposedCaseReplayV3,
    RootCauseConsensus,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v3.evaluation import (
    count_target_attachments_once,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v3.reference import (
    build_exposed_reference,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v3.runner import (
    preflight,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.exposed_audit import (
    audit as audit_v10,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.preflight import (
    verify as verify_v10,
)


def test_v3_preflight_preserves_sealed_and_uncalled_cases() -> None:
    result = preflight()

    assert result["status"] == "PASS"
    assert result["remaining_fresh_cases_preserved"] == 7
    assert result["scientific_provider_calls"] == 0
    assert result["graph_writes"] == 0
    assert result["qualification_credit"] is False


def test_v3_reference_is_adjudication_derived_not_output_tailored() -> None:
    parameters = inspect.signature(build_exposed_reference).parameters
    assert "raw_output_path" not in parameters
    assert "model_output" not in parameters

    generated = build_exposed_reference(
        v2_reference_path=DEFAULT_PATHS.v2_reference,
        dispute_packet_path=DEFAULT_PATHS.dispute_packet,
        consensus_path=DEFAULT_PATHS.consensus,
    )
    frozen = ExposedCaseReferenceV3.model_validate_json(
        DEFAULT_PATHS.reference.read_text(encoding="utf-8")
    )

    assert generated == frozen
    assert frozen.direction.value == "NOT_APPLICABLE"
    assert frozen.uncertainty.value == "ASSERTED"
    assert len(frozen.contextual_participants) == 1
    context = frozen.contextual_participants[0]
    assert context.mention.text == ("fresh BALB/c fibroblasts transformed by v-Ki-ras")
    assert context.role == "CONTEXTUAL_PARTICIPANT"
    assert frozen.v2_rescored is False
    assert frozen.model_output_used_to_choose_reference_values is False


def test_v3_replay_separates_root_error_from_cascades() -> None:
    result = ExposedCaseReplayV3.model_validate_json(
        DEFAULT_PATHS.result.read_text(encoding="utf-8")
    )
    fields = {item.field_id: item for item in result.fields}

    assert result.direct_cg_event_exact is True
    assert result.direct_cg_participant_exact is False
    assert result.genuine_model_error_issue_ids == ("A_DIRECT_PARTICIPANT_OCCURRENCE",)
    assert fields["role:T9"].status == "BLOCKED_BY_OCCURRENCE"
    assert fields["direct_attachment"].status == "BLOCKED_BY_OCCURRENCE"
    assert fields["contextual_participants"].status == "MATCH"
    assert fields["direction"].status == "MATCH"
    assert fields["uncertainty"].status == "MATCH"
    assert result.raw_v2_unsupported_count == 4
    assert result.independent_unsupported_root_count == 1
    assert result.cascaded_structural_miss_count == 3
    assert result.contradiction_count == 0
    assert result.scientific_pass_fail_recalculated is False
    assert result.frozen_v2_grader_invoked is False


def test_v3_attachment_mapping_traverses_multi_argument_link_once() -> None:
    arguments = (
        EventArgument(
            role="AFFECTED_ENTITY",
            target_kind="PARTICIPANT",
            target_id="participant-direct",
            explanation="The direct participant.",
        ),
        EventArgument(
            role="CONTEXTUAL_PARTICIPANT",
            target_kind="PARTICIPANT",
            target_id="participant-context",
            explanation="The source context.",
        ),
    )

    assert (
        count_target_attachments_once(
            arguments,
            target_id="participant-direct",
        )
        == 1
    )
    assert (
        count_target_attachments_once(
            arguments,
            target_id="participant-context",
        )
        == 1
    )


def test_consensus_did_not_trigger_unneeded_tiebreak_or_credit() -> None:
    consensus = RootCauseConsensus.model_validate_json(
        DEFAULT_PATHS.consensus.read_text(encoding="utf-8")
    )

    assert consensus.tiebreaker_run is False
    assert consensus.remaining_fresh_cases_consumed == 0
    assert consensus.graph_writes == 0
    assert consensus.qualification_credit is False
    assert consensus.human_expert_qualification_credit is False


def test_v10_is_one_preregistered_rule_and_remains_unexecuted() -> None:
    result = verify_v10()

    assert result["status"] == "PASS"
    assert result["single_scientific_change"] == (
        "NAMED_BIOMEDICAL_OCCURRENCE_BOUNDARY"
    )
    assert result["provider_calls"] == 0
    assert result["remaining_fresh_cases_preserved"] == 7
    assert result["graph_writes"] == 0
    assert result["qualification_credit"] is False


def test_v10_rule_finds_an_independent_exposed_example_without_fresh_calls() -> None:
    result = audit_v10()

    assert result.exposed_case_count == 5
    assert result.exposed_participant_count == 12
    assert result.changed_participant_count == 1
    assert result.unchanged_participant_count == 11
    assert result.findings[0].case_id == "generalization-uncertainty"
    assert result.findings[0].original_text == "SLC12A3 gene"
    assert result.findings[0].corrected_text == "SLC12A3"
    assert result.all_existing_evaluator_matches_preserved is True
    assert result.provider_calls == 0
    assert result.fresh_cases_consumed == 0
