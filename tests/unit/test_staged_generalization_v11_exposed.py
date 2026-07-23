"""V11 semantic-evidence grounding and exposed-gate regressions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from scripts.validation.provider_receipt_boundary.background import (
    BackgroundProviderExecution,
    TelemetryProviderRequestV2,
)
from scripts.validation.public_gold.staged_event.generalization.grading.artifacts import (
    verify_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.grading.evaluation import (
    evaluate_case,
)
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    case_policy,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_acceptance import (
    compare_with_v9,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    CaseExecutionPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11 import (
    provider,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11.acceptance import (
    V11Acceptance,
    V11AcceptanceInput,
    evaluate_acceptance,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
    V11ExecutionPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11.preflight import (
    ordered_cases,
    provider_input,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11.preflight import (
    verify as verify_v11,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11.runner import (
    V11Runtime,
    execute,
)

REPO = Path(__file__).resolve().parents[2]
_SEALED_HASHES = {
    "docs/validation/preregistrations/2026-07-22-fresh-cg-occurrence-v2-v1.json": (
        "2b26d580422efedcb44b7de8d8b7e973f2dae04bff020cdce85f3b2b8d4c1b98"
    ),
    "docs/validation/results/2026-07-22-fresh-cg-occurrence-v2-v1.json": (
        "2a006ea527ef2f22670dd1ec61d9a39e099cac415047852a3f44cd4b8b67544a"
    ),
    "docs/validation/preregistrations/2026-07-22-fresh-cg-occurrence-v2-v2.json": (
        "144d54d3acbee866401499758603ace87a3e4c74deb0c970695234f8c7e52577"
    ),
    "docs/validation/results/2026-07-22-fresh-cg-occurrence-v2-v2.json": (
        "b98ac29ae7d2899b2781329d1cd9462e1948818e7b7c1160ab1ecebfc34e2ab5"
    ),
    "docs/validation/results/2026-07-22-fresh-cg-v3-exposed-case-replay-v1.json": (
        "9b36da7d111fb0cdd062b1e80a49337f426295e5c5a82f7fbae3b081526739b8"
    ),
    "docs/validation/preregistrations/2026-07-22-staged-generalization-v9.json": (
        "7a170db78370571f986208530547c5ee4ec85a148634002f87a18dcc486e85b9"
    ),
    "docs/validation/results/2026-07-22-staged-generalization-v9.json": (
        "034cc3f9265a514851dfc5fd39ac3aae81c154a071ed92bf95ed7e175494e399"
    ),
    "docs/validation/prompts/2026-07-22-staged-generalization-v10.md": (
        "9e154dd779c937226bbc59adbf36b69194a2f145f34eaebcf954416290b3e203"
    ),
    "docs/validation/preregistrations/"
    "2026-07-22-staged-generalization-v10-exposed-run-v1.json": (
        "bdcb5127609c2f2c491e0cae2089e1bae593ee85ab86c4fb03ca8ba04142a18a"
    ),
    "docs/validation/results/"
    "2026-07-22-staged-generalization-v10-exposed-run-v1.json": (
        "afeca31c8d15ce40c7c8cd75750d210353e807c55d121fec65b49b347bce4bb9"
    ),
    "docs/validation/reports/"
    "2026-07-22-staged-generalization-v10-exposed-run-v1-final.md": (
        "e59f6a41d37b19d4052d39da3233600cb949b9ce8fcceba2c82e10910ceaf3d3"
    ),
}


def test_v11_preregistration_is_single_change_reordered_and_blind() -> None:
    preregistration = verify_v11()
    frozen = cast("dict[str, object]", preregistration["frozen_state"])
    provider_contract = cast("dict[str, object]", frozen["provider"])

    assert preregistration["root_cause_classification"] == (
        "SEMANTIC_EVIDENCE_PROMPT_CONTRACT_GAP"
    )
    assert preregistration["single_scientific_change"] == (
        "UNIQUE_COMPLETE_SEMANTIC_EVIDENCE_GROUNDING"
    )
    assert tuple(cast("list[str]", frozen["case_order"])) == CASE_ORDER
    assert tuple(case.case_id for case in ordered_cases()) == CASE_ORDER
    assert provider_contract["model"] == "openai:gpt-5.6-luna"
    assert provider_contract["reasoning_effort"] == "high"
    assert provider_contract["application_max_output_tokens"] is None
    assert provider_contract["application_max_total_tokens"] is None
    assert provider_contract["provider_retries"] == 0
    for case in ordered_cases():
        value = provider_input(DEFAULT_PATHS, case.case_id)
        assert '"reference"' not in value
        assert "acceptable_texts" not in value
        assert "direct CG" not in value
        assert "V3 corrected reference" not in value
        assert "osteonectin" not in value


def test_v11_provider_request_omits_generation_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[TelemetryProviderRequestV2] = []

    def fake_execute(**kwargs: object) -> object:
        request = kwargs["request"]
        assert isinstance(request, TelemetryProviderRequestV2)
        captured.append(request)
        return object()

    monkeypatch.setattr(
        provider,
        "execute_background_provider_call_telemetry_v2",
        fake_execute,
    )
    result = provider.execute_case(
        api_key="redacted-test-key",
        case_id="case-1",
        provider_input="input",
        preregistration_sha256="a" * 64,
        paths=CaseExecutionPaths(
            attempt=tmp_path / "attempt.json",
            bundle=tmp_path / "bundle.json",
            receipt=tmp_path / "receipt.json",
            raw_output=tmp_path / "raw.json",
            evaluation=tmp_path / "evaluation.json",
        ),
    )

    assert result is not None
    assert len(captured) == 1
    assert not hasattr(captured[0], "max_output_tokens")
    assert not hasattr(captured[0], "max_total_tokens")
    assert not hasattr(captured[0], "max_cost_usd")


def test_v10_ambiguous_fragments_fail_and_v9_complete_sentence_passes() -> None:
    case = next(
        item
        for item in ordered_cases()
        if item.case_id == "generalization-negated-association"
    )
    v10_output = _raw_v10(case.case_id)
    v9_output = _raw_v9(case.case_id)
    v10_acceptance = _acceptance(case.case_id, v10_output)
    v9_acceptance = _acceptance(case.case_id, v9_output)

    assert v10_output.semantic_axes[0].evidence_items == (
        "steroid dose before ICI initiation",
        "was no longer associated with",
        "OS",
    )
    assert case.source.count("steroid dose before ICI initiation") == 2
    assert case.source.count("OS") == 6
    assert case.local_context.count("OS") == 2
    assert v10_acceptance.semantic_evidence_unique is False
    assert v10_acceptance.failure_classification == (
        "SEMANTIC_EVIDENCE_GROUNDING_FAILURE"
    )
    assert v9_acceptance.semantic_evidence_unique is True
    assert v9_acceptance.negated_complete_sentence_observed is True
    assert v9_acceptance.passed is True


def test_v11_preserves_slc12a3_boundary_acceptance() -> None:
    case_id = "generalization-uncertainty"
    output = _raw_v9(case_id)
    corrected = output.model_copy(
        update={
            "participants": tuple(
                participant.model_copy(update={"exact_text": "SLC12A3"})
                if participant.exact_text == "SLC12A3 gene"
                else participant
                for participant in output.participants
            )
        }
    )

    uncorrected = _acceptance(case_id, output)
    accepted = _acceptance(case_id, corrected)

    assert uncorrected.failure_classification == "BOUNDARY_RULE_ERROR"
    assert accepted.v10_boundary.target_correction_observed is True
    assert accepted.v10_boundary.forbidden_suffix_absent is True
    assert accepted.passed is True


def test_large_usage_is_scientifically_admitted_then_stops_before_next_call(
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
        _case_paths: CaseExecutionPaths,
    ) -> BackgroundProviderExecution[V9StagedGeneralizationOutput]:
        calls.append(case_id)
        return _execution(canary, "response-v11-budget", cost_usd=5.25)

    monkeypatch.setenv("OPENAI_API_KEY", "redacted-test-key")
    decision = execute(V11Runtime(call), paths=paths, remote_gate=False)
    result = cast(
        "dict[str, object]",
        json.loads(paths.result.read_text(encoding="utf-8")),
    )
    outcomes = cast("list[dict[str, object]]", result["case_outcomes"])

    assert decision == "INVALID_V11_EXECUTION"
    assert calls == ["generalization-comparison-canary"]
    assert result["failure_stage"] == "OPERATIONAL_BUDGET_STOP"
    assert result["failed_case_id"] == "generalization-uncertainty"
    assert result["provider_calls"] == 1
    assert result["provider_retries"] == 0
    assert result["duplicate_creation_calls"] == 0
    assert result["output_tokens"] == 900_000
    assert result["cost_usd"] == pytest.approx(5.25)
    assert cast("dict[str, object]", outcomes[0]["v11_acceptance"])["passed"] is True
    assert not paths.case("generalization-uncertainty").attempt.exists()


def test_v11_reaches_repaired_boundary_then_fail_fast_seals_grounding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    outputs = {
        "generalization-comparison-canary": _raw_v9("generalization-comparison-canary"),
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
        _case_paths: CaseExecutionPaths,
    ) -> BackgroundProviderExecution[V9StagedGeneralizationOutput]:
        calls.append(case_id)
        return _execution(
            outputs[case_id],
            f"response-v11-{len(calls)}",
            cost_usd=0.01,
        )

    monkeypatch.setenv("OPENAI_API_KEY", "redacted-test-key")
    decision = execute(V11Runtime(call), paths=paths, remote_gate=False)
    result = cast(
        "dict[str, object]",
        json.loads(paths.result.read_text(encoding="utf-8")),
    )

    assert decision == "V11_EXPOSED_GATE_FAIL_GROUNDING"
    assert calls == list(CASE_ORDER[:3])
    assert result["stopped_after_case_id"] == ("generalization-negated-association")
    assert result["first_failure_classification"] == (
        "SEMANTIC_EVIDENCE_GROUNDING_FAILURE"
    )
    assert result["slc12a3_corrected_by_actual_model_call"] is True
    assert result["provider_calls"] == 3
    assert result["provider_retries"] == 0
    assert result["duplicate_creation_calls"] == 0
    assert not paths.case("generalization-null-statistics").attempt.exists()


def test_v1_through_v10_sealed_artifacts_remain_byte_identical() -> None:
    for relative_path, expected in _SEALED_HASHES.items():
        assert hashlib.sha256((REPO / relative_path).read_bytes()).hexdigest() == (
            expected
        )


def test_checked_in_v11_timeout_is_invalid_unscored_and_exactly_once() -> None:
    result = cast(
        "dict[str, object]",
        json.loads(DEFAULT_PATHS.result.read_text(encoding="utf-8")),
    )
    attempt = cast(
        "dict[str, object]",
        json.loads(
            DEFAULT_PATHS.case("generalization-comparison-canary").attempt.read_text(
                encoding="utf-8"
            )
        ),
    )
    late_status = cast(
        "dict[str, object]",
        json.loads(
            (
                REPO / "docs/validation/receipts/"
                "2026-07-22-staged-generalization-v11-exposed-run-v1-"
                "generalization-comparison-canary-late-status.json"
            ).read_text(encoding="utf-8")
        ),
    )

    assert result["decision"] == "INVALID_V11_EXECUTION"
    assert result["failure_stage"] == "BACKGROUND_POLLING_TIMEOUT"
    assert result["failed_case_id"] == "generalization-comparison-canary"
    assert result["planned_case_count"] == 6
    assert result["executed_case_count"] == 0
    assert result["case_outcomes"] == []
    assert result["scientific_metrics_calculated_for_admitted_cases"] is False
    assert result["provider_calls"] == 1
    assert result["provider_retries"] == 0
    assert result["duplicate_creation_calls"] == 0
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0
    assert result["total_tokens"] == 0
    assert result["cost_usd"] == pytest.approx(0.0)
    assert result["remaining_cost_usd"] == pytest.approx(5.0)
    assert result["fresh_cases_consumed"] == 0
    assert result["remaining_fresh_cases_preserved"] == 7
    assert result["graph_writes"] == 0
    assert result["trusted_promotion"] is False
    diagnostics = cast("dict[str, object]", result["diagnostics"])
    assert diagnostics["polling_retrieval_requests"] == 170
    assert diagnostics["creation_repeated"] is False

    assert attempt["state"] == "ACKNOWLEDGED"
    assert attempt["provider_creation_limit"] == 1
    assert attempt["provider_retries"] == 0
    assert (
        attempt["preregistration_sha256"]
        == hashlib.sha256(DEFAULT_PATHS.preregistration.read_bytes()).hexdigest()
    )
    assert late_status["response_id"] == attempt["response_id"]
    assert late_status["provider_status"] == "queued"
    assert late_status["provider_usage"] is None
    assert late_status["creation_calls_after_terminal"] == 0
    assert late_status["provider_retries_after_terminal"] == 0
    assert late_status["scientific_admission"] is False
    assert late_status["scientific_rescore"] is False

    canary_paths = DEFAULT_PATHS.case("generalization-comparison-canary")
    assert not canary_paths.bundle.exists()
    assert not canary_paths.receipt.exists()
    assert not canary_paths.raw_output.exists()
    assert not canary_paths.evaluation.exists()
    for case_id in CASE_ORDER[1:]:
        case_paths = DEFAULT_PATHS.case(case_id)
        assert not any(
            path.exists()
            for path in (
                case_paths.attempt,
                case_paths.bundle,
                case_paths.receipt,
                case_paths.raw_output,
                case_paths.evaluation,
            )
        )


def _acceptance(
    case_id: str,
    output: V9StagedGeneralizationOutput,
) -> V11Acceptance:
    case = next(item for item in ordered_cases() if item.case_id == case_id)
    policy = verify_frozen_policy(DEFAULT_PATHS.grading)
    metrics = evaluate_case(case, output, case_policy(policy, case_id))
    v9_baseline = _baseline(DEFAULT_PATHS.v9_result, case_id)
    v10_baseline = _baseline(DEFAULT_PATHS.v10_result, case_id)
    return evaluate_acceptance(
        V11AcceptanceInput(
            case=case,
            output=output,
            metrics=metrics,
            v9_comparison=compare_with_v9(metrics, v9_baseline),
            v10_comparison=compare_with_v9(metrics, v10_baseline),
            v9_baseline_passed=(
                cast("bool", v9_baseline["passed"]) if v9_baseline is not None else None
            ),
        )
    )


def _baseline(path: Path, case_id: str) -> dict[str, object] | None:
    result = cast(
        "dict[str, object]",
        json.loads(path.read_text(encoding="utf-8")),
    )
    return next(
        (
            cast("dict[str, object]", item)
            for item in cast("list[object]", result["cases"])
            if cast("dict[str, object]", item)["case_id"] == case_id
        ),
        None,
    )


def _raw_v9(case_id: str) -> V9StagedGeneralizationOutput:
    return V9StagedGeneralizationOutput.model_validate_json(
        DEFAULT_PATHS.v9_raw_output(case_id).read_text(encoding="utf-8")
    )


def _raw_v10(case_id: str) -> V9StagedGeneralizationOutput:
    return V9StagedGeneralizationOutput.model_validate_json(
        DEFAULT_PATHS.v10_raw_output(case_id).read_text(encoding="utf-8")
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


def _paths(tmp_path: Path) -> V11ExecutionPaths:
    return replace(
        DEFAULT_PATHS,
        result=tmp_path / "result.json",
        report=tmp_path / "report.md",
        receipts=tmp_path / "receipts",
        raw_outputs=tmp_path / "raw",
        evaluations=tmp_path / "evaluations",
    )


def _execution(
    output: V9StagedGeneralizationOutput,
    response_id: str,
    *,
    cost_usd: float,
) -> BackgroundProviderExecution[V9StagedGeneralizationOutput]:
    canonical = output.model_dump(mode="json")
    envelope: dict[str, object] = {"id": response_id}
    return BackgroundProviderExecution(
        extraction=output,
        canonical_payload=canonical,
        acknowledgement_response=envelope,
        terminal_response=envelope,
        confirmation_response=envelope,
        receipt={
            "status": "VERIFIED_LIVE_TELEMETRY_V2",
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
