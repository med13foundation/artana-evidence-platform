"""Immutable contracts for qualified claims extracted from source text."""

from __future__ import annotations

import builtins
import hashlib
import json
from enum import Enum
from typing import Final, Literal

from artana_evidence_api.document_extraction_support.claim_frames.arguments import (
    ClaimArgument,
)
from artana_evidence_api.runtime.agent_output_schema import SourceMeasurementNumber
from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class Polarity(str, Enum):
    """Closed direction of the claim's source-local finding."""

    SUPPORT = "SUPPORT"
    REFUTE = "REFUTE"
    UNCERTAIN = "UNCERTAIN"
    HYPOTHESIS = "HYPOTHESIS"
    NULL_RESULT = "NULL_RESULT"


class EpistemicStatus(str, Enum):
    """Closed statement status, separate from the direction of a finding."""

    ASSERTED = "ASSERTED"
    PROVISIONAL = "PROVISIONAL"
    UNCERTAIN = "UNCERTAIN"
    HYPOTHESIS = "HYPOTHESIS"
    NULL_RESULT = "NULL_RESULT"


class QualifierState(str, Enum):
    """Whether a material qualifier has source-backed content."""

    PRESENT = "PRESENT"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNRESOLVED = "UNRESOLVED"


class MeasurementFieldRole(str, Enum):
    """Closed semantic role for a literal source measurement."""

    THRESHOLD = "THRESHOLD"
    TIMEFRAME = "TIMEFRAME"
    OUTCOME = "OUTCOME"
    DOSAGE = "DOSAGE"
    POPULATION_SIZE = "POPULATION_SIZE"
    OTHER = "OTHER"


class SourceEvidenceSpan(BaseModel):
    """One exact source excerpt and its stable source-local locator."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        populate_by_name=True,
    )

    exact_span: str = Field(
        ...,
        min_length=1,
        max_length=12000,
        validation_alias=AliasChoices("exact_span", "evidence_span", "span"),
    )
    locator: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        validation_alias=AliasChoices("locator", "source_locator"),
    )

    @property
    def span(self) -> str:
        """Return the exact excerpt using the concise terminology."""
        return self.exact_span

    @property
    def source_locator(self) -> str:
        """Return the stable locator used by source-bound measurements."""
        return self.locator


class ClaimSourceMeasurement(SourceMeasurementNumber):
    """Immutable source measurement accepted by a qualified ClaimFrame."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        json_schema_extra={"x-artana-numeric-origin": "source_measurement"},
    )

    source_hash: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    field_name: MeasurementFieldRole = Field(..., strict=False)
    extraction_method: Literal["agent_exact_copy"] = "agent_exact_copy"


class ClaimQualifier(BaseModel):
    """A material qualifier with explicit absence and evidence semantics."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        populate_by_name=True,
    )

    state: QualifierState = Field(
        ...,
        strict=False,
        validation_alias=AliasChoices("state", "status"),
    )
    value: str | None = Field(default=None, max_length=4000)
    exact_span: str | None = Field(
        default=None,
        max_length=12000,
        validation_alias=AliasChoices("exact_span", "evidence_span", "span"),
    )

    @model_validator(mode="after")
    def validate_state_content(self) -> ClaimQualifier:
        """Prevent absent qualifiers from carrying invented source content."""
        value = self.value
        exact_span = self.exact_span
        has_value = value is not None
        has_span = exact_span is not None
        if self.state is QualifierState.PRESENT:
            if not has_value or not has_span:
                raise ValueError(
                    "present qualifiers require both value and exact_span",
                )
            if value is None or exact_span is None:
                raise AssertionError("present qualifier narrowing failed")
            if value.strip() == "" or exact_span.strip() == "":
                raise ValueError(
                    "present qualifiers require nonempty value and exact_span",
                )
        elif has_value or has_span:
            raise ValueError(
                "not_applicable and unresolved qualifiers cannot carry content",
            )
        return self

    @classmethod
    def present(cls, *, value: str, exact_span: str) -> ClaimQualifier:
        """Build a qualifier whose value must later be bound to source text."""
        return cls(state=QualifierState.PRESENT, value=value, exact_span=exact_span)

    @classmethod
    def not_applicable(cls) -> ClaimQualifier:
        """Build a qualifier that does not apply to this claim."""
        return cls(state=QualifierState.NOT_APPLICABLE)

    @classmethod
    def unresolved(cls) -> ClaimQualifier:
        """Build a qualifier that extraction could not resolve."""
        return cls(state=QualifierState.UNRESOLVED)

    @property
    def evidence_span(self) -> str | None:
        """Return the exact qualifier excerpt, if one is present."""
        return self.exact_span


Qualifier: Final = ClaimQualifier
_MIN_ASSERTION_ARGUMENTS: Final = 2

_QUALIFIER_FIELDS: Final[tuple[str, ...]] = (
    "biological_or_variant_state",
    "condition",
    "population",
    "intervention",
    "comparator",
    "outcome",
    "study_design",
    "treatment_setting",
    "timeframe",
    "threshold",
)


class ClaimFrame(BaseModel):
    """Complete, lossless extraction frame for one source-local claim."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        populate_by_name=True,
    )

    subject: str = Field(..., min_length=1, max_length=1000)
    predicate: str = Field(..., min_length=1, max_length=1000)
    object: str = Field(..., min_length=1, max_length=1000)
    source_evidence: SourceEvidenceSpan = Field(
        ...,
        validation_alias=AliasChoices("source_evidence", "evidence"),
    )
    polarity: Polarity = Field(..., strict=False)
    epistemic_status: EpistemicStatus = Field(..., strict=False)
    assertion_arguments: tuple[ClaimArgument, ...] = Field(
        default=(),
        max_length=32,
    )
    biological_or_variant_state: ClaimQualifier
    condition: ClaimQualifier = Field(default_factory=ClaimQualifier.unresolved)
    population: ClaimQualifier
    intervention: ClaimQualifier
    comparator: ClaimQualifier
    outcome: ClaimQualifier
    study_design: ClaimQualifier
    treatment_setting: ClaimQualifier
    timeframe: ClaimQualifier
    threshold: ClaimQualifier
    source_measurements: tuple[ClaimSourceMeasurement, ...] = Field(
        default=(),
        max_length=64,
    )
    extraction_rationale: str = Field(..., min_length=1, max_length=4000)

    @field_validator("source_measurements", mode="before")
    @classmethod
    def restore_measurement_tuple(
        cls,
        value: builtins.object,
    ) -> builtins.object:
        """Restore the immutable tuple after a JSON persistence round trip."""

        return tuple(value) if isinstance(value, list) else value

    @field_validator("assertion_arguments", mode="before")
    @classmethod
    def restore_argument_tuple(cls, value: builtins.object) -> builtins.object:
        """Restore immutable typed arguments after a JSON persistence round trip."""

        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_assertion_arguments(self) -> ClaimFrame:
        """Reject partial or duplicate n-ary argument persistence."""

        if not self.assertion_arguments:
            return self
        if (
            len({argument.exact_span for argument in self.assertion_arguments})
            < _MIN_ASSERTION_ARGUMENTS
        ):
            raise ValueError("claim frame requires at least two distinct arguments")
        identities = tuple(
            (argument.role, argument.exact_span)
            for argument in self.assertion_arguments
        )
        if len(set(identities)) != len(identities):
            raise ValueError("claim frame arguments must be role/span unique")
        return self

    @property
    def evidence(self) -> SourceEvidenceSpan:
        """Return the source evidence envelope."""
        return self.source_evidence

    @property
    def source_locator(self) -> str:
        """Return the locator for the frame's exact source evidence."""
        return self.source_evidence.locator

    @property
    def semantic_fingerprint(self) -> str:
        """Return the stable digest of every serialized frame field."""
        semantic_payload = self.model_dump(mode="json")
        semantic_payload.pop("extraction_rationale")
        payload = json.dumps(
            semantic_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @property
    def dedupe_identity(self) -> str:
        """Return semantic identity while ignoring harmless qualifier boundaries."""

        payload = self.model_dump(mode="json")
        payload.pop("extraction_rationale")
        for field in _QUALIFIER_FIELDS:
            qualifier = payload[field]
            if isinstance(qualifier, dict):
                qualifier.pop("exact_span", None)
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @property
    def is_positive_projection_candidate(self) -> bool:
        """Return whether the source semantics could support a positive projection."""
        return (
            self.polarity is Polarity.SUPPORT
            and self.epistemic_status is EpistemicStatus.ASSERTED
            and all(
                getattr(self, field).state is not QualifierState.UNRESOLVED
                for field in _QUALIFIER_FIELDS
            )
            and any(
                getattr(self, field).state is QualifierState.PRESENT
                for field in _QUALIFIER_FIELDS
            )
        )

    @property
    def is_positive_projection_eligible(self) -> bool:
        """Return false until an independent agent verifies the complete frame.

        Extraction establishes source-bound categorical content, not semantic
        role correctness. Eligibility therefore belongs to the later verifier
        boundary and must never be inferred from an extraction frame alone.
        """

        return False


def claim_frame_semantic_fingerprint(frame: ClaimFrame) -> str:
    """Return a frame's deterministic semantic fingerprint."""
    return frame.semantic_fingerprint


def claim_frame_dedupe_identity(frame: ClaimFrame) -> str:
    """Return a frame's deterministic deduplication identity."""
    return frame.dedupe_identity


def is_positive_projection_eligible(frame: ClaimFrame) -> bool:
    """Return false because extraction alone cannot authorize projection."""
    return frame.is_positive_projection_eligible


def replace_claim_frame_projection(
    frame: ClaimFrame | None,
    *,
    subject: str | None = None,
    predicate: str | None = None,
    object_: str | None = None,
) -> ClaimFrame | None:
    """Update a compatibility projection without desynchronizing its frame."""

    if frame is None:
        return None
    return frame.model_copy(
        update={
            "subject": subject if subject is not None else frame.subject,
            "predicate": predicate if predicate is not None else frame.predicate,
            "object": object_ if object_ is not None else frame.object,
        },
    )


__all__ = [
    "ClaimFrame",
    "ClaimQualifier",
    "ClaimSourceMeasurement",
    "EpistemicStatus",
    "MeasurementFieldRole",
    "Polarity",
    "Qualifier",
    "QualifierState",
    "SourceEvidenceSpan",
    "SourceMeasurementNumber",
    "claim_frame_dedupe_identity",
    "claim_frame_semantic_fingerprint",
    "is_positive_projection_eligible",
    "replace_claim_frame_projection",
]
