"""Integrity check for the #174 authorization artifact."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_EXPECTED_ARTIFACT_SHA256: Final = (
    "1d15e7b05248daf6ad10f6a647be4820e7303dcd724caee2a84f5da9da734f68"
)
_EXPECTED_REPORT_SHA256: Final = (
    "1e775d4ea0b203a6c69fa4b218ff7ff3d1512ea7b031617eff4d46f1c10d2f43"
)


@dataclass(frozen=True, slots=True)
class DiscoveryAuthorization:
    """Verified permission for exactly one hidden discovery unit."""

    artifact_sha256: str
    report_sha256: str


def load_discovery_authorization(
    path: Path,
    *,
    expected_artifact_sha256: str = _EXPECTED_ARTIFACT_SHA256,
    expected_report_sha256: str = _EXPECTED_REPORT_SHA256,
) -> DiscoveryAuthorization:
    """Require the exact successful #174 artifact and its narrow scope."""

    raw_bytes = path.read_bytes()
    artifact_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    if artifact_sha256 != expected_artifact_sha256:
        raise RuntimeError("discovery authorization artifact SHA-256 changed")
    raw: object = json.loads(raw_bytes)
    if not isinstance(raw, dict):
        raise TypeError("discovery authorization report must be an object")
    report: dict[str, object] = raw
    embedded_sha256 = report.get("report_sha256")
    if not isinstance(embedded_sha256, str):
        raise TypeError("discovery authorization report digest is missing")
    canonical = dict(report)
    canonical.pop("report_sha256")
    recomputed_sha256 = _sha256_json(canonical)
    if (
        embedded_sha256 != expected_report_sha256
        or recomputed_sha256 != expected_report_sha256
    ):
        raise RuntimeError("discovery authorization embedded digest changed")
    if report.get("schema_version") != "tg04_representation_adjudication.v1":
        raise RuntimeError("discovery authorization schema changed")
    if report.get("run_id") != "tg04-representation-adjudication-luna-01":
        raise RuntimeError("discovery authorization run changed")
    gate = report.get("gate")
    if not isinstance(gate, dict):
        raise TypeError("discovery authorization gate must be an object")
    if gate.get("passed") is not True or gate.get("decision") != (
        "PROCEED_TO_ONE_UNANNOTATED_DISCOVERY_UNIT"
    ):
        raise RuntimeError("discovery authorization gate did not pass")
    requirements = gate.get("requirements")
    if not isinstance(requirements, dict) or not requirements:
        raise TypeError("discovery authorization requirements are missing")
    if not all(value is True for value in requirements.values()):
        raise RuntimeError("discovery authorization requirements did not all pass")
    scope = report.get("conclusion_scope")
    if not isinstance(scope, dict):
        raise TypeError("discovery authorization scope must be an object")
    if (
        scope.get("exact_benchmark_score_changed") is not False
        or scope.get("exact_whole_event_match_count") != 0
        or scope.get("scientific_readiness_proven") is not False
        or scope.get("persistence_authorized") is not False
    ):
        raise RuntimeError("discovery authorization scope widened")
    return DiscoveryAuthorization(
        artifact_sha256=artifact_sha256,
        report_sha256=embedded_sha256,
    )


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8"),
    ).hexdigest()


__all__ = ["DiscoveryAuthorization", "load_discovery_authorization"]
