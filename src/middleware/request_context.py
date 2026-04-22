from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.datastructures import MutableHeaders
from starlette.requests import Request

from src.infrastructure.observability.request_context import (
    REQUEST_ID_HEADER,
    build_audit_context,
    resolve_request_id,
)

if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestContextMiddleware:
    """Attach request IDs and audit context to the request lifecycle."""

    def __init__(self, app: ASGIApp, header_name: str = REQUEST_ID_HEADER) -> None:
        self.app = app
        self._header_name = header_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        request_id = resolve_request_id(request)
        state = scope.setdefault("state", {})
        if not isinstance(state, dict):
            state = {}
            scope["state"] = state
        state["request_id"] = request_id
        state["audit_context"] = build_audit_context(request)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if self._header_name not in headers:
                    headers[self._header_name] = request_id

            await send(message)

        await self.app(scope, receive, send_with_request_id)


__all__ = ["RequestContextMiddleware"]
