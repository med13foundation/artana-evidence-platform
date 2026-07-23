"""Deterministic V14 preregistration and fail-closed execution preflight."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import cast

from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    write_json_atomic,
)
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    policy_sha256,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.contracts import (
    load_contract,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.dependency_manifest import (
    build_dependency_manifest,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.frozen_policy import (
    verify_v13_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
    EXPECTED_BRANCH,
    EXPERIMENT_ID,
    GLOBAL_MAX_CALLS,
    GLOBAL_MAX_COST_USD,
    MODEL,
    REASONING_EFFORT,
    REPO,
    REQUEST_TIMEOUT_SECONDS,
    V13_SEALED_HEAD,
    V14Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.prompt import (
    EXPECTED_RULE_SHA256,
    ordered_cases,
    provider_input,
    verify_rule,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.provider import (
    build_request,
    provider_format,
)

_RUNTIME_ROOTS = ("scripts/run_staged_generalization_v14_exposed.py",)
_V13_FREEZE_COMMITS = (
    "25d68f00ddbd1112b930574b1b9a0e32555c2100",
    V13_SEALED_HEAD,
)
_TEST_PATHS = (
    "tests/unit/test_staged_generalization.py",
    "tests/unit/test_staged_generalization_grading.py",
    "tests/unit/test_staged_generalization_v6.py",
    "tests/unit/test_staged_generalization_v7.py",
    "tests/unit/test_staged_generalization_v8.py",
    "tests/unit/test_staged_generalization_v9.py",
    "tests/unit/test_staged_generalization_v10_exposed.py",
    "tests/unit/test_staged_generalization_v11_exposed.py",
    "tests/unit/test_staged_generalization_v11_run2.py",
    "tests/unit/test_staged_generalization_v12.py",
    "tests/unit/test_staged_generalization_v13_dependency_manifest.py",
    "tests/unit/test_staged_generalization_v13_evaluation.py",
    "tests/unit/test_staged_generalization_v13_frozen_panel.py",
    "tests/unit/test_staged_generalization_v13_preflight.py",
    "tests/unit/test_staged_generalization_v13_provider_custody.py",
    "tests/unit/test_staged_generalization_v13_runtime.py",
    "tests/unit/test_staged_generalization_v14_evaluation.py",
    "tests/unit/test_staged_generalization_v14_prompt.py",
    "tests/unit/test_staged_generalization_v14_preflight.py",
    "tests/unit/test_staged_generalization_v14_runtime.py",
)
_REVIEW_PATH_FIELDS = (
    "span_review_a",
    "span_review_b",
    "role_review_a",
    "role_review_b",
    "wording_review_a",
    "wording_review_b",
)
_REMOTE_REF_FIELDS = 2


class V14PreflightError(RuntimeError):
    """A frozen V14 scientific, custody, or repository invariant changed."""


def build_sealed_v13_manifest() -> dict[str, object]:
    """Prove every selected V12, V13, and shared-grader byte is unchanged."""

    tracked = _git_at_head_paths(V13_SEALED_HEAD)
    v13_commit_paths = {
        path for commit in _V13_FREEZE_COMMITS for path in _git_changed_paths(commit)
    }
    selected = tuple(
        path
        for path in tracked
        if _is_historical_protected(path) or path in v13_commit_paths
    )
    if not selected:
        raise V14PreflightError("sealed V13 protected file set is empty")
    entries: list[dict[str, str]] = []
    for relative in selected:
        sealed = _git_show(V13_SEALED_HEAD, relative)
        current_path = REPO / relative
        if not current_path.is_file() or current_path.read_bytes() != sealed:
            raise V14PreflightError(f"historical protected file changed: {relative}")
        entries.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(sealed).hexdigest(),
            }
        )
    return {
        "schema_version": "artana.staged_generalization.v14_sealed_v13_manifest.v1",
        "sealed_head": V13_SEALED_HEAD,
        "selection": {
            "v12_implementation_and_artifacts": True,
            "v13_implementation_and_artifacts": True,
            "v13_freeze_commits": list(_V13_FREEZE_COMMITS),
            "shared_grader": True,
        },
        "file_count": len(entries),
        "files": entries,
        "all_current_bytes_equal_sealed_head": True,
    }


def build_rule_audit(paths: V14Paths = DEFAULT_PATHS) -> dict[str, object]:
    """Record the expected effect of the sole rule across the exposed panel."""

    rule = verify_rule(paths)
    return {
        "schema_version": "artana.staged_generalization.v14_rule_audit.v1",
        "rule_sha256": rule["rule_sha256"],
        "consensus_sha256": _sha256(paths.consensus),
        "case_order": list(CASE_ORDER),
        "case_assessments": [
            {
                "case_id": "generalization-comparison-canary",
                "expected_effect": "NONE",
                "previous_behavior_must_remain_stable": True,
            },
            {
                "case_id": "generalization-drug-sensitivity",
                "expected_effect": "NONE",
                "previous_behavior_must_remain_stable": True,
            },
            {
                "case_id": "generalization-uncertainty",
                "expected_effect": (
                    "INDEPENDENT_LEXICAL_IDENTIFIER_REMAINS_UNEXPANDED"
                ),
                "previous_behavior_must_remain_stable": True,
                "participant_boundary_canary_runs_before_target": True,
            },
            {
                "case_id": "generalization-explicit-nested-cause",
                "expected_effect": "RETAIN_REQUIRED_HEAD_AND_RESTRICTIVE_SCOPE",
                "optional_role_policy": ("ZERO_OR_ONE_SOURCE_ENTAILED_REDUNDANT_EDGE"),
            },
            {
                "case_id": "generalization-negated-association",
                "expected_effect": "NONE",
                "previous_behavior_must_remain_stable": True,
            },
            {
                "case_id": "generalization-null-statistics",
                "expected_effect": "NONE",
                "previous_behavior_must_remain_stable": True,
            },
        ],
        "change_scope": {
            "prompt_changes": ["PARTICIPANT_OCCURRENCE_TEXT"],
            "v14_local_evaluator_changes": ["OPTIONAL_INNER_CAUSAL_AGENT_MULTIPLICITY"],
            "event_inventory": "UNCHANGED",
            "entity_types": "UNCHANGED",
            "mandatory_participants": "UNCHANGED",
            "mandatory_links": "UNCHANGED",
            "root_selection": "UNCHANGED",
            "semantic_axes": "UNCHANGED",
            "evidence_grounding": "UNCHANGED",
            "completeness": "UNCHANGED",
            "shared_grader": "UNCHANGED",
            "bionlp_cg_projection": "UNCHANGED_RAW_REVIEW_ONLY",
        },
        "source_general": True,
        "case_specific_provider_examples": False,
        "fresh_cases_accessed": 0,
        "provider_calls": 0,
        "graph_writes": 0,
        "trusted_promotion": False,
        "verdict": "PASS",
    }


def build_preregistration(paths: V14Paths = DEFAULT_PATHS) -> dict[str, object]:
    """Recompute every V14 scientific, execution, and custody binding."""

    _verify_inputs(paths)
    cases = ordered_cases(paths)
    policy = verify_v13_frozen_policy(paths.v13.grading, cases=cases)
    contract = load_contract(
        paths.v13.nested_two_lane_contract,
        adjudication_path=paths.v13.nested_adjudication,
        v12_contract_path=paths.v13.v12_drug_two_lane_contract,
    )
    dependencies = tuple(
        asdict(item) for item in build_dependency_manifest(REPO, _RUNTIME_ROOTS)
    )
    dependency_sha = _canonical_sha256(dependencies)
    provider_inputs = {
        case.case_id: hashlib.sha256(
            provider_input(case.case_id, paths).encode()
        ).hexdigest()
        for case in cases
    }
    request = build_request(
        case_id=cases[0].case_id,
        provider_input=provider_input(cases[0].case_id, paths),
        preregistration_sha256="0" * 64,
    )
    request_fields = set(type(request).__dataclass_fields__)
    if "max_output_tokens" in request_fields or "max_total_tokens" in request_fields:
        raise V14PreflightError("V14 request contract contains a token ceiling")
    frozen_files = _frozen_file_hashes(paths)
    return {
        "schema_version": "artana.staged_generalization.v14_exposed_gate.v1",
        "experiment_id": EXPERIMENT_ID,
        "authorization": "PREREGISTERED_V14_EXPOSED_CASES_ONLY",
        "scientific_hypothesis": (
            "Adding the source-general independent-denotation test to the "
            "existing named-biomedical occurrence boundary will prevent "
            "headless or restrictively broadened participant spans while "
            "preserving independently referential lexical names, without "
            "changing any event, role, root, semantic, grounding, "
            "completeness, or BioNLP-CG projection rule."
        ),
        "authorized_changes": {
            "prompt_change_count": 1,
            "prompt_change": "COMPLETE_PARTICIPANT_DENOTATION_V1",
            "v14_local_evaluator_correction": (
                "ONE_ADJUDICATED_OPTIONAL_INNER_CAUSAL_AGENT_ZERO_OR_ONE"
            ),
            "evaluator_correction_is_second_prompt_hypothesis": False,
        },
        "forbidden_changes": {
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
        },
        "frozen_state": {
            "sealed_v13_head": V13_SEALED_HEAD,
            "sealed_v13_manifest_sha256": _sha256(paths.sealed_v13_manifest),
            "sealed_v13_manifest_file_count": _object(
                json.loads(paths.sealed_v13_manifest.read_text(encoding="utf-8"))
            )["file_count"],
            "case_order": list(CASE_ORDER),
            "panel_sha256": _sha256(paths.v13.panel),
            "panel_canonical_sha256": _canonical_sha256(
                json.loads(paths.v13.panel.read_text(encoding="utf-8"))
            ),
            "participant_rule_sha256": EXPECTED_RULE_SHA256,
            "consensus_sha256": _sha256(paths.consensus),
            "rule_audit_sha256": _sha256(paths.rule_audit),
            "independent_review_sha256": {
                field: _sha256(cast("Path", getattr(paths, field)))
                for field in _REVIEW_PATH_FIELDS
            },
            "nested_contract_sha256": _sha256(paths.v13.nested_two_lane_contract),
            "nested_contract_root": contract.source_lane.root_event_key,
            "grading_policy_sha256": policy_sha256(policy),
            "schema_sha256": _canonical_sha256(
                V9StagedGeneralizationOutput.model_json_schema()
            ),
            "provider_format_sha256": _canonical_sha256(provider_format()),
            "provider_input_sha256_by_case": provider_inputs,
            "runtime_dependency_roots": list(_RUNTIME_ROOTS),
            "runtime_dependency_manifest": list(dependencies),
            "runtime_dependency_manifest_sha256": dependency_sha,
            "frozen_file_sha256": frozen_files,
        },
        "provider": {
            "transport": "DIRECT_OPENAI_FOREGROUND_RESPONSES",
            "transport_implementation": "V13_REUSED_BYTE_IDENTICAL",
            "model": f"openai:{MODEL}",
            "reasoning_effort": REASONING_EFFORT,
            "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
            "background": False,
            "store": True,
            "application_max_output_tokens": None,
            "application_max_total_tokens": None,
            "exactly_one_creation_per_case": True,
            "provider_retries": 0,
            "fallback": False,
            "confirmation_retrieval_required": True,
            "input_item_retrieval_required": True,
            "rejected_attempt_custody_required": True,
            "stable_response_id_custody": True,
        },
        "operational_budget": {
            "cumulative_max_cost_usd": GLOBAL_MAX_COST_USD,
            "maximum_creation_calls": GLOBAL_MAX_CALLS,
            "check_before_each_creation": True,
            "record_usage_latency_and_cost_after_each_call": True,
            "rejected_calls_count_toward_budget": True,
            "unaccounted_rejected_call_stops_next_creation": True,
            "telemetry_affects_scientific_scoring": False,
        },
        "acceptance": {
            "all_six_source_semantic_cases_pass": True,
            "all_previously_repaired_behaviors_stable": True,
            "complete_participant_denotation_pass": True,
            "optional_edge_count_allowed": [0, 1],
            "optional_edge_cannot_replace_mandatory": True,
            "raw_bionlp_cg_projection_measured_separately": True,
            "raw_bionlp_cg_projection_is_qualification_blocking": False,
            "all_receipts_valid": True,
            "provider_retries": 0,
            "duplicate_creation_calls": 0,
        },
        "stopping_rules": {
            "sequential_fail_fast": True,
            "first_real_source_scientific_failure": True,
            "invalid_schema_custody_or_exactly_once": True,
            "operational_budget_exhaustion": True,
            "provider_outage_or_missing_secret": True,
        },
        "rules": {
            "expected_execution_branch": EXPECTED_BRANCH,
            "exposed_cases_only": True,
            "fresh_case_calls_allowed": False,
            "fresh_cases_consumed": 0,
            "graph_writes": False,
            "trusted_graph_promotion": False,
            "execution_output_paths_must_be_absent": True,
            "remote_head_must_match_pushed_branch": True,
            "tracked_worktree_must_be_clean": True,
            "unrelated_untracked_paths_preserved": True,
            "v15_automatic_start_allowed": False,
        },
        "qualification_credit": False,
    }


def write_candidate(paths: V14Paths = DEFAULT_PATHS) -> None:
    """Write deterministic control artifacts before the package is frozen."""

    for path in (
        paths.sealed_v13_manifest,
        paths.rule_audit,
        paths.preregistration,
    ):
        if path.exists():
            raise V14PreflightError(f"V14 candidate already exists: {path.name}")
    write_json_atomic(paths.sealed_v13_manifest, build_sealed_v13_manifest())
    write_json_atomic(paths.rule_audit, build_rule_audit(paths))
    write_json_atomic(paths.preregistration, build_preregistration(paths))


def verify(
    paths: V14Paths = DEFAULT_PATHS,
    *,
    remote_gate: bool = False,
    require_package_review: bool = True,
) -> dict[str, object]:
    """Recompute the freeze, then optionally verify the pushed execution head."""

    expected_manifest = build_sealed_v13_manifest()
    if _read_json(paths.sealed_v13_manifest) != expected_manifest:
        raise V14PreflightError("sealed V13 manifest differs from current bytes")
    expected_audit = build_rule_audit(paths)
    if _read_json(paths.rule_audit) != expected_audit:
        raise V14PreflightError("V14 rule audit differs from frozen state")
    expected_preregistration = build_preregistration(paths)
    if _read_json(paths.preregistration) != expected_preregistration:
        raise V14PreflightError("V14 preregistration differs from frozen state")
    review = (
        _verify_package_review(paths, expected_preregistration)
        if require_package_review
        else None
    )
    remote = verify_remote_execution_state(paths) if remote_gate else None
    return {
        "experiment_id": EXPERIMENT_ID,
        "preregistration_sha256": _sha256(paths.preregistration),
        "runtime_dependency_manifest_sha256": _object(
            expected_preregistration["frozen_state"]
        )["runtime_dependency_manifest_sha256"],
        "sealed_v13_manifest_sha256": _sha256(paths.sealed_v13_manifest),
        "package_review": review,
        "remote": remote,
    }


def verify_remote_execution_state(
    paths: V14Paths = DEFAULT_PATHS,
) -> dict[str, object]:
    """Require the exact pushed branch while preserving unrelated untracked files."""

    branch = _git("branch", "--show-current")
    if branch != EXPECTED_BRANCH:
        raise V14PreflightError(f"V14 requires branch {EXPECTED_BRANCH}")
    local = _git("rev-parse", "HEAD")
    remote = _git("ls-remote", "--heads", "origin", branch).split()
    if len(remote) != _REMOTE_REF_FIELDS or remote[0] != local:
        raise V14PreflightError("local and remote heads differ before V14")
    tracked_status = _git("status", "--porcelain=v1", "--untracked-files=no")
    if tracked_status:
        raise V14PreflightError("tracked worktree changes exist before V14")
    present = [
        _relative(path) for path in _execution_output_paths(paths) if path.exists()
    ]
    if present:
        raise V14PreflightError(f"V14 execution output exists: {present}")
    prereg = _read_json(paths.preregistration)
    frozen = _object(prereg.get("frozen_state"))
    dependencies = cast(
        "list[dict[str, str]]",
        frozen.get("runtime_dependency_manifest"),
    )
    required = {
        paths.preregistration,
        paths.package_review,
        *(REPO / item["path"] for item in dependencies),
        *(REPO / path for path in _TEST_PATHS),
        *(_frozen_input_paths(paths)),
    }
    for path in required:
        relative = _relative(path)
        if _git("ls-files", "--error-unmatch", "--", relative) != relative:
            raise V14PreflightError(f"V14 frozen path is untracked: {relative}")
    status = _git("status", "--porcelain=v1", "--untracked-files=all")
    unexpected = [
        line for line in status.splitlines() if line and not line.startswith("?? ")
    ]
    if unexpected:
        raise V14PreflightError("tracked worktree changed during remote gate")
    untracked = [line[3:] for line in status.splitlines() if line.startswith("?? ")]
    return {
        "branch": branch,
        "local_head": local,
        "remote_head": remote[0],
        "tracked_modification_count": 0,
        "execution_outputs_absent": True,
        "untracked_paths_preserved": untracked,
    }


def _verify_inputs(paths: V14Paths) -> None:
    verify_rule(paths)
    consensus = _read_json(paths.consensus)
    consensus_state = _object(consensus.get("consensus"))
    if (
        consensus_state.get("overall_verdict") != "PASS"
        or consensus_state.get("tiebreak_required") is not False
    ):
        raise V14PreflightError("independent V14 consensus is not PASS")
    frozen_reviews = _object(
        _object(consensus.get("frozen_inputs")).get("independent_reviews")
    )
    review_by_field = {
        "span_review_a": "participant_span_reviewer_a",
        "span_review_b": "participant_span_reviewer_b",
        "role_review_a": "inner_role_reviewer_a",
        "role_review_b": "inner_role_reviewer_b",
    }
    for field, key in review_by_field.items():
        review = _object(frozen_reviews.get(key))
        path = cast("Path", getattr(paths, field))
        if review.get("sha256") != _sha256(path):
            raise V14PreflightError(f"consensus review hash changed: {field}")
    consensus_sha256 = _sha256(paths.consensus)
    review_a = _read_json(paths.wording_review_a)
    review_b = _read_json(paths.wording_review_b)
    wording_reviews = (
        (
            paths.wording_review_a,
            review_a,
            _object(
                _object(review_a.get("review_inputs")).get("four_reviewer_consensus")
            ).get("sha256"),
        ),
        (
            paths.wording_review_b,
            review_b,
            _object(review_b.get("review_basis")).get("four_reviewer_consensus_sha256"),
        ),
    )
    for path, review, consensus_binding in wording_reviews:
        if (
            review.get("verdict") != "PASS"
            or review.get("rule_sha256") != EXPECTED_RULE_SHA256
            or review.get("source_general") is not True
            or review.get("scope_limited_to_participant_text") is not True
        ):
            raise V14PreflightError(f"wording review failed: {path.name}")
        if consensus_binding != consensus_sha256:
            raise V14PreflightError(
                f"wording review consensus binding changed: {path.name}"
            )
    qualification = _read_json(paths.v13.qualified_transport_result)
    if qualification.get("decision") != "FOREGROUND_TRANSPORT_QUALIFIED":
        raise V14PreflightError("frozen foreground transport is not qualified")
    manifest = _read_json(paths.sealed_v13_manifest)
    if manifest.get("all_current_bytes_equal_sealed_head") is not True:
        raise V14PreflightError("V13 sealed-byte proof is absent")
    audit = _read_json(paths.rule_audit)
    if audit.get("verdict") != "PASS":
        raise V14PreflightError("V14 rule audit is not PASS")


def _verify_package_review(
    paths: V14Paths,
    preregistration: dict[str, object],
) -> dict[str, object]:
    review = _read_json(paths.package_review)
    prereg_sha = _sha256(paths.preregistration)
    frozen = _object(preregistration.get("frozen_state"))
    if (
        review.get("verdict") != "HARD_PASS"
        or review.get("reviewed_complete_package") is not True
        or review.get("preregistration_sha256") != prereg_sha
        or review.get("runtime_dependency_manifest_sha256")
        != frozen.get("runtime_dependency_manifest_sha256")
        or review.get("provider_calls") != 0
        or review.get("fresh_cases_accessed") != 0
        or review.get("graph_writes") != 0
        or review.get("trusted_promotion") is not False
    ):
        raise V14PreflightError("complete-package review is not a hard PASS")
    reviewed = review.get("reviewed_files_sha256")
    if not isinstance(reviewed, dict) or not reviewed:
        raise V14PreflightError("complete-package review file hashes are absent")
    for relative, digest in reviewed.items():
        if (
            not isinstance(relative, str)
            or not isinstance(digest, str)
            or _sha256(REPO / relative) != digest
        ):
            raise V14PreflightError(f"complete-package review hash changed: {relative}")
    return {
        "verdict": "HARD_PASS",
        "review_sha256": _sha256(paths.package_review),
        "reviewed_file_count": len(reviewed),
    }


def _frozen_file_hashes(paths: V14Paths) -> dict[str, str]:
    return {_relative(path): _sha256(path) for path in _frozen_input_paths(paths)}


def _frozen_input_paths(paths: V14Paths) -> tuple[Path, ...]:
    grading = paths.v13.grading
    return tuple(
        sorted(
            {
                paths.v13.panel,
                paths.v13.panel_source_custody,
                paths.v13.v11_prompt,
                paths.v13.v12_focus_rule,
                paths.v13.root_rule,
                paths.v13.nested_adjudication,
                paths.v13.nested_two_lane_contract,
                paths.v13.v12_drug_adjudication,
                paths.v13.v12_drug_two_lane_contract,
                paths.v13.preregistration,
                paths.v13.result,
                paths.v13.report,
                paths.v13.qualified_transport_result,
                paths.participant_rule,
                paths.consensus,
                paths.span_review_a,
                paths.span_review_b,
                paths.role_review_a,
                paths.role_review_b,
                paths.rule_audit,
                paths.wording_review_a,
                paths.wording_review_b,
                paths.sealed_v13_manifest,
                grading.packet,
                grading.evidence,
                grading.schema,
                grading.first_review,
                grading.second_review,
                grading.tiebreaker_review,
                grading.policy,
            }
        )
    )


def _execution_output_paths(paths: V14Paths) -> tuple[Path, ...]:
    case_paths: list[Path] = []
    for case_id in CASE_ORDER:
        item = paths.case(case_id)
        case_paths.extend(
            (
                item.attempt,
                item.bundle,
                item.receipt,
                item.raw_output,
                item.evaluation,
            )
        )
    return (paths.result, paths.report, *case_paths)


def _is_historical_protected(path: str) -> bool:
    return (
        path.startswith(
            (
                "scripts/validation/public_gold/staged_event/generalization/"
                "repair_v12/",
                "scripts/validation/public_gold/staged_event/generalization/"
                "repair_v13/",
                "scripts/validation/public_gold/staged_event/generalization/grading/",
            )
        )
        or path
        in {
            "scripts/run_staged_generalization_v12_exposed.py",
            "scripts/run_staged_generalization_v13_exposed.py",
            "tests/unit/test_staged_generalization_grading.py",
        }
        or "staged-generalization-v12" in path
        or "staged-generalization-v13" in path
        or "staged_generalization_v12" in path
        or "staged_generalization_v13" in path
    )


def _git_at_head_paths(commit: str) -> tuple[str, ...]:
    value = _run_git_bytes("ls-tree", "-r", "--name-only", commit).decode()
    return tuple(sorted(line for line in value.splitlines() if line))


def _git_changed_paths(commit: str) -> tuple[str, ...]:
    value = _run_git_bytes(
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        commit,
    ).decode()
    return tuple(sorted(line for line in value.splitlines() if line))


def _git_show(commit: str, path: str) -> bytes:
    return _run_git_bytes("show", f"{commit}:{path}")


def _run_git_bytes(*arguments: str) -> bytes:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=REPO,
        check=False,
        capture_output=True,
    )
    if completed.returncode:
        raise V14PreflightError(completed.stderr.decode().strip())
    return completed.stdout


def _git(*arguments: str) -> str:
    return _run_git_bytes(*arguments).decode().strip()


def _read_json(path: Path) -> dict[str, object]:
    return _object(json.loads(path.read_text(encoding="utf-8")))


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise V14PreflightError("expected JSON object")
    return cast("dict[str, object]", value)


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError as exc:
        raise V14PreflightError(f"path escapes repository: {path}") from exc


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "V14PreflightError",
    "build_preregistration",
    "build_rule_audit",
    "build_sealed_v13_manifest",
    "verify",
    "verify_remote_execution_state",
    "write_candidate",
]
