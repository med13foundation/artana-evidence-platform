"""FastAPI application factory for the standalone harness service."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from .config import get_settings
from .database import engine
from .models.api_key import HarnessApiKeyModel
from .models.user import HarnessUserModel
from .rate_limits import create_rate_limiter, maybe_rate_limit_request
from .request_context import (
    REQUEST_ID_HEADER,
    bind_current_request_id,
    build_audit_context,
    install_request_id_log_record_factory,
    reset_current_request_id,
    resolve_request_id,
)
from .routers.approvals import router as approvals_router
from .routers.artifacts import router as artifacts_router
from .routers.authentication import router as authentication_router
from .routers.chat import router as chat_router
from .routers.continuous_learning_runs import (
    router as continuous_learning_runs_router,
)
from .routers.documents import router as documents_router
from .routers.full_ai_orchestrator_runs import (
    router as full_ai_orchestrator_runs_router,
)
from .routers.graph_connection_runs import router as graph_connection_runs_router
from .routers.graph_curation_runs import router as graph_curation_runs_router
from .routers.graph_explorer import router as graph_explorer_router
from .routers.graph_search_runs import router as graph_search_runs_router
from .routers.harnesses import router as harnesses_router
from .routers.health import router as health_router
from .routers.hypothesis_runs import router as hypothesis_runs_router
from .routers.marrvel import router as marrvel_router
from .routers.mechanism_discovery_runs import (
    router as mechanism_discovery_runs_router,
)
from .routers.proposals import router as proposals_router
from .routers.pubmed import router as pubmed_router
from .routers.research_bootstrap_runs import (
    router as research_bootstrap_runs_router,
)
from .routers.research_init import router as research_init_router
from .routers.research_onboarding_runs import (
    router as research_onboarding_runs_router,
)
from .routers.research_state import router as research_state_router
from .routers.review_queue import router as review_queue_router
from .routers.runs import router as runs_router
from .routers.schedules import router as schedules_router
from .routers.spaces import router as spaces_router
from .routers.supervisor_runs import router as supervisor_runs_router
from .runtime_skill_registry import validate_graph_harness_skill_configuration

logger = logging.getLogger(__name__)


def _normalize_error_detail(detail: object) -> str:
    """Coerce handler payloads into the string-only detail contract."""
    if isinstance(detail, dict):
        message = detail.get("message")
        if isinstance(message, str) and message.strip() != "":
            return message
        nested_detail = detail.get("detail")
        if isinstance(nested_detail, str) and nested_detail.strip() != "":
            return nested_detail
    if isinstance(detail, list):
        return "; ".join(str(item) for item in detail)
    return str(detail)


def _validation_error_detail(error: RequestValidationError) -> str:
    """Serialize validation failures into readable string messages."""

    def _format_validation_error(validation_error: dict[str, object]) -> str:
        message = str(validation_error.get("msg", "Validation error")).strip()
        if message.startswith("Value error, "):
            message = message.removeprefix("Value error, ").strip()
        location = validation_error.get("loc")
        if isinstance(location, tuple | list) and len(location) > 0:
            prefix = " -> ".join(str(part) for part in location)
            return f"{prefix}: {message or 'Validation error'}"
        return message or "Validation error"

    errors = error.errors()
    messages = [
        _format_validation_error(validation_error) for validation_error in errors
    ]
    deduplicated_messages = list(dict.fromkeys(messages))
    return (
        "; ".join(deduplicated_messages)
        if deduplicated_messages
        else "Validation error"
    )


@asynccontextmanager
async def _app_lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Ensure required auth tables exist when the app starts."""
    HarnessUserModel.__table__.create(bind=engine, checkfirst=True)
    HarnessApiKeyModel.__table__.create(bind=engine, checkfirst=True)
    yield


def create_app() -> FastAPI:  # noqa: PLR0915
    """Create the standalone harness API application."""
    validate_graph_harness_skill_configuration()
    install_request_id_log_record_factory()
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        docs_url="/docs",
        openapi_url=settings.openapi_url,
        lifespan=_app_lifespan,
    )
    app.state.rate_limiter = create_rate_limiter()

    @app.middleware("http")
    async def _rate_limit_middleware(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = resolve_request_id(request)
        request.state.request_id = request_id
        request.state.audit_context = build_audit_context(request)
        token = bind_current_request_id(request_id)
        try:
            limiter = app.state.rate_limiter
            rate_limit_response, rl_status = maybe_rate_limit_request(request, limiter)
            if rate_limit_response is not None:
                return rate_limit_response
            response = await call_next(request)
            response.headers.setdefault(REQUEST_ID_HEADER, request_id)
            if rl_status is not None:
                response.headers.setdefault("X-RateLimit-Limit", str(rl_status.limit))
                response.headers.setdefault(
                    "X-RateLimit-Remaining",
                    str(rl_status.remaining),
                )
                response.headers.setdefault(
                    "X-RateLimit-Reset",
                    str(rl_status.reset_seconds),
                )
            return response
        finally:
            reset_current_request_id(token)

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(
        request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        request_id = resolve_request_id(request)
        response_headers = dict(exc.headers or {})
        response_headers.setdefault(REQUEST_ID_HEADER, request_id)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": _normalize_error_detail(exc.detail),
                "request_id": request_id,
            },
            headers=response_headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        request_id = resolve_request_id(request)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "detail": _validation_error_detail(exc),
                "request_id": request_id,
            },
            headers={REQUEST_ID_HEADER: request_id},
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.error(
            "Unhandled harness request error",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        request_id = resolve_request_id(request)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error", "request_id": request_id},
            headers={REQUEST_ID_HEADER: request_id},
        )

    app.include_router(authentication_router)
    app.include_router(approvals_router)
    app.include_router(health_router)
    app.include_router(artifacts_router)
    app.include_router(chat_router)
    app.include_router(continuous_learning_runs_router)
    app.include_router(documents_router)
    app.include_router(full_ai_orchestrator_runs_router)
    app.include_router(graph_connection_runs_router)
    app.include_router(graph_curation_runs_router)
    app.include_router(graph_explorer_router)
    app.include_router(graph_search_runs_router)
    app.include_router(hypothesis_runs_router)
    app.include_router(mechanism_discovery_runs_router)
    app.include_router(harnesses_router)
    app.include_router(proposals_router)
    app.include_router(marrvel_router)
    app.include_router(pubmed_router)
    app.include_router(research_bootstrap_runs_router)
    app.include_router(research_init_router)
    app.include_router(research_onboarding_runs_router)
    app.include_router(research_state_router)
    app.include_router(review_queue_router)
    app.include_router(runs_router)
    app.include_router(schedules_router)
    app.include_router(spaces_router)
    app.include_router(supervisor_runs_router)

    return app


__all__ = ["create_app"]
