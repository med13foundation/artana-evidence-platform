"""Fail-closed replay of the non-creditable V3 event inventory."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts.validation.public_gold.staged_event.context_experiment.source_first.inventory import (
    EventInventoryOutput,
    ResolvedInventoryEvent,
    compare_exposed_inventory,
    resolve_inventory,
)

REPO = Path(__file__).resolve().parents[6]
SOURCE = REPO / (
    "validation/public_gold/bionlp_cg/raw/bionlp-st-2013-cg-master/"
    "original-data/devel/PMID-16428936.txt"
)
V3_CUSTODY = REPO / (
    "docs/validation/receipts/2026-07-22-staged-luna-v3-inventory-custody.json"
)
V3_PREREGISTRATION = REPO / (
    "docs/validation/preregistrations/"
    "2026-07-22-staged-luna-event-construction-v3.json"
)
INVENTORY_PROMPT = REPO / (
    "docs/validation/prompts/2026-07-22-staged-luna-event-inventory-v2.md"
)
SOURCE_SHA256 = "00da32aa63d3aa0f48d3c02f806e8db9ca2cd10bda0357280674a188a04523ab"
PAYLOAD_SHA256 = "0b6124d935a0708961a8cb9515341365c2eaae4486c4a932fb1d02c86adc6356"
EXPECTED_RESPONSE_ID = "resp_0318bce8f23c6172006a60f02ae04881998ef9903dab5b0548"
EXPECTED_EVENT_IDS = (
    "evt_decrease_c_myc_activity",
    "evt_cancer_cell_sensitivity",
    "evt_enhances_sensitivity",
)
SCOPE_START = 0
SCOPE_END = 222


class DiagnosticReplayError(RuntimeError):
    """The preserved diagnostic inventory cannot be replayed faithfully."""


@dataclass(frozen=True, slots=True)
class DiagnosticInventoryReplay:
    inventory: tuple[ResolvedInventoryEvent, ...]
    evidence: dict[str, object]


def load_diagnostic_inventory() -> DiagnosticInventoryReplay:
    """Verify V3 custody and replay its exact typed inventory offline."""

    bundle = _object(V3_CUSTODY)
    preregistration = _object(V3_PREREGISTRATION)
    frozen = preregistration.get("frozen_state")
    if not isinstance(frozen, dict):
        raise DiagnosticReplayError("V3 frozen state is absent")
    source = SOURCE.read_text(encoding="utf-8")
    if hashlib.sha256(source.encode()).hexdigest() != SOURCE_SHA256:
        raise DiagnosticReplayError("exposed source hash changed")
    _require_equal(bundle, "response_id", EXPECTED_RESPONSE_ID)
    _require_equal(bundle, "output_sha256", PAYLOAD_SHA256)
    _require_equal(bundle, "provider_input_sha256", frozen.get("inventory_provider_input_sha256"))
    _require_equal(bundle, "schema_sha256", frozen.get("inventory_schema_sha256"))
    if frozen.get("source_sha256") != SOURCE_SHA256:
        raise DiagnosticReplayError("V3 preregistered source hash changed")
    prompt_hash = hashlib.sha256(INVENTORY_PROMPT.read_bytes()).hexdigest()
    if frozen.get("inventory_prompt_sha256") != prompt_hash:
        raise DiagnosticReplayError("V3 inventory prompt hash changed")
    receipt = bundle.get("receipt")
    if not isinstance(receipt, dict) or receipt.get("status") != "VERIFIED_LIVE":
        raise DiagnosticReplayError("V3 receipt is not verified live")
    budgets = bundle.get("requested_and_observed_budgets")
    if not isinstance(budgets, dict):
        raise DiagnosticReplayError("V3 budget evidence is absent")
    if any(budgets.get(axis) != "PASS" for axis in ("output_tokens", "total_tokens", "latency", "cost")):
        raise DiagnosticReplayError("V3 provider budget did not pass")
    typed_payload = bundle.get("typed_output")
    if not isinstance(typed_payload, dict):
        raise DiagnosticReplayError("V3 canonical typed payload is absent")
    recomputed_payload_hash = _canonical_sha256(typed_payload)
    if recomputed_payload_hash != PAYLOAD_SHA256:
        raise DiagnosticReplayError("V3 canonical payload hash mismatch")
    output = EventInventoryOutput.model_validate_json(
        json.dumps(typed_payload, separators=(",", ":"))
    )
    ids = tuple(item.temporary_event_id for item in output.events)
    if ids != EXPECTED_EVENT_IDS:
        raise DiagnosticReplayError("V3 event identity or ordering changed")
    inventory = resolve_inventory(
        output,
        source=source,
        scope_start=SCOPE_START,
        scope_end=SCOPE_END,
    )
    gate = compare_exposed_inventory(inventory)
    if not gate.passed or not gate.intermediate_event_present:
        raise DiagnosticReplayError("V3 diagnostic inventory gate did not pass")
    evidence = {
        "status": "NONCREDITABLE_DIAGNOSTIC_STAGE1_PASS",
        "response_id": EXPECTED_RESPONSE_ID,
        "receipt_status": receipt["status"],
        "budget_results": {
            axis: budgets[axis]
            for axis in ("output_tokens", "total_tokens", "latency", "cost")
        },
        "provider_input_sha256": bundle["provider_input_sha256"],
        "recorded_payload_sha256": bundle["output_sha256"],
        "recomputed_payload_sha256": recomputed_payload_hash,
        "source_sha256": SOURCE_SHA256,
        "inventory_prompt_sha256": prompt_hash,
        "inventory_schema_sha256": frozen["inventory_schema_sha256"],
        "resolved_events": [
            {
                "event_id": item.temporary_event_id,
                "event_type": item.event_type.value,
                "trigger": asdict(item.trigger),
                "structural_position": item.structural_position,
                "explanation": item.explanation,
            }
            for item in inventory
        ],
        "inventory_gate": asdict(gate),
        "qualification_credit": False,
        "trusted_promotion": False,
    }
    return DiagnosticInventoryReplay(inventory=inventory, evidence=evidence)


def _object(path: Path) -> dict[str, object]:
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise DiagnosticReplayError(f"artifact is not an object: {path.name}")
    return loaded


def _require_equal(container: dict[str, object], key: str, expected: object) -> None:
    if container.get(key) != expected:
        raise DiagnosticReplayError(f"V3 custody mismatch: {key}")


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "DiagnosticInventoryReplay",
    "DiagnosticReplayError",
    "EXPECTED_EVENT_IDS",
    "PAYLOAD_SHA256",
    "load_diagnostic_inventory",
]
