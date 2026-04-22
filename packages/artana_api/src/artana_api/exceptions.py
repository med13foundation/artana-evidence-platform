"""Public exception types for the Artana SDK."""

from __future__ import annotations


class ArtanaError(RuntimeError):
    """Base error raised by the public Artana SDK."""


class ArtanaConfigurationError(ArtanaError):
    """Raised when SDK configuration is missing or invalid."""


class ArtanaRequestError(ArtanaError):
    """Raised when the Artana API returns a failed HTTP response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class ArtanaResponseValidationError(ArtanaError):
    """Raised when an Artana API response cannot be validated."""


__all__ = [
    "ArtanaConfigurationError",
    "ArtanaError",
    "ArtanaRequestError",
    "ArtanaResponseValidationError",
]
