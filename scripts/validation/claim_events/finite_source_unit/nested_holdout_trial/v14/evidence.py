"""Canonical evidence envelope for V14 three-stage execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v14.custody import (
    V14_EXECUTION_CONTRACT_VERSION,
    V14_EXECUTION_MANIFEST_SHA256,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v14.lineage import (
    V14AttemptLineageInput,
    require_v14_attempt_lineage,
)
from scripts.validation.claim_events.finite_source_unit.normalization.review import (
    LocalReviewDisposition,
    SourceUnitNormalizedReviewResult,
)
from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    canonical_json_sha256,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
        ModelAttemptAuditRecord,
    )

    from scripts.validation.claim_events.finite_source_unit.contracts import (
        SourceUnitExtractionOutput,
    )
    from scripts.validation.claim_events.finite_source_unit.normalization.v13_review_contracts import (
        SourceUnitNormalizedReviewOutputV13V6,
    )
    from scripts.validation.claim_events.finite_source_unit.normalization.v14_contracts import (
        SourceUnitNormalizationProposalV14,
    )
    from scripts.validation.claim_events.finite_source_unit.normalization.v14_service import (
        V14NormalizationEnvelope,
    )
    from scripts.validation.claim_events.finite_source_unit.service import (
        SourceUnitExtractionResult,
    )
    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )

V14ExecutionStage = Literal["primary", "structure_normalization", "normalized_review"]


class V14EvidenceObserver(Protocol):
    def __call__(self, evidence: V14ThreeCallAgentEvidence) -> None: ...


@dataclass(frozen=True, slots=True)
class V14ThreeCallAgentEvidence:
    """Raw V14 proposal, derived envelope, review, and exact audit lineage."""

    unit: FrozenSourceUnit
    execution_model_id: str
    execution_namespace: str
    audit_evidence_unit_id: str
    original_extraction: SourceUnitExtractionOutput | None
    original_result: SourceUnitExtractionResult | None
    original_raw_output: dict[str, object] | None
    normalization_proposal: SourceUnitNormalizationProposalV14 | None
    normalization_envelope: V14NormalizationEnvelope | None
    normalization_raw_output: dict[str, object] | None
    normalized_review: SourceUnitNormalizedReviewOutputV13V6 | None
    review_result: SourceUnitNormalizedReviewResult | None
    review_raw_output: dict[str, object] | None
    records: tuple[ModelAttemptAuditRecord, ...]
    error_type: str | None
    failed_stage: V14ExecutionStage | None
    execution_complete: bool
    failure_before_audit_record: bool
    execution_contract_version: str = V14_EXECUTION_CONTRACT_VERSION
    execution_manifest_sha256: str = V14_EXECUTION_MANIFEST_SHA256
    evidence_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _require_consistency(self)
        object.__setattr__(self, "evidence_sha256", _evidence_sha256(self))

    @property
    def local_review_passed(self) -> bool:
        return (
            self.error_type is None
            and self.failed_stage is None
            and self.review_result is not None
            and self.review_result.local_review_disposition
            is LocalReviewDisposition.PASS
        )

    @property
    def scientifically_qualified(self) -> bool:
        """Three calls still lack independent completeness and live receipts."""

        return False


def build_v14_evidence(  # noqa: PLR0913
    *,
    unit: FrozenSourceUnit,
    execution_model_id: str,
    execution_namespace: str,
    audit_evidence_unit_id: str,
    original_output: SourceUnitExtractionOutput | None,
    original_result: SourceUnitExtractionResult | None,
    original_raw: dict[str, object] | None,
    proposal: SourceUnitNormalizationProposalV14 | None,
    normalization: V14NormalizationEnvelope | None,
    normalization_raw: dict[str, object] | None,
    review_output: SourceUnitNormalizedReviewOutputV13V6 | None,
    review_result: SourceUnitNormalizedReviewResult | None,
    review_raw: dict[str, object] | None,
    records: tuple[ModelAttemptAuditRecord, ...],
    error_type: str | None,
    failed_stage: V14ExecutionStage | None,
    execution_complete: bool,
    failure_before_audit_record: bool,
) -> V14ThreeCallAgentEvidence:
    return V14ThreeCallAgentEvidence(
        unit=unit,
        execution_model_id=execution_model_id,
        execution_namespace=execution_namespace,
        audit_evidence_unit_id=audit_evidence_unit_id,
        original_extraction=original_output,
        original_result=original_result,
        original_raw_output=original_raw,
        normalization_proposal=proposal,
        normalization_envelope=normalization,
        normalization_raw_output=normalization_raw,
        normalized_review=review_output,
        review_result=review_result,
        review_raw_output=review_raw,
        records=records,
        error_type=error_type,
        failed_stage=failed_stage,
        execution_complete=execution_complete,
        failure_before_audit_record=failure_before_audit_record,
    )


def _require_consistency(evidence: V14ThreeCallAgentEvidence) -> None:
    if evidence.execution_contract_version != V14_EXECUTION_CONTRACT_VERSION:
        raise ValueError("V14 evidence contract version is not issued")
    if evidence.execution_manifest_sha256 != V14_EXECUTION_MANIFEST_SHA256:
        raise ValueError("V14 evidence manifest is not issued")
    if any(
        record.execution_contract_version != V14_EXECUTION_CONTRACT_VERSION
        for record in evidence.records
    ):
        raise ValueError("V14 audit records disagree with execution lineage")
    require_v14_attempt_lineage(
        V14AttemptLineageInput(
            unit=evidence.unit,
            execution_model_id=evidence.execution_model_id,
            execution_namespace=evidence.execution_namespace,
            audit_evidence_unit_id=evidence.audit_evidence_unit_id,
            original_result=evidence.original_result,
            original_raw_output=evidence.original_raw_output,
            normalization_envelope=evidence.normalization_envelope,
            normalization_raw_output=evidence.normalization_raw_output,
            records=evidence.records,
            execution_complete=evidence.execution_complete,
            failure_before_audit_record=evidence.failure_before_audit_record,
            failed_stage=evidence.failed_stage,
            error_type=evidence.error_type,
        )
    )
    if evidence.original_result is not None:
        if evidence.original_extraction != evidence.original_result.output:
            raise ValueError("V14 primary parsed output is detached")
        evidence.original_result.require_canonical_envelope(unit=evidence.unit)
    _require_raw_stage(
        role="primary",
        parsed=evidence.original_extraction,
        raw=evidence.original_raw_output,
        records=evidence.records,
        allow_failed_raw=evidence.failed_stage == "primary",
    )
    if evidence.normalization_envelope is not None:
        if evidence.normalization_proposal != evidence.normalization_envelope.proposal:
            raise ValueError("V14 proposal is detached from its derived envelope")
        if evidence.original_result is None:
            raise ValueError("V14 normalization requires original extraction")
        evidence.normalization_envelope.require_canonical_envelope(
            unit=evidence.unit,
            original=evidence.original_result,
        )
    _require_raw_stage(
        role="structure_normalization",
        parsed=evidence.normalization_proposal,
        raw=evidence.normalization_raw_output,
        records=evidence.records,
        allow_failed_raw=evidence.failed_stage == "structure_normalization",
    )
    if evidence.review_result is not None:
        if evidence.normalization_envelope is None:
            raise ValueError("V14 review requires canonical normalization")
        if evidence.normalized_review != evidence.review_result.output:
            raise ValueError("V14 review parsed output is detached")
        if (
            evidence.review_result.normalization_envelope_sha256
            != evidence.normalization_envelope.canonical_result.envelope_sha256
        ):
            raise ValueError("V14 review is detached from canonical normalization")
    _require_raw_stage(
        role="normalized_review",
        parsed=evidence.normalized_review,
        raw=evidence.review_raw_output,
        records=evidence.records,
        allow_failed_raw=evidence.failed_stage == "normalized_review",
    )


def _require_raw_stage(
    *,
    role: V14ExecutionStage,
    parsed: object | None,
    raw: dict[str, object] | None,
    records: tuple[ModelAttemptAuditRecord, ...],
    allow_failed_raw: bool,
) -> None:
    role_records = tuple(record for record in records if record.attempt_role == role)
    if parsed is None:
        if raw is not None and not allow_failed_raw:
            raise ValueError(f"V14 {role} raw output lacks parsed evidence")
        if raw is not None and (
            len(role_records) != 1
            or role_records[0].raw_model_payload != raw
            or role_records[0].payload_sha256 != canonical_json_sha256(raw)
        ):
            raise ValueError(f"V14 failed {role} raw output is not audited")
        return
    model_dump = getattr(parsed, "model_dump", None)
    if model_dump is None or model_dump(mode="json") != raw:
        raise ValueError(f"V14 {role} raw and parsed outputs disagree")
    if len(role_records) != 1 or role_records[0].raw_model_payload != raw:
        raise ValueError(f"V14 {role} output is not bound to one audit record")
    if role_records[0].payload_sha256 != canonical_json_sha256(raw):
        raise ValueError(f"V14 {role} payload hash is invalid")


def _evidence_sha256(evidence: V14ThreeCallAgentEvidence) -> str:
    return canonical_json_sha256(
        {
            "unit_input_sha256": evidence.unit.input_sha256,
            "execution_model_id": evidence.execution_model_id,
            "execution_namespace": evidence.execution_namespace,
            "audit_evidence_unit_id": evidence.audit_evidence_unit_id,
            "original_raw_output": evidence.original_raw_output,
            "normalization_raw_output": evidence.normalization_raw_output,
            "normalization_envelope_sha256": (
                None
                if evidence.normalization_envelope is None
                else evidence.normalization_envelope.envelope_sha256
            ),
            "review_raw_output": evidence.review_raw_output,
            "review_output_sha256": (
                None
                if evidence.review_result is None
                else evidence.review_result.output_sha256
            ),
            "records": [record.as_json() for record in evidence.records],
            "error_type": evidence.error_type,
            "failed_stage": evidence.failed_stage,
            "execution_complete": evidence.execution_complete,
            "failure_before_audit_record": evidence.failure_before_audit_record,
            "execution_contract_version": evidence.execution_contract_version,
            "execution_manifest_sha256": evidence.execution_manifest_sha256,
        }
    )


__all__ = [
    "V14EvidenceObserver",
    "V14ExecutionStage",
    "V14ThreeCallAgentEvidence",
    "build_v14_evidence",
]
