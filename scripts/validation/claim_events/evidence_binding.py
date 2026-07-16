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
)
from artana_evidence_api.document_extraction_support.claim_frames import (
    BoundClaimInventoryItem,
    ClaimInventoryCompletenessReview,
    ClaimInventoryItem,
    bind_claim_inventory,
    claim_inventory_identity,
    coalesce_long_sentence_chunks,
)
from artana_evidence_api.document_extraction_support.full_text_chunking import (
    RelationExtractionTextChunk,
    build_relation_extraction_text_chunks,
)
from artana_evidence_api.document_extraction_support.llm_extraction.claim_inventory import (
    build_claim_inventory_prompt,
    build_inventory_completeness_prompt,
)
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    bind_prompt_to_invocation,
    output_schema_json_sha256,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    llm_extraction_document_fingerprint,
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


@dataclass(frozen=True, slots=True)
class _PromptContext:
    total_chunks: int
    source_sha256: str
    evidence_unit_sha256: str
    output_schema_identity: str
    output_schema_sha256: str
    completeness_schema_identity: str
    completeness_schema_sha256: str


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


@dataclass(frozen=True, slots=True)
class _PredictionValidationContext:
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
    return tuple(collected.expectations), topology


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
        if outcome not in {"accepted", "intentionally_skipped"}:
            raise ValueError("TG-04 report contains invalid agent output")
        if attempt.get("source_sha256") != source_sha256:
            raise ValueError(
                "TG-04 attempt source hash differs from frozen case source"
            )
        if attempt.get("evidence_unit_sha256") != evidence_unit_sha256:
            raise ValueError("TG-04 attempt is bound to the wrong fixture case")
        _validate_attempt_record(attempt, outcome)
        if outcome == "accepted":
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
    elif outcome == "accepted" and role == "claim_inventory_completeness":
        collected.completeness_attempts.append(attempt)
    elif outcome == "accepted" and role == "claim_inventory_recovery":
        collected.recovery_attempts.append(attempt)


def _validate_inventory_workflow(
    workflow: _InventoryWorkflowInput,
) -> tuple[str, dict[str, str]]:
    if workflow.recovery_attempts:
        raise ValueError(
            "TG-04 development qualification requires complete initial inventory",
        )
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
    )
    signatures: list[dict[str, object]] = []
    accepted_inventory: dict[str, str] = {}
    unused_completeness = list(workflow.completeness_attempts)
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
        )
        zero = workflow.zero_by_input[input_sha256]
        initial_claims = _raw_claim_payloads(initial)
        expected_zero_outcome = (
            "intentionally_skipped" if initial_claims else "accepted"
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
        )
        inventory_attempt = initial if initial_claims else zero
        inventory = bind_claim_inventory(
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
        for claim in inventory:
            if claim.inventory_id in accepted_inventory:
                raise ValueError(
                    "TG-04 accepted inventory identity repeats across chunks"
                )
            accepted_inventory[claim.inventory_id] = _canonical_json(
                claim.item.model_dump(mode="json"),
            )
        _take_complete_review_attempt(
            attempts=unused_completeness,
            chunk=chunk,
            inventory=inventory,
            context=context,
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
            },
        )
    if unused_completeness:
        raise ValueError("TG-04 report contains unbound completeness attempts")
    return _canonical_sha256(signatures), accepted_inventory


def _take_complete_review_attempt(
    *,
    attempts: list[Mapping[str, object]],
    chunk: RelationExtractionTextChunk,
    inventory: tuple[BoundClaimInventoryItem, ...],
    context: _PromptContext,
) -> Mapping[str, object]:
    input_sha256 = _inventory_ids_sha256(inventory)
    matches: list[Mapping[str, object]] = []
    for attempt in attempts:
        if attempt.get("input_sha256") != input_sha256:
            continue
        invocation_id = _text(
            attempt.get("invocation_id"),
            "completeness invocation_id",
        )
        prompt = build_inventory_completeness_prompt(
            chunk=chunk,
            total_chunks=context.total_chunks,
            document_fingerprint=context.source_sha256,
            current_inventory=inventory,
            confirmation=False,
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
    review = ClaimInventoryCompletenessReview.model_validate(
        _object(attempt.get("raw_model_payload"), "completeness raw payload"),
    )
    if review.decision.value != "COMPLETE" or review.missing_claims:
        raise ValueError("TG-04 initial inventory was not independently complete")
    attempts.remove(attempt)
    return attempt


def _validate_inventory_prompt(
    *,
    attempt: Mapping[str, object],
    chunk: RelationExtractionTextChunk,
    context: _PromptContext,
    zero_retry: bool,
) -> None:
    if attempt.get("output_schema_identity") != context.output_schema_identity:
        raise ValueError("TG-04 inventory output schema differs from production schema")
    invocation_id = _text(attempt.get("invocation_id"), "inventory invocation_id")
    prompt = build_claim_inventory_prompt(
        chunk=chunk,
        total_chunks=context.total_chunks,
        document_fingerprint=context.source_sha256,
        zero_retry=zero_retry,
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
                "arguments": _agent_arguments(event.get("arguments")),
                "source_locator": event.get("source_locator"),
                "event_type": event.get("event_type"),
                "polarity": event.get("polarity"),
                "epistemic_status": event.get("epistemic_status"),
                "inventory_rationale": event.get("inventory_rationale"),
            },
        )
        source_start = _integer(event.get("source_start"), "prediction source_start")
        source_end = _integer(event.get("source_end"), "prediction source_end")
        if source_end != source_start + len(item.exact_span):
            raise ValueError("TG-04 prediction source offsets do not match exact_span")
        if context.normalized_source[source_start:source_end] != item.exact_span:
            raise ValueError("TG-04 prediction exact_span differs from frozen source")
        _validate_scored_mentions(event=event, item=item, source_start=source_start)
        inventory_id = claim_inventory_identity(
            item=item,
            source_sha256=context.source_sha256,
            source_start=source_start,
        )
        if event.get("inventory_id") != inventory_id:
            raise ValueError("TG-04 prediction inventory identity mismatch")
        if inventory_id in inventory:
            raise ValueError("TG-04 prediction repeats an inventory identity")
        inventory[inventory_id] = _canonical_json(item.model_dump(mode="json"))
    return inventory


def _validate_scored_mentions(
    *,
    event: Mapping[str, object],
    item: ClaimInventoryItem,
    source_start: int,
) -> None:
    cue = item.relation_cue_span
    if item.exact_span.count(cue) != 1:
        raise ValueError("TG-04 scored trigger is ambiguous within its source span")
    if event.get("trigger_span") != cue or event.get(
        "trigger_source_start"
    ) != source_start + item.exact_span.index(cue):
        raise ValueError("TG-04 scored trigger differs from provider-bound inventory")
    scored_arguments = _sequence(event.get("arguments"), "prediction arguments")
    if len(scored_arguments) != len(item.arguments):
        raise ValueError("TG-04 scored argument count differs from inventory")
    for scored, argument in zip(scored_arguments, item.arguments, strict=True):
        scored_argument = _object(scored, "prediction argument")
        if item.exact_span.count(argument.exact_span) != 1:
            raise ValueError(
                "TG-04 scored argument is ambiguous within its source span"
            )
        expected_start = source_start + item.exact_span.index(argument.exact_span)
        if scored_argument.get("source_start") != expected_start:
            raise ValueError("TG-04 scored argument offset differs from inventory")


def _validate_attempt_record(attempt: Mapping[str, object], outcome: object) -> None:
    role = attempt.get("attempt_role")
    expected_topology = {
        "claim_inventory": ("claim_inventory", None),
        "zero_candidate_retry": ("claim_inventory", "zero_candidate_retry"),
        "claim_inventory_completeness": ("claim_inventory_completeness", None),
        "claim_inventory_recovery": ("claim_inventory_recovery", None),
    }
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
    if outcome == "accepted":
        if not isinstance(raw_payload, Mapping):
            raise ValueError("TG-04 accepted attempt lacks a raw payload")
        if payload_sha256 != _sha256_text(_canonical_json(raw_payload)):
            raise ValueError(
                "TG-04 raw payload hash differs from provider-bound payload"
            )
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


def _raw_claim_payloads(attempt: Mapping[str, object]) -> set[str]:
    if attempt.get("validation_outcome") == "intentionally_skipped":
        return set()
    payload = _object(attempt.get("raw_model_payload"), "raw model payload")
    return {
        _canonical_json(ClaimInventoryItem.model_validate(item).model_dump(mode="json"))
        for item in _sequence(payload.get("claims"), "raw inventory claims")
    }


def _agent_arguments(value: object) -> list[dict[str, object]]:
    return [
        {
            key: argument.get(key)
            for key in ("role", "event_role", "exact_span", "role_rationale")
        }
        for item in _sequence(value, "prediction arguments")
        if (argument := _object(item, "prediction argument"))
    ]


def _inventory_ids_sha256(inventory: Sequence[BoundClaimInventoryItem]) -> str:
    return _sha256_text(
        json.dumps(
            [claim.inventory_id for claim in inventory],
            separators=(",", ":"),
            ensure_ascii=True,
        ),
    )


def _insert_unique_attempt(
    attempts: dict[str, Mapping[str, object]],
    attempt: Mapping[str, object],
) -> None:
    input_sha256 = _text(attempt.get("input_sha256"), "inventory input_sha256")
    if input_sha256 in attempts:
        raise ValueError("TG-04 source chunk has duplicate inventory attempt topology")
    attempts[input_sha256] = attempt


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


__all__ = ["EvidenceCaseContract", "bind_case_evidence"]
