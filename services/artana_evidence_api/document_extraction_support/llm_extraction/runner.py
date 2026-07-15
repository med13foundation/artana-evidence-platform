"""Inventory-first, one-claim-at-a-time LLM extraction orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from artana_evidence_api.document_extraction_contracts import (
    ClaimExtractionLineage,
    ExtractedRelationCandidate,
)
from artana_evidence_api.document_extraction_prompting import (
    build_claim_inventory_completeness_output_schema,
    build_claim_inventory_output_schema,
    build_missing_claim_recovery_output_schema,
    build_single_claim_framing_output_schema,
)
from artana_evidence_api.document_extraction_support.claim_frames import (
    BoundClaimInventoryItem,
    InventoryCompletenessDecision,
    coalesce_long_sentence_chunks,
    merge_bound_claim_inventories,
)
from artana_evidence_api.document_extraction_support.full_text_chunking import (
    RelationExtractionTextChunk,
)
from artana_evidence_api.document_extraction_support.llm_extraction.claim_framing import (
    run_single_claim_framing_stage,
)
from artana_evidence_api.document_extraction_support.llm_extraction.claim_inventory import (
    run_claim_inventory_stage,
    run_inventory_completeness_review_stage,
    run_missing_claim_recovery_stage,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    ModelAttemptAuditRecord,
    ModelStepRunner,
    current_model_attempt_audit,
    start_model_attempt_audit,
    stop_model_attempt_audit,
)
from pydantic import BaseModel

_MAX_INVENTORY_CLAIMS_PER_CHUNK = 64


@dataclass(slots=True)
class LLMRelationExtractionAttempt:
    """Observable result of the decomposed agent extraction pipeline."""

    candidates: list[ExtractedRelationCandidate]
    unknown_relation_types: set[str]
    raw_relation_count: int
    inventory_claim_count: int = 0
    framing_abstention_count: int = 0
    processed_chunk_count: int = 0
    semantic_inventory_complete: bool = True
    inventory_incompleteness: tuple[BoundClaimInventoryItem, ...] = ()
    claim_lineage: tuple[ClaimExtractionLineage, ...] = ()
    raw_agent_outputs: tuple[dict[str, object], ...] = ()
    model_attempt_records: tuple[ModelAttemptAuditRecord, ...] = ()


@dataclass(frozen=True, slots=True)
class _ChunkInventoryOutcome:
    """Complete-or-explicitly-incomplete inventory result for one source chunk."""

    claims: tuple[BoundClaimInventoryItem, ...]
    unresolved_missing_claims: tuple[BoundClaimInventoryItem, ...]
    raw_agent_outputs: tuple[dict[str, object], ...]

    @property
    def complete(self) -> bool:
        return not self.unresolved_missing_claims


async def run_llm_relation_extraction_with_zero_retry(
    *,
    normalized_text: str,
    chunks: tuple[RelationExtractionTextChunk, ...],
    max_relations: int,
    document_fingerprint: str,
    output_schema: type[BaseModel],
    weak_review_output_schema: type[BaseModel],
    client: object,
    tenant: object,
    model_id: str,
    step_runner: ModelStepRunner,
    execution_namespace: str = "",
) -> LLMRelationExtractionAttempt:
    """Inventory claims, then frame each claim in its own strict agent call.

    ``output_schema`` and ``weak_review_output_schema`` remain in the signature
    while the caller migrates. They are deliberately not used as a compatibility
    extraction path: accepting either would restore the multi-relation behavior
    this pipeline replaces.
    """

    del max_relations, output_schema, weak_review_output_schema
    inventory_output_schema = build_claim_inventory_output_schema(
        _MAX_INVENTORY_CLAIMS_PER_CHUNK,
    )
    completeness_output_schema = build_claim_inventory_completeness_output_schema()
    recovery_output_schema = build_missing_claim_recovery_output_schema()
    framing_output_schema = build_single_claim_framing_output_schema()
    extraction_chunks = coalesce_long_sentence_chunks(
        normalized_text=normalized_text,
        chunks=chunks,
    )

    audit_session = current_model_attempt_audit()
    owns_audit_session = audit_session is None
    if audit_session is None:
        audit_session = start_model_attempt_audit()
    first_record_index = len(audit_session.records)

    candidates: list[ExtractedRelationCandidate] = []
    unknown_relation_types: set[str] = set()
    raw_agent_outputs: list[dict[str, object]] = []
    claim_lineage: list[ClaimExtractionLineage] = []
    unresolved_missing_claims: list[BoundClaimInventoryItem] = []
    inventory_claim_count = 0
    framing_abstention_count = 0
    raw_relation_count = 0

    try:
        for chunk in extraction_chunks:
            inventory_outcome = await _inventory_chunk_with_recovery(
                chunk=chunk,
                total_chunks=len(extraction_chunks),
                document_fingerprint=document_fingerprint,
                inventory_output_schema=inventory_output_schema,
                completeness_output_schema=completeness_output_schema,
                recovery_output_schema=recovery_output_schema,
                client=client,
                tenant=tenant,
                model_id=model_id,
                step_runner=step_runner,
                execution_namespace=execution_namespace,
            )
            raw_agent_outputs.extend(inventory_outcome.raw_agent_outputs)
            inventory_claims = inventory_outcome.claims
            unresolved_missing_claims.extend(
                inventory_outcome.unresolved_missing_claims,
            )

            inventory_claim_count += len(inventory_claims)
            for inventory_claim in inventory_claims:
                framing_result = await run_single_claim_framing_stage(
                    inventory_claim=inventory_claim,
                    output_schema=framing_output_schema,
                    client=client,
                    tenant=tenant,
                    model_id=model_id,
                    step_runner=step_runner,
                    execution_namespace=execution_namespace,
                )
                raw_agent_outputs.extend(framing_result.raw_agent_outputs)
                framed_claim = framing_result.framed_claim
                if (
                    framing_result.attempt_record.semantic_unit_id
                    != inventory_claim.inventory_id
                ):
                    raise AssertionError(
                        "claim framing audit lost its stable inventory identity",
                    )
                claim_lineage.append(
                    ClaimExtractionLineage(
                        inventory_id=inventory_claim.inventory_id,
                        source_sha256=inventory_claim.source_sha256,
                        source_start=inventory_claim.source_start,
                        source_end=inventory_claim.source_end,
                        claim_local_source_start=(
                            framing_result.source_region.source_start
                        ),
                        claim_local_source_end=framing_result.source_region.source_end,
                        inventory_payload=inventory_claim.item.model_dump(mode="json"),
                        framing_decision=(
                            "ABSTAIN" if framed_claim.abstained else "FRAMED"
                        ),
                        candidate=framed_claim.candidate,
                        framing_attempt=framing_result.attempt_record.as_json(),
                        raw_agent_output=framing_result.raw_agent_outputs[0],
                    ),
                )
                if framed_claim.abstained:
                    framing_abstention_count += 1
                    continue
                raw_relation_count += 1
                if framed_claim.candidate is not None:
                    candidates.append(framed_claim.candidate)
                if framed_claim.unknown_relation_type is not None:
                    unknown_relation_types.add(framed_claim.unknown_relation_type)

        return LLMRelationExtractionAttempt(
            candidates=candidates,
            unknown_relation_types=unknown_relation_types,
            raw_relation_count=raw_relation_count,
            inventory_claim_count=inventory_claim_count,
            framing_abstention_count=framing_abstention_count,
            processed_chunk_count=len(extraction_chunks),
            semantic_inventory_complete=not unresolved_missing_claims,
            inventory_incompleteness=tuple(unresolved_missing_claims),
            claim_lineage=tuple(claim_lineage),
            raw_agent_outputs=tuple(raw_agent_outputs),
            model_attempt_records=tuple(
                audit_session.records[first_record_index:],
            ),
        )
    finally:
        if owns_audit_session:
            stop_model_attempt_audit(audit_session)


async def _inventory_chunk_with_recovery(
    *,
    chunk: RelationExtractionTextChunk,
    total_chunks: int,
    document_fingerprint: str,
    inventory_output_schema: type[BaseModel],
    completeness_output_schema: type[BaseModel],
    recovery_output_schema: type[BaseModel],
    client: object,
    tenant: object,
    model_id: str,
    step_runner: ModelStepRunner,
    execution_namespace: str,
) -> _ChunkInventoryOutcome:
    inventory_result = await run_claim_inventory_stage(
        chunk=chunk,
        total_chunks=total_chunks,
        document_fingerprint=document_fingerprint,
        output_schema=inventory_output_schema,
        client=client,
        tenant=tenant,
        model_id=model_id,
        step_runner=step_runner,
        execution_namespace=execution_namespace,
    )
    raw_outputs = list(inventory_result.raw_agent_outputs)
    inventory_claims = inventory_result.claims
    review_result = await run_inventory_completeness_review_stage(
        chunk=chunk,
        total_chunks=total_chunks,
        document_fingerprint=document_fingerprint,
        current_inventory=inventory_claims,
        output_schema=completeness_output_schema,
        client=client,
        tenant=tenant,
        model_id=model_id,
        step_runner=step_runner,
        execution_namespace=execution_namespace,
    )
    raw_outputs.extend(review_result.raw_agent_outputs)
    if review_result.review.decision is InventoryCompletenessDecision.COMPLETE:
        return _ChunkInventoryOutcome(
            claims=inventory_claims,
            unresolved_missing_claims=(),
            raw_agent_outputs=tuple(raw_outputs),
        )

    recovered_claims: tuple[BoundClaimInventoryItem, ...] = ()
    for missing_claim in review_result.review.missing_claims:
        recovery_result = await run_missing_claim_recovery_stage(
            chunk=chunk,
            document_fingerprint=document_fingerprint,
            missing_claim=missing_claim,
            output_schema=recovery_output_schema,
            client=client,
            tenant=tenant,
            model_id=model_id,
            step_runner=step_runner,
            execution_namespace=execution_namespace,
        )
        recovered_claims = merge_bound_claim_inventories(
            recovered_claims,
            recovery_result.claims,
        )
        raw_outputs.extend(recovery_result.raw_agent_outputs)

    combined_inventory = merge_bound_claim_inventories(
        inventory_claims,
        recovered_claims,
    )
    confirmation = await run_inventory_completeness_review_stage(
        chunk=chunk,
        total_chunks=total_chunks,
        document_fingerprint=document_fingerprint,
        current_inventory=combined_inventory,
        output_schema=completeness_output_schema,
        client=client,
        tenant=tenant,
        model_id=model_id,
        step_runner=step_runner,
        execution_namespace=execution_namespace,
        confirmation=True,
    )
    raw_outputs.extend(confirmation.raw_agent_outputs)
    unresolved = (
        ()
        if confirmation.review.decision is InventoryCompletenessDecision.COMPLETE
        else confirmation.review.missing_claims
    )
    return _ChunkInventoryOutcome(
        claims=combined_inventory,
        unresolved_missing_claims=unresolved,
        raw_agent_outputs=tuple(raw_outputs),
    )


__all__ = [
    "LLMRelationExtractionAttempt",
    "run_llm_relation_extraction_with_zero_retry",
]
