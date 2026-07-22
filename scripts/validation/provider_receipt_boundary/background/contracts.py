"""Typed contracts for one background provider execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel

_OutputT = TypeVar("_OutputT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class BackgroundExecutionBudgets:
    acknowledgement_timeout_seconds: float
    polling_interval_seconds: float
    max_polling_seconds: float

    def __post_init__(self) -> None:
        for name, value in (
            ("acknowledgement_timeout_seconds", self.acknowledgement_timeout_seconds),
            ("polling_interval_seconds", self.polling_interval_seconds),
            ("max_polling_seconds", self.max_polling_seconds),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True, slots=True)
class BackgroundProviderExecution(Generic[_OutputT]):
    extraction: _OutputT
    canonical_payload: dict[str, object]
    acknowledgement_response: dict[str, object]
    terminal_response: dict[str, object]
    confirmation_response: dict[str, object]
    receipt: dict[str, object]


@dataclass(frozen=True, slots=True)
class PollingResult:
    terminal_response: dict[str, object]
    status_history: tuple[str, ...]
    retrieval_requests: int
    polling_seconds: float


__all__ = [
    "BackgroundExecutionBudgets",
    "BackgroundProviderExecution",
    "PollingResult",
]
