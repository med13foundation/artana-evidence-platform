"""Shared constants for the live evidence session audit script."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_LOG_TAIL_LINES = 80
_DEFAULT_SESSION_KIND = "live_evidence_session_audit"
_HTTP_OK = 200
_DEFAULT_ENV_FILES = (
    Path(".env.postgres"),
    Path(".env"),
    Path("scripts/.env"),
)
_QUOTED_ENV_MIN_LENGTH = 2

__all__ = [
    "_DEFAULT_ENV_FILES",
    "_DEFAULT_LOG_TAIL_LINES",
    "_DEFAULT_SESSION_KIND",
    "_HTTP_OK",
    "_QUOTED_ENV_MIN_LENGTH",
    "_REPO_ROOT",
]
