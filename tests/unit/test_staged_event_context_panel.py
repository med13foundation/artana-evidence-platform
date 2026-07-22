from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
)
from scripts.validation.public_gold.staged_event.context_experiment.compact_input import (
    V1_PARTICIPANT_INPUT_BYTES,
    build_compact_payload,
    canonical_payload_bytes,
)
from scripts.validation.public_gold.staged_event.context_experiment.contracts import (
    SourceBoundEventInventory,
    SourceBoundParticipant,
    SourceBoundParticipantOutput,
)
from scripts.validation.public_gold.staged_event.context_experiment.live_execution import (
    _record_rejected_budget,
)
from scripts.validation.public_gold.staged_event.context_experiment.panel import (
    CONTROL_IDS,
    DEPENDENCY_CONTEXT_IDS,
    PANEL_IDS,
    REPAIR_TARGET_IDS,
    WRONG_EVENT_TYPE_IDS,
    _participant_map,
    _sentence_spans,
    build_context_panel,
)
from scripts.validation.public_gold.staged_event.context_experiment.participant_grounding import (
    ParticipantGroundingError,
    ground_participants,
    validate_participant_grounding,
)
from scripts.validation.public_gold.staged_event.context_experiment.preflight import (
    RESULT_PATH,
    SOURCE_PATH,
    _canonical_sha256,
    build_preregistration,
)
from scripts.validation.public_gold.staged_event.live_execution import BudgetLedger

ROOT = Path(__file__).resolve().parents[2]
from scripts.validation.public_gold.staged_event.contracts import (
    EventParticipantInventory,
    ParticipantCandidate,
    ParticipantInventoryOutput,
    ParticipantTargetKind,
    SourceEntityType,
)


def test_panel_is_fixed_to_semantic_errors_controls_and_dependencies() -> None:
    assert PANEL_IDS == REPAIR_TARGET_IDS | CONTROL_IDS | DEPENDENCY_CONTEXT_IDS
    assert len(PANEL_IDS) == 20
    assert not PANEL_IDS & WRONG_EVENT_TYPE_IDS


def test_sentence_offsets_resolve_exactly() -> None:
    source = "First event occurs. These cells respond. A final result follows."
    spans = _sentence_spans(source)

    assert [source[int(item["start"]) : int(item["end"])] for item in spans] == [
        item["text"] for item in spans
    ]
    assert [item["text"] for item in spans] == [
        "First event occurs.",
        "These cells respond.",
        "A final result follows.",
    ]


def test_repeated_participants_have_source_bound_occurrence_ids() -> None:
    source = "A activates A in A-positive cells."
    output = ParticipantInventoryOutput(
        inventories=(
            EventParticipantInventory(
                event_id="E-test",
                decision="INVENTORIED",
                participants=(
                    ParticipantCandidate(
                        participant_key="a",
                        exact_text="A",
                        occurrence_id="occurrence-1",
                        occurrence_index=1,
                        candidate_target_kind=ParticipantTargetKind.PARTICIPANT,
                        source_entity_type=SourceEntityType.GENE_OR_GENE_PRODUCT,
                        explanation="The repeated participant is explicit.",
                    ),
                ),
                abstention_reason=None,
            ),
        )
    )

    mentions = _participant_map(source, output)

    assert [item["occurrence_id"] for item in mentions] == [
        "occurrence-0",
        "occurrence-1",
        "occurrence-2",
    ]
    assert [item["start"] for item in mentions] == [0, 12, 17]


def test_few_shots_cover_the_broken_semantic_boundaries_without_gold() -> None:
    prompt_names = (
        "2026-07-22-luna-context-participants.md",
        "2026-07-22-luna-context-roles.md",
        "2026-07-22-luna-context-modifiers.md",
        "2026-07-22-luna-context-verification.md",
    )
    prompts = {
        name: (ROOT / "docs/validation/prompts" / name).read_text(encoding="utf-8")
        for name in prompt_names
    }
    combined = "\n".join(prompts.values()).lower()

    assert "occurrence id" in prompts[prompt_names[0]].lower()
    assert "complete reduction event as `cause`" in prompts[prompt_names[1]].lower()
    assert "not necessarily speculative" in prompts[prompt_names[2]].lower()
    assert "one wrong role" in prompts[prompt_names[3]].lower()
    assert "gold e1" not in combined
    assert "9/30" not in combined
    assert "expected event count" not in combined
    assert "numeric confidence" in prompts[prompt_names[3]].lower()


def test_compact_payload_serializes_shared_source_and_event_map_once() -> None:
    panel = build_context_panel(
        result_path=ROOT / RESULT_PATH, source_path=ROOT / SOURCE_PATH
    )
    payload = build_compact_payload(panel=panel, prior_stage_outputs={})
    serialized = json.dumps(payload, sort_keys=True)
    source = str(panel.shared_context["source_text"])

    assert serialized.count(json.dumps(source)[1:-1]) == 1
    assert "compact_event_map" in payload["shared_context"]
    assert all("source_text" not in packet for packet in panel.packets)
    assert all("event_map" not in packet for packet in panel.packets)
    assert canonical_payload_bytes(payload) < V1_PARTICIPANT_INPUT_BYTES // 2


def test_preregistration_freezes_compact_input_size_and_hashes() -> None:
    preregistration = build_preregistration(ROOT, authorized=True)
    inputs = preregistration["frozen_state"]["inputs"]

    assert inputs["participant_provider_input_bytes"] < V1_PARTICIPANT_INPUT_BYTES // 2
    assert inputs["participant_estimated_input_tokens"] > 0
    assert inputs["input_token_estimation_method"] == "ceil(utf8_bytes/4)"
    assert inputs["participant_provider_input_sha256"]
    assert inputs["shared_context_sha256"]
    assert inputs["target_packets_sha256"]


@pytest.mark.parametrize(
    ("section", "key"),
    [
        ("source", "sha256"),
        ("inputs", "target_packets_sha256"),
        ("prompts", "participants"),
        ("schemas", "participants"),
        ("model", "reasoning_effort"),
    ],
)
def test_frozen_hash_changes_for_every_owned_input(section: str, key: str) -> None:
    preregistration = build_preregistration(ROOT, authorized=True)
    frozen = preregistration["frozen_state"]
    original = _canonical_sha256(frozen)
    changed = copy.deepcopy(frozen)
    section_value = changed[section]
    assert isinstance(section_value, dict)
    current = section_value[key]
    section_value[key] = (
        {"changed": True} if isinstance(current, dict) else f"{current}-changed"
    )

    assert _canonical_sha256(changed) != original


def test_rejected_budget_is_recorded_with_observed_accounting() -> None:
    ledger = BudgetLedger(
        max_calls=4,
        max_tokens=300_000,
        max_output_tokens_per_call=50_000,
        max_cost_usd=3.0,
        max_latency_seconds=3600.0,
    )
    error = ProviderExecutionError(
        "RECEIPT_BUDGET",
        "total token ceiling exceeded",
        diagnostics={
            "response_id": "resp-redacted",
            "provider_input_bytes": 45_000,
            "estimated_input_tokens": 11_250,
            "input_token_estimation_method": "ceil(utf8_bytes/4)",
            "observed_usage": {
                "input_tokens": 11_000,
                "cached_input_tokens": 1_000,
                "output_tokens": 300_000,
                "reasoning_tokens": 299_000,
                "total_tokens": 311_000,
                "latency_seconds": 100.0,
                "cost_usd": 1.81,
            },
        },
    )

    _record_rejected_budget(ledger, "participants", error)

    assert ledger.calls == 1
    assert ledger.total_tokens == 311_000
    assert ledger.total_cost_usd == pytest.approx(1.81)
    assert ledger.receipts[0]["status"] == "REJECTED_BUDGET"


def test_source_bound_participant_must_resolve_inside_event_scope() -> None:
    panel = build_context_panel(
        result_path=ROOT / RESULT_PATH, source_path=ROOT / SOURCE_PATH
    )
    packet = panel.packets[0]
    sentence = packet["primary_evidence_sentence"]
    assert isinstance(sentence, dict)
    text = str(sentence["text"])
    exact = text.split()[0]
    start = int(sentence["start"])
    output = SourceBoundParticipantOutput(
        inventories=(
            SourceBoundEventInventory(
                event_id=str(packet["event_id"]),
                decision="INVENTORIED",
                participants=(
                    SourceBoundParticipant(
                        participant_key="local",
                        exact_text=exact,
                        start=start,
                        end=start + len(exact),
                        occurrence_id="occurrence-0",
                        candidate_target_kind=ParticipantTargetKind.PARTICIPANT,
                        source_entity_type=SourceEntityType.GENE_OR_GENE_PRODUCT,
                        explanation="Exact local source span.",
                    ),
                ),
                abstention_reason=None,
            ),
        )
    )

    validate_participant_grounding(output, panel=panel)
    grounded = ground_participants(output, panel=panel)
    expected_index = str(panel.shared_context["source_text"])[:start].count(exact)
    assert grounded.inventories[0].participants[0].occurrence_index == expected_index
    invalid = output.model_copy(
        update={
            "inventories": (
                output.inventories[0].model_copy(
                    update={
                        "participants": (
                            output.inventories[0]
                            .participants[0]
                            .model_copy(update={"start": 0, "end": len(exact)}),
                        )
                    }
                ),
            )
        }
    )
    with pytest.raises(ParticipantGroundingError):
        validate_participant_grounding(invalid, panel=panel)
