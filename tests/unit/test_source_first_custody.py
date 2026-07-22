from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validation.public_gold.lossless_event_experiment_contracts import (
    SourceEventType,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    CustodyPersistenceError,
    StageCustodyInput,
    StageCustodyPaths,
    persist_stage_custody,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.inventory import (
    EventInventoryOutput,
    InventoryEvent,
)


def _output() -> EventInventoryOutput:
    return EventInventoryOutput(
        packet_id="fake-stage",
        events=(
            InventoryEvent(
                temporary_event_id="event-1",
                event_type=SourceEventType.REGULATION,
                exact_trigger="state",
                exact_evidence="A state changed.",
                structural_position="ROOT_CANDIDATE",
                explanation="An explicit state.",
            ),
        ),
    )


def _receipt() -> dict[str, object]:
    return {
        "status": "VERIFIED_LIVE",
        "identity": {
            "response_id": "resp-fake",
            "output_items": (("reasoning", "rs-1"), ("message", "msg-1")),
        },
        "budgets": {
            "requested_max_output_tokens": 16000,
            "requested_max_total_tokens": 24000,
            "requested_max_latency_seconds": 900.0,
            "requested_max_cost_usd": 0.25,
            "observed_output_tokens": 100,
            "observed_total_tokens": 200,
            "observed_latency_seconds": 1.0,
            "observed_cost_usd": 0.01,
            "output_tokens": "PASS",
            "total_tokens": "PASS",
            "latency": "PASS",
            "cost": "PASS",
        },
    }


def _paths(root: Path) -> StageCustodyPaths:
    return StageCustodyPaths(
        bundle=root / "bundle.json",
        receipt=root / "receipt.json",
        raw_output=root / "raw.json",
    )


def test_atomic_custody_preserves_strict_tuple_output(tmp_path: Path) -> None:
    output = _output()

    record = persist_stage_custody(
        custody_input=StageCustodyInput(
            paths=_paths(tmp_path),
            stage="EVENT_INVENTORY",
            provider_input="frozen input",
            schema_sha256="schema-hash",
        ),
        output=output,
        canonical_payload=output.model_dump(mode="json"),
        receipt=_receipt(),
    )

    bundle = json.loads((tmp_path / "bundle.json").read_text())
    assert isinstance(output.events, tuple)
    assert bundle["typed_output"]["events"][0]["temporary_event_id"] == "event-1"
    assert bundle["response_id"] == "resp-fake"
    assert record.bundle_sha256
    assert not tuple(tmp_path.glob(".*.json.*"))


@pytest.mark.parametrize(
    "receipt",
    [
        {"budgets": {}},
        {"identity": {"response_id": "resp-fake"}},
    ],
)
def test_custody_fails_before_writing_incomplete_lineage(
    tmp_path: Path, receipt: dict[str, object]
) -> None:
    with pytest.raises(CustodyPersistenceError):
        persist_stage_custody(
            custody_input=StageCustodyInput(
                paths=_paths(tmp_path),
                stage="EVENT_INVENTORY",
                provider_input="frozen input",
                schema_sha256="schema-hash",
            ),
            output=_output(),
            canonical_payload=_output().model_dump(mode="json"),
            receipt=receipt,
        )

    assert not tuple(tmp_path.iterdir())


def test_canonical_bundle_survives_derivative_model_mismatch(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    canonical = _output().model_dump(mode="json")
    canonical["packet_id"] = "provider-packet"

    with pytest.raises(CustodyPersistenceError, match="differs"):
        persist_stage_custody(
            custody_input=StageCustodyInput(
                paths=paths,
                stage="EVENT_INVENTORY",
                provider_input="frozen input",
                schema_sha256="schema-hash",
            ),
            output=_output(),
            canonical_payload=canonical,
            receipt=_receipt(),
        )

    assert paths.bundle.exists()
    assert not paths.receipt.exists()
    assert not paths.raw_output.exists()
