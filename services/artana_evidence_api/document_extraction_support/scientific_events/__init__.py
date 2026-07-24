"""Lossless source-bound scientific event graph contracts."""

from artana_evidence_api.document_extraction_support.scientific_events.contracts import (
    EventArgumentTarget,
    MentionKind,
    ScientificEvent,
    ScientificEventArgument,
    ScientificEventDocument,
    ScientificEventLineage,
    ScientificEventMention,
    ScientificEventModifier,
    SourceOffsetSpan,
)
from artana_evidence_api.document_extraction_support.scientific_events.validation import (
    ScientificEventValidationError,
    canonical_document_sha256,
    resolve_unique_span,
    validate_scientific_event_document,
)

__all__ = [
    "EventArgumentTarget",
    "MentionKind",
    "ScientificEvent",
    "ScientificEventArgument",
    "ScientificEventDocument",
    "ScientificEventLineage",
    "ScientificEventMention",
    "ScientificEventModifier",
    "ScientificEventValidationError",
    "SourceOffsetSpan",
    "canonical_document_sha256",
    "resolve_unique_span",
    "validate_scientific_event_document",
]
