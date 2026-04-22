"""Domain entity for append-only pipeline trace events."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field

from src.type_definitions.common import JSONObject  # noqa: TC001

PipelineRunEventLevel = Literal["info", "warning", "error"]
PipelineRunEventScopeKind = Literal[
    "run",
    "query",
    "document",
    "dictionary",
    "concept",
    "relation",
    "graph",
    "agent",
    "tool",
    "cost",
]

_PIPELINE_RUN_EVENT_LEVELS: dict[str, PipelineRunEventLevel] = {
    "info": "info",
    "warning": "warning",
    "error": "error",
}
_PIPELINE_RUN_EVENT_SCOPE_KINDS: dict[str, PipelineRunEventScopeKind] = {
    "run": "run",
    "query": "query",
    "document": "document",
    "dictionary": "dictionary",
    "concept": "concept",
    "relation": "relation",
    "graph": "graph",
    "agent": "agent",
    "tool": "tool",
    "cost": "cost",
}


def resolve_pipeline_run_event_level(raw_value: str) -> PipelineRunEventLevel:
    """Validate and normalize persisted event levels."""
    resolved = _PIPELINE_RUN_EVENT_LEVELS.get(raw_value)
    if resolved is not None:
        return resolved
    msg = f"Unsupported pipeline event level: {raw_value}"
    raise ValueError(msg)


def resolve_pipeline_run_event_scope_kind(raw_value: str) -> PipelineRunEventScopeKind:
    """Validate and normalize persisted event scope kinds."""
    resolved = _PIPELINE_RUN_EVENT_SCOPE_KINDS.get(raw_value)
    if resolved is not None:
        return resolved
    msg = f"Unsupported pipeline event scope kind: {raw_value}"
    raise ValueError(msg)


class PipelineRunEvent(BaseModel):
    """One persisted pipeline event for human and agent diagnostics."""

    model_config = ConfigDict(frozen=True)

    seq: int | None = Field(default=None, ge=1)
    research_space_id: UUID
    source_id: UUID
    pipeline_run_id: str = Field(..., min_length=1, max_length=255)
    event_type: str = Field(..., min_length=1, max_length=64)
    stage: str | None = Field(default=None, max_length=64)
    scope_kind: PipelineRunEventScopeKind
    scope_id: str | None = Field(default=None, max_length=255)
    level: PipelineRunEventLevel = "info"
    status: str | None = Field(default=None, max_length=64)
    agent_kind: str | None = Field(default=None, max_length=64)
    agent_run_id: str | None = Field(default=None, max_length=255)
    error_code: str | None = Field(default=None, max_length=128)
    message: str = Field(..., min_length=1)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    queue_wait_ms: int | None = Field(default=None, ge=0)
    timeout_budget_ms: int | None = Field(default=None, ge=0)
    payload: JSONObject = Field(default_factory=dict)


__all__ = [
    "PipelineRunEvent",
    "PipelineRunEventLevel",
    "PipelineRunEventScopeKind",
    "resolve_pipeline_run_event_level",
    "resolve_pipeline_run_event_scope_kind",
]
