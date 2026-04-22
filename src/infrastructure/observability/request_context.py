from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Final
from uuid import uuid4

from fastapi import Request  # noqa: TC002 - Needed at runtime for FastAPI DI

from src.type_definitions.common import AuditContext  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

REQUEST_ID_HEADER: Final[str] = "X-Request-ID"
_REQUEST_ID_CONTEXT: ContextVar[str | None] = ContextVar(
    "artana_request_id",
    default=None,
)
_LOG_RECORD_FACTORY_STATE = {"installed": False}


def get_current_request_id() -> str | None:
    """Return the request ID bound to the current execution context."""
    return _REQUEST_ID_CONTEXT.get()


def bind_current_request_id(request_id: str) -> Token[str | None]:
    """Bind one request ID to the current execution context."""
    return _REQUEST_ID_CONTEXT.set(request_id)


def reset_current_request_id(token: Token[str | None]) -> None:
    """Restore the previous request ID binding."""
    _REQUEST_ID_CONTEXT.reset(token)


@contextmanager
def request_id_context(request_id: str) -> Iterator[None]:
    """Bind one request ID for the lifetime of the context manager."""
    token = bind_current_request_id(request_id)
    try:
        yield
    finally:
        reset_current_request_id(token)


def build_request_id_headers(
    headers: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return headers augmented with the current request ID when present."""
    resolved_headers = dict(headers or {})
    request_id = get_current_request_id()
    has_request_id_header = any(
        key.lower() == REQUEST_ID_HEADER.lower() for key in resolved_headers
    )
    if request_id and not has_request_id_header:
        resolved_headers[REQUEST_ID_HEADER] = request_id
    return resolved_headers


def install_request_id_log_record_factory() -> None:
    """Ensure log records carry and display the current request ID."""
    if _LOG_RECORD_FACTORY_STATE["installed"]:
        return

    previous_factory = logging.getLogRecordFactory()

    def _factory(*args: object, **kwargs: object) -> logging.LogRecord:
        record = previous_factory(*args, **kwargs)
        request_id = get_current_request_id()
        record.request_id = request_id or "-"
        if (
            request_id
            and isinstance(record.msg, str)
            and "[request_id=" not in record.msg
        ):
            record.msg = f"[request_id={request_id}] {record.msg}"
        return record

    logging.setLogRecordFactory(_factory)
    _LOG_RECORD_FACTORY_STATE["installed"] = True


def resolve_request_id(request: Request) -> str:
    """Resolve or generate a request ID for traceability."""
    header_id = request.headers.get(REQUEST_ID_HEADER)
    if header_id:
        return header_id

    state_id = getattr(request.state, "request_id", None)
    if isinstance(state_id, str) and state_id:
        return state_id

    context_id = get_current_request_id()
    if isinstance(context_id, str) and context_id:
        return context_id

    return uuid4().hex


def build_audit_context(request: Request) -> AuditContext:
    """Build request metadata for audit logging."""
    request_id = resolve_request_id(request)
    forwarded_for = request.headers.get("x-forwarded-for")
    ip_address: str | None
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    else:
        ip_address = request.client.host if request.client else None

    return {
        "request_id": request_id,
        "ip_address": ip_address,
        "user_agent": request.headers.get("user-agent"),
        "method": request.method,
        "path": request.url.path,
    }


def _merge_audit_context(request: Request, state_context: object) -> AuditContext:
    context = build_audit_context(request)
    if not isinstance(state_context, dict):
        return context

    request_id = state_context.get("request_id")
    if isinstance(request_id, str) and request_id:
        context["request_id"] = request_id

    ip_address = state_context.get("ip_address")
    if (
        isinstance(ip_address, str) or ip_address is None
    ) and "ip_address" in state_context:
        context["ip_address"] = ip_address

    user_agent = state_context.get("user_agent")
    if (
        isinstance(user_agent, str) or user_agent is None
    ) and "user_agent" in state_context:
        context["user_agent"] = user_agent

    method = state_context.get("method")
    if isinstance(method, str) and method:
        context["method"] = method

    path = state_context.get("path")
    if isinstance(path, str) and path:
        context["path"] = path

    return context


def get_audit_context(request: Request) -> AuditContext:
    """FastAPI dependency to provide audit context."""
    state_context = getattr(request.state, "audit_context", None)
    return _merge_audit_context(request, state_context)


__all__ = [
    "REQUEST_ID_HEADER",
    "bind_current_request_id",
    "build_audit_context",
    "build_request_id_headers",
    "get_audit_context",
    "get_current_request_id",
    "install_request_id_log_record_factory",
    "request_id_context",
    "reset_current_request_id",
    "resolve_request_id",
]


__all__ = ["REQUEST_ID_HEADER", "build_audit_context", "get_audit_context"]
