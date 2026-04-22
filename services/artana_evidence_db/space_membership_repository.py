"""Service-local SQLAlchemy adapter for graph-owned space memberships."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_db.space_membership import MembershipRole, ResearchSpaceMembership
from artana_evidence_db.space_models import (
    GraphSpaceMembershipModel,
    GraphSpaceMembershipRoleEnum,
)
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _to_entity(model: GraphSpaceMembershipModel) -> ResearchSpaceMembership:
    return ResearchSpaceMembership(
        id=UUID(str(model.id)),
        space_id=UUID(str(model.space_id)),
        user_id=UUID(str(model.user_id)),
        role=MembershipRole(str(model.role.value)),
        invited_by=(
            UUID(str(model.invited_by)) if model.invited_by is not None else None
        ),
        invited_at=model.invited_at,
        joined_at=model.joined_at,
        is_active=bool(model.is_active),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlAlchemyKernelSpaceMembershipRepository:
    """Manage graph-owned space membership rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_space(
        self,
        space_id: UUID,
    ) -> list[ResearchSpaceMembership]:
        stmt = (
            select(GraphSpaceMembershipModel)
            .where(GraphSpaceMembershipModel.space_id == space_id)
            .order_by(GraphSpaceMembershipModel.user_id.asc())
        )
        return [_to_entity(model) for model in self._session.scalars(stmt).all()]

    def get_for_space_user(
        self,
        *,
        space_id: UUID,
        user_id: UUID,
    ) -> ResearchSpaceMembership | None:
        stmt = (
            select(GraphSpaceMembershipModel)
            .where(GraphSpaceMembershipModel.space_id == space_id)
            .where(GraphSpaceMembershipModel.user_id == user_id)
        )
        model = self._session.execute(stmt).scalar_one_or_none()
        if model is None:
            return None
        return _to_entity(model)

    def save(
        self,
        membership: ResearchSpaceMembership,
    ) -> ResearchSpaceMembership:
        stmt = (
            select(GraphSpaceMembershipModel)
            .where(GraphSpaceMembershipModel.space_id == membership.space_id)
            .where(GraphSpaceMembershipModel.user_id == membership.user_id)
        )
        model = self._session.execute(stmt).scalar_one_or_none()
        if model is None:
            model = GraphSpaceMembershipModel(
                id=membership.id,
                space_id=membership.space_id,
                user_id=membership.user_id,
                role=GraphSpaceMembershipRoleEnum(membership.role.value),
                invited_by=membership.invited_by,
                invited_at=membership.invited_at,
                joined_at=membership.joined_at,
                is_active=membership.is_active,
            )
            self._session.add(model)
        else:
            model.role = GraphSpaceMembershipRoleEnum(membership.role.value)
            model.invited_by = membership.invited_by
            model.invited_at = membership.invited_at
            model.joined_at = membership.joined_at
            model.is_active = membership.is_active
        self._session.flush()
        return _to_entity(model)

    def replace_for_space(
        self,
        *,
        space_id: UUID,
        memberships: list[ResearchSpaceMembership],
    ) -> list[ResearchSpaceMembership]:
        """Replace one space membership set with the supplied graph-owned snapshot."""
        existing_stmt = select(GraphSpaceMembershipModel).where(
            GraphSpaceMembershipModel.space_id == space_id,
        )
        existing_models = {
            UUID(str(model.user_id)): model
            for model in self._session.scalars(existing_stmt).all()
        }

        desired_user_ids = {membership.user_id for membership in memberships}
        now = datetime.now(UTC)

        for membership in memberships:
            model = existing_models.get(membership.user_id)
            if model is None:
                model = GraphSpaceMembershipModel(
                    id=membership.id,
                    space_id=membership.space_id,
                    user_id=membership.user_id,
                    role=GraphSpaceMembershipRoleEnum(membership.role.value),
                    invited_by=membership.invited_by,
                    invited_at=membership.invited_at,
                    joined_at=membership.joined_at,
                    is_active=membership.is_active,
                )
                self._session.add(model)
                existing_models[membership.user_id] = model
                continue

            model.role = GraphSpaceMembershipRoleEnum(membership.role.value)
            model.invited_by = membership.invited_by
            model.invited_at = membership.invited_at
            model.joined_at = membership.joined_at
            model.is_active = membership.is_active
            model.updated_at = now

        for user_id, model in existing_models.items():
            if user_id in desired_user_ids:
                continue
            model.is_active = False
            model.updated_at = now

        self._session.flush()
        return self.list_for_space(space_id)


__all__ = ["SqlAlchemyKernelSpaceMembershipRepository"]
