"""Diagnostics builders for document extraction flows."""

from __future__ import annotations

from typing import Literal

from artana_evidence_api.document_extraction_contracts import (
    ClaimExtractionLineage,
    ClaimExtractionRoutingStatus,
    DocumentCandidateExtractionDiagnostics,
    DocumentProposalReviewDiagnostics,
)

CandidateFallbackStatus = Literal["fallback_error", "unavailable"]


def candidate_not_needed() -> DocumentCandidateExtractionDiagnostics:
    """Return diagnostics for empty input where no extraction was needed."""

    return DocumentCandidateExtractionDiagnostics(llm_candidate_status="not_needed")


def candidate_completed(
    *,
    candidate_count: int,
    pruned_generic_relation_count: int = 0,
    quality_filtered_candidate_count: int = 0,
    llm_extraction_chunk_count: int = 0,
    llm_extraction_text_char_count: int = 0,
    claim_extraction_routing_status: ClaimExtractionRoutingStatus = "not_run",
    candidate_overflow_count: int = 0,
    claim_lineage: tuple[ClaimExtractionLineage, ...] = (),
    raw_agent_outputs: tuple[dict[str, object], ...] = (),
    model_attempt_records: tuple[dict[str, object], ...] = (),
    inventory_binding_rejections: tuple[dict[str, object], ...] = (),
) -> DocumentCandidateExtractionDiagnostics:
    """Return diagnostics for a successful LLM candidate extraction."""

    return DocumentCandidateExtractionDiagnostics(
        llm_candidate_status="completed",
        llm_candidate_count=candidate_count,
        pruned_generic_relation_count=pruned_generic_relation_count,
        quality_filtered_candidate_count=quality_filtered_candidate_count,
        llm_extraction_chunk_count=llm_extraction_chunk_count,
        llm_extraction_text_char_count=llm_extraction_text_char_count,
        claim_extraction_routing_status=claim_extraction_routing_status,
        candidate_overflow_count=candidate_overflow_count,
        claim_lineage=claim_lineage,
        raw_agent_outputs=raw_agent_outputs,
        model_attempt_records=model_attempt_records,
        inventory_binding_rejections=inventory_binding_rejections,
    )


def candidate_llm_empty(
    *,
    fallback_candidate_count: int,
    pruned_generic_relation_count: int = 0,
    quality_filtered_candidate_count: int = 0,
    llm_extraction_chunk_count: int = 0,
    llm_extraction_text_char_count: int = 0,
    claim_extraction_routing_status: ClaimExtractionRoutingStatus = "not_run",
    claim_lineage: tuple[ClaimExtractionLineage, ...] = (),
    raw_agent_outputs: tuple[dict[str, object], ...] = (),
    model_attempt_records: tuple[dict[str, object], ...] = (),
    inventory_binding_rejections: tuple[dict[str, object], ...] = (),
) -> DocumentCandidateExtractionDiagnostics:
    """Return diagnostics when the LLM succeeded but produced no usable claims."""

    return DocumentCandidateExtractionDiagnostics(
        llm_candidate_status="llm_empty",
        llm_candidate_error="LLM succeeded but returned zero usable candidates",
        fallback_candidate_count=fallback_candidate_count,
        pruned_generic_relation_count=pruned_generic_relation_count,
        quality_filtered_candidate_count=quality_filtered_candidate_count,
        llm_extraction_chunk_count=llm_extraction_chunk_count,
        llm_extraction_text_char_count=llm_extraction_text_char_count,
        claim_extraction_routing_status=claim_extraction_routing_status,
        claim_lineage=claim_lineage,
        raw_agent_outputs=raw_agent_outputs,
        model_attempt_records=model_attempt_records,
        inventory_binding_rejections=inventory_binding_rejections,
    )


def candidate_semantic_incomplete(
    *,
    claim_lineage: tuple[ClaimExtractionLineage, ...],
    raw_agent_outputs: tuple[dict[str, object], ...],
    model_attempt_records: tuple[dict[str, object], ...],
    inventory_binding_rejections: tuple[dict[str, object], ...],
    llm_extraction_chunk_count: int,
    llm_extraction_text_char_count: int,
) -> DocumentCandidateExtractionDiagnostics:
    """Return fail-closed diagnostics for an incomplete reviewed inventory."""

    return DocumentCandidateExtractionDiagnostics(
        llm_candidate_status="semantic_incomplete",
        llm_candidate_error=(
            "Inventory completeness remained INCOMPLETE after one agent recovery pass"
        ),
        llm_extraction_chunk_count=llm_extraction_chunk_count,
        llm_extraction_text_char_count=llm_extraction_text_char_count,
        claim_extraction_routing_status="semantic_incomplete",
        claim_lineage=claim_lineage,
        raw_agent_outputs=raw_agent_outputs,
        model_attempt_records=model_attempt_records,
        inventory_binding_rejections=inventory_binding_rejections,
    )


def candidate_fallback(
    *,
    status: CandidateFallbackStatus,
    error: str,
    fallback_candidate_count: int,
    pruned_generic_relation_count: int = 0,
    quality_filtered_candidate_count: int = 0,
) -> DocumentCandidateExtractionDiagnostics:
    """Return normalized diagnostics for candidate fallback paths."""

    return DocumentCandidateExtractionDiagnostics(
        llm_candidate_status=status,
        llm_candidate_error=error,
        fallback_candidate_count=fallback_candidate_count,
        pruned_generic_relation_count=pruned_generic_relation_count,
        quality_filtered_candidate_count=quality_filtered_candidate_count,
    )


def runtime_error_candidate_status(error: str) -> CandidateFallbackStatus:
    """Classify runtime errors into unavailable versus failed-fallback status."""

    if "OPENAI_API_KEY not configured" in error:
        return "unavailable"
    return "fallback_error"


def proposal_review_not_needed() -> DocumentProposalReviewDiagnostics:
    """Return diagnostics when there were no drafts to review."""

    return DocumentProposalReviewDiagnostics(llm_review_status="not_needed")


def proposal_review_unavailable(error: str) -> DocumentProposalReviewDiagnostics:
    """Return diagnostics for unavailable proposal-review infrastructure."""

    return DocumentProposalReviewDiagnostics(
        llm_review_status="unavailable",
        llm_review_error=error,
    )


def proposal_review_fallback_error(error: str) -> DocumentProposalReviewDiagnostics:
    """Return diagnostics when proposal review falls back after an attempted call."""

    return DocumentProposalReviewDiagnostics(
        llm_review_status="fallback_error",
        llm_review_error=error,
    )


def proposal_review_completed() -> DocumentProposalReviewDiagnostics:
    """Return diagnostics for a completed proposal-review LLM pass."""

    return DocumentProposalReviewDiagnostics(llm_review_status="completed")


__all__ = [
    "candidate_completed",
    "candidate_fallback",
    "candidate_llm_empty",
    "candidate_not_needed",
    "candidate_semantic_incomplete",
    "proposal_review_completed",
    "proposal_review_fallback_error",
    "proposal_review_not_needed",
    "proposal_review_unavailable",
    "runtime_error_candidate_status",
]
