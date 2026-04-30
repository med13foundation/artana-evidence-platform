"""Harness-owned supervisor run endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated
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
from artana_evidence_api.queued_run import (
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
    _ensure_pending_chat_graph_write_proposal,
    _require_reviewable_chat_graph_write_candidate,
)
from artana_evidence_api.routers.runs import (
    HarnessRunResponse,
)
from artana_evidence_api.routers.supervisor_details import (
    _build_supervisor_chat_graph_write_review_responses,
    _filtered_supervisor_run_details,
    _normalized_supervisor_filters,
    _require_supervisor_briefing_chat_context,
    _require_supervisor_run_record,
    _supervisor_dashboard_highlights,
    _supervisor_list_summary,
    _supervisor_review_history,
    _supervisor_sort_key,
    _supervisor_summary,
    _upsert_supervisor_review_step,
    build_supervisor_run_detail_response,
    build_supervisor_run_response,
)
from artana_evidence_api.routers.supervisor_models import (
    SupervisorArtifactKeysResponse,
    SupervisorBootstrapArtifactKeysResponse,
    SupervisorChatArtifactKeysResponse,
    SupervisorChatGraphWriteCandidateDecisionResponse,
    SupervisorChatGraphWriteReviewResponse,
    SupervisorCurationArtifactKeysResponse,
    SupervisorDashboardApprovalRunPointerResponse,
    SupervisorDashboardHighlightsResponse,
    SupervisorDashboardResponse,
    SupervisorDashboardRunPointerResponse,
    SupervisorRunDailyCountResponse,
    SupervisorRunDetailResponse,
    SupervisorRunListResponse,
    SupervisorRunListSummaryResponse,
    SupervisorRunRequest,
    SupervisorRunResponse,
    SupervisorRunTrendSummaryResponse,
    SupervisorStepResponse,
)
from artana_evidence_api.run_registry import (
    HarnessRunRegistry,  # noqa: TC001
)
from artana_evidence_api.supervisor_runtime import (
    queue_supervisor_run,
)
from artana_evidence_api.transparency import (
    append_manual_review_decision,
    ensure_run_transparency_seed,
)
from artana_evidence_api.types.common import JSONObject, json_value
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from artana_evidence_api.auth import HarnessUser
    from artana_evidence_api.harness_runtime import HarnessExecutionServices

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
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    parent_graph_api_gateway: GraphTransportBundle = _PARENT_GRAPH_API_GATEWAY_DEPENDENCY,
    execution_services: HarnessExecutionServices = (
        _HARNESS_EXECUTION_SERVICES_DEPENDENCY
    ),
) -> SupervisorRunResponse | JSONResponse:
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
    execution_services: HarnessExecutionServices = (
        _HARNESS_EXECUTION_SERVICES_DEPENDENCY
    ),
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
        request_metadata: JSONObject = {
            **request.metadata,
            "chat_candidate_index": candidate_index,
            "chat_session_id": chat_session_id,
            "supervisor_run_id": supervisor_run.id,
        }
        supervisor_workspace_patch: JSONObject = {
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
        review_entry: JSONObject = {
            "reviewed_at": datetime.now(UTC).isoformat(),
            "chat_run_id": chat_run_id,
            "chat_session_id": chat_session_id,
            "candidate_index": candidate_index,
            "decision": request.decision,
            "decision_status": updated_proposal.status,
            "proposal_id": updated_proposal.id,
            "proposal_status": updated_proposal.status,
            "candidate": json_value(candidate.model_dump(mode="json")),
        }
        if request.decision == "promote":
            review_entry["graph_claim_id"] = json_value(
                updated_proposal.metadata.get("graph_claim_id"),
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
        updated_summary: JSONObject = {
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
