from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import timedelta
    from uuid import UUID


class JWTProviderService(Protocol):
    """Protocol describing JWT provider capabilities required by the application."""

    def create_access_token(
        self,
        user_id: UUID,
        role: str,
        expires_delta: timedelta | None = None,
        extra_claims: Mapping[str, object] | None = None,
        issuer: str = "artana-resource-library",
    ) -> str:
        """Create a signed JWT access token."""

    def create_refresh_token(
        self,
        user_id: UUID,
        expires_delta: timedelta | None = None,
    ) -> str:
        """Create a signed JWT refresh token."""

    def decode_token(self, token: str) -> dict[str, object]:
        """Decode and validate a JWT token, returning its payload."""
