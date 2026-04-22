#!/usr/bin/env python3
"""Seed admin user and test users for Artana Resource Library.

Creates a default admin user for initial system access and optionally
creates multiple test users for testing research spaces and memberships.
Run this script after database migrations to create the first admin account.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

# Add project root to path before importing project modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "services"))

from sqlalchemy.exc import SQLAlchemyError

from services.artana_evidence_api.sqlalchemy_stores import (
    SqlAlchemyHarnessResearchSpaceStore,
)
from src.database.session import SessionLocal
from src.domain.entities.user import UserRole, UserStatus
from src.infrastructure.security.password_hasher import PasswordHasher
from src.models.database.user import UserModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


MIN_ADMIN_PASSWORD_LENGTH = 12
ADMIN_PASSWORD_ENV_VAR = (
    "ARTANA_ADMIN_PASSWORD"  # noqa: S105 - env var name, not a credential
)


def _resolve_admin_password(explicit: str | None) -> str:
    """Resolve admin password from CLI flag or environment."""
    candidate = explicit or os.getenv(ADMIN_PASSWORD_ENV_VAR)
    if not candidate:
        message = (
            "Admin password required. Pass --password or set "
            f"{ADMIN_PASSWORD_ENV_VAR}."
        )
        raise ValueError(message)
    if len(candidate) < MIN_ADMIN_PASSWORD_LENGTH:
        message = (
            "Admin password must be at least "
            f"{MIN_ADMIN_PASSWORD_LENGTH} characters long."
        )
        raise ValueError(message)
    return candidate


def create_admin_user(
    email: str = "admin@artana.org",
    username: str = "admin",
    password: str | None = None,
    full_name: str = "Artana Administrator",
) -> None:
    """
    Create an admin user in the database.

    Args:
        email: Admin email address
        username: Admin username
        password: Admin password (will be hashed)
        full_name: Admin full name
    """
    session = SessionLocal()
    password_hasher = PasswordHasher()
    resolved_password = _resolve_admin_password(password)
    resolved_password_hash = password_hasher.hash_password(resolved_password)

    try:
        # Reconcile an existing account into the local admin user.
        existing = session.query(UserModel).filter(UserModel.email == email).first()

        if existing:
            existing.role = UserRole.ADMIN
            existing.status = UserStatus.ACTIVE
            existing.email_verified = True
            existing.hashed_password = resolved_password_hash
            existing.login_attempts = 0
            existing.locked_until = None
            existing.email_verification_token = None
            existing.password_reset_token = None
            existing.password_reset_expires = None
            if username.strip():
                existing.username = username
            if full_name.strip():
                existing.full_name = full_name
            session.commit()
            _ensure_personal_default_space(
                session=session,
                user=existing,
            )
            logger.info("✅ Admin user reconciled successfully!")
            logger.info("   Email: %s", email)
            logger.info("   Existing account upgraded to active admin.")
            logger.info("   Cleared login lockouts and reset pending auth tokens.")
            logger.warning("   Password provided via CLI/env (not logged).")
            return

        # Create admin user
        admin = UserModel(
            email=email,
            username=username,
            full_name=full_name,
            hashed_password=resolved_password_hash,
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            email_verified=True,
        )

        session.add(admin)
        session.commit()
        _ensure_personal_default_space(
            session=session,
            user=admin,
        )

        logger.info("✅ Admin user created successfully!")
        logger.info("   Email: %s", email)
        logger.info("   Username: %s", username)
        logger.warning("   Password provided via CLI/env (not logged).")
        logger.warning("   ⚠️  Rotate the password after first login!")

    except SQLAlchemyError:
        session.rollback()
        logger.exception("Failed to create admin user")
        raise
    finally:
        session.close()


def _ensure_personal_default_space(*, session: Session, user: UserModel) -> None:
    """Ensure the seeded admin has one usable personal default space."""
    store = SqlAlchemyHarnessResearchSpaceStore(session=session)
    record = store.ensure_default_space(
        owner_id=user.id,
        owner_email=user.email,
        owner_username=user.username,
        owner_full_name=user.full_name,
        owner_role=user.role.value,
        owner_status=user.status.value,
    )
    logger.info("   Default space ready: %s (%s)", record.name, record.id)


def create_test_users(
    count: int = 5,
    password: str = "test1234",
    base_email: str = "testuser",
    base_username: str = "testuser",
) -> int:
    """
    Create multiple test users for testing research spaces.

    Args:
        count: Number of test users to create (default: 5)
        password: Password for all test users (default: test123)
        base_email: Base email prefix (default: testuser)
        base_username: Base username prefix (default: testuser)

    Returns:
        Number of users created successfully
    """
    session = SessionLocal()
    password_hasher = PasswordHasher()

    # Test user templates with different roles
    test_user_templates = [
        {"role": UserRole.CURATOR, "name": "Curator"},
        {"role": UserRole.RESEARCHER, "name": "Researcher"},
        {"role": UserRole.RESEARCHER, "name": "Researcher"},
        {"role": UserRole.VIEWER, "name": "Viewer"},
        {"role": UserRole.VIEWER, "name": "Viewer"},
    ]

    created_count = 0
    skipped_count = 0

    try:
        for i in range(count):
            # Cycle through templates if count > templates length
            template = test_user_templates[i % len(test_user_templates)]
            role = template["role"]
            role_name = template["name"]

            # Generate user data
            user_num = i + 1
            email = f"{base_email}{user_num}@artana.org"
            username = f"{base_username}{user_num}"
            full_name = f"Test {role_name} {user_num}"

            # Check if user already exists
            existing = session.query(UserModel).filter(UserModel.email == email).first()

            if existing:
                logger.debug("User with email %s already exists, skipping", email)
                skipped_count += 1
                continue

            # Create test user
            test_user = UserModel(
                email=email,
                username=username,
                full_name=full_name,
                hashed_password=password_hasher.hash_password(password),
                role=role,
                status=UserStatus.ACTIVE,
                email_verified=True,
            )

            session.add(test_user)
            created_count += 1
            logger.info(
                "Created test user: %s (%s) - Role: %s",
                username,
                email,
                role.value,
            )

        session.commit()
        logger.info("✅ Created %d test users", created_count)
        if skipped_count > 0:
            logger.info("Skipped %d existing users", skipped_count)
        logger.info("   Password for all test users: %s", password)
        logger.warning(
            "   ⚠️  These are test users - change passwords in production!",
        )

        return created_count  # noqa: TRY300
    except SQLAlchemyError:
        session.rollback()
        logger.exception("Failed to create test users")
        raise
    finally:
        session.close()


def main() -> None:
    """Main entry point for user seeding."""
    parser = argparse.ArgumentParser(
        description="Create admin and test users for Artana Resource Library",
    )
    parser.add_argument(
        "--email",
        default="admin@artana.org",
        help="Admin email address (default: admin@artana.org)",
    )
    parser.add_argument(
        "--username",
        default="admin",
        help="Admin username (default: admin)",
    )
    parser.add_argument(
        "--password",
        help=(
            "Admin password (required unless ARTANA_ADMIN_PASSWORD environment "
            "variable is set)"
        ),
    )
    parser.add_argument(
        "--full-name",
        default="Artana Administrator",
        help="Admin full name (default: Artana Administrator)",
    )
    parser.add_argument(
        "--create-test-users",
        action="store_true",
        help="Create test users for testing research spaces",
    )
    parser.add_argument(
        "--test-user-count",
        type=int,
        default=5,
        help="Number of test users to create (default: 5)",
    )
    parser.add_argument(
        "--test-password",
        default="test1234",
        help="Password for test users (default: test1234)",
    )
    parser.add_argument(
        "--skip-admin",
        action="store_true",
        help="Skip creating admin user (only create test users)",
    )

    args = parser.parse_args()

    try:
        # Create admin user unless skipped
        if not args.skip_admin:
            logger.info("Creating admin user...")
            create_admin_user(
                email=args.email,
                username=args.username,
                password=args.password,
                full_name=args.full_name,
            )
            logger.info("")

        # Create test users if requested
        if args.create_test_users:
            logger.info("Creating test users...")
            created = create_test_users(
                count=args.test_user_count,
                password=args.test_password,
            )
            logger.info("")
            logger.info("Summary:")
            logger.info("  Test users created: %d", created)
            logger.info("  Test user password: %s", args.test_password)
            logger.info("  Test users can be used for research space testing")

    except (SQLAlchemyError, ValueError, RuntimeError):
        logger.exception("Failed to seed users")
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover - script entrypoint
    main()
