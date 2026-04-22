"""
Application service for query generation agent operations.

Orchestrates the QueryAgentPort for intelligent query generation use cases,
handling cross-cutting concerns like logging, metrics, and research space
context resolution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.agents.contracts.query_generation import QueryGenerationContract

if TYPE_CHECKING:
    from src.domain.agents.ports.query_agent_port import QueryAgentPort
    from src.domain.repositories.research_space_repository import (
        ResearchSpaceRepository,
    )

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QueryAgentServiceDependencies:
    """
    Dependencies for QueryAgentService.

    Follows dependency injection pattern for testability.
    """

    query_agent: QueryAgentPort
    research_space_repository: ResearchSpaceRepository | None = None


class QueryAgentService:
    """
    Application service for query generation operations.

    This service orchestrates the QueryAgentPort to implement use cases
    for intelligent query generation. It handles:
    - Research space context resolution
    - Logging and metrics
    - Error handling and fallback strategies
    - Multi-source query coordination

    The service delegates all AI operations to the QueryAgentPort,
    keeping business logic in the domain layer.
    """

    def __init__(self, dependencies: QueryAgentServiceDependencies) -> None:
        """
        Initialize the query agent service.

        Args:
            dependencies: Injected dependencies for the service
        """
        self._agent = dependencies.query_agent
        self._research_space_repo = dependencies.research_space_repository

    async def generate_query_for_source(  # noqa: PLR0913
        self,
        research_space_description: str,
        user_instructions: str,
        source_type: str,
        *,
        model_id: str | None = None,
        user_id: str | None = None,
        correlation_id: str | None = None,
    ) -> QueryGenerationContract:
        """
        Generate an intelligent query for a specific data source.

        This is the primary use case for query generation. It transforms
        research context and user instructions into a high-fidelity
        search query optimized for the target data source.

        Args:
            research_space_description: Description of the research space context
            user_instructions: User-provided prompting to steer the agent
            source_type: The type of data source (e.g., "pubmed", "clinvar")
            model_id: Optional model ID override for this request
            user_id: Optional user ID for audit attribution
            correlation_id: Optional correlation ID for distributed tracing

        Returns:
            QueryGenerationContract with the generated query and metadata
        """
        logger.info(
            "Generating query for source=%s model=%s user=%s correlation=%s",
            source_type,
            model_id or "default",
            user_id,
            correlation_id,
        )

        result = await self._agent.generate_query(
            research_space_description=research_space_description,
            user_instructions=user_instructions,
            source_type=source_type,
            model_id=model_id,
            user_id=user_id,
            correlation_id=correlation_id,
        )

        logger.info(
            "Query generation complete: decision=%s confidence=%.2f source=%s",
            result.decision,
            result.confidence_score,
            source_type,
        )

        return result

    async def generate_query_for_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        user_instructions: str,
        source_type: str,
        *,
        model_id: str | None = None,
        user_id: str | None = None,
        correlation_id: str | None = None,
    ) -> QueryGenerationContract:
        """
        Generate a query using research space context by ID.

        Resolves the research space description from the repository
        and generates an intelligent query.

        Args:
            research_space_id: ID of the research space
            user_instructions: User-provided prompting to steer the agent
            source_type: The type of data source
            model_id: Optional model ID override for this request
            user_id: Optional user ID for audit attribution
            correlation_id: Optional correlation ID for distributed tracing

        Returns:
            QueryGenerationContract with the generated query and metadata

        Raises:
            ValueError: If research space repository is not configured
            LookupError: If research space is not found
        """
        from uuid import UUID

        if self._research_space_repo is None:
            msg = (
                "Research space repository not configured. "
                "Use generate_query_for_source() instead."
            )
            raise ValueError(msg)

        try:
            space_uuid = UUID(research_space_id)
        except ValueError as exc:
            msg = f"Invalid research space ID format: {research_space_id}"
            raise ValueError(msg) from exc

        research_space = self._research_space_repo.find_by_id(space_uuid)
        if research_space is None:
            msg = f"Research space not found: {research_space_id}"
            raise LookupError(msg)

        # Extract description from research space
        description = getattr(research_space, "description", None) or ""

        return await self.generate_query_for_source(
            research_space_description=description,
            user_instructions=user_instructions,
            source_type=source_type,
            model_id=model_id,
            user_id=user_id,
            correlation_id=correlation_id,
        )

    async def generate_queries_for_multiple_sources(  # noqa: PLR0913
        self,
        research_space_description: str,
        user_instructions: str,
        source_types: list[str],
        *,
        model_id: str | None = None,
        user_id: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, QueryGenerationContract]:
        """
        Generate queries for multiple data sources.

        Executes query generation for each source type and returns
        a mapping of source type to result contract.

        Args:
            research_space_description: Description of the research space context
            user_instructions: User-provided prompting to steer the agent
            source_types: List of data source types to generate queries for
            model_id: Optional model ID override for all requests
            user_id: Optional user ID for audit attribution
            correlation_id: Optional correlation ID for distributed tracing

        Returns:
            Dict mapping source_type to QueryGenerationContract
        """
        results: dict[str, QueryGenerationContract] = {}

        for source_type in source_types:
            try:
                result = await self.generate_query_for_source(
                    research_space_description=research_space_description,
                    user_instructions=user_instructions,
                    source_type=source_type,
                    model_id=model_id,
                    user_id=user_id,
                    correlation_id=correlation_id,
                )
                results[source_type] = result
            except (ValueError, LookupError, RuntimeError) as exc:
                logger.warning(
                    "Failed to generate query for source=%s: %s",
                    source_type,
                    exc,
                )
                # Create an error contract for failed sources
                results[source_type] = QueryGenerationContract(
                    decision="escalate",
                    confidence_score=0.0,
                    rationale=f"Query generation failed: {exc}",
                    evidence=[],
                    query="",
                    source_type=source_type,
                    query_complexity="simple",
                )

        return results

    def get_last_run_id(self) -> str | None:
        """
        Get the last agent run ID for debugging/inspection.

        Returns:
            The last run ID if available, None otherwise
        """
        if hasattr(self._agent, "get_last_run_id"):
            run_id = self._agent.get_last_run_id()
            return run_id if isinstance(run_id, str) else None
        return None

    async def close(self) -> None:
        """
        Clean up resources.

        Should be called during application shutdown.
        """
        await self._agent.close()
