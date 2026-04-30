"""Artifact and progress helpers for research-init runs."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.alias_yield_reporting import source_results_with_alias_yield
from artana_evidence_api.bootstrap_proposal_review import (
    review_bootstrap_enrichment_proposals,
)
from artana_evidence_api.research_init_models import (
    ResearchInitProgressObserver,
    ResearchInitPubMedResultRecord,
)
from artana_evidence_api.types.common import (
    JSONObject,
    ResearchSpaceSourcePreferences,
    json_object_or_empty,
)

if TYPE_CHECKING:
    from artana_evidence_api.harness_runtime import HarnessExecutionServices
    from artana_evidence_api.proposal_store import (
        HarnessProposalDraft,
        HarnessProposalStore,
    )
    from artana_evidence_api.research_bootstrap_runtime import (
        ResearchBootstrapClaimCurationSummary,
    )

_TOTAL_PROGRESS_STEPS = 5


def store_reviewed_enrichment_proposals(
    *,
    proposal_store: HarnessProposalStore,
    proposals: list[HarnessProposalDraft],
    space_id: UUID,
    run_id: UUID | str,
    objective: str,
) -> int:
    """Store reviewed bootstrap proposals without direct graph promotion."""
    logger = logging.getLogger(__name__)
    if not proposals:
        return 0
    reviewed_proposals = review_bootstrap_enrichment_proposals(
        proposals,
        objective=objective,
    )
    created_records = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run_id,
        proposals=reviewed_proposals,
    )
    if created_records:
        logger.info(
            "Stored %d/%d reviewed bootstrap enrichment proposals for space %s",
            len(created_records),
            len(proposals),
            space_id,
        )
    return len(created_records)


def serialize_research_state(state: object) -> JSONObject | None:
    """Serialize the small research-state shape stored in result artifacts."""
    if state is None:
        return None
    space_id = getattr(state, "space_id", None)
    if not isinstance(space_id, UUID | str):
        return None
    return {
        "space_id": str(space_id),
        "objective": getattr(state, "objective", None),
        "current_hypotheses": list(getattr(state, "current_hypotheses", [])),
        "explored_questions": list(getattr(state, "explored_questions", [])),
        "pending_questions": list(getattr(state, "pending_questions", [])),
    }


def research_init_result_payload(
    *,
    run_id: str,
    selected_sources: ResearchSpaceSourcePreferences,
    source_results: dict[str, JSONObject],
    pubmed_results: list[ResearchInitPubMedResultRecord],
    documents_ingested: int,
    proposal_count: int,
    research_state: JSONObject | None,
    pending_questions: list[str],
    errors: list[str],
    claim_curation: JSONObject | None = None,
    research_brief_markdown: str | None = None,
) -> JSONObject:
    """Build the terminal research-init result artifact payload."""
    serialized_source_results = source_results_with_alias_yield(source_results)
    result: JSONObject = {
        "run_id": run_id,
        "selected_sources": json_object_or_empty(selected_sources),
        "source_results": serialized_source_results,
        "pubmed_results": [
            {
                "query": result_item.query,
                "total_found": result_item.total_found,
                "abstracts_ingested": result_item.abstracts_ingested,
            }
            for result_item in pubmed_results
        ],
        "documents_ingested": documents_ingested,
        "proposal_count": proposal_count,
        "research_state": research_state,
        "pending_questions": list(pending_questions),
        "errors": list(errors),
        "claim_curation": claim_curation,
    }
    if research_brief_markdown is not None:
        result["research_brief_markdown"] = research_brief_markdown
    return result


def serialize_claim_curation_summary(
    summary: ResearchBootstrapClaimCurationSummary | None,
) -> JSONObject | None:
    """Serialize the claim-curation summary exposed in result artifacts."""
    if summary is None:
        return None
    return {
        "status": summary.status,
        "run_id": summary.run_id,
        "proposal_ids": list(summary.proposal_ids),
        "proposal_count": summary.proposal_count,
        "blocked_proposal_count": summary.blocked_proposal_count,
        "pending_approval_count": summary.pending_approval_count,
        "reason": summary.reason,
    }


def set_research_init_progress(
    *,
    services: HarnessExecutionServices,
    space_id: UUID,
    run_id: str,
    phase: str,
    message: str,
    progress_percent: float,
    completed_steps: int,
    metadata: JSONObject | None = None,
    progress_observer: ResearchInitProgressObserver | None = None,
) -> None:
    """Set run progress and notify the optional research-init observer."""
    resolved_metadata = {} if metadata is None else metadata
    services.run_registry.set_progress(
        space_id=space_id,
        run_id=run_id,
        phase=phase,
        message=message,
        progress_percent=progress_percent,
        completed_steps=completed_steps,
        total_steps=_TOTAL_PROGRESS_STEPS,
        metadata=resolved_metadata,
        merge_existing=False,
    )
    if progress_observer is None:
        return
    try:
        workspace_record = services.artifact_store.get_workspace(
            space_id=space_id,
            run_id=run_id,
        )
    except TimeoutError:
        logging.getLogger(__name__).warning(
            "Skipped research-init progress workspace hydration after timeout",
            extra={"run_id": run_id, "space_id": str(space_id)},
        )
        workspace_record = None
    progress_observer.on_progress(
        phase=phase,
        message=message,
        progress_percent=progress_percent,
        completed_steps=completed_steps,
        metadata=resolved_metadata,
        workspace_snapshot=(
            workspace_record.snapshot if workspace_record is not None else {}
        ),
    )


__all__ = [
    "research_init_result_payload",
    "serialize_claim_curation_summary",
    "serialize_research_state",
    "set_research_init_progress",
    "store_reviewed_enrichment_proposals",
]
