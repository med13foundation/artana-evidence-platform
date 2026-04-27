"""Goal-driven evidence-selection harness endpoints."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from artana_evidence_api.artifact_store import HarnessArtifactStore  # noqa: TC001
from artana_evidence_api.auth import HarnessUser, get_current_harness_user
from artana_evidence_api.config import get_settings
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_harness_execution_services,
    get_run_registry,
    require_harness_space_write_access,
)
from artana_evidence_api.evidence_selection_model_planner import (
    is_model_source_planner_available,
    model_source_planner_unavailable_detail,
)
from artana_evidence_api.evidence_selection_runtime import (
    EvidenceSelectionCandidateSearch,
    EvidenceSelectionMode,
    EvidenceSelectionProposalMode,
    EvidenceSelectionSourcePlannerMode,
    queue_evidence_selection_run,
)
from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
    EvidenceSelectionSourceSearchError,
    validate_live_source_search,
)
from artana_evidence_api.harness_runtime import HarnessExecutionServices
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
from artana_evidence_api.routers.runs import HarnessRunResponse
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.source_registry import (
    get_source_definition,
    normalize_source_key,
)
from artana_evidence_api.types.common import JSONObject
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

router = APIRouter(
    prefix="/v1/spaces",
    tags=["evidence-selection-runs"],
    dependencies=[Depends(require_harness_space_write_access)],
)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)
_CURRENT_USER_DEPENDENCY = Depends(get_current_harness_user)


class EvidenceSelectionCandidateSearchRequest(BaseModel):
    """Saved source-search run to screen during an evidence-selection pass."""

    model_config = ConfigDict(strict=True)

    source_key: str = Field(..., min_length=1, max_length=64)
    search_id: UUID
    max_records: int | None = Field(default=None, ge=1, le=100)

    @field_validator("search_id", mode="before")
    @classmethod
    def _parse_search_id(cls, value: object) -> UUID:
        if isinstance(value, UUID):
            return value
        if isinstance(value, str):
            return UUID(value)
        msg = "search_id must be a UUID"
        raise ValueError(msg)

    @field_validator("source_key")
    @classmethod
    def _normalize_source_key(cls, value: str) -> str:
        normalized = normalize_source_key(value)
        if get_source_definition(normalized) is None:
            msg = f"Unknown source '{value}'"
            raise ValueError(msg)
        return normalized

    def to_runtime(self) -> EvidenceSelectionCandidateSearch:
        """Return the runtime candidate-search contract."""

        return EvidenceSelectionCandidateSearch(
            source_key=self.source_key,
            search_id=self.search_id,
            max_records=self.max_records,
        )


class EvidenceSelectionSourceSearchRequest(BaseModel):
    """Source-search request the harness should create before screening."""

    model_config = ConfigDict(strict=True)

    source_key: str = Field(..., min_length=1, max_length=64)
    query_payload: JSONObject = Field(default_factory=dict)
    max_records: int | None = Field(default=None, ge=1, le=100)
    timeout_seconds: float | None = Field(default=None, gt=0.0, le=120.0)

    @field_validator("source_key")
    @classmethod
    def _normalize_source_key(cls, value: str) -> str:
        normalized = normalize_source_key(value)
        source = get_source_definition(normalized)
        if source is None:
            msg = f"Unknown source '{value}'"
            raise ValueError(msg)
        if not source.direct_search_enabled:
            msg = f"Source '{value}' does not support direct source search"
            raise ValueError(msg)
        return normalized

    @model_validator(mode="after")
    def _require_query_payload(self) -> EvidenceSelectionSourceSearchRequest:
        if not self.query_payload:
            msg = "query_payload must not be empty"
            raise ValueError(msg)
        raw_parameters = self.query_payload.get("parameters")
        parameter_payload = raw_parameters if isinstance(raw_parameters, dict) else {}
        if self.max_records is not None and (
            "max_results" in self.query_payload or "max_results" in parameter_payload
        ):
            msg = "Provide max_records or query_payload.max_results, not both"
            raise ValueError(msg)
        try:
            validate_live_source_search(self.to_runtime())
        except (EvidenceSelectionSourceSearchError, ValueError) as exc:
            msg = f"Invalid query_payload for source '{self.source_key}': {exc}"
            raise ValueError(msg) from exc
        return self

    def to_runtime(self) -> EvidenceSelectionLiveSourceSearch:
        """Return the runtime live source-search contract."""

        return EvidenceSelectionLiveSourceSearch(
            source_key=self.source_key,
            query_payload=self.query_payload,
            max_records=self.max_records,
            timeout_seconds=self.timeout_seconds,
        )


class EvidenceSelectionRunRequest(BaseModel):
    """Request payload for one goal-driven evidence-selection run."""

    model_config = ConfigDict(strict=True)

    goal: str = Field(..., min_length=1, max_length=4000)
    instructions: str | None = Field(default=None, min_length=1, max_length=4000)
    sources: list[str] = Field(default_factory=list, max_length=25)
    proposal_mode: Literal["review_required"] = "review_required"
    mode: Literal["shadow", "guarded"] = "guarded"
    planner_mode: Literal["model", "deterministic"] = "model"
    live_network_allowed: bool = Field(
        default=False,
        description=(
            "Allow this evidence-selection run to create live external "
            "source-search requests."
        ),
    )
    source_searches: list[EvidenceSelectionSourceSearchRequest] = Field(
        default_factory=list,
        max_length=50,
    )
    candidate_searches: list[EvidenceSelectionCandidateSearchRequest] = Field(
        default_factory=list,
        max_length=100,
    )
    max_records_per_search: int = Field(default=3, ge=1, le=100)
    max_handoffs: int = Field(default=20, ge=0, le=200)
    inclusion_criteria: list[str] = Field(default_factory=list, max_length=100)
    exclusion_criteria: list[str] = Field(default_factory=list, max_length=100)
    population_context: str | None = Field(default=None, min_length=1, max_length=1000)
    evidence_types: list[str] = Field(default_factory=list, max_length=50)
    priority_outcomes: list[str] = Field(default_factory=list, max_length=50)
    title: str | None = Field(default=None, min_length=1, max_length=256)

    @field_validator("goal")
    @classmethod
    def _normalize_goal(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if normalized == "":
            msg = "goal must not be empty"
            raise ValueError(msg)
        return normalized

    @field_validator("instructions", "population_context", "title")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @field_validator(
        "sources",
        "inclusion_criteria",
        "exclusion_criteria",
        "evidence_types",
        "priority_outcomes",
    )
    @classmethod
    def _normalize_string_list(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            candidate = " ".join(value.split())
            if candidate and candidate not in normalized:
                normalized.append(candidate)
        return normalized

    @field_validator("sources")
    @classmethod
    def _normalize_sources(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            source_key = normalize_source_key(value)
            if get_source_definition(source_key) is None:
                msg = f"Unknown source '{value}'"
                raise ValueError(msg)
            if source_key not in normalized:
                normalized.append(source_key)
        return normalized

    @model_validator(mode="after")
    def _default_sources_from_candidates(self) -> EvidenceSelectionRunRequest:
        if self.mode == "guarded" and self.max_handoffs == 0:
            msg = "guarded evidence runs require max_handoffs to be at least 1"
            raise ValueError(msg)
        if self.source_searches and not self.live_network_allowed:
            msg = (
                "live_network_allowed must be true when source_searches are "
                "provided."
            )
            raise ValueError(msg)
        if (
            self.planner_mode == "model"
            and not self.live_network_allowed
            and not self.candidate_searches
        ):
            msg = (
                "live_network_allowed must be true for goal-only model-planned "
                "evidence runs."
            )
            raise ValueError(msg)
        if (
            self.planner_mode == "deterministic"
            and not self.candidate_searches
            and not self.source_searches
        ):
            msg = "Provide source_searches or candidate_searches for this deterministic evidence-run slice"
            raise ValueError(msg)
        if self.sources:
            return self
        candidate_sources = [
            candidate.source_key
            for candidate in self.candidate_searches
        ]
        live_sources = [source.source_key for source in self.source_searches]
        if not candidate_sources and not live_sources:
            return self
        self.sources = list(dict.fromkeys([*live_sources, *candidate_sources]))
        return self


class EvidenceSelectionFollowUpRequest(BaseModel):
    """Request payload for adding instructions to an existing research run."""

    model_config = ConfigDict(strict=True)

    goal: str | None = Field(default=None, min_length=1, max_length=4000)
    instructions: str = Field(..., min_length=1, max_length=4000)
    sources: list[str] = Field(default_factory=list, max_length=25)
    proposal_mode: Literal["review_required"] = "review_required"
    mode: Literal["shadow", "guarded"] = "guarded"
    planner_mode: Literal["model", "deterministic"] = "model"
    live_network_allowed: bool = Field(
        default=False,
        description=(
            "Allow this evidence-selection follow-up to create live external "
            "source-search requests."
        ),
    )
    source_searches: list[EvidenceSelectionSourceSearchRequest] = Field(
        default_factory=list,
        max_length=50,
    )
    candidate_searches: list[EvidenceSelectionCandidateSearchRequest] = Field(
        default_factory=list,
        max_length=100,
    )
    max_records_per_search: int = Field(default=3, ge=1, le=100)
    max_handoffs: int = Field(default=20, ge=0, le=200)
    inclusion_criteria: list[str] = Field(default_factory=list, max_length=100)
    exclusion_criteria: list[str] = Field(default_factory=list, max_length=100)
    population_context: str | None = Field(default=None, min_length=1, max_length=1000)
    evidence_types: list[str] = Field(default_factory=list, max_length=50)
    priority_outcomes: list[str] = Field(default_factory=list, max_length=50)
    title: str | None = Field(default=None, min_length=1, max_length=256)

    @field_validator("instructions")
    @classmethod
    def _normalize_instructions(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if normalized == "":
            msg = "instructions must not be empty"
            raise ValueError(msg)
        return normalized

    @field_validator("goal", "population_context", "title")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @field_validator(
        "sources",
        "inclusion_criteria",
        "exclusion_criteria",
        "evidence_types",
        "priority_outcomes",
    )
    @classmethod
    def _normalize_string_list(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            candidate = " ".join(value.split())
            if candidate and candidate not in normalized:
                normalized.append(candidate)
        return normalized

    @field_validator("sources")
    @classmethod
    def _normalize_sources(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            source_key = normalize_source_key(value)
            if get_source_definition(source_key) is None:
                msg = f"Unknown source '{value}'"
                raise ValueError(msg)
            if source_key not in normalized:
                normalized.append(source_key)
        return normalized

    @model_validator(mode="after")
    def _default_sources_from_candidates(self) -> EvidenceSelectionFollowUpRequest:
        if self.mode == "guarded" and self.max_handoffs == 0:
            msg = "guarded evidence-run follow-ups require max_handoffs to be at least 1"
            raise ValueError(msg)
        if self.source_searches and not self.live_network_allowed:
            msg = (
                "live_network_allowed must be true when source_searches are "
                "provided."
            )
            raise ValueError(msg)
        if (
            self.planner_mode == "model"
            and not self.live_network_allowed
            and not self.candidate_searches
        ):
            msg = (
                "live_network_allowed must be true for goal-only model-planned "
                "evidence-run follow-ups."
            )
            raise ValueError(msg)
        if (
            self.planner_mode == "deterministic"
            and not self.candidate_searches
            and not self.source_searches
        ):
            msg = "Provide source_searches or candidate_searches for this deterministic evidence-run slice"
            raise ValueError(msg)
        if self.sources:
            return self
        candidate_sources = [
            candidate.source_key
            for candidate in self.candidate_searches
        ]
        live_sources = [source.source_key for source in self.source_searches]
        if not candidate_sources and not live_sources:
            return self
        self.sources = list(dict.fromkeys([*live_sources, *candidate_sources]))
        return self


class EvidenceSelectionRunResponse(BaseModel):
    """Completed evidence-selection run response."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    goal: str
    instructions: str | None = None
    mode: EvidenceSelectionMode
    planner_mode: EvidenceSelectionSourcePlannerMode = "deterministic"
    source_plan: JSONObject
    workspace_snapshot: JSONObject
    selected_records: list[JSONObject]
    skipped_records: list[JSONObject]
    deferred_records: list[JSONObject]
    handoffs: list[JSONObject]
    proposals: list[JSONObject]
    review_items: list[JSONObject]
    selected_count: int
    skipped_count: int
    deferred_count: int
    handoff_count: int
    proposal_count: int
    review_item_count: int
    errors: list[str]
    review_gate: JSONObject
    artifact_keys: list[str]


@router.post(
    "/{space_id}/agents/evidence-selection/runs",
    response_model=EvidenceSelectionRunResponse,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": HarnessAcceptedRunResponse}},
    summary="Start one goal-driven evidence-selection run",
)
async def create_evidence_selection_run(  # noqa: PLR0913
    space_id: UUID,
    request: EvidenceSelectionRunRequest,
    *,
    prefer: Annotated[str | None, Header(alias="Prefer")] = None,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
) -> EvidenceSelectionRunResponse | JSONResponse:
    """Queue one evidence-selection run and wait for a sync result when possible."""

    return await _create_evidence_selection_run_from_parts(
        space_id=space_id,
        goal=request.goal,
        instructions=request.instructions,
        sources=tuple(request.sources),
        proposal_mode=request.proposal_mode,
        mode=request.mode,
        planner_mode=request.planner_mode,
        live_network_allowed=request.live_network_allowed,
        source_searches=tuple(search.to_runtime() for search in request.source_searches),
        candidate_searches=tuple(
            candidate.to_runtime() for candidate in request.candidate_searches
        ),
        max_records_per_search=request.max_records_per_search,
        max_handoffs=request.max_handoffs,
        inclusion_criteria=tuple(request.inclusion_criteria),
        exclusion_criteria=tuple(request.exclusion_criteria),
        population_context=request.population_context,
        evidence_types=tuple(request.evidence_types),
        priority_outcomes=tuple(request.priority_outcomes),
        title=request.title or "Evidence Selection Harness",
        parent_run_id=None,
        created_by=current_user.id,
        prefer=prefer,
        run_registry=run_registry,
        artifact_store=artifact_store,
        execution_services=execution_services,
    )


@router.post(
    "/{space_id}/agents/evidence-selection/runs/{parent_run_id}/follow-ups",
    response_model=EvidenceSelectionRunResponse,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": HarnessAcceptedRunResponse}},
    summary="Start one evidence-selection follow-up run",
)
async def create_evidence_selection_follow_up_run(  # noqa: PLR0913
    space_id: UUID,
    parent_run_id: UUID,
    request: EvidenceSelectionFollowUpRequest,
    *,
    prefer: Annotated[str | None, Header(alias="Prefer")] = None,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
) -> EvidenceSelectionRunResponse | JSONResponse:
    """Queue one follow-up run inside the same research space."""

    parent = run_registry.get_run(space_id=space_id, run_id=parent_run_id)
    if parent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parent run '{parent_run_id}' not found in space '{space_id}'.",
        )
    if parent.harness_id != "evidence-selection":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Evidence-run follow-ups require an evidence-selection parent run.",
        )
    if parent.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Evidence-run follow-ups require a completed evidence-selection "
                "parent run."
            ),
        )
    parent_goal = parent.input_payload.get("goal")
    goal = request.goal or (parent_goal if isinstance(parent_goal, str) else None)
    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Follow-up requires a goal when the parent run has no goal.",
        )
    sources = _normalize_follow_up_sources(
        request.sources,
        request.source_searches,
        request.candidate_searches,
    )
    return await _create_evidence_selection_run_from_parts(
        space_id=space_id,
        goal=goal,
        instructions=request.instructions,
        sources=tuple(sources),
        proposal_mode=request.proposal_mode,
        mode=request.mode,
        planner_mode=request.planner_mode,
        live_network_allowed=request.live_network_allowed,
        source_searches=tuple(search.to_runtime() for search in request.source_searches),
        candidate_searches=tuple(
            candidate.to_runtime() for candidate in request.candidate_searches
        ),
        max_records_per_search=request.max_records_per_search,
        max_handoffs=request.max_handoffs,
        inclusion_criteria=tuple(request.inclusion_criteria),
        exclusion_criteria=tuple(request.exclusion_criteria),
        population_context=request.population_context,
        evidence_types=tuple(request.evidence_types),
        priority_outcomes=tuple(request.priority_outcomes),
        title=request.title or "Evidence Selection Follow-up",
        parent_run_id=parent_run_id,
        created_by=current_user.id,
        prefer=prefer,
        run_registry=run_registry,
        artifact_store=artifact_store,
        execution_services=execution_services,
    )


async def _create_evidence_selection_run_from_parts(  # noqa: PLR0913
    *,
    space_id: UUID,
    goal: str,
    instructions: str | None,
    sources: tuple[str, ...],
    proposal_mode: EvidenceSelectionProposalMode,
    mode: EvidenceSelectionMode,
    planner_mode: EvidenceSelectionSourcePlannerMode,
    live_network_allowed: bool,
    source_searches: tuple[EvidenceSelectionLiveSourceSearch, ...],
    candidate_searches: tuple[EvidenceSelectionCandidateSearch, ...],
    max_records_per_search: int,
    max_handoffs: int,
    inclusion_criteria: tuple[str, ...],
    exclusion_criteria: tuple[str, ...],
    population_context: str | None,
    evidence_types: tuple[str, ...],
    priority_outcomes: tuple[str, ...],
    title: str,
    parent_run_id: UUID | None,
    created_by: UUID,
    prefer: str | None,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    execution_services: HarnessExecutionServices,
) -> EvidenceSelectionRunResponse | JSONResponse:
    if (
        planner_mode == "model"
        and not source_searches
        and not candidate_searches
        and execution_services.source_planner is None
        and not is_model_source_planner_available()
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=model_source_planner_unavailable_detail(),
        )
    run = queue_evidence_selection_run(
        space_id=space_id,
        title=title,
        goal=goal,
        instructions=instructions,
        sources=sources,
        proposal_mode=proposal_mode,
        mode=mode,
        planner_mode=planner_mode,
        live_network_allowed=live_network_allowed,
        source_searches=source_searches,
        candidate_searches=candidate_searches,
        max_records_per_search=max_records_per_search,
        max_handoffs=max_handoffs,
        inclusion_criteria=inclusion_criteria,
        exclusion_criteria=exclusion_criteria,
        population_context=population_context,
        evidence_types=evidence_types,
        priority_outcomes=priority_outcomes,
        parent_run_id=parent_run_id,
        created_by=created_by,
        run_registry=run_registry,
        artifact_store=artifact_store,
        runtime=execution_services.runtime,
    )
    wake_worker_for_queued_run(run=run, execution_services=execution_services)
    if prefers_respond_async(prefer):
        accepted = build_accepted_run_response(run=run, run_registry=run_registry)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=accepted.model_dump(mode="json"),
            headers={"Preference-Applied": "respond-async"},
        )
    if should_require_worker_ready(execution_services=execution_services):
        require_worker_ready(operation_name="Evidence selection")
    await maybe_execute_test_worker_run(run=run, services=execution_services)
    wait_outcome = await wait_for_terminal_run(
        space_id=space_id,
        run_id=run.id,
        run_registry=run_registry,
        timeout_seconds=get_settings().sync_wait_timeout_seconds,
        poll_interval_seconds=get_settings().sync_wait_poll_seconds,
    )
    if wait_outcome.timed_out:
        accepted = build_accepted_run_response(run=run, run_registry=run_registry)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=accepted.model_dump(mode="json"),
        )
    if wait_outcome.run is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reload completed evidence-selection run '{run.id}'.",
        )
    if wait_outcome.run.status == "failed":
        raise_for_failed_run(run=wait_outcome.run, artifact_store=artifact_store)
    payload = load_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
    )
    return EvidenceSelectionRunResponse.model_validate(payload, strict=False)


def _normalize_follow_up_sources(
    sources: list[str],
    source_searches: list[EvidenceSelectionSourceSearchRequest],
    candidate_searches: list[EvidenceSelectionCandidateSearchRequest],
) -> list[str]:
    if sources:
        return sources
    return list(
        dict.fromkeys(
            [
                *(source.source_key for source in source_searches),
                *(candidate.source_key for candidate in candidate_searches),
            ],
        ),
    )


__all__ = [
    "EvidenceSelectionCandidateSearchRequest",
    "EvidenceSelectionFollowUpRequest",
    "EvidenceSelectionRunRequest",
    "EvidenceSelectionRunResponse",
    "EvidenceSelectionSourceSearchRequest",
    "create_evidence_selection_follow_up_run",
    "create_evidence_selection_run",
    "router",
]
