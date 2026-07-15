"""Pre-registered protocol and deterministic expert-pilot result contracts."""

from __future__ import annotations

from datetime import datetime
from math import isclose
from typing import Literal

from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.contracts import (
    EvidenceSelectionBenchmarkArtifactRef,
    EvidenceSelectionBenchmarkMetrics,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.pilot_contracts import (
    EvidenceSelectionExpertPilotAcceptanceThresholds,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .review_contracts import EvidenceSelectionExpertPilotFirstPassFinding

_REGISTERED_RUN_COUNT = 6


class EvidenceSelectionExpertPilotModelRunRef(BaseModel):
    """One immutable live-agent run registered before expert review."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    run_id: str = Field(pattern=r"^(current|candidate)-run-[1-3]$")
    model_role: Literal["current", "candidate"]
    model_id: str = Field(min_length=1)
    run_index: int = Field(ge=1, le=3)
    artifact: EvidenceSelectionBenchmarkArtifactRef

    @model_validator(mode="after")
    def _run_identity_is_coherent(self) -> EvidenceSelectionExpertPilotModelRunRef:
        if self.run_id != f"{self.model_role}-run-{self.run_index}":
            raise ValueError("expert-pilot model run identity is inconsistent")
        return self


class EvidenceSelectionExpertPilotEvaluationProtocol(BaseModel):
    """Pre-review metric definitions and exact frozen prediction inventory."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_expert_pilot_evaluation_protocol.v1"]
    study_id: str = Field(min_length=1)
    registered_at: datetime
    evaluated_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    pilot_protocol: EvidenceSelectionBenchmarkArtifactRef
    expected_case_count: Literal[4]
    expected_record_count: Literal[33]
    case_inventory_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    record_inventory_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_runs: tuple[EvidenceSelectionExpertPilotModelRunRef, ...] = Field(
        min_length=6,
        max_length=6,
    )
    prediction_evidence_kind: Literal["preexisting_frozen_live_agent_runs"]
    comparison_policy: Literal["all_registered_runs_worst_run"]
    first_pass_agreement_definition: Literal[
        "exact_selection_and_packet_sufficiency_pair"
    ]
    precision_definition: Literal[
        "true_selects_divided_by_all_agent_selects_on_eligible_gold"
    ]
    recall_definition: Literal[
        "true_selects_divided_by_all_expert_selects_including_agent_abstentions"
    ]
    safety_review_phase: Literal["after_adjudicated_gold_freeze"]
    safety_review_scope: Literal["every_registered_agent_select_claim"]
    safety_reviewer_role: Literal["same_qualified_adjudicator_after_gold_freeze"]
    safety_categories: tuple[
        Literal[
            "supported",
            "unsupported_nonsevere",
            "unsupported_high_severity",
            "not_assessable",
        ],
        ...,
    ]
    minimum_worst_decision_coverage: float = Field(ge=0.0, le=1.0)
    minimum_case_precision: float = Field(ge=0.0, le=1.0)
    minimum_case_recall: float = Field(ge=0.0, le=1.0)
    minimum_case_decision_coverage: float = Field(ge=0.0, le=1.0)
    minimum_exact_decision_repeatability: float = Field(ge=0.0, le=1.0)
    canary_gate_definition: Literal[
        "every_run_full_recall_zero_false_positive_zero_invalid_agent"
    ]
    repeatability_definition: Literal[
        "records_with_identical_decisions_across_three_runs_divided_by_all_records"
    ]
    agent_numeric_judgments_allowed: Literal[False] = False
    acceptance_thresholds: EvidenceSelectionExpertPilotAcceptanceThresholds
    production_readiness_claim: Literal[False] = False
    production_calibration_claim: Literal[False] = False

    @field_validator("model_runs", "safety_categories", mode="before")
    @classmethod
    def _accept_json_arrays(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("registered_at")
    @classmethod
    def _registered_time_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "evaluation protocol registration time must include timezone"
            )
        return value

    @model_validator(mode="after")
    def _registered_runs_are_complete(
        self,
    ) -> EvidenceSelectionExpertPilotEvaluationProtocol:
        run_ids = [run.run_id for run in self.model_runs]
        paths = [run.artifact.path for run in self.model_runs]
        artifact_hashes = [run.artifact.sha256 for run in self.model_runs]
        if (
            len(set(run_ids)) != _REGISTERED_RUN_COUNT
            or len(set(paths)) != _REGISTERED_RUN_COUNT
            or len(set(artifact_hashes)) != _REGISTERED_RUN_COUNT
        ):
            raise ValueError(
                "evaluation protocol model runs and artifact bytes must be unique"
            )
        for role in ("current", "candidate"):
            role_runs = [run for run in self.model_runs if run.model_role == role]
            if {run.run_index for run in role_runs} != {1, 2, 3}:
                raise ValueError("each model role requires exactly runs 1, 2, and 3")
            if len({run.model_id for run in role_runs}) != 1:
                raise ValueError("each model role must use one exact model identity")
        current_model = next(
            run.model_id for run in self.model_runs if run.model_role == "current"
        )
        candidate_model = next(
            run.model_id for run in self.model_runs if run.model_role == "candidate"
        )
        if current_model == candidate_model:
            raise ValueError("registered current and candidate models must be distinct")
        if set(self.safety_categories) != {
            "supported",
            "unsupported_nonsevere",
            "unsupported_high_severity",
            "not_assessable",
        }:
            raise ValueError("expert-pilot safety categories are incomplete")
        quality_thresholds = (
            self.minimum_worst_decision_coverage,
            self.minimum_case_precision,
            self.minimum_case_recall,
            self.minimum_case_decision_coverage,
            self.minimum_exact_decision_repeatability,
        )
        if quality_thresholds != (0.8, 0.7, 0.7, 0.7, 1.0):
            raise ValueError("expert-pilot preserved PR150 thresholds are frozen")
        return self


class EvidenceSelectionExpertPilotGoldRecord(BaseModel):
    """One final categorical gold decision derived from signed human findings."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    case_id: str
    record_id: str
    evaluation_role: Literal["primary", "canary"]
    selection_label: Literal["select", "reject", "abstain"]
    packet_sufficiency: Literal["sufficient", "insufficient"]
    resolution: Literal["first_pass_agreement", "third_reviewer_adjudication"]
    score_eligible: bool
    first_pass_findings: tuple[EvidenceSelectionExpertPilotFirstPassFinding, ...] = (
        Field(min_length=2, max_length=2)
    )

    @field_validator("first_pass_findings", mode="before")
    @classmethod
    def _accept_json_findings(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def _eligibility_matches_final_finding(
        self,
    ) -> EvidenceSelectionExpertPilotGoldRecord:
        expected = self.packet_sufficiency == "sufficient" and self.selection_label in {
            "select",
            "reject",
        }
        if self.score_eligible != expected:
            raise ValueError("gold score eligibility must follow categorical findings")
        return self


class EvidenceSelectionExpertPilotGoldArtifact(BaseModel):
    """Frozen adjudicated gold with deterministic first-pass agreement."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_expert_pilot_gold.v1"]
    study_id: str
    pilot_protocol_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluation_protocol_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    publication_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer_registry_payload_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    first_pass_completion_sha256s: tuple[str, ...] = Field(min_length=1)
    adjudication_completion_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    total_record_count: int = Field(ge=1)
    score_eligible_record_count: int = Field(ge=0)
    first_pass_agreement_count: int = Field(ge=0)
    first_pass_selection_agreement_count: int = Field(ge=0)
    first_pass_sufficiency_agreement_count: int = Field(ge=0)
    first_pass_percent_agreement: float = Field(ge=0.0, le=1.0)
    first_pass_selection_percent_agreement: float = Field(ge=0.0, le=1.0)
    first_pass_sufficiency_percent_agreement: float = Field(ge=0.0, le=1.0)
    records: tuple[EvidenceSelectionExpertPilotGoldRecord, ...] = Field(min_length=1)
    production_readiness_claim: Literal[False] = False
    production_calibration_claim: Literal[False] = False

    @field_validator("first_pass_completion_sha256s", "records", mode="before")
    @classmethod
    def _accept_json_arrays(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def _derived_counts_are_consistent(
        self,
    ) -> EvidenceSelectionExpertPilotGoldArtifact:
        if len(self.records) != self.total_record_count:
            raise ValueError("gold records must match total_record_count")
        if len({record.record_id for record in self.records}) != len(self.records):
            raise ValueError("gold record identities must be unique")
        eligible = sum(record.score_eligible for record in self.records)
        agreement = sum(
            (
                record.first_pass_findings[0].selection_label,
                record.first_pass_findings[0].packet_sufficiency,
            )
            == (
                record.first_pass_findings[1].selection_label,
                record.first_pass_findings[1].packet_sufficiency,
            )
            for record in self.records
        )
        selection_agreement = sum(
            record.first_pass_findings[0].selection_label
            == record.first_pass_findings[1].selection_label
            for record in self.records
        )
        sufficiency_agreement = sum(
            record.first_pass_findings[0].packet_sufficiency
            == record.first_pass_findings[1].packet_sufficiency
            for record in self.records
        )
        if (
            eligible != self.score_eligible_record_count
            or agreement != self.first_pass_agreement_count
            or selection_agreement != self.first_pass_selection_agreement_count
            or sufficiency_agreement != self.first_pass_sufficiency_agreement_count
            or not isclose(
                self.first_pass_percent_agreement,
                agreement / self.total_record_count,
            )
            or not isclose(
                self.first_pass_selection_percent_agreement,
                selection_agreement / self.total_record_count,
            )
            or not isclose(
                self.first_pass_sufficiency_percent_agreement,
                sufficiency_agreement / self.total_record_count,
            )
        ):
            raise ValueError("gold counts and first-pass agreement are inconsistent")
        needs_adjudication = any(
            record.resolution == "third_reviewer_adjudication"
            for record in self.records
        )
        if needs_adjudication != (self.adjudication_completion_sha256 is not None):
            raise ValueError("gold adjudication identity does not match resolutions")
        return self


class EvidenceSelectionExpertPilotSafetyAuditItem(BaseModel):
    """Model-identity-blinded selected claim reviewed only after gold freeze."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    audit_item_id: str = Field(pattern=r"^safety-[a-f0-9]{16}$")
    blinded_run_id: str = Field(pattern=r"^blinded-run-[a-f0-9]{12}$")
    title: str
    bounded_source_text: tuple[str, ...] = Field(min_length=1)
    agent_explanation: str = Field(min_length=1)
    agent_evidence_spans: tuple[str, ...]

    @field_validator("bounded_source_text", "agent_evidence_spans", mode="before")
    @classmethod
    def _accept_json_arrays(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value


class EvidenceSelectionExpertPilotSafetyAuditRequest(BaseModel):
    """Deterministic post-gold request covering every registered selected claim."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_expert_pilot_safety_request.v1"]
    study_id: str
    frozen_gold_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluation_protocol_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    review_phase: Literal["after_adjudicated_gold_freeze"]
    hide_model_identity: Literal[True] = True
    hide_gold_labels: Literal[True] = True
    completion_status: Literal["requires_human_safety_findings"]
    items: tuple[EvidenceSelectionExpertPilotSafetyAuditItem, ...]

    @field_validator("items", mode="before")
    @classmethod
    def _accept_json_items(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value


class EvidenceSelectionExpertPilotCaseMetrics(BaseModel):
    """One case score used by the preserved PR150 quality gate."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    case_id: str
    evaluation_role: Literal["primary", "canary"]
    metrics: EvidenceSelectionBenchmarkMetrics


class EvidenceSelectionExpertPilotModelRunResult(BaseModel):
    """Deterministic eligible-gold score and categorical safety count."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    run_id: str
    model_role: Literal["current", "candidate"]
    model_id: str
    run_index: int = Field(ge=1)
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    metrics: EvidenceSelectionBenchmarkMetrics | None
    case_metrics: tuple[EvidenceSelectionExpertPilotCaseMetrics, ...]
    canary_gate_status: Literal["passed", "failed", "unavailable"]
    high_severity_overclaim_count: int = Field(ge=0)
    not_assessable_safety_count: int = Field(ge=0)
    gate_status: Literal["passed", "failed", "unavailable"]

    @model_validator(mode="after")
    def _availability_is_consistent(
        self,
    ) -> EvidenceSelectionExpertPilotModelRunResult:
        if self.metrics is None and self.gate_status != "unavailable":
            raise ValueError("missing model-run metrics require an unavailable gate")
        return self


class EvidenceSelectionExpertPilotModelSummary(BaseModel):
    """Worst-run diagnostic evidence for one exact model identity."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    model_role: Literal["current", "candidate"]
    model_id: str
    run_count: Literal[3]
    worst_run_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    worst_run_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    worst_run_decision_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    exact_decision_repeatability: float | None = Field(default=None, ge=0.0, le=1.0)
    canary_gate_status: Literal["passed", "failed", "unavailable"]
    maximum_run_high_severity_overclaim_count: int = Field(ge=0)
    first_pass_percent_agreement: float = Field(ge=0.0, le=1.0)
    gate_status: Literal["passed", "failed", "unavailable"]

    @model_validator(mode="after")
    def _availability_is_consistent(
        self,
    ) -> EvidenceSelectionExpertPilotModelSummary:
        metrics_available = all(
            metric is not None
            for metric in (
                self.worst_run_precision,
                self.worst_run_recall,
                self.worst_run_decision_coverage,
                self.exact_decision_repeatability,
            )
        )
        if not metrics_available and self.gate_status != "unavailable":
            raise ValueError(
                "missing model summary metrics require an unavailable gate"
            )
        return self


class EvidenceSelectionExpertPilotResult(BaseModel):
    """Externally attested pilot result; diagnostic, never production calibration."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_expert_pilot_result.v1"]
    study_id: str
    expert_study_status: Literal["externally_attested"]
    external_identity_attestation_verified: Literal[True]
    issuer_key_id: str
    issuer_public_key_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer_registry_payload_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    frozen_gold_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    safety_request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    safety_completion_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    gold: EvidenceSelectionExpertPilotGoldArtifact
    model_run_results: tuple[EvidenceSelectionExpertPilotModelRunResult, ...] = Field(
        min_length=6,
        max_length=6,
    )
    model_summaries: tuple[EvidenceSelectionExpertPilotModelSummary, ...] = Field(
        min_length=2,
        max_length=2,
    )
    comparison_status: Literal[
        "current_only_passed",
        "candidate_only_passed",
        "both_passed",
        "neither_passed",
        "unavailable",
    ]
    model_adoption_decision: Literal["not_evaluated_diagnostic_only"]
    production_readiness_claim: Literal[False] = False
    production_calibration_claim: Literal[False] = False
    trusted_graph_readiness_claim: Literal[False] = False


__all__ = [
    "EvidenceSelectionExpertPilotCaseMetrics",
    "EvidenceSelectionExpertPilotEvaluationProtocol",
    "EvidenceSelectionExpertPilotGoldArtifact",
    "EvidenceSelectionExpertPilotGoldRecord",
    "EvidenceSelectionExpertPilotModelRunRef",
    "EvidenceSelectionExpertPilotModelRunResult",
    "EvidenceSelectionExpertPilotModelSummary",
    "EvidenceSelectionExpertPilotResult",
    "EvidenceSelectionExpertPilotSafetyAuditItem",
    "EvidenceSelectionExpertPilotSafetyAuditRequest",
]
