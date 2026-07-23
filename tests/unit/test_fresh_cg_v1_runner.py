"""Exactly-once and fail-fast tests for the fresh-CG runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validation.provider_receipt_boundary.background import (
    BackgroundProviderExecution,
)
from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.attempts import (
    acknowledge_attempt,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1 import (
    runner,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.config import (
    DEFAULT_PATHS,
    CaseArtifactPaths,
    ExperimentPaths,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.evaluation import (
    DirectCGMetrics,
    FreshCaseMetrics,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.provider_contract import (
    FreshCGProviderOutput,
)
from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.bindings import (
    OccurrenceBindingError,
)


def _paths(tmp_path: Path) -> ExperimentPaths:
    preregistration = tmp_path / "preregistration.json"
    preregistration.write_text("{}\n", encoding="utf-8")
    return ExperimentPaths(
        selection=DEFAULT_PATHS.selection,
        review_packet=DEFAULT_PATHS.review_packet,
        review_prompt=DEFAULT_PATHS.review_prompt,
        review_schema=DEFAULT_PATHS.review_schema,
        reviewer_a=DEFAULT_PATHS.reviewer_a,
        reviewer_b=DEFAULT_PATHS.reviewer_b,
        tiebreak_request=DEFAULT_PATHS.tiebreak_request,
        tiebreaker=DEFAULT_PATHS.tiebreaker,
        reference=DEFAULT_PATHS.reference,
        scientific_prompt=DEFAULT_PATHS.scientific_prompt,
        binding_prompt=DEFAULT_PATHS.binding_prompt,
        preregistration=preregistration,
        result=tmp_path / "result.json",
        report=tmp_path / "report.md",
        receipts=tmp_path / "receipts",
        raw_outputs=tmp_path / "raw",
    )


def _output(case_id: str) -> FreshCGProviderOutput:
    evidence = "Drug activates GENE."
    return FreshCGProviderOutput.model_validate_json(
        json.dumps(
            {
            "scientific_output": {
                "case_id": case_id,
                "inventory": [
                    {
                        "event_id": "event-1",
                        "event_type": "POSITIVE_REGULATION",
                        "trigger_text": "activates",
                        "exact_evidence": evidence,
                        "explanation": "The event is explicit.",
                    }
                ],
                "participants": [
                    {
                        "participant_id": "participant-1",
                        "entity_type": "GENE_OR_PROTEIN",
                        "exact_text": "GENE",
                        "exact_evidence": evidence,
                        "explanation": "The participant is explicit.",
                    }
                ],
                "links": [
                    {
                        "event_id": "event-1",
                        "arguments": [
                            {
                                "role": "AFFECTED_ENTITY",
                                "target_kind": "PARTICIPANT",
                                "target_id": "participant-1",
                                "explanation": "The event applies to GENE.",
                            }
                        ],
                    }
                ],
                "semantic_axes": [
                    {
                        "event_id": "event-1",
                        "direction": "INCREASED",
                        "comparison": "NOT_APPLICABLE",
                        "polarity": "AFFIRMED",
                        "uncertainty": "ASSERTED",
                        "statistical_observations": [
                            {"observation_type": "NONE", "exact_text": None}
                        ],
                        "author_interpretation": "NOT_CLAIMED",
                        "evidence_items": ["activates"],
                        "explanation": "The event is asserted.",
                    }
                ],
                "root_event_id": "event-1",
                "completeness": "COMPLETE",
                "structure_explanation": "One direct event.",
            },
            "occurrence_bindings": {
                "case_id": case_id,
                "event_mentions": [
                    {
                        "node_id": "event-1",
                        "identity": {
                            "evidence_span": {"start": 0, "end": 20},
                            "mention_span": {"start": 5, "end": 14},
                        },
                    }
                ],
                "participant_mentions": [
                    {
                        "node_id": "participant-1",
                        "identity": {
                            "evidence_span": {"start": 0, "end": 20},
                            "mention_span": {"start": 15, "end": 19},
                        },
                    }
                ],
                "semantic_evidence": [
                    {
                        "event_id": "event-1",
                        "evidence_item_spans": [{"start": 5, "end": 14}],
                        "statistical_observation_spans": [None],
                    }
                ],
            },
            }
        )
    )


def _execution(case_id: str, response_id: str) -> BackgroundProviderExecution[FreshCGProviderOutput]:
    output = _output(case_id)
    envelope: dict[str, object] = {"id": response_id}
    return BackgroundProviderExecution(
        extraction=output,
        canonical_payload=output.model_dump(mode="json"),
        acknowledgement_response=envelope,
        terminal_response=envelope,
        confirmation_response=envelope,
        receipt={
            "status": "VERIFIED_LIVE",
            "identity": {"response_id": response_id, "model": "gpt-5.6-luna"},
            "usage": {
                "input_tokens": 100,
                "output_tokens": 200,
                "total_tokens": 300,
                "latency_seconds": 1.0,
                "cost_usd": 0.01,
            },
            "budgets": {
                "requested_max_cost_usd": 0.15,
                "observed_cost_usd": 0.01,
                "cost": "PASS",
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


def test_runner_stops_before_second_case_on_scientific_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    calls: list[str] = []

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        _case_paths: CaseArtifactPaths,
    ) -> BackgroundProviderExecution[FreshCGProviderOutput]:
        calls.append(case_id)
        return _execution(case_id, f"response-{case_id}")

    monkeypatch.setattr(runner, "verify", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        runner,
        "evaluate_case",
        lambda case, _reference, _output: _metrics(case.case_id, passed=False),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    decision = runner.execute(runner.FreshCGRuntime(call), paths=paths)
    result = json.loads(paths.result.read_text(encoding="utf-8"))

    assert decision == "FRESH_EVIDENCE_FAIL_FAST"
    assert calls == ["fresh-cg-pmid-21963494-e3"]
    assert result["provider_calls"] == 1
    assert result["terminal_stage"] == "SCIENTIFIC_ACCEPTANCE"
    assert result["scientific_readiness"] == "FRESH_EVIDENCE_FAIL_FAST"
    assert result["evaluator_governance_readiness"] == "PASS"
    assert result["production_readiness"].startswith("NOT_READY")
    assert paths.report.exists()
    assert not paths.case("fresh-cg-pmid-2681013-e5").attempt.exists()

    with pytest.raises(runner.FreshCGExecutionError, match="already started"):
        runner.execute(runner.FreshCGRuntime(call), paths=paths)


def test_runner_marks_binding_failure_invalid_and_unscored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        _case_paths: CaseArtifactPaths,
    ) -> BackgroundProviderExecution[FreshCGProviderOutput]:
        return _execution(case_id, f"response-{case_id}")

    def reject_binding(*_args: object) -> FreshCaseMetrics:
        raise OccurrenceBindingError("absolute mention occurrence differs")

    monkeypatch.setattr(runner, "verify", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(runner, "evaluate_case", reject_binding)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    decision = runner.execute(runner.FreshCGRuntime(call), paths=paths)
    result = json.loads(paths.result.read_text(encoding="utf-8"))

    assert decision == "INVALID_EXPERIMENT_EXECUTION"
    assert result["failure_stage"] == "OCCURRENCE_BINDING"
    assert result["scientific_metrics_calculated"] is False
    assert result["provider_calls"] == 1
    assert result["evaluator_governance_readiness"] == "FAIL_CLOSED"


def test_runner_stops_after_one_acknowledged_invalid_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    calls: list[str] = []

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        case_paths: CaseArtifactPaths,
    ) -> BackgroundProviderExecution[FreshCGProviderOutput]:
        calls.append(case_id)
        acknowledge_attempt(case_paths.attempt, response_id="invalid-receipt-response")
        raise ProviderExecutionError(
            "RECEIPT_MISMATCH",
            "provider receipt differs from the frozen request",
        )

    monkeypatch.setattr(runner, "verify", lambda *_args, **_kwargs: {})
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    decision = runner.execute(runner.FreshCGRuntime(call), paths=paths)
    result = json.loads(paths.result.read_text(encoding="utf-8"))

    assert decision == "INVALID_EXPERIMENT_EXECUTION"
    assert calls == ["fresh-cg-pmid-21963494-e3"]
    assert result["failure_stage"] == "RECEIPT_MISMATCH"
    assert result["provider_calls"] == 1
    assert result["response_ids"] == ["invalid-receipt-response"]
    assert not paths.case("fresh-cg-pmid-2681013-e5").attempt.exists()


def test_runner_allows_exactly_eight_passes_without_production_qualification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    calls: list[str] = []

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        _case_paths: CaseArtifactPaths,
    ) -> BackgroundProviderExecution[FreshCGProviderOutput]:
        calls.append(case_id)
        return _execution(case_id, f"response-{len(calls)}")

    monkeypatch.setattr(runner, "verify", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        runner,
        "evaluate_case",
        lambda case, _reference, _output: _metrics(case.case_id, passed=True),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    decision = runner.execute(runner.FreshCGRuntime(call), paths=paths)
    result = json.loads(paths.result.read_text(encoding="utf-8"))

    assert decision == "FRESH_EVIDENCE_PASS"
    assert len(calls) == result["provider_calls"] == 8
    assert result["terminal_stage"] == "COMPLETED_CASE_ORDER"
    assert result["cost_usd"] == pytest.approx(0.08)
    assert result["qualification_credit"] is False
    assert result["trusted_graph_ready"] is False
    assert result["production_readiness"] == (
        "NOT_READY_INDEPENDENT_REPLICATION_REQUIRED"
    )
