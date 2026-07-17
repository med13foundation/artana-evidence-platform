"""Deterministic replay of bounded claim-inventory convergence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from artana_evidence_api.document_extraction_prompting import (
    build_claim_inventory_completeness_output_schema,
    build_claim_inventory_output_schema,
    build_missing_claim_recovery_output_schema,
)
from artana_evidence_api.document_extraction_support.claim_frames import (
    BoundClaimInventoryItem,
    BoundInventoryCompletenessReview,
    ClaimInventoryBindingRejection,
    ClaimInventoryCompletenessReview,
    ClaimInventoryItem,
    InventoryCompletenessDecision,
    MissingClaimRecoveryDecision,
    MissingClaimRecoveryDisposition,
    bind_claim_inventory_items,
    bind_inventory_completeness_review,
    canonicalize_bound_claim_inventory,
    claim_inventory_batch_input_sha256,
    merge_bound_claim_inventories,
    merge_claim_inventory_binding_rejections,
    partition_bound_claim_inventory,
)
from artana_evidence_api.document_extraction_support.llm_extraction.claim_inventory import (
    build_claim_inventory_prompt,
    build_inventory_completeness_prompt,
    build_missing_claim_recovery_prompt,
    inventory_completeness_input_sha256,
)
from artana_evidence_api.document_extraction_support.llm_extraction.inventory_convergence import (
    MAX_INVENTORY_RECOVERY_ROUNDS,
    InventoryConvergenceStopReason,
)
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    bind_prompt_to_invocation,
    output_schema_json_sha256,
)

from scripts.validation.claim_events.binding_rejections import (
    require_exact_rejection_events,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.full_text_chunking import (
        RelationExtractionTextChunk,
    )

_MAX_INVENTORY_CLAIMS_PER_CHUNK = 64


@dataclass(frozen=True, slots=True)
class InventoryWorkflowInput:
    """Provider-backed records required to replay one case inventory."""

    chunks: tuple[RelationExtractionTextChunk, ...]
    initial_by_input: Mapping[str, Mapping[str, object]]
    zero_by_input: Mapping[str, Mapping[str, object]]
    source_sha256: str
    evidence_unit_sha256: str
    completeness_attempts: Sequence[Mapping[str, object]]
    recovery_attempts: Sequence[Mapping[str, object]]
    inventory_binding_rejections_by_chunk: Mapping[
        int,
        tuple[ClaimInventoryBindingRejection, ...],
    ]
    completeness_binding_rejection_events: Sequence[Mapping[str, object]]


@dataclass(frozen=True, slots=True)
class InventoryWorkflowReplay:
    """Canonical, provider-independent result of one workflow replay."""

    topology_sha256: str
    accepted_inventory: dict[str, str]
    complete: bool
    recovery_round_count: int
    stop_reasons: tuple[str, ...]
    round_traces: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class _PromptContext:
    total_chunks: int
    source_sha256: str
    evidence_unit_sha256: str
    output_schema_identity: str
    output_schema_sha256: str
    completeness_schema_identity: str
    completeness_schema_sha256: str
    recovery_schema_identity: str
    recovery_schema_sha256: str


@dataclass(frozen=True, slots=True)
class _CompletenessSelection:
    chunk: RelationExtractionTextChunk
    inventory: tuple[BoundClaimInventoryItem, ...]
    excluded_inventory: tuple[BoundClaimInventoryItem, ...]
    binding_rejections: tuple[ClaimInventoryBindingRejection, ...]
    recovery_round: int

    @property
    def confirmation(self) -> bool:
        return self.recovery_round > 0


@dataclass(frozen=True, slots=True)
class _RecoveryContext:
    chunk: RelationExtractionTextChunk
    prompt: _PromptContext
    recovery_round: int
    parent_completeness_input_sha256: str


@dataclass(frozen=True, slots=True)
class _RecoveryEvidence:
    attempt: Mapping[str, object]
    decision: MissingClaimRecoveryDecision


@dataclass(frozen=True, slots=True)
class _RecoveryReplay:
    recovered: tuple[BoundClaimInventoryItem, ...]
    excluded: tuple[BoundClaimInventoryItem, ...]
    unresolved: tuple[BoundClaimInventoryItem, ...]
    signatures: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class _RoundTraceInput:
    chunk_index: int
    recovery_round: int
    parent_input_sha256: str
    input_inventory_ids: tuple[str, ...]
    missing_claims: tuple[BoundClaimInventoryItem, ...]
    decisions: tuple[dict[str, object], ...]
    output_inventory: tuple[BoundClaimInventoryItem, ...]
    excluded_inventory: tuple[BoundClaimInventoryItem, ...]


@dataclass(frozen=True, slots=True)
class _ChunkReplay:
    signature: dict[str, object]
    relation_inventory: tuple[BoundClaimInventoryItem, ...]
    complete: bool
    recovery_round_count: int
    stop_reason: InventoryConvergenceStopReason
    round_traces: tuple[dict[str, object], ...]


@dataclass(slots=True)
class _ReplayState:
    workflow: InventoryWorkflowInput
    prompt: _PromptContext
    completeness_attempts: list[Mapping[str, object]]
    recovery_attempts: list[Mapping[str, object]]
    completeness_rejection_events: list[Mapping[str, object]]


def replay_inventory_workflow(
    workflow: InventoryWorkflowInput,
    *,
    require_complete: bool,
) -> InventoryWorkflowReplay:
    """Replay every bounded state transition and enforce the terminal category."""

    state = _replay_state(workflow)
    signatures: list[dict[str, object]] = []
    accepted_inventory: dict[str, str] = {}
    stop_reasons: list[str] = []
    round_traces: list[dict[str, object]] = []
    recovery_round_count = 0
    complete = True
    for chunk in workflow.chunks:
        replay = _replay_chunk(chunk=chunk, state=state)
        signatures.append(replay.signature)
        _merge_accepted_inventory(
            accepted_inventory=accepted_inventory,
            claims=replay.relation_inventory,
        )
        complete = complete and replay.complete
        recovery_round_count += replay.recovery_round_count
        stop_reasons.append(replay.stop_reason.value)
        round_traces.extend(replay.round_traces)
    _require_no_unused_evidence(state)
    if require_complete != complete:
        expected = "complete" if require_complete else "semantically incomplete"
        raise ValueError(f"TG-04 inventory replay was not {expected}")
    return InventoryWorkflowReplay(
        topology_sha256=_canonical_sha256(signatures),
        accepted_inventory=accepted_inventory,
        complete=complete,
        recovery_round_count=recovery_round_count,
        stop_reasons=tuple(stop_reasons),
        round_traces=tuple(round_traces),
    )


def _replay_state(workflow: InventoryWorkflowInput) -> _ReplayState:
    expected_inputs = {chunk.sha256 for chunk in workflow.chunks}
    if (
        set(workflow.initial_by_input) != expected_inputs
        or set(workflow.zero_by_input) != expected_inputs
    ):
        raise ValueError("TG-04 inventory attempts do not cover every source chunk")
    inventory_schema = build_claim_inventory_output_schema(
        _MAX_INVENTORY_CLAIMS_PER_CHUNK
    )
    completeness_schema = build_claim_inventory_completeness_output_schema()
    recovery_schema = build_missing_claim_recovery_output_schema()
    return _ReplayState(
        workflow=workflow,
        prompt=_PromptContext(
            total_chunks=len(workflow.chunks),
            source_sha256=workflow.source_sha256,
            evidence_unit_sha256=workflow.evidence_unit_sha256,
            output_schema_identity=(
                f"{inventory_schema.__module__}.{inventory_schema.__qualname__}"
            ),
            output_schema_sha256=output_schema_json_sha256(inventory_schema),
            completeness_schema_identity=(
                f"{completeness_schema.__module__}.{completeness_schema.__qualname__}"
            ),
            completeness_schema_sha256=output_schema_json_sha256(
                completeness_schema
            ),
            recovery_schema_identity=(
                f"{recovery_schema.__module__}.{recovery_schema.__qualname__}"
            ),
            recovery_schema_sha256=output_schema_json_sha256(recovery_schema),
        ),
        completeness_attempts=list(workflow.completeness_attempts),
        recovery_attempts=list(workflow.recovery_attempts),
        completeness_rejection_events=list(
            workflow.completeness_binding_rejection_events
        ),
    )


def _replay_chunk(
    *,
    chunk: RelationExtractionTextChunk,
    state: _ReplayState,
) -> _ChunkReplay:
    initial, zero, inventory, prompt_rejections = _replay_initial_inventory(
        chunk=chunk,
        state=state,
    )
    review = _take_completeness_review(
        state=state,
        selection=_CompletenessSelection(
            chunk=chunk,
            inventory=inventory,
            excluded_inventory=(),
            binding_rejections=prompt_rejections,
            recovery_round=0,
        ),
    )
    combined_inventory = inventory
    excluded: tuple[BoundClaimInventoryItem, ...] = ()
    cumulative_rejections = prompt_rejections
    review_input_sha256 = inventory_completeness_input_sha256(
        inventory,
        (),
        prompt_rejections,
    )
    recovery_signatures: list[dict[str, object]] = []
    round_traces: list[dict[str, object]] = []
    stop_reason = InventoryConvergenceStopReason.INITIAL_COMPLETE
    recovery_round_count = 0
    if review.decision is InventoryCompletenessDecision.INCOMPLETE:
        for recovery_round in range(1, MAX_INVENTORY_RECOVERY_ROUNDS + 1):
            if not review.missing_claims:
                stop_reason = InventoryConvergenceStopReason.NO_NEW_IDENTITIES
                break
            before_ids = _adjudicated_ids(combined_inventory, excluded)
            recovery = _replay_recovery_round(
                review=review,
                attempts=state.recovery_attempts,
                context=_RecoveryContext(
                    chunk=chunk,
                    prompt=state.prompt,
                    recovery_round=recovery_round,
                    parent_completeness_input_sha256=review_input_sha256,
                ),
            )
            recovery_round_count = recovery_round
            input_inventory_ids = _inventory_ids(combined_inventory)
            combined_inventory = canonicalize_bound_claim_inventory(
                merge_bound_claim_inventories(combined_inventory, recovery.recovered)
            )
            excluded = canonicalize_bound_claim_inventory(
                merge_bound_claim_inventories(excluded, recovery.excluded)
            )
            recovery_signatures.extend(recovery.signatures)
            round_traces.append(
                _round_trace(
                    _RoundTraceInput(
                        chunk_index=chunk.index,
                        recovery_round=recovery_round,
                        parent_input_sha256=review_input_sha256,
                        input_inventory_ids=input_inventory_ids,
                        missing_claims=review.missing_claims,
                        decisions=recovery.signatures,
                        output_inventory=combined_inventory,
                        excluded_inventory=excluded,
                    )
                )
            )
            if recovery.unresolved:
                stop_reason = InventoryConvergenceStopReason.RECOVERY_ABSTAINED
                break
            if _adjudicated_ids(combined_inventory, excluded) == before_ids:
                stop_reason = InventoryConvergenceStopReason.NO_NEW_IDENTITIES
                recovery_round_count -= 1
                break
            cumulative_rejections = merge_claim_inventory_binding_rejections(
                cumulative_rejections,
                review.binding_rejections,
            )
            confirmation_selection = _CompletenessSelection(
                chunk=chunk,
                inventory=combined_inventory,
                excluded_inventory=excluded,
                binding_rejections=cumulative_rejections,
                recovery_round=recovery_round,
            )
            confirmation_input_sha256 = inventory_completeness_input_sha256(
                combined_inventory,
                excluded,
                cumulative_rejections,
            )
            confirmation = _take_completeness_review(
                state=state,
                selection=confirmation_selection,
            )
            if confirmation.decision is InventoryCompletenessDecision.COMPLETE:
                stop_reason = InventoryConvergenceStopReason.CONFIRMED_COMPLETE
                review = confirmation
                break
            review = confirmation
            review_input_sha256 = confirmation_input_sha256
        else:
            stop_reason = InventoryConvergenceStopReason.MAX_RECOVERY_ROUNDS
    complete = stop_reason in {
        InventoryConvergenceStopReason.INITIAL_COMPLETE,
        InventoryConvergenceStopReason.CONFIRMED_COMPLETE,
    }
    relation_inventory, _ = partition_bound_claim_inventory(combined_inventory)
    return _ChunkReplay(
        signature={
            "input_sha256": chunk.sha256,
            "initial_prompt_sha256": _sha256_text(
                build_claim_inventory_prompt(
                    chunk=chunk,
                    total_chunks=state.prompt.total_chunks,
                    document_fingerprint=state.prompt.source_sha256,
                )
            ),
            "zero_prompt_sha256": _sha256_text(
                build_claim_inventory_prompt(
                    chunk=chunk,
                    total_chunks=state.prompt.total_chunks,
                    document_fingerprint=state.prompt.source_sha256,
                    zero_retry=True,
                )
            ),
            "output_schema_identity": state.prompt.output_schema_identity,
            "binding_rejection_ids": [
                rejection.rejection_id for rejection in prompt_rejections
            ],
            "recovery": recovery_signatures,
            "excluded_inventory_ids": list(_inventory_ids(excluded)),
            "stop_reason": stop_reason.value,
            "round_traces": round_traces,
        },
        relation_inventory=relation_inventory,
        complete=complete,
        recovery_round_count=recovery_round_count,
        stop_reason=stop_reason,
        round_traces=tuple(round_traces),
    )


def _replay_initial_inventory(
    *,
    chunk: RelationExtractionTextChunk,
    state: _ReplayState,
) -> tuple[
    Mapping[str, object],
    Mapping[str, object],
    tuple[BoundClaimInventoryItem, ...],
    tuple[ClaimInventoryBindingRejection, ...],
]:
    initial = state.workflow.initial_by_input[chunk.sha256]
    if initial.get("validation_outcome") != "accepted":
        raise ValueError("TG-04 primary inventory call must be accepted")
    _validate_inventory_prompt(
        attempt=initial,
        chunk=chunk,
        context=state.prompt,
        zero_retry=False,
        schema_retry=initial.get("attempt_role") == "schema_retry",
    )
    zero = state.workflow.zero_by_input[chunk.sha256]
    prompt_rejections = state.workflow.inventory_binding_rejections_by_chunk.get(
        chunk.index,
        (),
    )
    expected_zero = (
        "intentionally_skipped"
        if _raw_claim_payloads(initial) or prompt_rejections
        else "accepted"
    )
    if zero.get("validation_outcome") != expected_zero:
        raise ValueError("TG-04 zero-inventory retry topology differs from agent output")
    _validate_inventory_prompt(
        attempt=zero,
        chunk=chunk,
        context=state.prompt,
        zero_retry=True,
        schema_retry=zero.get("attempt_role") == "schema_retry",
    )
    selected = zero if zero.get("validation_outcome") == "accepted" else initial
    binding = bind_claim_inventory_items(
        tuple(
            ClaimInventoryItem.model_validate(item)
            for item in _sequence(
                _object(selected.get("raw_model_payload"), "raw model payload").get(
                    "claims"
                ),
                "raw inventory claims",
            )
        ),
        source_text=chunk.text,
        source_sha256=state.workflow.source_sha256,
        chunk_index=chunk.index,
        source_start_offset=chunk.start_char,
    )
    return (
        initial,
        zero,
        canonicalize_bound_claim_inventory(binding.accepted),
        prompt_rejections,
    )


def _take_completeness_review(
    *,
    state: _ReplayState,
    selection: _CompletenessSelection,
) -> BoundInventoryCompletenessReview:
    input_sha256 = inventory_completeness_input_sha256(
        selection.inventory,
        selection.excluded_inventory,
        selection.binding_rejections,
    )
    matches: list[Mapping[str, object]] = []
    for attempt in state.completeness_attempts:
        if attempt.get("input_sha256") != input_sha256:
            continue
        invocation_id = _text(attempt.get("invocation_id"), "completeness invocation_id")
        base_prompt = build_inventory_completeness_prompt(
            chunk=selection.chunk,
            total_chunks=state.prompt.total_chunks,
            document_fingerprint=state.prompt.source_sha256,
            current_inventory=selection.inventory,
            excluded_inventory=selection.excluded_inventory,
            binding_rejections=selection.binding_rejections,
            confirmation=selection.confirmation,
            recovery_round=selection.recovery_round,
            schema_retry=attempt.get("attempt_role") == "schema_retry",
        )
        provider_prompt = bind_prompt_to_invocation(
            prompt=base_prompt,
            invocation_id=invocation_id,
            source_sha256=state.prompt.source_sha256,
            input_sha256=input_sha256,
            evidence_unit_sha256=state.prompt.evidence_unit_sha256,
            output_schema_sha256=state.prompt.completeness_schema_sha256,
        )
        if attempt.get("prompt_sha256") == _sha256_text(provider_prompt):
            matches.append(attempt)
    if len(matches) != 1:
        raise ValueError("TG-04 source chunk lacks one canonical completeness review")
    attempt = matches[0]
    if attempt.get("output_schema_identity") != state.prompt.completeness_schema_identity:
        raise ValueError("TG-04 completeness schema differs from production schema")
    review = bind_inventory_completeness_review(
        ClaimInventoryCompletenessReview.model_validate(
            _object(attempt.get("raw_model_payload"), "completeness raw payload")
        ),
        source_text=selection.chunk.text,
        source_sha256=state.prompt.source_sha256,
        chunk_index=selection.chunk.index,
        source_start_offset=selection.chunk.start_char,
        current_inventory=selection.inventory,
        excluded_inventory=selection.excluded_inventory,
    )
    invocation_id = _text(attempt.get("invocation_id"), "completeness invocation_id")
    rejection_events = tuple(
        event
        for event in state.completeness_rejection_events
        if _object(event.get("attempt_lineage"), "attempt lineage").get(
            "invocation_id"
        )
        == invocation_id
    )
    require_exact_rejection_events(
        attempt=attempt,
        phase="COMPLETENESS_REVIEW",
        expected_rejections=review.binding_rejections,
        reported_events=rejection_events,
    )
    for event in rejection_events:
        state.completeness_rejection_events.remove(event)
    state.completeness_attempts.remove(attempt)
    return review


def _replay_recovery_round(
    *,
    review: BoundInventoryCompletenessReview,
    attempts: list[Mapping[str, object]],
    context: _RecoveryContext,
) -> _RecoveryReplay:
    recovered: tuple[BoundClaimInventoryItem, ...] = ()
    excluded: tuple[BoundClaimInventoryItem, ...] = ()
    unresolved: tuple[BoundClaimInventoryItem, ...] = ()
    signatures: list[dict[str, object]] = []
    for missing_claim in canonicalize_bound_claim_inventory(review.missing_claims):
        evidence = _take_recovery_attempt(
            attempts=attempts,
            missing_claim=missing_claim,
            context=context,
        )
        decision = evidence.decision.decision
        if decision is MissingClaimRecoveryDisposition.RECOVER_EXPLICIT_CLAIM:
            recovered = merge_bound_claim_inventories(recovered, (missing_claim,))
        elif decision in {
            MissingClaimRecoveryDisposition.EXCLUDE_PROCEDURAL_METHOD,
            MissingClaimRecoveryDisposition.EXCLUDE_NOT_EXPLICIT,
        }:
            excluded = merge_bound_claim_inventories(excluded, (missing_claim,))
        else:
            unresolved = merge_bound_claim_inventories(unresolved, (missing_claim,))
        signatures.append(
            {
                "inventory_id": missing_claim.inventory_id,
                "decision": decision.value,
                "recovery_round": context.recovery_round,
                "prompt_sha256": _sha256_text(
                    build_missing_claim_recovery_prompt(
                        chunk=context.chunk,
                        document_fingerprint=context.prompt.source_sha256,
                        missing_claim=missing_claim,
                        recovery_round=context.recovery_round,
                        parent_completeness_input_sha256=(
                            context.parent_completeness_input_sha256
                        ),
                    )
                ),
            }
        )
    return _RecoveryReplay(
        recovered=canonicalize_bound_claim_inventory(recovered),
        excluded=canonicalize_bound_claim_inventory(excluded),
        unresolved=canonicalize_bound_claim_inventory(unresolved),
        signatures=tuple(signatures),
    )


def _take_recovery_attempt(
    *,
    attempts: list[Mapping[str, object]],
    missing_claim: BoundClaimInventoryItem,
    context: _RecoveryContext,
) -> _RecoveryEvidence:
    input_sha256 = claim_inventory_batch_input_sha256((missing_claim,))
    matches: list[Mapping[str, object]] = []
    for attempt in attempts:
        if (
            attempt.get("input_sha256") != input_sha256
            or attempt.get("semantic_unit_id") != missing_claim.inventory_id
        ):
            continue
        invocation_id = _text(attempt.get("invocation_id"), "recovery invocation_id")
        base_prompt = build_missing_claim_recovery_prompt(
            chunk=context.chunk,
            document_fingerprint=context.prompt.source_sha256,
            missing_claim=missing_claim,
            recovery_round=context.recovery_round,
            parent_completeness_input_sha256=(
                context.parent_completeness_input_sha256
            ),
        )
        provider_prompt = bind_prompt_to_invocation(
            prompt=base_prompt,
            invocation_id=invocation_id,
            source_sha256=context.prompt.source_sha256,
            input_sha256=input_sha256,
            evidence_unit_sha256=context.prompt.evidence_unit_sha256,
            output_schema_sha256=context.prompt.recovery_schema_sha256,
        )
        if attempt.get("prompt_sha256") == _sha256_text(provider_prompt):
            matches.append(attempt)
    if len(matches) != 1:
        raise ValueError("TG-04 missing descriptor lacks one canonical recovery")
    attempt = matches[0]
    if attempt.get("validation_outcome") != "accepted":
        raise ValueError("TG-04 recovery route contains invalid agent output")
    if attempt.get("output_schema_identity") != context.prompt.recovery_schema_identity:
        raise ValueError("TG-04 recovery schema differs from production schema")
    decision = MissingClaimRecoveryDecision.model_validate(
        _object(attempt.get("raw_model_payload"), "recovery raw payload")
    )
    attempts.remove(attempt)
    return _RecoveryEvidence(attempt=attempt, decision=decision)


def _validate_inventory_prompt(
    *,
    attempt: Mapping[str, object],
    chunk: RelationExtractionTextChunk,
    context: _PromptContext,
    zero_retry: bool,
    schema_retry: bool,
) -> None:
    if attempt.get("output_schema_identity") != context.output_schema_identity:
        raise ValueError("TG-04 inventory output schema differs from production schema")
    invocation_id = _text(attempt.get("invocation_id"), "inventory invocation_id")
    base_prompt = build_claim_inventory_prompt(
        chunk=chunk,
        total_chunks=context.total_chunks,
        document_fingerprint=context.source_sha256,
        zero_retry=zero_retry,
        schema_retry=schema_retry,
    )
    expected_prompt = base_prompt
    if attempt.get("validation_outcome") != "intentionally_skipped":
        expected_prompt = bind_prompt_to_invocation(
            prompt=base_prompt,
            invocation_id=invocation_id,
            source_sha256=context.source_sha256,
            input_sha256=chunk.sha256,
            evidence_unit_sha256=context.evidence_unit_sha256,
            output_schema_sha256=context.output_schema_sha256,
        )
    if attempt.get("prompt_sha256") != _sha256_text(expected_prompt):
        raise ValueError("TG-04 inventory prompt differs from frozen production prompt")


def _round_trace(trace: _RoundTraceInput) -> dict[str, object]:
    return {
        "chunk_index": trace.chunk_index,
        "recovery_round": trace.recovery_round,
        "parent_completeness_input_sha256": trace.parent_input_sha256,
        "input_inventory_ids": list(trace.input_inventory_ids),
        "missing_descriptor_ids": list(_inventory_ids(trace.missing_claims)),
        "decisions": [
            {
                "inventory_id": decision.get("inventory_id"),
                "disposition": decision.get("decision"),
            }
            for decision in trace.decisions
        ],
        "output_inventory_ids": list(_inventory_ids(trace.output_inventory)),
        "excluded_inventory_ids": list(_inventory_ids(trace.excluded_inventory)),
    }


def _require_no_unused_evidence(state: _ReplayState) -> None:
    if state.completeness_attempts:
        raise ValueError("TG-04 report contains unbound completeness attempts")
    if state.completeness_rejection_events:
        raise ValueError("TG-04 report contains unbound completeness rejections")
    if state.recovery_attempts:
        raise ValueError("TG-04 report contains an orphan recovery attempt")


def _merge_accepted_inventory(
    *,
    accepted_inventory: dict[str, str],
    claims: Sequence[BoundClaimInventoryItem],
) -> None:
    for claim in claims:
        if claim.inventory_id in accepted_inventory:
            raise ValueError("TG-04 accepted inventory identity repeats across chunks")
        accepted_inventory[claim.inventory_id] = _canonical_json(
            claim.item.model_dump(mode="json")
        )


def _adjudicated_ids(
    inventory: tuple[BoundClaimInventoryItem, ...],
    excluded: tuple[BoundClaimInventoryItem, ...],
) -> frozenset[str]:
    return frozenset(_inventory_ids(inventory)) | frozenset(_inventory_ids(excluded))


def _inventory_ids(
    inventory: tuple[BoundClaimInventoryItem, ...],
) -> tuple[str, ...]:
    return tuple(
        claim.inventory_id for claim in canonicalize_bound_claim_inventory(inventory)
    )


def _raw_claim_payloads(attempt: Mapping[str, object]) -> set[str]:
    if attempt.get("validation_outcome") == "intentionally_skipped":
        return set()
    payload = _object(attempt.get("raw_model_payload"), "raw model payload")
    return {
        _canonical_json(ClaimInventoryItem.model_validate(item).model_dump(mode="json"))
        for item in _sequence(payload.get("claims"), "raw inventory claims")
    }


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise TypeError(f"{label} must be a sequence")
    return value


def _object(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return cast("Mapping[str, object]", value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be nonempty text")
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _canonical_sha256(value: object) -> str:
    return _sha256_text(_canonical_json(value))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "InventoryWorkflowInput",
    "InventoryWorkflowReplay",
    "replay_inventory_workflow",
]
