"""User-facing v2 route names for the evidence workflow API."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from artana_evidence_api.approval_store import HarnessApprovalStore
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.auth import (
    HarnessUser,
    get_current_harness_user,
    require_harness_read_access,
)
from artana_evidence_api.chat_sessions import HarnessChatSessionStore
from artana_evidence_api.dependencies import (
    get_alphafold_source_gateway,
    get_approval_store,
    get_artifact_store,
    get_chat_session_store,
    get_clinicaltrials_source_gateway,
    get_clinvar_source_gateway,
    get_direct_source_search_store,
    get_document_binary_store,
    get_document_store,
    get_drugbank_source_gateway,
    get_graph_api_gateway,
    get_harness_execution_services,
    get_identity_gateway,
    get_mgi_source_gateway,
    get_proposal_store,
    get_pubmed_discovery_service,
    get_research_state_store,
    get_review_item_store,
    get_run_registry,
    get_source_search_handoff_store,
    get_uniprot_source_gateway,
    get_zfin_source_gateway,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.direct_source_search import (
    AlphaFoldSourceSearchRequest,
    AlphaFoldSourceSearchResponse,
    ClinicalTrialsSourceSearchRequest,
    ClinicalTrialsSourceSearchResponse,
    ClinVarSourceSearchRequest,
    ClinVarSourceSearchResponse,
    DirectSourceSearchStore,
    DrugBankSourceSearchRequest,
    DrugBankSourceSearchResponse,
    MGISourceSearchRequest,
    MGISourceSearchResponse,
    UniProtSourceSearchRequest,
    UniProtSourceSearchResponse,
    ZFINSourceSearchRequest,
    ZFINSourceSearchResponse,
    run_alphafold_direct_search,
    run_clinicaltrials_direct_search,
    run_clinvar_direct_search,
    run_drugbank_direct_search,
    run_mgi_direct_search,
    run_uniprot_direct_search,
    run_zfin_direct_search,
)
from artana_evidence_api.direct_source_search import (
    MarrvelSourceSearchResponse as DurableMarrvelSourceSearchResponse,
)
from artana_evidence_api.document_binary_store import HarnessDocumentBinaryStore
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.graph_client import GraphTransportBundle
from artana_evidence_api.harness_runtime import HarnessExecutionServices
from artana_evidence_api.identity.contracts import IdentityGateway
from artana_evidence_api.proposal_store import HarnessProposalStore
from artana_evidence_api.queued_run_support import HarnessAcceptedRunResponse
from artana_evidence_api.research_state import HarnessResearchStateStore
from artana_evidence_api.review_item_store import HarnessReviewItemStore
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.source_enrichment_bridges import (
    AllianceGeneGatewayProtocol,
    AlphaFoldGatewayProtocol,
    ClinicalTrialsGatewayProtocol,
    ClinVarGatewayProtocol,
    DrugBankGatewayProtocol,
    UniProtGatewayProtocol,
)
from artana_evidence_api.source_registry import (
    SourceDefinition,
    SourceListResponse,
    direct_search_source_keys,
    get_source_definition,
    list_source_definitions,
)
from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    SourceResultCapture,
    SourceSearchResponse,
    compact_provenance,
    source_result_capture_metadata,
)
from artana_evidence_api.source_search_handoff import (
    SourceSearchHandoffConflictError,
    SourceSearchHandoffNotFoundError,
    SourceSearchHandoffRequest,
    SourceSearchHandoffResponse,
    SourceSearchHandoffSelectionError,
    SourceSearchHandoffService,
    SourceSearchHandoffStore,
    SourceSearchHandoffUnsupportedError,
)
from artana_evidence_api.types.common import JSONObject, json_object_or_empty
from fastapi import (
    APIRouter,
    Body,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.responses import JSONResponse, StreamingResponse

from . import (
    authentication,
    chat,
    continuous_learning_runs,
    documents,
    full_ai_orchestrator_runs,
    graph_connection_runs,
    graph_curation_runs,
    graph_explorer,
    graph_search_runs,
    harnesses,
    hypothesis_runs,
    marrvel,
    mechanism_discovery_runs,
    proposals,
    pubmed,
    research_bootstrap_runs,
    research_init,
    research_onboarding_runs,
    research_state,
    review_queue,
    runs,
    schedules,
    spaces,
    supervisor_runs,
)
from .approvals import (
    HarnessApprovalDecisionRequest,
    HarnessApprovalListResponse,
    HarnessApprovalResponse,
    HarnessRunIntentRequest,
    HarnessRunIntentResponse,
)
from .approvals import decide_approval as _decide_approval
from .approvals import list_approvals as _list_approvals
from .approvals import record_intent as _record_intent
from .artifacts import (
    HarnessArtifactListResponse,
    HarnessArtifactResponse,
    HarnessWorkspaceResponse,
)
from .artifacts import get_artifact as _get_artifact
from .artifacts import get_workspace as _get_workspace
from .artifacts import list_artifacts as _list_artifacts
from .chat import stream_chat_message as _stream_chat_message
from .harnesses import HarnessTemplateResponse
from .harnesses import get_harness as _get_harness
from .runs import (
    HarnessRunEventListResponse,
    HarnessRunProgressResponse,
    HarnessRunResponse,
    HarnessRunResumeRequest,
    HarnessRunResumeResponse,
    RunCapabilitiesResponse,
    RunPolicyDecisionsResponse,
)
from .runs import get_run as _get_run
from .runs import get_run_capabilities as _get_run_capabilities
from .runs import get_run_policy_decisions as _get_run_policy_decisions
from .runs import get_run_progress as _get_run_progress
from .runs import list_run_events as _list_run_events
from .runs import resume_run as _resume_run
from .supervisor_runs import get_supervisor_run as _get_supervisor_run
from .supervisor_runs import (
    review_supervisor_chat_graph_write_candidate as _review_supervisor_update,
)

router = APIRouter()

_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_APPROVAL_STORE_DEPENDENCY = Depends(get_approval_store)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_CHAT_SESSION_STORE_DEPENDENCY = Depends(get_chat_session_store)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)
_PUBMED_DISCOVERY_SERVICE_DEPENDENCY = Depends(get_pubmed_discovery_service)
_MARRVEL_DISCOVERY_SERVICE_DEPENDENCY = Depends(marrvel.get_marrvel_discovery_service)
_DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY = Depends(get_direct_source_search_store)
_SOURCE_SEARCH_HANDOFF_STORE_DEPENDENCY = Depends(get_source_search_handoff_store)
_DOCUMENT_STORE_DEPENDENCY = Depends(get_document_store)
_DOCUMENT_BINARY_STORE_DEPENDENCY = Depends(get_document_binary_store)
_PROPOSAL_STORE_DEPENDENCY = Depends(get_proposal_store)
_REVIEW_ITEM_STORE_DEPENDENCY = Depends(get_review_item_store)
_RESEARCH_STATE_STORE_DEPENDENCY = Depends(get_research_state_store)
_CLINVAR_SOURCE_GATEWAY_DEPENDENCY = Depends(get_clinvar_source_gateway)
_CLINICALTRIALS_SOURCE_GATEWAY_DEPENDENCY = Depends(
    get_clinicaltrials_source_gateway,
)
_UNIPROT_SOURCE_GATEWAY_DEPENDENCY = Depends(get_uniprot_source_gateway)
_ALPHAFOLD_SOURCE_GATEWAY_DEPENDENCY = Depends(get_alphafold_source_gateway)
_DRUGBANK_SOURCE_GATEWAY_DEPENDENCY = Depends(get_drugbank_source_gateway)
_MGI_SOURCE_GATEWAY_DEPENDENCY = Depends(get_mgi_source_gateway)
_ZFIN_SOURCE_GATEWAY_DEPENDENCY = Depends(get_zfin_source_gateway)
_OpenAPIResponses = dict[int | str, dict[str, Any]]
_SOURCE_NOT_FOUND_RESPONSE: _OpenAPIResponses = {
    status.HTTP_404_NOT_FOUND: {"description": "Source is not registered."},
}
_DIRECT_SOURCE_SEARCH_RESPONSES: _OpenAPIResponses = {
    status.HTTP_404_NOT_FOUND: {"description": "Source is not registered."},
    status.HTTP_501_NOT_IMPLEMENTED: {
        "description": "Source does not support direct search yet.",
    },
}


class PubMedSourceSearchResponse(pubmed.DiscoverySearchJob):
    """Typed v2 PubMed source-search response with capture metadata."""

    source_capture: SourceResultCapture


class MarrvelSourceSearchResponse(DurableMarrvelSourceSearchResponse):
    """Typed v2 MARRVEL source-search response with durable capture metadata."""


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


def _validation_error_text(error: ValidationError) -> str:
    messages: list[str] = []
    for validation_error in error.errors():
        raw_location = validation_error.get("loc")
        message = str(validation_error.get("msg", "Validation error")).strip()
        if message.startswith("Value error, "):
            message = message.removeprefix("Value error, ").strip()
        if isinstance(raw_location, tuple | list) and raw_location:
            location = " -> ".join(str(part) for part in raw_location)
            messages.append(f"{location}: {message}")
        else:
            messages.append(message or "Validation error")
    return "; ".join(dict.fromkeys(messages)) or "Validation error"


def _require_source(source_key: str) -> SourceDefinition:
    source = get_source_definition(source_key)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{source_key}' is not registered.",
        )
    return source


def _require_direct_search_source(source_key: str) -> SourceDefinition:
    source = _require_source(source_key)
    if not source.direct_search_enabled:
        direct_sources = ", ".join(direct_search_source_keys())
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                f"Source '{source.source_key}' is available through research-plan "
                "or enrichment, but direct source search is not enabled yet. "
                f"Direct search sources: {direct_sources}."
            ),
        )
    return source


def _source_result_payload(
    result: object,
    *,
    source_capture: JSONObject | None = None,
) -> JSONObject:
    payload = json_object_or_empty(jsonable_encoder(result))
    if source_capture is not None:
        payload["source_capture"] = source_capture
    return payload


def _pubmed_source_capture(result: pubmed.DiscoverySearchJob) -> JSONObject:
    return source_result_capture_metadata(
        source_key="pubmed",
        capture_stage=SourceCaptureStage.SEARCH_RESULT,
        capture_method="direct_source_search",
        locator=f"pubmed:search:{result.id}",
        external_id=str(result.id),
        retrieved_at=result.completed_at or result.updated_at or result.created_at,
        search_id=str(result.id),
        query=result.query_preview,
        query_payload=result.parameters.model_dump(mode="json"),
        result_count=result.total_results,
        provenance=compact_provenance(
            provider=result.provider.value,
            status=result.status.value,
            storage_key=result.storage_key,
        ),
    )


def _marrvel_source_capture(result: marrvel.MarrvelSearchResponse) -> JSONObject:
    result_count = sum(result.panel_counts.values()) if result.panel_counts else 0
    return source_result_capture_metadata(
        source_key="marrvel",
        capture_stage=SourceCaptureStage.SEARCH_RESULT,
        capture_method="direct_source_search",
        locator=f"marrvel:search:{result.id}",
        search_id=str(result.id),
        query=result.query_value,
        query_payload={
            "query_mode": result.query_mode,
            "query_value": result.query_value,
            "gene_symbol": result.gene_symbol,
            "taxon_id": result.taxon_id,
            "available_panels": list(result.available_panels),
        },
        result_count=result_count,
        provenance=compact_provenance(
            status=result.status,
            gene_found=result.gene_found,
            resolved_gene_symbol=result.resolved_gene_symbol,
            resolved_variant=result.resolved_variant,
            panel_counts=result.panel_counts,
        ),
    )


_MARRVEL_VARIANT_PANEL_KEYS = frozenset(
    {
        "clinvar",
        "mutalyzer",
        "transvar",
        "gnomad_variant",
        "geno2mp_variant",
        "dgv_variant",
        "decipher_variant",
    },
)


def _marrvel_panel_records(result: marrvel.MarrvelSearchResponse) -> list[JSONObject]:
    records: list[JSONObject] = []
    for panel_name, payload in result.panels.items():
        panel_items = payload if isinstance(payload, list) else [payload]
        if not panel_items:
            continue
        for item_index, item in enumerate(panel_items):
            panel_payload = json_object_or_empty(item)
            variant_panel = panel_name in _MARRVEL_VARIANT_PANEL_KEYS
            record: JSONObject = {
                **panel_payload,
                "marrvel_record_id": f"{result.id}:{panel_name}:{item_index}",
                "panel_name": panel_name,
                "panel_family": "variant" if variant_panel else "context",
                "variant_aware_recommended": variant_panel,
                "query_mode": result.query_mode,
                "query_value": result.query_value,
                "gene_symbol": result.resolved_gene_symbol or result.gene_symbol,
                "resolved_gene_symbol": result.resolved_gene_symbol,
                "resolved_variant": result.resolved_variant,
                "taxon_id": result.taxon_id,
                "panel_payload": panel_payload,
            }
            hgvs_notation = _marrvel_hgvs_notation(result=result, record=panel_payload)
            if hgvs_notation is not None:
                record["hgvs_notation"] = hgvs_notation
            records.append(record)
    return records


def _marrvel_hgvs_notation(
    *,
    result: marrvel.MarrvelSearchResponse,
    record: JSONObject,
) -> str | None:
    for value in (
        record.get("hgvs_notation"),
        record.get("hgvs"),
        record.get("variant"),
        record.get("cdna_change"),
        record.get("protein_change"),
        result.resolved_variant,
        result.query_value if result.query_mode != "gene" else None,
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _durable_marrvel_source_search_response(
    *,
    result: marrvel.MarrvelSearchResponse,
    source_capture: SourceResultCapture,
    created_at: datetime,
    completed_at: datetime,
) -> DurableMarrvelSourceSearchResponse:
    records = _marrvel_panel_records(result)
    return DurableMarrvelSourceSearchResponse(
        id=result.id,
        space_id=result.space_id,
        query=result.query_value,
        query_mode=result.query_mode,
        query_value=result.query_value,
        gene_symbol=result.gene_symbol,
        resolved_gene_symbol=result.resolved_gene_symbol,
        resolved_variant=result.resolved_variant,
        taxon_id=result.taxon_id,
        gene_found=result.gene_found,
        gene_info=result.gene_info,
        omim_count=result.omim_count,
        variant_count=result.variant_count,
        panel_counts=result.panel_counts,
        panels=result.panels,
        available_panels=result.available_panels,
        record_count=len(records),
        records=records,
        created_at=created_at,
        completed_at=completed_at,
        source_capture=source_capture,
    )


def _parse_pubmed_source_search(payload: JSONObject) -> pubmed.PubMedSearchRequest:
    try:
        return pubmed.PubMedSearchRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_validation_error_text(exc),
        ) from exc


def _parse_marrvel_source_search(payload: JSONObject) -> marrvel.MarrvelSearchRequest:
    try:
        return marrvel.MarrvelSearchRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_validation_error_text(exc),
        ) from exc


def _parse_clinvar_source_search(payload: JSONObject) -> ClinVarSourceSearchRequest:
    try:
        return ClinVarSourceSearchRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_validation_error_text(exc),
        ) from exc


def _parse_clinicaltrials_source_search(
    payload: JSONObject,
) -> ClinicalTrialsSourceSearchRequest:
    try:
        return ClinicalTrialsSourceSearchRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_validation_error_text(exc),
        ) from exc


def _parse_uniprot_source_search(payload: JSONObject) -> UniProtSourceSearchRequest:
    try:
        return UniProtSourceSearchRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_validation_error_text(exc),
        ) from exc


def _parse_alphafold_source_search(payload: JSONObject) -> AlphaFoldSourceSearchRequest:
    try:
        return AlphaFoldSourceSearchRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_validation_error_text(exc),
        ) from exc


def _parse_drugbank_source_search(payload: JSONObject) -> DrugBankSourceSearchRequest:
    try:
        return DrugBankSourceSearchRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_validation_error_text(exc),
        ) from exc


def _parse_mgi_source_search(payload: JSONObject) -> MGISourceSearchRequest:
    try:
        return MGISourceSearchRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_validation_error_text(exc),
        ) from exc


def _parse_zfin_source_search(payload: JSONObject) -> ZFINSourceSearchRequest:
    try:
        return ZFINSourceSearchRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_validation_error_text(exc),
        ) from exc


async def _create_pubmed_source_search_payload(
    *,
    space_id: UUID,
    request: pubmed.PubMedSearchRequest,
    current_user: HarnessUser,
    pubmed_discovery_service: pubmed.PubMedDiscoveryService,
) -> JSONObject:
    pubmed_result = await pubmed.create_pubmed_search(
        space_id=space_id,
        request=request,
        current_user=current_user,
        pubmed_discovery_service=pubmed_discovery_service,
    )
    return _source_result_payload(
        pubmed_result,
        source_capture=_pubmed_source_capture(pubmed_result),
    )


def _get_pubmed_source_search_payload(
    *,
    space_id: UUID,
    search_id: UUID,
    current_user: HarnessUser,
    pubmed_discovery_service: pubmed.PubMedDiscoveryService,
) -> JSONObject:
    pubmed_result = pubmed.get_pubmed_search(
        space_id=space_id,
        job_id=search_id,
        current_user=current_user,
        pubmed_discovery_service=pubmed_discovery_service,
    )
    return _source_result_payload(
        pubmed_result,
        source_capture=_pubmed_source_capture(pubmed_result),
    )


async def _create_marrvel_source_search_payload(
    *,
    space_id: UUID,
    request: marrvel.MarrvelSearchRequest,
    current_user: HarnessUser,
    marrvel_discovery_service: marrvel.MarrvelDiscoveryService,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    created_at = datetime.now(UTC)
    marrvel_result = await marrvel.create_marrvel_search(
        space_id=space_id,
        request=request,
        current_user=current_user,
        marrvel_discovery_service=marrvel_discovery_service,
    )
    completed_at = datetime.now(UTC)
    source_capture = SourceResultCapture.model_validate(
        _marrvel_source_capture(marrvel_result),
    )
    durable_result = _durable_marrvel_source_search_response(
        result=marrvel_result,
        source_capture=source_capture,
        created_at=created_at,
        completed_at=completed_at,
    )
    saved_result = direct_source_search_store.save(
        durable_result,
        created_by=current_user.id,
    )
    return _source_result_payload(
        saved_result,
        source_capture=saved_result.source_capture.to_metadata(),
    )


def _get_marrvel_source_search_payload(
    *,
    space_id: UUID,
    search_id: UUID,
    current_user: HarnessUser,
    marrvel_discovery_service: marrvel.MarrvelDiscoveryService,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    stored_result = direct_source_search_store.get(
        space_id=space_id,
        source_key="marrvel",
        search_id=search_id,
    )
    if stored_result is not None:
        return _source_result_payload(
            stored_result,
            source_capture=stored_result.source_capture.to_metadata(),
        )

    marrvel_result = marrvel.get_marrvel_search(
        space_id=space_id,
        result_id=search_id,
        current_user=current_user,
        marrvel_discovery_service=marrvel_discovery_service,
    )
    completed_at = datetime.now(UTC)
    source_capture = SourceResultCapture.model_validate(
        _marrvel_source_capture(marrvel_result),
    )
    durable_result = _durable_marrvel_source_search_response(
        result=marrvel_result,
        source_capture=source_capture,
        created_at=completed_at,
        completed_at=completed_at,
    )
    return _source_result_payload(
        durable_result,
        source_capture=durable_result.source_capture.to_metadata(),
    )


async def _create_clinvar_source_search_payload(
    *,
    space_id: UUID,
    request: ClinVarSourceSearchRequest,
    current_user: HarnessUser,
    clinvar_gateway: ClinVarGatewayProtocol | None,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    if clinvar_gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ClinVar gateway is not available.",
        )
    try:
        result = await run_clinvar_direct_search(
            space_id=space_id,
            created_by=current_user.id,
            request=request,
            gateway=clinvar_gateway,
            store=direct_source_search_store,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ClinVar source search unavailable: {exc}",
        ) from exc
    return _source_result_payload(result)


def _get_clinvar_source_search_payload(
    *,
    space_id: UUID,
    search_id: UUID,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    result = direct_source_search_store.get(
        space_id=space_id,
        source_key="clinvar",
        search_id=search_id,
    )
    if not isinstance(result, ClinVarSourceSearchResponse):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ClinVar source search '{search_id}' not found in space '{space_id}'",
        )
    return _source_result_payload(result)


async def _create_clinicaltrials_source_search_payload(
    *,
    space_id: UUID,
    request: ClinicalTrialsSourceSearchRequest,
    current_user: HarnessUser,
    clinicaltrials_gateway: ClinicalTrialsGatewayProtocol | None,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    if clinicaltrials_gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ClinicalTrials.gov gateway is not available.",
        )
    try:
        result = await run_clinicaltrials_direct_search(
            space_id=space_id,
            created_by=current_user.id,
            request=request,
            gateway=clinicaltrials_gateway,
            store=direct_source_search_store,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ClinicalTrials.gov source search unavailable: {exc}",
        ) from exc
    return _source_result_payload(result)


def _get_clinicaltrials_source_search_payload(
    *,
    space_id: UUID,
    search_id: UUID,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    result = direct_source_search_store.get(
        space_id=space_id,
        source_key="clinical_trials",
        search_id=search_id,
    )
    if not isinstance(result, ClinicalTrialsSourceSearchResponse):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"ClinicalTrials.gov source search '{search_id}' not found "
                f"in space '{space_id}'"
            ),
        )
    return _source_result_payload(result)


async def _create_uniprot_source_search_payload(
    *,
    space_id: UUID,
    request: UniProtSourceSearchRequest,
    current_user: HarnessUser,
    uniprot_gateway: UniProtGatewayProtocol | None,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    if uniprot_gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="UniProt gateway is not available.",
        )
    try:
        result = await run_uniprot_direct_search(
            space_id=space_id,
            created_by=current_user.id,
            request=request,
            gateway=uniprot_gateway,
            store=direct_source_search_store,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"UniProt source search unavailable: {exc}",
        ) from exc
    return _source_result_payload(result)


def _get_uniprot_source_search_payload(
    *,
    space_id: UUID,
    search_id: UUID,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    result = direct_source_search_store.get(
        space_id=space_id,
        source_key="uniprot",
        search_id=search_id,
    )
    if not isinstance(result, UniProtSourceSearchResponse):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"UniProt source search '{search_id}' not found in space '{space_id}'",
        )
    return _source_result_payload(result)


async def _create_alphafold_source_search_payload(
    *,
    space_id: UUID,
    request: AlphaFoldSourceSearchRequest,
    current_user: HarnessUser,
    alphafold_gateway: AlphaFoldGatewayProtocol | None,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    if alphafold_gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AlphaFold gateway is not available.",
        )
    try:
        result = await run_alphafold_direct_search(
            space_id=space_id,
            created_by=current_user.id,
            request=request,
            gateway=alphafold_gateway,
            store=direct_source_search_store,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AlphaFold source search unavailable: {exc}",
        ) from exc
    return _source_result_payload(result)


def _get_alphafold_source_search_payload(
    *,
    space_id: UUID,
    search_id: UUID,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    result = direct_source_search_store.get(
        space_id=space_id,
        source_key="alphafold",
        search_id=search_id,
    )
    if not isinstance(result, AlphaFoldSourceSearchResponse):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"AlphaFold source search '{search_id}' not found "
                f"in space '{space_id}'"
            ),
        )
    return _source_result_payload(result)


async def _create_drugbank_source_search_payload(
    *,
    space_id: UUID,
    request: DrugBankSourceSearchRequest,
    current_user: HarnessUser,
    drugbank_gateway: DrugBankGatewayProtocol | None,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    if drugbank_gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DrugBank credentials are not configured.",
        )
    try:
        result = await run_drugbank_direct_search(
            space_id=space_id,
            created_by=current_user.id,
            request=request,
            gateway=drugbank_gateway,
            store=direct_source_search_store,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"DrugBank source search unavailable: {exc}",
        ) from exc
    return _source_result_payload(result)


def _get_drugbank_source_search_payload(
    *,
    space_id: UUID,
    search_id: UUID,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    result = direct_source_search_store.get(
        space_id=space_id,
        source_key="drugbank",
        search_id=search_id,
    )
    if not isinstance(result, DrugBankSourceSearchResponse):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DrugBank source search '{search_id}' not found in space '{space_id}'",
        )
    return _source_result_payload(result)


async def _create_mgi_source_search_payload(
    *,
    space_id: UUID,
    request: MGISourceSearchRequest,
    current_user: HarnessUser,
    mgi_gateway: AllianceGeneGatewayProtocol | None,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    if mgi_gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MGI gateway is not available.",
        )
    try:
        result = await run_mgi_direct_search(
            space_id=space_id,
            created_by=current_user.id,
            request=request,
            gateway=mgi_gateway,
            store=direct_source_search_store,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"MGI source search unavailable: {exc}",
        ) from exc
    return _source_result_payload(result)


def _get_mgi_source_search_payload(
    *,
    space_id: UUID,
    search_id: UUID,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    result = direct_source_search_store.get(
        space_id=space_id,
        source_key="mgi",
        search_id=search_id,
    )
    if not isinstance(result, MGISourceSearchResponse):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MGI source search '{search_id}' not found in space '{space_id}'",
        )
    return _source_result_payload(result)


async def _create_zfin_source_search_payload(
    *,
    space_id: UUID,
    request: ZFINSourceSearchRequest,
    current_user: HarnessUser,
    zfin_gateway: AllianceGeneGatewayProtocol | None,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    if zfin_gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ZFIN gateway is not available.",
        )
    try:
        result = await run_zfin_direct_search(
            space_id=space_id,
            created_by=current_user.id,
            request=request,
            gateway=zfin_gateway,
            store=direct_source_search_store,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ZFIN source search unavailable: {exc}",
        ) from exc
    return _source_result_payload(result)


def _get_zfin_source_search_payload(
    *,
    space_id: UUID,
    search_id: UUID,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    result = direct_source_search_store.get(
        space_id=space_id,
        source_key="zfin",
        search_id=search_id,
    )
    if not isinstance(result, ZFINSourceSearchResponse):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ZFIN source search '{search_id}' not found in space '{space_id}'",
        )
    return _source_result_payload(result)


def _find_route(source_router: APIRouter, *, path: str, method: str) -> APIRoute:
    for route in source_router.routes:
        if (
            isinstance(route, APIRoute)
            and route.path == path
            and method.upper() in route.methods
        ):
            return route
    msg = f"Missing source route for v2 alias: {method.upper()} {path}"
    raise RuntimeError(msg)


def _add_alias(
    *,
    source_router: APIRouter,
    source_path: str,
    target_path: str,
    method: str,
    summary: str,
    tags: Sequence[str],
) -> None:
    source = _find_route(source_router, path=source_path, method=method)
    router.add_api_route(
        target_path,
        source.endpoint,
        response_model=source.response_model,
        status_code=source.status_code,
        tags=list(tags),
        dependencies=source.dependencies,
        summary=summary,
        description=source.description,
        response_description=source.response_description,
        responses=source.responses,
        deprecated=source.deprecated,
        methods=[method.upper()],
        response_model_include=source.response_model_include,
        response_model_exclude=source.response_model_exclude,
        response_model_by_alias=source.response_model_by_alias,
        response_model_exclude_unset=source.response_model_exclude_unset,
        response_model_exclude_defaults=source.response_model_exclude_defaults,
        response_model_exclude_none=source.response_model_exclude_none,
        include_in_schema=source.include_in_schema,
        response_class=source.response_class,
        name=f"v2_{source.name}",
        callbacks=source.callbacks,
        openapi_extra=source.openapi_extra,
    )


_ALIASES = (
    # Account and space setup.
    (
        authentication.router,
        "POST",
        "/v1/auth/bootstrap",
        "/v2/auth/bootstrap",
        "Bootstrap self-hosted access",
        ("auth",),
    ),
    (
        authentication.router,
        "POST",
        "/v1/auth/testers",
        "/v2/auth/testers",
        "Create tester access",
        ("auth",),
    ),
    (
        authentication.router,
        "GET",
        "/v1/auth/me",
        "/v2/auth/me",
        "Get current identity",
        ("auth",),
    ),
    (
        authentication.router,
        "POST",
        "/v1/auth/api-keys",
        "/v2/auth/api-keys",
        "Create API key",
        ("auth",),
    ),
    (
        authentication.router,
        "GET",
        "/v1/auth/api-keys",
        "/v2/auth/api-keys",
        "List API keys",
        ("auth",),
    ),
    (
        authentication.router,
        "DELETE",
        "/v1/auth/api-keys/{key_id}",
        "/v2/auth/api-keys/{key_id}",
        "Revoke API key",
        ("auth",),
    ),
    (
        authentication.router,
        "POST",
        "/v1/auth/api-keys/{key_id}/rotate",
        "/v2/auth/api-keys/{key_id}/rotate",
        "Rotate API key",
        ("auth",),
    ),
    (
        spaces.router,
        "GET",
        "/v1/spaces",
        "/v2/spaces",
        "List research spaces",
        ("spaces",),
    ),
    (
        spaces.router,
        "POST",
        "/v1/spaces",
        "/v2/spaces",
        "Create research space",
        ("spaces",),
    ),
    (
        spaces.router,
        "PATCH",
        "/v1/spaces/{space_id}/settings",
        "/v2/spaces/{space_id}/settings",
        "Update research-space settings",
        ("spaces",),
    ),
    (
        spaces.router,
        "PUT",
        "/v1/spaces/default",
        "/v2/spaces/default",
        "Get or create default research space",
        ("spaces",),
    ),
    (
        spaces.router,
        "DELETE",
        "/v1/spaces/{space_id}",
        "/v2/spaces/{space_id}",
        "Archive research space",
        ("spaces",),
    ),
    (
        spaces.router,
        "GET",
        "/v1/spaces/{space_id}/members",
        "/v2/spaces/{space_id}/members",
        "List research-space members",
        ("spaces",),
    ),
    (
        spaces.router,
        "POST",
        "/v1/spaces/{space_id}/members",
        "/v2/spaces/{space_id}/members",
        "Add research-space member",
        ("spaces",),
    ),
    (
        spaces.router,
        "DELETE",
        "/v1/spaces/{space_id}/members/{user_id}",
        "/v2/spaces/{space_id}/members/{user_id}",
        "Remove research-space member",
        ("spaces",),
    ),
    # Evidence input and source discovery.
    (
        documents.router,
        "GET",
        "/v1/spaces/{space_id}/documents",
        "/v2/spaces/{space_id}/documents",
        "List documents",
        ("documents",),
    ),
    (
        documents.router,
        "GET",
        "/v1/spaces/{space_id}/documents/{document_id}",
        "/v2/spaces/{space_id}/documents/{document_id}",
        "Get document",
        ("documents",),
    ),
    (
        documents.router,
        "POST",
        "/v1/spaces/{space_id}/documents/text",
        "/v2/spaces/{space_id}/documents/text",
        "Add text document",
        ("documents",),
    ),
    (
        documents.router,
        "POST",
        "/v1/spaces/{space_id}/documents/pdf",
        "/v2/spaces/{space_id}/documents/pdf",
        "Upload PDF document",
        ("documents",),
    ),
    (
        documents.router,
        "POST",
        "/v1/spaces/{space_id}/documents/{document_id}/extract",
        "/v2/spaces/{space_id}/documents/{document_id}/extraction",
        "Extract evidence from document",
        ("documents",),
    ),
    (
        marrvel.router,
        "POST",
        "/v1/spaces/{space_id}/marrvel/ingest",
        "/v2/spaces/{space_id}/sources/marrvel/ingestion",
        "Ingest MARRVEL evidence",
        ("sources",),
    ),
    # Product workflow surfaces.
    (
        research_state.router,
        "GET",
        "/v1/spaces/{space_id}/research-state",
        "/v2/spaces/{space_id}/research-state",
        "Get research state",
        ("research",),
    ),
    (
        review_queue.router,
        "GET",
        "/v1/spaces/{space_id}/review-queue",
        "/v2/spaces/{space_id}/review-items",
        "List items needing review",
        ("review",),
    ),
    (
        review_queue.router,
        "GET",
        "/v1/spaces/{space_id}/review-queue/{item_id}",
        "/v2/spaces/{space_id}/review-items/{item_id}",
        "Get review item",
        ("review",),
    ),
    (
        review_queue.router,
        "POST",
        "/v1/spaces/{space_id}/review-queue/{item_id}/actions",
        "/v2/spaces/{space_id}/review-items/{item_id}/decision",
        "Decide review item",
        ("review",),
    ),
    (
        proposals.router,
        "GET",
        "/v1/spaces/{space_id}/proposals",
        "/v2/spaces/{space_id}/proposed-updates",
        "List proposed updates",
        ("review",),
    ),
    (
        proposals.router,
        "GET",
        "/v1/spaces/{space_id}/proposals/{proposal_id}",
        "/v2/spaces/{space_id}/proposed-updates/{proposal_id}",
        "Get proposed update",
        ("review",),
    ),
    (
        proposals.router,
        "POST",
        "/v1/spaces/{space_id}/proposals/{proposal_id}/promote",
        "/v2/spaces/{space_id}/proposed-updates/{proposal_id}/promote",
        "Promote proposed update",
        ("review",),
    ),
    (
        proposals.router,
        "POST",
        "/v1/spaces/{space_id}/proposals/{proposal_id}/reject",
        "/v2/spaces/{space_id}/proposed-updates/{proposal_id}/reject",
        "Reject proposed update",
        ("review",),
    ),
    # Generic task lifecycle.
    (
        graph_explorer.router,
        "GET",
        "/v1/spaces/{space_id}/graph-explorer/claims",
        "/v2/spaces/{space_id}/evidence-map/claims",
        "List evidence-map claims",
        ("evidence-map",),
    ),
    (
        graph_explorer.router,
        "GET",
        "/v1/spaces/{space_id}/graph-explorer/entities",
        "/v2/spaces/{space_id}/evidence-map/entities",
        "List evidence-map entities",
        ("evidence-map",),
    ),
    (
        graph_explorer.router,
        "GET",
        "/v1/spaces/{space_id}/graph-explorer/entities/{entity_id}/claims",
        "/v2/spaces/{space_id}/evidence-map/entities/{entity_id}/claims",
        "List claims for entity",
        ("evidence-map",),
    ),
    (
        graph_explorer.router,
        "GET",
        "/v1/spaces/{space_id}/graph-explorer/claims/{claim_id}/evidence",
        "/v2/spaces/{space_id}/evidence-map/claims/{claim_id}/evidence",
        "List claim evidence",
        ("evidence-map",),
    ),
    (
        graph_explorer.router,
        "POST",
        "/v1/spaces/{space_id}/graph-explorer/document",
        "/v2/spaces/{space_id}/evidence-map/export",
        "Export evidence map",
        ("evidence-map",),
    ),
    (
        chat.router,
        "GET",
        "/v1/spaces/{space_id}/chat-sessions",
        "/v2/spaces/{space_id}/chat-sessions",
        "List chat sessions",
        ("chat",),
    ),
    (
        chat.router,
        "POST",
        "/v1/spaces/{space_id}/chat-sessions",
        "/v2/spaces/{space_id}/chat-sessions",
        "Create chat session",
        ("chat",),
    ),
    (
        chat.router,
        "GET",
        "/v1/spaces/{space_id}/chat-sessions/{session_id}",
        "/v2/spaces/{space_id}/chat-sessions/{session_id}",
        "Get chat session",
        ("chat",),
    ),
    (
        chat.router,
        "POST",
        "/v1/spaces/{space_id}/chat-sessions/{session_id}/messages",
        "/v2/spaces/{space_id}/chat-sessions/{session_id}/messages",
        "Send chat message",
        ("chat",),
    ),
    (
        chat.router,
        "POST",
        "/v1/spaces/{space_id}/chat-sessions/{session_id}/proposals/graph-write",
        "/v2/spaces/{space_id}/chat-sessions/{session_id}/suggested-updates",
        "Stage suggested updates from chat",
        ("chat",),
    ),
    (
        chat.router,
        "POST",
        "/v1/spaces/{space_id}/chat-sessions/{session_id}/graph-write-candidates/{candidate_index}/review",
        "/v2/spaces/{space_id}/chat-sessions/{session_id}/suggested-updates/{candidate_index}/decision",
        "Decide suggested chat update",
        ("chat",),
    ),
    # Workflow-specific task creation.
    (
        graph_search_runs.router,
        "POST",
        "/v1/spaces/{space_id}/agents/graph-search/runs",
        "/v2/spaces/{space_id}/workflows/evidence-search/tasks",
        "Start evidence search task",
        ("workflows",),
    ),
    (
        graph_connection_runs.router,
        "POST",
        "/v1/spaces/{space_id}/agents/graph-connections/runs",
        "/v2/spaces/{space_id}/workflows/connection-discovery/tasks",
        "Start connection discovery task",
        ("workflows",),
    ),
    (
        hypothesis_runs.router,
        "POST",
        "/v1/spaces/{space_id}/agents/hypotheses/runs",
        "/v2/spaces/{space_id}/workflows/hypothesis-discovery/tasks",
        "Start hypothesis discovery task",
        ("workflows",),
    ),
    (
        mechanism_discovery_runs.router,
        "POST",
        "/v1/spaces/{space_id}/agents/mechanism-discovery/runs",
        "/v2/spaces/{space_id}/workflows/mechanism-discovery/tasks",
        "Start mechanism discovery task",
        ("workflows",),
    ),
    (
        continuous_learning_runs.router,
        "POST",
        "/v1/spaces/{space_id}/agents/continuous-learning/runs",
        "/v2/spaces/{space_id}/workflows/continuous-review/tasks",
        "Start continuous review task",
        ("workflows",),
    ),
    (
        full_ai_orchestrator_runs.router,
        "POST",
        "/v1/spaces/{space_id}/agents/full-ai-orchestrator/runs",
        "/v2/spaces/{space_id}/workflows/autopilot/tasks",
        "Start autopilot task",
        ("workflows",),
    ),
    (
        research_onboarding_runs.router,
        "POST",
        "/v1/spaces/{space_id}/agents/research-onboarding/runs",
        "/v2/spaces/{space_id}/workflows/research-onboarding/tasks",
        "Start research onboarding task",
        ("workflows",),
    ),
    (
        research_onboarding_runs.router,
        "POST",
        "/v1/spaces/{space_id}/agents/research-onboarding/turns",
        "/v2/spaces/{space_id}/workflows/research-onboarding/turns",
        "Continue research onboarding",
        ("workflows",),
    ),
    (
        supervisor_runs.router,
        "GET",
        "/v1/spaces/{space_id}/agents/supervisor/dashboard",
        "/v2/spaces/{space_id}/workflows/full-research/dashboard",
        "Get full research dashboard",
        ("workflows",),
    ),
    (
        supervisor_runs.router,
        "GET",
        "/v1/spaces/{space_id}/agents/supervisor/runs",
        "/v2/spaces/{space_id}/workflows/full-research/tasks",
        "List full research tasks",
        ("workflows",),
    ),
    # Automation and templates.
    (
        schedules.router,
        "GET",
        "/v1/spaces/{space_id}/schedules",
        "/v2/spaces/{space_id}/schedules",
        "List schedules",
        ("schedules",),
    ),
    (
        schedules.router,
        "POST",
        "/v1/spaces/{space_id}/schedules",
        "/v2/spaces/{space_id}/schedules",
        "Create schedule",
        ("schedules",),
    ),
    (
        schedules.router,
        "GET",
        "/v1/spaces/{space_id}/schedules/{schedule_id}",
        "/v2/spaces/{space_id}/schedules/{schedule_id}",
        "Get schedule",
        ("schedules",),
    ),
    (
        schedules.router,
        "PATCH",
        "/v1/spaces/{space_id}/schedules/{schedule_id}",
        "/v2/spaces/{space_id}/schedules/{schedule_id}",
        "Update schedule",
        ("schedules",),
    ),
    (
        schedules.router,
        "POST",
        "/v1/spaces/{space_id}/schedules/{schedule_id}/pause",
        "/v2/spaces/{space_id}/schedules/{schedule_id}/pause",
        "Pause schedule",
        ("schedules",),
    ),
    (
        schedules.router,
        "POST",
        "/v1/spaces/{space_id}/schedules/{schedule_id}/resume",
        "/v2/spaces/{space_id}/schedules/{schedule_id}/resume",
        "Resume schedule",
        ("schedules",),
    ),
    (
        schedules.router,
        "POST",
        "/v1/spaces/{space_id}/schedules/{schedule_id}/run-now",
        "/v2/spaces/{space_id}/schedules/{schedule_id}/start-now",
        "Start scheduled task now",
        ("schedules",),
    ),
)

for (
    _source_router,
    _method,
    _source_path,
    _target_path,
    _summary,
    _tags,
) in _ALIASES:
    _add_alias(
        source_router=_source_router,
        source_path=_source_path,
        target_path=_target_path,
        method=_method,
        summary=_summary,
        tags=_tags,
    )


@router.get(
    "/v2/sources",
    response_model=SourceListResponse,
    summary="List evidence sources",
    dependencies=[Depends(require_harness_read_access)],
    tags=["sources"],
)
def list_sources() -> SourceListResponse:
    """Return public evidence source capabilities."""

    sources = list(list_source_definitions())
    return SourceListResponse(sources=sources, total=len(sources))


@router.get(
    "/v2/sources/{source_key}",
    response_model=SourceDefinition,
    summary="Get evidence source",
    dependencies=[Depends(require_harness_read_access)],
    tags=["sources"],
    responses=_SOURCE_NOT_FOUND_RESPONSE,
)
def get_source(source_key: str) -> SourceDefinition:
    """Return one public evidence source capability definition."""

    return _require_source(source_key)


@router.post(
    "/v2/spaces/{space_id}/sources/pubmed/searches",
    response_model=PubMedSourceSearchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Search PubMed evidence source",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["sources"],
)
async def create_pubmed_source_search(
    space_id: UUID,
    request: pubmed.PubMedSearchRequest,
    *,
    current_user: HarnessUser = Depends(get_current_harness_user),
    pubmed_discovery_service: pubmed.PubMedDiscoveryService = (
        _PUBMED_DISCOVERY_SERVICE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 compatibility route for PubMed source search."""

    return await _create_pubmed_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=current_user,
        pubmed_discovery_service=pubmed_discovery_service,
    )


@router.get(
    "/v2/spaces/{space_id}/sources/pubmed/searches/{job_id}",
    response_model=PubMedSourceSearchResponse,
    summary="Get PubMed evidence source search",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["sources"],
)
def get_pubmed_source_search(
    space_id: UUID,
    job_id: UUID,
    *,
    current_user: HarnessUser = Depends(get_current_harness_user),
    pubmed_discovery_service: pubmed.PubMedDiscoveryService = (
        _PUBMED_DISCOVERY_SERVICE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 compatibility route for PubMed source-search lookup."""

    return _get_pubmed_source_search_payload(
        space_id=space_id,
        search_id=job_id,
        current_user=current_user,
        pubmed_discovery_service=pubmed_discovery_service,
    )


@router.post(
    "/v2/spaces/{space_id}/sources/marrvel/searches",
    response_model=MarrvelSourceSearchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Search MARRVEL evidence source",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["sources"],
)
async def create_marrvel_source_search(
    space_id: UUID,
    request: marrvel.MarrvelSearchRequest,
    *,
    current_user: HarnessUser = Depends(get_current_harness_user),
    marrvel_discovery_service: marrvel.MarrvelDiscoveryService = (
        _MARRVEL_DISCOVERY_SERVICE_DEPENDENCY
    ),
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 compatibility route for MARRVEL source search."""

    return await _create_marrvel_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=current_user,
        marrvel_discovery_service=marrvel_discovery_service,
        direct_source_search_store=direct_source_search_store,
    )


@router.get(
    "/v2/spaces/{space_id}/sources/marrvel/searches/{result_id}",
    response_model=MarrvelSourceSearchResponse,
    summary="Get MARRVEL evidence source search",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["sources"],
)
def get_marrvel_source_search(
    space_id: UUID,
    result_id: UUID,
    *,
    current_user: HarnessUser = Depends(get_current_harness_user),
    marrvel_discovery_service: marrvel.MarrvelDiscoveryService = (
        _MARRVEL_DISCOVERY_SERVICE_DEPENDENCY
    ),
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 compatibility route for MARRVEL source-search lookup."""

    return _get_marrvel_source_search_payload(
        space_id=space_id,
        search_id=result_id,
        current_user=current_user,
        marrvel_discovery_service=marrvel_discovery_service,
        direct_source_search_store=direct_source_search_store,
    )


@router.post(
    "/v2/spaces/{space_id}/sources/clinvar/searches",
    response_model=ClinVarSourceSearchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Search ClinVar evidence source",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["sources"],
)
async def create_clinvar_source_search(
    space_id: UUID,
    request: ClinVarSourceSearchRequest,
    *,
    current_user: HarnessUser = Depends(get_current_harness_user),
    clinvar_gateway: ClinVarGatewayProtocol | None = (
        _CLINVAR_SOURCE_GATEWAY_DEPENDENCY
    ),
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for ClinVar source search."""

    return await _create_clinvar_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=current_user,
        clinvar_gateway=clinvar_gateway,
        direct_source_search_store=direct_source_search_store,
    )


@router.get(
    "/v2/spaces/{space_id}/sources/clinvar/searches/{search_id}",
    response_model=ClinVarSourceSearchResponse,
    summary="Get ClinVar evidence source search",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["sources"],
)
def get_clinvar_source_search(
    space_id: UUID,
    search_id: UUID,
    *,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for ClinVar source-search lookup."""

    return _get_clinvar_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


@router.post(
    "/v2/spaces/{space_id}/sources/clinical_trials/searches",
    response_model=ClinicalTrialsSourceSearchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Search ClinicalTrials.gov evidence source",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["sources"],
)
async def create_clinicaltrials_source_search(
    space_id: UUID,
    request: ClinicalTrialsSourceSearchRequest,
    *,
    current_user: HarnessUser = Depends(get_current_harness_user),
    clinicaltrials_gateway: ClinicalTrialsGatewayProtocol | None = (
        _CLINICALTRIALS_SOURCE_GATEWAY_DEPENDENCY
    ),
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for ClinicalTrials.gov source search."""

    return await _create_clinicaltrials_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=current_user,
        clinicaltrials_gateway=clinicaltrials_gateway,
        direct_source_search_store=direct_source_search_store,
    )


@router.get(
    "/v2/spaces/{space_id}/sources/clinical_trials/searches/{search_id}",
    response_model=ClinicalTrialsSourceSearchResponse,
    summary="Get ClinicalTrials.gov evidence source search",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["sources"],
)
def get_clinicaltrials_source_search(
    space_id: UUID,
    search_id: UUID,
    *,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for ClinicalTrials.gov source-search lookup."""

    return _get_clinicaltrials_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


@router.post(
    "/v2/spaces/{space_id}/sources/uniprot/searches",
    response_model=UniProtSourceSearchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Search UniProt evidence source",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["sources"],
)
async def create_uniprot_source_search(
    space_id: UUID,
    request: UniProtSourceSearchRequest,
    *,
    current_user: HarnessUser = Depends(get_current_harness_user),
    uniprot_gateway: UniProtGatewayProtocol | None = (
        _UNIPROT_SOURCE_GATEWAY_DEPENDENCY
    ),
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for UniProt source search."""

    return await _create_uniprot_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=current_user,
        uniprot_gateway=uniprot_gateway,
        direct_source_search_store=direct_source_search_store,
    )


@router.get(
    "/v2/spaces/{space_id}/sources/uniprot/searches/{search_id}",
    response_model=UniProtSourceSearchResponse,
    summary="Get UniProt evidence source search",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["sources"],
)
def get_uniprot_source_search(
    space_id: UUID,
    search_id: UUID,
    *,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for UniProt source-search lookup."""

    return _get_uniprot_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


@router.post(
    "/v2/spaces/{space_id}/sources/alphafold/searches",
    response_model=AlphaFoldSourceSearchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Search AlphaFold evidence source",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["sources"],
)
async def create_alphafold_source_search(
    space_id: UUID,
    request: AlphaFoldSourceSearchRequest,
    *,
    current_user: HarnessUser = Depends(get_current_harness_user),
    alphafold_gateway: AlphaFoldGatewayProtocol | None = (
        _ALPHAFOLD_SOURCE_GATEWAY_DEPENDENCY
    ),
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for AlphaFold source search."""

    return await _create_alphafold_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=current_user,
        alphafold_gateway=alphafold_gateway,
        direct_source_search_store=direct_source_search_store,
    )


@router.get(
    "/v2/spaces/{space_id}/sources/alphafold/searches/{search_id}",
    response_model=AlphaFoldSourceSearchResponse,
    summary="Get AlphaFold evidence source search",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["sources"],
)
def get_alphafold_source_search(
    space_id: UUID,
    search_id: UUID,
    *,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for AlphaFold source-search lookup."""

    return _get_alphafold_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


@router.post(
    "/v2/spaces/{space_id}/sources/drugbank/searches",
    response_model=DrugBankSourceSearchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Search DrugBank evidence source",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["sources"],
)
async def create_drugbank_source_search(
    space_id: UUID,
    request: DrugBankSourceSearchRequest,
    *,
    current_user: HarnessUser = Depends(get_current_harness_user),
    drugbank_gateway: DrugBankGatewayProtocol | None = (
        _DRUGBANK_SOURCE_GATEWAY_DEPENDENCY
    ),
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for DrugBank source search."""

    return await _create_drugbank_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=current_user,
        drugbank_gateway=drugbank_gateway,
        direct_source_search_store=direct_source_search_store,
    )


@router.get(
    "/v2/spaces/{space_id}/sources/drugbank/searches/{search_id}",
    response_model=DrugBankSourceSearchResponse,
    summary="Get DrugBank evidence source search",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["sources"],
)
def get_drugbank_source_search(
    space_id: UUID,
    search_id: UUID,
    *,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for DrugBank source-search lookup."""

    return _get_drugbank_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


@router.post(
    "/v2/spaces/{space_id}/sources/mgi/searches",
    response_model=MGISourceSearchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Search MGI evidence source",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["sources"],
)
async def create_mgi_source_search(
    space_id: UUID,
    request: MGISourceSearchRequest,
    *,
    current_user: HarnessUser = Depends(get_current_harness_user),
    mgi_gateway: AllianceGeneGatewayProtocol | None = _MGI_SOURCE_GATEWAY_DEPENDENCY,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for MGI source search."""

    return await _create_mgi_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=current_user,
        mgi_gateway=mgi_gateway,
        direct_source_search_store=direct_source_search_store,
    )


@router.get(
    "/v2/spaces/{space_id}/sources/mgi/searches/{search_id}",
    response_model=MGISourceSearchResponse,
    summary="Get MGI evidence source search",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["sources"],
)
def get_mgi_source_search(
    space_id: UUID,
    search_id: UUID,
    *,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for MGI source-search lookup."""

    return _get_mgi_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


@router.post(
    "/v2/spaces/{space_id}/sources/zfin/searches",
    response_model=ZFINSourceSearchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Search ZFIN evidence source",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["sources"],
)
async def create_zfin_source_search(
    space_id: UUID,
    request: ZFINSourceSearchRequest,
    *,
    current_user: HarnessUser = Depends(get_current_harness_user),
    zfin_gateway: AllianceGeneGatewayProtocol | None = _ZFIN_SOURCE_GATEWAY_DEPENDENCY,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for ZFIN source search."""

    return await _create_zfin_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=current_user,
        zfin_gateway=zfin_gateway,
        direct_source_search_store=direct_source_search_store,
    )


@router.get(
    "/v2/spaces/{space_id}/sources/zfin/searches/{search_id}",
    response_model=ZFINSourceSearchResponse,
    summary="Get ZFIN evidence source search",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["sources"],
)
def get_zfin_source_search(
    space_id: UUID,
    search_id: UUID,
    *,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for ZFIN source-search lookup."""

    return _get_zfin_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


@router.post(
    "/v2/spaces/{space_id}/sources/{source_key}/searches",
    response_model=SourceSearchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Search evidence source",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["sources"],
    responses=_DIRECT_SOURCE_SEARCH_RESPONSES,
)
async def create_source_search(  # noqa: PLR0911
    space_id: UUID,
    source_key: str,
    request_payload: JSONObject = Body(...),
    *,
    current_user: HarnessUser = Depends(get_current_harness_user),
    pubmed_discovery_service: pubmed.PubMedDiscoveryService = (
        _PUBMED_DISCOVERY_SERVICE_DEPENDENCY
    ),
    marrvel_discovery_service: marrvel.MarrvelDiscoveryService = (
        _MARRVEL_DISCOVERY_SERVICE_DEPENDENCY
    ),
    clinvar_gateway: ClinVarGatewayProtocol | None = (
        _CLINVAR_SOURCE_GATEWAY_DEPENDENCY
    ),
    clinicaltrials_gateway: ClinicalTrialsGatewayProtocol | None = (
        _CLINICALTRIALS_SOURCE_GATEWAY_DEPENDENCY
    ),
    uniprot_gateway: UniProtGatewayProtocol | None = (
        _UNIPROT_SOURCE_GATEWAY_DEPENDENCY
    ),
    alphafold_gateway: AlphaFoldGatewayProtocol | None = (
        _ALPHAFOLD_SOURCE_GATEWAY_DEPENDENCY
    ),
    drugbank_gateway: DrugBankGatewayProtocol | None = (
        _DRUGBANK_SOURCE_GATEWAY_DEPENDENCY
    ),
    mgi_gateway: AllianceGeneGatewayProtocol | None = _MGI_SOURCE_GATEWAY_DEPENDENCY,
    zfin_gateway: AllianceGeneGatewayProtocol | None = _ZFIN_SOURCE_GATEWAY_DEPENDENCY,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Run a direct source search through the source registry."""

    source = _require_direct_search_source(source_key)
    if source.source_key == "pubmed":
        return await _create_pubmed_source_search_payload(
            space_id=space_id,
            request=_parse_pubmed_source_search(request_payload),
            current_user=current_user,
            pubmed_discovery_service=pubmed_discovery_service,
        )
    if source.source_key == "marrvel":
        return await _create_marrvel_source_search_payload(
            space_id=space_id,
            request=_parse_marrvel_source_search(request_payload),
            current_user=current_user,
            marrvel_discovery_service=marrvel_discovery_service,
            direct_source_search_store=direct_source_search_store,
        )
    if source.source_key == "clinvar":
        return await _create_clinvar_source_search_payload(
            space_id=space_id,
            request=_parse_clinvar_source_search(request_payload),
            current_user=current_user,
            clinvar_gateway=clinvar_gateway,
            direct_source_search_store=direct_source_search_store,
        )
    if source.source_key == "clinical_trials":
        return await _create_clinicaltrials_source_search_payload(
            space_id=space_id,
            request=_parse_clinicaltrials_source_search(request_payload),
            current_user=current_user,
            clinicaltrials_gateway=clinicaltrials_gateway,
            direct_source_search_store=direct_source_search_store,
        )
    if source.source_key == "uniprot":
        return await _create_uniprot_source_search_payload(
            space_id=space_id,
            request=_parse_uniprot_source_search(request_payload),
            current_user=current_user,
            uniprot_gateway=uniprot_gateway,
            direct_source_search_store=direct_source_search_store,
        )
    if source.source_key == "alphafold":
        return await _create_alphafold_source_search_payload(
            space_id=space_id,
            request=_parse_alphafold_source_search(request_payload),
            current_user=current_user,
            alphafold_gateway=alphafold_gateway,
            direct_source_search_store=direct_source_search_store,
        )
    if source.source_key == "drugbank":
        return await _create_drugbank_source_search_payload(
            space_id=space_id,
            request=_parse_drugbank_source_search(request_payload),
            current_user=current_user,
            drugbank_gateway=drugbank_gateway,
            direct_source_search_store=direct_source_search_store,
        )
    if source.source_key == "mgi":
        return await _create_mgi_source_search_payload(
            space_id=space_id,
            request=_parse_mgi_source_search(request_payload),
            current_user=current_user,
            mgi_gateway=mgi_gateway,
            direct_source_search_store=direct_source_search_store,
        )
    if source.source_key == "zfin":
        return await _create_zfin_source_search_payload(
            space_id=space_id,
            request=_parse_zfin_source_search(request_payload),
            current_user=current_user,
            zfin_gateway=zfin_gateway,
            direct_source_search_store=direct_source_search_store,
        )
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Source '{source.source_key}' does not support direct search.",
    )


@router.get(
    "/v2/spaces/{space_id}/sources/{source_key}/searches/{search_id}",
    response_model=SourceSearchResponse,
    summary="Get evidence source search",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["sources"],
    responses=_DIRECT_SOURCE_SEARCH_RESPONSES,
)
def get_source_search(  # noqa: PLR0911
    space_id: UUID,
    source_key: str,
    search_id: UUID,
    *,
    current_user: HarnessUser = Depends(get_current_harness_user),
    pubmed_discovery_service: pubmed.PubMedDiscoveryService = (
        _PUBMED_DISCOVERY_SERVICE_DEPENDENCY
    ),
    marrvel_discovery_service: marrvel.MarrvelDiscoveryService = (
        _MARRVEL_DISCOVERY_SERVICE_DEPENDENCY
    ),
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Return one direct source search result through the source registry."""

    source = _require_direct_search_source(source_key)
    if source.source_key == "pubmed":
        return _get_pubmed_source_search_payload(
            space_id=space_id,
            search_id=search_id,
            current_user=current_user,
            pubmed_discovery_service=pubmed_discovery_service,
        )
    if source.source_key == "marrvel":
        return _get_marrvel_source_search_payload(
            space_id=space_id,
            search_id=search_id,
            current_user=current_user,
            marrvel_discovery_service=marrvel_discovery_service,
            direct_source_search_store=direct_source_search_store,
        )
    if source.source_key == "clinvar":
        return _get_clinvar_source_search_payload(
            space_id=space_id,
            search_id=search_id,
            direct_source_search_store=direct_source_search_store,
        )
    if source.source_key == "clinical_trials":
        return _get_clinicaltrials_source_search_payload(
            space_id=space_id,
            search_id=search_id,
            direct_source_search_store=direct_source_search_store,
        )
    if source.source_key == "uniprot":
        return _get_uniprot_source_search_payload(
            space_id=space_id,
            search_id=search_id,
            direct_source_search_store=direct_source_search_store,
        )
    if source.source_key == "alphafold":
        return _get_alphafold_source_search_payload(
            space_id=space_id,
            search_id=search_id,
            direct_source_search_store=direct_source_search_store,
        )
    if source.source_key == "drugbank":
        return _get_drugbank_source_search_payload(
            space_id=space_id,
            search_id=search_id,
            direct_source_search_store=direct_source_search_store,
        )
    if source.source_key == "mgi":
        return _get_mgi_source_search_payload(
            space_id=space_id,
            search_id=search_id,
            direct_source_search_store=direct_source_search_store,
        )
    if source.source_key == "zfin":
        return _get_zfin_source_search_payload(
            space_id=space_id,
            search_id=search_id,
            direct_source_search_store=direct_source_search_store,
        )
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Source '{source.source_key}' does not support direct search.",
    )


@router.post(
    "/v2/spaces/{space_id}/sources/{source_key}/searches/{search_id}/handoffs",
    response_model=SourceSearchHandoffResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Hand off a captured source search",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["sources"],
    responses={
        **_DIRECT_SOURCE_SEARCH_RESPONSES,
        status.HTTP_409_CONFLICT: {
            "description": "Idempotency key was reused with different input.",
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "The request did not select exactly one source record.",
        },
    },
)
async def create_source_search_handoff(
    space_id: UUID,
    source_key: str,
    search_id: UUID,
    request: SourceSearchHandoffRequest,
    *,
    current_user: HarnessUser = Depends(get_current_harness_user),
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
    source_search_handoff_store: SourceSearchHandoffStore = (
        _SOURCE_SEARCH_HANDOFF_STORE_DEPENDENCY
    ),
    document_store: HarnessDocumentStore = _DOCUMENT_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
    review_item_store: HarnessReviewItemStore = _REVIEW_ITEM_STORE_DEPENDENCY,
    binary_store: HarnessDocumentBinaryStore = _DOCUMENT_BINARY_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = Depends(get_graph_api_gateway),
    research_state_store: HarnessResearchStateStore = _RESEARCH_STATE_STORE_DEPENDENCY,
) -> SourceSearchHandoffResponse:
    """Create an idempotent handoff from a saved source-search result."""

    source = _require_direct_search_source(source_key)
    service = SourceSearchHandoffService(
        search_store=direct_source_search_store,
        handoff_store=source_search_handoff_store,
        document_store=document_store,
        run_registry=run_registry,
    )
    try:
        response = service.create_handoff(
            space_id=space_id,
            source_key=source.source_key,
            search_id=search_id,
            created_by=current_user.id,
            request=request,
        )
    except SourceSearchHandoffNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SourceSearchHandoffUnsupportedError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc),
        ) from exc
    except SourceSearchHandoffConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SourceSearchHandoffSelectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    target_document = (
        document_store.get_document(
            space_id=space_id,
            document_id=response.target_document_id,
        )
        if response.target_document_id is not None
        else None
    )
    if (
        request.extract_now
        and response.target_document_id is not None
        and target_document is not None
        and target_document.extraction_status != "completed"
    ):
        extraction = await documents.extract_document(
            space_id=space_id,
            document_id=response.target_document_id,
            use_llm=False,
            document_store=document_store,
            proposal_store=proposal_store,
            review_item_store=review_item_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            binary_store=binary_store,
            graph_api_gateway=graph_api_gateway,
            research_state_store=research_state_store,
        )
        response = response.model_copy(
            update={"extraction": json_object_or_empty(jsonable_encoder(extraction))},
        )
    return response


@router.get(
    "/v2/workflow-templates",
    response_model=WorkflowTemplateListResponse,
    summary="List workflow templates",
    dependencies=[Depends(require_harness_read_access)],
    tags=["workflows"],
)
def list_workflow_templates() -> WorkflowTemplateListResponse:
    """Return the public workflow template catalog."""
    response = harnesses.list_harnesses()
    return WorkflowTemplateListResponse(
        workflow_templates=[
            WorkflowTemplateResponse.from_v1(template)
            for template in response.harnesses
        ],
        total=response.total,
    )


@router.post(
    "/v2/spaces/{space_id}/research-plan",
    response_model=ResearchPlanResponse,
    status_code=201,
    summary="Create research plan",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["research"],
)
async def create_research_plan(
    space_id: UUID,
    request: research_init.ResearchInitRequest,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = Depends(get_graph_api_gateway),
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
    current_user: HarnessUser = Depends(get_current_harness_user),
    identity_gateway: IdentityGateway = Depends(get_identity_gateway),
) -> ResearchPlanResponse:
    """Queue research planning work using public task language."""
    response = await research_init.create_research_init(
        space_id=space_id,
        request=request,
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=graph_api_gateway,
        execution_services=execution_services,
        current_user=current_user,
        identity_gateway=identity_gateway,
    )
    return ResearchPlanResponse.from_v1(response)


@router.post(
    "/v2/spaces/{space_id}/tasks",
    response_model=TaskResponse,
    status_code=201,
    summary="Start task",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["tasks"],
)
def create_task(
    space_id: UUID,
    request: TaskCreateRequest,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = Depends(get_graph_api_gateway),
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> TaskResponse:
    """Create one public task from a workflow template."""
    response = runs.create_run(
        space_id=space_id,
        request=request.to_v1(),
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=graph_api_gateway,
        execution_services=execution_services,
    )
    return TaskResponse.from_v1(response)


@router.post(
    "/v2/spaces/{space_id}/workflows/topic-setup/tasks",
    response_model=JSONObject,
    responses={202: {"model": AcceptedTaskResponse}},
    summary="Start topic setup task",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["workflows"],
)
async def create_topic_setup_task(
    space_id: UUID,
    request: research_bootstrap_runs.ResearchBootstrapRunRequest,
    *,
    prefer: str | None = Header(default=None),
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = Depends(get_graph_api_gateway),
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> JSONObject | JSONResponse:
    """Start one topic-setup task with public payload naming."""
    result = await research_bootstrap_runs.create_research_bootstrap_run(
        space_id=space_id,
        request=request,
        prefer=prefer,
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=graph_api_gateway,
        execution_services=execution_services,
    )
    if isinstance(result, JSONResponse):
        return _publicized_json_response(result)
    payload = _publicize_json_object(result.model_dump(mode="json"))
    return payload or {}


@router.post(
    "/v2/spaces/{space_id}/workflows/evidence-curation/tasks",
    response_model=JSONObject,
    responses={202: {"model": AcceptedTaskResponse}},
    summary="Start evidence curation task",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["workflows"],
)
async def create_evidence_curation_task(
    space_id: UUID,
    request: graph_curation_runs.ClaimCurationRunRequest,
    *,
    prefer: str | None = Header(default=None),
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    proposal_store: HarnessProposalStore = Depends(get_proposal_store),
    graph_api_gateway: GraphTransportBundle = Depends(get_graph_api_gateway),
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> JSONObject | JSONResponse:
    """Start one evidence-curation task with public payload naming."""
    result = await graph_curation_runs.create_claim_curation_run(
        space_id=space_id,
        request=request,
        prefer=prefer,
        run_registry=run_registry,
        artifact_store=artifact_store,
        proposal_store=proposal_store,
        graph_api_gateway=graph_api_gateway,
        execution_services=execution_services,
    )
    if isinstance(result, JSONResponse):
        return _publicized_json_response(result)
    payload = _publicize_json_object(result.model_dump(mode="json"))
    return payload or {}


@router.post(
    "/v2/spaces/{space_id}/workflows/full-research/tasks",
    response_model=JSONObject,
    responses={202: {"model": AcceptedTaskResponse}},
    summary="Start full research task",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["workflows"],
)
async def create_full_research_task(
    space_id: UUID,
    request: supervisor_runs.SupervisorRunRequest,
    *,
    prefer: str | None = Header(default=None),
    current_user: HarnessUser = Depends(get_current_harness_user),
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    parent_graph_api_gateway: GraphTransportBundle = Depends(
        get_graph_api_gateway, use_cache=False
    ),
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> JSONObject | JSONResponse:
    """Start one full-research task with public payload naming."""
    result = await supervisor_runs.create_supervisor_run(
        space_id=space_id,
        request=request,
        prefer=prefer,
        current_user=current_user,
        run_registry=run_registry,
        artifact_store=artifact_store,
        parent_graph_api_gateway=parent_graph_api_gateway,
        execution_services=execution_services,
    )
    if isinstance(result, JSONResponse):
        return _publicized_json_response(result)
    payload = _publicize_json_object(result.model_dump(mode="json"))
    return payload or {}


@router.get(
    "/v2/spaces/{space_id}/tasks",
    response_model=TaskListResponse,
    summary="List tasks",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def list_tasks(
    space_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
) -> TaskListResponse:
    """Return tracked tasks for one research space."""
    response = runs.list_runs(
        space_id=space_id,
        offset=offset,
        limit=limit,
        run_registry=run_registry,
    )
    return TaskListResponse.from_v1(response)


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}",
    response_model=TaskResponse,
    summary="Get task",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def get_task(
    space_id: UUID,
    task_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
) -> TaskResponse:
    """Return one tracked task."""
    return TaskResponse.from_v1(
        _get_run(space_id=space_id, run_id=task_id, run_registry=run_registry),
    )


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}/progress",
    response_model=TaskProgressResponse,
    summary="Get task progress",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def get_task_progress(
    space_id: UUID,
    task_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
) -> TaskProgressResponse:
    """Return the latest progress snapshot for one tracked task."""
    return TaskProgressResponse.from_v1(
        _get_run_progress(
            space_id=space_id,
            run_id=task_id,
            run_registry=run_registry,
        ),
    )


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}/events",
    response_model=HarnessRunEventListResponse,
    summary="List task events",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def list_task_events(
    space_id: UUID,
    task_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
) -> HarnessRunEventListResponse:
    """Return lifecycle events for one tracked task."""
    return _list_run_events(
        space_id=space_id,
        run_id=task_id,
        offset=offset,
        limit=limit,
        run_registry=run_registry,
    )


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}/capabilities",
    response_model=TaskCapabilitiesResponse,
    summary="Get task capabilities",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def get_task_capabilities(
    space_id: UUID,
    task_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> TaskCapabilitiesResponse:
    """Return the frozen tool and policy snapshot for one tracked task."""
    return TaskCapabilitiesResponse.from_v1(
        _get_run_capabilities(
            space_id=space_id,
            run_id=task_id,
            run_registry=run_registry,
            artifact_store=artifact_store,
            execution_services=execution_services,
        ),
    )


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}/decisions",
    response_model=TaskDecisionsResponse,
    summary="Get task decisions",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def get_task_decisions(
    space_id: UUID,
    task_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> TaskDecisionsResponse:
    """Return declared and observed decisions for one tracked task."""
    return TaskDecisionsResponse.from_v1(
        _get_run_policy_decisions(
            space_id=space_id,
            run_id=task_id,
            run_registry=run_registry,
            artifact_store=artifact_store,
            execution_services=execution_services,
        ),
    )


@router.post(
    "/v2/spaces/{space_id}/tasks/{task_id}/resume",
    response_model=TaskResumeResponse,
    summary="Resume paused task",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["tasks"],
)
async def resume_task(
    space_id: UUID,
    task_id: UUID,
    request: HarnessRunResumeRequest,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> TaskResumeResponse:
    """Resume one paused tracked task."""
    return TaskResumeResponse.from_v1(
        await _resume_run(
            space_id=space_id,
            run_id=task_id,
            request=request,
            run_registry=run_registry,
            artifact_store=artifact_store,
            execution_services=execution_services,
        ),
    )


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}/outputs",
    response_model=TaskOutputListResponse,
    summary="List task outputs",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def list_task_outputs(
    space_id: UUID,
    task_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> TaskOutputListResponse:
    """Return outputs stored for one tracked task."""
    return TaskOutputListResponse.from_v1(
        _list_artifacts(
            space_id=space_id,
            run_id=task_id,
            offset=offset,
            limit=limit,
            run_registry=run_registry,
            artifact_store=artifact_store,
        ),
    )


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}/outputs/{output_key}",
    response_model=TaskOutputResponse,
    summary="Get task output",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def get_task_output(
    space_id: UUID,
    task_id: UUID,
    output_key: str,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> TaskOutputResponse:
    """Return one output stored for one tracked task."""
    return TaskOutputResponse.from_v1(
        _get_artifact(
            space_id=space_id,
            run_id=task_id,
            artifact_key=output_key,
            run_registry=run_registry,
            artifact_store=artifact_store,
        ),
    )


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}/working-state",
    response_model=TaskWorkingStateResponse,
    summary="Get task working state",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def get_task_working_state(
    space_id: UUID,
    task_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> TaskWorkingStateResponse:
    """Return the working-state snapshot stored for one tracked task."""
    return TaskWorkingStateResponse.from_v1(
        _get_workspace(
            space_id=space_id,
            run_id=task_id,
            run_registry=run_registry,
            artifact_store=artifact_store,
        ),
    )


@router.post(
    "/v2/spaces/{space_id}/tasks/{task_id}/planned-actions",
    response_model=HarnessRunIntentResponse,
    summary="Record planned task actions",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["tasks"],
)
def record_task_plan(
    space_id: UUID,
    task_id: UUID,
    request: HarnessRunIntentRequest,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    approval_store: HarnessApprovalStore = _APPROVAL_STORE_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> HarnessRunIntentResponse:
    """Record actions a task wants to take before user approval."""
    return _record_intent(
        space_id=space_id,
        run_id=task_id,
        request=request,
        run_registry=run_registry,
        approval_store=approval_store,
        artifact_store=artifact_store,
    )


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}/approvals",
    response_model=HarnessApprovalListResponse,
    summary="List task approvals",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def list_task_approvals(
    space_id: UUID,
    task_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    approval_store: HarnessApprovalStore = _APPROVAL_STORE_DEPENDENCY,
) -> HarnessApprovalListResponse:
    """Return approvals for one tracked task."""
    return _list_approvals(
        space_id=space_id,
        run_id=task_id,
        offset=offset,
        limit=limit,
        run_registry=run_registry,
        approval_store=approval_store,
    )


@router.post(
    "/v2/spaces/{space_id}/tasks/{task_id}/approvals/{approval_key}/decision",
    response_model=HarnessApprovalResponse,
    summary="Decide task approval",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["tasks"],
)
def decide_task_approval(
    space_id: UUID,
    task_id: UUID,
    approval_key: str,
    request: HarnessApprovalDecisionRequest,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    approval_store: HarnessApprovalStore = _APPROVAL_STORE_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> HarnessApprovalResponse:
    """Approve or reject one gated task action."""
    return _decide_approval(
        space_id=space_id,
        run_id=task_id,
        approval_key=approval_key,
        request=request,
        run_registry=run_registry,
        approval_store=approval_store,
        artifact_store=artifact_store,
    )


@router.get(
    "/v2/workflow-templates/{template_id}",
    response_model=WorkflowTemplateResponse,
    summary="Get workflow template",
    dependencies=[Depends(require_harness_read_access)],
    tags=["workflows"],
)
def get_workflow_template(template_id: str) -> WorkflowTemplateResponse:
    """Return one workflow template by its public template id."""
    return WorkflowTemplateResponse.from_v1(_get_harness(harness_id=template_id))


@router.get(
    "/v2/spaces/{space_id}/chat-sessions/{session_id}/messages/{task_id}/stream",
    summary="Stream chat task events",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["chat"],
)
async def stream_chat_task_message(
    space_id: UUID,
    session_id: UUID,
    task_id: str,
    request: Request,
    *,
    chat_session_store: HarnessChatSessionStore = _CHAT_SESSION_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> StreamingResponse:
    """Stream events for one chat task."""
    return await _stream_chat_message(
        space_id=space_id,
        session_id=session_id,
        run_id=task_id,
        request=request,
        chat_session_store=chat_session_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )


@router.get(
    "/v2/spaces/{space_id}/workflows/full-research/tasks/{task_id}",
    response_model=JSONObject,
    summary="Get full research task",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["workflows"],
)
def get_full_research_task(
    space_id: UUID,
    task_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> JSONObject:
    """Return one full-research task detail response."""
    payload = _get_supervisor_run(
        space_id=space_id,
        run_id=task_id,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )
    return _publicize_json_object(payload.model_dump(mode="json")) or {}


@router.post(
    "/v2/spaces/{space_id}/workflows/full-research/tasks/{task_id}/suggested-updates/{candidate_index}/decision",
    response_model=JSONObject,
    summary="Decide full research suggested update",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["workflows"],
)
def decide_full_research_suggested_update(
    space_id: UUID,
    task_id: UUID,
    candidate_index: int,
    request: chat.ChatGraphWriteCandidateDecisionRequest,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    proposal_store: HarnessProposalStore = Depends(get_proposal_store),
    graph_api_gateway: GraphTransportBundle = Depends(get_graph_api_gateway),
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> JSONObject:
    """Promote or reject one suggested update from a full-research task."""
    payload = _review_supervisor_update(
        space_id=space_id,
        run_id=task_id,
        candidate_index=candidate_index,
        request=request,
        run_registry=run_registry,
        artifact_store=artifact_store,
        proposal_store=proposal_store,
        graph_api_gateway=graph_api_gateway,
        execution_services=execution_services,
    )
    return _publicize_json_object(payload.model_dump(mode="json")) or {}


__all__ = ["router"]
