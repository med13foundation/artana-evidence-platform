"""Public v2 response models and payload translation helpers."""

from __future__ import annotations

import json

from artana_evidence_api.queued_run import HarnessAcceptedRunResponse
from artana_evidence_api.routers import research_init, runs
from artana_evidence_api.routers.artifacts import (
    HarnessArtifactListResponse,
    HarnessArtifactResponse,
    HarnessWorkspaceResponse,
)
from artana_evidence_api.routers.harnesses import HarnessTemplateResponse
from artana_evidence_api.routers.runs import (
    HarnessRunProgressResponse,
    HarnessRunResponse,
    HarnessRunResumeResponse,
    RunCapabilitiesResponse,
    RunPolicyDecisionsResponse,
)
from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

_SCALAR_PUBLIC_KEY_RENAMES = {
    "approval_intent": "planned_actions",
    "approval_intent_key": "planned_actions_key",
    "agent_run_id": "agent_task_id",
    "artifact_key": "output_key",
    "artifact_keys": "output_keys",
    "artifacts_url": "outputs_url",
    "bootstrap_run_id": "bootstrap_task_id",
    "chat_graph_write_run_id": "chat_suggested_updates_task_id",
    "chat_run_id": "chat_task_id",
    "curation_run_id": "curation_task_id",
    "harness_id": "workflow_template_id",
    "ingestion_run_id": "ingestion_task_id",
    "last_enrichment_run_id": "last_enrichment_task_id",
    "last_extraction_run_id": "last_extraction_task_id",
    "last_run_id": "last_task_id",
    "pipeline_run_id": "pipeline_task_id",
    "policy_decisions": "decisions",
    "run_id": "task_id",
    "source_run_id": "source_task_id",
    "workspace_summary": "working_state_summary",
    "workspace_url": "working_state_url",
}


class TaskCreateRequest(BaseModel):
    """Create one generic task from a public workflow template."""

    model_config = ConfigDict(strict=True)

    workflow_template_id: str = Field(..., min_length=1, max_length=128)
    title: str | None = Field(default=None, min_length=1, max_length=256)
    input_payload: JSONObject = Field(default_factory=dict)

    def to_v1(self) -> runs.HarnessRunCreateRequest:
        return runs.HarnessRunCreateRequest(
            harness_id=self.workflow_template_id,
            title=self.title,
            input_payload=self.input_payload,
        )


class TaskResponse(BaseModel):
    """Serialized public task record."""

    model_config = ConfigDict(strict=True)

    id: str
    space_id: str
    workflow_template_id: str
    title: str
    status: str
    input_payload: JSONObject
    graph_service_status: str
    graph_service_version: str
    created_at: str
    updated_at: str

    @classmethod
    def from_v1(cls, response: HarnessRunResponse) -> TaskResponse:
        return cls(
            id=response.id,
            space_id=response.space_id,
            workflow_template_id=response.harness_id,
            title=response.title,
            status=response.status,
            input_payload=response.input_payload,
            graph_service_status=response.graph_service_status,
            graph_service_version=response.graph_service_version,
            created_at=response.created_at,
            updated_at=response.updated_at,
        )


class TaskListResponse(BaseModel):
    """List response for public tasks."""

    model_config = ConfigDict(strict=True)

    tasks: list[TaskResponse]
    total: int
    offset: int
    limit: int

    @classmethod
    def from_v1(cls, response: runs.HarnessRunListResponse) -> TaskListResponse:
        return cls(
            tasks=[TaskResponse.from_v1(item) for item in response.runs],
            total=response.total,
            offset=response.offset,
            limit=response.limit,
        )


class TaskProgressResponse(BaseModel):
    """Serialized task progress snapshot."""

    model_config = ConfigDict(strict=True)

    task_id: str
    status: str
    phase: str
    message: str
    progress_percent: float
    completed_steps: int
    total_steps: int | None
    resume_point: str | None
    metadata: JSONObject
    created_at: str
    updated_at: str

    @classmethod
    def from_v1(
        cls,
        response: HarnessRunProgressResponse,
    ) -> TaskProgressResponse:
        return cls(
            task_id=response.run_id,
            status=response.status,
            phase=response.phase,
            message=response.message,
            progress_percent=response.progress_percent,
            completed_steps=response.completed_steps,
            total_steps=response.total_steps,
            resume_point=response.resume_point,
            metadata=response.metadata,
            created_at=response.created_at,
            updated_at=response.updated_at,
        )


class TaskResumeResponse(BaseModel):
    """Combined task summary and progress after a resume request."""

    model_config = ConfigDict(strict=True)

    task: TaskResponse
    progress: TaskProgressResponse

    @classmethod
    def from_v1(cls, response: HarnessRunResumeResponse) -> TaskResumeResponse:
        return cls(
            task=TaskResponse.from_v1(response.run),
            progress=TaskProgressResponse.from_v1(response.progress),
        )


class TaskOutputResponse(BaseModel):
    """Serialized public task output payload."""

    model_config = ConfigDict(strict=True)

    key: str
    media_type: str
    content: JSONObject
    created_at: str
    updated_at: str

    @classmethod
    def from_v1(cls, response: HarnessArtifactResponse) -> TaskOutputResponse:
        return cls(
            key=response.key,
            media_type=response.media_type,
            content=response.content,
            created_at=response.created_at,
            updated_at=response.updated_at,
        )


class TaskOutputListResponse(BaseModel):
    """List response for public task outputs."""

    model_config = ConfigDict(strict=True)

    outputs: list[TaskOutputResponse]
    total: int
    offset: int
    limit: int

    @classmethod
    def from_v1(
        cls,
        response: HarnessArtifactListResponse,
    ) -> TaskOutputListResponse:
        return cls(
            outputs=[TaskOutputResponse.from_v1(item) for item in response.artifacts],
            total=response.total,
            offset=response.offset,
            limit=response.limit,
        )


class TaskWorkingStateResponse(BaseModel):
    """Serialized task working state snapshot."""

    model_config = ConfigDict(strict=True)

    working_state: JSONObject
    created_at: str
    updated_at: str

    @classmethod
    def from_v1(
        cls,
        response: HarnessWorkspaceResponse,
    ) -> TaskWorkingStateResponse:
        return cls(
            working_state=response.snapshot,
            created_at=response.created_at,
            updated_at=response.updated_at,
        )


class TaskCapabilitiesResponse(BaseModel):
    """Serialized public task capability snapshot."""

    model_config = ConfigDict(strict=True)

    task_id: str
    space_id: str
    workflow_template_id: str
    tool_groups: list[str] = Field(default_factory=list)
    preloaded_skill_names: list[str] = Field(default_factory=list)
    allowed_skill_names: list[str] = Field(default_factory=list)
    active_skill_names: list[str] = Field(default_factory=list)
    policy_profile: JSONObject
    output_key: str
    created_at: str
    updated_at: str
    visible_tools: list[runs.ToolCapabilityDescriptor] = Field(default_factory=list)
    filtered_tools: list[runs.ToolCapabilityDescriptor] = Field(default_factory=list)

    @classmethod
    def from_v1(
        cls,
        response: RunCapabilitiesResponse,
    ) -> TaskCapabilitiesResponse:
        return cls(
            task_id=response.run_id,
            space_id=response.space_id,
            workflow_template_id=response.harness_id,
            tool_groups=response.tool_groups,
            preloaded_skill_names=response.preloaded_skill_names,
            allowed_skill_names=response.allowed_skill_names,
            active_skill_names=response.active_skill_names,
            policy_profile=response.policy_profile,
            output_key=response.artifact_key,
            created_at=response.created_at,
            updated_at=response.updated_at,
            visible_tools=response.visible_tools,
            filtered_tools=response.filtered_tools,
        )


class TaskDecisionsResponse(BaseModel):
    """Serialized public task decision log."""

    model_config = ConfigDict(strict=True)

    task_id: str
    space_id: str
    workflow_template_id: str
    output_key: str
    declared_policy: list[JSONObject] = Field(default_factory=list)
    records: list[runs.ToolDecisionRecord] = Field(default_factory=list)
    summary: JSONObject
    created_at: str
    updated_at: str

    @classmethod
    def from_v1(
        cls,
        response: RunPolicyDecisionsResponse,
    ) -> TaskDecisionsResponse:
        return cls(
            task_id=response.run_id,
            space_id=response.space_id,
            workflow_template_id=response.harness_id,
            output_key=response.artifact_key,
            declared_policy=response.declared_policy,
            records=response.records,
            summary=response.summary,
            created_at=response.created_at,
            updated_at=response.updated_at,
        )


class WorkflowTemplateResponse(BaseModel):
    """Serialized public workflow template."""

    model_config = ConfigDict(strict=True)

    id: str
    display_name: str
    summary: str
    tool_groups: list[str]
    outputs: list[str]
    preloaded_skill_names: list[str]
    allowed_skill_names: list[str]
    default_task_budget: JSONObject | None = None

    @classmethod
    def from_v1(
        cls,
        response: HarnessTemplateResponse,
    ) -> WorkflowTemplateResponse:
        return cls(
            id=response.id,
            display_name=response.display_name,
            summary=response.summary,
            tool_groups=response.tool_groups,
            outputs=response.outputs,
            preloaded_skill_names=response.preloaded_skill_names,
            allowed_skill_names=response.allowed_skill_names,
            default_task_budget=response.default_run_budget,
        )


class WorkflowTemplateListResponse(BaseModel):
    """List response for public workflow templates."""

    model_config = ConfigDict(strict=True)

    workflow_templates: list[WorkflowTemplateResponse]
    total: int


class AcceptedTaskResponse(BaseModel):
    """Accepted async response for one queued public task."""

    model_config = ConfigDict(strict=True)

    task: TaskResponse
    progress_url: str
    events_url: str
    working_state_url: str
    outputs_url: str
    stream_url: str | None = None
    session: JSONObject | None = None

    @classmethod
    def from_v1(cls, response: HarnessAcceptedRunResponse) -> AcceptedTaskResponse:
        return cls(
            task=TaskResponse.from_v1(HarnessRunResponse.model_validate(response.run)),
            progress_url=_publicize_relative_url(response.progress_url) or "",
            events_url=_publicize_relative_url(response.events_url) or "",
            working_state_url=_publicize_relative_url(response.workspace_url) or "",
            outputs_url=_publicize_relative_url(response.artifacts_url) or "",
            stream_url=_publicize_relative_url(response.stream_url),
            session=_publicize_json_object(response.session),
        )


class ResearchPlanResponse(BaseModel):
    """Response from public research planning kickoff."""

    model_config = ConfigDict(strict=True)

    task: TaskResponse
    task_progress_url: str = Field(..., min_length=1)
    pubmed_results: list[research_init.ResearchInitPubMedResult]
    documents_ingested: int
    proposal_count: int
    research_state: JSONObject | None
    pending_questions: list[str]
    errors: list[str]

    @classmethod
    def from_v1(
        cls,
        response: research_init.ResearchInitResponse,
    ) -> ResearchPlanResponse:
        return cls(
            task=TaskResponse.from_v1(response.run),
            task_progress_url=_publicize_relative_url(response.poll_url) or "",
            pubmed_results=response.pubmed_results,
            documents_ingested=response.documents_ingested,
            proposal_count=response.proposal_count,
            research_state=response.research_state,
            pending_questions=response.pending_questions,
            errors=response.errors,
        )


def _publicize_relative_url(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    return (
        value.replace("/v1/", "/v2/")
        .replace("/runs/", "/tasks/")
        .replace("/policy-decisions", "/decisions")
        .replace("/artifacts", "/outputs")
        .replace("/workspace", "/working-state")
        .replace("/intent", "/planned-actions")
        .replace("/harnesses", "/workflow-templates")
        .replace("/review-queue", "/review-items")
        .replace("/graph-explorer", "/evidence-map")
        .replace("/graph-write-candidates", "/suggested-updates")
        .replace("/research-init", "/research-plan")
        .replace("/agents/research-bootstrap/runs", "/workflows/topic-setup/tasks")
        .replace("/agents/graph-curation/runs", "/workflows/evidence-curation/tasks")
        .replace("/agents/full-ai-orchestrator/runs", "/workflows/autopilot/tasks")
        .replace("/agents/supervisor/runs", "/workflows/full-research/tasks")
    )


def _looks_like_task_record(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return {
        "id",
        "space_id",
        "status",
        "created_at",
        "updated_at",
    }.issubset(value)


def _looks_like_task_progress(value: object) -> bool:
    return isinstance(value, dict) and {
        "run_id",
        "status",
        "phase",
        "progress_percent",
        "completed_steps",
        "created_at",
        "updated_at",
    }.issubset(value)


def _looks_like_task_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and all(_looks_like_task_record(item) for item in value)
        and bool(value)
    )


def _looks_like_output_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and all(
            isinstance(item, dict) and {"key", "media_type", "content"}.issubset(item)
            for item in value
        )
        and bool(value)
    )


def _looks_like_working_state(value: object) -> bool:
    return isinstance(value, dict) and ("snapshot" in value or "working_state" in value)


def _looks_like_accepted_task_response(value: object) -> bool:
    return isinstance(value, dict) and {
        "run",
        "progress_url",
        "events_url",
        "workspace_url",
        "artifacts_url",
    }.issubset(value)


def _looks_like_plan(value: object) -> bool:
    return (
        isinstance(value, dict) and "summary" in value and "proposed_actions" in value
    )


def _looks_like_workflow_template_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and all(
            isinstance(item, dict)
            and {"id", "display_name", "tool_groups"}.issubset(item)
            for item in value
        )
        and bool(value)
    )


def _looks_like_task_capabilities(value: object) -> bool:
    return isinstance(value, dict) and {
        "run_id",
        "space_id",
        "harness_id",
        "artifact_key",
        "tool_groups",
        "policy_profile",
    }.issubset(value)


def _looks_like_task_decisions(value: object) -> bool:
    return isinstance(value, dict) and {
        "run_id",
        "space_id",
        "harness_id",
        "artifact_key",
        "declared_policy",
        "records",
        "summary",
    }.issubset(value)


def _looks_like_graph_snapshot(value: object) -> bool:
    return isinstance(value, dict) and {
        "id",
        "space_id",
        "source_run_id",
        "claim_ids",
        "relation_ids",
        "graph_document_hash",
    }.issubset(value)


def _looks_like_claim_curation_summary(value: object) -> bool:
    return isinstance(value, dict) and {
        "status",
        "run_id",
        "proposal_ids",
        "proposal_count",
        "blocked_proposal_count",
        "pending_approval_count",
        "reason",
    }.issubset(value)


def _looks_like_supervisor_step(value: object) -> bool:
    return (
        isinstance(value, dict)
        and {
            "name",
            "status",
            "detail",
        }.issubset(value)
        and ("run_id" in value or "harness_id" in value)
    )


def _looks_like_supervisor_detail(value: object) -> bool:
    return isinstance(value, dict) and {
        "workflow",
        "artifact_keys",
        "bootstrap_run_id",
        "chat_graph_write_review_count",
        "steps",
    }.issubset(value)


def _looks_like_supervisor_review(value: object) -> bool:
    return isinstance(value, dict) and {
        "reviewed_at",
        "chat_run_id",
        "chat_session_id",
        "candidate_index",
        "decision",
        "proposal_id",
        "candidate",
    }.issubset(value)


def _looks_like_supervisor_dashboard_pointer(value: object) -> bool:
    return isinstance(value, dict) and {
        "run_id",
        "title",
        "status",
        "curation_source",
        "timestamp",
    }.issubset(value)


def _looks_like_supervisor_dashboard_approval_pointer(value: object) -> bool:
    return isinstance(value, dict) and {
        "run_id",
        "pending_approval_count",
        "curation_run_id",
        "approval_intent_key",
    }.issubset(value)


def _looks_like_supervisor_curation_artifact_keys(value: object) -> bool:
    return isinstance(value, dict) and {
        "curation_packet",
        "review_plan",
        "approval_intent",
    }.issubset(value)


def _should_rename_scalar_key(*, mapping: dict[object, object], key: str) -> bool:
    if key in {"workspace_url", "artifacts_url"}:
        match = _looks_like_accepted_task_response(mapping)
    elif key in {"harness_id", "run_id"}:
        match = (
            _looks_like_task_record(mapping)
            or _looks_like_task_progress(mapping)
            or _looks_like_task_capabilities(mapping)
            or _looks_like_task_decisions(mapping)
            or _looks_like_supervisor_step(mapping)
            or _looks_like_claim_curation_summary(mapping)
        )
    elif key == "artifact_key":
        match = _looks_like_task_capabilities(mapping) or _looks_like_task_decisions(
            mapping
        )
    elif key == "source_run_id":
        match = _looks_like_graph_snapshot(mapping)
    elif key in {
        "bootstrap_run_id",
        "chat_run_id",
        "chat_graph_write_run_id",
        "curation_run_id",
    }:
        match = (
            _looks_like_supervisor_detail(mapping)
            or _looks_like_supervisor_review(mapping)
            or _looks_like_supervisor_dashboard_approval_pointer(mapping)
            or _looks_like_supervisor_dashboard_pointer(mapping)
        )
    elif key == "artifact_keys":
        match = _looks_like_supervisor_detail(mapping)
    elif key in {"approval_intent", "approval_intent_key"}:
        match = _looks_like_supervisor_curation_artifact_keys(
            mapping
        ) or _looks_like_supervisor_dashboard_approval_pointer(mapping)
    elif key == "policy_decisions":
        match = _looks_like_task_decisions(mapping)
    else:
        match = False
    return match


def _public_key_for(
    *,
    mapping: dict[object, object],
    key: str,
    value: object,
) -> str:
    renamed = _SCALAR_PUBLIC_KEY_RENAMES.get(key)
    if renamed is not None and _should_rename_scalar_key(mapping=mapping, key=key):
        return renamed

    shape_based_key = key
    if key == "run" and _looks_like_task_record(value):
        shape_based_key = "task"
    elif key == "runs" and _looks_like_task_list(value):
        shape_based_key = "tasks"
    elif key == "artifacts" and _looks_like_output_list(value):
        shape_based_key = "outputs"
    elif key == "workspace" and _looks_like_working_state(value):
        shape_based_key = "working_state"
    elif key == "intent" and _looks_like_plan(value):
        shape_based_key = "plan"
    elif key == "harnesses" and _looks_like_workflow_template_list(value):
        shape_based_key = "workflow_templates"
    return shape_based_key


def _publicize_json(value: object) -> object:
    if isinstance(value, dict):
        publicized: dict[str, object] = {}
        for key, item in value.items():
            public_key = _public_key_for(mapping=value, key=str(key), value=item)
            publicized[public_key] = _publicize_json(item)
        return publicized
    if isinstance(value, list):
        return [_publicize_json(item) for item in value]
    if isinstance(value, str) and value.startswith("/v1/"):
        return _publicize_relative_url(value)
    return value


def _publicize_json_object(value: object) -> JSONObject | None:
    publicized = _publicize_json(value)
    return publicized if isinstance(publicized, dict) else None


def _publicize_response_payload(result: object) -> object:
    if isinstance(result, BaseModel):
        return _publicize_json(result.model_dump(mode="json"))
    if isinstance(result, JSONResponse):
        return _publicize_json(json.loads(result.body))
    return _publicize_json(result)


def _publicized_json_response(result: JSONResponse) -> JSONResponse:
    content = _publicize_json(json.loads(result.body))
    headers = dict(result.headers)
    return JSONResponse(
        status_code=result.status_code,
        content=content,
        headers=headers,
    )




__all__ = [
    "AcceptedTaskResponse",
    "ResearchPlanResponse",
    "TaskCapabilitiesResponse",
    "TaskCreateRequest",
    "TaskDecisionsResponse",
    "TaskListResponse",
    "TaskOutputListResponse",
    "TaskOutputResponse",
    "TaskProgressResponse",
    "TaskResponse",
    "TaskResumeResponse",
    "TaskWorkingStateResponse",
    "WorkflowTemplateListResponse",
    "WorkflowTemplateResponse",
    "_publicize_json",
    "_publicize_json_object",
    "_publicize_response_payload",
    "_publicized_json_response",
]
