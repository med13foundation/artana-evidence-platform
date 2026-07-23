"""V15 deterministic freeze and fail-closed repository preflight regressions."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable, Iterator
from dataclasses import asdict, fields, replace
from pathlib import Path
from typing import cast

import pytest
from pydantic import TypeAdapter

from scripts.validation.public_gold.staged_event.generalization.repair_v13.dependency_manifest import (
    build_dependency_manifest,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.provider import (
    build_request as build_v14_request,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15 import (
    preflight as v15_preflight,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
    EXPECTED_BRANCH,
    REPO,
    V14_SEALED_HEAD,
    V15_AUTHORIZATION_HEAD,
    V15_AUTHORIZATION_SHA256,
    V15Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15.preflight import (
    V15PreflightError,
    build_preregistration,
    build_sealed_v14_manifest,
    verify,
    verify_remote_execution_state,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15.provider import (
    build_request,
)

_OBJECT = TypeAdapter(dict[str, object])
_OBJECT_LIST = TypeAdapter(list[dict[str, object]])
_STRING_STRING = TypeAdapter(dict[str, str])
_RUNTIME_ROOT = "scripts/run_staged_generalization_v15_exposed.py"
_REQUIRED_RUNTIME_DEPENDENCIES = {
    _RUNTIME_ROOT,
    (
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v15/preflight.py"
    ),
    ("scripts/validation/public_gold/staged_event/generalization/repair_v15/runner.py"),
    ("scripts/validation/public_gold/staged_event/generalization/repair_v15/prompt.py"),
    (
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v14/evaluation.py"
    ),
    (
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v13/provider_execution.py"
    ),
    (
        "scripts/validation/public_gold/staged_event/generalization/"
        "grading/evaluation.py"
    ),
}


def test_sealed_v14_manifest_is_deterministic_and_binds_the_entire_tree() -> None:
    first = build_sealed_v14_manifest()
    second = build_sealed_v14_manifest()
    critical = _OBJECT_LIST.validate_python(first["critical_files"])
    by_path = {
        cast("str", entry["path"]): cast("str", entry["sha256"]) for entry in critical
    }

    assert first == second
    assert first["sealed_v14_head"] == V14_SEALED_HEAD
    assert first["sealed_v14_tree"] == ("e511c3d4fb8a7bb09634888cc73cf816e154cf7f")
    assert cast("int", first["sealed_tree_file_count"]) > len(critical)
    assert first["all_sealed_tree_paths_current_bytes_equal"] is True
    assert first["historical_results_rescored"] is False
    evaluator_path = (
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v14/evaluation.py"
    )
    assert first["v14_evaluator_sha256"] == (
        "28a6e6f7140bb5d240b34516afe52153d76753b5d6fc30d02ab44d59092811df"
    )
    assert (
        by_path[evaluator_path]
        == hashlib.sha256((REPO / evaluator_path).read_bytes()).hexdigest()
    )


def test_sealed_v14_manifest_rejects_any_non_additive_tree_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_git = v15_preflight._git

    def changed_git(*arguments: str) -> str:
        if arguments == ("diff", "--name-status", V14_SEALED_HEAD, "--"):
            return "M\tscripts/run_staged_generalization_v14_exposed.py"
        return original_git(*arguments)

    monkeypatch.setattr(v15_preflight, "_git", changed_git)
    with pytest.raises(V15PreflightError, match="sealed V14 tree changed"):
        build_sealed_v14_manifest()


def test_offline_audit_is_deterministic_and_explicitly_non_empirical() -> None:
    first = _read_json(DEFAULT_PATHS.offline_audit)
    second = v15_preflight._verify_offline_audit(DEFAULT_PATHS)
    required = _OBJECT.validate_python(first["required_invariant_assessments"])
    assessments = _OBJECT_LIST.validate_python(first["case_assessments"])

    assert first == second
    assert hashlib.sha256(DEFAULT_PATHS.offline_audit.read_bytes()).hexdigest() == (
        "cc9d7381335cb297a34d8d1ba9d54d1eb95fd7c600fe582d70e3d56f78ed22ca"
    )
    assert first["audit_evidence_kind"] == "OFFLINE_CONTRACT_COMPATIBILITY_ONLY"
    assert first["provider_behavior_empirically_validated"] is False
    assert first["scientific_fix_already_proven"] is False
    assert first["qualification_credit"] is False
    assert first["case_order"] == list(CASE_ORDER)
    assert [item["case_id"] for item in assessments] == list(CASE_ORDER)
    assert set(required.values()) == {"PASS"}
    assert first["provider_calls"] == 0
    assert first["fresh_cases_accessed"] == 0
    assert first["graph_writes"] == 0
    assert first["trusted_promotion"] is False


def test_preregistration_and_dependency_manifest_are_deterministic(
    candidate_paths: V15Paths,
) -> None:
    first = build_preregistration(candidate_paths)
    second = build_preregistration(candidate_paths)
    frozen = _OBJECT.validate_python(first["frozen_state"])
    entries = _OBJECT_LIST.validate_python(frozen["runtime_dependency_manifest"])
    canonical = json.dumps(
        entries,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    assert first == second
    assert (
        frozen["runtime_dependency_manifest_sha256"]
        == hashlib.sha256(canonical).hexdigest()
    )
    assert frozen["runtime_dependency_roots"] == [_RUNTIME_ROOT]
    assert frozen["case_order"] == list(CASE_ORDER)
    assert frozen["sealed_v14_head"] == V14_SEALED_HEAD
    assert frozen["v15_authorization_head"] == V15_AUTHORIZATION_HEAD
    assert frozen["v15_authorization_sha256"] == V15_AUTHORIZATION_SHA256


def test_dependency_manifest_hashes_the_complete_reused_runtime_closure(
    candidate_paths: V15Paths,
) -> None:
    preregistration = build_preregistration(candidate_paths)
    frozen = _OBJECT.validate_python(preregistration["frozen_state"])
    entries = _OBJECT_LIST.validate_python(frozen["runtime_dependency_manifest"])
    by_path = {
        cast("str", entry["path"]): cast("str", entry["sha256"]) for entry in entries
    }
    rebuilt = build_dependency_manifest(REPO, (_RUNTIME_ROOT,))

    assert list(by_path) == sorted(by_path)
    assert len(by_path) == len(entries)
    assert set(by_path) >= _REQUIRED_RUNTIME_DEPENDENCIES
    assert [(item.path, item.sha256) for item in rebuilt] == list(by_path.items())
    for relative, digest in by_path.items():
        path = Path(relative)
        assert not path.is_absolute()
        assert ".." not in path.parts
        assert (REPO / path).is_file()
        assert digest == hashlib.sha256((REPO / path).read_bytes()).hexdigest()


def test_preregistration_freezes_only_the_prompt_hypothesis(
    candidate_paths: V15Paths,
) -> None:
    preregistration = build_preregistration(candidate_paths)
    authorized = _OBJECT.validate_python(preregistration["authorized_changes"])
    forbidden = _OBJECT.validate_python(preregistration["forbidden_changes"])
    hypothesis = _OBJECT.validate_python(preregistration["scientific_hypothesis"])
    acceptance = _OBJECT.validate_python(preregistration["acceptance"])

    assert preregistration["scientific_evidence_status_before_execution"] == (
        "NOT_EMPIRICALLY_TESTED"
    )
    assert hypothesis["name"] == (
        "FOCUS_CLOSURE_AND_ROLE_BEARING_OCCURRENCE_CUSTODY_V1"
    )
    assert hypothesis["source_general"] is True
    assert hypothesis["case_specific_provider_examples"] is False
    assert authorized == {
        "prompt_change_count": 1,
        "prompt_change": ("FOCUS_CLOSURE_AND_ROLE_BEARING_OCCURRENCE_CUSTODY_V1"),
        "v15_evaluator_change": None,
        "v14_evaluator_reused_byte_identical": True,
    }
    assert all(value is True for value in forbidden.values())
    assert acceptance["v14_optional_edge_policy_unchanged"] is True
    assert acceptance["raw_bionlp_cg_projection_measured_separately"] is True
    assert acceptance["raw_bionlp_cg_projection_is_qualification_blocking"] is False


def test_request_reuses_all_nonmetadata_v14_fields_and_has_no_token_ceiling(
    candidate_paths: V15Paths,
) -> None:
    preregistration = build_preregistration(candidate_paths)
    v15_request = build_request(
        case_id=CASE_ORDER[0],
        provider_input="frozen provider packet",
        preregistration_sha256="0" * 64,
    )
    v14_request = build_v14_request(
        case_id=CASE_ORDER[0],
        provider_input="frozen provider packet",
        preregistration_sha256="0" * 64,
    )
    provider = _OBJECT.validate_python(preregistration["provider"])
    request_fields = {field.name for field in fields(v15_request)}

    assert {
        field: value
        for field, value in asdict(v15_request).items()
        if field != "metadata"
    } == {
        field: value
        for field, value in asdict(v14_request).items()
        if field != "metadata"
    }
    assert "max_output_tokens" not in request_fields
    assert "max_total_tokens" not in request_fields
    assert provider["application_max_output_tokens"] is None
    assert provider["application_max_total_tokens"] is None
    assert provider["provider_retries"] == 0


def test_runtime_and_inputs_have_no_fresh_or_graph_write_path(
    candidate_paths: V15Paths,
) -> None:
    preregistration = build_preregistration(candidate_paths)
    frozen = _OBJECT.validate_python(preregistration["frozen_state"])
    dependencies = _OBJECT_LIST.validate_python(frozen["runtime_dependency_manifest"])
    dependency_paths = {cast("str", entry["path"]).lower() for entry in dependencies}
    frozen_files = set(_STRING_STRING.validate_python(frozen["frozen_file_sha256"]))
    path_fields = {field.name for field in fields(V15Paths)}
    rules = _OBJECT.validate_python(preregistration["rules"])

    assert not any(
        "fresh-cg" in path or "fresh_cg" in path for path in dependency_paths
    )
    assert not any(
        path.startswith("services/artana_evidence_db/") for path in dependency_paths
    )
    assert not any("/graph_client" in path for path in dependency_paths)
    assert not any("fresh" in name or "graph" in name for name in path_fields)
    assert not any("fresh" in path.lower() for path in frozen_files)
    assert rules["exposed_cases_only"] is True
    assert rules["fresh_case_calls_allowed"] is False
    assert rules["fresh_cases_consumed"] == 0
    assert rules["graph_writes"] is False
    assert rules["trusted_graph_promotion"] is False
    assert rules["v16_automatic_start_allowed"] is False


def test_distinct_wording_reviewer_identities_are_required(
    candidate_paths: V15Paths,
) -> None:
    review_a = _read_json(candidate_paths.wording_review_a)
    review_b = _read_json(candidate_paths.wording_review_b)
    review_b["reviewer_id"] = review_a["reviewer_id"]
    _write_json(candidate_paths.wording_review_b, review_b)

    with pytest.raises(V15PreflightError, match="wording review failed"):
        build_preregistration(candidate_paths)


def test_complete_package_review_cannot_hash_only_one_file(
    candidate_paths: V15Paths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preregistration = _read_json(candidate_paths.preregistration)
    frozen = _OBJECT.validate_python(preregistration["frozen_state"])
    _write_json(
        candidate_paths.package_review,
        {
            "reviewer_id": "v15_complete_package_reviewer_independent",
            "verdict": "HARD_PASS",
            "reviewed_complete_package": True,
            "preregistration_sha256": hashlib.sha256(
                candidate_paths.preregistration.read_bytes()
            ).hexdigest(),
            "runtime_dependency_manifest_sha256": frozen[
                "runtime_dependency_manifest_sha256"
            ],
            "reviewed_files_sha256": {
                _relative(candidate_paths.preregistration): hashlib.sha256(
                    candidate_paths.preregistration.read_bytes()
                ).hexdigest()
            },
            "provider_calls": 0,
            "fresh_cases_accessed": 0,
            "graph_writes": 0,
            "trusted_promotion": False,
        },
    )
    monkeypatch.setattr(
        v15_preflight,
        "_V15_ALLOWED_ADDITIONS",
        frozenset(
            {
                _relative(candidate_paths.preregistration),
                _relative(candidate_paths.offline_audit),
                _relative(candidate_paths.package_review),
            }
        ),
    )
    monkeypatch.setattr(v15_preflight, "_V14_CRITICAL_PATHS", ())

    with pytest.raises(V15PreflightError, match="file set is incomplete"):
        v15_preflight._verify_package_review(candidate_paths, preregistration)


@pytest.mark.parametrize(
    ("artifact_field", "key", "mutated_value", "message"),
    [
        (
            "sealed_v14_manifest",
            "sealed_tree_file_count",
            -1,
            "sealed V14 manifest differs",
        ),
        (
            "offline_audit",
            "scientific_fix_already_proven",
            True,
            "offline audit hash changed",
        ),
        (
            "preregistration",
            "experiment_id",
            "mutated-experiment",
            "preregistration differs",
        ),
    ],
)
def test_verify_rejects_every_mutated_frozen_control_artifact(
    candidate_paths: V15Paths,
    artifact_field: str,
    key: str,
    mutated_value: object,
    message: str,
) -> None:
    path = cast("Path", getattr(candidate_paths, artifact_field))
    value = _read_json(path)
    value[key] = mutated_value
    _write_json(path, value)

    with pytest.raises(V15PreflightError, match=message):
        verify(candidate_paths, require_package_review=False)


def test_remote_gate_accepts_only_the_clean_pushed_additions(
    monkeypatch: pytest.MonkeyPatch,
    candidate_paths: V15Paths,
) -> None:
    head = "a" * 40
    monkeypatch.setattr(
        v15_preflight,
        "_git",
        _remote_git(
            head=head,
            untracked=("user-notes.txt", "validation/raw"),
            additions=(
                "docs/validation/adjudications/"
                "2026-07-23-staged-generalization-v14-to-v15-"
                "focus-closure-consensus-v1.json",
            ),
        ),
    )

    observed = verify_remote_execution_state(candidate_paths)

    assert observed == {
        "branch": EXPECTED_BRANCH,
        "local_head": head,
        "remote_head": head,
        "tracked_modification_count": 0,
        "sealed_v14_diff_is_additions_only": True,
        "execution_outputs_absent": True,
        "untracked_paths_preserved": ["user-notes.txt", "validation/raw"],
    }


@pytest.mark.parametrize(
    ("branch", "remote_head", "tracked_status", "diff", "message"),
    [
        ("alvaro/wrong-branch", None, "", "", "requires branch"),
        (EXPECTED_BRANCH, "b" * 40, "", "", "local and remote heads differ"),
        (EXPECTED_BRANCH, None, " M tracked.py", "", "tracked worktree changes"),
        (
            EXPECTED_BRANCH,
            None,
            "",
            "M\tscripts/run_staged_generalization_v14_exposed.py",
            "unauthorized V15 diff",
        ),
    ],
)
def test_remote_gate_rejects_branch_remote_dirty_and_historical_change(
    monkeypatch: pytest.MonkeyPatch,
    candidate_paths: V15Paths,
    branch: str,
    remote_head: str | None,
    tracked_status: str,
    diff: str,
    message: str,
) -> None:
    head = "a" * 40
    monkeypatch.setattr(
        v15_preflight,
        "_git",
        _remote_git(
            head=head,
            branch=branch,
            remote_head=remote_head,
            tracked_status=tracked_status,
            diff=diff,
        ),
    )

    with pytest.raises(V15PreflightError, match=message):
        verify_remote_execution_state(candidate_paths)


def test_remote_gate_rejects_existing_execution_output(
    monkeypatch: pytest.MonkeyPatch,
    candidate_paths: V15Paths,
) -> None:
    candidate_paths.result.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(v15_preflight, "_git", _remote_git(head="a" * 40))

    with pytest.raises(V15PreflightError, match="execution output exists"):
        verify_remote_execution_state(candidate_paths)


@pytest.fixture
def candidate_paths(repo_tmp_path: Path) -> V15Paths:
    paths = replace(
        DEFAULT_PATHS,
        wording_review_a=repo_tmp_path / "wording-review-a.json",
        wording_review_b=repo_tmp_path / "wording-review-b.json",
        offline_audit=repo_tmp_path / "offline-audit.json",
        sealed_v14_manifest=repo_tmp_path / "sealed-v14-manifest.json",
        preregistration=repo_tmp_path / "preregistration.json",
        package_review=repo_tmp_path / "package-review.json",
        result=repo_tmp_path / "result.json",
        report=repo_tmp_path / "report.md",
        receipts=repo_tmp_path / "receipts",
        raw_outputs=repo_tmp_path / "raw",
        evaluations=repo_tmp_path / "evaluations",
    )
    shutil.copyfile(DEFAULT_PATHS.wording_review_a, paths.wording_review_a)
    shutil.copyfile(DEFAULT_PATHS.wording_review_b, paths.wording_review_b)
    shutil.copyfile(DEFAULT_PATHS.offline_audit, paths.offline_audit)
    _write_json(paths.sealed_v14_manifest, build_sealed_v14_manifest())
    _write_json(paths.preregistration, build_preregistration(paths))
    return paths


@pytest.fixture
def repo_tmp_path(tmp_path: Path) -> Iterator[Path]:
    path = REPO / f".pytest-v15-preflight-{tmp_path.name}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def _remote_git(
    *,
    head: str,
    branch: str = EXPECTED_BRANCH,
    remote_head: str | None = None,
    tracked_status: str = "",
    diff: str = "",
    additions: tuple[str, ...] = (),
    untracked: tuple[str, ...] = (),
) -> Callable[..., str]:
    resolved_remote = head if remote_head is None else remote_head
    resolved_diff = diff or "\n".join(f"A\t{path}" for path in additions)

    def fake_git(*arguments: str) -> str:
        if arguments == ("branch", "--show-current"):
            return branch
        if arguments == ("rev-parse", "HEAD"):
            return head
        if arguments[:3] == ("ls-remote", "--heads", "origin"):
            return f"{resolved_remote}\trefs/heads/{branch}"
        if arguments == ("status", "--porcelain=v1", "--untracked-files=no"):
            return tracked_status
        if arguments == ("diff", "--name-status", f"{V14_SEALED_HEAD}..HEAD"):
            return resolved_diff
        if arguments == ("status", "--porcelain=v1", "--untracked-files=all"):
            return "\n".join(f"?? {path}" for path in untracked)
        if arguments[:3] == ("ls-files", "--error-unmatch", "--"):
            return arguments[-1]
        raise AssertionError(arguments)

    return fake_git


def _read_json(path: Path) -> dict[str, object]:
    return _OBJECT.validate_json(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _relative(path: Path) -> str:
    return path.resolve().relative_to(REPO.resolve()).as_posix()
