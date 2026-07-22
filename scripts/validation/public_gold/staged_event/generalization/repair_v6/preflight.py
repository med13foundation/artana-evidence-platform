"""Build and verify the V6 referential-grounding preregistration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.validation.public_gold.staged_event.generalization.contracts import (
    StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.grading.artifacts import (
    verify_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    policy_sha256,
)
from scripts.validation.public_gold.staged_event.generalization.panel import (
    agent_case,
    build_panel,
    panel_json,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v6.config import (
    EXPERIMENT_ID,
    GLOBAL_MAX_CALLS,
    GLOBAL_MAX_COST_USD,
    MAX_COST_USD,
    MAX_LATENCY_SECONDS,
    MAX_OUTPUT_TOKENS,
    MAX_TOTAL_TOKENS,
    MODEL,
    REASONING_EFFORT,
    ExperimentPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v6.provider import (
    provider_format,
)

CODE_FILES = (
    "scripts/run_staged_generalization_v6.py",
    "scripts/validation/provider_receipt_boundary/__init__.py",
    "scripts/validation/provider_receipt_boundary/canonical_payload.py",
    "scripts/validation/provider_receipt_boundary/contracts.py",
    "scripts/validation/provider_receipt_boundary/identity.py",
    "scripts/validation/provider_receipt_boundary/structural_diff.py",
    "scripts/validation/provider_receipt_boundary/validation.py",
    "scripts/validation/provider_receipt_boundary/background/__init__.py",
    "scripts/validation/provider_receipt_boundary/background/contracts.py",
    "scripts/validation/provider_receipt_boundary/background/execution.py",
    "scripts/validation/provider_receipt_boundary/background/polling.py",
    "scripts/validation/provider_receipt_boundary/background/states.py",
    "scripts/validation/public_gold/lossless_event_provider.py",
    "scripts/validation/public_gold/staged_event/context_experiment/role_alignment/policy.py",
    "scripts/validation/public_gold/staged_event/context_experiment/source_first/attempts.py",
    "scripts/validation/public_gold/staged_event/context_experiment/source_first/custody.py",
    "scripts/validation/public_gold/staged_event/generalization/anchors.py",
    "scripts/validation/public_gold/staged_event/generalization/contracts.py",
    "scripts/validation/public_gold/staged_event/generalization/panel.py",
    "scripts/validation/public_gold/staged_event/generalization/span_identity.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/agreement.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/artifacts.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/config.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/contracts.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/evaluation.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/policy.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v6/config.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v6/preflight.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v6/provider.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v6/runner.py",
)
PIVOT_BASIS_FILES = (
    "docs/validation/preregistrations/2026-07-22-staged-generalization-v5.json",
    "docs/validation/results/2026-07-22-staged-generalization-v5.json",
    "docs/validation/results/2026-07-22-staged-generalization-v5-generalization-uncertainty-raw.json",
    "docs/validation/reports/2026-07-22-staged-generalization-v5-grader-implementation.md",
)
_FORBIDDEN_PROMPT_CASE_TERMS = (
    "generalization-uncertainty",
    "947 variants",
    "SLC12A3",
    "the majority of which",
)


class V6PreflightError(RuntimeError):
    """The frozen V6 experiment state changed or is incomplete."""


def provider_input(paths: ExperimentPaths, case_id: str) -> str:
    cases = {case.case_id: case for case in build_panel()}
    case = cases.get(case_id)
    if case is None:
        raise V6PreflightError(f"unknown panel case: {case_id}")
    _validate_prompt(paths.prompt)
    return (
        paths.prompt.read_text(encoding="utf-8")
        + "\n\n--- FROZEN EXPOSED CASE ---\n"
        + json.dumps(agent_case(case), indent=2, sort_keys=True)
        + "\n--- END FROZEN EXPOSED CASE ---\n"
    )


def build_preregistration(paths: ExperimentPaths) -> dict[str, object]:
    cases = build_panel()
    root = _repo_root()
    _validate_prompt(paths.prompt)
    policy = verify_frozen_policy(paths.grading)
    v5_result = _load_v5_result(root / PIVOT_BASIS_FILES[1])
    return {
        "schema_version": "artana.staged_generalization.v6",
        "experiment_id": EXPERIMENT_ID,
        "supersedes_terminal": v5_result["decision"],
        "authorization": "EXPOSED_DEVELOPMENT_ONLY",
        "frozen_state": {
            "panel_sha256": _file_sha256(paths.panel),
            "prompt_sha256": _file_sha256(paths.prompt),
            "schema_sha256": _canonical_sha256(
                StagedGeneralizationOutput.model_json_schema()
            ),
            "provider_format_sha256": _canonical_sha256(provider_format()),
            "source_sha256_by_case": {
                case.case_id: case.source_sha256 for case in cases
            },
            "provider_input_sha256_by_case": {
                case.case_id: hashlib.sha256(
                    provider_input(paths, case.case_id).encode()
                ).hexdigest()
                for case in cases
            },
            "case_order": [case.case_id for case in cases],
            "canary_case_id": cases[0].case_id,
            "model": f"openai:{MODEL}",
            "reasoning_effort": REASONING_EFFORT,
            "grading": {
                "policy_sha256": policy_sha256(policy),
                "review_artifact_sha256": policy.review_artifact_sha256,
                "benchmark_lane": policy.benchmark_lane,
                "qualification_credit": policy.qualification_credit,
                "graph_promotion_allowed": policy.graph_promotion_allowed,
            },
            "pivot_basis_sha256": {
                relative: _file_sha256(root / relative)
                for relative in PIVOT_BASIS_FILES
            },
            "budgets": {
                "global_max_creation_calls": GLOBAL_MAX_CALLS,
                "global_max_cost_usd": GLOBAL_MAX_COST_USD,
                "per_call_max_output_tokens": MAX_OUTPUT_TOKENS,
                "per_call_max_total_tokens": MAX_TOTAL_TOKENS,
                "per_call_max_latency_seconds": MAX_LATENCY_SECONDS,
                "per_call_max_cost_usd": MAX_COST_USD,
                "provider_retries": 0,
            },
            "code_sha256": {
                relative: _file_sha256(root / relative) for relative in CODE_FILES
            },
        },
        "change_control": {
            "single_scientific_change": "SOURCE_GENERAL_REFERENTIAL_GROUNDING",
            "referential_rule": (
                "Resolve referring grammar to a unique explicit antecedent and "
                "ground the participant to the antecedent source span."
            ),
            "uncertainty_rule": (
                "Classify uncertainty from proposition content independently "
                "from whether the sentence asserts that content."
            ),
            "historical_v5_rescored": False,
            "grader_changed": False,
            "panel_changed": False,
            "schema_changed": False,
            "model_changed": False,
        },
        "rules": {
            "agent_inputs_exclude": [
                "grader policy",
                "expected roles",
                "event counts",
                "gold labels",
                "benchmark projections",
                "V5 output",
                "case-specific correction",
            ],
            "canary_first": True,
            "one_creation_call_per_case": True,
            "silent_retries": 0,
            "fallback": False,
            "untouched_sources": False,
            "graph_writes": False,
            "promotion": False,
            "benchmark_projection": "SEPARATE_EVALUATION_ONLY_REVIEW_ONLY",
            "terminal_decisions": [
                "ADVANCE_STAGED_GENERALIZATION",
                "PIVOT_WITH_EVIDENCE",
            ],
        },
        "acceptance": {
            "all_required_core_complete": True,
            "all_cases_pass": True,
            "ambiguous_context_count": 0,
            "unsupported_claim_count": 0,
            "contradiction_count": 0,
            "receipt_and_budget_validity": "ALL_CALLS",
            "source_meaning_preserved": True,
        },
    }


def write_candidate(paths: ExperimentPaths) -> None:
    paths.panel.parent.mkdir(parents=True, exist_ok=True)
    paths.panel.write_text(
        json.dumps(panel_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths.preregistration.parent.mkdir(parents=True, exist_ok=True)
    paths.preregistration.write_text(
        json.dumps(build_preregistration(paths), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify(paths: ExperimentPaths) -> dict[str, object]:
    loaded: object = json.loads(paths.preregistration.read_text(encoding="utf-8"))
    expected = build_preregistration(paths)
    if loaded != expected:
        raise V6PreflightError(
            "V6 preregistration differs from independently recomputed frozen state"
        )
    if not isinstance(loaded, dict):
        raise V6PreflightError("V6 preregistration must be an object")
    return loaded


def _validate_prompt(path: Path) -> None:
    prompt = path.read_text(encoding="utf-8")
    normalized = " ".join(prompt.split())
    present = [term for term in _FORBIDDEN_PROMPT_CASE_TERMS if term in normalized]
    if present:
        raise V6PreflightError(f"V6 prompt contains case-specific terms: {present}")
    required = (
        "ground the participant to the antecedent's exact contiguous source text",
        "independent of whether the sentence grammatically asserts that proposition",
    )
    if any(item not in normalized for item in required):
        raise V6PreflightError("V6 prompt lacks the preregistered source-general rules")


def _load_v5_result(path: Path) -> dict[str, object]:
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise V6PreflightError("V5 pivot basis is malformed")
    if loaded.get("decision") != "PIVOT_WITH_EVIDENCE":
        raise V6PreflightError("V5 pivot basis is not terminal")
    if loaded.get("all_receipts_valid") is not True:
        raise V6PreflightError("V5 pivot basis lacks valid receipt evidence")
    if loaded.get("stopped_after_case_id") != "generalization-uncertainty":
        raise V6PreflightError("V5 pivot basis changed failure family")
    return loaded


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "CODE_FILES",
    "PIVOT_BASIS_FILES",
    "V6PreflightError",
    "build_preregistration",
    "provider_input",
    "verify",
    "write_candidate",
]
