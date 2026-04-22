"""Governed graph submission service built on top of raw transport calls."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from artana_evidence_api.graph_client import (
    GraphDictionaryTransport,
    GraphRawMutationTransport,
    GraphServiceClientError,
    GraphTransportBundle,
    GraphTransportConfig,
)
from artana_evidence_api.graph_integration.context import (
    GraphCallContext,
    make_graph_raw_mutation_transport_factory,
)
from artana_evidence_api.graph_integration.contracts import (
    GovernedGraphCommand,
    ResolvedGraphIntent,
)
from artana_evidence_api.types.common import JSONObject
from artana_evidence_api.types.graph_contracts import (
    AIDecisionResponse,
    AIDecisionSubmitRequest,
    ConceptProposalCreateRequest,
    ConceptProposalResponse,
    ConnectorProposalCreateRequest,
    ConnectorProposalResponse,
    DictionaryEntityTypeProposalCreateRequest,
    DictionaryProposalResponse,
    DictionaryRelationConstraintProposalCreateRequest,
    DictionaryRelationTypeProposalCreateRequest,
    GraphChangeProposalCreateRequest,
    GraphChangeProposalResponse,
    GraphWorkflowActionRequest,
    GraphWorkflowCreateRequest,
    GraphWorkflowResponse,
    KernelObservationCreateRequest,
    KernelObservationResponse,
    KernelRelationClaimCreateRequest,
    KernelRelationClaimResponse,
    KernelRelationCreateRequest,
    KernelRelationResponse,
)

GraphTransportBundleFactory = Callable[[GraphCallContext], GraphTransportBundle]
GraphRawMutationTransportFactory = Callable[
    [GraphCallContext], GraphRawMutationTransport
]
GraphDictionaryTransportFactory = Callable[[], GraphDictionaryTransport]


def _default_bundle_factory(call_context: GraphCallContext) -> GraphTransportBundle:
    return GraphTransportBundle(call_context=call_context)


def _default_raw_mutation_transport_factory(
    call_context: GraphCallContext,
) -> GraphRawMutationTransport:
    return make_graph_raw_mutation_transport_factory(call_context=call_context)()


def _default_admin_dictionary_transport_factory() -> GraphDictionaryTransport:
    bundle = GraphTransportBundle(
        call_context=GraphCallContext.service(graph_admin=True)
    )
    return bundle.dictionary


def _relation_materialization_call_context(
    call_context: GraphCallContext,
) -> GraphCallContext:
    """Promote one scoped call context for the internal relation materialization path."""
    return GraphCallContext(
        user_id=call_context.user_id,
        role=call_context.role,
        graph_admin=True,
        graph_ai_principal=call_context.graph_ai_principal,
        graph_service_capabilities=call_context.graph_service_capabilities,
        request_id=call_context.request_id,
    )


def _call_flat_graph_mutation(
    *,
    graph_transport: object,
    space_id: UUID,
    command: GovernedGraphCommand,
) -> JSONObject | KernelRelationClaimResponse | KernelRelationResponse | None:
    legacy_space_id = str(space_id)
    if command.kind == "create_entity" and hasattr(graph_transport, "create_entity"):
        payload = command.payload
        create_entity = cast(
            "Callable[..., JSONObject | None]", graph_transport.create_entity
        )
        try:
            return create_entity(
                space_id=legacy_space_id,
                entity_type=str(payload["entity_type"]),
                display_label=str(payload["display_label"]),
                aliases=payload.get("aliases"),
                metadata=payload.get("metadata"),
                identifiers=payload.get("identifiers"),
            )
        except TypeError:
            return create_entity(
                space_id=legacy_space_id,
                entity_type=str(payload["entity_type"]),
                display_label=str(payload["display_label"]),
            )
    if command.kind == "create_claim" and hasattr(graph_transport, "create_claim"):
        create_claim = cast(
            "Callable[..., KernelRelationClaimResponse]",
            graph_transport.create_claim,
        )
        return create_claim(
            space_id=legacy_space_id,
            request=KernelRelationClaimCreateRequest.model_validate(command.payload),
        )
    if command.kind == "create_relation" and hasattr(
        graph_transport, "create_relation"
    ):
        create_relation = cast(
            "Callable[..., KernelRelationResponse]",
            graph_transport.create_relation,
        )
        return create_relation(
            space_id=legacy_space_id,
            request=KernelRelationCreateRequest.model_validate(command.payload),
        )
    return None


def _preserved_runtime_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.casefold() not in {"authorization", "x-request-id"}
    }


def _raw_transport_for_context(
    *,
    graph_transport: object,
    call_context: GraphCallContext,
    fallback_factory: GraphRawMutationTransportFactory,
) -> GraphRawMutationTransport:
    if not isinstance(graph_transport, GraphTransportBundle):
        return fallback_factory(call_context)
    runtime = graph_transport._runtime  # noqa: SLF001 - intentional shared transport runtime
    scoped_bundle = GraphTransportBundle(
        config=GraphTransportConfig(
            base_url=runtime.config.base_url,
            timeout_seconds=runtime.config.timeout_seconds,
            default_headers=_preserved_runtime_headers(runtime.config.default_headers),
        ),
        client=runtime.client,
        call_context=call_context,
    )
    return GraphRawMutationTransport(scoped_bundle._runtime)  # noqa: SLF001


@dataclass
class GraphWorkflowSubmissionService:
    """Submit preflighted graph commands through explicit transport contexts."""

    bundle_factory: GraphTransportBundleFactory = _default_bundle_factory
    raw_mutation_transport_factory: GraphRawMutationTransportFactory = (
        _default_raw_mutation_transport_factory
    )
    admin_dictionary_transport_factory: GraphDictionaryTransportFactory = (
        _default_admin_dictionary_transport_factory
    )

    def submit_resolved_intent(
        self,
        *,
        resolved_intent: ResolvedGraphIntent,
        graph_transport: GraphTransportBundle,
    ) -> (
        JSONObject
        | DictionaryProposalResponse
        | KernelRelationClaimResponse
        | KernelRelationResponse
    ):
        """Submit one preflighted entity/claim/relation intent."""
        proposal_commands = [
            command
            for command in resolved_intent.commands
            if command.kind.startswith("propose_")
        ]
        if proposal_commands:
            with self.admin_dictionary_transport_factory() as dictionary_transport:
                for command in proposal_commands:
                    self._apply_governed_command(
                        space_id=resolved_intent.raw_intent.space_id,
                        command=command,
                        dictionary_transport=dictionary_transport,
                    )

        create_commands = [
            command
            for command in resolved_intent.commands
            if command.kind in {"create_entity", "create_claim", "create_relation"}
        ]
        if not create_commands:
            review_detail = resolved_intent.blocked_detail or next(
                (
                    command.detail
                    for command in proposal_commands
                    if isinstance(command.detail, str) and command.detail.strip()
                ),
                None,
            )
            raise GraphServiceClientError(
                "Graph preflight requires review",
                status_code=400,
                detail=review_detail
                or "Governed graph review is required before mutation.",
            )
        command = create_commands[0]
        legacy_result = _call_flat_graph_mutation(
            graph_transport=graph_transport,
            space_id=resolved_intent.raw_intent.space_id,
            command=command,
        )
        if legacy_result is not None:
            return legacy_result
        if not hasattr(graph_transport, "call_context"):
            raise GraphServiceClientError(
                "Graph transport does not expose call_context",
                status_code=400,
                detail=command.kind,
            )
        raw_call_context = (
            _relation_materialization_call_context(graph_transport.call_context)
            if command.kind == "create_relation"
            else graph_transport.call_context
        )
        with _raw_transport_for_context(
            graph_transport=graph_transport,
            call_context=raw_call_context,
            fallback_factory=self.raw_mutation_transport_factory,
        ) as raw_transport:
            return self._apply_governed_command(
                space_id=resolved_intent.raw_intent.space_id,
                command=command,
                raw_transport=raw_transport,
            )

    def create_graph_workflow(
        self,
        *,
        space_id: UUID | str,
        request: GraphWorkflowCreateRequest,
        call_context: GraphCallContext,
    ) -> GraphWorkflowResponse:
        """Submit one unified workflow request through an explicit call context."""
        with self.bundle_factory(call_context) as bundle:
            return bundle.workflow.create_graph_workflow(
                space_id=space_id, request=request
            )

    def act_on_graph_workflow(
        self,
        *,
        space_id: UUID | str,
        workflow_id: UUID | str,
        request: GraphWorkflowActionRequest,
        call_context: GraphCallContext,
    ) -> GraphWorkflowResponse:
        """Submit one workflow action through an explicit call context."""
        with self.bundle_factory(call_context) as bundle:
            return bundle.workflow.act_on_graph_workflow(
                space_id=space_id,
                workflow_id=workflow_id,
                request=request,
            )

    def propose_concept(
        self,
        *,
        space_id: UUID | str,
        request: ConceptProposalCreateRequest,
        call_context: GraphCallContext,
        idempotency_key: str | None = None,
    ) -> ConceptProposalResponse:
        """Submit one governed concept proposal through an explicit context."""
        with self.bundle_factory(call_context) as bundle:
            return bundle.workflow.propose_concept(
                space_id=space_id,
                request=request,
                idempotency_key=idempotency_key,
            )

    def propose_graph_change(
        self,
        *,
        space_id: UUID | str,
        request: GraphChangeProposalCreateRequest,
        call_context: GraphCallContext,
        idempotency_key: str | None = None,
    ) -> GraphChangeProposalResponse:
        """Submit one governed graph-change proposal through an explicit context."""
        with self.bundle_factory(call_context) as bundle:
            return bundle.workflow.propose_graph_change(
                space_id=space_id,
                request=request,
                idempotency_key=idempotency_key,
            )

    def propose_connector(
        self,
        *,
        space_id: UUID | str,
        request: ConnectorProposalCreateRequest,
        call_context: GraphCallContext,
    ) -> ConnectorProposalResponse:
        """Submit one governed connector proposal through an explicit context."""
        with self.bundle_factory(call_context) as bundle:
            return bundle.workflow.propose_connector_metadata(
                space_id=space_id,
                request=request,
            )

    def submit_ai_decision(
        self,
        *,
        space_id: UUID | str,
        request: AIDecisionSubmitRequest,
        request_id: str | None = None,
    ) -> AIDecisionResponse:
        """Submit one AI decision using the declared AI principal as transport authority."""
        with self.bundle_factory(
            GraphCallContext.service(
                role="curator",
                graph_admin=True,
                graph_ai_principal=request.ai_principal,
                request_id=request_id,
            ),
        ) as bundle:
            return bundle.workflow.submit_ai_decision(
                space_id=space_id, request=request
            )

    def record_observation(
        self,
        *,
        space_id: UUID | str,
        request: KernelObservationCreateRequest,
        graph_transport: GraphTransportBundle,
    ) -> KernelObservationResponse:
        """Record one observation through the scoped raw mutation transport."""
        if hasattr(graph_transport, "create_observation"):
            create_observation = cast(
                "Callable[..., KernelObservationResponse]",
                graph_transport.create_observation,
            )
            try:
                return create_observation(space_id=space_id, request=request)
            except TypeError:
                pass
        if not hasattr(graph_transport, "call_context"):
            raise GraphServiceClientError(
                "Graph transport does not expose call_context",
                status_code=400,
                detail="create_observation",
            )
        with _raw_transport_for_context(
            graph_transport=graph_transport,
            call_context=graph_transport.call_context,
            fallback_factory=self.raw_mutation_transport_factory,
        ) as raw_transport:
            return raw_transport.create_observation_direct(
                space_id=space_id,
                request=request,
            )

    def _apply_governed_command(
        self,
        *,
        space_id: UUID,
        command: GovernedGraphCommand,
        raw_transport: GraphRawMutationTransport | None = None,
        dictionary_transport: GraphDictionaryTransport | None = None,
    ) -> (
        JSONObject
        | DictionaryProposalResponse
        | KernelRelationClaimResponse
        | KernelRelationResponse
    ):
        if command.kind == "create_entity":
            payload = command.payload
            aliases = payload.get("aliases")
            metadata = payload.get("metadata")
            identifiers = payload.get("identifiers")
            if raw_transport is None:
                raise GraphServiceClientError(
                    "Raw mutation transport is required",
                    status_code=400,
                    detail=command.kind,
                )
            return raw_transport.upsert_entity_direct(
                space_id=space_id,
                entity_type=str(payload["entity_type"]),
                display_label=str(payload["display_label"]),
                aliases=[str(alias) for alias in aliases]
                if isinstance(aliases, list)
                else None,
                metadata=metadata if isinstance(metadata, dict) else None,
                identifiers=(
                    {
                        str(key): str(value)
                        for key, value in identifiers.items()
                        if isinstance(key, str) and isinstance(value, str)
                    }
                    if isinstance(identifiers, dict)
                    else None
                ),
            )
        if command.kind == "create_claim":
            if raw_transport is None:
                raise GraphServiceClientError(
                    "Raw mutation transport is required",
                    status_code=400,
                    detail=command.kind,
                )
            return raw_transport.create_unresolved_claim_direct(
                space_id=space_id,
                request=KernelRelationClaimCreateRequest.model_validate(
                    command.payload
                ),
            )
        if command.kind == "create_relation":
            if raw_transport is None:
                raise GraphServiceClientError(
                    "Raw mutation transport is required",
                    status_code=400,
                    detail=command.kind,
                )
            return raw_transport.materialize_relation_direct(
                space_id=space_id,
                request=KernelRelationCreateRequest.model_validate(command.payload),
            )
        if command.kind == "propose_entity_type":
            if dictionary_transport is None:
                raise GraphServiceClientError(
                    "Dictionary transport is required",
                    status_code=400,
                    detail=command.kind,
                )
            return dictionary_transport.submit_entity_type_proposal(
                request=DictionaryEntityTypeProposalCreateRequest.model_validate(
                    command.payload,
                ),
            )
        if command.kind == "propose_relation_type":
            if dictionary_transport is None:
                raise GraphServiceClientError(
                    "Dictionary transport is required",
                    status_code=400,
                    detail=command.kind,
                )
            return dictionary_transport.submit_relation_type_proposal(
                request=DictionaryRelationTypeProposalCreateRequest.model_validate(
                    command.payload,
                ),
            )
        if command.kind == "propose_relation_constraint":
            if dictionary_transport is None:
                raise GraphServiceClientError(
                    "Dictionary transport is required",
                    status_code=400,
                    detail=command.kind,
                )
            return dictionary_transport.submit_relation_constraint_proposal(
                request=DictionaryRelationConstraintProposalCreateRequest.model_validate(
                    command.payload,
                ),
            )
        raise GraphServiceClientError(
            "Unsupported governed graph command",
            status_code=400,
            detail=command.kind,
        )


__all__ = ["GraphWorkflowSubmissionService"]
