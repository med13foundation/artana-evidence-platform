"""Agent claim-inventory stage for decomposed document extraction."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, cast

from artana_evidence_api.document_extraction_prompting import (
    CLAIM_INVENTORY_COMPLETENESS_SYSTEM_PROMPT,
    CLAIM_INVENTORY_SYSTEM_PROMPT,
    MISSING_CLAIM_RECOVERY_SYSTEM_PROMPT,
)
from artana_evidence_api.document_extraction_support.claim_frames import (
    BoundClaimInventoryItem,
    BoundInventoryCompletenessReview,
    ClaimInventoryBindingDisposition,
    ClaimInventoryBindingError,
    ClaimInventoryBindingRejection,
    ClaimInventoryBindingResult,
    ClaimInventoryCompletenessReview,
    ClaimInventoryItem,
    MissingClaimRecoveryDecision,
    MissingClaimRecoveryDisposition,
    bind_claim_inventory_items,
    bind_inventory_completeness_review,
    canonicalize_bound_claim_inventory,
    claim_inventory_batch_input_sha256,
    merge_bound_claim_inventories,
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
    ModelAttemptAuditRecord,
    ModelStepResult,
    ModelStepRunner,
    current_model_attempt_audit,
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
the frozen chunk and every field follows the schema. Anchor context may extend
outside a claim exact_span, but every selected mention must remain inside it.
Classify claim_kind explicitly, keep polarity independent from epistemic_status,
and preserve attached material
state suffixes such as -positive, -negative, or -mutant in a VARIANT span. Do
not invent a claim.
"""
_ZERO_RETRY_INSTRUCTION = """

ZERO-INVENTORY RETRY:
The previous inventory returned no claims. Re-read the frozen chunk once. Return
every explicit biomedical assertion with all material typed arguments, including
negative, null, uncertain, provisional, and hypothesis claims. Preserve a
procedure-like or measurement-only item with its categorical claim_kind when it
could otherwise be mistaken for a scientific finding. Return an empty list only
when no such item is stated. Do not use outside knowledge or
deterministic fallback.
"""


class ClaimInventoryResultLike(Protocol):
    """Typed view of the dynamic inventory output schema."""

    claims: list[ClaimInventoryItem]


class ClaimInventoryItemsRejectedError(StructuredModelSemanticError):
    """Raised when a schema-valid inventory has no source-bindable items."""

    def __init__(self, result: ClaimInventoryBindingResult) -> None:
        super().__init__("all claim inventory items failed source binding")
        self.result = result
        self.rejection_events: tuple[ClaimInventoryBindingRejectionEvent, ...] = ()


class InventoryBatchBindingStatus(str, Enum):
    """Categorical item-binding result for one inventory stage."""

    EMPTY = "EMPTY"
    COMPLETE = "COMPLETE"
    MIXED = "MIXED"
    ALL_REJECTED = "ALL_REJECTED"


class InventoryBindingPhase(str, Enum):
    """Agent stage that authored a rejected source-bound descriptor."""

    CLAIM_INVENTORY = "CLAIM_INVENTORY"
    COMPLETENESS_REVIEW = "COMPLETENESS_REVIEW"


@dataclass(frozen=True, slots=True)
class ClaimInventoryBindingRejectionEvent:
    """One item rejection bound to the exact provider-backed invocation."""

    event_id: str
    phase: InventoryBindingPhase
    rejection: ClaimInventoryBindingRejection
    attempt_record: ModelAttemptAuditRecord

    @property
    def rejection_id(self) -> str:
        return self.rejection.rejection_id

    @property
    def item(self) -> ClaimInventoryItem:
        return self.rejection.item

    @property
    def disposition(self) -> ClaimInventoryBindingDisposition:
        return self.rejection.disposition

    def as_json(self) -> dict[str, object]:
        """Serialize full rejection evidence plus its provider lineage."""

        return {
            "event_id": self.event_id,
            "phase": self.phase.value,
            "rejection": self.rejection.as_json(),
            "attempt_lineage": {
                "invocation_id": self.attempt_record.invocation_id,
                "provider_response_id": self.attempt_record.provider_response_id,
                "provider_output_sha256": (self.attempt_record.provider_output_sha256),
                "payload_sha256": self.attempt_record.payload_sha256,
                "source_sha256": self.attempt_record.source_sha256,
                "input_sha256": self.attempt_record.input_sha256,
            },
        }


class ClaimInventoryRepairFailedError(StructuredModelValidationError):
    """Terminal repair failure retaining earlier provider-bound rejections."""

    def __init__(
        self,
        *,
        cause: ValidationError | StructuredModelValidationError,
        rejection_events: tuple[ClaimInventoryBindingRejectionEvent, ...],
    ) -> None:
        super().__init__(f"claim inventory repair failed: {cause}")
        self.cause = cause
        self.rejection_events = rejection_events


@dataclass(frozen=True, slots=True)
class ClaimInventoryStageResult:
    """Bound inventory plus immutable raw outputs from its model calls."""

    claims: tuple[BoundClaimInventoryItem, ...]
    binding_status: InventoryBatchBindingStatus
    binding_rejections: tuple[ClaimInventoryBindingRejectionEvent, ...]
    raw_agent_outputs: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class InventoryCompletenessStageResult:
    """Source-bound categorical review plus its immutable agent output."""

    review: BoundInventoryCompletenessReview
    binding_rejections: tuple[ClaimInventoryBindingRejectionEvent, ...]
    raw_agent_outputs: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class MissingClaimRecoveryStageResult:
    """Categorical recovery decision bound to one immutable reviewed claim."""

    decision: MissingClaimRecoveryDisposition
    decision_rationale: str
    reviewed_claim: BoundClaimInventoryItem
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
    except ClaimInventoryItemsRejectedError as exc:
        rejected_attempt = _latest_model_attempt_record()
        rejected_events = _binding_rejection_events(
            rejections=exc.result.rejected,
            attempt_record=rejected_attempt,
            phase=InventoryBindingPhase.CLAIM_INVENTORY,
        )
        try:
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
        except ClaimInventoryItemsRejectedError as retry_exc:
            retry_exc.rejection_events = rejected_events + _binding_rejection_events(
                rejections=retry_exc.result.rejected,
                attempt_record=_latest_model_attempt_record(),
                phase=InventoryBindingPhase.CLAIM_INVENTORY,
            )
            raise
        except (ValidationError, StructuredModelValidationError) as retry_exc:
            raise ClaimInventoryRepairFailedError(
                cause=retry_exc,
                rejection_events=rejected_events,
            ) from retry_exc
        repaired = _claim_inventory_stage_result((retry_result,))
        rejected_raw = rejected_attempt.raw_model_payload
        if rejected_raw is None:
            raise AssertionError(
                "rejected inventory attempt lost its raw payload"
            ) from exc
        combined_events = rejected_events + repaired.binding_rejections
        return ClaimInventoryStageResult(
            claims=repaired.claims,
            binding_status=(
                InventoryBatchBindingStatus.MIXED
                if repaired.claims
                else InventoryBatchBindingStatus.ALL_REJECTED
            ),
            binding_rejections=combined_events,
            raw_agent_outputs=(rejected_raw, *repaired.raw_agent_outputs),
        )
    except (ValidationError, StructuredModelValidationError):
        try:
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
        except ClaimInventoryItemsRejectedError as retry_exc:
            retry_exc.rejection_events = _binding_rejection_events(
                rejections=retry_exc.result.rejected,
                attempt_record=_latest_model_attempt_record(),
                phase=InventoryBindingPhase.CLAIM_INVENTORY,
            )
            raise
        return _claim_inventory_stage_result(
            (retry_result,),
        )

    record_skipped_model_attempt(
        model_id=model_id,
        prompt=schema_retry_prompt,
        output_schema=output_schema,
        step_key=schema_retry_step_key,
        audit_context=schema_retry_context,
    )
    return _claim_inventory_stage_result((result,))


def build_inventory_completeness_prompt(
    *,
    chunk: RelationExtractionTextChunk,
    total_chunks: int,
    document_fingerprint: str,
    current_inventory: tuple[BoundClaimInventoryItem, ...],
    confirmation: bool,
    recovery_round: int = 0,
    excluded_inventory: tuple[BoundClaimInventoryItem, ...] = (),
    binding_rejections: tuple[ClaimInventoryBindingRejection, ...] = (),
    schema_retry: bool = False,
) -> str:
    """Build an independent source-only completeness review prompt."""

    if confirmation != (recovery_round > 0):
        raise ValueError(
            "completeness confirmation and recovery round must change together"
        )

    current_inventory = canonicalize_bound_claim_inventory(current_inventory)
    excluded_inventory = canonicalize_bound_claim_inventory(excluded_inventory)
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
    excluded_json = json.dumps(
        [
            {
                "inventory_id": claim.inventory_id,
                "claim": claim.item.model_dump(mode="json"),
            }
            for claim in excluded_inventory
        ],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    rejection_json = json.dumps(
        [
            {
                "rejection_id": rejection.rejection_id,
                "batch_index": rejection.batch_index,
                "disposition": rejection.disposition.value,
            }
            for rejection in binding_rejections
        ],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    phase = (
        f"post_recovery_confirmation_round_{recovery_round}"
        if confirmation
        else "initial_review"
    )
    return (
        f"{CLAIM_INVENTORY_COMPLETENESS_SYSTEM_PROMPT}\n\n"
        "MODEL CONTRACT\n"
        f"- prompt_version: {CLAIM_INVENTORY_COMPLETENESS_PROMPT_VERSION}\n"
        f"- review_phase: {phase}\n"
        f"- recovery_round: {recovery_round}\n"
        f"- document_sha256: {document_fingerprint}\n"
        f"- chunk_index: {chunk.index + 1} of {total_chunks}\n"
        f"- chunk_sha256: {chunk.sha256}\n"
        "- source_locator: normalized_extraction_text\n\n"
        "---\nCOMPLETE RETURNED INVENTORY\n---\n"
        f"{inventory_json}\n"
        "---\nEXCLUDED REVIEWED ITEMS\n---\n"
        f"{excluded_json}\n"
        "---\nREJECTED INVENTORY ITEM EVIDENCE\n---\n"
        f"{rejection_json}\n"
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
    recovery_round: int = 0,
    excluded_inventory: tuple[BoundClaimInventoryItem, ...] = (),
    binding_rejections: tuple[ClaimInventoryBindingRejection, ...] = (),
) -> InventoryCompletenessStageResult:
    """Review completeness with one audited schema-repair opportunity."""

    prompt = build_inventory_completeness_prompt(
        chunk=chunk,
        total_chunks=total_chunks,
        document_fingerprint=document_fingerprint,
        current_inventory=current_inventory,
        excluded_inventory=excluded_inventory,
        binding_rejections=binding_rejections,
        confirmation=confirmation,
        recovery_round=recovery_round,
    )
    phase = f"confirmation_{recovery_round}" if confirmation else "initial"
    step_key = _inventory_review_step_key(
        prompt_version=CLAIM_INVENTORY_COMPLETENESS_PROMPT_VERSION,
        phase=phase,
        chunk=chunk,
        current_inventory=current_inventory,
        excluded_inventory=excluded_inventory,
        binding_rejections=binding_rejections,
        model_id=model_id,
        execution_namespace=execution_namespace,
    )
    audit_context = _inventory_review_audit_context(
        document_fingerprint=document_fingerprint,
        current_inventory=current_inventory,
        excluded_inventory=excluded_inventory,
        binding_rejections=binding_rejections,
        schema_retry=False,
    )
    retry_prompt = build_inventory_completeness_prompt(
        chunk=chunk,
        total_chunks=total_chunks,
        document_fingerprint=document_fingerprint,
        current_inventory=current_inventory,
        excluded_inventory=excluded_inventory,
        binding_rejections=binding_rejections,
        confirmation=confirmation,
        recovery_round=recovery_round,
        schema_retry=True,
    )
    retry_step_key = _inventory_review_step_key(
        prompt_version=(
            f"{CLAIM_INVENTORY_COMPLETENESS_PROMPT_VERSION}.{_SCHEMA_RETRY_SUFFIX}"
        ),
        phase=phase,
        chunk=chunk,
        current_inventory=current_inventory,
        excluded_inventory=excluded_inventory,
        binding_rejections=binding_rejections,
        model_id=model_id,
        execution_namespace=execution_namespace,
    )
    retry_context = _inventory_review_audit_context(
        document_fingerprint=document_fingerprint,
        current_inventory=current_inventory,
        excluded_inventory=excluded_inventory,
        binding_rejections=binding_rejections,
        schema_retry=True,
    )
    try:
        result = await _run_inventory_completeness_step(
            chunk=chunk,
            document_fingerprint=document_fingerprint,
            current_inventory=current_inventory,
            excluded_inventory=excluded_inventory,
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
            excluded_inventory=excluded_inventory,
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
            binding_rejections=_binding_rejection_events(
                rejections=retry_result.value.binding_rejections,
                attempt_record=retry_result.attempt_record,
                phase=InventoryBindingPhase.COMPLETENESS_REVIEW,
            ),
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
        binding_rejections=_binding_rejection_events(
            rejections=result.value.binding_rejections,
            attempt_record=result.attempt_record,
            phase=InventoryBindingPhase.COMPLETENESS_REVIEW,
        ),
        raw_agent_outputs=(result.raw_output,),
    )


def _claim_inventory_stage_result(
    results: tuple[
        AuditedStructuredStepResult[BaseModel, ClaimInventoryBindingResult], ...
    ],
) -> ClaimInventoryStageResult:
    claims = merge_bound_claim_inventories(
        *(result.value.accepted for result in results),
    )
    binding_rejections = tuple(
        event
        for result in results
        for event in _binding_rejection_events(
            rejections=result.value.rejected,
            attempt_record=result.attempt_record,
            phase=InventoryBindingPhase.CLAIM_INVENTORY,
        )
    )
    if claims:
        status = (
            InventoryBatchBindingStatus.MIXED
            if binding_rejections
            else InventoryBatchBindingStatus.COMPLETE
        )
    else:
        status = (
            InventoryBatchBindingStatus.ALL_REJECTED
            if binding_rejections
            else InventoryBatchBindingStatus.EMPTY
        )
    return ClaimInventoryStageResult(
        claims=claims,
        binding_status=status,
        binding_rejections=binding_rejections,
        raw_agent_outputs=tuple(result.raw_output for result in results),
    )


def _binding_rejection_events(
    *,
    rejections: tuple[ClaimInventoryBindingRejection, ...],
    attempt_record: ModelAttemptAuditRecord,
    phase: InventoryBindingPhase,
) -> tuple[ClaimInventoryBindingRejectionEvent, ...]:
    return tuple(
        ClaimInventoryBindingRejectionEvent(
            event_id=hashlib.sha256(
                (
                    f"{phase.value}:{attempt_record.invocation_id}:"
                    f"{rejection.rejection_id}"
                ).encode(),
            ).hexdigest(),
            phase=phase,
            rejection=rejection,
            attempt_record=attempt_record,
        )
        for rejection in rejections
    )


def _latest_model_attempt_record() -> ModelAttemptAuditRecord:
    session = current_model_attempt_audit()
    if session is None or not session.records:
        raise AssertionError("inventory rejection lacks an audit record")
    return session.records[-1]


def build_missing_claim_recovery_prompt(
    *,
    chunk: RelationExtractionTextChunk,
    document_fingerprint: str,
    missing_claim: BoundClaimInventoryItem,
    recovery_round: int,
    parent_completeness_input_sha256: str,
) -> str:
    """Build one claim-unit recovery prompt from a reviewed missing descriptor."""

    if recovery_round < 1:
        raise ValueError("missing-claim recovery requires a positive recovery round")

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
        f"- recovery_round: {recovery_round}\n"
        "- parent_completeness_input_sha256: "
        f"{parent_completeness_input_sha256}\n"
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
    recovery_round: int,
    parent_completeness_input_sha256: str,
    output_schema: type[BaseModel],
    client: object,
    tenant: object,
    model_id: str,
    step_runner: ModelStepRunner,
    execution_namespace: str,
) -> MissingClaimRecoveryStageResult:
    """Adjudicate one reviewed descriptor without allowing span rewrites."""

    prompt = build_missing_claim_recovery_prompt(
        chunk=chunk,
        document_fingerprint=document_fingerprint,
        missing_claim=missing_claim,
        recovery_round=recovery_round,
        parent_completeness_input_sha256=parent_completeness_input_sha256,
    )
    step_key = fingerprinted_step_key(
        "research_init.claim_inventory_recovery.v4",
        MISSING_CLAIM_RECOVERY_PROMPT_VERSION,
        model_id,
        document_fingerprint,
        claim_inventory_batch_input_sha256((missing_claim,)),
        str(recovery_round),
        parent_completeness_input_sha256,
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

    def _bind_recovery(parsed: BaseModel) -> MissingClaimRecoveryDecision:
        return cast("MissingClaimRecoveryDecision", parsed)

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
            schema_id="document_extraction.claim_inventory_recovery.v4",
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
    return MissingClaimRecoveryStageResult(
        decision=result.value.decision,
        decision_rationale=result.value.decision_rationale,
        reviewed_claim=missing_claim,
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
) -> AuditedStructuredStepResult[BaseModel, ClaimInventoryBindingResult]:
    def _bind(parsed: BaseModel) -> ClaimInventoryBindingResult:
        output = cast("ClaimInventoryResultLike", parsed)
        try:
            result = bind_claim_inventory_items(
                tuple(output.claims),
                source_text=chunk.text,
                source_sha256=document_fingerprint,
                chunk_index=chunk.index,
                source_start_offset=chunk.start_char,
            )
        except ClaimInventoryBindingError as exc:
            raise StructuredModelSemanticError(str(exc)) from exc
        if not result.accepted and result.rejected:
            raise ClaimInventoryItemsRejectedError(result)
        return result

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
    excluded_inventory: tuple[BoundClaimInventoryItem, ...],
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
                excluded_inventory=excluded_inventory,
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
    excluded_inventory: tuple[BoundClaimInventoryItem, ...],
    binding_rejections: tuple[ClaimInventoryBindingRejection, ...],
    model_id: str,
    execution_namespace: str,
) -> str:
    return fingerprinted_step_key(
        "research_init.claim_inventory_completeness.v3",
        prompt_version,
        phase,
        model_id,
        chunk.sha256,
        inventory_completeness_input_sha256(
            current_inventory,
            excluded_inventory,
            binding_rejections,
        ),
        execution_namespace,
    )


def _inventory_review_audit_context(
    *,
    document_fingerprint: str,
    current_inventory: tuple[BoundClaimInventoryItem, ...],
    excluded_inventory: tuple[BoundClaimInventoryItem, ...],
    binding_rejections: tuple[ClaimInventoryBindingRejection, ...],
    schema_retry: bool,
) -> ModelAttemptAuditContext:
    return ModelAttemptAuditContext(
        attempt_role=(
            "schema_retry" if schema_retry else "claim_inventory_completeness"
        ),
        pass_role="claim_inventory_completeness",
        retry_context=None,
        source_sha256=document_fingerprint,
        input_sha256=inventory_completeness_input_sha256(
            current_inventory,
            excluded_inventory,
            binding_rejections,
        ),
        semantic_unit_id=None,
    )


def inventory_completeness_input_sha256(
    current_inventory: tuple[BoundClaimInventoryItem, ...],
    excluded_inventory: tuple[BoundClaimInventoryItem, ...],
    binding_rejections: tuple[ClaimInventoryBindingRejection, ...],
) -> str:
    current_inventory = canonicalize_bound_claim_inventory(current_inventory)
    excluded_inventory = canonicalize_bound_claim_inventory(excluded_inventory)
    if not excluded_inventory and not binding_rejections:
        return claim_inventory_batch_input_sha256(current_inventory)
    payload = {
        "current_inventory_ids": [claim.inventory_id for claim in current_inventory],
        "excluded_inventory_ids": [claim.inventory_id for claim in excluded_inventory],
        "binding_rejection_ids": [
            rejection.rejection_id for rejection in binding_rejections
        ],
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
    "ClaimInventoryBindingRejectionEvent",
    "ClaimInventoryItemsRejectedError",
    "ClaimInventoryRepairFailedError",
    "InventoryBatchBindingStatus",
    "InventoryBindingPhase",
    "InventoryCompletenessStageResult",
    "inventory_completeness_input_sha256",
    "MissingClaimRecoveryStageResult",
    "build_inventory_completeness_prompt",
    "build_missing_claim_recovery_prompt",
    "build_claim_inventory_prompt",
    "record_skipped_zero_inventory_retry",
    "run_claim_inventory_stage",
    "run_inventory_completeness_review_stage",
    "run_missing_claim_recovery_stage",
]
