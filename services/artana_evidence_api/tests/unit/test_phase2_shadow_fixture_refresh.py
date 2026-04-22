from __future__ import annotations

import json
from pathlib import Path

from artana_evidence_api.phase2_shadow_fixture_refresh import (
    Phase2ShadowFixtureRunSpec,
    Phase2ShadowFixtureSpec,
    build_fixture_bundle,
    default_phase2_shadow_fixture_specs,
    fixture_request_from_spec,
    phase2_shadow_fixture_specs_for_set,
    supplemental_phase2_shadow_fixture_specs,
)


def _compare_payload(
    *,
    baseline_run_id: str,
    checkpoint_key: str,
    target_action_type: str,
    target_step_key: str,
    target_source_key: str | None = None,
    round_number: int = 0,
) -> dict[str, object]:
    deterministic_target: dict[str, object] = {
        "target_action_type": target_action_type,
        "target_step_key": target_step_key,
    }
    if target_source_key is not None:
        deterministic_target["target_source_key"] = target_source_key
    return {
        "environment": {"pubmed_search_backend": "deterministic"},
        "baseline": {
            "run_id": baseline_run_id,
            "status": "completed",
            "telemetry": {
                "status": "available",
                "cost_usd": 0.01,
                "total_tokens": 500,
            },
            "telemetry_run_ids": [baseline_run_id, f"{baseline_run_id}:child"],
        },
        "cost_comparison": {
            "status": "available",
            "gate_within_2x_baseline": True,
        },
        "orchestrator": {
            "decision_history": {
                "decisions": [
                    {
                        "step_key": target_step_key,
                        "round_number": round_number,
                    }
                ]
            },
            "shadow_planner_timeline": {
                "checkpoints": [
                    {
                        "checkpoint_key": checkpoint_key,
                        "workspace_summary": {
                            "objective": "Fixture objective",
                            "counts": {"documents_ingested": 3},
                        },
                        "comparison": deterministic_target,
                    }
                ]
            },
        },
    }


def test_fixture_request_from_spec_builds_phase1_compare_request() -> None:
    spec = Phase2ShadowFixtureSpec(
        fixture_name="TEST",
        objective="Investigate TEST.",
        seed_terms=("TEST",),
        title="Test fixture",
        enabled_sources=("pubmed", "clinvar"),
        max_depth=2,
        max_hypotheses=20,
        runs=(Phase2ShadowFixtureRunSpec(run_id="test-run-1", checkpoint_keys=()),),
    )

    request = fixture_request_from_spec(spec)

    assert request.objective == "Investigate TEST."
    assert request.seed_terms == ("TEST",)
    assert request.sources["pubmed"] is True
    assert request.sources["clinvar"] is True
    assert request.sources["drugbank"] is False


def test_build_fixture_bundle_carries_baseline_telemetry_and_targets() -> None:
    spec = Phase2ShadowFixtureSpec(
        fixture_name="TEST",
        objective="Investigate TEST.",
        seed_terms=("TEST",),
        title="Test fixture",
        enabled_sources=("pubmed", "drugbank"),
        max_depth=2,
        max_hypotheses=20,
        runs=(
            Phase2ShadowFixtureRunSpec(
                run_id="test-run-1",
                checkpoint_keys=("after_driven_terms_ready",),
            ),
        ),
    )

    bundle = build_fixture_bundle(
        spec=spec,
        compare_payloads_by_run_id={
            "test-run-1": _compare_payload(
                baseline_run_id="baseline-1",
                checkpoint_key="after_driven_terms_ready",
                target_action_type="RUN_STRUCTURED_ENRICHMENT",
                target_source_key="drugbank",
                target_step_key="step.run_structured_enrichment.drugbank",
            ),
        },
    )

    assert bundle["fixture_name"] == "TEST"
    run = bundle["runs"][0]
    assert run["sources"] == {"pubmed": True, "drugbank": True}
    assert run["deterministic_baseline"]["run_id"] == "baseline-1"
    assert run["deterministic_baseline"]["telemetry"]["cost_usd"] == 0.01
    checkpoint = run["checkpoints"][0]
    assert checkpoint["checkpoint_key"] == "after_driven_terms_ready"
    assert checkpoint["deterministic_target"] == {
        "action_type": "RUN_STRUCTURED_ENRICHMENT",
        "round_number": 0,
        "step_key": "step.run_structured_enrichment.drugbank",
        "source_key": "drugbank",
    }


def test_build_fixture_bundle_uses_run_specific_compare_payloads() -> None:
    spec = Phase2ShadowFixtureSpec(
        fixture_name="TEST",
        objective="Investigate TEST.",
        seed_terms=("TEST",),
        title="Test fixture",
        enabled_sources=("pubmed",),
        max_depth=2,
        max_hypotheses=20,
        runs=(
            Phase2ShadowFixtureRunSpec(
                run_id="test-run-1",
                checkpoint_keys=("before_first_action",),
            ),
            Phase2ShadowFixtureRunSpec(
                run_id="test-run-2",
                checkpoint_keys=("before_terminal_stop",),
            ),
        ),
    )

    bundle = build_fixture_bundle(
        spec=spec,
        compare_payloads_by_run_id={
            "test-run-1": _compare_payload(
                baseline_run_id="baseline-1",
                checkpoint_key="before_first_action",
                target_action_type="QUERY_PUBMED",
                target_step_key="step.query_pubmed",
            ),
            "test-run-2": _compare_payload(
                baseline_run_id="baseline-2",
                checkpoint_key="before_terminal_stop",
                target_action_type="STOP",
                target_step_key="step.stop",
            ),
        },
    )

    assert bundle["runs"][0]["deterministic_baseline"]["run_id"] == "baseline-1"
    assert bundle["runs"][1]["deterministic_baseline"]["run_id"] == "baseline-2"


def test_default_phase2_fixture_specs_keep_reproducible_checkpoint_requests() -> None:
    specs_by_name = {
        spec.fixture_name: spec for spec in default_phase2_shadow_fixture_specs()
    }

    cftr_runs = {run.run_id: run.checkpoint_keys for run in specs_by_name["CFTR"].runs}
    med13_runs = {
        run.run_id: run.checkpoint_keys for run in specs_by_name["MED13"].runs
    }
    brca1_runs = {
        run.run_id: run.checkpoint_keys for run in specs_by_name["BRCA1"].runs
    }

    assert cftr_runs["cftr-run-2"] == ("after_bootstrap",)
    assert med13_runs["med13-run-2"] == ("before_terminal_stop",)
    assert brca1_runs["brca1-run-2"] == ("after_pubmed_discovery",)


def test_phase2_shadow_fixture_spec_sets_cover_objective_and_supplemental_cases() -> (
    None
):
    objective_specs = phase2_shadow_fixture_specs_for_set("objective")
    supplemental_specs = phase2_shadow_fixture_specs_for_set("supplemental")
    objective_names = [spec.fixture_name for spec in objective_specs]
    supplemental_names = [spec.fixture_name for spec in supplemental_specs]
    all_names = [
        spec.fixture_name for spec in phase2_shadow_fixture_specs_for_set("all")
    ]

    assert objective_names == ["BRCA1", "CFTR", "MED13", "PCSK9"]
    assert supplemental_names == [
        "SUPPLEMENTAL_CHASE_SELECTION",
        "SUPPLEMENTAL_CHASE_STOP",
        "SUPPLEMENTAL_BOUNDED_CHASE_CONTINUE",
        "SUPPLEMENTAL_LABEL_FILTERING",
    ]
    assert all_names == objective_names + supplemental_names
    assert supplemental_phase2_shadow_fixture_specs() == tuple(
        phase2_shadow_fixture_specs_for_set("supplemental")
    )
    supplemental_by_name = {spec.fixture_name: spec for spec in supplemental_specs}
    assert supplemental_by_name["SUPPLEMENTAL_CHASE_SELECTION"].seed_terms == (
        "CFTR",
        "cystic fibrosis",
    )
    assert supplemental_by_name["SUPPLEMENTAL_CHASE_SELECTION"].enabled_sources == (
        "pubmed",
        "clinvar",
        "drugbank",
    )
    assert supplemental_by_name["SUPPLEMENTAL_CHASE_STOP"].enabled_sources == (
        "pubmed",
        "clinvar",
        "marrvel",
        "mgi",
        "zfin",
    )
    assert supplemental_by_name["SUPPLEMENTAL_LABEL_FILTERING"].enabled_sources == (
        "pubmed",
        "clinvar",
        "drugbank",
        "alphafold",
    )
    assert supplemental_by_name[
        "SUPPLEMENTAL_BOUNDED_CHASE_CONTINUE"
    ].enabled_sources == (
        "pubmed",
        "clinvar",
        "drugbank",
        "alphafold",
    )


def test_committed_phase2_fixture_inventory_matches_default_specs() -> None:
    fixture_dir = Path(__file__).resolve().parents[1] / "fixtures" / "shadow_planner"

    for spec in default_phase2_shadow_fixture_specs():
        bundle = json.loads((fixture_dir / spec.fixture_filename).read_text())
        expected_runs = {run.run_id: run.checkpoint_keys for run in spec.runs}
        actual_runs = {
            str(run["run_id"]): tuple(
                str(checkpoint["checkpoint_key"]) for checkpoint in run["checkpoints"]
            )
            for run in bundle["runs"]
        }
        assert actual_runs == expected_runs


def test_committed_phase2_fixture_inventory_matches_supplemental_specs() -> None:
    fixture_dir = Path(__file__).resolve().parents[1] / "fixtures" / "shadow_planner"

    for spec in supplemental_phase2_shadow_fixture_specs():
        bundle = json.loads((fixture_dir / spec.fixture_filename).read_text())
        expected_runs = {run.run_id: run.checkpoint_keys for run in spec.runs}
        actual_runs = {
            str(run["run_id"]): tuple(
                str(checkpoint["checkpoint_key"]) for checkpoint in run["checkpoints"]
            )
            for run in bundle["runs"]
        }
        assert actual_runs == expected_runs


def test_build_fixture_bundle_backfills_chase_selection_from_compare_payload() -> None:
    spec = Phase2ShadowFixtureSpec(
        fixture_name="TEST",
        objective="Investigate TEST chase handling.",
        seed_terms=("TEST",),
        title="Test chase fixture",
        enabled_sources=("pubmed",),
        max_depth=2,
        max_hypotheses=20,
        runs=(
            Phase2ShadowFixtureRunSpec(
                run_id="test-run-1",
                checkpoint_keys=("after_bootstrap",),
            ),
        ),
    )

    compare_payload = _compare_payload(
        baseline_run_id="baseline-1",
        checkpoint_key="after_bootstrap",
        target_action_type="RUN_CHASE_ROUND",
        target_step_key="step.run_chase_round",
        round_number=1,
    )
    orchestrator = compare_payload["orchestrator"]
    assert isinstance(orchestrator, dict)
    shadow_planner_timeline = orchestrator["shadow_planner_timeline"]
    assert isinstance(shadow_planner_timeline, dict)
    checkpoints = shadow_planner_timeline["checkpoints"]
    assert isinstance(checkpoints, list)
    first_checkpoint = checkpoints[0]
    assert isinstance(first_checkpoint, dict)
    comparison = first_checkpoint["comparison"]
    assert isinstance(comparison, dict)
    comparison["deterministic_selected_entity_ids"] = ["entity-1"]
    comparison["deterministic_selected_labels"] = ["CDK8"]
    comparison["deterministic_stop_expected"] = False

    bundle = build_fixture_bundle(
        spec=spec,
        compare_payloads_by_run_id={"test-run-1": compare_payload},
    )

    workspace_summary = bundle["runs"][0]["checkpoints"][0]["workspace_summary"]
    assert workspace_summary["deterministic_selection"] == {
        "selected_entity_ids": ["entity-1"],
        "selected_labels": ["CDK8"],
        "stop_instead": False,
        "stop_reason": None,
        "selection_basis": (
            "Recovered deterministic chase selection from the compare payload."
        ),
    }
    assert workspace_summary["deterministic_candidate_count"] == 1
    assert workspace_summary["deterministic_threshold_met"] is True
