"""Forward-only operational-policy regressions for Fresh-CG V2."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from pydantic import BaseModel

from scripts.validation.provider_receipt_boundary.background import (
    BackgroundProviderExecution,
    TelemetryProviderRequestV2,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.evaluation import (
    DirectCGMetrics,
    FreshCaseMetrics,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.provider_contract import (
    FreshCGProviderOutput,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.reference_contracts import (
    FreshCGTwoLaneReference,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2 import (
    provider,
    runner,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.accounting import (
    OperationalLedger,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.config import (
    DEFAULT_PATHS,
    CaseArtifactPaths,
    ExperimentPaths,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.selection import (
    load_v2_selection,
)

REPO = Path(__file__).resolve().parents[2]
V1_HASHES = {
    "docs/validation/preregistrations/2026-07-22-fresh-cg-occurrence-v2-v1.json": (
        "2b26d580422efedcb44b7de8d8b7e973f2dae04bff020cdce85f3b2b8d4c1b98"
    ),
    "docs/validation/receipts/2026-07-22-fresh-cg-occurrence-v2-v1-fresh-cg-pmid-21963494-e3-attempt.json": (
        "52a66f88efbda9982f7d90ff8b83b3eefcfed838e2ea622435ef867ada8538db"
    ),
    "docs/validation/results/2026-07-22-fresh-cg-occurrence-v2-v1.json": (
        "2a006ea527ef2f22670dd1ec61d9a39e099cac415047852a3f44cd4b8b67544a"
    ),
    "docs/validation/reports/2026-07-22-fresh-cg-occurrence-v2-v1-final.md": (
        "2b350fac9cd0cdc9a1207dc85b23cb9fd833b9b4d31af6ba4d3ac71d601c8a6a"
    ),
}


def test_v2_request_omits_output_ceiling(
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
        paths=CaseArtifactPaths(
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


def test_large_usage_is_scientifically_record_only() -> None:
    execution = _execution("case-1", "response-1", cost_usd=5.25)
    ledger = OperationalLedger().record_execution(
        case_id="case-1",
        execution=cast("BackgroundProviderExecution[BaseModel]", execution),
    )

    value = ledger.as_json(global_max_cost_usd=5.0)
    assert value["output_tokens"] == 900_000
    assert value["cost_usd"] == pytest.approx(5.25)
    assert value["budget_exhausted"] is True
    assert value["token_and_cost_affect_scientific_scoring"] is False


def test_budget_stop_prevents_the_next_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    selection = load_v2_selection(DEFAULT_PATHS.selection)
    calls: list[str] = []

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        _case_paths: CaseArtifactPaths,
    ) -> BackgroundProviderExecution[FreshCGProviderOutput]:
        calls.append(case_id)
        return _execution(case_id, f"response-{case_id}", cost_usd=5.01)

    class _ReferenceLoader:
        @staticmethod
        def model_validate_json(_value: str) -> object:
            return SimpleNamespace(
                cases=tuple(
                    SimpleNamespace(case_id=case.case_id) for case in selection.cases
                )
            )

    monkeypatch.setattr(runner, "load_v2_selection", lambda _path: selection)
    monkeypatch.setattr(runner, "verify", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(runner, "FreshCGTwoLaneReference", _ReferenceLoader)
    monkeypatch.setattr(
        runner,
        "evaluate_case",
        lambda case, _reference, _output: _metrics(case.case_id, passed=True),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "redacted-test-key")

    decision = runner.execute(runner.FreshCGV2Runtime(call), paths=paths)
    result: object = json.loads(paths.result.read_text(encoding="utf-8"))

    assert isinstance(result, dict)
    assert decision == "OPERATIONAL_BUDGET_STOP"
    assert calls == [selection.cases[0].case_id]
    assert result["provider_calls"] == 1
    assert result["provider_retries"] == 0
    assert result["next_case_not_called"] == selection.cases[1].case_id
    assert result["scientific_case_results_preserved"] is True


def test_v1_artifacts_remain_byte_identical() -> None:
    for relative_path, expected in V1_HASHES.items():
        assert sha256((REPO / relative_path).read_bytes()).hexdigest() == expected


def test_seven_untouched_reference_cases_remain_identical() -> None:
    v1 = FreshCGTwoLaneReference.model_validate_json(
        (
            REPO
            / "docs/validation/references/2026-07-22-fresh-cg-two-lane-reference-v1.json"
        ).read_text(encoding="utf-8")
    )
    v2 = FreshCGTwoLaneReference.model_validate_json(
        DEFAULT_PATHS.reference.read_text(encoding="utf-8")
    )
    v1_cases = {case.case_id: case for case in v1.cases}

    assert len(v2.cases) == 8
    assert all(case == v1_cases[case.case_id] for case in v2.cases[:-1])
    assert v2.cases[-1].case_id == "fresh-cg-pmid-8895545-e6"


def _paths(tmp_path: Path) -> ExperimentPaths:
    preregistration = tmp_path / "preregistration.json"
    preregistration.write_text("{}\n", encoding="utf-8")
    reference = tmp_path / "reference.json"
    reference.write_text("{}\n", encoding="utf-8")
    return ExperimentPaths(
        selection=DEFAULT_PATHS.selection,
        review_packet=DEFAULT_PATHS.review_packet,
        replacement_review_packet=DEFAULT_PATHS.replacement_review_packet,
        review_prompt=DEFAULT_PATHS.review_prompt,
        review_schema=DEFAULT_PATHS.review_schema,
        replacement_review_schema=DEFAULT_PATHS.replacement_review_schema,
        reviewer_a=DEFAULT_PATHS.reviewer_a,
        reviewer_b=DEFAULT_PATHS.reviewer_b,
        replacement_reviewer_a=DEFAULT_PATHS.replacement_reviewer_a,
        replacement_reviewer_b=DEFAULT_PATHS.replacement_reviewer_b,
        tiebreak_request=DEFAULT_PATHS.tiebreak_request,
        tiebreaker=DEFAULT_PATHS.tiebreaker,
        replacement_tiebreaker=DEFAULT_PATHS.replacement_tiebreaker,
        reference=reference,
        scientific_prompt=DEFAULT_PATHS.scientific_prompt,
        binding_prompt=DEFAULT_PATHS.binding_prompt,
        preregistration=preregistration,
        result=tmp_path / "result.json",
        report=tmp_path / "report.md",
        receipts=tmp_path / "receipts",
        raw_outputs=tmp_path / "raw",
        evaluations=tmp_path / "evaluations",
    )


def _execution(
    case_id: str,
    response_id: str,
    *,
    cost_usd: float,
) -> BackgroundProviderExecution[FreshCGProviderOutput]:
    output = FreshCGProviderOutput.model_construct(
        scientific_output=None,
        occurrence_bindings=None,
    )
    canonical = output.model_dump(mode="json")
    envelope: dict[str, object] = {"id": response_id}
    return BackgroundProviderExecution(
        extraction=output,
        canonical_payload=canonical,
        acknowledgement_response=envelope,
        terminal_response=envelope,
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
            "provider_retries": 0,
            "duplicate_creation_calls": 0,
            "budgets": {
                "policy": "RECORD_ONLY_NOT_PER_CALL_VALIDATION",
                "requested_max_output_tokens": None,
                "requested_max_total_tokens": None,
                "requested_max_latency_seconds": None,
                "requested_max_cost_usd": None,
                "observed_output_tokens": 900_000,
                "observed_total_tokens": 900_100,
                "observed_latency_seconds": 1.0,
                "observed_cost_usd": cost_usd,
                "output_tokens": "RECORD_ONLY",
                "total_tokens": "RECORD_ONLY",
                "latency": "RECORD_ONLY",
                "cost": "RECORD_ONLY",
            },
        },
    )


def _metrics(case_id: str, *, passed: bool) -> FreshCaseMetrics:
    return FreshCaseMetrics(
        case_id=case_id,
        passed=passed,
        reference_complete=True,
        occurrence_binding_valid=True,
        direct_cg=DirectCGMetrics(
            required_event_type_and_occurrence=passed,
            required_participant_type_and_occurrence="1/1",
            required_argument_target_attachments="1/1",
            source_roles_preserved_in_reference=("Theme",),
            source_role_fidelity="NOT_EXPRESSED_BY_V9_ARTANA_SCHEMA",
            unprojected_addition_count=0,
            passed=passed,
        ),
        artana_fields=(),
        artana_scored_field_count=0,
        artana_passed_field_count=0,
        artana_failed_field_count=int(not passed),
        artana_review_only_field_count=0,
        required_core_complete=passed,
        exact_nested_event_structure=True,
        unsupported_claim_count=0,
        contradiction_count=0,
        failure_reasons=(() if passed else ("frozen scientific mismatch",)),
    )
