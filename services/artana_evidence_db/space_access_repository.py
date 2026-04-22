"""Service-local SQLAlchemy adapter for graph-space access resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_db.ports import SpaceAccessPort, SpaceRegistryPort
from artana_evidence_db.space_membership import MembershipRole
from artana_evidence_db.space_models import GraphSpaceMembershipModel
from artana_evidence_db.space_registry_repository import (
    SqlAlchemyKernelSpaceRegistryRepository,
)
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class SqlAlchemyKernelSpaceAccessRepository(SpaceAccessPort):
    """Resolve effective graph-space roles from graph registry plus memberships."""

    def __init__(
        self,
        session: Session,
        *,
        space_registry: SpaceRegistryPort | None = None,
    ) -> None:
        self._session = session
        self._space_registry = space_registry

    def get_effective_role(
        self,
        space_id: UUID,
        user_id: UUID,
    ) -> MembershipRole | None:
        registry = self._space_registry or SqlAlchemyKernelSpaceRegistryRepository(
            self._session,
        )
        space = registry.get_by_id(space_id)
        if space is None:
            return None
        if space.owner_id == user_id:
            return MembershipRole.OWNER

        membership_stmt = (
            select(GraphSpaceMembershipModel.role)
            .where(GraphSpaceMembershipModel.space_id == space_id)
            .where(GraphSpaceMembershipModel.user_id == user_id)
            .where(GraphSpaceMembershipModel.is_active == True)  # noqa: E712
        )
        membership_role = self._session.execute(membership_stmt).scalar_one_or_none()
        if membership_role is None:
            return None
        return MembershipRole(str(membership_role.value))


__all__ = ["SqlAlchemyKernelSpaceAccessRepository"]
