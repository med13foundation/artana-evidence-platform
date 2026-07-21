from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validation.provider_receipt_boundary.background_smoke import (
    BackgroundSmokePreflightError,
    build_preregistration,
    verify_preregistration,
)

ROOT = Path(__file__).parents[2]


def _candidate(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    payload = build_preregistration(ROOT)
    path = tmp_path / "background-smoke.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path, payload


def test_background_smoke_freezes_one_creation_and_polling_contract(
    tmp_path: Path,
) -> None:
    path, payload = _candidate(tmp_path)
    budgets = payload["budgets"]
    frozen_state = payload["frozen_state"]
    rules = payload["rules"]
    assert isinstance(budgets, dict)
    assert isinstance(frozen_state, dict)
    assert isinstance(rules, dict)
    transport = frozen_state["transport"]

    result = verify_preregistration(ROOT, path, require_clean_code=False)

    assert result["status"] == "PREFLIGHT_PASSED"
    assert budgets["provider_creation_calls"] == 1
    assert budgets["model_generation_calls"] == 1
    assert budgets["duplicate_creation_calls"] == 0
    assert budgets["provider_retries"] == 0
    assert budgets["max_cost_usd"] == 0.25
    assert transport == {
        "mode": "OPENAI_RESPONSES_BACKGROUND_POLLING",
        "background": True,
        "acknowledgement_timeout_seconds": 30.0,
        "polling_interval_seconds": 5.0,
        "max_polling_seconds": 900.0,
        "creation_idempotency_claimed": False,
        "automatic_cancellation": False,
    }
    assert rules["scientific_experiment_allowed"] is False
    assert rules["biomedical_source_allowed"] is False


def test_background_smoke_rejects_duplicate_creation_budget(tmp_path: Path) -> None:
    path, payload = _candidate(tmp_path)
    budgets = payload["budgets"]
    assert isinstance(budgets, dict)
    budgets["duplicate_creation_calls"] = 1
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BackgroundSmokePreflightError, match="duplicate_creation"):
        verify_preregistration(ROOT, path, require_clean_code=False)


def test_background_smoke_rejects_scientific_or_retry_capability(
    tmp_path: Path,
) -> None:
    path, payload = _candidate(tmp_path)
    rules = payload["rules"]
    assert isinstance(rules, dict)
    rules["retry_allowed"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BackgroundSmokePreflightError, match="prohibited"):
        verify_preregistration(ROOT, path, require_clean_code=False)


def test_background_smoke_rejects_frozen_state_drift(tmp_path: Path) -> None:
    path, payload = _candidate(tmp_path)
    frozen_state = payload["frozen_state"]
    assert isinstance(frozen_state, dict)
    transport = frozen_state["transport"]
    assert isinstance(transport, dict)
    transport["polling_interval_seconds"] = 1.0
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BackgroundSmokePreflightError, match="frozen state"):
        verify_preregistration(ROOT, path, require_clean_code=False)
