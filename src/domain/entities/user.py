"""
User entity for Artana Resource Library authentication system.

Implements domain-driven design with complete business logic for user management,
security policies, and authentication workflows.
"""

import re
import secrets
import unicodedata
from datetime import UTC, datetime, timedelta
from enum import Enum
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)


class UserStatus(str, Enum):
    """User account status enumeration."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


class UserRole(str, Enum):
    """User role enumeration with hierarchical permissions."""

    ADMIN = "admin"
    CURATOR = "curator"
    RESEARCHER = "researcher"
    VIEWER = "viewer"


MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES_DEFAULT = 30


class User(BaseModel):
    """
    User domain entity with comprehensive security and business logic.

    Handles user authentication, authorization, account security, and domain rules.
    """

    id: UUID = Field(default_factory=uuid4)
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    full_name: str = Field(min_length=1, max_length=100)
    hashed_password: str
    role: UserRole = UserRole.VIEWER
    status: UserStatus = UserStatus.PENDING_VERIFICATION

    # Email verification
    email_verified: bool = False
    email_verification_token: str | None = None

    # Password reset
    password_reset_token: str | None = None
    password_reset_expires: datetime | None = None

    # Security tracking
    last_login: datetime | None = None
    login_attempts: int = 0
    locked_until: datetime | None = None

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(from_attributes=True)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username format and security."""
        if not v:
            msg = "Username cannot be empty"
            raise ValueError(msg)

        # Normalize Unicode (NFKC normalization)
        normalized = unicodedata.normalize("NFKC", v)

        # Remove control characters
        cleaned = "".join(c for c in normalized if unicodedata.category(c)[0] != "C")

        # Character restrictions (allow Unicode letters, numbers, common symbols)
        if not re.match(r"^[\w\s\-_\.]+$", cleaned, re.UNICODE):
            msg = "Username contains invalid characters"
            raise ValueError(msg)

        return cleaned

    # Email validation is handled by EmailStr type

    @model_validator(mode="after")
    def validate_business_rules(self) -> "User":
        """Apply business rules and cross-field validations."""
        # Check password reset token expiration
        if (
            self.password_reset_token
            and self.password_reset_expires
            and self.password_reset_expires < datetime.now(UTC)
        ):
            # Clear expired reset token
            self.password_reset_token = None
            self.password_reset_expires = None

        return self

    def is_active(self) -> bool:
        """Check if user account is active."""
        return self.status == UserStatus.ACTIVE

    def is_locked(self) -> bool:
        """Check if account is temporarily locked."""
        return self.locked_until is not None and self.locked_until > datetime.now(
            UTC,
        )

    def can_authenticate(self) -> bool:
        """Check if user can authenticate (active and not locked)."""
        return self.is_active() and not self.is_locked()

    def record_login_attempt(self, *, success: bool) -> None:
        """Record a login attempt with security tracking."""
        if success:
            # Successful login
            self.login_attempts = 0
            self.last_login = datetime.now(UTC)
            # Clear any lockout
            self.locked_until = None
        else:
            # Failed login
            self.login_attempts += 1
            if self.login_attempts >= MAX_FAILED_ATTEMPTS:
                self.locked_until = datetime.now(UTC) + timedelta(
                    minutes=LOCK_MINUTES_DEFAULT,
                )

    def lock_account(self, duration_minutes: int = LOCK_MINUTES_DEFAULT) -> None:
        """Manually lock user account."""
        self.locked_until = datetime.now(UTC) + timedelta(
            minutes=duration_minutes,
        )
        self.status = UserStatus.SUSPENDED

    def unlock_account(self) -> None:
        """Unlock user account."""
        self.locked_until = None
        self.login_attempts = 0
        if self.status == UserStatus.SUSPENDED:
            self.status = UserStatus.ACTIVE

    def activate_account(self) -> None:
        """Activate an account and bypass email verification requirements."""
        self.status = UserStatus.ACTIVE
        self.locked_until = None
        self.login_attempts = 0
        self.email_verified = True
        self.email_verification_token = None
        self.updated_at = datetime.now(UTC)

    def mark_email_verified(self) -> None:
        """Mark user email as verified."""
        self.email_verified = True
        self.email_verification_token = None

    def generate_email_verification_token(self) -> str:
        """Generate a secure email verification token."""
        self.email_verification_token = secrets.token_urlsafe(32)
        return self.email_verification_token

    def generate_password_reset_token(self, expires_minutes: int = 60) -> str:
        """Generate a secure password reset token."""
        self.password_reset_token = secrets.token_urlsafe(32)
        self.password_reset_expires = datetime.now(UTC) + timedelta(
            minutes=expires_minutes,
        )
        return self.password_reset_token

    def clear_password_reset_token(self) -> None:
        """Clear password reset token."""
        self.password_reset_token = None
        self.password_reset_expires = None

    def can_reset_password(self, token: str) -> bool:
        """Check if password reset token is valid."""
        if not self.password_reset_token or not self.password_reset_expires:
            return False
        return (
            self.password_reset_token == token
            and self.password_reset_expires > datetime.now(UTC)
        )

    def update_profile(self, full_name: str | None = None) -> None:
        """Update user profile information."""
        if full_name is not None:
            self.full_name = full_name
        self.updated_at = datetime.now(UTC)

    def __str__(self) -> str:
        """String representation for logging/debugging."""
        return f"User(id={self.id}, email={self.email}, role={self.role.value}, status={self.status.value})"

    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        return (
            f"User(id={self.id!r}, email={self.email!r}, username={self.username!r}, "
            f"role={self.role!r}, status={self.status!r}, email_verified={self.email_verified!r})"
        )
