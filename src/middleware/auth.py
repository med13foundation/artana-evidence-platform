"""
Authentication middleware for Artana Resource Library API.

Implements API key-based authentication with role-based access control.
"""

import logging
import os
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, status
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from src.infrastructure.security.cors import get_allowed_origins

_ENVIRONMENT = os.getenv("ARTANA_ENV", "development").lower()
_ALLOW_MISSING_KEYS = (
    os.getenv("ARTANA_ALLOW_MISSING_API_KEYS")
    or ("1" if _ENVIRONMENT == "development" else "0")
) == "1"
logger = logging.getLogger(__name__)


class APIKeyAuth:
    """API key authentication handler."""

    def __init__(self) -> None:
        self.api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
        self.valid_api_keys: dict[str, str] = {}
        self._register_api_key("ADMIN_API_KEY", "admin")
        self._register_api_key("WRITE_API_KEY", "write")
        self._register_api_key("READ_API_KEY", "read")
        self.enabled = bool(self.valid_api_keys)
        if not self.enabled:
            if not _ALLOW_MISSING_KEYS:
                msg = (
                    "No API keys configured. Set ADMIN_API_KEY / WRITE_API_KEY / "
                    "READ_API_KEY environment variables or set "
                    "ARTANA_ALLOW_MISSING_API_KEYS=1 for local development."
                )
                raise RuntimeError(msg)
            logger.warning(
                "API key authentication disabled (no keys configured). "
                "Requests must rely on JWT bearer tokens.",
            )

    def _register_api_key(self, env_var: str, role: str) -> None:
        """Register an API key from environment variables."""
        api_key = os.getenv(env_var)
        if not api_key:
            return
        self.valid_api_keys[api_key] = role

    async def authenticate(self, request: Request) -> str | None:
        """
        Authenticate the request using API key.

        Returns the user role if authenticated, None otherwise.
        """
        api_key = await self.api_key_header(request)

        if not api_key:
            return None

        return self.valid_api_keys.get(api_key)

    def require_role(self, required_role: str) -> Callable[[Request], Awaitable[str]]:
        """
        Create a dependency that requires a specific role.

        Usage: Depends(auth.require_role("admin"))
        """

        async def role_checker(request: Request) -> str:
            role = await self.authenticate(request)
            if not role:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="API key required",
                    headers={"WWW-Authenticate": "APIKey"},
                )

            # Role hierarchy: admin > write > read
            role_hierarchy = {"read": 1, "write": 2, "admin": 3}

            if role_hierarchy.get(role, 0) < role_hierarchy.get(required_role, 999):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. Required: {required_role}, Got: {role}",
                )

            return role

        return role_checker


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to handle authentication for all requests."""

    def __init__(
        self,
        app: ASGIApp,
        exclude_paths: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.auth = APIKeyAuth()
        self.exclude_paths: list[str] = exclude_paths or [
            "/health/",
            "/docs",
            "/openapi.json",
            "/",
            "/auth/",  # All auth routes use JWT
            "/research-spaces",  # Research spaces use JWT
            "/admin/",  # Admin routes use JWT
            "/dashboard/",  # Dashboard routes use JWT
        ]

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Process each request through authentication middleware."""

        # Skip authentication for OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Skip authentication for excluded paths
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)

        if not self.auth.enabled:
            return await call_next(request)

        # Skip if JWT token is present (let JWTAuthMiddleware handle it)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return await call_next(request)

        # For read operations (GET), allow with any valid key
        # For write operations (POST, PUT, DELETE), require write or admin
        if request.method in ["POST", "PUT", "DELETE"]:
            required_role = "write"
        else:
            required_role = "read"

        role = await self.auth.authenticate(request)
        if not role:
            # Add CORS headers to error response
            origin = request.headers.get("origin")
            headers = {"WWW-Authenticate": "APIKey"}
            allowed_origins = get_allowed_origins()
            if origin and origin.rstrip("/") in allowed_origins:
                headers.update(
                    {
                        "Access-Control-Allow-Origin": origin,
                        "Access-Control-Allow-Credentials": "true",
                    },
                )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key required",
                headers=headers,
            )

        # Check role permissions
        role_hierarchy = {"read": 1, "write": 2, "admin": 3}
        if role_hierarchy.get(role, 0) < role_hierarchy.get(required_role, 999):
            # Add CORS headers to error response
            origin = request.headers.get("origin")
            headers = {}
            allowed_origins = get_allowed_origins()
            if origin and origin.rstrip("/") in allowed_origins:
                headers.update(
                    {
                        "Access-Control-Allow-Origin": origin,
                        "Access-Control-Allow-Credentials": "true",
                    },
                )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {required_role}",
                headers=headers,
            )

        # Add user info to request state
        request.state.user_role = role

        return await call_next(request)


# Global auth instance
auth = APIKeyAuth()
