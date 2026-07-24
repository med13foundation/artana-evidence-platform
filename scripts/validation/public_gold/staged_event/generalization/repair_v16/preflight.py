"""Deterministic V16 preregistration and fail-closed execution preflight."""

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
from scripts.validation.public_gold.staged_event.generalization.repair_v13.contracts import (
    load_contract,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.dependency_manifest import (
    build_dependency_manifest,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.frozen_policy import (
    verify_v13_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.config import (
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
    V15_SEALED_HEAD,
    V16Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.contracts import (
    V16StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.prompt import (
    ordered_cases,
    provider_input,
    verify_rule,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.provider import (
    build_request,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.reference_policy import (
    UNCERTAINTY_SCOPE_REFERENCE,
    reference_sha256,
)

_RUNTIME_ROOTS = ("scripts/run_staged_generalization_v16_exposed.py",)
_UNTRACKED_STATUS_PREFIX = "?? "
_V16_PACKAGE_REVIEW = (
    "docs/validation/reviews/"
    "2026-07-23-staged-generalization-v16-complete-package-review-v1.json"
)
_V15_SEALED_TREE = "eac043e7ce3098b9b680e84143258bf42c113e53"
_V15_CLASSIFICATION = (
    "docs/validation/reviews/"
    "2026-07-23-staged-generalization-v15-post-run-independent-classification-v1.json"
)
_V15_CLASSIFICATION_SHA256 = (
    "f5b33eb4227cff238d285181af2ed0ee68875e674857b4bec6a417763669e57e"
)
_V15_CRITICAL_PATHS = (
    _V15_CLASSIFICATION,
    "docs/validation/results/2026-07-23-staged-generalization-v15-exposed-run-v1.json",
    "docs/validation/reports/2026-07-23-staged-generalization-v15-exposed-run-v1-final.md",
    "docs/validation/reports/2026-07-23-staged-generalization-v15-quota-safe-stop-v1.json",
    "scripts/validation/public_gold/staged_event/generalization/grading/agreement.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/evaluation.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/policy.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v14/evaluation.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v15/config.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v15/preflight.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v15/prompt.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v15/provider.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v15/runner.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v15/terminal.py",
    "tests/unit/test_staged_generalization_v15_preflight.py",
    "tests/unit/test_staged_generalization_v15_prompt.py",
    "tests/unit/test_staged_generalization_v15_provider.py",
    "tests/unit/test_staged_generalization_v15_runtime.py",
)
_V16_ALLOWED_ADDITIONS = frozenset(
    {
        "docs/validation/adjudications/"
        "2026-07-23-staged-generalization-v16-source-scope-tiebreak-v1.json",
        "docs/validation/manifests/"
        "2026-07-23-staged-generalization-v16-sealed-v15-manifest-v1.json",
        "docs/validation/preregistrations/"
        "2026-07-23-staged-generalization-v16-exposed-run-v1.json",
        "docs/validation/prompts/"
        "2026-07-23-staged-generalization-v16-participant-scope-and-partitive.md",
        _V16_PACKAGE_REVIEW,
        "docs/validation/reviews/"
        "2026-07-23-staged-generalization-v16-minimal-schema-review-v1.json",
        "scripts/run_staged_generalization_v16_exposed.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v16/__init__.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v16/config.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v16/contracts.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v16/evaluation.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v16/preflight.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v16/prompt.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v16/provider.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v16/reference_policy.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v16/reporting.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v16/runner.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v16/terminal.py",
        "tests/unit/test_staged_generalization_v16_contracts.py",
        "tests/unit/test_staged_generalization_v16_evaluation.py",
        "tests/unit/test_staged_generalization_v16_preflight.py",
        "tests/unit/test_staged_generalization_v16_prompt.py",
        "tests/unit/test_staged_generalization_v16_provider.py",
        "tests/unit/test_staged_generalization_v16_runtime.py",
    }
)


class V16PreflightError(RuntimeError):
    """A frozen V16 scientific, custody, or repository invariant changed."""


def build_sealed_v15_manifest() -> dict[str, object]:
    """Prove V15 and every earlier tracked file remain byte-identical."""

    tree = _git("rev-parse", f"{V15_SEALED_HEAD}^{{tree}}")
    if tree != _V15_SEALED_TREE:
        raise V16PreflightError("sealed V15 tree identity changed")
    sealed_paths = _git_at_head_paths(V15_SEALED_HEAD)
    if not sealed_paths:
        raise V16PreflightError("sealed V15 tree is empty")
    for line in _git("diff", "--name-status", V15_SEALED_HEAD, "--").splitlines():
        status, _, relative = line.partition("\t")
        if status != "A" or relative not in _V16_ALLOWED_ADDITIONS:
            raise V16PreflightError(f"sealed V15 tree changed: {line}")
    critical = []
    for relative in _V15_CRITICAL_PATHS:
        expected = hashlib.sha256(_git_show(V15_SEALED_HEAD, relative)).hexdigest()
        observed = _sha256(REPO / relative)
        if observed != expected:
            raise V16PreflightError(f"sealed V15 critical file changed: {relative}")
        critical.append({"path": relative, "sha256": expected})
    if _critical_sha(critical, _V15_CLASSIFICATION) != _V15_CLASSIFICATION_SHA256:
        raise V16PreflightError("sealed V15 post-run classification hash changed")
    return {
        "schema_version": "artana.staged_generalization.v16_sealed_v15_manifest.v1",
        "sealed_v15_head": V15_SEALED_HEAD,
        "sealed_v15_tree": tree,
        "sealed_tree_file_count": len(sealed_paths),
        "critical_file_count": len(critical),
        "critical_files": critical,
        "v15_post_run_classification_sha256": _critical_sha(
            critical,
            _V15_CLASSIFICATION,
        ),
        "all_sealed_tree_paths_current_bytes_equal": True,
        "historical_results_rescored": False,
    }


def build_preregistration(paths: V16Paths = DEFAULT_PATHS) -> dict[str, object]:
    """Recompute every V16 scientific, execution, and custody binding."""

    _verify_source_adjudications(paths)
    rule = verify_rule(paths)
    cases = ordered_cases(paths)
    policy = verify_v13_frozen_policy(paths.v15.v14.v13.grading, cases=cases)
    load_contract(
        paths.v15.v14.v13.nested_two_lane_contract,
        adjudication_path=paths.v15.v14.v13.nested_adjudication,
        v12_contract_path=paths.v15.v14.v13.v12_drug_two_lane_contract,
    )
    uncertainty = next(
        item for item in cases if item.case_id == "generalization-uncertainty"
    )
    UNCERTAINTY_SCOPE_REFERENCE.verify(uncertainty)
    dependencies = tuple(
        asdict(item) for item in build_dependency_manifest(REPO, _RUNTIME_ROOTS)
    )
    provider_inputs = {
        case.case_id: hashlib.sha256(
            provider_input(case.case_id, paths).encode()
        ).hexdigest()
        for case in cases
    }
    first_input = provider_input(cases[0].case_id, paths)
    request = build_request(
        case_id=cases[0].case_id,
        provider_input=first_input,
        preregistration_sha256="0" * 64,
    )
    if hasattr(request, "max_output_tokens") or hasattr(request, "max_total_tokens"):
        raise V16PreflightError("V16 request contract contains a token ceiling")
    request_value = asdict(request)
    return {
        "schema_version": "artana.staged_generalization.v16_exposed_gate.v1",
        "experiment_id": EXPERIMENT_ID,
        "authorization": "PREREGISTERED_V16_EXPOSED_CASES_ONLY",
        "scientific_evidence_status_before_execution": "NOT_EMPIRICALLY_TESTED",
        "scientific_hypothesis": {
            "name": "PARTICIPANT_SCOPE_AND_PARTITIVE_REPRESENTATION_V1",
            "statement": (
                "When an explicit source condition narrows the referent set of a "
                "participant inherited by a focused event, an occurrence-bound "
                "participant scope link and any explicit partitive qualifier "
                "preserve source semantics without forcing a direct event argument "
                "or inventing a detection event."
            ),
            "source_general": True,
            "provider_prompt_change": "V16_PARTICIPANT_SCOPE_AND_PARTITIVE_ONLY",
            "schema_change": "V16_LOCAL_PARTICIPANT_SCOPE_AND_PARTITIVE_ONLY",
            "local_evaluator_change": "V16_UNCERTAINTY_SCOPE_OVERLAY_WITH_NON_TARGET_EXTENSION_REJECTION",
            "shared_historical_grader_change": False,
            "BioNLP_CG_projection_change": False,
        },
        "frozen_execution": {
            "case_order": list(CASE_ORDER),
            "canary_case_id": CASE_ORDER[0],
            "exposed_cases_only": True,
            "fresh_cases_accessed": 0,
            "graph_writes": 0,
            "trusted_promotion": False,
            "provider_retries_allowed": 0,
            "provider_fallback_allowed": False,
            "global_max_calls": GLOBAL_MAX_CALLS,
            "global_max_cost_usd": GLOBAL_MAX_COST_USD,
            "token_ceiling_present": False,
            "tokens_or_cost_affect_scientific_scoring": False,
            "fail_fast": True,
            "execution_order_hashes": provider_inputs,
        },
        "acceptance": {
            "source_semantic_pass": "Every exposed case passes the effective V16 source-semantic lane.",
            "uncertainty_scope": "The uncertainty case has exactly one grounded cohort-to-locus link and one grounded majority qualifier; direct classification-to-locus context is accepted zero or one time only after those mandatory structures pass.",
            "v16_extension_exclusivity": "Every exposed case other than uncertainty has empty participant_scope_links and no partitive_scope; any V16-only extension there is an unsupported source-semantic failure.",
            "historical_regressions": "Comparison, null-result polarity, uncertainty axes, SLC12A3 occurrence boundaries, exact grounding, drug focus, and nested dependency closure remain passing.",
            "bionlp_lane": "Measured separately and never used to reverse source-semantic scoring.",
            "stop_conditions": [
                "first scientific failure",
                "schema, custody, receipt, or exactly-once failure",
                "cumulative operational budget exhaustion",
                "provider outage or absent required secret",
            ],
        },
        "frozen_state": {
            "sealed_v15_head": V15_SEALED_HEAD,
            "sealed_v15_manifest_sha256": _sha256(paths.sealed_v15_manifest),
            "v15_post_run_classification_sha256": _V15_CLASSIFICATION_SHA256,
            "source_scope_tiebreak_sha256": _sha256(paths.source_tiebreak),
            "minimal_schema_review_sha256": _sha256(paths.schema_review),
            "scope_reference_sha256": reference_sha256(),
            "v16_rule_sha256": rule["rule_sha256"],
            "v16_output_schema_sha256": _canonical_sha256(
                V16StagedGeneralizationOutput.model_json_schema()
            ),
            "provider_request_sha256": _canonical_sha256(request_value),
            "grading_policy_sha256": policy_sha256(policy),
            "nested_contract_sha256": _sha256(
                paths.v15.v14.v13.nested_two_lane_contract
            ),
            "runtime_dependency_roots": list(_RUNTIME_ROOTS),
            "runtime_dependency_manifest": list(dependencies),
            "runtime_dependency_manifest_sha256": _canonical_sha256(dependencies),
            "model": MODEL,
            "reasoning_effort": REASONING_EFFORT,
            "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
        },
        "forbidden_changes": {
            "fresh_cases": "FORBIDDEN",
            "graph_writes": "FORBIDDEN",
            "trusted_promotion": "FORBIDDEN",
            "historical_rescoring": "FORBIDDEN",
            "shared_grader": "FORBIDDEN",
            "event_inventory": "UNCHANGED",
            "entity_types": "UNCHANGED",
            "legacy_event_argument_roles": "UNCHANGED",
            "root_selection": "UNCHANGED",
            "semantic_axes": "UNCHANGED",
            "evidence_grounding": "UNCHANGED",
            "BioNLP_CG_projection": "UNCHANGED_RAW_REVIEW_ONLY",
        },
    }


def write_candidate(paths: V16Paths = DEFAULT_PATHS) -> dict[str, object]:
    """Materialize deterministic preregistration artifacts before provider access."""

    manifest = build_sealed_v15_manifest()
    write_json_atomic(paths.sealed_v15_manifest, manifest)
    preregistration = build_preregistration(paths)
    write_json_atomic(paths.preregistration, preregistration)
    return preregistration


def verify(
    paths: V16Paths = DEFAULT_PATHS,
    *,
    remote_gate: bool = False,
    require_package_review: bool = True,
    require_tracked_dependencies: bool = True,
) -> dict[str, object]:
    """Fail closed unless the committed V16 package exactly matches its freeze."""

    expected_manifest = build_sealed_v15_manifest()
    observed_manifest = _read_json(paths.sealed_v15_manifest)
    if observed_manifest != expected_manifest:
        raise V16PreflightError("sealed V15 manifest differs from recomputation")
    expected = build_preregistration(paths)
    observed = _read_json(paths.preregistration)
    if observed != expected:
        raise V16PreflightError("V16 preregistration differs from recomputation")
    if require_tracked_dependencies:
        _verify_tracked_dependencies(observed)
    if require_package_review:
        _verify_package_review(paths, observed)
    remote = (
        verify_remote_execution_state(paths) if remote_gate else {"remote_gate": False}
    )
    return {
        "experiment_id": EXPERIMENT_ID,
        "preregistration_sha256": _sha256(paths.preregistration),
        "sealed_v15_manifest_sha256": _sha256(paths.sealed_v15_manifest),
        "remote": remote,
    }


def verify_remote_execution_state(paths: V16Paths = DEFAULT_PATHS) -> dict[str, object]:
    """Require the committed package and remote branch before any provider call."""

    branch = _git("branch", "--show-current")
    if branch != EXPECTED_BRANCH:
        raise V16PreflightError(f"V16 requires branch {EXPECTED_BRANCH}")
    local_head = _git("rev-parse", "HEAD")
    remote_lines = _git("ls-remote", "--heads", "origin", EXPECTED_BRANCH).splitlines()
    if len(remote_lines) != 1:
        raise V16PreflightError("V16 remote branch is absent or ambiguous")
    remote_head, _, remote_ref = remote_lines[0].partition("\t")
    if remote_ref != f"refs/heads/{EXPECTED_BRANCH}" or remote_head != local_head:
        raise V16PreflightError("V16 local and remote heads differ")
    tracked = _git("status", "--porcelain=v1", "--untracked-files=no")
    if tracked:
        raise V16PreflightError("V16 tracked worktree changes are present")
    untracked = _untracked_paths(
        _git("status", "--porcelain=v1", "--untracked-files=all")
    )
    if any(not value.startswith("validation/") for value in untracked):
        raise V16PreflightError("V16 has unrelated untracked worktree paths")
    _require_outputs_absent(paths)
    return {
        "branch": branch,
        "local_head": local_head,
        "remote_head": remote_head,
        "tracked_modification_count": 0,
        "execution_outputs_absent": True,
        "untracked_paths_preserved": list(untracked),
    }


def _verify_source_adjudications(paths: V16Paths) -> None:
    tiebreak = _read_json(paths.source_tiebreak)
    review = _read_json(paths.schema_review)
    custody = tiebreak.get("source_custody")
    findings = tiebreak.get("adjudicated_findings")
    if not isinstance(custody, dict) or not isinstance(findings, dict):
        raise V16PreflightError("V16 source tiebreak is malformed")
    if (
        custody.get("source_sha256")
        != "91dc8584459752004de193cdaa40efd8024b943f8f841ca5653e42b8d535de5b"
    ):
        raise V16PreflightError("V16 source tiebreak source custody changed")
    if findings.get("cohort_to_locus_scope") != "MANDATORY":
        raise V16PreflightError("V16 scope requirement is not independently frozen")
    if findings.get("partitive_majority_of_cohort") != "MANDATORY":
        raise V16PreflightError("V16 partitive requirement is not independently frozen")
    if (
        findings.get("direct_classification_to_locus_argument")
        != "OPTIONAL_REDUNDANT_CONTEXT_ONLY"
    ):
        raise V16PreflightError("V16 direct context boundary changed")
    if review.get("verdict") != "PASS":
        raise V16PreflightError("V16 minimal schema review is not approved")
    limits = review.get("review_limits")
    if not isinstance(limits, dict) or any(limits.get(key) for key in limits):
        raise V16PreflightError("V16 review has execution-side effects")


def _verify_package_review(
    paths: V16Paths,
    preregistration: dict[str, object],
) -> None:
    review = _read_json(paths.package_review)
    frozen = preregistration.get("frozen_state")
    if not isinstance(frozen, dict):
        raise V16PreflightError("V16 preregistration frozen state is malformed")
    if review.get("preregistration_sha256") != _sha256(paths.preregistration):
        raise V16PreflightError("V16 package review binds another preregistration")
    if (
        review.get("reviewer_id") != "v16_complete_package_reviewer_independent"
        or review.get("verdict") != "HARD_PASS"
        or review.get("reviewed_complete_package") is not True
        or review.get("runtime_dependency_manifest_sha256")
        != frozen.get("runtime_dependency_manifest_sha256")
        or review.get("sealed_v15_manifest_sha256")
        != frozen.get("sealed_v15_manifest_sha256")
        or review.get("provider_calls") != 0
        or review.get("fresh_cases_accessed") != 0
        or review.get("graph_writes") != 0
        or review.get("trusted_promotion") is not False
    ):
        raise V16PreflightError("V16 complete package review is not a hard PASS")
    reviewed = review.get("reviewed_files_sha256")
    if not isinstance(reviewed, dict):
        raise V16PreflightError("V16 complete package review file hashes are absent")
    expected = _expected_reviewed_files()
    if set(reviewed) != expected:
        raise V16PreflightError("V16 complete package review file set is incomplete")
    for relative, digest in reviewed.items():
        if (
            not isinstance(relative, str)
            or not isinstance(digest, str)
            or _sha256(REPO / relative) != digest
        ):
            raise V16PreflightError(
                f"V16 complete package review hash changed: {relative}"
            )


def _expected_reviewed_files() -> frozenset[str]:
    """Bind the complete V16 package plus the preserved V15 execution boundary."""

    return (_V16_ALLOWED_ADDITIONS - {_V16_PACKAGE_REVIEW}) | frozenset(
        _V15_CRITICAL_PATHS
    )


def _verify_tracked_dependencies(preregistration: dict[str, object]) -> None:
    frozen = preregistration.get("frozen_state")
    if not isinstance(frozen, dict):
        raise V16PreflightError("V16 preregistration frozen state is malformed")
    manifest = frozen.get("runtime_dependency_manifest")
    if not isinstance(manifest, list):
        raise V16PreflightError("V16 runtime dependency manifest is malformed")
    for item in manifest:
        if not isinstance(item, dict):
            raise V16PreflightError("V16 runtime dependency entry is malformed")
        relative = item.get("path")
        digest = item.get("sha256")
        if not isinstance(relative, str) or not isinstance(digest, str):
            raise V16PreflightError("V16 runtime dependency entry is incomplete")
        path = REPO / relative
        if not path.is_file() or not _is_tracked(relative):
            raise V16PreflightError(
                f"V16 runtime dependency is not tracked: {relative}"
            )
        if _sha256(path) != digest:
            raise V16PreflightError(f"V16 runtime dependency hash changed: {relative}")


def _require_outputs_absent(paths: V16Paths) -> None:
    candidates = [paths.result, paths.report]
    for case_id in CASE_ORDER:
        item = paths.case(case_id)
        candidates.extend(
            (item.attempt, item.bundle, item.receipt, item.raw_output, item.evaluation)
        )
    if any(path.exists() for path in candidates):
        raise V16PreflightError("V16 execution output exists")


def _git(*arguments: str) -> str:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _git_show(revision: str, relative: str) -> bytes:
    completed = subprocess.run(
        ("git", "show", f"{revision}:{relative}"),
        cwd=REPO,
        check=True,
        capture_output=True,
    )
    return completed.stdout


def _git_at_head_paths(revision: str) -> tuple[str, ...]:
    output = _git("ls-tree", "-r", "--name-only", revision)
    return tuple(line for line in output.splitlines() if line)


def _is_tracked(relative: str) -> bool:
    completed = subprocess.run(
        ("git", "ls-files", "--error-unmatch", "--", relative),
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def _untracked_paths(status: str) -> tuple[str, ...]:
    return tuple(
        line[3:]
        for line in status.splitlines()
        if line.startswith(_UNTRACKED_STATUS_PREFIX)
        and len(line) > len(_UNTRACKED_STATUS_PREFIX)
    )


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise V16PreflightError(f"V16 JSON artifact is not an object: {path}")
    return cast("dict[str, object]", value)


def _critical_sha(entries: list[dict[str, str]], relative: str) -> str:
    return next(item["sha256"] for item in entries if item["path"] == relative)


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "V16PreflightError",
    "build_preregistration",
    "build_sealed_v15_manifest",
    "verify",
    "verify_remote_execution_state",
    "write_candidate",
]
