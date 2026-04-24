"""Harness-owned research onboarding endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from uuid import UUID  # noqa: TC003

from artana_evidence_api.config import get_settings
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_graph_api_gateway,
    get_harness_execution_services,
    get_research_state_store,
    get_run_registry,
    require_harness_space_write_access,
)
from artana_evidence_api.graph_client import GraphServiceClientError
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
from artana_evidence_api.research_onboarding_agent_runtime import (
    OnboardingAgentExecutionError,
)
from artana_evidence_api.research_onboarding_runtime import (
    ResearchAssistantMessage,
    ResearchOnboardingContinuationRequest,
    ResearchOnboardingContinuationResult,
    ResearchOnboardingExecutionResult,
    queue_research_onboarding_continuation,
    queue_research_onboarding_run,
)
from artana_evidence_api.routers.runs import HarnessRunResponse
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.harness_runtime import HarnessExecutionServices
    from artana_evidence_api.research_state import HarnessResearchStateStore
    from artana_evidence_api.run_registry import HarnessRunRegistry

router = APIRouter(
    prefix="/v1/spaces",
    tags=["research-onboarding-runs"],
    dependencies=[Depends(require_harness_space_write_access)],
)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)
_RESEARCH_STATE_STORE_DEPENDENCY = Depends(get_research_state_store)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)


class ResearchOnboardingRunRequest(BaseModel):
    """Request payload for one onboarding run."""

    model_config = ConfigDict(strict=True)

    research_title: str = Field(min_length=1, max_length=100)
    primary_objective: str = Field(default="", max_length=4000)
    space_description: str = Field(default="", max_length=500)


class ResearchOnboardingContinuationRequestModel(BaseModel):
    """Request payload for one onboarding continuation turn."""

    model_config = ConfigDict(strict=True)

    thread_id: str = Field(min_length=1, max_length=100)
    message_id: str = Field(min_length=1, max_length=100)
    intent: str = Field(min_length=1, max_length=100)
    mode: str = Field(min_length=1, max_length=100)
    reply_text: str = Field(min_length=1, max_length=12000)
    reply_html: str = Field(default="", max_length=24000)
    attachments: list[JSONObject] = Field(default_factory=list)
    contextual_anchor: JSONObject | None = None


class HarnessResearchStateResponse(BaseModel):
    """Serialized structured research-state snapshot."""

    model_config = ConfigDict(strict=True)

    space_id: str
    objective: str | None
    current_hypotheses: list[str]
    explored_questions: list[str]
    pending_questions: list[str]
    last_graph_snapshot_id: str | None
    active_schedules: list[str]
    confidence_model: JSONObject
    budget_policy: JSONObject
    metadata: JSONObject
    created_at: str
    updated_at: str


class AssistantMessageResponse(BaseModel):
    """Serialized channel-neutral assistant message."""

    model_config = ConfigDict(strict=True)

    message_type: str
    title: str
    summary: str
    sections: list[JSONObject]
    questions: list[JSONObject]
    suggested_actions: list[JSONObject]
    artifacts: list[JSONObject]
    state_patch: JSONObject
    confidence_score: float
    rationale: str
    evidence: list[JSONObject]


class ResearchOnboardingRunResponse(BaseModel):
    """Combined response for a completed onboarding run."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    research_state: HarnessResearchStateResponse
    intake_artifact: JSONObject
    assistant_message: AssistantMessageResponse


class ResearchOnboardingContinuationResponse(BaseModel):
    """Combined response for a completed onboarding continuation turn."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    research_state: HarnessResearchStateResponse
    assistant_message: AssistantMessageResponse


def _serialize_assistant_message(
    assistant_message: ResearchAssistantMessage,
) -> AssistantMessageResponse:
    return AssistantMessageResponse(
        message_type=assistant_message.message_type,
        title=assistant_message.title,
        summary=assistant_message.summary,
        sections=assistant_message.sections,
        questions=assistant_message.questions,
        suggested_actions=assistant_message.suggested_actions,
        artifacts=assistant_message.artifacts,
        state_patch=assistant_message.state_patch,
        confidence_score=assistant_message.confidence_score,
        rationale=assistant_message.rationale,
        evidence=assistant_message.evidence,
    )


def _serialize_research_state(
    result: ResearchOnboardingExecutionResult | ResearchOnboardingContinuationResult,
) -> HarnessResearchStateResponse:
    state = result.research_state
    return HarnessResearchStateResponse(
        space_id=state.space_id,
        objective=state.objective,
        current_hypotheses=list(state.current_hypotheses),
        explored_questions=list(state.explored_questions),
        pending_questions=list(state.pending_questions),
        last_graph_snapshot_id=state.last_graph_snapshot_id,
        active_schedules=list(state.active_schedules),
        confidence_model=state.confidence_model,
        budget_policy=state.budget_policy,
        metadata=state.metadata,
        created_at=state.created_at.isoformat(),
        updated_at=state.updated_at.isoformat(),
    )


def _build_run_response(
    result: ResearchOnboardingExecutionResult,
) -> ResearchOnboardingRunResponse:
    return ResearchOnboardingRunResponse(
        run=HarnessRunResponse.from_record(result.run),
        research_state=_serialize_research_state(result),
        intake_artifact=result.intake_artifact,
        assistant_message=_serialize_assistant_message(result.assistant_message),
    )


def _build_continuation_response(
    result: ResearchOnboardingContinuationResult,
) -> ResearchOnboardingContinuationResponse:
    return ResearchOnboardingContinuationResponse(
        run=HarnessRunResponse.from_record(result.run),
        research_state=_serialize_research_state(result),
        assistant_message=_serialize_assistant_message(result.assistant_message),
    )


def _resolve_research_title_from_state(
    *,
    research_state: object | None,
) -> str:
    if research_state is None:
        return "Research space"
    metadata = getattr(research_state, "metadata", None)
    if not isinstance(metadata, dict):
        return "Research space"
    value = metadata.get("research_title")
    if not isinstance(value, str):
        return "Research space"
    resolved = value.strip()
    return resolved or "Research space"


@router.post(
    "/{space_id}/agents/research-onboarding/runs",
    response_model=ResearchOnboardingRunResponse,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": HarnessAcceptedRunResponse}},
    summary="Create the first onboarding assistant message for a research space",
)
async def create_research_onboarding_run(
    space_id: UUID,
    request: ResearchOnboardingRunRequest,
    *,
    prefer: Annotated[str | None, Header()] = None,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
    _research_state_store: HarnessResearchStateStore = _RESEARCH_STATE_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = (
        _HARNESS_EXECUTION_SERVICES_DEPENDENCY
    ),
) -> ResearchOnboardingRunResponse | JSONResponse:
    """Generate the first onboarding assistant message and persist typed artifacts."""
    try:
        if should_require_worker_ready(execution_services=execution_services):
            require_worker_ready(operation_name="Research onboarding")
        graph_health = graph_api_gateway.get_health()
        queued_run = queue_research_onboarding_run(
            space_id=space_id,
            research_title=request.research_title,
            primary_objective=request.primary_objective,
            space_description=request.space_description,
            graph_service_status=graph_health.status,
            graph_service_version=graph_health.version,
            run_registry=run_registry,
            artifact_store=artifact_store,
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
    except OnboardingAgentExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Onboarding agent unavailable: {exc}",
        ) from exc
    except GraphServiceClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Graph API unavailable: {exc}",
        ) from exc
    finally:
        graph_api_gateway.close()
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
            detail="Failed to reload completed research-onboarding run.",
        )
    if wait_outcome.run.status == "failed":
        raise_for_failed_run(run=wait_outcome.run, artifact_store=artifact_store)
    payload = load_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=queued_run.id,
    )
    return ResearchOnboardingRunResponse.model_validate(payload, strict=False)


@router.post(
    "/{space_id}/agents/research-onboarding/turns",
    response_model=ResearchOnboardingContinuationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": HarnessAcceptedRunResponse}},
    summary="Continue one onboarding thread turn after a researcher reply",
)
async def continue_research_onboarding(
    space_id: UUID,
    request: ResearchOnboardingContinuationRequestModel,
    *,
    prefer: Annotated[str | None, Header()] = None,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
    research_state_store: HarnessResearchStateStore = _RESEARCH_STATE_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = (
        _HARNESS_EXECUTION_SERVICES_DEPENDENCY
    ),
) -> ResearchOnboardingContinuationResponse | JSONResponse:
    """Generate the next structured onboarding assistant message."""
    existing_state = research_state_store.get_state(space_id=space_id)
    research_title = _resolve_research_title_from_state(research_state=existing_state)
    try:
        if should_require_worker_ready(execution_services=execution_services):
            require_worker_ready(operation_name="Research onboarding")
        graph_health = graph_api_gateway.get_health()
        queued_run = queue_research_onboarding_continuation(
            space_id=space_id,
            research_title=research_title,
            request=ResearchOnboardingContinuationRequest(
                thread_id=request.thread_id,
                message_id=request.message_id,
                intent=request.intent,
                mode=request.mode,
                reply_text=request.reply_text,
                reply_html=request.reply_html,
                attachments=list(request.attachments),
                contextual_anchor=request.contextual_anchor,
            ),
            graph_service_status=graph_health.status,
            graph_service_version=graph_health.version,
            run_registry=run_registry,
            artifact_store=artifact_store,
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
    except OnboardingAgentExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Onboarding agent unavailable: {exc}",
        ) from exc
    except GraphServiceClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Graph API unavailable: {exc}",
        ) from exc
    finally:
        graph_api_gateway.close()
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
            detail="Failed to reload completed research-onboarding turn.",
        )
    if wait_outcome.run.status == "failed":
        raise_for_failed_run(run=wait_outcome.run, artifact_store=artifact_store)
    payload = load_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=queued_run.id,
    )
    return ResearchOnboardingContinuationResponse.model_validate(
        payload,
        strict=False,
    )


__all__ = [
    "ResearchOnboardingContinuationRequestModel",
    "ResearchOnboardingContinuationResponse",
    "ResearchOnboardingRunRequest",
    "ResearchOnboardingRunResponse",
    "continue_research_onboarding",
    "create_research_onboarding_run",
    "router",
]
