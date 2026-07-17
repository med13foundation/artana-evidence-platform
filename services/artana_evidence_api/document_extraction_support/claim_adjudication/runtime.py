"""Compose trust, semantic adjudication, and relevance review for document drafts."""

from __future__ import annotations

from dataclasses import replace

from artana_evidence_api import document_extraction
from artana_evidence_api.document_extraction_contracts import (
    DocumentCandidateExtractionDiagnostics,
    DocumentExtractionReviewContext,
    ExtractedRelationCandidate,
)
from artana_evidence_api.document_extraction_support.claim_adjudication.contracts import (
    ClaimAdjudicationDiagnostics,
)
from artana_evidence_api.document_extraction_support.claim_adjudication.service import (
    adjudicate_document_claims,
)
from artana_evidence_api.document_store import HarnessDocumentRecord
from artana_evidence_api.proposal_store import HarnessProposalDraft


async def adjudicate_and_review_document_drafts(
    *,
    document: HarnessDocumentRecord,
    candidates: list[ExtractedRelationCandidate],
    drafts: tuple[HarnessProposalDraft, ...],
    candidate_diagnostics: DocumentCandidateExtractionDiagnostics,
    review_context: DocumentExtractionReviewContext,
) -> tuple[HarnessProposalDraft, ...]:
    """Apply trust lineage, independent adjudication, and relevance review."""

    trusted_drafts = document_extraction.with_candidate_extraction_trust_metadata(
        drafts=drafts,
        diagnostics=candidate_diagnostics,
    )
    adjudicated_drafts, diagnostics = await adjudicate_document_claims(
        document=document,
        drafts=trusted_drafts,
    )
    adjudicated_drafts = with_claim_adjudication_diagnostics(
        drafts=adjudicated_drafts,
        diagnostics=diagnostics,
    )
    return await document_extraction.review_document_extraction_drafts(
        document=document,
        candidates=candidates,
        drafts=adjudicated_drafts,
        review_context=review_context,
    )


def with_claim_adjudication_diagnostics(
    *,
    drafts: tuple[HarnessProposalDraft, ...],
    diagnostics: ClaimAdjudicationDiagnostics,
) -> tuple[HarnessProposalDraft, ...]:
    """Persist the document-level adjudication outcome on research-init drafts."""

    serialized = diagnostics.as_metadata()
    return tuple(
        replace(
            draft,
            metadata={
                **draft.metadata,
                "claim_adjudication_diagnostics": serialized,
            },
        )
        if draft.proposal_type == "candidate_claim"
        else draft
        for draft in drafts
    )


__all__ = [
    "adjudicate_and_review_document_drafts",
    "with_claim_adjudication_diagnostics",
]
