"""Deterministic local audit-lineage validation for V14 execution."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.document_extraction_support.llm_extraction.attempt_audit import (
    canonical_openai_response_id,
)
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    bind_prompt_to_invocation,
    kernel_run_id_for_invocation,
    output_schema_json_sha256,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    fingerprinted_step_key,
)

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitExtractionOutput,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v14.custody import (
    V14_EXECUTION_CONTRACT_VERSION,
    V14_EXECUTION_MANIFEST_SHA256,
    V14_EXECUTION_MODEL_IDS,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v14.prompts import (
    V14_NORMALIZATION_PROMPT_VERSION,
    V14_NORMALIZED_REVIEW_PROMPT_VERSION,
    V14_PROMPT_POLICY,
    v14_normalization_prompt,
    v14_normalized_review_prompt,
)
from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    canonical_json_sha256,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_review_contracts import (
    SourceUnitNormalizedReviewOutputV13V6,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v14_contracts import (
    SourceUnitNormalizationProposalV14,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v14_service import (
    V14_MAPPING_DERIVATION_VERSION,
)

_UUID4_VERSION = 4
_SHA256_HEX_LENGTH = 64
_EXPECTED_STAGE_COUNT = 3

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
        ModelAttemptAuditRecord,
    )
    from pydantic import BaseModel

    from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v14.evidence import (
        V14ExecutionStage,
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


@dataclass(frozen=True, slots=True)
class V14AttemptLineageInput:
    unit: FrozenSourceUnit
    execution_model_id: str
    execution_namespace: str
    audit_evidence_unit_id: str
    original_result: SourceUnitExtractionResult | None
    original_raw_output: dict[str, object] | None
    normalization_envelope: V14NormalizationEnvelope | None
    normalization_raw_output: dict[str, object] | None
    records: tuple[ModelAttemptAuditRecord, ...]
    execution_complete: bool
    failure_before_audit_record: bool
    failed_stage: V14ExecutionStage | None
    error_type: str | None


@dataclass(frozen=True, slots=True)
class _StageExpectation:
    role: V14ExecutionStage
    schema: type[BaseModel]
    prompt: str
    step_key: str


def require_v14_attempt_lineage(lineage: V14AttemptLineageInput) -> None:
    """Reject locally rewritten records while leaving provider proof to receipts."""

    if lineage.execution_model_id not in V14_EXECUTION_MODEL_IDS:
        raise ValueError("V14 evidence uses an unauthorized model")
    if not lineage.execution_namespace.strip():
        raise ValueError("V14 execution namespace must be nonempty")
    if not lineage.audit_evidence_unit_id.strip():
        raise ValueError("V14 audit evidence unit must be nonempty")

    expectations = _stage_expectations(lineage)
    _require_execution_topology(lineage=lineage, expectations=expectations)
    selected = expectations[: len(lineage.records)]

    evidence_unit_sha256 = hashlib.sha256(
        lineage.audit_evidence_unit_id.encode()
    ).hexdigest()
    invocation_ids: set[str] = set()
    for index, (record, expected) in enumerate(
        zip(lineage.records, selected, strict=True)
    ):
        _require_record_identity(
            record=record,
            expected=expected,
            lineage=lineage,
            evidence_unit_sha256=evidence_unit_sha256,
            invocation_ids=invocation_ids,
        )
        is_terminal_failure = (
            lineage.execution_complete
            and lineage.failed_stage == expected.role
            and index == len(lineage.records) - 1
        )
        if is_terminal_failure:
            if record.validation_outcome == "accepted":
                raise ValueError("V14 failed stage has an accepted audit record")
            if record.error_type != lineage.error_type:
                raise ValueError("V14 failed stage error category is detached")
        elif record.validation_outcome != "accepted" or record.error_type is not None:
            raise ValueError("V14 completed stage lacks an accepted audit record")


def _require_execution_topology(
    *,
    lineage: V14AttemptLineageInput,
    expectations: tuple[_StageExpectation, ...],
) -> None:
    if len(lineage.records) > len(expectations):
        raise ValueError("V14 audit records exceed executable stage custody")
    if not lineage.execution_complete:
        if (
            lineage.failed_stage is not None
            or lineage.error_type is not None
            or lineage.failure_before_audit_record
        ):
            raise ValueError("V14 intermediate evidence cannot be terminal")
        if len(lineage.records) not in {1, 2}:
            raise ValueError("V14 intermediate evidence requires one completed stage")
        return
    if lineage.failed_stage is None:
        if (
            lineage.error_type is not None
            or lineage.failure_before_audit_record
            or len(lineage.records) != _EXPECTED_STAGE_COUNT
        ):
            raise ValueError("V14 terminal success requires all three attempts")
        return
    if lineage.error_type is None:
        raise ValueError("V14 terminal failure requires an error category")
    expected_count = _stage_index(lineage.failed_stage) + int(
        not lineage.failure_before_audit_record
    )
    if len(lineage.records) != expected_count:
        raise ValueError("V14 terminal failure audit count is incomplete")


def _stage_expectations(
    lineage: V14AttemptLineageInput,
) -> tuple[_StageExpectation, ...]:
    namespace = fingerprinted_step_key(
        V14_EXECUTION_CONTRACT_VERSION,
        V14_EXECUTION_MANIFEST_SHA256,
        lineage.execution_namespace,
    )
    expectations = [
        _StageExpectation(
            role="primary",
            schema=SourceUnitExtractionOutput,
            prompt=V14_PROMPT_POLICY.extraction_prompt(lineage.unit),
            step_key=fingerprinted_step_key(
                V14_PROMPT_POLICY.extraction_version,
                lineage.execution_model_id,
                lineage.unit.input_sha256,
                namespace,
            ),
        )
    ]
    if lineage.original_result is None or lineage.original_raw_output is None:
        return tuple(expectations)
    original_sha256 = canonical_json_sha256(lineage.original_raw_output)
    expectations.append(
        _StageExpectation(
            role="structure_normalization",
            schema=SourceUnitNormalizationProposalV14,
            prompt=v14_normalization_prompt(
                unit=lineage.unit,
                original=lineage.original_result,
            ),
            step_key=fingerprinted_step_key(
                V14_NORMALIZATION_PROMPT_VERSION,
                lineage.execution_model_id,
                lineage.unit.input_sha256,
                original_sha256,
                V14_MAPPING_DERIVATION_VERSION,
                namespace,
            ),
        )
    )
    if (
        lineage.normalization_envelope is None
        or lineage.normalization_raw_output is None
    ):
        return tuple(expectations)
    expectations.append(
        _StageExpectation(
            role="normalized_review",
            schema=SourceUnitNormalizedReviewOutputV13V6,
            prompt=v14_normalized_review_prompt(
                unit=lineage.unit,
                original=lineage.original_result,
                normalized=lineage.normalization_envelope.canonical_result,
            ),
            step_key=fingerprinted_step_key(
                V14_NORMALIZED_REVIEW_PROMPT_VERSION,
                lineage.execution_model_id,
                lineage.unit.input_sha256,
                original_sha256,
                canonical_json_sha256(lineage.normalization_raw_output),
                namespace,
            ),
        )
    )
    return tuple(expectations)


def _require_record_identity(
    *,
    record: ModelAttemptAuditRecord,
    expected: _StageExpectation,
    lineage: V14AttemptLineageInput,
    evidence_unit_sha256: str,
    invocation_ids: set[str],
) -> None:
    try:
        invocation_uuid = UUID(record.invocation_id)
    except ValueError as exc:
        raise ValueError("V14 invocation identity is not a UUID") from exc
    if (
        invocation_uuid.version != _UUID4_VERSION
        or record.invocation_id in invocation_ids
    ):
        raise ValueError("V14 invocation identities are not unique UUID4 values")
    invocation_ids.add(record.invocation_id)
    expected_prompt_sha256 = hashlib.sha256(
        bind_prompt_to_invocation(
            prompt=expected.prompt,
            invocation_id=record.invocation_id,
            source_sha256=lineage.unit.source_sha256,
            input_sha256=lineage.unit.input_sha256,
            evidence_unit_sha256=evidence_unit_sha256,
            output_schema_sha256=output_schema_json_sha256(expected.schema),
        ).encode()
    ).hexdigest()
    expected_schema = f"{expected.schema.__module__}.{expected.schema.__qualname__}"
    static_values_match = (
        record.attempt_role == expected.role
        and record.pass_role == expected.role
        and record.retry_context is None
        and record.model_id == lineage.execution_model_id
        and record.step_key == expected.step_key
        and record.prompt_sha256 == expected_prompt_sha256
        and record.source_sha256 == lineage.unit.source_sha256
        and record.input_sha256 == lineage.unit.input_sha256
        and record.evidence_unit_sha256 == evidence_unit_sha256
        and record.semantic_unit_id == lineage.unit.unit_id
        and record.output_schema_identity == expected_schema
        and record.execution_contract_version == V14_EXECUTION_CONTRACT_VERSION
    )
    if not static_values_match:
        raise ValueError("V14 audit record static lineage was rewritten")
    expected_kernel_run_id = kernel_run_id_for_invocation(record.invocation_id)
    if record.validation_outcome == "accepted" and (
        record.kernel_run_id != expected_kernel_run_id
    ):
        raise ValueError("V14 kernel run is detached from its invocation")
    if record.validation_outcome == "accepted" and (
        record.kernel_event_seq is None or record.kernel_event_seq < 1
    ):
        raise ValueError("V14 kernel event sequence is invalid")
    if record.validation_outcome == "accepted" and record.replayed is not False:
        raise ValueError("V14 execution cannot count a replayed provider result")
    if record.validation_outcome == "accepted" and (
        record.provider_execution_response_id is None
        or record.provider_response_id is None
        or record.provider_output_sha256 is None
    ):
        raise ValueError("V14 accepted attempt lacks provider-boundary identity")
    if record.provider_execution_response_id is not None:
        try:
            canonical_response_id = canonical_openai_response_id(
                record.provider_execution_response_id
            )
        except ValueError as exc:
            raise ValueError("V14 provider response identity is invalid") from exc
        if record.provider_response_id != canonical_response_id:
            raise ValueError("V14 canonical provider response identity is detached")
    if record.provider_output_sha256 is not None and (
        len(record.provider_output_sha256) != _SHA256_HEX_LENGTH
    ):
        raise ValueError("V14 provider output hash is invalid")


def _stage_index(stage: V14ExecutionStage) -> int:
    return ("primary", "structure_normalization", "normalized_review").index(stage)


__all__ = ["V14AttemptLineageInput", "require_v14_attempt_lineage"]
