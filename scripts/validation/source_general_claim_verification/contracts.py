"""Typed categorical contracts for the offline adjudication experiment."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SHA256_PATTERN = r"^[0-9a-f]{64}$"
Sha256 = Annotated[str, Field(pattern=SHA256_PATTERN)]


class StrictModel(BaseModel):
    """Reject undeclared evaluator fields and make accepted records immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class EventType(StrEnum):
    CLINICAL_OUTCOME = "CLINICAL_OUTCOME"
    GENETIC_ASSOCIATION = "GENETIC_ASSOCIATION"
    MOLECULAR_MECHANISM = "MOLECULAR_MECHANISM"
    THERAPEUTIC_RESPONSE = "THERAPEUTIC_RESPONSE"
    DIAGNOSTIC_FINDING = "DIAGNOSTIC_FINDING"
    NULL_FINDING = "NULL_FINDING"
    OTHER_SCIENTIFIC = "OTHER_SCIENTIFIC"


class ParticipantRole(StrEnum):
    PRIMARY_SUBJECT = "PRIMARY_SUBJECT"
    PRIMARY_OBJECT = "PRIMARY_OBJECT"
    INTERVENTION = "INTERVENTION"
    COMPARATOR = "COMPARATOR"
    POPULATION = "POPULATION"
    OUTCOME = "OUTCOME"
    VARIANT = "VARIANT"
    GENE = "GENE"
    CONDITION = "CONDITION"
    SECONDARY_PARTICIPANT = "SECONDARY_PARTICIPANT"


class Direction(StrEnum):
    INCREASED = "INCREASED"
    DECREASED = "DECREASED"
    UNCHANGED = "UNCHANGED"
    BIDIRECTIONAL = "BIDIRECTIONAL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    AMBIGUOUS = "AMBIGUOUS"


class Comparison(StrEnum):
    GREATER_THAN = "GREATER_THAN"
    LESS_THAN = "LESS_THAN"
    EQUAL_TO = "EQUAL_TO"
    DIFFERENT_FROM = "DIFFERENT_FROM"
    NO_DIFFERENCE = "NO_DIFFERENCE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    AMBIGUOUS = "AMBIGUOUS"


class Polarity(StrEnum):
    AFFIRMED = "AFFIRMED"
    NEGATED = "NEGATED"
    NULL_RESULT = "NULL_RESULT"
    MIXED = "MIXED"
    AMBIGUOUS = "AMBIGUOUS"


class Uncertainty(StrEnum):
    ASSERTED = "ASSERTED"
    UNCERTAIN = "UNCERTAIN"
    HYPOTHESIS = "HYPOTHESIS"
    CONDITIONAL = "CONDITIONAL"
    ABSTAIN = "ABSTAIN"


class QuantitativeKind(StrEnum):
    COUNT = "COUNT"
    PERCENTAGE = "PERCENTAGE"
    CONTINUOUS_VALUE = "CONTINUOUS_VALUE"
    RATIO = "RATIO"
    RANGE = "RANGE"


class StatisticalObservation(StrEnum):
    P_VALUE = "P_VALUE"
    CONFIDENCE_INTERVAL = "CONFIDENCE_INTERVAL"
    EFFECT_ESTIMATE = "EFFECT_ESTIMATE"
    NONE = "NONE"


class AuthorInterpretation(StrEnum):
    SIGNIFICANT = "SIGNIFICANT"
    NOT_SIGNIFICANT = "NOT_SIGNIFICANT"
    NOT_CLAIMED = "NOT_CLAIMED"
    ABSTAIN = "ABSTAIN"


class ModifierAxis(StrEnum):
    COMPARISON_DIRECTION = "COMPARISON_DIRECTION"
    POLARITY = "POLARITY"
    UNCERTAINTY = "UNCERTAINTY"
    STATISTICAL_INTERPRETATION = "STATISTICAL_INTERPRETATION"
    SECONDARY_PARTICIPANT_ROLE = "SECONDARY_PARTICIPANT_ROLE"
    POPULATION = "POPULATION"
    INTERVENTION = "INTERVENTION"
    OUTCOME = "OUTCOME"
    TIMEFRAME = "TIMEFRAME"
    STUDY_CONTEXT = "STUDY_CONTEXT"


class CompletenessJudgment(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    AMBIGUOUS = "AMBIGUOUS"
    ABSTAIN = "ABSTAIN"


class AmbiguityKind(StrEnum):
    SOURCE_SCOPE = "SOURCE_SCOPE"
    PARTICIPANT_IDENTITY = "PARTICIPANT_IDENTITY"
    EVENT_BOUNDARY = "EVENT_BOUNDARY"
    RELATION_TYPE = "RELATION_TYPE"
    MISSING_CONTEXT = "MISSING_CONTEXT"
    OTHER = "OTHER"


class ReviewerRole(StrEnum):
    FIRST = "FIRST"
    SECOND = "SECOND"
    TIEBREAKER = "TIEBREAKER"


class VerifierDecision(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    ABSTAIN = "ABSTAIN"
    INVALID = "INVALID"


class ExperimentTerminal(StrEnum):
    VERIFIED_UNREPAIRED = "VERIFIED_UNREPAIRED"
    VERIFIED_AFTER_REPAIR = "VERIFIED_AFTER_REPAIR"
    REVIEW_ONLY = "REVIEW_ONLY"
    INVALID_VERIFICATION = "INVALID_VERIFICATION"


class RepairAttemptStatus(StrEnum):
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    PATCH_PRODUCED = "PATCH_PRODUCED"
    SCHEMA_FAILURE = "SCHEMA_FAILURE"
    REJECTED = "REJECTED"


class CaseKind(StrEnum):
    VALUABLE_CORRECT = "VALUABLE_CORRECT"
    CONTROLLED_MALFORMED = "CONTROLLED_MALFORMED"


class MalformedFamily(StrEnum):
    REVERSED_PARTICIPANT_ROLES = "REVERSED_PARTICIPANT_ROLES"
    MERGED_PARTICIPANTS = "MERGED_PARTICIPANTS"
    REVERSED_COMPARISON_OR_DIRECTION = "REVERSED_COMPARISON_OR_DIRECTION"
    NEGATION_INVERSION = "NEGATION_INVERSION"
    UNSUPPORTED_UNCERTAINTY = "UNSUPPORTED_UNCERTAINTY"
    STATISTICAL_INTERPRETATION_ERROR = "STATISTICAL_INTERPRETATION_ERROR"
    CROSS_EVENT_EVIDENCE = "CROSS_EVENT_EVIDENCE"
    MISSING_MODIFIER = "MISSING_MODIFIER"
    INVENTED_EVIDENCE = "INVENTED_EVIDENCE"
    INCOMPLETE_CLAIM = "INCOMPLETE_CLAIM"


class ExactSpan(StrictModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_order(self) -> ExactSpan:
        if self.end <= self.start:
            raise ValueError("span end must be greater than start")
        if self.end - self.start != len(self.text):
            raise ValueError("span offsets must have the same length as span text")
        return self


class SourceDocument(StrictModel):
    source_id: str = Field(min_length=1)
    source_sha256: Sha256
    text: str = Field(min_length=1)


class ExposedScope(StrictModel):
    scope_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_sha256: Sha256
    scope: ExactSpan


class CorpusArtifact(StrictModel):
    schema_version: Literal["source_general_claim_verification.corpus.v1"]
    exposed_only: Literal[True]
    sources: tuple[SourceDocument, ...] = Field(min_length=1)
    scopes: tuple[ExposedScope, ...] = Field(min_length=31, max_length=31)


class ReviewerIdentity(StrictModel):
    reviewer_id: str = Field(min_length=1)
    role: ReviewerRole
    model_id: str = Field(min_length=1)
    prompt_id: str = Field(min_length=1)
    prompt_sha256: Sha256


class Participant(StrictModel):
    participant_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    role: ParticipantRole
    evidence: ExactSpan
    explanation: str = Field(min_length=1)


class QuantitativeEvidence(StrictModel):
    kind: QuantitativeKind
    value_text: str = Field(min_length=1)
    unit_text: str | None = None
    evidence: ExactSpan
    explanation: str = Field(min_length=1)


class StatisticalEvidence(StrictModel):
    observation: StatisticalObservation
    observation_evidence: ExactSpan | None
    observation_explanation: str = Field(min_length=1)
    author_interpretation: AuthorInterpretation
    author_interpretation_evidence: ExactSpan | None
    author_interpretation_explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def separate_observation_from_interpretation(self) -> StatisticalEvidence:
        if self.observation is StatisticalObservation.NONE:
            if self.observation_evidence is not None:
                raise ValueError("NONE statistical observation cannot have evidence")
        elif self.observation_evidence is None:
            raise ValueError("a statistical observation requires exact evidence")
        if self.author_interpretation in {
            AuthorInterpretation.SIGNIFICANT,
            AuthorInterpretation.NOT_SIGNIFICANT,
        }:
            if self.author_interpretation_evidence is None:
                raise ValueError(
                    "author significance interpretation requires explicit source evidence",
                )
        elif self.author_interpretation_evidence is not None:
            raise ValueError(
                "NOT_CLAIMED or ABSTAIN cannot carry author-interpretation evidence",
            )
        return self


class RequiredModifier(StrictModel):
    axis: ModifierAxis
    category: str = Field(min_length=1)
    value_text: str | None = None
    evidence: ExactSpan
    explanation: str = Field(min_length=1)


class AmbiguityCondition(StrictModel):
    kind: AmbiguityKind
    explanation: str = Field(min_length=1)
    evidence: ExactSpan | None = None


class ClaimContent(StrictModel):
    event_text: str = Field(min_length=1)
    event_type: EventType
    event_evidence: ExactSpan
    event_type_explanation: str = Field(min_length=1)
    participants: tuple[Participant, ...] = Field(min_length=1)
    direction: Direction
    direction_evidence: ExactSpan
    direction_explanation: str = Field(min_length=1)
    comparison: Comparison
    comparison_evidence: ExactSpan
    comparison_explanation: str = Field(min_length=1)
    polarity: Polarity
    polarity_evidence: ExactSpan
    polarity_explanation: str = Field(min_length=1)
    uncertainty: Uncertainty
    uncertainty_evidence: ExactSpan
    uncertainty_explanation: str = Field(min_length=1)
    quantitative_evidence: tuple[QuantitativeEvidence, ...] = ()
    statistical_evidence: StatisticalEvidence
    required_modifiers: tuple[RequiredModifier, ...] = ()
    completeness: CompletenessJudgment
    completeness_explanation: str = Field(min_length=1)


class ReviewerPacket(StrictModel):
    scope_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_sha256: Sha256
    atomic_scope: ExactSpan
    claim: ClaimContent
    acceptable_equivalent_evidence: tuple[ExactSpan, ...] = ()
    ambiguity_or_abstention_conditions: tuple[AmbiguityCondition, ...] = ()
    explanation: str = Field(min_length=1)
    reviewer: ReviewerIdentity


class ReviewerPacketBatch(StrictModel):
    schema_version: Literal["source_general_claim_verification.reviewer_batch.v1"]
    corpus_sha256: Sha256
    reviewer: ReviewerIdentity
    packets: tuple[ReviewerPacket, ...] = Field(min_length=31, max_length=31)


class TiebreakerPacketBatch(StrictModel):
    schema_version: Literal["source_general_claim_verification.tiebreaker_batch.v1"]
    corpus_sha256: Sha256
    reviewer: ReviewerIdentity
    packets: tuple[ReviewerPacket, ...] = Field(min_length=1, max_length=31)


class FrozenReferencePacket(StrictModel):
    scope_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_sha256: Sha256
    atomic_scope: ExactSpan
    claim: ClaimContent
    acceptable_equivalent_evidence: tuple[ExactSpan, ...] = ()
    ambiguity_or_abstention_conditions: tuple[AmbiguityCondition, ...] = ()
    first_reviewer: ReviewerIdentity
    second_reviewer: ReviewerIdentity
    tiebreaker: ReviewerIdentity | None = None
    disagreement_fields: tuple[str, ...] = ()
    resolution_explanation: str = Field(min_length=1)
    excluded_as_ambiguous: bool
    packet_sha256: Sha256


class FrozenPacketSet(StrictModel):
    schema_version: Literal["source_general_claim_verification.packet_set.v1"]
    corpus_sha256: Sha256
    packets: tuple[FrozenReferencePacket, ...] = Field(min_length=31, max_length=31)
    unresolved_scope_ids: tuple[str, ...] = ()
    packet_set_sha256: Sha256


class CandidateClaim(StrictModel):
    scope_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_sha256: Sha256
    atomic_scope: ExactSpan
    claim: ClaimContent


class MalformedVariant(StrictModel):
    variant_id: str = Field(min_length=1)
    family: MalformedFamily
    reference_scope_id: str = Field(min_length=1)
    candidate: CandidateClaim
    changed_fields: tuple[str, ...] = Field(min_length=1)
    expected_decision: Literal["REJECT", "ABSTAIN"]


class ExperimentCaseResult(StrictModel):
    case_id: str = Field(min_length=1)
    reference_scope_id: str = Field(min_length=1)
    case_kind: CaseKind
    malformed_family: MalformedFamily | None = None
    original_claim: CandidateClaim
    verifier_decision: VerifierDecision
    repair_attempted: bool
    repair_attempt_status: RepairAttemptStatus
    repair_failure_axis: ModifierAxis | None = None
    repaired_claim: CandidateClaim | None = None
    reverification_decision: VerifierDecision | None = None
    terminal: ExperimentTerminal
    review_only: Literal[True]
    promotion_eligible: Literal[False]
    unsupported_content: bool
    contradiction: bool
    verifier_calls: int = Field(ge=0)
    repair_calls: int = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    cost_microusd: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_repair_shape(self) -> ExperimentCaseResult:
        if self.repair_attempted:
            self._validate_attempted_repair()
        else:
            self._validate_unattempted_repair()
        return self

    @model_validator(mode="after")
    def validate_terminal_state(self) -> ExperimentCaseResult:
        if self.terminal is ExperimentTerminal.VERIFIED_UNREPAIRED and (
            self.repair_attempted
            or self.verifier_decision is not VerifierDecision.ACCEPT
        ):
            raise ValueError("VERIFIED_UNREPAIRED requires an accepted original claim")
        if self.terminal is ExperimentTerminal.VERIFIED_AFTER_REPAIR and (
            self.repair_attempt_status is not RepairAttemptStatus.PATCH_PRODUCED
            or self.reverification_decision is not VerifierDecision.ACCEPT
        ):
            raise ValueError(
                "VERIFIED_AFTER_REPAIR requires an accepted fresh reverification",
            )
        return self

    @model_validator(mode="after")
    def validate_repair_precondition(self) -> ExperimentCaseResult:
        if (
            self.repair_attempted
            and self.verifier_decision is not VerifierDecision.REJECT
        ):
            raise ValueError("repair is allowed only after verifier rejection")
        return self

    @model_validator(mode="after")
    def validate_case_kind(self) -> ExperimentCaseResult:
        if self.case_kind is CaseKind.CONTROLLED_MALFORMED:
            if self.malformed_family is None:
                raise ValueError("malformed cases require a failure family")
        elif self.malformed_family is not None:
            raise ValueError("valuable correct cases cannot name a malformed family")
        return self

    def _validate_unattempted_repair(self) -> None:
        if self.repair_attempt_status is not RepairAttemptStatus.NOT_ATTEMPTED:
            raise ValueError("unattempted repairs must use NOT_ATTEMPTED status")
        if any(
            value is not None
            for value in (
                self.repair_failure_axis,
                self.repaired_claim,
                self.reverification_decision,
            )
        ):
            raise ValueError("unattempted repairs cannot carry repair output")

    def _validate_attempted_repair(self) -> None:
        if self.repair_attempt_status is RepairAttemptStatus.NOT_ATTEMPTED:
            raise ValueError("repair attempts require an attempted status")
        if self.repair_failure_axis is None:
            raise ValueError("repair attempts require exactly one named failure axis")
        if self.repair_attempt_status is RepairAttemptStatus.PATCH_PRODUCED:
            if self.repaired_claim is None:
                raise ValueError("PATCH_PRODUCED requires a repaired claim")
            if self.reverification_decision is None:
                raise ValueError("repaired claims require fresh reverification")
            return
        if self.repaired_claim is not None or self.reverification_decision is not None:
            raise ValueError(
                "failed or rejected repair attempts cannot carry accepted output",
            )


__all__ = [
    "AmbiguityCondition",
    "AmbiguityKind",
    "AuthorInterpretation",
    "CandidateClaim",
    "CaseKind",
    "ClaimContent",
    "Comparison",
    "CompletenessJudgment",
    "CorpusArtifact",
    "Direction",
    "EventType",
    "ExactSpan",
    "ExperimentCaseResult",
    "ExperimentTerminal",
    "ExposedScope",
    "FrozenPacketSet",
    "FrozenReferencePacket",
    "MalformedFamily",
    "MalformedVariant",
    "ModifierAxis",
    "Participant",
    "ParticipantRole",
    "Polarity",
    "QuantitativeEvidence",
    "QuantitativeKind",
    "RepairAttemptStatus",
    "RequiredModifier",
    "ReviewerIdentity",
    "ReviewerPacket",
    "ReviewerPacketBatch",
    "ReviewerRole",
    "SHA256_PATTERN",
    "Sha256",
    "SourceDocument",
    "StatisticalEvidence",
    "StatisticalObservation",
    "StrictModel",
    "TiebreakerPacketBatch",
    "Uncertainty",
    "VerifierDecision",
]
