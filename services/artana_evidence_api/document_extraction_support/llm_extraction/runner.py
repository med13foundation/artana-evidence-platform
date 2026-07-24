"""Inventory-first, one-claim-at-a-time LLM extraction orchestration."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

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
from artana_evidence_api.document_extraction_support.claim_adjudication.candidate_preservation import (
    as_review_only_candidate,
)
from artana_evidence_api.document_extraction_support.claim_frames import (
    BoundClaimInventoryItem,
    BoundControlledEventLink,
    ClaimInventoryItem,
    ControlledEventLinkAmbiguity,
    coalesce_long_sentence_chunks,
    link_controlled_events,
    merge_bound_claim_inventories,
    partition_bound_claim_inventory,
)
from artana_evidence_api.document_extraction_support.full_text_chunking import (
    RelationExtractionTextChunk,
)
from artana_evidence_api.document_extraction_support.llm_extraction.claim_framing import (
    run_single_claim_framing_stage,
)
from artana_evidence_api.document_extraction_support.llm_extraction.claim_inventory import (
    ClaimInventoryBindingRejectionEvent,
    InventoryBatchBindingStatus,
    record_skipped_zero_inventory_retry,
    run_claim_inventory_stage,
)
from artana_evidence_api.document_extraction_support.llm_extraction.inventory_convergence import (
    InventoryConvergenceStopReason,
    run_inventory_completeness_convergence,
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


class NonRelationDisposition(str, Enum):
    """Closed reason why a preserved inventory item cannot enter framing."""

    CLAIM_KIND_ROUTING = "CLAIM_KIND_ROUTING"
    EXCLUDE_PROCEDURAL_METHOD = "EXCLUDE_PROCEDURAL_METHOD"
    EXCLUDE_NOT_EXPLICIT = "EXCLUDE_NOT_EXPLICIT"


@dataclass(frozen=True, slots=True)
class NonRelationInventoryItem:
    """One non-lossy source item plus its categorical routing decision."""

    claim: BoundClaimInventoryItem
    disposition: NonRelationDisposition
    decision_rationale: str

    @property
    def inventory_id(self) -> str:
        return self.claim.inventory_id

    @property
    def item(self) -> ClaimInventoryItem:
        return self.claim.item


@dataclass(slots=True)
class LLMRelationExtractionAttempt:
    """Observable result of the decomposed agent extraction pipeline."""

    candidates: list[ExtractedRelationCandidate]
    unknown_relation_types: set[str]
    raw_relation_count: int
    inventory_claim_count: int = 0
    inventory_binding_rejection_count: int = 0
    inventory_recovery_round_count: int = 0
    inventory_convergence_stop_reasons: tuple[str, ...] = ()
    inventory_convergence_round_traces: tuple[dict[str, object], ...] = ()
    non_relation_item_count: int = 0
    framing_abstention_count: int = 0
    processed_chunk_count: int = 0
    semantic_inventory_complete: bool = True
    inventory_incompleteness: tuple[BoundClaimInventoryItem, ...] = ()
    inventory_binding_rejections: tuple[ClaimInventoryBindingRejectionEvent, ...] = ()
    unresolved_binding_rejection_count: int = 0
    non_relation_items: tuple[NonRelationInventoryItem, ...] = ()
    claim_lineage: tuple[ClaimExtractionLineage, ...] = ()
    raw_agent_outputs: tuple[dict[str, object], ...] = ()
    model_attempt_records: tuple[ModelAttemptAuditRecord, ...] = ()
    controlled_event_links: tuple[BoundControlledEventLink, ...] = ()
    controlled_event_link_ambiguities: tuple[ControlledEventLinkAmbiguity, ...] = ()


@dataclass(frozen=True, slots=True)
class LLMClaimInventoryAttempt:
    """Observable production inventory result before graph framing."""

    claims: tuple[BoundClaimInventoryItem, ...]
    processed_chunk_count: int
    semantic_inventory_complete: bool
    inventory_binding_rejection_count: int
    inventory_recovery_round_count: int
    inventory_convergence_stop_reasons: tuple[str, ...]
    inventory_convergence_round_traces: tuple[dict[str, object], ...]
    inventory_incompleteness: tuple[BoundClaimInventoryItem, ...]
    inventory_binding_rejections: tuple[ClaimInventoryBindingRejectionEvent, ...]
    unresolved_binding_rejection_count: int
    non_relation_items: tuple[NonRelationInventoryItem, ...]
    raw_agent_outputs: tuple[dict[str, object], ...]
    model_attempt_records: tuple[ModelAttemptAuditRecord, ...]
    controlled_event_links: tuple[BoundControlledEventLink, ...] = ()
    controlled_event_link_ambiguities: tuple[ControlledEventLinkAmbiguity, ...] = ()


@dataclass(frozen=True, slots=True)
class _ChunkInventoryOutcome:
    """Complete-or-explicitly-incomplete inventory result for one source chunk."""

    claims: tuple[BoundClaimInventoryItem, ...]
    non_relation_items: tuple[NonRelationInventoryItem, ...]
    unresolved_missing_claims: tuple[BoundClaimInventoryItem, ...]
    binding_rejections: tuple[ClaimInventoryBindingRejectionEvent, ...]
    unresolved_binding_rejection_count: int
    raw_agent_outputs: tuple[dict[str, object], ...]
    recovery_round_count: int
    convergence_stop_reason: InventoryConvergenceStopReason
    convergence_round_traces: tuple[dict[str, object], ...]

    @property
    def complete(self) -> bool:
        return (
            not self.unresolved_missing_claims
            and self.unresolved_binding_rejection_count == 0
        )


@dataclass(frozen=True, slots=True)
class _FramedInventoryOutcome:
    """One source-bound claim after its isolated framing call."""

    lineage: ClaimExtractionLineage
    candidates: tuple[ExtractedRelationCandidate, ...]
    unknown_relation_types: frozenset[str]
    raw_agent_outputs: tuple[dict[str, object], ...]
    abstained: bool


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
    inventory_binding_rejections: list[ClaimInventoryBindingRejectionEvent] = []
    unresolved_binding_rejection_count = 0
    inventory_outcomes: list[_ChunkInventoryOutcome] = []
    inventory_claim_count = 0
    non_relation_items: list[NonRelationInventoryItem] = []
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
            non_relation_items.extend(inventory_outcome.non_relation_items)
            unresolved_missing_claims.extend(
                inventory_outcome.unresolved_missing_claims,
            )
            inventory_binding_rejections.extend(
                inventory_outcome.binding_rejections,
            )
            unresolved_binding_rejection_count += (
                inventory_outcome.unresolved_binding_rejection_count
            )
            inventory_outcomes.append(inventory_outcome)

            inventory_claim_count += len(inventory_claims)
            for inventory_claim in inventory_claims:
                framing = await _frame_inventory_claim(
                    inventory_claim=inventory_claim,
                    framing_output_schema=framing_output_schema,
                    client=client,
                    tenant=tenant,
                    model_id=model_id,
                    step_runner=step_runner,
                    execution_namespace=execution_namespace,
                )
                raw_agent_outputs.extend(framing.raw_agent_outputs)
                claim_lineage.append(framing.lineage)
                if framing.abstained:
                    framing_abstention_count += 1
                    continue
                raw_relation_count += len(framing.candidates)
                candidates.extend(framing.candidates)
                unknown_relation_types.update(framing.unknown_relation_types)

        controlled_events = link_controlled_events(
            tuple(
                claim
                for outcome in inventory_outcomes
                for claim in outcome.claims
            ),
        )
        candidates, claim_lineage = _protect_nested_event_projections(
            candidates=candidates,
            claim_lineage=claim_lineage,
            controlled_event_links=controlled_events.links,
        )
        return LLMRelationExtractionAttempt(
            candidates=candidates,
            unknown_relation_types=unknown_relation_types,
            raw_relation_count=raw_relation_count,
            inventory_claim_count=inventory_claim_count,
            inventory_binding_rejection_count=len(inventory_binding_rejections),
            inventory_recovery_round_count=sum(
                outcome.recovery_round_count for outcome in inventory_outcomes
            ),
            inventory_convergence_stop_reasons=tuple(
                outcome.convergence_stop_reason.value for outcome in inventory_outcomes
            ),
            inventory_convergence_round_traces=tuple(
                trace
                for outcome in inventory_outcomes
                for trace in outcome.convergence_round_traces
            ),
            non_relation_item_count=len(non_relation_items),
            framing_abstention_count=framing_abstention_count,
            processed_chunk_count=len(extraction_chunks),
            semantic_inventory_complete=(
                not unresolved_missing_claims
                and unresolved_binding_rejection_count == 0
                and not controlled_events.ambiguities
            ),
            inventory_incompleteness=tuple(unresolved_missing_claims),
            inventory_binding_rejections=tuple(inventory_binding_rejections),
            unresolved_binding_rejection_count=(unresolved_binding_rejection_count),
            non_relation_items=tuple(non_relation_items),
            claim_lineage=tuple(claim_lineage),
            raw_agent_outputs=tuple(raw_agent_outputs),
            model_attempt_records=tuple(
                audit_session.records[first_record_index:],
            ),
            controlled_event_links=controlled_events.links,
            controlled_event_link_ambiguities=controlled_events.ambiguities,
        )
    finally:
        if owns_audit_session:
            stop_model_attempt_audit(audit_session)


def _protect_nested_event_projections(
    *,
    candidates: list[ExtractedRelationCandidate],
    claim_lineage: list[ClaimExtractionLineage],
    controlled_event_links: tuple[BoundControlledEventLink, ...],
) -> tuple[list[ExtractedRelationCandidate], list[ClaimExtractionLineage]]:
    """Keep event-to-event assertions review-only before downstream transforms."""

    if not controlled_event_links:
        return candidates, claim_lineage
    controller_ids = {
        link.controller_inventory_id for link in controlled_event_links
    }
    protected_lineage = [
        replace(
            lineage,
            candidates=tuple(
                as_review_only_candidate(
                    candidate,
                    "nested_event_projection_pending",
                )
                for candidate in lineage.candidates
            ),
        )
        if lineage.inventory_id in controller_ids
        else lineage
        for lineage in claim_lineage
    ]
    return (
        [
            candidate
            for lineage in protected_lineage
            for candidate in lineage.candidates
        ],
        protected_lineage,
    )


async def _frame_inventory_claim(
    *,
    inventory_claim: BoundClaimInventoryItem,
    framing_output_schema: type[BaseModel],
    client: object,
    tenant: object,
    model_id: str,
    step_runner: ModelStepRunner,
    execution_namespace: str,
) -> _FramedInventoryOutcome:
    framing_result = await run_single_claim_framing_stage(
        inventory_claim=inventory_claim,
        output_schema=framing_output_schema,
        client=client,
        tenant=tenant,
        model_id=model_id,
        step_runner=step_runner,
        execution_namespace=execution_namespace,
    )
    if framing_result.attempt_record.semantic_unit_id != inventory_claim.inventory_id:
        raise AssertionError("claim framing audit lost its stable inventory identity")
    framed_claim = framing_result.framed_claim
    return _FramedInventoryOutcome(
        lineage=ClaimExtractionLineage(
            inventory_id=inventory_claim.inventory_id,
            source_sha256=inventory_claim.source_sha256,
            source_start=inventory_claim.source_start,
            source_end=inventory_claim.source_end,
            claim_local_source_start=framing_result.source_region.source_start,
            claim_local_source_end=framing_result.source_region.source_end,
            inventory_payload=inventory_claim.item.model_dump(mode="json"),
            framing_decision=framed_claim.decision.value,
            candidates=framed_claim.candidates,
            decision_rationale=framed_claim.decision_rationale,
            framing_attempt=framing_result.attempt_record.as_json(),
            raw_agent_output=framing_result.raw_agent_outputs[0],
        ),
        candidates=framed_claim.candidates,
        unknown_relation_types=frozenset(framed_claim.unknown_relation_types),
        raw_agent_outputs=framing_result.raw_agent_outputs,
        abstained=framed_claim.abstained,
    )


async def run_llm_claim_inventory_with_zero_retry(
    *,
    normalized_text: str,
    chunks: tuple[RelationExtractionTextChunk, ...],
    document_fingerprint: str,
    client: object,
    tenant: object,
    model_id: str,
    step_runner: ModelStepRunner,
    execution_namespace: str = "",
) -> LLMClaimInventoryAttempt:
    """Run the production agent inventory and completeness stages only."""

    inventory_output_schema = build_claim_inventory_output_schema(
        _MAX_INVENTORY_CLAIMS_PER_CHUNK,
    )
    completeness_output_schema = build_claim_inventory_completeness_output_schema()
    recovery_output_schema = build_missing_claim_recovery_output_schema()
    extraction_chunks = coalesce_long_sentence_chunks(
        normalized_text=normalized_text,
        chunks=chunks,
    )
    audit_session = current_model_attempt_audit()
    owns_audit_session = audit_session is None
    if audit_session is None:
        audit_session = start_model_attempt_audit()
    first_record_index = len(audit_session.records)
    claims: tuple[BoundClaimInventoryItem, ...] = ()
    unresolved: tuple[BoundClaimInventoryItem, ...] = ()
    binding_rejections: tuple[ClaimInventoryBindingRejectionEvent, ...] = ()
    unresolved_binding_rejection_count = 0
    inventory_recovery_round_count = 0
    inventory_convergence_stop_reasons: tuple[str, ...] = ()
    inventory_convergence_round_traces: tuple[dict[str, object], ...] = ()
    non_relation_items: tuple[NonRelationInventoryItem, ...] = ()
    raw_outputs: tuple[dict[str, object], ...] = ()
    try:
        for chunk in extraction_chunks:
            outcome = await _inventory_chunk_with_recovery(
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
            claims = merge_bound_claim_inventories(claims, outcome.claims)
            unresolved = merge_bound_claim_inventories(
                unresolved,
                outcome.unresolved_missing_claims,
            )
            binding_rejections += outcome.binding_rejections
            unresolved_binding_rejection_count += (
                outcome.unresolved_binding_rejection_count
            )
            inventory_recovery_round_count += outcome.recovery_round_count
            inventory_convergence_stop_reasons += (
                outcome.convergence_stop_reason.value,
            )
            inventory_convergence_round_traces += outcome.convergence_round_traces
            non_relation_items = _merge_non_relation_items(
                non_relation_items,
                outcome.non_relation_items,
            )
            raw_outputs += outcome.raw_agent_outputs
        controlled_events = link_controlled_events(claims)
        return LLMClaimInventoryAttempt(
            claims=claims,
            processed_chunk_count=len(extraction_chunks),
            semantic_inventory_complete=(
                not unresolved
                and unresolved_binding_rejection_count == 0
                and not controlled_events.ambiguities
            ),
            inventory_binding_rejection_count=len(binding_rejections),
            inventory_recovery_round_count=inventory_recovery_round_count,
            inventory_convergence_stop_reasons=(
                inventory_convergence_stop_reasons
            ),
            inventory_convergence_round_traces=(
                inventory_convergence_round_traces
            ),
            inventory_incompleteness=unresolved,
            inventory_binding_rejections=binding_rejections,
            unresolved_binding_rejection_count=(unresolved_binding_rejection_count),
            non_relation_items=non_relation_items,
            raw_agent_outputs=raw_outputs,
            model_attempt_records=tuple(
                audit_session.records[first_record_index:],
            ),
            controlled_event_links=controlled_events.links,
            controlled_event_link_ambiguities=controlled_events.ambiguities,
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
    binding_rejections = inventory_result.binding_rejections
    if inventory_result.binding_status is not InventoryBatchBindingStatus.EMPTY:
        record_skipped_zero_inventory_retry(
            chunk=chunk,
            total_chunks=total_chunks,
            document_fingerprint=document_fingerprint,
            output_schema=inventory_output_schema,
            model_id=model_id,
            execution_namespace=execution_namespace,
        )
    else:
        retry_result = await run_claim_inventory_stage(
            chunk=chunk,
            total_chunks=total_chunks,
            document_fingerprint=document_fingerprint,
            output_schema=inventory_output_schema,
            client=client,
            tenant=tenant,
            model_id=model_id,
            step_runner=step_runner,
            execution_namespace=execution_namespace,
            zero_retry=True,
        )
        raw_outputs.extend(retry_result.raw_agent_outputs)
        inventory_claims = retry_result.claims
        binding_rejections += retry_result.binding_rejections
    convergence = await run_inventory_completeness_convergence(
        chunk=chunk,
        total_chunks=total_chunks,
        document_fingerprint=document_fingerprint,
        inventory=inventory_claims,
        binding_rejections=binding_rejections,
        completeness_output_schema=completeness_output_schema,
        recovery_output_schema=recovery_output_schema,
        client=client,
        tenant=tenant,
        model_id=model_id,
        step_runner=step_runner,
        execution_namespace=execution_namespace,
    )
    raw_outputs.extend(convergence.raw_agent_outputs)
    excluded_items = tuple(
        NonRelationInventoryItem(
            claim=exclusion.claim,
            disposition=NonRelationDisposition(exclusion.disposition.value),
            decision_rationale=exclusion.decision_rationale,
        )
        for exclusion in convergence.exclusions
    )
    claims, non_relation_items = _partition_inventory(convergence.inventory)
    return _ChunkInventoryOutcome(
        claims=claims,
        non_relation_items=_merge_non_relation_items(
            non_relation_items,
            excluded_items,
        ),
        unresolved_missing_claims=convergence.unresolved_missing_claims,
        binding_rejections=convergence.binding_rejections,
        unresolved_binding_rejection_count=(
            convergence.unresolved_binding_rejection_count
        ),
        raw_agent_outputs=tuple(raw_outputs),
        recovery_round_count=convergence.recovery_round_count,
        convergence_stop_reason=convergence.stop_reason,
        convergence_round_traces=tuple(
            trace.as_json() for trace in convergence.round_traces
        ),
    )


def _partition_inventory(
    inventory: tuple[BoundClaimInventoryItem, ...],
) -> tuple[
    tuple[BoundClaimInventoryItem, ...],
    tuple[NonRelationInventoryItem, ...],
]:
    relation_claims, excluded_claims = partition_bound_claim_inventory(inventory)
    non_relation_items = tuple(
        NonRelationInventoryItem(
            claim=claim,
            disposition=NonRelationDisposition.CLAIM_KIND_ROUTING,
            decision_rationale=claim.item.inventory_rationale,
        )
        for claim in excluded_claims
    )
    return relation_claims, non_relation_items


def _merge_non_relation_items(
    *inventories: tuple[NonRelationInventoryItem, ...],
) -> tuple[NonRelationInventoryItem, ...]:
    merged: list[NonRelationInventoryItem] = []
    seen_ids: set[str] = set()
    for inventory in inventories:
        for item in inventory:
            if item.inventory_id in seen_ids:
                continue
            seen_ids.add(item.inventory_id)
            merged.append(item)
    return tuple(merged)


__all__ = [
    "LLMClaimInventoryAttempt",
    "LLMRelationExtractionAttempt",
    "NonRelationDisposition",
    "NonRelationInventoryItem",
    "run_llm_claim_inventory_with_zero_retry",
    "run_llm_relation_extraction_with_zero_retry",
]
