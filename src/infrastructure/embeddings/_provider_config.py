"""Environment parsing helpers for embedding-provider configuration."""

from __future__ import annotations

import os


def env_bool(name: str, *, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def env_int(name: str, *, default: int, minimum: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        parsed = int(raw_value.strip())
    except ValueError:
        return default
    return max(parsed, minimum)


def env_float(name: str, *, default: float, minimum: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        parsed = float(raw_value.strip())
    except ValueError:
        return default
    return max(parsed, minimum)


__all__ = ["env_bool", "env_float", "env_int"]
