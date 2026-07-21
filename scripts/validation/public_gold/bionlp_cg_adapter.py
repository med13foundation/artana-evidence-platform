"""Parse BioNLP-ST 2013 Cancer Genetics development annotations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

TEXT_BOUND_FIELD_COUNT = 3


@dataclass(frozen=True, slots=True)
class TextBound:
    annotation_id: str
    annotation_type: str
    start: int
    end: int
    text: str


@dataclass(frozen=True, slots=True)
class EventArgument:
    role: str
    target_id: str


@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    event_type: str
    trigger_id: str
    arguments: tuple[EventArgument, ...]


@dataclass(frozen=True, slots=True)
class Modifier:
    modifier_id: str
    modifier_type: str
    target_id: str


@dataclass(frozen=True, slots=True)
class Document:
    document_id: str
    text: str
    entities: tuple[TextBound, ...]
    triggers: tuple[TextBound, ...]
    events: tuple[Event, ...]
    modifiers: tuple[Modifier, ...]


def load_development_directory(path: Path) -> tuple[Document, ...]:
    """Load only a directory explicitly named devel; test is never accepted."""

    if path.name != "devel":
        raise ValueError("Cancer Genetics adapter accepts the development split only")
    text_files = sorted(path.glob("*.txt"))
    if not text_files:
        raise ValueError("Cancer Genetics development directory contains no documents")
    return tuple(_load_document(text_file) for text_file in text_files)


def _load_document(text_file: Path) -> Document:
    document_id = text_file.stem
    text = text_file.read_text(encoding="utf-8")
    entities, _ = _parse_text_bounds(text_file.with_suffix(".a1"), text)
    triggers, remainder = _parse_text_bounds(text_file.with_suffix(".a2"), text)
    events: list[Event] = []
    modifiers: list[Modifier] = []
    for line in remainder:
        fields = line.split("\t")
        if line.startswith("E"):
            event_id, payload = fields
            parts = payload.split()
            event_type, trigger_id = parts[0].split(":", 1)
            arguments = tuple(EventArgument(*part.split(":", 1)) for part in parts[1:])
            events.append(Event(event_id, event_type, trigger_id, arguments))
        elif line.startswith("M"):
            modifier_id, payload = fields
            modifier_type, target_id = payload.split()
            modifiers.append(Modifier(modifier_id, modifier_type, target_id))
    _validate_references(entities, triggers, events, modifiers)
    return Document(
        document_id=document_id,
        text=text,
        entities=entities,
        triggers=triggers,
        events=tuple(events),
        modifiers=tuple(modifiers),
    )


def _parse_text_bounds(
    path: Path, source: str
) -> tuple[tuple[TextBound, ...], tuple[str, ...]]:
    text_bounds: list[TextBound] = []
    remainder: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("*"):
            continue
        if not line.startswith("T"):
            remainder.append(line)
            continue
        annotation_id, span, annotation_text = line.split("\t")
        span_parts = span.split()
        if len(span_parts) != TEXT_BOUND_FIELD_COUNT:
            raise ValueError("discontinuous Cancer Genetics spans are unsupported")
        annotation_type, start_text, end_text = span_parts
        start, end = int(start_text), int(end_text)
        if source[start:end] != annotation_text:
            raise ValueError(f"Cancer Genetics offset mismatch: {annotation_id}")
        text_bounds.append(
            TextBound(annotation_id, annotation_type, start, end, annotation_text)
        )
    return tuple(text_bounds), tuple(remainder)


def _validate_references(
    entities: tuple[TextBound, ...],
    triggers: tuple[TextBound, ...],
    events: list[Event],
    modifiers: list[Modifier],
) -> None:
    text_ids = {item.annotation_id for item in (*entities, *triggers)}
    event_ids = {event.event_id for event in events}
    for event in events:
        if event.trigger_id not in text_ids:
            raise ValueError(f"unknown Cancer Genetics trigger: {event.trigger_id}")
        for argument in event.arguments:
            if argument.target_id not in text_ids | event_ids:
                raise ValueError(
                    f"unknown Cancer Genetics argument: {argument.target_id}"
                )
    for modifier in modifiers:
        if modifier.target_id not in event_ids:
            raise ValueError(
                f"unknown Cancer Genetics modifier target: {modifier.target_id}"
            )


__all__ = [
    "Document",
    "Event",
    "EventArgument",
    "Modifier",
    "TextBound",
    "load_development_directory",
]
