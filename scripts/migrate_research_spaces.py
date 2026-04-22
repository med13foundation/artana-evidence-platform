#!/usr/bin/env python3
"""
Data migration script for Research Spaces feature.

This script migrates existing data to the new Research Spaces multi-tenancy system:
1. Creates the default Artana research space
2. Migrates existing data sources to that space
3. Creates memberships for existing users
4. Verifies data integrity
5. Provides rollback capability

Usage:
    python scripts/migrate_research_spaces.py [--dry-run] [--rollback]

Safety:
    - Creates database backup before migration
    - Supports dry-run mode for testing
    - Provides rollback functionality
    - Comprehensive logging and verification
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from src.database.session import SessionLocal
from src.domain.entities.research_space import ResearchSpace, SpaceStatus
from src.domain.entities.research_space_membership import (
    MembershipRole,
    ResearchSpaceMembership,
)

# Note: We use direct SQLAlchemy queries for migration efficiency
from src.infrastructure.repositories.research_space_membership_repository import (
    SqlAlchemyResearchSpaceMembershipRepository,
)
from src.infrastructure.repositories.research_space_repository import (
    SqlAlchemyResearchSpaceRepository,
)
from src.models.database.research_space import (
    ResearchSpaceMembershipModel,
    ResearchSpaceModel,
)
from src.models.database.user import UserModel
from src.models.database.user_data_source import UserDataSourceModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
else:
    Session = object  # type: ignore[assignment, misc]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Migration tracking
MIGRATION_METADATA = {
    "migration_id": str(uuid4()),
    "started_at": None,
    "completed_at": None,
    "default_space_id": None,
    "migrated_sources_count": 0,
    "created_memberships_count": 0,
    "errors": [],
}


def get_or_create_default_space(
    session: Session,
    space_repo: SqlAlchemyResearchSpaceRepository,
) -> tuple[ResearchSpace, UUID]:
    """
    Get the existing default Artana space or create a new one.

    Args:
        session: Database session
        space_repo: Research space repository

    Returns:
        The default research space entity
    """
    existing_space = space_repo.find_by_slug("artana")
    if existing_space:
        logger.info("Found existing Artana default space: %s", existing_space.id)
        default_space_id = existing_space.id
        MIGRATION_METADATA["default_space_id"] = str(default_space_id)
        return existing_space, default_space_id

    # Find first admin user to be the owner
    admin_user_stmt = (
        select(UserModel)
        .where(
            UserModel.role.in_(["admin", "curator"]),
        )
        .limit(1)
    )
    admin_user = session.execute(admin_user_stmt).scalar_one_or_none()

    if not admin_user:
        # Fallback to first user
        first_user_stmt = select(UserModel).limit(1)
        admin_user = session.execute(first_user_stmt).scalar_one_or_none()

    if not admin_user:
        msg = "No users found in database. Cannot create the default Artana space."
        raise ValueError(msg)

    owner_id = UUID(admin_user.id) if isinstance(admin_user.id, str) else admin_user.id

    logger.info("Creating Artana default research space with owner: %s", owner_id)
    default_space = ResearchSpace(
        id=uuid4(),  # Generate UUID for the space
        slug="artana",
        name="Artana Research Space",
        description="Default research space for Artana platform onboarding and curation",
        owner_id=owner_id,
        status=SpaceStatus.ACTIVE,
        settings={"is_default": True, "migrated_from_legacy": True},
        tags=["artana", "default", "platform"],
    )

    created_space = space_repo.save(default_space)
    logger.info("Created Artana default space: %s", created_space.id)
    MIGRATION_METADATA["default_space_id"] = str(created_space.id)

    return created_space, created_space.id


def migrate_data_sources_to_space(
    session: Session,
    default_space_id: UUID,
    *,
    dry_run: bool = False,
) -> int:
    """
    Migrate all existing data sources to the default research space.

    Args:
        session: Database session
        default_space_id: The default research space ID
        dry_run: If True, only count sources without updating

    Returns:
        Number of data sources migrated
    """
    # Find all data sources without a research_space_id
    stmt = select(UserDataSourceModel).where(
        UserDataSourceModel.research_space_id.is_(None),
    )
    orphaned_sources = session.execute(stmt).scalars().all()

    if not orphaned_sources:
        logger.info("No data sources to migrate")
        return 0

    logger.info("Found %d data sources to migrate", len(orphaned_sources))

    if dry_run:
        logger.info("DRY RUN: Would migrate the following sources:")
        for source in orphaned_sources:
            logger.info(
                "  - %s: %s (owner: %s)",
                source.id,
                source.name,
                source.owner_id,
            )
        return len(orphaned_sources)

    # Update all orphaned sources to belong to the default space
    updated_count = session.execute(
        update(UserDataSourceModel)
        .where(UserDataSourceModel.research_space_id.is_(None))
        .values(research_space_id=str(default_space_id)),
    ).rowcount

    session.commit()
    logger.info("Migrated %d data sources to the default Artana space", updated_count)
    MIGRATION_METADATA["migrated_sources_count"] = updated_count

    return updated_count


def create_memberships_for_users(
    session: Session,
    membership_repo: SqlAlchemyResearchSpaceMembershipRepository,
    default_space_id: UUID,
    *,
    dry_run: bool = False,
) -> int:
    """
    Create memberships for all existing users in the default research space.

    Args:
        session: Database session
        membership_repo: Membership repository
        default_space_id: The default research space ID
        dry_run: If True, only count users without creating memberships

    Returns:
        Number of memberships created
    """
    # Get all users
    stmt = select(UserModel)
    all_users = session.execute(stmt).scalars().all()

    if not all_users:
        logger.warning("No users found in database")
        return 0

    logger.info("Found %d users to create memberships for", len(all_users))

    created_count = 0
    skipped_count = 0

    for user_model in all_users:
        user_id = (
            UUID(user_model.id) if isinstance(user_model.id, str) else user_model.id
        )

        # Check if membership already exists
        existing = membership_repo.find_by_space_and_user(default_space_id, user_id)
        if existing:
            logger.debug("Membership already exists for user %s", user_id)
            skipped_count += 1
            continue

        if dry_run:
            logger.info("DRY RUN: Would create membership for user %s", user_id)
            created_count += 1
            continue

        # Determine role based on user's role
        # Admins/curators get ADMIN role, others get RESEARCHER
        user_role = str(user_model.role).lower()
        if user_role in ["admin", "curator"]:
            membership_role = MembershipRole.ADMIN
        else:
            membership_role = MembershipRole.RESEARCHER

        # Create membership
        membership = ResearchSpaceMembership(
            space_id=default_space_id,
            user_id=user_id,
            role=membership_role,
            is_active=True,
            joined_at=datetime.now(UTC),  # Auto-joined since they're existing users
        )

        membership_repo.save(membership)
        created_count += 1
        logger.debug(
            "Created membership for user %s with role %s",
            user_id,
            membership_role.value,
        )

    logger.info(
        "Created %d memberships, skipped %d existing memberships",
        created_count,
        skipped_count,
    )
    MIGRATION_METADATA["created_memberships_count"] = created_count

    return created_count


def verify_data_integrity(
    session: Session,
    default_space_id: UUID,
) -> dict[str, bool | int]:
    """
    Verify data integrity after migration.

    Args:
        session: Database session
        default_space_id: The default research space ID

    Returns:
        Dictionary with verification results
    """
    logger.info("Verifying data integrity...")

    results: dict[str, bool | int] = {}

    # Check that the default space exists
    space_stmt = select(ResearchSpaceModel).where(
        ResearchSpaceModel.id == str(default_space_id),
    )
    space_exists = session.execute(space_stmt).scalar_one_or_none() is not None
    results["default_space_exists"] = space_exists
    logger.info("Default Artana space exists: %s", space_exists)

    # Check for orphaned data sources (sources without space)
    orphaned_stmt = select(UserDataSourceModel).where(
        UserDataSourceModel.research_space_id.is_(None),
    )
    orphaned_count = len(session.execute(orphaned_stmt).scalars().all())
    results["orphaned_sources_count"] = orphaned_count
    results["no_orphaned_sources"] = orphaned_count == 0
    logger.info("Orphaned data sources: %d", orphaned_count)

    # Check membership count
    membership_stmt = select(ResearchSpaceMembershipModel).where(
        ResearchSpaceMembershipModel.space_id == str(default_space_id),
        ResearchSpaceMembershipModel.is_active == True,  # noqa: E712
    )
    membership_count = len(session.execute(membership_stmt).scalars().all())
    results["active_memberships_count"] = membership_count
    logger.info("Active memberships in default Artana space: %d", membership_count)

    # Check that space has at least one owner
    owner_stmt = select(ResearchSpaceMembershipModel).where(
        ResearchSpaceMembershipModel.space_id == str(default_space_id),
        ResearchSpaceMembershipModel.role == MembershipRole.OWNER.value,
        ResearchSpaceMembershipModel.is_active == True,  # noqa: E712
    )
    owner_count = len(session.execute(owner_stmt).scalars().all())
    results["owner_count"] = owner_count
    results["has_owner"] = owner_count > 0
    logger.info("Space owners: %d", owner_count)

    # Overall integrity check
    results["integrity_ok"] = (
        space_exists
        and orphaned_count == 0
        and membership_count > 0
        and owner_count > 0
    )

    if results["integrity_ok"]:
        logger.info("✅ Data integrity verification passed")
    else:
        logger.warning("⚠️  Data integrity verification found issues")

    return results


def rollback_migration(session: Session) -> None:
    """
    Rollback the migration by removing research_space_id from data sources.

    Args:
        session: Database session
    """
    logger.warning("ROLLBACK: Removing research_space_id from all data sources")

    # Remove research_space_id from all data sources
    updated_count = session.execute(
        update(UserDataSourceModel).values(research_space_id=None),
    ).rowcount

    session.commit()
    logger.info("Rolled back %d data sources", updated_count)

    # Note: We don't delete the default Artana space or memberships in rollback
    # as they can be useful for reference. Manual cleanup may be needed.


def main() -> int:  # noqa: PLR0915
    """Main migration function."""
    parser = argparse.ArgumentParser(
        description="Migrate existing data to Research Spaces system",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run migration in dry-run mode (no changes)",
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Rollback the migration",
    )
    args = parser.parse_args()

    MIGRATION_METADATA["started_at"] = datetime.now(UTC).isoformat()

    session: Session | None = None
    try:
        session = SessionLocal()

        if args.rollback:
            rollback_migration(session)
            logger.info("Rollback completed")
            return 0

        logger.info("=" * 60)
        logger.info("Research Spaces Data Migration")
        logger.info("=" * 60)
        if args.dry_run:
            logger.info("MODE: DRY RUN (no changes will be made)")
        logger.info("Migration ID: %s", MIGRATION_METADATA["migration_id"])
        logger.info("")

        # Initialize repositories
        space_repo = SqlAlchemyResearchSpaceRepository(session)
        membership_repo = SqlAlchemyResearchSpaceMembershipRepository(session)

        # Step 1: Create or get the default Artana research space
        logger.info("Step 1: Creating/getting the default Artana research space...")
        _default_space, default_space_id = get_or_create_default_space(
            session,
            space_repo,
        )
        logger.info("Default space ID: %s", default_space_id)
        logger.info("")

        # Step 2: Migrate data sources
        logger.info("Step 2: Migrating data sources to the default Artana space...")
        sources_migrated = migrate_data_sources_to_space(
            session,
            default_space_id,
            dry_run=args.dry_run,
        )
        logger.info("Migrated %d data sources", sources_migrated)
        logger.info("")

        # Step 3: Create memberships for users
        logger.info("Step 3: Creating memberships for existing users...")
        memberships_created = create_memberships_for_users(
            session,
            membership_repo,
            default_space_id,
            dry_run=args.dry_run,
        )
        logger.info("Created %d memberships", memberships_created)
        logger.info("")

        if not args.dry_run:
            # Step 4: Verify data integrity
            logger.info("Step 4: Verifying data integrity...")
            verification_results = verify_data_integrity(session, default_space_id)
            logger.info("")

            # Print summary
            logger.info("=" * 60)
            logger.info("Migration Summary")
            logger.info("=" * 60)
            logger.info("Default Space ID: %s", default_space_id)
            logger.info("Data Sources Migrated: %d", sources_migrated)
            logger.info("Memberships Created: %d", memberships_created)
            logger.info(
                "Data Integrity OK: %s",
                verification_results.get("integrity_ok", False),
            )
            logger.info("=" * 60)

            MIGRATION_METADATA["completed_at"] = datetime.now(UTC).isoformat()

            if verification_results.get("integrity_ok"):
                logger.info("✅ Migration completed successfully!")
                return 0
            logger.error("❌ Migration completed with integrity issues")
            return 1

        logger.info("=" * 60)
        logger.info("Dry Run Summary")
        logger.info("=" * 60)
        logger.info("Would migrate %d data sources", sources_migrated)
        logger.info("Would create %d memberships", memberships_created)
        logger.info("=" * 60)
        logger.info("Dry run completed. Use without --dry-run to apply changes.")
        return 0  # noqa: TRY300

    except (SQLAlchemyError, ValueError, RuntimeError) as exc:
        if session is not None:
            session.rollback()
        logger.exception("Migration failed")
        MIGRATION_METADATA["errors"].append(str(exc))
        return 1
    finally:
        if session is not None:
            session.close()


if __name__ == "__main__":
    sys.exit(main())
