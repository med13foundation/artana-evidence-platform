"""Live TG-04 execution through Artana's strict audited agent path."""

from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol, cast
from uuid import uuid4

from artana_evidence_api.document_extraction_prompting import (
    build_claim_inventory_completeness_output_schema,
    build_claim_inventory_output_schema,
    build_missing_claim_recovery_output_schema,
)
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    output_schema_json_sha256,
)

from scripts.validation.claim_events.fixture import require_frozen_development_fixture
from scripts.validation.claim_events.operational import (
    CaseExecutionOutcome,
    OperationalSafetyEvidence,
    build_operational_summary,
    require_sealable_unbindable_attempts,
)
from scripts.validation.claim_events.scoring import score_fixture
from scripts.validation.claim_frames.evidence import collect_repository_evidence
from scripts.validation.claim_frames.provider_receipts import (
    OpenAIProviderReceiptVerifier,
    ProviderReceiptExpectation,
    canonical_provider_model_id,
    verify_provider_receipts,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.claim_frames import (
        BoundClaimInventoryItem,
    )
    from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
        ModelAttemptAuditRecord,
    )

    from scripts.validation.claim_events.contracts import (
        NaryClaimCase,
        NaryClaimFixture,
    )
    from scripts.validation.claim_events.scoring import BenchmarkFixtureContract

_ALLOWED_MODELS: Final = frozenset(
    {"openai:gpt-5.6-luna", "openai:gpt-5.6-sol"},
)
_REPO_ROOT: Final = Path(__file__).resolve().parents[3]
_TASK_ID: Final = "nary_event_inventory"


class _AsyncClosable(Protocol):
    async def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class _CaseRunResult:
    prediction: dict[str, object]
    evidence: dict[str, object]
    records: tuple[ModelAttemptAuditRecord, ...]


def run_live_arm(
    *,
    fixture: NaryClaimFixture,
    model_id: str,
    run_id: str,
) -> dict[str, object]:
    """Execute one independently identified model run of the n-ary task."""

    require_frozen_development_fixture(fixture)
    _require_model(model_id)
    repository_evidence = collect_repository_evidence(_REPO_ROOT)
    if repository_evidence["clean"] is not True:
        raise RuntimeError("TG-04 live runs require a clean tracked worktree")
    return asyncio.run(
        _run_live_arm(
            fixture=fixture,
            model_id=model_id,
            run_id=run_id,
            repository_evidence=repository_evidence,
        ),
    )


async def _run_live_arm(
    *,
    fixture: NaryClaimFixture,
    model_id: str,
    run_id: str,
    repository_evidence: dict[str, object],
) -> dict[str, object]:
    client, tenant, execution_model_id, kernel, store = _build_inventory_runtime(
        model_id,
    )

    predictions: list[dict[str, object]] = []
    case_evidence: list[dict[str, object]] = []
    provider_ids: set[str] = set()
    receipt_expectations: list[ProviderReceiptExpectation] = []
    fallback_count = invalid_count = unidentified_provider_count = 0
    qualification_invalid_count = stress_invalid_count = 0
    try:
        for case in fixture.cases:
            case_result = await _execute_case(
                case=case,
                client=client,
                tenant=tenant,
                execution_model_id=execution_model_id,
            )
            case_expectations, case_invalid, case_unidentified = (
                _case_receipt_expectations(
                    records=case_result.records,
                    case_id=case.case_id,
                    model_id=model_id,
                )
            )
            invalid_count += case_invalid
            if str(case.control_status) == "REPRESENTABILITY_STRESS":
                stress_invalid_count += case_invalid
            else:
                qualification_invalid_count += case_invalid
            unidentified_provider_count += case_unidentified
            for expectation in case_expectations:
                if expectation.response_id in provider_ids:
                    raise RuntimeError("TG-04 provider response IDs must be unique")
                provider_ids.add(expectation.response_id)
                receipt_expectations.append(expectation)
            predictions.append(case_result.prediction)
            case_evidence.append(case_result.evidence)
    finally:
        with suppress(Exception):
            await kernel.close()
        with suppress(Exception):
            await store.close()

    final_repository_evidence = collect_repository_evidence(_REPO_ROOT)
    if final_repository_evidence != repository_evidence:
        raise RuntimeError("TG-04 repository state changed during the live run")
    score = score_fixture(cast("BenchmarkFixtureContract", fixture), predictions)
    provider_receipts = verify_provider_receipts(
        receipt_expectations,
        OpenAIProviderReceiptVerifier.from_environment(),
    )
    operational_summary = build_operational_summary(
        cases=fixture.cases,
        predictions=predictions,
        safety=OperationalSafetyEvidence(
            fallback_count=fallback_count,
            unidentified_provider_attempt_count=unidentified_provider_count,
            qualification_invalid_agent_output_count=qualification_invalid_count,
            representability_stress_invalid_agent_output_count=stress_invalid_count,
            provider_receipt_gate_passed=provider_receipts.gate_passed,
        ),
    )
    report: dict[str, object] = {
        "schema_version": "tg04_live_arm.v2",
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "fixture_sha256": fixture.sha256,
        "task_id": _TASK_ID,
        "model_id": model_id,
        "repository_evidence": repository_evidence,
        "predictions": predictions,
        "metrics": asdict(score.metrics),
        "case_scores": [asdict(case) for case in score.cases],
        "operational_summary": operational_summary,
        "safety": {
            "fallback_count": fallback_count,
            "invalid_agent_output_count": invalid_count,
            "qualification_invalid_agent_output_count": (qualification_invalid_count),
            "representability_stress_invalid_agent_output_count": (
                stress_invalid_count
            ),
            "provider_response_id_count": len(provider_ids),
            "provider_receipt_status": provider_receipts.status,
            "verified_provider_receipt_count": provider_receipts.verified_count,
            "unidentified_provider_attempt_count": unidentified_provider_count,
        },
        "provider_receipts": provider_receipts.as_json(),
        "case_evidence": case_evidence,
    }
    report["report_sha256"] = _sha256_json(report)
    return report


async def _execute_case(
    *,
    case: NaryClaimCase,
    client: object,
    tenant: object,
    execution_model_id: str,
) -> _CaseRunResult:
    from artana_evidence_api.document_extraction import normalize_text_document
    from artana_evidence_api.document_extraction_support.full_text_chunking import (
        build_relation_extraction_text_chunks,
    )
    from artana_evidence_api.document_extraction_support.llm_extraction.runner import (
        run_llm_claim_inventory_with_zero_retry,
    )
    from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
        StructuredModelValidationError,
    )
    from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
        llm_extraction_document_fingerprint,
        start_model_attempt_audit,
        stop_model_attempt_audit,
    )
    from artana_evidence_api.step_helpers import run_single_step_with_policy
    from pydantic import ValidationError

    invocation_namespace = f"tg04-{_TASK_ID}-{uuid4().hex}"
    normalized_text = normalize_text_document(case.source_text)
    audit = start_model_attempt_audit(evidence_unit_id=case.case_id)
    inventory = None
    terminal_error: ValidationError | StructuredModelValidationError | None = None
    try:
        try:
            inventory = await run_llm_claim_inventory_with_zero_retry(
                normalized_text=normalized_text,
                chunks=build_relation_extraction_text_chunks(normalized_text),
                document_fingerprint=llm_extraction_document_fingerprint(
                    normalized_text,
                ),
                client=client,
                tenant=tenant,
                model_id=execution_model_id,
                step_runner=run_single_step_with_policy,
                execution_namespace=invocation_namespace,
            )
        except (ValidationError, StructuredModelValidationError) as exc:
            terminal_error = exc
    finally:
        stop_model_attempt_audit(audit)

    if terminal_error is not None:
        require_sealable_unbindable_attempts(
            tuple(record.as_json() for record in audit.records),
        )
        if audit.records[-1].error_type != type(terminal_error).__name__:
            raise RuntimeError("TG-04 terminal audit error differs from raised error")

    events = [] if inventory is None else _nary_events(inventory.claims)
    outcome = _execution_outcome(events=events, failed=terminal_error is not None)
    routing_status = "unbound"
    if terminal_error is None:
        routing_status = (
            "complete"
            if inventory is not None and inventory.semantic_inventory_complete
            else "semantic_incomplete"
        )
    return _CaseRunResult(
        prediction={
            "case_id": case.case_id,
            "events": events,
            "abstained": not events,
            "execution_outcome": outcome.value,
        },
        evidence={
            "case_id": case.case_id,
            "invocation_namespace": invocation_namespace,
            "attempts": [record.as_json() for record in audit.records],
            "diagnostics": {
                "fallback_output_used": False,
                "claim_extraction_routing_status": routing_status,
                "terminal_error_category": (
                    None if terminal_error is None else type(terminal_error).__name__
                ),
            },
        },
        records=tuple(audit.records),
    )


def _execution_outcome(
    *,
    events: list[dict[str, object]],
    failed: bool,
) -> CaseExecutionOutcome:
    if failed:
        return CaseExecutionOutcome.UNBINDABLE_OUTPUT
    return (
        CaseExecutionOutcome.BOUND_OUTPUT if events else CaseExecutionOutcome.NO_OUTPUT
    )


def _build_inventory_runtime(
    model_id: str,
) -> tuple[object, object, str, _AsyncClosable, _AsyncClosable]:
    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
    from artana.ports.model import LiteLLMAdapter
    from artana_evidence_api.runtime import (
        ModelCapability,
        create_artana_postgres_store,
        get_model_registry,
        normalize_litellm_model_id,
    )

    configured = (
        get_model_registry()
        .get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
        )
        .model_id
    )
    if configured != model_id:
        raise RuntimeError(
            f"TG-04 requested {model_id}, but Artana configured {configured}",
        )
    store = create_artana_postgres_store()
    kernel = ArtanaKernel(
        store=store,
        model_port=LiteLLMAdapter(timeout_seconds=60.0),
    )
    return (
        SingleStepModelClient(kernel=kernel),
        TenantContext(
            tenant_id="tg04-nary-inventory",
            capabilities=frozenset(),
            budget_usd_limit=20.0,
        ),
        normalize_litellm_model_id(model_id),
        kernel,
        store,
    )


def _case_receipt_expectations(
    *,
    records: tuple[ModelAttemptAuditRecord, ...],
    case_id: str,
    model_id: str,
) -> tuple[list[ProviderReceiptExpectation], int, int]:
    expectations: list[ProviderReceiptExpectation] = []
    invalid_count = unidentified_count = 0
    for record in records:
        if record.validation_outcome == "intentionally_skipped":
            continue
        invalid_count += int(record.validation_outcome != "accepted")
        _require_attempt_model(record.model_id, model_id)
        unidentified_count += int(record.provider_response_id is None)
        if record.provider_response_id is not None:
            expectations.append(
                receipt_expectation_from_attempt(
                    case_id=case_id,
                    report_model_id=model_id,
                    record=record.as_json(),
                ),
            )
    return expectations, invalid_count, unidentified_count


def _nary_events(
    claims: tuple[BoundClaimInventoryItem, ...],
) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for claim in claims:
        item = claim.item.model_dump(mode="json")
        trigger_mention = claim.trigger_mention
        exact_span = item.get("exact_span")
        if not isinstance(exact_span, str):
            raise TypeError("TG-04 inventory exact_span must be text")
        raw_arguments = item.get("arguments", [])
        if not isinstance(raw_arguments, list):
            raise TypeError("TG-04 inventory arguments must be a list")
        arguments: list[dict[str, object]] = []
        for bound_argument, raw_argument in zip(
            claim.bound_arguments,
            raw_arguments,
            strict=True,
        ):
            if not isinstance(raw_argument, dict):
                raise TypeError("TG-04 inventory argument must be an object")
            argument_span = raw_argument.get("exact_span")
            if not isinstance(argument_span, str):
                raise TypeError("TG-04 inventory argument exact_span must be text")
            mentions = bound_argument.mentions
            arguments.append(
                {
                    **raw_argument,
                    "source_start": bound_argument.primary_mention.source_start,
                    "source_mentions": [
                        {
                            "exact_span": mention.exact_span,
                            "source_start": mention.source_start,
                            "source_end": mention.source_end,
                        }
                        for mention in mentions
                    ],
                },
            )
        events.append(
            {
                "inventory_id": claim.inventory_id,
                "source_start": claim.source_start,
                "source_end": claim.source_end,
                "exact_span": exact_span,
                "source_locator": item.get("source_locator"),
                "trigger_span": item.get("relation_cue_span"),
                "trigger_source_start": trigger_mention.source_start,
                "trigger_source_mention": {
                    "exact_span": trigger_mention.exact_span,
                    "source_start": trigger_mention.source_start,
                    "source_end": trigger_mention.source_end,
                },
                "relation_cue_span": item.get("relation_cue_span"),
                "relation_cue_anchor": item.get("relation_cue_anchor"),
                "event_type": item.get("event_type"),
                "polarity": item.get("polarity"),
                "epistemic_status": item.get("epistemic_status"),
                "arguments": arguments,
                "inventory_rationale": item.get("inventory_rationale"),
            },
        )
    return events


def _require_model(model_id: str) -> None:
    if model_id not in _ALLOWED_MODELS:
        raise ValueError(f"unsupported TG-04 model: {model_id}")


def receipt_expectation_from_attempt(
    *,
    case_id: str,
    report_model_id: str,
    record: dict[str, object],
) -> ProviderReceiptExpectation:
    def required(name: str) -> str:
        value = record.get(name)
        if not isinstance(value, str) or not value:
            raise RuntimeError(f"TG-04 provider attempt lacks {name}")
        return value

    payload_sha256 = record.get("payload_sha256")
    if payload_sha256 is not None and not isinstance(payload_sha256, str):
        raise TypeError("TG-04 payload_sha256 must be text or null")
    return ProviderReceiptExpectation(
        response_id=required("provider_response_id"),
        expected_case_id=case_id,
        expected_model_id=canonical_provider_model_id(report_model_id),
        expected_output_sha256=required("provider_output_sha256"),
        expected_payload_sha256=payload_sha256,
        expected_prompt_sha256=required("prompt_sha256"),
        expected_invocation_id=required("invocation_id"),
        expected_kernel_run_id=required("kernel_run_id"),
        expected_source_sha256=required("source_sha256"),
        expected_input_sha256=required("input_sha256"),
        expected_evidence_unit_sha256=required("evidence_unit_sha256"),
        expected_output_schema_sha256=_attempt_output_schema_sha256(record),
    )


def _attempt_output_schema_sha256(record: dict[str, object]) -> str:
    schema_role = record.get("pass_role")
    if schema_role == "claim_inventory":
        schema = build_claim_inventory_output_schema(64)
    elif schema_role == "claim_inventory_completeness":
        schema = build_claim_inventory_completeness_output_schema()
    elif schema_role == "claim_inventory_recovery":
        schema = build_missing_claim_recovery_output_schema()
    else:
        raise RuntimeError(
            f"TG-04 attempt has unsupported schema role: {schema_role}",
        )
    return output_schema_json_sha256(schema)


def _require_attempt_model(attempt_model_id: str, report_model_id: str) -> None:
    if attempt_model_id.replace("/", ":", 1) != report_model_id:
        raise RuntimeError(
            f"provider attempt model {attempt_model_id} differs from {report_model_id}",
        )


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = ["receipt_expectation_from_attempt", "run_live_arm"]
