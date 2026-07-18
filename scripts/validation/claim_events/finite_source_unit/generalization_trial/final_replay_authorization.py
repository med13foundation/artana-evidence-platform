"""Hash-pinned authorization for one final exposed adaptive replay."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

_EXPECTED_FILE_SHA256: Final = (
    "491b407371cd1cd1fe48d771bf62a05161982b10485fb3d0db49ae9b761982a3"
)
_EXPECTED_REPORT_SHA256: Final = (
    "41c35bb8bbeb1e416a481001724b592cf32b786ab54ed4c877574b186feca955"
)
_EXPECTED_FAILED_REQUIREMENTS: Final = frozenset(
    {"binding_rejection_zero", "sealed_expert_core_recovered"}
)
_EXPECTED_TRUSTED_CANDIDATE_COUNT: Final = 2


def verify_final_replay_authorization(path: Path) -> str:
    """Require the exact binding-only failure before the last exposed call."""

    file_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if file_sha256 != _EXPECTED_FILE_SHA256:
        raise RuntimeError("binding-only replay artifact changed")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("binding-only replay artifact must be a JSON object")
    _verify_final_replay_payload(payload)
    return file_sha256


def _verify_final_replay_payload(payload: dict[str, object]) -> None:
    gate = payload.get("gate")
    inputs = payload.get("gate_inputs")
    if (
        payload.get("schema_version") != "tg04_generalization_replay.v1"
        or payload.get("experiment_mode") != "adaptive_replay"
        or payload.get("report_sha256") != _EXPECTED_REPORT_SHA256
        or not isinstance(gate, dict)
        or gate.get("passed") is not False
        or gate.get("decision") != "STOP_AND_RECALIBRATE_GENERALIZATION"
        or not isinstance(inputs, dict)
        or inputs.get("binding_rejection_count") != 1
        or inputs.get("trusted_candidate_count") != _EXPECTED_TRUSTED_CANDIDATE_COUNT
        or inputs.get("invalid_agent_output_count") != 0
    ):
        raise RuntimeError("binding-only result does not authorize final replay")
    requirements = gate.get("requirements")
    if not isinstance(requirements, dict):
        raise TypeError("binding-only result lacks gate requirements")
    failed = {name for name, passed in requirements.items() if passed is not True}
    if failed != _EXPECTED_FAILED_REQUIREMENTS:
        raise RuntimeError("binding-only failure boundary changed")


__all__ = ["verify_final_replay_authorization"]
