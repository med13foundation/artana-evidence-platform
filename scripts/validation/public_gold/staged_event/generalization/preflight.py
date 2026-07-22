"""Build and independently verify the frozen generalization preregistration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.validation.public_gold.staged_event.generalization.config import (
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
from scripts.validation.public_gold.staged_event.generalization.contracts import (
    StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.panel import (
    agent_case,
    build_panel,
    panel_json,
)
from scripts.validation.public_gold.staged_event.generalization.provider import (
    provider_format,
)

CODE_FILES = (
    "scripts/validation/public_gold/staged_event/generalization/anchors.py",
    "scripts/validation/public_gold/staged_event/generalization/config.py",
    "scripts/validation/public_gold/staged_event/generalization/contracts.py",
    "scripts/validation/public_gold/staged_event/generalization/evaluation.py",
    "scripts/validation/public_gold/staged_event/generalization/panel.py",
    "scripts/validation/public_gold/staged_event/generalization/preflight.py",
    "scripts/validation/public_gold/staged_event/generalization/provider.py",
    "scripts/validation/public_gold/staged_event/generalization/runner.py",
    "scripts/validation/public_gold/staged_event/context_experiment/role_alignment/policy.py",
)


class GeneralizationPreflightError(RuntimeError):
    """Frozen experiment state is absent, malformed, or changed."""


def provider_input(paths: ExperimentPaths, case_id: str) -> str:
    cases = {case.case_id: case for case in build_panel()}
    case = cases.get(case_id)
    if case is None:
        raise GeneralizationPreflightError(f"unknown panel case: {case_id}")
    return (
        paths.prompt.read_text(encoding="utf-8")
        + "\n\n--- FROZEN EXPOSED CASE ---\n"
        + json.dumps(agent_case(case), indent=2, sort_keys=True)
        + "\n--- END FROZEN EXPOSED CASE ---\n"
    )


def build_preregistration(paths: ExperimentPaths) -> dict[str, object]:
    cases = build_panel()
    root = _repo_root()
    return {
        "schema_version": "artana.staged_generalization.v3",
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
        "rules": {
            "agent_inputs_exclude": [
                "expected roles",
                "event counts",
                "gold labels",
                "benchmark projections",
            ],
            "canary_first": True,
            "one_creation_call_per_case": True,
            "silent_retries": 0,
            "fallback": False,
            "untouched_sources": False,
            "graph_writes": False,
            "promotion": False,
            "benchmark_projection": "EVALUATION_ONLY_REVIEW_ONLY",
            "terminal_decisions": [
                "ADVANCE_STAGED_GENERALIZATION",
                "PIVOT_WITH_EVIDENCE",
            ],
        },
        "acceptance": {
            "all_cases_pass": True,
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
        raise GeneralizationPreflightError(
            "preregistration differs from independently recomputed frozen state"
        )
    if not isinstance(loaded, dict):
        raise GeneralizationPreflightError("preregistration must be an object")
    return loaded


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "GeneralizationPreflightError",
    "build_preregistration",
    "provider_input",
    "verify",
    "write_candidate",
]
