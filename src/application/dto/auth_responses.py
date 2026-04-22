"""
Response Data Transfer Objects for authentication operations.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.domain.entities.user import User, UserRole, UserStatus


def _example_auth_value(label: str) -> str:
    """Build schema example values without inline secret-like literals."""
    return f"<example-{label}>"


def _bearer_scheme() -> str:
    """Return the OAuth token scheme for schema examples."""
    return "bearer"


class UserPublic(BaseModel):
    """Public user information (excludes sensitive data)."""

    id: str
    email: str
    username: str
    full_name: str
    role: UserRole
    status: UserStatus
    email_verified: bool
    last_login: datetime | None
    created_at: datetime

    @classmethod
    def from_user(cls, user: User) -> "UserPublic":
        """Create UserPublic from User entity."""
        return cls(
            id=str(user.id),
            email=user.email,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            status=user.status,
            email_verified=user.email_verified,
            last_login=user.last_login,
            created_at=user.created_at,
        )


class LoginResponse(BaseModel):
    """Response for successful login."""

    access_token: str
    refresh_token: str
    token_type: str = Field(default_factory=lambda: "bearer")
    expires_in: int  # seconds
    user: UserPublic

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": _example_auth_value("access"),
                "refresh_token": _example_auth_value("refresh"),
                "token_type": _bearer_scheme(),
                "expires_in": 900,
                "user": {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "email": "user@example.com",
                    "username": "researcher1",
                    "full_name": "Dr. Jane Smith",
                    "role": "researcher",
                    "status": "active",
                    "email_verified": True,
                    "last_login": "2025-01-04T10:30:00Z",
                    "created_at": "2024-12-01T08:00:00Z",
                },
            },
        },
    )


class TokenRefreshResponse(BaseModel):
    """Response for token refresh."""

    access_token: str
    refresh_token: str
    token_type: str = Field(default_factory=lambda: "bearer")
    expires_in: int

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": _example_auth_value("access"),
                "refresh_token": _example_auth_value("refresh"),
                "token_type": _bearer_scheme(),
                "expires_in": 900,
            },
        },
    )


class UserProfileResponse(BaseModel):
    """Response for user profile information."""

    user: UserPublic

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user": {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "email": "user@example.com",
                    "username": "researcher1",
                    "full_name": "Dr. Jane Smith",
                    "role": "researcher",
                    "status": "active",
                    "email_verified": True,
                    "last_login": "2025-01-04T10:30:00Z",
                    "created_at": "2024-12-01T08:00:00Z",
                },
            },
        },
    )


class UserListResponse(BaseModel):
    """Response for user listing with pagination."""

    users: list[UserPublic]
    total: int
    skip: int
    limit: int

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "users": [
                    {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "email": "user1@example.com",
                        "username": "researcher1",
                        "full_name": "Dr. Jane Smith",
                        "role": "researcher",
                        "status": "active",
                        "email_verified": True,
                        "last_login": "2025-01-04T10:30:00Z",
                        "created_at": "2024-12-01T08:00:00Z",
                    },
                ],
                "total": 1,
                "skip": 0,
                "limit": 10,
            },
        },
    )


class UserStatisticsResponse(BaseModel):
    """Response for user statistics."""

    total_users: int
    active_users: int
    inactive_users: int
    suspended_users: int
    pending_verification: int
    by_role: dict[str, int]
    recent_registrations: int  # Last 30 days
    recent_logins: int  # Last 7 days

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_users": 150,
                "active_users": 120,
                "inactive_users": 10,
                "suspended_users": 5,
                "pending_verification": 15,
                "by_role": {"admin": 5, "curator": 15, "researcher": 80, "viewer": 50},
                "recent_registrations": 12,
                "recent_logins": 45,
            },
        },
    )


class PasswordResetResponse(BaseModel):
    """Response for password reset request."""

    message: str
    email: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Password reset email sent",
                "email": "user@example.com",
            },
        },
    )


class GenericSuccessResponse(BaseModel):
    """Generic success response."""

    message: str

    model_config = ConfigDict(
        json_schema_extra={"example": {"message": "Operation completed successfully"}},
    )


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str
    detail: str | None = None
    code: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "Authentication failed",
                "detail": "Invalid email or password",
                "code": "AUTH_INVALID_CREDENTIALS",
            },
        },
    )


class ValidationErrorResponse(BaseModel):
    """Validation error response."""

    error: str
    detail: dict[str, list[str]]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "Validation failed",
                "detail": {
                    "email": ["Invalid email format"],
                    "password": ["Password too short", "Missing number"],
                },
            },
        },
    )
