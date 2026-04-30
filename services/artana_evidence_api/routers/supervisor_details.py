"""Supervisor run detail, dashboard, and review serialization helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from uuid import UUID

from artana_evidence_api.routers.chat import (
    ChatMessageRunResponse,
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
from artana_evidence_api.routers.supervisor_models import (
    SupervisorArtifactKeysResponse,
    SupervisorBootstrapArtifactKeysResponse,
    SupervisorChatArtifactKeysResponse,
    SupervisorChatGraphWriteReviewResponse,
    SupervisorCurationArtifactKeysResponse,
    SupervisorDashboardApprovalRunPointerResponse,
    SupervisorDashboardHighlightsResponse,
    SupervisorDashboardRunPointerResponse,
    SupervisorRunDailyCountResponse,
    SupervisorRunDetailResponse,
    SupervisorRunListSummaryResponse,
    SupervisorRunResponse,
    SupervisorRunTrendSummaryResponse,
    SupervisorStepResponse,
    _SupervisorRunListFilters,
)
from artana_evidence_api.supervisor_runtime import (
    SupervisorExecutionResult,
    is_supervisor_workflow,
)
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
    from artana_evidence_api.types.common import JSONObject

def _build_supervisor_chat_graph_write_review_responses(
    *,
    summary: JSONObject,
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
) -> SupervisorRunResponse | JSONResponse:
    """Serialize one supervisor execution result for HTTP responses."""
    return SupervisorRunResponse(
        run=HarnessRunResponse.from_record(result.run),
        bootstrap=cast(
            "ResearchBootstrapRunResponse",
            build_research_bootstrap_run_response(result.bootstrap),
        ),
        chat=(
            cast("ChatMessageRunResponse", build_chat_message_run_response(result.chat))
            if result.chat is not None
            else None
        ),
        curation=(
            cast(
                "ClaimCurationRunResponse",
                build_claim_curation_run_response(result.curation),
            )
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
) -> HarnessRunRecord:
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
) -> JSONObject:
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
    summary: JSONObject,
) -> list[JSONObject]:
    raw_reviews = summary.get("chat_graph_write_reviews")
    if not isinstance(raw_reviews, list):
        return []
    return [item for item in raw_reviews if isinstance(item, dict)]


def _upsert_supervisor_review_step(
    *,
    summary: JSONObject,
    chat_run_id: str,
    review_count: int,
    decision_status: str,
    candidate_index: int,
) -> list[JSONObject]:
    raw_steps = summary.get("steps")
    existing_steps = (
        [item for item in raw_steps if isinstance(item, dict)]
        if isinstance(raw_steps, list)
        else []
    )
    updated_step: JSONObject = {
        "step": "chat_graph_write_review",
        "status": "completed",
        "harness_id": "graph-chat",
        "run_id": chat_run_id,
        "detail": (
            f"Recorded {review_count} direct briefing-chat graph-write review(s). "
            f"Latest decision: {decision_status} candidate {candidate_index}."
        ),
    }
    updated_steps: list[JSONObject] = []
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




__all__ = [
    "_build_supervisor_chat_graph_write_review_responses",
    "_filtered_supervisor_run_details",
    "_normalized_supervisor_filters",
    "_require_supervisor_briefing_chat_context",
    "_require_supervisor_run_record",
    "_supervisor_dashboard_highlights",
    "_supervisor_list_summary",
    "_supervisor_review_history",
    "_supervisor_sort_key",
    "_supervisor_summary",
    "_upsert_supervisor_review_step",
    "build_supervisor_run_detail_response",
    "build_supervisor_run_response",
]
