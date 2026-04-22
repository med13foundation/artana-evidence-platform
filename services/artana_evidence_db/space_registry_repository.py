"""Service-local SQLAlchemy adapter for the graph-owned space registry."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeGuard
from uuid import UUID

from artana_evidence_db.common_types import JSONObject, JSONValue, ResearchSpaceSettings
from artana_evidence_db.ports import SpaceRegistryPort
from artana_evidence_db.space_models import GraphSpaceModel, GraphSpaceStatusEnum
from artana_evidence_db.space_registry import KernelSpaceRegistryEntry
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _is_research_space_settings(value: object) -> TypeGuard[ResearchSpaceSettings]:
    return isinstance(value, dict)


def _is_json_value(value: object) -> TypeGuard[JSONValue]:
    if value is None or isinstance(value, str | int | float | bool):
        return True
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_json_value(item) for key, item in value.items()
        )
    if isinstance(value, list | tuple):
        return all(_is_json_value(item) for item in value)
    return False


def _serialize_settings(settings: ResearchSpaceSettings) -> JSONObject:
    payload: JSONObject = {}
    for key, value in settings.items():
        if _is_json_value(value):
            payload[key] = value
    return payload


def _coerce_settings(raw_settings: object) -> ResearchSpaceSettings:
    if not _is_research_space_settings(raw_settings):
        return {}
    return raw_settings


def _to_entity(model: GraphSpaceModel) -> KernelSpaceRegistryEntry:
    return KernelSpaceRegistryEntry(
        id=UUID(str(model.id)),
        slug=model.slug,
        name=model.name,
        description=model.description,
        owner_id=UUID(str(model.owner_id)),
        status=str(model.status.value),
        settings=_coerce_settings(model.settings),
        sync_source=model.sync_source,
        sync_fingerprint=model.sync_fingerprint,
        source_updated_at=model.source_updated_at,
        last_synced_at=model.last_synced_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlAlchemyKernelSpaceRegistryRepository(SpaceRegistryPort):
    """Resolve graph-local tenant metadata from the graph-owned registry."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(
        self,
        space_id: UUID,
    ) -> KernelSpaceRegistryEntry | None:
        model = self._session.get(GraphSpaceModel, space_id)
        if model is None:
            return None
        return _to_entity(model)

    def get_by_slug(
        self,
        slug: str,
    ) -> KernelSpaceRegistryEntry | None:
        stmt = select(GraphSpaceModel).where(GraphSpaceModel.slug == slug)
        model = self._session.scalar(stmt)
        if model is None:
            return None
        return _to_entity(model)

    def list_space_ids(self) -> list[UUID]:
        stmt = select(GraphSpaceModel.id).order_by(GraphSpaceModel.id.asc())
        return [UUID(str(space_id)) for space_id in self._session.scalars(stmt).all()]

    def list_entries(self) -> list[KernelSpaceRegistryEntry]:
        stmt = select(GraphSpaceModel).order_by(GraphSpaceModel.id.asc())
        return [_to_entity(model) for model in self._session.scalars(stmt).all()]

    def save(
        self,
        entry: KernelSpaceRegistryEntry,
    ) -> KernelSpaceRegistryEntry:
        model = self._session.get(GraphSpaceModel, entry.id)
        if model is None:
            model = GraphSpaceModel(
                id=entry.id,
                slug=entry.slug,
                name=entry.name,
                description=entry.description,
                owner_id=entry.owner_id,
                status=GraphSpaceStatusEnum(entry.status),
                settings=_serialize_settings(entry.settings),
                sync_source=entry.sync_source,
                sync_fingerprint=entry.sync_fingerprint,
                source_updated_at=entry.source_updated_at,
                last_synced_at=entry.last_synced_at,
            )
            self._session.add(model)
        else:
            model.slug = entry.slug
            model.name = entry.name
            model.description = entry.description
            model.owner_id = entry.owner_id
            model.status = GraphSpaceStatusEnum(entry.status)
            model.settings = _serialize_settings(entry.settings)
            model.sync_source = entry.sync_source
            model.sync_fingerprint = entry.sync_fingerprint
            model.source_updated_at = entry.source_updated_at
            model.last_synced_at = entry.last_synced_at
        self._session.flush()
        return _to_entity(model)


__all__ = ["SqlAlchemyKernelSpaceRegistryRepository"]
