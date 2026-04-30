"""URL helpers and Prefer-header parsing for queued runs."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_api.queued_run.constants import _RESPOND_ASYNC_PREFER_TOKEN


def prefers_respond_async(prefer: str | None) -> bool:
    """Return whether the request explicitly prefers async acceptance."""
    if not isinstance(prefer, str):
        return False
    for directive in prefer.split(","):
        token = directive.strip()
        if token == "":
            continue
        token_name = token.split(";", 1)[0].strip().lower()
        if token_name == _RESPOND_ASYNC_PREFER_TOKEN:
            return True
    return False


def progress_url(*, space_id: UUID | str, run_id: UUID | str) -> str:
    """Return the relative progress URL for one run."""
    return f"/v1/spaces/{space_id}/runs/{run_id}/progress"


def events_url(*, space_id: UUID | str, run_id: UUID | str) -> str:
    """Return the relative events URL for one run."""
    return f"/v1/spaces/{space_id}/runs/{run_id}/events"


def workspace_url(*, space_id: UUID | str, run_id: UUID | str) -> str:
    """Return the relative workspace URL for one run."""
    return f"/v1/spaces/{space_id}/runs/{run_id}/workspace"


def artifacts_url(*, space_id: UUID | str, run_id: UUID | str) -> str:
    """Return the relative artifacts URL for one run."""
    return f"/v1/spaces/{space_id}/runs/{run_id}/artifacts"


__all__ = [
    "artifacts_url",
    "events_url",
    "prefers_respond_async",
    "progress_url",
    "workspace_url",
]
