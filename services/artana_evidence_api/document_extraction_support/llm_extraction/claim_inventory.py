"""Agent claim-inventory stage for decomposed document extraction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol, cast

from artana_evidence_api.document_extraction_prompting import (
    CLAIM_INVENTORY_COMPLETENESS_SYSTEM_PROMPT,
    CLAIM_INVENTORY_SYSTEM_PROMPT,
    MISSING_CLAIM_RECOVERY_SYSTEM_PROMPT,
)
from artana_evidence_api.document_extraction_support.claim_frames import (
    BoundClaimInventoryItem,
    BoundInventoryCompletenessReview,
    ClaimInventoryBindingError,
    ClaimInventoryCompletenessReview,
    ClaimInventoryItem,
    MissingClaimRecoveryResult,
    bind_claim_inventory,
    bind_inventory_completeness_review,
    claim_inventory_batch_input_sha256,
    require_recovery_matches_review,
)
from artana_evidence_api.document_extraction_support.full_text_chunking import (
    RelationExtractionTextChunk,
)
from artana_evidence_api.document_extraction_support.llm_extraction.prompt_versions import (
    CLAIM_INVENTORY_COMPLETENESS_PROMPT_VERSION,
    CLAIM_INVENTORY_PROMPT_VERSION,
    MISSING_CLAIM_RECOVERY_PROMPT_VERSION,
)
from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    AuditedStructuredStepResult,
    StructuredModelSemanticError,
    StructuredModelValidationError,
    run_audited_structured_step,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    ModelAttemptAuditContext,
    ModelStepResult,
    ModelStepRunner,
    fingerprinted_step_key,
    record_skipped_model_attempt,
)
from pydantic import BaseModel, ValidationError

_SCHEMA_RETRY_SUFFIX = "schema_retry.v1"
_ZERO_RETRY_SUFFIX = "zero_candidate_retry.v1"
_SCHEMA_RETRY_INSTRUCTION = """

SCHEMA AND SOURCE-BINDING RETRY:
The previous inventory output failed the strict schema or exact-span binding.
Return the same source-local claims only when every span is copied exactly from
the frozen chunk and every field follows the schema. Preserve attached material
state suffixes such as -positive, -negative, or -mutant in a VARIANT span. Do
not invent a claim.
"""
_ZERO_RETRY_INSTRUCTION = """

ZERO-INVENTORY RETRY:
The previous inventory returned no claims. Re-read the frozen chunk once. Return
every explicit biomedical assertion with all material typed arguments, including
negative, null, uncertain, provisional, and hypothesis claims. Return an empty
list only when no such claim is stated. Do not use outside knowledge or
deterministic fallback.
"""


class ClaimInventoryResultLike(Protocol):
    """Typed view of the dynamic inventory output schema."""

    claims: list[ClaimInventoryItem]


@dataclass(frozen=True, slots=True)
class ClaimInventoryStageResult:
    """Bound inventory plus immutable raw outputs from its model calls."""

    claims: tuple[BoundClaimInventoryItem, ...]
    raw_agent_outputs: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class InventoryCompletenessStageResult:
    """Source-bound categorical review plus its immutable agent output."""

    review: BoundInventoryCompletenessReview
    raw_agent_outputs: tuple[dict[str, object], ...]


def build_claim_inventory_prompt(
    *,
    chunk: RelationExtractionTextChunk,
    total_chunks: int,
    document_fingerprint: str,
    zero_retry: bool = False,
    schema_retry: bool = False,
) -> str:
    """Build one source-only inventory prompt for a frozen chunk."""

    retry_instruction = _ZERO_RETRY_INSTRUCTION if zero_retry else ""
    schema_retry_instruction = _SCHEMA_RETRY_INSTRUCTION if schema_retry else ""
    return (
        f"{CLAIM_INVENTORY_SYSTEM_PROMPT}\n\n"
        "MODEL CONTRACT\n"
        f"- prompt_version: {CLAIM_INVENTORY_PROMPT_VERSION}\n"
        f"- document_sha256: {document_fingerprint}\n"
        f"- chunk_index: {chunk.index + 1} of {total_chunks}\n"
        f"- chunk_char_range: {chunk.start_char}-{chunk.end_char}\n"
        f"- chunk_sha256: {chunk.sha256}\n"
        "- source_locator: normalized_extraction_text\n\n"
        "---\nFROZEN SOURCE CHUNK\n---\n"
        f"{chunk.text}\n"
        "---\n"
        f"{retry_instruction}"
        f"{schema_retry_instruction}"
    )


async def run_claim_inventory_stage(
    *,
    chunk: RelationExtractionTextChunk,
    total_chunks: int,
    document_fingerprint: str,
    output_schema: type[BaseModel],
    client: object,
    tenant: object,
    model_id: str,
    step_runner: ModelStepRunner,
    execution_namespace: str,
    zero_retry: bool = False,
) -> ClaimInventoryStageResult:
    """Run and source-bind one inventory, with one agent schema repair."""

    prompt = build_claim_inventory_prompt(
        chunk=chunk,
        total_chunks=total_chunks,
        document_fingerprint=document_fingerprint,
        zero_retry=zero_retry,
    )
    prompt_version = CLAIM_INVENTORY_PROMPT_VERSION
    if zero_retry:
        prompt_version = f"{prompt_version}.{_ZERO_RETRY_SUFFIX}"
    step_key = _inventory_step_key(
        prompt_version=prompt_version,
        chunk=chunk,
        total_chunks=total_chunks,
        document_fingerprint=document_fingerprint,
        model_id=model_id,
        execution_namespace=execution_namespace,
    )
    audit_context = _inventory_audit_context(
        chunk=chunk,
        document_fingerprint=document_fingerprint,
        zero_retry=zero_retry,
        schema_retry=False,
    )
    schema_retry_prompt = build_claim_inventory_prompt(
        chunk=chunk,
        total_chunks=total_chunks,
        document_fingerprint=document_fingerprint,
        zero_retry=zero_retry,
        schema_retry=True,
    )
    schema_retry_step_key = _inventory_step_key(
        prompt_version=f"{prompt_version}.{_SCHEMA_RETRY_SUFFIX}",
        chunk=chunk,
        total_chunks=total_chunks,
        document_fingerprint=document_fingerprint,
        model_id=model_id,
        execution_namespace=execution_namespace,
    )
    schema_retry_context = _inventory_audit_context(
        chunk=chunk,
        document_fingerprint=document_fingerprint,
        zero_retry=zero_retry,
        schema_retry=True,
    )

    try:
        result = await _run_inventory_step(
            chunk=chunk,
            document_fingerprint=document_fingerprint,
            output_schema=output_schema,
            client=client,
            tenant=tenant,
            model_id=model_id,
            step_runner=step_runner,
            prompt=prompt,
            step_key=step_key,
            audit_context=audit_context,
        )
    except (ValidationError, StructuredModelValidationError):
        retry_result = await _run_inventory_step(
            chunk=chunk,
            document_fingerprint=document_fingerprint,
            output_schema=output_schema,
            client=client,
            tenant=tenant,
            model_id=model_id,
            step_runner=step_runner,
            prompt=schema_retry_prompt,
            step_key=schema_retry_step_key,
            audit_context=schema_retry_context,
        )
        return ClaimInventoryStageResult(
            claims=retry_result.value,
            raw_agent_outputs=(retry_result.raw_output,),
        )

    record_skipped_model_attempt(
        model_id=model_id,
        prompt=schema_retry_prompt,
        output_schema=output_schema,
        step_key=schema_retry_step_key,
        audit_context=schema_retry_context,
    )
    return ClaimInventoryStageResult(
        claims=result.value,
        raw_agent_outputs=(result.raw_output,),
    )


def build_inventory_completeness_prompt(
    *,
    chunk: RelationExtractionTextChunk,
    total_chunks: int,
    document_fingerprint: str,
    current_inventory: tuple[BoundClaimInventoryItem, ...],
    confirmation: bool,
    schema_retry: bool = False,
) -> str:
    """Build an independent source-only completeness review prompt."""

    inventory_payload = [
        {
            "inventory_id": claim.inventory_id,
            "claim": claim.item.model_dump(mode="json"),
        }
        for claim in current_inventory
    ]
    inventory_json = json.dumps(
        inventory_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    phase = "post_recovery_confirmation" if confirmation else "initial_review"
    return (
        f"{CLAIM_INVENTORY_COMPLETENESS_SYSTEM_PROMPT}\n\n"
        "MODEL CONTRACT\n"
        f"- prompt_version: {CLAIM_INVENTORY_COMPLETENESS_PROMPT_VERSION}\n"
        f"- review_phase: {phase}\n"
        f"- document_sha256: {document_fingerprint}\n"
        f"- chunk_index: {chunk.index + 1} of {total_chunks}\n"
        f"- chunk_sha256: {chunk.sha256}\n"
        "- source_locator: normalized_extraction_text\n\n"
        "---\nCOMPLETE RETURNED INVENTORY\n---\n"
        f"{inventory_json}\n"
        "---\nFROZEN SOURCE CHUNK\n---\n"
        f"{chunk.text}\n"
        "---\n"
        f"{_SCHEMA_RETRY_INSTRUCTION if schema_retry else ''}"
    )


async def run_inventory_completeness_review_stage(
    *,
    chunk: RelationExtractionTextChunk,
    total_chunks: int,
    document_fingerprint: str,
    current_inventory: tuple[BoundClaimInventoryItem, ...],
    output_schema: type[BaseModel],
    client: object,
    tenant: object,
    model_id: str,
    step_runner: ModelStepRunner,
    execution_namespace: str,
    confirmation: bool = False,
) -> InventoryCompletenessStageResult:
    """Review completeness with one audited schema-repair opportunity."""

    prompt = build_inventory_completeness_prompt(
        chunk=chunk,
        total_chunks=total_chunks,
        document_fingerprint=document_fingerprint,
        current_inventory=current_inventory,
        confirmation=confirmation,
    )
    phase = "confirmation" if confirmation else "initial"
    step_key = _inventory_review_step_key(
        prompt_version=CLAIM_INVENTORY_COMPLETENESS_PROMPT_VERSION,
        phase=phase,
        chunk=chunk,
        current_inventory=current_inventory,
        model_id=model_id,
        execution_namespace=execution_namespace,
    )
    audit_context = _inventory_review_audit_context(
        document_fingerprint=document_fingerprint,
        current_inventory=current_inventory,
        schema_retry=False,
    )
    retry_prompt = build_inventory_completeness_prompt(
        chunk=chunk,
        total_chunks=total_chunks,
        document_fingerprint=document_fingerprint,
        current_inventory=current_inventory,
        confirmation=confirmation,
        schema_retry=True,
    )
    retry_step_key = _inventory_review_step_key(
        prompt_version=(
            f"{CLAIM_INVENTORY_COMPLETENESS_PROMPT_VERSION}.{_SCHEMA_RETRY_SUFFIX}"
        ),
        phase=phase,
        chunk=chunk,
        current_inventory=current_inventory,
        model_id=model_id,
        execution_namespace=execution_namespace,
    )
    retry_context = _inventory_review_audit_context(
        document_fingerprint=document_fingerprint,
        current_inventory=current_inventory,
        schema_retry=True,
    )
    try:
        result = await _run_inventory_completeness_step(
            chunk=chunk,
            document_fingerprint=document_fingerprint,
            current_inventory=current_inventory,
            output_schema=output_schema,
            client=client,
            tenant=tenant,
            model_id=model_id,
            step_runner=step_runner,
            prompt=prompt,
            step_key=step_key,
            audit_context=audit_context,
        )
    except (ValidationError, StructuredModelValidationError):
        retry_result = await _run_inventory_completeness_step(
            chunk=chunk,
            document_fingerprint=document_fingerprint,
            current_inventory=current_inventory,
            output_schema=output_schema,
            client=client,
            tenant=tenant,
            model_id=model_id,
            step_runner=step_runner,
            prompt=retry_prompt,
            step_key=retry_step_key,
            audit_context=retry_context,
        )
        return InventoryCompletenessStageResult(
            review=retry_result.value,
            raw_agent_outputs=(retry_result.raw_output,),
        )

    record_skipped_model_attempt(
        model_id=model_id,
        prompt=retry_prompt,
        output_schema=output_schema,
        step_key=retry_step_key,
        audit_context=retry_context,
    )
    return InventoryCompletenessStageResult(
        review=result.value,
        raw_agent_outputs=(result.raw_output,),
    )


def build_missing_claim_recovery_prompt(
    *,
    chunk: RelationExtractionTextChunk,
    document_fingerprint: str,
    missing_claim: BoundClaimInventoryItem,
) -> str:
    """Build one claim-unit recovery prompt from a reviewed missing descriptor."""

    missing_json = json.dumps(
        missing_claim.item.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return (
        f"{MISSING_CLAIM_RECOVERY_SYSTEM_PROMPT}\n\n"
        "MODEL CONTRACT\n"
        f"- prompt_version: {MISSING_CLAIM_RECOVERY_PROMPT_VERSION}\n"
        f"- document_sha256: {document_fingerprint}\n"
        f"- inventory_id: {missing_claim.inventory_id}\n"
        f"- chunk_index: {chunk.index + 1}\n"
        "- source_locator: normalized_extraction_text\n\n"
        "---\nREVIEWED MISSING CLAIM\n---\n"
        f"{missing_json}\n"
        "---\nFROZEN SOURCE CHUNK\n---\n"
        f"{chunk.text}\n"
        "---\n"
    )


async def run_missing_claim_recovery_stage(
    *,
    chunk: RelationExtractionTextChunk,
    document_fingerprint: str,
    missing_claim: BoundClaimInventoryItem,
    output_schema: type[BaseModel],
    client: object,
    tenant: object,
    model_id: str,
    step_runner: ModelStepRunner,
    execution_namespace: str,
) -> ClaimInventoryStageResult:
    """Run exactly one audited recovery call for one reviewed missing claim."""

    prompt = build_missing_claim_recovery_prompt(
        chunk=chunk,
        document_fingerprint=document_fingerprint,
        missing_claim=missing_claim,
    )
    step_key = fingerprinted_step_key(
        "research_init.claim_inventory_recovery.v3",
        MISSING_CLAIM_RECOVERY_PROMPT_VERSION,
        model_id,
        document_fingerprint,
        claim_inventory_batch_input_sha256((missing_claim,)),
        execution_namespace,
    )
    audit_context = ModelAttemptAuditContext(
        attempt_role="claim_inventory_recovery",
        pass_role="claim_inventory_recovery",
        retry_context=None,
        source_sha256=document_fingerprint,
        input_sha256=claim_inventory_batch_input_sha256((missing_claim,)),
        semantic_unit_id=missing_claim.inventory_id,
    )

    def _bind_recovery(parsed: BaseModel) -> tuple[BoundClaimInventoryItem, ...]:
        output = cast("MissingClaimRecoveryResult", parsed)
        try:
            recovered = bind_claim_inventory(
                output.claims,
                source_text=chunk.text,
                source_sha256=document_fingerprint,
                chunk_index=chunk.index,
                source_start_offset=chunk.start_char,
            )
            require_recovery_matches_review(
                recovered_claims=recovered,
                reviewed_missing_claims=(missing_claim,),
            )
        except ClaimInventoryBindingError as exc:
            raise StructuredModelSemanticError(str(exc)) from exc
        return recovered

    async def _invoke_model(
        invocation_id: str,
        provider_prompt: str,
    ) -> ModelStepResult:
        return await step_runner(
            client,
            run_id=f"research-init-extraction:{invocation_id}",
            tenant=tenant,
            model=model_id,
            prompt=provider_prompt,
            output_schema=output_schema,
            schema_id="document_extraction.claim_inventory_recovery.v3",
            step_key=step_key,
            replay_policy="fork_on_drift",
        )

    result = await run_audited_structured_step(
        invoke_model=_invoke_model,
        model_id=model_id,
        prompt=prompt,
        output_schema=output_schema,
        step_key=step_key,
        audit_context=audit_context,
        validate_semantics=_bind_recovery,
    )
    return ClaimInventoryStageResult(
        claims=result.value,
        raw_agent_outputs=(result.raw_output,),
    )


def record_skipped_zero_inventory_retry(
    *,
    chunk: RelationExtractionTextChunk,
    total_chunks: int,
    document_fingerprint: str,
    output_schema: type[BaseModel],
    model_id: str,
    execution_namespace: str,
) -> None:
    """Audit a zero-inventory retry that was unnecessary for this chunk."""

    prompt = build_claim_inventory_prompt(
        chunk=chunk,
        total_chunks=total_chunks,
        document_fingerprint=document_fingerprint,
        zero_retry=True,
    )
    prompt_version = f"{CLAIM_INVENTORY_PROMPT_VERSION}.{_ZERO_RETRY_SUFFIX}"
    record_skipped_model_attempt(
        model_id=model_id,
        prompt=prompt,
        output_schema=output_schema,
        step_key=_inventory_step_key(
            prompt_version=prompt_version,
            chunk=chunk,
            total_chunks=total_chunks,
            document_fingerprint=document_fingerprint,
            model_id=model_id,
            execution_namespace=execution_namespace,
        ),
        audit_context=_inventory_audit_context(
            chunk=chunk,
            document_fingerprint=document_fingerprint,
            zero_retry=True,
            schema_retry=False,
        ),
    )


async def _run_inventory_step(
    *,
    chunk: RelationExtractionTextChunk,
    document_fingerprint: str,
    output_schema: type[BaseModel],
    client: object,
    tenant: object,
    model_id: str,
    step_runner: ModelStepRunner,
    prompt: str,
    step_key: str,
    audit_context: ModelAttemptAuditContext,
) -> AuditedStructuredStepResult[BaseModel, tuple[BoundClaimInventoryItem, ...]]:
    def _bind(parsed: BaseModel) -> tuple[BoundClaimInventoryItem, ...]:
        output = cast("ClaimInventoryResultLike", parsed)
        try:
            return bind_claim_inventory(
                tuple(output.claims),
                source_text=chunk.text,
                source_sha256=document_fingerprint,
                chunk_index=chunk.index,
                source_start_offset=chunk.start_char,
            )
        except ClaimInventoryBindingError as exc:
            raise StructuredModelSemanticError(str(exc)) from exc

    async def _invoke_model(
        invocation_id: str,
        provider_prompt: str,
    ) -> ModelStepResult:
        return await step_runner(
            client,
            run_id=f"research-init-extraction:{invocation_id}",
            tenant=tenant,
            model=model_id,
            prompt=provider_prompt,
            output_schema=output_schema,
            schema_id="document_extraction.claim_inventory.v3",
            step_key=step_key,
            replay_policy="fork_on_drift",
        )

    return await run_audited_structured_step(
        invoke_model=_invoke_model,
        model_id=model_id,
        prompt=prompt,
        output_schema=output_schema,
        step_key=step_key,
        audit_context=audit_context,
        validate_semantics=_bind,
    )


async def _run_inventory_completeness_step(
    *,
    chunk: RelationExtractionTextChunk,
    document_fingerprint: str,
    current_inventory: tuple[BoundClaimInventoryItem, ...],
    output_schema: type[BaseModel],
    client: object,
    tenant: object,
    model_id: str,
    step_runner: ModelStepRunner,
    prompt: str,
    step_key: str,
    audit_context: ModelAttemptAuditContext,
) -> AuditedStructuredStepResult[BaseModel, BoundInventoryCompletenessReview]:
    def _bind_review(parsed: BaseModel) -> BoundInventoryCompletenessReview:
        review = cast("ClaimInventoryCompletenessReview", parsed)
        try:
            return bind_inventory_completeness_review(
                review,
                source_text=chunk.text,
                source_sha256=document_fingerprint,
                chunk_index=chunk.index,
                source_start_offset=chunk.start_char,
                current_inventory=current_inventory,
            )
        except ClaimInventoryBindingError as exc:
            raise StructuredModelSemanticError(str(exc)) from exc

    async def _invoke_model(
        invocation_id: str,
        provider_prompt: str,
    ) -> ModelStepResult:
        return await step_runner(
            client,
            run_id=f"research-init-extraction:{invocation_id}",
            tenant=tenant,
            model=model_id,
            prompt=provider_prompt,
            output_schema=output_schema,
            schema_id="document_extraction.claim_inventory_completeness.v3",
            step_key=step_key,
            replay_policy="fork_on_drift",
        )

    return await run_audited_structured_step(
        invoke_model=_invoke_model,
        model_id=model_id,
        prompt=prompt,
        output_schema=output_schema,
        step_key=step_key,
        audit_context=audit_context,
        validate_semantics=_bind_review,
    )


def _inventory_step_key(
    *,
    prompt_version: str,
    chunk: RelationExtractionTextChunk,
    total_chunks: int,
    document_fingerprint: str,
    model_id: str,
    execution_namespace: str,
) -> str:
    return fingerprinted_step_key(
        "research_init.claim_inventory.v3",
        prompt_version,
        model_id,
        document_fingerprint,
        str(chunk.index),
        str(total_chunks),
        chunk.sha256,
        execution_namespace,
    )


def _inventory_review_step_key(
    *,
    prompt_version: str,
    phase: str,
    chunk: RelationExtractionTextChunk,
    current_inventory: tuple[BoundClaimInventoryItem, ...],
    model_id: str,
    execution_namespace: str,
) -> str:
    return fingerprinted_step_key(
        "research_init.claim_inventory_completeness.v3",
        prompt_version,
        phase,
        model_id,
        chunk.sha256,
        claim_inventory_batch_input_sha256(current_inventory),
        execution_namespace,
    )


def _inventory_review_audit_context(
    *,
    document_fingerprint: str,
    current_inventory: tuple[BoundClaimInventoryItem, ...],
    schema_retry: bool,
) -> ModelAttemptAuditContext:
    return ModelAttemptAuditContext(
        attempt_role=(
            "schema_retry" if schema_retry else "claim_inventory_completeness"
        ),
        pass_role="claim_inventory_completeness",
        retry_context=None,
        source_sha256=document_fingerprint,
        input_sha256=claim_inventory_batch_input_sha256(current_inventory),
        semantic_unit_id=None,
    )


def _inventory_audit_context(
    *,
    chunk: RelationExtractionTextChunk,
    document_fingerprint: str,
    zero_retry: bool,
    schema_retry: bool,
) -> ModelAttemptAuditContext:
    return ModelAttemptAuditContext(
        attempt_role=(
            "schema_retry"
            if schema_retry
            else "zero_candidate_retry"
            if zero_retry
            else "claim_inventory"
        ),
        pass_role="claim_inventory",
        retry_context="zero_candidate_retry" if zero_retry else None,
        source_sha256=document_fingerprint,
        input_sha256=chunk.sha256,
    )


__all__ = [
    "CLAIM_INVENTORY_COMPLETENESS_PROMPT_VERSION",
    "CLAIM_INVENTORY_PROMPT_VERSION",
    "MISSING_CLAIM_RECOVERY_PROMPT_VERSION",
    "ClaimInventoryStageResult",
    "InventoryCompletenessStageResult",
    "build_inventory_completeness_prompt",
    "build_missing_claim_recovery_prompt",
    "build_claim_inventory_prompt",
    "record_skipped_zero_inventory_retry",
    "run_claim_inventory_stage",
    "run_inventory_completeness_review_stage",
    "run_missing_claim_recovery_stage",
]
