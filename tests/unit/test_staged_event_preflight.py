from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validation.public_gold.lossless_event_scoring import (
    ExactCount,
    LosslessEventScore,
)
from scripts.validation.public_gold.staged_event.live_execution import (
    BudgetLedger,
    StagedComparisonError,
    _scientific_decision,
)
from scripts.validation.public_gold.staged_event.preflight import (
    StagedExperimentPreflightError,
    build_preregistration,
    verify_preregistration,
)
from scripts.validation.public_gold.staged_event.prompting import build_provider_format
from scripts.validation.public_gold.staged_event.registry import ALL_STAGES

ROOT = Path(__file__).parents[2]


def test_staged_candidate_is_reproducible_but_unauthorized(tmp_path: Path) -> None:
    payload = build_preregistration(ROOT)
    candidate = tmp_path / "candidate.json"
    candidate.write_text(json.dumps(payload), encoding="utf-8")

    verified = verify_preregistration(
        ROOT,
        candidate,
        require_authorized=False,
    )
    source = _required_dict(_required_dict(payload, "frozen_state"), "source")

    assert verified["status"] == "PREFLIGHT_PASSED"
    assert payload["execution_authorized"] is False
    assert source["selected_document_id"] == "PMID-16428936"
    assert source["test_access"] == "SEALED_NOT_READ"


@pytest.mark.parametrize("section", ["budgets", "acceptance", "rules", "baseline"])
def test_staged_preflight_rejects_policy_drift(tmp_path: Path, section: str) -> None:
    payload = build_preregistration(ROOT)
    policy = _required_dict(payload, section)
    policy[next(iter(policy))] = "tampered"
    candidate = tmp_path / "candidate.json"
    candidate.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        StagedExperimentPreflightError,
        match=f"policy changed: {section}",
    ):
        verify_preregistration(ROOT, candidate, require_authorized=False)


def test_every_stage_format_is_strict_and_categorically_described() -> None:
    for stage in ALL_STAGES:
        provider_format = build_provider_format(
            stage.output_model,
            description=stage.description,
        )
        assert provider_format["strict"] is True
        assert provider_format["description"] == stage.description


def test_budget_ledger_fails_closed_without_fabricating_accounting() -> None:
    ledger = BudgetLedger(
        max_calls=1,
        max_tokens=100,
        max_cost_usd=1.0,
        max_latency_seconds=10.0,
    )
    receipt = {
        "usage": {
            "total_tokens": 101,
            "cost_usd": 0.5,
            "latency_seconds": 1.0,
        }
    }

    with pytest.raises(StagedComparisonError, match="token budget"):
        ledger.record("discovery", receipt)

    assert ledger.total_tokens == 101
    assert ledger.total_cost_usd == 0.5


def test_advance_gate_is_fully_deterministic() -> None:
    passing = _score(
        complete=10,
        triggers=24,
        arguments=15,
        nested=5,
        unsupported=15,
    )
    failing = _score(
        complete=9,
        triggers=30,
        arguments=20,
        nested=8,
        unsupported=0,
    )

    assert (
        _scientific_decision(passing, completion_unsupported_increase=0)
        == "ADVANCE_STAGED"
    )
    assert (
        _scientific_decision(failing, completion_unsupported_increase=0)
        == "STAGED_NO_MEANINGFUL_IMPROVEMENT"
    )
    assert (
        _scientific_decision(passing, completion_unsupported_increase=1)
        == "STAGED_NO_MEANINGFUL_IMPROVEMENT"
    )


def _score(
    *,
    complete: int,
    triggers: int,
    arguments: int,
    nested: int,
    unsupported: int,
) -> LosslessEventScore:
    return LosslessEventScore(
        complete_events=ExactCount(gold=30, predicted=complete, matched=complete),
        triggers=ExactCount(gold=30, predicted=triggers, matched=triggers),
        typed_arguments=ExactCount(gold=37, predicted=arguments, matched=arguments),
        nested_arguments=ExactCount(gold=12, predicted=nested, matched=nested),
        modifiers=ExactCount(gold=2, predicted=0, matched=0),
        unsupported_or_invented_events=unsupported,
        unauthorized_semantic_mappings=0,
        invalid_offsets=0,
        unresolved_references=0,
        cycles=0,
        mismatches=(),
    )


def _required_dict(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload[key]
    assert isinstance(value, dict)
    return value
