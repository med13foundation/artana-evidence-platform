"""
Session lifecycle management helpers for authentication workflows.

Encapsulates session creation and failed login tracking to keep the primary
AuthenticationService focused on orchestration logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from src.domain.entities.session import UserSession

if TYPE_CHECKING:
    from src.domain.entities.user import User
    from src.domain.repositories.session_repository import SessionRepository
    from src.domain.repositories.user_repository import UserRepository


@dataclass
class SessionLifecycleManager:
    """Handle session creation and failed login tracking."""

    user_repository: UserRepository
    session_repository: SessionRepository
    access_token_expiry_minutes: int
    refresh_token_expiry_days: int
    max_sessions: int = 5
    max_failed_attempts: int = 5
    lockout_minutes: int = 30

    async def create_session(
        self,
        user: User,
        ip_address: str | None,
        user_agent: str | None,
        access_token: str,
        refresh_token: str,
    ) -> UserSession:
        """Create and persist a new authenticated session for the user."""
        active_sessions = await self.session_repository.count_active_sessions(user.id)

        if active_sessions >= self.max_sessions:
            sessions = await self.session_repository.get_user_sessions(
                user.id,
                include_expired=False,
            )
            if sessions:
                oldest_session = min(sessions, key=lambda session: session.created_at)
                await self.session_repository.revoke_session(oldest_session.id)

        session = UserSession(
            user_id=user.id,
            session_token=access_token,
            refresh_token=refresh_token,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=datetime.now(UTC)
            + timedelta(minutes=self.access_token_expiry_minutes),
            refresh_expires_at=datetime.now(UTC)
            + timedelta(days=self.refresh_token_expiry_days),
        )

        if ip_address and user_agent:
            session.generate_device_fingerprint(ip_address, user_agent)

        return await self.session_repository.create(session)

    async def record_failed_login_attempt(self, user: User) -> None:
        """
        Record a failed login attempt and apply lockout when thresholds are exceeded.
        """
        current_attempts = await self.user_repository.increment_login_attempts(user.id)

        if current_attempts >= self.max_failed_attempts:
            lockout_duration = timedelta(minutes=self.lockout_minutes)
            await self.user_repository.lock_account(
                user.id,
                datetime.now(UTC) + lockout_duration,
            )
