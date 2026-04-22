"""
User management service for Artana Resource Library.

Handles user lifecycle operations including registration, profile management, and administration.
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from src.application.dto.auth_requests import (
    AdminUpdateUserRequest,
    CreateUserRequest,
    RegisterUserRequest,
    UpdateUserRequest,
)
from src.application.dto.auth_responses import (
    UserListResponse,
    UserPublic,
    UserStatisticsResponse,
)
from src.domain.entities.user import User, UserRole, UserStatus
from src.domain.repositories.user_repository import UserRepository
from src.domain.services.security.password_hasher import PasswordHasherService

logger = logging.getLogger(__name__)

MIN_LOCAL_VISIBLE = 2


class UserManagementError(Exception):
    """Base exception for user management errors."""


class UserAlreadyExistsError(UserManagementError):
    """Raised when attempting to create user that already exists."""


class UserNotFoundError(UserManagementError):
    """Raised when user doesn't exist."""


class InvalidPasswordError(UserManagementError):
    """Raised when password is invalid."""


class EmailVerificationError(UserManagementError):
    """Raised when email verification fails."""


class UserManagementService:
    """
    Service for managing user accounts and profiles.

    Handles user registration, updates, password management, and administrative operations.
    """

    def __init__(
        self,
        user_repository: UserRepository,
        password_hasher: PasswordHasherService,
    ):
        self.user_repository = user_repository
        self.password_hasher = password_hasher

    async def register_user(self, request: RegisterUserRequest) -> User:
        logger.debug("Starting register_user for %s", request.email)

        # Check for existing users
        logger.debug("Checking for existing email")
        email_exists = await self.user_repository.exists_by_email(request.email)
        logger.debug("Email exists: %s", email_exists)
        if email_exists:
            msg = "User with this email already exists"
            raise UserAlreadyExistsError(msg)

        logger.debug("Checking for existing username")
        username_exists = await self.user_repository.exists_by_username(
            request.username,
        )
        logger.debug("Username exists: %s", username_exists)
        if username_exists:
            msg = "User with this username already exists"
            raise UserAlreadyExistsError(msg)

        # Validate password strength
        logger.debug("Validating password strength")
        password_strong = self.password_hasher.is_password_strong(request.password)
        logger.debug("Password strong: %s", password_strong)
        if not password_strong:
            msg = "Password does not meet security requirements"
            raise ValueError(msg)

        # Create user
        logger.debug("Creating user entity")
        user = User(
            email=request.email,
            username=request.username,
            full_name=request.full_name,
            hashed_password=self.password_hasher.hash_password(request.password),
            role=request.role,
            status=UserStatus.PENDING_VERIFICATION,
        )
        logger.debug("User created: %s", user.id)

        # Generate email verification token
        logger.debug("Generating email verification token")
        user.generate_email_verification_token()
        logger.debug("Token generated for user: %s", user.id)

        # Save user
        logger.debug("Saving user to database")
        logger.debug("User repository: %s", self.user_repository)
        logger.debug("User to save: %s", user)
        created_user = await self.user_repository.create(user)
        logger.debug("User saved: %s", created_user.id)

        return created_user

    async def create_user(self, request: CreateUserRequest, _created_by: UUID) -> User:
        # Check for existing users
        if await self.user_repository.exists_by_email(request.email):
            msg = "User with this email already exists"
            raise UserAlreadyExistsError(msg)

        if await self.user_repository.exists_by_username(request.username):
            msg = "User with this username already exists"
            raise UserAlreadyExistsError(msg)

        # Create user (admin-created users are active by default)
        user = User(
            email=request.email,
            username=request.username,
            full_name=request.full_name,
            hashed_password=self.password_hasher.hash_password(request.password),
            role=request.role,
            status=UserStatus.ACTIVE,
            email_verified=True,  # Admin-created users skip verification
        )

        return await self.user_repository.create(user)

    async def update_user(
        self,
        user_id: UUID,
        request: UpdateUserRequest,
        updated_by: UUID | None = None,
    ) -> User:
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            msg = "User not found"
            raise UserNotFoundError(msg)

        # Apply updates
        if request.full_name is not None:
            user.full_name = request.full_name

        if request.role is not None and updated_by:
            # Only admins can change roles
            admin_user = await self.user_repository.get_by_id(updated_by)
            if admin_user and admin_user.role == UserRole.ADMIN:
                user.role = request.role

        user.updated_at = datetime.now(UTC)

        return await self.user_repository.update(user)

    async def admin_update_user(
        self,
        user_id: UUID,
        request: AdminUpdateUserRequest,
    ) -> User:
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            msg = "User not found"
            raise UserNotFoundError(msg)

        # Apply admin updates
        if request.full_name is not None:
            user.full_name = request.full_name

        if request.role is not None:
            user.role = request.role

        if request.status is not None:
            # Validate status
            try:
                user.status = UserStatus(request.status.lower())
            except ValueError:
                msg = f"Invalid status: {request.status}"
                raise ValueError(msg) from None

        user.updated_at = datetime.now(UTC)

        return await self.user_repository.update(user)

    async def change_password(
        self,
        user_id: UUID,
        old_password: str,
        new_password: str,
    ) -> None:
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            msg = "User not found"
            raise UserNotFoundError(msg)

        # Verify old password
        if not self.password_hasher.verify_password(old_password, user.hashed_password):
            msg = "Current password is incorrect"
            raise InvalidPasswordError(msg)

        # Validate new password
        if not self.password_hasher.is_password_strong(new_password):
            msg = "New password does not meet security requirements"
            raise ValueError(msg)

        # Update password
        user.hashed_password = self.password_hasher.hash_password(new_password)
        user.updated_at = datetime.now(UTC)

        await self.user_repository.update(user)

        # TODO: Send password changed notification

    async def request_password_reset(self, email: str) -> str:
        user = await self.user_repository.get_by_email(email)
        if not user:
            # Return masked email even if user doesn't exist (security)
            return self._mask_email(email)

        # Generate reset token
        user.generate_password_reset_token()
        await self.user_repository.update(user)

        # TODO: Send password reset email

        return self._mask_email(email)

    async def reset_password(self, token: str, new_password: str) -> None:
        # Find user with this token
        # Note: This is inefficient - in production, you'd want a token index
        # For now, we'll iterate through users (not recommended for large datasets)

        # TODO: Implement proper token lookup in repository
        # For now, this is a placeholder implementation
        users = await self.user_repository.list_users(limit=1000)  # Get all users
        user = None
        for u in users:
            if (
                u.password_reset_token == token
                and u.password_reset_expires
                and u.password_reset_expires > datetime.now(UTC)
            ):
                user = u
                break

        if not user:
            msg = "Invalid or expired reset token"
            raise ValueError(msg)

        # Validate password
        if not self.password_hasher.is_password_strong(new_password):
            msg = "Password does not meet security requirements"
            raise ValueError(msg)

        # Update password and clear reset token
        user.hashed_password = self.password_hasher.hash_password(new_password)
        user.clear_password_reset_token()
        user.updated_at = datetime.now(UTC)

        await self.user_repository.update(user)

        # Revoke all sessions for security
        # TODO: await self.session_repository.revoke_all_user_sessions(user.id)

        # TODO: Send confirmation email

    async def verify_email(self, token: str) -> None:
        # Find user with this token
        # TODO: Implement proper token lookup in repository
        # For now, this is a placeholder implementation
        users = await self.user_repository.list_users(limit=1000)  # Get all users
        user = None
        for u in users:
            if u.email_verification_token == token:
                user = u
                break

        if not user:
            msg = "Invalid verification token"
            raise EmailVerificationError(msg)

        # Verify email
        user.mark_email_verified()
        await self.user_repository.update(user)

        # TODO: Send welcome email

    async def delete_user(self, user_id: UUID) -> None:
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            msg = "User not found"
            raise UserNotFoundError(msg)

        # TODO: Soft delete instead of hard delete for compliance

        # For now, hard delete
        await self.user_repository.delete(user_id)

        # TODO: Clean up related data (sessions, audit logs)

    async def get_user(self, user_id: UUID) -> User | None:
        return await self.user_repository.get_by_id(user_id)

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 100,
        role: UserRole | None = None,
        status: UserStatus | None = None,
    ) -> UserListResponse:
        users = await self.user_repository.list_users(
            skip=skip,
            limit=limit,
            role=role.value if role else None,
            status=status,
        )

        total = await self.user_repository.count_users(
            role=role.value if role else None,
            status=status,
        )

        return UserListResponse(
            users=[UserPublic.from_user(user) for user in users],
            total=total,
            skip=skip,
            limit=limit,
        )

    async def get_user_statistics(self) -> UserStatisticsResponse:
        try:
            # Count by status
            active_count = await self.user_repository.count_users_by_status(
                UserStatus.ACTIVE,
            )
            inactive_count = await self.user_repository.count_users_by_status(
                UserStatus.INACTIVE,
            )
            suspended_count = await self.user_repository.count_users_by_status(
                UserStatus.SUSPENDED,
            )
            pending_count = await self.user_repository.count_users_by_status(
                UserStatus.PENDING_VERIFICATION,
            )

            total_users = (
                active_count + inactive_count + suspended_count + pending_count
            )

            # Count by role
            role_counts: dict[str, int] = {}
            for role in UserRole:
                count = await self.user_repository.count_users(role=role.value)
                role_counts[role.value] = count

            # Recent activity (simplified - would need proper date filtering)
            recent_registrations = 0  # TODO: Implement date-based queries
            recent_logins = 0  # TODO: Implement date-based queries

            return UserStatisticsResponse(
                total_users=total_users,
                active_users=active_count,
                inactive_users=inactive_count,
                suspended_users=suspended_count,
                pending_verification=pending_count,
                by_role=role_counts,
                recent_registrations=recent_registrations,
                recent_logins=recent_logins,
            )
        except Exception:
            logger.exception(
                "Failed to compute user statistics; returning empty statistics payload",
            )
            return UserStatisticsResponse(
                total_users=0,
                active_users=0,
                inactive_users=0,
                suspended_users=0,
                pending_verification=0,
                by_role={role.value: 0 for role in UserRole},
                recent_registrations=0,
                recent_logins=0,
            )

    async def lock_user_account(
        self,
        user_id: UUID,
        _reason: str = "Administrative action",
    ) -> None:
        await self.user_repository.lock_account(
            user_id,
            datetime.now(UTC) + timedelta(days=30),  # 30 day lock
        )

        # TODO: Log security event
        # TODO: Send notification email

    async def unlock_user_account(self, user_id: UUID) -> None:
        await self.user_repository.unlock_account(user_id)

        # TODO: Log security event
        # TODO: Send notification email

    async def activate_user_account(self, user_id: UUID) -> User:
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            msg = "User not found"
            raise UserNotFoundError(msg)

        user.activate_account()
        return await self.user_repository.update(user)

    def _mask_email(self, email: str) -> str:
        try:
            local, domain = email.split("@", 1)
        except ValueError:
            return "***@***.***"

        if not local or not domain:
            return "***@***.***"

        if len(local) > MIN_LOCAL_VISIBLE:
            masked_local = local[0] + "*" * (len(local) - MIN_LOCAL_VISIBLE) + local[-1]
        else:
            masked_local = local[0] + "*" * (len(local) - 1)

        return f"{masked_local}@{domain}"
