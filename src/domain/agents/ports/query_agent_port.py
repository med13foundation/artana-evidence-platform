"""
Port interface for query generation agent operations.

Defines the contract for query generation agents with proper
lifecycle management and result typing.
"""

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from src.domain.agents.contracts.query_generation import QueryGenerationContract


class QueryAgentPort(ABC):
    """
    Port interface for query generation agent operations.

    Defines how the application layer interacts with query generation
    agents for creating intelligent search queries optimized for
    various data sources.
    """

    @abstractmethod
    async def generate_query(  # noqa: PLR0913
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
        Generate an intelligent query string for a specific data source.

        Args:
            research_space_description: Description of the research space context
            user_instructions: User-provided prompting to steer the agent
            source_type: The type of data source (e.g., "pubmed", "clinvar")
            model_id: Optional model ID override for this request (None = use default)
            user_id: Optional user ID for audit attribution
            correlation_id: Optional correlation ID for distributed tracing

        Returns:
            QueryGenerationContract with the generated query and metadata
        """

    @abstractmethod
    async def close(self) -> None:
        """
        Clean up resources and drain connection pools.

        Must be called during application shutdown to prevent
        connection leaks.
        """


@runtime_checkable
class QueryAgentRunMetadataProvider(Protocol):
    """Optional protocol for agents that expose their last orchestration run id."""

    def get_last_run_id(self) -> str | None:
        """Return the most recently executed run id, if available."""
        ...
