from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Final

from starlette.requests import Request

from src.application.curation.repositories.audit_repository import (
    SqlAlchemyAuditRepository,
)
from src.application.services.audit_service import AuditTrailService
from src.database.session import SessionLocal, set_session_rls_context
from src.domain.entities.user import User
from src.infrastructure.observability.request_context import get_audit_context

if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

    from src.type_definitions.common import AuditContext, JSONObject

logger = logging.getLogger(__name__)

DEFAULT_EXCLUDED_PREFIXES: Final[tuple[str, ...]] = (
    "/auth",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
    "/resources",
)

READ_METHODS: Final[frozenset[str]] = frozenset({"GET"})
MUTATION_ACTIONS: Final[dict[str, str]] = {
    "POST": "phi.create",
    "PUT": "phi.update",
    "PATCH": "phi.update",
    "DELETE": "phi.delete",
}

HTTP_ERROR_THRESHOLD: Final[int] = 400


class AuditLoggingMiddleware:
    """Log read access for HIPAA-aligned audit trails."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        exclude_prefixes: tuple[str, ...] = DEFAULT_EXCLUDED_PREFIXES,
    ) -> None:
        self.app = app
        self._exclude_prefixes = exclude_prefixes
        self._audit_service = AuditTrailService(SqlAlchemyAuditRepository())

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        if not self._should_audit(request):
            await self.app(scope, receive, send)
            return

        action = self._resolve_action(request.method)
        if action is None:
            await self.app(scope, receive, send)
            return

        status_code = 500
        audit_recorded = False

        async def record_audit_entry() -> None:
            nonlocal audit_recorded
            if audit_recorded:
                return

            context = get_audit_context(request)
            actor_id = _resolve_actor_id(request)
            details: JSONObject = {"status_code": status_code}
            success = status_code < HTTP_ERROR_THRESHOLD
            try:
                await asyncio.to_thread(
                    self._record_action,
                    action=action,
                    path=request.url.path,
                    actor_id=actor_id,
                    details=details,
                    context=context,
                    success=success,
                )
            except (
                Exception
            ):  # pragma: no cover - audit logging should never break requests
                logger.exception(
                    "Failed to record audit log for %s %s",
                    request.method,
                    request.url.path,
                )
            finally:
                audit_recorded = True

        async def audit_send(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                # Record the audit row when response headers are emitted so
                # long-lived streams are logged at request start, not finish.
                await record_audit_entry()
            await send(message)

        await self.app(scope, receive, audit_send)

    def _record_action(  # noqa: PLR0913 - audit persistence requires explicit fields
        self,
        *,
        action: str,
        path: str,
        actor_id: str | None,
        details: JSONObject,
        context: AuditContext,
        success: bool,
    ) -> None:
        db = SessionLocal()
        set_session_rls_context(db, bypass_rls=True)
        try:
            self._audit_service.record_action(
                db,
                action=action,
                target=("http_request", path),
                actor_id=actor_id,
                details=details,
                context=context,
                success=success,
            )
        finally:
            db.close()

    def _should_audit(self, request: Request) -> bool:
        method = request.method.upper()
        if method not in READ_METHODS and method not in MUTATION_ACTIONS:
            return False
        path = request.url.path
        return not any(path.startswith(prefix) for prefix in self._exclude_prefixes)

    @staticmethod
    def _resolve_action(method: str) -> str | None:
        normalized_method = method.upper()
        if normalized_method in READ_METHODS:
            return "phi.read"
        return MUTATION_ACTIONS.get(normalized_method)


def _resolve_actor_id(request: Request) -> str | None:
    state_user = getattr(request.state, "user", None)
    if isinstance(state_user, User):
        return str(state_user.id)
    return None


__all__ = ["AuditLoggingMiddleware"]
