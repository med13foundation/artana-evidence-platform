"""Content-blind selection and sealed expert structure for the nested holdout."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from scripts.validation.claim_events.bionlp_import import (
    TG04_BIONLP_ARCHIVE_SHA256,
    TG04_DEVELOPMENT_DOCUMENT_IDS,
    EventAnnotation,
    EventArgument,
    StandoffDocument,
    TextBoundAnnotation,
    load_standoff_document,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    FrozenSourceUnit,
    enumerate_source_units,
)

_SELECTION_SEED: Final = "4aa22b9b:nested-event-holdout"
_EXPECTED_DOCUMENT_COUNT: Final = 219
_EXPECTED_INCOMPATIBLE_DOCUMENT_IDS: Final = (
    "PMC-1134658-08-Discussion",
    "PMC-1920263-11-RESULTS-03",
    "PMID-7747440",
)
_EXPECTED_ELIGIBLE_UNIT_COUNT: Final = 16
_MINIMUM_INNER_DIRECT_ARGUMENTS: Final = 2
_EXPECTED_SELECTION_RANK: Final = (
    "0757a19258cb5e142ad2b9828c6ee0ed9755767ab90ddbad972c75867d3577af"
)
_EXPECTED_CASE_ID: Final = "bionlp-ge-2011-holdout:PMID-9233802"
_EXPECTED_UNIT_INDEX: Final = 6
_EXPECTED_UNIT_ID: Final = (
    "source-unit-31bc45a6ba24e4a11aa447b05605b154b572cfcc6bdabf1165146c9f7ef3f165"
)
_EXPECTED_SOURCE_SHA256: Final = (
    "9d451b9a5895ea7cf4c62e26e76336bee2cb95545cfd18792603eda0fc9b98c3"
)
_EXPECTED_INPUT_SHA256: Final = (
    "9e9ca12cb6b082b4dfcf925100a95eed632329c20b5f86c8a2ce4e66fafcf65c"
)
_EXPECTED_EXPERT_GRAPH_SHA256: Final = (
    "f5b05562dd68a26024ae0fc0f88d7b7b043a9631fba43b7ea53a81ad913d4593"
)
_ARTICLE_URL: Final = "https://pubmed.ncbi.nlm.nih.gov/9233802/"
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
_PARTICIPANT_TYPE_MAP: Final = {
    "Protein": "GENE_OR_PROTEIN",
    "Entity": "OTHER_ENTITY",
}


@dataclass(frozen=True, slots=True)
class SealedTrigger:
    """Expert-authored source identity for one event trigger."""

    exact_span: str
    source_start: int
    source_end: int


@dataclass(frozen=True, slots=True)
class SealedArgument:
    """One direct expert participant in a sealed event."""

    event_role: str
    reference_id: str
    participant_type: str
    exact_span: str
    source_start: int
    source_end: int


@dataclass(frozen=True, slots=True)
class SealedEvent:
    """One event with direct participants; nested themes live in links."""

    event_id: str
    event_type: str
    trigger: SealedTrigger
    arguments: tuple[SealedArgument, ...]


@dataclass(frozen=True, slots=True)
class SealedEventLink:
    """One expert event-to-event role reference."""

    controller_event_id: str
    event_role: str
    controlled_event_id: str


@dataclass(frozen=True, slots=True)
class SealedNestedEventGraph:
    """Minimum expert-authored nested structure hidden from both agents."""

    events: tuple[SealedEvent, ...]
    links: tuple[SealedEventLink, ...]

    def as_json(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class NestedHoldoutSelection:
    """One untouched source unit and independently sealed expert graph."""

    case_id: str
    unit: FrozenSourceUnit
    expert_graph: SealedNestedEventGraph
    trial_generation: int
    selection_seed: str
    selection_rule: str
    excluded_document_ids: tuple[str, ...]
    selection_rank: str
    candidate_unit_count: int
    holdout_document_count: int
    incompatible_document_ids: tuple[str, ...]
    archive_sha256: str
    expert_graph_sha256: str
    authoritative_article_url: str


@dataclass(frozen=True, slots=True)
class NestedEventCandidate:
    rank: str
    case_id: str
    unit: FrozenSourceUnit
    document: StandoffDocument
    nested_pairs: tuple[tuple[EventAnnotation, EventAnnotation], ...]


@dataclass(frozen=True, slots=True)
class NestedEventCandidateUniverse:
    """Recomputed holdout universe before seeded candidate ranking."""

    document_count: int
    incompatible_document_ids: tuple[str, ...]
    candidates: tuple[NestedEventCandidate, ...]


def select_nested_event_holdout(
    *,
    corpus_root: Path,
    archive_sha256: str,
) -> NestedHoldoutSelection:
    """Recompute the content-blind holdout and reject any corpus drift."""

    if archive_sha256 != TG04_BIONLP_ARCHIVE_SHA256:
        raise RuntimeError("BioNLP holdout archive hash changed")
    universe = enumerate_nested_event_candidates(
        corpus_root=corpus_root,
        selection_seed=_SELECTION_SEED,
    )
    if universe.document_count != _EXPECTED_DOCUMENT_COUNT:
        raise RuntimeError("BioNLP holdout document universe changed")
    if universe.incompatible_document_ids != _EXPECTED_INCOMPATIBLE_DOCUMENT_IDS:
        raise RuntimeError("BioNLP holdout importer exclusions changed")
    if len(universe.candidates) != _EXPECTED_ELIGIBLE_UNIT_COUNT:
        raise RuntimeError("BioNLP eligible nested-event unit count changed")

    selected = min(universe.candidates, key=lambda candidate: candidate.rank)
    graph = seal_nested_event_graph(selected)
    graph_sha256 = _sha256_json(graph.as_json())
    if (
        selected.rank != _EXPECTED_SELECTION_RANK
        or selected.case_id != _EXPECTED_CASE_ID
        or selected.unit.index != _EXPECTED_UNIT_INDEX
        or selected.unit.unit_id != _EXPECTED_UNIT_ID
        or selected.unit.source_sha256 != _EXPECTED_SOURCE_SHA256
        or selected.unit.input_sha256 != _EXPECTED_INPUT_SHA256
        or graph_sha256 != _EXPECTED_EXPERT_GRAPH_SHA256
    ):
        raise RuntimeError("pre-registered nested holdout selection changed")
    return NestedHoldoutSelection(
        case_id=selected.case_id,
        unit=selected.unit,
        expert_graph=graph,
        trial_generation=1,
        selection_seed=_SELECTION_SEED,
        selection_rule="lowest_sha256_eligible_unit_outside_development_panel",
        excluded_document_ids=(),
        selection_rank=selected.rank,
        candidate_unit_count=len(universe.candidates),
        holdout_document_count=universe.document_count,
        incompatible_document_ids=universe.incompatible_document_ids,
        archive_sha256=archive_sha256,
        expert_graph_sha256=graph_sha256,
        authoritative_article_url=_ARTICLE_URL,
    )


def enumerate_nested_event_candidates(
    *,
    corpus_root: Path,
    selection_seed: str,
    excluded_document_ids: frozenset[str] = frozenset(),
) -> NestedEventCandidateUniverse:
    """Enumerate eligible units without inspecting or ranking source meaning."""

    if not selection_seed.strip():
        raise ValueError("nested-event selection seed must be nonempty")
    development_ids = frozenset(TG04_DEVELOPMENT_DOCUMENT_IDS)
    document_ids = tuple(
        sorted(
            path.stem
            for path in corpus_root.glob("*.txt")
            if path.stem not in development_ids
        ),
    )
    incompatible: list[str] = []
    candidates: list[NestedEventCandidate] = []
    for document_id in document_ids:
        if document_id in excluded_document_ids:
            continue
        try:
            document = load_standoff_document(corpus_root, document_id)
        except ValueError:
            incompatible.append(document_id)
            continue
        case_id = f"bionlp-ge-2011-holdout:{document_id}"
        for unit in enumerate_source_units(case_id=case_id, source_text=document.source_text):
            nested_pairs = _eligible_nested_pairs(document=document, unit=unit)
            if not nested_pairs:
                continue
            rank = hashlib.sha256(
                f"{selection_seed}:{unit.unit_id}".encode(),
            ).hexdigest()
            candidates.append(
                NestedEventCandidate(
                    rank=rank,
                    case_id=case_id,
                    unit=unit,
                    document=document,
                    nested_pairs=nested_pairs,
                ),
            )
    return NestedEventCandidateUniverse(
        document_count=len(document_ids),
        incompatible_document_ids=tuple(incompatible),
        candidates=tuple(candidates),
    )


def _eligible_nested_pairs(
    *,
    document: StandoffDocument,
    unit: FrozenSourceUnit,
) -> tuple[tuple[EventAnnotation, EventAnnotation], ...]:
    events_by_id = {event.event_id: event for event in document.events}
    pairs: list[tuple[EventAnnotation, EventAnnotation]] = []
    for outer in document.events:
        if not _event_trigger_is_local(document, outer, unit):
            continue
        direct_outer = tuple(
            argument for argument in outer.arguments if argument.reference_id in document.text_bounds
        )
        nested_outer = tuple(
            argument for argument in outer.arguments if argument.reference_id in events_by_id
        )
        if not direct_outer or not nested_outer or not _direct_arguments_are_local(
            document,
            direct_outer,
            unit,
        ):
            continue
        for event_argument in nested_outer:
            inner = events_by_id[event_argument.reference_id]
            direct_inner = tuple(
                argument for argument in inner.arguments if argument.reference_id in document.text_bounds
            )
            if (
                len(direct_inner) >= _MINIMUM_INNER_DIRECT_ARGUMENTS
                and _event_trigger_is_local(document, inner, unit)
                and _direct_arguments_are_local(document, direct_inner, unit)
            ):
                pairs.append((outer, inner))
    return tuple(pairs)


def _event_trigger_is_local(
    document: StandoffDocument,
    event: EventAnnotation,
    unit: FrozenSourceUnit,
) -> bool:
    trigger = document.text_bounds[event.trigger_id]
    return unit.source_start <= trigger.start and trigger.end <= unit.source_end


def _direct_arguments_are_local(
    document: StandoffDocument,
    arguments: tuple[EventArgument, ...],
    unit: FrozenSourceUnit,
) -> bool:
    return all(
        unit.source_start <= document.text_bounds[argument.reference_id].start
        and document.text_bounds[argument.reference_id].end <= unit.source_end
        for argument in arguments
    )


def seal_nested_event_graph(candidate: NestedEventCandidate) -> SealedNestedEventGraph:
    events_by_id: dict[str, SealedEvent] = {}
    links: list[SealedEventLink] = []
    for outer, inner in candidate.nested_pairs:
        events_by_id[inner.event_id] = _seal_event(candidate.document, inner)
        events_by_id[outer.event_id] = _seal_event(candidate.document, outer)
        event_argument = next(
            argument for argument in outer.arguments if argument.reference_id == inner.event_id
        )
        links.append(
            SealedEventLink(
                controller_event_id=outer.event_id,
                event_role=_normalized_role(event_argument.role),
                controlled_event_id=inner.event_id,
            ),
        )
    return SealedNestedEventGraph(
        events=tuple(events_by_id[event_id] for event_id in sorted(events_by_id)),
        links=tuple(
            sorted(
                links,
                key=lambda link: (
                    link.controller_event_id,
                    link.event_role,
                    link.controlled_event_id,
                ),
            ),
        ),
    )


def _seal_event(document: StandoffDocument, event: EventAnnotation) -> SealedEvent:
    trigger = document.text_bounds[event.trigger_id]
    arguments = tuple(
        sorted(
            (
                _seal_argument(document.text_bounds[argument.reference_id], argument.role)
                for argument in event.arguments
                if argument.reference_id in document.text_bounds
            ),
            key=lambda argument: (argument.event_role, argument.reference_id),
        ),
    )
    try:
        event_type = _EVENT_TYPE_MAP[event.event_type]
    except KeyError as exc:
        raise RuntimeError("selected nested event type is not representable") from exc
    return SealedEvent(
        event_id=event.event_id,
        event_type=event_type,
        trigger=_seal_trigger(trigger),
        arguments=arguments,
    )


def _seal_trigger(bound: TextBoundAnnotation) -> SealedTrigger:
    return SealedTrigger(
        exact_span=bound.text,
        source_start=bound.start,
        source_end=bound.end,
    )


def _seal_argument(bound: TextBoundAnnotation, event_role: str) -> SealedArgument:
    try:
        participant_type = _PARTICIPANT_TYPE_MAP[bound.annotation_type]
    except KeyError as exc:
        raise RuntimeError("selected participant type is not representable") from exc
    return SealedArgument(
        event_role=_normalized_role(event_role),
        reference_id=bound.annotation_id,
        participant_type=participant_type,
        exact_span=bound.text,
        source_start=bound.start,
        source_end=bound.end,
    )


def _normalized_role(value: str) -> str:
    role = value.rstrip("0123456789").upper()
    if not role:
        raise RuntimeError("selected event role is empty after normalization")
    return role


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"),
    ).hexdigest()


__all__ = [
    "NestedHoldoutSelection",
    "NestedEventCandidate",
    "NestedEventCandidateUniverse",
    "SealedArgument",
    "SealedEvent",
    "SealedEventLink",
    "SealedNestedEventGraph",
    "enumerate_nested_event_candidates",
    "seal_nested_event_graph",
    "select_nested_event_holdout",
]
