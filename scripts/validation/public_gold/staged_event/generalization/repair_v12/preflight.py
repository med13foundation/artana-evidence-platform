"""Build and verify the forward-only V12 exposed-gate preregistration."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import cast

from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    write_json_atomic,
)
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
from scripts.validation.public_gold.staged_event.generalization.repair_v12.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
    EXPERIMENT_ID,
    GLOBAL_MAX_CALLS,
    GLOBAL_MAX_COST_USD,
    MODEL,
    REASONING_EFFORT,
    REPO,
    REQUEST_TIMEOUT_SECONDS,
    V12Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.contracts import (
    load_contract,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.offline_replay import (
    OfflineReplayPaths,
    build_offline_replay,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.prompt_audit import (
    verify_prompt_audit,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.provider import (
    provider_format,
)

PASS_TERMINAL = "V12_EXPOSED_GATE_PASS_READY_FOR_FRESH_PREREGISTRATION"
FOCUS_FAIL_TERMINAL = "V12_EXPOSED_GATE_FAIL_FOCUS_EVENT"
SOURCE_FAIL_TERMINAL = "V12_EXPOSED_GATE_FAIL_SOURCE_SEMANTICS"
CG_FAIL_TERMINAL = "V12_EXPOSED_GATE_FAIL_CG_PROJECTION"
UNRELATED_FAIL_TERMINAL = "V12_EXPOSED_GATE_FAIL_UNRELATED_REGRESSION"
INVALID_TERMINAL = "INVALID_V12_EXECUTION"
NO_AUTHORIZATION_TERMINAL = "NO_V12_AUTHORIZED_AFTER_ADJUDICATION"

_V11_SEALED_SHA256 = {
    "preregistration": (
        "6157de1e1cb59042a6f532caa3b5f91e248ab8d7e09919fd0a2d98ec2e8b3a6a"
    ),
    "result": "5b7e3d2e3827d640878de4d156bb509229bd0c3f35cf10358f1d886ed15950d1",
    "report": "6907eebeb84cad8c34615b92c2012909de6af3a845c1e0b51119311d48f20117",
}
_QUALIFIED_TRANSPORT_SHA256 = (
    "241eb7db30148ccdb48640da356ad2abcd82159363594b00c01d2b3a410353fb"
)
_IMPLEMENTATION_FILES = (
    "scripts/run_staged_generalization_v12_exposed.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v12/__init__.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v12/acceptance.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v12/accounting.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v12/config.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v12/contracts.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v12/evaluation.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v12/fresh_preregistration.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v12/offline_replay.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v12/preflight.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v12/prompt_audit.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v12/provider.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v12/reporting.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v12/runner.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v12/terminal.py",
)
_EVALUATOR_FILES = (
    "scripts/validation/public_gold/staged_event/generalization/grading/artifacts.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/evaluation.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/policy.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v12/contracts.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v12/evaluation.py",
)
_FOREGROUND_RECEIPT_FILES = (
    "scripts/validation/provider_receipt_boundary/canonical_payload.py",
    "scripts/validation/provider_receipt_boundary/contracts.py",
    "scripts/validation/provider_receipt_boundary/identity.py",
    "scripts/validation/provider_receipt_boundary/operational_accounting_v2.py",
    "scripts/validation/provider_receipt_boundary/validation.py",
    "scripts/validation/provider_receipt_boundary/foreground/contracts.py",
    "scripts/validation/provider_receipt_boundary/foreground/execution.py",
    "scripts/validation/provider_receipt_boundary/foreground/validation.py",
)
_REMOTE_REF_FIELD_COUNT = 2


class V12PreflightError(RuntimeError):
    """V12 differs from its independently reviewed preregistration."""


def ordered_cases() -> tuple[GeneralizationCase, ...]:
    by_id = {case.case_id: case for case in build_panel()}
    if set(by_id) != set(CASE_ORDER):
        raise V12PreflightError("V12 panel membership changed")
    return tuple(by_id[case_id] for case_id in CASE_ORDER)


def provider_input(
    case_id: str,
    paths: V12Paths = DEFAULT_PATHS,
) -> str:
    case = next(
        (item for item in ordered_cases() if item.case_id == case_id),
        None,
    )
    if case is None:
        raise V12PreflightError(f"unknown exposed case: {case_id}")
    verify_prompt_audit(
        rule_path=paths.focus_rule,
        audit_path=paths.focus_rule_audit,
        adjudication_path=paths.adjudication,
    )
    return (
        paths.v11_prompt.read_text(encoding="utf-8")
        + "\n\n--- V12 SINGLE SCIENTIFIC CHANGE ---\n"
        + paths.focus_rule.read_text(encoding="utf-8")
        + "--- END V12 SINGLE SCIENTIFIC CHANGE ---\n"
        + "\n--- FROZEN EXPOSED CASE ---\n"
        + json.dumps(agent_case(case), indent=2, sort_keys=True)
        + "\n--- END FROZEN EXPOSED CASE ---\n"
    )


def build_preregistration(
    paths: V12Paths = DEFAULT_PATHS,
) -> dict[str, object]:
    _verify_inputs(paths)
    policy = verify_frozen_policy(paths.grading)
    cases = ordered_cases()
    qualification = _object(
        json.loads(paths.qualified_transport_result.read_text(encoding="utf-8"))
    )
    if qualification.get("decision") != "FOREGROUND_TRANSPORT_QUALIFIED":
        raise V12PreflightError("direct foreground transport is not qualified")
    return {
        "schema_version": "artana.staged_generalization.v12_exposed_gate.v1",
        "experiment_id": EXPERIMENT_ID,
        "authorization": "PREREGISTERED_V12_EXPOSED_CASES_ONLY",
        "root_cause_classification": "FOCUS_EVENT_ANCHORING_PROMPT_GAP",
        "single_scientific_change": "FOCUS_EVENT_ANCHORING",
        "frozen_state": {
            "case_order": list(CASE_ORDER),
            "panel_sha256": _sha256(paths.panel),
            "v11_prompt_sha256": _sha256(paths.v11_prompt),
            "focus_rule_sha256": _sha256(paths.focus_rule),
            "focus_rule_audit_sha256": _sha256(paths.focus_rule_audit),
            "wording_review_sha256": {
                "reviewer_a": _sha256(paths.wording_review_a),
                "reviewer_b": _sha256(paths.wording_review_b),
            },
            "adjudication_sha256": _sha256(paths.adjudication),
            "two_lane_contract_sha256": _sha256(paths.two_lane_contract),
            "offline_replay_sha256": _sha256(paths.offline_replay),
            "source_sha256_by_case": {
                case.case_id: case.source_sha256 for case in cases
            },
            "provider_input_sha256_by_case": {
                case.case_id: hashlib.sha256(
                    provider_input(case.case_id, paths).encode()
                ).hexdigest()
                for case in cases
            },
            "schema_sha256": _canonical_sha256(
                V9StagedGeneralizationOutput.model_json_schema()
            ),
            "schema_basis": "UNCHANGED_V9_V11",
            "provider_format_sha256": _canonical_sha256(provider_format()),
            "grading_policy_sha256": policy_sha256(policy),
            "grader_relaxed": False,
            "frozen_grader_changed": False,
            "reference_changed_for_non_target_cases": False,
            "evaluation_contract": {
                "source_semantic_lane": "QUALIFICATION",
                "exact_cg_projection_lane": "REVIEW_ONLY",
                "cg_projection_qualification_credit": False,
                "implementation_sha256": _hash_files(_EVALUATOR_FILES),
            },
            "execution_implementation_sha256": _hash_files(
                _IMPLEMENTATION_FILES
            ),
            "receipt_implementation_sha256": _hash_files(
                _FOREGROUND_RECEIPT_FILES
            ),
        },
        "sealed_history": {
            "v11_terminal": "V11_EXPOSED_RUN_V2_FAIL_UNRELATED_REGRESSION",
            "v11_sha256": _V11_SEALED_SHA256,
            "historical_replay_diagnostic_only": True,
            "historical_replay_credit": False,
            "historical_results_rescored": False,
        },
        "provider": {
            "transport": "DIRECT_OPENAI_FOREGROUND_RESPONSES",
            "transport_qualification_sha256": _sha256(
                paths.qualified_transport_result
            ),
            "transport_qualification_reused": True,
            "model": f"openai:{MODEL}",
            "reasoning_effort": REASONING_EFFORT,
            "background": False,
            "store": True,
            "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
            "application_max_output_tokens": None,
            "application_max_total_tokens": None,
            "provider_retries": 0,
            "fallback": False,
            "exactly_one_creation_per_case": True,
            "stable_response_id_custody": True,
            "confirmation_retrieval_required": True,
            "input_item_retrieval_required": True,
        },
        "operational_budget": {
            "cumulative_max_cost_usd": GLOBAL_MAX_COST_USD,
            "maximum_creation_calls": GLOBAL_MAX_CALLS,
            "v12_starting_cost_usd": 0.0,
            "prior_transport_qualification_cost_included": False,
            "check_before_each_creation": True,
            "record_actual_usage_latency_and_cost_after_each_call": True,
            "stop_before_next_call_when_exhausted": True,
            "telemetry_affects_scientific_scoring": False,
            "valid_case_results_preserved_after_budget_stop": True,
        },
        "acceptance": {
            "all_six_cases_pass": True,
            "drug_focus_event_pass": True,
            "drug_source_semantic_lane_pass": True,
            "drug_exact_cg_projection_pass": True,
            "non_target_cases_use_unchanged_frozen_grader": True,
            "all_receipts_valid": True,
            "provider_retries": 0,
            "duplicate_creation_calls": 0,
        },
        "stopping_rules": {
            "sequential_fail_fast": True,
            "first_real_scientific_failure": True,
            "invalid_schema_custody_or_exactly_once": True,
            "operational_budget_exhaustion": True,
            "provider_outage_or_missing_secret": True,
        },
        "terminal_decisions": [
            PASS_TERMINAL,
            FOCUS_FAIL_TERMINAL,
            SOURCE_FAIL_TERMINAL,
            CG_FAIL_TERMINAL,
            UNRELATED_FAIL_TERMINAL,
            INVALID_TERMINAL,
            NO_AUTHORIZATION_TERMINAL,
        ],
        "rules": {
            "exposed_cases_only": True,
            "fresh_case_calls_allowed": False,
            "fresh_cases_consumed": 0,
            "prepare_draft_fresh_preregistration_only_on_pass": True,
            "graph_writes": False,
            "trusted_graph_promotion": False,
        },
    }


def write_candidate(paths: V12Paths = DEFAULT_PATHS) -> None:
    replay = build_offline_replay(
        OfflineReplayPaths(
            contract=paths.two_lane_contract,
            adjudication=paths.adjudication,
            v9_raw=paths.v9_raw,
            v9_result=paths.v9_result,
            v11_raw=paths.v11_raw,
            v11_result=paths.v11_result,
        )
    )
    write_json_atomic(paths.offline_replay, replay)
    write_json_atomic(paths.preregistration, build_preregistration(paths))


def verify(
    paths: V12Paths = DEFAULT_PATHS,
    *,
    remote_gate: bool = False,
) -> dict[str, object]:
    loaded = _object(
        json.loads(paths.preregistration.read_text(encoding="utf-8"))
    )
    if loaded != build_preregistration(paths):
        raise V12PreflightError("V12 preregistration differs from frozen state")
    if remote_gate:
        _verify_remote_head()
    return loaded


def _verify_inputs(paths: V12Paths) -> None:
    verify_prompt_audit(
        rule_path=paths.focus_rule,
        audit_path=paths.focus_rule_audit,
        adjudication_path=paths.adjudication,
    )
    load_contract(
        paths.two_lane_contract,
        adjudication_path=paths.adjudication,
    )
    expected_replay = build_offline_replay(
        OfflineReplayPaths(
            contract=paths.two_lane_contract,
            adjudication=paths.adjudication,
            v9_raw=paths.v9_raw,
            v9_result=paths.v9_result,
            v11_raw=paths.v11_raw,
            v11_result=paths.v11_result,
        )
    )
    observed_replay = _object(
        json.loads(paths.offline_replay.read_text(encoding="utf-8"))
    )
    if observed_replay != _json_value(expected_replay):
        raise V12PreflightError("V9/V11 diagnostic replay changed")
    _verify_wording_review(paths.wording_review_a, paths)
    _verify_wording_review(paths.wording_review_b, paths)
    historical = {
        "preregistration": _sha256(paths.v11_preregistration),
        "result": _sha256(paths.v11_result),
        "report": _sha256(paths.v11_report),
    }
    if historical != _V11_SEALED_SHA256:
        raise V12PreflightError("sealed V11 artifacts changed")
    if _sha256(paths.qualified_transport_result) != _QUALIFIED_TRANSPORT_SHA256:
        raise V12PreflightError("qualified foreground transport artifact changed")


def _verify_wording_review(path: Path, paths: V12Paths) -> None:
    review = _object(json.loads(path.read_text(encoding="utf-8")))
    if (
        review.get("verdict") != "PASS"
        or review.get("rule_sha256") != _sha256(paths.focus_rule)
        or review.get("audit_sha256") != _sha256(paths.focus_rule_audit)
        or review.get("single_change_scope") != "PASS"
        or review.get("source_generality") != "PASS"
        or review.get("leakage") != "PASS"
    ):
        raise V12PreflightError(f"wording review failed: {path.name}")
    safety = review.get("case_safety")
    if not isinstance(safety, dict) or set(safety) != set(CASE_ORDER):
        raise V12PreflightError("wording review case coverage changed")
    if set(safety.values()) != {"PASS"}:
        raise V12PreflightError("wording review has a case safety failure")


def _verify_remote_head() -> None:
    branch = _git("branch", "--show-current")
    local = _git("rev-parse", "HEAD")
    remote = _git("ls-remote", "--heads", "origin", branch).split()
    if (
        not branch
        or len(remote) != _REMOTE_REF_FIELD_COUNT
        or remote[0] != local
    ):
        raise V12PreflightError(
            "local and remote heads differ before V12 execution"
        )


def _git(*arguments: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed local Git executable.
        ["git", *arguments],  # noqa: S607
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise V12PreflightError(completed.stderr.strip())
    return completed.stdout.strip()


def _hash_files(names: tuple[str, ...]) -> dict[str, str]:
    return {name: _sha256(REPO / name) for name in names}


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _json_value(value: object) -> object:
    return json.loads(json.dumps(value))


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise V12PreflightError("expected JSON object")
    return cast("dict[str, object]", value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "CG_FAIL_TERMINAL",
    "FOCUS_FAIL_TERMINAL",
    "INVALID_TERMINAL",
    "NO_AUTHORIZATION_TERMINAL",
    "PASS_TERMINAL",
    "SOURCE_FAIL_TERMINAL",
    "UNRELATED_FAIL_TERMINAL",
    "V12PreflightError",
    "build_preregistration",
    "ordered_cases",
    "provider_input",
    "verify",
    "write_candidate",
]
