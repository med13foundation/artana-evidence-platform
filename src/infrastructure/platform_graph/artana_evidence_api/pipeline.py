"""Pipeline orchestration helpers for Artana Evidence API HTTP cutovers."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID

from src.application.agents.services.graph_connection_service import (
    GraphConnectionOutcome,
)
from src.domain.entities.user import User, UserRole

from .runtime import (
    build_artana_evidence_api_client_for_service,
    build_artana_evidence_api_client_for_user,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from src.domain.agents.contracts.graph_connection import (
        GraphConnectionContract,
        ProposedRelation,
    )
    from src.domain.agents.contracts.graph_search import GraphSearchContract

    from .client import ArtanaEvidenceApiClient


class ArtanaEvidenceApiGraphSearchAdapter:
    """Async adapter that runs graph search against the Artana Evidence API."""

    def __init__(
        self,
        *,
        client_factory: Callable[[], ArtanaEvidenceApiClient],
    ) -> None:
        self._client_factory = client_factory

    async def search(  # noqa: PLR0913
        self,
        *,
        question: str,
        research_space_id: str,
        max_depth: int = 2,
        top_k: int = 25,
        curation_statuses: list[str] | None = None,
        include_evidence_chains: bool = True,
        force_agent: bool = False,
        model_id: str | None = None,
    ) -> GraphSearchContract:
        del force_agent

        def _call_artana_evidence_api() -> GraphSearchContract:
            client = self._client_factory()
            try:
                return client.search_graph(
                    space_id=UUID(research_space_id),
                    question=question,
                    model_id=model_id,
                    max_depth=max_depth,
                    top_k=top_k,
                    curation_statuses=curation_statuses,
                    include_evidence_chains=include_evidence_chains,
                )
            finally:
                client.close()

        return await asyncio.to_thread(_call_artana_evidence_api)


def _map_contract_to_outcome(
    contract: GraphConnectionContract,
    *,
    research_space_id: str,
    seed_entity_id: str,
    shadow_mode: bool | None,
) -> GraphConnectionOutcome:
    proposed_relations_count = len(contract.proposed_relations)
    errors = (
        tuple(warning for warning in contract.warnings if isinstance(warning, str))
        if hasattr(contract, "warnings")
        else ()
    )
    return GraphConnectionOutcome(
        seed_entity_id=seed_entity_id,
        research_space_id=research_space_id,
        status="discovered",
        reason=contract.decision,
        review_required=proposed_relations_count > 0,
        shadow_mode=bool(shadow_mode),
        wrote_to_graph=False,
        run_id=contract.agent_run_id or "artana-evidence-api-run",
        proposed_relations_count=proposed_relations_count,
        persisted_relations_count=0,
        rejected_candidates_count=len(contract.rejected_candidates),
        errors=errors,
    )


def build_graph_connection_seed_runner_for_user(
    current_user: User,
    *,
    client_factory: Callable[[User], ArtanaEvidenceApiClient] = (
        build_artana_evidence_api_client_for_user
    ),
) -> Callable[..., Awaitable[GraphConnectionOutcome]]:
    """Build one HTTP-backed graph seed runner against the harness service."""

    async def _runner(  # noqa: PLR0913
        *,
        source_id: str,
        research_space_id: str,
        seed_entity_id: str,
        source_type: str,
        model_id: str | None,
        relation_types: list[str] | None,
        max_depth: int,
        shadow_mode: bool | None,
        pipeline_run_id: str | None,
        fallback_relations: tuple[ProposedRelation, ...] | None,
    ) -> GraphConnectionOutcome:
        del fallback_relations

        def _call_artana_evidence_api() -> GraphConnectionOutcome:
            client = client_factory(current_user)
            try:
                contract = client.discover_entity_connections(
                    space_id=UUID(research_space_id),
                    entity_id=UUID(seed_entity_id),
                    source_type=source_type,
                    source_id=source_id,
                    model_id=model_id,
                    relation_types=relation_types,
                    max_depth=max_depth,
                    shadow_mode=shadow_mode,
                    pipeline_run_id=pipeline_run_id,
                )
                return _map_contract_to_outcome(
                    contract,
                    research_space_id=research_space_id,
                    seed_entity_id=seed_entity_id,
                    shadow_mode=shadow_mode,
                )
            finally:
                client.close()

        return await asyncio.to_thread(_call_artana_evidence_api)

    return _runner


def build_graph_search_service_for_user(
    current_user: User,
    *,
    client_factory: Callable[[User], ArtanaEvidenceApiClient] = (
        build_artana_evidence_api_client_for_user
    ),
) -> ArtanaEvidenceApiGraphSearchAdapter:
    """Build one HTTP-backed graph-search adapter against Artana Evidence API."""
    return ArtanaEvidenceApiGraphSearchAdapter(
        client_factory=lambda: client_factory(current_user),
    )


def build_graph_connection_seed_runner_for_service(
    *,
    role: UserRole = UserRole.VIEWER,
    client_factory: Callable[[], ArtanaEvidenceApiClient] | None = None,
) -> Callable[..., Awaitable[GraphConnectionOutcome]]:
    """Build one service-authenticated graph seed runner against the harness."""
    resolved_client_factory = client_factory or (
        lambda: build_artana_evidence_api_client_for_service(role=role)
    )

    async def _runner(  # noqa: PLR0913
        *,
        source_id: str,
        research_space_id: str,
        seed_entity_id: str,
        source_type: str,
        model_id: str | None,
        relation_types: list[str] | None,
        max_depth: int,
        shadow_mode: bool | None,
        pipeline_run_id: str | None,
        fallback_relations: tuple[ProposedRelation, ...] | None,
    ) -> GraphConnectionOutcome:
        del fallback_relations

        def _call_artana_evidence_api() -> GraphConnectionOutcome:
            client = resolved_client_factory()
            try:
                contract = client.discover_entity_connections(
                    space_id=UUID(research_space_id),
                    entity_id=UUID(seed_entity_id),
                    source_type=source_type,
                    source_id=source_id,
                    model_id=model_id,
                    relation_types=relation_types,
                    max_depth=max_depth,
                    shadow_mode=shadow_mode,
                    pipeline_run_id=pipeline_run_id,
                )
                return _map_contract_to_outcome(
                    contract,
                    research_space_id=research_space_id,
                    seed_entity_id=seed_entity_id,
                    shadow_mode=shadow_mode,
                )
            finally:
                client.close()

        return await asyncio.to_thread(_call_artana_evidence_api)

    return _runner


def build_graph_search_service_for_service(
    *,
    role: UserRole = UserRole.VIEWER,
    client_factory: Callable[[], ArtanaEvidenceApiClient] | None = None,
) -> ArtanaEvidenceApiGraphSearchAdapter:
    """Build one service-authenticated graph-search adapter against Artana Evidence API."""
    resolved_client_factory = client_factory or (
        lambda: build_artana_evidence_api_client_for_service(role=role)
    )
    return ArtanaEvidenceApiGraphSearchAdapter(client_factory=resolved_client_factory)


__all__ = [
    "ArtanaEvidenceApiGraphSearchAdapter",
    "build_graph_connection_seed_runner_for_service",
    "build_graph_connection_seed_runner_for_user",
    "build_graph_search_service_for_service",
    "build_graph_search_service_for_user",
]
