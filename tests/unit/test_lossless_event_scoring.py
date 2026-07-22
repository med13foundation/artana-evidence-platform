from __future__ import annotations

import hashlib

from scripts.validation.public_gold.lossless_event_experiment_contracts import (
    ExtractedArgument,
    ExtractedEvent,
    ExtractedMention,
    ExtractedModifier,
    ExtractionProvenance,
    ScientificEventExtraction,
    SourceEventType,
    assemble_scientific_event_document,
)
from scripts.validation.public_gold.lossless_event_scoring import (
    score_scientific_event_document,
)


def _document(*, id_prefix: str, nested_role: str = "Cause"):
    source = "Cells grow and divide"
    extraction = ScientificEventExtraction(
        status="EXTRACTED",
        mentions=(
            ExtractedMention(
                annotation_id=f"{id_prefix}1",
                source_type="Cell",
                mention_kind="ENTITY",
                start=0,
                end=5,
                exact_text="Cells",
            ),
            ExtractedMention(
                annotation_id=f"{id_prefix}2",
                source_type="Growth",
                mention_kind="TRIGGER",
                start=6,
                end=10,
                exact_text="grow",
            ),
            ExtractedMention(
                annotation_id=f"{id_prefix}3",
                source_type="Cell_division",
                mention_kind="TRIGGER",
                start=15,
                end=21,
                exact_text="divide",
            ),
        ),
        events=(
            ExtractedEvent(
                annotation_id=f"{id_prefix}4",
                source_event_type=SourceEventType.GROWTH,
                artana_event_family=None,
                trigger_id=f"{id_prefix}2",
                arguments=(
                    ExtractedArgument(
                        source_role="Theme",
                        target_kind="PARTICIPANT",
                        target_id=f"{id_prefix}1",
                    ),
                ),
                modifiers=(),
            ),
            ExtractedEvent(
                annotation_id=f"{id_prefix}5",
                source_event_type=SourceEventType.CELL_DIVISION,
                artana_event_family=None,
                trigger_id=f"{id_prefix}3",
                arguments=(
                    ExtractedArgument(
                        source_role=nested_role,
                        target_kind="EVENT",
                        target_id=f"{id_prefix}4",
                    ),
                ),
                modifiers=(
                    ExtractedModifier(
                        annotation_id=f"{id_prefix}6",
                        source_modifier_type="Negation",
                    ),
                ),
            ),
        ),
        abstention_reason=None,
    )
    return assemble_scientific_event_document(
        extraction,
        document_id="PMID-1",
        source_text=source,
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        provenance=ExtractionProvenance(producer_identity="test"),
    )


def test_exact_scoring_ignores_local_annotation_identifiers() -> None:
    score = score_scientific_event_document(
        gold=_document(id_prefix="G"), predicted=_document(id_prefix="P")
    )

    assert score.scientific_gate_passed
    assert score.complete_events.matched == 2
    assert score.nested_arguments.matched == 1
    assert score.modifiers.matched == 1


def test_scoring_identifies_nested_role_mismatch_without_false_pass() -> None:
    score = score_scientific_event_document(
        gold=_document(id_prefix="G"),
        predicted=_document(id_prefix="P", nested_role="Theme"),
    )

    assert not score.scientific_gate_passed
    assert score.complete_events.matched == 1
    assert score.nested_arguments.matched == 0
    assert score.unsupported_or_invented_events == 1
    assert {item.category for item in score.mismatches} == {
        "MISSING_GOLD_EVENT",
        "UNMATCHED_PREDICTED_EVENT",
    }
