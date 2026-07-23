"""V13 execution-policy and fail-fast runtime regressions."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

import pytest
from pydantic import BaseModel

from scripts.validation.public_gold.staged_event.context_experiment.source_first.attempts import (
    acknowledge_attempt,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    CaseExecutionPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13 import (
    runner,
    terminal,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.acceptance import (
    failure_classification,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.accounting import (
    V13OperationalAccountingError,
    V13OperationalLedger,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
    V13Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.evaluation import (
    LaneStatus,
    V13CaseMetrics,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.provider import (
    build_request,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.provider_execution import (
    V13ProviderExecution,
    V13ProviderExecutionError,
    V13TransportEvidence,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.rejected_custody import (
    V13RejectedCustodyError,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.reporting import (
    write_final_report,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.runner import (
    V13Runtime,
    execute,
)

REPO = Path(__file__).resolve().parents[2]
_CANARY_RAW = REPO / (
    "docs/validation/results/"
    "2026-07-23-staged-generalization-v11-exposed-run-v2-"
    "generalization-comparison-canary-raw.json"
)


@dataclass(frozen=True, slots=True)
class _CaseStub:
    case_id: str


def test_provider_request_omits_all_application_generation_limits() -> None:
    request = build_request(
        case_id=CASE_ORDER[0],
        provider_input="frozen input",
        preregistration_sha256="a" * 64,
    )

    assert not hasattr(request, "max_output_tokens")
    assert not hasattr(request, "max_total_tokens")
    assert not hasattr(request, "max_cost_usd")
    assert request.metadata["artana_scientific_change"] == (
        "COMPOSITIONAL_FOCUS_ROOT_SELECTION"
    )
    assert request.metadata["artana_evaluation_contract"] == (
        "SOURCE_SEMANTICS_WITH_REVIEW_ONLY_CG_PROJECTION"
    )


def test_review_only_cg_failure_cannot_be_a_scientific_failure() -> None:
    metrics = _metrics(
        case_id="generalization-explicit-nested-cause",
        passed=True,
        source_status="PASS",
        cg_status="FAIL",
    )

    assert failure_classification(metrics) is None


def test_pass_result_seals_without_generating_a_fresh_draft(
    tmp_path: Path,
) -> None:
    paths = _temporary_paths(tmp_path)
    metrics = _metrics(
        case_id="generalization-explicit-nested-cause",
        passed=True,
        source_status="PASS",
        cg_status="FAIL",
    )

    decision = terminal.persist_scientific_terminal(
        paths,
        outcomes=(
            terminal.CaseOutcome(
                case_id=metrics.case_id,
                response_id="response-v13-pass",
                usage={},
                metrics=metrics,
                failure_classification=None,
            ),
        ),
        ledger=V13OperationalLedger(),
        planned_case_count=1,
        grading_policy_sha256="a" * 64,
    )

    assert decision == terminal.PASS_TERMINAL
    result = _load(paths.result)
    assert result["next_fresh_preregistration"] is None
    assert result["fresh_qualification_status"] == "PENDING_INDEPENDENT_REVIEW"
    assert result["automatic_fresh_draft_generated"] is False
    assert not paths.next_fresh_preregistration.exists()


def test_final_report_exclusive_failure_preserves_existing_bytes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sealed-report.md"
    original = b"sealed report bytes\n"
    path.write_bytes(original)

    with pytest.raises(FileExistsError):
        write_final_report(path, {"decision": "SHOULD_NOT_OVERWRITE"})

    assert path.read_bytes() == original


def test_large_usage_is_recorded_without_changing_scientific_status() -> None:
    output = _output(CASE_ORDER[0])
    execution = _execution(
        output,
        "response-v13-large",
        cost_usd=5.25,
        provider_retries=0,
    )

    ledger = V13OperationalLedger().record_execution(
        case_id=CASE_ORDER[0],
        execution=cast(
            "V13ProviderExecution[BaseModel]",
            execution,
        ),
    )
    value = ledger.as_json(global_max_cost_usd=5.0)

    assert value["output_tokens"] == 900_000
    assert value["cost_usd"] == pytest.approx(5.25)
    assert value["budget_exhausted"] is True
    assert value["scientific_scoring_affected_by_tokens_latency_or_cost"] is False


def test_response_id_cannot_be_reused_across_cases() -> None:
    first = _execution(
        _output(CASE_ORDER[0]),
        "response-v13-reused",
        cost_usd=0.01,
        provider_retries=0,
    )
    second = _execution(
        _output(CASE_ORDER[1]),
        "response-v13-reused",
        cost_usd=0.01,
        provider_retries=0,
    )
    ledger = V13OperationalLedger().record_execution(
        case_id=CASE_ORDER[0],
        execution=cast("V13ProviderExecution[BaseModel]", first),
    )

    with pytest.raises(
        V13OperationalAccountingError,
        match="response ID was reused",
    ):
        ledger.record_execution(
            case_id=CASE_ORDER[1],
            execution=cast("V13ProviderExecution[BaseModel]", second),
        )


def test_cumulative_budget_stops_before_reserving_the_next_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)
    calls: list[str] = []

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        case_paths: CaseExecutionPaths,
    ) -> V13ProviderExecution[V9StagedGeneralizationOutput]:
        calls.append(case_id)
        response_id = "response-v13-budget"
        acknowledge_attempt(case_paths.attempt, response_id=response_id)
        return _execution(
            _output(case_id),
            response_id,
            cost_usd=5.25,
            provider_retries=0,
        )

    _patch_execution_boundaries(monkeypatch, metrics_by_case={})

    decision = execute(V13Runtime(call), paths=paths, remote_gate=False)
    result = _load(paths.result)

    assert decision == terminal.OPERATIONAL_BUDGET_TERMINAL
    assert calls == [CASE_ORDER[0]]
    assert result["failure_stage"] == "OPERATIONAL_BUDGET_STOP"
    assert result["failed_case_id"] == CASE_ORDER[0]
    assert result["scientific_case_results_preserved"] is True
    diagnostics = result["diagnostics"]
    assert isinstance(diagnostics, dict)
    assert diagnostics["next_case_not_called"] == CASE_ORDER[1]
    assert result["provider_calls"] == 1
    assert result["output_tokens"] == 900_000
    assert result["cost_usd"] == pytest.approx(5.25)
    outcomes = result["case_outcomes"]
    assert isinstance(outcomes, list)
    assert isinstance(outcomes[0], dict)
    custody = outcomes[0]["custody"]
    assert isinstance(custody, dict)
    assert custody["bundle_sha256"]
    assert custody["receipt_sha256"]
    assert custody["raw_output_sha256"]
    metrics = outcomes[0]["v13_metrics"]
    assert isinstance(metrics, dict)
    assert metrics["passed"] is True
    assert not paths.case(CASE_ORDER[1]).attempt.exists()


def test_nonzero_retry_receipt_seals_invalid_without_a_second_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)
    calls: list[str] = []

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        case_paths: CaseExecutionPaths,
    ) -> V13ProviderExecution[V9StagedGeneralizationOutput]:
        calls.append(case_id)
        response_id = "response-v13-retry-invalid"
        acknowledge_attempt(case_paths.attempt, response_id=response_id)
        return _execution(
            _output(case_id),
            response_id,
            cost_usd=0.01,
            provider_retries=1,
        )

    _patch_execution_boundaries(monkeypatch, metrics_by_case={})

    decision = execute(V13Runtime(call), paths=paths, remote_gate=False)
    result = _load(paths.result)

    assert decision == terminal.INVALID_TERMINAL
    assert calls == [CASE_ORDER[0]]
    assert result["failure_stage"] == "EXACTLY_ONCE_ACCOUNTING"
    assert result["provider_calls"] == 1
    assert result["provider_retries"] == 1
    assert result["duplicate_creation_calls"] == 0
    assert not paths.case(CASE_ORDER[1]).attempt.exists()


def test_cross_case_response_id_reuse_seals_second_call_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)
    calls: list[str] = []

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        case_paths: CaseExecutionPaths,
    ) -> V13ProviderExecution[V9StagedGeneralizationOutput]:
        calls.append(case_id)
        response_id = "response-v13-cross-case-reuse"
        acknowledge_attempt(case_paths.attempt, response_id=response_id)
        return _execution(
            _output(case_id),
            response_id,
            cost_usd=0.01,
            provider_retries=0,
        )

    _patch_execution_boundaries(monkeypatch, metrics_by_case={})

    decision = execute(V13Runtime(call), paths=paths, remote_gate=False)
    result = _load(paths.result)

    assert decision == terminal.INVALID_TERMINAL
    assert calls == list(CASE_ORDER[:2])
    assert result["failure_stage"] == "RESPONSE_ID_CUSTODY"
    diagnostics = result["diagnostics"]
    assert isinstance(diagnostics, dict)
    assert diagnostics["original_failure_stage"] == "EXACTLY_ONCE_ACCOUNTING"
    assert diagnostics["reused_response_ids"] == ["response-v13-cross-case-reuse"]
    assert result["attempted_provider_calls"] == 2
    assert result["completed_provider_calls"] == 2
    assert result["admitted_provider_calls"] == 1
    assert result["rejected_provider_calls"] == 1
    per_call = result["per_call"]
    assert isinstance(per_call, list)
    assert isinstance(per_call[1], dict)
    assert per_call[1]["reused_response_ids"] == ["response-v13-cross-case-reuse"]
    assert not paths.case(CASE_ORDER[2]).attempt.exists()
    rejected_receipt = _load(paths.case(CASE_ORDER[1]).receipt)
    assert rejected_receipt["status"] == "REJECTED_UNADMITTED"


def test_first_scientific_failure_is_persisted_and_stops_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)
    calls: list[str] = []
    second = _metrics(
        case_id=CASE_ORDER[1],
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
        response_id = f"response-v13-{len(calls)}"
        acknowledge_attempt(case_paths.attempt, response_id=response_id)
        return _execution(
            _output(case_id),
            response_id,
            cost_usd=0.01,
            provider_retries=0,
        )

    _patch_execution_boundaries(
        monkeypatch,
        metrics_by_case={CASE_ORDER[1]: second},
    )

    decision = execute(V13Runtime(call), paths=paths, remote_gate=False)
    result = _load(paths.result)

    assert decision == terminal.UNRELATED_FAIL_TERMINAL
    assert calls == list(CASE_ORDER[:2])
    assert result["failed_case_id"] == CASE_ORDER[1]
    assert result["first_failure_classification"] == "UNRELATED_REGRESSION"
    assert result["provider_calls"] == 2
    assert result["provider_retries"] == 0
    assert result["duplicate_creation_calls"] == 0
    assert paths.case(CASE_ORDER[1]).evaluation.exists()
    assert not paths.case(CASE_ORDER[2]).attempt.exists()


def test_wrong_case_identity_is_a_custody_failure_not_evaluator_defect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        case_paths: CaseExecutionPaths,
    ) -> V13ProviderExecution[V9StagedGeneralizationOutput]:
        response_id = "response-v13-wrong-case"
        acknowledge_attempt(case_paths.attempt, response_id=response_id)
        wrong = _output(case_id).model_copy(update={"case_id": "wrong-case"})
        return _execution(
            wrong,
            response_id,
            cost_usd=0.01,
            provider_retries=0,
        )

    _patch_execution_boundaries(monkeypatch, metrics_by_case={})

    decision = execute(V13Runtime(call), paths=paths, remote_gate=False)
    result = _load(paths.result)

    assert decision == terminal.INVALID_TERMINAL
    assert result["failure_stage"] == "CASE_IDENTITY_CUSTODY"
    assert result["admitted_provider_calls"] == 0
    assert result["rejected_provider_calls"] == 1
    assert paths.case(CASE_ORDER[0]).bundle.exists()
    receipt = _load(paths.case(CASE_ORDER[0]).receipt)
    assert receipt["status"] == "REJECTED_UNADMITTED"
    assert receipt["failure_stage"] == "CASE_IDENTITY_CUSTODY"
    assert not paths.case(CASE_ORDER[0]).evaluation.exists()


def test_local_custody_failure_keeps_complete_transport_in_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        case_paths: CaseExecutionPaths,
    ) -> V13ProviderExecution[V9StagedGeneralizationOutput]:
        response_id = "response-v13-local-custody"
        acknowledge_attempt(case_paths.attempt, response_id=response_id)
        return _execution(
            _output(case_id),
            response_id,
            cost_usd=0.01,
            provider_retries=0,
        )

    _patch_execution_boundaries(monkeypatch, metrics_by_case={})
    monkeypatch.setattr(
        runner,
        "_persist_custody",
        lambda **_kwargs: (_ for _ in ()).throw(
            runner.V13ExecutionError("injected custody failure")
        ),
    )

    decision = execute(V13Runtime(call), paths=paths, remote_gate=False)
    result = _load(paths.result)

    assert decision == terminal.INVALID_TERMINAL
    assert result["failure_stage"] == "LOCAL_CUSTODY"
    assert result["admitted_provider_calls"] == 0
    assert result["rejected_provider_calls"] == 1
    diagnostics = result["diagnostics"]
    assert isinstance(diagnostics, dict)
    evidence = diagnostics["complete_transport_evidence"]
    assert isinstance(evidence, dict)
    assert evidence["response_ids"] == ["response-v13-local-custody"]
    assert evidence["creation_response"] is not None
    assert evidence["confirmation_response"] is not None
    assert evidence["input_items"] is not None


def test_rejected_custody_failure_keeps_complete_transport_and_stops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)
    calls: list[str] = []
    response_id = "response-v13-rejected-custody"
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
    canonical_payload: dict[str, object] = {
        "case_id": CASE_ORDER[0],
        "completeness": "ABSTAIN",
    }
    usage: dict[str, object] = {
        "input_tokens": 100,
        "cached_input_tokens": 0,
        "output_tokens": 25,
        "reasoning_tokens": 5,
        "total_tokens": 125,
        "latency_seconds": 2.5,
        "cost_usd": 0.01,
    }

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        _case_paths: CaseExecutionPaths,
    ) -> V13ProviderExecution[V9StagedGeneralizationOutput]:
        calls.append(case_id)
        raise V13ProviderExecutionError(
            "SCHEMA_VALIDATION",
            "injected rejected provider output",
            evidence=V13TransportEvidence(
                response_ids=(response_id,),
                creation_response=creation,
                confirmation_response=confirmation,
                input_items=input_items,
                canonical_payload=canonical_payload,
                usage=usage,
                latency_seconds=2.5,
                provider_creation_calls=1,
                completed_provider_calls=1,
                confirmation_retrieval_requests=1,
                input_item_retrieval_requests=1,
            ),
        )

    _patch_execution_boundaries(monkeypatch, metrics_by_case={})
    monkeypatch.setattr(
        runner,
        "persist_rejected_custody",
        lambda **_kwargs: (_ for _ in ()).throw(
            V13RejectedCustodyError("injected rejected-custody write failure")
        ),
    )

    decision = execute(V13Runtime(call), paths=paths, remote_gate=False)
    result = _load(paths.result)

    assert decision == terminal.INVALID_TERMINAL
    assert calls == [CASE_ORDER[0]]
    assert result["failure_stage"] == "REJECTED_CUSTODY_PERSISTENCE"
    assert result["attempted_provider_calls"] == 1
    assert result["completed_provider_calls"] == 1
    assert result["rejected_provider_calls"] == 1
    assert result["cost_usd"] == pytest.approx(0.01)
    diagnostics = result["diagnostics"]
    assert isinstance(diagnostics, dict)
    evidence = diagnostics["complete_transport_evidence"]
    assert isinstance(evidence, dict)
    assert evidence["response_ids"] == [response_id]
    assert evidence["creation_response"] == creation
    assert evidence["confirmation_response"] == confirmation
    assert evidence["input_items"] == list(input_items)
    assert evidence["canonical_payload"] == canonical_payload
    assert evidence["usage"] == usage
    assert evidence["latency_seconds"] == pytest.approx(2.5)
    assert not paths.case(CASE_ORDER[1]).attempt.exists()


def test_case_evaluation_write_failure_seals_consumed_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        case_paths: CaseExecutionPaths,
    ) -> V13ProviderExecution[V9StagedGeneralizationOutput]:
        response_id = "response-v13-evaluation-write"
        acknowledge_attempt(case_paths.attempt, response_id=response_id)
        return _execution(
            _output(case_id),
            response_id,
            cost_usd=0.01,
            provider_retries=0,
        )

    _patch_execution_boundaries(monkeypatch, metrics_by_case={})
    monkeypatch.setattr(
        runner,
        "persist_case_evaluation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("injected evaluation write failure")
        ),
    )

    decision = execute(V13Runtime(call), paths=paths, remote_gate=False)
    result = _load(paths.result)

    assert decision == terminal.INVALID_TERMINAL
    assert result["failure_stage"] == "CASE_EVALUATION_PERSISTENCE"
    assert result["attempted_provider_calls"] == 1
    assert result["completed_provider_calls"] == 1
    assert result["admitted_provider_calls"] == 1
    assert result["executed_case_count"] == 1
    assert result["all_receipts_valid"] is True
    assert result["all_evaluations_persisted"] is False
    diagnostics = result["diagnostics"]
    assert isinstance(diagnostics, dict)
    assert diagnostics["provider_call_and_custody_preserved"] is True
    assert paths.case(CASE_ORDER[0]).bundle.exists()


def test_evaluator_defect_reports_consumed_but_unevaluated_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        case_paths: CaseExecutionPaths,
    ) -> V13ProviderExecution[V9StagedGeneralizationOutput]:
        response_id = "response-v13-evaluator-defect"
        acknowledge_attempt(case_paths.attempt, response_id=response_id)
        return _execution(
            _output(case_id),
            response_id,
            cost_usd=0.01,
            provider_retries=0,
        )

    _patch_execution_boundaries(monkeypatch, metrics_by_case={})
    monkeypatch.setattr(
        runner,
        "evaluate_v13_case",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("injected evaluator defect")
        ),
    )

    decision = execute(V13Runtime(call), paths=paths, remote_gate=False)
    result = _load(paths.result)

    assert decision == terminal.INVALID_TERMINAL
    assert result["failure_stage"] == "EVALUATOR_DEFECT"
    assert result["executed_case_count"] == 1
    assert result["provider_attempted_case_ids"] == [CASE_ORDER[0]]
    assert result["scientifically_evaluated_case_count"] == 0
    assert result["scientifically_evaluated_case_ids"] == []
    assert result["called_but_unevaluated_case_ids"] == [CASE_ORDER[0]]
    assert result["stopped_after_case_id"] == CASE_ORDER[0]
    assert result["case_outcomes"] == []
    assert result["attempted_provider_calls"] == 1
    assert result["admitted_provider_calls"] == 1
    diagnostics = result["diagnostics"]
    assert isinstance(diagnostics, dict)
    assert diagnostics["provider_call_and_custody_preserved"] is True
    custody = diagnostics["custody"]
    assert isinstance(custody, dict)
    assert custody["bundle_sha256"]
    assert custody["receipt_sha256"]
    assert custody["raw_output_sha256"]


def _patch_execution_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    *,
    metrics_by_case: dict[str, V13CaseMetrics],
) -> None:
    monkeypatch.setattr(
        runner,
        "ordered_cases",
        lambda _paths: tuple(_CaseStub(case_id) for case_id in CASE_ORDER),
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
        "evaluate_v13_case",
        lambda case, *_args: metrics_by_case.get(
            case.case_id,
            _metrics(
                case_id=case.case_id,
                passed=True,
                source_status="PASS",
                cg_status="NOT_APPLICABLE",
            ),
        ),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "redacted-test-key")


def _temporary_paths(tmp_path: Path) -> V13Paths:
    preregistration = tmp_path / "preregistration.json"
    preregistration.write_text("{}\n", encoding="utf-8")
    return replace(
        DEFAULT_PATHS,
        preregistration=preregistration,
        result=tmp_path / "result.json",
        report=tmp_path / "report.md",
        next_fresh_preregistration=tmp_path / "fresh-draft.json",
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
    envelope: dict[str, object] = {"id": response_id, "background": False}
    return V13ProviderExecution(
        extraction=output,
        canonical_payload=output.model_dump(mode="json"),
        creation_response=envelope,
        confirmation_response=envelope,
        input_items=(
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "frozen input"}],
            },
        ),
        receipt={
            "status": "VERIFIED_LIVE",
            "identity": {
                "response_id": response_id,
                "model": "gpt-5.6-luna",
            },
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
        },
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
            if case_id == "generalization-explicit-nested-cause"
            else "NOT_APPLICABLE"
        ),
        full_focus_cg_status=(
            "NOT_MEASURED_UNREPRESENTABLE"
            if case_id == "generalization-explicit-nested-cause"
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
