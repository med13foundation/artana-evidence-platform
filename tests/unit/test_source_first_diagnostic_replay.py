from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validation.public_gold.staged_event.context_experiment.source_first import (
    diagnostic_replay,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.diagnostic_replay import (
    EXPECTED_EVENT_IDS,
    DiagnosticReplayError,
    load_diagnostic_inventory,
)


def test_v3_diagnostic_inventory_replays_with_exact_hashes_and_offsets() -> None:
    replay = load_diagnostic_inventory()

    assert tuple(item.temporary_event_id for item in replay.inventory) == EXPECTED_EVENT_IDS
    assert [(item.trigger.start, item.trigger.end) for item in replay.inventory] == [
        (0, 8),
        (48, 59),
        (27, 35),
    ]
    assert replay.evidence["status"] == "NONCREDITABLE_DIAGNOSTIC_STAGE1_PASS"
    assert replay.evidence["qualification_credit"] is False


def test_v3_diagnostic_inventory_fails_on_payload_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = json.loads(diagnostic_replay.V3_CUSTODY.read_text())
    bundle["typed_output"]["events"][0]["exact_trigger"] = "Changed"
    tampered = tmp_path / "custody.json"
    tampered.write_text(json.dumps(bundle))
    monkeypatch.setattr(diagnostic_replay, "V3_CUSTODY", tampered)

    with pytest.raises(DiagnosticReplayError, match="payload hash mismatch"):
        load_diagnostic_inventory()
