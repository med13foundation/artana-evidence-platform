from __future__ import annotations

import os

DEFAULT_ALLOWED_ORIGINS: list[str] = [
    "https://med13foundation.org",
    "https://curate.med13foundation.org",
    "https://admin.med13foundation.org",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:8080",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:8080",
]


def _normalize_origin(origin: str) -> str:
    return origin.strip().rstrip("/")


def get_allowed_origins() -> list[str]:
    configured = os.getenv("ARTANA_ALLOWED_ORIGINS", "")
    origins = [_normalize_origin(origin) for origin in DEFAULT_ALLOWED_ORIGINS]

    for raw_origin in configured.split(","):
        origin = _normalize_origin(raw_origin)
        if origin and origin not in origins:
            origins.append(origin)

    return origins
