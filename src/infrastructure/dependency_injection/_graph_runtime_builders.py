"""Monolith-side builders for graph search and graph connection orchestration."""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

from artana_evidence_db.composition import build_entity_repository
from artana_evidence_db.governance import (
    build_dictionary_repository,
    build_dictionary_service,
)
from artana_evidence_db.graph_query_repository import SqlAlchemyGraphQueryRepository
from artana_evidence_db.kernel_runtime_factories import (
    build_graph_read_model_update_dispatcher,
    build_relation_repository,
)
from artana_evidence_db.runtime import (
    GraphDomainPack,
    create_graph_domain_pack,
    is_flag_enabled,
)

from src.application.agents.services import (
    GovernanceService,
    GraphConnectionService,
    GraphConnectionServiceDependencies,
    GraphSearchService,
    GraphSearchServiceDependencies,
)
from src.application.services.research_query_service import ResearchQueryService
from src.domain.agents.contracts import EvidenceItem, GraphConnectionContract
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.graph_connection_port import GraphConnectionPort
from src.infrastructure.llm.adapters import (
    ArtanaGraphConnectionAdapter,
    ArtanaGraphSearchAdapter,
)
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.graph_domain_ai_config import create_graph_domain_ai_config

if TYPE_CHECKING:
    from artana_evidence_db.query_ports import GraphQueryPort
    from sqlalchemy.orm import Session

    from src.domain.agents.contexts.graph_connection_context import (
        GraphConnectionContext,
    )
    from src.domain.agents.graph_domain_ai_contracts import GraphDomainAiConfig
    from src.domain.agents.ports.graph_search_port import GraphSearchPort


class _UnavailableGraphConnectionAgent(GraphConnectionPort):
    """Fallback graph-connection agent when Artana is unavailable."""

    def __init__(self, reason: str) -> None:
        self._reason = reason

    async def discover(
        self,
        context: GraphConnectionContext,
        *,
        model_id: str | None = None,
    ) -> GraphConnectionContract:
        del model_id
        return GraphConnectionContract(
            decision="fallback",
            confidence_score=0.05,
            rationale=f"Graph connection agent unavailable ({self._reason}).",
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator=f"graph-connection:{context.research_space_id}",
                    excerpt=f"Unavailable reason: {self._reason}",
                    relevance=0.1,
                ),
            ],
            source_type=context.source_type,
            research_space_id=context.research_space_id,
            seed_entity_id=context.seed_entity_id,
            proposed_relations=[],
            rejected_candidates=[],
            shadow_mode=context.shadow_mode,
            agent_run_id=None,
        )

    async def close(self) -> None:
        return None


def _build_graph_query_repository(session: Session) -> SqlAlchemyGraphQueryRepository:
    return SqlAlchemyGraphQueryRepository(
        session,
        relation_repository=build_relation_repository(session),
    )


def _build_graph_search_agent(
    *,
    graph_query_service: GraphQueryPort,
    graph_domain_pack: GraphDomainPack,
    graph_domain_ai_config: GraphDomainAiConfig,
) -> GraphSearchPort | None:
    if not is_flag_enabled(graph_domain_pack.feature_flags.search_agent):
        return None
    if importlib.util.find_spec("artana") is None:
        return None

    registry = get_model_registry()
    model_spec = registry.get_default_model(ModelCapability.QUERY_GENERATION)
    try:
        return ArtanaGraphSearchAdapter(
            model=model_spec.model_id,
            search_extension=graph_domain_ai_config.search_extension,
            graph_query_service=graph_query_service,
        )
    except Exception:  # noqa: BLE001
        return None


def _build_graph_connection_agent(
    *,
    dictionary_service: object,
    graph_query_service: SqlAlchemyGraphQueryRepository,
    relation_repository: object,
    graph_domain_ai_config: GraphDomainAiConfig,
) -> GraphConnectionPort:
    registry = get_model_registry()
    model_spec = registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)
    try:
        return ArtanaGraphConnectionAdapter(
            model=model_spec.model_id,
            prompt_config=graph_domain_ai_config.graph_connection_prompt,
            dictionary_service=dictionary_service,
            graph_query_service=graph_query_service,
            relation_repository=relation_repository,
        )
    except Exception as exc:  # noqa: BLE001
        return _UnavailableGraphConnectionAgent(str(exc))


def build_graph_search_service(session: Session) -> GraphSearchService:
    """Build graph-search orchestration for the legacy monolith container."""
    graph_domain_pack = create_graph_domain_pack()
    graph_domain_ai_config = create_graph_domain_ai_config(graph_domain_pack.name)
    dictionary_service = build_dictionary_service(
        session,
        dictionary_loading_extension=graph_domain_pack.dictionary_loading_extension,
    )
    graph_query_service = _build_graph_query_repository(session)
    return GraphSearchService(
        dependencies=GraphSearchServiceDependencies(
            research_query_service=ResearchQueryService(
                dictionary_service=dictionary_service,
            ),
            graph_query_service=graph_query_service,
            graph_search_agent=_build_graph_search_agent(
                graph_query_service=graph_query_service,
                graph_domain_pack=graph_domain_pack,
                graph_domain_ai_config=graph_domain_ai_config,
            ),
            governance_service=GovernanceService(),
        ),
    )


def build_graph_connection_service(session: Session) -> GraphConnectionService:
    """Build graph-connection orchestration for the legacy monolith container."""
    from artana_evidence_db.kernel_repositories import (
        SqlAlchemyKernelClaimEvidenceRepository,
        SqlAlchemyKernelClaimParticipantRepository,
        SqlAlchemyKernelRelationClaimRepository,
        SqlAlchemyKernelRelationProjectionSourceRepository,
        SqlAlchemyKernelSpaceSettingsRepository,
    )
    from artana_evidence_db.kernel_services import (
        KernelRelationProjectionMaterializationService,
    )

    graph_domain_pack = create_graph_domain_pack()
    graph_domain_ai_config = create_graph_domain_ai_config(graph_domain_pack.name)
    dictionary_service = build_dictionary_service(
        session,
        dictionary_loading_extension=graph_domain_pack.dictionary_loading_extension,
    )
    relation_repository = build_relation_repository(session)
    graph_query_service = _build_graph_query_repository(session)
    graph_connection_agent = _build_graph_connection_agent(
        dictionary_service=dictionary_service,
        graph_query_service=graph_query_service,
        relation_repository=relation_repository,
        graph_domain_ai_config=graph_domain_ai_config,
    )

    return GraphConnectionService(
        dependencies=GraphConnectionServiceDependencies(
            graph_connection_agent=graph_connection_agent,
            graph_connection_prompt=graph_domain_ai_config.graph_connection_prompt,
            relation_repository=relation_repository,
            entity_repository=build_entity_repository(session),
            relation_claim_repository=SqlAlchemyKernelRelationClaimRepository(session),
            claim_participant_repository=SqlAlchemyKernelClaimParticipantRepository(
                session,
            ),
            claim_evidence_repository=SqlAlchemyKernelClaimEvidenceRepository(
                session,
            ),
            relation_projection_source_repository=(
                SqlAlchemyKernelRelationProjectionSourceRepository(session)
            ),
            relation_projection_materialization_service=(
                KernelRelationProjectionMaterializationService(
                    relation_repo=relation_repository,
                    relation_claim_repo=SqlAlchemyKernelRelationClaimRepository(
                        session,
                    ),
                    claim_participant_repo=(
                        SqlAlchemyKernelClaimParticipantRepository(session)
                    ),
                    claim_evidence_repo=SqlAlchemyKernelClaimEvidenceRepository(
                        session,
                    ),
                    entity_repo=build_entity_repository(session),
                    dictionary_repo=build_dictionary_repository(
                        session,
                        dictionary_loading_extension=(
                            graph_domain_pack.dictionary_loading_extension
                        ),
                    ),
                    relation_projection_repo=(
                        SqlAlchemyKernelRelationProjectionSourceRepository(session)
                    ),
                    read_model_update_dispatcher=(
                        build_graph_read_model_update_dispatcher(session)
                    ),
                )
            ),
            governance_service=GovernanceService(),
            space_settings_port=SqlAlchemyKernelSpaceSettingsRepository(session),
            rollback_on_error=session.rollback,
        ),
    )


__all__ = [
    "build_graph_connection_service",
    "build_graph_search_service",
]
