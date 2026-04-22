"""
JWT token provider for Artana Resource Library.

Provides secure JWT token creation, validation, and management.
"""

import secrets
import string
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import jwt

from src.domain.services.security.jwt_provider import JWTProviderService
from src.type_definitions.security import (
    DecodedTokenPayload,
    RefreshResult,
    TokenPayload,
)


class JWTProvider(JWTProviderService):
    """
    JWT token provider with secure token management.

    Features:
    - HS256 signing for security
    - Configurable token expiration
    - Token validation with error handling
    - Access and refresh token support
    """

    MIN_SECRET_LEN: int = 32

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        """
        Initialize JWT provider.

        Args:
            secret_key: Secret key for signing tokens (must be strong)
            algorithm: JWT algorithm (default: HS256)
        """
        self.secret_key = secret_key
        self.algorithm = algorithm

        # Validate secret key strength
        if not secret_key or len(secret_key) < self.MIN_SECRET_LEN:
            message = (
                f"JWT secret key must be at least {self.MIN_SECRET_LEN} characters long"
            )
            raise ValueError(message)

    def create_access_token(
        self,
        user_id: UUID,
        role: str,
        expires_delta: timedelta | None = None,
        extra_claims: Mapping[str, object] | None = None,
        issuer: str = "artana-resource-library",
    ) -> str:
        """
        Create a JWT access token.

        Args:
            user_id: User's unique identifier
            role: User's role
            expires_delta: Token expiration time (default: 15 minutes)

        Returns:
            JWT access token string
        """
        if expires_delta is None:
            expires_delta = timedelta(minutes=15)  # Short-lived access tokens

        expire = datetime.now(UTC) + expires_delta

        base_payload: TokenPayload = {
            "sub": str(user_id),
            "role": role,
            "type": "access",
            "jti": str(uuid4()),
            "exp": expire,
            "iat": datetime.now(UTC),
            "iss": issuer,
        }
        to_encode: dict[str, object] = dict(base_payload)
        if extra_claims is not None:
            to_encode.update(dict(extra_claims))

        return self._encode_token(to_encode)

    def create_refresh_token(
        self,
        user_id: UUID,
        expires_delta: timedelta | None = None,
    ) -> str:
        """
        Create a JWT refresh token.

        Args:
            user_id: User's unique identifier
            expires_delta: Token expiration time (default: 7 days)

        Returns:
            JWT refresh token string
        """
        if expires_delta is None:
            expires_delta = timedelta(days=7)  # Long-lived refresh tokens

        expire = datetime.now(UTC) + expires_delta

        to_encode: TokenPayload = {
            "sub": str(user_id),
            "type": "refresh",
            "jti": str(uuid4()),
            "exp": expire,
            "iat": datetime.now(UTC),
            "iss": "artana-resource-library",
        }

        return self._encode_token(to_encode)

    def decode_token(self, token: str) -> dict[str, object]:
        """
        Decode and validate a JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            ValueError: If token is invalid, expired, or malformed
        """
        try:
            payload_obj = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                issuer="artana-resource-library",
            )

            decoded_payload = self._coerce_decoded_payload(payload_obj)
            self._validate_payload(decoded_payload)

        except jwt.ExpiredSignatureError as exc:
            message = "Token has expired"
            raise ValueError(message) from exc
        except jwt.InvalidTokenError as exc:
            message = f"Invalid token: {exc!s}"
            raise ValueError(message) from exc
        except jwt.InvalidIssuerError as exc:
            message = "Invalid token issuer"
            raise ValueError(message) from exc
        except Exception as exc:
            message = f"Token validation failed: {exc!s}"
            raise ValueError(message) from exc
        # Type: DecodedTokenPayload is compatible with dict[str, object]
        return dict(decoded_payload)

    def get_token_expiration(self, token: str) -> datetime:
        """
        Get token expiration time without full validation.

        Args:
            token: JWT token string

        Returns:
            Token expiration datetime

        Raises:
            ValueError: If token is malformed
        """
        try:
            payload = self._decode_unverified_payload(token)
        except Exception as exc:
            message = f"Cannot parse token expiration: {exc!s}"
            raise ValueError(message) from exc

        exp_timestamp = payload.get("exp")
        if not isinstance(exp_timestamp, int | float):
            message = "Token has no expiration"
            raise TypeError(message)

        return datetime.fromtimestamp(int(exp_timestamp), tz=UTC)

    def is_token_expired(self, token: str) -> bool:
        """
        Check if token is expired without full validation.

        Args:
            token: JWT token string

        Returns:
            True if token is expired
        """
        try:
            expiration = self.get_token_expiration(token)
            return datetime.now(UTC) > expiration
        except ValueError:
            return True  # Treat unparseable tokens as expired

    def refresh_access_token(self, refresh_token: str) -> RefreshResult:
        """
        Create new access token from valid refresh token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            Dictionary with new access token and expiration info

        Raises:
            ValueError: If refresh token is invalid
        """
        # Validate refresh token
        payload = self.decode_token(refresh_token)

        if payload.get("type") != "refresh":
            message = "Invalid token type"
            raise ValueError(message)

        sub_value = payload.get("sub")
        if not isinstance(sub_value, str):
            message = "Invalid user ID in token"
            raise TypeError(message)
        user_id = UUID(sub_value)

        role_value = payload.get("role")
        role = (
            role_value if isinstance(role_value, str) else "viewer"
        )  # Default role if not in refresh token

        # Create new access token
        new_access_token = self.create_access_token(user_id, role)

        # Get expiration info
        expiration = self.get_token_expiration(new_access_token)

        return {
            "access_token": new_access_token,
            "expires_at": expiration,
            "user_id": str(user_id),
            "role": role,
        }

    def _encode_token(self, payload: Mapping[str, object]) -> str:
        """
        Encode payload into JWT token.

        Args:
            payload: Token payload

        Returns:
            JWT token string
        """
        try:
            serializable_payload = dict(payload)
            return jwt.encode(
                serializable_payload,
                self.secret_key,
                algorithm=self.algorithm,
            )
        except Exception as exc:
            message = f"Token encoding failed: {exc!s}"
            raise ValueError(message) from exc

    def _validate_payload(self, payload: DecodedTokenPayload) -> None:
        """
        Validate decoded token payload.

        Args:
            payload: Decoded token payload

        Raises:
            ValueError: If payload is invalid
        """
        required_fields = ["sub", "type", "exp", "iat", "iss"]

        for field in required_fields:
            if field not in payload:
                message = f"Token missing required field: {field}"
                raise ValueError(message)

        # Validate subject (user ID)
        try:
            UUID(payload["sub"])
        except (ValueError, TypeError) as exc:
            message = "Invalid user ID in token"
            raise ValueError(message) from exc

        # Validate token type
        if payload["type"] not in ["access", "refresh"]:
            message = "Invalid token type"
            raise ValueError(message)

        # Validate issuer
        if payload["iss"] != "artana-resource-library":
            message = "Invalid token issuer"
            raise ValueError(message)

        # Additional security checks can be added here
        # - Check if user still exists and is active
        # - Check if token has been revoked
        # - Check IP address consistency
        # - Check user agent consistency

    def generate_secure_secret(self, length: int = 64) -> str:
        """
        Generate a cryptographically secure secret for JWT signing.

        Args:
            length: Length of secret (default: 64)

        Returns:
            Secure random string
        """
        alphabet = string.ascii_letters + string.digits + string.punctuation
        return "".join(secrets.choice(alphabet) for _ in range(length))

    def _decode_unverified_payload(self, token: str) -> dict[str, object]:
        """Decode a token without verifying the signature."""
        decoded: object = jwt.decode(token, options={"verify_signature": False})
        if not isinstance(decoded, dict):
            message = "Decoded token payload must be a JSON object"
            raise TypeError(message)
        return {str(key): value for key, value in decoded.items()}

    def _coerce_decoded_payload(
        self,
        payload: Mapping[str, object],
    ) -> DecodedTokenPayload:
        """Convert a decoded JWT payload into a typed structure."""
        result: DecodedTokenPayload = {}

        subject = payload.get("sub")
        if isinstance(subject, str) and subject:
            result["sub"] = subject
        token_type = payload.get("type")
        type_map: dict[str, Literal["access", "refresh"]] = {
            "access": "access",
            "refresh": "refresh",
        }
        literal_type = type_map.get(token_type) if isinstance(token_type, str) else None
        if literal_type is not None:
            result["type"] = literal_type
        token_id = payload.get("jti")
        if isinstance(token_id, str) and token_id:
            result["jti"] = token_id
        role = payload.get("role")
        if isinstance(role, str):
            result["role"] = role
        graph_admin = payload.get("graph_admin")
        if isinstance(graph_admin, bool):
            result["graph_admin"] = graph_admin
        issuer = payload.get("iss")
        if isinstance(issuer, str):
            result["iss"] = issuer

        issued_at = payload.get("iat")
        if isinstance(issued_at, int | float):
            result["iat"] = int(issued_at)
        else:
            message = "Token missing issued-at timestamp"
            raise TypeError(message)

        expires = payload.get("exp")
        if isinstance(expires, int | float):
            result["exp"] = int(expires)
        else:
            message = "Token missing expiration timestamp"
            raise TypeError(message)

        return result
