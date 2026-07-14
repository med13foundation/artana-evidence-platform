"""Strict contracts for blinded benchmark-v2 expert pilot packets."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .contracts import EvidenceSelectionBenchmarkArtifactRef

ExpertPilotSelectionLabel = Literal["select", "reject", "abstain"]
ExpertPilotPacketSufficiency = Literal["sufficient", "insufficient"]


def _literal_nonblank(value: str) -> str:
    if not value.strip() or value != value.strip():
        raise ValueError("expert-pilot text must be literal, nonblank, and trimmed")
    return value


class EvidenceSelectionExpertPilotSourceRef(EvidenceSelectionBenchmarkArtifactRef):
    """One immutable source supplement associated with a benchmark record."""

    source_key: Literal["pubmed"]
    source_record_id: str = Field(pattern=r"^[0-9]+$")

    @field_validator("source_record_id")
    @classmethod
    def _validate_identity(cls, value: str) -> str:
        return _literal_nonblank(value)


class EvidenceSelectionExpertPilotSupplementManifest(BaseModel):
    """Content-addressed supplemental source inventory for the pilot."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_expert_pilot_supplements.v1"]
    supplements: tuple[EvidenceSelectionExpertPilotSourceRef, ...] = Field(
        min_length=1,
    )

    @field_validator("supplements", mode="before")
    @classmethod
    def _accept_json_array(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def _supplements_are_unique(
        self,
    ) -> EvidenceSelectionExpertPilotSupplementManifest:
        source_ids = [item.source_record_id for item in self.supplements]
        paths = [item.path for item in self.supplements]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("expert-pilot supplemental source IDs must be unique")
        if len(set(paths)) != len(paths):
            raise ValueError("expert-pilot supplemental paths must be unique")
        return self


class EvidenceSelectionExpertPilotAbstractSection(BaseModel):
    """One literal section from the frozen PubMed abstract."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    section: str = Field(min_length=1)
    text: str = Field(min_length=1)

    @field_validator("section", "text")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return _literal_nonblank(value)


class EvidenceSelectionExpertPilotSourceSupplement(BaseModel):
    """Frozen primary-source metadata without an interpretation or label."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_expert_pilot_source.v1"]
    source_key: Literal["pubmed"]
    source_record_id: str = Field(pattern=r"^[0-9]+$")
    source_url: str = Field(pattern=r"^https://pubmed\.ncbi\.nlm\.nih\.gov/[0-9]+/$")
    retrieval_method: Literal["ncbi_pubmed_efetch"]
    retrieved_at: datetime
    title: str = Field(min_length=1)
    doi: str = Field(min_length=1)
    publication_types: tuple[str, ...] = Field(min_length=1)
    abstract_sections: tuple[EvidenceSelectionExpertPilotAbstractSection, ...] = (
        Field(min_length=1)
    )

    @field_validator("publication_types", "abstract_sections", mode="before")
    @classmethod
    def _accept_json_arrays(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("title", "doi")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return _literal_nonblank(value)

    @field_validator("publication_types")
    @classmethod
    def _validate_publication_types(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_literal_nonblank(item) for item in value)
        if len(set(normalized)) != len(normalized):
            raise ValueError("publication types must be unique")
        return normalized

    @field_validator("retrieved_at")
    @classmethod
    def _retrieval_time_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("source retrieval time must include a timezone")
        return value

    @model_validator(mode="after")
    def _source_url_matches_identity(
        self,
    ) -> EvidenceSelectionExpertPilotSourceSupplement:
        expected_url = (
            f"https://pubmed.ncbi.nlm.nih.gov/{self.source_record_id}/"
        )
        if self.source_url != expected_url:
            raise ValueError("expert-pilot PubMed URL must match source_record_id")
        return self


class EvidenceSelectionExpertPilotBlindingPolicy(BaseModel):
    """Frozen protections against model and ranking leakage to reviewers."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    hide_model_identity: Literal[True] = True
    hide_model_decisions: Literal[True] = True
    hide_ai_diagnostics: Literal[True] = True
    hide_ranking_values: Literal[True] = True
    candidate_order: Literal["reviewer_specific_deterministic_shuffle"]


class EvidenceSelectionExpertPilotAcceptanceThresholds(BaseModel):
    """Code-owned thresholds computed only from categorical human findings."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    metric_origin: Literal["deterministic_from_categorical_human_findings"]
    minimum_adjudicated_precision: float = Field(ge=0.0, le=1.0)
    minimum_adjudicated_recall: float = Field(ge=0.0, le=1.0)
    minimum_first_pass_percent_agreement: float = Field(ge=0.0, le=1.0)
    maximum_high_severity_overclaim_count: Literal[0]

    @model_validator(mode="after")
    def _thresholds_are_frozen(
        self,
    ) -> EvidenceSelectionExpertPilotAcceptanceThresholds:
        thresholds = (
            self.minimum_adjudicated_precision,
            self.minimum_adjudicated_recall,
            self.minimum_first_pass_percent_agreement,
        )
        if thresholds != (0.8, 0.8, 0.8):
            raise ValueError("expert-pilot acceptance thresholds are frozen")
        return self


class EvidenceSelectionExpertPilotProtocol(BaseModel):
    """Predeclared diagnostic pilot protocol; never a readiness claim."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_expert_pilot_protocol.v1"]
    study_id: str = Field(min_length=1)
    study_tier: Literal["diagnostic_pilot"]
    benchmark_fixture: EvidenceSelectionBenchmarkArtifactRef
    supplement_manifest: EvidenceSelectionBenchmarkArtifactRef
    expected_case_ids: tuple[str, ...] = Field(min_length=1)
    expected_record_count: int = Field(ge=1)
    diagnostic_pilot_question_count: Literal[3]
    production_calibration_minimum_question_count: Literal[20]
    production_calibration_minimum_record_count: Literal[200]
    production_calibration_training_question_count: Literal[12]
    production_calibration_held_out_question_count: Literal[8]
    independent_reviewer_slots: tuple[str, ...] = Field(min_length=2)
    adjudicator_slot: str = Field(min_length=1)
    reviewer_qualification_requirement: Literal[
        "domain_qualified_human_bound_by_external_attestation"
    ]
    reviewer_identity_authentication: Literal["external_signed_attestation_required"]
    minimum_independent_reviewers_per_record: Literal[2] = 2
    disagreement_policy: Literal["third_reviewer_adjudication"]
    reviewer_labels: tuple[ExpertPilotSelectionLabel, ...]
    packet_sufficiency_labels: tuple[ExpertPilotPacketSufficiency, ...]
    reviewer_numeric_judgments_allowed: Literal[False] = False
    production_readiness_claim: Literal[False] = False
    production_calibration_claim: Literal[False] = False
    calibration_status: Literal["unavailable_insufficient_independent_corpus"]
    blinding: EvidenceSelectionExpertPilotBlindingPolicy
    acceptance_thresholds: EvidenceSelectionExpertPilotAcceptanceThresholds

    @field_validator(
        "expected_case_ids",
        "independent_reviewer_slots",
        "reviewer_labels",
        "packet_sufficiency_labels",
        mode="before",
    )
    @classmethod
    def _accept_json_arrays(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("study_id", "adjudicator_slot")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return _literal_nonblank(value)

    @field_validator("expected_case_ids", "independent_reviewer_slots")
    @classmethod
    def _validate_unique_text(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_literal_nonblank(item) for item in value)
        if len(set(normalized)) != len(normalized):
            raise ValueError("expert-pilot identities must be unique")
        return normalized

    @model_validator(mode="after")
    def _review_contract_is_frozen(self) -> EvidenceSelectionExpertPilotProtocol:
        if set(self.reviewer_labels) != {"select", "reject", "abstain"}:
            raise ValueError("expert-pilot reviewer labels must be the frozen categories")
        if set(self.packet_sufficiency_labels) != {"sufficient", "insufficient"}:
            raise ValueError("expert-pilot packet sufficiency labels are incomplete")
        if self.adjudicator_slot in self.independent_reviewer_slots:
            raise ValueError("expert-pilot adjudicator must be independent")
        return self


class EvidenceSelectionExpertPilotCandidate(BaseModel):
    """One blinded source candidate awaiting categorical human findings."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    candidate_id: str = Field(pattern=r"^candidate-[a-f0-9]{16}$")
    source_key: Literal["pubmed"]
    source_record_id: str = Field(pattern=r"^[0-9]+$")
    source_url: str = Field(pattern=r"^https://pubmed\.ncbi\.nlm\.nih\.gov/[0-9]+/$")
    title: str = Field(min_length=1)
    bounded_source_text: tuple[EvidenceSelectionExpertPilotAbstractSection, ...] = (
        Field(min_length=1)
    )
    selection_label: None = None
    packet_sufficiency: None = None
    supporting_spans: tuple[str, ...] = ()
    reviewer_explanation: None = None

    @field_validator("bounded_source_text", mode="before")
    @classmethod
    def _accept_json_source_text(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("supporting_spans", mode="before")
    @classmethod
    def _require_blank_supporting_spans(cls, value: object) -> tuple[()]:
        if value not in ([], ()):
            raise ValueError("uncompleted expert-pilot supporting spans must be empty")
        return ()


class EvidenceSelectionExpertPilotReviewerPacket(BaseModel):
    """Blinded editable packet distributed to one independent reviewer slot."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_expert_pilot_reviewer_packet.v1"]
    study_id: str
    packet_id: str = Field(pattern=r"^packet-[a-f0-9]{16}$")
    reviewer_slot: str
    review_role: Literal["independent_first_pass"]
    review_case_id: str = Field(pattern=r"^case-[a-f0-9]{16}$")
    goal: str
    instructions: str
    inclusion_criteria: tuple[str, ...]
    exclusion_criteria: tuple[str, ...]
    completion_status: Literal["requires_human_labels"]
    reviewer_identity_attestation_required: Literal[True] = True
    production_readiness_claim: Literal[False] = False
    candidates: tuple[EvidenceSelectionExpertPilotCandidate, ...] = Field(min_length=1)

    @field_validator(
        "inclusion_criteria",
        "exclusion_criteria",
        "candidates",
        mode="before",
    )
    @classmethod
    def _accept_json_arrays(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value


class EvidenceSelectionExpertPilotCandidateBinding(BaseModel):
    """Machine-only mapping from a blinded candidate to benchmark identity."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    candidate_id: str = Field(pattern=r"^candidate-[a-f0-9]{16}$")
    record_id: str = Field(min_length=1)
    historical_packet_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    supplement_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class EvidenceSelectionExpertPilotMachineSidecar(BaseModel):
    """Signed machine-only identity binding kept away from first-pass reviewers."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_expert_pilot_sidecar.v1"]
    study_id: str
    packet_id: str = Field(pattern=r"^packet-[a-f0-9]{16}$")
    reviewer_slot: str
    review_case_id: str = Field(pattern=r"^case-[a-f0-9]{16}$")
    case_id: str
    protocol_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    benchmark_fixture_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    supplement_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer_packet_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidate_bindings: tuple[EvidenceSelectionExpertPilotCandidateBinding, ...] = (
        Field(min_length=1)
    )
    producer_signature: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("candidate_bindings", mode="before")
    @classmethod
    def _accept_json_bindings(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def _bindings_are_unique(self) -> EvidenceSelectionExpertPilotMachineSidecar:
        candidate_ids = [item.candidate_id for item in self.candidate_bindings]
        record_ids = [item.record_id for item in self.candidate_bindings]
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("expert-pilot sidecar candidate IDs must be unique")
        if len(set(record_ids)) != len(record_ids):
            raise ValueError("expert-pilot sidecar record IDs must be unique")
        return self


class EvidenceSelectionExpertPilotPublishedArtifact(BaseModel):
    """Digest-bound identity for one published pilot artifact."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    artifact_kind: Literal["reviewer_packet", "machine_sidecar"]
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("path")
    @classmethod
    def _path_is_relative_and_literal(cls, value: str) -> str:
        normalized = _literal_nonblank(value)
        if normalized.startswith("/") or ".." in normalized.split("/"):
            raise ValueError("published expert-pilot path must stay relative")
        return normalized


class EvidenceSelectionExpertPilotPublicationManifest(BaseModel):
    """Deterministic inventory of one atomic packet publication."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_expert_pilot_publication.v1"]
    study_id: str
    protocol_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    benchmark_fixture_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    supplement_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    independent_reviewer_count: int = Field(ge=2)
    reviewer_packet_count: int = Field(ge=1)
    candidate_review_count: int = Field(ge=1)
    production_readiness_claim: Literal[False] = False
    production_calibration_claim: Literal[False] = False
    artifacts: tuple[EvidenceSelectionExpertPilotPublishedArtifact, ...] = Field(
        min_length=1
    )

    @field_validator("artifacts", mode="before")
    @classmethod
    def _accept_json_artifacts(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def _artifact_inventory_is_complete(
        self,
    ) -> EvidenceSelectionExpertPilotPublicationManifest:
        paths = [artifact.path for artifact in self.artifacts]
        if len(set(paths)) != len(paths):
            raise ValueError("published expert-pilot artifact paths must be unique")
        packet_count = sum(
            artifact.artifact_kind == "reviewer_packet"
            for artifact in self.artifacts
        )
        sidecar_count = sum(
            artifact.artifact_kind == "machine_sidecar"
            for artifact in self.artifacts
        )
        if packet_count != self.reviewer_packet_count or sidecar_count != packet_count:
            raise ValueError("every reviewer packet requires exactly one machine sidecar")
        return self


__all__ = [
    "EvidenceSelectionExpertPilotCandidate",
    "EvidenceSelectionExpertPilotCandidateBinding",
    "EvidenceSelectionExpertPilotMachineSidecar",
    "EvidenceSelectionExpertPilotPublicationManifest",
    "EvidenceSelectionExpertPilotProtocol",
    "EvidenceSelectionExpertPilotReviewerPacket",
    "EvidenceSelectionExpertPilotSourceSupplement",
    "EvidenceSelectionExpertPilotSupplementManifest",
]
