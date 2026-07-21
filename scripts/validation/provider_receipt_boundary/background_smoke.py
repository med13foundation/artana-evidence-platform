"""Preregister and run one tiny background receipt-boundary smoke."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import cast

from openai.lib._parsing._responses import type_to_text_format_param

from scripts.validation.provider_receipt_boundary.background import (
    BackgroundExecutionBudgets,
    execute_background_provider_call,
)
from scripts.validation.provider_receipt_boundary.canonical_payload import (
    canonical_sha256,
)
from scripts.validation.provider_receipt_boundary.smoke import (
    RESPONSE_FORMAT_DESCRIPTION,
    SMOKE_INPUT,
    ReceiptSmokeOutput,
)
from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
    ProviderRequest,
)

MODEL_IDENTITY = "openai:gpt-5.6-sol"
PROVIDER_MODEL_ID = "gpt-5.6-sol"
REASONING_EFFORT = "low"
SMOKE_VERSION = "v1"
MAX_COST_USD = 0.25
ACKNOWLEDGEMENT_TIMEOUT_SECONDS = 30.0
POLLING_INTERVAL_SECONDS = 5.0
MAX_POLLING_SECONDS = 900.0
MAX_TOTAL_TOKENS = 5000
MAX_OUTPUT_TOKENS = 1024
SMOKE_METADATA = {
    "artana_experiment": f"background-receipt-smoke-{SMOKE_VERSION}",
    "artana_data_class": "non-scientific",
}
CODE_FILES = (
    "scripts/validation/provider_receipt_boundary/__init__.py",
    "scripts/validation/provider_receipt_boundary/canonical_payload.py",
    "scripts/validation/provider_receipt_boundary/contracts.py",
    "scripts/validation/provider_receipt_boundary/identity.py",
    "scripts/validation/provider_receipt_boundary/structural_diff.py",
    "scripts/validation/provider_receipt_boundary/validation.py",
    "scripts/validation/provider_receipt_boundary/smoke.py",
    "scripts/validation/provider_receipt_boundary/background/__init__.py",
    "scripts/validation/provider_receipt_boundary/background/contracts.py",
    "scripts/validation/provider_receipt_boundary/background/execution.py",
    "scripts/validation/provider_receipt_boundary/background/polling.py",
    "scripts/validation/provider_receipt_boundary/background/states.py",
    "scripts/validation/provider_receipt_boundary/background_smoke.py",
    "scripts/validation/public_gold/lossless_event_provider.py",
)
DEPENDENCY_FILES = ("pyproject.toml",)
DEPENDENCY_PACKAGES = ("openai", "pydantic")
GIT_EXECUTABLE = "/usr/bin/git"


class BackgroundSmokePreflightError(ValueError):
    """The smoke differs from its preregistered transport contract."""


@dataclass(frozen=True, slots=True)
class BackgroundSmokeArtifacts:
    receipt: Path
    result: Path
    report: Path
    raw_output: Path


def compute_frozen_state(repository_root: Path) -> dict[str, object]:
    provider_format = cast(
        "dict[str, object]",
        type_to_text_format_param(ReceiptSmokeOutput),
    )
    provider_format["description"] = RESPONSE_FORMAT_DESCRIPTION
    code_files = {path: _file_sha256(repository_root / path) for path in CODE_FILES}
    dependency_files = {
        path: _file_sha256(repository_root / path) for path in DEPENDENCY_FILES
    }
    dependencies = {
        "python": platform.python_version(),
        "packages": {name: version(name) for name in DEPENDENCY_PACKAGES},
        "files": dependency_files,
    }
    return {
        "custody": {
            "commit": _git_stdout(repository_root, "rev-parse", "HEAD"),
            "tracked_executable_paths_clean": True,
        },
        "input": {
            "text": SMOKE_INPUT,
            "sha256": _text_sha256(SMOKE_INPUT),
            "classification": "NON_SCIENTIFIC",
            "biomedical_source_included": False,
        },
        "output": {
            "expected_contract": {
                "category": "OK",
                "explanation": "Receipt boundary confirmed.",
            },
            "provider_format": provider_format,
            "provider_format_sha256": canonical_sha256(provider_format),
        },
        "model": {
            "identity": MODEL_IDENTITY,
            "provider_model_id": PROVIDER_MODEL_ID,
            "reasoning_effort": REASONING_EFFORT,
            "temperature": "provider_default_not_set",
        },
        "request_metadata": SMOKE_METADATA,
        "transport": {
            "mode": "OPENAI_RESPONSES_BACKGROUND_POLLING",
            "background": True,
            "acknowledgement_timeout_seconds": ACKNOWLEDGEMENT_TIMEOUT_SECONDS,
            "polling_interval_seconds": POLLING_INTERVAL_SECONDS,
            "max_polling_seconds": MAX_POLLING_SECONDS,
            "creation_idempotency_claimed": False,
            "automatic_cancellation": False,
        },
        "implementation": {
            "code_files": code_files,
            "code_bundle_sha256": canonical_sha256(code_files),
        },
        "dependencies": {
            **dependencies,
            "bundle_sha256": canonical_sha256(dependencies),
        },
    }


def build_preregistration(repository_root: Path) -> dict[str, object]:
    return {
        "schema_version": f"artana.provider_receipt_boundary.background_smoke.{SMOKE_VERSION}",
        "status": "FROZEN_AUTHORIZED_FOR_ONE_NON_SCIENTIFIC_BACKGROUND_CALL",
        "execution_authorized": True,
        "frozen_state": compute_frozen_state(repository_root),
        "budgets": {
            "provider_creation_calls": 1,
            "model_generation_calls": 1,
            "duplicate_creation_calls": 0,
            "provider_retries": 0,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "max_total_tokens": MAX_TOTAL_TOKENS,
            "max_cost_usd": MAX_COST_USD,
            "max_latency_seconds": MAX_POLLING_SECONDS,
            "pricing_usd_per_token": {
                "input": 0.000005,
                "cached_input": 0.0000005,
                "output": 0.00003,
            },
        },
        "rules": {
            "retry_allowed": False,
            "fallback_allowed": False,
            "repair_allowed": False,
            "alternate_model_allowed": False,
            "biomedical_source_allowed": False,
            "scientific_experiment_allowed": False,
            "graph_write_allowed": False,
            "promotion_allowed": False,
            "creation_idempotency_claimed": False,
        },
        "stop_rules": [
            "stop before the provider call on deterministic preflight failure",
            "never repeat creation after an acknowledgement timeout",
            "poll only the acknowledged response ID",
            "stop on the first terminal or receipt failure",
            "stop after the single smoke whether it passes or fails",
        ],
    }


def verify_preregistration(
    repository_root: Path,
    preregistration_path: Path,
    *,
    require_clean_code: bool = True,
) -> dict[str, object]:
    payload = _read_json(preregistration_path)
    if payload.get("frozen_state") != compute_frozen_state(repository_root):
        raise BackgroundSmokePreflightError(
            "background smoke frozen state differs from recomputation"
        )
    if payload.get("execution_authorized") is not True:
        raise BackgroundSmokePreflightError("background smoke is not authorized")
    budgets = _required_dict(payload, "budgets")
    rules = _required_dict(payload, "rules")
    for key, expected in {
        "provider_creation_calls": 1,
        "model_generation_calls": 1,
        "duplicate_creation_calls": 0,
        "provider_retries": 0,
    }.items():
        if budgets.get(key) != expected:
            raise BackgroundSmokePreflightError(f"invalid background budget: {key}")
    if _required_float(budgets, "max_cost_usd") > MAX_COST_USD:
        raise BackgroundSmokePreflightError("background smoke cost exceeds $0.25")
    prohibited = (
        "retry_allowed",
        "fallback_allowed",
        "repair_allowed",
        "alternate_model_allowed",
        "biomedical_source_allowed",
        "scientific_experiment_allowed",
        "graph_write_allowed",
        "promotion_allowed",
        "creation_idempotency_claimed",
    )
    if any(rules.get(name) is not False for name in prohibited):
        raise BackgroundSmokePreflightError(
            "background smoke enables a prohibited rule"
        )
    if require_clean_code:
        _require_clean_code(repository_root)
    return {
        "status": "PREFLIGHT_PASSED",
        "preregistration_sha256": _file_sha256(preregistration_path),
        "frozen_state_sha256": canonical_sha256(payload["frozen_state"]),
    }


def run_smoke(
    *,
    repository_root: Path,
    preregistration_path: Path,
    artifacts: BackgroundSmokeArtifacts,
) -> str:
    preflight = verify_preregistration(repository_root, preregistration_path)
    preregistration = _read_json(preregistration_path)
    frozen = _required_dict(preregistration, "frozen_state")
    output = _required_dict(frozen, "output")
    model = _required_dict(frozen, "model")
    transport = _required_dict(frozen, "transport")
    budgets = _required_dict(preregistration, "budgets")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise BackgroundSmokePreflightError("OPENAI_API_KEY is required")
    try:
        execution = execute_background_provider_call(
            api_key=api_key,
            request=ProviderRequest(
                provider_input=SMOKE_INPUT,
                provider_format=_required_dict(output, "provider_format"),
                provider_model_id=_required_string(model, "provider_model_id"),
                reasoning_effort=_required_string(model, "reasoning_effort"),
                max_output_tokens=_required_int(budgets, "max_output_tokens"),
                max_total_tokens=_required_int(budgets, "max_total_tokens"),
                max_cost_usd=_required_float(budgets, "max_cost_usd"),
                max_latency_seconds=_required_float(budgets, "max_latency_seconds"),
                pricing=_pricing(_required_dict(budgets, "pricing_usd_per_token")),
                metadata={
                    str(key): str(value)
                    for key, value in _required_dict(frozen, "request_metadata").items()
                },
            ),
            transport_budgets=BackgroundExecutionBudgets(
                acknowledgement_timeout_seconds=_required_float(
                    transport, "acknowledgement_timeout_seconds"
                ),
                polling_interval_seconds=_required_float(
                    transport, "polling_interval_seconds"
                ),
                max_polling_seconds=_required_float(transport, "max_polling_seconds"),
            ),
            output_model=ReceiptSmokeOutput,
        )
    except ProviderExecutionError as exc:
        decision = _failure_decision(exc.stage)
        receipt = {
            "status": "UNVERIFIED",
            "failure_stage": exc.stage,
            "root_cause": exc.root_cause,
            "diagnostics": exc.diagnostics,
            "provider_retries": 0,
        }
        result = _result(decision, preflight, receipt)
        _write_artifacts(
            artifacts.receipt,
            receipt,
            artifacts.result,
            result,
            artifacts.report,
        )
        return decision

    artifacts.raw_output.parent.mkdir(parents=True, exist_ok=True)
    artifacts.raw_output.write_text(
        json.dumps(
            {
                "acknowledgement": execution.acknowledgement_response,
                "terminal": execution.terminal_response,
                "confirmation": execution.confirmation_response,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    decision = "BACKGROUND_TRANSPORT_VALIDATED"
    result = _result(decision, preflight, execution.receipt)
    _write_artifacts(
        artifacts.receipt,
        execution.receipt,
        artifacts.result,
        result,
        artifacts.report,
    )
    return decision


def _failure_decision(stage: str) -> str:
    if stage == "BACKGROUND_ACKNOWLEDGEMENT_TIMEOUT":
        return "BACKGROUND_TRANSPORT_REDESIGN_REQUIRED"
    if stage in {"BACKGROUND_CREATION_REJECTED", "STRUCTURED_OUTPUT_SCHEMA"}:
        return "INVALID_BACKGROUND_SMOKE"
    return "BACKGROUND_TRANSPORT_FAILED"


def _result(
    decision: str,
    preflight: dict[str, object],
    receipt: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": f"artana.provider_receipt_boundary.background_result.{SMOKE_VERSION}",
        "decision": decision,
        "preflight": preflight,
        "receipt_sha256": canonical_sha256(receipt),
        "receipt": receipt,
        "terminal_rules": {
            "scientific_experiments_run": 0,
            "biomedical_sources_accessed": 0,
            "fallbacks": 0,
            "repairs": 0,
            "graph_writes": 0,
            "promotions": 0,
        },
    }


def _write_artifacts(
    receipt_path: Path,
    receipt: dict[str, object],
    result_path: Path,
    result: dict[str, object],
    report_path: Path,
) -> None:
    _write_json(receipt_path, receipt)
    _write_json(result_path, result)
    usage = receipt.get("usage")
    identity = receipt.get("identity")
    response_id = identity.get("response_id") if isinstance(identity, dict) else None
    preflight = _required_dict(result, "preflight")
    report = [
        f"# Background Provider Receipt Smoke {SMOKE_VERSION.upper()}",
        "",
        f"**Decision:** `{result['decision']}`",
        "",
        "This was one tiny non-scientific background response. No biomedical source, scientific experiment, graph write, or promotion was used.",
        "",
        "## Integrity",
        "",
        f"- Preregistration: `{preflight['preregistration_sha256']}`",
        f"- Provider creation calls: `{receipt.get('provider_creation_calls', 1)}`",
        f"- Polling retrieval requests: `{receipt.get('polling_retrieval_requests', 0)}`",
        "- Provider retries and duplicate creation calls: `0`",
    ]
    if isinstance(usage, dict):
        report.extend(
            [
                "",
                "## Accounting",
                "",
                f"- Total tokens: `{usage.get('total_tokens')}`",
                f"- Latency seconds: `{usage.get('latency_seconds')}`",
                f"- Cost USD: `{usage.get('cost_usd')}`",
                f"- Status history: `{receipt.get('status_history')}`",
                f"- Response ID: `{response_id}`",
            ]
        )
    if receipt.get("failure_stage"):
        report.extend(
            [
                "",
                "## Failure",
                "",
                f"- Stage: `{receipt.get('failure_stage')}`",
                f"- Root cause: {receipt.get('root_cause')}",
                "",
                "```json",
                json.dumps(receipt.get("diagnostics"), indent=2, sort_keys=True),
                "```",
            ]
        )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")


def _require_clean_code(repository_root: Path) -> None:
    for staged in (False, True):
        command = [GIT_EXECUTABLE, "diff", "--quiet"]
        if staged:
            command.append("--cached")
        command.extend(["HEAD", "--", *CODE_FILES])
        completed = subprocess.run(command, cwd=repository_root, check=False)  # noqa: S603
        if completed.returncode == 1:
            raise BackgroundSmokePreflightError("background executable paths are dirty")
        if completed.returncode != 0:
            raise BackgroundSmokePreflightError("could not verify code custody")


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BackgroundSmokePreflightError("preregistration is not an object")
    return payload


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _required_dict(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise BackgroundSmokePreflightError(f"{key} must be an object")
    return value


def _required_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise BackgroundSmokePreflightError(f"{key} must be a string")
    return value


def _required_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or value < 0:
        raise BackgroundSmokePreflightError(f"{key} must be a nonnegative integer")
    return value


def _required_float(payload: dict[str, object], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, int | float) or value <= 0:
        raise BackgroundSmokePreflightError(f"{key} must be positive")
    return float(value)


def _pricing(payload: dict[str, object]) -> dict[str, float]:
    return {
        key: _required_float(payload, key)
        for key in ("input", "cached_input", "output")
    }


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        raise BackgroundSmokePreflightError(f"frozen file is missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_stdout(repository_root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        [GIT_EXECUTABLE, *arguments],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    write = commands.add_parser("write")
    write.add_argument("preregistration", type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("preregistration", type=Path)
    run = commands.add_parser("run")
    run.add_argument("preregistration", type=Path)
    run.add_argument("--receipt", type=Path, required=True)
    run.add_argument("--result", type=Path, required=True)
    run.add_argument("--report", type=Path, required=True)
    run.add_argument("--raw-output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    if args.command == "write":
        _write_json(args.preregistration, build_preregistration(root))
        print(_file_sha256(args.preregistration))
        return 0
    if args.command == "verify":
        print(
            json.dumps(
                verify_preregistration(root, args.preregistration), sort_keys=True
            )
        )
        return 0
    decision = run_smoke(
        repository_root=root,
        preregistration_path=args.preregistration,
        artifacts=BackgroundSmokeArtifacts(
            receipt=args.receipt,
            result=args.result,
            report=args.report,
            raw_output=args.raw_output,
        ),
    )
    print(decision)
    return 0 if decision == "BACKGROUND_TRANSPORT_VALIDATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
