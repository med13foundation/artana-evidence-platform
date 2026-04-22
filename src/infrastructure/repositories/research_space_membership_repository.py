"""
SQLAlchemy implementation of Research Space Membership repository for Artana Resource Library.

Data access layer for research space memberships with specialized queries
and efficient database operations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import and_, delete, desc, func, select, update

from src.domain.entities.research_space_membership import (
    MembershipRole,  # noqa: TC001 - Used at runtime
    ResearchSpaceMembership,  # noqa: TC001 - Used at runtime
)
from src.domain.repositories.research_space_repository import (
    ResearchSpaceMembershipRepository as ResearchSpaceMembershipRepositoryInterface,
)
from src.infrastructure.mappers.research_space_membership_mapper import (
    ResearchSpaceMembershipMapper,
)
from src.models.database.research_space import ResearchSpaceMembershipModel

if TYPE_CHECKING:  # pragma: no cover - typing only
    from uuid import UUID

    from sqlalchemy.orm import Session


class SqlAlchemyResearchSpaceMembershipRepository(
    ResearchSpaceMembershipRepositoryInterface,
):
    """
    Repository for ResearchSpaceMembership entities with specialized membership queries.

    Provides data access operations for research space memberships including
    role-based filtering, invitation workflows, and membership management.
    """

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        """Get the current database session."""
        if self._session is None:
            message = "Session not provided"
            raise ValueError(message)
        return self._session

    def save(self, membership: ResearchSpaceMembership) -> ResearchSpaceMembership:
        """Save a membership to the repository."""
        model = ResearchSpaceMembershipMapper.to_model(membership)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        domain_membership = ResearchSpaceMembershipMapper.to_domain(model)
        if domain_membership is None:
            message = "Failed to convert model to domain entity"
            raise ValueError(message)
        return domain_membership

    def find_by_id(
        self,
        membership_id: UUID,
    ) -> ResearchSpaceMembership | None:
        """Find a membership by its ID."""
        stmt = select(ResearchSpaceMembershipModel).where(
            ResearchSpaceMembershipModel.id == membership_id,
        )
        result = self.session.execute(stmt).scalar_one_or_none()
        return ResearchSpaceMembershipMapper.to_domain(result) if result else None

    def find_by_space(
        self,
        space_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpaceMembership]:
        """Find all memberships for a research space."""
        stmt = (
            select(ResearchSpaceMembershipModel)
            .where(ResearchSpaceMembershipModel.space_id == space_id)
            .where(ResearchSpaceMembershipModel.is_active == True)  # noqa: E712
            .order_by(desc(ResearchSpaceMembershipModel.created_at))
            .offset(skip)
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [
            domain_membership
            for model in results
            if (domain_membership := ResearchSpaceMembershipMapper.to_domain(model))
            is not None
        ]

    def find_by_user(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpaceMembership]:
        """Find all memberships for a user."""
        stmt = (
            select(ResearchSpaceMembershipModel)
            .where(ResearchSpaceMembershipModel.user_id == user_id)
            .where(ResearchSpaceMembershipModel.is_active == True)  # noqa: E712
            .order_by(desc(ResearchSpaceMembershipModel.created_at))
            .offset(skip)
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [
            domain_membership
            for model in results
            if (domain_membership := ResearchSpaceMembershipMapper.to_domain(model))
            is not None
        ]

    def find_by_space_and_user(
        self,
        space_id: UUID,
        user_id: UUID,
    ) -> ResearchSpaceMembership | None:
        """Find membership for a specific space and user."""
        stmt = select(ResearchSpaceMembershipModel).where(
            and_(
                ResearchSpaceMembershipModel.space_id == space_id,
                ResearchSpaceMembershipModel.user_id == user_id,
            ),
        )
        result = self.session.execute(stmt).scalar_one_or_none()
        return ResearchSpaceMembershipMapper.to_domain(result) if result else None

    def find_pending_invitations(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpaceMembership]:
        """Find pending invitations for a user."""
        stmt = (
            select(ResearchSpaceMembershipModel)
            .where(ResearchSpaceMembershipModel.user_id == user_id)
            .where(ResearchSpaceMembershipModel.invited_at.isnot(None))
            .where(ResearchSpaceMembershipModel.joined_at.is_(None))
            .order_by(desc(ResearchSpaceMembershipModel.invited_at))
            .offset(skip)
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [
            domain_membership
            for model in results
            if (domain_membership := ResearchSpaceMembershipMapper.to_domain(model))
            is not None
        ]

    def find_by_role(
        self,
        space_id: UUID,
        role: MembershipRole,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpaceMembership]:
        """Find memberships with a specific role in a space."""
        stmt = (
            select(ResearchSpaceMembershipModel)
            .where(
                and_(
                    ResearchSpaceMembershipModel.space_id == space_id,
                    ResearchSpaceMembershipModel.role == role.value,
                    ResearchSpaceMembershipModel.is_active == True,  # noqa: E712
                ),
            )
            .order_by(desc(ResearchSpaceMembershipModel.created_at))
            .offset(skip)
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [
            domain_membership
            for model in results
            if (domain_membership := ResearchSpaceMembershipMapper.to_domain(model))
            is not None
        ]

    def update_role(
        self,
        membership_id: UUID,
        role: MembershipRole,
    ) -> ResearchSpaceMembership | None:
        """Update the role of a membership."""
        stmt = (
            update(ResearchSpaceMembershipModel)
            .where(ResearchSpaceMembershipModel.id == membership_id)
            .values(role=role.value)
            .returning(ResearchSpaceMembershipModel)
        )
        result = self.session.execute(stmt).scalar_one_or_none()
        if result:
            self.session.commit()
            return ResearchSpaceMembershipMapper.to_domain(result)
        return None

    def accept_invitation(
        self,
        membership_id: UUID,
    ) -> ResearchSpaceMembership | None:
        """Accept a pending invitation."""
        now = datetime.now(UTC)
        stmt = (
            update(ResearchSpaceMembershipModel)
            .where(ResearchSpaceMembershipModel.id == membership_id)
            .values(joined_at=now, is_active=True)
            .returning(ResearchSpaceMembershipModel)
        )
        result = self.session.execute(stmt).scalar_one_or_none()
        if result:
            self.session.commit()
            return ResearchSpaceMembershipMapper.to_domain(result)
        return None

    def delete(self, membership_id: UUID) -> bool:
        """Delete a membership from the repository."""
        stmt = delete(ResearchSpaceMembershipModel).where(
            ResearchSpaceMembershipModel.id == membership_id,
        )
        result = self.session.execute(stmt)
        self.session.commit()
        affected = result.rowcount if hasattr(result, "rowcount") else 0
        return affected > 0

    def exists(self, membership_id: UUID) -> bool:
        """Check if a membership exists."""
        stmt = select(func.count()).where(
            ResearchSpaceMembershipModel.id == membership_id,
        )
        count = self.session.execute(stmt).scalar_one()
        return int(count) > 0

    def count_by_space(self, space_id: UUID) -> int:
        """Count active members in a research space."""
        stmt = select(func.count()).where(
            and_(
                ResearchSpaceMembershipModel.space_id == space_id,
                ResearchSpaceMembershipModel.is_active == True,  # noqa: E712
            ),
        )
        return self.session.execute(stmt).scalar_one()

    def is_user_member(self, space_id: UUID, user_id: UUID) -> bool:
        """Check if a user is a member of a research space."""
        stmt = select(func.count()).where(
            and_(
                ResearchSpaceMembershipModel.space_id == space_id,
                ResearchSpaceMembershipModel.user_id == user_id,
                ResearchSpaceMembershipModel.is_active == True,  # noqa: E712
            ),
        )
        count = self.session.execute(stmt).scalar_one()
        return int(count) > 0

    def get_user_role(
        self,
        space_id: UUID,
        user_id: UUID,
    ) -> MembershipRole | None:
        """Get user's role in a research space."""
        membership = self.find_by_space_and_user(space_id, user_id)
        return membership.role if membership else None
