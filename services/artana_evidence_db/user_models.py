"""Service-local user models for the standalone graph API."""

from __future__ import annotations

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
    """Service-local authenticated user entity."""

    id: UUID = Field(default_factory=uuid4)
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    full_name: str = Field(min_length=1, max_length=100)
    hashed_password: str
    role: UserRole = UserRole.VIEWER
    status: UserStatus = UserStatus.PENDING_VERIFICATION
    email_verified: bool = False
    email_verification_token: str | None = None
    password_reset_token: str | None = None
    password_reset_expires: datetime | None = None
    last_login: datetime | None = None
    login_attempts: int = 0
    locked_until: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(from_attributes=True)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        """Validate username format and normalize unicode."""
        if not value:
            msg = "Username cannot be empty"
            raise ValueError(msg)

        normalized = unicodedata.normalize("NFKC", value)
        cleaned = "".join(
            character
            for character in normalized
            if unicodedata.category(character)[0] != "C"
        )
        if not re.match(r"^[\w\s\-_\.]+$", cleaned, re.UNICODE):
            msg = "Username contains invalid characters"
            raise ValueError(msg)
        return cleaned

    @model_validator(mode="after")
    def validate_business_rules(self) -> User:
        """Clear expired password-reset state."""
        if (
            self.password_reset_token
            and self.password_reset_expires
            and self.password_reset_expires < datetime.now(UTC)
        ):
            self.password_reset_token = None
            self.password_reset_expires = None
        return self

    def is_active(self) -> bool:
        """Check whether the account is active."""
        return self.status == UserStatus.ACTIVE

    def is_locked(self) -> bool:
        """Check whether the account is temporarily locked."""
        return self.locked_until is not None and self.locked_until > datetime.now(UTC)

    def can_authenticate(self) -> bool:
        """Check whether the account can authenticate."""
        return self.is_active() and not self.is_locked()

    def record_login_attempt(self, *, success: bool) -> None:
        """Record a login attempt and update lockout state."""
        if success:
            self.login_attempts = 0
            self.last_login = datetime.now(UTC)
            self.locked_until = None
            return

        self.login_attempts += 1
        if self.login_attempts >= MAX_FAILED_ATTEMPTS:
            self.locked_until = datetime.now(UTC) + timedelta(
                minutes=LOCK_MINUTES_DEFAULT,
            )

    def lock_account(self, duration_minutes: int = LOCK_MINUTES_DEFAULT) -> None:
        """Manually lock the account."""
        self.locked_until = datetime.now(UTC) + timedelta(
            minutes=duration_minutes,
        )
        self.status = UserStatus.SUSPENDED

    def unlock_account(self) -> None:
        """Unlock the account and restore active status."""
        self.locked_until = None
        self.login_attempts = 0
        if self.status == UserStatus.SUSPENDED:
            self.status = UserStatus.ACTIVE

    def activate_account(self) -> None:
        """Mark the account as active and verified."""
        self.status = UserStatus.ACTIVE
        self.locked_until = None
        self.login_attempts = 0
        self.email_verified = True
        self.email_verification_token = None
        self.updated_at = datetime.now(UTC)

    def mark_email_verified(self) -> None:
        """Mark the account email as verified."""
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
        """Clear any active password-reset token."""
        self.password_reset_token = None
        self.password_reset_expires = None

    def can_reset_password(self, token: str) -> bool:
        """Check whether a password-reset token remains valid."""
        if not self.password_reset_token or not self.password_reset_expires:
            return False
        return (
            self.password_reset_token == token
            and self.password_reset_expires > datetime.now(UTC)
        )

    def update_profile(self, full_name: str | None = None) -> None:
        """Update basic profile fields."""
        if full_name is not None:
            self.full_name = full_name
        self.updated_at = datetime.now(UTC)


__all__ = ["User", "UserRole", "UserStatus"]
