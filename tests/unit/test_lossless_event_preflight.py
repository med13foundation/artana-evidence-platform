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

ROOT = Path(__file__).parents[2]
PREREGISTRATION = (
    ROOT / "docs/validation/preregistrations/"
    "2026-07-21-lossless-event-ir-development-experiment-v2.json"
)


def test_v2_preregistration_remains_immutable_after_boundary_change() -> None:
    with pytest.raises(ExperimentPreflightError, match="frozen state"):
        verify_preregistration(ROOT, PREREGISTRATION)


def test_v3_candidate_recomputes_but_remains_unauthorized(tmp_path: Path) -> None:
    payload = build_preregistration(ROOT)
    candidate = tmp_path / "candidate.json"
    candidate.write_text(json.dumps(payload), encoding="utf-8")

    result = verify_preregistration(
        ROOT,
        candidate,
        require_authorized=False,
    )

    assert result["status"] == "PREFLIGHT_PASSED"
    assert len(result["preregistration_sha256"]) == 64
    assert payload["execution_authorized"] is False
    assert payload["status"] == "FROZEN_UNAUTHORIZED_AWAITING_EXPLICIT_AUTHORIZATION"


def test_v3_preregistration_rejects_selection_drift(tmp_path: Path) -> None:
    payload = build_preregistration(ROOT)
    payload["frozen_state"]["source"]["selected_document_id"] = "PMID-10473104"
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ExperimentPreflightError, match="frozen state"):
        verify_preregistration(ROOT, tampered, require_authorized=False)


def test_v3_preregistration_rejects_recovery_or_promotion_capability(
    tmp_path: Path,
) -> None:
    payload = build_preregistration(ROOT)
    payload["rules"]["retry_allowed"] = True
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ExperimentPreflightError, match="prohibited"):
        verify_preregistration(ROOT, tampered, require_authorized=False)


def test_model_input_freeze_excludes_gold_annotation_components() -> None:
    state = compute_frozen_state(ROOT)
    model_input = state["model_input"]

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
    assert state["source"]["test_access"] == "SEALED_NOT_READ"
