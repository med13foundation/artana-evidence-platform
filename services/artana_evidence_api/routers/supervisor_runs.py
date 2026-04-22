"""Harness-owned supervisor run endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta  # noqa: TC003
from typing import Annotated
from uuid import UUID  # noqa: TC003

from artana_evidence_api.artifact_store import (
    HarnessArtifactStore,  # noqa: TC001
)
from artana_evidence_api.auth import (
    get_current_harness_user,
)
from artana_evidence_api.chat_graph_write_workflow import (
    ChatGraphWriteArtifactError,
    ChatGraphWriteCandidateError,
    ChatGraphWriteCandidateRequest,
    ChatGraphWriteVerificationError,
)
from artana_evidence_api.config import get_settings
from artana_evidence_api.dependencies import (
    get_approval_store,
    get_artifact_store,
    get_chat_session_store,
    get_graph_api_gateway,
    get_graph_chat_runner,
    get_graph_snapshot_store,
    get_harness_execution_services,
    get_proposal_store,
    get_research_state_store,
    get_run_registry,
    get_schedule_store,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.graph_client import (
    GraphServiceClientError,
    GraphTransportBundle,  # noqa: TC001
)
from artana_evidence_api.proposal_actions import (
    decide_proposal,
    promote_to_graph_claim,
)
from artana_evidence_api.proposal_store import (
    HarnessProposalStore,  # noqa: TC001
)
from artana_evidence_api.queued_run_support import (
    HarnessAcceptedRunResponse,
    build_accepted_run_response,
    load_primary_result_artifact,
    maybe_execute_test_worker_run,
    prefers_respond_async,
    raise_for_failed_run,
    require_worker_ready,
    should_require_worker_ready,
    wait_for_terminal_run,
    wake_worker_for_queued_run,
)
from artana_evidence_api.research_bootstrap_runtime import (
    normalize_bootstrap_seed_entity_ids,
)
from artana_evidence_api.routers.chat import (
    ChatGraphWriteCandidateDecisionRequest,
    ChatGraphWriteProposalRecordResponse,
    ChatMessageRunResponse,
    _ensure_pending_chat_graph_write_proposal,
    _require_reviewable_chat_graph_write_candidate,
    build_chat_message_run_response,
)
from artana_evidence_api.routers.graph_curation_runs import (
    ClaimCurationRunResponse,
    build_claim_curation_run_response,
)
from artana_evidence_api.routers.research_bootstrap_runs import (
    ResearchBootstrapRunResponse,
    build_research_bootstrap_run_response,
)
from artana_evidence_api.routers.runs import (
    HarnessRunProgressResponse,
    HarnessRunResponse,
)
from artana_evidence_api.run_registry import (
    HarnessRunRecord,  # noqa: TC001
    HarnessRunRegistry,  # noqa: TC001
)
from artana_evidence_api.supervisor_runtime import (
    SupervisorExecutionResult,
    is_supervisor_workflow,
    queue_supervisor_run,
)
from artana_evidence_api.transparency import (
    append_manual_review_decision,
    ensure_run_transparency_seed,
)
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(
    prefix="/v1/spaces",
    tags=["supervisor-runs"],
)

_CURRENT_USER_DEPENDENCY = Depends(get_current_harness_user)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_CHAT_SESSION_STORE_DEPENDENCY = Depends(get_chat_session_store)
_PROPOSAL_STORE_DEPENDENCY = Depends(get_proposal_store)
_APPROVAL_STORE_DEPENDENCY = Depends(get_approval_store)
_RESEARCH_STATE_STORE_DEPENDENCY = Depends(get_research_state_store)
_GRAPH_SNAPSHOT_STORE_DEPENDENCY = Depends(get_graph_snapshot_store)
_SCHEDULE_STORE_DEPENDENCY = Depends(get_schedule_store)
_GRAPH_CHAT_RUNNER_DEPENDENCY = Depends(get_graph_chat_runner)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)
_PARENT_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway, use_cache=False)
_BOOTSTRAP_GRAPH_API_GATEWAY_DEPENDENCY = Depends(
    get_graph_api_gateway,
    use_cache=False,
)
_CHAT_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway, use_cache=False)
_CURATION_GRAPH_API_GATEWAY_DEPENDENCY = Depends(
    get_graph_api_gateway,
    use_cache=False,
)
_STATUS_QUERY = Query(default=None, alias="status", min_length=1, max_length=32)
_CURATION_SOURCE_QUERY = Query(default=None, min_length=1, max_length=32)
_HAS_CHAT_GRAPH_WRITE_REVIEWS_QUERY = Query(default=None)
_OFFSET_QUERY = Query(default=0, ge=0, le=10_000)
_LIMIT_QUERY = Query(default=50, ge=1, le=200)
_SORT_BY_QUERY = Query(
    default="created_at",
    pattern="^(created_at|updated_at|chat_graph_write_review_count)$",
)
_SORT_DIRECTION_QUERY = Query(default="desc", pattern="^(asc|desc)$")
_CREATED_AFTER_QUERY = Query(default=None)
_CREATED_BEFORE_QUERY = Query(default=None)
_UPDATED_AFTER_QUERY = Query(default=None)
_UPDATED_BEFORE_QUERY = Query(default=None)


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


def _build_supervisor_chat_graph_write_review_responses(
    *,
    summary: dict[str, object],
) -> list[SupervisorChatGraphWriteReviewResponse]:
    return [
        SupervisorChatGraphWriteReviewResponse.model_validate(review)
        for review in _supervisor_review_history(summary=summary)
    ]


def _require_supervisor_summary(
    *,
    space_id: UUID,
    run_id: str,
    artifact_store: HarnessArtifactStore,
) -> JSONObject:
    summary = _supervisor_summary(
        space_id=space_id,
        run_id=run_id,
        artifact_store=artifact_store,
    )
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Supervisor run '{run_id}' is missing the canonical "
                "'supervisor_summary' artifact"
            ),
        )
    return summary


def _require_supervisor_progress(
    *,
    space_id: UUID,
    run_id: str,
    run_registry: HarnessRunRegistry,
) -> HarnessRunProgressResponse:
    progress = run_registry.get_progress(space_id=space_id, run_id=run_id)
    if progress is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Supervisor run '{run_id}' is missing lifecycle progress state",
        )
    return HarnessRunProgressResponse.from_record(progress)


def _summary_string(
    summary: JSONObject,
    key: str,
) -> str | None:
    value = summary.get(key)
    if isinstance(value, str) and value.strip() != "":
        return value
    return None


def _summary_string_list(
    summary: JSONObject,
    key: str,
) -> list[str]:
    raw_values = summary.get(key)
    if not isinstance(raw_values, list):
        return []
    return [
        value for value in raw_values if isinstance(value, str) and value.strip() != ""
    ]


def _summary_object(
    summary: JSONObject,
    key: str,
) -> JSONObject | None:
    value = summary.get(key)
    if isinstance(value, dict):
        return value
    return None


def _require_summary_object(
    summary: JSONObject,
    key: str,
    *,
    run_id: str,
) -> JSONObject:
    value = _summary_object(summary, key)
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Supervisor run '{run_id}' is missing the canonical "
                f"'{key}' summary field"
            ),
        )
    return value


def _summary_steps(
    *,
    summary: JSONObject,
) -> list[SupervisorStepResponse]:
    raw_steps = summary.get("steps")
    if not isinstance(raw_steps, list):
        return []
    return [
        SupervisorStepResponse.model_validate(step)
        for step in raw_steps
        if isinstance(step, dict)
    ]


def _bootstrap_detail_response(
    *,
    summary: JSONObject,
    run_id: str,
) -> ResearchBootstrapRunResponse:
    return ResearchBootstrapRunResponse.model_validate(
        _require_summary_object(summary, "bootstrap_response", run_id=run_id),
        strict=False,
    )


def _chat_detail_response(
    *,
    summary: JSONObject,
) -> ChatMessageRunResponse | None:
    payload = _summary_object(summary, "chat_response")
    if payload is None:
        return None
    return ChatMessageRunResponse.model_validate(payload, strict=False)


def _curation_detail_response(
    *,
    summary: JSONObject,
) -> ClaimCurationRunResponse | None:
    payload = _summary_object(summary, "curation_response")
    if payload is None:
        return None
    return ClaimCurationRunResponse.model_validate(payload, strict=False)


def _supervisor_artifact_keys_response(
    *,
    chat: ChatMessageRunResponse | None,
    curation: ClaimCurationRunResponse | None,
    curation_summary: JSONObject | None,
    curation_actions: JSONObject | None,
) -> SupervisorArtifactKeysResponse:
    return SupervisorArtifactKeysResponse(
        supervisor_plan="supervisor_plan",
        supervisor_summary="supervisor_summary",
        child_run_links="child_run_links",
        bootstrap=SupervisorBootstrapArtifactKeysResponse(
            graph_context_snapshot="graph_context_snapshot",
            graph_summary="graph_summary",
            research_brief="research_brief",
            source_inventory="source_inventory",
            candidate_claim_pack="candidate_claim_pack",
        ),
        chat=(
            SupervisorChatArtifactKeysResponse(
                graph_chat_result="graph_chat_result",
                chat_summary="chat_summary",
                grounded_answer_verification="grounded_answer_verification",
                memory_context="memory_context",
                graph_write_candidate_suggestions=(
                    "graph_write_candidate_suggestions"
                    if chat is not None
                    and chat.result.verification.status == "verified"
                    else None
                ),
                fresh_literature=(
                    "fresh_literature"
                    if chat is not None and chat.result.fresh_literature is not None
                    else None
                ),
            )
            if chat is not None
            else None
        ),
        curation=(
            SupervisorCurationArtifactKeysResponse(
                curation_packet="curation_packet",
                review_plan="review_plan",
                approval_intent="approval_intent",
                curation_summary=(
                    "curation_summary" if curation_summary is not None else None
                ),
                curation_actions=(
                    "curation_actions" if curation_actions is not None else None
                ),
            )
            if curation is not None
            else None
        ),
    )


def build_supervisor_run_detail_response(
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    artifact_store: HarnessArtifactStore,
    run_registry: HarnessRunRegistry,
) -> SupervisorRunDetailResponse:
    """Serialize the persisted supervisor summary into one typed detail response."""
    summary = _require_supervisor_summary(
        space_id=space_id,
        run_id=run.id,
        artifact_store=artifact_store,
    )
    bootstrap_run_id = _summary_string(summary, "bootstrap_run_id")
    curation_source = _summary_string(summary, "curation_source")
    workflow = _summary_string(summary, "workflow")
    if bootstrap_run_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Supervisor run '{run.id}' is missing the canonical "
                "'bootstrap_run_id' summary field"
            ),
        )
    if curation_source is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Supervisor run '{run.id}' is missing the canonical "
                "'curation_source' summary field"
            ),
        )
    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Supervisor run '{run.id}' is missing the canonical "
                "'workflow' summary field"
            ),
        )
    review_responses = _build_supervisor_chat_graph_write_review_responses(
        summary=summary,
    )
    bootstrap = _bootstrap_detail_response(summary=summary, run_id=run.id)
    chat = _chat_detail_response(summary=summary)
    curation = _curation_detail_response(summary=summary)
    curation_summary = _summary_object(summary, "curation_summary")
    curation_actions = _summary_object(summary, "curation_actions")
    return SupervisorRunDetailResponse(
        run=HarnessRunResponse.from_record(run),
        progress=_require_supervisor_progress(
            space_id=space_id,
            run_id=run.id,
            run_registry=run_registry,
        ),
        workflow=workflow,
        bootstrap=bootstrap,
        chat=chat,
        curation=curation,
        artifact_keys=_supervisor_artifact_keys_response(
            chat=chat,
            curation=curation,
            curation_summary=curation_summary,
            curation_actions=curation_actions,
        ),
        bootstrap_run_id=bootstrap_run_id,
        chat_run_id=_summary_string(summary, "chat_run_id"),
        chat_session_id=_summary_string(summary, "chat_session_id"),
        chat_graph_write_run_id=_summary_string(summary, "chat_graph_write_run_id"),
        curation_run_id=_summary_string(summary, "curation_run_id"),
        briefing_question=_summary_string(summary, "briefing_question"),
        curation_source=curation_source,
        curation_status=_summary_string(summary, "curation_status"),
        completed_at=_summary_string(summary, "completed_at"),
        chat_graph_write_proposal_ids=_summary_string_list(
            summary,
            "chat_graph_write_proposal_ids",
        ),
        selected_curation_proposal_ids=_summary_string_list(
            summary,
            "selected_curation_proposal_ids",
        ),
        skipped_steps=_summary_string_list(summary, "skipped_steps"),
        chat_graph_write_review_count=len(review_responses),
        latest_chat_graph_write_review=(
            review_responses[-1] if review_responses else None
        ),
        chat_graph_write_reviews=review_responses,
        steps=_summary_steps(summary=summary),
        curation_summary=curation_summary,
        curation_actions=curation_actions,
    )


def _matches_supervisor_list_filters(
    *,
    detail: SupervisorRunDetailResponse,
    filters: _SupervisorRunListFilters,
) -> bool:
    created_at = _normalized_filter_datetime(
        datetime.fromisoformat(detail.run.created_at),
    )
    updated_at = _normalized_filter_datetime(
        datetime.fromisoformat(detail.run.updated_at),
    )
    normalized_status_filter = (
        filters.status_filter.strip()
        if isinstance(filters.status_filter, str)
        and filters.status_filter.strip() != ""
        else None
    )
    normalized_curation_source_filter = (
        filters.curation_source_filter.strip()
        if isinstance(filters.curation_source_filter, str)
        and filters.curation_source_filter.strip() != ""
        else None
    )
    has_reviews = detail.chat_graph_write_review_count > 0
    return (
        (
            normalized_status_filter is None
            or detail.run.status == normalized_status_filter
        )
        and (
            normalized_curation_source_filter is None
            or detail.curation_source == normalized_curation_source_filter
        )
        and (
            filters.has_chat_graph_write_reviews is None
            or has_reviews == filters.has_chat_graph_write_reviews
        )
        and (filters.created_after is None or created_at >= filters.created_after)
        and (filters.created_before is None or created_at <= filters.created_before)
        and (filters.updated_after is None or updated_at >= filters.updated_after)
        and (filters.updated_before is None or updated_at <= filters.updated_before)
    )


def _normalized_filter_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _supervisor_sort_key(
    *,
    detail: SupervisorRunDetailResponse,
    sort_by: str,
) -> tuple[str | int, str]:
    if sort_by == "updated_at":
        return detail.run.updated_at, detail.run.id
    if sort_by == "chat_graph_write_review_count":
        return detail.chat_graph_write_review_count, detail.run.id
    return detail.run.created_at, detail.run.id


def _optional_iso_datetime(value: str | None) -> datetime | None:
    if not isinstance(value, str) or value.strip() == "":
        return None
    return _normalized_filter_datetime(datetime.fromisoformat(value))


def _recent_window_deltas(
    *,
    value: datetime | None,
    recent_24h_threshold: datetime,
    recent_7d_threshold: datetime,
) -> tuple[int, int]:
    if value is None:
        return 0, 0
    return int(value >= recent_24h_threshold), int(value >= recent_7d_threshold)


def _increment_daily_count(
    *,
    buckets: dict[str, int],
    value: datetime | None,
) -> None:
    if value is None:
        return
    day_key = value.date().isoformat()
    buckets[day_key] = buckets.get(day_key, 0) + 1


def _supervisor_list_trends(
    *,
    runs: list[SupervisorRunDetailResponse],
) -> SupervisorRunTrendSummaryResponse:
    now = datetime.now(UTC)
    recent_24h_threshold = now.replace(microsecond=0) - timedelta(hours=24)
    recent_7d_threshold = now.replace(microsecond=0) - timedelta(days=7)
    recent_24h_count = 0
    recent_7d_count = 0
    recent_completed_24h_count = 0
    recent_completed_7d_count = 0
    recent_reviewed_24h_count = 0
    recent_reviewed_7d_count = 0
    daily_created_counts: dict[str, int] = {}
    daily_completed_counts: dict[str, int] = {}
    daily_reviewed_counts: dict[str, int] = {}
    daily_unreviewed_counts: dict[str, int] = {}
    daily_bootstrap_curation_counts: dict[str, int] = {}
    daily_chat_graph_write_curation_counts: dict[str, int] = {}
    for run in runs:
        created_at = _normalized_filter_datetime(
            datetime.fromisoformat(run.run.created_at),
        )
        created_recent_24h_delta, created_recent_7d_delta = _recent_window_deltas(
            value=created_at,
            recent_24h_threshold=recent_24h_threshold,
            recent_7d_threshold=recent_7d_threshold,
        )
        recent_24h_count += created_recent_24h_delta
        recent_7d_count += created_recent_7d_delta
        _increment_daily_count(buckets=daily_created_counts, value=created_at)
        if run.chat_graph_write_review_count <= 0:
            _increment_daily_count(buckets=daily_unreviewed_counts, value=created_at)
        if run.curation_source == "bootstrap":
            _increment_daily_count(
                buckets=daily_bootstrap_curation_counts,
                value=created_at,
            )
        if run.curation_source == "chat_graph_write":
            _increment_daily_count(
                buckets=daily_chat_graph_write_curation_counts,
                value=created_at,
            )
        completed_at = _optional_iso_datetime(run.completed_at)
        completed_recent_24h_delta, completed_recent_7d_delta = _recent_window_deltas(
            value=completed_at,
            recent_24h_threshold=recent_24h_threshold,
            recent_7d_threshold=recent_7d_threshold,
        )
        recent_completed_24h_count += completed_recent_24h_delta
        recent_completed_7d_count += completed_recent_7d_delta
        _increment_daily_count(buckets=daily_completed_counts, value=completed_at)
        latest_review = run.latest_chat_graph_write_review
        reviewed_at = (
            _optional_iso_datetime(latest_review.reviewed_at)
            if latest_review is not None
            else None
        )
        reviewed_recent_24h_delta, reviewed_recent_7d_delta = _recent_window_deltas(
            value=reviewed_at,
            recent_24h_threshold=recent_24h_threshold,
            recent_7d_threshold=recent_7d_threshold,
        )
        recent_reviewed_24h_count += reviewed_recent_24h_delta
        recent_reviewed_7d_count += reviewed_recent_7d_delta
        _increment_daily_count(buckets=daily_reviewed_counts, value=reviewed_at)
    return SupervisorRunTrendSummaryResponse(
        recent_24h_count=recent_24h_count,
        recent_7d_count=recent_7d_count,
        recent_completed_24h_count=recent_completed_24h_count,
        recent_completed_7d_count=recent_completed_7d_count,
        recent_reviewed_24h_count=recent_reviewed_24h_count,
        recent_reviewed_7d_count=recent_reviewed_7d_count,
        daily_created_counts=[
            SupervisorRunDailyCountResponse(day=day, count=count)
            for day, count in sorted(daily_created_counts.items())
        ],
        daily_completed_counts=[
            SupervisorRunDailyCountResponse(day=day, count=count)
            for day, count in sorted(daily_completed_counts.items())
        ],
        daily_reviewed_counts=[
            SupervisorRunDailyCountResponse(day=day, count=count)
            for day, count in sorted(daily_reviewed_counts.items())
        ],
        daily_unreviewed_counts=[
            SupervisorRunDailyCountResponse(day=day, count=count)
            for day, count in sorted(daily_unreviewed_counts.items())
        ],
        daily_bootstrap_curation_counts=[
            SupervisorRunDailyCountResponse(day=day, count=count)
            for day, count in sorted(daily_bootstrap_curation_counts.items())
        ],
        daily_chat_graph_write_curation_counts=[
            SupervisorRunDailyCountResponse(day=day, count=count)
            for day, count in sorted(daily_chat_graph_write_curation_counts.items())
        ],
    )


def _supervisor_list_summary(
    *,
    runs: list[SupervisorRunDetailResponse],
) -> SupervisorRunListSummaryResponse:
    paused_run_count = 0
    completed_run_count = 0
    reviewed_run_count = 0
    bootstrap_curation_run_count = 0
    chat_graph_write_curation_run_count = 0
    for run in runs:
        if run.run.status == "paused":
            paused_run_count += 1
        if run.run.status == "completed":
            completed_run_count += 1
        if run.chat_graph_write_review_count > 0:
            reviewed_run_count += 1
        if run.curation_source == "bootstrap":
            bootstrap_curation_run_count += 1
        if run.curation_source == "chat_graph_write":
            chat_graph_write_curation_run_count += 1
    return SupervisorRunListSummaryResponse(
        total_runs=len(runs),
        paused_run_count=paused_run_count,
        completed_run_count=completed_run_count,
        reviewed_run_count=reviewed_run_count,
        unreviewed_run_count=len(runs) - reviewed_run_count,
        bootstrap_curation_run_count=bootstrap_curation_run_count,
        chat_graph_write_curation_run_count=chat_graph_write_curation_run_count,
        trends=_supervisor_list_trends(runs=runs),
    )


def _dashboard_run_pointer(
    *,
    run: SupervisorRunDetailResponse,
    timestamp: str,
) -> SupervisorDashboardRunPointerResponse:
    return SupervisorDashboardRunPointerResponse(
        run_id=run.run.id,
        title=run.run.title,
        status=run.run.status,
        curation_source=run.curation_source,
        timestamp=timestamp,
    )


def _dashboard_approval_run_pointer(
    *,
    run: SupervisorRunDetailResponse,
    timestamp: str,
    pending_approval_count: int,
) -> SupervisorDashboardApprovalRunPointerResponse:
    curation_artifact_keys = run.artifact_keys.curation
    return SupervisorDashboardApprovalRunPointerResponse(
        run_id=run.run.id,
        title=run.run.title,
        status=run.run.status,
        curation_source=run.curation_source,
        timestamp=timestamp,
        pending_approval_count=pending_approval_count,
        curation_run_id=run.curation_run_id,
        curation_packet_key=(
            curation_artifact_keys.curation_packet
            if curation_artifact_keys is not None
            else None
        ),
        review_plan_key=(
            curation_artifact_keys.review_plan
            if curation_artifact_keys is not None
            else None
        ),
        approval_intent_key=(
            curation_artifact_keys.approval_intent
            if curation_artifact_keys is not None
            else None
        ),
    )


def _preferred_pending_review_candidate(
    *,
    current: tuple[int, datetime, SupervisorRunDetailResponse] | None,
    pending_approval_count: int,
    created_at: datetime,
    run: SupervisorRunDetailResponse,
) -> tuple[int, datetime, SupervisorRunDetailResponse] | None:
    if pending_approval_count <= 0:
        return current
    if current is None:
        return (pending_approval_count, created_at, run)
    if pending_approval_count > current[0]:
        return (pending_approval_count, created_at, run)
    if pending_approval_count == current[0] and created_at > current[1]:
        return (pending_approval_count, created_at, run)
    return current


def _supervisor_dashboard_highlights(
    *,
    runs: list[SupervisorRunDetailResponse],
) -> SupervisorDashboardHighlightsResponse:
    latest_completed_run: tuple[datetime, SupervisorRunDetailResponse] | None = None
    latest_reviewed_run: tuple[datetime, SupervisorRunDetailResponse] | None = None
    oldest_paused_run: tuple[datetime, SupervisorRunDetailResponse] | None = None
    latest_bootstrap_run: tuple[datetime, SupervisorRunDetailResponse] | None = None
    latest_chat_graph_write_run: tuple[datetime, SupervisorRunDetailResponse] | None = (
        None
    )
    latest_approval_paused_run: (
        tuple[
            datetime,
            SupervisorRunDetailResponse,
            int,
        ]
        | None
    ) = None
    largest_pending_review_run: (
        tuple[
            int,
            datetime,
            SupervisorRunDetailResponse,
        ]
        | None
    ) = None
    largest_pending_bootstrap_review_run: (
        tuple[
            int,
            datetime,
            SupervisorRunDetailResponse,
        ]
        | None
    ) = None
    largest_pending_chat_graph_write_review_run: (
        tuple[
            int,
            datetime,
            SupervisorRunDetailResponse,
        ]
        | None
    ) = None
    for run in runs:
        created_at = _normalized_filter_datetime(
            datetime.fromisoformat(run.run.created_at),
        )
        pending_approval_count = (
            run.curation.pending_approval_count if run.curation is not None else 0
        )
        completed_at = _optional_iso_datetime(run.completed_at)
        if completed_at is not None and (
            latest_completed_run is None or completed_at > latest_completed_run[0]
        ):
            latest_completed_run = (completed_at, run)
        latest_review = run.latest_chat_graph_write_review
        reviewed_at = (
            _optional_iso_datetime(latest_review.reviewed_at)
            if latest_review is not None
            else None
        )
        if reviewed_at is not None and (
            latest_reviewed_run is None or reviewed_at > latest_reviewed_run[0]
        ):
            latest_reviewed_run = (reviewed_at, run)
        if run.run.status == "paused" and (
            oldest_paused_run is None or created_at < oldest_paused_run[0]
        ):
            oldest_paused_run = (created_at, run)
        if pending_approval_count > 0 and (
            latest_approval_paused_run is None
            or created_at > latest_approval_paused_run[0]
        ):
            latest_approval_paused_run = (created_at, run, pending_approval_count)
        largest_pending_review_run = _preferred_pending_review_candidate(
            current=largest_pending_review_run,
            pending_approval_count=pending_approval_count,
            created_at=created_at,
            run=run,
        )
        if run.curation_source == "bootstrap" and (
            latest_bootstrap_run is None or created_at > latest_bootstrap_run[0]
        ):
            latest_bootstrap_run = (created_at, run)
        if run.curation_source == "bootstrap":
            largest_pending_bootstrap_review_run = _preferred_pending_review_candidate(
                current=largest_pending_bootstrap_review_run,
                pending_approval_count=pending_approval_count,
                created_at=created_at,
                run=run,
            )
        if run.curation_source == "chat_graph_write" and (
            latest_chat_graph_write_run is None
            or created_at > latest_chat_graph_write_run[0]
        ):
            latest_chat_graph_write_run = (created_at, run)
        if run.curation_source == "chat_graph_write":
            largest_pending_chat_graph_write_review_run = (
                _preferred_pending_review_candidate(
                    current=largest_pending_chat_graph_write_review_run,
                    pending_approval_count=pending_approval_count,
                    created_at=created_at,
                    run=run,
                )
            )
    return SupervisorDashboardHighlightsResponse(
        latest_completed_run=(
            _dashboard_run_pointer(
                run=latest_completed_run[1],
                timestamp=latest_completed_run[0].isoformat(),
            )
            if latest_completed_run is not None
            else None
        ),
        latest_reviewed_run=(
            _dashboard_run_pointer(
                run=latest_reviewed_run[1],
                timestamp=latest_reviewed_run[0].isoformat(),
            )
            if latest_reviewed_run is not None
            else None
        ),
        oldest_paused_run=(
            _dashboard_run_pointer(
                run=oldest_paused_run[1],
                timestamp=oldest_paused_run[0].isoformat(),
            )
            if oldest_paused_run is not None
            else None
        ),
        latest_bootstrap_run=(
            _dashboard_run_pointer(
                run=latest_bootstrap_run[1],
                timestamp=latest_bootstrap_run[0].isoformat(),
            )
            if latest_bootstrap_run is not None
            else None
        ),
        latest_chat_graph_write_run=(
            _dashboard_run_pointer(
                run=latest_chat_graph_write_run[1],
                timestamp=latest_chat_graph_write_run[0].isoformat(),
            )
            if latest_chat_graph_write_run is not None
            else None
        ),
        latest_approval_paused_run=(
            _dashboard_approval_run_pointer(
                run=latest_approval_paused_run[1],
                timestamp=latest_approval_paused_run[0].isoformat(),
                pending_approval_count=latest_approval_paused_run[2],
            )
            if latest_approval_paused_run is not None
            else None
        ),
        largest_pending_review_run=(
            _dashboard_approval_run_pointer(
                run=largest_pending_review_run[2],
                timestamp=largest_pending_review_run[1].isoformat(),
                pending_approval_count=largest_pending_review_run[0],
            )
            if largest_pending_review_run is not None
            else None
        ),
        largest_pending_bootstrap_review_run=(
            _dashboard_approval_run_pointer(
                run=largest_pending_bootstrap_review_run[2],
                timestamp=largest_pending_bootstrap_review_run[1].isoformat(),
                pending_approval_count=largest_pending_bootstrap_review_run[0],
            )
            if largest_pending_bootstrap_review_run is not None
            else None
        ),
        largest_pending_chat_graph_write_review_run=(
            _dashboard_approval_run_pointer(
                run=largest_pending_chat_graph_write_review_run[2],
                timestamp=largest_pending_chat_graph_write_review_run[1].isoformat(),
                pending_approval_count=largest_pending_chat_graph_write_review_run[0],
            )
            if largest_pending_chat_graph_write_review_run is not None
            else None
        ),
    )


def _normalized_supervisor_filters(  # noqa: PLR0913
    *,
    status_filter: str | None,
    curation_source: str | None,
    has_chat_graph_write_reviews: bool | None,
    created_after: datetime | None,
    created_before: datetime | None,
    updated_after: datetime | None,
    updated_before: datetime | None,
) -> _SupervisorRunListFilters:
    return _SupervisorRunListFilters(
        status_filter=status_filter,
        curation_source_filter=curation_source,
        has_chat_graph_write_reviews=has_chat_graph_write_reviews,
        created_after=(
            _normalized_filter_datetime(created_after)
            if created_after is not None
            else None
        ),
        created_before=(
            _normalized_filter_datetime(created_before)
            if created_before is not None
            else None
        ),
        updated_after=(
            _normalized_filter_datetime(updated_after)
            if updated_after is not None
            else None
        ),
        updated_before=(
            _normalized_filter_datetime(updated_before)
            if updated_before is not None
            else None
        ),
    )


def _filtered_supervisor_run_details(
    *,
    space_id: UUID,
    filters: _SupervisorRunListFilters,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> list[SupervisorRunDetailResponse]:
    supervisor_runs = [
        run
        for run in run_registry.list_runs(space_id=space_id)
        if is_supervisor_workflow(run)
    ]
    return [
        detail
        for run in supervisor_runs
        for detail in [
            build_supervisor_run_detail_response(
                space_id=space_id,
                run=run,
                artifact_store=artifact_store,
                run_registry=run_registry,
            ),
        ]
        if _matches_supervisor_list_filters(
            detail=detail,
            filters=filters,
        )
    ]


def build_supervisor_run_response(
    result: SupervisorExecutionResult,
) -> SupervisorRunResponse:
    """Serialize one supervisor execution result for HTTP responses."""
    return SupervisorRunResponse(
        run=HarnessRunResponse.from_record(result.run),
        bootstrap=build_research_bootstrap_run_response(result.bootstrap),
        chat=(
            build_chat_message_run_response(result.chat)
            if result.chat is not None
            else None
        ),
        curation=(
            build_claim_curation_run_response(result.curation)
            if result.curation is not None
            else None
        ),
        briefing_question=result.briefing_question,
        curation_source=result.curation_source,
        chat_graph_write_proposal_ids=[
            proposal.id
            for proposal in (
                result.chat_graph_write.proposals
                if result.chat_graph_write is not None
                else []
            )
        ],
        selected_curation_proposal_ids=list(result.selected_curation_proposal_ids),
        chat_graph_write_review_count=0,
        latest_chat_graph_write_review=None,
        chat_graph_write_reviews=[],
        steps=[SupervisorStepResponse.model_validate(step) for step in result.steps],
    )


def _require_supervisor_run_record(
    *,
    space_id: UUID,
    run_id: UUID,
    run_registry: HarnessRunRegistry,
):
    run = run_registry.get_run(space_id=space_id, run_id=run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found in space '{space_id}'",
        )
    if not is_supervisor_workflow(run):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run '{run_id}' is not a supervisor workflow run",
        )
    return run


def _supervisor_summary(
    *,
    space_id: UUID,
    run_id: str,
    artifact_store: HarnessArtifactStore,
) -> dict[str, object]:
    summary_artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key="supervisor_summary",
    )
    if summary_artifact is None:
        return {}
    return summary_artifact.content


def _require_supervisor_briefing_chat_context(
    *,
    space_id: UUID,
    supervisor_run_id: str,
    artifact_store: HarnessArtifactStore,
) -> tuple[str, str]:
    workspace = artifact_store.get_workspace(
        space_id=space_id,
        run_id=supervisor_run_id,
    )
    workspace_snapshot = workspace.snapshot if workspace is not None else {}
    summary = _supervisor_summary(
        space_id=space_id,
        run_id=supervisor_run_id,
        artifact_store=artifact_store,
    )
    chat_run_id = workspace_snapshot.get("chat_run_id")
    if not isinstance(chat_run_id, str) or chat_run_id.strip() == "":
        chat_run_id = summary.get("chat_run_id")
    chat_session_id = workspace_snapshot.get("chat_session_id")
    if not isinstance(chat_session_id, str) or chat_session_id.strip() == "":
        chat_session_id = summary.get("chat_session_id")
    curation_source = workspace_snapshot.get("curation_source")
    if not isinstance(curation_source, str) or curation_source.strip() == "":
        curation_source = summary.get("curation_source")
    curation_run_id = workspace_snapshot.get("curation_run_id")
    if not isinstance(curation_run_id, str) or curation_run_id.strip() == "":
        curation_run_id = summary.get("curation_run_id")
    if not isinstance(chat_run_id, str) or chat_run_id.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Supervisor run '{supervisor_run_id}' does not have a completed "
                "briefing chat step"
            ),
        )
    if not isinstance(chat_session_id, str) or chat_session_id.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Supervisor run '{supervisor_run_id}' does not have a persisted "
                "briefing chat session"
            ),
        )
    if (
        isinstance(curation_source, str)
        and curation_source == "chat_graph_write"
        and isinstance(curation_run_id, str)
        and curation_run_id.strip() != ""
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Supervisor run '{supervisor_run_id}' already delegated chat "
                f"graph-write review to child claim-curation run '{curation_run_id}'"
            ),
        )
    return chat_run_id, chat_session_id


def _supervisor_review_history(
    *,
    summary: dict[str, object],
) -> list[dict[str, object]]:
    raw_reviews = summary.get("chat_graph_write_reviews")
    if not isinstance(raw_reviews, list):
        return []
    return [item for item in raw_reviews if isinstance(item, dict)]


def _upsert_supervisor_review_step(
    *,
    summary: dict[str, object],
    chat_run_id: str,
    review_count: int,
    decision_status: str,
    candidate_index: int,
) -> list[dict[str, object]]:
    raw_steps = summary.get("steps")
    existing_steps = (
        [item for item in raw_steps if isinstance(item, dict)]
        if isinstance(raw_steps, list)
        else []
    )
    updated_step = {
        "step": "chat_graph_write_review",
        "status": "completed",
        "harness_id": "graph-chat",
        "run_id": chat_run_id,
        "detail": (
            f"Recorded {review_count} direct briefing-chat graph-write review(s). "
            f"Latest decision: {decision_status} candidate {candidate_index}."
        ),
    }
    updated_steps: list[dict[str, object]] = []
    step_found = False
    for step in existing_steps:
        if step.get("step") == "chat_graph_write_review":
            updated_steps.append(updated_step)
            step_found = True
        else:
            updated_steps.append(step)
    if not step_found:
        updated_steps.append(updated_step)
    return updated_steps


@router.post(
    "/{space_id}/agents/supervisor/runs",
    response_model=SupervisorRunResponse,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": HarnessAcceptedRunResponse}},
    summary="Start one composed supervisor workflow run",
    dependencies=[Depends(require_harness_space_write_access)],
)
async def create_supervisor_run(  # noqa: PLR0913
    space_id: UUID,
    request: SupervisorRunRequest,
    *,
    prefer: Annotated[str | None, Header()] = None,
    current_user=_CURRENT_USER_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    parent_graph_api_gateway: GraphTransportBundle = _PARENT_GRAPH_API_GATEWAY_DEPENDENCY,
    execution_services=_HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> SupervisorRunResponse:
    """Run the forward-only supervisor composition across bootstrap, chat, and curation."""
    objective = (
        request.objective.strip() if isinstance(request.objective, str) else None
    )
    try:
        seed_entity_ids = normalize_bootstrap_seed_entity_ids(request.seed_entity_ids)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if objective is None and not seed_entity_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either objective or at least one seed_entity_id.",
        )
    if request.curation_source == "chat_graph_write" and not request.include_chat:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="chat_graph_write curation_source requires include_chat=true.",
        )
    resolved_title = (
        request.title.strip() if isinstance(request.title, str) else ""
    ) or "Supervisor Harness"
    try:
        if should_require_worker_ready(execution_services=execution_services):
            require_worker_ready(operation_name="Supervisor")
        parent_graph_health = parent_graph_api_gateway.get_health()
        queued_run = queue_supervisor_run(
            space_id=space_id,
            title=resolved_title,
            objective=objective,
            seed_entity_ids=seed_entity_ids,
            source_type=request.source_type,
            relation_types=request.relation_types,
            max_depth=request.max_depth,
            max_hypotheses=request.max_hypotheses,
            model_id=request.model_id,
            include_chat=request.include_chat,
            include_curation=request.include_curation,
            curation_source=request.curation_source,
            briefing_question=request.briefing_question,
            chat_max_depth=request.chat_max_depth,
            chat_top_k=request.chat_top_k,
            chat_include_evidence_chains=request.chat_include_evidence_chains,
            curation_proposal_limit=request.curation_proposal_limit,
            current_user_id=current_user.id,
            graph_service_status=parent_graph_health.status,
            graph_service_version=parent_graph_health.version,
            run_registry=run_registry,
            artifact_store=artifact_store,
        )
        ensure_run_transparency_seed(
            run=queued_run,
            artifact_store=artifact_store,
            runtime=execution_services.runtime,
        )
        wake_worker_for_queued_run(
            run=queued_run,
            execution_services=execution_services,
        )
        if prefers_respond_async(prefer):
            accepted = build_accepted_run_response(
                run=queued_run,
                run_registry=run_registry,
            )
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content=accepted.model_dump(mode="json"),
                headers={"Preference-Applied": "respond-async"},
            )
        await maybe_execute_test_worker_run(
            run=queued_run,
            services=execution_services,
        )
        wait_outcome = await wait_for_terminal_run(
            space_id=space_id,
            run_id=queued_run.id,
            run_registry=run_registry,
            timeout_seconds=get_settings().sync_wait_timeout_seconds,
            poll_interval_seconds=get_settings().sync_wait_poll_seconds,
        )
    except GraphServiceClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Graph API unavailable: {exc}",
        ) from exc
    except ChatGraphWriteCandidateError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except (ChatGraphWriteArtifactError, ChatGraphWriteVerificationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    finally:
        parent_graph_api_gateway.close()
    if wait_outcome.timed_out:
        accepted = build_accepted_run_response(
            run=queued_run,
            run_registry=run_registry,
        )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=accepted.model_dump(mode="json"),
        )
    if wait_outcome.run is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reload supervisor run.",
        )
    if wait_outcome.run.status == "failed":
        raise_for_failed_run(run=wait_outcome.run, artifact_store=artifact_store)
    payload = load_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=queued_run.id,
    )
    return SupervisorRunResponse.model_validate(payload, strict=False)


@router.get(
    "/{space_id}/agents/supervisor/dashboard",
    response_model=SupervisorDashboardResponse,
    summary="Get typed supervisor dashboard summary",
    dependencies=[Depends(require_harness_space_read_access)],
)
def get_supervisor_dashboard(  # noqa: PLR0913
    space_id: UUID,
    status_filter: str | None = _STATUS_QUERY,
    curation_source: str | None = _CURATION_SOURCE_QUERY,
    has_chat_graph_write_reviews: bool | None = _HAS_CHAT_GRAPH_WRITE_REVIEWS_QUERY,
    created_after: datetime | None = _CREATED_AFTER_QUERY,
    created_before: datetime | None = _CREATED_BEFORE_QUERY,
    updated_after: datetime | None = _UPDATED_AFTER_QUERY,
    updated_before: datetime | None = _UPDATED_BEFORE_QUERY,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> SupervisorDashboardResponse:
    """Return the typed supervisor dashboard summary without paginated run rows."""
    filters = _normalized_supervisor_filters(
        status_filter=status_filter,
        curation_source=curation_source,
        has_chat_graph_write_reviews=has_chat_graph_write_reviews,
        created_after=created_after,
        created_before=created_before,
        updated_after=updated_after,
        updated_before=updated_before,
    )
    detail_runs = _filtered_supervisor_run_details(
        space_id=space_id,
        filters=filters,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )
    return SupervisorDashboardResponse(
        summary=_supervisor_list_summary(runs=detail_runs),
        highlights=_supervisor_dashboard_highlights(runs=detail_runs),
    )


@router.get(
    "/{space_id}/agents/supervisor/runs",
    response_model=SupervisorRunListResponse,
    summary="List typed supervisor workflow runs",
    dependencies=[Depends(require_harness_space_read_access)],
)
def list_supervisor_runs(  # noqa: PLR0913
    space_id: UUID,
    status_filter: str | None = _STATUS_QUERY,
    curation_source: str | None = _CURATION_SOURCE_QUERY,
    has_chat_graph_write_reviews: bool | None = _HAS_CHAT_GRAPH_WRITE_REVIEWS_QUERY,
    created_after: datetime | None = _CREATED_AFTER_QUERY,
    created_before: datetime | None = _CREATED_BEFORE_QUERY,
    updated_after: datetime | None = _UPDATED_AFTER_QUERY,
    updated_before: datetime | None = _UPDATED_BEFORE_QUERY,
    offset: int = _OFFSET_QUERY,
    limit: int = _LIMIT_QUERY,
    sort_by: str = _SORT_BY_QUERY,
    sort_direction: str = _SORT_DIRECTION_QUERY,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> SupervisorRunListResponse:
    """Return typed supervisor workflow runs for one research space."""
    filters = _normalized_supervisor_filters(
        status_filter=status_filter,
        curation_source=curation_source,
        has_chat_graph_write_reviews=has_chat_graph_write_reviews,
        created_after=created_after,
        created_before=created_before,
        updated_after=updated_after,
        updated_before=updated_before,
    )
    detail_runs = _filtered_supervisor_run_details(
        space_id=space_id,
        filters=filters,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )
    reverse = sort_direction == "desc"
    summary = _supervisor_list_summary(runs=detail_runs)
    sorted_runs = sorted(
        detail_runs,
        key=lambda detail: _supervisor_sort_key(detail=detail, sort_by=sort_by),
        reverse=reverse,
    )
    paged_runs = sorted_runs[offset : offset + limit]
    return SupervisorRunListResponse(
        summary=summary,
        runs=paged_runs,
        total=len(detail_runs),
    )


@router.get(
    "/{space_id}/agents/supervisor/runs/{run_id}",
    response_model=SupervisorRunDetailResponse,
    summary="Get one typed supervisor workflow run",
    dependencies=[Depends(require_harness_space_read_access)],
)
def get_supervisor_run(
    space_id: UUID,
    run_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> SupervisorRunDetailResponse:
    """Return the persisted supervisor summary for one composed run."""
    run = _require_supervisor_run_record(
        space_id=space_id,
        run_id=run_id,
        run_registry=run_registry,
    )
    return build_supervisor_run_detail_response(
        space_id=space_id,
        run=run,
        artifact_store=artifact_store,
        run_registry=run_registry,
    )


@router.post(
    "/{space_id}/agents/supervisor/runs/{run_id}/chat-graph-write-candidates/{candidate_index}/review",
    response_model=SupervisorChatGraphWriteCandidateDecisionResponse,
    summary="Promote or reject one supervisor briefing-chat graph-write candidate",
    dependencies=[Depends(require_harness_space_write_access)],
)
def review_supervisor_chat_graph_write_candidate(  # noqa: PLR0913
    space_id: UUID,
    run_id: UUID,
    candidate_index: int,
    request: ChatGraphWriteCandidateDecisionRequest,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _PARENT_GRAPH_API_GATEWAY_DEPENDENCY,
    execution_services=_HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> SupervisorChatGraphWriteCandidateDecisionResponse:
    supervisor_run = _require_supervisor_run_record(
        space_id=space_id,
        run_id=run_id,
        run_registry=run_registry,
    )
    chat_run_id, chat_session_id = _require_supervisor_briefing_chat_context(
        space_id=space_id,
        supervisor_run_id=supervisor_run.id,
        artifact_store=artifact_store,
    )
    try:
        candidate = _require_reviewable_chat_graph_write_candidate(
            space_id=space_id,
            run_id=chat_run_id,
            candidate_index=candidate_index,
            artifact_store=artifact_store,
        )
        proposal = _ensure_pending_chat_graph_write_proposal(
            space_id=space_id,
            run_id=chat_run_id,
            session_id=UUID(chat_session_id),
            candidate=candidate,
            artifact_store=artifact_store,
            proposal_store=proposal_store,
            run_registry=run_registry,
        )
        request_metadata = {
            **request.metadata,
            "chat_candidate_index": candidate_index,
            "chat_session_id": chat_session_id,
            "supervisor_run_id": supervisor_run.id,
        }
        supervisor_workspace_patch = {
            "last_supervisor_chat_graph_write_candidate_index": candidate_index,
            "last_supervisor_chat_graph_write_candidate_decision": request.decision,
            "last_supervisor_chat_graph_write_proposal_id": proposal.id,
            "last_supervisor_chat_graph_write_chat_run_id": chat_run_id,
            "last_supervisor_chat_graph_write_chat_session_id": chat_session_id,
        }
        if request.decision == "promote":
            promotion_metadata = promote_to_graph_claim(
                space_id=space_id,
                proposal=proposal,
                request_metadata=request_metadata,
                graph_api_gateway=graph_api_gateway,
            )
            updated_proposal = decide_proposal(
                space_id=space_id,
                proposal_id=proposal.id,
                decision_status="promoted",
                decision_reason=request.reason,
                request_metadata=request_metadata,
                proposal_store=proposal_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
                decision_metadata=promotion_metadata,
                event_payload={
                    "candidate_index": candidate_index,
                    "source_key": proposal.source_key,
                    **promotion_metadata,
                },
                workspace_patch={
                    "last_promoted_graph_claim_id": promotion_metadata[
                        "graph_claim_id"
                    ],
                    "last_promoted_graph_relation_id": promotion_metadata.get(
                        "graph_relation_id",
                    ),
                },
            )
            supervisor_workspace_patch[
                "last_supervisor_chat_graph_write_graph_claim_id"
            ] = promotion_metadata["graph_claim_id"]
            append_manual_review_decision(
                space_id=space_id,
                run_id=supervisor_run.id,
                tool_name="create_graph_claim",
                decision="promote",
                reason=request.reason,
                artifact_key="supervisor_chat_graph_write_review",
                metadata={
                    "candidate_index": candidate_index,
                    "proposal_id": updated_proposal.id,
                    "chat_run_id": chat_run_id,
                    "chat_session_id": chat_session_id,
                    "source_key": proposal.source_key,
                    "graph_claim_id": promotion_metadata["graph_claim_id"],
                },
                artifact_store=artifact_store,
                run_registry=run_registry,
                runtime=execution_services.runtime,
            )
        else:
            updated_proposal = decide_proposal(
                space_id=space_id,
                proposal_id=proposal.id,
                decision_status="rejected",
                decision_reason=request.reason,
                request_metadata=request_metadata,
                proposal_store=proposal_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
                event_payload={
                    "candidate_index": candidate_index,
                    "source_key": proposal.source_key,
                },
            )
            append_manual_review_decision(
                space_id=space_id,
                run_id=supervisor_run.id,
                tool_name="supervisor_chat_graph_write_review",
                decision="reject",
                reason=request.reason,
                artifact_key="supervisor_chat_graph_write_review",
                metadata={
                    "candidate_index": candidate_index,
                    "proposal_id": updated_proposal.id,
                    "chat_run_id": chat_run_id,
                    "chat_session_id": chat_session_id,
                    "source_key": proposal.source_key,
                },
                artifact_store=artifact_store,
                run_registry=run_registry,
                runtime=execution_services.runtime,
            )
        review_artifact_key = "supervisor_chat_graph_write_review"
        review_entry: dict[str, object] = {
            "reviewed_at": datetime.now(UTC).isoformat(),
            "chat_run_id": chat_run_id,
            "chat_session_id": chat_session_id,
            "candidate_index": candidate_index,
            "decision": request.decision,
            "decision_status": updated_proposal.status,
            "proposal_id": updated_proposal.id,
            "proposal_status": updated_proposal.status,
            "candidate": candidate.model_dump(mode="json"),
        }
        if request.decision == "promote":
            review_entry["graph_claim_id"] = updated_proposal.metadata.get(
                "graph_claim_id",
            )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=supervisor_run.id,
            artifact_key=review_artifact_key,
            media_type="application/json",
            content={
                "supervisor_run_id": supervisor_run.id,
                **review_entry,
            },
        )
        summary = _supervisor_summary(
            space_id=space_id,
            run_id=supervisor_run.id,
            artifact_store=artifact_store,
        )
        review_history = [
            *_supervisor_review_history(summary=summary),
            review_entry,
        ]
        updated_summary = {
            **summary,
            "chat_graph_write_reviews": review_history,
            "chat_graph_write_review_count": len(review_history),
            "latest_chat_graph_write_review": review_entry,
            "steps": _upsert_supervisor_review_step(
                summary=summary,
                chat_run_id=chat_run_id,
                review_count=len(review_history),
                decision_status=updated_proposal.status,
                candidate_index=candidate_index,
            ),
        }
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=supervisor_run.id,
            artifact_key="supervisor_summary",
            media_type="application/json",
            content=updated_summary,
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=supervisor_run.id,
            patch={
                **supervisor_workspace_patch,
                "last_supervisor_chat_graph_write_review_key": review_artifact_key,
                "last_supervisor_summary_key": "supervisor_summary",
            },
        )
        decision_status = "promoted" if request.decision == "promote" else "rejected"
        run_registry.record_event(
            space_id=space_id,
            run_id=supervisor_run.id,
            event_type=f"supervisor.chat_graph_write_candidate_{decision_status}",
            message=(
                f"Supervisor {decision_status} chat graph-write candidate "
                f"'{candidate_index}'."
            ),
            payload={
                "chat_run_id": chat_run_id,
                "chat_session_id": chat_session_id,
                "candidate_index": candidate_index,
                "proposal_id": updated_proposal.id,
                "proposal_status": updated_proposal.status,
                "review_count": len(review_history),
            },
        )
    except GraphServiceClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Graph API unavailable: {exc}",
        ) from exc
    except (ChatGraphWriteArtifactError, ChatGraphWriteVerificationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    finally:
        graph_api_gateway.close()
    updated_summary = _supervisor_summary(
        space_id=space_id,
        run_id=supervisor_run.id,
        artifact_store=artifact_store,
    )
    review_responses = _build_supervisor_chat_graph_write_review_responses(
        summary=updated_summary,
    )
    refreshed_supervisor_run = run_registry.get_run(space_id=space_id, run_id=run_id)
    return SupervisorChatGraphWriteCandidateDecisionResponse(
        run=HarnessRunResponse.from_record(refreshed_supervisor_run or supervisor_run),
        chat_run_id=chat_run_id,
        chat_session_id=chat_session_id,
        candidate_index=candidate_index,
        candidate=candidate,
        proposal=ChatGraphWriteProposalRecordResponse.from_record(updated_proposal),
        chat_graph_write_review_count=len(review_responses),
        latest_chat_graph_write_review=(
            review_responses[-1] if review_responses else None
        ),
        chat_graph_write_reviews=review_responses,
    )


__all__ = [
    "SupervisorArtifactKeysResponse",
    "SupervisorDashboardApprovalRunPointerResponse",
    "SupervisorBootstrapArtifactKeysResponse",
    "SupervisorChatArtifactKeysResponse",
    "SupervisorChatGraphWriteCandidateDecisionResponse",
    "SupervisorChatGraphWriteReviewResponse",
    "SupervisorCurationArtifactKeysResponse",
    "SupervisorDashboardHighlightsResponse",
    "SupervisorDashboardResponse",
    "SupervisorDashboardRunPointerResponse",
    "SupervisorRunDailyCountResponse",
    "SupervisorRunDetailResponse",
    "SupervisorRunListResponse",
    "SupervisorRunListSummaryResponse",
    "SupervisorRunRequest",
    "SupervisorRunResponse",
    "SupervisorStepResponse",
    "SupervisorRunTrendSummaryResponse",
    "build_supervisor_run_detail_response",
    "build_supervisor_run_response",
    "create_supervisor_run",
    "get_supervisor_dashboard",
    "get_supervisor_run",
    "list_supervisor_runs",
    "review_supervisor_chat_graph_write_candidate",
    "router",
]
