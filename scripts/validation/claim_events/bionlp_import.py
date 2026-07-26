"""Deterministic adapter for expert-authored BioNLP standoff events."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from scripts.validation.claim_events.corpus_text import normalized_characters

_EVENT_TYPE_MAP: Final = {
    "Gene_expression": "EXPRESSION",
    "Transcription": "TRANSCRIPTION",
    "Protein_catabolism": "DEGRADATION",
    "Phosphorylation": "PHOSPHORYLATION",
    "Localization": "LOCALIZATION",
    "Binding": "BINDING",
    "Regulation": "REGULATION",
    "Positive_regulation": "POSITIVE_REGULATION",
    "Negative_regulation": "NEGATIVE_REGULATION",
}
_PARTICIPANT_ROLE_MAP: Final = {
    "Protein": "GENE_OR_PROTEIN",
    "Entity": "OTHER_ENTITY",
}
_EVENT_ROLE_PATTERN: Final = re.compile(r"[0-9]+$")
_MIN_EVENT_ARGUMENTS: Final = 2
_STANDOFF_PAIR_COLUMNS: Final = 2
_TEXT_BOUND_COLUMNS: Final = 3
TG04_BIONLP_ARCHIVE_SHA256: Final = (
    "f70e5f6d6e2a7f7fcdb5c8671715f3909a77662a6238015b2916ce939f2a890f"
)
POLARITY_ADJUDICATION_RECORD: Final = (
    "docs/validation/adjudications/"
    "2026-07-25-tg04-gold-polarity-inheritance-adjudication-v1.json"
)
#: Hand-adjudicated polarity corrections, keyed by (document, event annotation).
#:
#: Every entry is an event whose dropped nested parent carried the negation.
#: Each was read against its own source sentence; the rationale and the two
#: rejected candidates are recorded in `POLARITY_ADJUDICATION_RECORD`.  This is
#: deliberately a table and not a rule -- see `_adjudicated_epistemic_categories`.
#:
#: Each entry used to be annotated with the corpus sentence that justified it.
#: Those quotes were verbatim restricted text and have been removed; the
#: adjudication record holds the reasoning, and the sentence itself can be read
#: at the event's own offsets once the corpus is fetched.
POLARITY_ADJUDICATIONS: Final[dict[tuple[str, str], tuple[str, str]]] = {
    ("PMID-9164948", "E2"): ("REFUTE", "ASSERTED"),
    ("PMID-10402173", "E9"): ("REFUTE", "ASSERTED"),
    ("PMID-10402173", "E10"): ("REFUTE", "ASSERTED"),
    ("PMID-10402173", "E2"): ("REFUTE", "ASSERTED"),
    ("PMC-2222968-05-Results-04", "E8"): ("REFUTE", "ASSERTED"),
    ("PMID-8134378", "E9"): ("REFUTE", "ASSERTED"),
    ("PMID-9234696", "E14"): ("REFUTE", "ASSERTED"),
}
TG04_BIONLP_SOURCE_URL: Final = (
    "https://bionlp-st.dbcls.jp/GE/2011/downloads/"
    "BioNLP-ST_2011_genia_devel_data_rev1.tar.gz"
)
TG04_DEVELOPMENT_DOCUMENT_IDS: Final = (
    "PMC-1134658-15-Methods-06",
    "PMC-2806624-09-Supplementary_Material",
    "PMID-9361029",
    "PMID-10402173",
    "PMC-2222968-03-Results-02",
    "PMID-10090947",
    "PMC-2222968-22-Materials_and_Methods-14",
    "PMC-2222968-09-Materials_and_Methods-01",
    "PMID-8621480",
    "PMC-2222968-05-Results-04",
    "PMC-2806624-05-RESULTS-04",
    "PMC-2222968-15-Materials_and_Methods-07",
    "PMID-10092783",
    "PMC-2222968-40-caption-15",
    "PMC-1920263-21-caption-06",
    "PMID-8098881",
    "PMID-8098618",
    "PMC-1920263-08-MATERIALS_AND_METHODS-07",
    "PMID-8626528",
    "PMC-2222968-34-caption-09",
    "PMID-9802971",
    "PMID-9619918",
    "PMID-8895544",
    "PMC-2222968-06-Results-05",
    "PMID-9164948",
    "PMC-1920263-17-caption-02",
    "PMID-8134378",
    "PMID-9878621",
    "PMID-7749985",
    "PMID-9488049",
    "PMID-10096561",
    "PMID-9796702",
    "PMC-1942070-07-Discussion",
    "PMID-8096091",
    "PMID-9234696",
    "PMID-7605990",
    "PMID-7537762",
    "PMC-1920263-18-caption-03",
    "PMC-1134658-06-Results-05",
    "PMID-8898960",
)


def select_document_ids(root: Path, *, count: int) -> tuple[str, ...]:
    """Select corpus documents by the preregistered content-blind hash order."""

    if count < 1:
        raise ValueError("document selection count must be positive")
    document_ids = tuple(path.stem for path in root.glob("*.txt"))
    if len(document_ids) < count:
        raise ValueError("corpus contains fewer documents than the frozen selection")
    return tuple(
        sorted(
            document_ids,
            key=lambda document_id: (
                hashlib.sha256(document_id.encode("utf-8")).hexdigest(),
                document_id,
            ),
        )[:count],
    )


@dataclass(frozen=True, slots=True)
class TextBoundAnnotation:
    """One exact expert-authored text-bound annotation."""

    annotation_id: str
    annotation_type: str
    start: int
    end: int
    text: str


@dataclass(frozen=True, slots=True)
class EventArgument:
    """One corpus-native event role and annotation reference."""

    role: str
    reference_id: str


@dataclass(frozen=True, slots=True)
class EventAnnotation:
    """One expert-authored event with its trigger and arguments."""

    event_id: str
    event_type: str
    trigger_id: str
    arguments: tuple[EventArgument, ...]


@dataclass(frozen=True, slots=True)
class EventModifier:
    """One expert-authored negation or speculation modifier."""

    annotation_id: str
    modifier_type: str
    event_id: str


@dataclass(frozen=True, slots=True)
class StandoffDocument:
    """Parsed source text and its independent expert annotations."""

    document_id: str
    source_text: str
    text_bounds: dict[str, TextBoundAnnotation]
    events: tuple[EventAnnotation, ...]
    modifiers: tuple[EventModifier, ...]


def load_standoff_document(root: Path, document_id: str) -> StandoffDocument:
    """Load one BioNLP document without interpreting its scientific meaning."""

    raw_source_text = (root / f"{document_id}.txt").read_text(encoding="utf-8")
    primary_lines = _read_lines(root / f"{document_id}.a1")
    event_lines = _read_lines(root / f"{document_id}.a2")
    raw_text_bounds = _parse_text_bounds(
        primary_lines + event_lines,
        raw_source_text,
    )
    source_text, text_bounds = _normalize_text_bounds(
        raw_source_text,
        raw_text_bounds,
    )
    events = _parse_events(event_lines, text_bounds)
    modifiers = _parse_modifiers(event_lines, {event.event_id for event in events})
    return StandoffDocument(
        document_id=document_id,
        source_text=source_text,
        text_bounds=text_bounds,
        events=events,
        modifiers=modifiers,
    )


def _normalize_text_bounds(
    raw_source_text: str,
    raw_text_bounds: dict[str, TextBoundAnnotation],
) -> tuple[str, dict[str, TextBoundAnnotation]]:
    characters = normalized_characters(raw_source_text)
    normalized_source = "".join(character for character, _ in characters)
    normalized_index_by_raw = {
        raw_index: normalized_index
        for normalized_index, (_, raw_index) in enumerate(characters)
    }
    normalized_bounds: dict[str, TextBoundAnnotation] = {}
    for annotation_id, bound in raw_text_bounds.items():
        try:
            start = normalized_index_by_raw[bound.start]
            end = normalized_index_by_raw[bound.end - 1] + 1
        except KeyError as exc:
            raise ValueError(
                f"text-bound annotation intersects removed normalization whitespace: "
                f"{annotation_id}",
            ) from exc
        if normalized_source[start:end] != bound.text:
            raise ValueError(
                f"normalized text-bound annotation mismatch: {annotation_id}",
            )
        normalized_bounds[annotation_id] = TextBoundAnnotation(
            annotation_id=bound.annotation_id,
            annotation_type=bound.annotation_type,
            start=start,
            end=end,
            text=bound.text,
        )
    return normalized_source, normalized_bounds


def build_bionlp_fixture(
    *,
    root: Path,
    document_ids: tuple[str, ...],
    archive_sha256: str,
    source_url: str,
) -> dict[str, object]:
    """Convert preselected corpus documents into independent n-ary event gold."""

    if not document_ids:
        raise ValueError("BioNLP fixture requires preselected document IDs")
    if len(set(document_ids)) != len(document_ids):
        raise ValueError("BioNLP fixture document IDs must be unique")

    cases: list[dict[str, object]] = []
    empty_controls: list[str] = []
    true_negative_controls: list[str] = []
    representability_stress: list[str] = []
    event_exclusions: list[dict[str, object]] = []
    for document_id in document_ids:
        document = load_standoff_document(root, document_id)
        event_records, document_exclusions = _event_records_and_exclusions(document)
        event_exclusions.extend(document_exclusions)
        if not event_records:
            empty_controls.append(document_id)
            if document.events:
                representability_stress.append(document_id)
            else:
                true_negative_controls.append(document_id)
        control_status = "EVENT_GOLD"
        if document_id in true_negative_controls:
            control_status = "TRUE_NO_EVENT_CONTROL"
        elif document_id in representability_stress:
            control_status = "REPRESENTABILITY_STRESS"
        cases.append(
            {
                "case_id": f"bionlp-ge-2011:{document_id}",
                "title": document_id,
                "source": {
                    "corpus": "BioNLP-ST-2011-GE",
                    "document_id": document_id,
                    "source_url": source_url,
                    "archive_sha256": archive_sha256,
                    "mapping_version": "bionlp-ge-to-artana-event.v2",
                },
                "source_text": document.source_text,
                "events": event_records,
                "control_status": control_status,
            }
        )
    if not cases:
        raise ValueError("preselected BioNLP documents contain no eligible events")
    return {
        "schema_version": "tg04_nary_claim_benchmark.v1",
        "metadata": {
            "purpose": "frozen_expert_event_development_panel",
            "selection_method": "lowest_sha256_document_ids_before_content_review",
            "value_labels": "unadjudicated",
            "projection_labels": "unadjudicated",
            "production_semantic_policy_imported": False,
            "selected_document_ids": list(document_ids),
            "excluded_nested_document_ids": [],
            "excluded_no_eligible_document_ids": [],
            "empty_control_document_ids": empty_controls,
            "true_negative_control_document_ids": true_negative_controls,
            "representability_stress_document_ids": representability_stress,
            "event_exclusions": event_exclusions,
        },
        "cases": cases,
    }


def fixture_sha256(payload_bytes: bytes) -> str:
    """Return the immutable digest used to seal generated fixture bytes."""

    return hashlib.sha256(payload_bytes).hexdigest()


def _event_records_and_exclusions(
    document: StandoffDocument,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    modifiers_by_event = {
        modifier.event_id: modifier for modifier in document.modifiers
    }
    records: list[dict[str, object]] = []
    exclusions: list[dict[str, object]] = []
    events_by_id = {event.event_id: event for event in document.events}
    for event in sorted(
        document.events, key=lambda item: _annotation_sort_key(item.event_id)
    ):
        mapped_type = _EVENT_TYPE_MAP.get(event.event_type)
        if mapped_type is None:
            raise ValueError(
                "unmapped BioNLP event category "
                f"{event.event_type!r} in {document.document_id}:{event.event_id}",
            )
        if any(argument.reference_id in events_by_id for argument in event.arguments):
            exclusions.append(
                _event_exclusion(document, event, "nested_event_argument")
            )
            continue
        representable_arguments = tuple(
            argument
            for argument in event.arguments
            if argument.reference_id in document.text_bounds
        )
        if len(representable_arguments) < _MIN_EVENT_ARGUMENTS:
            exclusions.append(
                _event_exclusion(document, event, "insufficient_direct_arguments")
            )
            continue
        trigger = document.text_bounds[event.trigger_id]
        argument_bounds = [
            _argument_bound(argument, document.text_bounds, events_by_id)
            for argument in representable_arguments
        ]
        bounds = [trigger, *argument_bounds]
        source_start = min(bound.start for bound in bounds)
        source_end = max(bound.end for bound in bounds)
        source_span = document.source_text[source_start:source_end]
        if len({bound.text for bound in argument_bounds}) < _MIN_EVENT_ARGUMENTS:
            exclusions.append(
                _event_exclusion(document, event, "indistinct_argument_mentions")
            )
            continue
        if source_span.count(trigger.text) != 1:
            exclusions.append(
                _event_exclusion(document, event, "repeated_trigger_mention")
            )
            continue
        if any(source_span.count(bound.text) != 1 for bound in argument_bounds):
            exclusions.append(
                _event_exclusion(document, event, "repeated_argument_mention")
            )
            continue
        modifier = modifiers_by_event.get(event.event_id)
        polarity, epistemic_status = _adjudicated_epistemic_categories(
            document_id=document.document_id,
            event_annotation_id=event.event_id,
            modifier=modifier.modifier_type if modifier is not None else None,
        )
        records.append(
            {
                "event_id": f"{document.document_id}:{event.event_id}",
                "source_span": source_span,
                "source_locator": f"char:{source_start}-{source_end}",
                "trigger_span": trigger.text,
                "trigger_source_start": trigger.start,
                "event_type": mapped_type,
                "polarity": polarity,
                "epistemic_status": epistemic_status,
                "arguments": [
                    _argument_record(argument, document.text_bounds, events_by_id)
                    for argument in representable_arguments
                ],
                "value_status": "UNADJUDICATED",
                "value_reason": "Source corpus does not annotate Artana decision value.",
                "framing_decision": "UNADJUDICATED",
                "projection_adjudication": "UNADJUDICATED",
                "supported_projections": [],
                "annotation_provenance": {
                    "event_annotation_id": event.event_id,
                    "trigger_annotation_id": event.trigger_id,
                    "argument_annotation_ids": [
                        argument.reference_id for argument in representable_arguments
                    ],
                    "annotation_status": "expert_corpus",
                },
                "eligible_for_event_metrics": True,
            }
        )
    identity_counts = Counter(_record_identity(record) for record in records)
    retained: list[dict[str, object]] = []
    for record in records:
        if identity_counts[_record_identity(record)] == 1:
            retained.append(record)
            continue
        event_id = str(record["event_id"]).split(":")[-1]
        event = next(item for item in document.events if item.event_id == event_id)
        exclusions.append(
            _event_exclusion(document, event, "duplicate_production_identity")
        )
    return retained, exclusions


def _event_exclusion(
    document: StandoffDocument,
    event: EventAnnotation,
    reason: str,
) -> dict[str, object]:
    modifier_references = [
        modifier.annotation_id
        for modifier in document.modifiers
        if modifier.event_id == event.event_id
    ]
    return {
        "document_id": document.document_id,
        "event_id": event.event_id,
        "event_type": event.event_type,
        "reason": reason,
        "annotation_references": [
            event.event_id,
            event.trigger_id,
            *(argument.reference_id for argument in event.arguments),
            *modifier_references,
        ],
    }


def _record_identity(record: dict[str, object]) -> str:
    return json.dumps(
        {
            key: record[key]
            for key in (
                "source_span",
                "source_locator",
                "trigger_span",
                "trigger_source_start",
                "event_type",
                "polarity",
                "epistemic_status",
                "arguments",
            )
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _argument_record(
    argument: EventArgument,
    text_bounds: dict[str, TextBoundAnnotation],
    events_by_id: dict[str, EventAnnotation],
) -> dict[str, object]:
    bound = _argument_bound(argument, text_bounds, events_by_id)
    return {
        "argument_id": argument.reference_id,
        "event_role": _EVENT_ROLE_PATTERN.sub("", argument.role).upper(),
        "participant_role": (
            "BIOLOGICAL_PROCESS"
            if argument.reference_id in events_by_id
            else _PARTICIPANT_ROLE_MAP.get(bound.annotation_type, "OTHER_ENTITY")
        ),
        "exact_span": bound.text,
        "source_start": bound.start,
    }


def _argument_bound(
    argument: EventArgument,
    text_bounds: dict[str, TextBoundAnnotation],
    events_by_id: dict[str, EventAnnotation],
) -> TextBoundAnnotation:
    if argument.reference_id in text_bounds:
        return text_bounds[argument.reference_id]
    referenced_event = events_by_id.get(argument.reference_id)
    if referenced_event is None:
        raise ValueError(f"unknown event argument reference: {argument.reference_id}")
    return text_bounds[referenced_event.trigger_id]


def _epistemic_categories(modifier: str | None) -> tuple[str, str]:
    if modifier == "Negation":
        return "REFUTE", "ASSERTED"
    if modifier == "Speculation":
        return "UNCERTAIN", "UNCERTAIN"
    return "SUPPORT", "ASSERTED"


def _adjudicated_epistemic_categories(
    *,
    document_id: str,
    event_annotation_id: str,
    modifier: str | None,
) -> tuple[str, str]:
    """Apply the hand-adjudicated polarity corrections, then corpus modifiers.

    Polarity is otherwise derived only from a modifier attached to the event
    itself.  Each corrected event is the argument of a nested parent that the
    nesting filter dropped, and the negation was annotated on that parent, so
    the retained child silently kept SUPPORT while its source denies it.

    The corrections are a reviewed table rather than an inheritance rule on
    purpose.  Propagating negation from a dropped `Negative_regulation` parent
    is the obvious rule and it is wrong: it inverts `PMC-2806624-05-RESULTS-04`
    `E15`, where the reduction contrasts two cell genotypes rather than denying
    the induction, and `PMC-2222968-06-Results-05` `E16`, where the child is the
    parent's `Cause` and the negation denies its effect rather than its
    existence.  Both were tested and rejected; see the adjudication record.
    """

    correction = POLARITY_ADJUDICATIONS.get((document_id, event_annotation_id))
    if correction is not None:
        return correction
    return _epistemic_categories(modifier)


def _parse_text_bounds(
    lines: tuple[str, ...],
    source_text: str,
) -> dict[str, TextBoundAnnotation]:
    annotations: dict[str, TextBoundAnnotation] = {}
    for line in lines:
        if not line.startswith("T"):
            continue
        columns = line.split("\t")
        if len(columns) != _TEXT_BOUND_COLUMNS:
            raise ValueError(f"invalid text-bound annotation: {line}")
        annotation_id, descriptor, annotated_text = columns
        descriptor_parts = descriptor.split()
        if len(descriptor_parts) != _TEXT_BOUND_COLUMNS:
            raise ValueError("discontinuous BioNLP spans are not supported")
        annotation_type, raw_start, raw_end = descriptor_parts
        start, end = int(raw_start), int(raw_end)
        if source_text[start:end] != annotated_text:
            raise ValueError(f"text-bound annotation mismatch: {annotation_id}")
        if annotation_id in annotations:
            raise ValueError(f"duplicate text-bound annotation: {annotation_id}")
        annotations[annotation_id] = TextBoundAnnotation(
            annotation_id=annotation_id,
            annotation_type=annotation_type,
            start=start,
            end=end,
            text=annotated_text,
        )
    return annotations


def _parse_events(
    lines: tuple[str, ...],
    text_bounds: dict[str, TextBoundAnnotation],
) -> tuple[EventAnnotation, ...]:
    events: list[EventAnnotation] = []
    event_ids: set[str] = set()
    for line in lines:
        if not line.startswith("E"):
            continue
        columns = line.split("\t")
        if len(columns) != _STANDOFF_PAIR_COLUMNS:
            raise ValueError(f"invalid event annotation: {line}")
        event_id, descriptor = columns
        tokens = descriptor.split()
        event_type, trigger_id = _role_reference(tokens[0])
        if trigger_id not in text_bounds:
            raise ValueError(f"event trigger is not text-bound: {event_id}")
        if event_id in event_ids:
            raise ValueError(f"duplicate event annotation: {event_id}")
        event_ids.add(event_id)
        events.append(
            EventAnnotation(
                event_id=event_id,
                event_type=event_type,
                trigger_id=trigger_id,
                arguments=tuple(
                    EventArgument(*_role_reference(token)) for token in tokens[1:]
                ),
            )
        )
    return tuple(events)


def _parse_modifiers(
    lines: tuple[str, ...],
    event_ids: set[str],
) -> tuple[EventModifier, ...]:
    modifiers: list[EventModifier] = []
    modified_events: set[str] = set()
    for line in lines:
        if not line.startswith("M"):
            continue
        columns = line.split("\t")
        if len(columns) != _STANDOFF_PAIR_COLUMNS:
            raise ValueError(f"invalid event modifier: {line}")
        tokens = columns[1].split()
        if len(tokens) != _STANDOFF_PAIR_COLUMNS or tokens[0] not in {
            "Negation",
            "Speculation",
        }:
            raise ValueError(f"unsupported event modifier: {line}")
        modifier_id = columns[0]
        modifier_type, event_id = tokens
        if event_id not in event_ids:
            raise ValueError(f"modifier references unknown event: {event_id}")
        if event_id in modified_events:
            raise ValueError(f"event has multiple modifiers: {event_id}")
        modified_events.add(event_id)
        modifiers.append(
            EventModifier(
                annotation_id=modifier_id,
                modifier_type=modifier_type,
                event_id=event_id,
            )
        )
    return tuple(modifiers)


def _role_reference(token: str) -> tuple[str, str]:
    role, separator, reference = token.partition(":")
    if not separator or not role or not reference:
        raise ValueError(f"invalid role/reference token: {token}")
    return role, reference


def _read_lines(path: Path) -> tuple[str, ...]:
    return tuple(line for line in path.read_text(encoding="utf-8").splitlines() if line)


def _annotation_sort_key(annotation_id: str) -> tuple[str, int]:
    prefix = annotation_id[:1]
    suffix = annotation_id[1:]
    return prefix, int(suffix) if suffix.isdigit() else 0


__all__ = [
    "EventAnnotation",
    "EventArgument",
    "EventModifier",
    "StandoffDocument",
    "TG04_BIONLP_ARCHIVE_SHA256",
    "TG04_BIONLP_SOURCE_URL",
    "TG04_DEVELOPMENT_DOCUMENT_IDS",
    "TextBoundAnnotation",
    "build_bionlp_fixture",
    "fixture_sha256",
    "load_standoff_document",
]
