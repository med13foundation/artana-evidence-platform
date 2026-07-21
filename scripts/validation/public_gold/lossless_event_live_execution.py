"""One-shot orchestrator for the frozen lossless event development experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from scripts.validation.public_gold.bionlp_cg_event_projection import (
    project_development_directory,
)
from scripts.validation.public_gold.lossless_event_experiment_contracts import (
    ScientificEventExtraction,
    assemble_scientific_event_document,
    build_provider_input,
)
from scripts.validation.public_gold.lossless_event_preflight import (
    DEVELOPMENT_DIRECTORY,
    PROMPT_PATH,
    canonical_sha256,
    verify_preregistration,
)
from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
    ProviderRequest,
    execute_single_provider_call,
)
from scripts.validation.public_gold.lossless_event_provider_format import (
    build_scientific_event_provider_format,
)
from scripts.validation.public_gold.lossless_event_scoring import (
    score_scientific_event_document,
)
from scripts.validation.public_gold.source_selection import (
    load_development_sources,
    select_lowest_sha256,
)

DECISIONS = {
    "DEVELOPMENT_GATE_PASSED",
    "DEVELOPMENT_GATE_FAILED",
    "INVALID_EXPERIMENT",
}


@dataclass(frozen=True, slots=True)
class ExperimentArtifactPaths:
    receipt: Path
    result: Path
    report: Path
    raw_output: Path


def run_experiment(
    *,
    repository_root: Path,
    preregistration_path: Path,
    artifacts: ExperimentArtifactPaths,
) -> str:
    """Verify the freeze, make one call, score once, and always stop."""

    preflight = verify_preregistration(repository_root, preregistration_path)
    preregistration = json.loads(preregistration_path.read_text(encoding="utf-8"))
    frozen_state = _required_dict(preregistration, "frozen_state")
    source_state = _required_dict(frozen_state, "source")
    model_state = _required_dict(frozen_state, "model")
    budgets = _required_dict(preregistration, "budgets")
    sources = load_development_sources(
        repository_root / DEVELOPMENT_DIRECTORY,
        expected_documents=100,
    )
    selected = select_lowest_sha256(sources)
    prompt = (repository_root / PROMPT_PATH).read_text(encoding="utf-8")
    provider_input = build_provider_input(
        prompt=prompt,
        document_id=selected.document_id,
        source_sha256=selected.source_sha256,
        source_text=selected.source_text,
    )
    preregistration_sha256 = _file_sha256(preregistration_path)
    metadata = {
        "artana_experiment": "lossless-event-development-v2",
        "artana_preregistration_sha256": preregistration_sha256,
        "artana_source_sha256": selected.source_sha256,
    }
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required after offline preflight passes")
    try:
        execution = execute_single_provider_call(
            api_key=api_key,
            output_model=ScientificEventExtraction,
            request=ProviderRequest(
                provider_input=provider_input,
                provider_format=build_scientific_event_provider_format(),
                provider_model_id=_required_string(model_state, "provider_model_id"),
                reasoning_effort=_required_string(model_state, "reasoning_effort"),
                max_output_tokens=_required_int(budgets, "max_output_tokens"),
                max_total_tokens=_required_int(budgets, "max_total_tokens"),
                max_cost_usd=_required_float(budgets, "max_cost_usd"),
                max_latency_seconds=_required_float(budgets, "max_latency_seconds"),
                pricing=_pricing(_required_dict(budgets, "pricing_usd_per_token")),
                metadata=metadata,
            ),
        )
    except ProviderExecutionError as exc:
        result = _invalid_result(
            preregistration_sha256=preregistration_sha256,
            preflight=preflight,
            stage=exc.stage,
            root_cause=exc.root_cause,
        )
        _write_artifacts(
            receipt_path=artifacts.receipt,
            receipt={
                "status": "UNVERIFIED",
                "provider_calls_attempted": 1,
                "provider_retries": 0,
                "failure_stage": exc.stage,
                "root_cause": exc.root_cause,
                "diagnostics": exc.diagnostics,
            },
            result_path=artifacts.result,
            result=result,
            report_path=artifacts.report,
        )
        return "INVALID_EXPERIMENT"

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
    try:
        predicted = assemble_scientific_event_document(
            execution.extraction,
            document_id=selected.document_id,
            source_text=selected.source_text,
            source_sha256=selected.source_sha256,
            producer_identity=_required_string(model_state, "identity"),
        )
    except Exception as exc:  # noqa: BLE001 - structural failures invalidate execution.
        result = _invalid_result(
            preregistration_sha256=preregistration_sha256,
            preflight=preflight,
            stage="SCIENTIFIC_EVENT_IR_VALIDATION",
            root_cause=str(exc),
        )
        _write_artifacts(
            receipt_path=artifacts.receipt,
            receipt=execution.receipt,
            result_path=artifacts.result,
            result=result,
            report_path=artifacts.report,
        )
        return "INVALID_EXPERIMENT"

    gold_documents = project_development_directory(
        repository_root / DEVELOPMENT_DIRECTORY
    )
    gold = next(
        document
        for document in gold_documents
        if document.document_id == selected.document_id
    )
    score = score_scientific_event_document(gold=gold, predicted=predicted)
    decision = (
        "DEVELOPMENT_GATE_PASSED"
        if score.scientific_gate_passed
        else "DEVELOPMENT_GATE_FAILED"
    )
    final_result: dict[str, object] = {
        "schema_version": "artana.public_gold.lossless_event_result.v2",
        "decision": decision,
        "qualification_status": "DEVELOPMENT_ONLY_NON_QUALIFYING",
        "preregistration_sha256": preregistration_sha256,
        "preflight": preflight,
        "source": {
            "document_id": source_state["selected_document_id"],
            "source_sha256": source_state["selected_source_sha256"],
        },
        "provider_receipt_sha256": canonical_sha256(execution.receipt),
        "predicted_document_sha256": canonical_sha256(
            predicted.model_dump(mode="json")
        ),
        "score": score.as_json(),
        "terminal_rules": {
            "provider_calls": 1,
            "provider_retries": 0,
            "fallbacks": 0,
            "repairs": 0,
            "graph_writes": 0,
            "promotions": 0,
            "sealed_test_sources_accessed": 0,
        },
    }
    _write_artifacts(
        receipt_path=artifacts.receipt,
        receipt=execution.receipt,
        result_path=artifacts.result,
        result=final_result,
        report_path=artifacts.report,
    )
    return decision


def _invalid_result(
    *,
    preregistration_sha256: str,
    preflight: dict[str, object],
    stage: str,
    root_cause: str,
) -> dict[str, object]:
    return {
        "schema_version": "artana.public_gold.lossless_event_result.v2",
        "decision": "INVALID_EXPERIMENT",
        "qualification_status": "DEVELOPMENT_ONLY_NON_QUALIFYING",
        "preregistration_sha256": preregistration_sha256,
        "preflight": preflight,
        "failure": {"stage": stage, "root_cause": root_cause},
        "terminal_rules": {
            "provider_retries": 0,
            "fallbacks": 0,
            "repairs": 0,
            "graph_writes": 0,
            "promotions": 0,
            "sealed_test_sources_accessed": 0,
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
    decision = _required_string(result, "decision")
    if decision not in DECISIONS:
        raise ValueError("result decision is invalid")
    score = result.get("score")
    failure = result.get("failure")
    report = [
        "# Lossless Scientific Event Development Experiment V2",
        "",
        f"**Decision:** `{decision}`",
        "",
        "This is a one-call exposed-development result. It does not qualify the sealed test split, graph writes, or trusted promotion.",
        "",
        "## Integrity",
        "",
        f"- Preregistration: `{result['preregistration_sha256']}`",
        "- Provider retries: `0`",
        "- Fallbacks and repairs: `0`",
        "- Graph writes and promotions: `0`",
        "- Sealed test sources accessed: `0`",
    ]
    if isinstance(score, dict):
        report.extend(
            [
                "",
                "## Deterministic Scientific Result",
                "",
                "```json",
                json.dumps(score, indent=2, sort_keys=True),
                "```",
            ]
        )
    if isinstance(failure, dict):
        report.extend(
            [
                "",
                "## Invalidating Failure",
                "",
                f"- Stage: `{failure.get('stage')}`",
                f"- Root cause: {failure.get('root_cause')}",
            ]
        )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _required_dict(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be an object")
    return value


def _required_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _required_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a nonnegative integer")
    return value


def _required_float(payload: dict[str, object], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, int | float) or value <= 0:
        raise ValueError(f"{key} must be a positive number")
    return float(value)


def _pricing(payload: dict[str, object]) -> dict[str, float]:
    return {
        key: _required_float(payload, key)
        for key in ("input", "cached_input", "output")
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, required=True)
    args = parser.parse_args()
    repository_root = Path(__file__).resolve().parents[3]
    decision = run_experiment(
        repository_root=repository_root,
        preregistration_path=args.preregistration,
        artifacts=ExperimentArtifactPaths(
            receipt=args.receipt,
            result=args.result,
            report=args.report,
            raw_output=args.raw_output,
        ),
    )
    print(decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
