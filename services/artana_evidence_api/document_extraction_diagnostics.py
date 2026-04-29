"""Diagnostics builders for document extraction flows."""

from __future__ import annotations

from typing import Literal

from artana_evidence_api.document_extraction_contracts import (
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
) -> DocumentCandidateExtractionDiagnostics:
    """Return diagnostics for a successful LLM candidate extraction."""

    return DocumentCandidateExtractionDiagnostics(
        llm_candidate_status="completed",
        llm_candidate_count=candidate_count,
    )


def candidate_llm_empty(
    *,
    fallback_candidate_count: int,
) -> DocumentCandidateExtractionDiagnostics:
    """Return diagnostics when the LLM succeeded but produced no usable claims."""

    return DocumentCandidateExtractionDiagnostics(
        llm_candidate_status="llm_empty",
        llm_candidate_error="LLM succeeded but returned zero usable candidates",
        fallback_candidate_count=fallback_candidate_count,
    )


def candidate_fallback(
    *,
    status: CandidateFallbackStatus,
    error: str,
    fallback_candidate_count: int,
) -> DocumentCandidateExtractionDiagnostics:
    """Return normalized diagnostics for candidate fallback paths."""

    return DocumentCandidateExtractionDiagnostics(
        llm_candidate_status=status,
        llm_candidate_error=error,
        fallback_candidate_count=fallback_candidate_count,
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
    "proposal_review_completed",
    "proposal_review_fallback_error",
    "proposal_review_not_needed",
    "proposal_review_unavailable",
    "runtime_error_candidate_status",
]
