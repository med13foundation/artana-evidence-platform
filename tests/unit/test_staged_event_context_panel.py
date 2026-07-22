from __future__ import annotations

from pathlib import Path

from scripts.validation.public_gold.staged_event.context_experiment.panel import (
    CONTROL_IDS,
    DEPENDENCY_CONTEXT_IDS,
    PANEL_IDS,
    REPAIR_TARGET_IDS,
    WRONG_EVENT_TYPE_IDS,
    _participant_map,
    _sentence_spans,
)

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

    assert "occurrence ids" in prompts[prompt_names[0]].lower()
    assert "entire reduction event is cause" in prompts[prompt_names[1]].lower()
    assert "not necessarily speculative" in prompts[prompt_names[2]].lower()
    assert "one wrong role" in prompts[prompt_names[3]].lower()
    assert "gold e1" not in combined
    assert "9/30" not in combined
    assert "expected event count" not in combined
    assert "numeric confidence" in prompts[prompt_names[3]].lower()
