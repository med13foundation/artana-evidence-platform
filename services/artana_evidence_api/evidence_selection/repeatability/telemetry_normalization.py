"""Normalize Artana terminal events into semantic model-attempt facts."""

from __future__ import annotations

import json
from typing import Protocol, cast

from artana_evidence_api.evidence_selection.semantic.attempts import (
    SemanticModelAttemptContext,
)

from .contracts import (
    SemanticAttemptStatus,
    SemanticFailureCause,
    SemanticFailureStage,
    SemanticRuntimeModelAttempt,
    SemanticTelemetryUnavailableReason,
    SemanticTerminalOutcome,
)

_SHA256_HEX_LENGTH = 64


class _TerminalEvent(Protocol):
    event_id: object
    event_hash: object
    payload: object
    run_id: object
    seq: object


class _RequestedEvent(Protocol):
    event_id: object
    event_hash: object
    payload: object
    run_id: object
    seq: object


def normalize_semantic_terminal_attempt(
    *,
    attempt: SemanticModelAttemptContext,
    requested_event: object,
    event: object,
    expected_model_id: str,
) -> SemanticRuntimeModelAttempt:
    """Join one service attempt to one matching Artana terminal event."""

    typed_event = cast("_TerminalEvent", event)
    typed_requested_event = cast("_RequestedEvent", requested_event)
    payload = typed_event.payload
    model_id = normalize_semantic_model_id(_required_string(payload, "model"))
    if model_id != expected_model_id:
        raise ValueError("runtime ledger terminal event does not match the frozen model")
    terminal_step_key = getattr(payload, "step_key", None)
    if terminal_step_key != attempt.step_key:
        raise ValueError("runtime ledger terminal event does not match the semantic step")
    if typed_event.run_id != attempt.execution_id:
        raise ValueError("runtime ledger terminal event does not match the execution")
    requested_event_id, requested_event_seq, requested_event_hash = (
        _validate_requested_event(
            attempt=attempt,
            event=typed_requested_event,
            expected_model_id=expected_model_id,
            terminal_payload=payload,
        )
    )

    terminal_outcome = cast(
        "SemanticTerminalOutcome",
        _string_value(getattr(payload, "outcome", None)),
    )
    _validate_outcome_category(payload=payload, terminal_outcome=terminal_outcome)
    status, failure_stage, failure_cause = _attempt_outcome(
        attempt=attempt,
        payload=payload,
        terminal_outcome=terminal_outcome,
    )
    prompt_tokens = _optional_int(payload, "prompt_tokens")
    completion_tokens = _optional_int(payload, "completion_tokens")
    token_reason = _token_unavailable_reason(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        schema_validation_failure=failure_stage == "output_schema_validation",
    )
    cost_usd = _optional_number(payload, "cost_usd")
    cost_reason = _cost_unavailable_reason(
        cost_usd=cost_usd,
        schema_validation_failure=failure_stage == "output_schema_validation",
    )
    event_id, event_seq, event_hash = _terminal_event_identity(typed_event)
    return SemanticRuntimeModelAttempt(
        execution_id=attempt.execution_id,
        batch_id=attempt.batch_id,
        governed_context_sha256=attempt.governed_context_sha256,
        attempt_sequence=attempt.attempt_sequence,
        batch_attempt_number=attempt.batch_attempt_number,
        source_key=attempt.source_key,
        search_id=attempt.search_id,
        record_references=attempt.record_references,
        step_key=attempt.step_key,
        status=status,
        terminal_outcome=terminal_outcome,
        model_id=model_id,
        model_cycle_id=_required_string(payload, "model_cycle_id"),
        source_model_requested_event_id=requested_event_id,
        model_requested_event_seq=requested_event_seq,
        model_requested_event_hash=requested_event_hash,
        terminal_event_id=event_id,
        terminal_event_seq=event_seq,
        terminal_event_hash=event_hash,
        failure_stage=failure_stage,
        failure_cause=failure_cause,
        error_category=_optional_string(payload, "error_category"),
        error_class=_optional_string(payload, "error_class"),
        elapsed_ms=_required_int(payload, "elapsed_ms"),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        token_usage_provenance=(
            "artana_model_terminal" if token_reason is None else "unavailable"
        ),
        token_usage_unavailable_reason=token_reason,
        cost_usage_provenance=(
            "artana_model_terminal" if cost_reason is None else "unavailable"
        ),
        cost_usage_unavailable_reason=cost_reason,
    )


def missing_semantic_terminal_attempt(
    *,
    attempt: SemanticModelAttemptContext,
    expected_model_id: str,
) -> SemanticRuntimeModelAttempt:
    """Retain an attempt whose Artana terminal event cannot be observed."""

    return SemanticRuntimeModelAttempt(
        execution_id=attempt.execution_id,
        batch_id=attempt.batch_id,
        governed_context_sha256=attempt.governed_context_sha256,
        attempt_sequence=attempt.attempt_sequence,
        batch_attempt_number=attempt.batch_attempt_number,
        source_key=attempt.source_key,
        search_id=attempt.search_id,
        record_references=attempt.record_references,
        step_key=attempt.step_key,
        status="telemetry_unavailable",
        model_id=expected_model_id,
        failure_stage="telemetry_collection",
        failure_cause="model_terminal_event_missing",
        token_usage_provenance="unavailable",
        token_usage_unavailable_reason="model_terminal_event_missing",
        cost_usage_provenance="unavailable",
        cost_usage_unavailable_reason="model_terminal_event_missing",
    )


def normalize_semantic_model_id(model_id: str) -> str:
    """Normalize supported provider/model separators for identity comparison."""

    normalized = model_id.strip()
    if ":" in normalized:
        return normalized
    if "/" in normalized:
        provider, model_name = normalized.split("/", 1)
        if provider.strip() and model_name.strip():
            return f"{provider.strip()}:{model_name.strip()}"
    return normalized


def _attempt_outcome(
    *,
    attempt: SemanticModelAttemptContext,
    payload: object,
    terminal_outcome: SemanticTerminalOutcome,
) -> tuple[
    SemanticAttemptStatus,
    SemanticFailureStage | None,
    SemanticFailureCause | None,
]:
    if attempt.local_failure is not None:
        if terminal_outcome != "completed":
            raise ValueError("local semantic rejection requires a completed terminal")
        return (
            "rejected",
            cast("SemanticFailureStage", attempt.local_failure.stage),
            cast("SemanticFailureCause", attempt.local_failure.cause),
        )
    if terminal_outcome == "completed":
        return "completed", None, None
    if terminal_outcome == "abandoned":
        return "abandoned", "runtime_execution", "abandoned"
    failure_stage, failure_cause = _classify_terminal_failure(payload)
    return "failed", failure_stage, failure_cause


def _classify_terminal_failure(
    payload: object,
) -> tuple[SemanticFailureStage, SemanticFailureCause]:
    error_class = _optional_string(payload, "error_class")
    error_category = _optional_string(payload, "error_category")
    if error_class == "ValidationError" and _is_pydantic_diagnostic(payload):
        return "output_schema_validation", "schema_contract_rejected"
    category_mapping: dict[str, tuple[SemanticFailureStage, SemanticFailureCause]] = {
        "timeout": ("provider_call", "timeout"),
        "cancelled": ("runtime_execution", "cancelled"),
        "refusal": ("provider_response", "provider_refusal"),
        "provider_4xx": ("provider_call", "provider_client_error"),
        "provider_5xx": ("provider_call", "provider_server_error"),
        "transient": ("provider_call", "provider_transient_error"),
        "permanent": ("provider_call", "provider_permanent_error"),
        "network": ("provider_call", "network_error"),
    }
    return category_mapping.get(
        error_category or "",
        ("runtime_execution", "internal_error"),
    )


def _validate_outcome_category(
    *,
    payload: object,
    terminal_outcome: SemanticTerminalOutcome,
) -> None:
    category = _optional_string(payload, "error_category")
    error_class = _optional_string(payload, "error_class")
    if terminal_outcome == "completed":
        if category is not None or error_class is not None:
            raise ValueError("completed terminal cannot declare an error")
        return
    expected_categories: dict[SemanticTerminalOutcome, str] = {
        "timeout": "timeout",
        "cancelled": "cancelled",
        "abandoned": "abandoned",
    }
    expected = expected_categories.get(terminal_outcome)
    if expected is not None and category != expected:
        raise ValueError("terminal outcome contradicts its error category")
    if terminal_outcome == "failed" and category in {
        None,
        "timeout",
        "cancelled",
        "abandoned",
    }:
        raise ValueError("failed terminal requires a consistent error category")


def _validate_requested_event(
    *,
    attempt: SemanticModelAttemptContext,
    event: _RequestedEvent,
    expected_model_id: str,
    terminal_payload: object,
) -> tuple[str, int, str]:
    event_id, event_seq, event_hash = _event_identity(
        event,
        event_name="model request",
    )
    terminal_request_id = _required_string(
        terminal_payload,
        "source_model_requested_event_id",
    )
    if event_id != terminal_request_id:
        raise ValueError("terminal does not reference the joined model request")
    if event.run_id != attempt.execution_id:
        raise ValueError("model request does not match the semantic execution")
    payload = event.payload
    requested_model = normalize_semantic_model_id(_required_string(payload, "model"))
    if requested_model != expected_model_id:
        raise ValueError("model request does not match the frozen model")
    if getattr(payload, "step_key", None) != attempt.step_key:
        raise ValueError("model request does not match the semantic step")
    if _required_string(payload, "model_cycle_id") != _required_string(
        terminal_payload,
        "model_cycle_id",
    ):
        raise ValueError("model request and terminal cycle do not match")
    return event_id, event_seq, event_hash


def _is_pydantic_diagnostic(payload: object) -> bool:
    diagnostics_json = _optional_string(payload, "diagnostics_json")
    if diagnostics_json is None:
        return False
    try:
        diagnostics = json.loads(diagnostics_json)
    except json.JSONDecodeError:
        return False
    if not isinstance(diagnostics, dict):
        return False
    module = diagnostics.get("exception_module")
    return isinstance(module, str) and module.startswith(("pydantic", "pydantic_core"))


def _token_unavailable_reason(
    *,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    schema_validation_failure: bool,
) -> SemanticTelemetryUnavailableReason | None:
    if prompt_tokens is not None and completion_tokens is not None:
        return None
    if schema_validation_failure and prompt_tokens is None and completion_tokens is None:
        return "artana_exception_did_not_preserve_provider_usage"
    if (prompt_tokens is None) != (completion_tokens is None):
        return "artana_terminal_partial_token_usage"
    return "artana_terminal_missing_token_usage"


def _cost_unavailable_reason(
    *,
    cost_usd: float | None,
    schema_validation_failure: bool,
) -> SemanticTelemetryUnavailableReason | None:
    if cost_usd is not None:
        return None
    if schema_validation_failure:
        return "artana_exception_did_not_preserve_provider_usage"
    return "artana_terminal_missing_cost_usage"


def _terminal_event_identity(event: _TerminalEvent) -> tuple[str, int, str]:
    return _event_identity(event, event_name="terminal")


def _event_identity(
    event: _TerminalEvent | _RequestedEvent,
    *,
    event_name: str,
) -> tuple[str, int, str]:
    event_id = event.event_id
    seq = event.seq
    event_hash = event.event_hash
    if not isinstance(event_id, str) or not event_id:
        raise ValueError(f"runtime {event_name} event is missing event identity")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
        raise ValueError(f"runtime {event_name} event is missing sequence identity")
    if (
        not isinstance(event_hash, str)
        or len(event_hash) != _SHA256_HEX_LENGTH
        or any(character not in "0123456789abcdef" for character in event_hash)
    ):
        raise ValueError(f"runtime {event_name} event is missing hash identity")
    return event_id, seq, event_hash


def _required_string(value: object, field_name: str) -> str:
    result = getattr(value, field_name, None)
    if not isinstance(result, str) or not result:
        raise ValueError(f"runtime terminal event is missing {field_name}")
    return result


def _optional_string(value: object, field_name: str) -> str | None:
    result = getattr(value, field_name, None)
    return result if isinstance(result, str) and result else None


def _required_int(value: object, field_name: str) -> int:
    result = getattr(value, field_name, None)
    if not isinstance(result, int) or isinstance(result, bool) or result < 0:
        raise ValueError(f"runtime terminal event is missing {field_name}")
    return result


def _optional_int(value: object, field_name: str) -> int | None:
    result = getattr(value, field_name, None)
    if result is None:
        return None
    if not isinstance(result, int) or isinstance(result, bool) or result < 0:
        raise ValueError(f"runtime terminal event contains invalid {field_name}")
    return result


def _optional_number(value: object, field_name: str) -> float | None:
    result = getattr(value, field_name, None)
    if result is None:
        return None
    if not isinstance(result, int | float) or isinstance(result, bool) or result < 0:
        raise ValueError(f"runtime terminal event contains invalid {field_name}")
    return round(float(result), 8)


def _string_value(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw)


__all__ = [
    "missing_semantic_terminal_attempt",
    "normalize_semantic_model_id",
    "normalize_semantic_terminal_attempt",
]
