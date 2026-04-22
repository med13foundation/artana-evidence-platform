"""Chunked extraction execution helpers."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.application.agents.services._extraction_chunking_helpers import (
    ChunkedExtractionSummary,
    build_chunk_context,
    build_full_text_chunks,
    merge_chunk_contracts,
    should_use_full_text_chunking,
)
from src.domain.agents.contracts import RejectedFact
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from src.domain.agents.contexts.extraction_context import ExtractionContext
    from src.domain.agents.contracts.extraction import ExtractionContract
    from src.domain.agents.ports.extraction_agent_port import ExtractionAgentPort
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)


async def extract_contract_with_optional_chunking(
    *,
    agent: ExtractionAgentPort,
    context: ExtractionContext,
    model_id: str | None,
) -> tuple[ExtractionContract, ChunkedExtractionSummary]:
    started_at = datetime.now(UTC)
    logger.info(
        "Extraction chunk execution started",
        extra={
            "document_id": context.document_id,
            "source_type": context.source_type,
            "model_id": model_id,
        },
    )
    if not should_use_full_text_chunking(context):
        single_started_at = datetime.now(UTC)
        contract = await agent.extract(context, model_id=model_id)
        logger.info(
            "Extraction chunk execution finished in single mode",
            extra={
                "document_id": context.document_id,
                "duration_ms": int(
                    (datetime.now(UTC) - started_at).total_seconds() * 1000,
                ),
                "single_call_duration_ms": int(
                    (datetime.now(UTC) - single_started_at).total_seconds() * 1000,
                ),
                "decision": contract.decision,
                "relations_count": len(contract.relations),
                "observations_count": len(contract.observations),
            },
        )
        return (
            contract,
            ChunkedExtractionSummary(
                mode="single",
                chunk_count=0,
                successful_chunks=1,
                failed_chunks=0,
            ),
        )

    chunks = build_full_text_chunks(context)
    if not chunks:
        single_started_at = datetime.now(UTC)
        contract = await agent.extract(context, model_id=model_id)
        logger.info(
            "Extraction chunk execution fell back to single mode (no chunks built)",
            extra={
                "document_id": context.document_id,
                "duration_ms": int(
                    (datetime.now(UTC) - started_at).total_seconds() * 1000,
                ),
                "single_call_duration_ms": int(
                    (datetime.now(UTC) - single_started_at).total_seconds() * 1000,
                ),
                "decision": contract.decision,
                "relations_count": len(contract.relations),
                "observations_count": len(contract.observations),
            },
        )
        return (
            contract,
            ChunkedExtractionSummary(
                mode="single",
                chunk_count=0,
                successful_chunks=1,
                failed_chunks=0,
            ),
        )

    logger.info(
        "Extraction chunk execution entering chunked mode",
        extra={
            "document_id": context.document_id,
            "chunk_count": len(chunks),
            "model_id": model_id,
        },
    )
    chunk_contracts: list[ExtractionContract] = []
    failed_chunk_payloads: list[JSONObject] = []
    for chunk in chunks:
        chunk_context = build_chunk_context(base_context=context, chunk=chunk)
        chunk_started_at = datetime.now(UTC)
        logger.info(
            "Chunked extraction chunk started",
            extra={
                "document_id": context.document_id,
                "chunk_index": chunk.index + 1,
                "chunk_total": chunk.total,
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
                "model_id": model_id,
            },
        )
        try:
            chunk_contract = await agent.extract(
                chunk_context,
                model_id=model_id,
            )
        except (
            RuntimeError,
            ValueError,
            TypeError,
            LookupError,
            OSError,
            ConnectionError,
            TimeoutError,
        ) as exc:
            logger.warning(
                (
                    "Chunked extraction failed for document_id=%s chunk=%d/%d "
                    "model_id=%s: %s"
                ),
                context.document_id,
                chunk.index + 1,
                chunk.total,
                model_id or "default",
                exc,
                exc_info=True,
            )
            logger.warning(
                "Chunked extraction chunk failed",
                extra={
                    "document_id": context.document_id,
                    "chunk_index": chunk.index + 1,
                    "chunk_total": chunk.total,
                    "duration_ms": int(
                        (datetime.now(UTC) - chunk_started_at).total_seconds() * 1000,
                    ),
                    "error_class": type(exc).__name__,
                },
            )
            failed_chunk_payloads.append(
                {
                    "chunk_index": chunk.index,
                    "chunk_total": chunk.total,
                    "start_char": chunk.start_char,
                    "end_char": chunk.end_char,
                    "reason": f"chunk_execution_error:{type(exc).__name__}",
                    "error_class": type(exc).__name__,
                    "error_message": str(exc)[:500],
                },
            )
            continue
        if _is_chunk_level_failure(chunk_contract):
            failure_reason = _chunk_failure_reason(chunk_contract)
            failure_details = _chunk_failure_details(chunk_contract)
            logger.warning(
                (
                    "Chunked extraction returned escalation for document_id=%s "
                    "chunk=%d/%d reason=%s model_id=%s"
                ),
                context.document_id,
                chunk.index + 1,
                chunk.total,
                failure_reason,
                model_id or "default",
            )
            logger.warning(
                "Chunked extraction chunk escalated as failure",
                extra={
                    "document_id": context.document_id,
                    "chunk_index": chunk.index + 1,
                    "chunk_total": chunk.total,
                    "duration_ms": int(
                        (datetime.now(UTC) - chunk_started_at).total_seconds() * 1000,
                    ),
                    "failure_reason": failure_reason,
                },
            )
            failed_chunk_payloads.append(
                {
                    "chunk_index": chunk.index,
                    "chunk_total": chunk.total,
                    "start_char": chunk.start_char,
                    "end_char": chunk.end_char,
                    "reason": failure_reason,
                    "failure_details": to_json_value(failure_details),
                },
            )
            continue
        chunk_contracts.append(chunk_contract)
        logger.info(
            "Chunked extraction chunk finished",
            extra={
                "document_id": context.document_id,
                "chunk_index": chunk.index + 1,
                "chunk_total": chunk.total,
                "duration_ms": int(
                    (datetime.now(UTC) - chunk_started_at).total_seconds() * 1000,
                ),
                "decision": chunk_contract.decision,
                "relations_count": len(chunk_contract.relations),
                "observations_count": len(chunk_contract.observations),
                "rejected_facts_count": len(chunk_contract.rejected_facts),
            },
        )

    if not chunk_contracts:
        fallback_started_at = datetime.now(UTC)
        logger.warning(
            "Chunked extraction produced no successful chunks; running single-call fallback",
            extra={
                "document_id": context.document_id,
                "failed_chunk_count": len(failed_chunk_payloads),
                "chunk_count": len(chunks),
                "model_id": model_id,
            },
        )
        fallback_contract = await agent.extract(context, model_id=model_id)
        if failed_chunk_payloads:
            append_chunk_failure_rejections(
                contract=fallback_contract,
                failure_payloads=failed_chunk_payloads,
            )
        logger.info(
            "Extraction chunk execution finished in chunked fallback mode",
            extra={
                "document_id": context.document_id,
                "duration_ms": int(
                    (datetime.now(UTC) - started_at).total_seconds() * 1000,
                ),
                "fallback_call_duration_ms": int(
                    (datetime.now(UTC) - fallback_started_at).total_seconds() * 1000,
                ),
                "chunk_count": len(chunks),
                "failed_chunk_count": len(failed_chunk_payloads),
                "decision": fallback_contract.decision,
                "relations_count": len(fallback_contract.relations),
                "observations_count": len(fallback_contract.observations),
            },
        )
        return (
            fallback_contract,
            ChunkedExtractionSummary(
                mode="chunked_fallback_single",
                chunk_count=len(chunks),
                successful_chunks=0,
                failed_chunks=len(failed_chunk_payloads),
            ),
        )

    merged_contract = merge_chunk_contracts(
        base_context=context,
        contracts=tuple(chunk_contracts),
    )
    if failed_chunk_payloads:
        append_chunk_failure_rejections(
            contract=merged_contract,
            failure_payloads=failed_chunk_payloads,
        )
    logger.info(
        "Extraction chunk execution finished in chunked mode",
        extra={
            "document_id": context.document_id,
            "duration_ms": int((datetime.now(UTC) - started_at).total_seconds() * 1000),
            "chunk_count": len(chunks),
            "successful_chunk_count": len(chunk_contracts),
            "failed_chunk_count": len(failed_chunk_payloads),
            "decision": merged_contract.decision,
            "relations_count": len(merged_contract.relations),
            "observations_count": len(merged_contract.observations),
            "rejected_facts_count": len(merged_contract.rejected_facts),
        },
    )
    return (
        merged_contract,
        ChunkedExtractionSummary(
            mode="chunked",
            chunk_count=len(chunks),
            successful_chunks=len(chunk_contracts),
            failed_chunks=len(failed_chunk_payloads),
        ),
    )


def _is_chunk_level_failure(contract: ExtractionContract) -> bool:
    if contract.decision != "escalate":
        return False
    if (
        contract.entities
        or contract.observations
        or contract.relations
        or contract.rejected_facts
        or contract.pipeline_payloads
    ):
        return False
    rationale = contract.rationale.strip().lower()
    if "pipeline_execution_failed" in rationale:
        return True
    return any(
        "ai extraction unavailable" in evidence.excerpt.strip().lower()
        for evidence in contract.evidence
    )


def _chunk_failure_reason(contract: ExtractionContract) -> str:
    rationale = contract.rationale.strip()
    marker = "pipeline_execution_failed:"
    if marker in rationale:
        suffix = rationale.split(marker, maxsplit=1)[1].strip()
        if suffix:
            return f"chunk_pipeline_failed:{suffix[:120]}"
    open_paren = rationale.rfind("(")
    close_paren = rationale.rfind(")")
    if open_paren != -1 and close_paren > open_paren:
        fallback_suffix = rationale[open_paren + 1 : close_paren].strip()
        if fallback_suffix:
            return f"chunk_pipeline_failed:{fallback_suffix[:120]}"
    for evidence in contract.evidence:
        excerpt = evidence.excerpt.strip()
        lowered = excerpt.lower()
        prefix = "ai extraction unavailable:"
        if lowered.startswith(prefix):
            detail = excerpt[len(prefix) :].strip()
            if detail:
                return f"chunk_pipeline_failed:{detail[:120]}"
            return "chunk_pipeline_failed:ai_unavailable"
        if "ai extraction unavailable" in lowered:
            return "chunk_pipeline_failed:ai_unavailable"
    return "chunk_pipeline_failed:unknown"


def _chunk_failure_details(contract: ExtractionContract) -> dict[str, object]:
    evidence_excerpt: str | None = None
    if contract.evidence:
        excerpt = contract.evidence[0].excerpt.strip()
        if excerpt:
            evidence_excerpt = excerpt[:500]
    return {
        "decision": contract.decision,
        "confidence_score": contract.confidence_score,
        "agent_run_id": contract.agent_run_id,
        "rationale": contract.rationale[:1000],
        "evidence_excerpt": evidence_excerpt,
    }


def append_chunk_failure_rejections(
    *,
    contract: ExtractionContract,
    failure_payloads: list[JSONObject],
) -> None:
    for payload in failure_payloads:
        reason = payload.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            normalized_reason = "chunk_pipeline_failed:unknown"
        else:
            normalized_reason = reason.strip()[:255]
        normalized_payload: JSONObject = {
            str(key): to_json_value(value) for key, value in payload.items()
        }
        contract.rejected_facts.append(
            RejectedFact(
                fact_type="relation",
                reason=normalized_reason,
                payload=normalized_payload,
            ),
        )


__all__ = ["extract_contract_with_optional_chunking"]
