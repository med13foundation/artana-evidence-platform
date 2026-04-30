"""Report assembly and canary gates for Phase 1 guarded evaluation."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorPlannerMode,
)

from scripts.phase1_guarded_eval.common import (
    _GUARDED_SOURCE_CHASE_PROFILE,
    _ROLLBACK_REQUIRED_CANARY_GATES,
    Phase1GuardedCompareMode,
    Phase1GuardedReportMode,
    _base_fixture_name,
    _dict_value,
    _int_value,
    _maybe_string,
    _optional_float,
    _round_runtime_seconds,
    _string_list,
)
from scripts.phase1_guarded_eval.review import (
    _build_fixture_guarded_graduation_review,
    _build_fixture_review_summary,
)

if TYPE_CHECKING:
    from artana_evidence_api.phase2_shadow_fixture_refresh import (
        Phase2ShadowFixtureSet,
        Phase2ShadowFixtureSpec,
    )
    from artana_evidence_api.types.common import JSONObject

_GUARDED_CHASE_ROLLOUT_ENV = "ARTANA_ENABLE_GUARDED_CHASE_ROLLOUT"


def _guarded_chase_rollout_enabled() -> bool:
    return os.getenv(_GUARDED_CHASE_ROLLOUT_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _extract_guarded_decision_proofs(compare_payload: JSONObject) -> JSONObject:
    orchestrator = _dict_value(compare_payload.get("orchestrator"))
    workspace = _dict_value(orchestrator.get("workspace"))
    return _dict_value(workspace.get("guarded_decision_proofs"))


def _extract_guarded_readiness(compare_payload: JSONObject) -> JSONObject:
    orchestrator = _dict_value(compare_payload.get("orchestrator"))
    workspace = _dict_value(orchestrator.get("workspace"))
    return _dict_value(workspace.get("guarded_readiness"))


def _build_guarded_graduation_gate(
    *,
    fixture_reports: list[JSONObject],
    require_source_chase_interventions: bool = False,
) -> JSONObject:
    fixture_reviews = [
        _dict_value(fixture.get("guarded_graduation_review"))
        for fixture in fixture_reports
    ]
    fixture_count = len(fixture_reviews)
    fixtures_with_proof_summary = sum(
        1 for review in fixture_reviews if review.get("proof_summary_present") is True
    )
    fixtures_with_reviewable_proofs = sum(
        1
        for review in fixture_reviews
        if review.get("reviewable_proofs_present") is True
    )
    proof_count = sum(
        _int_value(review.get("proof_count")) for review in fixture_reviews
    )
    allowed_count = sum(
        _int_value(review.get("allowed_count")) for review in fixture_reviews
    )
    blocked_count = sum(
        _int_value(review.get("blocked_count")) for review in fixture_reviews
    )
    ignored_count = sum(
        _int_value(review.get("ignored_count")) for review in fixture_reviews
    )
    verified_count = sum(
        _int_value(review.get("verified_count")) for review in fixture_reviews
    )
    verification_failed_count = sum(
        _int_value(review.get("verification_failed_count"))
        for review in fixture_reviews
    )
    pending_verification_count = sum(
        _int_value(review.get("pending_verification_count"))
        for review in fixture_reviews
    )
    fallback_count = sum(
        _int_value(review.get("fallback_count")) for review in fixture_reviews
    )
    invalid_output_count = sum(
        _int_value(review.get("invalid_output_count")) for review in fixture_reviews
    )
    budget_violation_count = sum(
        _int_value(review.get("budget_violation_count")) for review in fixture_reviews
    )
    disabled_source_violation_count = sum(
        _int_value(review.get("disabled_source_violation_count"))
        for review in fixture_reviews
    )
    reserved_source_violation_count = sum(
        _int_value(review.get("reserved_source_violation_count"))
        for review in fixture_reviews
    )
    context_only_source_violation_count = sum(
        _int_value(review.get("context_only_source_violation_count"))
        for review in fixture_reviews
    )
    grounding_source_violation_count = sum(
        _int_value(review.get("grounding_source_violation_count"))
        for review in fixture_reviews
    )
    missing_rationale_count = sum(
        _int_value(review.get("missing_rationale_count")) for review in fixture_reviews
    )
    allowed_unverified_count = sum(
        _int_value(review.get("allowed_unverified_count")) for review in fixture_reviews
    )
    allowed_without_policy_count = sum(
        _int_value(review.get("allowed_without_policy_count"))
        for review in fixture_reviews
    )
    allowed_without_applied_action_count = sum(
        _int_value(review.get("allowed_without_applied_action_count"))
        for review in fixture_reviews
    )
    blocked_without_reason_count = sum(
        _int_value(review.get("blocked_without_reason_count"))
        for review in fixture_reviews
    )
    source_selection_intervention_count = sum(
        _int_value(review.get("source_selection_intervention_count"))
        for review in fixture_reviews
    )
    chase_or_stop_intervention_count = sum(
        _int_value(review.get("chase_or_stop_intervention_count"))
        for review in fixture_reviews
    )
    readiness_summaries_present = sum(
        1
        for review in fixture_reviews
        if review.get("readiness_summary_present") is True
    )
    readiness_profile_authority_exercised_count = sum(
        1
        for review in fixture_reviews
        if review.get("readiness_profile_authority_exercised") is True
    )
    fixtures_missing_profile_authority = [
        str(review.get("fixture_name", "unknown"))
        for review in fixture_reviews
        if review.get("readiness_profile_authority_exercised") is not True
    ]
    readiness_source_selection_intervention_count = sum(
        _int_value(
            _dict_value(review.get("readiness_intervention_counts")).get(
                "source_selection",
            ),
        )
        for review in fixture_reviews
    )
    readiness_chase_or_stop_intervention_count = sum(
        _int_value(
            _dict_value(review.get("readiness_intervention_counts")).get(
                "chase_or_stop",
            ),
        )
        for review in fixture_reviews
    )
    readiness_brief_generation_intervention_count = sum(
        _int_value(
            _dict_value(review.get("readiness_intervention_counts")).get(
                "brief_generation",
            ),
        )
        for review in fixture_reviews
    )
    blocked_or_ignored_count = blocked_count + ignored_count
    automated_gates = {
        "proof_summaries_present": (
            fixture_count > 0 and fixtures_with_proof_summary == fixture_count
        ),
        "reviewable_proofs_present": (
            fixture_count > 0 and fixtures_with_reviewable_proofs == fixture_count
        ),
        "at_least_one_allowed_proof": allowed_count > 0,
        "no_blocked_or_ignored_proofs": blocked_or_ignored_count == 0,
        "all_allowed_proofs_verified": allowed_unverified_count == 0,
        "no_verification_failures": verification_failed_count == 0,
        "no_pending_verifications": pending_verification_count == 0,
        "no_fallback_recommendations": fallback_count == 0,
        "no_invalid_outputs": invalid_output_count == 0,
        "no_budget_violations": budget_violation_count == 0,
        "no_disabled_source_violations": disabled_source_violation_count == 0,
        "qualitative_rationale_present_everywhere": missing_rationale_count == 0,
        "all_allowed_proofs_policy_allowed": allowed_without_policy_count == 0,
        "all_allowed_proofs_have_applied_action": (
            allowed_without_applied_action_count == 0
        ),
        "blocked_proofs_have_reasons": blocked_without_reason_count == 0,
    }
    if require_source_chase_interventions:
        automated_gates["at_least_one_source_selection_intervention"] = (
            source_selection_intervention_count > 0
        )
        automated_gates["at_least_one_chase_or_stop_intervention"] = (
            chase_or_stop_intervention_count > 0
        )
        automated_gates["profile_authority_exercised_everywhere"] = (
            fixture_count > 0
            and readiness_profile_authority_exercised_count == fixture_count
        )
    automated_gates["all_passed"] = all(automated_gates.values())
    fixtures_needing_review = [
        str(review.get("fixture_name", "unknown"))
        for review in fixture_reviews
        if review.get("gate_passed") is not True
    ]
    return {
        "all_passed": automated_gates["all_passed"],
        "automated_gates": automated_gates,
        "summary": {
            "fixture_count": fixture_count,
            "fixtures_with_proof_summary": fixtures_with_proof_summary,
            "fixtures_with_reviewable_proofs": fixtures_with_reviewable_proofs,
            "proof_count": proof_count,
            "allowed_count": allowed_count,
            "blocked_count": blocked_count,
            "ignored_count": ignored_count,
            "verified_count": verified_count,
            "verification_failed_count": verification_failed_count,
            "pending_verification_count": pending_verification_count,
            "fallback_count": fallback_count,
            "invalid_output_count": invalid_output_count,
            "budget_violation_count": budget_violation_count,
            "disabled_source_violation_count": disabled_source_violation_count,
            "reserved_source_violation_count": reserved_source_violation_count,
            "context_only_source_violation_count": (
                context_only_source_violation_count
            ),
            "grounding_source_violation_count": grounding_source_violation_count,
            "missing_rationale_count": missing_rationale_count,
            "allowed_unverified_count": allowed_unverified_count,
            "allowed_without_policy_count": allowed_without_policy_count,
            "allowed_without_applied_action_count": (
                allowed_without_applied_action_count
            ),
            "blocked_without_reason_count": blocked_without_reason_count,
            "blocked_or_ignored_count": blocked_or_ignored_count,
            "source_selection_intervention_count": (
                source_selection_intervention_count
            ),
            "chase_or_stop_intervention_count": chase_or_stop_intervention_count,
            "readiness_summaries_present": readiness_summaries_present,
            "readiness_profile_authority_exercised_count": (
                readiness_profile_authority_exercised_count
            ),
            "readiness_source_selection_intervention_count": (
                readiness_source_selection_intervention_count
            ),
            "readiness_chase_or_stop_intervention_count": (
                readiness_chase_or_stop_intervention_count
            ),
            "readiness_brief_generation_intervention_count": (
                readiness_brief_generation_intervention_count
            ),
            "fixtures_missing_profile_authority": fixtures_missing_profile_authority,
            "fixtures_needing_review": fixtures_needing_review,
        },
        "fixtures": fixture_reviews,
    }


def _build_guarded_report(  # noqa: PLR0912, PLR0913, PLR0915
    *,
    compare_payloads: list[JSONObject],
    fixture_specs: tuple[Phase2ShadowFixtureSpec, ...],
    fixture_set: Phase2ShadowFixtureSet,
    pubmed_backend: str,
    compare_mode: Phase1GuardedCompareMode,
    report_mode: Phase1GuardedReportMode = "standard",
    preflight: dict[str, str | None],
    guarded_rollout_profile: str = "guarded_low_risk",
    repeat_count: int = 1,
    canary_label: str | None = None,
    expected_run_count: int | None = None,
) -> JSONObject:
    _validate_compare_payload_count(
        compare_payloads=compare_payloads,
        fixture_specs=fixture_specs,
    )
    fixture_reports: list[JSONObject] = []
    total_applied = 0
    total_identified = 0
    total_candidates = 0
    total_verified = 0
    total_failed = 0
    total_pending = 0
    total_chase_actions = 0
    total_chase_verified = 0
    total_chase_exact_selection_matches = 0
    total_chase_candidate_count = 0
    total_chase_candidate_exact_selection_matches = 0
    total_chase_selected_entity_overlap_total = 0
    total_chase_selection_mismatch_count = 0
    total_terminal_control_actions = 0
    total_terminal_control_verified = 0
    total_chase_checkpoint_stops = 0
    total_orchestrator_filtered_chase_candidates = 0
    matched_count = 0
    diverged_count = 0
    rationale_present_count = 0
    expected_match_count = 0
    acceptable_divergence_count = 0
    accepted_conservative_stop_count = 0
    needs_review_count = 0
    execution_drift_count = 0
    live_source_jitter_count = 0
    downstream_state_drift_count = 0
    guarded_narrowing_drift_count = 0
    expected_follow_on_drift_count = 0
    total_runtime_seconds = 0.0
    runtime_fixture_count = 0
    failed_fixtures: list[JSONObject] = []
    for spec, compare_payload in zip(fixture_specs, compare_payloads, strict=True):
        _validate_compare_payload_shape(
            fixture_name=spec.fixture_name,
            compare_payload=compare_payload,
        )
        fixture_runtime_seconds = _optional_float(
            compare_payload.get("fixture_runtime_seconds"),
        )
        fixture_error = _dict_value(compare_payload.get("fixture_error"))
        if fixture_error:
            failed_fixture = {
                "fixture_name": spec.fixture_name,
                "error_type": _maybe_string(fixture_error.get("error_type"))
                or "unknown",
                "error_message": _maybe_string(
                    fixture_error.get("error_message"),
                )
                or "",
            }
            rounded_runtime_seconds = _round_runtime_seconds(fixture_runtime_seconds)
            if rounded_runtime_seconds is not None:
                failed_fixture["runtime_seconds"] = rounded_runtime_seconds
            failed_fixtures.append(failed_fixture)
        if fixture_runtime_seconds is not None:
            total_runtime_seconds += fixture_runtime_seconds
            runtime_fixture_count += 1
        guarded_evaluation = (
            dict(compare_payload.get("guarded_evaluation"))
            if isinstance(compare_payload.get("guarded_evaluation"), dict)
            else {}
        )
        review_summary = _build_fixture_review_summary(
            fixture_name=spec.fixture_name,
            compare_payload=compare_payload,
            guarded_evaluation=guarded_evaluation,
            compare_mode=compare_mode,
        )
        guarded_decision_proofs = _extract_guarded_decision_proofs(compare_payload)
        guarded_readiness = _extract_guarded_readiness(compare_payload)
        guarded_graduation_review = _build_fixture_guarded_graduation_review(
            fixture_name=spec.fixture_name,
            proof_summary=guarded_decision_proofs,
            readiness_summary=guarded_readiness,
        )
        total_applied += _int_value(guarded_evaluation.get("applied_count"))
        total_candidates += _int_value(guarded_evaluation.get("candidate_count"))
        total_identified += _int_value(guarded_evaluation.get("identified_count"))
        total_verified += _int_value(guarded_evaluation.get("verified_count"))
        total_failed += _int_value(
            guarded_evaluation.get("verification_failed_count"),
        )
        total_pending += _int_value(
            guarded_evaluation.get("pending_verification_count"),
        )
        total_chase_actions += _int_value(guarded_evaluation.get("chase_action_count"))
        total_chase_verified += _int_value(
            guarded_evaluation.get("chase_verified_count"),
        )
        total_chase_exact_selection_matches += _int_value(
            guarded_evaluation.get("chase_exact_selection_match_count"),
        )
        total_chase_candidate_count += _int_value(
            guarded_evaluation.get("chase_candidate_count"),
        )
        total_chase_candidate_exact_selection_matches += _int_value(
            guarded_evaluation.get(
                "chase_candidate_exact_selection_match_count",
            ),
        )
        total_chase_selected_entity_overlap_total += _int_value(
            guarded_evaluation.get("chase_selected_entity_overlap_total"),
        ) + _int_value(guarded_evaluation.get("chase_candidate_overlap_total"))
        total_chase_selection_mismatch_count += _int_value(
            guarded_evaluation.get("chase_selection_mismatch_count"),
        )
        total_terminal_control_actions += _int_value(
            guarded_evaluation.get("terminal_control_action_count"),
        )
        total_terminal_control_verified += _int_value(
            guarded_evaluation.get("terminal_control_verified_count"),
        )
        total_chase_checkpoint_stops += _int_value(
            guarded_evaluation.get("chase_checkpoint_stop_count"),
        )
        total_orchestrator_filtered_chase_candidates += _int_value(
            review_summary.get("orchestrator_filtered_chase_candidate_count"),
        )
        comparison_status = review_summary.get("comparison_status")
        if comparison_status == "matched":
            matched_count += 1
        elif comparison_status in {"diverged", "mismatch"}:
            diverged_count += 1
        if bool(review_summary.get("qualitative_rationale_present")):
            rationale_present_count += 1
        review_verdict = review_summary.get("review_verdict")
        if review_verdict == "expected_match":
            expected_match_count += 1
        elif review_verdict == "acceptable_divergence":
            acceptable_divergence_count += 1
        elif review_verdict == "accepted_conservative_stop":
            accepted_conservative_stop_count += 1
        elif review_verdict == "needs_review":
            needs_review_count += 1
        drift_class = review_summary.get("drift_class")
        if drift_class == "execution_drift":
            execution_drift_count += 1
        elif drift_class == "live_source_jitter":
            live_source_jitter_count += 1
        elif drift_class == "downstream_state_drift":
            downstream_state_drift_count += 1
        elif drift_class == "guarded_narrowing_drift":
            guarded_narrowing_drift_count += 1
        elif drift_class == "expected_follow_on_drift":
            expected_follow_on_drift_count += 1
        fixture_reports.append(
            {
                "fixture_name": spec.fixture_name,
                "fixture_status": "failed" if fixture_error else "completed",
                "fixture_error": fixture_error or None,
                "objective": spec.objective,
                "request": compare_payload.get("request"),
                "mismatches": _string_list(compare_payload.get("mismatches")),
                "advisories": _string_list(compare_payload.get("advisories")),
                "guarded_evaluation": guarded_evaluation,
                "guarded_decision_proofs": guarded_decision_proofs,
                "guarded_graduation_review": guarded_graduation_review,
                "review_summary": review_summary,
                "fixture_runtime_seconds": _round_runtime_seconds(
                    fixture_runtime_seconds,
                ),
                "orchestrator_run_id": _maybe_string(
                    _dict_value(compare_payload.get("orchestrator")).get("run_id"),
                ),
                "baseline_run_id": _maybe_string(
                    _dict_value(compare_payload.get("baseline")).get("run_id"),
                ),
            },
        )
    guarded_graduation_gate = _build_guarded_graduation_gate(
        fixture_reports=fixture_reports,
        require_source_chase_interventions=(
            guarded_rollout_profile == _GUARDED_SOURCE_CHASE_PROFILE
        ),
    )
    automated_gates = {
        "no_fixture_errors": len(failed_fixtures) == 0,
        "no_verification_failures": total_failed == 0,
        "no_pending_verifications": total_pending == 0,
        "at_least_one_guarded_action_applied": total_applied > 0,
        "at_least_one_guarded_intervention_identified": total_identified > 0,
    }
    automated_gates["all_passed"] = all(
        (
            automated_gates["no_fixture_errors"],
            automated_gates["no_verification_failures"],
            automated_gates["no_pending_verifications"],
            (
                automated_gates["at_least_one_guarded_action_applied"]
                if compare_mode == "dual_live_guarded"
                else automated_gates["at_least_one_guarded_intervention_identified"]
            ),
        ),
    )
    report_summary: JSONObject = {
        "fixture_count": len(fixture_reports),
        "run_count": len(fixture_reports),
        "unique_fixture_count": len(
            {
                _base_fixture_name(str(fixture.get("fixture_name", "unknown")))
                for fixture in fixture_reports
            },
        ),
        "repeat_count": repeat_count,
        "completed_fixture_count": len(fixture_reports) - len(failed_fixtures),
        "failed_fixture_count": len(failed_fixtures),
        "failed_fixtures": failed_fixtures,
        "timed_out_fixture_count": sum(
            1
            for fixture in failed_fixtures
            if fixture.get("error_type") == "TimeoutError"
        ),
        "timed_out_fixtures": [
            str(fixture.get("fixture_name"))
            for fixture in failed_fixtures
            if fixture.get("error_type") == "TimeoutError"
        ],
        "total_runtime_seconds": _round_runtime_seconds(total_runtime_seconds),
        "average_runtime_seconds": _round_runtime_seconds(
            (
                total_runtime_seconds / runtime_fixture_count
                if runtime_fixture_count > 0
                else None
            ),
        ),
        "applied_count": total_applied,
        "candidate_count": total_candidates,
        "identified_count": total_identified,
        "verified_count": total_verified,
        "verification_failed_count": total_failed,
        "pending_verification_count": total_pending,
        "chase_action_count": total_chase_actions,
        "chase_verified_count": total_chase_verified,
        "chase_exact_selection_match_count": total_chase_exact_selection_matches,
        "chase_candidate_count": total_chase_candidate_count,
        "chase_candidate_exact_selection_match_count": (
            total_chase_candidate_exact_selection_matches
        ),
        "chase_selected_entity_overlap_total": (
            total_chase_selected_entity_overlap_total
        ),
        "chase_selection_mismatch_count": total_chase_selection_mismatch_count,
        "terminal_control_action_count": total_terminal_control_actions,
        "terminal_control_verified_count": total_terminal_control_verified,
        "chase_checkpoint_stop_count": total_chase_checkpoint_stops,
        "orchestrator_filtered_chase_candidate_count": (
            total_orchestrator_filtered_chase_candidates
        ),
        "matched_count": matched_count,
        "diverged_count": diverged_count,
        "qualitative_rationale_present_count": rationale_present_count,
        "expected_match_count": expected_match_count,
        "acceptable_divergence_count": acceptable_divergence_count,
        "accepted_conservative_stop_count": accepted_conservative_stop_count,
        "needs_review_count": needs_review_count,
        "execution_drift_count": execution_drift_count,
        "live_source_jitter_count": live_source_jitter_count,
        "downstream_state_drift_count": downstream_state_drift_count,
        "guarded_narrowing_drift_count": guarded_narrowing_drift_count,
        "expected_follow_on_drift_count": expected_follow_on_drift_count,
        "fixtures_with_guarded_actions": [
            fixture["fixture_name"]
            for fixture in fixture_reports
            if _int_value(
                _dict_value(fixture.get("guarded_evaluation")).get(
                    "applied_count",
                ),
            )
            > 0
        ],
        "fixtures_with_guarded_chase_actions": [
            fixture["fixture_name"]
            for fixture in fixture_reports
            if _int_value(
                _dict_value(fixture.get("guarded_evaluation")).get(
                    "chase_action_count",
                ),
            )
            > 0
        ],
        "fixtures_with_guarded_terminal_control": [
            fixture["fixture_name"]
            for fixture in fixture_reports
            if _int_value(
                _dict_value(fixture.get("guarded_evaluation")).get(
                    "terminal_control_action_count",
                ),
            )
            > 0
        ],
        "fixtures_with_guarded_chase_checkpoint_stops": [
            fixture["fixture_name"]
            for fixture in fixture_reports
            if _int_value(
                _dict_value(fixture.get("guarded_evaluation")).get(
                    "chase_checkpoint_stop_count",
                ),
            )
            > 0
        ],
        "fixtures_with_replay_only_chase_candidates": [
            fixture["fixture_name"]
            for fixture in fixture_reports
            if _int_value(
                _dict_value(fixture.get("guarded_evaluation")).get(
                    "chase_candidate_count",
                ),
            )
            > 0
        ],
        "fixtures_with_filtered_chase_candidates": [
            fixture["fixture_name"]
            for fixture in fixture_reports
            if _int_value(
                _dict_value(fixture.get("review_summary")).get(
                    "orchestrator_filtered_chase_candidate_count",
                ),
            )
            > 0
        ],
        "fixtures_with_failures": [
            fixture["fixture_name"]
            for fixture in fixture_reports
            if _int_value(
                _dict_value(fixture.get("guarded_evaluation")).get(
                    "verification_failed_count",
                ),
            )
            > 0
        ],
        "fixtures_without_actions": [
            fixture["fixture_name"]
            for fixture in fixture_reports
            if _dict_value(fixture.get("guarded_evaluation")).get("status")
            == "no_guarded_actions_applied"
        ],
    }
    report: JSONObject = {
        "generated_at": datetime.now(UTC).isoformat(),
        "planner_mode": FullAIOrchestratorPlannerMode.GUARDED.value,
        "compare_mode": compare_mode,
        "report_mode": report_mode,
        "canary_label": canary_label,
        "expected_run_count": expected_run_count,
        "fixture_set": fixture_set,
        "pubmed_backend": pubmed_backend,
        "guarded_rollout_profile": guarded_rollout_profile,
        "repeat_count": repeat_count,
        "guarded_chase_rollout_enabled": _guarded_chase_rollout_enabled(),
        "preflight": preflight,
        "summary": report_summary,
        "automated_gates": automated_gates,
        "guarded_graduation_gate": guarded_graduation_gate,
        "canary_gate": None,
        "fixtures": fixture_reports,
    }
    if report_mode == "canary":
        report["canary_gate"] = _build_canary_gate(
            fixture_reports=fixture_reports,
            report_summary=report_summary,
            guarded_graduation_gate=guarded_graduation_gate,
            expected_run_count=expected_run_count,
        )
    return report


def _validate_compare_payload_count(
    *,
    compare_payloads: list[JSONObject],
    fixture_specs: tuple[Phase2ShadowFixtureSpec, ...],
) -> None:
    if len(compare_payloads) != len(fixture_specs):
        msg = (
            "Phase 1 guarded evaluation received "
            f"{len(compare_payloads)} compare payload(s) for "
            f"{len(fixture_specs)} fixture(s)."
        )
        raise ValueError(msg)


def _validate_compare_payload_shape(
    *,
    fixture_name: str,
    compare_payload: JSONObject,
) -> None:
    if not isinstance(compare_payload, dict):
        msg = (
            "Phase 1 guarded evaluation received a malformed compare payload "
            f"for fixture {fixture_name}: expected object, got "
            f"{type(compare_payload).__name__}."
        )
        raise TypeError(msg)
    fixture_error = compare_payload.get("fixture_error")
    if isinstance(fixture_error, dict):
        return
    missing_sections = [
        section
        for section in ("baseline", "orchestrator", "guarded_evaluation")
        if not isinstance(compare_payload.get(section), dict)
    ]
    if missing_sections:
        msg = (
            "Phase 1 guarded evaluation received a malformed compare payload "
            f"for fixture {fixture_name}: missing object section(s): "
            f"{', '.join(missing_sections)}."
        )
        raise ValueError(msg)


def _build_canary_gate(
    *,
    fixture_reports: list[JSONObject],
    report_summary: JSONObject,
    guarded_graduation_gate: JSONObject,
    expected_run_count: int | None,
) -> JSONObject:
    graduation_summary = _dict_value(guarded_graduation_gate.get("summary"))
    graduation_gates = _dict_value(guarded_graduation_gate.get("automated_gates"))
    timed_out_fixtures = _string_list(report_summary.get("timed_out_fixtures"))
    run_count = _int_value(report_summary.get("run_count"))
    source_policy_violation_counts = {
        "disabled": _int_value(
            graduation_summary.get("disabled_source_violation_count")
        ),
        "reserved": _int_value(
            graduation_summary.get("reserved_source_violation_count")
        ),
        "context_only": _int_value(
            graduation_summary.get("context_only_source_violation_count"),
        ),
        "grounding": _int_value(
            graduation_summary.get("grounding_source_violation_count"),
        ),
    }
    proof_clean_run_count = sum(
        1
        for fixture in fixture_reports
        if _dict_value(fixture.get("guarded_graduation_review")).get("gate_passed")
        is True
    )
    expected_run_count_met = (
        expected_run_count is None or run_count >= expected_run_count
    )
    automated_gates = {
        "guarded_graduation_gate_passed": guarded_graduation_gate.get("all_passed")
        is True,
        "proof_receipts_present_and_verified": all(
            (
                graduation_gates.get("proof_summaries_present") is True,
                graduation_gates.get("reviewable_proofs_present") is True,
                graduation_gates.get("at_least_one_allowed_proof") is True,
                graduation_gates.get("no_blocked_or_ignored_proofs") is True,
                graduation_gates.get("all_allowed_proofs_verified") is True,
                graduation_gates.get("no_verification_failures") is True,
                graduation_gates.get("no_pending_verifications") is True,
                graduation_gates.get("all_allowed_proofs_policy_allowed") is True,
                graduation_gates.get("all_allowed_proofs_have_applied_action") is True,
                graduation_gates.get("blocked_proofs_have_reasons") is True,
            ),
        ),
        "no_fixture_failures": _int_value(report_summary.get("failed_fixture_count"))
        == 0,
        "no_timeouts": len(timed_out_fixtures) == 0,
        "expected_run_count_met": expected_run_count_met,
        "no_invalid_outputs": _int_value(graduation_summary.get("invalid_output_count"))
        == 0,
        "no_fallback_outputs": _int_value(graduation_summary.get("fallback_count"))
        == 0,
        "no_budget_violations": _int_value(
            graduation_summary.get("budget_violation_count"),
        )
        == 0,
        "no_disabled_source_violations": source_policy_violation_counts["disabled"]
        == 0,
        "no_reserved_source_violations": source_policy_violation_counts["reserved"]
        == 0,
        "no_context_only_source_violations": (
            source_policy_violation_counts["context_only"] == 0
        ),
        "no_grounding_source_violations": (
            source_policy_violation_counts["grounding"] == 0
        ),
        "qualitative_rationale_present_everywhere": (
            graduation_gates.get("qualitative_rationale_present_everywhere") is True
        ),
        "profile_authority_exercised_everywhere": (
            graduation_gates.get("profile_authority_exercised_everywhere") is True
        ),
        "at_least_one_source_selection_intervention": (
            _int_value(graduation_summary.get("source_selection_intervention_count"))
            > 0
        ),
        "at_least_one_chase_or_stop_intervention": (
            _int_value(graduation_summary.get("chase_or_stop_intervention_count")) > 0
        ),
    }
    all_passed = all(automated_gates.values())
    rollback_required = any(
        automated_gates.get(gate_name) is False
        for gate_name in _ROLLBACK_REQUIRED_CANARY_GATES
    )
    verdict = (
        "pass" if all_passed else "rollback_required" if rollback_required else "hold"
    )
    notes: list[str] = []
    if expected_run_count is not None and run_count != expected_run_count:
        notes.append(
            "run_count differed from the expected coverage target "
            f"(expected {expected_run_count}, observed {run_count})",
        )
    if timed_out_fixtures:
        notes.append("one or more canary runs timed out")
    if proof_clean_run_count != len(fixture_reports):
        notes.append("one or more runs had non-clean guarded proof receipts")
    return {
        "all_passed": all_passed,
        "verdict": verdict,
        "automated_gates": automated_gates,
        "summary": {
            "run_count": run_count,
            "unique_fixture_count": _int_value(
                report_summary.get("unique_fixture_count"),
            ),
            "repeat_count": _int_value(report_summary.get("repeat_count")),
            "expected_run_count": expected_run_count,
            "expected_run_count_met": expected_run_count_met,
            "timeout_count": len(timed_out_fixtures),
            "timed_out_fixtures": timed_out_fixtures,
            "total_runtime_seconds": _optional_float(
                report_summary.get("total_runtime_seconds"),
            ),
            "average_runtime_seconds": _optional_float(
                report_summary.get("average_runtime_seconds"),
            ),
            "proof_clean_run_count": proof_clean_run_count,
            "proof_receipt_count": _int_value(graduation_summary.get("proof_count")),
            "verified_proof_receipt_count": _int_value(
                graduation_summary.get("verified_count"),
            ),
            "fallback_count": _int_value(graduation_summary.get("fallback_count")),
            "invalid_output_count": _int_value(
                graduation_summary.get("invalid_output_count"),
            ),
            "budget_violation_count": _int_value(
                graduation_summary.get("budget_violation_count"),
            ),
            "source_selection_intervention_count": _int_value(
                graduation_summary.get("source_selection_intervention_count"),
            ),
            "chase_or_stop_intervention_count": _int_value(
                graduation_summary.get("chase_or_stop_intervention_count"),
            ),
            "profile_authority_exercised_count": _int_value(
                graduation_summary.get("readiness_profile_authority_exercised_count"),
            ),
            "fixtures_missing_profile_authority": _string_list(
                graduation_summary.get("fixtures_missing_profile_authority"),
            ),
            "source_policy_violation_counts": source_policy_violation_counts,
            "source_policy_violation_total": sum(
                source_policy_violation_counts.values(),
            ),
        },
        "notes": notes,
    }
