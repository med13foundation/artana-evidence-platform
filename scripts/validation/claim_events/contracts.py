"""Immutable contracts for the TG-04 n-ary claim benchmark."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_MIN_NARY_ARGUMENTS: Final = 2


class BenchmarkEventType(StrEnum):
    """Closed event categories shared by the benchmark source corpora."""

    EXPRESSION = "EXPRESSION"
    TRANSCRIPTION = "TRANSCRIPTION"
    DEGRADATION = "DEGRADATION"
    PHOSPHORYLATION = "PHOSPHORYLATION"
    LOCALIZATION = "LOCALIZATION"
    BINDING = "BINDING"
    REGULATION = "REGULATION"
    POSITIVE_REGULATION = "POSITIVE_REGULATION"
    NEGATIVE_REGULATION = "NEGATIVE_REGULATION"
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    ASSOCIATION = "ASSOCIATION"
    TREATMENT_RESPONSE = "TREATMENT_RESPONSE"
    NO_EFFECT = "NO_EFFECT"
    OTHER_EXPLICIT = "OTHER_EXPLICIT"


class Polarity(StrEnum):
    SUPPORT = "SUPPORT"
    REFUTE = "REFUTE"
    UNCERTAIN = "UNCERTAIN"
    HYPOTHESIS = "HYPOTHESIS"
    NULL_RESULT = "NULL_RESULT"


class EpistemicStatus(StrEnum):
    ASSERTED = "ASSERTED"
    PROVISIONAL = "PROVISIONAL"
    UNCERTAIN = "UNCERTAIN"
    HYPOTHESIS = "HYPOTHESIS"
    NULL_RESULT = "NULL_RESULT"


class EventRole(StrEnum):
    """Closed roles used by supported primary event corpora."""

    AGENT = "AGENT"
    THEME = "THEME"
    TARGET = "TARGET"
    CAUSE = "CAUSE"
    EFFECT = "EFFECT"
    CONTEXT = "CONTEXT"
    SITE = "SITE"
    CSITE = "CSITE"
    ATLOC = "ATLOC"
    TOLOC = "TOLOC"
    FROMLOC = "FROMLOC"
    MEASURE = "MEASURE"


class ArtanaParticipantRole(StrEnum):
    """Closed Artana role retained before graph endpoint selection."""

    INTERVENTION = "INTERVENTION"
    CONDITION = "CONDITION"
    POPULATION = "POPULATION"
    VARIANT = "VARIANT"
    OUTCOME = "OUTCOME"
    COMPARATOR = "COMPARATOR"
    TIMEFRAME = "TIMEFRAME"
    STUDY_DESIGN = "STUDY_DESIGN"
    TREATMENT_SETTING = "TREATMENT_SETTING"
    GENE_OR_PROTEIN = "GENE_OR_PROTEIN"
    CHEMICAL_OR_DRUG = "CHEMICAL_OR_DRUG"
    BIOMARKER = "BIOMARKER"
    EXPOSURE = "EXPOSURE"
    BIOLOGICAL_PROCESS = "BIOLOGICAL_PROCESS"
    ANATOMY = "ANATOMY"
    MEASUREMENT = "MEASUREMENT"
    OTHER_ENTITY = "OTHER_ENTITY"


class FramingDecision(StrEnum):
    SINGLE_FRAME = "SINGLE_FRAME"
    MULTIPLE_VALID_FRAMES = "MULTIPLE_VALID_FRAMES"
    AMBIGUOUS = "AMBIGUOUS"
    ABSTAIN = "ABSTAIN"
    UNADJUDICATED = "UNADJUDICATED"


class ValueStatus(StrEnum):
    VALUABLE = "VALUABLE"
    NOT_VALUABLE = "NOT_VALUABLE"
    UNADJUDICATED = "UNADJUDICATED"


class ProjectionEligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    UNADJUDICATED = "UNADJUDICATED"


class BenchmarkEligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"


class AnnotationStatus(StrEnum):
    EXPERT_CORPUS = "expert_corpus"
    AUTHENTICATED_HUMAN_REVIEW = "authenticated_human_review"
    DEVELOPMENT_ANNOTATION = "development_annotation"


class CaseControlStatus(StrEnum):
    EVENT_GOLD = "EVENT_GOLD"
    TRUE_NO_EVENT_CONTROL = "TRUE_NO_EVENT_CONTROL"
    REPRESENTABILITY_STRESS = "REPRESENTABILITY_STRESS"


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    """Frozen corpus identity and archive binding for one source document."""

    corpus: str
    document_id: str
    source_url: str
    archive_sha256: str
    mapping_version: str

    def __post_init__(self) -> None:
        for label, value in (
            ("corpus", self.corpus),
            ("document_id", self.document_id),
            ("source_url", self.source_url),
            ("mapping_version", self.mapping_version),
        ):
            _require_text(value, label)
        if _SHA256_RE.fullmatch(self.archive_sha256) is None:
            raise ValueError("archive_sha256 must be lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class SourceLocator:
    """Exact character offsets into a case's frozen source text."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError("source locator must satisfy 0 <= start < end")

    def __str__(self) -> str:
        return f"char:{self.start}-{self.end}"


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """One exact source region bound by a character locator."""

    locator: SourceLocator
    exact_span: str

    def __post_init__(self) -> None:
        _require_text(self.exact_span, "source span")


@dataclass(frozen=True, slots=True)
class ExactTrigger:
    exact_span: str
    source_start: int

    def __post_init__(self) -> None:
        _require_text(self.exact_span, "trigger span")
        if self.source_start < 0:
            raise ValueError("trigger source_start must be nonnegative")


@dataclass(frozen=True, slots=True)
class ClaimArgument:
    """One source argument with event semantics and an Artana role."""

    argument_id: str
    event_role: EventRole
    participant_role: ArtanaParticipantRole
    exact_span: str
    source_start: int

    def __post_init__(self) -> None:
        _require_text(self.argument_id, "argument_id")
        _require_text(self.exact_span, "argument exact_span")
        if self.source_start < 0:
            raise ValueError("argument source_start must be nonnegative")

    @property
    def role(self) -> str:
        """Expose the Artana role expected by deterministic scoring."""

        return self.participant_role.value


@dataclass(frozen=True, slots=True)
class SupportedProjection:
    subject_argument_id: str
    relation_type: str
    object_argument_id: str

    def __post_init__(self) -> None:
        _require_text(self.subject_argument_id, "projection subject_argument_id")
        _require_text(self.relation_type, "projection relation_type")
        _require_text(self.object_argument_id, "projection object_argument_id")
        if self.subject_argument_id == self.object_argument_id:
            raise ValueError("projection subject and object arguments must differ")


@dataclass(frozen=True, slots=True)
class AnnotationProvenance:
    """Source-corpus annotation IDs supporting one event."""

    event_annotation_id: str
    trigger_annotation_id: str
    argument_annotation_ids: tuple[str, ...]
    status: AnnotationStatus

    def __post_init__(self) -> None:
        _require_text(self.event_annotation_id, "event_annotation_id")
        _require_text(self.trigger_annotation_id, "trigger_annotation_id")
        if not self.argument_annotation_ids:
            raise ValueError("annotation provenance requires argument annotation IDs")
        if len(set(self.argument_annotation_ids)) != len(self.argument_annotation_ids):
            raise ValueError("argument annotation IDs must be unique")
        for annotation_id in self.argument_annotation_ids:
            _require_text(annotation_id, "argument annotation ID")

    @property
    def is_independent(self) -> bool:
        return self.status in {
            AnnotationStatus.EXPERT_CORPUS,
            AnnotationStatus.AUTHENTICATED_HUMAN_REVIEW,
        }


@dataclass(frozen=True, slots=True)
class ValueAnnotation:
    """Categorical value gold, including an honest unlabeled state."""

    status: ValueStatus
    reason: str | None

    @property
    def included_in_valuable_recall(self) -> bool:
        return self.status is not ValueStatus.UNADJUDICATED


@dataclass(frozen=True, slots=True)
class ProjectionAnnotation:
    """Projection mapping state and semantically unordered unique projections."""

    status: ProjectionEligibilityStatus
    supported: tuple[SupportedProjection, ...]

    def __post_init__(self) -> None:
        if len(set(self.supported)) != len(self.supported):
            raise ValueError("supported projections must be unique")

    @property
    def included_in_projection_metrics(self) -> bool:
        return self.status is not ProjectionEligibilityStatus.UNADJUDICATED


@dataclass(frozen=True, slots=True)
class BenchmarkEligibility:
    status: BenchmarkEligibilityStatus

    @property
    def included_in_whole_claim_metrics(self) -> bool:
        return self.status is BenchmarkEligibilityStatus.ELIGIBLE


@dataclass(frozen=True, slots=True)
class NaryClaimEvent:
    """Complete categorical gold for one source-local n-ary event."""

    event_id: str
    source: SourceSpan
    trigger: ExactTrigger
    event_type: BenchmarkEventType
    polarity: Polarity
    epistemic_status: EpistemicStatus
    arguments: frozenset[ClaimArgument]
    value: ValueAnnotation
    framing_decision: FramingDecision
    projections: ProjectionAnnotation
    provenance: AnnotationProvenance
    eligibility: BenchmarkEligibility

    def __post_init__(self) -> None:
        _require_text(self.event_id, "event_id")
        if len(self.arguments) < _MIN_NARY_ARGUMENTS:
            raise ValueError("n-ary claim event requires at least two arguments")
        argument_ids = tuple(argument.argument_id for argument in self.arguments)
        if len(set(argument_ids)) != len(argument_ids):
            raise ValueError("claim argument IDs must be unique")
        identities = tuple(
            (
                argument.event_role,
                argument.participant_role,
                argument.exact_span,
                argument.source_start,
            )
            for argument in self.arguments
        )
        if len(set(identities)) != len(identities):
            raise ValueError("claim arguments must be role/span unique")
        if set(self.provenance.argument_annotation_ids) != set(argument_ids):
            raise ValueError("argument provenance must cover every argument exactly")
        bound_ids = set(argument_ids)
        for projection in self.projections.supported:
            if {
                projection.subject_argument_id,
                projection.object_argument_id,
            } - bound_ids:
                raise ValueError("supported projection references an unknown argument")
        if (
            self.framing_decision is FramingDecision.ABSTAIN
            and self.projections.supported
        ):
            raise ValueError("ABSTAIN gold cannot contain supported projections")
        if self.value.included_in_valuable_recall:
            if self.value.reason is None or self.value.reason.strip() == "":
                raise ValueError(
                    "adjudicated value labels require an independent reason"
                )
            if not self.provenance.is_independent:
                raise ValueError(
                    "adjudicated value labels require independent provenance"
                )
        if (
            self.projections.included_in_projection_metrics
            and not self.provenance.is_independent
        ):
            raise ValueError("adjudicated projections require independent provenance")
        if (
            self.eligibility.included_in_whole_claim_metrics
            and not self.provenance.is_independent
        ):
            raise ValueError("eligible events require independent provenance")

    @property
    def source_span(self) -> str:
        return self.source.exact_span

    @property
    def source_locator(self) -> str:
        return str(self.source.locator)

    @property
    def trigger_span(self) -> str:
        return self.trigger.exact_span

    @property
    def trigger_source_start(self) -> int:
        return self.trigger.source_start

    @property
    def valuable(self) -> ValueAnnotation:
        return self.value

    @property
    def supported_projections(self) -> ProjectionAnnotation:
        return self.projections


@dataclass(frozen=True, slots=True)
class NaryClaimCase:
    case_id: str
    title: str
    source: SourceIdentity
    source_text: str
    events: tuple[NaryClaimEvent, ...]
    control_status: CaseControlStatus

    def __post_init__(self) -> None:
        _require_text(self.case_id, "case_id")
        _require_text(self.title, "title")
        _require_text(self.source_text, "source_text")
        event_ids = tuple(event.event_id for event in self.events)
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("event IDs must be unique within a case")
        if self.control_status is CaseControlStatus.EVENT_GOLD and not self.events:
            raise ValueError("event-gold case requires at least one event")
        if self.control_status is not CaseControlStatus.EVENT_GOLD and self.events:
            raise ValueError("control cases cannot contain scored events")


@dataclass(frozen=True, slots=True)
class BenchmarkMetadata:
    purpose: str
    selection_method: str
    value_labels: str
    projection_labels: str
    production_semantic_policy_imported: bool
    selected_document_ids: tuple[str, ...]
    excluded_nested_document_ids: tuple[str, ...]
    excluded_no_eligible_document_ids: tuple[str, ...]
    empty_control_document_ids: tuple[str, ...]
    true_negative_control_document_ids: tuple[str, ...]
    representability_stress_document_ids: tuple[str, ...]
    event_exclusions: tuple[BenchmarkEventExclusion, ...]

    def __post_init__(self) -> None:
        if not self.selected_document_ids:
            raise ValueError("benchmark metadata requires selected document IDs")
        if len(set(self.selected_document_ids)) != len(self.selected_document_ids):
            raise ValueError("selected document IDs must be unique")
        excluded = (
            self.excluded_nested_document_ids + self.excluded_no_eligible_document_ids
        )
        if len(set(excluded)) != len(excluded):
            raise ValueError("excluded document IDs must be unique")
        if set(excluded) - set(self.selected_document_ids):
            raise ValueError("excluded documents must come from the frozen selection")
        if set(self.empty_control_document_ids) - set(self.selected_document_ids):
            raise ValueError("empty controls must come from the frozen selection")
        if set(self.true_negative_control_document_ids) | set(
            self.representability_stress_document_ids
        ) != set(self.empty_control_document_ids):
            raise ValueError("empty controls must split into negative and stress sets")
        if set(self.true_negative_control_document_ids) & set(
            self.representability_stress_document_ids
        ):
            raise ValueError("negative and stress control documents must be disjoint")
        if any(
            item.document_id not in self.selected_document_ids
            for item in self.event_exclusions
        ):
            raise ValueError("event exclusions must come from the frozen selection")


@dataclass(frozen=True, slots=True)
class BenchmarkEventExclusion:
    document_id: str
    event_id: str
    event_type: str
    reason: str
    annotation_references: tuple[str, ...]

    def __post_init__(self) -> None:
        for label, value in (
            ("document_id", self.document_id),
            ("event_id", self.event_id),
            ("event_type", self.event_type),
            ("reason", self.reason),
        ):
            _require_text(value, label)
        if not self.annotation_references:
            raise ValueError("event exclusion requires annotation references")


@dataclass(frozen=True, slots=True)
class NaryClaimFixture:
    path: Path
    sha256: str
    schema_version: str
    metadata: BenchmarkMetadata
    cases: tuple[NaryClaimCase, ...]

    @property
    def eligible_events(self) -> tuple[NaryClaimEvent, ...]:
        return tuple(
            event
            for case in self.cases
            for event in case.events
            if event.eligibility.included_in_whole_claim_metrics
        )

    def __post_init__(self) -> None:
        retained = {case.source.document_id for case in self.cases}
        if retained != set(self.metadata.selected_document_ids):
            raise ValueError(
                "fixture selection ledger must cover every selected document"
            )
        empty = {case.source.document_id for case in self.cases if not case.events}
        if empty != set(self.metadata.empty_control_document_ids):
            raise ValueError("fixture empty-control ledger differs from case events")
        true_negative = {
            case.source.document_id
            for case in self.cases
            if case.control_status is CaseControlStatus.TRUE_NO_EVENT_CONTROL
        }
        stress = {
            case.source.document_id
            for case in self.cases
            if case.control_status is CaseControlStatus.REPRESENTABILITY_STRESS
        }
        if true_negative != set(self.metadata.true_negative_control_document_ids):
            raise ValueError("true-negative control ledger differs from cases")
        if stress != set(self.metadata.representability_stress_document_ids):
            raise ValueError("representability-stress ledger differs from cases")

    @property
    def valuable_recall_events(self) -> tuple[NaryClaimEvent, ...]:
        return tuple(
            event
            for event in self.eligible_events
            if event.value.included_in_valuable_recall
        )


def validate_event_type_parity(production_values: Iterable[str]) -> None:
    """Fail if a supplied production event enum differs from benchmark categories."""

    benchmark_values = {event_type.value for event_type in BenchmarkEventType}
    supplied_values = set(production_values)
    if supplied_values != benchmark_values:
        missing = sorted(benchmark_values - supplied_values)
        extra = sorted(supplied_values - benchmark_values)
        raise ValueError(
            f"event type parity mismatch: missing={missing}, extra={extra}"
        )


def _require_text(value: str, label: str) -> None:
    if value.strip() == "":
        raise ValueError(f"{label} must be nonempty")


EventType = BenchmarkEventType
NaryClaimGold = NaryClaimEvent

__all__ = [
    "AnnotationProvenance",
    "AnnotationStatus",
    "ArtanaParticipantRole",
    "BenchmarkEligibility",
    "BenchmarkEligibilityStatus",
    "BenchmarkEventType",
    "BenchmarkMetadata",
    "ClaimArgument",
    "EpistemicStatus",
    "EventRole",
    "EventType",
    "ExactTrigger",
    "FramingDecision",
    "NaryClaimCase",
    "NaryClaimEvent",
    "NaryClaimFixture",
    "NaryClaimGold",
    "Polarity",
    "ProjectionAnnotation",
    "ProjectionEligibilityStatus",
    "SourceIdentity",
    "SourceLocator",
    "SourceSpan",
    "SupportedProjection",
    "ValueAnnotation",
    "ValueStatus",
    "validate_event_type_parity",
]
