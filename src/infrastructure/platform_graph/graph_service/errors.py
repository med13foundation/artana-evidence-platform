"""Shared error types for graph-service HTTP integrations."""

from __future__ import annotations


class GraphServiceClientError(Exception):
    """Graph service request failure."""

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


__all__ = ["GraphServiceClientError"]
