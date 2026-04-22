"""In-process API rate limiting for the standalone harness service."""

from __future__ import annotations

import hashlib
import math
import os
import threading
from dataclasses import dataclass, field
from enum import Enum
from time import monotonic
from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse

from .auth import _allow_test_auth_headers
from .request_context import REQUEST_ID_HEADER, resolve_request_id

if TYPE_CHECKING:
    from collections.abc import Mapping

    from starlette.requests import Request


_DEFAULT_GENERAL_REQUESTS_PER_WINDOW = 120
_DEFAULT_LLM_REQUESTS_PER_WINDOW = 30
_DEFAULT_WINDOW_SECONDS = 60.0
_HTTP_429_TOO_MANY_REQUESTS = 429
_POLLING_RUN_PATH_PATTERN = r"^/v1/spaces/[^/]+/runs/[^/]+(?:/progress)?$"
_LLM_HEAVY_PATH_MARKERS = (
    "/research-init",
    "/graph-search-runs",
    "/graph-connection-runs",
    "/continuous-learning-runs",
    "/research-bootstrap-runs",
    "/research-onboarding-runs",
    "/mechanism-discovery-runs",
    "/supervisor-runs",
    "/documents",
    "/chat",
    "/marrvel",
)
_PUBLIC_PATHS = frozenset({"/health", "/docs", "/redoc", "/openapi.json"})


class RateLimitTier(str, Enum):
    """Request buckets tracked by the harness limiter."""

    GENERAL = "general"
    LLM = "llm"


@dataclass(frozen=True, slots=True)
class RateLimitConfig:
    """Static rate limit thresholds for the harness service."""

    general_requests_per_window: int = _DEFAULT_GENERAL_REQUESTS_PER_WINDOW
    llm_requests_per_window: int = _DEFAULT_LLM_REQUESTS_PER_WINDOW
    window_seconds: float = _DEFAULT_WINDOW_SECONDS

    @classmethod
    def from_environment(cls) -> RateLimitConfig:
        """Build one limiter config from environment variables."""
        return cls(
            general_requests_per_window=_read_int_env(
                "ARTANA_EVIDENCE_API_RATE_LIMIT_GENERAL_PER_WINDOW",
                default=_DEFAULT_GENERAL_REQUESTS_PER_WINDOW,
            ),
            llm_requests_per_window=_read_int_env(
                "ARTANA_EVIDENCE_API_RATE_LIMIT_LLM_PER_WINDOW",
                default=_DEFAULT_LLM_REQUESTS_PER_WINDOW,
            ),
            window_seconds=_read_float_env(
                "ARTANA_EVIDENCE_API_RATE_LIMIT_WINDOW_SECONDS",
                default=_DEFAULT_WINDOW_SECONDS,
            ),
        )


@dataclass(slots=True)
class _WindowCounter:
    window_start: float
    request_count: int = 0


class RateLimitExceededError(Exception):
    """Raised when a request exceeds the configured threshold."""

    def __init__(
        self,
        *,
        tier: RateLimitTier,
        limit: int,
        retry_after_seconds: int,
    ) -> None:
        self.tier = tier
        self.limit = limit
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"Rate limit exceeded for {tier.value} requests. "
            f"Please retry after {retry_after_seconds} second(s).",
        )


@dataclass(frozen=True, slots=True)
class RateLimitStatus:
    """Snapshot of a caller's current rate-limit bucket after one request."""

    tier: RateLimitTier
    limit: int
    remaining: int
    reset_seconds: int


@dataclass(slots=True)
class InMemoryRateLimiter:
    """Thread-safe fixed-window limiter keyed by identity and tier."""

    config: RateLimitConfig = field(default_factory=RateLimitConfig.from_environment)
    _counters: dict[tuple[str, RateLimitTier], _WindowCounter] = field(
        default_factory=dict,
    )
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def allow(self, *, identity_key: str, tier: RateLimitTier) -> RateLimitStatus:
        """Record one request or raise when the bucket is exhausted.

        Returns a :class:`RateLimitStatus` snapshot so callers can attach
        ``X-RateLimit-*`` headers to successful responses.
        """
        limit = self._limit_for_tier(tier)
        if limit <= 0:
            return RateLimitStatus(tier=tier, limit=0, remaining=0, reset_seconds=0)

        now = monotonic()
        bucket_key = (identity_key, tier)
        with self._lock:
            self._purge_expired_counters(now=now)
            counter = self._counters.get(bucket_key)
            if counter is None:
                counter = _WindowCounter(window_start=now)
                self._counters[bucket_key] = counter
            reset_seconds = max(
                1,
                int(
                    math.ceil(
                        self.config.window_seconds - (now - counter.window_start),
                    ),
                ),
            )
            if counter.request_count >= limit:
                raise RateLimitExceededError(
                    tier=tier,
                    limit=limit,
                    retry_after_seconds=reset_seconds,
                )
            counter.request_count += 1
            remaining = max(0, limit - counter.request_count)
        return RateLimitStatus(
            tier=tier,
            limit=limit,
            remaining=remaining,
            reset_seconds=reset_seconds,
        )

    def _limit_for_tier(self, tier: RateLimitTier) -> int:
        if tier is RateLimitTier.LLM:
            return self.config.llm_requests_per_window
        return self.config.general_requests_per_window

    def _purge_expired_counters(self, *, now: float) -> None:
        expired_keys = [
            bucket_key
            for bucket_key, counter in self._counters.items()
            if (now - counter.window_start) >= self.config.window_seconds
        ]
        for bucket_key in expired_keys:
            del self._counters[bucket_key]


def _read_int_env(name: str, *, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return max(0, int(raw_value.strip()))
    except ValueError:
        return default


def _read_float_env(name: str, *, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return max(1.0, float(raw_value.strip()))
    except ValueError:
        return default


def _hash_identity(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def resolve_rate_limit_identity(
    headers: Mapping[str, str],
    *,
    client_host: str | None,
) -> str:
    """Return one stable bucket key for the current caller."""
    if _allow_test_auth_headers():
        test_user_id = headers.get("x-test-user-id")
        if isinstance(test_user_id, str) and test_user_id.strip() != "":
            return f"test-user:{test_user_id.strip()}"

    authorization = headers.get("authorization")
    if isinstance(authorization, str) and authorization.strip() != "":
        return f"authorization:{_hash_identity(authorization.strip())}"

    api_key = headers.get("x-artana-key")
    if isinstance(api_key, str) and api_key.strip() != "":
        return f"api-key:{_hash_identity(api_key.strip())}"

    if client_host is not None and client_host.strip() != "":
        return f"client:{client_host.strip()}"
    return "anonymous"


def classify_rate_limit_tier(path: str, method: str) -> RateLimitTier | None:
    """Return the rate-limit tier for one request path, or ``None`` if exempt."""
    if path in _PUBLIC_PATHS:
        return None
    if method.upper() == "GET" and _is_polling_run_path(path):
        return None
    if method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and _is_llm_heavy_path(
        path,
    ):
        return RateLimitTier.LLM
    return RateLimitTier.GENERAL


def maybe_rate_limit_request(
    request: Request,
    limiter: InMemoryRateLimiter,
) -> tuple[JSONResponse | None, RateLimitStatus | None]:
    """Enforce rate limits and return ``(response, status)``.

    When the caller is within limits the first element is ``None`` and the
    second is a :class:`RateLimitStatus` snapshot that the middleware should
    use to attach ``X-RateLimit-*`` headers to the downstream response.

    When the limit is exceeded the first element is a 429 JSON response
    (ready to return) and the second is ``None``.
    """
    tier = classify_rate_limit_tier(request.url.path, request.method)
    if tier is None:
        return None, None

    identity_key = resolve_rate_limit_identity(
        request.headers,
        client_host=request.client.host if request.client is not None else None,
    )
    try:
        rl_status = limiter.allow(identity_key=identity_key, tier=tier)
    except RateLimitExceededError as exc:
        request_id = resolve_request_id(request)
        return (
            JSONResponse(
                status_code=_HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": str(exc), "request_id": request_id},
                headers={
                    "Retry-After": str(exc.retry_after_seconds),
                    "X-RateLimit-Limit": str(exc.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(exc.retry_after_seconds),
                    REQUEST_ID_HEADER: request_id,
                },
            ),
            None,
        )
    return None, rl_status


def _is_polling_run_path(path: str) -> bool:
    import re

    return re.fullmatch(_POLLING_RUN_PATH_PATTERN, path) is not None


def _is_llm_heavy_path(path: str) -> bool:
    return any(marker in path for marker in _LLM_HEAVY_PATH_MARKERS)


def create_rate_limiter() -> InMemoryRateLimiter:
    """Build one limiter instance for a newly constructed app."""
    return InMemoryRateLimiter()


__all__ = [
    "InMemoryRateLimiter",
    "RateLimitConfig",
    "RateLimitExceededError",
    "RateLimitStatus",
    "RateLimitTier",
    "classify_rate_limit_tier",
    "create_rate_limiter",
    "maybe_rate_limit_request",
    "resolve_rate_limit_identity",
]
