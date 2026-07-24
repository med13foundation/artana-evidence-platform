"""Regression tests for V17's local frozen-package preflight."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.validation.public_gold.staged_event.generalization.repair_v17 import (
    preflight as v17_preflight,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
    EXPECTED_BRANCH,
    V16_SEALED_HEAD,
    V17Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.preflight import (
    V17PreflightError,
    build_preregistration,
    build_sealed_v16_manifest,
    verify,
    verify_remote_execution_state,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.prompt import (
    EXPECTED_RULE,
)


def test_sealed_v16_manifest_is_deterministic_and_binds_the_complete_baseline() -> None:
    first = build_sealed_v16_manifest()
    second = build_sealed_v16_manifest()
    critical = first["critical_files"]

    assert first == second
    assert first["sealed_v16_head"] == V16_SEALED_HEAD
    assert first["sealed_v16_tree"] == "472ed6b1c01270fdfa3e59e799b11dd14fa8bf49"
    file_count = first["sealed_tree_file_count"]
    assert isinstance(file_count, int)
    assert file_count > 2_000
    assert first["all_sealed_tree_paths_current_bytes_equal"] is True
    assert first["historical_results_rescored"] is False
    assert isinstance(critical, list)
    assert all(isinstance(item, dict) for item in critical)


def test_sealed_v16_manifest_rejects_a_historical_modification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_sealed_v16_change_is_rejected(
        monkeypatch,
        "M\tscripts/validation/public_gold/staged_event/generalization/repair_v16/runner.py",
    )


def test_sealed_v16_manifest_rejects_an_unenumerated_v17_addition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_sealed_v16_change_is_rejected(
        monkeypatch,
        "A\tscripts/validation/public_gold/staged_event/generalization/repair_v17/extra.py",
    )


def _assert_sealed_v16_change_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    changed_line: str,
) -> None:
    original_git = v17_preflight._git

    def changed_git(*arguments: str) -> str:
        if arguments == ("diff", "--name-status", V16_SEALED_HEAD, "--"):
            return changed_line
        return original_git(*arguments)

    monkeypatch.setattr(v17_preflight, "_git", changed_git)

    with pytest.raises(V17PreflightError, match="sealed V16 tree changed"):
        build_sealed_v16_manifest()


def test_preregistration_is_deterministic_and_freezes_the_v17_boundary(
    tmp_path: Path,
) -> None:
    paths = _temporary_paths(tmp_path)
    first = v17_preflight.write_candidate(paths)
    second = build_preregistration(paths)
    frozen = first["frozen_state"]
    execution = first["frozen_execution"]
    hypothesis = first["scientific_hypothesis"]
    assert isinstance(frozen, dict)
    assert isinstance(execution, dict)
    assert isinstance(hypothesis, dict)

    assert first == second
    assert (
        first["scientific_evidence_status_before_execution"] == "NOT_EMPIRICALLY_TESTED"
    )
    assert hypothesis["source_general"] is True
    assert hypothesis["shared_historical_grader_change"] is False
    assert hypothesis["name"] == "INLINE_VERSUS_ANAPHORIC_SCOPE_BOUNDARY_V1"
    assert execution["case_order"] == list(CASE_ORDER)
    assert execution["fresh_cases_accessed"] == 0
    assert execution["graph_writes"] == 0
    assert execution["trusted_promotion"] is False
    assert execution["token_ceiling_present"] is False
    assert frozen["sealed_v16_head"] == V16_SEALED_HEAD
    assert frozen["inline_versus_anaphoric_scope_tiebreak_sha256"]
    assert frozen["v16_output_schema_sha256"]
    assert frozen["runtime_dependency_roots"] == [
        "scripts/run_staged_generalization_v17_exposed.py"
    ]
    entries = frozen["runtime_dependency_manifest"]
    assert isinstance(entries, list)
    dependency_paths = {
        item["path"]
        for item in entries
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    assert any(path.endswith("repair_v17/preflight.py") for path in dependency_paths)
    assert any(path.endswith("repair_v16/evaluation.py") for path in dependency_paths)


def test_source_adjudication_rejects_a_changed_inline_scope_boundary(
    tmp_path: Path,
) -> None:
    changed = json.loads(DEFAULT_PATHS.source_tiebreak.read_text(encoding="utf-8"))
    findings = changed["adjudicated_findings"]
    assert isinstance(findings, dict)
    findings["comparison_inline_scope"] = "OPTIONAL"
    source_tiebreak = tmp_path / "adjudication.json"
    source_tiebreak.write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(V17PreflightError, match="comparison_inline_scope"):
        v17_preflight._verify_source_adjudication(
            replace(DEFAULT_PATHS, source_tiebreak=source_tiebreak)
        )


def test_preflight_refuses_an_untracked_runtime_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)
    v17_preflight.write_candidate(paths)
    original_is_tracked = v17_preflight._is_tracked

    def untracked_launcher(relative: str) -> bool:
        if relative == "scripts/run_staged_generalization_v17_exposed.py":
            return False
        return original_is_tracked(relative)

    monkeypatch.setattr(v17_preflight, "_is_tracked", untracked_launcher)

    with pytest.raises(V17PreflightError, match="runtime dependency is not tracked"):
        verify(paths, require_package_review=False)


def test_remote_gate_allows_only_expected_branch_clean_tracked_state_and_validation_debris(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)
    head = "a" * 40

    monkeypatch.setattr(
        v17_preflight,
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


def test_remote_gate_rejects_nonvalidation_untracked_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        v17_preflight,
        "_git",
        _remote_git(head="a" * 40, untracked=("scratch/preflight.txt",)),
    )

    with pytest.raises(V17PreflightError, match="unrelated untracked worktree"):
        verify_remote_execution_state(_temporary_paths(tmp_path))


def test_remote_gate_rejects_preexisting_execution_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)
    paths.result.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(v17_preflight, "_git", _remote_git(head="a" * 40))

    with pytest.raises(V17PreflightError, match="execution output exists"):
        verify_remote_execution_state(paths)


def test_remote_gate_rejects_an_absent_remote_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _remote_git(head="a" * 40)

    def absent_remote(*arguments: str) -> str:
        if arguments[:3] == ("ls-remote", "--heads", "origin"):
            return ""
        return baseline(*arguments)

    monkeypatch.setattr(v17_preflight, "_git", absent_remote)

    with pytest.raises(V17PreflightError, match="remote branch is absent"):
        verify_remote_execution_state(_temporary_paths(tmp_path))


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
        v17_preflight,
        "_git",
        _remote_git(
            head="a" * 40,
            branch=branch,
            remote_head=remote_head,
            tracked_status=tracked_status,
        ),
    )

    with pytest.raises(V17PreflightError, match=message):
        verify_remote_execution_state(_temporary_paths(tmp_path))


def test_package_review_must_bind_the_exact_preregistration_and_zero_side_effects(
    tmp_path: Path,
) -> None:
    paths = _temporary_paths(tmp_path)
    v17_preflight.write_candidate(paths)
    review = {
        "verdict": "HARD_PASS",
        "preregistration_sha256": "a" * 64,
        "fresh_cases_accessed": 1,
        "graph_writes": 0,
        "trusted_promotion": False,
    }
    paths.package_review.write_text(json.dumps(review), encoding="utf-8")

    with pytest.raises(V17PreflightError, match="binds another preregistration"):
        v17_preflight._verify_package_review(paths, {"frozen_state": {}})


def test_complete_package_review_binds_the_v17_and_preserved_v16_file_sets() -> None:
    reviewed = v17_preflight._expected_reviewed_files()

    assert (
        "scripts/validation/public_gold/staged_event/generalization/repair_v17/preflight.py"
        in reviewed
    )
    assert (
        "docs/validation/reviews/"
        "2026-07-23-staged-generalization-v16-post-run-independent-"
        "classification-v1.json" in reviewed
    )
    assert (
        "docs/validation/adjudications/"
        "2026-07-24-staged-generalization-v17-inline-versus-anaphoric-"
        "scope-tiebreak-v1.json" in reviewed
    )
    assert v17_preflight._V17_PACKAGE_REVIEW not in reviewed


def _temporary_paths(tmp_path: Path) -> V17Paths:
    inline_scope_rule = tmp_path / "inline-scope-rule.md"
    inline_scope_rule.write_text(EXPECTED_RULE, encoding="utf-8")
    source_tiebreak = tmp_path / "source-tiebreak.json"
    source_tiebreak.write_bytes(DEFAULT_PATHS.source_tiebreak.read_bytes())
    return replace(
        DEFAULT_PATHS,
        inline_scope_rule=inline_scope_rule,
        source_tiebreak=source_tiebreak,
        sealed_v16_manifest=tmp_path / "sealed-v16-manifest.json",
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
) -> Callable[..., str]:
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
