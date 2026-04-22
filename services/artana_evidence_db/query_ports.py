"""Service-local query-port protocols for graph search and planning."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from artana_evidence_db.common_types import JSONObject, JSONValue
from artana_evidence_db.kernel_domain_models import (
    DictionarySearchResult,
    KernelEntity,
    KernelObservation,
    KernelRelation,
    KernelRelationEvidence,
)
from artana_evidence_db.research_query_models import (
    ResearchQueryIntent,
    ResearchQueryPlan,
)


class GraphQueryPort(ABC):
    """Read-oriented graph query interface for graph-layer agents."""

    @abstractmethod
    def graph_query_entities(
        self,
        *,
        research_space_id: str,
        entity_type: str | None = None,
        query_text: str | None = None,
        limit: int = 200,
    ) -> list[KernelEntity]: ...

    @abstractmethod
    def graph_query_neighbourhood(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        depth: int = 1,
        relation_types: list[str] | None = None,
        limit: int = 200,
    ) -> list[KernelRelation]: ...

    @abstractmethod
    def graph_query_shared_subjects(
        self,
        *,
        research_space_id: str,
        entity_id_a: str,
        entity_id_b: str,
        limit: int = 100,
    ) -> list[KernelEntity]: ...

    @abstractmethod
    def graph_query_observations(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        variable_ids: list[str] | None = None,
        limit: int = 200,
    ) -> list[KernelObservation]: ...

    @abstractmethod
    def graph_query_relation_evidence(
        self,
        *,
        research_space_id: str,
        relation_id: str,
        limit: int = 200,
    ) -> list[KernelRelationEvidence]: ...

    @abstractmethod
    def graph_query_relations(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        entity_id: str,
        relation_types: list[str] | None = None,
        curation_statuses: list[str] | None = None,
        direction: Literal["outgoing", "incoming", "both"] = "both",
        depth: int = 1,
        limit: int = 200,
    ) -> list[KernelRelation]: ...

    @abstractmethod
    def graph_query_by_observation(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        variable_id: str,
        operator: Literal["eq", "lt", "lte", "gt", "gte", "contains"] = "eq",
        value: JSONValue | None = None,
        limit: int = 200,
    ) -> list[KernelEntity]: ...

    @abstractmethod
    def graph_aggregate(
        self,
        *,
        research_space_id: str,
        variable_id: str,
        entity_type: str | None = None,
        aggregation: Literal["count", "mean", "min", "max"] = "count",
    ) -> JSONObject: ...


class ResearchQueryPort(ABC):
    """Interface-layer API for natural-language graph query planning."""

    @abstractmethod
    def parse_intent(
        self,
        *,
        question: str,
        research_space_id: str,
    ) -> ResearchQueryIntent: ...

    @abstractmethod
    def resolve_terms(
        self,
        *,
        terms: list[str],
        domain_context: str | None = None,
        limit: int = 50,
    ) -> list[DictionarySearchResult]: ...

    @abstractmethod
    def build_query_plan(
        self,
        *,
        intent: ResearchQueryIntent,
        max_depth: int = 2,
        top_k: int = 25,
    ) -> ResearchQueryPlan: ...


__all__ = ["GraphQueryPort", "ResearchQueryPort"]
