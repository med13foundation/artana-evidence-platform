"""Hash-pinned authorization from failed fresh controlled-event repeat 1."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

_EXPECTED_FILE_SHA256: Final = (
    "11269f9c21b3670c75f339e0468364118c4f3a47ba2773783ec4102e681679f7"
)
_EXPECTED_REPORT_SHA256: Final = (
    "1503f4f1de58ab8156d960c4d4f9c888d2716bcb39255bc1b03ab95ee24464cc"
)
_EXPECTED_UNIT_ID: Final = (
    "source-unit-02c41780fd8d83965debdc337f89adce6283552fa76ac7d36ee12c56060ef21b"
)


def verify_failed_trial_authorization(path: Path) -> str:
    """Require the exact failed run before an adaptive replay is permitted."""

    file_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if file_sha256 != _EXPECTED_FILE_SHA256:
        raise RuntimeError("failed controlled-event artifact changed")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("failed controlled-event artifact must be a JSON object")
    _verify_failed_trial_payload(payload)
    return file_sha256


def _verify_failed_trial_payload(payload: dict[str, object]) -> None:
    gate = payload.get("gate")
    unit = payload.get("unit")
    if not isinstance(gate, dict) or not isinstance(unit, dict):
        raise TypeError("failed controlled-event artifact lacks gate custody")
    requirements = gate.get("requirements")
    if not isinstance(requirements, dict):
        raise TypeError("failed controlled-event artifact lacks requirements")
    if (
        payload.get("schema_version") != "tg04_controlled_event_trial.v1"
        or payload.get("report_sha256") != _EXPECTED_REPORT_SHA256
        or payload.get("repeat_index") != 1
        or unit.get("unit_id") != _EXPECTED_UNIT_ID
        or gate.get("passed") is not False
        or gate.get("decision") != "STOP_AND_RECALIBRATE_CONTROLLED_EVENT_EXTRACTION"
        or requirements.get("sealed_expert_core_recovered") is not False
        or requirements.get("provider_receipts_verified") is not False
    ):
        raise RuntimeError("artifact does not authorize the adaptive replay")


__all__ = ["verify_failed_trial_authorization"]
