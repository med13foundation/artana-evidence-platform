"""
Custom exceptions for Artana Resource Library authentication system.

Provides structured error handling with appropriate HTTP status codes.
"""

from fastapi import HTTPException, status

from src.type_definitions.common import JSONObject


class AuthenticationException(HTTPException):
    """Base exception for authentication-related errors."""

    def __init__(
        self,
        detail: str,
        status_code: int = status.HTTP_401_UNAUTHORIZED,
        headers: dict[str, str] | None = None,
        error_code: str | None = None,
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.error_code = error_code or "AUTH_ERROR"


class AuthorizationException(HTTPException):
    """Base exception for authorization-related errors."""

    def __init__(
        self,
        detail: str,
        status_code: int = status.HTTP_403_FORBIDDEN,
        error_code: str | None = None,
    ):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code or "AUTHZ_ERROR"


class ValidationException(HTTPException):
    """Base exception for validation-related errors."""

    def __init__(
        self,
        detail: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        error_code: str | None = None,
    ):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code or "VALIDATION_ERROR"


# Authentication-specific exceptions
class InvalidCredentialsException(AuthenticationException):
    """Raised when login credentials are invalid."""

    def __init__(self, detail: str = "Invalid email or password"):
        super().__init__(detail=detail, error_code="AUTH_INVALID_CREDENTIALS")


class AccountLockedException(AuthenticationException):
    """Raised when account is locked due to security policy."""

    def __init__(
        self,
        detail: str = "Account is locked due to multiple failed login attempts",
    ):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_423_LOCKED,
            error_code="AUTH_ACCOUNT_LOCKED",
        )


class AccountInactiveException(AuthenticationException):
    """Raised when account is not active."""

    def __init__(self, detail: str = "Account is not active"):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="AUTH_ACCOUNT_INACTIVE",
        )


class TokenExpiredException(AuthenticationException):
    """Raised when JWT token has expired."""

    def __init__(self, detail: str = "Token has expired"):
        super().__init__(
            detail=detail,
            error_code="AUTH_TOKEN_EXPIRED",
            headers={"WWW-Authenticate": "Bearer"},
        )


class TokenInvalidException(AuthenticationException):
    """Raised when JWT token is invalid."""

    def __init__(self, detail: str = "Invalid token"):
        super().__init__(
            detail=detail,
            error_code="AUTH_TOKEN_INVALID",
            headers={"WWW-Authenticate": "Bearer"},
        )


# Authorization-specific exceptions
class InsufficientPermissionsException(AuthorizationException):
    """Raised when user lacks required permissions."""

    def __init__(self, permission: str):
        super().__init__(
            detail=f"Permission denied: {permission}",
            error_code="AUTHZ_INSUFFICIENT_PERMISSIONS",
        )


class ResourceNotFoundException(AuthorizationException):
    """Raised when requested resource doesn't exist."""

    def __init__(self, resource: str):
        super().__init__(
            detail=f"Resource not found: {resource}",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="AUTHZ_RESOURCE_NOT_FOUND",
        )


# User management exceptions
class UserNotFoundException(ValidationException):
    """Raised when user doesn't exist."""

    def __init__(self, user_id: str):
        super().__init__(
            detail=f"User not found: {user_id}",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="USER_NOT_FOUND",
        )


class UserAlreadyExistsException(ValidationException):
    """Raised when attempting to create user that already exists."""

    def __init__(self, field: str, value: str):
        super().__init__(
            detail=f"User with {field} '{value}' already exists",
            status_code=status.HTTP_409_CONFLICT,
            error_code="USER_ALREADY_EXISTS",
        )


class PasswordPolicyException(ValidationException):
    """Raised when password doesn't meet security requirements."""

    def __init__(self, detail: str = "Password does not meet security requirements"):
        super().__init__(detail=detail, error_code="PASSWORD_POLICY_VIOLATION")


class EmailVerificationException(ValidationException):
    """Raised when email verification fails."""

    def __init__(self, detail: str = "Email verification failed"):
        super().__init__(detail=detail, error_code="EMAIL_VERIFICATION_FAILED")


# Exception handlers
def create_error_response(
    exc: Exception,
    _status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
) -> JSONObject:
    """
    Create standardized error response.

    Args:
        exc: Exception that occurred
        status_code: HTTP status code

    Returns:
        Standardized error response dictionary
    """
    error_response: JSONObject = {
        "error": "Internal server error",
        "detail": "An unexpected error occurred",
        "code": "INTERNAL_ERROR",
    }

    # Handle custom exceptions with error codes
    custom_code = getattr(exc, "error_code", None)
    if custom_code is not None:
        error_response["code"] = str(custom_code)
        error_detail = getattr(exc, "detail", exc)
        error_response["detail"] = str(error_detail)

    # Handle HTTPExceptions
    elif isinstance(exc, HTTPException):
        error_response["error"] = "Request error"
        error_response["detail"] = getattr(exc, "detail", str(exc))

    # Handle validation errors
    elif hasattr(exc, "errors"):
        error_response["error"] = "Validation error"
        error_response["detail"] = exc.errors()
        error_response["code"] = "VALIDATION_ERROR"

    return error_response


# Exception mapping for services
EXCEPTION_MAPPING = {
    "AuthenticationError": AuthenticationException,
    "AuthorizationError": AuthorizationException,
    "UserManagementError": ValidationException,
    "ValueError": ValidationException,
}
