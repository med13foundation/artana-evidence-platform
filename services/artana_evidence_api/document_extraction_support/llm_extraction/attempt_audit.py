"""Provider-boundary receipts and model-attempt audit records."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Sequence
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Literal, Protocol, cast
from uuid import uuid4

from pydantic import BaseModel

_DIRECT_OPENAI_RESPONSE_ID_RE = re.compile(r"^resp_[A-Za-z0-9_-]{1,59}$")
_LITELLM_OPENAI_RESPONSE_ENVELOPE_RE = re.compile(
    r"^litellm:custom_llm_provider:openai;model_id:None;"
    r"response_id:(?P<response_id>resp_[A-Za-z0-9_-]{1,59})$",
)
_MAX_DIRECT_OPENAI_RESPONSE_ID_LENGTH = 64
_MAX_LITELLM_RESPONSE_ENVELOPE_LENGTH = 256


class ModelStepResult(Protocol):
    """Minimal provider result required by extraction and its audit trail."""

    output: object
    run_id: str
    seq: int
    replayed: bool
    response_id: str | None
    response_output_items: Sequence[dict[str, object]]


ModelStepRunner = Callable[..., Awaitable[ModelStepResult]]

ModelAttemptRole = Literal[
    "claim_inventory",
    "claim_inventory_completeness",
    "claim_inventory_recovery",
    "claim_framing",
    "primary",
    "weak_review",
    "schema_retry",
    "zero_candidate_retry",
    "proposal_review",
    "structure_normalization",
    "normalized_review",
]
ModelAttemptPassRole = Literal[
    "claim_inventory",
    "claim_inventory_completeness",
    "claim_inventory_recovery",
    "claim_framing",
    "primary",
    "weak_review",
    "proposal_review",
    "structure_normalization",
    "normalized_review",
]
ModelAttemptValidationOutcome = Literal[
    "accepted",
    "schema_invalid",
    "semantic_invalid",
    "invocation_failed",
    "intentionally_skipped",
]


@dataclass(frozen=True, slots=True)
class ModelAttemptAuditContext:
    """Stable inputs that identify one possible model invocation."""

    attempt_role: ModelAttemptRole
    pass_role: ModelAttemptPassRole
    retry_context: Literal["zero_candidate_retry"] | None
    source_sha256: str
    input_sha256: str
    semantic_unit_id: str | None = None


@dataclass(frozen=True, slots=True)
class ModelAttemptAuditRecord:
    """Immutable raw-boundary record for one invocation or explicit skip."""

    invocation_id: str
    attempt_role: ModelAttemptRole
    pass_role: ModelAttemptPassRole
    retry_context: Literal["zero_candidate_retry"] | None
    model_id: str
    step_key: str
    prompt_sha256: str
    source_sha256: str
    input_sha256: str
    evidence_unit_sha256: str
    semantic_unit_id: str | None
    output_schema_identity: str
    provider_execution_response_id: str | None
    provider_response_id: str | None
    provider_output_sha256: str | None
    kernel_run_id: str | None
    kernel_event_seq: int | None
    replayed: bool | None
    raw_model_payload_json: str | None
    payload_sha256: str | None
    validation_outcome: ModelAttemptValidationOutcome
    error_type: str | None

    @property
    def raw_model_payload(self) -> dict[str, object] | None:
        """Return a fresh copy of the immutable raw payload snapshot."""

        if self.raw_model_payload_json is None:
            return None
        return _freeze_json_object(json.loads(self.raw_model_payload_json))

    def as_json(self) -> dict[str, object]:
        """Return an isolated JSON-safe representation."""

        return _freeze_json_object(
            {
                "invocation_id": self.invocation_id,
                "attempt_role": self.attempt_role,
                "pass_role": self.pass_role,
                "retry_context": self.retry_context,
                "model_id": self.model_id,
                "step_key": self.step_key,
                "prompt_sha256": self.prompt_sha256,
                "source_sha256": self.source_sha256,
                "input_sha256": self.input_sha256,
                "evidence_unit_sha256": self.evidence_unit_sha256,
                "semantic_unit_id": self.semantic_unit_id,
                "output_schema_identity": self.output_schema_identity,
                "provider_execution_response_id": (self.provider_execution_response_id),
                "provider_response_id": self.provider_response_id,
                "provider_output_sha256": self.provider_output_sha256,
                "kernel_run_id": self.kernel_run_id,
                "kernel_event_seq": self.kernel_event_seq,
                "replayed": self.replayed,
                "raw_model_payload": self.raw_model_payload,
                "payload_sha256": self.payload_sha256,
                "validation_outcome": self.validation_outcome,
                "error_type": self.error_type,
            },
        )


@dataclass(slots=True)
class ModelAttemptAuditSession:
    """Mutable collection scope whose records remain immutable."""

    records: list[ModelAttemptAuditRecord] = field(default_factory=list)
    evidence_unit_sha256: str | None = None
    record_observer: Callable[[ModelAttemptAuditRecord], None] | None = field(
        default=None,
        repr=False,
    )
    context_token: Token[ModelAttemptAuditSession | None] | None = field(
        default=None,
        repr=False,
    )


_MODEL_ATTEMPT_AUDIT_SESSION: ContextVar[ModelAttemptAuditSession | None] = ContextVar(
    "document_extraction_model_attempt_audit",
    default=None,
)


def start_model_attempt_audit(
    *,
    evidence_unit_id: str | None = None,
    record_observer: Callable[[ModelAttemptAuditRecord], None] | None = None,
) -> ModelAttemptAuditSession:
    """Start an audit scope inherited by child asyncio tasks."""

    if evidence_unit_id is not None and not evidence_unit_id.strip():
        raise ValueError("evidence_unit_id must be nonempty when provided")
    session = ModelAttemptAuditSession(
        evidence_unit_sha256=(
            _sha256_text(evidence_unit_id) if evidence_unit_id is not None else None
        ),
        record_observer=record_observer,
    )
    session.context_token = _MODEL_ATTEMPT_AUDIT_SESSION.set(session)
    return session


def stop_model_attempt_audit(session: ModelAttemptAuditSession) -> None:
    """Restore the audit scope active before ``session`` started."""

    if session.context_token is not None:
        _MODEL_ATTEMPT_AUDIT_SESSION.reset(session.context_token)
        session.context_token = None


def current_model_attempt_audit() -> ModelAttemptAuditSession | None:
    """Return the active audit session, if one exists."""

    return _MODEL_ATTEMPT_AUDIT_SESSION.get()


def model_attempt_evidence_unit_sha256(*, default: str) -> str:
    """Return the active evidence-unit binding or a source-bound default."""

    session = current_model_attempt_audit()
    if session is None or session.evidence_unit_sha256 is None:
        return default
    return session.evidence_unit_sha256


def model_attempt_audit_manifest(
    *,
    document_id: str,
    records: Sequence[ModelAttemptAuditRecord],
) -> dict[str, object]:
    """Build a canonically hashed document-extraction audit artifact."""

    attempts = [record.as_json() for record in records]
    manifest: dict[str, object] = {
        "schema_version": "document_extraction.model_attempt_audit.v1",
        "document_id": document_id,
        "attempt_count": len(attempts),
        "attempts": attempts,
        "attempts_sha256": _canonical_json_sha256(attempts),
    }
    return {
        **manifest,
        "manifest_sha256": _canonical_json_sha256(manifest),
    }


def record_skipped_model_attempt(
    *,
    model_id: str,
    prompt: str,
    output_schema: type[BaseModel],
    step_key: str,
    audit_context: ModelAttemptAuditContext,
) -> ModelAttemptAuditRecord:
    """Record that a fully identified model path was intentionally not invoked."""

    record = _build_model_attempt_record(
        invocation_id=str(uuid4()),
        model_id=model_id,
        prompt=prompt,
        output_schema=output_schema,
        step_key=step_key,
        audit_context=audit_context,
        model_result=None,
        raw_model_payload=None,
        validation_outcome="intentionally_skipped",
        error_type=None,
    )
    _append_model_attempt_record(record)
    return record


def record_model_attempt(
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
    error_type: str | None,
) -> ModelAttemptAuditRecord:
    """Append one exact model-boundary outcome to the active audit session."""

    raw_model_payload = (
        freeze_model_boundary_output(raw_output) if raw_output is not None else None
    )
    record = _build_model_attempt_record(
        invocation_id=invocation_id,
        model_id=model_id,
        prompt=prompt,
        output_schema=output_schema,
        step_key=step_key,
        audit_context=audit_context,
        model_result=model_result,
        raw_model_payload=raw_model_payload,
        validation_outcome=validation_outcome,
        error_type=error_type,
    )
    _append_model_attempt_record(record)
    return record


def _append_model_attempt_record(record: ModelAttemptAuditRecord) -> None:
    session = current_model_attempt_audit()
    if session is not None:
        session.records.append(record)
        if session.record_observer is not None:
            session.record_observer(record)


def _build_model_attempt_record(
    *,
    invocation_id: str,
    model_id: str,
    prompt: str,
    output_schema: type[BaseModel],
    step_key: str,
    audit_context: ModelAttemptAuditContext,
    model_result: object | None,
    raw_model_payload: dict[str, object] | None,
    validation_outcome: ModelAttemptValidationOutcome,
    error_type: str | None,
) -> ModelAttemptAuditRecord:
    raw_model_payload_json = (
        _canonical_json(raw_model_payload) if raw_model_payload is not None else None
    )
    provider_execution_response_id = _optional_string_attribute(
        model_result,
        "response_id",
    )
    return ModelAttemptAuditRecord(
        invocation_id=invocation_id,
        attempt_role=audit_context.attempt_role,
        pass_role=audit_context.pass_role,
        retry_context=audit_context.retry_context,
        model_id=model_id,
        step_key=step_key,
        prompt_sha256=_sha256_text(prompt),
        source_sha256=audit_context.source_sha256,
        input_sha256=audit_context.input_sha256,
        evidence_unit_sha256=model_attempt_evidence_unit_sha256(
            default=audit_context.source_sha256,
        ),
        semantic_unit_id=audit_context.semantic_unit_id,
        output_schema_identity=(
            f"{output_schema.__module__}.{output_schema.__qualname__}"
        ),
        provider_execution_response_id=provider_execution_response_id,
        provider_response_id=_canonical_response_id_or_none(
            provider_execution_response_id,
        ),
        provider_output_sha256=_provider_output_sha256(model_result),
        kernel_run_id=_optional_string_attribute(model_result, "run_id"),
        kernel_event_seq=_optional_int_attribute(model_result, "seq"),
        replayed=_optional_bool_attribute(model_result, "replayed"),
        raw_model_payload_json=raw_model_payload_json,
        payload_sha256=(
            hashlib.sha256(raw_model_payload_json.encode("utf-8")).hexdigest()
            if raw_model_payload_json is not None
            else None
        ),
        validation_outcome=validation_outcome,
        error_type=error_type,
    )


def _optional_string_attribute(value: object | None, name: str) -> str | None:
    attribute = getattr(value, name, None)
    return attribute if isinstance(attribute, str) and attribute else None


def _optional_int_attribute(value: object | None, name: str) -> int | None:
    attribute = getattr(value, name, None)
    return (
        attribute
        if isinstance(attribute, int) and not isinstance(attribute, bool)
        else None
    )


def _optional_bool_attribute(value: object | None, name: str) -> bool | None:
    attribute = getattr(value, name, None)
    return attribute if isinstance(attribute, bool) else None


def canonical_openai_response_id(response_id: str) -> str:
    """Return a direct OpenAI ID from a strict direct or LiteLLM identity."""

    if _DIRECT_OPENAI_RESPONSE_ID_RE.fullmatch(response_id) is not None:
        return response_id
    if (
        not response_id.startswith("resp_")
        or len(response_id) <= _MAX_DIRECT_OPENAI_RESPONSE_ID_LENGTH
        or len(response_id) > _MAX_LITELLM_RESPONSE_ENVELOPE_LENGTH
    ):
        raise ValueError("response ID is not a recognized OpenAI receipt identity")

    encoded_envelope = response_id.removeprefix("resp_")
    if re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", encoded_envelope) is None:
        raise ValueError("LiteLLM response envelope is not canonical URL-safe base64")
    unpadded_envelope = encoded_envelope.rstrip("=")
    supplied_padding = encoded_envelope[len(unpadded_envelope) :]
    canonical_padding = "=" * (-len(unpadded_envelope) % 4)
    if supplied_padding not in {"", canonical_padding}:
        raise ValueError("LiteLLM response envelope has non-canonical padding")
    padded = unpadded_envelope + canonical_padding
    try:
        decoded_bytes = base64.b64decode(padded, altchars=b"-_", validate=True)
        decoded_envelope = decoded_bytes.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("LiteLLM response envelope cannot be decoded") from exc
    canonical_encoding = (
        base64.urlsafe_b64encode(decoded_bytes)
        .decode("ascii")
        .rstrip(
            "=",
        )
    )
    if canonical_encoding != unpadded_envelope:
        raise ValueError("LiteLLM response envelope encoding is not canonical")
    match = _LITELLM_OPENAI_RESPONSE_ENVELOPE_RE.fullmatch(decoded_envelope)
    if match is None:
        raise ValueError("LiteLLM response envelope is not the OpenAI receipt grammar")
    return match.group("response_id")


def _canonical_response_id_or_none(response_id: str | None) -> str | None:
    if response_id is None:
        return None
    try:
        return canonical_openai_response_id(response_id)
    except ValueError:
        return None


def _provider_output_sha256(model_result: object | None) -> str | None:
    """Bind a provider response ID to its exact canonical Responses output."""

    if _optional_string_attribute(model_result, "response_id") is None:
        return None
    output_items = getattr(model_result, "response_output_items", None)
    if not isinstance(output_items, Sequence) or isinstance(output_items, str | bytes):
        return None
    if not all(isinstance(item, dict) for item in output_items):
        return None
    return _canonical_json_sha256(list(output_items))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def freeze_model_boundary_output(output: object) -> dict[str, object]:
    """Freeze a structured provider result before validation and normalization."""

    return _freeze_json_object(output)


def _freeze_json_object(value: object) -> dict[str, object]:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    frozen = json.loads(json.dumps(value))
    if not isinstance(frozen, dict):
        raise TypeError("model payload must be a JSON object")
    return cast("dict[str, object]", frozen)


__all__ = [
    "ModelAttemptAuditContext",
    "ModelAttemptAuditRecord",
    "ModelAttemptAuditSession",
    "ModelAttemptPassRole",
    "ModelAttemptRole",
    "ModelAttemptValidationOutcome",
    "ModelStepResult",
    "ModelStepRunner",
    "canonical_openai_response_id",
    "current_model_attempt_audit",
    "freeze_model_boundary_output",
    "model_attempt_audit_manifest",
    "model_attempt_evidence_unit_sha256",
    "record_model_attempt",
    "record_skipped_model_attempt",
    "start_model_attempt_audit",
    "stop_model_attempt_audit",
]
