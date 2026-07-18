"""Hash-pinned authorization from the successful offline reassessment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

_EXPECTED_FILE_SHA256: Final = (
    "5a54a37d185f338edb76e5edb8166dacd36fb9adea301cba41699a7249e8dc09"
)
_EXPECTED_REPORT_SHA256: Final = (
    "7a97214a6540f4de7cfeefc8d556cbdc69e4f08e9f24a4410016bd902ef38435"
)


def verify_reassessment_authorization(path: Path) -> str:
    """Require the exact zero-call reassessment that authorized a fresh unit."""

    file_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if file_sha256 != _EXPECTED_FILE_SHA256:
        raise RuntimeError("reassessment authorization artifact changed")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("reassessment authorization must be a JSON object")
    _verify_authorization_payload(payload)
    return file_sha256


def _verify_authorization_payload(payload: dict[str, object]) -> None:
    gate = payload.get("gate")
    conclusion = payload.get("conclusion_scope")
    if (
        payload.get("schema_version") != "tg04_controlled_event_reassessment.v1"
        or payload.get("report_sha256") != _EXPECTED_REPORT_SHA256
        or not isinstance(gate, dict)
        or gate.get("passed") is not True
        or gate.get("decision") != "PROCEED_TO_NEW_FRESH_UNIT"
        or not isinstance(conclusion, dict)
        or conclusion.get("model_call_count") != 0
        or conclusion.get("qualification_eligible") is not False
    ):
        raise RuntimeError("reassessment did not authorize a fresh generalization unit")


__all__ = ["verify_reassessment_authorization"]
