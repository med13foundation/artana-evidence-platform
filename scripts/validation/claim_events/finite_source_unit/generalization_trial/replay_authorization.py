"""Hash-pinned authorization from the failed fresh generalization repeat."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

_EXPECTED_FILE_SHA256: Final = (
    "76c9ac65ba8c659784adedd626e83b82d69561ea2389b1cb04ba7c1eea09c302"
)
_EXPECTED_REPORT_SHA256: Final = (
    "7b742b487c0fd38674c257b1bafa319cc9a2f6c4dc1cb21b55d061001261f383"
)
_EXPECTED_FAILED_REQUIREMENTS: Final = frozenset(
    {
        "all_candidates_source_entailed",
        "all_candidates_structure_trusted",
        "sealed_expert_core_recovered",
    }
)


def verify_failed_generalization_authorization(path: Path) -> str:
    """Require the exact failed fresh result before adaptive replay."""

    file_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if file_sha256 != _EXPECTED_FILE_SHA256:
        raise RuntimeError("failed generalization artifact changed")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("failed generalization artifact must be a JSON object")
    _verify_failed_generalization_payload(payload)
    return file_sha256


def _verify_failed_generalization_payload(payload: dict[str, object]) -> None:
    gate = payload.get("gate")
    unit = payload.get("unit")
    if (
        payload.get("schema_version") != "tg04_generalization_trial.v1"
        or payload.get("experiment_mode") != "fresh"
        or payload.get("repeat_index") != 1
        or payload.get("report_sha256") != _EXPECTED_REPORT_SHA256
        or not isinstance(gate, dict)
        or gate.get("passed") is not False
        or gate.get("decision") != "STOP_AND_RECALIBRATE_GENERALIZATION"
        or not isinstance(unit, dict)
        or unit.get("unit_id")
        != "source-unit-6508d78fe2bb4886b606f91f2c990c36b55f54b2ac9886448e5251693222b3fe"
    ):
        raise RuntimeError("failed result does not authorize adaptive replay")
    requirements = gate.get("requirements")
    if not isinstance(requirements, dict):
        raise TypeError("failed result lacks gate requirements")
    failed = {name for name, passed in requirements.items() if passed is not True}
    if failed != _EXPECTED_FAILED_REQUIREMENTS:
        raise RuntimeError("failed result boundary changed")


__all__ = ["verify_failed_generalization_authorization"]
