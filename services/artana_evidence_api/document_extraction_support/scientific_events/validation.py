"""Deterministic structural validation for scientific event graphs."""

from __future__ import annotations

import hashlib
import json
from typing import Protocol, TypeVar

from artana_evidence_api.document_extraction_support.scientific_events.contracts import (
    EventArgumentTarget,
    MentionKind,
    ScientificEvent,
    ScientificEventDocument,
    SourceOffsetSpan,
)


class ScientificEventValidationError(ValueError):
    """The event graph violates source custody or structural consistency."""


def validate_scientific_event_document(document: ScientificEventDocument) -> None:
    """Validate provenance, offsets, references, and acyclic event structure."""

    actual_source_hash = hashlib.sha256(document.source_text.encode()).hexdigest()
    if document.source_sha256 != actual_source_hash:
        raise ScientificEventValidationError("source hash does not match source text")

    mentions = _unique_by_id(document.mentions, "mention")
    events = _unique_by_id(document.events, "event")
    modifier_ids: set[str] = set()

    for mention in document.mentions:
        _validate_span(document.source_text, mention.span)
    for event in document.events:
        _validate_lineage(document, event)
        trigger = mentions.get(event.trigger_id)
        if trigger is None or trigger.mention_kind is not MentionKind.TRIGGER:
            raise ScientificEventValidationError(
                f"event {event.annotation_id} has an invalid trigger reference"
            )
        for argument in event.arguments:
            targets = (
                mentions
                if argument.target_kind is EventArgumentTarget.PARTICIPANT
                else events
            )
            if argument.target_id not in targets:
                raise ScientificEventValidationError(
                    f"event {event.annotation_id} has unresolved {argument.target_kind.value.lower()} reference {argument.target_id}"
                )
        for modifier in event.modifiers:
            if modifier.annotation_id in modifier_ids:
                raise ScientificEventValidationError(
                    f"duplicate modifier annotation id: {modifier.annotation_id}"
                )
            modifier_ids.add(modifier.annotation_id)
    _reject_event_cycles(document)


def resolve_unique_span(source_text: str, exact_text: str) -> SourceOffsetSpan:
    """Resolve one unambiguous exact mention without guessing an occurrence."""

    first = source_text.find(exact_text)
    if first < 0:
        raise ScientificEventValidationError("exact text is absent from source")
    if source_text.find(exact_text, first + 1) >= 0:
        raise ScientificEventValidationError("exact text has ambiguous source offsets")
    return SourceOffsetSpan(
        start=first, end=first + len(exact_text), exact_text=exact_text
    )


def canonical_document_sha256(document: ScientificEventDocument) -> str:
    """Hash a deterministic serialization without changing tuple order."""

    payload = document.model_dump(mode="json")
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_span(source_text: str, span: SourceOffsetSpan) -> None:
    if span.end > len(source_text):
        raise ScientificEventValidationError("source span exceeds document bounds")
    if source_text[span.start : span.end] != span.exact_text:
        raise ScientificEventValidationError(
            "source span offsets do not match exact text"
        )


class _HasAnnotationId(Protocol):
    annotation_id: str


_IdentityT = TypeVar("_IdentityT", bound=_HasAnnotationId)


def _unique_by_id(items: tuple[_IdentityT, ...], label: str) -> dict[str, _IdentityT]:
    indexed: dict[str, _IdentityT] = {}
    for item in items:
        annotation_id = item.annotation_id
        if annotation_id in indexed:
            raise ScientificEventValidationError(
                f"duplicate {label} annotation id: {annotation_id}"
            )
        indexed[annotation_id] = item
    return indexed


def _validate_lineage(
    document: ScientificEventDocument, event: ScientificEvent
) -> None:
    event_id = event.annotation_id
    lineage = event.lineage
    if lineage.document_id != document.document_id:
        raise ScientificEventValidationError(
            f"event {event_id} lineage document mismatch"
        )
    if lineage.source_sha256 != document.source_sha256:
        raise ScientificEventValidationError(
            f"event {event_id} lineage source mismatch"
        )
    if lineage.annotation_id != event_id:
        raise ScientificEventValidationError(
            f"event {event_id} lineage identity mismatch"
        )
    if lineage.schema_version != document.schema_version:
        raise ScientificEventValidationError(
            f"event {event_id} lineage schema mismatch"
        )


def _reject_event_cycles(document: ScientificEventDocument) -> None:
    edges = {
        event.annotation_id: tuple(
            argument.target_id
            for argument in event.arguments
            if argument.target_kind is EventArgumentTarget.EVENT
        )
        for event in document.events
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(event_id: str) -> None:
        if event_id in visiting:
            raise ScientificEventValidationError("cyclic scientific event references")
        if event_id in visited:
            return
        visiting.add(event_id)
        for target_id in edges[event_id]:
            visit(target_id)
        visiting.remove(event_id)
        visited.add(event_id)

    for event_id in edges:
        visit(event_id)


__all__ = [
    "ScientificEventValidationError",
    "canonical_document_sha256",
    "resolve_unique_span",
    "validate_scientific_event_document",
]
