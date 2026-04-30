"""Review and proof-gate helpers for Phase 1 guarded evaluation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.phase1_guarded_eval.common import (
    _GUARDED_CHASE_STRATEGY,
    _GUARDED_SOURCE_STRATEGY,
    _GUARDED_TERMINAL_STRATEGY,
    Phase1GuardedCompareMode,
    _bool_or_none,
    _dict_of_ints,
    _dict_value,
    _excerpt_text,
    _int_or_none,
    _int_value,
    _list_count,
    _list_of_dicts,
    _maybe_string,
    _proof_source_policy_violation_category,
    _string_list,
)

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject


def _proof_display_id(proof: JSONObject) -> str:
    proof_id = _maybe_string(proof.get("proof_id"))
    if proof_id is not None:
        return proof_id
    checkpoint_key = _maybe_string(proof.get("checkpoint_key"))
    if checkpoint_key is not None:
        return checkpoint_key
    return "unknown-proof"


def _proof_display_ids(proofs: list[JSONObject]) -> list[str]:
    return [_proof_display_id(proof) for proof in proofs]


def _build_fixture_guarded_graduation_review(  # noqa: PLR0912, PLR0915
    *,
    fixture_name: str,
    proof_summary: JSONObject,
    readiness_summary: JSONObject | None = None,
) -> JSONObject:
    proofs = _list_of_dicts(proof_summary.get("proofs"))
    proof_count = _int_value(proof_summary.get("proof_count"))
    if proof_count == 0 and proofs:
        proof_count = len(proofs)
    allowed_proofs = [
        proof for proof in proofs if proof.get("decision_outcome") == "allowed"
    ]
    blocked_proofs = [
        proof for proof in proofs if proof.get("decision_outcome") == "blocked"
    ]
    ignored_proofs = [
        proof for proof in proofs if proof.get("decision_outcome") == "ignored"
    ]
    fallback_proofs = [proof for proof in proofs if proof.get("used_fallback") is True]
    invalid_proofs = [
        proof
        for proof in proofs
        if _maybe_string(proof.get("validation_error")) is not None
        or proof.get("planner_status") in {"failed", "invalid"}
    ]
    budget_violation_proofs = [
        proof for proof in proofs if proof.get("budget_violation") is True
    ]
    disabled_source_violation_proofs = [
        proof for proof in proofs if proof.get("disabled_source_violation") is True
    ]
    reserved_source_violation_proofs = [
        proof
        for proof in proofs
        if _proof_source_policy_violation_category(proof) == "reserved"
    ]
    context_only_source_violation_proofs = [
        proof
        for proof in proofs
        if _proof_source_policy_violation_category(proof) == "context_only"
    ]
    grounding_source_violation_proofs = [
        proof
        for proof in proofs
        if _proof_source_policy_violation_category(proof) == "grounding"
    ]
    missing_rationale_proofs = [
        proof
        for proof in proofs
        if proof.get("qualitative_rationale_present") is not True
    ]
    verification_failed_proofs = [
        proof
        for proof in proofs
        if proof.get("verification_status") == "verification_failed"
    ]
    pending_verification_proofs = [
        proof for proof in proofs if proof.get("verification_status") == "pending"
    ]
    allowed_unverified_proofs = [
        proof
        for proof in allowed_proofs
        if proof.get("verification_status") != "verified"
    ]
    allowed_without_policy_proofs = [
        proof for proof in allowed_proofs if proof.get("policy_allowed") is not True
    ]
    allowed_without_applied_action_proofs = [
        proof
        for proof in allowed_proofs
        if _maybe_string(proof.get("applied_action_type")) is None
    ]
    blocked_without_reason_proofs = [
        proof
        for proof in blocked_proofs
        if _maybe_string(proof.get("outcome_reason")) is None
    ]
    source_selection_intervention_proofs = [
        proof
        for proof in allowed_proofs
        if proof.get("guarded_strategy") == _GUARDED_SOURCE_STRATEGY
    ]
    chase_or_stop_intervention_proofs = [
        proof
        for proof in allowed_proofs
        if proof.get("guarded_strategy") == _GUARDED_CHASE_STRATEGY
        or (
            proof.get("guarded_strategy") == _GUARDED_TERMINAL_STRATEGY
            and proof.get("applied_action_type") == "STOP"
        )
    ]
    proof_summary_present = bool(proof_summary)
    reviewable_proofs_present = proof_count > 0
    gate_passed = all(
        (
            proof_summary_present,
            reviewable_proofs_present,
            len(allowed_proofs) > 0,
            len(blocked_proofs) == 0,
            len(ignored_proofs) == 0,
            len(fallback_proofs) == 0,
            len(invalid_proofs) == 0,
            len(budget_violation_proofs) == 0,
            len(disabled_source_violation_proofs) == 0,
            len(missing_rationale_proofs) == 0,
            len(verification_failed_proofs) == 0,
            len(pending_verification_proofs) == 0,
            len(allowed_unverified_proofs) == 0,
            len(allowed_without_policy_proofs) == 0,
            len(allowed_without_applied_action_proofs) == 0,
            len(blocked_without_reason_proofs) == 0,
        ),
    )
    notes: list[str] = []
    if not proof_summary_present:
        notes.append("missing guarded decision proof summary")
    elif not reviewable_proofs_present:
        notes.append("guarded decision proof summary has no proof receipts")
    if not allowed_proofs:
        notes.append("no allowed guarded action proof")
    if blocked_proofs or ignored_proofs:
        notes.append("planner influence was blocked or ignored")
    if fallback_proofs:
        notes.append("planner fallback was present")
    if invalid_proofs:
        notes.append("invalid planner output was present")
    if budget_violation_proofs:
        notes.append("budget violation was present")
    if disabled_source_violation_proofs:
        notes.append("disabled-source violation was present")
    if missing_rationale_proofs:
        notes.append("qualitative rationale was missing")
    if verification_failed_proofs:
        notes.append("verification failure was present")
    if pending_verification_proofs or allowed_unverified_proofs:
        notes.append("allowed proof was not verified")
    if allowed_without_policy_proofs:
        notes.append("allowed proof missed policy approval")
    if allowed_without_applied_action_proofs:
        notes.append("allowed proof missed applied action")
    if blocked_without_reason_proofs:
        notes.append("blocked proof missed outcome reason")

    return {
        "fixture_name": fixture_name,
        "proof_summary_present": proof_summary_present,
        "reviewable_proofs_present": reviewable_proofs_present,
        "gate_passed": gate_passed,
        "proof_count": proof_count,
        "allowed_count": len(allowed_proofs),
        "blocked_count": len(blocked_proofs),
        "ignored_count": len(ignored_proofs),
        "verified_count": len(
            [
                proof
                for proof in proofs
                if proof.get("verification_status") == "verified"
            ]
        ),
        "verification_failed_count": len(verification_failed_proofs),
        "pending_verification_count": len(pending_verification_proofs),
        "fallback_count": len(fallback_proofs),
        "invalid_output_count": len(invalid_proofs),
        "budget_violation_count": len(budget_violation_proofs),
        "disabled_source_violation_count": len(disabled_source_violation_proofs),
        "reserved_source_violation_count": len(reserved_source_violation_proofs),
        "context_only_source_violation_count": len(
            context_only_source_violation_proofs,
        ),
        "grounding_source_violation_count": len(grounding_source_violation_proofs),
        "missing_rationale_count": len(missing_rationale_proofs),
        "allowed_unverified_count": len(allowed_unverified_proofs),
        "allowed_without_policy_count": len(allowed_without_policy_proofs),
        "allowed_without_applied_action_count": len(
            allowed_without_applied_action_proofs,
        ),
        "blocked_without_reason_count": len(blocked_without_reason_proofs),
        "blocked_or_ignored_count": len(blocked_proofs) + len(ignored_proofs),
        "source_selection_intervention_count": len(
            source_selection_intervention_proofs,
        ),
        "chase_or_stop_intervention_count": len(chase_or_stop_intervention_proofs),
        "proof_ids": _proof_display_ids(proofs),
        "blocked_or_ignored_proof_ids": _proof_display_ids(
            blocked_proofs + ignored_proofs,
        ),
        "fallback_proof_ids": _proof_display_ids(fallback_proofs),
        "invalid_proof_ids": _proof_display_ids(invalid_proofs),
        "budget_violation_proof_ids": _proof_display_ids(budget_violation_proofs),
        "disabled_source_violation_proof_ids": _proof_display_ids(
            disabled_source_violation_proofs,
        ),
        "reserved_source_violation_proof_ids": _proof_display_ids(
            reserved_source_violation_proofs,
        ),
        "context_only_source_violation_proof_ids": _proof_display_ids(
            context_only_source_violation_proofs,
        ),
        "grounding_source_violation_proof_ids": _proof_display_ids(
            grounding_source_violation_proofs,
        ),
        "missing_rationale_proof_ids": _proof_display_ids(
            missing_rationale_proofs,
        ),
        "allowed_unverified_proof_ids": _proof_display_ids(
            allowed_unverified_proofs,
        ),
        "source_selection_intervention_proof_ids": _proof_display_ids(
            source_selection_intervention_proofs,
        ),
        "chase_or_stop_intervention_proof_ids": _proof_display_ids(
            chase_or_stop_intervention_proofs,
        ),
        "readiness_summary_present": readiness_summary is not None
        and bool(readiness_summary),
        "readiness_profile_authority_exercised": (
            readiness_summary.get("profile_authority_exercised")
            if isinstance(readiness_summary, dict)
            else None
        ),
        "readiness_intervention_counts": _readiness_intervention_counts(
            readiness_summary,
        ),
        "notes": notes,
    }


def _readiness_intervention_counts(
    readiness_summary: JSONObject | None,
) -> JSONObject:
    raw = (
        _dict_value(readiness_summary.get("intervention_counts"))
        if isinstance(readiness_summary, dict)
        else {}
    )
    return {
        "source_selection": _int_value(raw.get("source_selection")),
        "chase_or_stop": _int_value(raw.get("chase_or_stop")),
        "brief_generation": _int_value(raw.get("brief_generation")),
    }


def _latest_chase_context(summary: JSONObject) -> JSONObject:
    for key in ("pending_chase_round", "chase_round_2", "chase_round_1"):
        value = _dict_value(summary.get(key))
        if value:
            return value
    return {}


def _build_fixture_review_summary(
    *,
    fixture_name: str,
    compare_payload: JSONObject,
    guarded_evaluation: JSONObject,
    compare_mode: Phase1GuardedCompareMode,
) -> JSONObject:
    baseline_summary = _dict_value(
        _dict_value(compare_payload.get("baseline")).get("workspace"),
    )
    orchestrator_summary = _dict_value(
        _dict_value(compare_payload.get("orchestrator")).get("workspace"),
    )
    applied_actions = _list_of_dicts(guarded_evaluation.get("applied_actions"))
    candidate_actions = _list_of_dicts(guarded_evaluation.get("candidate_actions"))
    primary_action = _select_primary_review_action(
        applied_actions + candidate_actions,
    )
    baseline_chase_context = _latest_chase_context(baseline_summary)
    orchestrator_chase_context = _latest_chase_context(orchestrator_summary)
    baseline_proposal_count = _int_or_none(baseline_summary.get("proposal_count"))
    orchestrator_proposal_count = _int_or_none(
        orchestrator_summary.get("proposal_count"),
    )
    proposal_count_delta: int | None = None
    if baseline_proposal_count is not None and orchestrator_proposal_count is not None:
        proposal_count_delta = orchestrator_proposal_count - baseline_proposal_count
    rationale = _maybe_string(primary_action.get("qualitative_rationale"))
    mismatches = _string_list(compare_payload.get("mismatches"))
    comparison_status = _maybe_string(primary_action.get("comparison_status"))
    selected_source_key = _maybe_string(primary_action.get("source_key"))
    deterministic_target_source_key = _maybe_string(
        primary_action.get("target_source_key"),
    )
    action_type = _maybe_string(primary_action.get("action_type"))
    selected_entity_ids = _string_list(primary_action.get("selected_entity_ids"))
    selected_labels = _string_list(primary_action.get("selected_labels"))
    deterministic_selected_entity_ids = _string_list(
        primary_action.get("deterministic_selected_entity_ids"),
    )
    deterministic_selected_labels = _string_list(
        primary_action.get("deterministic_selected_labels"),
    )
    exact_chase_selection_match = _bool_or_none(
        primary_action.get("exact_selection_match"),
    )
    stop_reason = _maybe_string(primary_action.get("stop_reason"))
    deterministic_stop_expected = _bool_or_none(
        primary_action.get("deterministic_stop_expected"),
    )
    review_verdict, review_note = _classify_fixture_review_verdict(
        fixture_name=fixture_name,
        review_summary={
            "comparison_status": comparison_status,
            "action_type": action_type,
            "guarded_strategy": _maybe_string(primary_action.get("guarded_strategy")),
            "selected_source_key": selected_source_key,
            "deterministic_target_source_key": deterministic_target_source_key,
            "selected_entity_ids": selected_entity_ids,
            "deterministic_selected_entity_ids": deterministic_selected_entity_ids,
            "exact_chase_selection_match": exact_chase_selection_match,
            "qualitative_rationale_present": rationale is not None,
            "stop_reason": stop_reason,
            "deterministic_stop_expected": deterministic_stop_expected,
        },
    )
    orchestrator_guarded_mode = _extract_enrichment_execution_mode(
        orchestrator_summary,
    )
    deferred_guarded_source_count = _count_deferred_guarded_sources(
        orchestrator_summary,
    )
    filtered_chase_context_drift = _filtered_chase_context_differs(
        baseline_summary=baseline_summary,
        orchestrator_summary=orchestrator_summary,
    )
    drift_class, drift_note = _classify_downstream_drift(
        review_verdict=review_verdict,
        mismatches=mismatches,
        proposal_count_delta=proposal_count_delta,
        comparison_status=comparison_status,
        orchestrator_guarded_mode=orchestrator_guarded_mode,
        deferred_guarded_source_count=deferred_guarded_source_count,
        filtered_chase_context_drift=filtered_chase_context_drift,
        compare_mode=compare_mode,
    )
    top_mismatch = _select_top_mismatch(
        mismatches=mismatches,
        drift_class=drift_class,
    )
    return {
        "selected_source_key": selected_source_key,
        "deterministic_target_source_key": deterministic_target_source_key,
        "comparison_status": comparison_status,
        "action_type": action_type,
        "guarded_strategy": _maybe_string(primary_action.get("guarded_strategy")),
        "round_number": _int_or_none(primary_action.get("round_number")),
        "target_action_type": _maybe_string(primary_action.get("target_action_type")),
        "planner_status": _maybe_string(primary_action.get("planner_status")),
        "stop_reason": stop_reason,
        "deterministic_stop_expected": deterministic_stop_expected,
        "selected_entity_ids": selected_entity_ids,
        "selected_labels": selected_labels,
        "deterministic_selected_entity_ids": deterministic_selected_entity_ids,
        "deterministic_selected_labels": deterministic_selected_labels,
        "selected_entity_overlap_count": _int_or_none(
            primary_action.get("selected_entity_overlap_count"),
        ),
        "exact_chase_selection_match": exact_chase_selection_match,
        "selection_basis": _maybe_string(primary_action.get("selection_basis")),
        "baseline_proposal_count": baseline_proposal_count,
        "orchestrator_proposal_count": orchestrator_proposal_count,
        "proposal_count_delta": proposal_count_delta,
        "orchestrator_guarded_mode": orchestrator_guarded_mode,
        "deferred_guarded_source_count": deferred_guarded_source_count,
        "baseline_pending_questions_count": _list_count(
            baseline_summary.get("pending_questions"),
        ),
        "orchestrator_pending_questions_count": _list_count(
            orchestrator_summary.get("pending_questions"),
        ),
        "baseline_filtered_chase_candidate_count": _int_or_none(
            baseline_chase_context.get("filtered_chase_candidate_count"),
        ),
        "baseline_filtered_chase_filter_reason_counts": _dict_of_ints(
            baseline_chase_context.get("filtered_chase_filter_reason_counts"),
        ),
        "baseline_filtered_chase_labels": _string_list(
            baseline_chase_context.get("filtered_chase_labels"),
        ),
        "orchestrator_filtered_chase_candidate_count": _int_or_none(
            orchestrator_chase_context.get("filtered_chase_candidate_count"),
        ),
        "orchestrator_filtered_chase_filter_reason_counts": _dict_of_ints(
            orchestrator_chase_context.get("filtered_chase_filter_reason_counts"),
        ),
        "orchestrator_filtered_chase_labels": _string_list(
            orchestrator_chase_context.get("filtered_chase_labels"),
        ),
        "qualitative_rationale_present": rationale is not None,
        "qualitative_rationale_excerpt": _excerpt_text(rationale, max_chars=220),
        "review_verdict": review_verdict,
        "review_note": review_note,
        "mismatch_count": len(mismatches),
        "drift_class": drift_class,
        "drift_note": drift_note,
        "top_mismatch": top_mismatch,
    }


def _select_primary_review_action(candidate_actions: list[JSONObject]) -> JSONObject:
    """Pick the action that should drive the human review summary.

    Guarded source narrowing often appears first, but chase-selection divergence is the
    sharper manual-review signal once the planner is actually steering chase rounds.
    Prefer a mismatched chase selection when present so the summary reflects the
    highest-signal remaining review question.
    """

    for action in candidate_actions:
        if _maybe_string(action.get("guarded_strategy")) != "chase_selection":
            continue
        if _bool_or_none(action.get("exact_selection_match")) is False:
            return action
    for action in candidate_actions:
        if _maybe_string(action.get("guarded_strategy")) == "chase_selection":
            return action
    for action in candidate_actions:
        if _maybe_string(action.get("guarded_strategy")) != "terminal_control_flow":
            continue
        if _maybe_string(action.get("checkpoint_key")) not in {
            "after_bootstrap",
            "after_chase_round_1",
        }:
            continue
        return action
    return candidate_actions[0] if candidate_actions else {}


def _classify_fixture_review_verdict(
    *,
    fixture_name: str,
    review_summary: JSONObject,
) -> tuple[str, str]:
    normalized_fixture = fixture_name.strip().casefold()
    comparison_status = _maybe_string(review_summary.get("comparison_status"))
    action_type = _maybe_string(review_summary.get("action_type"))
    guarded_strategy = _maybe_string(review_summary.get("guarded_strategy"))
    selected_source_key = _maybe_string(review_summary.get("selected_source_key"))
    deterministic_target_source_key = _maybe_string(
        review_summary.get("deterministic_target_source_key"),
    )
    exact_chase_selection_match = _bool_or_none(
        review_summary.get("exact_chase_selection_match"),
    )
    selected_entity_ids = _string_list(review_summary.get("selected_entity_ids"))
    deterministic_selected_entity_ids = _string_list(
        review_summary.get("deterministic_selected_entity_ids"),
    )
    qualitative_rationale_present = bool(
        review_summary.get("qualitative_rationale_present"),
    )
    stop_reason = _maybe_string(review_summary.get("stop_reason"))
    deterministic_stop_expected = _bool_or_none(
        review_summary.get("deterministic_stop_expected"),
    )
    if comparison_status == "matched":
        if action_type == "STOP" and guarded_strategy == "terminal_control_flow":
            if deterministic_stop_expected is True:
                reason_suffix = (
                    f" ({stop_reason.replace('_', ' ')})"
                    if stop_reason is not None
                    else ""
                )
                return (
                    "expected_match",
                    "Planner correctly stopped at the chase checkpoint because the "
                    f"deterministic threshold was not met{reason_suffix}.",
                )
            reason_suffix = (
                f" ({stop_reason.replace('_', ' ')})" if stop_reason is not None else ""
            )
            return (
                "expected_match",
                "Planner correctly used guarded terminal control at the chase "
                f"checkpoint{reason_suffix}.",
            )
        if action_type == "RUN_CHASE_ROUND":
            return (
                "expected_match",
                "Planner matched the deterministic chase selection for this fixture.",
            )
        return (
            "expected_match",
            "Planner matched the deterministic next source for this fixture.",
        )
    if not qualitative_rationale_present:
        if action_type == "RUN_CHASE_ROUND":
            return (
                "needs_review",
                "Planner did not provide qualitative rationale for the chase selection.",
            )
        return (
            "needs_review",
            "Planner did not provide qualitative rationale for the source choice.",
        )
    if (
        normalized_fixture == "brca1"
        and comparison_status in {"diverged", "mismatch"}
        and action_type == "RUN_STRUCTURED_ENRICHMENT"
        and selected_source_key == "drugbank"
        and deterministic_target_source_key == "clinvar"
    ):
        return (
            "acceptable_divergence",
            "Objective is therapy-shaped, so preferring DrugBank over ClinVar is acceptable for BRCA1.",
        )
    if (
        normalized_fixture == "med13"
        and comparison_status in {"diverged", "mismatch"}
        and action_type == "RUN_STRUCTURED_ENRICHMENT"
        and selected_source_key in {"marrvel", "mgi"}
        and deterministic_target_source_key == "clinvar"
    ):
        return (
            "acceptable_divergence",
            "Objective is developmental/model-organism shaped, so preferring a model-organism source over ClinVar is acceptable for MED13.",
        )
    if (
        action_type == "RUN_CHASE_ROUND"
        and comparison_status in {"diverged", "mismatch"}
        and selected_entity_ids
        and set(selected_entity_ids).issubset(set(deterministic_selected_entity_ids))
        and exact_chase_selection_match is False
    ):
        return (
            "acceptable_divergence",
            "Planner narrowed the deterministic chase set to a bounded subset with qualitative rationale, so this guarded divergence is acceptable.",
        )
    if (
        action_type == "STOP"
        and guarded_strategy == "terminal_control_flow"
        and comparison_status in {"diverged", "mismatch"}
        and stop_reason is not None
    ):
        return (
            "accepted_conservative_stop",
            "Planner made a conservative guarded STOP with qualitative rationale; treat this as an accepted safety-first divergence when the proof gate is clean.",
        )
    if comparison_status in {"diverged", "mismatch"}:
        return (
            "needs_review",
            "Planner diverged from the deterministic source without a fixture-specific acceptance rule.",
        )
    return (
        "needs_review",
        "Planner did not expose enough comparison detail to classify this fixture automatically.",
    )


def _classify_downstream_drift(  # noqa: PLR0913
    *,
    review_verdict: str,
    mismatches: list[str],
    proposal_count_delta: int,
    comparison_status: str | None,
    orchestrator_guarded_mode: str | None,
    deferred_guarded_source_count: int,
    filtered_chase_context_drift: bool,
    compare_mode: Phase1GuardedCompareMode,
) -> tuple[str | None, str | None]:
    if not mismatches:
        return (None, None)
    if (
        review_verdict == "expected_match"
        and comparison_status == "matched"
        and (
            orchestrator_guarded_mode == "guarded_single_source"
            or deferred_guarded_source_count > 0
        )
    ):
        return (
            "guarded_narrowing_drift",
            "Guarded mode intentionally narrowed structured enrichment to one source, so downstream workspace drift is expected.",
        )
    if review_verdict in {"acceptable_divergence", "accepted_conservative_stop"}:
        return (
            "expected_follow_on_drift",
            "Planner intentionally chose a different accepted path, so downstream workspace drift is expected.",
        )
    if (
        review_verdict == "expected_match"
        and comparison_status == "matched"
        and compare_mode == "dual_live_guarded"
        and proposal_count_delta == 0
        and filtered_chase_context_drift
        and all(
            mismatch
            == "source_results differ between baseline and orchestrator summaries"
            for mismatch in mismatches
        )
    ):
        return (
            "live_source_jitter",
            "Planner matched the deterministic next step, and the remaining drift is limited to chase-candidate pool differences across the two live spaces.",
        )
    if (
        review_verdict == "expected_match"
        and comparison_status == "matched"
        and compare_mode == "dual_live_guarded"
    ):
        if proposal_count_delta == 0 and _mismatches_are_downstream_state_only(
            mismatches,
        ):
            return (
                "downstream_state_drift",
                "Planner matched the deterministic next step and evidence counts aligned; the remaining drift is limited to generated follow-up state such as pending-question wording or summary fields.",
            )
        return (
            "live_source_jitter",
            "Planner matched the deterministic next step, and the remaining drift is likely coming from rerunning live sources in a separate space.",
        )
    if review_verdict == "expected_match":
        return (
            "execution_drift",
            "Planner matched the deterministic next step, but the final workspace still drifted and should be investigated.",
        )
    return (
        "needs_review",
        "Workspace drift is present and this fixture still needs manual review.",
    )


def _select_top_mismatch(
    *,
    mismatches: list[str],
    drift_class: str | None,
) -> str | None:
    if not mismatches:
        return None
    if drift_class == "live_source_jitter":
        for mismatch in mismatches:
            if not mismatch.startswith("proposal_count: "):
                return mismatch
    return mismatches[0]


def _filtered_chase_context_differs(
    *,
    baseline_summary: JSONObject,
    orchestrator_summary: JSONObject,
) -> bool:
    baseline_context = _latest_chase_context(baseline_summary)
    orchestrator_context = _latest_chase_context(orchestrator_summary)
    if not baseline_context and not orchestrator_context:
        return False
    return (
        _int_or_none(baseline_context.get("filtered_chase_candidate_count"))
        != _int_or_none(orchestrator_context.get("filtered_chase_candidate_count"))
        or _dict_of_ints(baseline_context.get("filtered_chase_filter_reason_counts"))
        != _dict_of_ints(
            orchestrator_context.get("filtered_chase_filter_reason_counts"),
        )
        or _string_list(baseline_context.get("filtered_chase_labels"))
        != _string_list(orchestrator_context.get("filtered_chase_labels"))
    )


def _extract_enrichment_execution_mode(workspace_summary: JSONObject) -> str | None:
    source_results = _dict_value(workspace_summary.get("source_results"))
    orchestration = _dict_value(source_results.get("enrichment_orchestration"))
    return _maybe_string(orchestration.get("execution_mode"))


def _count_deferred_guarded_sources(workspace_summary: JSONObject) -> int:
    source_results = _dict_value(workspace_summary.get("source_results"))
    deferred_count = 0
    for source_key, source_summary in source_results.items():
        if source_key == "enrichment_orchestration":
            continue
        normalized_summary = _dict_value(source_summary)
        if normalized_summary.get("deferred_reason") == "guarded_source_selection":
            deferred_count += 1
    return deferred_count


def _mismatches_are_downstream_state_only(mismatches: list[str]) -> bool:
    allowed_prefixes = (
        "pending_questions:",
        "source_results differ between baseline and orchestrator summaries",
    )
    return bool(mismatches) and all(
        any(mismatch.startswith(prefix) for prefix in allowed_prefixes)
        for mismatch in mismatches
    )
