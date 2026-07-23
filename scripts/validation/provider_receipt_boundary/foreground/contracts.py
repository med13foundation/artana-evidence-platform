"""Typed contracts for a direct foreground Responses execution."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel

_OutputT = TypeVar("_OutputT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class ForegroundExecutionRuntime:
    """Injectable transport boundary for deterministic tests."""

    client: object | None = None
    monotonic: Callable[[], float] = time.monotonic
    on_completed: Callable[[str], None] | None = None


@dataclass(frozen=True, slots=True)
class ForegroundProviderExecution(Generic[_OutputT]):
    """Verified foreground output, confirmation, and receipt."""

    extraction: _OutputT
    canonical_payload: dict[str, object]
    creation_response: dict[str, object]
    confirmation_response: dict[str, object]
    receipt: dict[str, object]


__all__ = ["ForegroundExecutionRuntime", "ForegroundProviderExecution"]
