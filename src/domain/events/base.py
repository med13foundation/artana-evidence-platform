from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject


class DomainEvent(BaseModel):
    """Base domain event structure."""

    event_type: str
    entity_type: str
    entity_id: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: JSONObject = Field(default_factory=dict)


__all__ = ["DomainEvent"]
