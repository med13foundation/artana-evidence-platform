"""Build and verify the forward-only V11 exposed-gate preregistration."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import cast

from scripts.validation.public_gold.staged_event.generalization.grading.artifacts import (
    verify_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    policy_sha256,
)
from scripts.validation.public_gold.staged_event.generalization.panel import (
    GeneralizationCase,
    agent_case,
    build_panel,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_provider import (
    provider_format,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.historical_v9 import (
    verify_provenance,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
    EXPERIMENT_ID,
    GLOBAL_MAX_CALLS,
    GLOBAL_MAX_COST_USD,
    MODEL,
    REASONING_EFFORT,
    REPO,
    V11ExecutionPaths,
)

_CALLED_V9_CASES = (
    "generalization-comparison-canary",
    "generalization-null-statistics",
    "generalization-negated-association",
    "generalization-uncertainty",
    "generalization-drug-sensitivity",
)
_CALLED_V10_CASES = (
    "generalization-comparison-canary",
    "generalization-null-statistics",
    "generalization-negated-association",
)
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
    "scripts/run_staged_generalization_v11_exposed.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v11/"
    "acceptance.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v11/"
    "accounting.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v11/config.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v11/"
    "preflight.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v11/provider.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v11/runner.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v11/terminal.py",
)
_FORBIDDEN_AGENT_INPUT_TERMS = (
    '"reference"',
    "acceptable_texts",
    "expected participant",
    "direct CG",
    "Fresh-CG V2",
    "V3 corrected reference",
    "grader policy",
    "osteonectin",
)
_V10_PROMPT = REPO / "docs/validation/prompts/2026-07-22-staged-generalization-v10.md"
_REMOTE_REF_FIELD_COUNT = 2
_SEMANTIC_SECTION = """Semantic-axis evidence grounding:

- Every `semantic_axes.evidence_items` entry must be exact source text that
  resolves uniquely within the supplied local source context.
- Prefer the complete exact source sentence containing the scientific
  proposition and its event trigger.
- When the same complete sentence supports several semantic axes, reuse that
  same sentence rather than splitting it into fragments.
- Do not return an isolated participant name, abbreviation, trigger, or phrase
  when it is repeated or otherwise ambiguous in the supplied source.
- This rule changes only evidence anchoring. It does not change the event,
  participant, role, direction, comparison, polarity, uncertainty, statistics,
  author interpretation, or scientific meaning.

"""


class V11PreflightError(RuntimeError):
    """V11 differs from its frozen single-change contract."""


def ordered_cases() -> tuple[GeneralizationCase, ...]:
    by_id = {case.case_id: case for case in build_panel()}
    if set(by_id) != set(CASE_ORDER):
        raise V11PreflightError("V11 panel membership changed")
    return tuple(by_id[case_id] for case_id in CASE_ORDER)


def provider_input(paths: V11ExecutionPaths, case_id: str) -> str:
    cases = {case.case_id: case for case in ordered_cases()}
    case = cases.get(case_id)
    if case is None:
        raise V11PreflightError(f"unknown exposed case: {case_id}")
    _verify_prompt_delta(paths)
    value = (
        paths.prompt.read_text(encoding="utf-8")
        + "\n\n--- FROZEN EXPOSED CASE ---\n"
        + json.dumps(agent_case(case), indent=2, sort_keys=True)
        + "\n--- END FROZEN EXPOSED CASE ---\n"
    )
    present = [term for term in _FORBIDDEN_AGENT_INPUT_TERMS if term in value]
    if present:
        raise V11PreflightError(
            f"V11 provider input exposes forbidden material: {present}"
        )
    return value


def build_preregistration(
    paths: V11ExecutionPaths = DEFAULT_PATHS,
) -> dict[str, object]:
    """Recompute V11 inputs, baselines, evaluator, policy, and custody pins."""

    _verify_prompt_delta(paths)
    root_cause = _verify_root_cause(paths)
    provenance = verify_provenance()
    policy = verify_frozen_policy(paths.grading)
    cases = ordered_cases()
    v9_metrics = _case_metrics(paths.v9_result)
    v10_metrics = _case_metrics(paths.v10_result)
    if tuple(v9_metrics) != _CALLED_V9_CASES:
        raise V11PreflightError("V9 baseline case order changed")
    if tuple(v10_metrics) != _CALLED_V10_CASES:
        raise V11PreflightError("V10 baseline case order changed")
    return {
        "schema_version": "artana.staged_generalization.v11_exposed_run.v1",
        "experiment_id": EXPERIMENT_ID,
        "authorization": "PREREGISTERED_EXPOSED_DEVELOPMENT_MODEL_EXECUTION",
        "qualification_credit": False,
        "single_scientific_change": ("UNIQUE_COMPLETE_SEMANTIC_EVIDENCE_GROUNDING"),
        "root_cause_classification": root_cause["classification"],
        "frozen_state": {
            "root_cause_artifact_sha256": _sha256(paths.root_cause),
            "historical_v9_provenance_sha256": _sha256(paths.historical_provenance),
            "historical_v9_disposition": provenance["disposition"],
            "panel_sha256": _sha256(paths.panel),
            "prompt_sha256": _sha256(paths.prompt),
            "prompt_basis": "V10_PLUS_ONE_SEMANTIC_EVIDENCE_SECTION",
            "schema_sha256": _canonical_sha256(
                V9StagedGeneralizationOutput.model_json_schema()
            ),
            "schema_basis": "UNCHANGED_V9_V10",
            "provider_format_sha256": _canonical_sha256(provider_format()),
            "case_order": list(CASE_ORDER),
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
            "v9_baseline": _baseline(
                preregistration=paths.v9_preregistration,
                result=paths.v9_result,
                called=_CALLED_V9_CASES,
                metrics=v9_metrics,
                raw_output=paths.v9_raw_output,
            ),
            "v10_baseline": {
                **_baseline(
                    preregistration=paths.v10_preregistration,
                    result=paths.v10_result,
                    called=_CALLED_V10_CASES,
                    metrics=v10_metrics,
                    raw_output=paths.v10_raw_output,
                ),
                "report_sha256": _sha256(paths.v10_report),
                "terminal": ("V10_EXPOSED_GATE_FAIL_MODEL_CORRECTION_REQUIRED"),
                "historical_result_immutable": True,
                "historical_result_rescored": False,
            },
            "evaluator": {
                "kind": "FROZEN_V9_EXACT_OCCURRENCE_AND_DUAL_LANE_GRADER",
                "implementation_sha256": _hash_files(REPO, _EVALUATOR_FILES),
                "changed": False,
            },
            "current_receipt_code_sha256": _hash_files(REPO, _RECEIPT_FILES),
            "execution_implementation_sha256": _hash_files(
                REPO,
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
            "negated_grounding_case_id": "generalization-negated-association",
            "negated_semantic_evidence_is_complete_event_sentence": True,
            "all_semantic_evidence_items_resolve_uniquely": True,
            "protected_case_id": "generalization-explicit-nested-cause",
            "protected_lexicalized_names": [
                "HCMV immediate-early proteins",
                "immediate-early proteins",
            ],
            "no_v9_boolean_field_regression": True,
            "no_v9_error_count_regression": True,
            "no_v10_boolean_field_regression": True,
            "no_v10_error_count_regression": True,
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
            "no_prompt_patch_or_v12_after_failure": True,
        },
        "rules": {
            "exposed_public_cases_only": True,
            "fresh_case_calls_allowed": False,
            "fresh_cases_consumed": 0,
            "agent_inputs_exclude": [
                "expected participant spans",
                "direct CG answers",
                "grader internals",
                "Fresh-CG V2 output",
                "V3 corrected reference",
                "SLC12A3 expected answer",
                "osteonectin expected answer",
                "output-tailored examples",
            ],
            "one_creation_call_per_case": True,
            "provider_retries": 0,
            "graph_writes": False,
            "trusted_graph_promotion": False,
        },
        "terminal_decisions": [
            "V11_EXPOSED_GATE_PASS_READY_FOR_NEW_FRESH_PREREGISTRATION",
            "V11_EXPOSED_GATE_FAIL_BOUNDARY",
            "V11_EXPOSED_GATE_FAIL_GROUNDING",
            "V11_EXPOSED_GATE_FAIL_UNRELATED_REGRESSION",
            "INVALID_V11_EXECUTION",
        ],
    }


def write_candidate(paths: V11ExecutionPaths = DEFAULT_PATHS) -> None:
    paths.preregistration.parent.mkdir(parents=True, exist_ok=True)
    paths.preregistration.write_text(
        json.dumps(build_preregistration(paths), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify(
    paths: V11ExecutionPaths = DEFAULT_PATHS,
    *,
    remote_gate: bool = False,
) -> dict[str, object]:
    loaded = _object(json.loads(paths.preregistration.read_text(encoding="utf-8")))
    expected = build_preregistration(paths)
    if loaded != expected:
        raise V11PreflightError(
            "V11 preregistration differs from recomputed frozen state"
        )
    if remote_gate:
        _verify_remote_head(REPO)
    return loaded


def _verify_prompt_delta(paths: V11ExecutionPaths) -> None:
    v10 = _V10_PROMPT.read_text(encoding="utf-8")
    marker = "Named biomedical occurrence boundary:\n"
    expected = v10.replace(
        "# Staged Scientific Event Generalization V10",
        "# Staged Scientific Event Generalization V11",
        1,
    ).replace(marker, _SEMANTIC_SECTION + marker, 1)
    if paths.prompt.read_text(encoding="utf-8") != expected:
        raise V11PreflightError("V11 prompt is not the exact single-change delta")


def _verify_root_cause(paths: V11ExecutionPaths) -> dict[str, object]:
    artifact = _object(json.loads(paths.root_cause.read_text(encoding="utf-8")))
    if artifact.get("classification") != "SEMANTIC_EVIDENCE_PROMPT_CONTRACT_GAP":
        raise V11PreflightError("V10 root cause classification changed")
    frozen_hashes = cast("dict[str, object]", artifact["frozen_artifact_sha256"])
    expected_hashes = {
        "evaluator": _sha256(
            REPO / "scripts/validation/public_gold/staged_event/generalization/"
            "evaluation.py"
        ),
        "resolver": _sha256(
            REPO / "scripts/validation/public_gold/staged_event/generalization/"
            "anchors.py"
        ),
        "schema": _sha256(
            REPO / "scripts/validation/public_gold/staged_event/generalization/"
            "contracts.py"
        ),
        "v10_evaluation": _sha256(
            REPO / "docs/validation/evaluations/"
            "2026-07-22-staged-generalization-v10-exposed-run-v1-"
            "generalization-negated-association-evaluation.json"
        ),
        "v10_prompt": _sha256(_V10_PROMPT),
        "v10_raw_output": _sha256(
            paths.v10_raw_output("generalization-negated-association")
        ),
        "v9_prompt": _sha256(
            REPO / "docs/validation/prompts/2026-07-22-staged-generalization-v9.md"
        ),
        "v9_raw_output": _sha256(
            paths.v9_raw_output("generalization-negated-association")
        ),
    }
    if frozen_hashes != expected_hashes:
        raise V11PreflightError("V10 root-cause evidence hashes changed")
    case = next(
        item
        for item in build_panel()
        if item.case_id == "generalization-negated-association"
    )
    counts = cast("dict[str, object]", artifact["source_occurrence_counts"])
    expected_counts = {
        "local_context": {
            phrase: case.local_context.count(phrase)
            for phrase in (
                "OS",
                "steroid dose before ICI initiation",
                "was no longer associated with",
            )
        },
        "source": {
            phrase: case.source.count(phrase)
            for phrase in (
                "OS",
                "steroid dose before ICI initiation",
                "was no longer associated with",
            )
        },
    }
    if counts != expected_counts:
        raise V11PreflightError("V10 grounding occurrence evidence changed")
    evidence = cast("dict[str, object]", artifact["v10_evidence"])
    v10_output = V9StagedGeneralizationOutput.model_validate_json(
        paths.v10_raw_output(case.case_id).read_text(encoding="utf-8")
    )
    if evidence["semantic_axes_evidence_items"] != list(
        v10_output.semantic_axes[0].evidence_items
    ):
        raise V11PreflightError("V10 semantic evidence diagnosis changed")
    v10_result = _object(json.loads(paths.v10_result.read_text(encoding="utf-8")))
    if v10_result.get("decision") != (
        "V10_EXPOSED_GATE_FAIL_MODEL_CORRECTION_REQUIRED"
    ):
        raise V11PreflightError("sealed V10 terminal changed")
    return artifact


def _baseline(
    *,
    preregistration: Path,
    result: Path,
    called: tuple[str, ...],
    metrics: dict[str, dict[str, object]],
    raw_output: Callable[[str], Path],
) -> dict[str, object]:
    return {
        "preregistration_sha256": _sha256(preregistration),
        "result_sha256": _sha256(result),
        "raw_output_sha256_by_case": {
            case_id: _sha256(raw_output(case_id)) for case_id in called
        },
        "metrics_sha256_by_case": {
            case_id: _canonical_sha256(metrics[case_id]) for case_id in called
        },
        "called_case_ids": list(called),
    }


def _case_metrics(path: Path) -> dict[str, dict[str, object]]:
    loaded = _object(json.loads(path.read_text(encoding="utf-8")))
    result: dict[str, dict[str, object]] = {}
    for item in _objects(loaded["cases"]):
        case_id = item.get("case_id")
        if not isinstance(case_id, str):
            raise V11PreflightError("baseline case metrics are malformed")
        result[case_id] = item
    return result


def _verify_remote_head(repo: Path) -> None:
    branch = _git(repo, "branch", "--show-current")
    if not branch:
        raise V11PreflightError("detached HEAD cannot execute V11")
    local = _git(repo, "rev-parse", "HEAD")
    fields = _git(repo, "ls-remote", "--heads", "origin", branch).split()
    if len(fields) != _REMOTE_REF_FIELD_COUNT or fields[0] != local:
        raise V11PreflightError("local and remote execution HEAD differ")


def _git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed local Git command.
        ["git", *arguments],  # noqa: S607
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise V11PreflightError(completed.stderr.strip())
    return completed.stdout.strip()


def _hash_files(root: Path, files: tuple[str, ...]) -> dict[str, str]:
    return {file_name: _sha256(root / file_name) for file_name in files}


def _objects(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise V11PreflightError("expected JSON array")
    return [_object(item) for item in value]


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise V11PreflightError("expected JSON object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "V11PreflightError",
    "build_preregistration",
    "ordered_cases",
    "provider_input",
    "verify",
    "write_candidate",
]
