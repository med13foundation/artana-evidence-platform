"""Immutable contracts for lossless source-bound scientific event graphs."""

from __future__ import annotations

from enum import Enum

from artana_evidence_api.document_extraction_support.claim_frames.event_types import (
    ClaimEventType,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator


class MentionKind(str, Enum):
    """Structural kind of one source annotation."""

    ENTITY = "ENTITY"
    TRIGGER = "TRIGGER"


class EventArgumentTarget(str, Enum):
    """Whether an argument points to source text or another event."""

    PARTICIPANT = "PARTICIPANT"
    EVENT = "EVENT"


class SourceOffsetSpan(BaseModel):
    """Exact source text with half-open character offsets."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    start: int = Field(..., ge=0)
    end: int = Field(..., ge=1)
    exact_text: str = Field(..., min_length=1, max_length=12000)

    @model_validator(mode="after")
    def validate_order(self) -> SourceOffsetSpan:
        if self.end <= self.start:
            raise ValueError("source span end must be greater than start")
        return self


class ScientificEventMention(BaseModel):
    """One entity or trigger copied from the source annotation."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    annotation_id: str = Field(..., min_length=1, max_length=256)
    source_type: str = Field(..., min_length=1, max_length=256)
    mention_kind: MentionKind = Field(..., strict=False)
    span: SourceOffsetSpan


class ScientificEventArgument(BaseModel):
    """One verbatim source role and its typed annotation reference."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    source_role: str = Field(..., min_length=1, max_length=256)
    target_kind: EventArgumentTarget = Field(..., strict=False)
    target_id: str = Field(..., min_length=1, max_length=256)


class ScientificEventModifier(BaseModel):
    """One event-local modifier such as source negation or speculation."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    annotation_id: str = Field(..., min_length=1, max_length=256)
    source_modifier_type: str = Field(..., min_length=1, max_length=256)


class ScientificEventLineage(BaseModel):
    """Immutable custody binding for one imported or agent-produced event."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    corpus_name: str = Field(..., min_length=1, max_length=256)
    corpus_version: str = Field(..., min_length=1, max_length=256)
    split: str = Field(..., min_length=1, max_length=64)
    document_id: str = Field(..., min_length=1, max_length=256)
    source_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    annotation_source_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    annotation_id: str = Field(..., min_length=1, max_length=256)
    producer_type: str = Field(..., min_length=1, max_length=64)
    producer_identity: str = Field(..., min_length=1, max_length=512)
    schema_version: str = Field(..., min_length=1, max_length=128)


class ScientificEvent(BaseModel):
    """One event without binary flattening or source-label translation."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    annotation_id: str = Field(..., min_length=1, max_length=256)
    source_event_type: str = Field(..., min_length=1, max_length=256)
    artana_event_family: ClaimEventType | None = Field(default=None, strict=False)
    trigger_id: str = Field(..., min_length=1, max_length=256)
    arguments: tuple[ScientificEventArgument, ...] = Field(default=(), max_length=64)
    modifiers: tuple[ScientificEventModifier, ...] = Field(default=(), max_length=32)
    lineage: ScientificEventLineage


class ScientificEventDocument(BaseModel):
    """A complete source document and its lossless event graph."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: str = Field(..., min_length=1, max_length=128)
    document_id: str = Field(..., min_length=1, max_length=256)
    source_text: str = Field(..., min_length=1, max_length=500000)
    source_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    mentions: tuple[ScientificEventMention, ...]
    events: tuple[ScientificEvent, ...]


__all__ = [
    "EventArgumentTarget",
    "MentionKind",
    "ScientificEvent",
    "ScientificEventArgument",
    "ScientificEventDocument",
    "ScientificEventLineage",
    "ScientificEventMention",
    "ScientificEventModifier",
    "SourceOffsetSpan",
]
