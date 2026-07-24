"""Deterministic V18 preregistration and fail-closed execution preflight.

V18 is deliberately a small, version-local repair over the sealed V17 package.
The preflight proves that the V17 history has not moved, binds the
independently adjudicated anaphoric-locus-completeness rule, and rejects
provider execution unless the complete V18 package is committed, reviewed,
and reproducible.
"""

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
from scripts.validation.public_gold.staged_event.generalization.repair_v16.contracts import (
    V16StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.reference_policy import (
    UNCERTAINTY_SCOPE_REFERENCE,
    reference_sha256,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v18.config import (
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
    V17_SEALED_HEAD,
    V18Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v18.prompt import (
    ordered_cases,
    provider_input,
    verify_rule,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v18.provider import (
    build_request,
)

_RUNTIME_ROOTS = ("scripts/run_staged_generalization_v18_exposed.py",)
_UNTRACKED_STATUS_PREFIX = "?? "
_V18_PACKAGE_REVIEW = (
    "docs/validation/reviews/"
    "2026-07-24-staged-generalization-v18-complete-package-review-v1.json"
)
_V17_SEALED_TREE = "dda54adff2412344a6799891dbac010088ffca47"
_V17_POST_RUN_CLASSIFICATION = (
    "docs/validation/reviews/"
    "2026-07-24-staged-generalization-v17-post-run-independent-"
    "classification-v1.json"
)
_V17_POST_RUN_CLASSIFICATION_SHA256 = (
    "1c60228ea707535c3b52e6a4cf48af629b2231f9017af3b1227a68a530444902"
)
_V17_CRITICAL_PATHS = (
    "docs/validation/adjudications/"
    "2026-07-24-staged-generalization-v17-inline-versus-anaphoric-"
    "scope-tiebreak-v1.json",
    "docs/validation/evaluations/"
    "2026-07-24-staged-generalization-v17-exposed-run-v1-"
    "generalization-comparison-canary-evaluation.json",
    "docs/validation/evaluations/"
    "2026-07-24-staged-generalization-v17-exposed-run-v1-"
    "generalization-drug-sensitivity-evaluation.json",
    "docs/validation/evaluations/"
    "2026-07-24-staged-generalization-v17-exposed-run-v1-"
    "generalization-uncertainty-evaluation.json",
    "docs/validation/manifests/"
    "2026-07-24-staged-generalization-v17-sealed-v16-manifest-v1.json",
    "docs/validation/preregistrations/"
    "2026-07-24-staged-generalization-v17-exposed-run-v1.json",
    "docs/validation/prompts/"
    "2026-07-24-staged-generalization-v17-inline-versus-anaphoric-scope.md",
    "docs/validation/receipts/"
    "2026-07-24-staged-generalization-v17-exposed-run-v1-"
    "generalization-comparison-canary-attempt.json",
    "docs/validation/receipts/"
    "2026-07-24-staged-generalization-v17-exposed-run-v1-"
    "generalization-comparison-canary-custody.json",
    "docs/validation/receipts/"
    "2026-07-24-staged-generalization-v17-exposed-run-v1-"
    "generalization-comparison-canary.json",
    "docs/validation/receipts/"
    "2026-07-24-staged-generalization-v17-exposed-run-v1-"
    "generalization-drug-sensitivity-attempt.json",
    "docs/validation/receipts/"
    "2026-07-24-staged-generalization-v17-exposed-run-v1-"
    "generalization-drug-sensitivity-custody.json",
    "docs/validation/receipts/"
    "2026-07-24-staged-generalization-v17-exposed-run-v1-"
    "generalization-drug-sensitivity.json",
    "docs/validation/receipts/"
    "2026-07-24-staged-generalization-v17-exposed-run-v1-"
    "generalization-uncertainty-attempt.json",
    "docs/validation/receipts/"
    "2026-07-24-staged-generalization-v17-exposed-run-v1-"
    "generalization-uncertainty-custody.json",
    "docs/validation/receipts/"
    "2026-07-24-staged-generalization-v17-exposed-run-v1-"
    "generalization-uncertainty.json",
    "docs/validation/reports/"
    "2026-07-24-staged-generalization-v17-exposed-run-v1-final.md",
    "docs/validation/results/"
    "2026-07-24-staged-generalization-v17-exposed-run-v1-"
    "generalization-comparison-canary-raw.json",
    "docs/validation/results/"
    "2026-07-24-staged-generalization-v17-exposed-run-v1-"
    "generalization-drug-sensitivity-raw.json",
    "docs/validation/results/"
    "2026-07-24-staged-generalization-v17-exposed-run-v1-"
    "generalization-uncertainty-raw.json",
    "docs/validation/results/2026-07-24-staged-generalization-v17-exposed-run-v1.json",
    "docs/validation/reviews/"
    "2026-07-24-staged-generalization-v17-complete-package-review-v1.json",
    _V17_POST_RUN_CLASSIFICATION,
    "scripts/run_staged_generalization_v17_exposed.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v17/__init__.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v17/config.py",
    "scripts/validation/public_gold/staged_event/generalization/"
    "repair_v17/evaluation.py",
    "scripts/validation/public_gold/staged_event/generalization/"
    "repair_v17/preflight.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v17/prompt.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v17/provider.py",
    "scripts/validation/public_gold/staged_event/generalization/"
    "repair_v17/reporting.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v17/runner.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v17/terminal.py",
    "tests/unit/test_staged_generalization_v17_evaluation.py",
    "tests/unit/test_staged_generalization_v17_preflight.py",
    "tests/unit/test_staged_generalization_v17_prompt.py",
    "tests/unit/test_staged_generalization_v17_provider.py",
    "tests/unit/test_staged_generalization_v17_runtime.py",
)
_V18_ALLOWED_ADDITIONS = frozenset(
    {
        "docs/validation/adjudications/"
        "2026-07-24-staged-generalization-v18-anaphoric-locus-completeness-"
        "tiebreak-v1.json",
        "docs/validation/manifests/"
        "2026-07-24-staged-generalization-v18-sealed-v17-manifest-v1.json",
        "docs/validation/preregistrations/"
        "2026-07-24-staged-generalization-v18-exposed-run-v1.json",
        "docs/validation/prompts/"
        "2026-07-24-staged-generalization-v18-anaphoric-locus-completeness.md",
        _V18_PACKAGE_REVIEW,
        "scripts/run_staged_generalization_v18_exposed.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v18/__init__.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v18/config.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v18/evaluation.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v18/preflight.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v18/prompt.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v18/provider.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v18/reporting.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v18/runner.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v18/terminal.py",
        "tests/unit/test_staged_generalization_v18_evaluation.py",
        "tests/unit/test_staged_generalization_v18_preflight.py",
        "tests/unit/test_staged_generalization_v18_prompt.py",
        "tests/unit/test_staged_generalization_v18_provider.py",
        "tests/unit/test_staged_generalization_v18_runtime.py",
    }
)
_UNCERTAINTY_SOURCE_SHA256 = (
    "91dc8584459752004de193cdaa40efd8024b943f8f841ca5653e42b8d535de5b"
)


class V18PreflightError(RuntimeError):
    """A frozen V18 scientific, custody, or repository invariant changed."""


def build_sealed_v17_manifest() -> dict[str, object]:
    """Prove that the sealed V17 lineage remains byte-identical.

    The V17 tree is the complete historical baseline.  A tree-to-working-tree
    diff permits only the finite V18 package additions; this proves every
    other tracked historical path is unchanged.  Critical V17 source,
    execution, and classification artifacts are also individually
    hash-bound for readable custody evidence in the preregistration.
    """

    tree = _git("rev-parse", f"{V17_SEALED_HEAD}^{{tree}}")
    if tree != _V17_SEALED_TREE:
        raise V18PreflightError("sealed V17 tree identity changed")
    sealed_paths = _git_at_head_paths(V17_SEALED_HEAD)
    if not sealed_paths:
        raise V18PreflightError("sealed V17 tree is empty")
    for line in _git("diff", "--name-status", V17_SEALED_HEAD, "--").splitlines():
        status, _, relative = line.partition("\t")
        if status != "A" or relative not in _V18_ALLOWED_ADDITIONS:
            raise V18PreflightError(f"sealed V17 tree changed: {line}")
    critical = []
    for relative in _V17_CRITICAL_PATHS:
        expected = hashlib.sha256(_git_show(V17_SEALED_HEAD, relative)).hexdigest()
        observed = _sha256(REPO / relative)
        if observed != expected:
            raise V18PreflightError(f"sealed V17 critical file changed: {relative}")
        critical.append({"path": relative, "sha256": expected})
    if (
        _critical_sha(critical, _V17_POST_RUN_CLASSIFICATION)
        != _V17_POST_RUN_CLASSIFICATION_SHA256
    ):
        raise V18PreflightError("sealed V17 post-run classification hash changed")
    return {
        "schema_version": "artana.staged_generalization.v18_sealed_v17_manifest.v1",
        "sealed_v17_head": V17_SEALED_HEAD,
        "sealed_v17_tree": tree,
        "sealed_tree_file_count": len(sealed_paths),
        "critical_file_count": len(critical),
        "critical_files": critical,
        "v17_post_run_classification_sha256": _critical_sha(
            critical,
            _V17_POST_RUN_CLASSIFICATION,
        ),
        "all_sealed_tree_paths_current_bytes_equal": True,
        "historical_results_rescored": False,
    }


def build_preregistration(paths: V18Paths = DEFAULT_PATHS) -> dict[str, object]:
    """Recompute every V18 scientific, execution, and custody binding."""

    _verify_source_adjudication(paths)
    rule = verify_rule(paths)
    cases = ordered_cases(paths)
    policy = verify_v13_frozen_policy(paths.v17.v16.v15.v14.v13.grading, cases=cases)
    load_contract(
        paths.v17.v16.v15.v14.v13.nested_two_lane_contract,
        adjudication_path=paths.v17.v16.v15.v14.v13.nested_adjudication,
        v12_contract_path=paths.v17.v16.v15.v14.v13.v12_drug_two_lane_contract,
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
    request = build_request(
        case_id=cases[0].case_id,
        provider_input=provider_input(cases[0].case_id, paths),
        preregistration_sha256="0" * 64,
    )
    if hasattr(request, "max_output_tokens") or hasattr(request, "max_total_tokens"):
        raise V18PreflightError("V18 request contract contains a token ceiling")
    request_value = asdict(request)
    return {
        "schema_version": "artana.staged_generalization.v18_exposed_gate.v1",
        "experiment_id": EXPERIMENT_ID,
        "authorization": "PREREGISTERED_V18_EXPOSED_CASES_ONLY",
        "scientific_evidence_status_before_execution": "NOT_EMPIRICALLY_TESTED",
        "scientific_hypothesis": {
            "name": "ANAPHORIC_LOCUS_COMPLETENESS_V1",
            "statement": (
                "When a downstream anaphoric aggregate or partitive depends on "
                "a restriction the source states outside its antecedent's "
                "complete role-bearing span, that restriction must be "
                "represented as its own participant with a scope link from "
                "the antecedent, regardless of how inferable the restriction "
                "seems. This requirement is independent of, and unweakened "
                "by, the unchanged V17 prohibition on decomposing an "
                "already-inline restriction."
            ),
            "source_general": True,
            "provider_prompt_change": "V18_ANAPHORIC_LOCUS_COMPLETENESS_ONLY",
            "schema_change": "NONE_V16_TYPED_SCOPE_SCHEMA_RETAINED",
            "local_evaluator_change": "NONE_V17_EVALUATOR_REUSED_BYTE_IDENTICAL",
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
            "source_semantic_pass": (
                "Every exposed case passes the effective V18 source-semantic "
                "lane, which is the unmodified V17 evaluator."
            ),
            "comparison_inline_scope": (
                "The comparison retains complete RA-restricted population "
                "spans and contains no inline-scope child participant or "
                "link, unchanged from V17."
            ),
            "uncertainty_anaphoric_scope": (
                "The uncertainty case has exactly one grounded cohort-to-locus "
                "typed scope link and one grounded MAJORITY qualifier; direct "
                "classification-to-locus context remains accepted zero or one "
                "time only after those mandatory structures pass."
            ),
            "historical_regressions": (
                "Comparison, null-result polarity, uncertainty axes, "
                "SLC12A3 occurrence boundaries, exact grounding, drug focus, "
                "and nested dependency closure remain passing."
            ),
            "bionlp_lane": "Measured separately and never used to reverse source-semantic scoring.",
            "stop_conditions": [
                "first scientific failure",
                "schema, custody, receipt, or exactly-once failure",
                "cumulative operational budget exhaustion",
                "provider outage or absent required secret",
            ],
        },
        "frozen_state": {
            "sealed_v17_head": V17_SEALED_HEAD,
            "sealed_v17_manifest_sha256": _sha256(paths.sealed_v17_manifest),
            "v17_post_run_classification_sha256": _V17_POST_RUN_CLASSIFICATION_SHA256,
            "anaphoric_locus_completeness_tiebreak_sha256": _sha256(
                paths.source_tiebreak
            ),
            "v18_rule_sha256": rule["rule_sha256"],
            "v16_scope_reference_sha256": reference_sha256(),
            "v16_output_schema_sha256": _canonical_sha256(
                V16StagedGeneralizationOutput.model_json_schema()
            ),
            "provider_request_sha256": _canonical_sha256(request_value),
            "grading_policy_sha256": policy_sha256(policy),
            "nested_contract_sha256": _sha256(
                paths.v17.v16.v15.v14.v13.nested_two_lane_contract
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


def write_candidate(paths: V18Paths = DEFAULT_PATHS) -> dict[str, object]:
    """Materialize deterministic V18 freeze artifacts before provider access."""

    manifest = build_sealed_v17_manifest()
    write_json_atomic(paths.sealed_v17_manifest, manifest)
    preregistration = build_preregistration(paths)
    write_json_atomic(paths.preregistration, preregistration)
    return preregistration


def verify(
    paths: V18Paths = DEFAULT_PATHS,
    *,
    remote_gate: bool = False,
    require_package_review: bool = True,
    require_tracked_dependencies: bool = True,
) -> dict[str, object]:
    """Fail closed unless the committed V18 package exactly matches its freeze."""

    expected_manifest = build_sealed_v17_manifest()
    observed_manifest = _read_json(paths.sealed_v17_manifest)
    if observed_manifest != expected_manifest:
        raise V18PreflightError("sealed V17 manifest differs from recomputation")
    expected = build_preregistration(paths)
    observed = _read_json(paths.preregistration)
    if observed != expected:
        raise V18PreflightError("V18 preregistration differs from recomputation")
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
        "sealed_v17_manifest_sha256": _sha256(paths.sealed_v17_manifest),
        "remote": remote,
    }


def verify_remote_execution_state(paths: V18Paths = DEFAULT_PATHS) -> dict[str, object]:
    """Require the committed package and remote branch before any provider call."""

    branch = _git("branch", "--show-current")
    if branch != EXPECTED_BRANCH:
        raise V18PreflightError(f"V18 requires branch {EXPECTED_BRANCH}")
    local_head = _git("rev-parse", "HEAD")
    remote_lines = _git("ls-remote", "--heads", "origin", EXPECTED_BRANCH).splitlines()
    if len(remote_lines) != 1:
        raise V18PreflightError("V18 remote branch is absent or ambiguous")
    remote_head, _, remote_ref = remote_lines[0].partition("\t")
    if remote_ref != f"refs/heads/{EXPECTED_BRANCH}" or remote_head != local_head:
        raise V18PreflightError("V18 local and remote heads differ")
    tracked = _git("status", "--porcelain=v1", "--untracked-files=no")
    if tracked:
        raise V18PreflightError("V18 tracked worktree changes are present")
    untracked = _untracked_paths(
        _git("status", "--porcelain=v1", "--untracked-files=all")
    )
    if any(not value.startswith("validation/") for value in untracked):
        raise V18PreflightError("V18 has unrelated untracked worktree paths")
    _require_outputs_absent(paths)
    return {
        "branch": branch,
        "local_head": local_head,
        "remote_head": remote_head,
        "tracked_modification_count": 0,
        "execution_outputs_absent": True,
        "untracked_paths_preserved": list(untracked),
    }


def _verify_source_adjudication(paths: V18Paths) -> None:
    adjudication = _read_json(paths.source_tiebreak)
    custody = adjudication.get("source_custody")
    findings = adjudication.get("adjudicated_findings")
    limits = adjudication.get("review_limits")
    if (
        not isinstance(custody, dict)
        or not isinstance(findings, dict)
        or not isinstance(limits, dict)
    ):
        raise V18PreflightError("V18 source adjudication is malformed")
    uncertainty = custody.get("uncertainty")
    if not isinstance(uncertainty, dict):
        raise V18PreflightError("V18 source adjudication custody is malformed")
    if uncertainty.get("source_sha256") != _UNCERTAINTY_SOURCE_SHA256:
        raise V18PreflightError("V18 uncertainty source custody changed")
    expected_findings = {
        "uncertainty_typed_scope": "MANDATORY",
        "uncertainty_cohort_to_locus_scope": "MANDATORY",
        "uncertainty_partitive_majority_of_cohort": "MANDATORY",
        "uncertainty_direct_classification_to_locus_argument": "OPTIONAL_REDUNDANT_CONTEXT_ONLY",
        "uncertainty_locus_omission_excusable_by_inferability": "NEVER_TRUE_STRUCTURAL_REQUIREMENT_NOT_EPISTEMIC",
        "inline_versus_anaphoric_boundary_v17_rule": "UNCHANGED_AND_INDEPENDENT_OF_THIS_FINDING",
        "separate_detection_event": "NOT_REQUIRED",
    }
    for key, expected in expected_findings.items():
        if findings.get(key) != expected:
            raise V18PreflightError(f"V18 source adjudication finding changed: {key}")
    expected_limits = {
        "provider_calls": 0,
        "fresh_cases_accessed": 0,
        "graph_writes": 0,
        "trusted_promotion": False,
        "historical_artifacts_modified": False,
    }
    if any(limits.get(key) != expected for key, expected in expected_limits.items()):
        raise V18PreflightError("V18 source adjudication has execution-side effects")


def _verify_package_review(
    paths: V18Paths,
    preregistration: dict[str, object],
) -> None:
    review = _read_json(paths.package_review)
    frozen = preregistration.get("frozen_state")
    if not isinstance(frozen, dict):
        raise V18PreflightError("V18 preregistration frozen state is malformed")
    if review.get("preregistration_sha256") != _sha256(paths.preregistration):
        raise V18PreflightError("V18 package review binds another preregistration")
    if (
        review.get("reviewer_id") != "v18_complete_package_reviewer_independent"
        or review.get("verdict") != "HARD_PASS"
        or review.get("reviewed_complete_package") is not True
        or review.get("runtime_dependency_manifest_sha256")
        != frozen.get("runtime_dependency_manifest_sha256")
        or review.get("sealed_v17_manifest_sha256")
        != frozen.get("sealed_v17_manifest_sha256")
        or review.get("provider_calls") != 0
        or review.get("fresh_cases_accessed") != 0
        or review.get("graph_writes") != 0
        or review.get("trusted_promotion") is not False
    ):
        raise V18PreflightError("V18 complete package review is not a hard PASS")
    reviewed = review.get("reviewed_files_sha256")
    if not isinstance(reviewed, dict):
        raise V18PreflightError("V18 complete package review file hashes are absent")
    expected = _expected_reviewed_files()
    if set(reviewed) != expected:
        raise V18PreflightError("V18 complete package review file set is incomplete")
    for relative, digest in reviewed.items():
        if (
            not isinstance(relative, str)
            or not isinstance(digest, str)
            or _sha256(REPO / relative) != digest
        ):
            raise V18PreflightError(
                f"V18 complete package review hash changed: {relative}"
            )


def _expected_reviewed_files() -> frozenset[str]:
    """Bind all V18 additions and the preserved V17 scientific boundary."""

    return (_V18_ALLOWED_ADDITIONS - {_V18_PACKAGE_REVIEW}) | frozenset(
        _V17_CRITICAL_PATHS
    )


def _verify_tracked_dependencies(preregistration: dict[str, object]) -> None:
    frozen = preregistration.get("frozen_state")
    if not isinstance(frozen, dict):
        raise V18PreflightError("V18 preregistration frozen state is malformed")
    manifest = frozen.get("runtime_dependency_manifest")
    if not isinstance(manifest, list):
        raise V18PreflightError("V18 runtime dependency manifest is malformed")
    for item in manifest:
        if not isinstance(item, dict):
            raise V18PreflightError("V18 runtime dependency entry is malformed")
        relative = item.get("path")
        digest = item.get("sha256")
        if not isinstance(relative, str) or not isinstance(digest, str):
            raise V18PreflightError("V18 runtime dependency entry is incomplete")
        path = REPO / relative
        if not path.is_file() or not _is_tracked(relative):
            raise V18PreflightError(
                f"V18 runtime dependency is not tracked: {relative}"
            )
        if _sha256(path) != digest:
            raise V18PreflightError(f"V18 runtime dependency hash changed: {relative}")


def _require_outputs_absent(paths: V18Paths) -> None:
    candidates = [paths.result, paths.report]
    for case_id in CASE_ORDER:
        item = paths.case(case_id)
        candidates.extend(
            (item.attempt, item.bundle, item.receipt, item.raw_output, item.evaluation)
        )
    if any(path.exists() for path in candidates):
        raise V18PreflightError("V18 execution output exists")


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
        raise V18PreflightError(f"V18 JSON artifact is not an object: {path}")
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
    "V18PreflightError",
    "build_preregistration",
    "build_sealed_v17_manifest",
    "verify",
    "verify_remote_execution_state",
    "write_candidate",
]
