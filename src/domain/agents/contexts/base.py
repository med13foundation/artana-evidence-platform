"""
Base context for AI agent pipelines.

Provides a typed context with MED13-specific fields for auditability
and traceability.
"""

from pydantic import BaseModel, ConfigDict, Field


class BaseAgentContext(BaseModel):
    """
    Base context for all MED13 AI agent pipelines.

    Defines shared fields required for:
    - User attribution (audit trail)
    - Source tracking
    - Request metadata
    """

    model_config = ConfigDict(extra="allow")

    user_id: str | None = Field(
        default=None,
        description="ID of the user who initiated the agent request",
    )
    request_source: str = Field(
        default="api",
        description="Source of the request (api, ui, background, etc.)",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Correlation ID for distributed tracing",
    )
