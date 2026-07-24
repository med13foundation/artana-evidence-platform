from __future__ import annotations

import hashlib

import pytest
from artana_evidence_api.document_extraction_support.scientific_events import (
    EventArgumentTarget,
    MentionKind,
    ScientificEvent,
    ScientificEventArgument,
    ScientificEventDocument,
    ScientificEventLineage,
    ScientificEventMention,
    ScientificEventModifier,
    ScientificEventValidationError,
    SourceOffsetSpan,
    canonical_document_sha256,
    resolve_unique_span,
    validate_scientific_event_document,
)

SOURCE = "Drug inhibits growth and may suppress invasion."
SOURCE_HASH = hashlib.sha256(SOURCE.encode()).hexdigest()
ANNOTATION_HASH = "a" * 64
SCHEMA = "artana.scientific_event_graph.test"


def _mention(
    annotation_id: str,
    source_type: str,
    exact_text: str,
    *,
    kind: MentionKind,
) -> ScientificEventMention:
    start = SOURCE.index(exact_text)
    return ScientificEventMention(
        annotation_id=annotation_id,
        source_type=source_type,
        mention_kind=kind,
        span=SourceOffsetSpan(
            start=start,
            end=start + len(exact_text),
            exact_text=exact_text,
        ),
    )


def _lineage(event_id: str) -> ScientificEventLineage:
    return ScientificEventLineage(
        corpus_name="fixture",
        corpus_version="1",
        split="development",
        document_id="doc",
        source_sha256=SOURCE_HASH,
        annotation_source_sha256=ANNOTATION_HASH,
        annotation_id=event_id,
        producer_type="PUBLIC_GOLD_DETERMINISTIC_IMPORT",
        producer_identity="test",
        schema_version=SCHEMA,
    )


def _event(
    event_id: str,
    event_type: str,
    trigger_id: str,
    arguments: tuple[ScientificEventArgument, ...] = (),
    modifiers: tuple[ScientificEventModifier, ...] = (),
) -> ScientificEvent:
    return ScientificEvent(
        annotation_id=event_id,
        source_event_type=event_type,
        artana_event_family=None,
        trigger_id=trigger_id,
        arguments=arguments,
        modifiers=modifiers,
        lineage=_lineage(event_id),
    )


def _document(events: tuple[ScientificEvent, ...]) -> ScientificEventDocument:
    return ScientificEventDocument(
        schema_version=SCHEMA,
        document_id="doc",
        source_text=SOURCE,
        source_sha256=SOURCE_HASH,
        mentions=(
            _mention("T1", "Chemical", "Drug", kind=MentionKind.ENTITY),
            _mention("T2", "Negative_regulation", "inhibits", kind=MentionKind.TRIGGER),
            _mention("T3", "Growth", "growth", kind=MentionKind.TRIGGER),
            _mention("T4", "Invasion", "invasion", kind=MentionKind.ENTITY),
            _mention("T5", "Negative_regulation", "suppress", kind=MentionKind.TRIGGER),
        ),
        events=events,
    )


def test_preserves_unary_nested_repeated_roles_and_modifiers() -> None:
    unary = _event("E1", "Growth", "T3")
    outer = _event(
        "E2",
        "Source_category_not_in_Artana",
        "T2",
        (
            ScientificEventArgument(
                source_role="Theme",
                target_kind=EventArgumentTarget.EVENT,
                target_id="E1",
            ),
            ScientificEventArgument(
                source_role="Cause",
                target_kind=EventArgumentTarget.PARTICIPANT,
                target_id="T1",
            ),
            ScientificEventArgument(
                source_role="Theme2",
                target_kind=EventArgumentTarget.PARTICIPANT,
                target_id="T4",
            ),
        ),
        (
            ScientificEventModifier(
                annotation_id="M1", source_modifier_type="Negation"
            ),
            ScientificEventModifier(
                annotation_id="M2", source_modifier_type="Speculation"
            ),
        ),
    )
    document = _document((unary, outer))

    validate_scientific_event_document(document)

    assert document.events[0].arguments == ()
    assert document.events[1].source_event_type == "Source_category_not_in_Artana"
    assert document.events[1].artana_event_family is None
    assert tuple(argument.source_role for argument in document.events[1].arguments) == (
        "Theme",
        "Cause",
        "Theme2",
    )
    assert tuple(argument.target_id for argument in document.events[1].arguments) == (
        "E1",
        "T1",
        "T4",
    )


def test_rejects_missing_references_and_cycles() -> None:
    missing = _event(
        "E1",
        "Growth",
        "T3",
        (
            ScientificEventArgument(
                source_role="Theme",
                target_kind=EventArgumentTarget.EVENT,
                target_id="E404",
            ),
        ),
    )
    with pytest.raises(ScientificEventValidationError, match="unresolved event"):
        validate_scientific_event_document(_document((missing,)))

    first = _event(
        "E1",
        "Growth",
        "T3",
        (
            ScientificEventArgument(
                source_role="Theme",
                target_kind=EventArgumentTarget.EVENT,
                target_id="E2",
            ),
        ),
    )
    second = _event(
        "E2",
        "Regulation",
        "T2",
        (
            ScientificEventArgument(
                source_role="Theme",
                target_kind=EventArgumentTarget.EVENT,
                target_id="E1",
            ),
        ),
    )
    with pytest.raises(ScientificEventValidationError, match="cyclic"):
        validate_scientific_event_document(_document((first, second)))


def test_rejects_invalid_offsets_and_ambiguous_resolution() -> None:
    mention = _mention("T1", "Chemical", "Drug", kind=MentionKind.ENTITY)
    invalid = mention.model_copy(
        update={"span": SourceOffsetSpan(start=1, end=5, exact_text="Drug")}
    )
    document = _document((_event("E1", "Growth", "T3"),)).model_copy(
        update={"mentions": (invalid,)}
    )
    with pytest.raises(ScientificEventValidationError, match="do not match"):
        validate_scientific_event_document(document)

    with pytest.raises(ScientificEventValidationError, match="ambiguous"):
        resolve_unique_span("BRAF and BRAF", "BRAF")


def test_serialization_and_hash_are_deterministic() -> None:
    document = _document((_event("E1", "Growth", "T3"),))

    first = canonical_document_sha256(document)
    restored = ScientificEventDocument.model_validate_json(document.model_dump_json())

    assert canonical_document_sha256(restored) == first
