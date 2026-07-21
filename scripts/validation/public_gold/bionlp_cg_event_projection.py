"""Losslessly project exposed Cancer Genetics events into Artana's event IR."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

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
    canonical_document_sha256,
    validate_scientific_event_document,
)

from scripts.validation.public_gold.bionlp_cg_adapter import (
    Document,
    Event,
    TextBound,
    load_development_directory,
)

SCHEMA_VERSION = "artana.scientific_event_graph.v1"
CORPUS_NAME = "BioNLP-ST 2013 Cancer Genetics"
CORPUS_VERSION = "1.0.0"
PRODUCER_IDENTITY = "scripts.validation.public_gold.bionlp_cg_event_projection"
EXPECTED_DEVELOPMENT_DOCUMENTS = 100
EXPECTED_DEVELOPMENT_EVENTS = 2915


@dataclass(frozen=True, slots=True)
class _ProjectionContext:
    document: Document
    source_hash: str
    annotation_hash: str
    event_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class LosslessReplayReport:
    documents: int
    events: int
    participant_mentions: int
    triggers: int
    arguments: int
    nested_arguments: int
    modifiers: int
    unresolved_references: int
    unauthorized_semantic_mappings: int
    mismatches: int
    projection_sha256: str

    @property
    def passed(self) -> bool:
        return (
            self.documents == EXPECTED_DEVELOPMENT_DOCUMENTS
            and self.events == EXPECTED_DEVELOPMENT_EVENTS
            and self.unresolved_references == 0
            and self.unauthorized_semantic_mappings == 0
            and self.mismatches == 0
        )


def project_development_directory(
    path: Path,
) -> tuple[ScientificEventDocument, ...]:
    """Project every exposed development document without semantic mapping."""

    source_documents = load_development_directory(path)
    return tuple(_project_document(path, document) for document in source_documents)


def replay_development_directory(path: Path) -> LosslessReplayReport:
    """Project and compare every event field to the original annotations."""

    source_documents = load_development_directory(path)
    projected_documents = tuple(
        _project_document(path, document) for document in source_documents
    )
    mismatches = 0
    for source, projected in zip(source_documents, projected_documents, strict=True):
        mismatches += _count_mismatches(source, projected)
    projection_hash = _projection_sha256(projected_documents)
    return LosslessReplayReport(
        documents=len(projected_documents),
        events=sum(len(document.events) for document in projected_documents),
        participant_mentions=sum(
            mention.mention_kind is MentionKind.ENTITY
            for document in projected_documents
            for mention in document.mentions
        ),
        triggers=sum(
            mention.mention_kind is MentionKind.TRIGGER
            for document in projected_documents
            for mention in document.mentions
        ),
        arguments=sum(
            len(event.arguments)
            for document in projected_documents
            for event in document.events
        ),
        nested_arguments=sum(
            argument.target_kind is EventArgumentTarget.EVENT
            for document in projected_documents
            for event in document.events
            for argument in event.arguments
        ),
        modifiers=sum(
            len(event.modifiers)
            for document in projected_documents
            for event in document.events
        ),
        unresolved_references=0,
        unauthorized_semantic_mappings=sum(
            event.artana_event_family is not None
            for document in projected_documents
            for event in document.events
        ),
        mismatches=mismatches,
        projection_sha256=projection_hash,
    )


def _project_document(path: Path, document: Document) -> ScientificEventDocument:
    source_hash = hashlib.sha256(document.text.encode()).hexdigest()
    annotation_hash = _annotation_source_sha256(path, document.document_id)
    context = _ProjectionContext(
        document=document,
        source_hash=source_hash,
        annotation_hash=annotation_hash,
        event_ids=frozenset(event.event_id for event in document.events),
    )
    modifiers_by_event: dict[str, list[ScientificEventModifier]] = {}
    for modifier in document.modifiers:
        modifiers_by_event.setdefault(modifier.target_id, []).append(
            ScientificEventModifier(
                annotation_id=modifier.modifier_id,
                source_modifier_type=modifier.modifier_type,
            )
        )
    projected = ScientificEventDocument(
        schema_version=SCHEMA_VERSION,
        document_id=document.document_id,
        source_text=document.text,
        source_sha256=source_hash,
        mentions=tuple(
            [_mention(item, MentionKind.ENTITY) for item in document.entities]
            + [_mention(item, MentionKind.TRIGGER) for item in document.triggers]
        ),
        events=tuple(
            _event(
                item,
                context=context,
                modifiers=tuple(modifiers_by_event.get(item.event_id, ())),
            )
            for item in document.events
        ),
    )
    validate_scientific_event_document(projected)
    return projected


def _mention(item: TextBound, kind: MentionKind) -> ScientificEventMention:
    return ScientificEventMention(
        annotation_id=item.annotation_id,
        source_type=item.annotation_type,
        mention_kind=kind,
        span=SourceOffsetSpan(start=item.start, end=item.end, exact_text=item.text),
    )


def _event(
    item: Event,
    *,
    context: _ProjectionContext,
    modifiers: tuple[ScientificEventModifier, ...],
) -> ScientificEvent:
    return ScientificEvent(
        annotation_id=item.event_id,
        source_event_type=item.event_type,
        artana_event_family=None,
        trigger_id=item.trigger_id,
        arguments=tuple(
            ScientificEventArgument(
                source_role=argument.role,
                target_kind=(
                    EventArgumentTarget.EVENT
                    if argument.target_id in context.event_ids
                    else EventArgumentTarget.PARTICIPANT
                ),
                target_id=argument.target_id,
            )
            for argument in item.arguments
        ),
        modifiers=modifiers,
        lineage=ScientificEventLineage(
            corpus_name=CORPUS_NAME,
            corpus_version=CORPUS_VERSION,
            split="development",
            document_id=context.document.document_id,
            source_sha256=context.source_hash,
            annotation_source_sha256=context.annotation_hash,
            annotation_id=item.event_id,
            producer_type="PUBLIC_GOLD_DETERMINISTIC_IMPORT",
            producer_identity=PRODUCER_IDENTITY,
            schema_version=SCHEMA_VERSION,
        ),
    )


def _annotation_source_sha256(path: Path, document_id: str) -> str:
    payload = {
        "a1": (path / f"{document_id}.a1").read_text(encoding="utf-8"),
        "a2": (path / f"{document_id}.a2").read_text(encoding="utf-8"),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _count_mismatches(
    source: Document,
    projected: ScientificEventDocument,
) -> int:
    projected_events = {event.annotation_id: event for event in projected.events}
    projected_mentions = {
        mention.annotation_id: mention for mention in projected.mentions
    }
    source_mentions = (*source.entities, *source.triggers)
    mismatches = abs(len(source_mentions) - len(projected.mentions))
    mismatches += abs(len(source.events) - len(projected.events))
    for mention in source_mentions:
        candidate = projected_mentions.get(mention.annotation_id)
        if candidate is None:
            mismatches += 1
            continue
        actual_mention = (
            candidate.source_type,
            candidate.span.start,
            candidate.span.end,
            candidate.span.exact_text,
        )
        expected_mention = (
            mention.annotation_type,
            mention.start,
            mention.end,
            mention.text,
        )
        mismatches += actual_mention != expected_mention
    for event in source.events:
        candidate = projected_events.get(event.event_id)
        if candidate is None:
            mismatches += 1
            continue
        trigger = projected_mentions[candidate.trigger_id]
        expected_trigger = next(
            item for item in source.triggers if item.annotation_id == event.trigger_id
        )
        expected_modifiers = tuple(
            (item.modifier_id, item.modifier_type)
            for item in source.modifiers
            if item.target_id == event.event_id
        )
        actual = (
            candidate.source_event_type,
            candidate.trigger_id,
            trigger.span.start,
            trigger.span.end,
            trigger.span.exact_text,
            tuple(
                (argument.source_role, argument.target_id)
                for argument in candidate.arguments
            ),
            tuple(
                (modifier.annotation_id, modifier.source_modifier_type)
                for modifier in candidate.modifiers
            ),
        )
        expected = (
            event.event_type,
            event.trigger_id,
            expected_trigger.start,
            expected_trigger.end,
            expected_trigger.text,
            tuple((argument.role, argument.target_id) for argument in event.arguments),
            expected_modifiers,
        )
        mismatches += actual != expected
    return mismatches


def _projection_sha256(documents: tuple[ScientificEventDocument, ...]) -> str:
    hashes = [canonical_document_sha256(document) for document in documents]
    encoded = json.dumps(hashes, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "LosslessReplayReport",
    "project_development_directory",
    "replay_development_directory",
]
