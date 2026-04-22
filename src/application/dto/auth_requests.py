"""
Request Data Transfer Objects for authentication operations.
"""

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.domain.entities.user import UserRole


def _example_auth_value(label: str) -> str:
    """Build schema example values without inline secret-like literals."""
    return f"<example-{label}>"


class LoginRequest(BaseModel):
    """Request for user login."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "password": _example_auth_value("login"),
            },
        },
    )


class RegisterUserRequest(BaseModel):
    """Request for user registration."""

    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    full_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.VIEWER

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "newuser@example.com",
                "username": "new_user",
                "full_name": "New User",
                "password": _example_auth_value("signup"),
                "role": "researcher",
            },
        },
    )


class UpdateUserRequest(BaseModel):
    """Request for updating user profile."""

    full_name: str | None = Field(None, min_length=1, max_length=100)
    role: UserRole | None = None

    model_config = ConfigDict(
        json_schema_extra={"example": {"full_name": "Updated Name", "role": "curator"}},
    )


class ChangePasswordRequest(BaseModel):
    """Request for changing user password."""

    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "old_password": _example_auth_value("current"),
                "new_password": _example_auth_value("replacement"),
            },
        },
    )


class ForgotPasswordRequest(BaseModel):
    """Request for password reset."""

    email: EmailStr

    model_config = ConfigDict(
        json_schema_extra={"example": {"email": "user@example.com"}},
    )


class ResetPasswordRequest(BaseModel):
    """Request for resetting password with token."""

    token: str = Field(min_length=32, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "token": _example_auth_value("reset"),
                "new_password": _example_auth_value("replacement"),
            },
        },
    )


class RefreshTokenRequest(BaseModel):
    """Request for refreshing access token."""

    refresh_token: str = Field(min_length=1, max_length=4096)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "refresh_token": _example_auth_value("refresh"),
            },
        },
    )


class UpdateProfileRequest(BaseModel):
    """Request for updating user profile."""

    full_name: str | None = Field(None, min_length=1, max_length=100)

    model_config = ConfigDict(
        json_schema_extra={"example": {"full_name": "Updated Full Name"}},
    )


class CreateUserRequest(BaseModel):
    """Request for admin creating a user."""

    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    full_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.VIEWER

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "admin-created@example.com",
                "username": "admin_created",
                "full_name": "Admin Created User",
                "password": _example_auth_value("temporary"),
                "role": "researcher",
            },
        },
    )


class AdminUpdateUserRequest(BaseModel):
    """Request for admin updating a user."""

    full_name: str | None = Field(None, min_length=1, max_length=100)
    role: UserRole | None = None
    status: str | None = None  # Will be validated by service

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "full_name": "Updated by Admin",
                "role": "admin",
                "status": "active",
            },
        },
    )
