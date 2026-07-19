"""Content-blind selection and sealed expert structure for the nested holdout."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimKind,
    InventoryAssertionScope,
    InventoryEpistemicStatus,
    InventoryPolarity,
)

from scripts.validation.claim_events.bionlp_import import (
    TG04_BIONLP_ARCHIVE_SHA256,
    TG04_DEVELOPMENT_DOCUMENT_IDS,
    EventAnnotation,
    EventArgument,
    StandoffDocument,
    TextBoundAnnotation,
    load_standoff_document,
)
from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitEligibilityCategory,
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
_MINIMUM_COMPLETE_LOCAL_EVENTS: Final = 2
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
_EXPECTED_PROJECTION_SET_SHA256: Final = (
    "4811ff571a75f9324b3ff7fd93b8b5e7b6ce031fda8547b1fcba8c3d606bbb86"
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
    referents: tuple[SealedReferenceArgument, ...] = ()


@dataclass(frozen=True, slots=True)
class SealedEvent:
    """One event with direct participants; nested themes live in links."""

    event_id: str
    event_type: str
    trigger: SealedTrigger
    arguments: tuple[SealedArgument, ...]
    argument_alternatives: tuple[tuple[SealedArgument, ...], ...] = ()
    trigger_alternatives: tuple[SealedTrigger, ...] = ()


@dataclass(frozen=True, slots=True)
class SealedEventLink:
    """One expert event-to-event role reference."""

    controller_event_id: str
    event_role: str
    controlled_event_id: str
    controller_argument: SealedReferenceArgument | None = None

    def as_json(self) -> dict[str, object]:
        """Preserve legacy link JSON while emitting optional source identity."""

        payload: dict[str, object] = {
            "controller_event_id": self.controller_event_id,
            "event_role": self.event_role,
            "controlled_event_id": self.controlled_event_id,
        }
        if self.controller_argument is not None:
            payload["controller_argument"] = asdict(self.controller_argument)
        return payload


@dataclass(frozen=True, slots=True)
class SealedReferenceArgument:
    """Source identity of the controller argument that references an event."""

    participant_type: str
    exact_span: str
    source_start: int
    source_end: int


@dataclass(frozen=True, slots=True)
class SealedNestedEventGraph:
    """Minimum expert-authored nested structure hidden from both agents."""

    events: tuple[SealedEvent, ...]
    links: tuple[SealedEventLink, ...]

    def as_json(self) -> dict[str, object]:
        return {
            "events": tuple(_sealed_event_json(event) for event in self.events),
            "links": tuple(link.as_json() for link in self.links),
        }


def _sealed_event_json(event: SealedEvent) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "trigger": asdict(event.trigger),
        "arguments": tuple(_sealed_argument_json(item) for item in event.arguments),
    }
    if event.argument_alternatives:
        payload["argument_alternatives"] = tuple(
            tuple(_sealed_argument_json(item) for item in alternative)
            for alternative in event.argument_alternatives
        )
    if event.trigger_alternatives:
        payload["trigger_alternatives"] = tuple(
            asdict(trigger) for trigger in event.trigger_alternatives
        )
    return payload


def _sealed_argument_json(argument: SealedArgument) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_role": argument.event_role,
        "reference_id": argument.reference_id,
        "participant_type": argument.participant_type,
        "exact_span": argument.exact_span,
        "source_start": argument.source_start,
        "source_end": argument.source_end,
    }
    if argument.referents:
        payload["referents"] = tuple(asdict(item) for item in argument.referents)
    return payload


class ProjectionProvenance(StrEnum):
    """Authorship provenance for one pre-inference acceptable projection."""

    BIONLP_EXPERT = "BIONLP_EXPERT"
    SOURCE_VALID_ALTERNATIVE = "SOURCE_VALID_ALTERNATIVE"
    AGENT_EXPERT_ADJUDICATED = "AGENT_EXPERT_ADJUDICATED"


class CompleteGraphSelectionProfile(StrEnum):
    """Corpus-authored categorical filter applied before content-blind ranking."""

    ANY_CLOSED_GRAPH = "ANY_CLOSED_GRAPH"
    NEGATED_RESULT_GRAPH = "NEGATED_RESULT_GRAPH"


@dataclass(frozen=True, slots=True)
class SealedEventSemantics:
    """Source-adjudicated statement status for one projected event."""

    event_id: str
    claim_kind: ClaimKind
    polarity: InventoryPolarity
    epistemic_status: InventoryEpistemicStatus
    assertion_scope: InventoryAssertionScope = InventoryAssertionScope.SOURCE_ASSERTED


@dataclass(frozen=True, slots=True)
class SealedGraphProjection:
    """One complete graph projection accepted before agent execution."""

    projection_id: str
    provenance: ProjectionProvenance
    scientific_rationale: str
    graph: SealedNestedEventGraph
    event_semantics: tuple[SealedEventSemantics, ...]

    def as_json(self) -> dict[str, object]:
        semantic_payloads: list[dict[str, object]] = []
        for semantics in self.event_semantics:
            payload: dict[str, object] = {
                "event_id": semantics.event_id,
                "claim_kind": semantics.claim_kind,
                "polarity": semantics.polarity,
                "epistemic_status": semantics.epistemic_status,
            }
            if semantics.assertion_scope is not InventoryAssertionScope.SOURCE_ASSERTED:
                payload["assertion_scope"] = semantics.assertion_scope
            semantic_payloads.append(payload)
        return {
            "projection_id": self.projection_id,
            "provenance": self.provenance,
            "scientific_rationale": self.scientific_rationale,
            "graph": self.graph.as_json(),
            "event_semantics": tuple(semantic_payloads),
        }


@dataclass(frozen=True, slots=True)
class SealedProjectionSet:
    """Finite alternatives that must never be mixed for benchmark credit."""

    canonical_projection_id: str
    projections: tuple[SealedGraphProjection, ...]

    @property
    def canonical_projection(self) -> SealedGraphProjection:
        """Return the uniquely named scientific reference projection."""

        matches = tuple(
            projection
            for projection in self.projections
            if projection.projection_id == self.canonical_projection_id
        )
        if len(matches) != 1:
            raise RuntimeError("sealed projection set lacks one canonical projection")
        return matches[0]

    def as_json(self) -> dict[str, object]:
        return {
            "canonical_projection_id": self.canonical_projection_id,
            "projections": tuple(
                projection.as_json() for projection in self.projections
            ),
        }


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
    projection_set: SealedProjectionSet
    projection_set_sha256: str
    expected_eligibility_category: SourceUnitEligibilityCategory


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


@dataclass(frozen=True, slots=True)
class CompleteEventGraphCandidate:
    """One unit whose complete representable event graph is source-local."""

    rank: str
    case_id: str
    unit: FrozenSourceUnit
    document: StandoffDocument
    local_events: tuple[EventAnnotation, ...]


@dataclass(frozen=True, slots=True)
class CompleteEventGraphCandidateUniverse:
    """Recomputed complete-graph universe before seeded ranking."""

    document_count: int
    incompatible_document_ids: tuple[str, ...]
    candidates: tuple[CompleteEventGraphCandidate, ...]


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
    projection_set = canonical_projection_set(
        graph,
        scientific_rationale=(
            "The BioNLP expert graph is the sole pre-registered complete projection."
        ),
    )
    validate_sealed_projection_set(projection_set, unit=selected.unit)
    projection_set_sha256 = _sha256_json(projection_set.as_json())
    if (
        selected.rank != _EXPECTED_SELECTION_RANK
        or selected.case_id != _EXPECTED_CASE_ID
        or selected.unit.index != _EXPECTED_UNIT_INDEX
        or selected.unit.unit_id != _EXPECTED_UNIT_ID
        or selected.unit.source_sha256 != _EXPECTED_SOURCE_SHA256
        or selected.unit.input_sha256 != _EXPECTED_INPUT_SHA256
        or graph_sha256 != _EXPECTED_EXPERT_GRAPH_SHA256
        or projection_set_sha256 != _EXPECTED_PROJECTION_SET_SHA256
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
        projection_set=projection_set,
        projection_set_sha256=projection_set_sha256,
        expected_eligibility_category=SourceUnitEligibilityCategory.FINDING,
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
        for unit in enumerate_source_units(
            case_id=case_id, source_text=document.source_text
        ):
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


def enumerate_complete_event_graph_candidates(
    *,
    corpus_root: Path,
    selection_seed: str,
    excluded_document_ids: frozenset[str] = frozenset(),
    profile: CompleteGraphSelectionProfile = (
        CompleteGraphSelectionProfile.ANY_CLOSED_GRAPH
    ),
) -> CompleteEventGraphCandidateUniverse:
    """Enumerate units only when every local corpus event forms one closed graph."""

    if not selection_seed.strip():
        raise ValueError("complete-event selection seed must be nonempty")
    development_ids = frozenset(TG04_DEVELOPMENT_DOCUMENT_IDS)
    document_ids = tuple(
        sorted(
            path.stem
            for path in corpus_root.glob("*.txt")
            if path.stem not in development_ids
        ),
    )
    incompatible: list[str] = []
    candidates: list[CompleteEventGraphCandidate] = []
    for document_id in document_ids:
        if document_id in excluded_document_ids:
            continue
        try:
            document = load_standoff_document(corpus_root, document_id)
        except ValueError:
            incompatible.append(document_id)
            continue
        case_id = f"bionlp-ge-2011-holdout:{document_id}"
        for unit in enumerate_source_units(
            case_id=case_id, source_text=document.source_text
        ):
            local_events = _complete_local_event_graph(document=document, unit=unit)
            if local_events is None:
                continue
            if not _selection_profile_allows(
                profile=profile,
                document=document,
                local_events=local_events,
            ):
                continue
            rank = hashlib.sha256(
                f"{selection_seed}:{unit.unit_id}".encode(),
            ).hexdigest()
            candidates.append(
                CompleteEventGraphCandidate(
                    rank=rank,
                    case_id=case_id,
                    unit=unit,
                    document=document,
                    local_events=local_events,
                ),
            )
    return CompleteEventGraphCandidateUniverse(
        document_count=len(document_ids),
        incompatible_document_ids=tuple(incompatible),
        candidates=tuple(candidates),
    )


def _selection_profile_allows(
    *,
    profile: CompleteGraphSelectionProfile,
    document: StandoffDocument,
    local_events: tuple[EventAnnotation, ...],
) -> bool:
    if profile is CompleteGraphSelectionProfile.ANY_CLOSED_GRAPH:
        return True
    local_event_ids = {event.event_id for event in local_events}
    controlled_event_ids = {
        argument.reference_id
        for event in local_events
        for argument in event.arguments
        if argument.reference_id in local_event_ids
    }
    top_level_event_ids = local_event_ids - controlled_event_ids
    return any(
        modifier.modifier_type == "Negation"
        and modifier.event_id in top_level_event_ids
        for modifier in document.modifiers
    )


def _complete_local_event_graph(
    *,
    document: StandoffDocument,
    unit: FrozenSourceUnit,
) -> tuple[EventAnnotation, ...] | None:
    """Return every local event only when all identities are closed and representable."""

    local_events = tuple(
        event
        for event in document.events
        if _event_trigger_is_local(document, event, unit)
    )
    if len(local_events) < _MINIMUM_COMPLETE_LOCAL_EVENTS:
        return None
    local_ids = {event.event_id for event in local_events}
    linked_ids: set[str] = set()
    for event in local_events:
        if event.event_type not in _EVENT_TYPE_MAP:
            return None
        direct_arguments = tuple(
            argument
            for argument in event.arguments
            if argument.reference_id in document.text_bounds
        )
        event_arguments = tuple(
            argument
            for argument in event.arguments
            if argument.reference_id not in document.text_bounds
        )
        if not direct_arguments:
            return None
        if not _direct_arguments_are_local(document, direct_arguments, unit):
            return None
        if any(
            document.text_bounds[argument.reference_id].annotation_type
            not in _PARTICIPANT_TYPE_MAP
            for argument in direct_arguments
        ):
            return None
        if any(argument.reference_id not in local_ids for argument in event_arguments):
            return None
        for argument in event_arguments:
            linked_ids.update((event.event_id, argument.reference_id))
    if linked_ids != local_ids:
        return None
    return tuple(sorted(local_events, key=lambda event: event.event_id))


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
            argument
            for argument in outer.arguments
            if argument.reference_id in document.text_bounds
        )
        nested_outer = tuple(
            argument
            for argument in outer.arguments
            if argument.reference_id in events_by_id
        )
        if (
            not direct_outer
            or not nested_outer
            or not _direct_arguments_are_local(
                document,
                direct_outer,
                unit,
            )
        ):
            continue
        for event_argument in nested_outer:
            inner = events_by_id[event_argument.reference_id]
            direct_inner = tuple(
                argument
                for argument in inner.arguments
                if argument.reference_id in document.text_bounds
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
            argument
            for argument in outer.arguments
            if argument.reference_id == inner.event_id
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


def seal_complete_event_graph(
    candidate: CompleteEventGraphCandidate,
) -> SealedNestedEventGraph:
    """Seal every event and event reference in a closed source-local graph."""

    local_ids = {event.event_id for event in candidate.local_events}
    links = tuple(
        sorted(
            (
                SealedEventLink(
                    controller_event_id=event.event_id,
                    event_role=_normalized_role(argument.role),
                    controlled_event_id=argument.reference_id,
                )
                for event in candidate.local_events
                for argument in event.arguments
                if argument.reference_id in local_ids
            ),
            key=lambda link: (
                link.controller_event_id,
                link.event_role,
                link.controlled_event_id,
            ),
        ),
    )
    return SealedNestedEventGraph(
        events=tuple(
            _seal_event(candidate.document, event) for event in candidate.local_events
        ),
        links=links,
    )


def canonical_projection_set(
    graph: SealedNestedEventGraph,
    *,
    scientific_rationale: str,
    event_semantics: tuple[SealedEventSemantics, ...] | None = None,
) -> SealedProjectionSet:
    """Wrap one BioNLP graph in the same finite contract used by later trials."""

    sealed_semantics = event_semantics or tuple(
        SealedEventSemantics(
            event_id=event.event_id,
            claim_kind=ClaimKind.SCIENTIFIC_FINDING,
            polarity=InventoryPolarity.SUPPORT,
            epistemic_status=InventoryEpistemicStatus.ASSERTED,
        )
        for event in graph.events
    )
    return SealedProjectionSet(
        canonical_projection_id="bionlp-expert",
        projections=(
            SealedGraphProjection(
                projection_id="bionlp-expert",
                provenance=ProjectionProvenance.BIONLP_EXPERT,
                scientific_rationale=scientific_rationale,
                graph=graph,
                event_semantics=sealed_semantics,
            ),
        ),
    )


def validate_sealed_projection_set(
    projection_set: SealedProjectionSet,
    *,
    unit: FrozenSourceUnit,
) -> None:
    """Reject projection drift, dangling links, and non-verbatim source identity."""

    if not projection_set.projections:
        raise RuntimeError("sealed projection set must not be empty")
    projection_ids = tuple(
        projection.projection_id for projection in projection_set.projections
    )
    if any(not projection_id.strip() for projection_id in projection_ids):
        raise RuntimeError("sealed projection IDs must be nonempty")
    if len(set(projection_ids)) != len(projection_ids):
        raise RuntimeError("sealed projection IDs must be unique")
    if projection_set.canonical_projection_id not in projection_ids:
        raise RuntimeError("canonical projection is absent from the sealed set")
    canonical = next(
        projection
        for projection in projection_set.projections
        if projection.projection_id == projection_set.canonical_projection_id
    )
    bionlp_projection_count = sum(
        projection.provenance is ProjectionProvenance.BIONLP_EXPERT
        for projection in projection_set.projections
    )
    if bionlp_projection_count > 1:
        raise RuntimeError("sealed projection set permits at most one BioNLP graph")
    if bionlp_projection_count == 1 and (
        canonical.provenance is not ProjectionProvenance.BIONLP_EXPERT
    ):
        raise RuntimeError("BioNLP projection must be canonical when credit-eligible")

    projection_hashes: set[str] = set()
    for projection in projection_set.projections:
        if not projection.scientific_rationale.strip():
            raise RuntimeError("sealed projection rationale must be nonempty")
        projection_hash = _sha256_json(
            {
                "graph": projection.graph.as_json(),
                "event_semantics": [
                    asdict(semantics) for semantics in projection.event_semantics
                ],
            },
        )
        if projection_hash in projection_hashes:
            raise RuntimeError("sealed projections must be semantically distinct")
        projection_hashes.add(projection_hash)
        _validate_projection_graph(projection.graph, unit=unit)
        event_ids = {event.event_id for event in projection.graph.events}
        semantic_ids = tuple(
            semantics.event_id for semantics in projection.event_semantics
        )
        if len(set(semantic_ids)) != len(semantic_ids):
            raise RuntimeError("sealed event-semantic IDs must be unique")
        if set(semantic_ids) != event_ids:
            raise RuntimeError(
                "sealed event semantics must cover projection events exactly",
            )


def _validate_projection_graph(
    graph: SealedNestedEventGraph,
    *,
    unit: FrozenSourceUnit,
) -> None:
    if not graph.events:
        raise RuntimeError("sealed projection requires at least one event")
    event_ids = tuple(event.event_id for event in graph.events)
    if len(set(event_ids)) != len(event_ids):
        raise RuntimeError("sealed projection event IDs must be unique")
    for event in graph.events:
        _validate_event_triggers(event, unit=unit)
        argument_sets = (event.arguments, *event.argument_alternatives)
        if len(
            {
                _sha256_json(tuple(_sealed_argument_json(item) for item in items))
                for items in argument_sets
            }
        ) != len(argument_sets):
            raise RuntimeError("sealed event argument alternatives must be distinct")
        for arguments in argument_sets:
            _validate_sealed_arguments(arguments, unit=unit)
    for link in graph.links:
        if (
            link.controller_event_id not in event_ids
            or link.controlled_event_id not in event_ids
        ):
            raise RuntimeError("sealed projection contains a dangling event link")
        if link.controller_event_id == link.controlled_event_id:
            raise RuntimeError(
                "sealed projection event link cannot be self-referential"
            )
        if link.event_role not in {"CAUSE", "THEME"}:
            raise RuntimeError("sealed projection event link role is unsupported")
        if link.controller_argument is not None:
            _require_verbatim_local_span(
                unit=unit,
                exact_span=link.controller_argument.exact_span,
                source_start=link.controller_argument.source_start,
                source_end=link.controller_argument.source_end,
            )
    link_identities = tuple(
        (
            link.controller_event_id,
            link.event_role,
            link.controlled_event_id,
            None
            if link.controller_argument is None
            else (
                link.controller_argument.participant_type,
                link.controller_argument.exact_span,
                link.controller_argument.source_start,
                link.controller_argument.source_end,
            ),
        )
        for link in graph.links
    )
    if len(set(link_identities)) != len(link_identities):
        raise RuntimeError("sealed projection event links must be unique")


def _validate_event_triggers(
    event: SealedEvent,
    *,
    unit: FrozenSourceUnit,
) -> None:
    triggers = (event.trigger, *event.trigger_alternatives)
    trigger_identities = tuple(
        (trigger.exact_span, trigger.source_start, trigger.source_end)
        for trigger in triggers
    )
    if len(set(trigger_identities)) != len(trigger_identities):
        raise RuntimeError("sealed event trigger alternatives must be distinct")
    for trigger in triggers:
        _require_verbatim_local_span(
            unit=unit,
            exact_span=trigger.exact_span,
            source_start=trigger.source_start,
            source_end=trigger.source_end,
        )


def _validate_sealed_arguments(
    arguments: tuple[SealedArgument, ...],
    *,
    unit: FrozenSourceUnit,
) -> None:
    argument_identities = tuple(
        (
            argument.event_role,
            argument.participant_type,
            argument.exact_span,
            argument.source_start,
            argument.source_end,
        )
        for argument in arguments
    )
    if len(set(argument_identities)) != len(argument_identities):
        raise RuntimeError("sealed projection arguments must be unique")
    for argument in arguments:
        _require_verbatim_local_span(
            unit=unit,
            exact_span=argument.exact_span,
            source_start=argument.source_start,
            source_end=argument.source_end,
        )
        for referent in argument.referents:
            _require_verbatim_local_span(
                unit=unit,
                exact_span=referent.exact_span,
                source_start=referent.source_start,
                source_end=referent.source_end,
            )


def _require_verbatim_local_span(
    *,
    unit: FrozenSourceUnit,
    exact_span: str,
    source_start: int,
    source_end: int,
) -> None:
    local_start = source_start - unit.source_start
    local_end = source_end - unit.source_start
    if (
        local_start < 0
        or local_end > len(unit.text)
        or local_start >= local_end
        or unit.text[local_start:local_end] != exact_span
    ):
        raise RuntimeError("sealed projection span is not verbatim in the source unit")


def _seal_event(document: StandoffDocument, event: EventAnnotation) -> SealedEvent:
    trigger = document.text_bounds[event.trigger_id]
    arguments = tuple(
        sorted(
            (
                _seal_argument(
                    document.text_bounds[argument.reference_id], argument.role
                )
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
    "CompleteGraphSelectionProfile",
    "CompleteEventGraphCandidate",
    "CompleteEventGraphCandidateUniverse",
    "NestedHoldoutSelection",
    "NestedEventCandidate",
    "NestedEventCandidateUniverse",
    "ProjectionProvenance",
    "SealedArgument",
    "SealedEvent",
    "SealedEventLink",
    "SealedReferenceArgument",
    "SealedEventSemantics",
    "SealedGraphProjection",
    "SealedNestedEventGraph",
    "SealedProjectionSet",
    "canonical_projection_set",
    "enumerate_complete_event_graph_candidates",
    "enumerate_nested_event_candidates",
    "seal_nested_event_graph",
    "seal_complete_event_graph",
    "select_nested_event_holdout",
    "validate_sealed_projection_set",
]
