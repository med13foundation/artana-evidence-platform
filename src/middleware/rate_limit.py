"""Rate limiting middleware for Artana Resource Library API."""

import time
from collections import defaultdict
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp


class TokenBucket:
    """Token bucket implementation for rate limiting."""

    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize token bucket.

        Args:
            capacity: Maximum number of tokens (requests per window)
            refill_rate: Tokens added per second
        """
        self.capacity: int = capacity
        self.refill_rate: float = refill_rate
        self.tokens: float = float(capacity)
        self.last_refill: float = time.time()

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if successful."""
        self._refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True

        return False

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(float(self.capacity), self.tokens + tokens_to_add)
        self.last_refill = now


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce rate limiting."""

    def __init__(
        self,
        app: ASGIApp,
        exclude_paths: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.exclude_paths: list[str] = exclude_paths or ["/health/"]
        self.buckets: defaultdict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(
                capacity=100,
                refill_rate=10,
            ),  # 100 requests, 10 per second
        )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Process each request through rate limiting middleware."""

        # Skip rate limiting for excluded paths
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)

        # Get client identifier (IP address)
        client_ip = self._get_client_ip(request)

        # Get or create token bucket for this client
        bucket = self.buckets[client_ip]

        # Try to consume a token
        if not bucket.consume():
            # Rate limit exceeded
            retry_after = int((bucket.capacity - bucket.tokens) / bucket.refill_rate)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )

        # Add rate limit headers to response
        response = await call_next(request)

        # Add rate limit headers
        remaining = int(bucket.tokens)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Limit"] = str(bucket.capacity)
        response.headers["X-RateLimit-Reset"] = str(
            int(bucket.last_refill + bucket.capacity / bucket.refill_rate),
        )

        return response

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request."""
        # Check for forwarded headers (useful behind proxies)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in case of multiple
            return forwarded_for.split(",")[0].strip()

        # Check for other proxy headers
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fall back to direct client IP
        return getattr(request.client, "host", "unknown")


class EndpointRateLimitMiddleware(BaseHTTPMiddleware):
    """More granular rate limiting based on endpoint and HTTP method."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

        # Different limits for different endpoints
        self.endpoint_limits: dict[str, defaultdict[str, TokenBucket]] = {
            "GET": defaultdict(
                lambda: TokenBucket(capacity=200, refill_rate=20),
            ),  # 200 req, 20/sec
            "POST": defaultdict(
                lambda: TokenBucket(capacity=50, refill_rate=5),
            ),  # 50 req, 5/sec
            "PUT": defaultdict(
                lambda: TokenBucket(capacity=50, refill_rate=5),
            ),  # 50 req, 5/sec
            "DELETE": defaultdict(
                lambda: TokenBucket(capacity=20, refill_rate=2),
            ),  # 20 req, 2/sec
        }
        # Paths that should bypass endpoint-specific limits (method -> prefixes)
        self.method_exemptions: dict[str, tuple[str, ...]] = {
            "POST": (
                "/data-discovery/sessions",  # session creation is already gated upstream
            ),
        }

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Apply different rate limits based on HTTP method."""

        # Skip for health checks
        if request.url.path.startswith("/health/"):
            return await call_next(request)

        method = request.method
        if method not in self.endpoint_limits:
            return await call_next(request)

        exempt_prefixes = self.method_exemptions.get(method, ())
        if any(request.url.path.startswith(prefix) for prefix in exempt_prefixes):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        bucket = self.endpoint_limits[method][client_ip]

        if not bucket.consume():
            retry_after = int((bucket.capacity - bucket.tokens) / bucket.refill_rate)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for {method} requests. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)

        # Add rate limit headers
        remaining = int(bucket.tokens)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Limit"] = str(bucket.capacity)

        return response

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request."""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        return getattr(request.client, "host", "unknown")
