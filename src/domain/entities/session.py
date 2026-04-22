"""
Session entity for Artana Resource Library authentication system.

Manages user sessions, JWT token tracking, and session lifecycle.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.type_definitions.common import JSONObject


class SessionStatus(str, Enum):
    """Session status enumeration."""

    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class UserSession(BaseModel):
    """
    User session domain entity with JWT token management.

    Tracks user sessions, token lifecycle, and security monitoring.
    """

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID

    # JWT tokens
    session_token: str | None = None  # Access token
    refresh_token: str | None = None

    # Session metadata
    ip_address: str | None = None
    user_agent: str | None = None
    device_fingerprint: str | None = None

    # Session lifecycle
    status: SessionStatus = SessionStatus.ACTIVE
    expires_at: datetime
    refresh_expires_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def validate_session_times(self) -> "UserSession":
        """Validate session timing constraints."""
        # Ensure timezone-aware datetimes for comparison
        expires_at = self.expires_at
        refresh_expires_at = self.refresh_expires_at

        # Convert to UTC if naive
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if refresh_expires_at.tzinfo is None:
            refresh_expires_at = refresh_expires_at.replace(tzinfo=UTC)

        # Refresh token must expire after access token
        if refresh_expires_at <= expires_at:
            msg = "Refresh token must expire after access token"
            raise ValueError(msg)

        # Session should not be created with expired tokens
        now = datetime.now(UTC)
        if expires_at <= now:
            msg = "Cannot create session with already expired access token"
            raise ValueError(msg)

        return self

    def is_expired(self) -> bool:
        """Check if access token is expired."""
        now = datetime.now(UTC)
        # Ensure expires_at is timezone-aware for comparison
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return now > expires_at

    def is_refresh_expired(self) -> bool:
        """Check if refresh token is expired."""
        now = datetime.now(UTC)
        # Ensure refresh_expires_at is timezone-aware for comparison
        refresh_expires_at = self.refresh_expires_at
        if refresh_expires_at.tzinfo is None:
            refresh_expires_at = refresh_expires_at.replace(tzinfo=UTC)
        return now > refresh_expires_at

    def is_active(self) -> bool:
        """Check if session is active (not expired or revoked)."""
        return self.status == SessionStatus.ACTIVE and not self.is_expired()

    def can_refresh(self) -> bool:
        """Check if session can be refreshed."""
        return self.status == SessionStatus.ACTIVE and not self.is_refresh_expired()

    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.now(UTC)

    def revoke(self) -> None:
        """Revoke the session (logout)."""
        self.status = SessionStatus.REVOKED

    def extend(
        self,
        access_token_expiry: timedelta = timedelta(minutes=15),
        refresh_token_expiry: timedelta = timedelta(days=7),
    ) -> None:
        """Extend session with new tokens."""
        now = datetime.now(UTC)
        self.expires_at = now + access_token_expiry
        self.refresh_expires_at = now + refresh_token_expiry
        self.update_activity()

    def generate_device_fingerprint(
        self,
        ip_address: str,
        user_agent: str,
        additional_data: JSONObject | None = None,
    ) -> str:
        """Generate a device fingerprint for session tracking."""

        # Create fingerprint from device characteristics
        fingerprint_data = f"{ip_address}|{user_agent}"

        if additional_data:
            # Add additional device data if available
            fingerprint_data += f"|{additional_data}"

        # Hash for consistent length and privacy
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]
        self.device_fingerprint = fingerprint
        return fingerprint

    def is_suspicious_activity(self, new_ip: str, new_user_agent: str) -> bool:
        """Check if session activity appears suspicious."""
        if not self.ip_address or not self.user_agent:
            return False  # Cannot determine without baseline

        # Basic heuristic: IP or user agent changed
        return (self.ip_address != new_ip) or (self.user_agent != new_user_agent)

    def time_since_activity(self) -> timedelta:
        """Calculate time since last activity."""
        now = datetime.now(UTC)
        last_activity = self.last_activity
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=UTC)
        return now - last_activity

    def time_until_expiry(self) -> timedelta:
        """Calculate time until access token expires."""
        now = datetime.now(UTC)
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at - now

    def time_until_refresh_expiry(self) -> timedelta:
        """Calculate time until refresh token expires."""
        now = datetime.now(UTC)
        refresh_expires_at = self.refresh_expires_at
        if refresh_expires_at.tzinfo is None:
            refresh_expires_at = refresh_expires_at.replace(tzinfo=UTC)
        return refresh_expires_at - now

    def __str__(self) -> str:
        """String representation for logging."""
        return (
            f"UserSession(id={self.id}, user_id={self.user_id}, "
            f"status={self.status.value}, expires_at={self.expires_at})"
        )

    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        return (
            f"UserSession(id={self.id!r}, user_id={self.user_id!r}, "
            f"status={self.status!r}, expires_at={self.expires_at!r}, "
            f"last_activity={self.last_activity!r})"
        )
