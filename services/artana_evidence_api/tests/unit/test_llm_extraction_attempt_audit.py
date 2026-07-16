"""Regression tests for document-extraction model-attempt auditing."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from types import SimpleNamespace
from typing import Literal, Never

import pytest
from artana.ports.model import ModelOutputValidationError, ModelUsage
from artana_evidence_api.document_extraction_prompting import (
    _build_llm_extraction_output_schema,
)
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    kernel_run_id_for_invocation,
)
from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    StructuredModelSchemaError,
    run_audited_structured_step,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    ModelAttemptAuditContext,
    canonical_openai_response_id,
    model_attempt_audit_manifest,
    record_skipped_model_attempt,
    run_llm_relation_extraction_pass,
    start_model_attempt_audit,
    stop_model_attempt_audit,
)
from pydantic import BaseModel, ValidationError


class _ProviderBoundSchema(BaseModel):
    approved: bool


def _legacy_output_schema() -> type:
    return _build_llm_extraction_output_schema(
        max_relations=10,
        strict_relation_type=False,
        require_claim_frame_fields=False,
    )


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _litellm_response_id(
    provider_response_id: str,
    *,
    provider: str = "openai",
    model_id: str = "None",
    padded: bool = False,
) -> str:
    envelope = (
        f"litellm:custom_llm_provider:{provider};model_id:{model_id};"
        f"response_id:{provider_response_id}"
    )
    encoded = base64.urlsafe_b64encode(envelope.encode("utf-8")).decode("ascii")
    return f"resp_{encoded if padded else encoded.rstrip('=')}"


@pytest.mark.asyncio
async def test_schema_invalid_attempt_preserves_exact_raw_payload() -> None:
    raw_payload = {
        "relations": [
            {
                "subject": "MED13",
                "unexpected": {"nested": [1, True, None]},
            },
        ],
        "raw_trace": "model-boundary-value",
    }
    schema = _legacy_output_schema()
    provider_response_id = "resp_provider_audit_1"
    execution_response_id = _litellm_response_id(provider_response_id)
    response_output_items = ({"id": "msg_provider_audit_1", "type": "message"},)

    async def _step_runner(*_args: object, **_kwargs: object) -> object:
        return SimpleNamespace(
            output=raw_payload,
            run_id="kernel-run-audit-1",
            seq=17,
            replayed=False,
            response_id=execution_response_id,
            response_output_items=response_output_items,
        )

    session = start_model_attempt_audit()
    try:
        with pytest.raises(ValidationError):
            await run_llm_relation_extraction_pass(
                step_runner=_step_runner,
                client=object(),
                tenant=object(),
                model_id="openai/gpt-audit-test",
                prompt="extract one relation",
                output_schema=schema,
                step_key="document_extraction.test.primary",
                source_text="MED13 associates with cardiomyopathy.",
                source_hash="a" * 64,
                audit_context=ModelAttemptAuditContext(
                    attempt_role="primary",
                    pass_role="primary",
                    retry_context=None,
                    source_sha256="a" * 64,
                    input_sha256="b" * 64,
                ),
            )
    finally:
        stop_model_attempt_audit(session)

    assert len(session.records) == 1
    record = session.records[0]
    assert record.validation_outcome == "schema_invalid"
    assert record.semantic_unit_id is None
    assert record.error_type == "ValidationError"
    assert record.raw_model_payload == raw_payload
    assert record.payload_sha256 == _canonical_sha256(raw_payload)
    assert record.provider_execution_response_id == execution_response_id
    assert record.provider_response_id == provider_response_id
    assert record.provider_output_sha256 == _canonical_sha256(
        list(response_output_items),
    )
    assert record.kernel_run_id == "kernel-run-audit-1"
    assert record.kernel_event_seq == 17
    assert record.replayed is False
    assert "model-boundary-value" not in (record.error_type or "")
    mutable_copy = record.raw_model_payload
    assert mutable_copy is not None
    mutable_copy["raw_trace"] = "tampered"
    assert record.raw_model_payload == raw_payload

    first_manifest = model_attempt_audit_manifest(
        document_id="document-1",
        records=session.records,
    )
    second_manifest = model_attempt_audit_manifest(
        document_id="document-1",
        records=session.records,
    )
    assert first_manifest == second_manifest
    manifest_without_hash = dict(first_manifest)
    manifest_sha256 = manifest_without_hash.pop("manifest_sha256")
    assert manifest_sha256 == _canonical_sha256(manifest_without_hash)


@pytest.mark.asyncio
@pytest.mark.parametrize("replay_state", ["fresh", "replayed"])
async def test_kernel_schema_failure_remains_provider_bound_for_retry(
    replay_state: Literal["fresh", "replayed"],
) -> None:
    replayed = replay_state == "replayed"
    raw_payload = {"approved": "maybe"}
    provider_response_id = "resp_provider_kernel_invalid_1"
    response_output_items = (
        {
            "type": "message",
            "content": [
                {
                    "type": "output_text",
                    "text": json.dumps(raw_payload, sort_keys=True),
                }
            ],
        },
    )

    async def _invoke_model(invocation_id: str, _prompt: str) -> Never:
        error = ModelOutputValidationError(
            raw_output=json.dumps(raw_payload, sort_keys=True),
            usage=ModelUsage(prompt_tokens=11, completion_tokens=3, cost_usd=0.01),
            api_mode_used="responses",
            response_id=provider_response_id,
            response_output_items=response_output_items,
        )
        error.bind_kernel_terminal(
            run_id=kernel_run_id_for_invocation(invocation_id),
            seq=23,
            replayed=replayed,
        )
        raise error

    session = start_model_attempt_audit()
    try:
        with pytest.raises(StructuredModelSchemaError):
            await run_audited_structured_step(
                invoke_model=_invoke_model,
                model_id="openai:gpt-5.6-luna",
                prompt="Return one decision.",
                output_schema=_ProviderBoundSchema,
                step_key="document_extraction.test.provider_schema_failure",
                audit_context=ModelAttemptAuditContext(
                    attempt_role="schema_retry",
                    pass_role="claim_inventory",
                    retry_context=None,
                    source_sha256="c" * 64,
                    input_sha256="d" * 64,
                ),
                validate_semantics=lambda parsed: parsed,
            )
    finally:
        stop_model_attempt_audit(session)

    assert len(session.records) == 1
    record = session.records[0]
    assert record.validation_outcome == "schema_invalid"
    assert record.error_type == "StructuredModelSchemaError"
    assert record.raw_model_payload == raw_payload
    assert record.provider_response_id == provider_response_id
    assert record.provider_output_sha256 == _canonical_sha256(
        list(response_output_items),
    )
    assert record.kernel_run_id is not None
    assert record.kernel_event_seq == 23
    assert record.replayed is replayed


def test_semantic_unit_id_is_serialized_for_claim_framing_attempts() -> None:
    semantic_unit_id = "inventory-unit-1"
    session = start_model_attempt_audit()
    try:
        record = record_skipped_model_attempt(
            model_id="openai/gpt-audit-test",
            prompt="frame one inventoried claim",
            output_schema=_legacy_output_schema(),
            step_key="document_extraction.test.claim_framing",
            audit_context=ModelAttemptAuditContext(
                attempt_role="schema_retry",
                pass_role="claim_framing",
                retry_context=None,
                source_sha256="a" * 64,
                input_sha256="b" * 64,
                semantic_unit_id=semantic_unit_id,
            ),
        )
    finally:
        stop_model_attempt_audit(session)

    assert record.semantic_unit_id == semantic_unit_id
    assert record.as_json()["semantic_unit_id"] == semantic_unit_id
    manifest = model_attempt_audit_manifest(
        document_id="document-framing",
        records=session.records,
    )
    assert manifest["attempts"][0]["semantic_unit_id"] == semantic_unit_id


def test_openai_response_id_accepts_only_direct_or_exact_litellm_envelope() -> None:
    provider_response_id = "resp_provider_receipt_123"

    assert canonical_openai_response_id(provider_response_id) == provider_response_id
    assert (
        canonical_openai_response_id(_litellm_response_id(provider_response_id))
        == provider_response_id
    )
    assert (
        canonical_openai_response_id(
            _litellm_response_id(provider_response_id, padded=True),
        )
        == provider_response_id
    )


@pytest.mark.parametrize(
    "response_id",
    [
        "resp-not-an-openai-id",
        "resp_" + ("a" * 60),
        _litellm_response_id("resp_provider_receipt_123", provider="azure"),
        _litellm_response_id("resp_provider_receipt_123", model_id="model-1"),
        _litellm_response_id("resp_provider_receipt_123", padded=True) + "=",
        "resp_"
        + base64.urlsafe_b64encode(b"arbitrary-wrapper" * 8)
        .decode("ascii")
        .rstrip("="),
    ],
)
def test_openai_response_id_rejects_malformed_or_other_provider_wrappers(
    response_id: str,
) -> None:
    with pytest.raises(ValueError):
        canonical_openai_response_id(response_id)


@pytest.mark.asyncio
async def test_cancelled_model_invocation_is_recorded_before_timeout_fallback() -> None:
    schema = _legacy_output_schema()

    async def _cancelled_step_runner(*_args: object, **_kwargs: object) -> object:
        raise asyncio.CancelledError

    session = start_model_attempt_audit()
    try:
        with pytest.raises(asyncio.CancelledError):
            await run_llm_relation_extraction_pass(
                step_runner=_cancelled_step_runner,
                client=object(),
                tenant=object(),
                model_id="openai/gpt-audit-test",
                prompt="extract before timeout",
                output_schema=schema,
                step_key="document_extraction.test.timeout",
                source_text="MED13 associates with cardiomyopathy.",
                source_hash="d" * 64,
            )
    finally:
        stop_model_attempt_audit(session)

    assert len(session.records) == 1
    assert session.records[0].validation_outcome == "invocation_failed"
    assert session.records[0].error_type == "CancelledError"
    assert session.records[0].raw_model_payload is None
