"""Provider output and deterministic assembly for the lossless event experiment."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Literal

from artana_evidence_api.document_extraction_support.claim_frames.event_types import (
    ClaimEventType,  # noqa: TC002 - required at runtime by Pydantic
)
from artana_evidence_api.document_extraction_support.scientific_events import (
    EventArgumentTarget,
    MentionKind,
    ScientificEvent,
    ScientificEventArgument,
    ScientificEventDocument,
    ScientificEventLineage,
    ScientificEventMention,
    ScientificEventModifier,
    SourceOffsetSpan,
    validate_scientific_event_document,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "artana.scientific_event_graph.v1"
CORPUS_NAME = "BioNLP-ST 2013 Cancer Genetics"
CORPUS_VERSION = "1.0.0"


class SourceEventType(str, Enum):
    """Frozen source categories exposed to the extraction agent."""

    ACETYLATION = "Acetylation"
    AMINO_ACID_CATABOLISM = "Amino_acid_catabolism"
    BINDING = "Binding"
    BLOOD_VESSEL_DEVELOPMENT = "Blood_vessel_development"
    BREAKDOWN = "Breakdown"
    CARCINOGENESIS = "Carcinogenesis"
    CATABOLISM = "Catabolism"
    CELL_DEATH = "Cell_death"
    CELL_DIFFERENTIATION = "Cell_differentiation"
    CELL_DIVISION = "Cell_division"
    CELL_PROLIFERATION = "Cell_proliferation"
    CELL_TRANSFORMATION = "Cell_transformation"
    DNA_METHYLATION = "DNA_methylation"
    DEATH = "Death"
    DEPHOSPHORYLATION = "Dephosphorylation"
    DEVELOPMENT = "Development"
    DISSOCIATION = "Dissociation"
    GENE_EXPRESSION = "Gene_expression"
    GLYCOLYSIS = "Glycolysis"
    GROWTH = "Growth"
    INFECTION = "Infection"
    LOCALIZATION = "Localization"
    METABOLISM = "Metabolism"
    METASTASIS = "Metastasis"
    MUTATION = "Mutation"
    NEGATIVE_REGULATION = "Negative_regulation"
    PATHWAY = "Pathway"
    PHOSPHORYLATION = "Phosphorylation"
    PLANNED_PROCESS = "Planned_process"
    POSITIVE_REGULATION = "Positive_regulation"
    PROTEIN_PROCESSING = "Protein_processing"
    REGULATION = "Regulation"
    REMODELING = "Remodeling"
    SYNTHESIS = "Synthesis"
    TRANSCRIPTION = "Transcription"
    TRANSLATION = "Translation"
    UBIQUITINATION = "Ubiquitination"


class ExtractedMention(BaseModel):
    """One agent-owned source mention with exact offsets."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    annotation_id: str = Field(..., min_length=1, max_length=256)
    source_type: str = Field(..., min_length=1, max_length=256)
    mention_kind: MentionKind = Field(..., strict=False)
    start: int = Field(..., ge=0)
    end: int = Field(..., ge=1)
    exact_text: str = Field(..., min_length=1, max_length=12000)


class ExtractedArgument(BaseModel):
    """One agent-owned role and typed target reference."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    source_role: str = Field(..., min_length=1, max_length=256)
    target_kind: EventArgumentTarget = Field(..., strict=False)
    target_id: str = Field(..., min_length=1, max_length=256)


class ExtractedModifier(BaseModel):
    """One agent-owned event-local negation or speculation label."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    annotation_id: str = Field(..., min_length=1, max_length=256)
    source_modifier_type: Literal["Negation", "Speculation"]


class ExtractedEvent(BaseModel):
    """One agent-owned scientific event before deterministic custody assembly."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    annotation_id: str = Field(..., min_length=1, max_length=256)
    source_event_type: SourceEventType = Field(..., strict=False)
    artana_event_family: ClaimEventType | None = Field(..., strict=False)
    trigger_id: str = Field(..., min_length=1, max_length=256)
    arguments: tuple[ExtractedArgument, ...] = Field(..., max_length=64)
    modifiers: tuple[ExtractedModifier, ...] = Field(..., max_length=32)


class ScientificEventExtraction(BaseModel):
    """Strict structured output returned by the single provider call."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    status: Literal["EXTRACTED", "ABSTAIN"]
    mentions: tuple[ExtractedMention, ...]
    events: tuple[ExtractedEvent, ...]
    abstention_reason: str | None = Field(..., max_length=2000)

    @model_validator(mode="after")
    def validate_status(self) -> ScientificEventExtraction:
        if self.status == "ABSTAIN":
            if self.events or self.mentions or not self.abstention_reason:
                raise ValueError("ABSTAIN requires a reason and no extracted content")
        elif self.abstention_reason is not None:
            raise ValueError("EXTRACTED cannot include an abstention reason")
        return self


def build_provider_input(
    *,
    prompt: str,
    document_id: str,
    source_sha256: str,
    source_text: str,
) -> str:
    """Bind the frozen generic prompt to one source without annotation metadata."""

    return (
        f"{prompt.rstrip()}\n\n"
        "# Frozen execution input\n\n"
        f"Document ID: `{document_id}`\n"
        f"Source SHA-256: `{source_sha256}`\n\n"
        "## Abstract\n\n"
        f"{source_text}"
    )


def assemble_scientific_event_document(
    extraction: ScientificEventExtraction,
    *,
    document_id: str,
    source_text: str,
    source_sha256: str,
    producer_identity: str,
) -> ScientificEventDocument:
    """Add immutable custody fields without changing agent semantic decisions."""

    extraction_hash = _canonical_sha256(extraction.model_dump(mode="json"))
    document = ScientificEventDocument(
        schema_version=SCHEMA_VERSION,
        document_id=document_id,
        source_text=source_text,
        source_sha256=source_sha256,
        mentions=tuple(
            ScientificEventMention(
                annotation_id=mention.annotation_id,
                source_type=mention.source_type,
                mention_kind=mention.mention_kind,
                span=SourceOffsetSpan(
                    start=mention.start,
                    end=mention.end,
                    exact_text=mention.exact_text,
                ),
            )
            for mention in extraction.mentions
        ),
        events=tuple(
            ScientificEvent(
                annotation_id=event.annotation_id,
                source_event_type=event.source_event_type.value,
                artana_event_family=event.artana_event_family,
                trigger_id=event.trigger_id,
                arguments=tuple(
                    ScientificEventArgument(
                        source_role=argument.source_role,
                        target_kind=argument.target_kind,
                        target_id=argument.target_id,
                    )
                    for argument in event.arguments
                ),
                modifiers=tuple(
                    ScientificEventModifier(
                        annotation_id=modifier.annotation_id,
                        source_modifier_type=modifier.source_modifier_type,
                    )
                    for modifier in event.modifiers
                ),
                lineage=ScientificEventLineage(
                    corpus_name=CORPUS_NAME,
                    corpus_version=CORPUS_VERSION,
                    split="development",
                    document_id=document_id,
                    source_sha256=source_sha256,
                    annotation_source_sha256=extraction_hash,
                    annotation_id=event.annotation_id,
                    producer_type="AGENT_EXTRACTION",
                    producer_identity=producer_identity,
                    schema_version=SCHEMA_VERSION,
                ),
            )
            for event in extraction.events
        ),
    )
    validate_scientific_event_document(document)
    return document


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "ExtractedArgument",
    "ExtractedEvent",
    "ExtractedMention",
    "ExtractedModifier",
    "ScientificEventExtraction",
    "SourceEventType",
    "assemble_scientific_event_document",
    "build_provider_input",
]
