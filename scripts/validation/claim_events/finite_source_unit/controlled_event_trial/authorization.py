"""Hash-pinned authorization from the successful structure replay."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

_EXPECTED_FILE_SHA256: Final = (
    "d0a19ad1591698d010943f266aa8efdf8abf8e7f37ceba619af81ce109fdd7d1"
)
_EXPECTED_REPORT_SHA256: Final = (
    "238b99c275f2c489ac83416363a5ca3cea43e94ea110a75006923f4d7540869e"
)


def verify_structure_replay_authorization(path: Path) -> str:
    """Require the exact successful replay before spending a fresh unit."""

    file_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if file_sha256 != _EXPECTED_FILE_SHA256:
        raise RuntimeError("structure-replay authorization artifact changed")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("structure-replay authorization must be a JSON object")
    _verify_authorization_payload(payload)
    return file_sha256


def _verify_authorization_payload(payload: dict[str, object]) -> None:
    gate = payload.get("gate")
    if (
        payload.get("schema_version") != "tg04_structure_replay.v1"
        or payload.get("report_sha256") != _EXPECTED_REPORT_SHA256
        or not isinstance(gate, dict)
        or gate.get("passed") is not True
        or gate.get("decision") != "PROCEED_TO_ONE_NEW_HIDDEN_UNIT"
    ):
        raise RuntimeError("structure replay did not authorize a fresh unit")


__all__ = ["verify_structure_replay_authorization"]
