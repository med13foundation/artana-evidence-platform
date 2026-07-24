"""Regression tests for the CI check planner.

The planner decides which gates run for a change.  A path it does not
recognize plans no jobs at all, so a scientific threshold or evaluator edited
under an unlisted prefix would merge with zero checks.  These tests pin the
prefixes that must never silently stop triggering.
"""

from __future__ import annotations

import pytest

from scripts.ci.plan_service_checks import plan_checks

_PULL_REQUEST = {"event_name": "pull_request", "ref": "refs/pull/1/merge"}


@pytest.mark.parametrize(
    "path",
    [
        "scripts/validation/claim_events/evaluation.py",
        "scripts/validation/claim_events/scoring.py",
        "scripts/validation/relation_feasibility/models.py",
    ],
)
def test_scientific_evaluation_paths_plan_gates(path: str) -> None:
    """Editing a scoring lane must never plan zero jobs.

    `claim_events/evaluation.py` holds the qualification floors.  Before this
    was pinned, a change lowering one of them planned no jobs and passed.
    """

    plan = plan_checks([path], **_PULL_REQUEST)

    assert plan.evidence_api is True
    assert plan.repo_control is True
    assert plan.docs_only is False


def test_service_change_plans_the_evidence_api_gate() -> None:
    plan = plan_checks(
        ["services/artana_evidence_api/document_extraction.py"],
        **_PULL_REQUEST,
    )

    assert plan.evidence_api is True
    assert plan.targeted_test_paths == ()


def test_graph_service_change_plans_the_graph_gate() -> None:
    plan = plan_checks(
        ["services/artana_evidence_db/relation_repository.py"],
        **_PULL_REQUEST,
    )

    assert plan.graph_service is True


def test_test_only_change_plans_targeted_tests_instead_of_full_gates() -> None:
    plan = plan_checks(
        ["services/artana_evidence_api/tests/unit/test_document_extraction.py"],
        **_PULL_REQUEST,
    )

    assert plan.targeted_test_paths != ()
    assert plan.evidence_api is False


def test_docs_only_change_plans_no_service_gates() -> None:
    plan = plan_checks(["docs/artana-vision-and-direction.md"], **_PULL_REQUEST)

    assert plan.docs_only is True
    assert plan.evidence_api is False
    assert plan.graph_service is False


def test_workflow_change_forces_the_full_plan() -> None:
    plan = plan_checks([".github/workflows/service-checks.yml"], **_PULL_REQUEST)

    assert plan.full is True
    assert plan.evidence_api is True
    assert plan.graph_service is True


def test_main_branch_always_runs_the_full_plan() -> None:
    plan = plan_checks(
        ["docs/artana-vision-and-direction.md"],
        event_name="push",
        ref="refs/heads/main",
    )

    assert plan.full is True


def test_unknown_path_plans_nothing_and_is_a_deliberate_default() -> None:
    """Document the fail-open default so a future reader sees the risk.

    An unrecognized path plans no gates.  That is why every scientific and
    service prefix must be enumerated explicitly.
    """

    plan = plan_checks(["some/unlisted/path.py"], **_PULL_REQUEST)

    assert plan.evidence_api is False
    assert plan.graph_service is False
    assert plan.repo_control is False
    assert plan.full is False
