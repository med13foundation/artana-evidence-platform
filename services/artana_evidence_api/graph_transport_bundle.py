"""Convenience bundle for graph API transports."""

from __future__ import annotations

from uuid import UUID

import httpx

from .config import get_settings
from .graph_integration.context import GraphCallContext
from .graph_transport import (
    GraphDictionaryTransport,
    GraphQueryTransport,
    GraphRawMutationTransportT,
    GraphServiceHealthResponse,
    GraphTransportConfig,
    GraphValidationTransport,
    GraphWorkflowTransport,
    SupportsGraphApiHttpClient,
    _GraphTransportRuntime,
    build_graph_raw_mutation_transport,
)
from .types.graph_contracts import (
    AIDecisionResponse,
    AIDecisionSubmitRequest,
    ClaimParticipantListResponse,
    ConceptProposalCreateRequest,
    ConceptProposalResponse,
    ConnectorProposalCreateRequest,
    ConnectorProposalResponse,
    CreateManualHypothesisRequest,
    ExplanationResponse,
    GraphChangeProposalCreateRequest,
    GraphChangeProposalResponse,
    GraphWorkflowActionRequest,
    GraphWorkflowCreateRequest,
    GraphWorkflowKind,
    GraphWorkflowListResponse,
    GraphWorkflowResponse,
    GraphWorkflowStatus,
    HypothesisListResponse,
    HypothesisResponse,
    KernelClaimEvidenceListResponse,
    KernelEntityEmbeddingRefreshRequest,
    KernelEntityEmbeddingRefreshResponse,
    KernelEntityEmbeddingStatusListResponse,
    KernelEntityListResponse,
    KernelGraphDocumentRequest,
    KernelGraphDocumentResponse,
    KernelReasoningPathDetailResponse,
    KernelReasoningPathListResponse,
    KernelRelationClaimListResponse,
    KernelRelationConflictListResponse,
    KernelRelationSuggestionListResponse,
    KernelRelationSuggestionRequest,
    OperatingModeCapabilitiesResponse,
    OperatingModeRequest,
    OperatingModeResponse,
)


class GraphTransportBundle:
    """Default graph integration surface for normal application code."""

    def __init__(
        self,
        config: GraphTransportConfig | None = None,
        *,
        client: SupportsGraphApiHttpClient | None = None,
        call_context: GraphCallContext | None = None,
    ) -> None:
        settings = get_settings()
        resolved_call_context = call_context or GraphCallContext.service()
        default_headers = resolved_call_context.default_headers()
        if config is None:
            resolved_config = GraphTransportConfig(
                base_url=settings.graph_api_url,
                timeout_seconds=settings.graph_api_timeout_seconds,
                default_headers=default_headers,
            )
        else:
            merged_default_headers = dict(default_headers)
            merged_default_headers.update(config.default_headers)
            resolved_config = GraphTransportConfig(
                base_url=config.base_url,
                timeout_seconds=config.timeout_seconds,
                default_headers=merged_default_headers,
            )
        owns_client = client is None
        runtime_client = client or httpx.Client(
            base_url=resolved_config.base_url.rstrip("/"),
            timeout=resolved_config.timeout_seconds,
            headers=resolved_config.default_headers,
        )
        runtime = _GraphTransportRuntime(
            config=resolved_config,
            call_context=resolved_call_context,
            client=runtime_client,
            owns_client=owns_client,
        )
        self._runtime = runtime
        self.query = GraphQueryTransport(runtime)
        self.validation = GraphValidationTransport(runtime)
        self.dictionary = GraphDictionaryTransport(runtime)
        self.workflow = GraphWorkflowTransport(runtime)
        self._raw_mutation = build_graph_raw_mutation_transport(runtime)

    @property
    def call_context(self) -> GraphCallContext:
        return self._runtime.call_context

    def close(self) -> None:
        self._runtime.close()

    def __enter__(self) -> GraphTransportBundle:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        del exc_type, exc, traceback
        self.close()

    def get_health(self) -> GraphServiceHealthResponse:
        return self.query.get_health()

    def refresh_entity_embeddings(
        self,
        *,
        space_id: UUID | str,
        request: KernelEntityEmbeddingRefreshRequest,
    ) -> KernelEntityEmbeddingRefreshResponse:
        return self.query.refresh_entity_embeddings(space_id=space_id, request=request)

    def list_entity_embedding_status(
        self,
        *,
        space_id: UUID | str,
        entity_ids: list[str] | None = None,
    ) -> KernelEntityEmbeddingStatusListResponse:
        return self.query.list_entity_embedding_status(
            space_id=space_id,
            entity_ids=entity_ids,
        )

    def suggest_relations(
        self,
        *,
        space_id: UUID | str,
        request: KernelRelationSuggestionRequest,
    ) -> KernelRelationSuggestionListResponse:
        return self.query.suggest_relations(space_id=space_id, request=request)

    def list_entities(
        self,
        *,
        space_id: UUID | str,
        q: str | None = None,
        entity_type: str | None = None,
        ids: list[str] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelEntityListResponse:
        return self.query.list_entities(
            space_id=space_id,
            q=q,
            entity_type=entity_type,
            ids=ids,
            offset=offset,
            limit=limit,
        )

    def list_claims(
        self,
        *,
        space_id: UUID | str,
        claim_status: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelRelationClaimListResponse:
        return self.query.list_claims(
            space_id=space_id,
            claim_status=claim_status,
            offset=offset,
            limit=limit,
        )

    def get_graph_document(
        self,
        *,
        space_id: UUID | str,
        request: KernelGraphDocumentRequest,
    ) -> KernelGraphDocumentResponse:
        return self.query.get_graph_document(space_id=space_id, request=request)

    def list_claims_by_entity(
        self,
        *,
        space_id: UUID | str,
        entity_id: UUID | str,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelRelationClaimListResponse:
        return self.query.list_claims_by_entity(
            space_id=space_id,
            entity_id=entity_id,
            offset=offset,
            limit=limit,
        )

    def list_claim_participants(
        self,
        *,
        space_id: UUID | str,
        claim_id: UUID | str,
    ) -> ClaimParticipantListResponse:
        return self.query.list_claim_participants(space_id=space_id, claim_id=claim_id)

    def list_claim_evidence(
        self,
        *,
        space_id: UUID | str,
        claim_id: UUID | str,
    ) -> KernelClaimEvidenceListResponse:
        return self.query.list_claim_evidence(space_id=space_id, claim_id=claim_id)

    def list_relation_conflicts(
        self,
        *,
        space_id: UUID | str,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelRelationConflictListResponse:
        return self.query.list_relation_conflicts(
            space_id=space_id,
            offset=offset,
            limit=limit,
        )

    def list_reasoning_paths(
        self,
        *,
        space_id: UUID | str,
        start_entity_id: UUID | str | None = None,
        end_entity_id: UUID | str | None = None,
        status: str | None = None,
        path_kind: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelReasoningPathListResponse:
        return self.query.list_reasoning_paths(
            space_id=space_id,
            start_entity_id=start_entity_id,
            end_entity_id=end_entity_id,
            status=status,
            path_kind=path_kind,
            offset=offset,
            limit=limit,
        )

    def get_reasoning_path(
        self,
        *,
        space_id: UUID | str,
        path_id: UUID | str,
    ) -> KernelReasoningPathDetailResponse:
        return self.query.get_reasoning_path(space_id=space_id, path_id=path_id)

    def create_manual_hypothesis(
        self,
        *,
        space_id: UUID | str,
        request: CreateManualHypothesisRequest,
    ) -> HypothesisResponse:
        return self.query.create_manual_hypothesis(space_id=space_id, request=request)

    def list_hypotheses(
        self,
        *,
        space_id: UUID | str,
        offset: int = 0,
        limit: int = 50,
    ) -> HypothesisListResponse:
        return self.query.list_hypotheses(
            space_id=space_id,
            offset=offset,
            limit=limit,
        )

    def get_operating_mode(
        self,
        *,
        space_id: UUID | str,
    ) -> OperatingModeResponse:
        return self.workflow.get_operating_mode(space_id=space_id)

    def update_operating_mode(
        self,
        *,
        space_id: UUID | str,
        request: OperatingModeRequest,
    ) -> OperatingModeResponse:
        return self.workflow.update_operating_mode(space_id=space_id, request=request)

    def get_operating_mode_capabilities(
        self,
        *,
        space_id: UUID | str,
    ) -> OperatingModeCapabilitiesResponse:
        return self.workflow.get_operating_mode_capabilities(space_id=space_id)

    def create_graph_workflow(
        self,
        *,
        space_id: UUID | str,
        request: GraphWorkflowCreateRequest,
    ) -> GraphWorkflowResponse:
        return self.workflow.create_graph_workflow(space_id=space_id, request=request)

    def list_graph_workflows(
        self,
        *,
        space_id: UUID | str,
        kind: GraphWorkflowKind | None = None,
        status: GraphWorkflowStatus | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> GraphWorkflowListResponse:
        return self.workflow.list_graph_workflows(
            space_id=space_id,
            kind=kind,
            status=status,
            offset=offset,
            limit=limit,
        )

    def get_graph_workflow(
        self,
        *,
        space_id: UUID | str,
        workflow_id: UUID | str,
    ) -> GraphWorkflowResponse:
        return self.workflow.get_graph_workflow(
            space_id=space_id,
            workflow_id=workflow_id,
        )

    def act_on_graph_workflow(
        self,
        *,
        space_id: UUID | str,
        workflow_id: UUID | str,
        request: GraphWorkflowActionRequest,
    ) -> GraphWorkflowResponse:
        return self.workflow.act_on_graph_workflow(
            space_id=space_id,
            workflow_id=workflow_id,
            request=request,
        )

    def explain_graph_resource(
        self,
        *,
        space_id: UUID | str,
        resource_type: str,
        resource_id: UUID | str,
    ) -> ExplanationResponse:
        return self.workflow.explain_graph_resource(
            space_id=space_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )

    def propose_concept(
        self,
        *,
        space_id: UUID | str,
        request: ConceptProposalCreateRequest,
        idempotency_key: str | None = None,
    ) -> ConceptProposalResponse:
        return self.workflow.propose_concept(
            space_id=space_id,
            request=request,
            idempotency_key=idempotency_key,
        )

    def propose_graph_change(
        self,
        *,
        space_id: UUID | str,
        request: GraphChangeProposalCreateRequest,
        idempotency_key: str | None = None,
    ) -> GraphChangeProposalResponse:
        return self.workflow.propose_graph_change(
            space_id=space_id,
            request=request,
            idempotency_key=idempotency_key,
        )

    def submit_ai_decision(
        self,
        *,
        space_id: UUID | str,
        request: AIDecisionSubmitRequest,
    ) -> AIDecisionResponse:
        return self.workflow.submit_ai_decision(space_id=space_id, request=request)

    def propose_connector_metadata(
        self,
        *,
        space_id: UUID | str,
        request: ConnectorProposalCreateRequest,
    ) -> ConnectorProposalResponse:
        return self.workflow.propose_connector_metadata(
            space_id=space_id,
            request=request,
        )

    def privileged_mutation_transport(self) -> GraphRawMutationTransportT:
        """Return the explicit privileged mutation transport for allowlisted flows."""
        return self._raw_mutation


__all__ = ["GraphTransportBundle"]
