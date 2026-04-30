"""Research-bootstrap result models and claim-curation helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.claim_curation_workflow import (
    ClaimCurationNoEligibleProposalsError,
    execute_claim_curation_run_for_proposals,
)

if TYPE_CHECKING:
    from artana_evidence_api.approval_store import HarnessApprovalStore
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotRecord
    from artana_evidence_api.proposal_store import (
        HarnessProposalRecord,
        HarnessProposalStore,
    )
    from artana_evidence_api.research_state import HarnessResearchStateRecord
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
    from artana_evidence_api.types.common import JSONObject
    from artana_evidence_api.types.graph_contracts import (
        KernelEntityEmbeddingStatusListResponse,
    )

@dataclass(frozen=True, slots=True)
class ResearchBootstrapExecutionResult:
    """One completed research-bootstrap execution result."""

    run: HarnessRunRecord
    graph_snapshot: HarnessGraphSnapshotRecord
    research_state: HarnessResearchStateRecord
    research_brief: JSONObject
    graph_summary: JSONObject
    source_inventory: JSONObject
    proposal_records: list[HarnessProposalRecord]
    pending_questions: list[str]
    errors: list[str]
    claim_curation: ResearchBootstrapClaimCurationSummary | None = None


@dataclass(frozen=True, slots=True)
class ResearchBootstrapClaimCurationSummary:
    """One optional governed claim-curation follow-up for bootstrap proposals."""

    status: str
    run_id: str | None
    proposal_ids: tuple[str, ...]
    proposal_count: int
    blocked_proposal_count: int
    pending_approval_count: int
    reason: str | None = None


def _embedding_readiness_payload(
    *,
    status_response: KernelEntityEmbeddingStatusListResponse,
) -> JSONObject:
    ready_count = 0
    pending_count = 0
    failed_count = 0
    stale_count = 0
    skipped_source_ids: list[str] = []
    for status_row in status_response.statuses:
        normalized_state = status_row.state.strip().lower()
        if normalized_state == "ready":
            ready_count += 1
            continue
        skipped_source_ids.append(str(status_row.entity_id))
        if normalized_state == "failed":
            failed_count += 1
        elif normalized_state == "stale":
            stale_count += 1
        else:
            pending_count += 1
    return {
        "statuses": [
            status_row.model_dump(mode="json")
            for status_row in status_response.statuses
        ],
        "embedding_ready_seed_count": ready_count,
        "embedding_pending_seed_count": pending_count,
        "embedding_failed_seed_count": failed_count,
        "embedding_stale_seed_count": stale_count,
        "skipped_relation_suggestion_source_ids": skipped_source_ids,
    }


def _claim_curation_summary_payload(
    summary: ResearchBootstrapClaimCurationSummary,
) -> JSONObject:
    return {
        "status": summary.status,
        "run_id": summary.run_id,
        "proposal_ids": list(summary.proposal_ids),
        "proposal_count": summary.proposal_count,
        "blocked_proposal_count": summary.blocked_proposal_count,
        "pending_approval_count": summary.pending_approval_count,
        "reason": summary.reason,
    }


def _select_bootstrap_claim_curation_proposals(
    *,
    proposals: list[HarnessProposalRecord],
    limit: int,
) -> list[HarnessProposalRecord]:
    bounded_limit = max(limit, 1)
    selected = [
        proposal
        for proposal in proposals
        if proposal.proposal_type == "candidate_claim"
        and proposal.status == "pending_review"
    ]
    return selected[:bounded_limit]


def _maybe_start_bootstrap_claim_curation(  # noqa: PLR0913
    *,
    space_id: UUID,
    proposals: list[HarnessProposalRecord],
    proposal_limit: int,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    proposal_store: HarnessProposalStore,
    approval_store: HarnessApprovalStore | None,
    graph_api_gateway_factory: Callable[[], GraphTransportBundle] | None,
    runtime: GraphHarnessKernelRuntime,
) -> tuple[ResearchBootstrapClaimCurationSummary | None, list[str]]:
    if approval_store is None or graph_api_gateway_factory is None:
        return None, []

    curatable_proposals = _select_bootstrap_claim_curation_proposals(
        proposals=proposals,
        limit=proposal_limit,
    )
    if not curatable_proposals:
        return None, []

    try:
        execution = execute_claim_curation_run_for_proposals(
            space_id=space_id,
            proposals=curatable_proposals,
            title="Claim Curation Harness",
            run_registry=run_registry,
            artifact_store=artifact_store,
            proposal_store=proposal_store,
            approval_store=approval_store,
            graph_api_gateway=graph_api_gateway_factory(),
            runtime=runtime,
        )
    except ClaimCurationNoEligibleProposalsError as exc:
        summary = ResearchBootstrapClaimCurationSummary(
            status="skipped",
            run_id=None,
            proposal_ids=tuple(proposal.id for proposal in curatable_proposals),
            proposal_count=len(curatable_proposals),
            blocked_proposal_count=len(curatable_proposals),
            pending_approval_count=0,
            reason=str(exc),
        )
        return summary, [f"claim_curation:{exc}"]
    except Exception as exc:  # noqa: BLE001
        summary = ResearchBootstrapClaimCurationSummary(
            status="failed",
            run_id=None,
            proposal_ids=tuple(proposal.id for proposal in curatable_proposals),
            proposal_count=len(curatable_proposals),
            blocked_proposal_count=0,
            pending_approval_count=0,
            reason=f"Failed to initialize claim curation: {exc}",
        )
        return summary, [f"claim_curation:Failed to initialize claim curation: {exc}"]

    return (
        ResearchBootstrapClaimCurationSummary(
            status=execution.run.status,
            run_id=execution.run.id,
            proposal_ids=tuple(proposal.id for proposal in curatable_proposals),
            proposal_count=execution.proposal_count,
            blocked_proposal_count=execution.blocked_proposal_count,
            pending_approval_count=execution.pending_approval_count,
            reason=None,
        ),
        [],
    )




__all__ = [
    "ResearchBootstrapClaimCurationSummary",
    "ResearchBootstrapExecutionResult",
    "_claim_curation_summary_payload",
    "_embedding_readiness_payload",
    "_maybe_start_bootstrap_claim_curation",
]
