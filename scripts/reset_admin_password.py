#!/usr/bin/env python3
"""Reset admin user password for Artana Resource Library.

This script resets the password for the admin user, useful when
the password is forgotten or needs to be reset.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Add project root to path before importing project modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.exc import SQLAlchemyError

from src.database.session import SessionLocal
from src.infrastructure.security.password_hasher import PasswordHasher
from src.models.database.user import UserModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


MIN_ADMIN_PASSWORD_LENGTH = 12
ADMIN_PASSWORD_ENV_VAR = (
    "ARTANA_ADMIN_PASSWORD"  # noqa: S105 - env var name, not a credential
)


def _resolve_password(explicit: str | None) -> str:
    """Resolve secure password input."""
    candidate = explicit or os.getenv(ADMIN_PASSWORD_ENV_VAR)
    if not candidate:
        message = (
            "New admin password required. Pass --password or set "
            f"{ADMIN_PASSWORD_ENV_VAR}."
        )
        raise ValueError(message)
    if len(candidate) < MIN_ADMIN_PASSWORD_LENGTH:
        message = (
            "Admin password must be at least "
            f"{MIN_ADMIN_PASSWORD_LENGTH} characters."
        )
        raise ValueError(message)
    return candidate


def reset_admin_password(
    email: str = "admin@artana.org",
    password: str | None = None,
) -> bool:
    """
    Reset password for admin user.

    Args:
        email: Admin email address
        password: New password (will be hashed)

    Returns:
        True if password was reset, False if user not found
    """
    session = SessionLocal()
    password_hasher = PasswordHasher()
    resolved_password = _resolve_password(password)

    try:
        # Find admin user
        admin = session.query(UserModel).filter(UserModel.email == email).first()

        if not admin:
            logger.error("Admin user with email %s not found!", email)
            logger.info("Run 'make db-seed-admin' to create the admin user.")
            return False

        # Reset password
        admin.hashed_password = password_hasher.hash_password(resolved_password)
        session.commit()

        logger.info("✅ Admin password reset successfully!")
        logger.info("   Email: %s", email)
        logger.info("   Username: %s", admin.username)
        logger.warning("   Password provided via CLI/env (not logged).")
        logger.warning("   ⚠️  Rotate the password after first login!")

    except SQLAlchemyError:
        session.rollback()
        logger.exception("Failed to reset admin password")
        raise
    else:
        return True
    finally:
        session.close()


def verify_admin_user(email: str = "admin@artana.org") -> bool:
    """
    Verify admin user exists and show details.

    Args:
        email: Admin email address

    Returns:
        True if user exists, False otherwise
    """
    session = SessionLocal()

    try:
        admin = session.query(UserModel).filter(UserModel.email == email).first()

        if not admin:
            logger.error("Admin user with email %s not found!", email)
            logger.info("Run 'make db-seed-admin' to create the admin user.")
            return False

        logger.info("✅ Admin user found!")
        logger.info("   Email: %s", admin.email)
        logger.info("   Username: %s", admin.username)
        logger.info("   Full Name: %s", admin.full_name)
        logger.info("   Role: %s", admin.role)
        logger.info("   Status: %s", admin.status)
        logger.info("   Email Verified: %s", admin.email_verified)

    except SQLAlchemyError:
        logger.exception("Failed to verify admin user")
        raise
    else:
        return True
    finally:
        session.close()


def main() -> None:
    """Main entry point for password reset."""
    parser = argparse.ArgumentParser(
        description="Reset admin user password for Artana Resource Library",
    )
    parser.add_argument(
        "--email",
        default="admin@artana.org",
        help="Admin email address (default: admin@artana.org)",
    )
    parser.add_argument(
        "--password",
        help=(
            "New password (required unless ARTANA_ADMIN_PASSWORD environment "
            "variable is set)"
        ),
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify admin user exists, don't reset password",
    )

    args = parser.parse_args()

    try:
        if args.verify_only:
            success = verify_admin_user(email=args.email)
        else:
            password = _resolve_password(args.password)
            success = reset_admin_password(email=args.email, password=password)

        if not success:
            sys.exit(1)

    except (SQLAlchemyError, ValueError, RuntimeError):
        logger.exception("Failed to reset admin password")
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover - script entrypoint
    main()
