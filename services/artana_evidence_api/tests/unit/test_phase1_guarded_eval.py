from __future__ import annotations

from artana_evidence_api.phase2_shadow_fixture_refresh import (
    phase2_shadow_fixture_specs_for_set,
)

from scripts.run_phase1_guarded_eval import (
    _build_fixture_failure_compare_payload,
    _build_fixture_guarded_graduation_review,
    _build_fixture_review_summary,
    _build_guarded_graduation_gate,
    _build_guarded_report,
    _render_filtered_chase_summary,
    _selected_action_display,
    render_phase1_guarded_evaluation_markdown,
)


def _guarded_proof(**overrides: object) -> dict[str, object]:
    proof: dict[str, object] = {
        "proof_id": "guarded-proof-001-after_bootstrap",
        "checkpoint_key": "after_bootstrap",
        "guarded_strategy": "chase_selection",
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
    }
    proof.update(overrides)
    return proof


def _guarded_proof_summary(
    proofs: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "mode": "guarded",
        "policy_version": "guarded-rollout.v1",
        "guarded_rollout_profile": "guarded_low_risk",
        "proof_count": len(proofs),
        "allowed_count": sum(
            1 for proof in proofs if proof.get("decision_outcome") == "allowed"
        ),
        "blocked_count": sum(
            1 for proof in proofs if proof.get("decision_outcome") == "blocked"
        ),
        "ignored_count": sum(
            1 for proof in proofs if proof.get("decision_outcome") == "ignored"
        ),
        "verified_count": sum(
            1 for proof in proofs if proof.get("verification_status") == "verified"
        ),
        "verification_failed_count": sum(
            1
            for proof in proofs
            if proof.get("verification_status") == "verification_failed"
        ),
        "pending_verification_count": sum(
            1 for proof in proofs if proof.get("verification_status") == "pending"
        ),
        "artifact_keys": ["full_ai_orchestrator_guarded_decision_proof_001"],
        "proofs": proofs,
    }


def test_guarded_graduation_review_passes_verified_allowed_proofs() -> None:
    review = _build_fixture_guarded_graduation_review(
        fixture_name="BRCA1",
        proof_summary=_guarded_proof_summary([_guarded_proof()]),
    )

    assert review["gate_passed"] is True
    assert review["proof_summary_present"] is True
    assert review["allowed_count"] == 1
    assert review["blocked_or_ignored_count"] == 0
    assert review["notes"] == []


def test_guarded_graduation_review_fails_missing_proof_summary() -> None:
    review = _build_fixture_guarded_graduation_review(
        fixture_name="BRCA1",
        proof_summary={},
    )

    assert review["gate_passed"] is False
    assert review["proof_summary_present"] is False
    assert "missing guarded decision proof summary" in review["notes"]


def test_guarded_graduation_review_fails_unsafe_proof_receipts() -> None:
    review = _build_fixture_guarded_graduation_review(
        fixture_name="MED13",
        proof_summary=_guarded_proof_summary(
            [
                _guarded_proof(
                    proof_id="guarded-proof-001-after_driven_terms_ready",
                    decision_outcome="blocked",
                    outcome_reason="invalid_planner_output",
                    applied_action_type=None,
                    policy_allowed=False,
                    verification_status=None,
                    used_fallback=True,
                    validation_error="source disabled",
                    qualitative_rationale_present=False,
                    budget_violation=True,
                    disabled_source_violation=True,
                    planner_status="invalid",
                )
            ],
        ),
    )

    assert review["gate_passed"] is False
    assert review["fallback_count"] == 1
    assert review["invalid_output_count"] == 1
    assert review["budget_violation_count"] == 1
    assert review["disabled_source_violation_count"] == 1
    assert review["missing_rationale_count"] == 1
    assert review["blocked_or_ignored_count"] == 1


def test_guarded_graduation_gate_aggregates_fixture_reviews() -> None:
    passing_review = _build_fixture_guarded_graduation_review(
        fixture_name="BRCA1",
        proof_summary=_guarded_proof_summary([_guarded_proof()]),
    )
    failing_review = _build_fixture_guarded_graduation_review(
        fixture_name="MED13",
        proof_summary=_guarded_proof_summary(
            [_guarded_proof(verification_status="pending")],
        ),
    )
    gate = _build_guarded_graduation_gate(
        fixture_reports=[
            {
                "fixture_name": "BRCA1",
                "guarded_graduation_review": passing_review,
            },
            {
                "fixture_name": "MED13",
                "guarded_graduation_review": failing_review,
            },
        ],
    )

    assert gate["all_passed"] is False
    assert gate["summary"]["proof_count"] == 2
    assert gate["summary"]["pending_verification_count"] == 1
    assert gate["automated_gates"]["all_allowed_proofs_verified"] is False
    assert gate["summary"]["fixtures_needing_review"] == ["MED13"]


def test_source_chase_gate_requires_profile_authority_everywhere() -> None:
    exercised_readiness = {
        "profile_authority_exercised": True,
        "intervention_counts": {
            "source_selection": 1,
            "chase_or_stop": 1,
            "brief_generation": 0,
        },
    }
    unexercised_readiness = {
        "profile_authority_exercised": False,
        "intervention_counts": {
            "source_selection": 0,
            "chase_or_stop": 0,
            "brief_generation": 0,
        },
    }
    source_proof = _guarded_proof(
        proof_id="guarded-proof-001-after_driven_terms_ready",
        checkpoint_key="after_driven_terms_ready",
        guarded_strategy="prioritized_structured_sequence",
        recommended_action_type="RUN_STRUCTURED_ENRICHMENT",
        applied_action_type="RUN_STRUCTURED_ENRICHMENT",
    )
    chase_proof = _guarded_proof()

    exercised_review = _build_fixture_guarded_graduation_review(
        fixture_name="BRCA1",
        proof_summary=_guarded_proof_summary([source_proof, chase_proof]),
        readiness_summary=exercised_readiness,
    )
    unexercised_review = _build_fixture_guarded_graduation_review(
        fixture_name="MED13",
        proof_summary=_guarded_proof_summary([source_proof, chase_proof]),
        readiness_summary=unexercised_readiness,
    )

    assert exercised_review["readiness_profile_authority_exercised"] is True
    assert exercised_review["readiness_intervention_counts"] == {
        "source_selection": 1,
        "chase_or_stop": 1,
        "brief_generation": 0,
    }
    assert unexercised_review["readiness_profile_authority_exercised"] is False

    exercised_only_gate = _build_guarded_graduation_gate(
        fixture_reports=[
            {
                "fixture_name": "BRCA1",
                "guarded_graduation_review": exercised_review,
            },
        ],
        require_source_chase_interventions=True,
    )
    mixed_gate = _build_guarded_graduation_gate(
        fixture_reports=[
            {
                "fixture_name": "BRCA1",
                "guarded_graduation_review": exercised_review,
            },
            {
                "fixture_name": "MED13",
                "guarded_graduation_review": unexercised_review,
            },
        ],
        require_source_chase_interventions=True,
    )

    assert (
        exercised_only_gate["automated_gates"]["profile_authority_exercised_everywhere"]
        is True
    )
    assert exercised_only_gate["all_passed"] is True
    assert (
        mixed_gate["automated_gates"]["profile_authority_exercised_everywhere"] is False
    )
    assert mixed_gate["all_passed"] is False
    assert mixed_gate["summary"]["fixtures_missing_profile_authority"] == ["MED13"]
    assert mixed_gate["summary"]["readiness_source_selection_intervention_count"] == 1
    assert mixed_gate["summary"]["readiness_chase_or_stop_intervention_count"] == 1


def test_gate_omits_profile_authority_check_when_source_chase_not_required() -> None:
    review = _build_fixture_guarded_graduation_review(
        fixture_name="BRCA1",
        proof_summary=_guarded_proof_summary([_guarded_proof()]),
        readiness_summary={
            "profile_authority_exercised": None,
            "intervention_counts": {
                "source_selection": 0,
                "chase_or_stop": 1,
                "brief_generation": 0,
            },
        },
    )
    gate = _build_guarded_graduation_gate(
        fixture_reports=[
            {
                "fixture_name": "BRCA1",
                "guarded_graduation_review": review,
            },
        ],
    )

    assert "profile_authority_exercised_everywhere" not in gate["automated_gates"]
    assert gate["all_passed"] is True


def test_guarded_report_marks_fixture_errors_as_failed_gates() -> None:
    spec = phase2_shadow_fixture_specs_for_set("supplemental")[0]
    compare_payload = _build_fixture_failure_compare_payload(
        spec=spec,
        exc=TimeoutError("baseline phase timed out"),
        compare_mode="dual_live_guarded",
        guarded_rollout_profile="guarded_low_risk",
    )

    report = _build_guarded_report(
        compare_payloads=[compare_payload],
        fixture_specs=(spec,),
        fixture_set="supplemental",
        pubmed_backend="deterministic",
        compare_mode="dual_live_guarded",
        preflight={
            "status": "ready",
            "capability": "query_generation",
            "model_id": "openai/test",
            "detail": "ok",
        },
    )

    assert report["summary"]["failed_fixture_count"] == 1
    assert report["summary"]["failed_fixtures"] == [
        {
            "fixture_name": "SUPPLEMENTAL_CHASE_SELECTION",
            "error_type": "TimeoutError",
            "error_message": "baseline phase timed out",
        }
    ]
    assert report["automated_gates"]["no_fixture_errors"] is False
    assert report["automated_gates"]["all_passed"] is False
    assert report["fixtures"][0]["fixture_status"] == "failed"
    assert report["guarded_graduation_gate"]["all_passed"] is False


def test_guarded_markdown_renders_graduation_gate_section() -> None:
    graduation_review = _build_fixture_guarded_graduation_review(
        fixture_name="BRCA1",
        proof_summary=_guarded_proof_summary([_guarded_proof()]),
    )
    report = {
        "generated_at": "2026-04-16T00:00:00+00:00",
        "planner_mode": "guarded",
        "compare_mode": "dual_live_guarded",
        "fixture_set": "objective",
        "pubmed_backend": "deterministic",
        "guarded_chase_rollout_enabled": True,
        "summary": {
            "fixture_count": 1,
            "applied_count": 1,
            "identified_count": 1,
            "candidate_count": 1,
            "verified_count": 1,
            "verification_failed_count": 0,
            "pending_verification_count": 0,
            "qualitative_rationale_present_count": 1,
        },
        "automated_gates": {
            "all_passed": True,
            "no_verification_failures": True,
            "no_pending_verifications": True,
            "at_least_one_guarded_action_applied": True,
            "at_least_one_guarded_intervention_identified": True,
        },
        "guarded_graduation_gate": _build_guarded_graduation_gate(
            fixture_reports=[
                {
                    "fixture_name": "BRCA1",
                    "guarded_graduation_review": graduation_review,
                }
            ],
        ),
        "fixtures": [
            {
                "fixture_name": "BRCA1",
                "guarded_evaluation": {"status": "applied", "applied_count": 1},
                "review_summary": {"review_verdict": "expected_match"},
                "guarded_graduation_review": graduation_review,
            }
        ],
    }

    markdown = render_phase1_guarded_evaluation_markdown(report)

    assert "## Guarded Graduation Gate" in markdown
    assert "- Guarded graduation gate: PASS" in markdown
    assert "| BRCA1 | applied |" in markdown


def test_build_fixture_review_summary_prioritizes_chase_mismatch() -> None:
    review_summary = _build_fixture_review_summary(
        fixture_name="PCSK9",
        compare_payload={
            "baseline": {"workspace": {"proposal_count": 34, "pending_questions": []}},
            "orchestrator": {
                "workspace": {"proposal_count": 35, "pending_questions": []}
            },
            "mismatches": ["proposal_count: baseline=34 orchestrator=35"],
        },
        guarded_evaluation={
            "candidate_actions": [
                {
                    "action_type": "RUN_STRUCTURED_ENRICHMENT",
                    "comparison_status": "matched",
                    "source_key": "drugbank",
                    "target_source_key": "drugbank",
                    "target_action_type": "RUN_STRUCTURED_ENRICHMENT",
                    "planner_status": "completed",
                    "guarded_strategy": "prioritized_structured_sequence",
                    "qualitative_rationale": "DrugBank is the best next fit.",
                },
                {
                    "action_type": "RUN_CHASE_ROUND",
                    "comparison_status": "diverged",
                    "source_key": None,
                    "target_source_key": None,
                    "target_action_type": "RUN_CHASE_ROUND",
                    "planner_status": "completed",
                    "guarded_strategy": "chase_selection",
                    "qualitative_rationale": "Keep the chase narrow and high-value.",
                    "selected_entity_ids": ["entity-1", "entity-2", "entity-3"],
                    "selected_labels": [
                        "PCSK9 inhibitor",
                        "alirocumab",
                        "acute coronary syndrome",
                    ],
                    "deterministic_selected_entity_ids": [
                        "entity-1",
                        "entity-2",
                        "entity-3",
                        "entity-4",
                    ],
                    "deterministic_selected_labels": [
                        "PCSK9 inhibitor",
                        "alirocumab",
                        "acute coronary syndrome",
                        "dyslipidemia",
                    ],
                    "selected_entity_overlap_count": 3,
                    "exact_selection_match": False,
                    "selection_basis": "Use a smaller bounded subset.",
                    "round_number": 1,
                },
            ]
        },
        compare_mode="dual_live_guarded",
    )

    assert review_summary["action_type"] == "RUN_CHASE_ROUND"
    assert review_summary["review_verdict"] == "acceptable_divergence"
    assert review_summary["exact_chase_selection_match"] is False
    assert review_summary["selected_entity_overlap_count"] == 3


def test_build_fixture_review_summary_prefers_chase_action_when_present() -> None:
    review_summary = _build_fixture_review_summary(
        fixture_name="CFTR",
        compare_payload={
            "baseline": {"workspace": {"proposal_count": 37, "pending_questions": []}},
            "orchestrator": {
                "workspace": {"proposal_count": 37, "pending_questions": []}
            },
            "mismatches": [],
        },
        guarded_evaluation={
            "candidate_actions": [
                {
                    "action_type": "RUN_STRUCTURED_ENRICHMENT",
                    "comparison_status": "matched",
                    "source_key": "clinvar",
                    "target_source_key": "clinvar",
                    "target_action_type": "RUN_STRUCTURED_ENRICHMENT",
                    "planner_status": "completed",
                    "guarded_strategy": "prioritized_structured_sequence",
                    "qualitative_rationale": "ClinVar is the best next fit.",
                },
                {
                    "action_type": "RUN_CHASE_ROUND",
                    "comparison_status": "matched",
                    "source_key": None,
                    "target_source_key": None,
                    "target_action_type": "RUN_CHASE_ROUND",
                    "planner_status": "completed",
                    "guarded_strategy": "chase_selection",
                    "qualitative_rationale": "Use the deterministic bounded chase set.",
                    "selected_entity_ids": ["entity-1", "entity-2"],
                    "selected_labels": ["result 1", "result 4"],
                    "deterministic_selected_entity_ids": ["entity-1", "entity-2"],
                    "deterministic_selected_labels": ["result 1", "result 4"],
                    "selected_entity_overlap_count": 2,
                    "exact_selection_match": True,
                    "selection_basis": "Follow the deterministic chase set.",
                    "round_number": 1,
                },
            ]
        },
        compare_mode="dual_live_guarded",
    )

    assert review_summary["action_type"] == "RUN_CHASE_ROUND"
    assert review_summary["selected_labels"] == ["result 1", "result 4"]
    assert review_summary["review_verdict"] == "expected_match"


def test_build_fixture_review_summary_prefers_applied_terminal_control_action() -> None:
    review_summary = _build_fixture_review_summary(
        fixture_name="CFTR",
        compare_payload={
            "baseline": {"workspace": {"proposal_count": 37, "pending_questions": []}},
            "orchestrator": {
                "workspace": {"proposal_count": 37, "pending_questions": []}
            },
            "mismatches": [],
        },
        guarded_evaluation={
            "applied_actions": [
                {
                    "checkpoint_key": "after_bootstrap",
                    "action_type": "STOP",
                    "source_key": None,
                    "guarded_strategy": "terminal_control_flow",
                    "comparison_status": "matched",
                    "target_action_type": "RUN_CHASE_ROUND",
                    "target_source_key": None,
                    "planner_status": "completed",
                    "qualitative_rationale": "There are not enough strong chase leads to continue.",
                    "stop_reason": "threshold_not_met",
                    "deterministic_stop_expected": True,
                },
            ],
            "candidate_actions": [
                {
                    "action_type": "RUN_STRUCTURED_ENRICHMENT",
                    "comparison_status": "matched",
                    "source_key": "clinvar",
                    "target_source_key": "clinvar",
                    "target_action_type": "RUN_STRUCTURED_ENRICHMENT",
                    "planner_status": "completed",
                    "guarded_strategy": "prioritized_structured_sequence",
                    "qualitative_rationale": "ClinVar is the best next fit.",
                },
            ],
        },
        compare_mode="dual_live_guarded",
    )

    assert review_summary["action_type"] == "STOP"
    assert review_summary["stop_reason"] == "threshold_not_met"
    assert review_summary["deterministic_stop_expected"] is True
    assert review_summary["review_verdict"] == "expected_match"


def test_build_fixture_review_summary_classifies_generic_matched_terminal_control() -> (
    None
):
    review_summary = _build_fixture_review_summary(
        fixture_name="CFTR",
        compare_payload={
            "baseline": {"workspace": {"proposal_count": 37, "pending_questions": []}},
            "orchestrator": {
                "workspace": {"proposal_count": 38, "pending_questions": []}
            },
            "mismatches": ["proposal_count: baseline=37 orchestrator=38"],
        },
        guarded_evaluation={
            "applied_actions": [
                {
                    "checkpoint_key": "after_bootstrap",
                    "action_type": "STOP",
                    "source_key": None,
                    "guarded_strategy": "terminal_control_flow",
                    "comparison_status": "matched",
                    "target_action_type": "RUN_CHASE_ROUND",
                    "target_source_key": None,
                    "planner_status": "completed",
                    "qualitative_rationale": "The run is ready to stop.",
                    "stop_reason": "guarded_stop_requested",
                },
            ],
            "candidate_actions": [],
        },
        compare_mode="dual_live_guarded",
    )

    assert review_summary["action_type"] == "STOP"
    assert review_summary["review_verdict"] == "expected_match"
    assert "guarded terminal control" in review_summary["review_note"]


def test_selected_action_display_compacts_chase_labels() -> None:
    display = _selected_action_display(
        {
            "selected_labels": [
                "PCSK9 inhibitor",
                "alirocumab",
                "acute coronary syndrome",
                "dyslipidemia",
            ]
        },
        target=False,
    )

    assert display == "PCSK9 inhibitor, alirocumab, acute coronary syndrome (+1)"


def test_selected_action_display_shows_stop_for_terminal_control() -> None:
    selected_display = _selected_action_display(
        {"action_type": "STOP", "stop_reason": "threshold_not_met"},
        target=False,
    )
    target_display = _selected_action_display(
        {"deterministic_stop_expected": True},
        target=True,
    )

    assert selected_display == "STOP"
    assert target_display == "STOP"


def test_build_fixture_review_summary_surfaces_filtered_chase_candidates() -> None:
    review_summary = _build_fixture_review_summary(
        fixture_name="BRCA1",
        compare_payload={
            "baseline": {
                "workspace": {
                    "proposal_count": 33,
                    "pending_questions": [],
                    "pending_chase_round": {
                        "filtered_chase_candidate_count": 5,
                        "filtered_chase_filter_reason_counts": {
                            "generic_result_label": 1,
                            "clinical_significance_bucket": 3,
                            "accession_like_placeholder": 1,
                        },
                        "filtered_chase_labels": [
                            "result 1",
                            "Pathogenic variant",
                            "Likely benign variant",
                            "Uncertain significance",
                            "CFIO01_06523",
                        ],
                    },
                }
            },
            "orchestrator": {
                "workspace": {
                    "proposal_count": 33,
                    "pending_questions": [],
                    "pending_chase_round": {
                        "filtered_chase_candidate_count": 5,
                        "filtered_chase_filter_reason_counts": {
                            "generic_result_label": 1,
                            "clinical_significance_bucket": 3,
                            "accession_like_placeholder": 1,
                        },
                        "filtered_chase_labels": [
                            "result 1",
                            "Pathogenic variant",
                            "Likely benign variant",
                            "Uncertain significance",
                            "CFIO01_06523",
                        ],
                    },
                }
            },
            "mismatches": [],
        },
        guarded_evaluation={
            "candidate_actions": [
                {
                    "action_type": "RUN_STRUCTURED_ENRICHMENT",
                    "comparison_status": "diverged",
                    "source_key": "drugbank",
                    "target_source_key": "clinvar",
                    "target_action_type": "RUN_STRUCTURED_ENRICHMENT",
                    "planner_status": "completed",
                    "guarded_strategy": "prioritized_structured_sequence",
                    "qualitative_rationale": "DrugBank is the best next fit.",
                }
            ]
        },
        compare_mode="dual_live_guarded",
    )

    assert review_summary["orchestrator_filtered_chase_candidate_count"] == 5
    assert review_summary["orchestrator_filtered_chase_filter_reason_counts"] == {
        "generic_result_label": 1,
        "clinical_significance_bucket": 3,
        "accession_like_placeholder": 1,
    }
    assert _render_filtered_chase_summary(review_summary) == (
        "shared count=5 | reasons=accession_like_placeholder=1, "
        "clinical_significance_bucket=3, generic_result_label=1 | examples=result 1, "
        "Pathogenic variant, Likely benign variant (+2)"
    )
