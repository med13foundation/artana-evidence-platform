"""Application service for source-agnostic query generation orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from uuid import UUID

    from src.domain.agents.ports.query_agent_port import QueryAgentPort
    from src.domain.repositories.research_space_repository import (
        ResearchSpaceRepository,
    )


@dataclass(frozen=True)
class QueryGenerationServiceDependencies:
    """Optional collaborators used by query generation orchestration."""

    query_agent: QueryAgentPort | None = None
    research_space_repository: ResearchSpaceRepository | None = None


@dataclass(frozen=True)
class QueryGenerationRequest:
    """Input contract for resolving an execution query."""

    base_query: str
    source_type: str
    is_ai_managed: bool
    agent_prompt: str = ""
    model_id: str | None = None
    use_research_space_context: bool = True
    research_space_id: UUID | None = None


@dataclass(frozen=True)
class QueryGenerationResult:
    """Resolved query details including execution mode and agent metadata."""

    query: str
    decision: Literal["generated", "fallback", "escalate", "skipped"]
    confidence: float
    run_id: str | None
    execution_mode: Literal["ai", "deterministic"]
    fallback_reason: str | None = None


class QueryGenerationService:
    """Resolve a query using deterministic defaults plus optional AI overlay."""

    def __init__(self, dependencies: QueryGenerationServiceDependencies) -> None:
        self._query_agent = dependencies.query_agent
        self._research_space_repository = dependencies.research_space_repository

    async def resolve_query(
        self,
        request: QueryGenerationRequest,
    ) -> QueryGenerationResult:
        base_query = request.base_query.strip()
        if not request.is_ai_managed or self._query_agent is None:
            return QueryGenerationResult(
                query=base_query,
                decision="skipped",
                confidence=0.0,
                run_id=None,
                execution_mode="deterministic",
                fallback_reason="ai_query_generation_disabled_or_unavailable",
            )

        research_space_description = ""
        if (
            request.use_research_space_context
            and request.research_space_id is not None
            and self._research_space_repository is not None
        ):
            space = self._research_space_repository.find_by_id(
                request.research_space_id,
            )
            if space is not None:
                research_space_description = space.description

        source_type = request.source_type.strip().lower() or "pubmed"
        contract = await self._query_agent.generate_query(
            research_space_description=research_space_description,
            user_instructions=request.agent_prompt,
            source_type=source_type,
            model_id=request.model_id,
        )

        resolved_query = base_query
        candidate_query = contract.query.strip()
        if (
            contract.decision == "generated"
            and candidate_query
            or contract.decision == "fallback"
            and candidate_query
        ):
            resolved_query = candidate_query

        return QueryGenerationResult(
            query=resolved_query,
            decision=contract.decision,
            confidence=contract.confidence_score,
            run_id=self._extract_run_id(),
            execution_mode="ai",
            fallback_reason=self._resolve_fallback_reason(
                decision=contract.decision,
                rationale=contract.rationale,
            ),
        )

    def _extract_run_id(self) -> str | None:
        if self._query_agent is None:
            return None
        provider = getattr(self._query_agent, "get_last_run_id", None)
        if not callable(provider):
            return None
        run_id = provider()
        if not isinstance(run_id, str):
            return None
        normalized = run_id.strip()
        return normalized or None

    @staticmethod
    def _resolve_fallback_reason(
        *,
        decision: str,
        rationale: str,
    ) -> str | None:
        if decision == "fallback":
            normalized = rationale.strip()
            return normalized or "agent_returned_fallback"
        if decision == "escalate":
            return "agent_requested_escalation"
        return None


__all__ = [
    "QueryGenerationRequest",
    "QueryGenerationResult",
    "QueryGenerationService",
    "QueryGenerationServiceDependencies",
]
