"""Deterministic validation for agent-owned claim falsification and repair."""

from __future__ import annotations

import builtins
import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Final

from artana_evidence_api.document_extraction_support.claim_frames.arguments import (
    ClaimArgument,
    ClaimArgumentRole,
)
from artana_evidence_api.document_extraction_support.claim_frames.contracts import (
    ClaimFrame,
    ClaimQualifier,
    ClaimSourceMeasurement,
    EpistemicStatus,
    Polarity,
)
from artana_evidence_api.document_extraction_support.claim_frames.normalization import (
    ClaimFrameNormalizationError,
    normalize_claim_frame,
)
from artana_evidence_api.document_extraction_support.full_text_chunking import (
    sentence_boundary_end_offsets,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SHA256_HEX_LENGTH = 64


class VerificationVerdict(str, Enum):
    ENTAILED = "ENTAILED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT = "INSUFFICIENT"
    ABSTAIN = "ABSTAIN"


class ParticipantRoleFinding(str, Enum):
    FAITHFUL = "FAITHFUL"
    INCORRECT = "INCORRECT"
    AMBIGUOUS = "AMBIGUOUS"


class ApplicabilityFinding(str, Enum):
    FAITHFUL = "FAITHFUL"
    INCORRECT = "INCORRECT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class BinaryFinding(str, Enum):
    FAITHFUL = "FAITHFUL"
    INCORRECT = "INCORRECT"


class CompletenessFinding(str, Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    AMBIGUOUS = "AMBIGUOUS"


class ObservedStatisticalEvidence(str, Enum):
    P_VALUE = "P_VALUE"
    CONFIDENCE_INTERVAL = "CONFIDENCE_INTERVAL"
    EFFECT_ESTIMATE = "EFFECT_ESTIMATE"
    NONE = "NONE"


class AuthorStatisticalClaim(str, Enum):
    SIGNIFICANT = "SIGNIFICANT"
    NOT_SIGNIFICANT = "NOT_SIGNIFICANT"
    NOT_CLAIMED = "NOT_CLAIMED"


class VerificationFailureAxis(str, Enum):
    PARTICIPANT_ROLES = "PARTICIPANT_ROLES"
    DIRECTION = "DIRECTION"
    COMPARISON = "COMPARISON"
    POLARITY = "POLARITY"
    UNCERTAINTY = "UNCERTAINTY"
    STATISTICAL_INTERPRETATION = "STATISTICAL_INTERPRETATION"
    MODIFIER = "MODIFIER"
    CORE_EVENT = "CORE_EVENT"
    PRIMARY_PARTICIPANT = "PRIMARY_PARTICIPANT"
    UNSUPPORTED_EVIDENCE = "UNSUPPORTED_EVIDENCE"
    AMBIGUOUS_SOURCE_SCOPE = "AMBIGUOUS_SOURCE_SCOPE"
    NEW_EVENT_REQUIRED = "NEW_EVENT_REQUIRED"


class ClaimVerificationTerminal(str, Enum):
    VERIFIED_UNREPAIRED = "VERIFIED_UNREPAIRED"
    VERIFIED_AFTER_REPAIR = "VERIFIED_AFTER_REPAIR"
    REVIEW_ONLY = "REVIEW_ONLY"
    INVALID_VERIFICATION = "INVALID_VERIFICATION"


class VerificationModelRelationship(str, Enum):
    SAME_MODEL_FRESH_CALL = "SAME_MODEL_FRESH_CALL"
    DIFFERENT_CONFIGURED_MODEL_UNCONFIRMED = "DIFFERENT_CONFIGURED_MODEL_UNCONFIRMED"


class ClaimVerificationOutput(BaseModel):
    """Categorical, source-only output authored by the verifier agent."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    verdict: VerificationVerdict = Field(..., strict=False)
    participant_roles: ParticipantRoleFinding = Field(..., strict=False)
    direction: ApplicabilityFinding = Field(..., strict=False)
    comparison: ApplicabilityFinding = Field(..., strict=False)
    polarity: BinaryFinding = Field(..., strict=False)
    uncertainty: BinaryFinding = Field(..., strict=False)
    statistical_interpretation: ApplicabilityFinding = Field(..., strict=False)
    observed_statistical_evidence: ObservedStatisticalEvidence = Field(
        ...,
        strict=False,
    )
    author_statistical_claim: AuthorStatisticalClaim = Field(..., strict=False)
    statistical_evidence_spans: tuple[str, ...] = Field(default=(), max_length=16)
    statistical_cue_spans: tuple[str, ...] = Field(default=(), max_length=16)
    statistical_literal_spans: tuple[str, ...] = Field(default=(), max_length=16)
    author_claim_evidence_spans: tuple[str, ...] = Field(default=(), max_length=16)
    completeness: CompletenessFinding = Field(..., strict=False)
    evidence_spans: tuple[str, ...] = Field(..., min_length=1, max_length=16)
    explanation: str = Field(..., min_length=1, max_length=2000)
    failure_axes: tuple[VerificationFailureAxis, ...] = Field(
        default=(),
        max_length=16,
    )

    @field_validator(
        "evidence_spans",
        "statistical_evidence_spans",
        "statistical_cue_spans",
        "statistical_literal_spans",
        "author_claim_evidence_spans",
        mode="before",
    )
    @classmethod
    def restore_evidence_tuple(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("failure_axes", mode="before")
    @classmethod
    def restore_failure_axis_tuple(cls, value: object) -> object:
        if isinstance(value, list | tuple):
            return tuple(VerificationFailureAxis(item) for item in value)
        return value

    @model_validator(mode="after")
    def require_unique_evidence_and_axes(self) -> ClaimVerificationOutput:
        if len(set(self.evidence_spans)) != len(self.evidence_spans):
            raise ValueError("verification evidence spans must be unique")
        if len(set(self.failure_axes)) != len(self.failure_axes):
            raise ValueError("verification failure axes must be unique")
        if any(
            len(set(spans)) != len(spans)
            for spans in (
                self.statistical_evidence_spans,
                self.statistical_cue_spans,
                self.statistical_literal_spans,
                self.author_claim_evidence_spans,
            )
        ):
            raise ValueError("statistical evidence spans must be unique")
        return self


class ClaimQualifierPatch(BaseModel):
    """One named modifier update with no access to event identity."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    field_name: str = Field(
        ...,
        pattern=(
            "^(biological_or_variant_state|condition|population|intervention|"
            "comparator|outcome|study_design|treatment_setting|timeframe|threshold)$"
        ),
    )
    value: ClaimQualifier


class ClaimSemanticPatch(BaseModel):
    """Axis-limited patch; absence of core-event fields is intentional."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    subject: str | None = Field(default=None, min_length=1, max_length=1000)
    object: str | None = Field(default=None, min_length=1, max_length=1000)
    polarity: Polarity | None = Field(default=None, strict=False)
    epistemic_status: EpistemicStatus | None = Field(default=None, strict=False)
    assertion_arguments: tuple[ClaimArgument, ...] | None = Field(
        default=None,
        max_length=32,
    )
    source_measurements: tuple[ClaimSourceMeasurement, ...] | None = Field(
        default=None,
        max_length=64,
    )
    qualifier_updates: tuple[ClaimQualifierPatch, ...] | None = Field(
        default=None,
        max_length=10,
    )
    evidence_spans: tuple[str, ...] = Field(..., min_length=1, max_length=16)
    explanation: str = Field(..., min_length=1, max_length=2000)

    @field_validator(
        "assertion_arguments",
        "source_measurements",
        "qualifier_updates",
        "evidence_spans",
        mode="before",
    )
    @classmethod
    def restore_patch_tuples(cls, value: builtins.object) -> builtins.object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def require_one_unique_change(self) -> ClaimSemanticPatch:
        changes = (
            self.subject,
            self.object,
            self.polarity,
            self.epistemic_status,
            self.assertion_arguments,
            self.source_measurements,
            self.qualifier_updates,
        )
        if all(change is None for change in changes):
            raise ValueError("claim semantic patch must change at least one field")
        if len(set(self.evidence_spans)) != len(self.evidence_spans):
            raise ValueError("repair evidence spans must be unique")
        qualifier_updates = self.qualifier_updates or ()
        names = tuple(update.field_name for update in qualifier_updates)
        if len(set(names)) != len(names):
            raise ValueError("repair qualifier fields must be unique")
        return self


class ClaimFalsificationValidationError(ValueError):
    """Verifier or repair output violated a deterministic boundary."""


@dataclass(frozen=True, slots=True)
class ValidatedClaimVerification:
    finding: ClaimVerificationOutput
    evidence_offsets: tuple[tuple[int, int], ...]
    statistical_evidence_offsets: tuple[tuple[int, int], ...]
    statistical_cue_offsets: tuple[tuple[int, int], ...]
    statistical_literal_offsets: tuple[tuple[int, int], ...]
    author_claim_evidence_offsets: tuple[tuple[int, int], ...]
    source_region_sha256: str
    claim_sha256: str

    @property
    def fully_verified(self) -> bool:
        finding = self.finding
        return (
            finding.verdict is VerificationVerdict.ENTAILED
            and finding.participant_roles is ParticipantRoleFinding.FAITHFUL
            and finding.direction
            in {ApplicabilityFinding.FAITHFUL, ApplicabilityFinding.NOT_APPLICABLE}
            and finding.comparison
            in {ApplicabilityFinding.FAITHFUL, ApplicabilityFinding.NOT_APPLICABLE}
            and finding.polarity is BinaryFinding.FAITHFUL
            and finding.uncertainty is BinaryFinding.FAITHFUL
            and finding.statistical_interpretation
            in {ApplicabilityFinding.FAITHFUL, ApplicabilityFinding.NOT_APPLICABLE}
            and finding.completeness is CompletenessFinding.COMPLETE
            and not finding.failure_axes
        )

    @property
    def repairable(self) -> bool:
        finding = self.finding
        return (
            finding.verdict is VerificationVerdict.ENTAILED
            and finding.participant_roles is not ParticipantRoleFinding.AMBIGUOUS
            and finding.completeness is not CompletenessFinding.AMBIGUOUS
            and bool(finding.failure_axes)
            and set(finding.failure_axes).issubset(_REPAIRABLE_FAILURE_AXES)
        )


@dataclass(frozen=True, slots=True)
class AppliedClaimRepair:
    original_claim_sha256: str
    repaired_claim_sha256: str
    repaired_frame: ClaimFrame
    evidence_offsets: tuple[tuple[int, int], ...]
    source_region_sha256: str
    changed_fields: tuple[str, ...]


_REPAIRABLE_FAILURE_AXES: Final = frozenset(
    {
        VerificationFailureAxis.PARTICIPANT_ROLES,
        VerificationFailureAxis.DIRECTION,
        VerificationFailureAxis.COMPARISON,
        VerificationFailureAxis.POLARITY,
        VerificationFailureAxis.UNCERTAINTY,
        VerificationFailureAxis.STATISTICAL_INTERPRETATION,
        VerificationFailureAxis.MODIFIER,
    },
)
_AXIS_FIELDS: Final = {
    VerificationFailureAxis.PARTICIPANT_ROLES: frozenset({"assertion_arguments"}),
    VerificationFailureAxis.DIRECTION: frozenset({"subject", "object"}),
    VerificationFailureAxis.COMPARISON: frozenset({"qualifier_updates"}),
    VerificationFailureAxis.POLARITY: frozenset({"polarity"}),
    VerificationFailureAxis.UNCERTAINTY: frozenset({"epistemic_status"}),
    VerificationFailureAxis.STATISTICAL_INTERPRETATION: frozenset(
        {"source_measurements"},
    ),
    VerificationFailureAxis.MODIFIER: frozenset({"qualifier_updates"}),
}
_QUALIFIER_ARGUMENT_ROLES: Final = {
    "comparator": ClaimArgumentRole.COMPARATOR,
    "study_design": ClaimArgumentRole.STUDY_DESIGN,
    "treatment_setting": ClaimArgumentRole.TREATMENT_SETTING,
    "timeframe": ClaimArgumentRole.TIMEFRAME,
    "threshold": ClaimArgumentRole.MEASUREMENT,
}


def validate_claim_verification(
    *,
    output: ClaimVerificationOutput,
    claim_frame: ClaimFrame,
    source_region: str,
    expected_source_sha256: str,
    expected_claim_sha256: str,
) -> ValidatedClaimVerification:
    """Bind categorical verifier output without changing its scientific meaning."""

    _require_sha256(expected_source_sha256, label="source")
    if claim_frame.semantic_fingerprint != expected_claim_sha256:
        raise ClaimFalsificationValidationError(
            "claim hash changed before verification"
        )
    _require_sha256(expected_claim_sha256, label="claim")
    _require_atomic_event_scope(claim_frame.source_evidence.exact_span)
    evidence_offsets = _resolve_evidence_spans(
        output.evidence_spans,
        source_region=source_region,
        claim_evidence=claim_frame.source_evidence.exact_span,
    )
    statistical_evidence_offsets = _resolve_evidence_spans(
        output.statistical_evidence_spans,
        source_region=source_region,
        claim_evidence=claim_frame.source_evidence.exact_span,
    )
    statistical_cue_offsets = _resolve_evidence_spans(
        output.statistical_cue_spans,
        source_region=source_region,
        claim_evidence=claim_frame.source_evidence.exact_span,
    )
    statistical_literal_offsets = _resolve_evidence_spans(
        output.statistical_literal_spans,
        source_region=source_region,
        claim_evidence=claim_frame.source_evidence.exact_span,
    )
    author_claim_evidence_offsets = _resolve_evidence_spans(
        output.author_claim_evidence_spans,
        source_region=source_region,
        claim_evidence=claim_frame.source_evidence.exact_span,
    )
    _require_endpoint_evidence(output=output, claim_frame=claim_frame)
    _require_categorical_consistency(output)
    return ValidatedClaimVerification(
        finding=output,
        evidence_offsets=evidence_offsets,
        statistical_evidence_offsets=statistical_evidence_offsets,
        statistical_cue_offsets=statistical_cue_offsets,
        statistical_literal_offsets=statistical_literal_offsets,
        author_claim_evidence_offsets=author_claim_evidence_offsets,
        source_region_sha256=hashlib.sha256(source_region.encode()).hexdigest(),
        claim_sha256=expected_claim_sha256,
    )


def apply_claim_semantic_patch(
    *,
    original_frame: ClaimFrame,
    patch: ClaimSemanticPatch,
    authorized_failure_axes: tuple[VerificationFailureAxis, ...],
    source_region: str,
    expected_source_sha256: str,
) -> AppliedClaimRepair:
    """Apply only authorized fields and rebind every source-bearing value."""

    _require_sha256(expected_source_sha256, label="source")
    if not authorized_failure_axes or not set(authorized_failure_axes).issubset(
        _REPAIRABLE_FAILURE_AXES,
    ):
        raise ClaimFalsificationValidationError("claim failure is not repairable")
    changed_fields = _patch_changed_fields(
        patch=patch,
        original_frame=original_frame,
    )
    if not changed_fields:
        raise ClaimFalsificationValidationError("claim patch does not change the claim")
    allowed_fields = frozenset().union(
        *(_AXIS_FIELDS[axis] for axis in authorized_failure_axes),
    )
    if not set(changed_fields).issubset(allowed_fields):
        raise ClaimFalsificationValidationError(
            "claim patch changed a field outside failure_axes",
        )
    _require_direction_is_exact_swap(original_frame=original_frame, patch=patch)
    _require_secondary_role_only_patch(original_frame=original_frame, patch=patch)
    _require_qualifier_updates_are_axis_limited(
        original_frame=original_frame,
        patch=patch,
        authorized_failure_axes=authorized_failure_axes,
    )
    evidence_offsets = _resolve_evidence_spans(
        patch.evidence_spans,
        source_region=source_region,
        claim_evidence=original_frame.source_evidence.exact_span,
    )
    update = _frame_update_payload(patch)
    repaired = original_frame.model_copy(update=update)
    try:
        repaired = normalize_claim_frame(
            repaired,
            source_region,
            expected_source_hash=expected_source_sha256,
        )
    except ClaimFrameNormalizationError as exc:
        raise ClaimFalsificationValidationError(str(exc)) from exc
    if repaired.predicate != original_frame.predicate:
        raise ClaimFalsificationValidationError("repair changed the core relation type")
    if repaired.semantic_fingerprint == original_frame.semantic_fingerprint:
        raise ClaimFalsificationValidationError(
            "claim repair produced an unchanged claim"
        )
    return AppliedClaimRepair(
        original_claim_sha256=original_frame.semantic_fingerprint,
        repaired_claim_sha256=repaired.semantic_fingerprint,
        repaired_frame=repaired,
        evidence_offsets=evidence_offsets,
        source_region_sha256=hashlib.sha256(source_region.encode()).hexdigest(),
        changed_fields=changed_fields,
    )


def verifier_model_relationship(
    *,
    first_model_id: str,
    second_model_id: str,
) -> VerificationModelRelationship:
    if first_model_id == second_model_id:
        return VerificationModelRelationship.SAME_MODEL_FRESH_CALL
    return VerificationModelRelationship.DIFFERENT_CONFIGURED_MODEL_UNCONFIRMED


def _require_categorical_consistency(output: ClaimVerificationOutput) -> None:
    expected = _expected_axis_failures(output)
    actual = set(output.failure_axes)
    if not expected.issubset(actual):
        raise ClaimFalsificationValidationError(
            "verifier failure_axes omit an incorrect categorical field",
        )
    _require_failure_axes_are_justified(
        output=output,
        expected=expected,
        actual=actual,
    )
    if output.verdict is VerificationVerdict.ENTAILED and not actual and expected:
        raise ClaimFalsificationValidationError(
            "entailed verifier result is inconsistent"
        )
    _require_statistical_evidence_contract(output)


def _expected_axis_failures(
    output: ClaimVerificationOutput,
) -> set[VerificationFailureAxis]:
    expected: set[VerificationFailureAxis] = set()
    if output.participant_roles is not ParticipantRoleFinding.FAITHFUL:
        expected.add(VerificationFailureAxis.PARTICIPANT_ROLES)
    if output.direction is ApplicabilityFinding.INCORRECT:
        expected.add(VerificationFailureAxis.DIRECTION)
    if output.comparison is ApplicabilityFinding.INCORRECT:
        expected.add(VerificationFailureAxis.COMPARISON)
    if output.polarity is BinaryFinding.INCORRECT:
        expected.add(VerificationFailureAxis.POLARITY)
    if output.uncertainty is BinaryFinding.INCORRECT:
        expected.add(VerificationFailureAxis.UNCERTAINTY)
    if output.statistical_interpretation is ApplicabilityFinding.INCORRECT:
        expected.add(VerificationFailureAxis.STATISTICAL_INTERPRETATION)
    return expected


def _require_failure_axes_are_justified(
    *,
    output: ClaimVerificationOutput,
    expected: set[VerificationFailureAxis],
    actual: set[VerificationFailureAxis],
) -> None:
    completeness_reasons = {
        VerificationFailureAxis.MODIFIER,
        VerificationFailureAxis.NEW_EVENT_REQUIRED,
        VerificationFailureAxis.AMBIGUOUS_SOURCE_SCOPE,
    }
    if (
        output.completeness is not CompletenessFinding.COMPLETE
        and not actual & completeness_reasons
    ):
        raise ClaimFalsificationValidationError(
            "incomplete verification lacks a categorical completeness reason",
        )
    justified = set(expected)
    if output.completeness is not CompletenessFinding.COMPLETE:
        justified.update(completeness_reasons)
    if output.participant_roles is not ParticipantRoleFinding.FAITHFUL:
        justified.add(VerificationFailureAxis.PRIMARY_PARTICIPANT)
    if output.verdict is not VerificationVerdict.ENTAILED:
        justified.update(
            {
                VerificationFailureAxis.CORE_EVENT,
                VerificationFailureAxis.PRIMARY_PARTICIPANT,
                VerificationFailureAxis.UNSUPPORTED_EVIDENCE,
                VerificationFailureAxis.AMBIGUOUS_SOURCE_SCOPE,
                VerificationFailureAxis.NEW_EVENT_REQUIRED,
            },
        )
    if not actual.issubset(justified):
        raise ClaimFalsificationValidationError(
            "verifier failure_axes include an unsupported categorical failure",
        )


def _require_endpoint_evidence(
    *,
    output: ClaimVerificationOutput,
    claim_frame: ClaimFrame,
) -> None:
    if output.participant_roles is ParticipantRoleFinding.FAITHFUL and not any(
        _contains_exact_endpoint(span, claim_frame.subject)
        and _contains_exact_endpoint(span, claim_frame.object)
        for span in output.evidence_spans
    ):
        raise ClaimFalsificationValidationError(
            "faithful participant finding lacks both primary participants",
        )


def _contains_exact_endpoint(span: str, endpoint: str) -> bool:
    pattern = re.compile(rf"(?<!\w){re.escape(endpoint)}(?!\w)")
    return len(tuple(pattern.finditer(span))) == 1


def _require_statistical_evidence_contract(output: ClaimVerificationOutput) -> None:
    statistical_spans = output.statistical_evidence_spans
    cue_spans = output.statistical_cue_spans
    literal_spans = output.statistical_literal_spans
    author_spans = output.author_claim_evidence_spans
    if (output.observed_statistical_evidence is ObservedStatisticalEvidence.NONE) != (
        not statistical_spans and not cue_spans and not literal_spans
    ):
        raise ClaimFalsificationValidationError(
            "observed statistical category and evidence spans are inconsistent",
        )
    if output.observed_statistical_evidence is not ObservedStatisticalEvidence.NONE:
        if not statistical_spans or not cue_spans or not literal_spans:
            raise ClaimFalsificationValidationError(
                "statistical observation requires evidence, cue, and literal spans",
            )
        if any(
            re.search(r"(?<!\w)[+-]?(?:\d+(?:\.\d+)?|\.\d+)", span) is None
            for span in literal_spans
        ):
            raise ClaimFalsificationValidationError(
                "statistical literal span must contain an exact numeric literal",
            )
        if not all(
            any(cue in evidence for evidence in statistical_spans) for cue in cue_spans
        ) or not all(
            any(literal in evidence for evidence in statistical_spans)
            for literal in literal_spans
        ):
            raise ClaimFalsificationValidationError(
                "statistical cue and literal must belong to statistical evidence",
            )
    if (output.author_statistical_claim is AuthorStatisticalClaim.NOT_CLAIMED) != (
        not author_spans
    ):
        raise ClaimFalsificationValidationError(
            "author statistical claim and evidence spans are inconsistent",
        )
    if not set(statistical_spans + author_spans).issubset(output.evidence_spans):
        raise ClaimFalsificationValidationError(
            "statistical evidence must be included in verification evidence",
        )


def _require_atomic_event_scope(claim_evidence: str) -> None:
    normalized_end = len(claim_evidence.rstrip())
    boundaries = sentence_boundary_end_offsets(claim_evidence)
    if len(boundaries) > 1 or any(end < normalized_end for end in boundaries):
        raise ClaimFalsificationValidationError(
            "claim evidence must contain exactly one atomic sentence",
        )


def _resolve_evidence_spans(
    spans: tuple[str, ...],
    *,
    source_region: str,
    claim_evidence: str,
) -> tuple[tuple[int, int], ...]:
    offsets: list[tuple[int, int]] = []
    for span in spans:
        if source_region.count(span) != 1:
            raise ClaimFalsificationValidationError(
                "evidence span must resolve exactly once inside claim-local source",
            )
        if span not in claim_evidence:
            raise ClaimFalsificationValidationError(
                "evidence span is outside the framed claim evidence",
            )
        start = source_region.index(span)
        offsets.append((start, start + len(span)))
    return tuple(offsets)


def _patch_changed_fields(
    *,
    patch: ClaimSemanticPatch,
    original_frame: ClaimFrame,
) -> tuple[str, ...]:
    changed = [
        field
        for field in (
            "subject",
            "object",
            "polarity",
            "epistemic_status",
            "assertion_arguments",
            "source_measurements",
            "qualifier_updates",
        )
        if getattr(patch, field) is not None
        and field != "qualifier_updates"
        and getattr(patch, field) != getattr(original_frame, field)
    ]
    if any(
        update.value != getattr(original_frame, update.field_name)
        for update in patch.qualifier_updates or ()
    ):
        changed.append("qualifier_updates")
    return tuple(changed)


def _require_direction_is_exact_swap(
    *,
    original_frame: ClaimFrame,
    patch: ClaimSemanticPatch,
) -> None:
    if patch.subject is None and patch.object is None:
        return
    if patch.subject is None or patch.object is None:
        raise ClaimFalsificationValidationError(
            "direction repair requires both endpoints",
        )
    if (patch.subject, patch.object) != (original_frame.object, original_frame.subject):
        raise ClaimFalsificationValidationError(
            "direction repair may only swap the original endpoints",
        )


def _require_secondary_role_only_patch(
    *,
    original_frame: ClaimFrame,
    patch: ClaimSemanticPatch,
) -> None:
    repaired = patch.assertion_arguments
    if repaired is None:
        return
    original_by_span = {
        argument.exact_span: argument for argument in original_frame.assertion_arguments
    }
    repaired_by_span = {argument.exact_span: argument for argument in repaired}
    if set(original_by_span) != set(repaired_by_span):
        raise ClaimFalsificationValidationError(
            "participant-role repair changed the participant inventory",
        )
    for primary_span in (original_frame.subject, original_frame.object):
        if repaired_by_span.get(primary_span) != original_by_span.get(primary_span):
            raise ClaimFalsificationValidationError(
                "participant-role repair changed a primary participant",
            )


def _require_qualifier_updates_are_axis_limited(
    *,
    original_frame: ClaimFrame,
    patch: ClaimSemanticPatch,
    authorized_failure_axes: tuple[VerificationFailureAxis, ...],
) -> None:
    updates = patch.qualifier_updates or ()
    if not updates:
        return
    allowed_fields: set[str] = set()
    if VerificationFailureAxis.COMPARISON in authorized_failure_axes:
        allowed_fields.add("comparator")
    if VerificationFailureAxis.MODIFIER in authorized_failure_axes:
        allowed_fields.update(
            {"study_design", "treatment_setting", "timeframe", "threshold"},
        )
    argument_roles_by_span = {
        argument.exact_span: argument.role
        for argument in original_frame.assertion_arguments
    }
    for update in updates:
        if update.field_name not in allowed_fields:
            raise ClaimFalsificationValidationError(
                "qualifier repair may not change event identity or participants",
            )
        existing = getattr(original_frame, update.field_name)
        if existing.value in {original_frame.subject, original_frame.object}:
            raise ClaimFalsificationValidationError(
                "qualifier repair may not change a primary participant",
            )
        if (
            update.value.value is None
            or update.value.exact_span is None
            or argument_roles_by_span.get(update.value.exact_span)
            is not _QUALIFIER_ARGUMENT_ROLES[update.field_name]
        ):
            raise ClaimFalsificationValidationError(
                "qualifier repair requires an existing source-bound argument",
            )


def _frame_update_payload(patch: ClaimSemanticPatch) -> dict[str, object]:
    payload: dict[str, object] = {}
    for field in (
        "subject",
        "object",
        "polarity",
        "epistemic_status",
        "assertion_arguments",
        "source_measurements",
    ):
        value = getattr(patch, field)
        if value is not None:
            payload[field] = value
    for qualifier_patch in patch.qualifier_updates or ():
        payload[qualifier_patch.field_name] = qualifier_patch.value
    return payload


def _require_sha256(value: str, *, label: str) -> None:
    if len(value) != _SHA256_HEX_LENGTH or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ClaimFalsificationValidationError(f"{label} hash must be SHA-256")


__all__ = [
    "ApplicabilityFinding",
    "AppliedClaimRepair",
    "AuthorStatisticalClaim",
    "BinaryFinding",
    "ClaimFalsificationValidationError",
    "ClaimQualifierPatch",
    "ClaimSemanticPatch",
    "ClaimVerificationOutput",
    "ClaimVerificationTerminal",
    "CompletenessFinding",
    "ObservedStatisticalEvidence",
    "ParticipantRoleFinding",
    "ValidatedClaimVerification",
    "VerificationFailureAxis",
    "VerificationModelRelationship",
    "VerificationVerdict",
    "apply_claim_semantic_patch",
    "validate_claim_verification",
    "verifier_model_relationship",
]
