"""Trust metadata helpers for variant-aware document extraction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING

from artana_evidence_api.document_extraction_contracts import (
    DocumentCandidateExtractionDiagnostics,
)
from artana_evidence_api.document_extraction_drafts import (
    candidate_extraction_trust_metadata,
    with_candidate_extraction_trust_metadata,
)
from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.review_item_store import HarnessReviewItemDraft
from artana_evidence_api.types.common import JSONObject, json_object_or_empty
from artana_evidence_api.variant_extraction_contracts import ExtractionContract

if TYPE_CHECKING:
    from artana_evidence_api.variant_aware_document_extraction import (
        VariantAwareDocumentExtractionResult,
    )


def variant_aware_candidate_diagnostics(
    *,
    contract: ExtractionContract,
    proposal_drafts: tuple[HarnessProposalDraft, ...],
    fallback_from_signals: bool = False,
) -> DocumentCandidateExtractionDiagnostics:
    """Map variant-aware extraction decisions into candidate trust diagnostics."""

    agent_candidate_count = (
        len(contract.entities) + len(contract.observations) + len(contract.relations)
    )
    if (
        contract.decision == "generated"
        and agent_candidate_count > 0
        and not fallback_from_signals
    ):
        return DocumentCandidateExtractionDiagnostics(
            llm_candidate_status="completed",
            llm_candidate_count=agent_candidate_count,
        )
    return DocumentCandidateExtractionDiagnostics(
        llm_candidate_status="fallback",
        fallback_candidate_count=len(proposal_drafts),
    )


def with_variant_aware_trust_metadata(
    result: VariantAwareDocumentExtractionResult,
) -> VariantAwareDocumentExtractionResult:
    """Attach extraction trust flags to variant-aware result metadata."""

    from artana_evidence_api.variant_aware_document_extraction import (
        VariantAwareDocumentExtractionResult,
    )

    diagnostics = variant_aware_candidate_diagnostics(
        contract=result.contract,
        proposal_drafts=result.proposal_drafts,
        fallback_from_signals=(
            result.extraction_diagnostics.get("fallback_from_signals") is True
        ),
    )
    trust_metadata = candidate_extraction_trust_metadata(diagnostics)
    return VariantAwareDocumentExtractionResult(
        contract=result.contract,
        proposal_drafts=with_candidate_extraction_trust_metadata(
            drafts=result.proposal_drafts,
            diagnostics=diagnostics,
        ),
        review_item_drafts=with_candidate_extraction_trust_review_metadata(
            review_items=result.review_item_drafts,
            diagnostics=diagnostics,
        ),
        skipped_items=result.skipped_items,
        candidate_discovery=result.candidate_discovery,
        extraction_diagnostics={
            **result.extraction_diagnostics,
            **trust_metadata,
        },
    )


def with_candidate_extraction_trust_review_metadata(
    *,
    review_items: tuple[HarnessReviewItemDraft, ...],
    diagnostics: DocumentCandidateExtractionDiagnostics,
) -> tuple[HarnessReviewItemDraft, ...]:
    """Attach candidate-extraction trust flags to review item drafts."""

    trust_metadata = candidate_extraction_trust_metadata(diagnostics)
    return tuple(
        replace(
            review_item,
            metadata={
                **review_item.metadata,
                **trust_metadata,
            },
            payload=_review_item_payload_with_trust_metadata(
                payload=review_item.payload,
                trust_metadata=trust_metadata,
            ),
        )
        for review_item in review_items
    )


def _review_item_payload_with_trust_metadata(
    *,
    payload: JSONObject,
    trust_metadata: JSONObject,
) -> JSONObject:
    proposal_draft_value = payload.get("proposal_draft")
    if not isinstance(proposal_draft_value, Mapping):
        return {**payload}
    proposal_draft = json_object_or_empty(proposal_draft_value)
    proposal_metadata = json_object_or_empty(proposal_draft.get("metadata"))
    return {
        **payload,
        "proposal_draft": {
            **proposal_draft,
            "metadata": {
                **proposal_metadata,
                **trust_metadata,
            },
        },
    }


__all__ = [
    "variant_aware_candidate_diagnostics",
    "with_variant_aware_trust_metadata",
]
