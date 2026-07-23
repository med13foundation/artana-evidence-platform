"""V12 two-lane contract and offline replay regressions."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from scripts.validation.provider_receipt_boundary.foreground import (
    ForegroundProviderExecution,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.attempts import (
    acknowledge_attempt,
)
from scripts.validation.public_gold.staged_event.generalization.grading.artifacts import (
    verify_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.grading.config import (
    DEFAULT_PATHS as GRADING_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    case_policy,
)
from scripts.validation.public_gold.staged_event.generalization.panel import (
    GeneralizationCase,
    build_panel,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    CaseExecutionPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12 import (
    runner,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
    V12Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.contracts import (
    load_contract,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.evaluation import (
    V12CaseMetrics,
    evaluate_v12_case,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.offline_replay import (
    OfflineReplayPaths,
    build_offline_replay,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.preflight import (
    verify,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.prompt_audit import (
    EXPECTED_RULE,
    verify_prompt_audit,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.provider import (
    build_request,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.runner import (
    V12Runtime,
    execute,
)

REPO = Path(__file__).resolve().parents[2]
ADJUDICATION = REPO / (
    "docs/validation/adjudications/"
    "2026-07-23-pmid-21965773-drug-sensitivity-two-lane-adjudication-v1.json"
)
CONTRACT = REPO / (
    "docs/validation/adjudications/"
    "2026-07-23-staged-generalization-v12-two-lane-contract-v1.json"
)
V9_RAW = REPO / (
    "docs/validation/results/"
    "2026-07-22-staged-generalization-v9-generalization-drug-sensitivity-raw.json"
)
V9_RESULT = REPO / (
    "docs/validation/results/2026-07-22-staged-generalization-v9.json"
)
V11_RAW = REPO / (
    "docs/validation/results/"
    "2026-07-23-staged-generalization-v11-exposed-run-v2-"
    "generalization-drug-sensitivity-raw.json"
)
V11_RESULT = REPO / (
    "docs/validation/results/"
    "2026-07-23-staged-generalization-v11-exposed-run-v2.json"
)
RULE = REPO / (
    "docs/validation/prompts/"
    "2026-07-23-staged-generalization-v12-focus-event-anchoring.md"
)
RULE_AUDIT = REPO / (
    "docs/validation/adjudications/"
    "2026-07-23-staged-generalization-v12-focus-rule-offline-audit-v1.json"
)


def _case(
    case_id: str = "generalization-drug-sensitivity",
) -> GeneralizationCase:
    return next(item for item in build_panel() if item.case_id == case_id)


def _output(path: Path) -> V9StagedGeneralizationOutput:
    return V9StagedGeneralizationOutput.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _metrics(path: Path) -> V12CaseMetrics:
    case = _case()
    policy = verify_frozen_policy(GRADING_PATHS.grading)
    contract = load_contract(CONTRACT, adjudication_path=ADJUDICATION)
    return evaluate_v12_case(
        case,
        _output(path),
        case_policy(policy, case.case_id),
        contract,
    )


def test_v12_contract_is_bound_to_independent_adjudication() -> None:
    contract = load_contract(CONTRACT, adjudication_path=ADJUDICATION)

    assert contract.source_lane.root_trigger == "sensitivity"
    assert contract.source_lane.acceptable_event_types == (
        "ASSOCIATION",
        "REGULATION",
    )
    assert contract.source_lane.acceptable_direction_values == (
        "NOT_APPLICABLE",
        "OBSERVED",
    )
    assert contract.cg_projection_lane.review_only is True
    assert contract.cg_projection_lane.qualification_credit is False
    assert contract.graph_promotion_allowed is False


def test_focus_rule_is_source_general_and_audited_against_every_case() -> None:
    audit = verify_prompt_audit(
        rule_path=RULE,
        audit_path=RULE_AUDIT,
        adjudication_path=ADJUDICATION,
    )

    assert RULE.read_text(encoding="utf-8") == EXPECTED_RULE
    assert audit["case_count"] == 6
    assert audit["single_scientific_change"] == "FOCUS_EVENT_ANCHORING"
    assert audit["unresolved_safety_findings"] == []


def test_v9_replay_passes_new_source_lane_and_exact_review_only_projection() -> None:
    metrics = _metrics(V9_RAW)

    assert metrics.passed is True
    assert metrics.focus_event_passed is True
    assert metrics.source_semantic_status == "PASS"
    assert metrics.cg_projection_status == "PASS"
    assert metrics.exact_evidence_grounding is True
    assert metrics.unsupported_extraction_count == 0
    assert metrics.qualification_credit is False
    assert metrics.cg_projection is not None
    assert metrics.cg_projection["event"] == {
        "type": "REGULATION",
        "trigger": {
            "exact_text": "sensitivity",
            "start": 354,
            "end": 365,
        },
    }


def test_offline_replay_grants_no_credit_and_preserves_sealed_results() -> None:
    replay = build_offline_replay(
        OfflineReplayPaths(
            contract=CONTRACT,
            adjudication=ADJUDICATION,
            v9_raw=V9_RAW,
            v9_result=V9_RESULT,
            v11_raw=V11_RAW,
            v11_result=V11_RESULT,
        )
    )
    entries = replay["entries"]

    assert replay["diagnostic_only"] is True
    assert replay["historical_replay_credit"] is False
    assert isinstance(entries, list)
    assert all(entry["retroactive_credit"] is False for entry in entries)
    assert all(entry["sealed_result_changed"] is False for entry in entries)
    assert entries[0]["v12_diagnostic"]["passed"] is True
    assert entries[1]["v12_diagnostic"]["passed"] is False


def test_v11_replay_fails_focus_and_occurrence_but_keeps_context_permitted() -> None:
    metrics = _metrics(V11_RAW)

    assert metrics.passed is False
    assert metrics.focus_event_passed is False
    assert metrics.source_semantic_status == "FAIL"
    assert metrics.cg_projection_status == "FAIL"
    assert metrics.mandatory_participants_passed is False
    assert metrics.permitted_context_count == 2
    assert metrics.qualification_credit is False
    assert "highlighted sensitivity event is not the source root" in (
        metrics.failure_reasons
    )


def test_wrong_unique_drug_antecedent_cannot_replace_focus_local_occurrence() -> None:
    output = _output(V9_RAW)
    drug = next(
        participant
        for participant in output.participants
        if participant.entity_type == "SIMPLE_CHEMICAL"
    )
    changed_drug = drug.model_copy(
        update={"exact_text": "5-fluorouracil (5-FU)"}
    )
    changed = output.model_copy(
        update={
            "participants": tuple(
                changed_drug if item == drug else item
                for item in output.participants
            )
        }
    )
    case = _case()
    policy = verify_frozen_policy(GRADING_PATHS.grading)
    contract = load_contract(CONTRACT, adjudication_path=ADJUDICATION)

    metrics = evaluate_v12_case(
        case,
        changed,
        case_policy(policy, case.case_id),
        contract,
    )

    assert metrics.source_semantic_status == "FAIL"
    assert metrics.cg_projection_status == "FAIL"
    assert metrics.mandatory_participants_passed is False


def test_non_target_cases_still_use_unchanged_frozen_grader() -> None:
    case = _case("generalization-comparison-canary")
    output = V9StagedGeneralizationOutput.model_validate_json(
        (
            REPO
            / "docs/validation/results/"
            "2026-07-23-staged-generalization-v11-exposed-run-v2-"
            "generalization-comparison-canary-raw.json"
        ).read_text(encoding="utf-8")
    )
    policy = verify_frozen_policy(GRADING_PATHS.grading)
    contract = load_contract(CONTRACT, adjudication_path=ADJUDICATION)

    metrics = evaluate_v12_case(
        case,
        output,
        case_policy(policy, case.case_id),
        contract,
    )

    assert metrics.passed is True
    assert metrics.historical_grader_passed is True
    assert metrics.cg_projection_status == "NOT_APPLICABLE"


def test_checked_in_preregistration_verifies_and_omits_token_limits() -> None:
    preregistration = verify()
    provider = preregistration["provider"]

    assert isinstance(provider, dict)
    assert provider["application_max_output_tokens"] is None
    assert provider["application_max_total_tokens"] is None
    assert provider["provider_retries"] == 0
    assert provider["fallback"] is False
    assert preregistration["single_scientific_change"] == (
        "FOCUS_EVENT_ANCHORING"
    )


def test_provider_request_has_no_generation_or_cost_ceiling() -> None:
    request = build_request(
        case_id="generalization-comparison-canary",
        provider_input="frozen input",
        preregistration_sha256="a" * 64,
    )

    assert not hasattr(request, "max_output_tokens")
    assert not hasattr(request, "max_total_tokens")
    assert not hasattr(request, "max_cost_usd")
    assert request.metadata["artana_scientific_change"] == (
        "FOCUS_EVENT_ANCHORING"
    )


def test_large_usage_is_persisted_then_stops_before_next_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _temporary_paths(tmp_path)
    canary = V9StagedGeneralizationOutput.model_validate_json(
        (
            REPO
            / "docs/validation/results/"
            "2026-07-23-staged-generalization-v11-exposed-run-v2-"
            "generalization-comparison-canary-raw.json"
        ).read_text(encoding="utf-8")
    )
    calls: list[str] = []

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        case_paths: CaseExecutionPaths,
    ) -> ForegroundProviderExecution[V9StagedGeneralizationOutput]:
        calls.append(case_id)
        response_id = "response-v12-budget"
        acknowledge_attempt(case_paths.attempt, response_id=response_id)
        return _execution(canary, response_id, cost_usd=5.25)

    monkeypatch.setattr(runner, "verify", lambda *_args, **_kwargs: {})
    monkeypatch.setenv("OPENAI_API_KEY", "redacted-test-key")

    decision = execute(V12Runtime(call), paths=paths, remote_gate=False)
    result = json.loads(paths.result.read_text(encoding="utf-8"))

    assert decision == "INVALID_V12_EXECUTION"
    assert calls == [CASE_ORDER[0]]
    assert result["failure_stage"] == "OPERATIONAL_BUDGET_STOP"
    assert result["failed_case_id"] == CASE_ORDER[1]
    assert result["provider_calls"] == 1
    assert result["provider_retries"] == 0
    assert result["duplicate_creation_calls"] == 0
    assert result["output_tokens"] == 900_000
    assert result["cost_usd"] == pytest.approx(5.25)
    assert result["case_outcomes"][0]["v12_metrics"]["passed"] is True
    assert not paths.case(CASE_ORDER[1]).attempt.exists()


def test_sealed_v11_artifacts_remain_byte_identical() -> None:
    expected = {
        DEFAULT_PATHS.v11_preregistration: (
            "6157de1e1cb59042a6f532caa3b5f91e"
            "248ab8d7e09919fd0a2d98ec2e8b3a6a"
        ),
        DEFAULT_PATHS.v11_result: (
            "5b7e3d2e3827d640878de4d156bb5092"
            "29bd0c3f35cf10358f1d886ed15950d1"
        ),
        DEFAULT_PATHS.v11_report: (
            "6907eebeb84cad8c34615b92c2012909"
            "de6af3a845c1e0b51119311d48f20117"
        ),
    }

    for path, digest in expected.items():
        assert sha256(path.read_bytes()).hexdigest() == digest


def _temporary_paths(tmp_path: Path) -> V12Paths:
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


def _execution(
    output: V9StagedGeneralizationOutput,
    response_id: str,
    *,
    cost_usd: float,
) -> ForegroundProviderExecution[V9StagedGeneralizationOutput]:
    envelope: dict[str, object] = {"id": response_id, "background": False}
    return ForegroundProviderExecution(
        extraction=output,
        canonical_payload=output.model_dump(mode="json"),
        creation_response=envelope,
        confirmation_response=envelope,
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
