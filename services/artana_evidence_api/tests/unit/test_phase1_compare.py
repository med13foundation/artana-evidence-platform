from __future__ import annotations

import asyncio
from uuid import UUID

import pytest
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorPlannerMode,
)
from artana_evidence_api.phase1_compare import (
    Phase1CompareRequest,
    _await_compare_phase,
    _build_compare_orchestrator_progress_observer,
    _build_phase1_cost_comparison,
    _collect_run_ids_from_payload,
    _CompareProgressObserver,
    _expand_run_lineage_from_events,
    _normalize_pending_questions,
    _progress_event_payload,
    build_compare_advisories,
    build_guarded_evaluation,
    build_phase1_source_preferences,
    compare_workspace_summaries,
    resolve_compare_environment,
    summarize_guarded_execution,
    summarize_workspace,
)


def test_build_phase1_source_preferences_marks_selected_sources() -> None:
    preferences = build_phase1_source_preferences(["pubmed", "clinvar"])

    assert preferences["pubmed"] is True
    assert preferences["clinvar"] is True
    assert preferences["marrvel"] is False


def test_build_phase1_source_preferences_rejects_unknown_sources() -> None:
    try:
        build_phase1_source_preferences(["pubmed", "mystery_source"])
    except ValueError as exc:
        assert "Unknown source keys" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected ValueError for unknown source")


def test_await_compare_phase_raises_timeout_with_phase_label() -> None:
    async def _sleep_forever() -> None:
        await asyncio.sleep(60)

    with pytest.raises(TimeoutError) as exc_info:
        asyncio.run(
            _await_compare_phase(
                awaitable=_sleep_forever(),
                timeout_seconds=0.01,
                flow="orchestrator",
                phase="shadow_checkpoint_flush",
                message="Shared-baseline shadow checkpoint flush",
                metadata={},
            )
        )

    assert "orchestrator phase 'shadow_checkpoint_flush' timed out" in str(
        exc_info.value,
    )


def test_summarize_workspace_extracts_high_signal_fields() -> None:
    summary = summarize_workspace(
        {
            "status": "completed",
            "documents_ingested": 3,
            "proposal_count": 5,
            "pending_questions": [],
            "errors": [],
            "pubmed_results": [{"query": "MED13", "total_found": 4}],
            "driven_terms": ["MED13", "MED13L"],
            "bootstrap_run_id": "bootstrap-1",
            "bootstrap_summary": {"proposal_count": 2},
            "research_brief": {"title": "Brief"},
            "pending_chase_round": {
                "round_number": 1,
                "deterministic_candidate_count": 2,
                "deterministic_threshold_met": False,
                "filtered_chase_candidate_count": 3,
                "filtered_chase_filter_reason_counts": {
                    "generic_result_label": 1,
                    "clinical_significance_bucket": 2,
                },
                "filtered_chase_candidates": [
                    {"display_label": "result 1"},
                    {"display_label": "Pathogenic variant"},
                    {"display_label": "Likely benign variant"},
                ],
            },
            "source_results": {
                "pubmed": {"status": "completed"},
                "clinvar": {"status": "skipped"},
            },
            "planner_execution_mode": "guarded",
            "guarded_execution": {
                "mode": "guarded",
                "applied_count": 1,
                "verified_count": 1,
                "verification_failed_count": 0,
                "pending_verification_count": 0,
                "actions": [],
            },
            "guarded_decision_proofs_key": (
                "full_ai_orchestrator_guarded_decision_proofs"
            ),
            "guarded_decision_proofs": {
                "mode": "guarded",
                "policy_version": "guarded-rollout.v1",
                "guarded_rollout_profile": "guarded_chase_only",
                "guarded_rollout_profile_source": "request",
                "proof_count": 2,
                "allowed_count": 1,
                "blocked_count": 1,
                "ignored_count": 0,
                "verified_count": 1,
                "verification_failed_count": 0,
                "pending_verification_count": 0,
                "artifact_keys": [
                    "full_ai_orchestrator_guarded_decision_proof_001",
                ],
                "proofs": [
                    {
                        "proof_id": "guarded-proof-001-after_bootstrap",
                        "checkpoint_key": "after_bootstrap",
                        "guarded_strategy": "chase_selection",
                        "guarded_rollout_profile": "guarded_chase_only",
                        "guarded_rollout_profile_source": "request",
                        "decision_outcome": "allowed",
                        "outcome_reason": "guarded_policy_allowed",
                        "recommended_action_type": "RUN_CHASE_ROUND",
                        "applied_action_type": "RUN_CHASE_ROUND",
                        "policy_allowed": True,
                        "verification_status": "verified",
                        "used_fallback": False,
                        "fallback_reason": None,
                        "validation_error": None,
                        "qualitative_rationale_present": True,
                        "budget_violation": False,
                        "disabled_source_violation": False,
                        "planner_status": "completed",
                        "model_id": "openai/test",
                        "prompt_version": "phase2-shadow-planner.v1",
                        "agent_run_id": "agent-run-1",
                        "recommendation": {"large": "payload"},
                    },
                ],
            },
        },
    )

    assert summary["documents_ingested"] == 3
    assert summary["brief_present"] is True
    assert summary["planner_execution_mode"] == "guarded"
    assert summary["guarded_execution"] == {
        "mode": "guarded",
        "applied_count": 1,
        "verified_count": 1,
        "verification_failed_count": 0,
        "pending_verification_count": 0,
        "actions": [],
    }
    assert summary["guarded_decision_proofs_key"] == (
        "full_ai_orchestrator_guarded_decision_proofs"
    )
    assert summary["guarded_decision_proofs"] == {
        "mode": "guarded",
        "policy_version": "guarded-rollout.v1",
        "guarded_rollout_profile": "guarded_chase_only",
        "guarded_rollout_profile_source": "request",
        "proof_count": 2,
        "allowed_count": 1,
        "blocked_count": 1,
        "ignored_count": 0,
        "verified_count": 1,
        "verification_failed_count": 0,
        "pending_verification_count": 0,
        "artifact_keys": ["full_ai_orchestrator_guarded_decision_proof_001"],
        "proofs": [
            {
                "proof_id": "guarded-proof-001-after_bootstrap",
                "checkpoint_key": "after_bootstrap",
                "guarded_strategy": "chase_selection",
                "guarded_rollout_profile": "guarded_chase_only",
                "guarded_rollout_profile_source": "request",
                "decision_outcome": "allowed",
                "outcome_reason": "guarded_policy_allowed",
                "recommended_action_type": "RUN_CHASE_ROUND",
                "applied_action_type": "RUN_CHASE_ROUND",
                "policy_allowed": True,
                "verification_status": "verified",
                "used_fallback": False,
                "fallback_reason": None,
                "validation_error": None,
                "qualitative_rationale_present": True,
                "budget_violation": False,
                "disabled_source_violation": False,
                "planner_status": "completed",
                "model_id": "openai/test",
                "prompt_version": "phase2-shadow-planner.v1",
                "agent_run_id": "agent-run-1",
            },
        ],
    }
    assert summary["source_results"] == {
        "pubmed": {"status": "completed"},
        "clinvar": {"status": "skipped"},
    }
    assert summary["pending_chase_round"] == {
        "round_number": 1,
        "candidate_count": None,
        "deterministic_candidate_count": 2,
        "deterministic_threshold_met": False,
        "selection_mode": None,
        "selected_labels": [],
        "filtered_chase_candidate_count": 3,
        "filtered_chase_filter_reason_counts": {
            "generic_result_label": 1,
            "clinical_significance_bucket": 2,
        },
        "filtered_chase_labels": [
            "result 1",
            "Pathogenic variant",
            "Likely benign variant",
        ],
    }


def test_summarize_guarded_execution_extracts_failed_actions() -> None:
    summary = summarize_guarded_execution(
        {
            "mode": "guarded",
            "applied_count": 2,
            "verified_count": 1,
            "verification_failed_count": 1,
            "pending_verification_count": 0,
            "actions": [
                {
                    "checkpoint_key": "after_driven_terms_ready",
                    "applied_action_type": "RUN_STRUCTURED_ENRICHMENT",
                    "applied_source_key": "drugbank",
                    "verification_status": "verified",
                    "verification_reason": "selected_source_completed",
                },
                {
                    "checkpoint_key": "after_chase_round_1",
                    "applied_action_type": "GENERATE_BRIEF",
                    "applied_source_key": None,
                    "verification_status": "verification_failed",
                    "verification_reason": "brief_missing",
                },
            ],
        },
    )

    assert summary["present"] is True
    assert summary["all_verified"] is False
    assert summary["verification_failed_count"] == 1
    assert summary["failed_actions"] == [
        {
            "checkpoint_key": "after_chase_round_1",
            "action_type": "GENERATE_BRIEF",
            "source_key": None,
            "verification_reason": "brief_missing",
        },
    ]


def test_summarize_guarded_execution_tracks_chase_selection_metrics() -> None:
    summary = summarize_guarded_execution(
        {
            "mode": "guarded",
            "applied_count": 1,
            "verified_count": 1,
            "verification_failed_count": 0,
            "pending_verification_count": 0,
            "actions": [
                {
                    "checkpoint_key": "after_bootstrap",
                    "applied_action_type": "RUN_CHASE_ROUND",
                    "applied_source_key": None,
                    "guarded_strategy": "chase_selection",
                    "round_number": 1,
                    "selected_entity_ids": ["entity-gata4", "entity-tbx5"],
                    "selected_labels": ["GATA4", "TBX5"],
                    "deterministic_selected_entity_ids": [
                        "entity-gata4",
                        "entity-tbx5",
                    ],
                    "deterministic_selected_labels": ["GATA4", "TBX5"],
                    "selection_basis": "These are the strongest next candidates.",
                    "verification_status": "verified",
                    "verification_reason": "selected_subset_completed",
                },
            ],
        },
    )

    assert summary["chase_action_count"] == 1
    assert summary["chase_verified_count"] == 1
    assert summary["chase_exact_selection_match_count"] == 1
    assert summary["chase_selected_entity_overlap_total"] == 2
    assert summary["chase_selection_mismatch_count"] == 0
    assert summary["actions"][0]["guarded_strategy"] == "chase_selection"
    assert summary["actions"][0]["selected_labels"] == ["GATA4", "TBX5"]
    assert summary["actions"][0]["exact_selection_match"] is True
    assert summary["actions"][0]["selected_entity_overlap_count"] == 2


def test_summarize_guarded_execution_tracks_terminal_control_metrics() -> None:
    summary = summarize_guarded_execution(
        {
            "mode": "guarded",
            "applied_count": 1,
            "verified_count": 1,
            "verification_failed_count": 0,
            "pending_verification_count": 0,
            "actions": [
                {
                    "checkpoint_key": "after_bootstrap",
                    "applied_action_type": "STOP",
                    "applied_source_key": None,
                    "guarded_strategy": "terminal_control_flow",
                    "comparison_status": "matched",
                    "target_action_type": "RUN_CHASE_ROUND",
                    "target_source_key": None,
                    "planner_status": "completed",
                    "qualitative_rationale": "The candidate set is too weak to justify a chase round.",
                    "stop_reason": "threshold_not_met",
                    "deterministic_stop_expected": True,
                    "verification_status": "verified",
                    "verification_reason": "threshold_not_met",
                },
            ],
        },
    )

    assert summary["terminal_control_action_count"] == 1
    assert summary["terminal_control_verified_count"] == 1
    assert summary["chase_checkpoint_stop_count"] == 1
    assert summary["actions"][0]["action_type"] == "STOP"
    assert summary["actions"][0]["stop_reason"] == "threshold_not_met"
    assert summary["actions"][0]["deterministic_stop_expected"] is True


def test_build_guarded_evaluation_reports_clean_guarded_run() -> None:
    evaluation = build_guarded_evaluation(
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        orchestrator_workspace={
            "guarded_execution": {
                "mode": "guarded",
                "applied_count": 1,
                "verified_count": 1,
                "verification_failed_count": 0,
                "pending_verification_count": 0,
                "actions": [
                    {
                        "checkpoint_key": "after_driven_terms_ready",
                        "applied_action_type": "RUN_STRUCTURED_ENRICHMENT",
                        "applied_source_key": "drugbank",
                        "verification_status": "verified",
                        "verification_reason": "selected_source_completed",
                    },
                ],
            },
        },
    )

    assert evaluation["mode"] == "guarded"
    assert evaluation["status"] == "clean"
    assert evaluation["all_verified"] is True
    assert evaluation["candidate_count"] == 0
    assert evaluation["identified_count"] == 1
    assert evaluation["verified_count"] == 1


def test_build_guarded_evaluation_exposes_applied_terminal_control_actions() -> None:
    evaluation = build_guarded_evaluation(
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        orchestrator_workspace={
            "guarded_execution": {
                "mode": "guarded",
                "applied_count": 1,
                "verified_count": 1,
                "verification_failed_count": 0,
                "pending_verification_count": 0,
                "actions": [
                    {
                        "checkpoint_key": "after_bootstrap",
                        "applied_action_type": "STOP",
                        "applied_source_key": None,
                        "guarded_strategy": "terminal_control_flow",
                        "comparison_status": "matched",
                        "target_action_type": "RUN_CHASE_ROUND",
                        "target_source_key": None,
                        "planner_status": "completed",
                        "qualitative_rationale": "Stop before a low-value chase round.",
                        "stop_reason": "threshold_not_met",
                        "deterministic_stop_expected": True,
                        "verification_status": "verified",
                        "verification_reason": "threshold_not_met",
                    },
                ],
            },
        },
    )

    assert evaluation["status"] == "clean"
    assert evaluation["terminal_control_action_count"] == 1
    assert evaluation["terminal_control_verified_count"] == 1
    assert evaluation["chase_checkpoint_stop_count"] == 1
    assert evaluation["applied_actions"] == [
        {
            "checkpoint_key": "after_bootstrap",
            "action_type": "STOP",
            "source_key": None,
            "guarded_strategy": "terminal_control_flow",
            "round_number": None,
            "comparison_status": "matched",
            "target_action_type": "RUN_CHASE_ROUND",
            "target_source_key": None,
            "planner_status": "completed",
            "qualitative_rationale": "Stop before a low-value chase round.",
            "stop_reason": "threshold_not_met",
            "recommended_stop": None,
            "deterministic_stop_expected": True,
            "verification_status": "verified",
            "verification_reason": "threshold_not_met",
        },
    ]


def test_build_guarded_evaluation_reports_replay_only_candidate() -> None:
    evaluation = build_guarded_evaluation(
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        orchestrator_workspace={
            "guarded_execution": {
                "mode": "guarded",
                "applied_count": 0,
                "verified_count": 0,
                "verification_failed_count": 0,
                "pending_verification_count": 0,
                "actions": [],
            },
            "source_results": {
                "drugbank": {"status": "completed"},
                "clinical_trials": {"status": "completed"},
            },
        },
        shadow_planner_summary={
            "timeline": [
                {
                    "checkpoint_key": "after_driven_terms_ready",
                    "recommendation": {
                        "planner_status": "completed",
                        "decision": {
                            "decision_id": "shadow-1",
                            "action_type": "RUN_STRUCTURED_ENRICHMENT",
                            "source_key": "drugbank",
                            "step_key": "shadow.step",
                            "evidence_basis": "DrugBank is the tighter next step.",
                            "qualitative_rationale": "The drug-mechanism objective points to DrugBank first.",
                            "expected_value_band": "medium",
                            "risk_level": "low",
                        },
                    },
                    "comparison": {
                        "checkpoint_key": "after_driven_terms_ready",
                        "comparison_status": "mismatch",
                        "target_action_type": "RUN_STRUCTURED_ENRICHMENT",
                        "target_source_key": "clinical_trials",
                    },
                },
            ],
        },
    )

    assert evaluation["status"] == "candidate_detected_replay_only"
    assert evaluation["applied_count"] == 0
    assert evaluation["candidate_count"] == 1
    assert evaluation["identified_count"] == 1
    assert evaluation["all_verified"] is None
    assert evaluation["candidate_actions"] == [
        {
            "checkpoint_key": "after_driven_terms_ready",
            "action_type": "RUN_STRUCTURED_ENRICHMENT",
            "source_key": "drugbank",
            "guarded_strategy": "prioritized_structured_sequence",
            "round_number": None,
            "comparison_status": "mismatch",
            "target_action_type": "RUN_STRUCTURED_ENRICHMENT",
            "target_source_key": "clinical_trials",
            "planner_status": "completed",
            "qualitative_rationale": "The drug-mechanism objective points to DrugBank first.",
            "stop_reason": None,
            "recommended_stop": None,
            "deterministic_stop_expected": None,
            "verification_status": "pending",
            "verification_reason": None,
            "evaluation_mode": "shared_baseline_replay_counterfactual",
        },
    ]


def test_build_guarded_evaluation_reports_replay_only_chase_candidate() -> None:
    evaluation = build_guarded_evaluation(
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        orchestrator_workspace={
            "guarded_execution": {
                "mode": "guarded",
                "applied_count": 0,
                "verified_count": 0,
                "verification_failed_count": 0,
                "pending_verification_count": 0,
                "actions": [],
            },
        },
        shadow_planner_summary={
            "timeline": [
                {
                    "checkpoint_key": "after_bootstrap",
                    "workspace_summary": {
                        "chase_candidates": [
                            {
                                "entity_id": "entity-gata4",
                                "display_label": "GATA4",
                                "normalized_label": "gata4",
                                "candidate_rank": 1,
                                "observed_round": 1,
                                "available_source_keys": ["marrvel", "clinvar"],
                                "evidence_basis": "Observed after bootstrap.",
                                "novelty_basis": "not_in_previous_seed_terms",
                            },
                            {
                                "entity_id": "entity-tbx5",
                                "display_label": "TBX5",
                                "normalized_label": "tbx5",
                                "candidate_rank": 2,
                                "observed_round": 1,
                                "available_source_keys": ["marrvel", "clinvar"],
                                "evidence_basis": "Observed after bootstrap.",
                                "novelty_basis": "not_in_previous_seed_terms",
                            },
                        ],
                        "deterministic_selection": {
                            "selected_entity_ids": [
                                "entity-gata4",
                                "entity-tbx5",
                            ],
                            "selected_labels": ["GATA4", "TBX5"],
                            "stop_instead": False,
                            "stop_reason": None,
                            "selection_basis": "Deterministic threshold met.",
                        },
                    },
                    "recommendation": {
                        "planner_status": "completed",
                        "decision": {
                            "decision_id": "shadow-1",
                            "action_type": "RUN_CHASE_ROUND",
                            "source_key": None,
                            "step_key": "shadow.step",
                            "evidence_basis": "These chase leads are the strongest.",
                            "qualitative_rationale": "The bootstrap leads point to the same two follow-up genes.",
                            "expected_value_band": "medium",
                            "risk_level": "low",
                            "action_input": {
                                "selected_entity_ids": [
                                    "entity-gata4",
                                    "entity-tbx5",
                                ],
                                "selected_labels": ["GATA4", "TBX5"],
                                "selection_basis": "These are the clearest next follow-ups.",
                            },
                        },
                    },
                    "comparison": {
                        "checkpoint_key": "after_bootstrap",
                        "comparison_status": "matched",
                        "target_action_type": "RUN_CHASE_ROUND",
                        "target_source_key": None,
                    },
                },
            ],
        },
    )

    assert evaluation["status"] == "candidate_detected_replay_only"
    assert evaluation["candidate_count"] == 1
    assert evaluation["chase_candidate_count"] == 1
    assert evaluation["chase_candidate_exact_selection_match_count"] == 1
    assert evaluation["chase_candidate_overlap_total"] == 2
    assert evaluation["candidate_actions"][0]["guarded_strategy"] == "chase_selection"
    assert evaluation["candidate_actions"][0]["round_number"] == 1
    assert evaluation["candidate_actions"][0]["selected_labels"] == ["GATA4", "TBX5"]
    assert evaluation["candidate_actions"][0]["exact_selection_match"] is True


def test_build_guarded_evaluation_is_not_applicable_for_shadow_mode() -> None:
    evaluation = build_guarded_evaluation(
        planner_mode=FullAIOrchestratorPlannerMode.SHADOW,
        orchestrator_workspace={},
    )

    assert evaluation["status"] == "not_applicable"
    assert evaluation["all_verified"] is None
    assert evaluation["candidate_count"] == 0


def test_compare_workspace_summaries_reports_meaningful_differences() -> None:
    mismatches = compare_workspace_summaries(
        baseline={
            "documents_ingested": 3,
            "proposal_count": 4,
            "pending_questions": [],
            "pubmed_results": [{"query": "MED13"}],
            "driven_terms": ["MED13"],
            "brief_present": True,
            "source_results": {"pubmed": {"status": "completed"}},
        },
        orchestrator={
            "documents_ingested": 3,
            "proposal_count": 5,
            "pending_questions": [],
            "pubmed_results": [{"query": "MED13"}],
            "driven_terms": ["MED13", "MED13L"],
            "brief_present": False,
            "source_results": {"pubmed": {"status": "running"}},
        },
    )

    assert any("proposal_count" in mismatch for mismatch in mismatches)
    assert any("driven_terms" in mismatch for mismatch in mismatches)
    assert any("brief_present" in mismatch for mismatch in mismatches)
    assert any("source_results differ" in mismatch for mismatch in mismatches)


def test_compare_workspace_summaries_normalizes_uuid_only_pending_questions() -> None:
    mismatches = compare_workspace_summaries(
        baseline={
            "documents_ingested": 3,
            "proposal_count": 4,
            "pending_questions": [
                "What evidence best supports 11111111-1111-4111-8111-111111111111 CAUSES 22222222-2222-4222-8222-222222222222?"
            ],
            "pubmed_results": [{"query": "MED13"}],
            "driven_terms": ["MED13"],
            "brief_present": True,
            "source_results": {"pubmed": {"status": "completed"}},
        },
        orchestrator={
            "documents_ingested": 3,
            "proposal_count": 4,
            "pending_questions": [
                "What evidence best supports aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa CAUSES bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb?"
            ],
            "pubmed_results": [{"query": "MED13"}],
            "driven_terms": ["MED13"],
            "brief_present": True,
            "source_results": {"pubmed": {"status": "completed"}},
        },
    )

    assert not any("pending_questions" in mismatch for mismatch in mismatches)


def test_compare_workspace_summaries_normalizes_pending_question_relation_wording() -> (
    None
):
    mismatches = compare_workspace_summaries(
        baseline={
            "documents_ingested": 3,
            "proposal_count": 4,
            "pending_questions": [
                "What evidence best supports BRCA1 BIOMARKER_FOR PARP inhibitor response?"
            ],
            "pubmed_results": [{"query": "BRCA1"}],
            "driven_terms": ["BRCA1"],
            "brief_present": True,
            "source_results": {"pubmed": {"status": "completed"}},
        },
        orchestrator={
            "documents_ingested": 3,
            "proposal_count": 4,
            "pending_questions": [
                "What evidence best supports BRCA1 ASSOCIATED_WITH PARP inhibitor response?"
            ],
            "pubmed_results": [{"query": "BRCA1"}],
            "driven_terms": ["BRCA1"],
            "brief_present": True,
            "source_results": {"pubmed": {"status": "completed"}},
        },
    )

    assert not any("pending_questions" in mismatch for mismatch in mismatches)


def test_compare_workspace_summaries_normalizes_pending_question_order() -> None:
    mismatches = compare_workspace_summaries(
        baseline={
            "documents_ingested": 3,
            "proposal_count": 4,
            "pending_questions": [
                "What evidence best supports BRCA1 BIOMARKER_FOR PARP inhibitor response?",
                "What evidence best supports BRCA1 PART_OF DNA repair?",
            ],
            "pubmed_results": [{"query": "BRCA1"}],
            "driven_terms": ["BRCA1"],
            "brief_present": True,
            "source_results": {"pubmed": {"status": "completed"}},
        },
        orchestrator={
            "documents_ingested": 3,
            "proposal_count": 4,
            "pending_questions": [
                "What evidence best supports BRCA1 PART_OF DNA repair?",
                "What evidence best supports BRCA1 ASSOCIATED_WITH PARP inhibitor response?",
            ],
            "pubmed_results": [{"query": "BRCA1"}],
            "driven_terms": ["BRCA1"],
            "brief_present": True,
            "source_results": {"pubmed": {"status": "completed"}},
        },
    )

    assert not any("pending_questions" in mismatch for mismatch in mismatches)


def test_compare_workspace_summaries_deduplicates_normalized_pending_questions() -> (
    None
):
    mismatches = compare_workspace_summaries(
        baseline={
            "documents_ingested": 3,
            "proposal_count": 4,
            "pending_questions": [
                "What evidence best supports BRCA1 BIOMARKER_FOR PARP inhibitor response?",
                "What evidence best supports BRCA1 BIOMARKER_FOR PARP inhibitor response?",
            ],
            "pubmed_results": [{"query": "BRCA1"}],
            "driven_terms": ["BRCA1"],
            "brief_present": True,
            "source_results": {"pubmed": {"status": "completed"}},
        },
        orchestrator={
            "documents_ingested": 3,
            "proposal_count": 4,
            "pending_questions": [
                "What evidence best supports BRCA1 ASSOCIATED_WITH PARP inhibitor response?",
            ],
            "pubmed_results": [{"query": "BRCA1"}],
            "driven_terms": ["BRCA1"],
            "brief_present": True,
            "source_results": {"pubmed": {"status": "completed"}},
        },
    )

    assert not any("pending_questions" in mismatch for mismatch in mismatches)


def test_compare_workspace_summaries_normalizes_order_insensitive_source_results() -> (
    None
):
    mismatches = compare_workspace_summaries(
        baseline={
            "documents_ingested": 3,
            "proposal_count": 4,
            "pending_questions": [],
            "pubmed_results": [{"query": "BRCA1"}],
            "driven_terms": ["BRCA1"],
            "brief_present": True,
            "source_results": {
                "enrichment_orchestration": {
                    "selected_enrichment_sources": [
                        "clinvar",
                        "drugbank",
                        "alphafold",
                    ],
                    "driven_genes_from_pubmed": ["BRCA1", "PARP"],
                },
                "pending_chase_round": {
                    "filtered_chase_labels": [
                        "result 1",
                        "Colletotrichum fioriniae",
                        "Pathogenic variant",
                    ],
                },
            },
        },
        orchestrator={
            "documents_ingested": 3,
            "proposal_count": 4,
            "pending_questions": [],
            "pubmed_results": [{"query": "BRCA1"}],
            "driven_terms": ["BRCA1"],
            "brief_present": True,
            "source_results": {
                "pending_chase_round": {
                    "filtered_chase_labels": [
                        "Pathogenic variant",
                        "result 1",
                        "Colletotrichum fioriniae",
                    ],
                },
                "enrichment_orchestration": {
                    "selected_enrichment_sources": [
                        "alphafold",
                        "drugbank",
                        "clinvar",
                    ],
                    "driven_genes_from_pubmed": ["PARP", "BRCA1"],
                },
            },
        },
    )

    assert not any("source_results differ" in mismatch for mismatch in mismatches)


def test_collect_run_ids_from_payload_uses_run_id_fields_only() -> None:
    run_ids = _collect_run_ids_from_payload(
        {
            "run_id": "root-run",
            "bootstrap_run_id": "bootstrap-run",
            "agent_run_ids": ["agent-1", "agent-2"],
            "nested": {
                "extraction_agent_run_id": "extract-1",
                "entity_id": "11111111-1111-4111-8111-111111111111",
                "other_ids": ["ignore-me"],
            },
            "plain_uuid": "22222222-2222-4222-8222-222222222222",
        },
    )

    assert run_ids == [
        "root-run",
        "bootstrap-run",
        "agent-1",
        "agent-2",
        "extract-1",
    ]


def test_collect_run_ids_from_payload_parses_embedded_json_strings() -> None:
    run_ids = _collect_run_ids_from_payload(
        {
            "summary_json": (
                '{"run_id":"research-init-extraction:abc",'
                '"nested":{"agent_run_ids":["document-proposal-review:def"]}}'
            ),
        },
    )

    assert run_ids == [
        "research-init-extraction:abc",
        "document-proposal-review:def",
    ]


def test_expand_run_lineage_from_events_discovers_child_run_ids() -> None:
    class _Payload:
        def __init__(self, data: dict[str, object]) -> None:
            self._data = data

        def model_dump(self, *, mode: str) -> dict[str, object]:
            assert mode == "json"
            return self._data

    class _Event:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = _Payload(payload)

    class _Store:
        async def get_events_for_run(self, run_id: str) -> list[object]:
            if run_id == "baseline-run":
                return [
                    _Event(
                        {
                            "summary_json": (
                                '{"run_id":"research-init-extraction:child-1"}'
                            ),
                        },
                    ),
                ]
            if run_id == "research-init-extraction:child-1":
                return [
                    _Event(
                        {
                            "result_json": (
                                '{"agent_run_ids":['
                                '"document-proposal-review:child-2"'
                                "]} "
                            ).strip(),
                        },
                    ),
                ]
            return []

    run_ids = asyncio.run(
        _expand_run_lineage_from_events(
            store=_Store(),
            run_ids=("baseline-run",),
        ),
    )

    assert run_ids == [
        "baseline-run",
        "research-init-extraction:child-1",
        "document-proposal-review:child-2",
    ]


def test_normalize_pending_questions_replaces_embedded_uuids() -> None:
    normalized = _normalize_pending_questions(
        [
            "What evidence best supports 11111111-1111-4111-8111-111111111111 CAUSES 22222222-2222-4222-8222-222222222222?"
        ],
    )

    assert normalized == ["What evidence best supports <uuid> <relation> <uuid>?"]


def test_normalize_pending_questions_deduplicates_equivalent_questions() -> None:
    normalized = _normalize_pending_questions(
        [
            "What evidence best supports BRCA1 BIOMARKER_FOR PARP inhibitor response?",
            "What evidence best supports BRCA1 ASSOCIATED_WITH PARP inhibitor response?",
        ],
    )

    assert normalized == [
        "What evidence best supports BRCA1 <relation> PARP inhibitor response?",
    ]


def test_progress_event_payload_is_stable() -> None:
    payload = _progress_event_payload(
        flow="baseline",
        phase="structured_enrichment",
        message="Querying structured sources.",
        progress_percent=0.45,
        completed_steps=2,
        metadata={"source_count": 4},
    )

    assert payload == {
        "flow": "baseline",
        "phase": "structured_enrichment",
        "message": "Querying structured sources.",
        "progress_percent": 0.45,
        "completed_steps": 2,
        "metadata": {"source_count": 4},
    }


def test_build_phase1_cost_comparison_uses_real_baseline_totals() -> None:
    comparison = _build_phase1_cost_comparison(
        baseline_telemetry={
            "status": "available",
            "cost_usd": 0.02,
            "total_tokens": 1000,
            "latency_seconds": 2.5,
        },
        shadow_cost_tracking={
            "status": "available",
            "planner_total_cost_usd": 0.03,
            "planner_total_tokens": 600,
            "planner_total_latency_seconds": 1.25,
        },
    )

    assert comparison["status"] == "available"
    assert comparison["evaluated"] is True
    assert comparison["planner_vs_baseline_cost_ratio"] == 1.5
    assert comparison["gate_within_2x_baseline"] is True


def test_build_phase1_cost_comparison_handles_missing_baseline_cost() -> None:
    comparison = _build_phase1_cost_comparison(
        baseline_telemetry={"status": "unavailable"},
        shadow_cost_tracking={
            "status": "available",
            "planner_total_cost_usd": 0.03,
        },
    )

    assert comparison["status"] == "partial"
    assert comparison["evaluated"] is False
    assert comparison["gate_within_2x_baseline"] is None


def test_compare_progress_observer_skips_duplicate_signatures() -> None:
    observer = _CompareProgressObserver(flow="baseline")

    observer.on_progress(
        phase="pubmed_discovery",
        message="Discovering papers.",
        progress_percent=0.2,
        completed_steps=1,
        metadata={},
        workspace_snapshot={},
    )
    first_signature = observer.last_signature

    observer.on_progress(
        phase="pubmed_discovery",
        message="Discovering papers.",
        progress_percent=0.2,
        completed_steps=1,
        metadata={"ignored": True},
        workspace_snapshot={"ignored": True},
    )

    assert observer.last_signature == first_signature


def test_build_compare_orchestrator_progress_observer_matches_runtime_contract() -> (
    None
):
    request = Phase1CompareRequest(
        objective="Investigate MED13 syndrome",
        seed_terms=("MED13",),
        title="MED13 parity compare",
        sources=build_phase1_source_preferences(
            ["pubmed", "clinvar", "marrvel", "pdf", "text"],
        ),
        max_depth=2,
        max_hypotheses=20,
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
    )

    progress_observer = _build_compare_orchestrator_progress_observer(
        artifact_store=HarnessArtifactStore(),
        space_id=UUID("11111111-1111-4111-8111-111111111111"),
        run_id="22222222-2222-4222-8222-222222222222",
        request=request,
    )

    assert progress_observer.action_registry
    assert progress_observer.planner_mode is FullAIOrchestratorPlannerMode.GUARDED
    assert progress_observer.initial_workspace_summary["checkpoint_key"] == (
        "before_first_action"
    )
    assert progress_observer.initial_workspace_summary["counts"] == {
        "documents_ingested": 0,
        "proposal_count": 0,
        "pending_question_count": 0,
        "error_count": 0,
        "evidence_gap_count": 0,
        "contradiction_count": 0,
    }


def test_resolve_compare_environment_defaults_to_default_backend(monkeypatch) -> None:
    monkeypatch.delenv("ARTANA_PUBMED_SEARCH_BACKEND", raising=False)

    assert resolve_compare_environment() == {
        "pubmed_search_backend": "default",
    }


def test_build_compare_advisories_warns_for_live_backend_mismatches() -> None:
    advisories = build_compare_advisories(
        mismatches=["proposal_count: baseline=1 orchestrator=2"],
        environment={"pubmed_search_backend": "default"},
    )

    assert advisories == [
        "Live PubMed/backend variability can change candidate sets and proposal counts between runs; rerun compare with the deterministic backend to isolate orchestrator parity."
    ]


def test_build_compare_advisories_warns_for_guarded_verification_failures() -> None:
    advisories = build_compare_advisories(
        mismatches=[],
        environment={"pubmed_search_backend": "deterministic"},
        guarded_evaluation={"status": "verification_failed"},
    )

    assert advisories == [
        "Guarded pilot accepted an action that did not verify cleanly; inspect guarded_evaluation.failed_actions before widening the allowlist."
    ]


def test_build_compare_advisories_explains_expected_live_guarded_divergence() -> None:
    advisories = build_compare_advisories(
        mismatches=["proposal_count: baseline=8 orchestrator=5"],
        environment={
            "pubmed_search_backend": "deterministic",
            "compare_mode": "dual_live_guarded",
        },
        guarded_evaluation={"status": "clean"},
    )

    assert advisories == [
        "Live guarded compare is expected to diverge from the deterministic baseline when the planner actually narrows structured sources or stops before chase round 2."
    ]
