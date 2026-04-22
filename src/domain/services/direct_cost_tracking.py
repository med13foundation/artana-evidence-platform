"""Shared direct-cost recorder primitives usable across architecture layers."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


@dataclass(frozen=True, slots=True)
class DirectCostUsage:
    """One directly observed provider usage record."""

    provider: str
    model_id: str
    operation: str
    cost_usd: float
    prompt_tokens: int
    completion_tokens: int
    stage: str | None = None


_ACTIVE_COST_USAGE_RECORDER: ContextVar[Callable[[DirectCostUsage], None] | None] = (
    ContextVar(
        "active_direct_cost_usage_recorder",
        default=None,
    )
)


@contextmanager
def activate_cost_usage_recorder(
    recorder: Callable[[DirectCostUsage], None],
) -> Iterator[None]:
    """Temporarily activate a direct-usage recorder for the current context."""
    token = _ACTIVE_COST_USAGE_RECORDER.set(recorder)
    try:
        yield
    finally:
        _ACTIVE_COST_USAGE_RECORDER.reset(token)


def get_active_cost_usage_recorder() -> Callable[[DirectCostUsage], None] | None:
    """Return the current direct-usage recorder, if one is active."""
    return _ACTIVE_COST_USAGE_RECORDER.get()


__all__ = [
    "DirectCostUsage",
    "activate_cost_usage_recorder",
    "get_active_cost_usage_recorder",
]
