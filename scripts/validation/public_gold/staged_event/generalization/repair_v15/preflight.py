"""Deterministic V15 preregistration and fail-closed execution preflight."""

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
from scripts.validation.public_gold.staged_event.generalization.repair_v14.provider import (
    build_request as build_v14_request,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15.config import (
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
    V14_SEALED_HEAD,
    V15_AUTHORIZATION_HEAD,
    V15_AUTHORIZATION_SHA256,
    V15Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15.prompt import (
    EXPECTED_RULE_SHA256,
    ordered_cases,
    provider_input,
    verify_rule,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15.provider import (
    build_request,
    provider_format,
)

_RUNTIME_ROOTS = ("scripts/run_staged_generalization_v15_exposed.py",)
_V14_SEALED_TREE = "e511c3d4fb8a7bb09634888cc73cf816e154cf7f"
_OFFLINE_AUDIT_SHA256 = (
    "cc9d7381335cb297a34d8d1ba9d54d1eb95fd7c600fe582d70e3d56f78ed22ca"
)
_OFFLINE_REQUIRED_INVARIANTS = frozenset(
    {
        "true_anaphora_and_ellipsis_remain_resolvable",
        "focus_local_named_occurrences_remain_local",
        "focus_internal_nested_event_closure_remains_complete",
        "v14_noun_head_and_restrictive_identity_rule_remains_unchanged",
        "v14_optional_inner_edge_policy_remains_unchanged",
        "all_earlier_repaired_behaviors_remain_stable",
    }
)
_REMOTE_REF_FIELDS = 2
_V14_CRITICAL_PATHS = (
    "docs/validation/preregistrations/"
    "2026-07-23-staged-generalization-v14-exposed-run-v1.json",
    "docs/validation/prompts/"
    "2026-07-23-staged-generalization-v14-complete-participant-denotation.md",
    "docs/validation/results/2026-07-23-staged-generalization-v14-exposed-run-v1.json",
    "docs/validation/reviews/"
    "2026-07-23-staged-generalization-v14-complete-package-review-v1.json",
    "docs/validation/reviews/"
    "2026-07-23-staged-generalization-v14-post-run-independent-classification-v1.json",
    "scripts/run_staged_generalization_v14_exposed.py",
    "scripts/validation/public_gold/staged_event/generalization/"
    "repair_v14/evaluation.py",
    "scripts/validation/public_gold/staged_event/generalization/"
    "repair_v14/preflight.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v14/prompt.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v14/provider.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v14/runner.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v14/terminal.py",
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
    "tests/unit/test_staged_generalization_v14_preflight.py",
    "tests/unit/test_staged_generalization_v14_prompt.py",
    "tests/unit/test_staged_generalization_v14_runtime.py",
    "tests/unit/test_staged_generalization_v15_preflight.py",
    "tests/unit/test_staged_generalization_v15_prompt.py",
    "tests/unit/test_staged_generalization_v15_provider.py",
    "tests/unit/test_staged_generalization_v15_runtime.py",
)
_V15_ALLOWED_ADDITIONS = frozenset(
    {
        "docs/validation/adjudications/"
        "2026-07-23-staged-generalization-v14-to-v15-focus-closure-consensus-v1.json",
        "docs/validation/adjudications/"
        "2026-07-23-staged-generalization-v15-focus-closure-offline-audit-v1.json",
        "docs/validation/manifests/"
        "2026-07-23-staged-generalization-v15-sealed-v14-manifest-v1.json",
        "docs/validation/preregistrations/"
        "2026-07-23-staged-generalization-v15-exposed-run-v1.json",
        "docs/validation/prompts/"
        "2026-07-23-staged-generalization-v15-focus-closure-and-"
        "role-bearing-occurrence-custody.md",
        "docs/validation/reviews/"
        "2026-07-23-staged-generalization-v15-complete-package-review-v1.json",
        "docs/validation/reviews/"
        "2026-07-23-staged-generalization-v15-rule-wording-reviewer-a-v1.json",
        "docs/validation/reviews/"
        "2026-07-23-staged-generalization-v15-rule-wording-reviewer-b-v1.json",
        "scripts/run_staged_generalization_v15_exposed.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v15/__init__.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v15/config.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v15/preflight.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v15/prompt.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v15/provider.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v15/reporting.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v15/runner.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v15/terminal.py",
        "tests/unit/test_staged_generalization_v15_preflight.py",
        "tests/unit/test_staged_generalization_v15_prompt.py",
        "tests/unit/test_staged_generalization_v15_provider.py",
        "tests/unit/test_staged_generalization_v15_runtime.py",
    }
)


class V15PreflightError(RuntimeError):
    """A frozen V15 scientific, custody, or repository invariant changed."""


def build_sealed_v14_manifest() -> dict[str, object]:
    """Prove every file in the sealed V14 tree remains byte-identical."""

    tree = _git("rev-parse", f"{V14_SEALED_HEAD}^{{tree}}")
    if tree != _V14_SEALED_TREE:
        raise V15PreflightError("sealed V14 tree identity changed")
    sealed_paths = _git_at_head_paths(V14_SEALED_HEAD)
    if not sealed_paths:
        raise V15PreflightError("sealed V14 tree is empty")
    changes = _git("diff", "--name-status", V14_SEALED_HEAD, "--")
    for line in changes.splitlines():
        status, _, relative = line.partition("\t")
        if status != "A" or relative not in _V15_ALLOWED_ADDITIONS:
            raise V15PreflightError(f"sealed V14 tree changed: {line}")
    critical = [
        {
            "path": relative,
            "sha256": hashlib.sha256(_git_show(V14_SEALED_HEAD, relative)).hexdigest(),
        }
        for relative in _V14_CRITICAL_PATHS
    ]
    return {
        "schema_version": "artana.staged_generalization.v15_sealed_v14_manifest.v1",
        "sealed_v14_head": V14_SEALED_HEAD,
        "sealed_v14_tree": tree,
        "sealed_tree_file_count": len(sealed_paths),
        "critical_file_count": len(critical),
        "critical_files": critical,
        "v14_evaluator_sha256": _critical_sha(
            critical,
            "scripts/validation/public_gold/staged_event/generalization/"
            "repair_v14/evaluation.py",
        ),
        "all_sealed_tree_paths_current_bytes_equal": True,
        "historical_results_rescored": False,
    }


def build_preregistration(paths: V15Paths = DEFAULT_PATHS) -> dict[str, object]:
    """Recompute every V15 scientific, execution, and custody binding."""

    _verify_inputs(paths)
    cases = ordered_cases(paths)
    policy = verify_v13_frozen_policy(paths.v14.v13.grading, cases=cases)
    contract = load_contract(
        paths.v14.v13.nested_two_lane_contract,
        adjudication_path=paths.v14.v13.nested_adjudication,
        v12_contract_path=paths.v14.v13.v12_drug_two_lane_contract,
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
    first_input = provider_input(cases[0].case_id, paths)
    request = build_request(
        case_id=cases[0].case_id,
        provider_input=first_input,
        preregistration_sha256="0" * 64,
    )
    frozen_request = build_v14_request(
        case_id=cases[0].case_id,
        provider_input=first_input,
        preregistration_sha256="0" * 64,
    )
    request_value = asdict(request)
    frozen_request_value = asdict(frozen_request)
    request_value.pop("metadata")
    frozen_request_value.pop("metadata")
    if request_value != frozen_request_value:
        raise V15PreflightError("V15 changed a non-metadata V14 request field")
    if hasattr(request, "max_output_tokens") or hasattr(request, "max_total_tokens"):
        raise V15PreflightError("V15 request contract contains a token ceiling")
    frozen_files = _frozen_file_hashes(paths)
    wording_reviews = {
        "reviewer_a": _sha256(paths.wording_review_a),
        "reviewer_b": _sha256(paths.wording_review_b),
    }
    return {
        "schema_version": "artana.staged_generalization.v15_exposed_gate.v1",
        "experiment_id": EXPERIMENT_ID,
        "authorization": "PREREGISTERED_V15_EXPOSED_CASES_ONLY",
        "scientific_evidence_status_before_execution": "NOT_EMPIRICALLY_TESTED",
        "scientific_hypothesis": {
            "name": "FOCUS_CLOSURE_AND_ROLE_BEARING_OCCURRENCE_CUSTODY_V1",
            "statement": (
                "Construct the mandatory focused event graph only from events "
                "denoted by the highlighted finding and their complete inward "
                "focus-internal dependency closure. Bind each explicit "
                "self-denoting role-bearing focus occurrence before participant "
                "text minimization. Other context may resolve one genuinely "
                "dependent or implicit argument under the frozen rules, but may "
                "neither add an outside predicate as an event nor replace an "
                "explicit focus-local occurrence with an antecedent, definition, "
                "or alias."
            ),
            "single_owning_boundary": (
                "PROVIDER_FACING_FOCUS_AND_OCCURRENCE_SCOPE_CONTRACT"
            ),
            "source_general": True,
            "case_specific_provider_examples": False,
        },
        "authorized_changes": {
            "prompt_change_count": 1,
            "prompt_change": ("FOCUS_CLOSURE_AND_ROLE_BEARING_OCCURRENCE_CUSTODY_V1"),
            "v15_evaluator_change": None,
            "v14_evaluator_reused_byte_identical": True,
        },
        "forbidden_changes": {
            "event_inventory_or_taxonomy": True,
            "entity_types": True,
            "mandatory_participants_or_links": True,
            "root_selection": True,
            "semantic_axes": True,
            "statistics": True,
            "evidence_grounding": True,
            "completeness": True,
            "shared_or_historical_graders": True,
            "v14_artifacts": True,
            "v14_local_optional_edge_policy": True,
            "bionlp_cg_projection_policy": True,
            "transport_or_custody": True,
        },
        "frozen_state": {
            "sealed_v14_head": V14_SEALED_HEAD,
            "sealed_v14_tree": _V14_SEALED_TREE,
            "sealed_v14_manifest_sha256": _sha256(paths.sealed_v14_manifest),
            "sealed_v14_evaluator_sha256": _sha256(
                REPO / "scripts/validation/public_gold/staged_event/generalization/"
                "repair_v14/evaluation.py"
            ),
            "v15_authorization_head": V15_AUTHORIZATION_HEAD,
            "v15_authorization_sha256": V15_AUTHORIZATION_SHA256,
            "case_order": list(CASE_ORDER),
            "panel_sha256": _sha256(paths.v14.v13.panel),
            "panel_canonical_sha256": _canonical_sha256(
                json.loads(paths.v14.v13.panel.read_text(encoding="utf-8"))
            ),
            "v15_rule_sha256": EXPECTED_RULE_SHA256,
            "offline_audit_sha256": _sha256(paths.offline_audit),
            "independent_wording_review_sha256": wording_reviews,
            "v14_participant_rule_sha256": _sha256(paths.v14.participant_rule),
            "v14_optional_edge_consensus_sha256": _sha256(paths.v14.consensus),
            "nested_contract_sha256": _sha256(paths.v14.v13.nested_two_lane_contract),
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
            "request_base": "V14_REQUEST_REUSED_NONMETADATA_FIELDS_IDENTICAL",
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
            "focus_closure_and_role_occurrence_hypothesis_pass": True,
            "v14_complete_participant_denotation_pass": True,
            "v14_optional_edge_policy_unchanged": True,
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
            "v16_automatic_start_allowed": False,
        },
        "qualification_credit": False,
    }


def write_candidate(paths: V15Paths = DEFAULT_PATHS) -> None:
    """Write deterministic control artifacts before the package is frozen."""

    _verify_offline_audit(paths)
    for path in (paths.sealed_v14_manifest, paths.preregistration):
        if path.exists():
            raise V15PreflightError(f"V15 candidate already exists: {path.name}")
    write_json_atomic(paths.sealed_v14_manifest, build_sealed_v14_manifest())
    write_json_atomic(paths.preregistration, build_preregistration(paths))


def verify(
    paths: V15Paths = DEFAULT_PATHS,
    *,
    remote_gate: bool = False,
    require_package_review: bool = True,
) -> dict[str, object]:
    """Recompute the freeze, then optionally verify the pushed execution head."""

    expected_manifest = build_sealed_v14_manifest()
    if _read_json(paths.sealed_v14_manifest) != expected_manifest:
        raise V15PreflightError("sealed V14 manifest differs from current bytes")
    _verify_offline_audit(paths)
    expected_preregistration = build_preregistration(paths)
    if _read_json(paths.preregistration) != expected_preregistration:
        raise V15PreflightError("V15 preregistration differs from frozen state")
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
        "sealed_v14_manifest_sha256": _sha256(paths.sealed_v14_manifest),
        "package_review": review,
        "remote": remote,
    }


def verify_remote_execution_state(
    paths: V15Paths = DEFAULT_PATHS,
) -> dict[str, object]:
    """Require the exact pushed branch while preserving unrelated untracked files."""

    branch = _git("branch", "--show-current")
    if branch != EXPECTED_BRANCH:
        raise V15PreflightError(f"V15 requires branch {EXPECTED_BRANCH}")
    local = _git("rev-parse", "HEAD")
    remote = _git("ls-remote", "--heads", "origin", branch).split()
    if len(remote) != _REMOTE_REF_FIELDS or remote[0] != local:
        raise V15PreflightError("local and remote heads differ before V15")
    tracked_status = _git("status", "--porcelain=v1", "--untracked-files=no")
    if tracked_status:
        raise V15PreflightError("tracked worktree changes exist before V15")
    changes = _git("diff", "--name-status", f"{V14_SEALED_HEAD}..HEAD")
    for line in changes.splitlines():
        status, _, relative = line.partition("\t")
        if status != "A" or relative not in _V15_ALLOWED_ADDITIONS:
            raise V15PreflightError(
                f"sealed V14 tree has unauthorized V15 diff: {line}"
            )
    present = [
        _relative(path) for path in _execution_output_paths(paths) if path.exists()
    ]
    if present:
        raise V15PreflightError(f"V15 execution output exists: {present}")
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
        *_frozen_input_paths(paths),
    }
    for path in required:
        relative = _relative(path)
        if _git("ls-files", "--error-unmatch", "--", relative) != relative:
            raise V15PreflightError(f"V15 frozen path is untracked: {relative}")
    status = _git("status", "--porcelain=v1", "--untracked-files=all")
    unexpected = [
        line for line in status.splitlines() if line and not line.startswith("?? ")
    ]
    if unexpected:
        raise V15PreflightError("tracked worktree changed during remote gate")
    untracked = [line[3:] for line in status.splitlines() if line.startswith("?? ")]
    return {
        "branch": branch,
        "local_head": local,
        "remote_head": remote[0],
        "tracked_modification_count": 0,
        "sealed_v14_diff_is_additions_only": True,
        "execution_outputs_absent": True,
        "untracked_paths_preserved": untracked,
    }


def _verify_inputs(paths: V15Paths) -> None:
    rule = verify_rule(paths)
    if rule.get("evaluator_change") is not False:
        raise V15PreflightError("V15 rule authorizes an evaluator change")
    if _sha256(paths.consensus) != V15_AUTHORIZATION_SHA256:
        raise V15PreflightError("V15 authorization hash changed")
    consensus = _read_json(paths.consensus)
    authorization = _object(consensus.get("v15_authorization"))
    hypothesis = _object(consensus.get("unified_v15_hypothesis"))
    if (
        authorization.get("status")
        != "AUTHORIZED_FOR_MINIMAL_EXPOSED_HYPOTHESIS_TEST_ONLY"
        or hypothesis.get("name")
        != "FOCUS_CLOSURE_AND_ROLE_BEARING_OCCURRENCE_CUSTODY_V1"
        or consensus.get("consensus_verdict")
        != "V15_MINIMAL_EXPOSED_HYPOTHESIS_TEST_AUTHORIZED_NOT_YET_FROZEN"
    ):
        raise V15PreflightError("independent V15 authorization is absent")
    wording_reviews = (
        (paths.wording_review_a, "v15_rule_wording_reviewer_a"),
        (paths.wording_review_b, "v15_rule_wording_reviewer_b"),
    )
    for path, expected_reviewer in wording_reviews:
        review = _read_json(path)
        if (
            review.get("reviewer_id") != expected_reviewer
            or review.get("verdict") != "HARD_PASS"
            or review.get("reviewed_exact_bytes") is not True
            or review.get("rule_sha256") != EXPECTED_RULE_SHA256
            or review.get("consensus_sha256") != V15_AUTHORIZATION_SHA256
            or review.get("source_general") is not True
            or review.get("additive_to_v14") is not True
            or review.get("evaluator_changed") is not False
            or review.get("case_specific_terms_present") != []
            or review.get("provider_calls") != 0
            or review.get("fresh_cases_accessed") != 0
            or review.get("graph_writes") != 0
            or review.get("trusted_promotion") is not False
        ):
            raise V15PreflightError(f"wording review failed: {path.name}")
    _verify_offline_audit(paths)
    manifest = _read_json(paths.sealed_v14_manifest)
    if (
        manifest.get("all_sealed_tree_paths_current_bytes_equal") is not True
        or manifest.get("v14_evaluator_sha256")
        != "28a6e6f7140bb5d240b34516afe52153d76753b5d6fc30d02ab44d59092811df"
    ):
        raise V15PreflightError("sealed V14 byte proof is absent")
    qualification = _read_json(paths.v14.v13.qualified_transport_result)
    if qualification.get("decision") != "FOREGROUND_TRANSPORT_QUALIFIED":
        raise V15PreflightError("frozen foreground transport is not qualified")


def _verify_package_review(
    paths: V15Paths,
    preregistration: dict[str, object],
) -> dict[str, object]:
    review = _read_json(paths.package_review)
    prereg_sha = _sha256(paths.preregistration)
    frozen = _object(preregistration.get("frozen_state"))
    if (
        review.get("reviewer_id") != "v15_complete_package_reviewer_independent"
        or review.get("verdict") != "HARD_PASS"
        or review.get("reviewed_complete_package") is not True
        or review.get("preregistration_sha256") != prereg_sha
        or review.get("runtime_dependency_manifest_sha256")
        != frozen.get("runtime_dependency_manifest_sha256")
        or review.get("provider_calls") != 0
        or review.get("fresh_cases_accessed") != 0
        or review.get("graph_writes") != 0
        or review.get("trusted_promotion") is not False
    ):
        raise V15PreflightError("complete-package review is not a hard PASS")
    reviewed = review.get("reviewed_files_sha256")
    if not isinstance(reviewed, dict) or not reviewed:
        raise V15PreflightError("complete-package review file hashes are absent")
    review_relative = _relative(paths.package_review)
    expected_reviewed = set(_V15_ALLOWED_ADDITIONS) - {review_relative} | set(
        _V14_CRITICAL_PATHS
    )
    if set(reviewed) != expected_reviewed:
        raise V15PreflightError("complete-package review file set is incomplete")
    for relative, digest in reviewed.items():
        if (
            not isinstance(relative, str)
            or not isinstance(digest, str)
            or _sha256(REPO / relative) != digest
        ):
            raise V15PreflightError(f"complete-package review hash changed: {relative}")
    return {
        "verdict": "HARD_PASS",
        "review_sha256": _sha256(paths.package_review),
        "reviewed_file_count": len(reviewed),
    }


def _verify_offline_audit(paths: V15Paths) -> dict[str, object]:
    if _sha256(paths.offline_audit) != _OFFLINE_AUDIT_SHA256:
        raise V15PreflightError("V15 offline audit hash changed")
    audit = _read_json(paths.offline_audit)
    required = _object(audit.get("required_invariant_assessments"))
    assessments = audit.get("case_assessments")
    unchanged = _object(audit.get("unchanged_scientific_contract"))
    if (
        audit.get("verdict") != "PASS"
        or audit.get("audit_evidence_kind") != "OFFLINE_CONTRACT_COMPATIBILITY_ONLY"
        or audit.get("provider_behavior_empirically_validated") is not False
        or audit.get("scientific_fix_already_proven") is not False
        or audit.get("qualification_credit") is not False
        or audit.get("provider_prompt_case_specific_examples") is not False
        or audit.get("case_order") != list(CASE_ORDER)
        or set(required) != _OFFLINE_REQUIRED_INVARIANTS
        or set(required.values()) != {"PASS"}
        or not isinstance(assessments, list)
        or [item.get("case_id") for item in assessments if isinstance(item, dict)]
        != list(CASE_ORDER)
        or not unchanged
        or any(value is not True for value in unchanged.values())
        or audit.get("provider_calls") != 0
        or audit.get("fresh_cases_accessed") != 0
        or audit.get("graph_writes") != 0
        or audit.get("trusted_promotion") is not False
    ):
        raise V15PreflightError("V15 offline audit contract is invalid")
    return audit


def _frozen_file_hashes(paths: V15Paths) -> dict[str, str]:
    return {_relative(path): _sha256(path) for path in _frozen_input_paths(paths)}


def _frozen_input_paths(paths: V15Paths) -> tuple[Path, ...]:
    v13 = paths.v14.v13
    grading = v13.grading
    post_run_classification = (
        REPO / "docs/validation/reviews/"
        "2026-07-23-staged-generalization-v14-post-run-"
        "independent-classification-v1.json"
    )
    return tuple(
        sorted(
            {
                v13.panel,
                v13.panel_source_custody,
                v13.v11_prompt,
                v13.v12_focus_rule,
                v13.root_rule,
                v13.nested_adjudication,
                v13.nested_two_lane_contract,
                v13.v12_drug_adjudication,
                v13.v12_drug_two_lane_contract,
                v13.qualified_transport_result,
                paths.v14.participant_rule,
                paths.v14.consensus,
                paths.v14.rule_audit,
                paths.v14.sealed_v13_manifest,
                paths.v14.preregistration,
                paths.v14.package_review,
                paths.v14.result,
                paths.v14.report,
                post_run_classification,
                paths.focus_occurrence_rule,
                paths.consensus,
                paths.wording_review_a,
                paths.wording_review_b,
                paths.offline_audit,
                paths.sealed_v14_manifest,
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


def _execution_output_paths(paths: V15Paths) -> tuple[Path, ...]:
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


def _critical_sha(entries: list[dict[str, str]], path: str) -> str:
    for entry in entries:
        if entry["path"] == path:
            return entry["sha256"]
    raise V15PreflightError(f"critical V14 path is absent: {path}")


def _git_at_head_paths(commit: str) -> tuple[str, ...]:
    value = _run_git_bytes("ls-tree", "-r", "--name-only", commit).decode()
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
        raise V15PreflightError(completed.stderr.decode().strip())
    return completed.stdout


def _git(*arguments: str) -> str:
    return _run_git_bytes(*arguments).decode().strip()


def _read_json(path: Path) -> dict[str, object]:
    return _object(json.loads(path.read_text(encoding="utf-8")))


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise V15PreflightError("expected JSON object")
    return cast("dict[str, object]", value)


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError as exc:
        raise V15PreflightError(f"path escapes repository: {path}") from exc


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "V15PreflightError",
    "build_preregistration",
    "build_sealed_v14_manifest",
    "verify",
    "verify_remote_execution_state",
    "write_candidate",
]
