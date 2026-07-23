"""Forward-only V10 exposed execution and historical isolation regressions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
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
    policy_sha256,
)
from scripts.validation.public_gold.staged_event.generalization.panel import build_panel
from scripts.validation.public_gold.staged_event.generalization.repair_v9.config import (
    DEFAULT_PATHS as V9_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.preflight import (
    V9PreflightError,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.preflight import (
    verify as verify_v9,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10 import (
    execution_provider,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_acceptance import (
    compare_with_v9,
    evaluate_acceptance,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    DEFAULT_PATHS,
    CaseExecutionPaths,
    V10ExecutionPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_preflight import (
    provider_input,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_preflight import (
    verify as verify_v10_execution,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_runner import (
    V10Runtime,
    execute,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.historical_v9 import (
    HistoricalV9ProvenanceError,
    verify_provenance,
)

REPO = Path(__file__).resolve().parents[2]
_V1_V2_SEALED_HASHES = {
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
}


def test_historical_v9_reproduces_at_pin_but_not_under_current_receipt_code() -> None:
    with pytest.raises(
        V9PreflightError,
        match="independently recomputed frozen state",
    ):
        verify_v9(V9_PATHS)

    provenance = verify_provenance()
    failure = cast("dict[str, object]", provenance["reported_failure"])
    disposition = cast("dict[str, object]", provenance["disposition"])

    assert provenance["historical_code_manifest_match"] is True
    assert provenance["current_checkout_code_manifest_match"] is False
    assert len(
        cast(
            "list[dict[str, str]]",
            provenance["current_checkout_code_manifest_mismatches"],
        )
    ) == 6
    assert failure == {
        "file": "scripts/validation/provider_receipt_boundary/__init__.py",
        "expected_sha256": (
            "f5352623348b5b3a2d30a217c535a9c4a19bd50eadeec2d583218337bff7260a"
        ),
        "observed_sha256": (
            "8291018b46a4db88ac589a730f4dc247c2aeb7ede6d01f3aeca41f0c47668510"
        ),
        "change_commit": "8778bf427006d9e01daa76c56e56119457adc0e6",
        "change_predates_v10_base": True,
        "change_postdates_v9_seal": True,
    }
    assert disposition["sealed_v9_rewrite_authorized"] is False
    assert disposition["sealed_v9_rescore_authorized"] is False
    assert disposition["current_receipt_code_authorized_for_v9"] is False


def test_historical_isolation_rejects_modified_v9_preregistration(
    tmp_path: Path,
) -> None:
    changed = tmp_path / "changed-v9.json"
    value = json.loads(DEFAULT_PATHS.v9_preregistration.read_text(encoding="utf-8"))
    value["authorization"] = "SILENTLY_REAUTHORIZED"
    changed.write_text(json.dumps(value), encoding="utf-8")
    paths = replace(DEFAULT_PATHS, v9_preregistration=changed)

    with pytest.raises(
        HistoricalV9ProvenanceError,
        match="sealed historical preregistration changed",
    ):
        verify_provenance(paths)


def test_v10_execution_preregistration_is_reproducible_and_blind() -> None:
    preregistration = verify_v10_execution()
    frozen = cast("dict[str, object]", preregistration["frozen_state"])
    provider = cast("dict[str, object]", frozen["provider"])

    assert preregistration["single_scientific_change"] == (
        "NAMED_BIOMEDICAL_OCCURRENCE_BOUNDARY"
    )
    assert provider["model"] == "openai:gpt-5.6-luna"
    assert provider["reasoning_effort"] == "high"
    assert provider["application_max_output_tokens"] is None
    assert provider["application_max_total_tokens"] is None
    assert provider["provider_retries"] == 0
    assert provider["fallback"] is False
    for case in build_panel():
        value = provider_input(DEFAULT_PATHS, case.case_id)
        assert '"reference"' not in value
        assert "acceptable_texts" not in value
        assert "direct CG" not in value
        assert "V3 corrected reference" not in value


def test_v10_provider_request_omits_generation_limits(
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
        execution_provider,
        "execute_background_provider_call_telemetry_v2",
        fake_execute,
    )
    result = execution_provider.execute_case(
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


def test_v10_accepts_exact_slc12a3_without_suffix_and_preserves_v9_science() -> None:
    case = next(
        item for item in build_panel() if item.case_id == "generalization-uncertainty"
    )
    output = V9StagedGeneralizationOutput.model_validate_json(
        DEFAULT_PATHS.v9_raw_output(case.case_id).read_text(encoding="utf-8")
    )
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
    policy = verify_frozen_policy(DEFAULT_PATHS.grading)
    metrics = evaluate_case(
        case,
        corrected,
        case_policy(policy, case.case_id),
    )
    baseline = _baseline(case.case_id)
    comparison = compare_with_v9(metrics, baseline)
    acceptance = evaluate_acceptance(
        corrected,
        metrics,
        comparison,
        v9_baseline_passed=True,
    )

    assert metrics.passed is True
    assert comparison.regressed_fields == ()
    assert acceptance.target_correction_observed is True
    assert acceptance.forbidden_suffix_absent is True
    assert acceptance.passed is True


def test_large_usage_is_recorded_and_only_stops_the_next_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    canary = V9StagedGeneralizationOutput.model_validate_json(
        DEFAULT_PATHS.v9_raw_output("generalization-comparison-canary").read_text(
            encoding="utf-8"
        )
    )
    calls: list[str] = []

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        _case_paths: CaseExecutionPaths,
    ) -> BackgroundProviderExecution[V9StagedGeneralizationOutput]:
        calls.append(case_id)
        return _execution(canary, "response-v10-budget", cost_usd=5.25)

    monkeypatch.setenv("OPENAI_API_KEY", "redacted-test-key")
    decision = execute(V10Runtime(call), paths=paths, remote_gate=False)
    result = cast(
        "dict[str, object]",
        json.loads(paths.result.read_text(encoding="utf-8")),
    )
    outcomes = cast("list[dict[str, object]]", result["case_outcomes"])

    assert decision == "INVALID_V10_EXECUTION"
    assert calls == ["generalization-comparison-canary"]
    assert result["failure_stage"] == "OPERATIONAL_BUDGET_STOP"
    assert result["provider_calls"] == 1
    assert result["provider_retries"] == 0
    assert result["duplicate_creation_calls"] == 0
    assert result["output_tokens"] == 900_000
    assert result["cost_usd"] == pytest.approx(5.25)
    assert cast("dict[str, object]", outcomes[0]["boundary_acceptance"])[
        "passed"
    ] is True


def test_v10_stops_after_first_scientific_regression_and_persists_evaluation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    canary = V9StagedGeneralizationOutput.model_validate_json(
        DEFAULT_PATHS.v9_raw_output("generalization-comparison-canary").read_text(
            encoding="utf-8"
        )
    )
    wrong_axes = canary.semantic_axes[0].model_copy(update={"direction": "DECREASED"})
    failing = canary.model_copy(update={"semantic_axes": (wrong_axes,)})
    calls: list[str] = []

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        _case_paths: CaseExecutionPaths,
    ) -> BackgroundProviderExecution[V9StagedGeneralizationOutput]:
        calls.append(case_id)
        return _execution(failing, "response-v10-scientific-fail", cost_usd=0.01)

    monkeypatch.setenv("OPENAI_API_KEY", "redacted-test-key")
    decision = execute(V10Runtime(call), paths=paths, remote_gate=False)
    result = cast(
        "dict[str, object]",
        json.loads(paths.result.read_text(encoding="utf-8")),
    )

    assert decision == "V10_EXPOSED_GATE_FAIL_MODEL_CORRECTION_REQUIRED"
    assert calls == ["generalization-comparison-canary"]
    assert result["first_failure_classification"] == (
        "UNRELATED_SCIENTIFIC_REGRESSION"
    )
    assert paths.case("generalization-comparison-canary").evaluation.exists()
    assert not paths.case("generalization-null-statistics").attempt.exists()
    assert result["provider_retries"] == 0
    assert result["duplicate_creation_calls"] == 0


def test_checked_in_v10_result_recomputes_and_preserves_fail_fast_custody() -> None:
    result = cast(
        "dict[str, object]",
        json.loads(DEFAULT_PATHS.result.read_text(encoding="utf-8")),
    )
    outcomes = cast("list[dict[str, object]]", result["case_outcomes"])
    case_ids = [cast("str", item["case_id"]) for item in outcomes]
    panel = {case.case_id: case for case in build_panel()}
    policy = verify_frozen_policy(DEFAULT_PATHS.grading)
    preregistration_sha256 = hashlib.sha256(
        DEFAULT_PATHS.execution_preregistration.read_bytes()
    ).hexdigest()
    schema_sha256 = cast(
        "dict[str, object]",
        cast(
            "dict[str, object]",
            json.loads(
                DEFAULT_PATHS.execution_preregistration.read_text(encoding="utf-8")
            ),
        )["frozen_state"],
    )["schema_sha256"]
    response_ids: list[str] = []

    assert result["decision"] == (
        "V10_EXPOSED_GATE_FAIL_MODEL_CORRECTION_REQUIRED"
    )
    assert case_ids == [
        "generalization-comparison-canary",
        "generalization-null-statistics",
        "generalization-negated-association",
    ]
    assert result["first_failure_classification"] == (
        "UNRELATED_SCIENTIFIC_REGRESSION"
    )
    assert result["slc12a3_corrected_by_actual_model_call"] is False
    assert result["provider_calls"] == 3
    assert result["provider_retries"] == 0
    assert result["duplicate_creation_calls"] == 0
    assert result["cost_usd"] == pytest.approx(0.150774)
    assert result["remaining_cost_usd"] == pytest.approx(4.849226)
    assert result["fresh_cases_consumed"] == 0
    assert result["graph_writes"] == 0
    assert result["trusted_promotion"] is False
    assert result["optional_consumed_case_diagnostic"] == (
        "SKIPPED_PUBLIC_GATE_FAILED"
    )
    assert result["grading_policy_sha256"] == policy_sha256(policy)

    for outcome, case_id in zip(outcomes, case_ids, strict=True):
        case_paths = DEFAULT_PATHS.case(case_id)
        output = V9StagedGeneralizationOutput.model_validate_json(
            case_paths.raw_output.read_text(encoding="utf-8")
        )
        metrics = evaluate_case(
            panel[case_id],
            output,
            case_policy(policy, case_id),
        )
        baseline = _baseline(case_id)
        comparison = compare_with_v9(metrics, baseline)
        acceptance = evaluate_acceptance(
            output,
            metrics,
            comparison,
            v9_baseline_passed=cast("bool", baseline["passed"]),
        )
        attempt = cast(
            "dict[str, object]",
            json.loads(case_paths.attempt.read_text(encoding="utf-8")),
        )
        bundle = cast(
            "dict[str, object]",
            json.loads(case_paths.bundle.read_text(encoding="utf-8")),
        )
        receipt = cast(
            "dict[str, object]",
            json.loads(case_paths.receipt.read_text(encoding="utf-8")),
        )
        identity = cast("dict[str, object]", receipt["identity"])
        budgets = cast("dict[str, object]", receipt["budgets"])
        response_id = cast("str", identity["response_id"])

        assert outcome["scientific_grader"] == json.loads(
            json.dumps(asdict(metrics))
        )
        assert outcome["v9_comparison"] == json.loads(
            json.dumps(asdict(comparison))
        )
        assert outcome["boundary_acceptance"] == json.loads(
            json.dumps(acceptance.as_json())
        )
        assert attempt["preregistration_sha256"] == preregistration_sha256
        assert attempt["provider_creation_limit"] == 1
        assert attempt["provider_retries"] == 0
        assert attempt["response_id"] == response_id
        assert bundle["response_id"] == response_id
        assert bundle["provider_input_sha256"] == hashlib.sha256(
            provider_input(DEFAULT_PATHS, case_id).encode()
        ).hexdigest()
        assert bundle["schema_sha256"] == schema_sha256
        assert bundle["typed_output"] == output.model_dump(mode="json")
        assert bundle["receipt"] == receipt
        assert receipt["status"] == "VERIFIED_LIVE"
        assert receipt["provider_creation_calls"] == 1
        assert receipt["provider_retries"] == 0
        assert receipt["duplicate_creation_calls"] == 0
        assert receipt["confirmation_retrieval_requests"] == 1
        assert receipt["input_item_retrieval_requests"] == 1
        assert budgets["requested_max_output_tokens"] is None
        assert budgets["requested_max_total_tokens"] is None
        assert budgets["output_tokens"] == "RECORD_ONLY"
        assert budgets["total_tokens"] == "RECORD_ONLY"
        assert budgets["latency"] == "RECORD_ONLY"
        assert budgets["cost"] == "RECORD_ONLY"
        response_ids.append(response_id)

    assert len(response_ids) == len(set(response_ids)) == 3
    failed = cast("dict[str, object]", outcomes[-1]["scientific_grader"])
    assert failed["failure_reasons"] == [
        "evidence grounding failed: evidence item is absent or ambiguous in context"
    ]
    assert failed["exact_evidence_grounding"] is False
    assert failed["required_core_complete"] is True
    failed_output = V9StagedGeneralizationOutput.model_validate_json(
        DEFAULT_PATHS.case("generalization-negated-association").raw_output.read_text(
            encoding="utf-8"
        )
    )
    assert failed_output.semantic_axes[0].evidence_items == (
        "steroid dose before ICI initiation",
        "was no longer associated with",
        "OS",
    )
    for uncalled in (
        "generalization-uncertainty",
        "generalization-drug-sensitivity",
        "generalization-explicit-nested-cause",
    ):
        case_paths = DEFAULT_PATHS.case(uncalled)
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


def test_sealed_v1_v2_artifacts_remain_byte_identical() -> None:
    for relative_path, expected in _V1_V2_SEALED_HASHES.items():
        assert hashlib.sha256((REPO / relative_path).read_bytes()).hexdigest() == (
            expected
        )


def _paths(tmp_path: Path) -> V10ExecutionPaths:
    return replace(
        DEFAULT_PATHS,
        result=tmp_path / "result.json",
        report=tmp_path / "report.md",
        receipts=tmp_path / "receipts",
        raw_outputs=tmp_path / "raw",
        evaluations=tmp_path / "evaluations",
    )


def _baseline(case_id: str) -> dict[str, object]:
    result = cast(
        "dict[str, object]",
        json.loads(DEFAULT_PATHS.v9_result.read_text(encoding="utf-8")),
    )
    return next(
        cast("dict[str, object]", item)
        for item in cast("list[object]", result["cases"])
        if cast("dict[str, object]", item)["case_id"] == case_id
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
