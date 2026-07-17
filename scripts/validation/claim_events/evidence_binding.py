"""Bind TG-04 scored inventory events to source and provider-audited outputs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

from artana_evidence_api.document_extraction import normalize_text_document
from artana_evidence_api.document_extraction_prompting import (
    build_claim_inventory_output_schema,
)
from artana_evidence_api.document_extraction_support.claim_frames import (
    BoundClaimInventoryItem,
    ClaimInventoryItem,
    bind_claim_inventory_item_at_source,
    bind_claim_inventory_items,
    coalesce_long_sentence_chunks,
)
from artana_evidence_api.document_extraction_support.full_text_chunking import (
    RelationExtractionTextChunk,
    build_relation_extraction_text_chunks,
)
from artana_evidence_api.document_extraction_support.llm_extraction.claim_inventory import (
    build_claim_inventory_prompt,
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
    validate_binding_rejection_events as _validate_binding_rejection_events,
)
from scripts.validation.claim_events.inventory_workflow_replay import (
    InventoryWorkflowInput,
    InventoryWorkflowReplay,
    replay_inventory_workflow,
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
class _PredictionValidationContext:
    normalized_source: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class _UnbindableAttemptContext:
    case_id: str
    model_id: str
    source_sha256: str
    evidence_unit_sha256: str
    chunks_by_sha: Mapping[str, RelationExtractionTextChunk]
    prompt_context: _PromptContext


@dataclass(frozen=True, slots=True)
class _InventoryCaseReplay:
    expectations: tuple[ProviderReceiptExpectation, ...]
    workflow: InventoryWorkflowReplay
    normalized_source: str
    source_sha256: str


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

    replay = _replay_case_inventory(
        case=case,
        case_record=case_record,
        diagnostics=diagnostics,
        model_id=model_id,
        require_complete=True,
    )
    _validate_convergence_diagnostics(diagnostics, replay.workflow)
    predicted_inventory = _validate_predictions(
        prediction=prediction,
        context=_PredictionValidationContext(
            normalized_source=replay.normalized_source,
            source_sha256=replay.source_sha256,
        ),
    )
    if predicted_inventory != replay.workflow.accepted_inventory:
        raise ValueError(
            "TG-04 scored predictions differ from accepted inventory claims"
        )
    derived_outcome = (
        "BOUND_OUTPUT" if replay.workflow.accepted_inventory else "NO_OUTPUT"
    )
    if prediction.get("execution_outcome") != derived_outcome:
        raise ValueError("TG-04 execution outcome differs from accepted inventory")
    return replay.expectations, replay.workflow.topology_sha256


def bind_semantically_incomplete_case_evidence(
    *,
    case: EvidenceCaseContract,
    prediction: Mapping[str, object],
    case_record: Mapping[str, object],
    model_id: str,
) -> tuple[tuple[ProviderReceiptExpectation, ...], str]:
    """Replay an honest bounded non-convergence with zero scored events."""

    if _text(case_record.get("case_id"), "case evidence case_id") != case.case_id:
        raise ValueError("TG-04 case evidence is bound to the wrong fixture case")
    diagnostics = _object(case_record.get("diagnostics"), "diagnostics")
    if diagnostics.get("fallback_output_used") is True:
        raise ValueError("TG-04 case used fallback output")
    if diagnostics.get("claim_extraction_routing_status") != "semantic_incomplete":
        raise ValueError("TG-04 incomplete evidence has the wrong routing status")
    if prediction.get("execution_outcome") != "SEMANTICALLY_INCOMPLETE":
        raise ValueError("TG-04 incomplete evidence has the wrong outcome")
    if _sequence(prediction.get("events"), "prediction events"):
        raise ValueError("TG-04 incomplete evidence cannot contain scored events")
    if prediction.get("abstained") is not True:
        raise ValueError("TG-04 incomplete evidence must abstain")
    replay = _replay_case_inventory(
        case=case,
        case_record=case_record,
        diagnostics=diagnostics,
        model_id=model_id,
        require_complete=False,
    )
    _validate_convergence_diagnostics(diagnostics, replay.workflow)
    return replay.expectations, replay.workflow.topology_sha256


def _replay_case_inventory(
    *,
    case: EvidenceCaseContract,
    case_record: Mapping[str, object],
    diagnostics: Mapping[str, object],
    model_id: str,
    require_complete: bool,
) -> _InventoryCaseReplay:
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
    inventory_rejections, completeness_rejections = (
        _validate_binding_rejection_events(
            attempts=attempts,
            reported_events=reported_rejection_events,
            chunks=chunks,
            source_sha256=source_sha256,
        )
    )
    collected = _collect_attempts(
        attempts=attempts,
        case_id=case.case_id,
        model_id=model_id,
        source_sha256=source_sha256,
        evidence_unit_sha256=evidence_unit_sha256,
    )
    workflow = replay_inventory_workflow(
        InventoryWorkflowInput(
            chunks=chunks,
            initial_by_input=collected.initial_by_input,
            zero_by_input=collected.zero_by_input,
            source_sha256=source_sha256,
            evidence_unit_sha256=evidence_unit_sha256,
            completeness_attempts=collected.completeness_attempts,
            recovery_attempts=collected.recovery_attempts,
            inventory_binding_rejections_by_chunk=inventory_rejections,
            completeness_binding_rejection_events=completeness_rejections,
        ),
        require_complete=require_complete,
    )
    return _InventoryCaseReplay(
        expectations=tuple(collected.expectations),
        workflow=workflow,
        normalized_source=normalized_source,
        source_sha256=source_sha256,
    )


def _validate_convergence_diagnostics(
    diagnostics: Mapping[str, object],
    replay: InventoryWorkflowReplay,
) -> None:
    if diagnostics.get("inventory_recovery_round_count") != (
        replay.recovery_round_count
    ):
        raise ValueError("TG-04 recovery-round count differs from replay")
    if diagnostics.get("inventory_convergence_stop_reasons") != list(
        replay.stop_reasons
    ):
        raise ValueError("TG-04 convergence stop reasons differ from replay")
    if diagnostics.get("inventory_convergence_round_traces") != list(
        replay.round_traces
    ):
        raise ValueError("TG-04 convergence round traces differ from replay")


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
    error_types_by_outcome: dict[str, frozenset[str | None]] = {
        "accepted": frozenset({None}),
        "schema_invalid": frozenset(
            {"StructuredModelSchemaError", "ValidationError"}
        ),
        "semantic_invalid": frozenset(
            {
            "StructuredModelSemanticError",
            "ClaimInventoryItemsRejectedError",
            }
        ),
    }
    expected_error_types = error_types_by_outcome[derived]
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
    expected_prompt = prompt
    if attempt.get("validation_outcome") != "intentionally_skipped":
        expected_prompt = bind_prompt_to_invocation(
            prompt=prompt,
            invocation_id=invocation_id,
            source_sha256=context.source_sha256,
            input_sha256=chunk.sha256,
            evidence_unit_sha256=context.evidence_unit_sha256,
            output_schema_sha256=context.output_schema_sha256,
        )
    if attempt.get("prompt_sha256") != _sha256_text(expected_prompt):
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
