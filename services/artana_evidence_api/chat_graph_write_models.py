"""Shared models for chat-derived graph-write candidates."""

from __future__ import annotations

from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from pydantic import BaseModel, ConfigDict, Field


class ChatGraphWriteCandidateRequest(BaseModel):
    """One graph-write proposal candidate derived from chat findings."""

    model_config = ConfigDict(strict=True)

    source_entity_id: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_entity_id: str = Field(..., min_length=1, max_length=64)
    evidence_entity_ids: list[str] = Field(min_length=1, max_length=20)
    title: str | None = Field(default=None, min_length=1, max_length=256)
    summary: str | None = Field(default=None, min_length=1, max_length=2000)
    rationale: str | None = Field(default=None, min_length=1, max_length=4000)
    ranking_score: float | None = Field(default=None, ge=0.0, le=1.0)
    ranking_metadata: JSONObject | None = None


__all__ = ["ChatGraphWriteCandidateRequest"]
