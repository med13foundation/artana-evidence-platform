"""V14 deterministic freeze and fail-closed repository preflight regressions."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable, Iterator
from dataclasses import fields, replace
from pathlib import Path
from typing import cast

import pytest
from pydantic import TypeAdapter

from scripts.validation.public_gold.staged_event.generalization.repair_v13.dependency_manifest import (
    build_dependency_manifest,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.frozen_panel import (
    load_frozen_panel,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14 import (
    preflight as v14_preflight,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
    EXPECTED_BRANCH,
    REPO,
    V13_SEALED_HEAD,
    V14Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.preflight import (
    V14PreflightError,
    build_preregistration,
    build_rule_audit,
    build_sealed_v13_manifest,
    verify,
    verify_remote_execution_state,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.prompt import (
    EXPECTED_RULE_SHA256,
    ordered_cases,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.provider import (
    build_request,
)

_OBJECT = TypeAdapter(dict[str, object])
_OBJECT_LIST = TypeAdapter(list[dict[str, object]])
_STRING_OBJECT = TypeAdapter(dict[str, object])
_STRING_STRING = TypeAdapter(dict[str, str])

_HISTORICAL_CANARIES = {
    (
        "docs/validation/adjudications/"
        "2026-07-23-pmid-7966592-nested-two-lane-adjudication-v1.json"
    ),
    (
        "docs/validation/adjudications/"
        "2026-07-23-pmid-7966592-nested-two-lane-adjudication-v1.md"
    ),
    "scripts/run_staged_generalization_v12_exposed.py",
    "scripts/run_staged_generalization_v13_exposed.py",
    ("scripts/validation/public_gold/staged_event/generalization/grading/policy.py"),
    ("scripts/validation/public_gold/staged_event/generalization/repair_v12/config.py"),
    ("scripts/validation/public_gold/staged_event/generalization/repair_v13/config.py"),
    "tests/unit/test_staged_generalization_grading.py",
}
_RUNTIME_ROOT = "scripts/run_staged_generalization_v14_exposed.py"
_REQUIRED_RUNTIME_DEPENDENCIES = {
    _RUNTIME_ROOT,
    (
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v14/preflight.py"
    ),
    (
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v14/evaluation.py"
    ),
    ("scripts/validation/public_gold/staged_event/generalization/repair_v14/prompt.py"),
    (
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v13/evaluation.py"
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


def test_sealed_v13_manifest_is_deterministic_and_covers_history() -> None:
    first = build_sealed_v13_manifest()
    second = build_sealed_v13_manifest()
    entries = _OBJECT_LIST.validate_python(first["files"])
    by_path = {
        cast("str", entry["path"]): cast("str", entry["sha256"]) for entry in entries
    }

    assert first == second
    assert first["sealed_head"] == V13_SEALED_HEAD
    assert first["file_count"] == len(entries)
    assert first["all_current_bytes_equal_sealed_head"] is True
    assert _object(first["selection"]) == {
        "v12_implementation_and_artifacts": True,
        "v13_implementation_and_artifacts": True,
        "v13_freeze_commits": [
            "25d68f00ddbd1112b930574b1b9a0e32555c2100",
            V13_SEALED_HEAD,
        ],
        "shared_grader": True,
    }
    assert list(by_path) == sorted(by_path)
    assert set(by_path) >= _HISTORICAL_CANARIES
    for relative, digest in by_path.items():
        assert digest == hashlib.sha256((REPO / relative).read_bytes()).hexdigest()


def test_sealed_v13_manifest_rejects_a_current_byte_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    relative = (
        "scripts/validation/public_gold/staged_event/generalization/grading/policy.py"
    )
    sealed = b"sealed shared grader\n"
    current = tmp_path / relative
    current.parent.mkdir(parents=True)
    current.write_bytes(sealed)
    monkeypatch.setattr(v14_preflight, "REPO", tmp_path)
    monkeypatch.setattr(
        v14_preflight,
        "_git_at_head_paths",
        lambda _commit: (relative,),
    )
    monkeypatch.setattr(
        v14_preflight,
        "_git_changed_paths",
        lambda _commit: (),
    )
    monkeypatch.setattr(
        v14_preflight,
        "_git_show",
        lambda _commit, _path: sealed,
    )

    assert build_sealed_v13_manifest()["all_current_bytes_equal_sealed_head"] is True

    current.write_bytes(sealed + b"mutation")
    with pytest.raises(V14PreflightError, match="historical protected file changed"):
        build_sealed_v13_manifest()


def test_rule_audit_is_deterministic_and_freezes_only_two_bounded_changes() -> None:
    first = build_rule_audit()
    second = build_rule_audit()
    scope = _object(first["change_scope"])
    assessments = _OBJECT_LIST.validate_python(first["case_assessments"])

    assert first == second
    assert first["verdict"] == "PASS"
    assert first["source_general"] is True
    assert first["case_specific_provider_examples"] is False
    assert first["case_order"] == list(CASE_ORDER)
    assert [item["case_id"] for item in assessments] == list(CASE_ORDER)
    assert scope["prompt_changes"] == ["PARTICIPANT_OCCURRENCE_TEXT"]
    assert scope["v14_local_evaluator_changes"] == [
        "OPTIONAL_INNER_CAUSAL_AGENT_MULTIPLICITY"
    ]
    for unchanged in (
        "event_inventory",
        "entity_types",
        "mandatory_participants",
        "mandatory_links",
        "root_selection",
        "semantic_axes",
        "evidence_grounding",
        "completeness",
        "shared_grader",
    ):
        assert scope[unchanged] == "UNCHANGED"
    assert scope["bionlp_cg_projection"] == "UNCHANGED_RAW_REVIEW_ONLY"
    assert first["fresh_cases_accessed"] == 0
    assert first["provider_calls"] == 0
    assert first["graph_writes"] == 0
    assert first["trusted_promotion"] is False


def test_preregistration_and_dependency_manifest_are_deterministic(
    candidate_paths: V14Paths,
) -> None:
    first = build_preregistration(candidate_paths)
    second = build_preregistration(candidate_paths)
    frozen = _object(first["frozen_state"])
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


def test_dependency_manifest_hashes_the_complete_local_runtime_closure(
    candidate_paths: V14Paths,
) -> None:
    preregistration = build_preregistration(candidate_paths)
    frozen = _object(preregistration["frozen_state"])
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


def test_runtime_and_frozen_inputs_have_no_fresh_or_graph_write_path(
    candidate_paths: V14Paths,
) -> None:
    preregistration = build_preregistration(candidate_paths)
    frozen = _object(preregistration["frozen_state"])
    dependencies = _OBJECT_LIST.validate_python(frozen["runtime_dependency_manifest"])
    dependency_paths = {cast("str", entry["path"]).lower() for entry in dependencies}
    frozen_files = set(_STRING_STRING.validate_python(frozen["frozen_file_sha256"]))
    v14_path_fields = {field.name for field in fields(V14Paths)}

    assert not any(
        "fresh-cg" in path or "fresh_cg" in path for path in dependency_paths
    )
    assert not any(
        path.startswith("services/artana_evidence_db/") for path in dependency_paths
    )
    assert not any("/graph_client" in path for path in dependency_paths)
    assert not any("fresh" in name or "graph" in name for name in v14_path_fields)
    assert (
        candidate_paths.v13.next_fresh_preregistration.resolve().as_posix()
        not in frozen_files
    )
    assert not any("fresh" in path.lower() for path in frozen_files)
    rules = _object(preregistration["rules"])
    assert rules["exposed_cases_only"] is True
    assert rules["fresh_case_calls_allowed"] is False
    assert rules["fresh_cases_consumed"] == 0
    assert rules["graph_writes"] is False
    assert rules["trusted_graph_promotion"] is False


def test_preregistration_freezes_one_prompt_delta_and_one_local_correction(
    candidate_paths: V14Paths,
) -> None:
    preregistration = build_preregistration(candidate_paths)
    authorized = _object(preregistration["authorized_changes"])
    forbidden = _object(preregistration["forbidden_changes"])

    assert authorized == {
        "prompt_change_count": 1,
        "prompt_change": "COMPLETE_PARTICIPANT_DENOTATION_V1",
        "v14_local_evaluator_correction": (
            "ONE_ADJUDICATED_OPTIONAL_INNER_CAUSAL_AGENT_ZERO_OR_ONE"
        ),
        "evaluator_correction_is_second_prompt_hypothesis": False,
    }
    assert forbidden == {
        "event_inventory": True,
        "entity_types": True,
        "mandatory_participants_or_links": True,
        "root_selection": True,
        "semantic_axes": True,
        "evidence_grounding": True,
        "completeness": True,
        "shared_or_historical_graders": True,
        "v13_artifacts": True,
        "bionlp_cg_projection_policy": True,
    }
    acceptance = _object(preregistration["acceptance"])
    assert acceptance["optional_edge_count_allowed"] == [0, 1]
    assert acceptance["optional_edge_cannot_replace_mandatory"] is True
    assert acceptance["raw_bionlp_cg_projection_measured_separately"] is True
    assert acceptance["raw_bionlp_cg_projection_is_qualification_blocking"] is False


def test_case_membership_is_v13_identical_and_order_is_preregistered(
    candidate_paths: V14Paths,
) -> None:
    v13_cases = load_frozen_panel(candidate_paths.v13.panel)
    v14_cases = ordered_cases(candidate_paths)
    preregistration = build_preregistration(candidate_paths)
    frozen = _object(preregistration["frozen_state"])

    assert {case.case_id for case in v14_cases} == {case.case_id for case in v13_cases}
    assert tuple(case.case_id for case in v14_cases) == CASE_ORDER
    assert frozen["case_order"] == list(CASE_ORDER)
    assert CASE_ORDER.index("generalization-uncertainty") < CASE_ORDER.index(
        "generalization-explicit-nested-cause"
    )


def test_request_and_preregistration_have_no_application_token_ceiling(
    candidate_paths: V14Paths,
) -> None:
    preregistration = build_preregistration(candidate_paths)
    request = build_request(
        case_id=CASE_ORDER[0],
        provider_input="frozen provider packet",
        preregistration_sha256="0" * 64,
    )
    provider = _object(preregistration["provider"])
    request_fields = {field.name for field in fields(request)}

    assert "max_output_tokens" not in request_fields
    assert "max_total_tokens" not in request_fields
    assert provider["application_max_output_tokens"] is None
    assert provider["application_max_total_tokens"] is None
    assert provider["provider_retries"] == 0


def test_preregistration_rejects_stale_wording_review_consensus_binding(
    candidate_paths: V14Paths,
) -> None:
    review = _read_json(candidate_paths.wording_review_a)
    inputs = _object(review["review_inputs"])
    consensus = _object(inputs["four_reviewer_consensus"])
    consensus["sha256"] = "0" * 64
    inputs["four_reviewer_consensus"] = consensus
    review["review_inputs"] = inputs
    _write_json(candidate_paths.wording_review_a, review)

    with pytest.raises(
        V14PreflightError,
        match="wording review consensus binding changed",
    ):
        build_preregistration(candidate_paths)


@pytest.mark.parametrize(
    ("artifact_field", "key", "mutated_value", "message"),
    [
        (
            "sealed_v13_manifest",
            "file_count",
            -1,
            "sealed V13 manifest differs",
        ),
        ("rule_audit", "verdict", "FAIL", "rule audit differs"),
        (
            "preregistration",
            "experiment_id",
            "mutated-experiment",
            "preregistration differs",
        ),
    ],
)
def test_verify_rejects_every_mutated_frozen_control_artifact(
    candidate_paths: V14Paths,
    artifact_field: str,
    key: str,
    mutated_value: object,
    message: str,
) -> None:
    path = cast("Path", getattr(candidate_paths, artifact_field))
    value = _read_json(path)
    value[key] = mutated_value
    _write_json(path, value)

    with pytest.raises(V14PreflightError, match=message):
        verify(candidate_paths, require_package_review=False)


def test_remote_gate_accepts_only_the_exact_clean_pushed_branch(
    monkeypatch: pytest.MonkeyPatch,
    candidate_paths: V14Paths,
) -> None:
    head = "a" * 40
    monkeypatch.setattr(
        v14_preflight,
        "_git",
        _remote_git(head=head, untracked=("user-notes.txt", "validation/raw")),
    )

    observed = verify_remote_execution_state(candidate_paths)

    assert observed == {
        "branch": EXPECTED_BRANCH,
        "local_head": head,
        "remote_head": head,
        "tracked_modification_count": 0,
        "execution_outputs_absent": True,
        "untracked_paths_preserved": ["user-notes.txt", "validation/raw"],
    }


@pytest.mark.parametrize(
    ("branch", "remote_head", "tracked_status", "message"),
    [
        ("alvaro/wrong-branch", None, "", "requires branch"),
        (EXPECTED_BRANCH, "b" * 40, "", "local and remote heads differ"),
        (EXPECTED_BRANCH, None, " M tracked.py", "tracked worktree changes"),
    ],
)
def test_remote_gate_rejects_branch_remote_and_dirty_state(
    monkeypatch: pytest.MonkeyPatch,
    candidate_paths: V14Paths,
    branch: str,
    remote_head: str | None,
    tracked_status: str,
    message: str,
) -> None:
    head = "a" * 40
    monkeypatch.setattr(
        v14_preflight,
        "_git",
        _remote_git(
            head=head,
            branch=branch,
            remote_head=remote_head,
            tracked_status=tracked_status,
        ),
    )

    with pytest.raises(V14PreflightError, match=message):
        verify_remote_execution_state(candidate_paths)


def test_remote_gate_rejects_existing_execution_output(
    monkeypatch: pytest.MonkeyPatch,
    candidate_paths: V14Paths,
) -> None:
    candidate_paths.result.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(v14_preflight, "_git", _remote_git(head="a" * 40))

    with pytest.raises(V14PreflightError, match="execution output exists"):
        verify_remote_execution_state(candidate_paths)


def test_remote_gate_rejects_an_untracked_runtime_dependency(
    monkeypatch: pytest.MonkeyPatch,
    candidate_paths: V14Paths,
) -> None:
    monkeypatch.setattr(
        v14_preflight,
        "_git",
        _remote_git(head="a" * 40, untracked_required=_RUNTIME_ROOT),
    )

    with pytest.raises(V14PreflightError, match="frozen path is untracked"):
        verify_remote_execution_state(candidate_paths)


@pytest.fixture
def candidate_paths(repo_tmp_path: Path) -> V14Paths:
    paths = replace(
        DEFAULT_PATHS,
        rule_audit=repo_tmp_path / "rule-audit.json",
        wording_review_a=repo_tmp_path / "wording-review-a.json",
        wording_review_b=repo_tmp_path / "wording-review-b.json",
        sealed_v13_manifest=repo_tmp_path / "sealed-v13-manifest.json",
        preregistration=repo_tmp_path / "preregistration.json",
        package_review=repo_tmp_path / "package-review.json",
        result=repo_tmp_path / "result.json",
        report=repo_tmp_path / "report.md",
        receipts=repo_tmp_path / "receipts",
        raw_outputs=repo_tmp_path / "raw",
        evaluations=repo_tmp_path / "evaluations",
    )
    consensus_sha256 = hashlib.sha256(paths.consensus.read_bytes()).hexdigest()
    wording_review_a = {
        "verdict": "PASS",
        "rule_sha256": EXPECTED_RULE_SHA256,
        "source_general": True,
        "scope_limited_to_participant_text": True,
        "review_inputs": {
            "four_reviewer_consensus": {
                "sha256": consensus_sha256,
            }
        },
    }
    wording_review_b = {
        "verdict": "PASS",
        "rule_sha256": EXPECTED_RULE_SHA256,
        "source_general": True,
        "scope_limited_to_participant_text": True,
        "review_basis": {
            "four_reviewer_consensus_sha256": consensus_sha256,
        },
    }
    _write_json(paths.wording_review_a, wording_review_a)
    _write_json(paths.wording_review_b, wording_review_b)
    _write_json(paths.sealed_v13_manifest, build_sealed_v13_manifest())
    _write_json(paths.rule_audit, build_rule_audit(paths))
    _write_json(paths.preregistration, build_preregistration(paths))
    return paths


@pytest.fixture
def repo_tmp_path(tmp_path: Path) -> Iterator[Path]:
    path = REPO / f".pytest-v14-preflight-{tmp_path.name}"
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
    untracked: tuple[str, ...] = (),
    untracked_required: str | None = None,
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
            return "\n".join(f"?? {path}" for path in untracked)
        if arguments[:3] == ("ls-files", "--error-unmatch", "--"):
            if arguments[-1] == untracked_required:
                return ""
            return arguments[-1]
        raise AssertionError(arguments)

    return fake_git


def _read_json(path: Path) -> dict[str, object]:
    return _OBJECT.validate_json(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _object(value: object) -> dict[str, object]:
    return _STRING_OBJECT.validate_python(value)
