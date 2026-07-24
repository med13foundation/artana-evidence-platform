"""Deterministic V16 freeze and fail-closed repository preflight regressions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.validation.public_gold.staged_event.generalization.repair_v16 import (
    preflight as v16_preflight,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
    EXPECTED_BRANCH,
    V15_SEALED_HEAD,
    V16Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.preflight import (
    V16PreflightError,
    build_preregistration,
    build_sealed_v15_manifest,
    verify,
    verify_remote_execution_state,
)


def test_sealed_v15_manifest_is_deterministic_and_binds_the_complete_baseline() -> None:
    first = build_sealed_v15_manifest()
    second = build_sealed_v15_manifest()
    critical = first["critical_files"]

    assert first == second
    assert first["sealed_v15_head"] == V15_SEALED_HEAD
    assert first["sealed_v15_tree"] == "eac043e7ce3098b9b680e84143258bf42c113e53"
    assert first["sealed_tree_file_count"] > 2_000
    assert first["all_sealed_tree_paths_current_bytes_equal"] is True
    assert first["historical_results_rescored"] is False
    assert isinstance(critical, list)
    assert all(isinstance(item, dict) for item in critical)


def test_sealed_v15_manifest_rejects_any_non_additive_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_git = v16_preflight._git

    def changed_git(*arguments: str) -> str:
        if arguments == ("diff", "--name-status", V15_SEALED_HEAD, "--"):
            return "M\tscripts/validation/public_gold/staged_event/generalization/repair_v15/runner.py"
        return original_git(*arguments)

    monkeypatch.setattr(v16_preflight, "_git", changed_git)

    with pytest.raises(V16PreflightError, match="sealed V15 tree changed"):
        build_sealed_v15_manifest()


def test_preregistration_is_deterministic_and_freezes_scope_schema_and_full_dependency_closure() -> (
    None
):
    first = build_preregistration()
    second = build_preregistration()
    frozen = first["frozen_state"]
    execution = first["frozen_execution"]

    assert first == second
    assert (
        first["scientific_evidence_status_before_execution"] == "NOT_EMPIRICALLY_TESTED"
    )
    assert first["scientific_hypothesis"]["source_general"] is True
    assert first["scientific_hypothesis"]["shared_historical_grader_change"] is False
    assert (
        first["scientific_hypothesis"]["local_evaluator_change"]
        == "V16_UNCERTAINTY_SCOPE_OVERLAY_WITH_NON_TARGET_EXTENSION_REJECTION"
    )
    assert execution["case_order"] == list(CASE_ORDER)
    assert execution["fresh_cases_accessed"] == 0
    assert execution["graph_writes"] == 0
    assert execution["trusted_promotion"] is False
    assert execution["token_ceiling_present"] is False
    assert (
        first["acceptance"]["v16_extension_exclusivity"]
        == "Every exposed case other than uncertainty has empty participant_scope_links and no partitive_scope; any V16-only extension there is an unsupported source-semantic failure."
    )
    assert frozen["sealed_v15_head"] == V15_SEALED_HEAD
    assert frozen["scope_reference_sha256"]
    assert frozen["v16_output_schema_sha256"]
    assert frozen["runtime_dependency_roots"] == [
        "scripts/run_staged_generalization_v16_exposed.py"
    ]
    entries = frozen["runtime_dependency_manifest"]
    assert isinstance(entries, list)
    assert any(item["path"].endswith("repair_v16/runner.py") for item in entries)
    assert any(item["path"].endswith("repair_v16/contracts.py") for item in entries)


def test_preflight_refuses_untracked_runtime_dependencies_before_freeze_commit(
    tmp_path: Path,
) -> None:
    paths = _temporary_paths(tmp_path)
    v16_preflight.write_candidate(paths)

    with pytest.raises(V16PreflightError, match="runtime dependency is not tracked"):
        verify(paths, require_package_review=False)


def test_remote_gate_allows_only_expected_branch_clean_tracked_state_and_validation_debris(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)
    head = "a" * 40

    monkeypatch.setattr(
        v16_preflight,
        "_git",
        _remote_git(
            head=head,
            untracked=("validation/public_gold/bionlp_cg/raw",),
        ),
    )

    observed = verify_remote_execution_state(paths)

    assert observed == {
        "branch": EXPECTED_BRANCH,
        "local_head": head,
        "remote_head": head,
        "tracked_modification_count": 0,
        "execution_outputs_absent": True,
        "untracked_paths_preserved": ["validation/public_gold/bionlp_cg/raw"],
    }


@pytest.mark.parametrize(
    ("branch", "remote_head", "tracked_status", "message"),
    [
        ("alvaro/wrong-branch", None, "", "requires branch"),
        (EXPECTED_BRANCH, "b" * 40, "", "local and remote heads differ"),
        (EXPECTED_BRANCH, None, " M tracked.py", "tracked worktree changes"),
    ],
)
def test_remote_gate_rejects_unsafe_repository_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    branch: str,
    remote_head: str | None,
    tracked_status: str,
    message: str,
) -> None:
    monkeypatch.setattr(
        v16_preflight,
        "_git",
        _remote_git(
            head="a" * 40,
            branch=branch,
            remote_head=remote_head,
            tracked_status=tracked_status,
        ),
    )

    with pytest.raises(V16PreflightError, match=message):
        verify_remote_execution_state(_temporary_paths(tmp_path))


def test_package_review_must_bind_the_exact_preregistration_and_zero_side_effects(
    tmp_path: Path,
) -> None:
    paths = _temporary_paths(tmp_path)
    v16_preflight.write_candidate(paths)
    review = {
        "verdict": "PASS",
        "preregistration_sha256": "a" * 64,
        "fresh_cases_accessed": 1,
        "graph_writes": 0,
        "trusted_promotion": False,
    }
    paths.package_review.write_text(json.dumps(review), encoding="utf-8")

    with pytest.raises(V16PreflightError, match="binds another preregistration"):
        v16_preflight._verify_package_review(
            paths,
            {"frozen_state": {}},
        )


def test_complete_package_review_must_bind_every_reviewed_file_hash(
    tmp_path: Path,
) -> None:
    paths = _temporary_paths(tmp_path)
    preregistration = v16_preflight.write_candidate(paths)
    frozen = preregistration["frozen_state"]
    assert isinstance(frozen, dict)
    review = {
        "reviewer_id": "v16_complete_package_reviewer_independent",
        "verdict": "HARD_PASS",
        "reviewed_complete_package": True,
        "preregistration_sha256": _sha256(paths.preregistration),
        "runtime_dependency_manifest_sha256": frozen[
            "runtime_dependency_manifest_sha256"
        ],
        "sealed_v15_manifest_sha256": frozen["sealed_v15_manifest_sha256"],
        "provider_calls": 0,
        "fresh_cases_accessed": 0,
        "graph_writes": 0,
        "trusted_promotion": False,
        "reviewed_files_sha256": {},
    }
    paths.package_review.write_text(json.dumps(review), encoding="utf-8")

    with pytest.raises(V16PreflightError, match="file set is incomplete"):
        v16_preflight._verify_package_review(paths, preregistration)


def test_complete_package_review_accepts_the_exact_comprehensive_file_set(
    tmp_path: Path,
) -> None:
    paths = _temporary_paths(tmp_path)
    preregistration = v16_preflight.write_candidate(paths)
    frozen = preregistration["frozen_state"]
    assert isinstance(frozen, dict)
    reviewed_files = {
        relative: _sha256(v16_preflight.REPO / relative)
        for relative in v16_preflight._expected_reviewed_files()
    }
    review = {
        "reviewer_id": "v16_complete_package_reviewer_independent",
        "verdict": "HARD_PASS",
        "reviewed_complete_package": True,
        "preregistration_sha256": _sha256(paths.preregistration),
        "runtime_dependency_manifest_sha256": frozen[
            "runtime_dependency_manifest_sha256"
        ],
        "sealed_v15_manifest_sha256": frozen["sealed_v15_manifest_sha256"],
        "provider_calls": 0,
        "fresh_cases_accessed": 0,
        "graph_writes": 0,
        "trusted_promotion": False,
        "reviewed_files_sha256": reviewed_files,
    }
    paths.package_review.write_text(json.dumps(review), encoding="utf-8")

    v16_preflight._verify_package_review(paths, preregistration)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _temporary_paths(tmp_path: Path) -> V16Paths:
    return replace(
        DEFAULT_PATHS,
        sealed_v15_manifest=tmp_path / "sealed-v15-manifest.json",
        preregistration=tmp_path / "preregistration.json",
        package_review=tmp_path / "package-review.json",
        result=tmp_path / "result.json",
        report=tmp_path / "report.md",
        receipts=tmp_path / "receipts",
        raw_outputs=tmp_path / "raw",
        evaluations=tmp_path / "evaluations",
    )


def _remote_git(
    *,
    head: str,
    branch: str = EXPECTED_BRANCH,
    remote_head: str | None = None,
    tracked_status: str = "",
    untracked: tuple[str, ...] = (),
):
    resolved_remote = head if remote_head is None else remote_head

    def fake_git(*arguments: str) -> str:
        if arguments == ("branch", "--show-current"):
            return branch
        if arguments == ("rev-parse", "HEAD"):
            return head
        if arguments[:3] == ("ls-remote", "--heads", "origin"):
            return f"{resolved_remote}\trefs/heads/{branch}"
        if arguments == ("status", "--porcelain=v1", "--untracked-files=no"):
            return tracked_status
        if arguments == ("status", "--porcelain=v1", "--untracked-files=all"):
            values = [tracked_status] if tracked_status else []
            values.extend(f"?? {item}" for item in untracked)
            return "\n".join(values)
        raise AssertionError(f"unexpected git call: {arguments}")

    return fake_git
