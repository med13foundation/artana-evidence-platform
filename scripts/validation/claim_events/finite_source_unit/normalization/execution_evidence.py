"""Canonical evidence envelope for three-stage source-unit execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

from scripts.validation.claim_events.finite_source_unit.normalization.execution_custody import (
    expected_issued_manifest,
)
from scripts.validation.claim_events.finite_source_unit.normalization.review import (
    LocalReviewDisposition,
    SourceUnitNormalizedReviewResult,
)
from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    SourceUnitNormalizationResult,
    canonical_json_sha256,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
        ModelAttemptAuditRecord,
    )

    from scripts.validation.claim_events.finite_source_unit.contracts import (
        SourceUnitExtractionOutput,
    )
    from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
        SourceUnitNormalizationOutput,
        SourceUnitNormalizedReviewOutput,
    )
    from scripts.validation.claim_events.finite_source_unit.service import (
        SourceUnitExtractionResult,
    )

ExecutionStage = Literal["primary", "structure_normalization", "normalized_review"]


@dataclass(frozen=True, slots=True)
class ThreeCallAgentRunEvidence:
    """Non-lossy evidence from three ordered, audited provider calls."""

    original_extraction: SourceUnitExtractionOutput | None
    original_result: SourceUnitExtractionResult | None
    original_raw_output: dict[str, object] | None
    normalized_extraction: SourceUnitNormalizationOutput | None
    normalized_result: SourceUnitNormalizationResult | None
    normalized_raw_output: dict[str, object] | None
    normalized_review: SourceUnitNormalizedReviewOutput | None
    review_result: SourceUnitNormalizedReviewResult | None
    review_raw_output: dict[str, object] | None
    records: tuple[ModelAttemptAuditRecord, ...]
    error_type: str | None
    execution_contract_version: str | None
    failed_stage: ExecutionStage | None
    execution_manifest_sha256: str | None = None
    evidence_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _require_consistent_agent_run_evidence(self)
        object.__setattr__(self, "evidence_sha256", _agent_run_evidence_sha256(self))

    @property
    def local_review_passed(self) -> bool:
        """Report local consistency without claiming source completeness."""

        return (
            self.error_type is None
            and self.failed_stage is None
            and self.review_result is not None
            and self.review_result.local_review_disposition
            is LocalReviewDisposition.PASS
        )

    @property
    def scientifically_qualified(self) -> bool:
        """Remain false: this three-call topology has no completeness witness."""

        return False


class ThreeCallEvidenceObserver(Protocol):
    def __call__(self, evidence: ThreeCallAgentRunEvidence) -> None: ...


class ModelAttemptObserver(Protocol):
    def __call__(self, record: ModelAttemptAuditRecord) -> None: ...


def build_three_call_agent_evidence(  # noqa: PLR0913
    *,
    original_output: SourceUnitExtractionOutput | None,
    original_result: SourceUnitExtractionResult | None,
    original_raw: dict[str, object] | None,
    normalized_output: SourceUnitNormalizationOutput | None,
    normalized_result: SourceUnitNormalizationResult | None,
    normalized_raw: dict[str, object] | None,
    review_output: SourceUnitNormalizedReviewOutput | None,
    review_result: SourceUnitNormalizedReviewResult | None,
    review_raw: dict[str, object] | None,
    records: tuple[ModelAttemptAuditRecord, ...],
    error_type: str | None,
    execution_contract_version: str | None,
    execution_manifest_sha256: str | None,
    failed_stage: ExecutionStage | None,
) -> ThreeCallAgentRunEvidence:
    return ThreeCallAgentRunEvidence(
        original_extraction=original_output,
        original_result=original_result,
        original_raw_output=original_raw,
        normalized_extraction=normalized_output,
        normalized_result=normalized_result,
        normalized_raw_output=normalized_raw,
        normalized_review=review_output,
        review_result=review_result,
        review_raw_output=review_raw,
        records=records,
        error_type=error_type,
        execution_contract_version=execution_contract_version,
        execution_manifest_sha256=execution_manifest_sha256,
        failed_stage=failed_stage,
    )


def _require_consistent_agent_run_evidence(evidence: ThreeCallAgentRunEvidence) -> None:
    contract_version = evidence.execution_contract_version
    if contract_version is not None and contract_version.startswith(
        "tg04.finite_source_unit.v13_execution."
    ):
        expected_manifest = expected_issued_manifest(contract_version)
        if evidence.execution_manifest_sha256 != expected_manifest:
            raise ValueError("issued V13 evidence manifest does not match its lineage")
    elif evidence.execution_manifest_sha256 is not None:
        raise ValueError("caller-composed evidence cannot carry an issued manifest")
    if any(
        record.execution_contract_version != evidence.execution_contract_version
        for record in evidence.records
    ):
        raise ValueError("audit records disagree with execution contract lineage")
    _require_stage_consistency(
        stage="primary",
        parsed=evidence.original_extraction,
        result_output=(
            None if evidence.original_result is None else evidence.original_result.output
        ),
        raw=evidence.original_raw_output,
        records=evidence.records,
    )
    _require_stage_consistency(
        stage="structure_normalization",
        parsed=evidence.normalized_extraction,
        result_output=(
            None
            if evidence.normalized_result is None
            else evidence.normalized_result.output
        ),
        raw=evidence.normalized_raw_output,
        records=evidence.records,
    )
    _require_stage_consistency(
        stage="normalized_review",
        parsed=evidence.normalized_review,
        result_output=(
            None if evidence.review_result is None else evidence.review_result.output
        ),
        raw=evidence.review_raw_output,
        records=evidence.records,
    )
    if evidence.review_result is None:
        return
    if evidence.normalized_result is None:
        raise ValueError("review result requires a normalized result")
    if (
        evidence.review_result.normalization_envelope_sha256
        != evidence.normalized_result.envelope_sha256
    ):
        raise ValueError("review result is detached from normalization custody")
    if (
        evidence.review_result.source_unit_input_sha256
        != evidence.records[-1].input_sha256
    ):
        raise ValueError("review result is detached from source-unit custody")


def _require_stage_consistency(
    *,
    stage: ExecutionStage,
    parsed: object | None,
    result_output: object | None,
    raw: dict[str, object] | None,
    records: tuple[ModelAttemptAuditRecord, ...],
) -> None:
    present = (parsed is not None, result_output is not None, raw is not None)
    if len(set(present)) != 1:
        raise ValueError(f"{stage} evidence fields must be present together")
    if parsed is None:
        return
    if parsed != result_output:
        raise ValueError(f"{stage} parsed output and validated result disagree")
    model_dump = getattr(parsed, "model_dump", None)
    if model_dump is None or model_dump(mode="json") != raw:
        raise ValueError(f"{stage} raw payload and parsed output disagree")
    stage_records = tuple(record for record in records if record.attempt_role == stage)
    if len(stage_records) != 1 or stage_records[0].raw_model_payload != raw:
        raise ValueError(f"{stage} raw payload is not bound to one audit record")
    if stage_records[0].payload_sha256 != canonical_json_sha256(raw):
        raise ValueError(f"{stage} audit payload hash does not match raw payload")


def _agent_run_evidence_sha256(evidence: ThreeCallAgentRunEvidence) -> str:
    return canonical_json_sha256(
        {
            "original_raw_output": evidence.original_raw_output,
            "normalized_raw_output": evidence.normalized_raw_output,
            "review_raw_output": evidence.review_raw_output,
            "original_envelope_sha256": (
                None
                if evidence.original_result is None
                else evidence.original_result.envelope_sha256
            ),
            "normalization_envelope_sha256": (
                None
                if evidence.normalized_result is None
                else evidence.normalized_result.envelope_sha256
            ),
            "review_output_sha256": (
                None
                if evidence.review_result is None
                else evidence.review_result.output_sha256
            ),
            "records": [record.as_json() for record in evidence.records],
            "error_type": evidence.error_type,
            "execution_contract_version": evidence.execution_contract_version,
            "execution_manifest_sha256": evidence.execution_manifest_sha256,
            "failed_stage": evidence.failed_stage,
        }
    )


__all__ = [
    "ExecutionStage",
    "ModelAttemptObserver",
    "ThreeCallAgentRunEvidence",
    "ThreeCallEvidenceObserver",
    "build_three_call_agent_evidence",
]
