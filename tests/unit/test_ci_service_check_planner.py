from __future__ import annotations

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
    changed_test = "services/artana_evidence_api/tests/unit/test_deploy_runtime_regressions.py"
    plan = plan_checks(
        [changed_test],
        event_name="pull_request",
        ref="refs/pull/13/merge",
    )

    assert not plan.evidence_api
    assert not plan.graph_service
    assert not plan.full
    assert plan.targeted_test_paths == (changed_test,)


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
