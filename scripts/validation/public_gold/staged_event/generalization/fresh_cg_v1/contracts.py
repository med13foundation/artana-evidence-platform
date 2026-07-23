"""Frozen contracts for mechanical fresh-CG holdout selection."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from scripts.validation.public_gold.staged_event.contracts import StrictStageModel

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
ArtanaEventType = Literal[
    "REGULATION",
    "POSITIVE_REGULATION",
    "NEGATIVE_REGULATION",
    "GENE_EXPRESSION",
]
ArtanaEntityType = Literal["CANCER", "SIMPLE_CHEMICAL", "GENE_OR_PROTEIN"]
RESERVE_DOCUMENT_COUNT = 12


class ExactSourceSpan(StrictStageModel):
    """One exact half-open span in the frozen UTF-8 source text."""

    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_span_length(self) -> ExactSourceSpan:
        if self.end <= self.start:
            raise ValueError("source span end must be greater than start")
        if self.end - self.start != len(self.text):
            raise ValueError("source span offsets must match text length")
        return self


class DirectCGArgument(StrictStageModel):
    """One unmodified Theme/Cause edge from the public CG annotation."""

    source_role: str = Field(pattern=r"^(Theme|Cause)\d*$")
    target_annotation_id: str = Field(pattern=r"^T\d+$")


class DirectCGEvent(StrictStageModel):
    """Selected public-CG event and its direct entity arguments."""

    event_id: str = Field(pattern=r"^E\d+$")
    source_event_type: str = Field(min_length=1)
    artana_event_type: ArtanaEventType
    trigger_annotation_id: str = Field(pattern=r"^T\d+$")
    trigger: ExactSourceSpan
    arguments: tuple[DirectCGArgument, ...] = Field(min_length=1)


class DirectCGParticipant(StrictStageModel):
    """Selected public-CG entity occurrence without semantic reinterpretation."""

    annotation_id: str = Field(pattern=r"^T\d+$")
    source_entity_type: str = Field(min_length=1)
    artana_entity_type: ArtanaEntityType
    mention: ExactSourceSpan


class ConsideredEvent(StrictStageModel):
    """Deterministic eligibility decision for an event considered in order."""

    event_id: str = Field(pattern=r"^E\d+$")
    trigger_start: int = Field(ge=0)
    disposition: Literal["INELIGIBLE", "SELECTED"]
    reasons: tuple[str, ...]

    @model_validator(mode="after")
    def validate_reasons(self) -> ConsideredEvent:
        if self.disposition == "INELIGIBLE" and not self.reasons:
            raise ValueError("ineligible events require explicit reasons")
        if self.disposition == "SELECTED" and self.reasons != ("FIRST_ELIGIBLE",):
            raise ValueError("selected event must record FIRST_ELIGIBLE")
        return self


class FreshCGCase(StrictStageModel):
    """Self-contained source bytes and exact direct-CG reference for one case."""

    case_id: str = Field(min_length=1)
    case_order: int = Field(ge=1, le=8)
    document_id: str = Field(pattern=r"^PMID-\d+$")
    source_encoding: Literal["utf-8"] = "utf-8"
    source_text: str = Field(min_length=1)
    source_bytes_base64: str = Field(min_length=1)
    source_sha256: Sha256
    a1_sha256: Sha256
    a2_sha256: Sha256
    annotation_source_sha256: Sha256
    permitted_context: ExactSourceSpan
    event: DirectCGEvent
    participants: tuple[DirectCGParticipant, ...] = Field(min_length=1)
    considered_events: tuple[ConsideredEvent, ...] = Field(min_length=1)
    selection_reason: Literal[
        "FIRST_OFFSET_ORDER_EVENT_MEETING_ALL_FROZEN_ELIGIBILITY_RULES"
    ]
    direct_cg_reference_sha256: Sha256


class SkippedDocument(StrictStageModel):
    """Reserved document with no event satisfying the frozen rules."""

    document_id: str = Field(pattern=r"^PMID-\d+$")
    reason: Literal["NO_ELIGIBLE_EVENT"]
    considered_events: tuple[ConsideredEvent, ...] = Field(min_length=1)


class FreshCGSelection(StrictStageModel):
    """Create-once eight-case selection from the ordered twelve-document reserve."""

    schema_version: Literal[
        "artana.staged_generalization.fresh_cg_selection.v1"
    ] = "artana.staged_generalization.fresh_cg_selection.v1"
    selection_policy_version: Literal[
        "artana.staged_generalization.fresh_cg_selection_policy.v1"
    ] = "artana.staged_generalization.fresh_cg_selection_policy.v1"
    reserve_order: tuple[str, ...] = Field(min_length=12, max_length=12)
    selected_document_ids: tuple[str, ...] = Field(min_length=8, max_length=8)
    unused_document_ids: tuple[str, ...] = Field(min_length=4, max_length=4)
    skipped_documents: tuple[SkippedDocument, ...]
    cases: tuple[FreshCGCase, ...] = Field(min_length=8, max_length=8)
    provider_packet_excludes: tuple[str, ...]
    model_outputs_used_for_selection: Literal[False] = False
    unresolved_coreference_rule: Literal[
        "DIRECT_TEXT_BOUND_CORE_ARGUMENTS_WITH_NO_PRONOMINAL_MENTIONS"
    ] = "DIRECT_TEXT_BOUND_CORE_ARGUMENTS_WITH_NO_PRONOMINAL_MENTIONS"

    @model_validator(mode="after")
    def validate_partition_and_order(self) -> FreshCGSelection:
        if len(set(self.reserve_order)) != RESERVE_DOCUMENT_COUNT:
            raise ValueError("reserve document IDs must be unique")
        selected = tuple(case.document_id for case in self.cases)
        if selected != self.selected_document_ids:
            raise ValueError("selected document order differs from case order")
        if tuple(case.case_order for case in self.cases) != tuple(range(1, 9)):
            raise ValueError("fresh case order must be exactly one through eight")
        if set(self.selected_document_ids) & set(self.unused_document_ids):
            raise ValueError("selected and unused document IDs overlap")
        if set(self.selected_document_ids) | set(self.unused_document_ids) != set(
            self.reserve_order
        ):
            raise ValueError("selected and unused IDs must partition the reserve")
        selected_positions = tuple(
            self.reserve_order.index(document_id)
            for document_id in self.selected_document_ids
        )
        if selected_positions != tuple(sorted(selected_positions)):
            raise ValueError("fresh cases changed the frozen reserve order")
        return self


__all__ = [
    "ArtanaEntityType",
    "ArtanaEventType",
    "ConsideredEvent",
    "DirectCGArgument",
    "DirectCGEvent",
    "DirectCGParticipant",
    "ExactSourceSpan",
    "FreshCGCase",
    "FreshCGSelection",
    "Sha256",
    "SkippedDocument",
]
