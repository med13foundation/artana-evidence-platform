"""Integrity checks for the frozen TG-04 known-expert input artifact."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_EXPECTED_ARTIFACT_SHA256: Final = (
    "865a4eadab94021d57e7446b7f8ce96125aa29b7b3d6df6ed92f267f6a36f775"
)
_EXPECTED_REPORT_SHA256: Final = (
    "adc7d5fa2aac69464f72c8e7f62327d8696838373f67b7682a9200af037031dc"
)
_EXPECTED_RUN_ID: Final = "tg04-known-expert-unit-luna-01"
_EXPECTED_MODEL_ID: Final = "openai:gpt-5.6-luna"
_EXPECTED_UNIT_ID: Final = (
    "source-unit-e14e44064324af2f721a3d02d2caf44c00218a0ab6c4afc58e9bace413c9d46c"
)


@dataclass(frozen=True, slots=True)
class FrozenKnownExpertArtifact:
    """Small verified view of the create-once #173 live artifact."""

    artifact_sha256: str
    report_sha256: str
    source_text: str
    source_sha256: str
    input_sha256: str
    unit_id: str
    predicted_event: Mapping[str, object]
    prior_exact_match_count: int
    prior_predicted_event_count: int
    prior_non_exact_requirements_passed: bool


def load_frozen_known_expert_artifact(
    path: Path,
    *,
    expected_artifact_sha256: str = _EXPECTED_ARTIFACT_SHA256,
    expected_report_sha256: str = _EXPECTED_REPORT_SHA256,
) -> FrozenKnownExpertArtifact:
    """Reject replacement, modified, or safety-incomplete prior artifacts."""

    raw_bytes = path.read_bytes()
    artifact_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    if artifact_sha256 != expected_artifact_sha256:
        raise RuntimeError("known-expert artifact SHA-256 changed")
    raw: object = json.loads(raw_bytes)
    report = _required_mapping(raw, "report")
    embedded_report_sha256 = _required_text(report, "report_sha256")
    canonical_report = dict(report)
    canonical_report.pop("report_sha256")
    recomputed_report_sha256 = _sha256_json(canonical_report)
    if (
        embedded_report_sha256 != expected_report_sha256
        or recomputed_report_sha256 != expected_report_sha256
    ):
        raise RuntimeError("known-expert embedded report digest changed")
    if _required_text(report, "schema_version") != "tg04_known_expert_source_unit.v1":
        raise RuntimeError("known-expert artifact schema changed")
    if _required_text(report, "run_id") != _EXPECTED_RUN_ID:
        raise RuntimeError("known-expert artifact run changed")
    if _required_text(report, "model_id") != _EXPECTED_MODEL_ID:
        raise RuntimeError("known-expert artifact model changed")

    unit = _required_mapping(report.get("unit"), "unit")
    unit_id = _required_text(unit, "unit_id")
    if unit_id != _EXPECTED_UNIT_ID:
        raise RuntimeError("known-expert artifact unit changed")
    gate = _required_mapping(report.get("gate"), "gate")
    if (
        gate.get("passed") is not False
        or gate.get("decision") != "STOP_AND_RECALIBRATE"
    ):
        raise RuntimeError("known-expert prior gate must remain failed")
    requirements = _required_mapping(gate.get("requirements"), "gate requirements")
    exact_requirement = "exactly_one_complete_expert_event"
    if requirements.get(exact_requirement) is not False:
        raise RuntimeError("known-expert exact-match failure changed")
    non_exact_requirements = tuple(
        value for key, value in requirements.items() if key != exact_requirement
    )
    if not non_exact_requirements or not all(
        value is True for value in non_exact_requirements
    ):
        raise RuntimeError("known-expert prior safety requirements did not all pass")

    gate_inputs = _required_mapping(report.get("gate_inputs"), "gate inputs")
    predicted_events = report.get("predicted_events")
    if not isinstance(predicted_events, list) or len(predicted_events) != 1:
        raise RuntimeError("known-expert artifact must contain one predicted event")
    predicted_event = _required_mapping(predicted_events[0], "predicted event")
    return FrozenKnownExpertArtifact(
        artifact_sha256=artifact_sha256,
        report_sha256=embedded_report_sha256,
        source_text=_required_text(unit, "text"),
        source_sha256=_required_text(unit, "source_sha256"),
        input_sha256=_required_text(unit, "input_sha256"),
        unit_id=unit_id,
        predicted_event=predicted_event,
        prior_exact_match_count=_required_integer(
            gate_inputs,
            "exact_whole_event_match_count",
        ),
        prior_predicted_event_count=_required_integer(
            gate_inputs,
            "predicted_event_count",
        ),
        prior_non_exact_requirements_passed=True,
    )


def _required_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"known-expert {label} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise TypeError(f"known-expert {label} keys must be text")
    return value


def _required_text(value: Mapping[str, object], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item:
        raise ValueError(f"known-expert field {field} must be text")
    return item


def _required_integer(value: Mapping[str, object], field: str) -> int:
    item = value.get(field)
    if not isinstance(item, int) or isinstance(item, bool) or item < 0:
        raise ValueError(f"known-expert field {field} must be a nonnegative integer")
    return item


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8"),
    ).hexdigest()


__all__ = ["FrozenKnownExpertArtifact", "load_frozen_known_expert_artifact"]
