"""Bind TG-04 scored inventory events to source and provider-audited outputs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

from artana_evidence_api.document_extraction import normalize_text_document
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
    bind_claim_inventory_item_at_source,
    bind_claim_inventory_items,
    bind_inventory_completeness_review,
    claim_inventory_batch_input_sha256,
    coalesce_long_sentence_chunks,
    merge_bound_claim_inventories,
    merge_claim_inventory_binding_rejections,
    partition_bound_claim_inventory,
)
from artana_evidence_api.document_extraction_support.full_text_chunking import (
    RelationExtractionTextChunk,
    build_relation_extraction_text_chunks,
)
from artana_evidence_api.document_extraction_support.llm_extraction.claim_inventory import (
    build_claim_inventory_prompt,
    build_inventory_completeness_prompt,
    build_missing_claim_recovery_prompt,
    inventory_completeness_input_sha256,
)
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    bind_prompt_to_invocation,
    output_schema_json_sha256,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    llm_extraction_document_fingerprint,
)
from pydantic import ValidationError

from scripts.validation.claim_events.binding_rejections import (
    expected_rejection_event as _expected_rejection_event,
)
from scripts.validation.claim_events.binding_rejections import (
    require_exact_rejection_events as _require_exact_rejection_events,
)
from scripts.validation.claim_events.binding_rejections import (
    validate_binding_rejection_events as _validate_binding_rejection_events,
)
from scripts.validation.claim_events.operational import (
    require_sealable_unbindable_attempts,
)
from scripts.validation.claim_events.runner import receipt_expectation_from_attempt

if TYPE_CHECKING:
    from scripts.validation.claim_frames.provider_receipts import (
        ProviderReceiptExpectation,
    )

_MAX_INVENTORY_CLAIMS_PER_CHUNK = 64


class EvidenceCaseContract(Protocol):
    @property
    def case_id(self) -> str: ...

    @property
    def source_text(self) -> str: ...

    @property
    def control_status(self) -> object: ...


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


@dataclass(slots=True)
class _CollectedAttempts:
    expectations: list[ProviderReceiptExpectation]
    completeness_attempts: list[Mapping[str, object]]
    recovery_attempts: list[Mapping[str, object]]
    initial_by_input: dict[str, Mapping[str, object]]
    zero_by_input: dict[str, Mapping[str, object]]


@dataclass(frozen=True, slots=True)
class _InventoryWorkflowInput:
    chunks: Sequence[RelationExtractionTextChunk]
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
class _PredictionValidationContext:
    normalized_source: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class _RecoveryDecisionEvidence:
    attempt: Mapping[str, object]
    decision: MissingClaimRecoveryDecision


@dataclass(frozen=True, slots=True)
class _CompletenessReviewSelection:
    chunk: RelationExtractionTextChunk
    inventory: tuple[BoundClaimInventoryItem, ...]
    excluded_inventory: tuple[BoundClaimInventoryItem, ...]
    binding_rejections: tuple[ClaimInventoryBindingRejection, ...]
    confirmation: bool


@dataclass(frozen=True, slots=True)
class _UnbindableAttemptContext:
    case_id: str
    model_id: str
    source_sha256: str
    evidence_unit_sha256: str
    chunks_by_sha: Mapping[str, RelationExtractionTextChunk]
    prompt_context: _PromptContext


def bind_case_evidence(
    *,
    case: EvidenceCaseContract,
    prediction: Mapping[str, object],
    case_record: Mapping[str, object],
    model_id: str,
) -> tuple[tuple[ProviderReceiptExpectation, ...], str]:
    """Validate one scored case against canonical prompts and raw agent payloads."""

    if _text(case_record.get("case_id"), "case evidence case_id") != case.case_id:
        raise ValueError("TG-04 case evidence is bound to the wrong fixture case")
    diagnostics = _object(case_record.get("diagnostics"), "diagnostics")
    if diagnostics.get("fallback_output_used") is True:
        raise ValueError("TG-04 case used fallback output")
    if diagnostics.get("claim_extraction_routing_status") != "complete":
        raise ValueError("TG-04 case did not complete semantic inventory routing")

    normalized_source = normalize_text_document(case.source_text)
    source_sha256 = llm_extraction_document_fingerprint(normalized_source)
    evidence_unit_sha256 = _sha256_text(case.case_id)
    chunks = coalesce_long_sentence_chunks(
        normalized_text=normalized_source,
        chunks=build_relation_extraction_text_chunks(normalized_source),
    )
    attempts = tuple(
        _object(item, "attempt")
        for item in _sequence(case_record.get("attempts"), "attempts")
    )
    reported_rejection_events = tuple(
        _object(item, "inventory binding rejection event")
        for item in _sequence(
            diagnostics.get("inventory_binding_rejections", []),
            "inventory binding rejections",
        )
    )
    if diagnostics.get("inventory_binding_rejection_count", 0) != len(
        reported_rejection_events
    ):
        raise ValueError("TG-04 binding rejection count differs from evidence")
    (
        inventory_rejections_by_chunk,
        completeness_rejection_events,
    ) = _validate_binding_rejection_events(
        attempts=attempts,
        reported_events=reported_rejection_events,
        chunks=chunks,
        source_sha256=source_sha256,
    )
    collected = _collect_attempts(
        attempts=attempts,
        case_id=case.case_id,
        model_id=model_id,
        source_sha256=source_sha256,
        evidence_unit_sha256=evidence_unit_sha256,
    )

    topology, accepted_inventory = _validate_inventory_workflow(
        _InventoryWorkflowInput(
            chunks=chunks,
            initial_by_input=collected.initial_by_input,
            zero_by_input=collected.zero_by_input,
            source_sha256=source_sha256,
            evidence_unit_sha256=evidence_unit_sha256,
            completeness_attempts=collected.completeness_attempts,
            recovery_attempts=collected.recovery_attempts,
            inventory_binding_rejections_by_chunk=(inventory_rejections_by_chunk),
            completeness_binding_rejection_events=(completeness_rejection_events),
        ),
    )
    predicted_inventory = _validate_predictions(
        prediction=prediction,
        context=_PredictionValidationContext(
            normalized_source=normalized_source,
            source_sha256=source_sha256,
        ),
    )
    if predicted_inventory != accepted_inventory:
        raise ValueError(
            "TG-04 scored predictions differ from accepted inventory claims"
        )
    derived_outcome = "BOUND_OUTPUT" if accepted_inventory else "NO_OUTPUT"
    if prediction.get("execution_outcome") != derived_outcome:
        raise ValueError("TG-04 execution outcome differs from accepted inventory")
    return tuple(collected.expectations), topology


def bind_unbindable_case_evidence(
    *,
    case: EvidenceCaseContract,
    prediction: Mapping[str, object],
    case_record: Mapping[str, object],
    model_id: str,
) -> tuple[tuple[ProviderReceiptExpectation, ...], str]:
    """Bind a descriptive stress failure to raw provider-backed attempts."""

    diagnostics = _validate_unbindable_case_contract(
        case=case,
        prediction=prediction,
        case_record=case_record,
    )

    normalized_source = normalize_text_document(case.source_text)
    source_sha256 = llm_extraction_document_fingerprint(normalized_source)
    evidence_unit_sha256 = _sha256_text(case.case_id)
    chunks = coalesce_long_sentence_chunks(
        normalized_text=normalized_source,
        chunks=build_relation_extraction_text_chunks(normalized_source),
    )
    chunks_by_sha = {chunk.sha256: chunk for chunk in chunks}
    schema = build_claim_inventory_output_schema(_MAX_INVENTORY_CLAIMS_PER_CHUNK)
    context = _PromptContext(
        total_chunks=len(chunks),
        source_sha256=source_sha256,
        evidence_unit_sha256=evidence_unit_sha256,
        output_schema_identity=f"{schema.__module__}.{schema.__qualname__}",
        output_schema_sha256=output_schema_json_sha256(schema),
        completeness_schema_identity="unused",
        completeness_schema_sha256="unused",
        recovery_schema_identity="unused",
        recovery_schema_sha256="unused",
    )
    attempts = tuple(
        _object(item, "attempt")
        for item in _sequence(case_record.get("attempts"), "attempts")
    )
    if not attempts:
        raise ValueError("TG-04 unbindable output lacks audited attempts")
    reported_rejection_events = tuple(
        _object(item, "inventory binding rejection event")
        for item in _sequence(
            diagnostics.get("inventory_binding_rejections", []),
            "inventory binding rejections",
        )
    )
    if diagnostics.get("inventory_binding_rejection_count", 0) != len(
        reported_rejection_events
    ):
        raise ValueError("TG-04 binding rejection count differs from evidence")
    _, completeness_rejection_events = _validate_binding_rejection_events(
        attempts=attempts,
        reported_events=reported_rejection_events,
        chunks=chunks,
        source_sha256=source_sha256,
    )
    if completeness_rejection_events:
        raise ValueError("TG-04 unbindable inventory has completeness rejections")
    require_sealable_unbindable_attempts(attempts)
    terminal_error = _text(
        diagnostics.get("terminal_error_category"),
        "terminal_error_category",
    )
    if attempts[-1].get("error_type") != terminal_error:
        raise ValueError("TG-04 terminal error category differs from audited attempt")
    expectations, signatures, invalid_count = _collect_unbindable_attempts(
        attempts=attempts,
        context=_UnbindableAttemptContext(
            case_id=case.case_id,
            model_id=model_id,
            source_sha256=source_sha256,
            evidence_unit_sha256=evidence_unit_sha256,
            chunks_by_sha=chunks_by_sha,
            prompt_context=context,
        ),
    )
    if invalid_count == 0:
        raise ValueError("TG-04 unbindable output lacks a terminal invalid attempt")
    if not expectations:
        raise ValueError("TG-04 unbindable output lacks provider-bound attempts")
    return tuple(expectations), _canonical_sha256(signatures)


def _validate_unbindable_case_contract(
    *,
    case: EvidenceCaseContract,
    prediction: Mapping[str, object],
    case_record: Mapping[str, object],
) -> Mapping[str, object]:
    if str(case.control_status) != "REPRESENTABILITY_STRESS":
        raise ValueError("TG-04 qualification cases cannot be unbindable")
    if prediction.get("execution_outcome") != "UNBINDABLE_OUTPUT":
        raise ValueError("TG-04 unbindable evidence has the wrong outcome")
    if _sequence(prediction.get("events"), "prediction events"):
        raise ValueError("TG-04 unbindable output cannot contain scored events")
    if prediction.get("abstained") is not True:
        raise ValueError("TG-04 unbindable output must abstain")
    if _text(case_record.get("case_id"), "case evidence case_id") != case.case_id:
        raise ValueError("TG-04 case evidence is bound to the wrong fixture case")
    diagnostics = _object(case_record.get("diagnostics"), "diagnostics")
    if diagnostics.get("fallback_output_used") is True:
        raise ValueError("TG-04 case used fallback output")
    if diagnostics.get("claim_extraction_routing_status") != "unbound":
        raise ValueError("TG-04 unbindable evidence must be routed as unbound")
    return diagnostics


def _collect_unbindable_attempts(
    *,
    attempts: Sequence[Mapping[str, object]],
    context: _UnbindableAttemptContext,
) -> tuple[
    list[ProviderReceiptExpectation],
    list[dict[str, object]],
    int,
]:
    expectations: list[ProviderReceiptExpectation] = []
    signatures: list[dict[str, object]] = []
    invalid_count = 0
    for attempt in attempts:
        outcome = attempt.get("validation_outcome")
        if outcome not in {
            "accepted",
            "schema_invalid",
            "semantic_invalid",
            "intentionally_skipped",
        }:
            raise ValueError("TG-04 unbindable output has a non-semantic failure")
        if attempt.get("source_sha256") != context.source_sha256:
            raise ValueError("TG-04 attempt source hash differs from frozen source")
        if attempt.get("evidence_unit_sha256") != context.evidence_unit_sha256:
            raise ValueError("TG-04 attempt is bound to the wrong fixture case")
        _validate_attempt_record(attempt, outcome)
        if outcome != "intentionally_skipped":
            expectations.append(
                receipt_expectation_from_attempt(
                    case_id=context.case_id,
                    report_model_id=context.model_id,
                    record=dict(attempt),
                ),
            )
        invalid_count += int(outcome in {"schema_invalid", "semantic_invalid"})
        if attempt.get("attempt_role") in {
            "claim_inventory",
            "zero_candidate_retry",
            "schema_retry",
        }:
            input_sha256 = _text(attempt.get("input_sha256"), "input_sha256")
            chunk = context.chunks_by_sha.get(input_sha256)
            if chunk is None:
                raise ValueError("TG-04 inventory attempt targets an unknown chunk")
            _validate_reported_inventory_outcome(
                attempt=attempt,
                chunk=chunk,
                source_sha256=context.source_sha256,
            )
            role = attempt.get("attempt_role")
            _validate_inventory_prompt(
                attempt=attempt,
                chunk=chunk,
                context=context.prompt_context,
                zero_retry=(
                    role == "zero_candidate_retry"
                    or attempt.get("retry_context") == "zero_candidate_retry"
                ),
                schema_retry=role == "schema_retry",
            )
        signatures.append(
            {
                "attempt_role": attempt.get("attempt_role"),
                "pass_role": attempt.get("pass_role"),
                "retry_context": attempt.get("retry_context"),
                "input_sha256": attempt.get("input_sha256"),
                "prompt_sha256": attempt.get("prompt_sha256"),
                "output_schema_identity": attempt.get("output_schema_identity"),
            },
        )
    return expectations, signatures, invalid_count


def _validate_reported_inventory_outcome(
    *,
    attempt: Mapping[str, object],
    chunk: RelationExtractionTextChunk,
    source_sha256: str,
) -> None:
    reported = attempt.get("validation_outcome")
    if reported == "intentionally_skipped":
        return
    payload = _object(attempt.get("raw_model_payload"), "raw model payload")
    schema = build_claim_inventory_output_schema(_MAX_INVENTORY_CLAIMS_PER_CHUNK)
    try:
        schema.model_validate(payload)
    except ValidationError:
        derived = "schema_invalid"
    else:
        claims = tuple(
            ClaimInventoryItem.model_validate(item)
            for item in _sequence(payload.get("claims"), "raw inventory claims")
        )
        result = bind_claim_inventory_items(
            claims,
            source_text=chunk.text,
            source_sha256=source_sha256,
            chunk_index=chunk.index,
            source_start_offset=chunk.start_char,
        )
        derived = (
            "semantic_invalid"
            if not result.accepted and result.rejected
            else "accepted"
        )
    if reported != derived:
        raise ValueError("TG-04 reported validation outcome differs from replay")
    expected_error_types = {
        "accepted": {None},
        "schema_invalid": {"StructuredModelSchemaError", "ValidationError"},
        "semantic_invalid": {
            "StructuredModelSemanticError",
            "ClaimInventoryItemsRejectedError",
        },
    }[derived]
    if attempt.get("error_type") not in expected_error_types:
        raise ValueError("TG-04 reported error type differs from validation replay")


def _collect_attempts(
    *,
    attempts: Sequence[Mapping[str, object]],
    case_id: str,
    model_id: str,
    source_sha256: str,
    evidence_unit_sha256: str,
) -> _CollectedAttempts:
    collected = _CollectedAttempts([], [], [], {}, {})
    for attempt in attempts:
        outcome = attempt.get("validation_outcome")
        if outcome not in {
            "accepted",
            "schema_invalid",
            "semantic_invalid",
            "intentionally_skipped",
        }:
            raise ValueError("TG-04 report contains invalid agent output")
        if attempt.get("source_sha256") != source_sha256:
            raise ValueError(
                "TG-04 attempt source hash differs from frozen case source"
            )
        if attempt.get("evidence_unit_sha256") != evidence_unit_sha256:
            raise ValueError("TG-04 attempt is bound to the wrong fixture case")
        _validate_attempt_record(attempt, outcome)
        if outcome != "intentionally_skipped":
            collected.expectations.append(
                receipt_expectation_from_attempt(
                    case_id=case_id,
                    report_model_id=model_id,
                    record=dict(attempt),
                ),
            )
        _collect_attempt_by_role(collected, attempt, outcome)
    return collected


def _collect_attempt_by_role(
    collected: _CollectedAttempts,
    attempt: Mapping[str, object],
    outcome: object,
) -> None:
    role = attempt.get("attempt_role")
    if role == "claim_inventory":
        _insert_unique_attempt(collected.initial_by_input, attempt)
    elif role == "zero_candidate_retry":
        _insert_unique_attempt(collected.zero_by_input, attempt)
    elif role == "schema_retry":
        if outcome == "intentionally_skipped":
            return
        if attempt.get("pass_role") == "claim_inventory":
            target = (
                collected.zero_by_input
                if attempt.get("retry_context") == "zero_candidate_retry"
                else collected.initial_by_input
            )
            _replace_invalid_attempt(target, attempt)
        elif outcome == "accepted" and attempt.get("pass_role") == (
            "claim_inventory_completeness"
        ):
            collected.completeness_attempts.append(attempt)
        elif outcome == "accepted" and attempt.get("pass_role") == (
            "claim_inventory_recovery"
        ):
            collected.recovery_attempts.append(attempt)
    elif outcome == "accepted" and role == "claim_inventory_completeness":
        collected.completeness_attempts.append(attempt)
    elif outcome == "accepted" and role == "claim_inventory_recovery":
        collected.recovery_attempts.append(attempt)


def _validate_inventory_workflow(
    workflow: _InventoryWorkflowInput,
) -> tuple[str, dict[str, str]]:
    expected_inputs = {chunk.sha256 for chunk in workflow.chunks}
    if (
        set(workflow.initial_by_input) != expected_inputs
        or set(workflow.zero_by_input) != expected_inputs
    ):
        raise ValueError("TG-04 inventory attempts do not cover every source chunk")
    output_schema = build_claim_inventory_output_schema(
        _MAX_INVENTORY_CLAIMS_PER_CHUNK,
    )
    output_schema_identity = f"{output_schema.__module__}.{output_schema.__qualname__}"
    completeness_schema = build_claim_inventory_completeness_output_schema()
    recovery_schema = build_missing_claim_recovery_output_schema()
    context = _PromptContext(
        total_chunks=len(workflow.chunks),
        source_sha256=workflow.source_sha256,
        evidence_unit_sha256=workflow.evidence_unit_sha256,
        output_schema_identity=output_schema_identity,
        output_schema_sha256=output_schema_json_sha256(output_schema),
        completeness_schema_identity=(
            f"{completeness_schema.__module__}.{completeness_schema.__qualname__}"
        ),
        completeness_schema_sha256=output_schema_json_sha256(completeness_schema),
        recovery_schema_identity=(
            f"{recovery_schema.__module__}.{recovery_schema.__qualname__}"
        ),
        recovery_schema_sha256=output_schema_json_sha256(recovery_schema),
    )
    signatures: list[dict[str, object]] = []
    accepted_inventory: dict[str, str] = {}
    unused_completeness = list(workflow.completeness_attempts)
    unused_recovery = list(workflow.recovery_attempts)
    unused_completeness_rejections = list(
        workflow.completeness_binding_rejection_events
    )
    for chunk in workflow.chunks:
        input_sha256 = chunk.sha256
        initial = workflow.initial_by_input[input_sha256]
        if initial.get("validation_outcome") != "accepted":
            raise ValueError("TG-04 primary inventory call must be accepted")
        _validate_inventory_prompt(
            attempt=initial,
            chunk=chunk,
            context=context,
            zero_retry=False,
            schema_retry=initial.get("attempt_role") == "schema_retry",
        )
        zero = workflow.zero_by_input[input_sha256]
        initial_claims = _raw_claim_payloads(initial)
        prompt_rejections = workflow.inventory_binding_rejections_by_chunk.get(
            chunk.index,
            (),
        )
        expected_zero_outcome = (
            "intentionally_skipped"
            if initial_claims or prompt_rejections
            else "accepted"
        )
        if zero.get("validation_outcome") != expected_zero_outcome:
            raise ValueError(
                "TG-04 zero-inventory retry topology differs from agent output"
            )
        _validate_inventory_prompt(
            attempt=zero,
            chunk=chunk,
            context=context,
            zero_retry=True,
            schema_retry=zero.get("attempt_role") == "schema_retry",
        )
        inventory_attempt = _select_inventory_attempt(initial=initial, zero=zero)
        binding_result = bind_claim_inventory_items(
            tuple(
                ClaimInventoryItem.model_validate(item)
                for item in _sequence(
                    _object(
                        inventory_attempt.get("raw_model_payload"),
                        "raw model payload",
                    ).get("claims"),
                    "raw inventory claims",
                )
            ),
            source_text=chunk.text,
            source_sha256=workflow.source_sha256,
            chunk_index=chunk.index,
            source_start_offset=chunk.start_char,
        )
        inventory = binding_result.accepted
        review = _take_completeness_review_attempt(
            attempts=unused_completeness,
            selection=_CompletenessReviewSelection(
                chunk=chunk,
                inventory=inventory,
                excluded_inventory=(),
                binding_rejections=prompt_rejections,
                confirmation=False,
            ),
            reported_rejection_events=unused_completeness_rejections,
            context=context,
        )
        recovered, excluded, recovery_signatures = _validate_recovery_decisions(
            review=review,
            attempts=unused_recovery,
            chunk=chunk,
            context=context,
        )
        combined_inventory = merge_bound_claim_inventories(inventory, recovered)
        if review.decision is InventoryCompletenessDecision.INCOMPLETE:
            confirmation_rejections = merge_claim_inventory_binding_rejections(
                prompt_rejections,
                review.binding_rejections,
            )
            confirmation = _take_completeness_review_attempt(
                attempts=unused_completeness,
                selection=_CompletenessReviewSelection(
                    chunk=chunk,
                    inventory=combined_inventory,
                    excluded_inventory=excluded,
                    binding_rejections=confirmation_rejections,
                    confirmation=True,
                ),
                reported_rejection_events=unused_completeness_rejections,
                context=context,
            )
            if (
                confirmation.decision is not InventoryCompletenessDecision.COMPLETE
                or confirmation.missing_claims
                or confirmation.binding_rejections
            ):
                raise ValueError("TG-04 recovered inventory was not confirmed complete")
        relation_inventory, _non_relation_inventory = partition_bound_claim_inventory(
            combined_inventory
        )
        _merge_accepted_inventory(
            accepted_inventory=accepted_inventory,
            claims=relation_inventory,
        )
        signatures.append(
            {
                "input_sha256": input_sha256,
                "initial_prompt_sha256": _sha256_text(
                    build_claim_inventory_prompt(
                        chunk=chunk,
                        total_chunks=context.total_chunks,
                        document_fingerprint=context.source_sha256,
                    ),
                ),
                "zero_prompt_sha256": _sha256_text(
                    build_claim_inventory_prompt(
                        chunk=chunk,
                        total_chunks=context.total_chunks,
                        document_fingerprint=context.source_sha256,
                        zero_retry=True,
                    ),
                ),
                "output_schema_identity": output_schema_identity,
                "completeness_output_schema_identity": (
                    context.completeness_schema_identity
                ),
                "binding_rejection_ids": [
                    rejection.rejection_id for rejection in prompt_rejections
                ],
                "recovery": recovery_signatures,
                "excluded_inventory_ids": [claim.inventory_id for claim in excluded],
            },
        )
    if unused_completeness:
        raise ValueError("TG-04 report contains unbound completeness attempts")
    if unused_completeness_rejections:
        raise ValueError("TG-04 report contains unbound completeness rejections")
    if unused_recovery:
        raise ValueError("TG-04 report contains an orphan recovery attempt")
    return _canonical_sha256(signatures), accepted_inventory


def _take_completeness_review_attempt(
    *,
    attempts: list[Mapping[str, object]],
    selection: _CompletenessReviewSelection,
    reported_rejection_events: list[Mapping[str, object]],
    context: _PromptContext,
) -> BoundInventoryCompletenessReview:
    input_sha256 = inventory_completeness_input_sha256(
        selection.inventory,
        selection.excluded_inventory,
        selection.binding_rejections,
    )
    matches: list[Mapping[str, object]] = []
    for attempt in attempts:
        if attempt.get("input_sha256") != input_sha256:
            continue
        invocation_id = _text(
            attempt.get("invocation_id"),
            "completeness invocation_id",
        )
        prompt = build_inventory_completeness_prompt(
            chunk=selection.chunk,
            total_chunks=context.total_chunks,
            document_fingerprint=context.source_sha256,
            current_inventory=selection.inventory,
            excluded_inventory=selection.excluded_inventory,
            binding_rejections=selection.binding_rejections,
            confirmation=selection.confirmation,
            schema_retry=attempt.get("attempt_role") == "schema_retry",
        )
        provider_prompt = bind_prompt_to_invocation(
            prompt=prompt,
            invocation_id=invocation_id,
            source_sha256=context.source_sha256,
            input_sha256=input_sha256,
            evidence_unit_sha256=context.evidence_unit_sha256,
            output_schema_sha256=context.completeness_schema_sha256,
        )
        if attempt.get("prompt_sha256") == _sha256_text(provider_prompt):
            matches.append(attempt)
    if len(matches) != 1:
        raise ValueError("TG-04 source chunk lacks one canonical completeness review")
    attempt = matches[0]
    if attempt.get("output_schema_identity") != context.completeness_schema_identity:
        raise ValueError("TG-04 completeness schema differs from production schema")
    raw_review = ClaimInventoryCompletenessReview.model_validate(
        _object(attempt.get("raw_model_payload"), "completeness raw payload"),
    )
    review = bind_inventory_completeness_review(
        raw_review,
        source_text=selection.chunk.text,
        source_sha256=context.source_sha256,
        chunk_index=selection.chunk.index,
        source_start_offset=selection.chunk.start_char,
        current_inventory=selection.inventory,
        excluded_inventory=selection.excluded_inventory,
    )
    invocation_id = _text(
        attempt.get("invocation_id"),
        "completeness invocation_id",
    )
    matching_rejection_events = tuple(
        event
        for event in reported_rejection_events
        if _object(event.get("attempt_lineage"), "attempt lineage").get("invocation_id")
        == invocation_id
    )
    _require_exact_rejection_events(
        attempt=attempt,
        phase="COMPLETENESS_REVIEW",
        expected_rejections=review.binding_rejections,
        reported_events=matching_rejection_events,
    )
    for event in matching_rejection_events:
        reported_rejection_events.remove(event)
    attempts.remove(attempt)
    return review


def _validate_recovery_decisions(
    *,
    review: BoundInventoryCompletenessReview,
    attempts: list[Mapping[str, object]],
    chunk: RelationExtractionTextChunk,
    context: _PromptContext,
) -> tuple[
    tuple[BoundClaimInventoryItem, ...],
    tuple[BoundClaimInventoryItem, ...],
    list[dict[str, object]],
]:
    if review.decision is InventoryCompletenessDecision.COMPLETE:
        if review.missing_claims or review.binding_rejections:
            raise ValueError("TG-04 complete review contains unresolved descriptors")
        return (), (), []

    recovered: tuple[BoundClaimInventoryItem, ...] = ()
    excluded: tuple[BoundClaimInventoryItem, ...] = ()
    signatures: list[dict[str, object]] = []
    for missing_claim in review.missing_claims:
        evidence = _take_recovery_attempt(
            attempts=attempts,
            chunk=chunk,
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
            raise ValueError(
                "TG-04 complete routing cannot contain recovery abstention"
            )
        signatures.append(
            {
                "inventory_id": missing_claim.inventory_id,
                "decision": decision.value,
                "invocation_id": evidence.attempt.get("invocation_id"),
                "prompt_sha256": evidence.attempt.get("prompt_sha256"),
            },
        )
    return recovered, excluded, signatures


def _take_recovery_attempt(
    *,
    attempts: list[Mapping[str, object]],
    chunk: RelationExtractionTextChunk,
    missing_claim: BoundClaimInventoryItem,
    context: _PromptContext,
) -> _RecoveryDecisionEvidence:
    input_sha256 = claim_inventory_batch_input_sha256((missing_claim,))
    matches: list[Mapping[str, object]] = []
    for attempt in attempts:
        if (
            attempt.get("input_sha256") != input_sha256
            or attempt.get("semantic_unit_id") != missing_claim.inventory_id
        ):
            continue
        invocation_id = _text(attempt.get("invocation_id"), "recovery invocation_id")
        prompt = build_missing_claim_recovery_prompt(
            chunk=chunk,
            document_fingerprint=context.source_sha256,
            missing_claim=missing_claim,
        )
        provider_prompt = bind_prompt_to_invocation(
            prompt=prompt,
            invocation_id=invocation_id,
            source_sha256=context.source_sha256,
            input_sha256=input_sha256,
            evidence_unit_sha256=context.evidence_unit_sha256,
            output_schema_sha256=context.recovery_schema_sha256,
        )
        if attempt.get("prompt_sha256") == _sha256_text(provider_prompt):
            matches.append(attempt)
    if len(matches) != 1:
        raise ValueError("TG-04 missing descriptor lacks one canonical recovery")
    attempt = matches[0]
    if attempt.get("validation_outcome") != "accepted":
        raise ValueError("TG-04 complete routing contains invalid recovery output")
    if attempt.get("output_schema_identity") != context.recovery_schema_identity:
        raise ValueError("TG-04 recovery schema differs from production schema")
    decision = MissingClaimRecoveryDecision.model_validate(
        _object(attempt.get("raw_model_payload"), "recovery raw payload"),
    )
    attempts.remove(attempt)
    return _RecoveryDecisionEvidence(attempt=attempt, decision=decision)


def _merge_accepted_inventory(
    *,
    accepted_inventory: dict[str, str],
    claims: Sequence[BoundClaimInventoryItem],
) -> None:
    for claim in claims:
        if claim.inventory_id in accepted_inventory:
            raise ValueError("TG-04 accepted inventory identity repeats across chunks")
        accepted_inventory[claim.inventory_id] = _canonical_json(
            claim.item.model_dump(mode="json"),
        )


def _validate_inventory_prompt(
    *,
    attempt: Mapping[str, object],
    chunk: RelationExtractionTextChunk,
    context: _PromptContext,
    zero_retry: bool,
    schema_retry: bool = False,
) -> None:
    if attempt.get("output_schema_identity") != context.output_schema_identity:
        raise ValueError("TG-04 inventory output schema differs from production schema")
    invocation_id = _text(attempt.get("invocation_id"), "inventory invocation_id")
    prompt = build_claim_inventory_prompt(
        chunk=chunk,
        total_chunks=context.total_chunks,
        document_fingerprint=context.source_sha256,
        zero_retry=zero_retry,
        schema_retry=schema_retry,
    )
    provider_prompt = bind_prompt_to_invocation(
        prompt=prompt,
        invocation_id=invocation_id,
        source_sha256=context.source_sha256,
        input_sha256=chunk.sha256,
        evidence_unit_sha256=context.evidence_unit_sha256,
        output_schema_sha256=context.output_schema_sha256,
    )
    if attempt.get("prompt_sha256") != _sha256_text(provider_prompt):
        raise ValueError("TG-04 inventory prompt differs from frozen production prompt")


def _validate_predictions(
    *,
    prediction: Mapping[str, object],
    context: _PredictionValidationContext,
) -> dict[str, str]:
    inventory: dict[str, str] = {}
    for raw_event in _sequence(prediction.get("events"), "prediction events"):
        event = _object(raw_event, "prediction event")
        item = ClaimInventoryItem.model_validate(
            {
                "exact_span": event.get("exact_span"),
                "relation_cue_span": event.get("relation_cue_span"),
                "relation_cue_anchor": event.get("relation_cue_anchor"),
                "arguments": _agent_arguments(event.get("arguments")),
                "source_locator": event.get("source_locator"),
                "claim_kind": event.get("claim_kind"),
                "event_type": event.get("event_type"),
                "polarity": event.get("polarity"),
                "epistemic_status": event.get("epistemic_status"),
                "inventory_rationale": event.get("inventory_rationale"),
            },
        )
        if not item.claim_kind.relation_eligible:
            raise ValueError("TG-04 prediction contains a non-relation inventory item")
        source_start = _integer(event.get("source_start"), "prediction source_start")
        source_end = _integer(event.get("source_end"), "prediction source_end")
        if source_end != source_start + len(item.exact_span):
            raise ValueError("TG-04 prediction source offsets do not match exact_span")
        if context.normalized_source[source_start:source_end] != item.exact_span:
            raise ValueError("TG-04 prediction exact_span differs from frozen source")
        bound_claim = bind_claim_inventory_item_at_source(
            item=item,
            source_text=context.normalized_source,
            source_sha256=context.source_sha256,
            chunk_index=0,
            source_start=source_start,
        )
        _validate_scored_mentions(event=event, bound_claim=bound_claim)
        inventory_id = bound_claim.inventory_id
        if event.get("inventory_id") != inventory_id:
            raise ValueError("TG-04 prediction inventory identity mismatch")
        if inventory_id in inventory:
            raise ValueError("TG-04 prediction repeats an inventory identity")
        inventory[inventory_id] = _canonical_json(item.model_dump(mode="json"))
    return inventory


def _validate_scored_mentions(
    *,
    event: Mapping[str, object],
    bound_claim: BoundClaimInventoryItem,
) -> None:
    item = bound_claim.item
    cue = item.relation_cue_span
    trigger = bound_claim.trigger_mention
    if (
        event.get("trigger_span") != cue
        or event.get("trigger_source_start") != trigger.source_start
    ):
        raise ValueError("TG-04 scored trigger differs from provider-bound inventory")
    if event.get("trigger_source_mention") != {
        "exact_span": trigger.exact_span,
        "source_start": trigger.source_start,
        "source_end": trigger.source_end,
    }:
        raise ValueError("TG-04 scored trigger mention differs from inventory")
    scored_arguments = _sequence(event.get("arguments"), "prediction arguments")
    if len(scored_arguments) != len(item.arguments):
        raise ValueError("TG-04 scored argument count differs from inventory")
    for scored, bound_argument in zip(
        scored_arguments,
        bound_claim.bound_arguments,
        strict=True,
    ):
        scored_argument = _object(scored, "prediction argument")
        mentions = bound_argument.mentions
        if (
            scored_argument.get("source_start")
            != bound_argument.primary_mention.source_start
        ):
            raise ValueError("TG-04 scored argument offset differs from inventory")
        expected_mentions = [
            {
                "exact_span": mention.exact_span,
                "source_start": mention.source_start,
                "source_end": mention.source_end,
            }
            for mention in mentions
        ]
        if scored_argument.get("source_mentions") != expected_mentions:
            raise ValueError("TG-04 scored argument mentions differ from inventory")


def _validate_attempt_record(attempt: Mapping[str, object], outcome: object) -> None:
    role = attempt.get("attempt_role")
    expected_topology = {
        "claim_inventory": ("claim_inventory", None),
        "zero_candidate_retry": ("claim_inventory", "zero_candidate_retry"),
        "claim_inventory_completeness": ("claim_inventory_completeness", None),
        "claim_inventory_recovery": ("claim_inventory_recovery", None),
    }
    if role == "schema_retry":
        _validate_schema_retry_topology(attempt)
    else:
        if role not in expected_topology:
            raise ValueError("TG-04 report contains an unexpected attempt role")
        expected_pass_role, expected_retry = expected_topology[role]
        if (
            attempt.get("pass_role") != expected_pass_role
            or attempt.get("retry_context") != expected_retry
        ):
            raise ValueError("TG-04 attempt role topology is invalid")
    raw_payload = attempt.get("raw_model_payload")
    payload_sha256 = attempt.get("payload_sha256")
    if outcome in {"accepted", "schema_invalid", "semantic_invalid"}:
        if not isinstance(raw_payload, Mapping):
            raise ValueError("TG-04 executed attempt lacks a raw payload")
        if payload_sha256 != _sha256_text(_canonical_json(raw_payload)):
            raise ValueError(
                "TG-04 raw payload hash differs from provider-bound payload"
            )
        for field in (
            "provider_response_id",
            "provider_output_sha256",
            "kernel_run_id",
        ):
            if not isinstance(attempt.get(field), str) or not attempt.get(field):
                raise ValueError("TG-04 executed attempt lacks provider custody")
        return
    if raw_payload is not None or payload_sha256 is not None:
        raise ValueError("TG-04 skipped attempt must not contain a payload")
    for field in (
        "provider_response_id",
        "provider_output_sha256",
        "kernel_run_id",
    ):
        if attempt.get(field) is not None:
            raise ValueError(
                "TG-04 skipped attempt contains provider execution evidence"
            )


def _validate_schema_retry_topology(attempt: Mapping[str, object]) -> None:
    pass_role = attempt.get("pass_role")
    retry_context = attempt.get("retry_context")
    valid = (
        pass_role == "claim_inventory"
        and retry_context in {None, "zero_candidate_retry"}
    ) or (pass_role == "claim_inventory_completeness" and retry_context is None)
    if not valid:
        raise ValueError("TG-04 schema retry topology is invalid")


def _raw_claim_payloads(attempt: Mapping[str, object]) -> set[str]:
    if attempt.get("validation_outcome") == "intentionally_skipped":
        return set()
    payload = _object(attempt.get("raw_model_payload"), "raw model payload")
    return {
        _canonical_json(ClaimInventoryItem.model_validate(item).model_dump(mode="json"))
        for item in _sequence(payload.get("claims"), "raw inventory claims")
    }


def _select_inventory_attempt(
    *,
    initial: Mapping[str, object],
    zero: Mapping[str, object],
) -> Mapping[str, object]:
    """Select the executed inventory result without parsing a skipped retry."""

    return zero if zero.get("validation_outcome") == "accepted" else initial


def _agent_arguments(value: object) -> list[dict[str, object]]:
    return [
        {
            key: argument.get(key)
            for key in (
                "role",
                "event_role",
                "exact_span",
                "mention_anchors",
                "role_rationale",
            )
        }
        for item in _sequence(value, "prediction arguments")
        if (argument := _object(item, "prediction argument"))
    ]


def _insert_unique_attempt(
    attempts: dict[str, Mapping[str, object]],
    attempt: Mapping[str, object],
) -> None:
    input_sha256 = _text(attempt.get("input_sha256"), "inventory input_sha256")
    if input_sha256 in attempts:
        raise ValueError("TG-04 source chunk has duplicate inventory attempt topology")
    attempts[input_sha256] = attempt


def _replace_invalid_attempt(
    attempts: dict[str, Mapping[str, object]],
    retry: Mapping[str, object],
) -> None:
    input_sha256 = _text(retry.get("input_sha256"), "inventory input_sha256")
    original = attempts.get(input_sha256)
    if original is None or original.get("validation_outcome") not in {
        "schema_invalid",
        "semantic_invalid",
    }:
        raise ValueError("TG-04 schema retry does not follow one invalid attempt")
    attempts[input_sha256] = retry


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


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _canonical_sha256(value: object) -> str:
    return _sha256_text(_canonical_json(value))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "EvidenceCaseContract",
    "_expected_rejection_event",
    "bind_case_evidence",
    "bind_unbindable_case_evidence",
]
