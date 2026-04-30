"""Markdown and file rendering for Phase 1 guarded evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.phase1_guarded_eval.common import (
    _bool_or_none,
    _canary_verdict_label,
    _dict_of_ints,
    _dict_value,
    _display_float,
    _fixture_list_text,
    _gate_label,
    _int_or_none,
    _list_of_dicts,
    _maybe_string,
    _optional_gate_label,
    _string_list,
)
from scripts.phase1_guarded_eval.review import _classify_fixture_review_verdict

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject


def _drift_label(value: object) -> str | None:
    drift_class = _maybe_string(value)
    if drift_class == "execution_drift":
        return "Execution drift"
    if drift_class == "live_source_jitter":
        return "Live-source jitter"
    if drift_class == "downstream_state_drift":
        return "Downstream state drift"
    if drift_class == "guarded_narrowing_drift":
        return "Expected guarded narrowing"
    if drift_class == "expected_follow_on_drift":
        return "Expected downstream drift"
    if drift_class == "needs_review":
        return "Review-needed drift"
    return None


def _selected_action_display(
    review_summary: JSONObject,
    *,
    target: bool,
) -> str:
    if target:
        if _bool_or_none(review_summary.get("deterministic_stop_expected")) is True:
            return "STOP"
        if (
            _maybe_string(review_summary.get("action_type")) == "STOP"
            and _maybe_string(review_summary.get("guarded_strategy"))
            == "terminal_control_flow"
            and _maybe_string(review_summary.get("comparison_status")) == "matched"
        ):
            return "STOP"
    elif _maybe_string(review_summary.get("action_type")) == "STOP":
        return "STOP"
    source_key = (
        _maybe_string(review_summary.get("deterministic_target_source_key"))
        if target
        else _maybe_string(review_summary.get("selected_source_key"))
    )
    if source_key is not None:
        return source_key
    labels = (
        _string_list(review_summary.get("deterministic_selected_labels"))
        if target
        else _string_list(review_summary.get("selected_labels"))
    )
    if labels:
        return _compact_label_display(labels)
    return "n/a"


def _compact_label_display(labels: list[str], *, limit: int = 3) -> str:
    if len(labels) <= limit:
        return ", ".join(labels)
    head = ", ".join(labels[:limit])
    return f"{head} (+{len(labels) - limit})"


def _format_reason_counts(reason_counts: dict[str, int]) -> str:
    if not reason_counts:
        return "none"
    ordered_items = sorted(reason_counts.items())
    return ", ".join(f"{reason}={count}" for reason, count in ordered_items)


def _render_filtered_chase_summary(review_summary: JSONObject) -> str | None:
    baseline_count = _int_or_none(
        review_summary.get("baseline_filtered_chase_candidate_count"),
    )
    orchestrator_count = _int_or_none(
        review_summary.get("orchestrator_filtered_chase_candidate_count"),
    )
    baseline_labels = _string_list(review_summary.get("baseline_filtered_chase_labels"))
    orchestrator_labels = _string_list(
        review_summary.get("orchestrator_filtered_chase_labels"),
    )
    baseline_reasons = _dict_of_ints(
        review_summary.get("baseline_filtered_chase_filter_reason_counts"),
    )
    orchestrator_reasons = _dict_of_ints(
        review_summary.get("orchestrator_filtered_chase_filter_reason_counts"),
    )
    if (
        (baseline_count in {None, 0})
        and (orchestrator_count in {None, 0})
        and not baseline_labels
        and not orchestrator_labels
    ):
        return None
    if (
        baseline_count == orchestrator_count
        and baseline_labels == orchestrator_labels
        and baseline_reasons == orchestrator_reasons
    ):
        return (
            f"shared count={baseline_count or 0}"
            f" | reasons={_format_reason_counts(baseline_reasons)}"
            f" | examples={_compact_label_display(baseline_labels) if baseline_labels else 'n/a'}"
        )
    return (
        f"baseline count={baseline_count or 0}"
        f" | reasons={_format_reason_counts(baseline_reasons)}"
        f" | examples={_compact_label_display(baseline_labels) if baseline_labels else 'n/a'}"
        f" || orchestrator count={orchestrator_count or 0}"
        f" | reasons={_format_reason_counts(orchestrator_reasons)}"
        f" | examples={_compact_label_display(orchestrator_labels) if orchestrator_labels else 'n/a'}"
    )


def _render_chase_selection_summary(review_summary: JSONObject) -> str | None:
    selected_labels = _string_list(review_summary.get("selected_labels"))
    deterministic_labels = _string_list(
        review_summary.get("deterministic_selected_labels"),
    )
    if not selected_labels and not deterministic_labels:
        return None
    overlap_count = _int_or_none(review_summary.get("selected_entity_overlap_count"))
    exact_match = _bool_or_none(review_summary.get("exact_chase_selection_match"))
    exact_label = (
        "yes" if exact_match is True else "no" if exact_match is False else "n/a"
    )
    overlap_label = overlap_count if overlap_count is not None else "n/a"
    return (
        f"planner={', '.join(selected_labels) or 'n/a'}"
        f" | deterministic={', '.join(deterministic_labels) or 'n/a'}"
        f" | overlap={overlap_label}"
        f" | exact match={exact_label}"
    )


def _render_terminal_control_summary(review_summary: JSONObject) -> str | None:
    if _maybe_string(review_summary.get("action_type")) != "STOP":
        return None
    stop_reason = _maybe_string(review_summary.get("stop_reason")) or "unspecified"
    deterministic_stop_expected = _bool_or_none(
        review_summary.get("deterministic_stop_expected"),
    )
    if deterministic_stop_expected is True:
        expected_label = "yes"
    elif deterministic_stop_expected is False:
        expected_label = "no"
    elif _maybe_string(review_summary.get("comparison_status")) == "matched":
        expected_label = "matched terminal control"
    else:
        expected_label = "n/a"
    return (
        f"planner=STOP | deterministic_stop_expected={expected_label}"
        f" | stop_reason={stop_reason}"
    )


def _review_note_for_display(
    *,
    fixture_name: str,
    review_summary: JSONObject,
) -> str | None:
    _review_verdict, review_note = _classify_fixture_review_verdict(
        fixture_name=fixture_name,
        review_summary=review_summary,
    )
    return review_note


def render_phase1_guarded_evaluation_markdown(  # noqa: PLR0912, PLR0915
    report: JSONObject,
) -> str:
    """Render a concise Markdown summary for human review."""

    summary = _dict_value(report.get("summary"))
    automated_gates = _dict_value(report.get("automated_gates"))
    guarded_graduation_gate = _dict_value(report.get("guarded_graduation_gate"))
    graduation_summary = _dict_value(guarded_graduation_gate.get("summary"))
    graduation_gates = _dict_value(guarded_graduation_gate.get("automated_gates"))
    canary_gate = _dict_value(report.get("canary_gate"))
    canary_summary = _dict_value(canary_gate.get("summary"))
    canary_gates = _dict_value(canary_gate.get("automated_gates"))
    source_policy_violation_counts = _dict_value(
        canary_summary.get("source_policy_violation_counts"),
    )
    fixtures = _list_of_dicts(report.get("fixtures"))
    report_mode = _maybe_string(report.get("report_mode")) or "standard"
    lines = [
        (
            "# Guarded Source+Chase Canary Evaluation"
            if report_mode == "canary"
            else "# Phase 1 Guarded Evaluation"
        ),
        "",
        f"- Generated: {report.get('generated_at', 'n/a')}",
        f"- Planner mode: {report.get('planner_mode', 'guarded')}",
        f"- Compare mode: {report.get('compare_mode', 'unknown')}",
        f"- Report mode: {report_mode}",
        f"- Fixture set: {report.get('fixture_set', 'objective')}",
        f"- PubMed backend: {report.get('pubmed_backend', 'unknown')}",
        f"- Guarded rollout profile: {report.get('guarded_rollout_profile', 'unknown')}",
        f"- Repeat count: {report.get('repeat_count', 1)}",
    ]
    canary_label = _maybe_string(report.get("canary_label"))
    if canary_label is not None:
        lines.append(f"- Canary label: {canary_label}")
    if report.get("expected_run_count") is not None:
        lines.append(f"- Expected run count: {report.get('expected_run_count')}")
    lines.extend(
        [
            (
                "- Guarded chase rollout: "
                f"{'enabled' if report.get('guarded_chase_rollout_enabled') else 'disabled'}"
            ),
            f"- Automated gates: {'PASS' if automated_gates.get('all_passed') else 'FAIL'}",
            (
                "- Guarded graduation gate: "
                f"{'PASS' if guarded_graduation_gate.get('all_passed') else 'FAIL'}"
            ),
        ]
    )
    if report_mode == "canary":
        lines.append(
            "- Canary gate: "
            f"{'PASS' if canary_gate.get('all_passed') else 'FAIL'}"
            f" ({_canary_verdict_label(canary_gate.get('verdict'))})",
        )
    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Fixtures: {summary.get('fixture_count', 0)}",
            f"- Runs: {summary.get('run_count', summary.get('fixture_count', 0))}",
            f"- Unique fixtures: {summary.get('unique_fixture_count', 0)}",
            f"- Completed fixtures: {summary.get('completed_fixture_count', 0)}",
            f"- Failed fixtures: {summary.get('failed_fixture_count', 0)}",
            f"- Timed-out fixtures: {summary.get('timed_out_fixture_count', 0)}",
            (
                "- Timed-out fixture names: "
                f"{_fixture_list_text(summary.get('timed_out_fixtures'))}"
            ),
            (
                "- Total runtime (s): "
                f"{_display_float(summary.get('total_runtime_seconds'))}"
            ),
            (
                "- Average runtime (s): "
                f"{_display_float(summary.get('average_runtime_seconds'))}"
            ),
            f"- Guarded actions applied: {summary.get('applied_count', 0)}",
            f"- Guarded interventions identified: {summary.get('identified_count', 0)}",
            f"- Replay-only guarded candidates: {summary.get('candidate_count', 0)}",
            f"- Guarded actions verified: {summary.get('verified_count', 0)}",
            f"- Verification failures: {summary.get('verification_failed_count', 0)}",
            f"- Pending verifications: {summary.get('pending_verification_count', 0)}",
            f"- Guarded chase actions: {summary.get('chase_action_count', 0)}",
            f"- Verified guarded chase actions: {summary.get('chase_verified_count', 0)}",
            (
                f"- Replay-only chase candidates: {summary.get('chase_candidate_count', 0)}"
            ),
        ],
    )
    lines.extend(
        [
            (
                "- Exact chase selection matches: "
                f"{summary.get('chase_exact_selection_match_count', 0)}"
            ),
            (
                "- Replay exact chase selection matches: "
                f"{summary.get('chase_candidate_exact_selection_match_count', 0)}"
            ),
            (
                "- Chase selected-entity overlap total: "
                f"{summary.get('chase_selected_entity_overlap_total', 0)}"
            ),
            (
                "- Chase selection mismatches: "
                f"{summary.get('chase_selection_mismatch_count', 0)}"
            ),
            (
                "- Guarded terminal-control actions: "
                f"{summary.get('terminal_control_action_count', 0)}"
            ),
            (
                "- Verified terminal-control actions: "
                f"{summary.get('terminal_control_verified_count', 0)}"
            ),
            (
                "- Guarded chase checkpoint stops: "
                f"{summary.get('chase_checkpoint_stop_count', 0)}"
            ),
            (
                "- Orchestrator filtered chase candidates: "
                f"{summary.get('orchestrator_filtered_chase_candidate_count', 0)}"
            ),
            (
                "- Fixtures with guarded chase actions: "
                f"{_fixture_list_text(summary.get('fixtures_with_guarded_chase_actions'))}"
            ),
            (
                "- Fixtures with guarded terminal control: "
                f"{_fixture_list_text(summary.get('fixtures_with_guarded_terminal_control'))}"
            ),
            (
                "- Fixtures with guarded chase checkpoint stops: "
                f"{_fixture_list_text(summary.get('fixtures_with_guarded_chase_checkpoint_stops'))}"
            ),
            (
                "- Fixtures with replay-only chase candidates: "
                f"{_fixture_list_text(summary.get('fixtures_with_replay_only_chase_candidates'))}"
            ),
            (
                "- Fixtures with filtered chase candidates: "
                f"{_fixture_list_text(summary.get('fixtures_with_filtered_chase_candidates'))}"
            ),
            f"- Source matches: {summary.get('matched_count', 0)}",
            f"- Source divergences: {summary.get('diverged_count', 0)}",
            f"- Expected matches: {summary.get('expected_match_count', 0)}",
            f"- Acceptable divergences: {summary.get('acceptable_divergence_count', 0)}",
            (
                "- Accepted conservative stops: "
                f"{summary.get('accepted_conservative_stop_count', 0)}"
            ),
            f"- Needs review: {summary.get('needs_review_count', 0)}",
            f"- Execution drift after match: {summary.get('execution_drift_count', 0)}",
            (
                "- Downstream state drift after match: "
                f"{summary.get('downstream_state_drift_count', 0)}"
            ),
            (
                "- Expected guarded narrowing after match: "
                f"{summary.get('guarded_narrowing_drift_count', 0)}"
            ),
            (
                "- Expected downstream drift after accepted divergence: "
                f"{summary.get('expected_follow_on_drift_count', 0)}"
            ),
            (
                "- Qualitative rationale present: "
                f"{summary.get('qualitative_rationale_present_count', 0)}/"
                f"{summary.get('fixture_count', 0)}"
            ),
            (f"- Guarded proof receipts: {graduation_summary.get('proof_count', 0)}"),
            (
                "- Allowed guarded proof receipts: "
                f"{graduation_summary.get('allowed_count', 0)}"
            ),
            (
                "- Blocked or ignored guarded proof receipts: "
                f"{graduation_summary.get('blocked_or_ignored_count', 0)}"
            ),
            (
                "- Source-selection interventions: "
                f"{graduation_summary.get('source_selection_intervention_count', 0)}"
            ),
            (
                "- Chase-or-stop interventions: "
                f"{graduation_summary.get('chase_or_stop_intervention_count', 0)}"
            ),
            "",
            "## Automated Gates",
            "",
            f"- No fixture errors: {_gate_label(automated_gates.get('no_fixture_errors'))}",
            f"- No verification failures: {_gate_label(automated_gates.get('no_verification_failures'))}",
            f"- No pending verifications: {_gate_label(automated_gates.get('no_pending_verifications'))}",
            f"- At least one guarded action applied: {_gate_label(automated_gates.get('at_least_one_guarded_action_applied'))}",
            f"- At least one guarded intervention identified: {_gate_label(automated_gates.get('at_least_one_guarded_intervention_identified'))}",
            "",
            "## Guarded Graduation Gate",
            "",
        ],
    )
    lines.extend(
        [
            (
                "- Proof summaries present: "
                f"{_gate_label(graduation_gates.get('proof_summaries_present'))}"
            ),
            (
                "- Reviewable proof receipts present: "
                f"{_gate_label(graduation_gates.get('reviewable_proofs_present'))}"
            ),
            (
                "- At least one allowed proof receipt: "
                f"{_gate_label(graduation_gates.get('at_least_one_allowed_proof'))}"
            ),
            (
                "- No blocked or ignored proof receipts: "
                f"{_gate_label(graduation_gates.get('no_blocked_or_ignored_proofs'))}"
            ),
            (
                "- All allowed proof receipts verified: "
                f"{_gate_label(graduation_gates.get('all_allowed_proofs_verified'))}"
            ),
            (
                "- No fallback recommendations: "
                f"{_gate_label(graduation_gates.get('no_fallback_recommendations'))}"
            ),
            (
                "- No invalid outputs: "
                f"{_gate_label(graduation_gates.get('no_invalid_outputs'))}"
            ),
            (
                "- No budget violations: "
                f"{_gate_label(graduation_gates.get('no_budget_violations'))}"
            ),
            (
                "- No disabled-source violations: "
                f"{_gate_label(graduation_gates.get('no_disabled_source_violations'))}"
            ),
            (
                "- Qualitative rationale present everywhere: "
                f"{_gate_label(graduation_gates.get('qualitative_rationale_present_everywhere'))}"
            ),
            (
                "- At least one source-selection intervention: "
                f"{_optional_gate_label(graduation_gates.get('at_least_one_source_selection_intervention'))}"
            ),
            (
                "- At least one chase-or-stop intervention: "
                f"{_optional_gate_label(graduation_gates.get('at_least_one_chase_or_stop_intervention'))}"
            ),
            (
                "- Profile authority exercised everywhere: "
                f"{_optional_gate_label(graduation_gates.get('profile_authority_exercised_everywhere'))}"
            ),
            (
                "- Readiness source-selection interventions: "
                f"{graduation_summary.get('readiness_source_selection_intervention_count', 0)}"
            ),
            (
                "- Readiness chase-or-stop interventions: "
                f"{graduation_summary.get('readiness_chase_or_stop_intervention_count', 0)}"
            ),
            (
                "- Readiness brief-generation interventions: "
                f"{graduation_summary.get('readiness_brief_generation_intervention_count', 0)}"
            ),
            (
                "- Fixtures missing profile authority: "
                f"{_fixture_list_text(graduation_summary.get('fixtures_missing_profile_authority'))}"
            ),
            (
                "- Fixtures needing review: "
                f"{_fixture_list_text(graduation_summary.get('fixtures_needing_review'))}"
            ),
        ],
    )
    if report_mode == "canary":
        lines.extend(
            [
                "",
                "## Canary Gate",
                "",
                f"- Verdict: {_canary_verdict_label(canary_gate.get('verdict'))}",
                (
                    "- Proof-clean runs: "
                    f"{canary_summary.get('proof_clean_run_count', 0)}/"
                    f"{canary_summary.get('run_count', 0)}"
                ),
                (
                    "- Expected run count met: "
                    f"{_gate_label(canary_gates.get('expected_run_count_met'))}"
                ),
                (
                    "- No fixture failures: "
                    f"{_gate_label(canary_gates.get('no_fixture_failures'))}"
                ),
                f"- No timeouts: {_gate_label(canary_gates.get('no_timeouts'))}",
                (
                    "- Proof receipts present and verified: "
                    f"{_gate_label(canary_gates.get('proof_receipts_present_and_verified'))}"
                ),
                (
                    "- No invalid outputs: "
                    f"{_gate_label(canary_gates.get('no_invalid_outputs'))}"
                ),
                (
                    "- No fallback outputs: "
                    f"{_gate_label(canary_gates.get('no_fallback_outputs'))}"
                ),
                (
                    "- No budget violations: "
                    f"{_gate_label(canary_gates.get('no_budget_violations'))}"
                ),
                (
                    "- No disabled-source violations: "
                    f"{_gate_label(canary_gates.get('no_disabled_source_violations'))}"
                ),
                (
                    "- No reserved-source violations: "
                    f"{_gate_label(canary_gates.get('no_reserved_source_violations'))}"
                ),
                (
                    "- No context-only source violations: "
                    f"{_gate_label(canary_gates.get('no_context_only_source_violations'))}"
                ),
                (
                    "- No grounding-source violations: "
                    f"{_gate_label(canary_gates.get('no_grounding_source_violations'))}"
                ),
                (
                    "- Qualitative rationale present everywhere: "
                    f"{_gate_label(canary_gates.get('qualitative_rationale_present_everywhere'))}"
                ),
                (
                    "- Profile authority exercised everywhere: "
                    f"{_gate_label(canary_gates.get('profile_authority_exercised_everywhere'))}"
                ),
                (
                    "- At least one source-selection intervention: "
                    f"{_gate_label(canary_gates.get('at_least_one_source_selection_intervention'))}"
                ),
                (
                    "- At least one chase-or-stop intervention: "
                    f"{_gate_label(canary_gates.get('at_least_one_chase_or_stop_intervention'))}"
                ),
                (
                    "- Source-policy violations: disabled="
                    f"{source_policy_violation_counts.get('disabled', 0)}, "
                    "reserved="
                    f"{source_policy_violation_counts.get('reserved', 0)}, "
                    "context_only="
                    f"{source_policy_violation_counts.get('context_only', 0)}, "
                    "grounding="
                    f"{source_policy_violation_counts.get('grounding', 0)}"
                ),
                (
                    "- Canary notes: "
                    f"{'; '.join(_string_list(canary_gate.get('notes'))) or 'none'}"
                ),
            ],
        )
    lines.extend(
        [
            "",
            "## Fixtures",
            "",
            "| Fixture | Status | Selected | Target | Compare | Verdict | Applied | Verified | Proof Gate |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ],
    )
    for fixture in fixtures:
        guarded = _dict_value(fixture.get("guarded_evaluation"))
        review_summary = _dict_value(fixture.get("review_summary"))
        graduation_review = _dict_value(fixture.get("guarded_graduation_review"))
        lines.append(
            "| "
            f"{fixture.get('fixture_name', 'unknown')} | "
            f"{guarded.get('status', 'unknown')} | "
            f"{_selected_action_display(review_summary, target=False)} | "
            f"{_selected_action_display(review_summary, target=True)} | "
            f"{review_summary.get('comparison_status', 'n/a')} | "
            f"{review_summary.get('review_verdict', 'n/a')} | "
            f"{guarded.get('applied_count', 0)} | "
            f"{guarded.get('verified_count', 0)} | "
            f"{'PASS' if graduation_review.get('gate_passed') else 'FAIL'} | "
        )
    lines.extend(("", "## Fixture Notes", ""))
    for fixture in fixtures:
        fixture_error = _dict_value(fixture.get("fixture_error"))
        review_summary = _dict_value(fixture.get("review_summary"))
        graduation_review = _dict_value(fixture.get("guarded_graduation_review"))
        lines.extend(
            [
                f"### {fixture.get('fixture_name', 'unknown')}",
                (
                    f"- Selected: {_selected_action_display(review_summary, target=False)}"
                    f" | Target: "
                    f"{_selected_action_display(review_summary, target=True)}"
                    f" | Compare: {review_summary.get('comparison_status', 'n/a')}"
                    f" | Verdict: {review_summary.get('review_verdict', 'n/a')}"
                ),
                (
                    f"- Proposals: baseline={review_summary.get('baseline_proposal_count', 'n/a')}"
                    f" | orchestrator={review_summary.get('orchestrator_proposal_count', 'n/a')}"
                    f" | delta={review_summary.get('proposal_count_delta', 'n/a')}"
                ),
                (
                    "- Runtime (s): "
                    f"{_display_float(fixture.get('fixture_runtime_seconds'))}"
                ),
                (
                    "- Proof gate: "
                    f"{'PASS' if graduation_review.get('gate_passed') else 'FAIL'}"
                    f" | proofs={graduation_review.get('proof_count', 0)}"
                    f" | allowed={graduation_review.get('allowed_count', 0)}"
                    f" | blocked_or_ignored="
                    f"{graduation_review.get('blocked_or_ignored_count', 0)}"
                ),
            ],
        )
        if fixture_error:
            lines.append(
                "- Fixture error: "
                f"{fixture_error.get('error_type', 'unknown')}: "
                f"{fixture_error.get('error_message', '')}"
            )
        proof_notes = _string_list(graduation_review.get("notes"))
        if proof_notes:
            lines.append(f"- Proof notes: {'; '.join(proof_notes)}")
        verdict_note = _review_note_for_display(
            fixture_name=str(fixture.get("fixture_name", "unknown")),
            review_summary=review_summary,
        )
        if verdict_note is not None:
            lines.append(f"- Verdict note: {verdict_note}")
        rationale_excerpt = _maybe_string(
            review_summary.get("qualitative_rationale_excerpt"),
        )
        if rationale_excerpt is not None:
            lines.append(f"- Rationale: {rationale_excerpt}")
        terminal_control_summary = _render_terminal_control_summary(review_summary)
        if terminal_control_summary is not None:
            lines.append(f"- Terminal control: {terminal_control_summary}")
        chase_summary = _render_chase_selection_summary(review_summary)
        if chase_summary is not None:
            lines.append(f"- Chase selection: {chase_summary}")
        filtered_chase_summary = _render_filtered_chase_summary(review_summary)
        if filtered_chase_summary is not None:
            lines.append(f"- Filtered chase candidates: {filtered_chase_summary}")
        drift_label = _drift_label(review_summary.get("drift_class"))
        top_mismatch = _maybe_string(review_summary.get("top_mismatch"))
        if drift_label is not None and top_mismatch is not None:
            lines.append(f"- {drift_label}: {top_mismatch}")
        drift_note = _maybe_string(review_summary.get("drift_note"))
        if drift_note is not None:
            lines.append(f"- Drift note: {drift_note}")
        if drift_label is None and top_mismatch is not None:
            lines.append(f"- Top mismatch: {top_mismatch}")
        lines.append("")
    return "\n".join(lines)


def write_phase1_guarded_evaluation_report(
    report: JSONObject,
    *,
    output_dir: str | Path,
) -> JSONObject:
    """Write the aggregate report and per-fixture JSON payloads."""

    _validate_guarded_report_payload(report)
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    summary_json_path = output_dir_path / "summary.json"
    summary_markdown_path = output_dir_path / "summary.md"
    summary_json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_markdown_path.write_text(
        render_phase1_guarded_evaluation_markdown(report) + "\n",
        encoding="utf-8",
    )

    fixture_report_paths: JSONObject = {}
    for fixture_report in _list_of_dicts(report.get("fixtures")):
        fixture_name = str(fixture_report.get("fixture_name", "unknown"))
        fixture_path = output_dir_path / f"{fixture_name.casefold()}_guarded.json"
        fixture_path.write_text(
            json.dumps(fixture_report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        fixture_report_paths[fixture_name] = str(fixture_path)

    manifest = {
        "output_dir": str(output_dir_path),
        "summary_json": str(summary_json_path),
        "summary_markdown": str(summary_markdown_path),
        "fixture_reports": fixture_report_paths,
    }
    (output_dir_path / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _validate_guarded_report_payload(report: JSONObject) -> None:
    if not isinstance(report, dict):
        msg = (
            "Phase 1 guarded evaluation report must be a JSON object, got "
            f"{type(report).__name__}."
        )
        raise TypeError(msg)
    missing_sections = [
        section
        for section in ("summary", "automated_gates", "guarded_graduation_gate")
        if not isinstance(report.get(section), dict)
    ]
    if missing_sections:
        msg = (
            "Phase 1 guarded evaluation report is malformed: missing object "
            f"section(s): {', '.join(missing_sections)}."
        )
        raise ValueError(msg)
    fixtures = report.get("fixtures")
    if not isinstance(fixtures, list):
        msg = "Phase 1 guarded evaluation report is malformed: fixtures must be a list."
        raise TypeError(msg)
    for index, fixture in enumerate(fixtures):
        if isinstance(fixture, dict):
            continue
        msg = (
            "Phase 1 guarded evaluation report is malformed: fixture entry "
            f"{index} must be an object, got {type(fixture).__name__}."
        )
        raise TypeError(msg)
    if report.get("report_mode") == "canary":
        canary_gate = report.get("canary_gate")
        if not isinstance(canary_gate, dict):
            msg = (
                "Phase 1 guarded evaluation report is malformed: canary mode "
                "requires an object `canary_gate` section."
            )
            raise ValueError(msg)
        missing_canary_sections = [
            section
            for section in ("summary", "automated_gates")
            if not isinstance(canary_gate.get(section), dict)
        ]
        if missing_canary_sections:
            msg = (
                "Phase 1 guarded evaluation report is malformed: canary mode "
                "requires object `canary_gate` subsection(s): "
                f"{', '.join(missing_canary_sections)}."
            )
            raise ValueError(msg)
        if _maybe_string(canary_gate.get("verdict")) is None:
            msg = (
                "Phase 1 guarded evaluation report is malformed: canary mode "
                "requires a non-empty `canary_gate.verdict` value."
            )
            raise ValueError(msg)
