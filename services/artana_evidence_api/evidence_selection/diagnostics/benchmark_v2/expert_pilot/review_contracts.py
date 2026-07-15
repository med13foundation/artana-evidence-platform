"""Human-owned categorical and externally signed expert-pilot contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.pilot_contracts import (
    EvidenceSelectionExpertPilotAbstractSection,
    ExpertPilotPacketSufficiency,
    ExpertPilotSelectionLabel,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ReviewerRole = Literal["independent_first_pass", "adjudicator_and_safety_reviewer"]
SafetyAssessment = Literal[
    "supported",
    "unsupported_nonsevere",
    "unsupported_high_severity",
    "not_assessable",
]


def _literal_nonblank(value: str) -> str:
    if not value.strip() or value != value.strip():
        raise ValueError(
            "expert-pilot review text must be literal, nonblank, and trimmed"
        )
    return value


def _literal_unique_spans(value: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(_literal_nonblank(span) for span in value)
    if len(set(normalized)) != len(normalized):
        raise ValueError("expert-pilot supporting spans must be unique")
    return normalized


def _aware(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return value


class EvidenceSelectionExpertPilotReviewerCredential(BaseModel):
    """Issuer-certified reviewer identity and public verification key."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    reviewer_id: str = Field(min_length=1)
    subject_identity_id: str = Field(pattern=r"^verified-subject-[a-zA-Z0-9._-]+$")
    reviewer_slot: str = Field(min_length=1)
    review_role: ReviewerRole
    key_id: str = Field(pattern=r"^reviewer-key-[a-zA-Z0-9._-]+$")
    public_key_hex: str = Field(pattern=r"^[a-f0-9]{64}$")
    identity_assurance: Literal["issuer_verified_real_person"]
    qualification_claim: Literal["domain_qualified_human"]
    independence_claim: Literal["independent_of_model_development_and_other_reviewers"]
    conflict_of_interest_declaration: Literal["no_conflict_declared"]

    @field_validator("reviewer_id", "reviewer_slot")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return _literal_nonblank(value)


class EvidenceSelectionExpertPilotReviewerRegistryPayload(BaseModel):
    """Externally issued credentials bound to one frozen pilot and evaluation."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_expert_pilot_reviewer_registry.v1"]
    study_id: str = Field(min_length=1)
    pilot_protocol_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluation_protocol_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    publication_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    issuer_id: str = Field(min_length=1)
    valid_from: datetime
    valid_until: datetime
    credentials: tuple[EvidenceSelectionExpertPilotReviewerCredential, ...] = Field(
        min_length=3
    )

    @field_validator("credentials", mode="before")
    @classmethod
    def _accept_json_credentials(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("study_id", "issuer_id")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return _literal_nonblank(value)

    @field_validator("valid_from", "valid_until")
    @classmethod
    def _validate_time(cls, value: datetime) -> datetime:
        return _aware(value, field_name="reviewer credential validity time")

    @model_validator(mode="after")
    def _registry_is_coherent(
        self,
    ) -> EvidenceSelectionExpertPilotReviewerRegistryPayload:
        if self.valid_until <= self.valid_from:
            raise ValueError("reviewer credential validity window must be positive")
        identities = [credential.reviewer_id for credential in self.credentials]
        subjects = [credential.subject_identity_id for credential in self.credentials]
        slots = [credential.reviewer_slot for credential in self.credentials]
        keys = [credential.key_id for credential in self.credentials]
        public_keys = [credential.public_key_hex for credential in self.credentials]
        if any(
            len(set(values)) != len(values)
            for values in (identities, subjects, slots, keys, public_keys)
        ):
            raise ValueError("reviewer identities, slots, and keys must be distinct")
        return self


class EvidenceSelectionExpertPilotSignedReviewerRegistry(BaseModel):
    """Registry whose issuer signature anchors external identity assurance."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    payload: EvidenceSelectionExpertPilotReviewerRegistryPayload
    issuer_key_id: str = Field(pattern=r"^issuer-key-[a-zA-Z0-9._-]+$")
    signature_algorithm: Literal["ed25519"]
    signature_hex: str = Field(pattern=r"^[a-f0-9]{128}$")


class EvidenceSelectionExpertPilotReviewFinding(BaseModel):
    """One human categorical decision with literal packet evidence."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    candidate_id: str = Field(pattern=r"^candidate-[a-f0-9]{16}$")
    selection_label: ExpertPilotSelectionLabel
    packet_sufficiency: ExpertPilotPacketSufficiency
    supporting_spans: tuple[str, ...]
    reviewer_explanation: str = Field(min_length=1)

    @field_validator("supporting_spans", mode="before")
    @classmethod
    def _accept_json_spans(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("supporting_spans")
    @classmethod
    def _validate_spans(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _literal_unique_spans(value)

    @field_validator("reviewer_explanation")
    @classmethod
    def _validate_explanation(cls, value: str) -> str:
        return _literal_nonblank(value)

    @model_validator(mode="after")
    def _decisive_sufficient_finding_has_evidence(
        self,
    ) -> EvidenceSelectionExpertPilotReviewFinding:
        if (
            self.selection_label in {"select", "reject"}
            and self.packet_sufficiency == "sufficient"
            and not self.supporting_spans
        ):
            raise ValueError(
                "decisive sufficient reviewer findings require literal supporting spans"
            )
        return self


class EvidenceSelectionExpertPilotReviewCompletionPayload(BaseModel):
    """One reviewer's completed packet, signed outside the platform."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_expert_pilot_review_completion.v1"]
    study_id: str
    packet_id: str = Field(pattern=r"^packet-[a-f0-9]{16}$")
    reviewer_slot: str
    review_case_id: str = Field(pattern=r"^case-[a-f0-9]{16}$")
    reviewer_id: str
    reviewer_packet_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluation_protocol_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    completed_at: datetime
    findings: tuple[EvidenceSelectionExpertPilotReviewFinding, ...] = Field(
        min_length=1
    )

    @field_validator("findings", mode="before")
    @classmethod
    def _accept_json_findings(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("completed_at")
    @classmethod
    def _validate_completion_time(cls, value: datetime) -> datetime:
        return _aware(value, field_name="review completion time")

    @model_validator(mode="after")
    def _candidate_findings_are_unique(
        self,
    ) -> EvidenceSelectionExpertPilotReviewCompletionPayload:
        candidate_ids = [finding.candidate_id for finding in self.findings]
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("review completion candidate findings must be unique")
        return self


class EvidenceSelectionExpertPilotSignedReviewCompletion(BaseModel):
    """Reviewer completion bound to its certified Ed25519 key."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    payload: EvidenceSelectionExpertPilotReviewCompletionPayload
    reviewer_key_id: str = Field(pattern=r"^reviewer-key-[a-zA-Z0-9._-]+$")
    signature_algorithm: Literal["ed25519"]
    signature_hex: str = Field(pattern=r"^[a-f0-9]{128}$")


class EvidenceSelectionExpertPilotFirstPassFinding(BaseModel):
    """Identity-blinded first-pass context shown to the adjudicator."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    selection_label: ExpertPilotSelectionLabel
    packet_sufficiency: ExpertPilotPacketSufficiency
    supporting_spans: tuple[str, ...]
    reviewer_explanation: str


class EvidenceSelectionExpertPilotAdjudicationItem(BaseModel):
    """One neutral disagreement requiring the predeclared third reviewer."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    adjudication_item_id: str = Field(pattern=r"^adjudication-[a-f0-9]{16}$")
    review_case_id: str = Field(pattern=r"^adjudication-case-[a-f0-9]{16}$")
    goal: str
    instructions: str
    inclusion_criteria: tuple[str, ...]
    exclusion_criteria: tuple[str, ...]
    title: str
    bounded_source_text: tuple[EvidenceSelectionExpertPilotAbstractSection, ...]
    first_pass_findings: tuple[EvidenceSelectionExpertPilotFirstPassFinding, ...] = (
        Field(min_length=2, max_length=2)
    )

    @field_validator(
        "inclusion_criteria",
        "exclusion_criteria",
        "bounded_source_text",
        "first_pass_findings",
        mode="before",
    )
    @classmethod
    def _accept_json_arrays(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value


class EvidenceSelectionExpertPilotAdjudicationRequest(BaseModel):
    """Deterministically generated, model-blinded disagreement packet."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_expert_pilot_adjudication_request.v1"]
    study_id: str
    pilot_protocol_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluation_protocol_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer_registry_payload_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    first_pass_completion_sha256s: tuple[str, ...] = Field(min_length=1)
    completion_status: Literal["requires_human_adjudication"]
    hide_model_identity: Literal[True] = True
    hide_model_decisions: Literal[True] = True
    items: tuple[EvidenceSelectionExpertPilotAdjudicationItem, ...]

    @field_validator("first_pass_completion_sha256s", "items", mode="before")
    @classmethod
    def _accept_json_arrays(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value


class EvidenceSelectionExpertPilotAdjudicationFinding(BaseModel):
    """Third-reviewer categorical resolution for one disagreement."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    adjudication_item_id: str = Field(pattern=r"^adjudication-[a-f0-9]{16}$")
    selection_label: ExpertPilotSelectionLabel
    packet_sufficiency: ExpertPilotPacketSufficiency
    supporting_spans: tuple[str, ...]
    reviewer_explanation: str = Field(min_length=1)

    @field_validator("supporting_spans", mode="before")
    @classmethod
    def _accept_json_spans(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("supporting_spans")
    @classmethod
    def _validate_spans(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _literal_unique_spans(value)

    @field_validator("reviewer_explanation")
    @classmethod
    def _validate_explanation(cls, value: str) -> str:
        return _literal_nonblank(value)


class EvidenceSelectionExpertPilotAdjudicationCompletionPayload(BaseModel):
    """Signed adjudication over the exact generated disagreement request."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal[
        "evidence_selection_expert_pilot_adjudication_completion.v1"
    ]
    study_id: str
    adjudicator_slot: str
    reviewer_id: str
    adjudication_request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    completed_at: datetime
    findings: tuple[EvidenceSelectionExpertPilotAdjudicationFinding, ...]

    @field_validator("findings", mode="before")
    @classmethod
    def _accept_json_findings(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("completed_at")
    @classmethod
    def _validate_completion_time(cls, value: datetime) -> datetime:
        return _aware(value, field_name="adjudication completion time")


class EvidenceSelectionExpertPilotSignedAdjudicationCompletion(BaseModel):
    """Adjudication completion bound to the certified adjudicator key."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    payload: EvidenceSelectionExpertPilotAdjudicationCompletionPayload
    reviewer_key_id: str = Field(pattern=r"^reviewer-key-[a-zA-Z0-9._-]+$")
    signature_algorithm: Literal["ed25519"]
    signature_hex: str = Field(pattern=r"^[a-f0-9]{128}$")


class EvidenceSelectionExpertPilotSafetyFinding(BaseModel):
    """Categorical human audit of one selected model claim after gold freeze."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    audit_item_id: str = Field(pattern=r"^safety-[a-f0-9]{16}$")
    assessment: SafetyAssessment
    claim_spans: tuple[str, ...]
    source_support_spans: tuple[str, ...]
    reviewer_explanation: str = Field(min_length=1)

    @field_validator("claim_spans", "source_support_spans", mode="before")
    @classmethod
    def _accept_json_spans(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("claim_spans", "source_support_spans")
    @classmethod
    def _validate_spans(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _literal_unique_spans(value)

    @field_validator("reviewer_explanation")
    @classmethod
    def _validate_explanation(cls, value: str) -> str:
        return _literal_nonblank(value)


class EvidenceSelectionExpertPilotSafetyCompletionPayload(BaseModel):
    """Signed post-gold safety review over the exact generated request."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_expert_pilot_safety_completion.v1"]
    study_id: str
    safety_reviewer_slot: str
    reviewer_id: str
    safety_request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    frozen_gold_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    completed_at: datetime
    findings: tuple[EvidenceSelectionExpertPilotSafetyFinding, ...]

    @field_validator("findings", mode="before")
    @classmethod
    def _accept_json_findings(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("completed_at")
    @classmethod
    def _validate_completion_time(cls, value: datetime) -> datetime:
        return _aware(value, field_name="safety completion time")


class EvidenceSelectionExpertPilotSignedSafetyCompletion(BaseModel):
    """Safety completion bound to the certified adjudicator key."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    payload: EvidenceSelectionExpertPilotSafetyCompletionPayload
    reviewer_key_id: str = Field(pattern=r"^reviewer-key-[a-zA-Z0-9._-]+$")
    signature_algorithm: Literal["ed25519"]
    signature_hex: str = Field(pattern=r"^[a-f0-9]{128}$")


__all__ = [
    "EvidenceSelectionExpertPilotAdjudicationCompletionPayload",
    "EvidenceSelectionExpertPilotAdjudicationFinding",
    "EvidenceSelectionExpertPilotAdjudicationItem",
    "EvidenceSelectionExpertPilotAdjudicationRequest",
    "EvidenceSelectionExpertPilotFirstPassFinding",
    "EvidenceSelectionExpertPilotReviewCompletionPayload",
    "EvidenceSelectionExpertPilotReviewFinding",
    "EvidenceSelectionExpertPilotReviewerCredential",
    "EvidenceSelectionExpertPilotReviewerRegistryPayload",
    "EvidenceSelectionExpertPilotSafetyCompletionPayload",
    "EvidenceSelectionExpertPilotSafetyFinding",
    "EvidenceSelectionExpertPilotSignedAdjudicationCompletion",
    "EvidenceSelectionExpertPilotSignedReviewCompletion",
    "EvidenceSelectionExpertPilotSignedReviewerRegistry",
    "EvidenceSelectionExpertPilotSignedSafetyCompletion",
    "SafetyAssessment",
]
