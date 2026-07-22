from __future__ import annotations

import hashlib
import json

import pytest
from pydantic import ValidationError

from scripts.validation.public_gold.lossless_event_experiment_contracts import (
    ExtractedArgument,
    ExtractedEvent,
    ExtractedMention,
    ExtractedModifier,
    ExtractionProvenance,
    ScientificEventExtraction,
    SourceEventType,
    assemble_scientific_event_document,
    build_provider_input,
)


def _extraction() -> ScientificEventExtraction:
    return ScientificEventExtraction(
        status="EXTRACTED",
        mentions=(
            ExtractedMention(
                annotation_id="T1",
                source_type="Cell",
                mention_kind="ENTITY",
                start=0,
                end=5,
                exact_text="Cells",
            ),
            ExtractedMention(
                annotation_id="T2",
                source_type="Growth",
                mention_kind="TRIGGER",
                start=6,
                end=10,
                exact_text="grow",
            ),
        ),
        events=(
            ExtractedEvent(
                annotation_id="E1",
                source_event_type=SourceEventType.GROWTH,
                artana_event_family=None,
                trigger_id="T2",
                arguments=(
                    ExtractedArgument(
                        source_role="Theme",
                        target_kind="PARTICIPANT",
                        target_id="T1",
                    ),
                ),
                modifiers=(
                    ExtractedModifier(
                        annotation_id="M1", source_modifier_type="Speculation"
                    ),
                ),
            ),
        ),
        abstention_reason=None,
    )


def test_agent_output_assembles_without_relabeling_semantics() -> None:
    source = "Cells grow"
    document = assemble_scientific_event_document(
        _extraction(),
        document_id="PMID-1",
        source_text=source,
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        provenance=ExtractionProvenance(producer_identity="openai:gpt-5.6-sol"),
    )

    assert document.events[0].source_event_type == "Growth"
    assert document.events[0].arguments[0].source_role == "Theme"
    assert document.events[0].modifiers[0].source_modifier_type == "Speculation"
    assert document.events[0].lineage.producer_type == "AGENT_EXTRACTION"


def test_assembly_rejects_invalid_offsets_and_references() -> None:
    extraction = _extraction().model_copy(
        update={
            "mentions": (
                _extraction().mentions[0].model_copy(update={"exact_text": "Wrong"}),
                _extraction().mentions[1],
            )
        }
    )

    with pytest.raises(ValueError, match="offsets do not match"):
        assemble_scientific_event_document(
            extraction,
            document_id="PMID-1",
            source_text="Cells grow",
            source_sha256=hashlib.sha256(b"Cells grow").hexdigest(),
            provenance=ExtractionProvenance(producer_identity="openai:gpt-5.6-sol"),
        )


def test_status_contract_prevents_partial_abstention() -> None:
    payload = _extraction().model_dump(mode="json")
    payload.update(status="ABSTAIN", abstention_reason="uncertain")

    with pytest.raises(ValidationError, match="ABSTAIN"):
        ScientificEventExtraction.model_validate_json(json.dumps(payload))


def test_provider_input_contains_only_prompt_and_source_binding() -> None:
    provider_input = build_provider_input(
        prompt="generic prompt",
        document_id="PMID-1",
        source_sha256="a" * 64,
        source_text="visible abstract",
    )

    assert "generic prompt" in provider_input
    assert "visible abstract" in provider_input
    assert "GOLD_TRIGGER_SENTINEL" not in provider_input
    assert ".a1" not in provider_input
    assert ".a2" not in provider_input
