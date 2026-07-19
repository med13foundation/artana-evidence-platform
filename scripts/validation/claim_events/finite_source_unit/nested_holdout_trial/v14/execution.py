"""Three-stage orchestration for sealed V14 deterministic normalization."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    fingerprinted_step_key,
    start_model_attempt_audit,
    stop_model_attempt_audit,
)

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitExtractionOutput,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v14.custody import (
    V14_EXECUTION_CONTRACT_VERSION,
    V14_EXECUTION_MANIFEST_SHA256,
    V14_EXECUTION_MODEL_IDS,
    V14ExecutionContractError,
    computed_v14_execution_manifest_sha256,
    require_v14_execution_manifest,
    v14_execution_manifest,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v14.evidence import (
    V14EvidenceObserver,
    V14ExecutionStage,
    V14ThreeCallAgentEvidence,
    build_v14_evidence,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v14.prompts import (
    V14_NORMALIZATION_PROMPT_VERSION,
    V14_NORMALIZED_REVIEW_PROMPT_VERSION,
    V14_PROMPT_POLICY,
    v14_normalization_prompt,
    v14_normalized_review_prompt,
)
from scripts.validation.claim_events.finite_source_unit.normalization.review import (
    SourceUnitNormalizedReviewResult,
    review_source_unit_normalization,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_review import (
    bind_v13_context_dimension_review,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_review_contracts import (
    SourceUnitNormalizedReviewOutputV13V6,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v14_contracts import (
    SourceUnitNormalizationProposalV14,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v14_service import (
    V14NormalizationEnvelope,
    normalize_source_unit_proposal_v14,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    SourceUnitExtractionResult,
    extract_source_unit,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
        ModelAttemptAuditRecord,
    )

    from scripts.validation.claim_events.finite_source_unit.normalization.execution_evidence import (
        ModelAttemptObserver,
    )
    from scripts.validation.claim_events.finite_source_unit.service import (
        FiniteSourceUnitModelClient,
    )
    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )


async def execute_v14_source_unit_agents(  # noqa: PLR0913, PLR0915
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
    audit_evidence_unit_id: str | None = None,
    evidence_observer: V14EvidenceObserver | None = None,
    attempt_observer: ModelAttemptObserver | None = None,
) -> V14ThreeCallAgentEvidence:
    """Run exactly three V14 stages and stop on the first invalid result."""

    require_v14_execution_manifest()
    if model_id not in V14_EXECUTION_MODEL_IDS:
        raise V14ExecutionContractError("V14 execution model is not authorized")
    namespace = fingerprinted_step_key(
        V14_EXECUTION_CONTRACT_VERSION,
        V14_EXECUTION_MANIFEST_SHA256,
        execution_namespace,
    )
    evidence_unit_id = audit_evidence_unit_id or unit.unit_id
    audit = start_model_attempt_audit(
        evidence_unit_id=evidence_unit_id,
        execution_contract_version=V14_EXECUTION_CONTRACT_VERSION,
        record_observer=attempt_observer,
    )
    original_output: SourceUnitExtractionOutput | None = None
    original_result: SourceUnitExtractionResult | None = None
    original_raw: dict[str, object] | None = None
    proposal: SourceUnitNormalizationProposalV14 | None = None
    normalization: V14NormalizationEnvelope | None = None
    normalization_raw: dict[str, object] | None = None
    review_output: SourceUnitNormalizedReviewOutputV13V6 | None = None
    review_result: SourceUnitNormalizedReviewResult | None = None
    review_raw: dict[str, object] | None = None
    error_type: str | None = None
    active_stage: V14ExecutionStage = "primary"
    failed_stage: V14ExecutionStage | None = None
    try:
        original = await extract_source_unit(
            client=client,
            tenant=tenant,
            model_id=model_id,
            execution_namespace=namespace,
            unit=unit,
            prompt_policy=V14_PROMPT_POLICY,
        )
        original_output = original.parsed
        original_result = original.value
        original_raw = original.raw_output
        _observe(
            evidence_observer,
            _build_evidence(
                unit=unit,
                execution_model_id=model_id,
                execution_namespace=execution_namespace,
                audit_evidence_unit_id=evidence_unit_id,
                original_output=original_output,
                original_result=original_result,
                original_raw=original_raw,
                proposal=proposal,
                normalization=normalization,
                normalization_raw=normalization_raw,
                review_output=review_output,
                review_result=review_result,
                review_raw=review_raw,
                records=tuple(audit.records),
                error_type=None,
                failed_stage=None,
                execution_complete=False,
                failure_before_audit_record=False,
            ),
        )

        active_stage = "structure_normalization"
        normalized = await normalize_source_unit_proposal_v14(
            client=client,
            tenant=tenant,
            model_id=model_id,
            execution_namespace=namespace,
            unit=unit,
            original=original_result,
            original_raw_output=original_raw,
            prompt=v14_normalization_prompt(unit=unit, original=original_result),
            prompt_version=V14_NORMALIZATION_PROMPT_VERSION,
        )
        proposal = normalized.parsed
        normalization = normalized.value
        normalization_raw = normalized.raw_output
        _observe(
            evidence_observer,
            _build_evidence(
                unit=unit,
                execution_model_id=model_id,
                execution_namespace=execution_namespace,
                audit_evidence_unit_id=evidence_unit_id,
                original_output=original_output,
                original_result=original_result,
                original_raw=original_raw,
                proposal=proposal,
                normalization=normalization,
                normalization_raw=normalization_raw,
                review_output=review_output,
                review_result=review_result,
                review_raw=review_raw,
                records=tuple(audit.records),
                error_type=None,
                failed_stage=None,
                execution_complete=False,
                failure_before_audit_record=False,
            ),
        )

        active_stage = "normalized_review"
        reviewed = await review_source_unit_normalization(
            client=client,
            tenant=tenant,
            model_id=model_id,
            execution_namespace=namespace,
            unit=unit,
            original=original_result,
            normalized=normalization.canonical_result,
            original_raw_output=original_raw,
            normalized_raw_output=normalization_raw,
            prompt=v14_normalized_review_prompt(
                unit=unit,
                original=original_result,
                normalized=normalization.canonical_result,
            ),
            prompt_version=V14_NORMALIZED_REVIEW_PROMPT_VERSION,
            output_schema=SourceUnitNormalizedReviewOutputV13V6,
            review_binder=bind_v13_context_dimension_review,
        )
        review_output = reviewed.parsed
        review_result = reviewed.value
        review_raw = reviewed.raw_output
    except Exception as exc:  # noqa: BLE001 - preserve terminal category.
        error_type = type(exc).__name__
        failed_stage = active_stage
        failed_raw = _failed_raw(
            active_stage=active_stage,
            records=tuple(audit.records),
        )
        if active_stage == "primary" and original_raw is None:
            original_raw = failed_raw
        elif active_stage == "structure_normalization" and normalization_raw is None:
            normalization_raw = failed_raw
        elif active_stage == "normalized_review" and review_raw is None:
            review_raw = failed_raw
    finally:
        stop_model_attempt_audit(audit)
    failure_before_audit_record = failed_stage is not None and not any(
        record.attempt_role == failed_stage for record in audit.records
    )
    evidence = _build_evidence(
        unit=unit,
        execution_model_id=model_id,
        execution_namespace=execution_namespace,
        audit_evidence_unit_id=evidence_unit_id,
        original_output=original_output,
        original_result=original_result,
        original_raw=original_raw,
        proposal=proposal,
        normalization=normalization,
        normalization_raw=normalization_raw,
        review_output=review_output,
        review_result=review_result,
        review_raw=review_raw,
        records=tuple(audit.records),
        error_type=error_type,
        failed_stage=failed_stage,
        execution_complete=True,
        failure_before_audit_record=failure_before_audit_record,
    )
    _observe(evidence_observer, evidence)
    return evidence


def has_locally_consistent_v14_execution(evidence: V14ThreeCallAgentEvidence) -> bool:
    """Check issued local lineage without claiming receipt or completeness proof."""

    return (
        evidence.execution_complete
        and evidence.execution_contract_version == V14_EXECUTION_CONTRACT_VERSION
        and evidence.execution_manifest_sha256 == V14_EXECUTION_MANIFEST_SHA256
        and evidence.error_type is None
        and evidence.failed_stage is None
        and tuple(record.attempt_role for record in evidence.records)
        == ("primary", "structure_normalization", "normalized_review")
        and tuple(record.output_schema_identity for record in evidence.records)
        == (
            _schema_identity(SourceUnitExtractionOutput),
            _schema_identity(SourceUnitNormalizationProposalV14),
            _schema_identity(SourceUnitNormalizedReviewOutputV13V6),
        )
        and all(
            record.execution_contract_version == V14_EXECUTION_CONTRACT_VERSION
            and record.validation_outcome == "accepted"
            and record.provider_response_id is not None
            and record.provider_output_sha256 is not None
            and record.model_id in V14_EXECUTION_MODEL_IDS
            for record in evidence.records
        )
    )


def _failed_raw(
    *,
    active_stage: V14ExecutionStage,
    records: tuple[ModelAttemptAuditRecord, ...],
) -> dict[str, object] | None:
    matches = tuple(record for record in records if record.attempt_role == active_stage)
    return matches[-1].raw_model_payload if matches else None


def _build_evidence(  # noqa: PLR0913
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
    return build_v14_evidence(
        unit=unit,
        execution_model_id=execution_model_id,
        execution_namespace=execution_namespace,
        audit_evidence_unit_id=audit_evidence_unit_id,
        original_output=original_output,
        original_result=original_result,
        original_raw=original_raw,
        proposal=proposal,
        normalization=normalization,
        normalization_raw=normalization_raw,
        review_output=review_output,
        review_result=review_result,
        review_raw=review_raw,
        records=records,
        error_type=error_type,
        failed_stage=failed_stage,
        execution_complete=execution_complete,
        failure_before_audit_record=failure_before_audit_record,
    )


def _observe(
    observer: V14EvidenceObserver | None,
    evidence: V14ThreeCallAgentEvidence,
) -> None:
    if observer is not None:
        observer(evidence)


def _schema_identity(schema: type[object]) -> str:
    return f"{schema.__module__}.{schema.__qualname__}"


__all__ = [
    "V14_EXECUTION_CONTRACT_VERSION",
    "V14_EXECUTION_MANIFEST_SHA256",
    "V14_EXECUTION_MODEL_IDS",
    "V14ExecutionContractError",
    "V14ThreeCallAgentEvidence",
    "computed_v14_execution_manifest_sha256",
    "execute_v14_source_unit_agents",
    "has_locally_consistent_v14_execution",
    "v14_execution_manifest",
]
