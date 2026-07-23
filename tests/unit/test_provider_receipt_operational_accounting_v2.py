from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from scripts.build_fresh_cg_operational_accounting_v2 import build_artifact
from scripts.validation.provider_receipt_boundary.operational_accounting_v2 import (
    ZERO_USAGE,
    OperationalAccountingError,
    OperationalAccountingV2,
    UsageTotals,
    usage_from_rejection_diagnostics,
    validate_reported_output_ceiling,
)

REPO = Path(__file__).resolve().parents[2]
SEALED_RESULT = REPO / (
    "docs/validation/results/2026-07-22-fresh-cg-occurrence-v2-v1.json"
)
SEALED_ARTIFACT_HASHES = {
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


def test_sealed_fresh_cg_artifacts_remain_byte_identical() -> None:
    for relative_path, expected_hash in SEALED_ARTIFACT_HASHES.items():
        assert sha256((REPO / relative_path).read_bytes()).hexdigest() == expected_hash


def test_sealed_rejection_counts_real_spend_without_scientific_admission() -> None:
    result: object = json.loads(SEALED_RESULT.read_text(encoding="utf-8"))
    assert isinstance(result, dict)
    diagnostics = result["diagnostics"]
    assert isinstance(diagnostics, dict)
    rejected = usage_from_rejection_diagnostics(diagnostics)
    accounting = OperationalAccountingV2(
        provider_creation_calls=1,
        admitted_provider_calls=0,
        admitted_scientific_usage=ZERO_USAGE,
        rejected_provider_usage=(rejected,),
        global_max_cost_usd=1.20,
    )

    value = accounting.as_json()
    assert value["scientific_admitted_accounting"] == ZERO_USAGE.as_json()
    assert value["rejected_unadmitted_accounting"] == rejected.as_json()
    assert value["operational_observed_accounting"] == rejected.as_json()
    assert value["rejected_provider_calls"] == 1
    budget = value["global_budget_accounting"]
    assert isinstance(budget, dict)
    assert budget["consumed_cost_usd"] == pytest.approx(0.246147)
    assert budget["remaining_cost_usd"] == pytest.approx(0.953853)
    assert budget["includes_rejected_provider_spend"] is True


def test_rejected_spend_participates_in_prospective_global_budget() -> None:
    rejected = UsageTotals(100, 0, 100, 20, 200, 1.0, 0.90)
    accounting = OperationalAccountingV2(
        provider_creation_calls=1,
        admitted_provider_calls=0,
        admitted_scientific_usage=ZERO_USAGE,
        rejected_provider_usage=(rejected,),
        global_max_cost_usd=1.0,
    )

    assert accounting.prospective_call_allowed(maximum_call_cost_usd=0.10)
    assert not accounting.prospective_call_allowed(maximum_call_cost_usd=0.11)


def test_provider_reported_ceiling_must_match_frozen_request() -> None:
    validate_reported_output_ceiling(
        {"max_output_tokens": 20_000},
        expected_max_output_tokens=20_000,
    )

    with pytest.raises(OperationalAccountingError, match="differs"):
        validate_reported_output_ceiling(
            {"max_output_tokens": 40_000},
            expected_max_output_tokens=20_000,
        )


def test_usage_rejects_reasoning_double_counting() -> None:
    with pytest.raises(OperationalAccountingError, match="token totals"):
        UsageTotals(
            input_tokens=10,
            cached_input_tokens=0,
            output_tokens=20,
            reasoning_tokens=5,
            total_tokens=35,
            latency_seconds=1.0,
            cost_usd=0.01,
        )


def test_fresh_cg_correction_is_derived_without_rewriting_science() -> None:
    value = build_artifact()
    admitted = value["scientific_admitted_accounting"]
    rejected = value["rejected_unadmitted_accounting"]
    operational = value["operational_observed_accounting"]

    assert admitted == ZERO_USAGE.as_json()
    assert isinstance(rejected, dict)
    assert rejected["cost_usd"] == pytest.approx(0.246147)
    assert operational == rejected
    assert value["scientific_admission"] is False
    assert value["scientific_credit"] is False
    assert value["provider_execution_authorized"] is False
    assert value["historical_artifacts_rewritten"] is False
