"""
Security and authentication typed contracts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypedDict

if TYPE_CHECKING:
    from datetime import datetime


class TokenPayload(TypedDict, total=False):
    sub: str
    role: str
    graph_admin: bool
    type: Literal["access", "refresh"]
    jti: str
    exp: datetime
    iat: datetime
    iss: str


class DecodedTokenPayload(TypedDict, total=False):
    sub: str
    role: str
    graph_admin: bool
    type: Literal["access", "refresh"]
    jti: str
    exp: int
    iat: int
    iss: str


class RefreshResult(TypedDict):
    access_token: str
    expires_at: datetime
    user_id: str
    role: str


class PasswordAnalysis(TypedDict):
    """Password complexity analysis results."""

    length: int
    has_lowercase: bool
    has_uppercase: bool
    has_digit: bool
    has_special: bool
    is_strong: bool
    score: int
    issues: list[str]


class HashInfo(TypedDict, total=False):
    """Metadata returned from hash inspection."""

    scheme: str | None
    needs_update: bool
    is_valid: bool
    error: str


__all__ = [
    "DecodedTokenPayload",
    "HashInfo",
    "PasswordAnalysis",
    "RefreshResult",
    "TokenPayload",
]
