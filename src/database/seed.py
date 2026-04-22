"""Database seeding helpers for Artana Resource Library."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from secrets import token_urlsafe
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from sqlalchemy.sql.schema import Table

from src.database.seed_data import SOURCE_CATALOG_ENTRIES
from src.domain.entities.user import UserRole, UserStatus
from src.infrastructure.security.password_hasher import PasswordHasher
from src.models.database import (
    MembershipRoleEnum,
    ResearchSpaceMembershipModel,
    ResearchSpaceModel,
    SourceCatalogEntryModel,
    SpaceStatusEnum,
    SystemStatusModel,
    UserModel,
)
from src.type_definitions.system_status import MaintenanceModeState

logger = logging.getLogger(__name__)

SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
SYSTEM_USER_ID_STR = str(SYSTEM_USER_ID)
SYSTEM_USER_EMAIL = "system@artana.org"
SYSTEM_USER_USERNAME = "artana-system"
SYSTEM_USER_PASSWORD = os.getenv("ARTANA_SYSTEM_USER_PASSWORD")
SYSTEM_USER_FULL_NAME = "Artana System Automation"

DEFAULT_RESEARCH_SPACE_ID = UUID("560e9e0b-13bd-4337-a55d-2d3f650e451f")
DEFAULT_RESEARCH_SPACE_ID_STR = str(DEFAULT_RESEARCH_SPACE_ID)
DEFAULT_RESEARCH_SPACE_SLUG = "artana-core-space"
DEFAULT_RESEARCH_SPACE_NAME = "Artana Core Research Space"


def _ensure_system_user(session: Session) -> UserModel:
    """Ensure the deterministic system automation user exists."""
    password_hasher = PasswordHasher()

    system_user = (
        session.query(UserModel)
        .filter(UserModel.id == SYSTEM_USER_ID_STR)
        .one_or_none()
    )
    if system_user:
        return system_user

    # Attempt lookup by email (in case existing DB has user without deterministic ID)
    existing_by_email = (
        session.query(UserModel)
        .filter(UserModel.email == SYSTEM_USER_EMAIL)
        .one_or_none()
    )
    if existing_by_email:
        logger.info(
            "Aligning existing system user %s to deterministic ID %s",
            SYSTEM_USER_EMAIL,
            SYSTEM_USER_ID,
        )
        existing_by_email.id = SYSTEM_USER_ID_STR
        session.flush()
        return existing_by_email

    password_secret = SYSTEM_USER_PASSWORD or token_urlsafe(32)

    system_user = UserModel(
        id=SYSTEM_USER_ID_STR,
        email=SYSTEM_USER_EMAIL,
        username=SYSTEM_USER_USERNAME,
        full_name=SYSTEM_USER_FULL_NAME,
        hashed_password=password_hasher.hash_password(password_secret),
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        email_verified=True,
    )
    session.add(system_user)
    session.flush()
    logger.info("Seeded system automation user (%s)", SYSTEM_USER_EMAIL)
    return system_user


def ensure_default_research_space_seeded(session: Session) -> None:
    """Ensure the canonical Artana research space exists with deterministic IDs."""
    owner = _ensure_system_user(session)

    space = (
        session.query(ResearchSpaceModel)
        .filter(ResearchSpaceModel.id == DEFAULT_RESEARCH_SPACE_ID_STR)
        .one_or_none()
    )

    if not space:
        space = ResearchSpaceModel(
            id=DEFAULT_RESEARCH_SPACE_ID_STR,
            slug=DEFAULT_RESEARCH_SPACE_SLUG,
            name=DEFAULT_RESEARCH_SPACE_NAME,
            description=(
                "Primary workspace for Artana teams. Used as the default "
                "context when creating demo sessions or platform data sources."
            ),
            owner_id=owner.id,
            status=SpaceStatusEnum.ACTIVE,
            settings={
                "visibility": "private",
                "data_retention_days": 90,
                "auto_archive_days": 30,
            },
            tags=["artana", "core", "default"],
        )
        session.add(space)
        session.flush()
        logger.info(
            "Seeded default research space '%s' (%s)",
            DEFAULT_RESEARCH_SPACE_NAME,
            DEFAULT_RESEARCH_SPACE_ID,
        )

    membership = (
        session.query(ResearchSpaceMembershipModel)
        .filter(
            ResearchSpaceMembershipModel.space_id == DEFAULT_RESEARCH_SPACE_ID_STR,
            ResearchSpaceMembershipModel.user_id == owner.id,
        )
        .one_or_none()
    )

    if not membership:
        membership = ResearchSpaceMembershipModel(
            space_id=DEFAULT_RESEARCH_SPACE_ID_STR,
            user_id=owner.id,
            role=MembershipRoleEnum.OWNER,
            invited_by=owner.id,
            invited_at=datetime.now(UTC),
            joined_at=datetime.now(UTC),
            is_active=True,
        )
        session.add(membership)
        logger.info(
            "Linked system user %s to default research space as owner",
            SYSTEM_USER_EMAIL,
        )


def ensure_source_catalog_seeded(session: Session) -> None:
    """Ensure the source catalog has up-to-date demo entries."""
    existing_entries = {
        entry.id: entry for entry in session.query(SourceCatalogEntryModel).all()
    }

    inserted = 0
    updated = 0

    for entry_data in SOURCE_CATALOG_ENTRIES:
        entry_payload = dict(entry_data)
        entry_payload.setdefault("query_capabilities", {})
        entry_id = str(entry_payload["id"])
        model = existing_entries.get(entry_id)
        if model:
            for field, value in entry_payload.items():
                setattr(model, field, value)
            updated += 1
        else:
            session.add(SourceCatalogEntryModel(**entry_payload))
            inserted += 1

    logger.info(
        "Ensured %s source catalog entries (inserted=%s, updated=%s)",
        len(SOURCE_CATALOG_ENTRIES),
        inserted,
        updated,
    )


def ensure_system_status_initialized(session: Session) -> None:
    """Ensure maintenance mode state table & record exist."""
    bind = session.get_bind()
    system_status_table = SystemStatusModel.__table__
    if (
        bind is not None
        and system_status_table is not None
        and isinstance(system_status_table, Table)
    ):
        system_status_table.create(bind=bind, checkfirst=True)
    record = session.get(SystemStatusModel, "maintenance_mode")
    if record is None:
        session.add(
            SystemStatusModel(
                key="maintenance_mode",
                value=MaintenanceModeState().model_dump(mode="json"),
            ),
        )
        session.commit()
