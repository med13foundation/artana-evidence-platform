"""Hash-pinned authorization from the first failed adaptive replay."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

_EXPECTED_FILE_SHA256: Final = (
    "28b9320a30bc9012dd6350eafad9cbbc29f314344f6600d6f1c8c555d7625b4e"
)
_EXPECTED_REPORT_SHA256: Final = (
    "9ef7bb42b224610ffc8c5fa04588b5058f877f09431a9013e3fd13150d5f3201"
)
_EXPECTED_FAILED_REQUIREMENTS: Final = frozenset(
    {
        "agent_execution_complete",
        "all_candidates_source_entailed",
        "all_candidates_structure_trusted",
        "binding_rejection_zero",
        "candidate_inventory_complete",
        "independent_categories_agree",
        "invalid_agent_output_zero",
        "sealed_expert_core_recovered",
        "verifier_recognized_finding",
    }
)


def verify_failed_adaptive_replay_authorization(path: Path) -> str:
    """Require the exact first adaptive failure before one second replay."""

    file_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if file_sha256 != _EXPECTED_FILE_SHA256:
        raise RuntimeError("failed adaptive replay artifact changed")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("failed adaptive replay artifact must be a JSON object")
    _verify_failed_adaptive_replay_payload(payload)
    return file_sha256


def _verify_failed_adaptive_replay_payload(payload: dict[str, object]) -> None:
    gate = payload.get("gate")
    outputs = payload.get("agent_outputs")
    if (
        payload.get("schema_version") != "tg04_generalization_replay.v1"
        or payload.get("experiment_mode") != "adaptive_replay"
        or payload.get("report_sha256") != _EXPECTED_REPORT_SHA256
        or not isinstance(gate, dict)
        or gate.get("passed") is not False
        or gate.get("decision") != "STOP_AND_RECALIBRATE_GENERALIZATION"
        or not isinstance(outputs, dict)
        or outputs.get("error_type") != "StructuredModelSchemaError"
    ):
        raise RuntimeError("failed adaptive result does not authorize a second replay")
    requirements = gate.get("requirements")
    if not isinstance(requirements, dict):
        raise TypeError("failed adaptive result lacks gate requirements")
    failed = {name for name, passed in requirements.items() if passed is not True}
    if failed != _EXPECTED_FAILED_REQUIREMENTS:
        raise RuntimeError("failed adaptive result boundary changed")


__all__ = ["verify_failed_adaptive_replay_authorization"]
