from __future__ import annotations

from uuid import UUID  # noqa: TC003

from src.domain.entities.user_data_source import (  # noqa: TC001
    SourceStatus,
    UserDataSource,
)
from src.type_definitions.common import JSONObject  # noqa: TC001

from .base import DomainEvent


def _serialize_uuid(value: UUID | str | None) -> str | None:
    return str(value) if value is not None else None


class SourceCreatedEvent(DomainEvent):
    """Event emitted when a user data source is created."""

    @classmethod
    def from_source(cls, source: UserDataSource) -> SourceCreatedEvent:
        payload: JSONObject = {
            "owner_id": _serialize_uuid(source.owner_id),
            "source_type": source.source_type.value,
            "status": source.status.value,
            "research_space_id": _serialize_uuid(source.research_space_id),
        }
        return cls(
            event_type="source.created",
            entity_type="UserDataSource",
            entity_id=str(source.id),
            payload=payload,
        )


class SourceUpdatedEvent(DomainEvent):
    """Event emitted when a user data source is updated."""

    @classmethod
    def from_source(
        cls,
        source: UserDataSource,
        *,
        changed_fields: list[str],
    ) -> SourceUpdatedEvent:
        payload: JSONObject = {
            "owner_id": _serialize_uuid(source.owner_id),
            "source_type": source.source_type.value,
            "changed_fields": list(changed_fields),
        }
        return cls(
            event_type="source.updated",
            entity_type="UserDataSource",
            entity_id=str(source.id),
            payload=payload,
        )


class SourceStatusChangedEvent(DomainEvent):
    """Event emitted when a user data source status changes."""

    @classmethod
    def from_source(
        cls,
        source: UserDataSource,
        *,
        previous_status: SourceStatus,
    ) -> SourceStatusChangedEvent:
        return cls(
            event_type="source.status_changed",
            entity_type="UserDataSource",
            entity_id=str(source.id),
            payload={
                "owner_id": _serialize_uuid(source.owner_id),
                "source_type": source.source_type.value,
                "from_status": previous_status.value,
                "to_status": source.status.value,
            },
        )


__all__ = [
    "SourceCreatedEvent",
    "SourceStatusChangedEvent",
    "SourceUpdatedEvent",
]
