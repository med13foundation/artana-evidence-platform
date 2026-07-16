"""Live TG-04 execution through Artana's strict audited agent path."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast
from uuid import uuid4

from artana_evidence_api.document_extraction_prompting import (
    build_claim_inventory_completeness_output_schema,
    build_claim_inventory_output_schema,
    build_missing_claim_recovery_output_schema,
    build_single_claim_framing_output_schema,
)
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    output_schema_json_sha256,
)

from scripts.validation.claim_events.fixture import require_frozen_development_fixture
from scripts.validation.claim_events.scoring import score_fixture
from scripts.validation.claim_frames.evidence import collect_repository_evidence
from scripts.validation.claim_frames.provider_receipts import (
    OpenAIProviderReceiptVerifier,
    ProviderReceiptExpectation,
    canonical_provider_model_id,
    verify_provider_receipts,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_contracts import (
        ClaimExtractionLineage,
    )

    from scripts.validation.claim_events.contracts import NaryClaimFixture
    from scripts.validation.claim_events.scoring import BenchmarkFixtureContract

_ALLOWED_MODELS: Final = frozenset(
    {"openai:gpt-5.6-luna", "openai:gpt-5.6-sol"},
)
_SPACE_CONTEXT: Final = "TG-04 untouched BioNLP event benchmark."
_REPO_ROOT: Final = Path(__file__).resolve().parents[3]
_TASK_ID: Final = "nary_event_inventory"


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
    from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
        start_model_attempt_audit,
        stop_model_attempt_audit,
    )
    from artana_evidence_api.document_extraction_support.strict_relation_discovery import (
        discover_relation_candidates_strict,
    )
    from artana_evidence_api.runtime import ModelCapability, get_model_registry

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

    predictions: list[dict[str, object]] = []
    case_evidence: list[dict[str, object]] = []
    provider_ids: set[str] = set()
    receipt_expectations: list[ProviderReceiptExpectation] = []
    fallback_count = invalid_count = unidentified_provider_count = 0
    for case in fixture.cases:
        invocation_namespace = f"tg04-{_TASK_ID}-{uuid4().hex}"
        audit = start_model_attempt_audit(evidence_unit_id=case.case_id)
        try:
            _candidates, diagnostics = await discover_relation_candidates_strict(
                case.source_text,
                max_relations=64,
                space_context=_SPACE_CONTEXT,
                execution_namespace=invocation_namespace,
            )
            events = _nary_events(diagnostics.claim_lineage)
            fallback_count += int(diagnostics.fallback_output_used)
        finally:
            stop_model_attempt_audit(audit)

        attempts = [record.as_json() for record in audit.records]
        for record in audit.records:
            if record.validation_outcome == "intentionally_skipped":
                continue
            invalid_count += int(record.validation_outcome != "accepted")
            _require_attempt_model(record.model_id, model_id)
            unidentified_provider_count += int(record.provider_response_id is None)
            if record.provider_response_id is not None:
                if record.provider_response_id in provider_ids:
                    raise RuntimeError("TG-04 provider response IDs must be unique")
                provider_ids.add(record.provider_response_id)
                receipt_expectations.append(
                    receipt_expectation_from_attempt(
                        case_id=case.case_id,
                        report_model_id=model_id,
                        record=record.as_json(),
                    ),
                )
        predictions.append(
            {
                "case_id": case.case_id,
                "events": events,
                "abstained": not events,
            },
        )
        case_evidence.append(
            {
                "case_id": case.case_id,
                "invocation_namespace": invocation_namespace,
                "attempts": attempts,
                "diagnostics": diagnostics.as_metadata(),
            },
        )

    final_repository_evidence = collect_repository_evidence(_REPO_ROOT)
    if final_repository_evidence != repository_evidence:
        raise RuntimeError("TG-04 repository state changed during the live run")
    score = score_fixture(cast("BenchmarkFixtureContract", fixture), predictions)
    provider_receipts = verify_provider_receipts(
        receipt_expectations,
        OpenAIProviderReceiptVerifier.from_environment(),
    )
    report: dict[str, object] = {
        "schema_version": "tg04_live_arm.v1",
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "fixture_sha256": fixture.sha256,
        "task_id": _TASK_ID,
        "model_id": model_id,
        "repository_evidence": repository_evidence,
        "predictions": predictions,
        "metrics": asdict(score.metrics),
        "case_scores": [asdict(case) for case in score.cases],
        "safety": {
            "fallback_count": fallback_count,
            "invalid_agent_output_count": invalid_count,
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


def _nary_events(
    lineage: tuple[ClaimExtractionLineage, ...],
) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for claim in lineage:
        item = claim.inventory_payload
        exact_span = item.get("exact_span")
        if not isinstance(exact_span, str):
            raise TypeError("TG-04 inventory exact_span must be text")
        raw_arguments = item.get("arguments", [])
        if not isinstance(raw_arguments, list):
            raise TypeError("TG-04 inventory arguments must be a list")
        arguments: list[dict[str, object]] = []
        for raw_argument in raw_arguments:
            if not isinstance(raw_argument, dict):
                raise TypeError("TG-04 inventory argument must be an object")
            argument_span = raw_argument.get("exact_span")
            if not isinstance(argument_span, str):
                raise TypeError("TG-04 inventory argument exact_span must be text")
            arguments.append(
                {
                    **raw_argument,
                    "source_start": claim.source_start
                    + exact_span.index(argument_span),
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
                "trigger_source_start": (
                    claim.source_start
                    + exact_span.index(str(item.get("relation_cue_span")))
                ),
                "relation_cue_span": item.get("relation_cue_span"),
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
    role = record.get("attempt_role")
    if role in {"claim_inventory", "zero_candidate_retry"}:
        schema = build_claim_inventory_output_schema(64)
    elif role == "claim_inventory_completeness":
        schema = build_claim_inventory_completeness_output_schema()
    elif role == "claim_inventory_recovery":
        schema = build_missing_claim_recovery_output_schema()
    elif role == "claim_framing":
        schema = build_single_claim_framing_output_schema()
    else:
        raise RuntimeError(f"TG-04 attempt has unsupported schema role: {role}")
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
