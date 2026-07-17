"""Bounded completeness convergence for source-bound claim inventories."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from artana_evidence_api.document_extraction_support.claim_frames import (
    BoundClaimInventoryItem,
    BoundInventoryCompletenessReview,
    ClaimInventoryBindingRejection,
    InventoryCompletenessDecision,
    MissingClaimRecoveryDisposition,
    canonicalize_bound_claim_inventory,
    merge_bound_claim_inventories,
    merge_claim_inventory_binding_rejections,
)
from artana_evidence_api.document_extraction_support.full_text_chunking import (
    RelationExtractionTextChunk,
)
from artana_evidence_api.document_extraction_support.llm_extraction.claim_inventory import (
    ClaimInventoryBindingRejectionEvent,
    inventory_completeness_input_sha256,
    run_inventory_completeness_review_stage,
    run_missing_claim_recovery_stage,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    ModelStepRunner,
)
from pydantic import BaseModel

MAX_INVENTORY_RECOVERY_ROUNDS: Final = 2


class InventoryConvergenceStopReason(str, Enum):
    """Closed reason why one chunk's completeness loop stopped."""

    INITIAL_COMPLETE = "INITIAL_COMPLETE"
    CONFIRMED_COMPLETE = "CONFIRMED_COMPLETE"
    RECOVERY_ABSTAINED = "RECOVERY_ABSTAINED"
    NO_NEW_IDENTITIES = "NO_NEW_IDENTITIES"
    MAX_RECOVERY_ROUNDS = "MAX_RECOVERY_ROUNDS"


@dataclass(frozen=True, slots=True)
class InventoryRecoveryExclusion:
    """One source-bound descriptor excluded by a categorical agent decision."""

    claim: BoundClaimInventoryItem
    disposition: MissingClaimRecoveryDisposition
    decision_rationale: str


@dataclass(frozen=True, slots=True)
class InventoryRecoveryDecisionTrace:
    """One categorical descriptor decision inside a deterministic round trace."""

    inventory_id: str
    disposition: MissingClaimRecoveryDisposition


@dataclass(frozen=True, slots=True)
class InventoryConvergenceRoundTrace:
    """Provider-independent state transition for one recovery round."""

    chunk_index: int
    recovery_round: int
    parent_completeness_input_sha256: str
    input_inventory_ids: tuple[str, ...]
    missing_descriptor_ids: tuple[str, ...]
    decisions: tuple[InventoryRecoveryDecisionTrace, ...]
    output_inventory_ids: tuple[str, ...]
    excluded_inventory_ids: tuple[str, ...]

    def as_json(self) -> dict[str, object]:
        return {
            "chunk_index": self.chunk_index,
            "recovery_round": self.recovery_round,
            "parent_completeness_input_sha256": (
                self.parent_completeness_input_sha256
            ),
            "input_inventory_ids": list(self.input_inventory_ids),
            "missing_descriptor_ids": list(self.missing_descriptor_ids),
            "decisions": [
                {
                    "inventory_id": decision.inventory_id,
                    "disposition": decision.disposition.value,
                }
                for decision in self.decisions
            ],
            "output_inventory_ids": list(self.output_inventory_ids),
            "excluded_inventory_ids": list(self.excluded_inventory_ids),
        }


@dataclass(frozen=True, slots=True)
class InventoryConvergenceResult:
    """Auditable terminal state of the bounded completeness loop."""

    inventory: tuple[BoundClaimInventoryItem, ...]
    exclusions: tuple[InventoryRecoveryExclusion, ...]
    unresolved_missing_claims: tuple[BoundClaimInventoryItem, ...]
    binding_rejections: tuple[ClaimInventoryBindingRejectionEvent, ...]
    unresolved_binding_rejection_count: int
    raw_agent_outputs: tuple[dict[str, object], ...]
    recovery_round_count: int
    stop_reason: InventoryConvergenceStopReason
    round_traces: tuple[InventoryConvergenceRoundTrace, ...]

    @property
    def complete(self) -> bool:
        return (
            not self.unresolved_missing_claims
            and self.unresolved_binding_rejection_count == 0
            and self.stop_reason
            in {
                InventoryConvergenceStopReason.INITIAL_COMPLETE,
                InventoryConvergenceStopReason.CONFIRMED_COMPLETE,
            }
        )


@dataclass(frozen=True, slots=True)
class _RecoveryRoundResult:
    recovered: tuple[BoundClaimInventoryItem, ...]
    exclusions: tuple[InventoryRecoveryExclusion, ...]
    unresolved: tuple[BoundClaimInventoryItem, ...]
    raw_agent_outputs: tuple[dict[str, object], ...]
    abstained: bool
    decisions: tuple[InventoryRecoveryDecisionTrace, ...]


async def run_inventory_completeness_convergence(
    *,
    chunk: RelationExtractionTextChunk,
    total_chunks: int,
    document_fingerprint: str,
    inventory: tuple[BoundClaimInventoryItem, ...],
    binding_rejections: tuple[ClaimInventoryBindingRejectionEvent, ...],
    completeness_output_schema: type[BaseModel],
    recovery_output_schema: type[BaseModel],
    client: object,
    tenant: object,
    model_id: str,
    step_runner: ModelStepRunner,
    execution_namespace: str,
) -> InventoryConvergenceResult:
    """Review and recover an inventory with a strict two-round upper bound."""

    current_inventory = canonicalize_bound_claim_inventory(inventory)
    exclusions: tuple[InventoryRecoveryExclusion, ...] = ()
    round_traces: tuple[InventoryConvergenceRoundTrace, ...] = ()
    raw_outputs: tuple[dict[str, object], ...] = ()
    all_rejections = binding_rejections
    initial_prompt_rejections = _prompt_binding_rejections(all_rejections)
    review_input_sha256 = inventory_completeness_input_sha256(
        current_inventory,
        (),
        initial_prompt_rejections,
    )
    review_result = await run_inventory_completeness_review_stage(
        chunk=chunk,
        total_chunks=total_chunks,
        document_fingerprint=document_fingerprint,
        current_inventory=current_inventory,
        binding_rejections=initial_prompt_rejections,
        output_schema=completeness_output_schema,
        client=client,
        tenant=tenant,
        model_id=model_id,
        step_runner=step_runner,
        execution_namespace=execution_namespace,
    )
    raw_outputs += review_result.raw_agent_outputs
    all_rejections += review_result.binding_rejections
    review = review_result.review
    if review.decision is InventoryCompletenessDecision.COMPLETE:
        return _result(
            inventory=current_inventory,
            exclusions=exclusions,
            binding_rejections=all_rejections,
            raw_outputs=raw_outputs,
            recovery_round_count=0,
            stop_reason=InventoryConvergenceStopReason.INITIAL_COMPLETE,
            round_traces=round_traces,
        )

    for recovery_round in range(1, MAX_INVENTORY_RECOVERY_ROUNDS + 1):
        if not review.missing_claims:
            return _result(
                inventory=current_inventory,
                exclusions=exclusions,
                binding_rejections=all_rejections,
                unresolved_binding_rejection_count=len(review.binding_rejections),
                raw_outputs=raw_outputs,
                recovery_round_count=recovery_round - 1,
                stop_reason=InventoryConvergenceStopReason.NO_NEW_IDENTITIES,
                round_traces=round_traces,
            )
        before_ids = _adjudicated_inventory_ids(current_inventory, exclusions)
        input_inventory_ids = _inventory_ids(current_inventory)
        round_result = await _run_recovery_round(
            review=review,
            recovery_round=recovery_round,
            parent_completeness_input_sha256=review_input_sha256,
            chunk=chunk,
            document_fingerprint=document_fingerprint,
            recovery_output_schema=recovery_output_schema,
            client=client,
            tenant=tenant,
            model_id=model_id,
            step_runner=step_runner,
            execution_namespace=execution_namespace,
        )
        raw_outputs += round_result.raw_agent_outputs
        current_inventory = canonicalize_bound_claim_inventory(
            merge_bound_claim_inventories(
                current_inventory,
                round_result.recovered,
            )
        )
        exclusions = _merge_exclusions(exclusions, round_result.exclusions)
        round_traces += (
            InventoryConvergenceRoundTrace(
                chunk_index=chunk.index,
                recovery_round=recovery_round,
                parent_completeness_input_sha256=review_input_sha256,
                input_inventory_ids=input_inventory_ids,
                missing_descriptor_ids=_inventory_ids(review.missing_claims),
                decisions=round_result.decisions,
                output_inventory_ids=_inventory_ids(current_inventory),
                excluded_inventory_ids=_inventory_ids(
                    tuple(item.claim for item in exclusions)
                ),
            ),
        )
        if round_result.abstained:
            return _result(
                inventory=current_inventory,
                exclusions=exclusions,
                unresolved_missing_claims=round_result.unresolved,
                binding_rejections=all_rejections,
                unresolved_binding_rejection_count=len(review.binding_rejections),
                raw_outputs=raw_outputs,
                recovery_round_count=recovery_round,
                stop_reason=InventoryConvergenceStopReason.RECOVERY_ABSTAINED,
                round_traces=round_traces,
            )

        after_ids = _adjudicated_inventory_ids(current_inventory, exclusions)
        if after_ids == before_ids:
            return _result(
                inventory=current_inventory,
                exclusions=exclusions,
                unresolved_missing_claims=review.missing_claims,
                binding_rejections=all_rejections,
                unresolved_binding_rejection_count=len(review.binding_rejections),
                raw_outputs=raw_outputs,
                recovery_round_count=recovery_round - 1,
                stop_reason=InventoryConvergenceStopReason.NO_NEW_IDENTITIES,
                round_traces=round_traces,
            )

        confirmation_rejections = _prompt_binding_rejections(all_rejections)
        confirmation_excluded = canonicalize_bound_claim_inventory(
            tuple(item.claim for item in exclusions)
        )
        confirmation_input_sha256 = inventory_completeness_input_sha256(
            current_inventory,
            confirmation_excluded,
            confirmation_rejections,
        )
        confirmation = await run_inventory_completeness_review_stage(
            chunk=chunk,
            total_chunks=total_chunks,
            document_fingerprint=document_fingerprint,
            current_inventory=current_inventory,
            excluded_inventory=confirmation_excluded,
            binding_rejections=confirmation_rejections,
            output_schema=completeness_output_schema,
            client=client,
            tenant=tenant,
            model_id=model_id,
            step_runner=step_runner,
            execution_namespace=execution_namespace,
            confirmation=True,
            recovery_round=recovery_round,
        )
        raw_outputs += confirmation.raw_agent_outputs
        all_rejections += confirmation.binding_rejections
        review = confirmation.review
        if review.decision is InventoryCompletenessDecision.COMPLETE:
            return _result(
                inventory=current_inventory,
                exclusions=exclusions,
                binding_rejections=all_rejections,
                raw_outputs=raw_outputs,
                recovery_round_count=recovery_round,
                stop_reason=InventoryConvergenceStopReason.CONFIRMED_COMPLETE,
                round_traces=round_traces,
            )
        review_input_sha256 = confirmation_input_sha256

    return _result(
        inventory=current_inventory,
        exclusions=exclusions,
        unresolved_missing_claims=review.missing_claims,
        binding_rejections=all_rejections,
        unresolved_binding_rejection_count=len(review.binding_rejections),
        raw_outputs=raw_outputs,
        recovery_round_count=MAX_INVENTORY_RECOVERY_ROUNDS,
        stop_reason=InventoryConvergenceStopReason.MAX_RECOVERY_ROUNDS,
        round_traces=round_traces,
    )


async def _run_recovery_round(
    *,
    review: BoundInventoryCompletenessReview,
    recovery_round: int,
    parent_completeness_input_sha256: str,
    chunk: RelationExtractionTextChunk,
    document_fingerprint: str,
    recovery_output_schema: type[BaseModel],
    client: object,
    tenant: object,
    model_id: str,
    step_runner: ModelStepRunner,
    execution_namespace: str,
) -> _RecoveryRoundResult:
    recovered: tuple[BoundClaimInventoryItem, ...] = ()
    exclusions: tuple[InventoryRecoveryExclusion, ...] = ()
    raw_outputs: tuple[dict[str, object], ...] = ()
    unresolved: tuple[BoundClaimInventoryItem, ...] = ()
    decisions: tuple[InventoryRecoveryDecisionTrace, ...] = ()
    for missing_claim in canonicalize_bound_claim_inventory(review.missing_claims):
        recovery = await run_missing_claim_recovery_stage(
            chunk=chunk,
            document_fingerprint=document_fingerprint,
            missing_claim=missing_claim,
            recovery_round=recovery_round,
            parent_completeness_input_sha256=(parent_completeness_input_sha256),
            output_schema=recovery_output_schema,
            client=client,
            tenant=tenant,
            model_id=model_id,
            step_runner=step_runner,
            execution_namespace=execution_namespace,
        )
        raw_outputs += recovery.raw_agent_outputs
        decisions += (
            InventoryRecoveryDecisionTrace(
                inventory_id=missing_claim.inventory_id,
                disposition=recovery.decision,
            ),
        )
        if (
            recovery.decision
            is MissingClaimRecoveryDisposition.RECOVER_EXPLICIT_CLAIM
        ):
            recovered = merge_bound_claim_inventories(
                recovered,
                (recovery.reviewed_claim,),
            )
            continue
        if recovery.decision in {
            MissingClaimRecoveryDisposition.EXCLUDE_PROCEDURAL_METHOD,
            MissingClaimRecoveryDisposition.EXCLUDE_NOT_EXPLICIT,
        }:
            exclusions = _merge_exclusions(
                exclusions,
                (
                    InventoryRecoveryExclusion(
                        claim=recovery.reviewed_claim,
                        disposition=recovery.decision,
                        decision_rationale=recovery.decision_rationale,
                    ),
                ),
            )
            continue
        unresolved = canonicalize_bound_claim_inventory(
            merge_bound_claim_inventories(unresolved, (missing_claim,))
        )
    return _RecoveryRoundResult(
        recovered=recovered,
        exclusions=exclusions,
        unresolved=unresolved,
        raw_agent_outputs=raw_outputs,
        abstained=bool(unresolved),
        decisions=decisions,
    )


def _result(
    *,
    inventory: tuple[BoundClaimInventoryItem, ...],
    exclusions: tuple[InventoryRecoveryExclusion, ...],
    binding_rejections: tuple[ClaimInventoryBindingRejectionEvent, ...],
    raw_outputs: tuple[dict[str, object], ...],
    recovery_round_count: int,
    stop_reason: InventoryConvergenceStopReason,
    round_traces: tuple[InventoryConvergenceRoundTrace, ...],
    unresolved_missing_claims: tuple[BoundClaimInventoryItem, ...] = (),
    unresolved_binding_rejection_count: int = 0,
) -> InventoryConvergenceResult:
    return InventoryConvergenceResult(
        inventory=inventory,
        exclusions=exclusions,
        unresolved_missing_claims=unresolved_missing_claims,
        binding_rejections=binding_rejections,
        unresolved_binding_rejection_count=unresolved_binding_rejection_count,
        raw_agent_outputs=raw_outputs,
        recovery_round_count=recovery_round_count,
        stop_reason=stop_reason,
        round_traces=round_traces,
    )


def _adjudicated_inventory_ids(
    inventory: tuple[BoundClaimInventoryItem, ...],
    exclusions: tuple[InventoryRecoveryExclusion, ...],
) -> frozenset[str]:
    return frozenset(
        claim.inventory_id for claim in inventory
    ) | frozenset(exclusion.claim.inventory_id for exclusion in exclusions)


def _merge_exclusions(
    *groups: tuple[InventoryRecoveryExclusion, ...],
) -> tuple[InventoryRecoveryExclusion, ...]:
    merged: list[InventoryRecoveryExclusion] = []
    seen_ids: set[str] = set()
    for group in groups:
        for exclusion in group:
            if exclusion.claim.inventory_id in seen_ids:
                continue
            seen_ids.add(exclusion.claim.inventory_id)
            merged.append(exclusion)
    return tuple(
        sorted(
            merged,
            key=lambda item: (
                item.claim.source_start,
                item.claim.source_end,
                item.claim.inventory_id,
            ),
        )
    )


def _inventory_ids(
    inventory: tuple[BoundClaimInventoryItem, ...],
) -> tuple[str, ...]:
    return tuple(
        claim.inventory_id for claim in canonicalize_bound_claim_inventory(inventory)
    )


def _prompt_binding_rejections(
    events: tuple[ClaimInventoryBindingRejectionEvent, ...],
) -> tuple[ClaimInventoryBindingRejection, ...]:
    return merge_claim_inventory_binding_rejections(
        tuple(event.rejection for event in events),
    )


__all__ = [
    "MAX_INVENTORY_RECOVERY_ROUNDS",
    "InventoryConvergenceResult",
    "InventoryConvergenceRoundTrace",
    "InventoryConvergenceStopReason",
    "InventoryRecoveryDecisionTrace",
    "InventoryRecoveryExclusion",
    "run_inventory_completeness_convergence",
]
