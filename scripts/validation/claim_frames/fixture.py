"""Frozen TG-03 ClaimFrame fixture loading and benchmark validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, cast

QUALIFIER_FIELDS: Final[tuple[str, ...]] = (
    "biological_or_variant_state",
    "population",
    "intervention",
    "comparator",
    "outcome",
    "study_design",
    "treatment_setting",
    "timeframe",
    "threshold",
)
POLARITY_CATEGORIES: Final = frozenset(
    {"SUPPORT", "REFUTE", "UNCERTAIN", "HYPOTHESIS", "NULL_RESULT"},
)
EPISTEMIC_STATUS_CATEGORIES: Final = frozenset(
    {"ASSERTED", "PROVISIONAL", "UNCERTAIN", "HYPOTHESIS", "NULL_RESULT"},
)
QUALIFIER_STATE_CATEGORIES: Final = frozenset(
    {"PRESENT", "NOT_APPLICABLE", "UNRESOLVED"},
)
ADJUDICATION_STATUS_CATEGORIES: Final = frozenset({"adjudicated", "unresolved"})
DEFAULT_SOURCE_LOCATOR: Final = "normalized_extraction_text"
LEGACY_METHODOLOGY_REASON: Final = (
    "legacy fixture lacks explicit adjudication, promotion, and source-measurement gold"
)
_METHODOLOGY_COMPLETE_SCHEMAS: Final = frozenset(
    {"tg03_qualifier_benchmark.v3", "tg03_qualifier_benchmark.v4"},
)
REQUIRED_GATE_SCHEMA: Final = "tg03_qualifier_benchmark.v4"
REQUIRED_GATE_FIXTURE_SHA256: Final = (
    "b09c84fbc76642436a68c34ca9630636de36c78f077504e128a66662dc1b5888"
)
_REPO_ROOT: Final = Path(__file__).resolve().parents[3]
_SEALED_BASE_FIXTURE: Final = (
    "scripts/validation/claim_frames/fixtures/tg03_qualifier_holdout_v2.json",
    "22fbdf50333811d52e26296e9f1ddd561bfe0f29b0ed7d3771017199552ab956",
)
_SEALED_METHODOLOGY_EVIDENCE: Final = {
    "tg03_qualifier_benchmark.v3": (
        "docs/validation/reports/tg03-qualified-claim-frame-runs/"
        "tg03-holdout-v2-to-v3-methodology-adjudication.json",
        "7e7b0625258d0576816e2c1f0556797015446f77f5b9f913e1f343599f5f7cf3",
        "v2_to_v3",
    ),
    "tg03_qualifier_benchmark.v4": (
        "docs/validation/reports/tg03-qualified-claim-frame-runs/"
        "tg03-holdout-v3-to-v4-measurement-adjudication.json",
        "da9c01ea84e14284a16789b6cf36403c1d3570d8049dc045ad64b92b49ef418a",
        "v3_to_v4",
    ),
}
DEFAULT_FIXTURE_PATH = Path(
    "scripts/validation/claim_frames/fixtures/tg03_qualifier_holdout_v4.json",
)


def require_gate_fixture(fixture: BenchmarkFixture) -> None:
    """Require the one sealed methodology profile authorized for TG-03 gates."""

    if fixture.schema_version != REQUIRED_GATE_SCHEMA:
        raise ValueError(f"TG-03 merge gates require {REQUIRED_GATE_SCHEMA}")
    if fixture.sha256 != REQUIRED_GATE_FIXTURE_SHA256:
        raise ValueError("TG-03 merge-gate fixture hash is not the sealed v4 hash")
    if fixture.path.resolve() != (_REPO_ROOT / DEFAULT_FIXTURE_PATH).resolve():
        raise ValueError("TG-03 merge gates require the repository-sealed v4 fixture")


@dataclass(frozen=True, slots=True)
class ExpectedQualifier:
    """Categorical expected state and optional source-bound qualifier value."""

    state: str
    value: str | None
    exact_span: str | None


@dataclass(frozen=True, slots=True)
class ExpectedSourceMeasurement:
    """Independent gold identity for one literal source measurement."""

    value: str
    source_locator: str
    literal_span: str
    field_name: str
    unit: str
    extraction_method: str


@dataclass(frozen=True, slots=True)
class ExpectedFrame:
    """One expected source-local semantic frame."""

    frame_id: str
    subject: str
    predicate: str
    object: str
    source_span: str
    source_locator: str
    polarity: str
    epistemic_status: str
    qualifiers: dict[str, ExpectedQualifier]
    promotion_eligible: bool | None
    source_measurements: tuple[ExpectedSourceMeasurement, ...]


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One frozen source text and its expected categorical frames."""

    case_id: str
    title: str
    category: str
    source_text: str
    frames: tuple[ExpectedFrame, ...]
    adjudication_status: str | None
    unresolved_frame_ids: tuple[str, ...]

    @property
    def included_in_quality_metrics(self) -> bool:
        """Return whether gold is adjudicated enough for quality denominators."""

        return self.adjudication_status == "adjudicated"


@dataclass(frozen=True, slots=True)
class BenchmarkFixture:
    """Fixture plus the hash and completeness of its exact methodology."""

    path: Path
    sha256: str
    schema_version: str
    cases: tuple[BenchmarkCase, ...]
    methodology_complete: bool
    methodology_incomplete_reason: str | None
    base_fixture_sha256: str | None = None
    base_fixture_path: Path | None = None
    methodology_evidence_path: Path | None = None
    methodology_evidence_sha256: str | None = None


def load_fixture(path: Path = DEFAULT_FIXTURE_PATH) -> BenchmarkFixture:
    """Load a frozen fixture without network, model, or production-policy access."""

    raw_bytes = path.read_bytes()
    payload = _json_object(raw_bytes, "TG-03 fixture")
    schema_version = _required_string(payload, "schema_version")
    if schema_version in _METHODOLOGY_COMPLETE_SCHEMAS:
        return _load_v3_fixture(path=path, raw_bytes=raw_bytes, payload=payload)
    return _load_legacy_fixture(
        path=path,
        raw_bytes=raw_bytes,
        payload=payload,
        schema_version=schema_version,
    )


def _load_v3_fixture(
    *,
    path: Path,
    raw_bytes: bytes,
    payload: dict[str, object],
) -> BenchmarkFixture:
    base_record = _object(payload.get("base_fixture"), "base_fixture")
    path = _sealed_repo_file(path, "TG-03 methodology fixture", allow_absolute=True)
    expected_base_path, expected_base_sha256 = _SEALED_BASE_FIXTURE
    if _required_string(base_record, "path") != expected_base_path:
        raise ValueError("TG-03 complete fixtures must use the sealed v2 base path")
    if _required_string(base_record, "sha256") != expected_base_sha256:
        raise ValueError("TG-03 complete fixtures must use the sealed v2 base hash")
    base_path = _sealed_repo_file(
        _required_string(base_record, "path"),
        "TG-03 base fixture",
    )
    base_bytes = base_path.read_bytes()
    base_sha256 = hashlib.sha256(base_bytes).hexdigest()
    if base_sha256 != _required_string(base_record, "sha256"):
        raise ValueError("TG-03 v3 base fixture hash does not match sealed bytes")
    if _required_string(base_record, "schema_version") != "tg03_qualifier_benchmark.v2":
        raise ValueError("TG-03 v3 base fixture record must declare schema v2")
    base_payload = _json_object(base_bytes, "TG-03 v3 base fixture")
    if (
        _required_string(base_payload, "schema_version")
        != "tg03_qualifier_benchmark.v2"
    ):
        raise ValueError("TG-03 v3 must be based on the immutable v2 fixture")
    legacy = _load_legacy_fixture(
        path=base_path,
        raw_bytes=base_bytes,
        payload=base_payload,
        schema_version="tg03_qualifier_benchmark.v2",
    )
    methodology_path, methodology_sha256 = _validate_methodology_evidence(
        schema_version=_required_string(payload, "schema_version"),
        fixture_path=path,
        fixture_sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )

    raw_methodology = payload.get("case_methodology")
    if not isinstance(raw_methodology, list):
        raise TypeError("TG-03 v3 case_methodology must be a list")
    methodology = {
        _required_string(record, "case_id"): record
        for item in raw_methodology
        for record in (_object(item, "case methodology"),)
    }
    if len(methodology) != len(raw_methodology):
        raise ValueError("TG-03 v3 case methodology IDs must be unique")
    expected_case_ids = {case.case_id for case in legacy.cases}
    if set(methodology) != expected_case_ids:
        raise ValueError("TG-03 v3 methodology must cover every v2 case exactly once")

    cases = tuple(
        _apply_case_methodology(case, methodology[case.case_id])
        for case in legacy.cases
    )
    return BenchmarkFixture(
        path=path,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        schema_version=_required_string(payload, "schema_version"),
        cases=cases,
        methodology_complete=True,
        methodology_incomplete_reason=None,
        base_fixture_sha256=base_sha256,
        base_fixture_path=base_path,
        methodology_evidence_path=methodology_path,
        methodology_evidence_sha256=methodology_sha256,
    )


def _load_legacy_fixture(
    *,
    path: Path,
    raw_bytes: bytes,
    payload: dict[str, object],
    schema_version: str,
) -> BenchmarkFixture:
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("TG-03 fixture must contain a non-empty cases list")
    cases = tuple(_parse_legacy_case(raw_case) for raw_case in raw_cases)
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("TG-03 fixture case IDs must be unique")
    return BenchmarkFixture(
        path=path,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        schema_version=schema_version,
        cases=cases,
        methodology_complete=False,
        methodology_incomplete_reason=LEGACY_METHODOLOGY_REASON,
    )


def _parse_legacy_case(raw_case: object) -> BenchmarkCase:
    payload = _object(raw_case, "case")
    raw_frames = payload.get("expected_frames")
    if not isinstance(raw_frames, list) or not raw_frames:
        raise ValueError("each TG-03 case must contain expected_frames")
    source_text = _required_string(payload, "source_text")
    frames = tuple(_parse_legacy_frame(item) for item in raw_frames)
    _validate_source_bindings(source_text, frames)
    return BenchmarkCase(
        case_id=_required_string(payload, "case_id"),
        title=_required_string(payload, "title"),
        category=_required_string(payload, "category"),
        source_text=source_text,
        frames=frames,
        adjudication_status=None,
        unresolved_frame_ids=(),
    )


def _parse_legacy_frame(raw_frame: object) -> ExpectedFrame:
    payload = _object(raw_frame, "expected frame")
    polarity = _required_string(payload, "polarity")
    epistemic_status = _required_string(payload, "epistemic_status")
    _closed(polarity, POLARITY_CATEGORIES, "polarity")
    _closed(epistemic_status, EPISTEMIC_STATUS_CATEGORIES, "epistemic_status")
    source_locator = payload.get("source_locator", DEFAULT_SOURCE_LOCATOR)
    if not isinstance(source_locator, str) or not source_locator:
        raise ValueError("expected frame source_locator must be a non-empty string")
    raw_qualifiers = payload.get("qualifiers", {})
    if not isinstance(raw_qualifiers, dict):
        raise TypeError("expected frame qualifiers must be an object")
    unknown_fields = set(raw_qualifiers) - set(QUALIFIER_FIELDS)
    if unknown_fields:
        raise ValueError(f"unknown qualifier fields: {sorted(unknown_fields)}")
    return ExpectedFrame(
        frame_id=_required_string(payload, "frame_id"),
        subject=_required_string(payload, "subject"),
        predicate=_required_string(payload, "predicate"),
        object=_required_string(payload, "object"),
        source_span=_required_string(payload, "source_span"),
        source_locator=source_locator,
        polarity=polarity,
        epistemic_status=epistemic_status,
        qualifiers={
            field: _parse_qualifier(raw_qualifiers.get(field))
            for field in QUALIFIER_FIELDS
        },
        promotion_eligible=None,
        source_measurements=(),
    )


def _apply_case_methodology(
    case: BenchmarkCase,
    raw_methodology: dict[str, object],
) -> BenchmarkCase:
    adjudication_status = _required_string(raw_methodology, "adjudication_status")
    _closed(
        adjudication_status,
        ADJUDICATION_STATUS_CATEGORIES,
        "adjudication_status",
    )
    unresolved_frame_ids = _string_tuple(
        raw_methodology.get("unresolved_frame_ids", []),
        "unresolved_frame_ids",
    )
    case_frame_ids = {frame.frame_id for frame in case.frames}
    if not set(unresolved_frame_ids) <= case_frame_ids:
        raise ValueError(f"unknown unresolved frame IDs for case {case.case_id}")
    if (adjudication_status == "unresolved") != bool(unresolved_frame_ids):
        raise ValueError(
            "unresolved cases must identify unresolved_frame_ids and adjudicated cases must not",
        )

    raw_frames = raw_methodology.get("frames")
    if not isinstance(raw_frames, list):
        raise TypeError("TG-03 v3 case methodology frames must be a list")
    frame_methodology = {
        _required_string(record, "frame_id"): record
        for item in raw_frames
        for record in (_object(item, "frame methodology"),)
    }
    if set(frame_methodology) != case_frame_ids or len(frame_methodology) != len(
        raw_frames
    ):
        raise ValueError(
            f"TG-03 v3 methodology must cover every frame in {case.case_id}"
        )
    frames = tuple(
        _apply_frame_methodology(
            frame,
            frame_methodology[frame.frame_id],
            source_text=case.source_text,
        )
        for frame in case.frames
    )
    return replace(
        case,
        frames=frames,
        adjudication_status=adjudication_status,
        unresolved_frame_ids=unresolved_frame_ids,
    )


def _apply_frame_methodology(
    frame: ExpectedFrame,
    raw_methodology: dict[str, object],
    *,
    source_text: str,
) -> ExpectedFrame:
    promotion_eligible = raw_methodology.get("promotion_eligible")
    if not isinstance(promotion_eligible, bool):
        raise TypeError("TG-03 v3 promotion_eligible must be boolean")
    raw_measurements = raw_methodology.get("expected_source_measurements")
    if not isinstance(raw_measurements, list):
        raise TypeError(
            "TG-03 v3 expected_source_measurements must be an explicit list"
        )
    measurements = tuple(
        _parse_source_measurement(item, source_text=source_text, frame=frame)
        for item in raw_measurements
    )
    return replace(
        frame,
        promotion_eligible=promotion_eligible,
        source_measurements=measurements,
    )


def _parse_source_measurement(
    raw_measurement: object,
    *,
    source_text: str,
    frame: ExpectedFrame,
) -> ExpectedSourceMeasurement:
    payload = _object(raw_measurement, "expected source measurement")
    if payload.get("origin") != "source_measurement":
        raise ValueError(
            "expected source measurement origin must be source_measurement"
        )
    measurement = ExpectedSourceMeasurement(
        value=_required_string(payload, "value"),
        source_locator=_required_string(payload, "source_locator"),
        literal_span=_required_string(payload, "literal_span"),
        field_name=_required_string(payload, "field_name"),
        unit=_required_string(payload, "unit"),
        extraction_method=_required_string(payload, "extraction_method"),
    )
    if measurement.source_locator != frame.source_locator:
        raise ValueError("expected source measurement locator must match its frame")
    if source_text.count(measurement.literal_span) != 1:
        raise ValueError("expected source measurement span must occur exactly once")
    if frame.source_span.count(measurement.literal_span) != 1:
        raise ValueError("expected source measurement must be inside its frame span")
    if measurement.value not in measurement.literal_span:
        raise ValueError("expected source measurement value must occur in literal_span")
    return measurement


def _parse_qualifier(raw_qualifier: object) -> ExpectedQualifier:
    if raw_qualifier is None:
        return ExpectedQualifier(state="NOT_APPLICABLE", value=None, exact_span=None)
    payload = _object(raw_qualifier, "qualifier")
    state = _required_string(payload, "state")
    _closed(state, QUALIFIER_STATE_CATEGORIES, "qualifier state")
    value = _optional_string(payload.get("value"))
    exact_span = _optional_string(payload.get("exact_span"))
    if state == "PRESENT" and (value is None or exact_span is None):
        raise ValueError("PRESENT qualifiers require value and exact_span")
    if state != "PRESENT" and (value is not None or exact_span is not None):
        raise ValueError("absent qualifiers cannot contain value or exact_span")
    return ExpectedQualifier(state=state, value=value, exact_span=exact_span)


def _validate_source_bindings(
    source_text: str,
    frames: tuple[ExpectedFrame, ...],
) -> None:
    for frame in frames:
        if source_text.count(frame.source_span) != 1:
            raise ValueError(
                f"source_span for {frame.frame_id} must occur exactly once"
            )
        normalized_span = frame.source_span.casefold()
        if frame.subject.casefold() not in normalized_span:
            raise ValueError(
                f"source_span for {frame.frame_id} must contain the subject"
            )
        if frame.object.casefold() not in normalized_span:
            raise ValueError(
                f"source_span for {frame.frame_id} must contain the object"
            )
        for field, qualifier in frame.qualifiers.items():
            if qualifier.state != "PRESENT":
                continue
            if (
                qualifier.exact_span is None
                or source_text.count(qualifier.exact_span) != 1
            ):
                raise ValueError(
                    f"qualifier {field} for {frame.frame_id} is not uniquely source-bound",
                )
            if qualifier.value is None or qualifier.value not in qualifier.exact_span:
                raise ValueError(
                    f"qualifier {field} for {frame.frame_id} lacks value binding"
                )
            if qualifier.exact_span not in frame.source_span:
                raise ValueError(
                    f"qualifier {field} for {frame.frame_id} is outside source_span"
                )


def _validate_methodology_evidence(
    *,
    schema_version: str,
    fixture_path: Path,
    fixture_sha256: str,
) -> tuple[Path, str]:
    try:
        evidence_path_text, expected_sha256, transition = _SEALED_METHODOLOGY_EVIDENCE[
            schema_version
        ]
    except KeyError as exc:
        raise ValueError(
            f"no sealed methodology evidence is registered for {schema_version}",
        ) from exc
    if "PLACEHOLDER" in expected_sha256:
        raise RuntimeError("TG-03 methodology evidence hash is not sealed")
    evidence_path = _sealed_repo_file(evidence_path_text, "TG-03 methodology evidence")
    evidence_bytes = evidence_path.read_bytes()
    actual_sha256 = hashlib.sha256(evidence_bytes).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError("TG-03 methodology evidence hash does not match sealed bytes")
    evidence = _json_object(evidence_bytes, "TG-03 methodology evidence")
    if _required_string(evidence, "transition") != transition:
        raise ValueError("TG-03 methodology evidence transition does not match fixture")
    if evidence.get("source_cases_changed") is not False:
        raise ValueError(
            "TG-03 methodology evidence must declare unchanged source cases"
        )
    to_record = _object(evidence.get("to"), "TG-03 methodology evidence to record")
    if _repo_relative_path(fixture_path) != _required_string(to_record, "path"):
        raise ValueError(
            "TG-03 methodology evidence target path does not match fixture"
        )
    if _required_string(to_record, "sha256") != fixture_sha256:
        raise ValueError("TG-03 methodology evidence target hash does not match")
    return evidence_path, actual_sha256


def _sealed_repo_file(
    raw_path: Path | str,
    label: str,
    *,
    allow_absolute: bool = False,
) -> Path:
    path = Path(raw_path)
    if path.is_absolute() and not allow_absolute:
        raise ValueError(f"{label} path must be repository-relative")
    candidate = path if path.is_absolute() else _REPO_ROOT / path
    resolved = candidate.resolve()
    repo_root = _REPO_ROOT.resolve()
    if resolved == repo_root or repo_root not in resolved.parents:
        raise ValueError(f"{label} path must remain inside the repository")
    if not resolved.is_file():
        raise FileNotFoundError(f"{label} path is not a file: {path}")
    return resolved


def _repo_relative_path(path: Path) -> str:
    return path.resolve().relative_to(_REPO_ROOT.resolve()).as_posix()


def _json_object(raw_bytes: bytes, label: str) -> dict[str, object]:
    return _object(json.loads(raw_bytes), label)


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a JSON object")
    return cast("dict[str, object]", value)


def _required_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("optional qualifier fields must be non-empty strings")
    return value.strip()


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise TypeError(f"{label} must be a list of non-empty strings")
    output = tuple(cast("list[str]", value))
    if len(output) != len(set(output)):
        raise ValueError(f"{label} must contain unique values")
    return output


def _closed(value: str, choices: frozenset[str], label: str) -> None:
    if value not in choices:
        raise ValueError(f"unknown {label}: {value}")


__all__ = [
    "ADJUDICATION_STATUS_CATEGORIES",
    "BenchmarkCase",
    "BenchmarkFixture",
    "DEFAULT_FIXTURE_PATH",
    "DEFAULT_SOURCE_LOCATOR",
    "EPISTEMIC_STATUS_CATEGORIES",
    "ExpectedFrame",
    "ExpectedQualifier",
    "ExpectedSourceMeasurement",
    "LEGACY_METHODOLOGY_REASON",
    "POLARITY_CATEGORIES",
    "QUALIFIER_FIELDS",
    "QUALIFIER_STATE_CATEGORIES",
    "REQUIRED_GATE_FIXTURE_SHA256",
    "REQUIRED_GATE_SCHEMA",
    "load_fixture",
    "require_gate_fixture",
]
