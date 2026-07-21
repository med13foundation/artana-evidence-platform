"""Preregister and run one non-scientific receipt-boundary smoke call."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Literal

from openai.lib._parsing._responses import type_to_text_format_param
from pydantic import BaseModel, ConfigDict

from scripts.validation.provider_receipt_boundary.canonical_payload import (
    canonical_sha256,
)
from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
    ProviderRequest,
    execute_single_provider_call,
)

MODEL_IDENTITY = "openai:gpt-5.6-sol"
PROVIDER_MODEL_ID = "gpt-5.6-sol"
REASONING_EFFORT = "low"
MAX_SMOKE_COST_USD = 0.25
SMOKE_INPUT = (
    "This is a non-scientific transport verification. Return the categorical status OK."
)
SMOKE_METADATA = {
    "artana_experiment": "receipt-boundary-smoke-v1",
    "artana_data_class": "non-scientific",
}
SMOKE_CODE_FILES = (
    "scripts/validation/provider_receipt_boundary/__init__.py",
    "scripts/validation/provider_receipt_boundary/canonical_payload.py",
    "scripts/validation/provider_receipt_boundary/contracts.py",
    "scripts/validation/provider_receipt_boundary/identity.py",
    "scripts/validation/provider_receipt_boundary/structural_diff.py",
    "scripts/validation/provider_receipt_boundary/validation.py",
    "scripts/validation/provider_receipt_boundary/smoke.py",
    "scripts/validation/public_gold/lossless_event_provider.py",
)
DEPENDENCY_FILES = ("pyproject.toml",)
DEPENDENCY_PACKAGES = ("openai", "pydantic")
BOUNDARY_FAILURE_STAGES = {
    "RECEIPT_ENVELOPE",
    "RECEIPT_PAYLOAD",
}


class SmokePreflightError(ValueError):
    """The smoke request differs from its immutable preregistration."""


@dataclass(frozen=True, slots=True)
class SmokeArtifactPaths:
    """Committed and local-only outputs from the single smoke call."""

    receipt: Path
    result: Path
    report: Path
    raw_output: Path


class ReceiptSmokeOutput(BaseModel):
    """The deliberately tiny non-scientific structured response."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    status: Literal["OK"]


def compute_smoke_frozen_state(repository_root: Path) -> dict[str, object]:
    """Recompute every request and implementation value without a provider call."""

    provider_format = type_to_text_format_param(ReceiptSmokeOutput)
    code_files = {
        path: _file_sha256(repository_root / path) for path in SMOKE_CODE_FILES
    }
    dependency_files = {
        path: _file_sha256(repository_root / path) for path in DEPENDENCY_FILES
    }
    dependencies = {
        "python": platform.python_version(),
        "packages": {name: version(name) for name in DEPENDENCY_PACKAGES},
        "files": dependency_files,
    }
    return {
        "input": {
            "sha256": _sha256_text(SMOKE_INPUT),
            "classification": "NON_SCIENTIFIC",
            "biomedical_source_included": False,
        },
        "output": {
            "schema_sha256": canonical_sha256(ReceiptSmokeOutput.model_json_schema()),
            "provider_format_sha256": canonical_sha256(provider_format),
            "provider_format": provider_format,
        },
        "model": {
            "identity": MODEL_IDENTITY,
            "provider_model_id": PROVIDER_MODEL_ID,
            "reasoning_effort": REASONING_EFFORT,
            "temperature": "provider_default_not_set",
        },
        "request_metadata": SMOKE_METADATA,
        "implementation": {
            "code_files": code_files,
            "code_bundle_sha256": canonical_sha256(code_files),
        },
        "dependencies": {
            **dependencies,
            "bundle_sha256": canonical_sha256(dependencies),
        },
    }


def build_smoke_preregistration(repository_root: Path) -> dict[str, object]:
    """Build the sole authorized non-scientific smoke contract."""

    return {
        "schema_version": "artana.provider_receipt_boundary.smoke.v1",
        "status": "FROZEN_AUTHORIZED_FOR_ONE_NON_SCIENTIFIC_CALL",
        "execution_authorized": True,
        "frozen_state": compute_smoke_frozen_state(repository_root),
        "budgets": {
            "provider_calls": 1,
            "provider_retries": 0,
            "max_output_tokens": 1024,
            "max_total_tokens": 5000,
            "max_cost_usd": MAX_SMOKE_COST_USD,
            "max_latency_seconds": 300.0,
            "pricing_usd_per_token": {
                "input": 0.000005,
                "cached_input": 0.0000005,
                "output": 0.00003,
            },
        },
        "rules": {
            "retry_allowed": False,
            "fallback_allowed": False,
            "biomedical_source_allowed": False,
            "scientific_experiment_allowed": False,
            "graph_write_allowed": False,
            "promotion_allowed": False,
        },
        "acceptance": {
            "structured_status": "OK",
            "canonical_payload_match": "EXACT",
            "identity_input_schema_usage": "VERIFIED",
            "unknown_envelope_differences_allowed": 0,
        },
    }


def verify_smoke_preregistration(
    repository_root: Path,
    preregistration_path: Path,
) -> dict[str, object]:
    """Fail unless an independent recomputation matches the frozen smoke."""

    payload = _read_json(preregistration_path)
    if payload.get("frozen_state") != compute_smoke_frozen_state(repository_root):
        raise SmokePreflightError(
            "smoke frozen state differs from deterministic recomputation"
        )
    if payload.get("execution_authorized") is not True:
        raise SmokePreflightError("smoke is not explicitly authorized")
    budgets = _required_dict(payload, "budgets")
    rules = _required_dict(payload, "rules")
    if budgets.get("provider_calls") != 1 or budgets.get("provider_retries") != 0:
        raise SmokePreflightError("smoke is not exactly one provider call")
    if _required_float(budgets, "max_cost_usd") > MAX_SMOKE_COST_USD:
        raise SmokePreflightError("smoke cost ceiling exceeds $0.25")
    required_false = (
        "retry_allowed",
        "fallback_allowed",
        "biomedical_source_allowed",
        "scientific_experiment_allowed",
        "graph_write_allowed",
        "promotion_allowed",
    )
    if any(rules.get(name) is not False for name in required_false):
        raise SmokePreflightError("smoke enables a prohibited capability")
    return {
        "status": "PREFLIGHT_PASSED",
        "preregistration_sha256": _file_sha256(preregistration_path),
        "frozen_state_sha256": canonical_sha256(payload["frozen_state"]),
    }


def run_smoke(
    *,
    repository_root: Path,
    preregistration_path: Path,
    artifacts: SmokeArtifactPaths,
) -> str:
    """Make exactly one non-scientific call and stop after its receipt verdict."""

    preflight = verify_smoke_preregistration(
        repository_root,
        preregistration_path,
    )
    preregistration = _read_json(preregistration_path)
    frozen_state = _required_dict(preregistration, "frozen_state")
    output_state = _required_dict(frozen_state, "output")
    model_state = _required_dict(frozen_state, "model")
    budgets = _required_dict(preregistration, "budgets")
    provider_format = _required_dict(output_state, "provider_format")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SmokePreflightError("OPENAI_API_KEY is required after preflight")

    try:
        execution = execute_single_provider_call(
            api_key=api_key,
            output_model=ReceiptSmokeOutput,
            request=ProviderRequest(
                provider_input=SMOKE_INPUT,
                provider_format=provider_format,
                provider_model_id=_required_string(
                    model_state,
                    "provider_model_id",
                ),
                reasoning_effort=_required_string(
                    model_state,
                    "reasoning_effort",
                ),
                max_output_tokens=_required_int(budgets, "max_output_tokens"),
                max_total_tokens=_required_int(budgets, "max_total_tokens"),
                max_cost_usd=_required_float(budgets, "max_cost_usd"),
                max_latency_seconds=_required_float(
                    budgets,
                    "max_latency_seconds",
                ),
                pricing=_pricing(_required_dict(budgets, "pricing_usd_per_token")),
                metadata={
                    str(key): str(value)
                    for key, value in _required_dict(
                        frozen_state,
                        "request_metadata",
                    ).items()
                },
            ),
        )
    except ProviderExecutionError as exc:
        decision = (
            "RECEIPT_BOUNDARY_FAILED"
            if exc.stage in BOUNDARY_FAILURE_STAGES
            else "INVALID_SMOKE_EXPERIMENT"
        )
        receipt = {
            "status": "UNVERIFIED",
            "provider_calls": 1,
            "provider_retries": 0,
            "failure_stage": exc.stage,
            "root_cause": exc.root_cause,
            "diagnostics": exc.diagnostics,
        }
        result = _smoke_result(
            decision=decision,
            preflight=preflight,
            receipt=receipt,
        )
        _write_artifacts(
            receipt_path=artifacts.receipt,
            receipt=receipt,
            result_path=artifacts.result,
            result=result,
            report_path=artifacts.report,
        )
        return decision

    artifacts.raw_output.parent.mkdir(parents=True, exist_ok=True)
    artifacts.raw_output.write_text(
        json.dumps(
            {
                "creation": execution.creation_response,
                "retrieval": execution.retrieval_response,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    decision = "RECEIPT_BOUNDARY_VALIDATED"
    result = _smoke_result(
        decision=decision,
        preflight=preflight,
        receipt=execution.receipt,
    )
    _write_artifacts(
        receipt_path=artifacts.receipt,
        receipt=execution.receipt,
        result_path=artifacts.result,
        result=result,
        report_path=artifacts.report,
    )
    return decision


def _smoke_result(
    *,
    decision: str,
    preflight: dict[str, object],
    receipt: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "artana.provider_receipt_boundary.smoke_result.v1",
        "decision": decision,
        "preflight": preflight,
        "receipt_sha256": canonical_sha256(receipt),
        "receipt": receipt,
        "terminal_rules": {
            "provider_calls": 1,
            "provider_retries": 0,
            "fallbacks": 0,
            "biomedical_sources_accessed": 0,
            "scientific_experiments_run": 0,
            "graph_writes": 0,
            "promotions": 0,
        },
    }


def _write_artifacts(
    *,
    receipt_path: Path,
    receipt: dict[str, object],
    result_path: Path,
    result: dict[str, object],
    report_path: Path,
) -> None:
    _write_json(receipt_path, receipt)
    _write_json(result_path, result)
    usage = receipt.get("usage")
    differences = receipt.get("differences")
    failure_stage = receipt.get("failure_stage")
    root_cause = receipt.get("root_cause")
    preflight = _required_dict(result, "preflight")
    report = [
        "# Provider Receipt Boundary Smoke",
        "",
        f"**Decision:** `{result['decision']}`",
        "",
        "This was one non-scientific categorical provider call. It did not access "
        "biomedical sources, run the scientific experiment, write to the graph, or "
        "enable promotion.",
        "",
        "## Custody",
        "",
        f"- Preregistration: `{preflight['preregistration_sha256']}`",
        "- Provider calls: `1`",
        "- Provider retries and fallbacks: `0`",
        "- Biomedical sources accessed: `0`",
    ]
    if isinstance(usage, dict):
        report.extend(
            [
                "",
                "## Accounting",
                "",
                f"- Input tokens: `{usage.get('input_tokens')}`",
                f"- Cached input tokens: `{usage.get('cached_input_tokens')}`",
                f"- Output tokens: `{usage.get('output_tokens')}`",
                f"- Reasoning tokens: `{usage.get('reasoning_tokens')}`",
                f"- Total tokens: `{usage.get('total_tokens')}`",
                f"- Latency seconds: `{usage.get('latency_seconds')}`",
                f"- Cost USD: `{usage.get('cost_usd')}`",
            ]
        )
    if isinstance(differences, list):
        report.extend(
            [
                "",
                "## Creation Versus Retrieval",
                "",
                f"- Differing field paths: `{len(differences)}`",
                "- Every listed difference was explicitly allowlisted; values are "
                "represented only by hashes in the receipt.",
                "",
                "```json",
                json.dumps(differences, indent=2, sort_keys=True),
                "```",
            ]
        )
    if isinstance(failure_stage, str):
        report.extend(
            [
                "",
                "## Failure",
                "",
                f"- Stage: `{failure_stage}`",
                f"- Root cause: {root_cause}",
            ]
        )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SmokePreflightError("preregistration is not a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _required_dict(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise SmokePreflightError(f"{key} must be an object")
    return value


def _required_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise SmokePreflightError(f"{key} must be a non-empty string")
    return value


def _required_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or value < 0:
        raise SmokePreflightError(f"{key} must be a non-negative integer")
    return value


def _required_float(payload: dict[str, object], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, int | float) or value < 0:
        raise SmokePreflightError(f"{key} must be a non-negative number")
    return float(value)


def _pricing(payload: dict[str, object]) -> dict[str, float]:
    return {
        key: _required_float(payload, key)
        for key in ("input", "cached_input", "output")
    }


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        raise SmokePreflightError(f"frozen file is missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    repository_root = Path(__file__).resolve().parents[3]
    if args.command == "write":
        _write_json(
            args.preregistration,
            build_smoke_preregistration(repository_root),
        )
        print(_file_sha256(args.preregistration))
        return 0
    if args.command == "verify":
        print(
            json.dumps(
                verify_smoke_preregistration(
                    repository_root,
                    args.preregistration,
                ),
                sort_keys=True,
            )
        )
        return 0
    decision = run_smoke(
        repository_root=repository_root,
        preregistration_path=args.preregistration,
        artifacts=SmokeArtifactPaths(
            receipt=args.receipt,
            result=args.result,
            report=args.report,
            raw_output=args.raw_output,
        ),
    )
    print(decision)
    return 0 if decision == "RECEIPT_BOUNDARY_VALIDATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
