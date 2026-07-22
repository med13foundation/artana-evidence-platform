from __future__ import annotations

import json
from pathlib import Path

from scripts.validation.public_gold.staged_event.context_experiment.offline_participant_adjudication import (
    PAYLOAD_SHA256,
    deterministic_metrics,
)

PACKETS = Path(
    "docs/validation/adjudications/2026-07-22-luna-context-v2-participant-packets.json"
)
CONSENSUS = Path(
    "docs/validation/adjudications/2026-07-22-luna-context-v2-participant-consensus.json"
)


def _packets() -> dict[str, object]:
    payload = json.loads(PACKETS.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_preserved_luna_payload_builds_complete_noncreditable_packets() -> None:
    packets = _packets()
    metrics = deterministic_metrics(packets)

    assert packets["retrieved_payload_sha256"] == PAYLOAD_SHA256
    assert packets["participant_count"] == 25
    assert len(packets["packets"]) == 25
    assert metrics["offset_failures"] == 2
    assert metrics["wrong_to_correct_events"] == []
    assert metrics["correct_to_wrong_events"] == []
    assert metrics["correct_controls_preserved"] == [
        "E-0effc9409e12ed77b198",
        "E-2d5bd3d8506d519d2d69",
        "E-60b0d54816b0585893d1",
    ]


def test_offset_invalid_participant_never_receives_exact_gold_credit() -> None:
    packets = _packets()
    invalid = [item for item in packets["packets"] if not item["exact_span_valid"]]

    assert len(invalid) == 2
    assert all(not item["exact_gold_participant"] for item in invalid)
    assert any(item["counterfactual_exact_gold_if_offset_valid"] for item in invalid)


def test_consensus_stops_before_micro_canary_when_no_errors_are_repaired() -> None:
    consensus = json.loads(CONSENSUS.read_text(encoding="utf-8"))
    metrics = consensus["metrics"]

    assert consensus["decision"] == "PIVOT_TO_SPECIALIST_CANDIDATES"
    assert consensus["micro_canary_executed"] is False
    assert len(consensus["judgments"]) == 25
    assert metrics["wrong_to_correct_events"] == []
    assert metrics["correct_to_wrong_events"] == []
    assert len(metrics["correct_controls_preserved"]) == 4
    assert metrics["unsupported_extras"] == 2
    assert metrics["unresolved_disagreements"] == 0
