"""V17 execution-policy, custody, and fail-fast runtime regressions."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from scripts.validation.public_gold.staged_event.context_experiment.source_first.attempts import (
    acknowledge_attempt,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    CaseExecutionPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.evaluation import (
    V13CaseMetrics,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.provider_execution import (
    V13ProviderExecution,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.contracts import (
    V16StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17 import (
    runner,
    terminal,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
    EXPERIMENT_ID,
    V17Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.evaluation import (
    V17CaseEvaluation,
    V17ScopeAssessment,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.runner import (
    V17Runtime,
    execute,
)

REPO = Path(__file__).resolve().parents[2]
_V11_UNCERTAINTY_RAW = REPO / (
    "docs/validation/results/"
    "2026-07-23-staged-generalization-v11-exposed-run-v2-"
    "generalization-uncertainty-raw.json"
)


@dataclass(frozen=True, slots=True)
class _CaseStub:
    case_id: str


def test_success_persists_v17_identity_exactly_once_custody_and_separate_lanes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)
    case_id = CASE_ORDER[0]

    def call(
        _api_key: str,
        called_case_id: str,
        _value: str,
        _preregistration_sha256: str,
        case_paths: CaseExecutionPaths,
    ) -> V13ProviderExecution[V16StagedGeneralizationOutput]:
        acknowledge_attempt(case_paths.attempt, response_id="response-v17-success")
        return _execution(
            _output(called_case_id), "response-v17-success", cost_usd=0.25
        )

    _patch_execution_boundaries(
        monkeypatch,
        case_ids=(case_id,),
        evaluations={case_id: _evaluation(case_id=case_id, passed=True)},
    )

    decision = execute(V17Runtime(call), paths=paths, remote_gate=False)
    result = _load(paths.result)
    custody = _load(paths.case(case_id).bundle)
    evaluation = _load(paths.case(case_id).evaluation)

    assert decision == terminal.PASS_TERMINAL
    assert (
        result["schema_version"] == "artana.staged_generalization.v17_exposed_result.v1"
    )
    assert result["experiment_id"] == EXPERIMENT_ID
    assert (
        result["single_scientific_change"]
        == "INLINE_VERSUS_ANAPHORIC_SCOPE_BOUNDARY_V1"
    )
    assert result["shared_or_historical_grader_changed"] is False
    assert result["v16_schema_reused_byte_identical"] is True
    assert result["inline_optional_scope_capability_added"] is False
    assert result["provider_calls"] == 1
    assert result["completed_provider_calls"] == 1
    assert result["admitted_provider_calls"] == 1
    assert result["provider_retries"] == 0
    assert result["duplicate_creation_calls"] == 0
    assert result["transport_qualification_provider_calls_in_v17"] == 0
    assert result["fresh_cases_consumed"] == 0
    assert result["graph_writes"] == 0
    assert result["trusted_promotion"] is False
    assert custody["stage"] == f"GENERALIZATION_V17_EXPOSED:{case_id}"
    assert evaluation["evaluator_implementation"] == "repair_v17.evaluate_v17_case"
    assert evaluation["raw_v16_diagnostic_lane"] == "PRESERVED_UNSCORED"
    assert evaluation["bionlp_cg_projection_lane"] == "RAW_REVIEW_ONLY"


def test_v17_scope_failure_is_persisted_before_fail_fast_without_next_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)
    case_ids = ("generalization-comparison-canary", CASE_ORDER[-1])
    calls: list[str] = []
    persisted: list[bool] = []

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        case_paths: CaseExecutionPaths,
    ) -> V13ProviderExecution[V16StagedGeneralizationOutput]:
        calls.append(case_id)
        acknowledge_attempt(case_paths.attempt, response_id="response-v17-scope-fail")
        return _execution(_output(case_id), "response-v17-scope-fail", cost_usd=0.01)

    _patch_execution_boundaries(
        monkeypatch,
        case_ids=case_ids,
        evaluations={
            case_ids[0]: _evaluation(
                case_id=case_ids[0], passed=False, scope_passed=False
            )
        },
    )
    runtime = V17Runtime(
        call,
        after_case_persist=lambda: persisted.append(
            paths.case(case_ids[0]).evaluation.exists()
        ),
    )

    decision = execute(runtime, paths=paths, remote_gate=False)
    result = _load(paths.result)

    assert decision == terminal.SOURCE_FAIL_TERMINAL
    assert calls == [case_ids[0]]
    assert persisted == [True]
    assert result["first_failure_classification"] == "SOURCE_SEMANTICS"
    assert paths.case(case_ids[0]).evaluation.exists()
    assert not paths.case(case_ids[1]).attempt.exists()


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
    ) -> V13ProviderExecution[V16StagedGeneralizationOutput]:
        calls.append(case_id)
        acknowledge_attempt(case_paths.attempt, response_id="response-v17-retry")
        return _execution(
            _output(case_id),
            "response-v17-retry",
            cost_usd=0.01,
            provider_retries=1,
        )

    _patch_execution_boundaries(monkeypatch, case_ids=case_ids, evaluations={})

    decision = execute(V17Runtime(call), paths=paths, remote_gate=False)
    result = _load(paths.result)

    assert decision == terminal.INVALID_TERMINAL
    assert calls == [case_ids[0]]
    assert result["failure_stage"] == "EXACTLY_ONCE_ACCOUNTING"
    assert result["provider_retries"] == 1
    assert result["admitted_provider_calls"] == 0
    assert result["rejected_provider_calls"] == 1
    assert not paths.case(case_ids[1]).attempt.exists()


def test_cumulative_budget_stop_persists_the_case_and_makes_no_next_call(
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
    ) -> V13ProviderExecution[V16StagedGeneralizationOutput]:
        calls.append(case_id)
        acknowledge_attempt(case_paths.attempt, response_id="response-v17-budget")
        return _execution(_output(case_id), "response-v17-budget", cost_usd=5.0)

    _patch_execution_boundaries(monkeypatch, case_ids=case_ids, evaluations={})

    decision = execute(V17Runtime(call), paths=paths, remote_gate=False)
    result = _load(paths.result)

    assert decision == terminal.OPERATIONAL_BUDGET_TERMINAL
    assert calls == [case_ids[0]]
    assert result["failure_stage"] == "OPERATIONAL_BUDGET_STOP"
    assert result["cost_usd"] == pytest.approx(5.0)
    assert result["remaining_cost_usd"] == pytest.approx(0.0)
    assert result["scientific_case_results_preserved"] is True
    assert paths.case(case_ids[0]).evaluation.exists()
    assert not paths.case(case_ids[1]).attempt.exists()


def _patch_execution_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    *,
    case_ids: tuple[str, ...],
    evaluations: dict[str, V17CaseEvaluation],
) -> None:
    monkeypatch.setattr(
        runner,
        "ordered_cases",
        lambda _paths: tuple(_CaseStub(case_id) for case_id in case_ids),
    )
    monkeypatch.setattr(
        runner, "provider_input", lambda case_id, _paths: f"input:{case_id}"
    )
    monkeypatch.setattr(runner, "verify", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        runner, "verify_v13_frozen_policy", lambda *_args, **_kwargs: object()
    )
    monkeypatch.setattr(runner, "case_policy", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(runner, "policy_sha256", lambda *_args, **_kwargs: "a" * 64)
    monkeypatch.setattr(runner, "load_contract", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        runner,
        "evaluate_v17_case",
        lambda case, *_args, **_kwargs: evaluations.get(
            case.case_id,
            _evaluation(case_id=case.case_id, passed=True),
        ),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-a-secret")


def _temporary_paths(tmp_path: Path) -> V17Paths:
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


def _output(case_id: str) -> V16StagedGeneralizationOutput:
    output = V16StagedGeneralizationOutput.model_validate_json(
        _V11_UNCERTAINTY_RAW.read_text(encoding="utf-8")
    )
    return output.model_copy(update={"case_id": case_id})


def _execution(
    output: V16StagedGeneralizationOutput,
    response_id: str,
    *,
    cost_usd: float,
    provider_retries: int = 0,
) -> V13ProviderExecution[V16StagedGeneralizationOutput]:
    creation: dict[str, object] = {"id": response_id, "status": "completed"}
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
            "identity": {"response_id": response_id, "model": "gpt-5.6-luna"},
            "usage": _usage(cost_usd),
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


def _usage(cost_usd: float) -> dict[str, object]:
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
    *, case_id: str, passed: bool, scope_passed: bool = True
) -> V17CaseEvaluation:
    status = "PASS" if passed else "FAIL"
    metrics = V13CaseMetrics(
        case_id=case_id,
        passed=passed,
        focus_event_passed=passed,
        source_semantic_status=status,
        benchmark_projection_status="NOT_APPLICABLE",
        benchmark_projection_scope="NOT_APPLICABLE",
        full_focus_cg_status="NOT_APPLICABLE",
        mandatory_participants_passed=passed,
        participant_roles_passed=passed,
        semantic_axes_passed=passed,
        exact_evidence_grounding=passed,
        unsupported_extraction_count=0 if passed else 1,
        permitted_context_count=0,
        benchmark_projection=None,
        failure_reasons=() if passed else ("injected scope failure",),
        historical_grader_passed=passed,
        root_selection_status="PASS" if passed else "FAIL",
        completeness="COMPLETE",
        source_dimensions_except_root_passed=passed,
        root_only_failure=False,
    )
    scope = V17ScopeAssessment(
        policy="INLINE_VERSUS_ANAPHORIC_SCOPE_BOUNDARY_V1",
        passed=scope_passed,
        grounding_passed=scope_passed,
        scope_link_observed_count=1 if scope_passed else 0,
        scope_link_accepted_count=1 if scope_passed else 0,
        partitive_observed_count=1 if scope_passed else 0,
        partitive_accepted_count=1 if scope_passed else 0,
        optional_direct_context_observed_count=0,
        optional_direct_context_accepted_count=0,
        inline_redundant_scope_count=0 if scope_passed else 1,
        unreviewed_scope_count=0,
        untypeable_scope_count=0,
        failure_reasons=() if scope_passed else ("injected scope failure",),
    )
    return V17CaseEvaluation(
        metrics=metrics,
        raw_v16_metrics=metrics,
        raw_v14_metrics=metrics,
        scope_assessment=scope,
    )


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value
