"""
Context for query generation agent pipelines.

Provides typed context for query generation workflows including
research space context, source-specific metadata, and audit fields.

Per production guidance, context fields should be indexable
for fast filtering and include audit metadata for compliance.
"""

from datetime import UTC, datetime

from pydantic import Field

from src.domain.agents.contexts.base import BaseAgentContext


class QueryGenerationContext(BaseAgentContext):
    """
    Context for query generation agent pipelines.

    Extends BaseAgentContext with fields specific to query generation
    workflows, including research space context and source targeting.

    Audit Fields (Indexed for Fast Filtering):
    - user_id: For audit attribution and access control
    - correlation_id: For distributed tracing
    - request_source: API, UI, scheduler, etc.
    - created_at: Timestamp for audit logs

    Research Context:
    - research_space_id: Links to research space entity
    - research_space_description: Context for the agent
    - source_type: Target data source (pubmed, clinvar, etc.)

    Workflow State:
    - user_instructions: User-provided steering
    - previous_queries: For iterative refinement
    - iteration_count: Track refinement iterations
    """

    # --- Audit Fields (Indexed in Postgres for fast filtering) ---
    user_id: str | None = Field(
        default=None,
        description="User ID for audit attribution and access control",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Correlation ID for distributed tracing",
    )
    request_source: str = Field(
        default="api",
        description="Source of the request (api, ui, scheduler, background)",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the context was created",
    )

    # --- Research Context ---
    research_space_id: str | None = Field(
        default=None,
        description="ID of the research space this query is for",
    )
    research_space_description: str | None = Field(
        default=None,
        description="Description of the research space context",
    )
    source_type: str = Field(
        default="unknown",
        description="Target data source type (pubmed, clinvar, etc.)",
    )

    # --- Workflow State ---
    user_instructions: str | None = Field(
        default=None,
        description="User-provided instructions for query steering",
    )
    previous_queries: list[str] = Field(
        default_factory=list,
        description="Previously generated queries for refinement context",
    )
    iteration_count: int = Field(
        default=0,
        description="Number of refinement iterations performed",
    )

    # --- Governance Metadata ---
    governance_flags: dict[str, bool] = Field(
        default_factory=dict,
        description="Governance flags applied to this run (pii_scrubbed, etc.)",
    )
