"""Unit tests for offline Phase 2 shadow-planner evaluation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from artana_evidence_api.phase2_shadow_compare import (
    DEFAULT_PHASE2_SHADOW_FIXTURE_DIR,
    PHASE2_SHADOW_REPORT_VERSION,
    evaluate_phase2_shadow_fixture_bundle_sync,
    evaluate_phase2_shadow_fixture_directory_sync,
    load_phase2_shadow_fixture,
    load_phase2_shadow_fixture_paths,
    render_phase2_shadow_evaluation_markdown,
    write_phase2_shadow_evaluation_report,
)

_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "shadow_planner"


def _telemetry_payload() -> dict[str, object]:
    return {
        "status": "available",
        "model_terminal_count": 1,
        "prompt_tokens": 120,
        "completion_tokens": 30,
        "total_tokens": 150,
        "cost_usd": 0.0042,
        "latency_seconds": 0.25,
        "tool_call_count": 0,
    }


def _deterministic_baseline_telemetry_payload() -> dict[str, object]:
    return {
        "status": "available",
        "model_terminal_count": 2,
        "prompt_tokens": 400,
        "completion_tokens": 100,
        "total_tokens": 500,
        "cost_usd": 0.01,
        "latency_seconds": 0.5,
        "tool_call_count": 0,
    }


def _chase_action_input_from_workspace(
    workspace_summary: dict[str, object],
) -> dict[str, object]:
    deterministic_selection = workspace_summary.get("deterministic_selection")
    if not isinstance(deterministic_selection, dict):
        return {}
    return {
        "selected_entity_ids": list(
            deterministic_selection.get("selected_entity_ids", [])
        ),
        "selected_labels": list(deterministic_selection.get("selected_labels", [])),
        "selection_basis": deterministic_selection.get("selection_basis"),
    }


async def _fixture_planner(
    checkpoint_key: str,
    workspace_summary: dict[str, object],
    sources: dict[str, bool],
) -> dict[str, object]:
    del sources
    mapping = {
        "before_first_action": ("QUERY_PUBMED", "pubmed"),
        "after_pubmed_discovery": ("INGEST_AND_EXTRACT_PUBMED", "pubmed"),
        "after_pubmed_ingest_extract": ("RUN_STRUCTURED_ENRICHMENT", "clinvar"),
        "after_chase_round_1": ("RUN_CHASE_ROUND", None),
        "after_driven_terms_ready": ("RUN_STRUCTURED_ENRICHMENT", "drugbank"),
        "before_brief_generation": ("GENERATE_BRIEF", None),
        "before_terminal_stop": ("STOP", None),
    }
    if checkpoint_key == "after_bootstrap":
        action_type, source_key = _after_bootstrap_fixture_action(workspace_summary)
    else:
        action_type, source_key = mapping[checkpoint_key]
    action_input = (
        _chase_action_input_from_workspace(workspace_summary)
        if checkpoint_key in {"after_bootstrap", "after_chase_round_1"}
        and action_type == "RUN_CHASE_ROUND"
        else {}
    )
    return {
        "planner_status": "completed",
        "model_id": "gpt-5.4",
        "agent_run_id": f"agent:{checkpoint_key}",
        "prompt_version": "fixture-prompt-v1",
        "telemetry": _telemetry_payload(),
        "decision": {
            "decision_id": f"fixture:{checkpoint_key}",
            "round_number": 0,
            "action_type": action_type,
            "action_input": action_input,
            "source_key": source_key,
            "evidence_basis": "Fixture planner output.",
            "stop_reason": "fixture_stop" if action_type == "STOP" else None,
            "step_key": f"fixture.shadow.{checkpoint_key}",
            "status": "recommended",
            "qualitative_rationale": (
                "This recommendation follows the fixture checkpoint context."
            ),
            "metadata": {
                "model_id": "gpt-5.4",
                "agent_run_id": f"agent:{checkpoint_key}",
                "prompt_version": "fixture-prompt-v1",
            },
        },
    }


async def _boundary_planner(
    checkpoint_key: str,
    workspace_summary: dict[str, object],
    sources: dict[str, bool],
) -> dict[str, object]:
    del sources
    if checkpoint_key == "after_pubmed_discovery":
        action_type = "RUN_STRUCTURED_ENRICHMENT"
        source_key = "drugbank"
    elif checkpoint_key == "after_bootstrap":
        action_type, source_key = _after_bootstrap_fixture_action(workspace_summary)
    else:
        mapping = {
            "before_first_action": ("QUERY_PUBMED", "pubmed"),
            "after_pubmed_ingest_extract": ("RUN_STRUCTURED_ENRICHMENT", "clinvar"),
            "after_chase_round_1": ("RUN_CHASE_ROUND", None),
            "after_driven_terms_ready": ("RUN_STRUCTURED_ENRICHMENT", "drugbank"),
            "before_brief_generation": ("GENERATE_BRIEF", None),
            "before_terminal_stop": ("STOP", None),
        }
        action_type, source_key = mapping[checkpoint_key]
    action_input = (
        _chase_action_input_from_workspace(workspace_summary)
        if checkpoint_key in {"after_bootstrap", "after_chase_round_1"}
        and action_type == "RUN_CHASE_ROUND"
        else {}
    )
    return {
        "planner_status": "completed",
        "model_id": "gpt-5.4",
        "agent_run_id": f"agent:{checkpoint_key}",
        "prompt_version": "fixture-prompt-v1",
        "telemetry": _telemetry_payload(),
        "decision": {
            "decision_id": f"fixture:{checkpoint_key}",
            "round_number": 0,
            "action_type": action_type,
            "action_input": action_input,
            "source_key": source_key,
            "evidence_basis": "Fixture planner output.",
            "stop_reason": "fixture_stop" if action_type == "STOP" else None,
            "step_key": f"fixture.shadow.{checkpoint_key}",
            "status": "recommended",
            "qualitative_rationale": (
                "This recommendation follows the fixture checkpoint context."
            ),
            "metadata": {
                "model_id": "gpt-5.4",
                "agent_run_id": f"agent:{checkpoint_key}",
                "prompt_version": "fixture-prompt-v1",
            },
        },
    }


def _after_bootstrap_fixture_action(
    workspace_summary: dict[str, object],
) -> tuple[str, str | None]:
    deterministic_selection = workspace_summary.get("deterministic_selection")
    if isinstance(deterministic_selection, dict) and deterministic_selection.get(
        "stop_instead"
    ):
        return ("STOP", None)
    return ("RUN_CHASE_ROUND", None)


def test_phase2_shadow_fixture_bundles_load() -> None:
    fixture_names = [
        path.name for path in load_phase2_shadow_fixture_paths(_FIXTURE_DIR)
    ]

    assert DEFAULT_PHASE2_SHADOW_FIXTURE_DIR.name == "shadow_planner"
    assert fixture_names == [
        "brca1.json",
        "cftr.json",
        "med13.json",
        "pcsk9.json",
        "supplemental_bounded_chase_continue.json",
        "supplemental_chase_selection.json",
        "supplemental_chase_stop.json",
        "supplemental_label_filtering.json",
    ]


def test_phase2_shadow_compare_reports_all_fixture_runs() -> None:
    reports = []
    for fixture_path in load_phase2_shadow_fixture_paths(_FIXTURE_DIR):
        report = evaluate_phase2_shadow_fixture_bundle_sync(
            load_phase2_shadow_fixture(fixture_path),
            planner_callable=_fixture_planner,
        )
        reports.append(report)

    total_runs = sum(int(report["run_count"]) for report in reports)
    total_checkpoints = sum(int(report["total_checkpoints"]) for report in reports)

    assert total_runs == 12
    assert total_checkpoints == 14
    assert all(
        report["report_version"] == PHASE2_SHADOW_REPORT_VERSION for report in reports
    )
    assert all(report["disabled_source_violations"] == 0 for report in reports)
    assert all(report["budget_violations"] == 0 for report in reports)
    assert all(report["planner_failures"] == 0 for report in reports)
    assert all(report["invalid_recommendations"] == 0 for report in reports)
    assert all(report["fallback_recommendations"] == 0 for report in reports)
    assert all(report["unavailable_recommendations"] == 0 for report in reports)
    assert all(
        report["qualitative_rationale_present_count"] == report["total_checkpoints"]
        for report in reports
    )
    assert all(
        report["stop_matches"] <= report["summary"]["chase_checkpoint_count"]
        for report in reports
    )
    assert all(
        report["chase_action_matches"] <= report["summary"]["chase_checkpoint_count"]
        for report in reports
    )
    assert all(
        report["exact_chase_selection_matches"]
        <= report["summary"]["chase_selection_available_count"]
        for report in reports
    )
    assert all(
        report["source_matches"] == report["total_checkpoints"] for report in reports
    )
    assert all(report["summary"]["boundary_mismatches"] == 0 for report in reports)

    med13_report = next(
        report for report in reports if report["fixture_name"] == "MED13"
    )
    med13_actions = [
        checkpoint["recommended_action_type"]
        for run_report in med13_report["reports"]
        for checkpoint in run_report["checkpoint_reports"]
    ]
    assert med13_report["automated_gates"]["all_passed"] is True
    assert all(
        checkpoint["qualitative_rationale_present"] is True
        and checkpoint["used_fallback"] is False
        and checkpoint["planner_failure"] is False
        and checkpoint["invalid_recommendation"] is False
        and checkpoint["model_id"] == "gpt-5.4"
        and checkpoint["prompt_version"] == "fixture-prompt-v1"
        for run_report in med13_report["reports"]
        for checkpoint in run_report["checkpoint_reports"]
    )
    assert "GENERATE_BRIEF" in med13_actions
    assert "STOP" in med13_actions


def test_phase2_shadow_supplemental_fixture_tracks_exact_chase_selection() -> None:
    report = evaluate_phase2_shadow_fixture_bundle_sync(
        load_phase2_shadow_fixture(_FIXTURE_DIR / "supplemental_chase_selection.json"),
        planner_callable=_fixture_planner,
    )

    assert report["fixture_name"] == "SUPPLEMENTAL_CHASE_SELECTION"
    assert report["summary"]["chase_checkpoint_count"] == 1
    assert report["summary"]["chase_action_matches"] == 1
    assert report["summary"]["chase_selection_available_count"] == 1
    assert report["summary"]["exact_chase_selection_matches"] == 1
    checkpoint_report = report["reports"][0]["checkpoint_reports"][0]
    assert checkpoint_report["checkpoint_key"] == "after_bootstrap"
    assert checkpoint_report["exact_selection_match"] is True
    assert checkpoint_report["selected_entity_overlap_count"] == 3
    assert checkpoint_report["planner_only_labels"] == []
    assert checkpoint_report["deterministic_only_labels"] == []


def test_phase2_shadow_supplemental_bounded_chase_fixture_tracks_exact_selection() -> (
    None
):
    report = evaluate_phase2_shadow_fixture_bundle_sync(
        load_phase2_shadow_fixture(
            _FIXTURE_DIR / "supplemental_bounded_chase_continue.json",
        ),
        planner_callable=_fixture_planner,
    )

    assert report["fixture_name"] == "SUPPLEMENTAL_BOUNDED_CHASE_CONTINUE"
    assert report["summary"]["chase_checkpoint_count"] == 1
    assert report["summary"]["chase_action_matches"] == 1
    assert report["summary"]["chase_selection_available_count"] == 1
    assert report["summary"]["exact_chase_selection_matches"] == 1
    checkpoint_report = report["reports"][0]["checkpoint_reports"][0]
    assert checkpoint_report["checkpoint_key"] == "after_bootstrap"
    assert checkpoint_report["exact_selection_match"] is True
    assert checkpoint_report["selected_entity_overlap_count"] == 4
    assert checkpoint_report["planner_only_labels"] == []
    assert checkpoint_report["deterministic_only_labels"] == []


def test_phase2_shadow_supplemental_chase_stop_fixture_tracks_stop_match() -> None:
    report = evaluate_phase2_shadow_fixture_bundle_sync(
        load_phase2_shadow_fixture(
            _FIXTURE_DIR / "supplemental_chase_stop.json",
        ),
        planner_callable=_fixture_planner,
    )

    assert report["fixture_name"] == "SUPPLEMENTAL_CHASE_STOP"
    assert report["summary"]["chase_checkpoint_count"] == 1
    assert report["summary"]["stop_matches"] == 1
    checkpoint_report = report["reports"][0]["checkpoint_reports"][0]
    assert checkpoint_report["checkpoint_key"] == "after_bootstrap"
    assert checkpoint_report["recommended_action_type"] == "STOP"
    assert checkpoint_report["deterministic_action_type"] == "STOP"
    assert checkpoint_report["stop_match"] is True
    assert checkpoint_report["selected_entity_overlap_count"] == 0


def test_phase2_shadow_supplemental_label_fixture_surfaces_filtered_candidates() -> (
    None
):
    report = evaluate_phase2_shadow_fixture_bundle_sync(
        load_phase2_shadow_fixture(
            _FIXTURE_DIR / "supplemental_label_filtering.json",
        ),
        planner_callable=_fixture_planner,
    )

    assert report["fixture_name"] == "SUPPLEMENTAL_LABEL_FILTERING"
    checkpoint_report = report["reports"][0]["checkpoint_reports"][0]
    assert checkpoint_report["filtered_chase_candidate_count"] == 2
    assert checkpoint_report["filtered_chase_filter_reason_counts"] == {
        "generic_result_label": 1,
        "underanchored_fragment_label": 1,
    }
    assert checkpoint_report["filtered_chase_labels"] == [
        "C Terminus domain",
        "result 1",
    ]


def test_phase2_shadow_directory_report_writes_outputs(tmp_path: Path) -> None:
    report = evaluate_phase2_shadow_fixture_directory_sync(
        _FIXTURE_DIR,
        planner_callable=_fixture_planner,
    )

    assert report["fixture_count"] == 8
    assert report["run_count"] == 12
    assert report["total_checkpoints"] == 14
    assert report["automated_gates"]["minimum_fixture_coverage_met"] is True
    assert report["automated_gates"]["minimum_run_coverage_met"] is True
    assert report["automated_gates"]["all_passed"] is True
    assert report["cost_tracking"]["status"] == "available"
    assert report["cost_tracking"]["deterministic_baseline_status"] in {
        "partial",
        "available",
    }
    assert report["cost_tracking"]["planner_total_cost_usd"] == pytest.approx(0.0588)
    assert report["cost_tracking"]["planner_total_tokens"] == 2100
    assert report["manual_review"]["required_fixtures"] == [
        "BRCA1",
        "CFTR",
        "MED13",
        "PCSK9",
        "SUPPLEMENTAL_BOUNDED_CHASE_CONTINUE",
        "SUPPLEMENTAL_CHASE_SELECTION",
        "SUPPLEMENTAL_CHASE_STOP",
        "SUPPLEMENTAL_LABEL_FILTERING",
    ]
    assert report["manual_review"]["source_improvement_candidate_fixtures"] == []
    assert report["manual_review"]["closure_improvement_candidate_fixtures"] == []
    assert report["manual_review"]["boundary_fixtures"] == []
    assert report["summary"]["chase_action_matches"] == 5
    assert report["summary"]["chase_selection_available_count"] == 3
    assert report["summary"]["exact_chase_selection_matches"] == 3
    assert report["summary"]["checkpoints_with_filtered_chase_candidates"] == 1
    assert report["summary"]["filtered_chase_candidate_total"] == 2
    assert report["summary"]["planner_stopped_while_deterministic_continue_count"] == 0
    assert report["summary"]["planner_continued_while_deterministic_stop_count"] == 0

    manifest = write_phase2_shadow_evaluation_report(report, output_dir=tmp_path)
    summary_json_path = Path(str(manifest["summary_json"]))
    summary_markdown_path = Path(str(manifest["summary_markdown"]))

    assert summary_json_path.exists()
    assert summary_markdown_path.exists()
    assert Path(str(manifest["fixture_reports"]["BRCA1"])).exists()
    assert Path(str(manifest["fixture_reports"]["MED13"])).exists()

    payload = json.loads(summary_json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["run_count"] == 12
    markdown = render_phase2_shadow_evaluation_markdown(report)
    assert "Phase 2 Shadow Planner Evaluation" in markdown
    assert "Automated gates: PASS" in markdown
    assert "Chase action matches" in markdown
    assert "Exact chase selection matches" in markdown
    assert "Filtered chase candidates" in markdown
    assert "Boundary mismatches" in markdown
    assert "Source-improvement candidates" in markdown
    assert "Closure-improvement candidates" in markdown
    assert "Boundary fixtures: none" in markdown
    assert "Source-improvement candidate fixtures: none" in markdown
    assert "Closure-improvement candidate fixtures: none" in markdown
    assert "Planner total cost" in markdown
    assert "Deterministic baseline cost" in markdown
    assert "Planner stopped while deterministic would continue" in markdown
    assert "Human review is required for all fixtures" in markdown


def test_phase2_shadow_directory_tracks_boundary_only_mismatches() -> None:
    report = evaluate_phase2_shadow_fixture_directory_sync(
        _FIXTURE_DIR,
        planner_callable=_boundary_planner,
    )

    assert report["summary"]["boundary_mismatches"] == 0
    assert report["summary"]["action_matches"] == 13
    assert report["summary"]["source_matches"] == 13
    assert report["summary"]["stop_matches"] == 5
    assert report["summary"]["exact_match_expected_checkpoints"] == 14
    assert report["summary"]["exact_match_expected_action_matches"] == 13
    assert report["summary"]["exact_match_expected_source_matches"] == 13
    assert report["manual_review"]["boundary_fixtures"] == []
    assert report["manual_review"]["priority_fixtures"] == ["BRCA1"]
    assert report["cost_tracking"]["status"] == "available"

    brca1_report = next(
        fixture for fixture in report["fixtures"] if fixture["fixture_name"] == "BRCA1"
    )
    boundary_checkpoint = next(
        checkpoint
        for run_report in brca1_report["reports"]
        for checkpoint in run_report["checkpoint_reports"]
        if checkpoint["checkpoint_key"] == "after_pubmed_discovery"
    )
    assert boundary_checkpoint["deterministic_target_planner_state"] == "live"
    assert boundary_checkpoint["exact_match_expected"] is True
    assert boundary_checkpoint["boundary_mismatch"] is False
    assert boundary_checkpoint["boundary_reason"] is None


def test_phase2_shadow_directory_uses_override_baseline_telemetry_for_cost_gate() -> (
    None
):
    baseline_payloads = [_deterministic_baseline_telemetry_payload() for _ in range(8)]

    report = evaluate_phase2_shadow_fixture_directory_sync(
        _FIXTURE_DIR,
        planner_callable=_fixture_planner,
        deterministic_baseline_telemetry_payloads=baseline_payloads,
        deterministic_baseline_expected_run_count=8,
    )

    assert report["summary"]["deterministic_baseline_run_count"] == 8
    assert report["summary"]["deterministic_baseline_expected_run_count"] == 8
    assert report["summary"]["deterministic_baseline_runs_with_cost"] == 8
    assert report["summary"]["deterministic_total_cost_usd"] == pytest.approx(0.08)
    assert report["cost_tracking"]["deterministic_baseline_status"] == "available"
    assert report["cost_tracking"]["evaluated"] is True
    assert report["cost_tracking"]["gate_within_limit"] is True
    assert report["cost_tracking"]["planner_vs_deterministic_cost_ratio"] == (
        pytest.approx(0.735)
    )


def test_phase2_shadow_directory_fails_gate_when_baseline_expected_count_mismatches() -> (
    None
):
    baseline_payloads = [_deterministic_baseline_telemetry_payload()]

    report = evaluate_phase2_shadow_fixture_directory_sync(
        _FIXTURE_DIR,
        planner_callable=_fixture_planner,
        deterministic_baseline_telemetry_payloads=baseline_payloads,
        deterministic_baseline_expected_run_count=8,
    )

    assert report["summary"]["deterministic_baseline_run_count"] == 1
    assert report["summary"]["deterministic_baseline_expected_run_count"] == 8
    assert (
        report["automated_gates"]["deterministic_baseline_expected_count_met"] is False
    )
    assert report["automated_gates"]["all_passed"] is False


def test_phase2_shadow_directory_reports_malformed_fixture_as_failed(
    tmp_path: Path,
) -> None:
    (tmp_path / "bad.json").write_text("[]\n", encoding="utf-8")

    report = evaluate_phase2_shadow_fixture_directory_sync(
        tmp_path,
        planner_callable=_fixture_planner,
    )

    assert report["fixture_count"] == 1
    assert report["summary"]["malformed_fixture_errors"] == 1
    assert report["automated_gates"]["no_malformed_fixture_entries"] is False
    assert report["automated_gates"]["all_passed"] is False
    fixture_report = report["fixtures"][0]
    assert fixture_report["fixture_name"] == "BAD"
    assert fixture_report["fixture_status"] == "failed"
    assert fixture_report["fixture_error"]["type"] == "Phase2MalformedFixtureError"
    checkpoint_report = fixture_report["reports"][0]["checkpoint_reports"][0]
    assert checkpoint_report["malformed_fixture_error"] is True
    assert checkpoint_report["error"]["type"] == "Phase2MalformedFixtureError"


def test_phase2_shadow_bundle_reports_non_dict_run_and_checkpoint_entries() -> None:
    fixture_bundle = {
        "fixture_name": "MALFORMED_ENTRIES",
        "runs": [
            "not-a-run",
            {
                "run_id": "malformed-checkpoint-run",
                "objective": "Investigate malformed checkpoint handling.",
                "sources": {"pubmed": True},
                "checkpoints": ["not-a-checkpoint"],
            },
        ],
    }

    report = evaluate_phase2_shadow_fixture_bundle_sync(
        fixture_bundle,
        planner_callable=_fixture_planner,
    )

    assert report["run_count"] == 2
    assert report["summary"]["malformed_fixture_errors"] == 2
    assert report["automated_gates"]["no_malformed_fixture_entries"] is False
    assert report["automated_gates"]["all_passed"] is False
    first_error = report["reports"][0]["checkpoint_reports"][0]["error"]
    second_error = report["reports"][1]["checkpoint_reports"][0]["error"]
    assert first_error["type"] == "MalformedRunEntry"
    assert "run entry must be an object" in first_error["message"]
    assert second_error["type"] == "MalformedCheckpointEntry"
    assert "checkpoint entry must be an object" in second_error["message"]


def test_phase2_shadow_bundle_tracks_chase_divergence_directions() -> None:
    fixture_bundle = {
        "fixture_name": "CHASE_DIVERGENCE",
        "runs": [
            {
                "run_id": "run-stop-early",
                "objective": "Investigate a case where the planner should stop early.",
                "sources": {"pubmed": True},
                "checkpoints": [
                    {
                        "checkpoint_key": "after_bootstrap",
                        "workspace_summary": {
                            "objective": (
                                "Investigate a case where the planner should stop early."
                            ),
                            "deterministic_selection": {
                                "selected_entity_ids": ["entity-1"],
                                "selected_labels": ["CDK8"],
                                "stop_instead": False,
                                "stop_reason": None,
                                "selection_basis": "Deterministic baseline continues.",
                            },
                        },
                        "deterministic_target": {
                            "action_type": "RUN_CHASE_ROUND",
                            "source_key": None,
                            "round_number": 1,
                            "step_key": "fixture.after_bootstrap.run_chase_round",
                        },
                    }
                ],
            },
            {
                "run_id": "run-continue-past-stop",
                "objective": (
                    "Investigate a case where the planner keeps chasing past the stop."
                ),
                "sources": {"pubmed": True},
                "checkpoints": [
                    {
                        "checkpoint_key": "after_bootstrap",
                        "workspace_summary": {
                            "objective": (
                                "Investigate a case where the planner keeps chasing "
                                "past the stop."
                            ),
                            "deterministic_selection": {
                                "selected_entity_ids": [],
                                "selected_labels": [],
                                "stop_instead": True,
                                "stop_reason": "threshold_not_met",
                                "selection_basis": (
                                    "Deterministic baseline stops below threshold."
                                ),
                            },
                        },
                        "deterministic_target": {
                            "action_type": "STOP",
                            "source_key": None,
                            "round_number": 1,
                            "step_key": "fixture.after_bootstrap.stop",
                        },
                    }
                ],
            },
        ],
    }

    async def _divergence_planner(
        checkpoint_key: str,
        workspace_summary: dict[str, object],
        sources: dict[str, bool],
    ) -> dict[str, object]:
        del checkpoint_key, sources
        objective = str(workspace_summary.get("objective", ""))
        if "stop early" in objective:
            return {
                "planner_status": "completed",
                "model_id": "gpt-5.4",
                "agent_run_id": "agent:stop-early",
                "prompt_version": "fixture-prompt-v1",
                "telemetry": _telemetry_payload(),
                "decision": {
                    "decision_id": "fixture:stop-early",
                    "round_number": 1,
                    "action_type": "STOP",
                    "action_input": {},
                    "source_key": None,
                    "evidence_basis": "The candidate set looks too weak to continue.",
                    "stop_reason": "low_incremental_value",
                    "step_key": "fixture.shadow.after_bootstrap.stop",
                    "status": "recommended",
                    "qualitative_rationale": (
                        "Stop because the remaining lead does not justify another round."
                    ),
                    "metadata": {},
                },
            }
        return {
            "planner_status": "completed",
            "model_id": "gpt-5.4",
            "agent_run_id": "agent:continue",
            "prompt_version": "fixture-prompt-v1",
            "telemetry": _telemetry_payload(),
            "decision": {
                "decision_id": "fixture:continue",
                "round_number": 1,
                "action_type": "RUN_CHASE_ROUND",
                "action_input": {
                    "selected_entity_ids": ["entity-9"],
                    "selected_labels": ["MED13L"],
                    "selection_basis": "Take one more bounded chase step.",
                },
                "source_key": None,
                "evidence_basis": "One more lead still looks worthwhile.",
                "stop_reason": None,
                "step_key": "fixture.shadow.after_bootstrap.run_chase_round",
                "status": "recommended",
                "qualitative_rationale": (
                    "Continue with one bounded lead because the remaining candidate is still informative."
                ),
                "metadata": {},
            },
        }

    report = evaluate_phase2_shadow_fixture_bundle_sync(
        fixture_bundle,
        planner_callable=_divergence_planner,
    )

    assert report["summary"]["chase_checkpoint_count"] == 2
    assert report["summary"]["chase_action_matches"] == 0
    assert report["summary"]["stop_matches"] == 0
    assert report["summary"]["chase_selection_available_count"] == 1
    assert report["summary"]["exact_chase_selection_matches"] == 0
    assert report["summary"]["planner_conservative_stops"] == 1
    assert report["summary"]["planner_stopped_while_deterministic_continue_count"] == 1
    assert report["summary"]["planner_continued_when_threshold_stop_count"] == 1
    assert report["summary"]["planner_continued_while_deterministic_stop_count"] == 1

    checkpoint_reports = [
        checkpoint
        for run_report in report["reports"]
        for checkpoint in run_report["checkpoint_reports"]
    ]
    stop_early_checkpoint = next(
        checkpoint
        for checkpoint in checkpoint_reports
        if checkpoint["recommended_action_type"] == "STOP"
    )
    continue_checkpoint = next(
        checkpoint
        for checkpoint in checkpoint_reports
        if checkpoint["recommended_action_type"] == "RUN_CHASE_ROUND"
    )
    assert stop_early_checkpoint["planner_stopped_while_deterministic_continue"] is True
    assert stop_early_checkpoint["exact_selection_match"] is False
    assert continue_checkpoint["planner_continued_while_deterministic_stop"] is True
    assert continue_checkpoint["chase_selection_available"] is False


def test_phase2_shadow_directory_treats_zero_cost_planner_telemetry_as_unavailable() -> (
    None
):
    async def _zero_cost_planner(
        checkpoint_key: str,
        workspace_summary: dict[str, object],
        sources: dict[str, bool],
    ) -> dict[str, object]:
        result = await _fixture_planner(
            checkpoint_key,
            workspace_summary,
            sources,
        )
        telemetry_payload = result.get("telemetry")
        assert isinstance(telemetry_payload, dict)
        telemetry = dict(telemetry_payload)
        telemetry["cost_usd"] = 0.0
        result["telemetry"] = telemetry
        return result

    report = evaluate_phase2_shadow_fixture_directory_sync(
        _FIXTURE_DIR,
        planner_callable=_zero_cost_planner,
    )

    assert report["cost_tracking"]["status"] == "unavailable"
    assert report["cost_tracking"]["evaluated"] is False
    assert report["cost_tracking"]["gate_within_limit"] is None
    assert report["cost_tracking"]["planner_total_cost_usd"] is None
    assert report["cost_tracking"]["zero_cost_with_tokens_checkpoints"] == 14
    assert "reported zero USD cost throughout" in report["cost_tracking"]["notes"]


def test_phase2_shadow_directory_notes_when_baseline_cost_fields_are_missing() -> None:
    report = evaluate_phase2_shadow_fixture_directory_sync(
        _FIXTURE_DIR,
        planner_callable=_fixture_planner,
    )

    assert report["summary"]["deterministic_baseline_run_count"] == 12
    assert report["summary"]["deterministic_baseline_expected_run_count"] == 12
    assert report["summary"]["deterministic_baseline_runs_with_cost"] == 0
    assert "baseline cost fields are still missing" in report["cost_tracking"]["notes"]


def test_phase2_shadow_directory_counts_invalid_and_unavailable_outputs() -> None:
    async def _problem_planner(
        checkpoint_key: str,
        workspace_summary: dict[str, object],
        sources: dict[str, bool],
    ) -> dict[str, object]:
        del workspace_summary, sources
        if checkpoint_key == "before_first_action":
            return {
                "planner_status": "invalid",
                "used_fallback": True,
                "validation_error": "action_not_live",
                "decision": {
                    "decision_id": "fixture:invalid",
                    "round_number": 0,
                    "action_type": "QUERY_PUBMED",
                    "action_input": {},
                    "source_key": "pubmed",
                    "evidence_basis": "Invalid planner output fixture.",
                    "stop_reason": None,
                    "step_key": "fixture.shadow.invalid",
                    "status": "recommended",
                    "qualitative_rationale": "The planner returned an invalid choice.",
                    "fallback_reason": "action_not_live",
                    "metadata": {},
                },
            }
        return {
            "planner_status": "unavailable",
            "used_fallback": True,
            "decision": {
                "decision_id": "fixture:unavailable",
                "round_number": 0,
                "action_type": "STOP",
                "action_input": {},
                "source_key": None,
                "evidence_basis": "Planner unavailable fixture.",
                "stop_reason": "planner_unavailable",
                "step_key": "fixture.shadow.unavailable",
                "status": "recommended",
                "qualitative_rationale": "Stop because the planner is unavailable.",
                "fallback_reason": "shadow_planner_unavailable",
                "metadata": {},
            },
        }

    report = evaluate_phase2_shadow_fixture_directory_sync(
        _FIXTURE_DIR,
        planner_callable=_problem_planner,
    )

    assert report["summary"]["invalid_recommendations"] >= 1
    assert report["summary"]["fallback_recommendations"] >= 2
    assert report["summary"]["unavailable_recommendations"] >= 1
    assert report["summary"]["planner_failures"] >= 1
    assert report["automated_gates"]["no_invalid_recommendations"] is False
    assert (
        report["automated_gates"]["no_fallback_or_unavailable_recommendations"] is False
    )


def test_phase2_shadow_fixture_counts_disabled_source_violations() -> None:
    async def _disabled_source_planner(
        checkpoint_key: str,
        workspace_summary: dict[str, object],
        sources: dict[str, bool],
    ) -> dict[str, object]:
        del checkpoint_key, workspace_summary, sources
        return {
            "planner_status": "completed",
            "used_fallback": True,
            "decision": {
                "decision_id": "fixture:disabled-source",
                "round_number": 0,
                "action_type": "RUN_STRUCTURED_ENRICHMENT",
                "action_input": {},
                "source_key": "clinvar",
                "evidence_basis": "Disabled source fixture.",
                "stop_reason": None,
                "step_key": "fixture.shadow.disabled_source",
                "status": "recommended",
                "qualitative_rationale": (
                    "The planner tried to use a structured source that is disabled."
                ),
                "fallback_reason": "source_disabled",
                "metadata": {},
            },
        }

    fixture_bundle = {
        "fixture_name": "DISABLED_SOURCE",
        "runs": [
            {
                "run_id": "disabled-source-run-1",
                "objective": "Investigate disabled sources.",
                "sources": {"pubmed": True, "clinvar": False},
                "checkpoints": [
                    {
                        "checkpoint_key": "after_pubmed_ingest_extract",
                        "workspace_summary": {
                            "objective": "Investigate disabled sources.",
                        },
                        "deterministic_target": {
                            "action_type": "RUN_STRUCTURED_ENRICHMENT",
                            "source_key": "clinvar",
                            "round_number": 0,
                            "step_key": "fixture.disabled.after_pubmed_ingest_extract",
                        },
                    }
                ],
            }
        ],
    }

    report = evaluate_phase2_shadow_fixture_bundle_sync(
        fixture_bundle,
        planner_callable=_disabled_source_planner,
    )

    assert report["disabled_source_violations"] == 1
    assert report["fallback_recommendations"] == 1
    assert report["automated_gates"]["no_disabled_source_violations"] is False


def test_phase2_shadow_directory_exposes_canonical_source_taxonomy() -> None:
    async def _taxonomy_planner(
        checkpoint_key: str,
        workspace_summary: dict[str, object],
        sources: dict[str, bool],
    ) -> dict[str, object]:
        del checkpoint_key, workspace_summary, sources
        return {
            "planner_status": "completed",
            "model_id": "gpt-5.4",
            "agent_run_id": "agent:taxonomy",
            "prompt_version": "fixture-prompt-v1",
            "telemetry": _telemetry_payload(),
            "decision": {
                "decision_id": "fixture:taxonomy",
                "round_number": 0,
                "action_type": "QUERY_PUBMED",
                "action_input": {},
                "source_key": "pubmed",
                "evidence_basis": "Taxonomy fixture.",
                "stop_reason": None,
                "step_key": "fixture.shadow.taxonomy",
                "status": "recommended",
                "qualitative_rationale": (
                    "Start with literature because the run still needs grounded evidence."
                ),
                "metadata": {
                    "model_id": "gpt-5.4",
                    "agent_run_id": "agent:taxonomy",
                    "prompt_version": "fixture-prompt-v1",
                },
            },
        }

    fixture_bundle = {
        "fixture_name": "SOURCE_TAXONOMY",
        "runs": [
            {
                "run_id": "taxonomy-run-1",
                "objective": "Investigate taxonomy handling.",
                "sources": {
                    "pubmed": True,
                    "pdf": True,
                    "text": True,
                    "clinvar": True,
                    "uniprot": True,
                    "hgnc": True,
                },
                "checkpoints": [
                    {
                        "checkpoint_key": "before_first_action",
                        "workspace_summary": {
                            "objective": "Investigate taxonomy handling.",
                        },
                        "deterministic_target": {
                            "action_type": "QUERY_PUBMED",
                            "source_key": "pubmed",
                            "round_number": 0,
                            "step_key": "fixture.taxonomy.before_first_action",
                        },
                    }
                ],
            }
        ],
    }

    report = evaluate_phase2_shadow_fixture_bundle_sync(
        fixture_bundle,
        planner_callable=_taxonomy_planner,
    )

    assert report["source_taxonomy"] == {
        "live_evidence": ["pubmed", "clinvar"],
        "context_only": ["pdf", "text"],
        "reserved": ["uniprot", "hgnc"],
        "grounding": [],
    }
    run_report = report["reports"][0]
    checkpoint_report = run_report["checkpoint_reports"][0]
    assert run_report["source_taxonomy"] == report["source_taxonomy"]
    assert checkpoint_report["source_taxonomy"] == report["source_taxonomy"]
    assert checkpoint_report["recommended_source_taxonomy"] == "live_evidence"
    assert checkpoint_report["deterministic_source_taxonomy"] == "live_evidence"


def test_phase2_shadow_directory_tracks_objective_source_improvement_candidates(
    tmp_path: Path,
) -> None:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = fixture_dir / "brca1_source_choice.json"
    fixture_path.write_text(
        json.dumps(
            {
                "fixture_name": "BRCA1_SOURCE_CHOICE",
                "runs": [
                    {
                        "run_id": "brca1-source-choice-run-1",
                        "objective": "Investigate BRCA1 and PARP inhibitor response.",
                        "sources": {
                            "pubmed": True,
                            "clinvar": True,
                            "drugbank": True,
                            "clinical_trials": True,
                        },
                        "checkpoints": [
                            {
                                "checkpoint_key": "after_pubmed_ingest_extract",
                                "workspace_summary": {
                                    "objective": (
                                        "Investigate BRCA1 and PARP inhibitor response."
                                    ),
                                    "objective_routing_hints": {
                                        "objective_tags": ["drug_mechanism"],
                                        "preferred_structured_sources": [
                                            "drugbank",
                                            "clinical_trials",
                                            "clinvar",
                                        ],
                                        "preferred_pending_structured_sources": [
                                            "drugbank",
                                            "clinical_trials",
                                            "clinvar",
                                        ],
                                        "summary": (
                                            "The objective emphasizes therapy or "
                                            "inhibitor questions, so drug and target "
                                            "mechanism sources should lead the "
                                            "remaining structured follow-up."
                                        ),
                                    },
                                },
                                "deterministic_target": {
                                    "action_type": "RUN_STRUCTURED_ENRICHMENT",
                                    "source_key": "clinvar",
                                    "round_number": 0,
                                    "step_key": (
                                        "fixture.after_pubmed_ingest_extract.clinvar"
                                    ),
                                },
                            }
                        ],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    async def _objective_source_planner(
        checkpoint_key: str,
        workspace_summary: dict[str, object],
        sources: dict[str, bool],
    ) -> dict[str, object]:
        del checkpoint_key, workspace_summary, sources
        return {
            "planner_status": "completed",
            "model_id": "gpt-5.4",
            "agent_run_id": "agent:after_pubmed_ingest_extract",
            "prompt_version": "fixture-prompt-v1",
            "telemetry": _telemetry_payload(),
            "decision": {
                "decision_id": "fixture:after_pubmed_ingest_extract",
                "round_number": 0,
                "action_type": "RUN_STRUCTURED_ENRICHMENT",
                "action_input": {},
                "source_key": "drugbank",
                "evidence_basis": "Drug mechanism evidence should lead next.",
                "stop_reason": None,
                "step_key": "fixture.shadow.after_pubmed_ingest_extract",
                "status": "recommended",
                "qualitative_rationale": (
                    "Use DrugBank because the objective is about inhibitor response "
                    "and the routing hints prioritize drug and target mechanism evidence."
                ),
                "metadata": {
                    "model_id": "gpt-5.4",
                    "agent_run_id": "agent:after_pubmed_ingest_extract",
                    "prompt_version": "fixture-prompt-v1",
                },
            },
        }

    report = evaluate_phase2_shadow_fixture_directory_sync(
        fixture_dir,
        planner_callable=_objective_source_planner,
    )

    assert report["summary"]["source_matches"] == 0
    assert report["summary"]["source_improvement_candidates"] == 1
    assert report["manual_review"]["priority_fixtures"] == []
    assert report["manual_review"]["source_improvement_candidate_fixtures"] == [
        "BRCA1_SOURCE_CHOICE"
    ]


def test_phase2_shadow_directory_tracks_closure_improvement_candidates(
    tmp_path: Path,
) -> None:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = fixture_dir / "cftr_closure_ready.json"
    fixture_path.write_text(
        json.dumps(
            {
                "fixture_name": "CFTR_CLOSURE_READY",
                "runs": [
                    {
                        "run_id": "cftr-closure-run-1",
                        "objective": "Investigate CFTR and cystic fibrosis.",
                        "sources": {
                            "pubmed": True,
                            "clinvar": True,
                            "drugbank": True,
                        },
                        "checkpoints": [
                            {
                                "checkpoint_key": "after_bootstrap",
                                "workspace_summary": {
                                    "objective": "Investigate CFTR and cystic fibrosis.",
                                    "counts": {
                                        "documents_ingested": 10,
                                        "proposal_count": 36,
                                        "pending_question_count": 0,
                                        "evidence_gap_count": 0,
                                        "contradiction_count": 0,
                                        "error_count": 0,
                                    },
                                    "planner_constraints": {
                                        "live_action_types": [
                                            "RUN_CHASE_ROUND",
                                            "GENERATE_BRIEF",
                                        ],
                                        "source_required_action_types": [],
                                        "control_action_types_without_source_key": [
                                            "RUN_CHASE_ROUND",
                                            "GENERATE_BRIEF",
                                        ],
                                        "pubmed_source_key": "pubmed",
                                        "pubmed_ingest_pending": False,
                                        "structured_enrichment_source_keys": [
                                            "clinvar",
                                            "drugbank",
                                        ],
                                        "pending_structured_enrichment_source_keys": [],
                                    },
                                    "prior_decisions": [
                                        {
                                            "action_type": "RUN_BOOTSTRAP",
                                            "status": "completed",
                                        }
                                    ],
                                },
                                "deterministic_target": {
                                    "action_type": "RUN_CHASE_ROUND",
                                    "source_key": None,
                                    "round_number": 1,
                                    "step_key": (
                                        "fixture.after_bootstrap.run_chase_round"
                                    ),
                                },
                            }
                        ],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    async def _closure_planner(
        checkpoint_key: str,
        workspace_summary: dict[str, object],
        sources: dict[str, bool],
    ) -> dict[str, object]:
        del checkpoint_key, workspace_summary, sources
        return {
            "planner_status": "completed",
            "model_id": "gpt-5.4",
            "agent_run_id": "agent:after_bootstrap",
            "prompt_version": "fixture-prompt-v1",
            "telemetry": _telemetry_payload(),
            "decision": {
                "decision_id": "fixture:after_bootstrap",
                "round_number": 1,
                "action_type": "GENERATE_BRIEF",
                "action_input": {},
                "source_key": None,
                "evidence_basis": (
                    "The workspace is already ready to move from retrieval to synthesis."
                ),
                "stop_reason": None,
                "step_key": "fixture.shadow.after_bootstrap",
                "status": "recommended",
                "qualitative_rationale": (
                    "Generate the brief because grounded evidence is already present "
                    "and there are no remaining questions, gaps, contradictions, or "
                    "pending structured sources."
                ),
                "metadata": {
                    "model_id": "gpt-5.4",
                    "agent_run_id": "agent:after_bootstrap",
                    "prompt_version": "fixture-prompt-v1",
                },
            },
        }

    report = evaluate_phase2_shadow_fixture_directory_sync(
        fixture_dir,
        planner_callable=_closure_planner,
    )

    assert report["summary"]["action_matches"] == 0
    assert report["summary"]["closure_improvement_candidates"] == 1
    assert report["manual_review"]["priority_fixtures"] == []
    assert report["manual_review"]["closure_improvement_candidate_fixtures"] == [
        "CFTR_CLOSURE_READY"
    ]


def test_phase2_shadow_bundle_uses_deterministic_baseline_cost_when_present() -> None:
    fixture_bundle = load_phase2_shadow_fixture(_FIXTURE_DIR / "med13.json")
    runs = fixture_bundle["runs"]
    assert isinstance(runs, list)
    for run_payload in runs:
        assert isinstance(run_payload, dict)
        run_payload["deterministic_baseline_telemetry"] = (
            _deterministic_baseline_telemetry_payload()
        )

    report = evaluate_phase2_shadow_fixture_bundle_sync(
        fixture_bundle,
        planner_callable=_fixture_planner,
    )

    assert report["cost_tracking"]["status"] == "available"
    assert report["cost_tracking"]["deterministic_baseline_status"] == "available"
    assert report["cost_tracking"]["evaluated"] is True
    assert report["cost_tracking"]["deterministic_total_cost_usd"] == pytest.approx(
        0.02,
    )
    assert report["cost_tracking"]["planner_total_cost_usd"] == pytest.approx(0.0126)
    assert report["cost_tracking"][
        "planner_vs_deterministic_cost_ratio"
    ] == pytest.approx(
        0.63,
    )
    assert report["cost_tracking"]["gate_within_limit"] is True
