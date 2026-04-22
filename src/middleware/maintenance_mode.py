"""
Maintenance mode middleware to enforce read-only behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.infrastructure.dependency_injection.container import container

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.types import ASGIApp


class MaintenanceModeMiddleware(BaseHTTPMiddleware):
    """Block state-changing requests while maintenance mode is active."""

    SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
    ALLOWED_PREFIXES = (
        "/admin/system/maintenance",
        "/admin/storage/configurations",
    )

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._system_status_service = container.get_system_status_service()

    def _is_allowed_path(self, path: str) -> bool:
        return any(path.startswith(prefix) for prefix in self.ALLOWED_PREFIXES)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        service = self._system_status_service
        state = await service.get_maintenance_state()

        if not state.is_active:
            return await call_next(request)

        if request.method in self.SAFE_METHODS or self._is_allowed_path(
            request.url.path,
        ):
            return await call_next(request)

        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "Maintenance mode active. Please try again later.",
                "maintenance_message": state.message,
            },
        )
