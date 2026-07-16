"""Typed authorship contract for governed graph write requests."""

from __future__ import annotations

from typing import Literal

GraphWriteAuthorship = Literal["MANUAL", "AGENT"]


def effective_graph_write_authorship(
    *,
    requested_authorship: GraphWriteAuthorship,
    authenticated_ai_principal: str | None,
) -> GraphWriteAuthorship:
    """Resolve authorship from server-owned identity before caller input."""
    if authenticated_ai_principal is not None and authenticated_ai_principal.strip():
        return "AGENT"
    return requested_authorship


__all__ = ["GraphWriteAuthorship", "effective_graph_write_authorship"]
