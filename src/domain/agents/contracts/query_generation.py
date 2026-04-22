"""
Query generation contract for data source agents.

This contract defines the output schema for agents that generate
search queries for various data sources (PubMed, ClinVar, etc.).
"""

from typing import Literal

from pydantic import Field

from src.domain.agents.contracts.base import BaseAgentContract


class QueryGenerationContract(BaseAgentContract):
    """
    Contract for query generation agents.

    Extends BaseAgentContract with query-specific fields for
    generating search queries optimized for various data sources.

    The decision field indicates:
    - generated: Query was successfully generated with high confidence
    - fallback: Agent fell back to a simpler query strategy
    - escalate: Query generation requires human review
    """

    decision: Literal["generated", "fallback", "escalate"] = Field(
        ...,
        description="Outcome of the query generation process",
    )
    query: str = Field(
        ...,
        description="The generated query string for the data source",
    )
    source_type: str = Field(
        ...,
        description="The data source type this query is optimized for",
    )
    query_complexity: Literal["simple", "moderate", "complex"] = Field(
        default="moderate",
        description="Assessed complexity of the generated query",
    )
    estimated_result_count: int | None = Field(
        default=None,
        description="Estimated number of results (if available)",
    )
