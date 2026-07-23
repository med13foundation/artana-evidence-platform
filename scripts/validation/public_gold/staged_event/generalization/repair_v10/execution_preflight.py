"""Build and verify the forward-only V10 exposed execution preregistration."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import cast

from scripts.validation.public_gold.staged_event.generalization.grading.artifacts import (
    verify_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    policy_sha256,
)
from scripts.validation.public_gold.staged_event.generalization.panel import (
    agent_case,
    build_panel,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    DEFAULT_PATHS,
    EXPERIMENT_ID,
    GLOBAL_MAX_CALLS,
    GLOBAL_MAX_COST_USD,
    MODEL,
    REASONING_EFFORT,
    REPO,
    V10ExecutionPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_provider import (
    provider_format,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.historical_v9 import (
    verify_provenance,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.preflight import (
    verify as verify_offline_v10,
)

_CALLED_V9_CASES = (
    "generalization-comparison-canary",
    "generalization-null-statistics",
    "generalization-negated-association",
    "generalization-uncertainty",
    "generalization-drug-sensitivity",
)
_UNCALLED_V9_CASES = ("generalization-explicit-nested-cause",)
_EVALUATOR_FILES = (
    "scripts/validation/public_gold/staged_event/generalization/anchors.py",
    "scripts/validation/public_gold/staged_event/generalization/evaluation.py",
    "scripts/validation/public_gold/staged_event/generalization/span_identity.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/artifacts.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/evaluation.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/policy.py",
)
_RECEIPT_FILES = (
    "scripts/validation/provider_receipt_boundary/__init__.py",
    "scripts/validation/provider_receipt_boundary/canonical_payload.py",
    "scripts/validation/provider_receipt_boundary/contracts.py",
    "scripts/validation/provider_receipt_boundary/identity.py",
    "scripts/validation/provider_receipt_boundary/operational_accounting_v2.py",
    "scripts/validation/provider_receipt_boundary/structural_diff.py",
    "scripts/validation/provider_receipt_boundary/validation.py",
    "scripts/validation/provider_receipt_boundary/background/__init__.py",
    "scripts/validation/provider_receipt_boundary/background/contracts.py",
    "scripts/validation/provider_receipt_boundary/background/execution.py",
    "scripts/validation/provider_receipt_boundary/background/polling.py",
    "scripts/validation/provider_receipt_boundary/background/states.py",
)
_IMPLEMENTATION_FILES = (
    "scripts/run_staged_generalization_v10_exposed.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v10/"
    "execution_acceptance.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v10/"
    "execution_accounting.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v10/"
    "execution_config.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v10/"
    "execution_preflight.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v10/"
    "execution_provider.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v10/"
    "execution_runner.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v10/"
    "execution_terminal.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v10/"
    "historical_v9.py",
)
_FORBIDDEN_AGENT_INPUT_TERMS = (
    '"reference"',
    "acceptable_texts",
    "expected participant",
    "direct CG",
    "Fresh-CG V2",
    "V3 corrected reference",
    "grader policy",
)
_REMOTE_REF_FIELD_COUNT = 2


class V10ExecutionPreflightError(RuntimeError):
    """The exposed V10 run differs from its frozen execution contract."""


def provider_input(
    paths: V10ExecutionPaths,
    case_id: str,
) -> str:
    cases = {case.case_id: case for case in build_panel()}
    case = cases.get(case_id)
    if case is None:
        raise V10ExecutionPreflightError(f"unknown exposed case: {case_id}")
    verify_offline_v10()
    value = (
        paths.prompt.read_text(encoding="utf-8")
        + "\n\n--- FROZEN EXPOSED CASE ---\n"
        + json.dumps(agent_case(case), indent=2, sort_keys=True)
        + "\n--- END FROZEN EXPOSED CASE ---\n"
    )
    present = [term for term in _FORBIDDEN_AGENT_INPUT_TERMS if term in value]
    if present:
        raise V10ExecutionPreflightError(
            f"V10 provider input exposes forbidden material: {present}"
        )
    return value


def build_preregistration(
    paths: V10ExecutionPaths = DEFAULT_PATHS,
) -> dict[str, object]:
    """Recompute every input, reference, baseline, evaluator, and policy pin."""

    offline = verify_offline_v10()
    provenance = verify_provenance(paths)
    policy = verify_frozen_policy(paths.grading)
    cases = build_panel()
    case_order = tuple(case.case_id for case in cases)
    if case_order != (*_CALLED_V9_CASES, *_UNCALLED_V9_CASES):
        raise V10ExecutionPreflightError("exposed case order changed")
    v9_result = _object(json.loads(paths.v9_result.read_text(encoding="utf-8")))
    v9_metrics = {
        cast("str", item["case_id"]): item for item in _objects(v9_result["cases"])
    }
    if tuple(v9_metrics) != _CALLED_V9_CASES:
        raise V10ExecutionPreflightError("V9 baseline case order changed")
    root = REPO
    return {
        "schema_version": "artana.staged_generalization.v10_exposed_run.v1",
        "experiment_id": EXPERIMENT_ID,
        "authorization": "PREREGISTERED_EXPOSED_DEVELOPMENT_MODEL_EXECUTION",
        "qualification_credit": False,
        "supersedes_terminal": "MODEL_CORRECTION_REQUIRED",
        "single_scientific_change": "NAMED_BIOMEDICAL_OCCURRENCE_BOUNDARY",
        "frozen_state": {
            "offline_v10_preregistration_sha256": _sha256(
                paths.offline_preregistration
            ),
            "offline_v10_preflight": offline,
            "historical_v9_provenance_sha256": _sha256(
                paths.historical_provenance
            ),
            "historical_v9_disposition": provenance["disposition"],
            "panel_sha256": _sha256(paths.panel),
            "prompt_sha256": _sha256(paths.prompt),
            "schema_sha256": _canonical_sha256(
                V9StagedGeneralizationOutput.model_json_schema()
            ),
            "schema_basis": "UNCHANGED_V9",
            "provider_format_sha256": _canonical_sha256(provider_format()),
            "case_order": list(case_order),
            "expected_maximum_provider_calls": GLOBAL_MAX_CALLS,
            "source_sha256_by_case": {
                case.case_id: case.source_sha256 for case in cases
            },
            "provider_input_sha256_by_case": {
                case.case_id: hashlib.sha256(
                    provider_input(paths, case.case_id).encode()
                ).hexdigest()
                for case in cases
            },
            "authoritative_references": {
                "embedded_panel_reference_sha256": _sha256(paths.panel),
                "grading_policy_sha256": policy_sha256(policy),
                "review_artifact_sha256": policy.review_artifact_sha256,
                "grading_artifact_sha256": {
                    "packet": _sha256(paths.grading.packet),
                    "evidence": _sha256(paths.grading.evidence),
                    "schema": _sha256(paths.grading.schema),
                    "first_review": _sha256(paths.grading.first_review),
                    "second_review": _sha256(paths.grading.second_review),
                    "tiebreaker_review": _sha256(paths.grading.tiebreaker_review),
                    "policy": _sha256(paths.grading.policy),
                },
            },
            "v9_baseline": {
                "preregistration_sha256": _sha256(paths.v9_preregistration),
                "result_sha256": _sha256(paths.v9_result),
                "raw_output_sha256_by_case": {
                    case_id: _sha256(paths.v9_raw_output(case_id))
                    for case_id in _CALLED_V9_CASES
                },
                "metrics_sha256_by_case": {
                    case_id: _canonical_sha256(v9_metrics[case_id])
                    for case_id in _CALLED_V9_CASES
                },
                "called_case_ids": list(_CALLED_V9_CASES),
                "uncalled_case_ids": list(_UNCALLED_V9_CASES),
                "historical_result_immutable": True,
                "historical_result_rescored": False,
            },
            "evaluator": {
                "kind": "FROZEN_V9_EXACT_OCCURRENCE_AND_DUAL_LANE_GRADER",
                "implementation_sha256": _hash_files(root, _EVALUATOR_FILES),
                "changed": False,
            },
            "current_receipt_code_sha256": _hash_files(root, _RECEIPT_FILES),
            "execution_implementation_sha256": _hash_files(
                root,
                _IMPLEMENTATION_FILES,
            ),
            "provider": {
                "model": f"openai:{MODEL}",
                "reasoning_effort": REASONING_EFFORT,
                "transport": "DIRECT_OPENAI_BACKGROUND_RESPONSES",
                "background": True,
                "store": True,
                "confirmation_retrieval_required": True,
                "input_item_retrieval_required": True,
                "provider_retries": 0,
                "fallback": False,
                "application_max_output_tokens": None,
                "application_max_total_tokens": None,
            },
            "operational_budget": {
                "cumulative_max_cost_usd": GLOBAL_MAX_COST_USD,
                "check_before_each_creation": True,
                "record_actual_spend_after_each_call": True,
                "stop_before_next_call_when_exhausted": True,
                "token_latency_and_cost_are_record_only": True,
                "scientific_results_are_not_retroactively_erased": True,
            },
        },
        "acceptance": {
            "all_cases_scientific_grader_pass": True,
            "target_case_id": "generalization-uncertainty",
            "required_target_occurrence": "SLC12A3",
            "forbidden_target_suffix_expansion": "SLC12A3 gene",
            "protected_case_id": "generalization-explicit-nested-cause",
            "protected_lexicalized_names": [
                "HCMV immediate-early proteins",
                "immediate-early proteins",
            ],
            "non_target_participants_correct_and_complete": True,
            "no_v9_boolean_field_regression": True,
            "no_v9_error_count_regression": True,
            "event_inventory_types_roles_links_and_axes_preserved_or_improved": True,
            "exact_occurrence_grounding": True,
            "all_receipts_valid": True,
            "provider_retries": 0,
            "duplicate_creation_calls": 0,
            "graph_writes": 0,
        },
        "stopping_rules": {
            "sequential_fail_fast": True,
            "first_scientific_failure": True,
            "invalid_schema_custody_or_exactly_once": True,
            "operational_budget_exhaustion": True,
            "provider_outage_or_missing_secret": True,
            "no_prompt_patch_or_v11_after_failure": True,
        },
        "rules": {
            "exposed_public_cases_only": True,
            "fresh_case_calls_allowed": False,
            "fresh_cases_consumed": 0,
            "agent_inputs_exclude": [
                "expected participant spans",
                "direct CG answers",
                "grader internals",
                "V2 Fresh-CG output",
                "V3 corrected reference",
                "output-tailored examples",
            ],
            "one_creation_call_per_case": True,
            "provider_retries": 0,
            "graph_writes": False,
            "trusted_graph_promotion": False,
            "optional_consumed_case_diagnostic_requires_full_public_gate_pass": True,
        },
        "terminal_decisions": [
            "V10_EXPOSED_GATE_PASS_READY_FOR_NEW_FRESH_PREREGISTRATION",
            "V10_EXPOSED_GATE_FAIL_MODEL_CORRECTION_REQUIRED",
            "INVALID_V10_EXECUTION",
            "BLOCKED_HISTORICAL_REPRODUCIBILITY_UNRESOLVED",
        ],
    }


def write_candidate(paths: V10ExecutionPaths = DEFAULT_PATHS) -> None:
    paths.execution_preregistration.parent.mkdir(parents=True, exist_ok=True)
    paths.execution_preregistration.write_text(
        json.dumps(build_preregistration(paths), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify(
    paths: V10ExecutionPaths = DEFAULT_PATHS,
    *,
    remote_gate: bool = False,
) -> dict[str, object]:
    loaded = _object(
        json.loads(paths.execution_preregistration.read_text(encoding="utf-8"))
    )
    expected = build_preregistration(paths)
    if loaded != expected:
        raise V10ExecutionPreflightError(
            "V10 execution preregistration differs from recomputed frozen state"
        )
    if remote_gate:
        _verify_remote_head(REPO)
    return loaded


def _verify_remote_head(repo: Path) -> None:
    branch = _git(repo, "branch", "--show-current")
    if not branch:
        raise V10ExecutionPreflightError("detached HEAD cannot execute V10")
    local = _git(repo, "rev-parse", "HEAD")
    remote_line = _git(repo, "ls-remote", "--heads", "origin", branch)
    fields = remote_line.split()
    if len(fields) != _REMOTE_REF_FIELD_COUNT or fields[0] != local:
        raise V10ExecutionPreflightError("local and remote execution HEAD differ")


def _git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed local Git command.
        ["git", *arguments],  # noqa: S607
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise V10ExecutionPreflightError(completed.stderr.strip())
    return completed.stdout.strip()


def _hash_files(root: Path, files: tuple[str, ...]) -> dict[str, str]:
    return {file_name: _sha256(root / file_name) for file_name in files}


def _objects(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise V10ExecutionPreflightError("expected JSON array")
    return [_object(item) for item in value]


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise V10ExecutionPreflightError("expected JSON object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "V10ExecutionPreflightError",
    "build_preregistration",
    "provider_input",
    "verify",
    "write_candidate",
]
