"""Build and verify the V5 dual-lane grader preregistration."""

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
from scripts.validation.public_gold.staged_event.generalization.grading.config import (
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
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    policy_sha256,
)
from scripts.validation.public_gold.staged_event.generalization.grading.provider import (
    provider_format,
)
from scripts.validation.public_gold.staged_event.generalization.panel import (
    agent_case,
    build_panel,
    panel_json,
)

CODE_FILES = (
    "scripts/validation/public_gold/staged_event/context_experiment/role_alignment/policy.py",
    "scripts/validation/public_gold/staged_event/generalization/anchors.py",
    "scripts/validation/public_gold/staged_event/generalization/contracts.py",
    "scripts/validation/public_gold/staged_event/generalization/evaluation.py",
    "scripts/validation/public_gold/staged_event/generalization/panel.py",
    "scripts/validation/public_gold/staged_event/generalization/span_identity.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/agreement.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/artifacts.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/config.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/contracts.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/evaluation.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/offline_replay.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/packets.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/policy.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/preflight.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/provider.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/runner.py",
)


class GradingPreflightError(RuntimeError):
    """The independently frozen V5 experiment state changed or is incomplete."""


def provider_input(paths: ExperimentPaths, case_id: str) -> str:
    cases = {case.case_id: case for case in build_panel()}
    case = cases.get(case_id)
    if case is None:
        raise GradingPreflightError(f"unknown panel case: {case_id}")
    return (
        paths.prompt.read_text(encoding="utf-8")
        + "\n\n--- FROZEN EXPOSED CASE ---\n"
        + json.dumps(agent_case(case), indent=2, sort_keys=True)
        + "\n--- END FROZEN EXPOSED CASE ---\n"
    )


def build_preregistration(paths: ExperimentPaths) -> dict[str, object]:
    cases = build_panel()
    root = _repo_root()
    policy = verify_frozen_policy(paths.grading)
    replay = _load_replay(paths.offline_replay)
    return {
        "schema_version": "artana.staged_generalization.v5",
        "experiment_id": EXPERIMENT_ID,
        "supersedes_terminal": "PIVOT_WITH_EVIDENCE",
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
                "blinded_packet_sha256": _file_sha256(paths.grading.packet),
                "review_schema_sha256": _file_sha256(paths.grading.schema),
                "primary_source_evidence_sha256": _file_sha256(paths.grading.evidence),
                "policy_sha256": policy_sha256(policy),
                "review_artifact_sha256": policy.review_artifact_sha256,
                "offline_v4_replay_sha256": _file_sha256(paths.offline_replay),
                "offline_v4_replay_decision": replay["decision"],
            },
            "benchmark_custody": {
                "official_task_url": (
                    "https://2013.bionlp-st.org/tasks/cancer-genetics-cg-task"
                ),
                "official_task_retrieved_sha256": (
                    "1c45043bfe12bd2610054a93e27fa98e9dd6b6b17663c5e252e51fd5e6420c92"
                ),
                "task_paper_url": "https://aclanthology.org/W13-2008.pdf",
                "task_paper_retrieved_sha256": (
                    "8e0e4301d869fec7e2e79c3852c0333582b587dda592464ccde05ed975379e07"
                ),
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
        "rules": {
            "permitted_change": (
                "Replace closed minimal-inventory equality with independently frozen "
                "required-core plus permitted-context grading."
            ),
            "historical_v4_rescored": False,
            "offline_v4_replay_qualification_credit": False,
            "required_core_cannot_be_replaced_by_context": True,
            "unlisted_additions": "UNSUPPORTED",
            "ambiguous_additions": "REVIEW_ONLY_BLOCKS_PASS",
            "permitted_context_requirements": [
                "exact_source_grounded",
                "correct_entity_type",
                "nonduplicative",
                "explicitly_allowed_role",
                "linked_to_required_core_event",
            ],
            "agent_inputs_exclude": [
                "grader policy",
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
        raise GradingPreflightError(
            "V5 preregistration differs from independently recomputed frozen state"
        )
    if not isinstance(loaded, dict):
        raise GradingPreflightError("V5 preregistration must be an object")
    return loaded


def _load_replay(path: Path) -> dict[str, object]:
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise GradingPreflightError("offline replay must be an object")
    if loaded.get("decision") not in {
        "OFFLINE_DUAL_LANE_GRADER_PASS",
        "OFFLINE_DUAL_LANE_GRADER_FAIL",
    }:
        raise GradingPreflightError("offline V4 dual-lane replay is incomplete")
    if loaded.get("historical_result_changed") is not False:
        raise GradingPreflightError("offline replay changed the historical V4 result")
    if loaded.get("qualification_credit") is not False:
        raise GradingPreflightError(
            "offline replay cannot receive qualification credit"
        )
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
    "GradingPreflightError",
    "build_preregistration",
    "provider_input",
    "verify",
    "write_candidate",
]
