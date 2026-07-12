from __future__ import annotations

import pytest

from scripts.ci.plan_service_checks import emit_github_outputs, plan_checks


def test_docs_only_pr_skips_service_gates() -> None:
    plan = plan_checks(
        ["README.md", "docs/user-guide/01-getting-started.md"],
        event_name="pull_request",
        ref="refs/pull/12/merge",
    )

    assert plan.docs_only
    assert not plan.evidence_api
    assert not plan.graph_service
    assert not plan.repo_control
    assert not plan.full
    assert plan.targeted_test_paths == ()


def test_unit_test_only_pr_runs_targeted_tests() -> None:
    changed_test = (
        "services/artana_evidence_api/tests/unit/test_deploy_runtime_regressions.py"
    )
    plan = plan_checks(
        [changed_test],
        event_name="pull_request",
        ref="refs/pull/13/merge",
    )

    assert not plan.evidence_api
    assert not plan.graph_service
    assert not plan.full
    assert plan.targeted_test_paths == (changed_test,)


def test_agent_output_guard_test_change_runs_static_registry_gate() -> None:
    changed_test = (
        "services/artana_evidence_api/tests/unit/"
        "test_agent_output_schema_registry.py"
    )

    plan = plan_checks(
        [changed_test],
        event_name="pull_request",
        ref="refs/pull/13/merge",
    )

    assert plan.evidence_api
    assert not plan.graph_service
    assert plan.repo_control
    assert not plan.full
    assert plan.targeted_test_paths == ()


def test_evidence_api_code_pr_runs_evidence_api_gate_only() -> None:
    plan = plan_checks(
        ["services/artana_evidence_api/research_init_runtime.py"],
        event_name="pull_request",
        ref="refs/pull/14/merge",
    )

    assert plan.evidence_api
    assert not plan.graph_service
    assert not plan.full
    assert plan.targeted_test_paths == ()


def test_evidence_selection_gate_runners_run_evidence_api_gate() -> None:
    for changed_file in (
        "scripts/run_evidence_selection_expert_study_gate.py",
        "scripts/run_evidence_selection_review_calibration_gate.py",
    ):
        plan = plan_checks(
            [changed_file],
            event_name="pull_request",
            ref="refs/pull/14/merge",
        )

        assert plan.evidence_api
        assert not plan.graph_service
        assert not plan.full
        assert plan.targeted_test_paths == ()


def test_evidence_selection_semantic_baseline_script_runs_evidence_api_gate() -> None:
    plan = plan_checks(
        ["scripts/generate_evidence_selection_semantic_baseline.py"],
        event_name="pull_request",
        ref="refs/pull/14/merge",
    )

    assert plan.evidence_api
    assert not plan.graph_service
    assert not plan.repo_control
    assert not plan.full
    assert plan.targeted_test_paths == ()


def test_evidence_selection_semantic_agent_script_runs_evidence_api_gate() -> None:
    plan = plan_checks(
        ["scripts/run_evidence_selection_semantic_agent_evaluation.py"],
        event_name="pull_request",
        ref="refs/pull/14/merge",
    )

    assert plan.evidence_api
    assert not plan.graph_service
    assert not plan.repo_control
    assert not plan.full
    assert plan.targeted_test_paths == ()


@pytest.mark.parametrize(
    "report_path",
    [
        "docs/validation/reports/pr-semantic-pr2-agent-selector-evaluation.json",
        "docs/validation/reports/pr-semantic-pr2-agent-selector-evaluation.md",
    ],
)
def test_evidence_selection_semantic_agent_reports_run_evidence_api_gate(
    report_path: str,
) -> None:
    plan = plan_checks(
        [report_path],
        event_name="pull_request",
        ref="refs/pull/14/merge",
    )

    assert plan.evidence_api
    assert not plan.graph_service
    assert not plan.repo_control
    assert not plan.full
    assert plan.targeted_test_paths == ()


def test_evidence_selection_validation_fixtures_run_evidence_api_gate() -> None:
    plan = plan_checks(
        [
            "scripts/validation/evidence_selection/fixtures/review_ranking_shadow_seed_v1.json"
        ],
        event_name="pull_request",
        ref="refs/pull/14/merge",
    )

    assert plan.evidence_api
    assert not plan.graph_service
    assert not plan.repo_control
    assert not plan.full
    assert plan.targeted_test_paths == ()


def test_semantic_baseline_reports_run_evidence_api_gate() -> None:
    for changed_file in (
        "docs/validation/reports/2026-07-11-pr-semantic-pr1-failure-corpus-baseline.json",
        "docs/validation/reports/2026-07-11-pr-semantic-pr1-failure-corpus-baseline.md",
    ):
        plan = plan_checks(
            [changed_file],
            event_name="pull_request",
            ref="refs/pull/14/merge",
        )

        assert plan.evidence_api
        assert not plan.graph_service
        assert not plan.repo_control
        assert not plan.full


def test_evidence_api_builder_script_pr_runs_evidence_api_gate() -> None:
    plan = plan_checks(
        ["scripts/build_evidence_selection_expert_study_bundle.py"],
        event_name="pull_request",
        ref="refs/pull/141/merge",
    )

    assert plan.evidence_api
    assert not plan.graph_service
    assert not plan.repo_control
    assert not plan.full
    assert plan.targeted_test_paths == ()


def test_evidence_api_source_export_script_pr_runs_evidence_api_gate() -> None:
    plan = plan_checks(
        ["scripts/build_evidence_selection_source_exports.py"],
        event_name="pull_request",
        ref="refs/pull/145/merge",
    )

    assert plan.evidence_api
    assert not plan.graph_service
    assert not plan.repo_control
    assert not plan.full
    assert plan.targeted_test_paths == ()


def test_evidence_api_shadow_review_packet_script_pr_runs_evidence_api_gate() -> None:
    plan = plan_checks(
        ["scripts/build_evidence_selection_shadow_review_packet.py"],
        event_name="pull_request",
        ref="refs/pull/147/merge",
    )

    assert plan.evidence_api
    assert not plan.graph_service
    assert not plan.repo_control
    assert not plan.full
    assert plan.targeted_test_paths == ()


def test_evidence_api_shadow_review_source_input_script_pr_runs_evidence_api_gate() -> (
    None
):
    plan = plan_checks(
        ["scripts/build_evidence_selection_shadow_review_source_inputs.py"],
        event_name="pull_request",
        ref="refs/pull/148/merge",
    )

    assert plan.evidence_api
    assert not plan.graph_service
    assert not plan.repo_control
    assert not plan.full
    assert plan.targeted_test_paths == ()


def test_evidence_api_shadow_review_study_pipeline_script_pr_runs_evidence_api_gate() -> (
    None
):
    plan = plan_checks(
        ["scripts/build_evidence_selection_shadow_review_study_artifacts.py"],
        event_name="pull_request",
        ref="refs/pull/149/merge",
    )

    assert plan.evidence_api
    assert not plan.graph_service
    assert not plan.repo_control
    assert not plan.full
    assert plan.targeted_test_paths == ()


def test_evidence_api_shadow_review_study_batch_script_pr_runs_evidence_api_gate() -> (
    None
):
    plan = plan_checks(
        ["scripts/build_evidence_selection_shadow_review_study_batch.py"],
        event_name="pull_request",
        ref="refs/pull/150/merge",
    )

    assert plan.evidence_api
    assert not plan.graph_service
    assert not plan.repo_control
    assert not plan.full
    assert plan.targeted_test_paths == ()


def test_evidence_api_shadow_review_study_batch_manifest_script_pr_runs_evidence_api_gate() -> (
    None
):
    plan = plan_checks(
        ["scripts/build_evidence_selection_shadow_review_study_batch_manifest.py"],
        event_name="pull_request",
        ref="refs/pull/153/merge",
    )

    assert plan.evidence_api
    assert not plan.graph_service
    assert not plan.repo_control
    assert not plan.full
    assert plan.targeted_test_paths == ()


def test_graph_service_code_pr_runs_graph_gate_only() -> None:
    plan = plan_checks(
        ["services/artana_evidence_db/governance.py"],
        event_name="pull_request",
        ref="refs/pull/15/merge",
    )

    assert not plan.evidence_api
    assert plan.graph_service
    assert not plan.full


def test_ci_planner_change_runs_repo_control_checks() -> None:
    plan = plan_checks(
        ["scripts/ci/plan_service_checks.py"],
        event_name="pull_request",
        ref="refs/pull/18/merge",
    )

    assert not plan.evidence_api
    assert not plan.graph_service
    assert plan.repo_control
    assert not plan.full


def test_agent_output_validator_change_runs_evidence_and_repo_control_gates() -> None:
    plan = plan_checks(
        ["scripts/ci/validate_agent_output_boundaries.py"],
        event_name="pull_request",
        ref="refs/pull/18/merge",
    )

    assert plan.evidence_api
    assert not plan.graph_service
    assert plan.repo_control
    assert not plan.full


def test_relation_feasibility_quality_code_runs_evidence_api_and_repo_control() -> None:
    plan = plan_checks(
        ["scripts/validation/relation_feasibility/scoring.py"],
        event_name="pull_request",
        ref="refs/pull/19/merge",
    )

    assert plan.evidence_api
    assert not plan.graph_service
    assert plan.repo_control
    assert not plan.full
    assert plan.targeted_test_paths == ()


def test_workflow_or_shared_config_pr_uses_full_gate() -> None:
    for changed_file in (
        ".github/workflows/evidence-api-service-checks.yml",
        "pyproject.toml",
    ):
        plan = plan_checks(
            [changed_file],
            event_name="pull_request",
            ref="refs/pull/16/merge",
        )

        assert plan.evidence_api
        assert plan.graph_service
        assert plan.repo_control
        assert plan.full


def test_push_to_main_uses_full_gate_even_for_docs() -> None:
    plan = plan_checks(
        ["docs/architecture/current-system.md"],
        event_name="push",
        ref="refs/heads/main",
    )

    assert plan.evidence_api
    assert plan.graph_service
    assert plan.repo_control
    assert plan.full


def test_github_output_shape_is_yaml_friendly() -> None:
    plan = plan_checks(
        ["tests/unit/test_control_files.py"],
        event_name="pull_request",
        ref="refs/pull/17/merge",
    )

    assert emit_github_outputs(plan).splitlines() == [
        "docs_only=false",
        "evidence_api=false",
        "graph_service=false",
        "repo_control=false",
        "full=false",
        "targeted_tests=true",
        "targeted_test_paths=tests/unit/test_control_files.py",
    ]
