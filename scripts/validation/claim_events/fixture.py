"""Strict JSON loader for TG-04 n-ary claim benchmark fixtures."""

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from pathlib import Path
from typing import Final, TypeVar, cast

from scripts.validation.claim_events.contracts import (
    AnnotationProvenance,
    AnnotationStatus,
    ArtanaParticipantRole,
    BenchmarkEligibility,
    BenchmarkEligibilityStatus,
    BenchmarkEventExclusion,
    BenchmarkEventType,
    BenchmarkMetadata,
    CaseControlStatus,
    ClaimArgument,
    EpistemicStatus,
    EventRole,
    ExactTrigger,
    FramingDecision,
    NaryClaimCase,
    NaryClaimEvent,
    NaryClaimFixture,
    Polarity,
    ProjectionAnnotation,
    ProjectionEligibilityStatus,
    SourceIdentity,
    SourceLocator,
    SourceSpan,
    SupportedProjection,
    ValueAnnotation,
    ValueStatus,
)
from scripts.validation.claim_events.corpus_text import (
    canonical_fixture_bytes,
    is_redacted,
    rehydrate_fixture_payload,
)

SCHEMA_VERSION: Final = "tg04_nary_claim_benchmark.v1"
DEFAULT_DEVELOPMENT_FIXTURE_PATH: Final = Path(
    "scripts/validation/claim_events/fixtures/tg04_bionlp_ge_development_v1.json"
)
#: The digest of the *rehydrated* panel -- unchanged since the fixture was
#: frozen, and unchanged by the removal of its corpus text.  Rehydration is
#: exact, so this still pins the same 40 documents, 53 events and 419 exclusions
#: it always pinned, including the text the offsets address.
FROZEN_DEVELOPMENT_FIXTURE_SHA256: Final = (
    "26d67408a7a2446de5d36fca3f8a80a732b6519afe00e303c893eef3c824268d"
)
#: The digest of the bytes actually committed, which carry no corpus text.
#: Pinning both ends means neither our annotations nor the corpus revision they
#: describe can drift: the committed digest fixes the offsets and labels, and
#: the frozen digest above fixes the text those offsets resolve to.
REDACTED_DEVELOPMENT_FIXTURE_SHA256: Final = (
    "b13e9f83d2feddada80b121aa1dbf57ea9ff7991d4c3bb8001e1e6ab9d240026"
)
#: v2 repairs seven gold events whose polarity contradicted their own source.
#:
#: Each is the argument of a nested parent the importer dropped, and the
#: negation was annotated on that parent, so the retained child kept SUPPORT
#: while its sentence denied it -- an extractor reading the paper correctly was
#: scored wrong.  v1 stays sealed and byte-identical; only `polarity` differs,
#: on exactly seven of the 53 events.  See
#: `bionlp_import.POLARITY_ADJUDICATION_RECORD`.
#:
#: The gates still run on v1.  Moving them to v2 pins a different panel and
#: belongs in the evaluation preregistration alongside the primary-matcher
#: decision, not in the repair that produced it.
DEVELOPMENT_FIXTURE_V2_PATH: Final = Path(
    "scripts/validation/claim_events/fixtures/tg04_bionlp_ge_development_v2.json"
)
FROZEN_DEVELOPMENT_FIXTURE_V2_SHA256: Final = (
    "9a1b8e671cbc1b8a4abe790d110a0ff0edc6af65e7c88a459d3224db46c17c26"
)
REDACTED_DEVELOPMENT_FIXTURE_V2_SHA256: Final = (
    "d123860658b55ecab4cdbe7261bfb5b995bec1295c794f2a689264f975bbacce"
)
_REPO_ROOT: Final = Path(__file__).resolve().parents[3]
_LOCATOR_RE: Final = re.compile(r"^char:(?P<start>\d+)-(?P<end>\d+)$")
_EnumT = TypeVar("_EnumT", bound=StrEnum)


def load_fixture(path: Path, *, corpus: Path | None = None) -> NaryClaimFixture:
    """Load and validate one fixture, rehydrating restricted text if needed.

    A committed fixture carries no corpus text, so it is rejoined with the
    fetched corpus first.  `sha256` is always the digest of the text-bearing
    fixture, redacted or not, so a gate pinning the panel keeps pinning the
    same bytes it pinned before the text was removed.

    `corpus` names the extracted documents to rejoin with.  Callers that hold
    one particular copy -- the importer, which has just extracted the archive
    it was given and verified its digest -- must pass it, or validation is
    performed against whatever `ARTANA_BIONLP_GE_CORPUS` or the default cache
    happens to hold, which is a different corpus than the one under test.
    """

    raw_bytes = path.read_bytes()
    payload = _object(_decode_json(raw_bytes), "fixture")
    if is_redacted(payload):
        # Hash the rehydrated panel, not the committed bytes, so digests pinned
        # before the corpus text was removed keep pinning the same panel.
        payload = _object(rehydrate_fixture_payload(payload, root=corpus), "fixture")
        raw_bytes = canonical_fixture_bytes(payload)
    _require_keys(payload, {"schema_version", "metadata", "cases"}, "fixture")
    schema_version = _string(payload, "schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"unknown TG-04 fixture schema_version: {schema_version}")
    raw_cases = _array(payload["cases"], "cases")
    if not raw_cases:
        raise ValueError("TG-04 fixture must contain at least one case")
    cases = tuple(_parse_case(item) for item in raw_cases)
    case_ids = tuple(case.case_id for case in cases)
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("TG-04 fixture case IDs must be unique")
    fixture = NaryClaimFixture(
        path=path,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        schema_version=schema_version,
        metadata=_parse_metadata(payload["metadata"]),
        cases=cases,
    )
    if not fixture.eligible_events:
        raise ValueError("TG-04 fixture must contain at least one eligible event")
    return fixture


def load_fixture_payload(path: Path) -> dict[str, object]:
    """Return the text-bearing fixture JSON, rehydrating a committed fixture.

    For callers that work on the raw payload rather than the parsed contracts.
    Raises `RestrictedCorpusUnavailableError` if the corpus is not present.
    """

    payload = _object(_decode_json(path.read_bytes()), "fixture")
    if is_redacted(payload):
        return _object(rehydrate_fixture_payload(payload), "fixture")
    return payload


def require_frozen_development_fixture(fixture: NaryClaimFixture) -> None:
    """Require the exact expert corpus panel used for model/task development."""

    expected_path = (_REPO_ROOT / DEFAULT_DEVELOPMENT_FIXTURE_PATH).resolve()
    fixture_path = getattr(fixture, "path", None)
    if not isinstance(fixture_path, Path) or fixture_path.resolve() != expected_path:
        raise ValueError("TG-04 development gates require the frozen fixture path")
    if fixture.sha256 != FROZEN_DEVELOPMENT_FIXTURE_SHA256:
        raise ValueError("TG-04 development gates require the frozen fixture hash")
    committed = hashlib.sha256(expected_path.read_bytes()).hexdigest()
    if committed != REDACTED_DEVELOPMENT_FIXTURE_SHA256:
        raise ValueError("TG-04 development gates require the committed fixture hash")
    if fixture.metadata.purpose != "frozen_expert_event_development_panel":
        raise ValueError("TG-04 development gates require development panel metadata")


def _parse_metadata(raw: object) -> BenchmarkMetadata:
    record = _object(raw, "metadata")
    _require_keys(
        record,
        {
            "purpose",
            "selection_method",
            "value_labels",
            "projection_labels",
            "production_semantic_policy_imported",
            "selected_document_ids",
            "excluded_nested_document_ids",
            "excluded_no_eligible_document_ids",
            "empty_control_document_ids",
            "true_negative_control_document_ids",
            "representability_stress_document_ids",
            "event_exclusions",
        },
        "metadata",
    )
    return BenchmarkMetadata(
        purpose=_string(record, "purpose"),
        selection_method=_string(record, "selection_method"),
        value_labels=_string(record, "value_labels"),
        projection_labels=_string(record, "projection_labels"),
        production_semantic_policy_imported=_boolean(
            record,
            "production_semantic_policy_imported",
        ),
        selected_document_ids=tuple(
            _plain_string(item, "selected document ID")
            for item in _array(record["selected_document_ids"], "selected_document_ids")
        ),
        excluded_nested_document_ids=tuple(
            _plain_string(item, "excluded nested document ID")
            for item in _array(
                record["excluded_nested_document_ids"],
                "excluded_nested_document_ids",
            )
        ),
        excluded_no_eligible_document_ids=tuple(
            _plain_string(item, "excluded no-eligible document ID")
            for item in _array(
                record["excluded_no_eligible_document_ids"],
                "excluded_no_eligible_document_ids",
            )
        ),
        empty_control_document_ids=tuple(
            _plain_string(item, "empty control document ID")
            for item in _array(
                record["empty_control_document_ids"],
                "empty_control_document_ids",
            )
        ),
        true_negative_control_document_ids=tuple(
            _plain_string(item, "true negative control document ID")
            for item in _array(
                record["true_negative_control_document_ids"],
                "true_negative_control_document_ids",
            )
        ),
        representability_stress_document_ids=tuple(
            _plain_string(item, "representability stress document ID")
            for item in _array(
                record["representability_stress_document_ids"],
                "representability_stress_document_ids",
            )
        ),
        event_exclusions=tuple(
            _parse_event_exclusion(item)
            for item in _array(record["event_exclusions"], "event_exclusions")
        ),
    )


def _parse_event_exclusion(raw: object) -> BenchmarkEventExclusion:
    record = _object(raw, "event exclusion")
    _require_keys(
        record,
        {
            "document_id",
            "event_id",
            "event_type",
            "reason",
            "annotation_references",
        },
        "event exclusion",
    )
    return BenchmarkEventExclusion(
        document_id=_string(record, "document_id"),
        event_id=_string(record, "event_id"),
        event_type=_string(record, "event_type"),
        reason=_string(record, "reason"),
        annotation_references=tuple(
            _plain_string(item, "annotation reference")
            for item in _array(
                record["annotation_references"],
                "annotation_references",
            )
        ),
    )


def _parse_case(raw: object) -> NaryClaimCase:
    record = _object(raw, "case")
    _require_keys(
        record,
        {"case_id", "title", "source", "source_text", "events", "control_status"},
        "case",
    )
    source_text = _string(record, "source_text")
    raw_events = _array(record["events"], "events")
    events = tuple(_parse_event(item, source_text) for item in raw_events)
    return NaryClaimCase(
        case_id=_string(record, "case_id"),
        title=_string(record, "title"),
        source=_parse_source_identity(record["source"]),
        source_text=source_text,
        events=events,
        control_status=_category(record, "control_status", CaseControlStatus),
    )


def _parse_source_identity(raw: object) -> SourceIdentity:
    record = _object(raw, "source identity")
    _require_keys(
        record,
        {"corpus", "document_id", "source_url", "archive_sha256", "mapping_version"},
        "source identity",
    )
    return SourceIdentity(
        corpus=_string(record, "corpus"),
        document_id=_string(record, "document_id"),
        source_url=_string(record, "source_url"),
        archive_sha256=_string(record, "archive_sha256"),
        mapping_version=_string(record, "mapping_version"),
    )


def _parse_event(raw: object, source_text: str) -> NaryClaimEvent:
    record = _object(raw, "event")
    _require_keys(
        record,
        {
            "event_id",
            "source_span",
            "source_locator",
            "trigger_span",
            "trigger_source_start",
            "event_type",
            "polarity",
            "epistemic_status",
            "arguments",
            "value_status",
            "value_reason",
            "framing_decision",
            "projection_adjudication",
            "supported_projections",
            "annotation_provenance",
            "eligible_for_event_metrics",
        },
        "event",
    )
    source = SourceSpan(
        locator=_parse_locator(_string(record, "source_locator")),
        exact_span=_string(record, "source_span"),
    )
    _validate_bound_source_span(source, source_text)
    trigger = ExactTrigger(
        exact_span=_string(record, "trigger_span"),
        source_start=_integer(record, "trigger_source_start"),
    )
    _require_contained(trigger.exact_span, source.exact_span, "trigger span")
    trigger_end = trigger.source_start + len(trigger.exact_span)
    if source_text[trigger.source_start : trigger_end] != trigger.exact_span:
        raise ValueError("trigger source_start does not bind its exact span")
    if not (
        source.locator.start <= trigger.source_start < trigger_end <= source.locator.end
    ):
        raise ValueError("trigger source offsets are outside the event source span")
    raw_arguments = _array(record["arguments"], "arguments")
    arguments = tuple(_parse_argument(item) for item in raw_arguments)
    if len(set(arguments)) != len(arguments):
        raise ValueError("claim arguments must be unique")
    for argument in arguments:
        _require_contained(argument.exact_span, source.exact_span, "argument span")
        argument_end = argument.source_start + len(argument.exact_span)
        if source_text[argument.source_start : argument_end] != argument.exact_span:
            raise ValueError("argument source_start does not bind its exact span")
        if not (
            source.locator.start
            <= argument.source_start
            < argument_end
            <= source.locator.end
        ):
            raise ValueError(
                "argument source offsets are outside the event source span"
            )
    supported = tuple(
        _parse_projection(item)
        for item in _array(record["supported_projections"], "supported_projections")
    )
    if len(set(supported)) != len(supported):
        raise ValueError("supported projections must be unique")
    return NaryClaimEvent(
        event_id=_string(record, "event_id"),
        source=source,
        trigger=trigger,
        event_type=_category(record, "event_type", BenchmarkEventType),
        polarity=_category(record, "polarity", Polarity),
        epistemic_status=_category(record, "epistemic_status", EpistemicStatus),
        arguments=frozenset(arguments),
        value=ValueAnnotation(
            status=_category(record, "value_status", ValueStatus),
            reason=_optional_string(record, "value_reason"),
        ),
        framing_decision=_category(record, "framing_decision", FramingDecision),
        projections=ProjectionAnnotation(
            status=_category(
                record,
                "projection_adjudication",
                ProjectionEligibilityStatus,
            ),
            supported=supported,
        ),
        provenance=_parse_provenance(record["annotation_provenance"]),
        eligibility=BenchmarkEligibility(
            status=(
                BenchmarkEligibilityStatus.ELIGIBLE
                if _boolean(record, "eligible_for_event_metrics")
                else BenchmarkEligibilityStatus.INELIGIBLE
            ),
        ),
    )


def _parse_argument(raw: object) -> ClaimArgument:
    record = _object(raw, "argument")
    _require_keys(
        record,
        {
            "argument_id",
            "event_role",
            "participant_role",
            "exact_span",
            "source_start",
        },
        "argument",
    )
    return ClaimArgument(
        argument_id=_string(record, "argument_id"),
        event_role=_category(record, "event_role", EventRole),
        participant_role=_category(record, "participant_role", ArtanaParticipantRole),
        exact_span=_string(record, "exact_span"),
        source_start=_integer(record, "source_start"),
    )


def _parse_projection(raw: object) -> SupportedProjection:
    record = _object(raw, "supported projection")
    _require_keys(
        record,
        {"subject_argument_id", "relation_type", "object_argument_id"},
        "supported projection",
    )
    return SupportedProjection(
        subject_argument_id=_string(record, "subject_argument_id"),
        relation_type=_string(record, "relation_type"),
        object_argument_id=_string(record, "object_argument_id"),
    )


def _parse_provenance(raw: object) -> AnnotationProvenance:
    record = _object(raw, "annotation provenance")
    _require_keys(
        record,
        {
            "event_annotation_id",
            "trigger_annotation_id",
            "argument_annotation_ids",
            "annotation_status",
        },
        "annotation provenance",
    )
    return AnnotationProvenance(
        event_annotation_id=_string(record, "event_annotation_id"),
        trigger_annotation_id=_string(record, "trigger_annotation_id"),
        argument_annotation_ids=tuple(
            _plain_string(item, "argument annotation ID")
            for item in _array(
                record["argument_annotation_ids"],
                "argument_annotation_ids",
            )
        ),
        status=_category(record, "annotation_status", AnnotationStatus),
    )


def _parse_locator(raw: str) -> SourceLocator:
    match = _LOCATOR_RE.fullmatch(raw)
    if match is None:
        raise ValueError("source_locator must use char:<start>-<end>")
    return SourceLocator(start=int(match["start"]), end=int(match["end"]))


def _validate_bound_source_span(span: SourceSpan, source_text: str) -> None:
    if span.locator.end > len(source_text):
        raise ValueError("source span ends outside source text")
    if source_text[span.locator.start : span.locator.end] != span.exact_span:
        raise ValueError("source span locator does not bind its exact span")


def _require_contained(span: str, source_region: str, label: str) -> None:
    if span not in source_region:
        raise ValueError(f"{label} is not bound to the event source span")


def _decode_json(raw_bytes: bytes) -> object:
    try:
        return cast("object", json.loads(raw_bytes))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("TG-04 fixture must be valid UTF-8 JSON") from exc


def _object(raw: object, label: str) -> dict[str, object]:
    if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
        raise TypeError(f"{label} must be an object with string keys")
    return cast("dict[str, object]", raw)


def _array(raw: object, label: str) -> list[object]:
    if not isinstance(raw, list):
        raise TypeError(f"{label} must be a list")
    return cast("list[object]", raw)


def _string(record: dict[str, object], key: str) -> str:
    return _plain_string(record.get(key), key)


def _plain_string(raw: object, label: str) -> str:
    if not isinstance(raw, str) or raw.strip() == "":
        raise TypeError(f"{label} must be a nonempty string")
    return raw


def _optional_string(record: dict[str, object], key: str) -> str | None:
    value = record.get(key)
    if value is None:
        return None
    return _plain_string(value, key)


def _boolean(record: dict[str, object], key: str) -> bool:
    value = record.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be a boolean")
    return value


def _integer(record: dict[str, object], key: str) -> int:
    value = record.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TypeError(f"{key} must be a nonnegative integer")
    return value


def _category(
    record: dict[str, object],
    key: str,
    enum_type: type[_EnumT],
) -> _EnumT:
    raw = _string(record, key)
    try:
        return enum_type(raw)
    except ValueError as exc:
        raise ValueError(f"unknown {key} category: {raw}") from exc


def _require_keys(record: dict[str, object], expected: set[str], label: str) -> None:
    actual = set(record)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise ValueError(f"{label} keys mismatch: missing={missing}, unknown={unknown}")


__all__ = [
    "DEFAULT_DEVELOPMENT_FIXTURE_PATH",
    "DEVELOPMENT_FIXTURE_V2_PATH",
    "FROZEN_DEVELOPMENT_FIXTURE_SHA256",
    "FROZEN_DEVELOPMENT_FIXTURE_V2_SHA256",
    "REDACTED_DEVELOPMENT_FIXTURE_SHA256",
    "REDACTED_DEVELOPMENT_FIXTURE_V2_SHA256",
    "SCHEMA_VERSION",
    "load_fixture",
    "load_fixture_payload",
    "require_frozen_development_fixture",
]
