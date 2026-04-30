"""Pydantic models for supervisor run routes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from artana_evidence_api.chat_graph_write_workflow import (
    ChatGraphWriteCandidateRequest,
)
from artana_evidence_api.routers.chat import (
    ChatGraphWriteProposalRecordResponse,
    ChatMessageRunResponse,
)
from artana_evidence_api.routers.graph_curation_runs import ClaimCurationRunResponse
from artana_evidence_api.routers.research_bootstrap_runs import (
    ResearchBootstrapRunResponse,
)
from artana_evidence_api.routers.runs import (
    HarnessRunProgressResponse,
    HarnessRunResponse,
)
from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field


class SupervisorRunRequest(BaseModel):
    """Request payload for one composed supervisor workflow run."""

    model_config = ConfigDict(strict=True)

    objective: str | None = Field(default=None, min_length=1, max_length=4000)
    seed_entity_ids: list[str] | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, min_length=1, max_length=256)
    source_type: str = Field(default="pubmed", min_length=1, max_length=64)
    relation_types: list[str] | None = Field(default=None, max_length=200)
    max_depth: int = Field(default=2, ge=1, le=4)
    max_hypotheses: int = Field(default=20, ge=1, le=100)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    include_chat: bool = True
    include_curation: bool = True
    curation_source: str = Field(
        default="bootstrap",
        pattern="^(bootstrap|chat_graph_write)$",
    )
    briefing_question: str | None = Field(default=None, min_length=1, max_length=4000)
    chat_max_depth: int = Field(default=2, ge=1, le=4)
    chat_top_k: int = Field(default=10, ge=1, le=25)
    chat_include_evidence_chains: bool = True
    curation_proposal_limit: int = Field(default=5, ge=1, le=25)


class SupervisorStepResponse(BaseModel):
    """One composed step result within a supervisor run."""

    model_config = ConfigDict(strict=True)

    step: str
    status: str
    harness_id: str | None
    run_id: str | None
    detail: str


class SupervisorRunResponse(BaseModel):
    """Combined response for one supervisor orchestration run."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    bootstrap: ResearchBootstrapRunResponse
    chat: ChatMessageRunResponse | None
    curation: ClaimCurationRunResponse | None
    briefing_question: str | None
    curation_source: str
    chat_graph_write_proposal_ids: list[str]
    selected_curation_proposal_ids: list[str]
    chat_graph_write_review_count: int
    latest_chat_graph_write_review: SupervisorChatGraphWriteReviewResponse | None
    chat_graph_write_reviews: list[SupervisorChatGraphWriteReviewResponse]
    steps: list[SupervisorStepResponse]


class SupervisorChatGraphWriteReviewResponse(BaseModel):
    """One typed supervisor briefing-chat graph-write review record."""

    model_config = ConfigDict(strict=True)

    reviewed_at: str
    chat_run_id: str
    chat_session_id: str
    candidate_index: int
    decision: str
    decision_status: str
    proposal_id: str
    proposal_status: str
    graph_claim_id: str | None = None
    candidate: ChatGraphWriteCandidateRequest


class SupervisorRunDetailResponse(BaseModel):
    """Persisted supervisor run state for typed reloads."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    progress: HarnessRunProgressResponse
    workflow: str
    bootstrap: ResearchBootstrapRunResponse
    chat: ChatMessageRunResponse | None
    curation: ClaimCurationRunResponse | None
    artifact_keys: SupervisorArtifactKeysResponse
    bootstrap_run_id: str
    chat_run_id: str | None
    chat_session_id: str | None
    chat_graph_write_run_id: str | None
    curation_run_id: str | None
    briefing_question: str | None
    curation_source: str
    curation_status: str | None
    completed_at: str | None
    chat_graph_write_proposal_ids: list[str]
    selected_curation_proposal_ids: list[str]
    skipped_steps: list[str]
    chat_graph_write_review_count: int
    latest_chat_graph_write_review: SupervisorChatGraphWriteReviewResponse | None
    chat_graph_write_reviews: list[SupervisorChatGraphWriteReviewResponse]
    steps: list[SupervisorStepResponse]
    curation_summary: JSONObject | None
    curation_actions: JSONObject | None


class SupervisorBootstrapArtifactKeysResponse(BaseModel):
    """Child bootstrap artifact keys exposed through supervisor state."""

    model_config = ConfigDict(strict=True)

    graph_context_snapshot: str
    graph_summary: str
    research_brief: str
    source_inventory: str
    candidate_claim_pack: str


class SupervisorChatArtifactKeysResponse(BaseModel):
    """Child chat artifact keys exposed through supervisor state."""

    model_config = ConfigDict(strict=True)

    graph_chat_result: str
    chat_summary: str
    grounded_answer_verification: str
    memory_context: str
    graph_write_candidate_suggestions: str | None
    fresh_literature: str | None


class SupervisorCurationArtifactKeysResponse(BaseModel):
    """Child curation artifact keys exposed through supervisor state."""

    model_config = ConfigDict(strict=True)

    curation_packet: str
    review_plan: str
    approval_intent: str
    curation_summary: str | None
    curation_actions: str | None


class SupervisorArtifactKeysResponse(BaseModel):
    """Parent and child artifact keys for one supervisor run."""

    model_config = ConfigDict(strict=True)

    supervisor_plan: str
    supervisor_summary: str
    child_run_links: str
    bootstrap: SupervisorBootstrapArtifactKeysResponse
    chat: SupervisorChatArtifactKeysResponse | None
    curation: SupervisorCurationArtifactKeysResponse | None


class SupervisorRunListResponse(BaseModel):
    """Typed list response for supervisor workflow runs."""

    model_config = ConfigDict(strict=True)

    summary: SupervisorRunListSummaryResponse
    runs: list[SupervisorRunDetailResponse]
    total: int


class SupervisorDashboardResponse(BaseModel):
    """Typed dashboard response for supervisor workflow summaries."""

    model_config = ConfigDict(strict=True)

    summary: SupervisorRunListSummaryResponse
    highlights: SupervisorDashboardHighlightsResponse


class SupervisorDashboardRunPointerResponse(BaseModel):
    """One dashboard deep-link pointer to a supervisor run."""

    model_config = ConfigDict(strict=True)

    run_id: str
    title: str
    status: str
    curation_source: str
    timestamp: str


class SupervisorDashboardApprovalRunPointerResponse(BaseModel):
    """One dashboard deep-link pointer for approval-focused supervisor highlights."""

    model_config = ConfigDict(strict=True)

    run_id: str
    title: str
    status: str
    curation_source: str
    timestamp: str
    pending_approval_count: int
    curation_run_id: str | None
    curation_packet_key: str | None
    review_plan_key: str | None
    approval_intent_key: str | None


class SupervisorDashboardHighlightsResponse(BaseModel):
    """Typed dashboard deep-link highlights for supervisor workflows."""

    model_config = ConfigDict(strict=True)

    latest_completed_run: SupervisorDashboardRunPointerResponse | None
    latest_reviewed_run: SupervisorDashboardRunPointerResponse | None
    oldest_paused_run: SupervisorDashboardRunPointerResponse | None
    latest_bootstrap_run: SupervisorDashboardRunPointerResponse | None
    latest_chat_graph_write_run: SupervisorDashboardRunPointerResponse | None
    latest_approval_paused_run: SupervisorDashboardApprovalRunPointerResponse | None
    largest_pending_review_run: SupervisorDashboardApprovalRunPointerResponse | None
    largest_pending_bootstrap_review_run: (
        SupervisorDashboardApprovalRunPointerResponse | None
    )
    largest_pending_chat_graph_write_review_run: (
        SupervisorDashboardApprovalRunPointerResponse | None
    )


class SupervisorRunListSummaryResponse(BaseModel):
    """Aggregate dashboard-style counts for a typed supervisor list."""

    model_config = ConfigDict(strict=True)

    total_runs: int
    paused_run_count: int
    completed_run_count: int
    reviewed_run_count: int
    unreviewed_run_count: int
    bootstrap_curation_run_count: int
    chat_graph_write_curation_run_count: int
    trends: SupervisorRunTrendSummaryResponse


class SupervisorRunDailyCountResponse(BaseModel):
    """One UTC day bucket in the supervisor list trend summary."""

    model_config = ConfigDict(strict=True)

    day: str
    count: int


class SupervisorRunTrendSummaryResponse(BaseModel):
    """Trend buckets for a typed supervisor list summary."""

    model_config = ConfigDict(strict=True)

    recent_24h_count: int
    recent_7d_count: int
    recent_completed_24h_count: int
    recent_completed_7d_count: int
    recent_reviewed_24h_count: int
    recent_reviewed_7d_count: int
    daily_created_counts: list[SupervisorRunDailyCountResponse]
    daily_completed_counts: list[SupervisorRunDailyCountResponse]
    daily_reviewed_counts: list[SupervisorRunDailyCountResponse]
    daily_unreviewed_counts: list[SupervisorRunDailyCountResponse]
    daily_bootstrap_curation_counts: list[SupervisorRunDailyCountResponse]
    daily_chat_graph_write_curation_counts: list[SupervisorRunDailyCountResponse]


@dataclass(frozen=True, slots=True)
class _SupervisorRunListFilters:
    status_filter: str | None
    curation_source_filter: str | None
    has_chat_graph_write_reviews: bool | None
    created_after: datetime | None
    created_before: datetime | None
    updated_after: datetime | None
    updated_before: datetime | None


class SupervisorChatGraphWriteCandidateDecisionResponse(BaseModel):
    """Decision result for one supervisor briefing-chat graph-write candidate."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    chat_run_id: str
    chat_session_id: str
    candidate_index: int
    candidate: ChatGraphWriteCandidateRequest
    proposal: ChatGraphWriteProposalRecordResponse
    chat_graph_write_review_count: int
    latest_chat_graph_write_review: SupervisorChatGraphWriteReviewResponse | None
    chat_graph_write_reviews: list[SupervisorChatGraphWriteReviewResponse]




__all__ = [
    "SupervisorArtifactKeysResponse",
    "SupervisorBootstrapArtifactKeysResponse",
    "SupervisorChatArtifactKeysResponse",
    "SupervisorChatGraphWriteCandidateDecisionResponse",
    "SupervisorChatGraphWriteReviewResponse",
    "SupervisorCurationArtifactKeysResponse",
    "SupervisorDashboardApprovalRunPointerResponse",
    "SupervisorDashboardHighlightsResponse",
    "SupervisorDashboardResponse",
    "SupervisorDashboardRunPointerResponse",
    "SupervisorRunDailyCountResponse",
    "SupervisorRunDetailResponse",
    "SupervisorRunListResponse",
    "SupervisorRunListSummaryResponse",
    "SupervisorRunRequest",
    "SupervisorRunResponse",
    "SupervisorRunTrendSummaryResponse",
    "SupervisorStepResponse",
    "_SupervisorRunListFilters",
]
