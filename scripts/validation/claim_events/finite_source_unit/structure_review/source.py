"""Hash-pinned #177 artifact loading for structure-review replay."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitExtractionOutput,
)
from scripts.validation.claim_events.finite_source_unit.discovery.fresh_unit import (
    select_fresh_hidden_unit,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    bind_source_unit_extraction,
)
from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
    sha256_json,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.claim_frames import (
        BoundClaimInventoryItem,
    )

    from scripts.validation.claim_events.contracts import NaryClaimFixture
    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )

_REPO_ROOT: Final = Path(__file__).resolve().parents[5]
_PR177_REPORT_PATH: Final = (
    _REPO_ROOT / "docs/validation/reports/2026-07-18-tg04-fresh-hidden-discovery.md"
)
#: Moved once, by the 2026-07-25 redaction, which replaced quoted source spans
#: in the report with locators and digests and changed no finding, count or
#: verdict in it.  The redaction did not update this pin.  Superseded digest:
#: `9928865a22846c22def452370c74c05246668b41d6bb53da8564235185e2aea6`.
_PR177_REPORT_SHA256: Final = (
    "c330d1da1bd0dc04d98812cf94e825b14ae543664593e395113515cddf7f1231"
)
_PR177_ARTIFACT_SHA256: Final = (
    "b547b677af93b36dc3f3a5c950f913b918d54cbfd9ed63c26c2ccc6fa07d5ffc"
)
_PR177_ARTIFACT_SCHEMA: Final = "tg04_fresh_hidden_discovery.v1"
_EXPECTED_CANDIDATE_COUNT: Final = 2


@dataclass(frozen=True, slots=True)
class FrozenStructureReplaySource:
    """Verified source unit and candidates recovered from the immutable artifact."""

    unit: FrozenSourceUnit
    candidates: tuple[BoundClaimInventoryItem, ...]
    report_sha256: str
    artifact_sha256: str
    prior_embedded_report_sha256: str


def load_structure_replay_source(
    *,
    fixture: NaryClaimFixture,
    artifact_path: Path,
) -> FrozenStructureReplaySource:
    """Verify custody and bind the exact #177 candidates back to source."""

    report_sha256 = _verify_sha256(
        _PR177_REPORT_PATH,
        expected_sha256=_PR177_REPORT_SHA256,
        label="#177 report",
    )
    artifact_sha256 = _verify_sha256(
        artifact_path,
        expected_sha256=_PR177_ARTIFACT_SHA256,
        label="#177 artifact",
    )
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("#177 artifact must be a JSON object")
    if payload.get("schema_version") != _PR177_ARTIFACT_SCHEMA:
        raise RuntimeError("#177 artifact schema changed")
    embedded_sha256 = payload.get("report_sha256")
    if not isinstance(embedded_sha256, str):
        raise TypeError("#177 artifact lacks an embedded report hash")
    canonical_payload = dict(payload)
    canonical_payload.pop("report_sha256")
    if sha256_json(canonical_payload) != embedded_sha256:
        raise RuntimeError("#177 embedded report hash mismatch")

    selection = select_fresh_hidden_unit(fixture)
    unit_payload = payload.get("unit")
    if not isinstance(unit_payload, dict):
        raise TypeError("#177 artifact lacks a source unit")
    expected_identity = {
        "unit_id": selection.unit.unit_id,
        "source_sha256": selection.unit.source_sha256,
        "input_sha256": selection.unit.input_sha256,
    }
    if any(unit_payload.get(key) != value for key, value in expected_identity.items()):
        raise RuntimeError("#177 artifact source-unit identity changed")

    agent_outputs = payload.get("agent_outputs")
    if not isinstance(agent_outputs, dict):
        raise TypeError("#177 artifact lacks agent outputs")
    extraction_payload = agent_outputs.get("extraction")
    extraction = SourceUnitExtractionOutput.model_validate(extraction_payload)
    binding = bind_source_unit_extraction(extraction, unit=selection.unit)
    if len(binding.accepted) != _EXPECTED_CANDIDATE_COUNT or binding.rejected:
        raise RuntimeError("#177 candidate inventory no longer binds exactly")
    return FrozenStructureReplaySource(
        unit=selection.unit,
        candidates=binding.accepted,
        report_sha256=report_sha256,
        artifact_sha256=artifact_sha256,
        prior_embedded_report_sha256=embedded_sha256,
    )


def _verify_sha256(path: Path, *, expected_sha256: str, label: str) -> str:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected_sha256:
        raise RuntimeError(f"{label} changed")
    return actual


__all__ = ["FrozenStructureReplaySource", "load_structure_replay_source"]
