from __future__ import annotations

import hashlib
import json
from pathlib import Path

from artana_evidence_api.document_extraction_support.scientific_events import (
    ScientificEventDocument,
)

ROOT = Path(__file__).parents[2]
PREREGISTRATION = (
    ROOT
    / "docs/validation/preregistrations/2026-07-21-lossless-event-ir-development-experiment.json"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_frozen_lossless_event_experiment_hashes_match_workspace() -> None:
    preregistration = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
    frozen = preregistration["frozen_implementation"]
    actual_code_hashes = {path: _sha256(ROOT / path) for path in frozen["code_files"]}
    schema_payload = ScientificEventDocument.model_json_schema()
    schema_hash = hashlib.sha256(
        json.dumps(schema_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    bundle_hash = hashlib.sha256(
        json.dumps(actual_code_hashes, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    assert actual_code_hashes == frozen["code_files"]
    assert schema_hash == frozen["schema_sha256"]
    assert bundle_hash == frozen["implementation_bundle_sha256"]
    assert (
        _sha256(ROOT / preregistration["prompt"]["path"])
        == preregistration["prompt"]["sha256"]
    )
    assert preregistration["execution_authorized"] is False
    assert preregistration["source"]["test_access"] == "SEALED"
