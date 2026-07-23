"""V15 execution-policy, custody, and fail-fast runtime regressions."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

import pytest

from scripts.validation.public_gold.staged_event.context_experiment.source_first.attempts import (
    acknowledge_attempt,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    CaseExecutionPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.evaluation import (
    LaneStatus,
    V13CaseMetrics,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.provider_execution import (
    V13ProviderExecution,
    V13ProviderExecutionError,
    V13TransportEvidence,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.evaluation import (
    V14CaseEvaluation,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15 import (
    runner,
    terminal,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
    EXPERIMENT_ID,
    V15Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15.runner import (
    V15Runtime,
    execute,
)

REPO = Path(__file__).resolve().parents[2]
_CANARY_RAW = REPO / (
    "docs/validation/results/"
    "2026-07-23-staged-generalization-v11-exposed-run-v2-"
    "generalization-comparison-canary-raw.json"
)
_NESTED_CASE = "generalization-explicit-nested-cause"


@dataclass(frozen=True, slots=True)
class _CaseStub:
    case_id: str


def test_success_has_v15_identity_exactly_once_custody_and_separate_lanes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)
    raw = _metrics(
        case_id=_NESTED_CASE,
        passed=False,
        source_status="FAIL",
        cg_status="FAIL",
    )
    effective = _metrics(
        case_id=_NESTED_CASE,
        passed=True,
        source_status="PASS",
        cg_status="FAIL",
    )

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        case_paths: CaseExecutionPaths,
    ) -> V13ProviderExecution[V9StagedGeneralizationOutput]:
        response_id = "response-v15-success"
        acknowledge_attempt(case_paths.attempt, response_id=response_id)
        return _execution(
            _output(case_id),
            response_id,
            cost_usd=0.25,
            provider_retries=0,
        )

    _patch_execution_boundaries(
        monkeypatch,
        case_ids=(_NESTED_CASE,),
        evaluations_by_case={
            _NESTED_CASE: _evaluation(
                effective=effective,
                raw=raw,
                optional_observed=1,
                optional_accepted=1,
                normalization_status="ACCEPTED_SOURCE_ENTAILED_REDUNDANCY",
            )
        },
    )

    decision = execute(V15Runtime(call), paths=paths, remote_gate=False)
    result = _load(paths.result)
    evaluation = _load(paths.case(_NESTED_CASE).evaluation)
    custody = _load(paths.case(_NESTED_CASE).bundle)
    receipt = cast("dict[str, object]", custody["receipt"])

    assert decision == terminal.PASS_TERMINAL
    assert result["schema_version"] == (
        "artana.staged_generalization.v15_exposed_result.v1"
    )
    assert result["experiment_id"] == EXPERIMENT_ID
    assert result["single_scientific_change"] == (
        "FOCUS_CLOSURE_AND_ROLE_BEARING_OCCURRENCE_CUSTODY_V1"
    )
    assert result["scientific_change_kind"] == "PROVIDER_PROMPT_ONLY"
    assert result["evaluator_implementation"] == "repair_v14.evaluate_v14_case"
    assert result["evaluator_changed_from_v14"] is False
    assert result["sealed_v14_preserved"] is True
    assert result["v15_authorization_head"]
    assert result["v15_authorization_sha256"]
    assert result["operational_policy_version"] == (
        "artana.staged_generalization.v15_operational_policy.v1"
    )
    assert result["provider_calls"] == 1
    assert result["completed_provider_calls"] == 1
    assert result["admitted_provider_calls"] == 1
    assert result["rejected_provider_calls"] == 0
    assert result["confirmation_retrieval_requests"] == 1
    assert result["input_item_retrieval_requests"] == 1
    assert result["provider_retries"] == 0
    assert result["duplicate_creation_calls"] == 0
    assert result["transport_qualification_provider_calls_in_v15"] == 0
    assert "transport_qualification_provider_calls_in_v13" not in result
    assert receipt["provider_creation_calls"] == 1
    assert receipt["confirmation_retrieval_requests"] == 1
    assert receipt["input_item_retrieval_requests"] == 1
    assert receipt["provider_retries"] == 0
    assert receipt["duplicate_creation_calls"] == 0
    assert custody["stage"] == f"GENERALIZATION_V15_EXPOSED:{_NESTED_CASE}"
    assert evaluation["schema_version"] == (
        "artana.staged_generalization.v15_case_evaluation.v1"
    )
    assert "v14_evaluation" in evaluation
    assert "v15_evaluation" not in evaluation
    assert evaluation["evaluator_implementation"] == ("repair_v14.evaluate_v14_case")
    assert evaluation["scientific_decision_lane"] == "SOURCE_SEMANTICS"
    assert evaluation["bionlp_cg_projection_lane"] == "RAW_REVIEW_ONLY"
    source_lane = cast("list[dict[str, object]]", result["source_semantic_lane"])
    cg_lane = cast(
        "list[dict[str, object]]",
        result["raw_bionlp_cg_projection_lane"],
    )
    assert source_lane == [
        {
            "case_id": _NESTED_CASE,
            "status": "PASS",
            "passed": True,
            "failure_reasons": [],
        }
    ]
    assert cg_lane[0]["status"] == "FAIL"
    assert result["benchmark_projection_affects_scientific_decision"] is False
    assert result["fresh_cases_consumed"] == 0
    assert result["fresh_qualification_status"] == "NOT_STARTED"
    assert result["graph_writes"] == 0
    assert result["trusted_promotion"] is False
    assert not tuple(tmp_path.rglob("*fresh*"))


def test_scientific_failure_is_persisted_before_fail_fast(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)
    case_ids = CASE_ORDER[:2]
    calls: list[str] = []
    persistence_observed: list[bool] = []
    failed = _metrics(
        case_id=case_ids[0],
        passed=False,
        source_status="FAIL",
        cg_status="NOT_APPLICABLE",
    )

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        case_paths: CaseExecutionPaths,
    ) -> V13ProviderExecution[V9StagedGeneralizationOutput]:
        calls.append(case_id)
        response_id = "response-v15-scientific-fail"
        acknowledge_attempt(case_paths.attempt, response_id=response_id)
        return _execution(
            _output(case_id),
            response_id,
            cost_usd=0.01,
            provider_retries=0,
        )

    _patch_execution_boundaries(
        monkeypatch,
        case_ids=case_ids,
        evaluations_by_case={case_ids[0]: _evaluation(effective=failed)},
    )
    runtime = V15Runtime(
        call,
        after_case_persist=lambda: persistence_observed.append(
            paths.case(case_ids[0]).evaluation.exists()
        ),
    )

    decision = execute(runtime, paths=paths, remote_gate=False)
    result = _load(paths.result)

    assert decision == terminal.REGRESSION_FAIL_TERMINAL
    assert calls == [case_ids[0]]
    assert persistence_observed == [True]
    assert paths.case(case_ids[0]).evaluation.exists()
    assert result["scientifically_evaluated_case_ids"] == [case_ids[0]]
    assert result["first_failure_classification"] == "UNRELATED_REGRESSION"
    assert not paths.case(case_ids[1]).attempt.exists()


def test_rejected_completed_attempt_preserves_transport_and_usage_custody(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)
    case_ids = CASE_ORDER[:2]
    response_id = "response-v15-rejected"
    creation: dict[str, object] = {
        "id": response_id,
        "status": "completed",
        "output": [],
    }
    confirmation: dict[str, object] = {**creation, "confirmed": True}
    input_items: tuple[dict[str, object], ...] = (
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "frozen input"}],
        },
    )
    usage = _usage(cost_usd=0.02)

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        case_paths: CaseExecutionPaths,
    ) -> V13ProviderExecution[V9StagedGeneralizationOutput]:
        acknowledge_attempt(case_paths.attempt, response_id=response_id)
        raise V13ProviderExecutionError(
            "STRUCTURED_OUTPUT_SCHEMA",
            "injected schema rejection",
            evidence=V13TransportEvidence(
                response_ids=(response_id,),
                creation_response=creation,
                confirmation_response=confirmation,
                input_items=input_items,
                canonical_payload={"case_id": case_id, "completeness": "ABSTAIN"},
                usage=usage,
                latency_seconds=2.5,
                provider_creation_calls=1,
                completed_provider_calls=1,
                confirmation_retrieval_requests=1,
                input_item_retrieval_requests=1,
            ),
        )

    _patch_execution_boundaries(
        monkeypatch,
        case_ids=case_ids,
        evaluations_by_case={},
    )

    decision = execute(V15Runtime(call), paths=paths, remote_gate=False)
    result = _load(paths.result)
    receipt = _load(paths.case(case_ids[0]).receipt)
    custody = _load(paths.case(case_ids[0]).bundle)

    assert decision == terminal.INVALID_TERMINAL
    assert result["failure_stage"] == "STRUCTURED_OUTPUT_SCHEMA"
    assert result["attempted_provider_calls"] == 1
    assert result["completed_provider_calls"] == 1
    assert result["admitted_provider_calls"] == 0
    assert result["rejected_provider_calls"] == 1
    assert result["confirmation_retrieval_requests"] == 1
    assert result["input_item_retrieval_requests"] == 1
    assert result["cost_usd"] == pytest.approx(0.02)
    assert receipt["status"] == "REJECTED_UNADMITTED"
    assert receipt["stage"] == f"GENERALIZATION_V15_EXPOSED:{case_ids[0]}"
    transport = cast("dict[str, object]", receipt["transport_evidence"])
    assert transport["creation_response"] == creation
    assert transport["confirmation_response"] == confirmation
    assert transport["input_items"] == list(input_items)
    assert transport["usage"] == usage
    assert custody["status"] == "REJECTED_UNADMITTED"
    assert custody["stage"] == f"GENERALIZATION_V15_EXPOSED:{case_ids[0]}"
    assert not paths.case(case_ids[1]).attempt.exists()


def test_reused_response_id_fails_closed_and_rejects_second_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)
    case_ids = CASE_ORDER[:2]
    response_id = "response-v15-reused"
    calls: list[str] = []

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        case_paths: CaseExecutionPaths,
    ) -> V13ProviderExecution[V9StagedGeneralizationOutput]:
        calls.append(case_id)
        acknowledge_attempt(case_paths.attempt, response_id=response_id)
        return _execution(
            _output(case_id),
            response_id,
            cost_usd=0.01,
            provider_retries=0,
        )

    _patch_execution_boundaries(
        monkeypatch,
        case_ids=case_ids,
        evaluations_by_case={},
    )

    decision = execute(V15Runtime(call), paths=paths, remote_gate=False)
    result = _load(paths.result)

    assert decision == terminal.INVALID_TERMINAL
    assert calls == list(case_ids)
    assert result["failure_stage"] == "RESPONSE_ID_CUSTODY"
    assert result["attempted_provider_calls"] == 2
    assert result["completed_provider_calls"] == 2
    assert result["admitted_provider_calls"] == 1
    assert result["rejected_provider_calls"] == 1
    diagnostics = cast("dict[str, object]", result["diagnostics"])
    assert diagnostics["reused_response_ids"] == [response_id]


def test_nonzero_retry_receipt_fails_closed_without_next_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)
    case_ids = CASE_ORDER[:2]
    calls: list[str] = []

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        case_paths: CaseExecutionPaths,
    ) -> V13ProviderExecution[V9StagedGeneralizationOutput]:
        calls.append(case_id)
        response_id = "response-v15-retry"
        acknowledge_attempt(case_paths.attempt, response_id=response_id)
        return _execution(
            _output(case_id),
            response_id,
            cost_usd=0.01,
            provider_retries=1,
        )

    _patch_execution_boundaries(
        monkeypatch,
        case_ids=case_ids,
        evaluations_by_case={},
    )

    decision = execute(V15Runtime(call), paths=paths, remote_gate=False)
    result = _load(paths.result)

    assert decision == terminal.INVALID_TERMINAL
    assert calls == [case_ids[0]]
    assert result["failure_stage"] == "EXACTLY_ONCE_ACCOUNTING"
    assert result["provider_retries"] == 1
    assert result["duplicate_creation_calls"] == 0
    assert result["admitted_provider_calls"] == 0
    assert result["rejected_provider_calls"] == 1
    assert not paths.case(case_ids[1]).attempt.exists()


def test_cumulative_five_dollar_stop_persists_case_and_makes_no_next_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)
    case_ids = CASE_ORDER[:2]
    calls: list[str] = []

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        case_paths: CaseExecutionPaths,
    ) -> V13ProviderExecution[V9StagedGeneralizationOutput]:
        calls.append(case_id)
        response_id = "response-v15-budget"
        acknowledge_attempt(case_paths.attempt, response_id=response_id)
        return _execution(
            _output(case_id),
            response_id,
            cost_usd=5.0,
            provider_retries=0,
        )

    _patch_execution_boundaries(
        monkeypatch,
        case_ids=case_ids,
        evaluations_by_case={},
    )

    decision = execute(V15Runtime(call), paths=paths, remote_gate=False)
    result = _load(paths.result)

    assert decision == terminal.OPERATIONAL_BUDGET_TERMINAL
    assert calls == [case_ids[0]]
    assert result["failure_stage"] == "OPERATIONAL_BUDGET_STOP"
    assert result["provider_calls"] == 1
    assert result["cost_usd"] == pytest.approx(5.0)
    assert result["remaining_cost_usd"] == pytest.approx(0.0)
    assert result["budget_exhausted"] is True
    assert result["scientific_case_results_preserved"] is True
    assert paths.case(case_ids[0]).evaluation.exists()
    assert not paths.case(case_ids[1]).attempt.exists()
    diagnostics = cast("dict[str, object]", result["diagnostics"])
    assert diagnostics["next_case_not_called"] == case_ids[1]


def _patch_execution_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    *,
    case_ids: tuple[str, ...],
    evaluations_by_case: dict[str, V14CaseEvaluation],
) -> None:
    monkeypatch.setattr(
        runner,
        "ordered_cases",
        lambda _paths: tuple(_CaseStub(case_id) for case_id in case_ids),
    )
    monkeypatch.setattr(
        runner,
        "provider_input",
        lambda case_id, _paths: f"frozen input for {case_id}",
    )
    monkeypatch.setattr(runner, "verify", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        runner,
        "verify_v13_frozen_policy",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(runner, "case_policy", lambda *_args: object())
    monkeypatch.setattr(runner, "policy_sha256", lambda *_args: "a" * 64)
    monkeypatch.setattr(runner, "load_contract", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        runner,
        "evaluate_v14_case",
        lambda case, *_args, **_kwargs: evaluations_by_case.get(
            case.case_id,
            _evaluation(
                effective=_metrics(
                    case_id=case.case_id,
                    passed=True,
                    source_status="PASS",
                    cg_status="NOT_APPLICABLE",
                ),
            ),
        ),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "redacted-test-key")


def _temporary_paths(tmp_path: Path) -> V15Paths:
    preregistration = tmp_path / "preregistration.json"
    preregistration.write_text("{}\n", encoding="utf-8")
    return replace(
        DEFAULT_PATHS,
        preregistration=preregistration,
        result=tmp_path / "result.json",
        report=tmp_path / "report.md",
        receipts=tmp_path / "receipts",
        raw_outputs=tmp_path / "raw",
        evaluations=tmp_path / "evaluations",
    )


def _output(case_id: str) -> V9StagedGeneralizationOutput:
    output = V9StagedGeneralizationOutput.model_validate_json(
        _CANARY_RAW.read_text(encoding="utf-8")
    )
    return output.model_copy(update={"case_id": case_id})


def _execution(
    output: V9StagedGeneralizationOutput,
    response_id: str,
    *,
    cost_usd: float,
    provider_retries: int,
) -> V13ProviderExecution[V9StagedGeneralizationOutput]:
    creation: dict[str, object] = {
        "id": response_id,
        "status": "completed",
        "background": False,
    }
    confirmation: dict[str, object] = {**creation, "confirmed": True}
    input_items: tuple[dict[str, object], ...] = (
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "frozen input"}],
        },
    )
    return V13ProviderExecution(
        extraction=output,
        canonical_payload=output.model_dump(mode="json"),
        creation_response=creation,
        confirmation_response=confirmation,
        input_items=input_items,
        receipt={
            "status": "VERIFIED_LIVE",
            "identity": {
                "response_id": response_id,
                "model": "gpt-5.6-luna",
            },
            "usage": _usage(cost_usd=cost_usd),
            "provider_creation_calls": 1,
            "completed_provider_calls": 1,
            "confirmation_retrieval_requests": 1,
            "input_item_retrieval_requests": 1,
            "provider_retries": provider_retries,
            "duplicate_creation_calls": 0,
            "budgets": {
                "policy": "RECORD_ONLY_NOT_PER_CALL_VALIDATION",
                "output_tokens": "RECORD_ONLY",
                "total_tokens": "RECORD_ONLY",
                "latency": "RECORD_ONLY",
                "cost": "RECORD_ONLY",
            },
            "v13_transport_custody": {
                "creation_response": creation,
                "confirmation_response": confirmation,
                "input_items": list(input_items),
            },
        },
    )


def _usage(*, cost_usd: float) -> dict[str, object]:
    return {
        "input_tokens": 100,
        "cached_input_tokens": 0,
        "output_tokens": 900_000,
        "reasoning_tokens": 100_000,
        "total_tokens": 900_100,
        "latency_seconds": 1.0,
        "cost_usd": cost_usd,
    }


def _evaluation(
    *,
    effective: V13CaseMetrics,
    raw: V13CaseMetrics | None = None,
    optional_observed: int = 0,
    optional_accepted: int = 0,
    normalization_status: str = "NOT_APPLICABLE",
) -> V14CaseEvaluation:
    return V14CaseEvaluation(
        metrics=effective,
        raw_v13_metrics=raw or effective,
        optional_edge_observed_count=optional_observed,
        optional_edge_accepted_count=optional_accepted,
        normalization_status=normalization_status,
    )


def _metrics(
    *,
    case_id: str,
    passed: bool,
    source_status: LaneStatus,
    cg_status: LaneStatus,
) -> V13CaseMetrics:
    return V13CaseMetrics(
        case_id=case_id,
        passed=passed,
        focus_event_passed=passed,
        source_semantic_status=source_status,
        benchmark_projection_status=cg_status,
        benchmark_projection_scope=(
            "EXACT_CG_ROOT_DEPENDENCY_CHAIN"
            if case_id == _NESTED_CASE
            else "NOT_APPLICABLE"
        ),
        full_focus_cg_status=(
            "NOT_MEASURED_UNREPRESENTABLE"
            if case_id == _NESTED_CASE
            else "NOT_APPLICABLE"
        ),
        mandatory_participants_passed=passed,
        participant_roles_passed=passed,
        semantic_axes_passed=passed,
        exact_evidence_grounding=passed,
        unsupported_extraction_count=0 if passed else 1,
        permitted_context_count=0,
        benchmark_projection=None,
        failure_reasons=() if passed else ("injected scientific failure",),
        historical_grader_passed=passed,
        root_selection_status="PASS" if passed else "FAIL",
        completeness="COMPLETE",
        source_dimensions_except_root_passed=passed,
        root_only_failure=False,
    )


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value
