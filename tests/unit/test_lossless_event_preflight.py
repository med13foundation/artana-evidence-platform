from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validation.public_gold.lossless_event_preflight import (
    ExperimentPreflightError,
    build_preregistration,
    compute_frozen_state,
    verify_preregistration,
)
from scripts.validation.public_gold.lossless_event_provider_format import (
    PROVIDER_RESPONSE_FORMAT_DESCRIPTION,
    build_scientific_event_provider_format,
)

ROOT = Path(__file__).parents[2]
V2_PREREGISTRATION = (
    ROOT / "docs/validation/preregistrations/"
    "2026-07-21-lossless-event-ir-development-experiment-v2.json"
)
V3_PREREGISTRATION = (
    ROOT / "docs/validation/preregistrations/"
    "2026-07-21-lossless-event-ir-development-experiment-v3.json"
)


def test_v2_preregistration_remains_immutable_after_boundary_change() -> None:
    with pytest.raises(ExperimentPreflightError, match="frozen state"):
        verify_preregistration(ROOT, V2_PREREGISTRATION)


def test_v3_preregistration_remains_immutable_after_background_change() -> None:
    with pytest.raises(ExperimentPreflightError, match="frozen state"):
        verify_preregistration(ROOT, V3_PREREGISTRATION)


def test_v4_candidate_recomputes_but_remains_unauthorized(tmp_path: Path) -> None:
    payload = build_preregistration(ROOT)
    candidate = tmp_path / "candidate.json"
    candidate.write_text(json.dumps(payload), encoding="utf-8")

    result = verify_preregistration(
        ROOT,
        candidate,
        require_authorized=False,
    )

    assert result["status"] == "PREFLIGHT_PASSED"
    preregistration_sha256 = result["preregistration_sha256"]
    assert isinstance(preregistration_sha256, str)
    assert len(preregistration_sha256) == 64
    assert payload["execution_authorized"] is False
    assert payload["status"] == "FROZEN_UNAUTHORIZED_AWAITING_EXPLICIT_AUTHORIZATION"


def test_v4_provider_format_has_one_explicit_stable_description() -> None:
    first = build_scientific_event_provider_format()
    second = build_scientific_event_provider_format()

    assert first == second
    assert first is not second
    assert first["description"] == PROVIDER_RESPONSE_FORMAT_DESCRIPTION
    assert first["description"]


def test_v4_preregistration_rejects_selection_drift(tmp_path: Path) -> None:
    payload = build_preregistration(ROOT)
    frozen_state = _required_dict(payload, "frozen_state")
    source = _required_dict(frozen_state, "source")
    source["selected_document_id"] = "PMID-10473104"
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ExperimentPreflightError, match="frozen state"):
        verify_preregistration(ROOT, tampered, require_authorized=False)


def test_v4_preregistration_rejects_recovery_or_promotion_capability(
    tmp_path: Path,
) -> None:
    payload = build_preregistration(ROOT)
    rules = _required_dict(payload, "rules")
    rules["retry_allowed"] = True
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ExperimentPreflightError, match="prohibited"):
        verify_preregistration(ROOT, tampered, require_authorized=False)


def test_model_input_freeze_excludes_gold_annotation_components() -> None:
    state = compute_frozen_state(ROOT)
    model_input = _required_dict(state, "model_input")
    source = _required_dict(state, "source")

    assert model_input["components"] == [
        "frozen_generic_prompt",
        "document_id",
        "source_sha256",
        "source_text",
    ]
    assert model_input["gold_annotations_included"] is False
    assert model_input["gold_counts_included"] is False
    assert model_input["gold_event_ids_included"] is False
    assert model_input["gold_arguments_included"] is False
    assert source["test_access"] == "SEALED_NOT_READ"
    assert state["transport"] == {
        "mode": "OPENAI_RESPONSES_BACKGROUND_POLLING",
        "background": True,
        "acknowledgement_timeout_seconds": 30.0,
        "polling_interval_seconds": 5.0,
        "max_polling_seconds": 900.0,
        "provider_creation_calls": 1,
        "duplicate_creation_calls": 0,
        "provider_retries": 0,
        "creation_idempotency_claimed": False,
    }


def _required_dict(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload[key]
    assert isinstance(value, dict)
    return value
