from __future__ import annotations

import json
from pathlib import Path

import pytest
from openai.types.responses.response_format_text_json_schema_config import (
    ResponseFormatTextJSONSchemaConfig,
)

from scripts.validation.provider_receipt_boundary.smoke import (
    SMOKE_INPUT,
    SmokePreflightError,
    build_smoke_preregistration,
    verify_smoke_preregistration,
)

ROOT = Path(__file__).parents[2]


def _write_candidate(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    payload = build_smoke_preregistration(ROOT)
    path = tmp_path / "receipt-smoke.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path, payload


def test_smoke_preregistration_recomputes_exactly_and_is_non_scientific(
    tmp_path: Path,
) -> None:
    path, payload = _write_candidate(tmp_path)

    verification = verify_smoke_preregistration(ROOT, path)

    assert verification["status"] == "PREFLIGHT_PASSED"
    assert payload["budgets"]["provider_calls"] == 1
    assert payload["budgets"]["provider_retries"] == 0
    assert payload["budgets"]["max_cost_usd"] == 0.25
    assert payload["rules"]["biomedical_source_allowed"] is False
    assert "biomedical" not in SMOKE_INPUT.lower()


def test_openai_response_schema_serialization_uses_wire_aliases_and_unset_fields() -> (
    None
):
    schema = {"type": "object", "additionalProperties": False}
    response_format = ResponseFormatTextJSONSchemaConfig(
        name="receipt_smoke",
        schema=schema,
        type="json_schema",
        strict=True,
    )

    api_shape = response_format.to_dict(
        mode="json",
        use_api_names=True,
        exclude_unset=True,
        exclude_none=False,
    )

    assert api_shape == {
        "name": "receipt_smoke",
        "schema": schema,
        "type": "json_schema",
        "strict": True,
    }
    assert "schema_" not in api_shape
    assert "description" not in api_shape


def test_smoke_preregistration_rejects_request_or_code_drift(tmp_path: Path) -> None:
    path, payload = _write_candidate(tmp_path)
    payload["frozen_state"]["input"]["sha256"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SmokePreflightError, match="frozen state"):
        verify_smoke_preregistration(ROOT, path)


@pytest.mark.parametrize(
    ("section", "key", "value", "message"),
    [
        ("budgets", "provider_calls", 2, "exactly one"),
        ("budgets", "max_cost_usd", 0.26, "cost ceiling"),
        ("rules", "retry_allowed", True, "prohibited"),
        ("rules", "scientific_experiment_allowed", True, "prohibited"),
    ],
)
def test_smoke_preregistration_rejects_unsafe_capabilities(
    tmp_path: Path,
    section: str,
    key: str,
    value: object,
    message: str,
) -> None:
    path, payload = _write_candidate(tmp_path)
    payload[section][key] = value
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SmokePreflightError, match=message):
        verify_smoke_preregistration(ROOT, path)
