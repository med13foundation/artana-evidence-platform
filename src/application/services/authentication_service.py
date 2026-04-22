"""
Authentication service for Artana Resource Library.

Handles user authentication, session management, and security operations.
"""

import logging
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

from src.application.dto.auth_requests import LoginRequest
from src.application.dto.auth_responses import (
    LoginResponse,
    TokenRefreshResponse,
    UserPublic,
)
from src.application.services.authentication_session_manager import (
    SessionLifecycleManager,
)
from src.domain.entities.session import UserSession
from src.domain.entities.user import User, UserRole, UserStatus
from src.domain.repositories.session_repository import SessionRepository
from src.domain.repositories.user_repository import UserRepository
from src.domain.services.security.jwt_provider import JWTProviderService
from src.domain.services.security.password_hasher import PasswordHasherService


class AuthenticationError(Exception):
    """Base exception for authentication errors."""


class InvalidCredentialsError(AuthenticationError):
    """Raised when login credentials are invalid."""


class AccountLockedError(AuthenticationError):
    """Raised when account is locked due to security policy."""


class AccountInactiveError(AuthenticationError):
    """Raised when account is not active."""


class AuthenticationService:
    """
    Service for handling user authentication and session management.

    Implements secure authentication with comprehensive security measures.
    """

    # Session expiration configuration (configurable via environment variables)
    ACCESS_TOKEN_EXPIRY_MINUTES = int(
        os.getenv("ARTANA_ACCESS_TOKEN_EXPIRY_MINUTES", "60"),
    )  # Default: 60 minutes (1 hour)
    REFRESH_TOKEN_EXPIRY_DAYS = int(
        os.getenv("ARTANA_REFRESH_TOKEN_EXPIRY_DAYS", "7"),
    )  # Default: 7 days
    SLIDING_EXPIRATION_ENABLED = (
        os.getenv("ARTANA_SLIDING_SESSION_EXPIRATION", "true").lower() == "true"
    )  # Default: enabled
    SESSION_ACTIVITY_WRITE_INTERVAL_SECONDS = max(
        int(
            os.getenv(
                "ARTANA_SESSION_ACTIVITY_WRITE_INTERVAL_SECONDS",
                "300",
            ),
        ),
        0,
    )  # Default: 5 minutes

    def __init__(
        self,
        user_repository: UserRepository,
        session_repository: SessionRepository,
        jwt_provider: JWTProviderService,
        password_hasher: PasswordHasherService,
    ):
        """
        Initialize authentication service.

        Args:
            user_repository: User data access
            session_repository: Session data access
            jwt_provider: JWT token management
            password_hasher: Password security
        """
        self.user_repository = user_repository
        self.session_repository = session_repository
        self.jwt_provider = jwt_provider
        self.password_hasher = password_hasher
        self.session_lifecycle = SessionLifecycleManager(
            user_repository=user_repository,
            session_repository=session_repository,
            access_token_expiry_minutes=self.ACCESS_TOKEN_EXPIRY_MINUTES,
            refresh_token_expiry_days=self.REFRESH_TOKEN_EXPIRY_DAYS,
        )

    @staticmethod
    def _access_token_extra_claims(user: User) -> dict[str, object]:
        """Emit graph-service claims needed by direct standalone-service callers."""
        return {"graph_admin": user.role == UserRole.ADMIN}

    async def authenticate_user(
        self,
        request: LoginRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> LoginResponse:
        """
        Authenticate user with email and password.

        Args:
            request: Login credentials
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            Login response with tokens

        Raises:
            InvalidCredentialsError: Invalid email or password
            AccountLockedError: Account is locked
            AccountInactiveError: Account is not active
        """
        # Get user by email (constant time regardless of existence)
        user = await self.user_repository.get_by_email(request.email)

        # Verify credentials (constant time)
        password_valid = False
        if user:
            password_valid = self.password_hasher.verify_password(
                request.password,
                user.hashed_password,
            )

        if not user or not password_valid:
            # Record failed attempt for security monitoring
            if user:
                await self.session_lifecycle.record_failed_login_attempt(user)
            msg = "Invalid email or password"
            raise InvalidCredentialsError(msg)

        # Check account status
        if not user.can_authenticate():
            if user.is_locked():
                msg = "Account is locked due to multiple failed login attempts"
                raise AccountLockedError(msg)
            if user.status != UserStatus.ACTIVE:
                msg = "Account is not active"
                raise AccountInactiveError(msg)

        # Update login tracking
        user.record_login_attempt(success=True)
        await self.user_repository.update(user)

        # Generate tokens first
        access_token = self.jwt_provider.create_access_token(
            user.id,
            user.role.value,
            extra_claims=self._access_token_extra_claims(user),
        )
        refresh_token = self.jwt_provider.create_refresh_token(user.id)

        # Create session with tokens
        await self.session_lifecycle.create_session(
            user,
            ip_address,
            user_agent,
            access_token=access_token,
            refresh_token=refresh_token,
        )

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=900,  # 15 minutes
            user=UserPublic.from_user(user),
        )

    async def refresh_token(self, refresh_token: str) -> TokenRefreshResponse:
        """
        Refresh access token using refresh token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            New token pair

        Raises:
            AuthenticationError: Invalid or expired refresh token
        """
        try:
            # Get active session by refresh token
            session = await self.session_repository.get_active_by_refresh_token(
                refresh_token,
            )

            if not session:
                msg = "Invalid refresh token"
                raise AuthenticationError(msg)  # noqa: TRY301

            # Get user
            user = await self.user_repository.get_by_id(session.user_id)
            if not user or not user.can_authenticate():
                # Revoke session if user is invalid
                await self.session_repository.revoke_session(session.id)
                msg = "User session invalid"
                raise AuthenticationError(msg)  # noqa: TRY301

            # Generate new tokens
            new_access_token = self.jwt_provider.create_access_token(
                user.id,
                user.role.value,
                extra_claims=self._access_token_extra_claims(user),
            )
            new_refresh_token = self.jwt_provider.create_refresh_token(user.id)

            # Update session with new tokens and expiration times
            session.session_token = new_access_token
            session.refresh_token = new_refresh_token
            session.expires_at = datetime.now(UTC) + timedelta(
                minutes=self.ACCESS_TOKEN_EXPIRY_MINUTES,
            )
            session.refresh_expires_at = datetime.now(UTC) + timedelta(
                days=self.REFRESH_TOKEN_EXPIRY_DAYS,
            )
            session.update_activity()

            await self.session_repository.update(session)

            return TokenRefreshResponse(
                access_token=new_access_token,
                refresh_token=new_refresh_token,
                expires_in=900,
            )
        except AuthenticationError:
            raise
        except Exception as exc:
            msg = f"Token refresh failed: {exc!s}"
            raise AuthenticationError(msg) from exc

    async def logout(self, access_token: str) -> None:
        """
        Logout user by revoking session.

        Args:
            access_token: Current access token
        """
        session = await self.session_repository.get_by_access_token(access_token)
        if session:
            await self.session_repository.revoke_session(session.id)

    def _extend_session_if_needed(self, session: UserSession) -> None:
        """
        Extend session expiration if sliding expiration is enabled and needed.

        Args:
            session: Active session to potentially extend
        """
        if not self.SLIDING_EXPIRATION_ENABLED:
            return

        now = datetime.now(UTC)
        time_until_expiry = session.time_until_expiry()

        # Extend session if it expires within 20% of its lifetime
        # This ensures users don't get logged out during active use
        expiry_threshold_minutes = max(
            self.ACCESS_TOKEN_EXPIRY_MINUTES * 0.2,
            5,  # Minimum 5 minutes threshold
        )
        expiry_threshold = timedelta(minutes=expiry_threshold_minutes)

        if time_until_expiry < expiry_threshold:
            logger = logging.getLogger(__name__)
            logger.debug(
                "[validate_token] Extending session expiration "
                "(sliding expiration). Current expiry in: %s, "
                "extending to %d minutes",
                time_until_expiry,
                self.ACCESS_TOKEN_EXPIRY_MINUTES,
            )
            # Extend access token expiration to full duration
            session.expires_at = now + timedelta(
                minutes=self.ACCESS_TOKEN_EXPIRY_MINUTES,
            )

            # Also extend refresh token if it's close to expiring
            # (within 1 day or 10% of its lifetime, whichever is smaller)
            time_until_refresh_expiry = session.time_until_refresh_expiry()
            refresh_threshold = min(
                timedelta(days=1),
                timedelta(days=self.REFRESH_TOKEN_EXPIRY_DAYS * 0.1),
            )
            if time_until_refresh_expiry < refresh_threshold:
                logger.debug(
                    "[validate_token] Also extending refresh token expiration",
                )
                session.refresh_expires_at = now + timedelta(
                    days=self.REFRESH_TOKEN_EXPIRY_DAYS,
                )

    @staticmethod
    def _coerce_utc(value: datetime) -> datetime:
        """Normalize datetime values for safe comparisons."""
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    async def _update_session_activity(self, session: UserSession) -> None:
        """
        Update session activity and extend if needed.

        Args:
            session: Active session to update
        """
        logger = logging.getLogger(__name__)
        logger.debug(
            "[validate_token] Session found: id=%s, status=%s, "
            "expires_at=%s (tzinfo=%s), "
            "refresh_expires_at=%s (tzinfo=%s)",
            session.id,
            session.status,
            session.expires_at,
            session.expires_at.tzinfo,
            session.refresh_expires_at,
            session.refresh_expires_at.tzinfo,
        )

        try:
            is_active_result = session.is_active()
            logger.debug(
                "[validate_token] Session is_active() result: %s",
                is_active_result,
            )

            if is_active_result:
                previous_expires_at = self._coerce_utc(session.expires_at)
                previous_refresh_expires_at = self._coerce_utc(
                    session.refresh_expires_at,
                )
                self._extend_session_if_needed(session)
                expires_at_changed = (
                    self._coerce_utc(session.expires_at) != previous_expires_at
                )
                refresh_expires_at_changed = (
                    self._coerce_utc(session.refresh_expires_at)
                    != previous_refresh_expires_at
                )
                expiration_changed = expires_at_changed or refresh_expires_at_changed

                write_interval = timedelta(
                    seconds=self.SESSION_ACTIVITY_WRITE_INTERVAL_SECONDS,
                )
                should_persist_activity = (
                    expiration_changed
                    or write_interval == timedelta(seconds=0)
                    or session.time_since_activity() >= write_interval
                )

                if should_persist_activity:
                    session.update_activity()
                    await self.session_repository.update(session)
                    logger.debug(
                        "[validate_token] Session activity updated "
                        "(expiration_changed=%s, write_interval_seconds=%d)",
                        expiration_changed,
                        self.SESSION_ACTIVITY_WRITE_INTERVAL_SECONDS,
                    )
                else:
                    logger.debug(
                        "[validate_token] Skipped session activity write "
                        "(write_interval_seconds=%d)",
                        self.SESSION_ACTIVITY_WRITE_INTERVAL_SECONDS,
                    )
        except Exception:
            logger.exception("[validate_token] Error checking session.is_active()")
            raise

    async def validate_token(self, token: str) -> User:
        """
        Validate JWT token and return user.

        Args:
            token: JWT access token

        Returns:
            Authenticated user

        Raises:
            AuthenticationError: Invalid token
        """
        logger = logging.getLogger(__name__)

        try:
            logger.debug(
                "[validate_token] Starting token validation for token: %s...",
                token[:20],
            )

            # Decode and validate token
            payload = self.jwt_provider.decode_token(token)
            logger.debug(
                "[validate_token] Token decoded successfully, payload keys: %s",
                list(payload.keys()),
            )

            if payload.get("type") != "access":
                msg = "Invalid token type"
                logger.warning(
                    "[validate_token] Invalid token type: %s",
                    payload.get("type"),
                )
                raise AuthenticationError(msg)  # noqa: TRY301

            # Get user
            sub_value = payload.get("sub")
            if not isinstance(sub_value, str):
                msg = "Invalid user ID in token"
                logger.warning(
                    "[validate_token] Invalid user ID type: %s",
                    type(sub_value),
                )
                raise AuthenticationError(msg)  # noqa: TRY301
            user_id = UUID(sub_value)
            logger.debug("[validate_token] Extracted user_id: %s", user_id)
            user = await self.user_repository.get_by_id(user_id)

            if not user:
                msg = "User not found"
                logger.warning("[validate_token] User not found: %s", user_id)
                raise AuthenticationError(msg)  # noqa: TRY301

            if not user.can_authenticate():
                msg = "User account not active"
                logger.warning("[validate_token] User account not active: %s", user_id)
                raise AuthenticationError(msg)  # noqa: TRY301

            # Update session activity if session exists
            logger.debug("[validate_token] Looking up session by access token")
            session = await self.session_repository.get_by_access_token(token)

            if session:
                await self._update_session_activity(session)
            else:
                logger.debug("[validate_token] No session found for token")

            logger.debug(
                "[validate_token] Token validation successful for user: %s",
                user_id,
            )
            return user  # noqa: TRY300
        except AuthenticationError:
            raise
        except Exception as exc:
            # Log expected token validation failures at debug level (no traceback)
            # These are normal authentication failures (invalid/expired tokens)
            logger.debug(
                "[validate_token] Token validation failed: %s",
                str(exc),
            )
            msg = f"Token validation failed: {exc!s}"
            raise AuthenticationError(msg) from exc

    async def get_user_sessions(self, user_id: UUID) -> list[UserSession]:
        """
        Get all active sessions for a user.

        Args:
            user_id: User ID

        Returns:
            List of active sessions
        """
        return await self.session_repository.get_active_sessions(user_id)

    async def revoke_user_session(self, user_id: UUID, session_id: UUID) -> None:
        """
        Revoke a specific user session.

        Args:
            user_id: User ID (for authorization)
            session_id: Session to revoke
        """
        # Verify session belongs to user
        session = await self.session_repository.get_by_id(session_id)
        if session and session.user_id == user_id:
            await self.session_repository.revoke_session(session_id)

    async def revoke_all_user_sessions(self, user_id: UUID) -> int:
        """
        Revoke all sessions for a user.

        Args:
            user_id: User ID

        Returns:
            Number of sessions revoked
        """
        return await self.session_repository.revoke_all_user_sessions(user_id)

    async def revoke_expired_sessions(self) -> int:
        """
        Revoke all expired sessions (mark as EXPIRED).

        Returns:
            Number of sessions revoked
        """
        return await self.session_repository.revoke_expired_sessions()

    async def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions (maintenance operation).

        Returns:
            Number of sessions cleaned up
        """
        return await self.session_repository.cleanup_expired_sessions()
