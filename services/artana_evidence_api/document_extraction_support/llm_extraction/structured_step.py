"""Audited structured model invocation shared by decomposed extraction stages."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar
from uuid import uuid4

from artana.ports.model import ModelOutputValidationError
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    bind_prompt_to_invocation,
    kernel_run_id_for_invocation,
    output_schema_json_sha256,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    ModelAttemptAuditContext,
    ModelAttemptAuditRecord,
    ModelAttemptValidationOutcome,
    ModelStepResult,
    model_attempt_evidence_unit_sha256,
    record_model_attempt,
)
from pydantic import BaseModel, ValidationError

ParsedModelT = TypeVar("ParsedModelT", bound=BaseModel)
ValidatedValueT = TypeVar("ValidatedValueT")
ModelStepInvoker = Callable[[str, str], Awaitable[ModelStepResult]]


class StructuredModelValidationError(ValueError):
    """Base failure for a provider result rejected by extraction validation."""


class StructuredModelSchemaError(StructuredModelValidationError):
    """Raised when provider-bound structured output violates its schema."""


class StructuredModelSemanticError(StructuredModelValidationError):
    """Raised when schema-valid model output violates source semantics."""


class StructuredModelInvocationTopologyError(RuntimeError):
    """Raised when the kernel result belongs to a different local invocation."""


@dataclass(frozen=True, slots=True)
class AuditedStructuredStepResult(Generic[ParsedModelT, ValidatedValueT]):
    """Parsed and source-validated value plus its immutable raw snapshot."""

    parsed: ParsedModelT
    value: ValidatedValueT
    raw_output: dict[str, object]
    attempt_record: ModelAttemptAuditRecord


async def run_audited_structured_step(
    *,
    invoke_model: ModelStepInvoker,
    model_id: str,
    prompt: str,
    output_schema: type[ParsedModelT],
    step_key: str,
    audit_context: ModelAttemptAuditContext,
    validate_semantics: Callable[[ParsedModelT], ValidatedValueT],
) -> AuditedStructuredStepResult[ParsedModelT, ValidatedValueT]:
    """Invoke one kernel step and audit every terminal outcome."""

    invocation_id = str(uuid4())
    provider_prompt = bind_prompt_to_invocation(
        prompt=prompt,
        invocation_id=invocation_id,
        source_sha256=audit_context.source_sha256,
        input_sha256=audit_context.input_sha256,
        evidence_unit_sha256=model_attempt_evidence_unit_sha256(
            default=audit_context.source_sha256,
        ),
        output_schema_sha256=output_schema_json_sha256(output_schema),
    )
    model_result: ModelStepResult | None = None
    raw_output: object | None = None
    try:
        model_result = await invoke_model(invocation_id, provider_prompt)
        raw_output = model_result.output
        _require_invocation_topology(
            model_result=model_result,
            invocation_id=invocation_id,
        )
        parsed = (
            raw_output
            if isinstance(raw_output, output_schema)
            else output_schema.model_validate(raw_output)
        )
        validated = validate_semantics(parsed)
    except asyncio.CancelledError as exc:
        _record_terminal_attempt(
            invocation_id=invocation_id,
            model_id=model_id,
            prompt=provider_prompt,
            output_schema=output_schema,
            step_key=step_key,
            audit_context=audit_context,
            model_result=model_result,
            raw_output=raw_output,
            validation_outcome="invocation_failed",
            error_type=type(exc).__name__,
        )
        raise
    except ModelOutputValidationError as exc:
        raw_output = exc.output
        _require_invocation_topology(
            model_result=exc,
            invocation_id=invocation_id,
        )
        _record_terminal_attempt(
            invocation_id=invocation_id,
            model_id=model_id,
            prompt=provider_prompt,
            output_schema=output_schema,
            step_key=step_key,
            audit_context=audit_context,
            model_result=exc,
            raw_output=raw_output,
            validation_outcome="schema_invalid",
            error_type=StructuredModelSchemaError.__name__,
        )
        raise StructuredModelSchemaError(str(exc)) from exc
    except ValidationError as exc:
        _record_terminal_attempt(
            invocation_id=invocation_id,
            model_id=model_id,
            prompt=provider_prompt,
            output_schema=output_schema,
            step_key=step_key,
            audit_context=audit_context,
            model_result=model_result,
            raw_output=raw_output,
            validation_outcome="schema_invalid",
            error_type=type(exc).__name__,
        )
        raise
    except StructuredModelSemanticError as exc:
        _record_terminal_attempt(
            invocation_id=invocation_id,
            model_id=model_id,
            prompt=provider_prompt,
            output_schema=output_schema,
            step_key=step_key,
            audit_context=audit_context,
            model_result=model_result,
            raw_output=raw_output,
            validation_outcome="semantic_invalid",
            error_type=type(exc).__name__,
        )
        raise
    except Exception as exc:
        _record_terminal_attempt(
            invocation_id=invocation_id,
            model_id=model_id,
            prompt=provider_prompt,
            output_schema=output_schema,
            step_key=step_key,
            audit_context=audit_context,
            model_result=model_result,
            raw_output=raw_output,
            validation_outcome="invocation_failed",
            error_type=type(exc).__name__,
        )
        raise

    record = record_model_attempt(
        invocation_id=invocation_id,
        model_id=model_id,
        prompt=provider_prompt,
        output_schema=output_schema,
        step_key=step_key,
        audit_context=audit_context,
        model_result=model_result,
        raw_output=raw_output,
        validation_outcome="accepted",
        error_type=None,
    )
    immutable_raw_output = record.raw_model_payload
    if immutable_raw_output is None:
        raise AssertionError("accepted structured output must have a raw snapshot")
    return AuditedStructuredStepResult(
        parsed=parsed,
        value=validated,
        raw_output=immutable_raw_output,
        attempt_record=record,
    )


def _require_invocation_topology(
    *,
    model_result: object,
    invocation_id: str,
) -> None:
    expected_run_id = kernel_run_id_for_invocation(invocation_id)
    if getattr(model_result, "run_id", None) != expected_run_id:
        raise StructuredModelInvocationTopologyError(
            "structured model result does not match its invocation run",
        )


def _record_terminal_attempt(
    *,
    invocation_id: str,
    model_id: str,
    prompt: str,
    output_schema: type[BaseModel],
    step_key: str,
    audit_context: ModelAttemptAuditContext,
    model_result: object | None,
    raw_output: object | None,
    validation_outcome: ModelAttemptValidationOutcome,
    error_type: str,
) -> None:
    record_model_attempt(
        invocation_id=invocation_id,
        model_id=model_id,
        prompt=prompt,
        output_schema=output_schema,
        step_key=step_key,
        audit_context=audit_context,
        model_result=model_result,
        raw_output=raw_output,
        validation_outcome=validation_outcome,
        error_type=error_type,
    )


__all__ = [
    "AuditedStructuredStepResult",
    "StructuredModelInvocationTopologyError",
    "StructuredModelSchemaError",
    "StructuredModelSemanticError",
    "StructuredModelValidationError",
    "run_audited_structured_step",
]
