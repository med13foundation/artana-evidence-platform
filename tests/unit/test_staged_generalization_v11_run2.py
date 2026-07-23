"""V11 run-2 operational-continuation and reporting regressions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from scripts.validation.provider_receipt_boundary.foreground import (
    ForegroundProviderExecution,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.attempts import (
    acknowledge_attempt,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    CaseExecutionPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11.config import (
    DEFAULT_PATHS as V11_SCIENCE_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2 import (
    runner,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.artifacts import (
    RUN1_SEALED_SHA256,
    report_correction,
    verify_operational_artifacts,
    write_operational_artifacts,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
    QualificationPaths,
    V11Run2Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.reporting import (
    render_final_report,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.qualification import (
    verify_qualification_preregistration,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.runner import (
    V11Run2Runtime,
    execute,
)


def test_run1_correction_preserves_sealed_bytes_and_explains_invalidity(
    tmp_path: Path,
) -> None:
    paths = replace(
        DEFAULT_PATHS,
        operational_diagnosis=tmp_path / "diagnosis.json",
        report_correction=tmp_path / "correction.md",
    )

    write_operational_artifacts(paths)
    verify_operational_artifacts(paths)

    for name, expected in RUN1_SEALED_SHA256.items():
        sealed_path = {
            "preregistration": paths.run1_preregistration,
            "result": paths.run1_result,
            "report": paths.run1_report,
            "seal": paths.run1_seal,
            "attempt": paths.run1_attempt,
            "late_status": paths.run1_late_status,
        }[name]
        assert hashlib.sha256(sealed_path.read_bytes()).hexdigest() == expected
    correction = paths.report_correction.read_text(encoding="utf-8")
    assert correction == report_correction()
    assert "SEMANTIC_EVIDENCE_PROMPT_CONTRACT_GAP" in correction
    assert "UNIQUE_COMPLETE_SEMANTIC_EVIDENCE_GROUNDING" in correction
    assert "neither" in correction
    assert "scientifically validated" in correction


def test_invalid_report_retains_preregistered_context() -> None:
    report = render_final_report(
        {
            "decision": "INVALID_V11_RUN_V2_EXECUTION",
            "preregistered_root_cause_classification": (
                "SEMANTIC_EVIDENCE_PROMPT_CONTRACT_GAP"
            ),
            "frozen_scientific_change": (
                "UNIQUE_COMPLETE_SEMANTIC_EVIDENCE_GROUNDING"
            ),
            "scientific_contract_validated_during_run": False,
            "operational_root_cause_classification": "PROVIDER_QUEUE_STALL",
            "transport": "DIRECT_OPENAI_FOREGROUND_RESPONSES",
            "run1_report_correction_sha256": "a" * 64,
            "case_outcomes": [],
        }
    )

    assert "Preregistered root cause: `None`" not in report
    assert "Frozen V11 change: `None`" not in report
    assert "SEMANTIC_EVIDENCE_PROMPT_CONTRACT_GAP" in report
    assert "UNIQUE_COMPLETE_SEMANTIC_EVIDENCE_GROUNDING" in report
    assert "did not scientifically validate either" in report


def test_foreground_qualification_is_preregistered_without_scientific_credit() -> None:
    preregistration = verify_qualification_preregistration()
    provider = _object(preregistration["provider"])
    acceptance = _object(preregistration["acceptance"])

    assert provider["transport"] == "DIRECT_OPENAI_FOREGROUND_RESPONSES"
    assert provider["background"] is False
    assert provider["provider_retries"] == 0
    assert provider["fallback"] is False
    assert provider["application_max_output_tokens"] is None
    assert provider["application_max_total_tokens"] is None
    assert acceptance["one_creation_call"] is True
    assert acceptance["scientific_credit"] is False


def test_large_scientific_usage_is_admitted_before_global_budget_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    canary = _raw_v9("generalization-comparison-canary")
    calls: list[str] = []

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        case_paths: CaseExecutionPaths,
    ) -> ForegroundProviderExecution[V9StagedGeneralizationOutput]:
        calls.append(case_id)
        response_id = "response-v11-run2-budget"
        acknowledge_attempt(case_paths.attempt, response_id=response_id)
        return _execution(canary, response_id, cost_usd=5.25)

    monkeypatch.setattr(runner, "verify", lambda *_args, **_kwargs: {})
    monkeypatch.setenv("OPENAI_API_KEY", "redacted-test-key")
    decision = execute(V11Run2Runtime(call), paths=paths, remote_gate=False)
    result = _object(json.loads(paths.result.read_text(encoding="utf-8")))
    outcomes = cast("list[dict[str, object]]", result["case_outcomes"])

    assert decision == "INVALID_V11_RUN_V2_EXECUTION"
    assert calls == ["generalization-comparison-canary"]
    assert result["failure_stage"] == "OPERATIONAL_BUDGET_STOP"
    assert result["failed_case_id"] == "generalization-uncertainty"
    assert result["provider_calls"] == 2
    assert result["transport_qualification_provider_calls"] == 1
    assert result["scientific_provider_calls"] == 1
    assert result["provider_retries"] == 0
    assert result["duplicate_creation_calls"] == 0
    assert result["cost_usd"] == pytest.approx(5.30)
    assert cast("dict[str, object]", outcomes[0]["v11_acceptance"])["passed"] is True
    assert result["scientific_contract_validated_during_run"] is False
    assert not paths.case("generalization-uncertainty").attempt.exists()


def test_run2_reaches_boundary_then_fails_fast_on_grounding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    outputs = {
        "generalization-comparison-canary": _raw_v9(
            "generalization-comparison-canary"
        ),
        "generalization-uncertainty": _corrected_uncertainty(),
        "generalization-negated-association": _raw_v10(
            "generalization-negated-association"
        ),
    }
    calls: list[str] = []

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        case_paths: CaseExecutionPaths,
    ) -> ForegroundProviderExecution[V9StagedGeneralizationOutput]:
        calls.append(case_id)
        response_id = f"response-v11-run2-{len(calls)}"
        acknowledge_attempt(case_paths.attempt, response_id=response_id)
        return _execution(outputs[case_id], response_id, cost_usd=0.01)

    monkeypatch.setattr(runner, "verify", lambda *_args, **_kwargs: {})
    monkeypatch.setenv("OPENAI_API_KEY", "redacted-test-key")
    decision = execute(V11Run2Runtime(call), paths=paths, remote_gate=False)
    result = _object(json.loads(paths.result.read_text(encoding="utf-8")))

    assert decision == "V11_EXPOSED_RUN_V2_FAIL_GROUNDING"
    assert calls == list(CASE_ORDER[:3])
    assert result["stopped_after_case_id"] == (
        "generalization-negated-association"
    )
    assert result["first_failure_classification"] == (
        "SEMANTIC_EVIDENCE_GROUNDING_FAILURE"
    )
    assert result["slc12a3_corrected_by_actual_model_call"] is True
    assert result["provider_calls"] == 4
    assert result["scientific_provider_calls"] == 3
    assert result["provider_retries"] == 0
    assert result["duplicate_creation_calls"] == 0
    assert not paths.case("generalization-null-statistics").attempt.exists()


def _paths(tmp_path: Path) -> V11Run2Paths:
    qualification = QualificationPaths(
        preregistration=tmp_path / "qualification-preregistration.json",
        attempt=tmp_path / "qualification-attempt.json",
        bundle=tmp_path / "qualification-custody.json",
        receipt=tmp_path / "qualification-receipt.json",
        raw_output=tmp_path / "qualification-raw.json",
        result=tmp_path / "qualification-result.json",
    )
    qualification.result.write_text(
        json.dumps(
            {
                "decision": "FOREGROUND_TRANSPORT_QUALIFIED",
                "response_id": "response-qualification",
                "provider_creation_calls": 1,
                "provider_retries": 0,
                "duplicate_creation_calls": 0,
                "usage": {
                    "input_tokens": 10,
                    "cached_input_tokens": 0,
                    "output_tokens": 10,
                    "reasoning_tokens": 2,
                    "total_tokens": 20,
                    "latency_seconds": 1.0,
                    "cost_usd": 0.05,
                },
            }
        ),
        encoding="utf-8",
    )
    correction = tmp_path / "report-correction.md"
    correction.write_text(report_correction(), encoding="utf-8")
    preregistration = tmp_path / "preregistration.json"
    preregistration.write_text("{}\n", encoding="utf-8")
    return replace(
        DEFAULT_PATHS,
        preregistration=preregistration,
        report_correction=correction,
        qualification=qualification,
        result=tmp_path / "result.json",
        report=tmp_path / "report.md",
        fresh_preregistration=tmp_path / "fresh-preregistration.json",
        receipts=tmp_path / "receipts",
        raw_outputs=tmp_path / "raw",
        evaluations=tmp_path / "evaluations",
    )


def _raw_v9(case_id: str) -> V9StagedGeneralizationOutput:
    return V9StagedGeneralizationOutput.model_validate_json(
        V11_SCIENCE_PATHS.v9_raw_output(case_id).read_text(encoding="utf-8")
    )


def _raw_v10(case_id: str) -> V9StagedGeneralizationOutput:
    return V9StagedGeneralizationOutput.model_validate_json(
        V11_SCIENCE_PATHS.v10_raw_output(case_id).read_text(encoding="utf-8")
    )


def _corrected_uncertainty() -> V9StagedGeneralizationOutput:
    output = _raw_v9("generalization-uncertainty")
    return output.model_copy(
        update={
            "participants": tuple(
                participant.model_copy(update={"exact_text": "SLC12A3"})
                if participant.exact_text == "SLC12A3 gene"
                else participant
                for participant in output.participants
            )
        }
    )


def _execution(
    output: V9StagedGeneralizationOutput,
    response_id: str,
    *,
    cost_usd: float,
) -> ForegroundProviderExecution[V9StagedGeneralizationOutput]:
    canonical = output.model_dump(mode="json")
    envelope: dict[str, object] = {"id": response_id, "background": False}
    return ForegroundProviderExecution(
        extraction=output,
        canonical_payload=canonical,
        creation_response=envelope,
        confirmation_response=envelope,
        receipt={
            "status": "VERIFIED_LIVE",
            "identity": {"response_id": response_id, "model": "gpt-5.6-luna"},
            "usage": {
                "input_tokens": 100,
                "cached_input_tokens": 0,
                "output_tokens": 900_000,
                "reasoning_tokens": 100_000,
                "total_tokens": 900_100,
                "latency_seconds": 1.0,
                "cost_usd": cost_usd,
            },
            "provider_creation_calls": 1,
            "confirmation_retrieval_requests": 1,
            "input_item_retrieval_requests": 1,
            "provider_retries": 0,
            "duplicate_creation_calls": 0,
            "budgets": {
                "policy": "RECORD_ONLY_NOT_PER_CALL_VALIDATION",
                "output_tokens": "RECORD_ONLY",
                "total_tokens": "RECORD_ONLY",
                "latency": "RECORD_ONLY",
                "cost": "RECORD_ONLY",
            },
        },
    )


def _object(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value
