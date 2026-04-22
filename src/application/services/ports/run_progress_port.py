"""Port interface for runtime run-progress lookup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True)
class RunProgressSnapshot:
    """Normalized progress snapshot for one Artana run."""

    run_id: str
    status: str
    percent: int
    current_stage: str | None
    completed_stages: tuple[str, ...]
    started_at: datetime | None
    updated_at: datetime | None
    eta_seconds: int | None


class RunProgressPort(Protocol):
    """Abstraction for reading live run progress."""

    def get_run_progress(
        self,
        *,
        run_id: str,
        tenant_id: str,
    ) -> RunProgressSnapshot | None:
        """Return progress for `run_id` in `tenant_id`, or `None` when unavailable."""


__all__ = ["RunProgressPort", "RunProgressSnapshot"]
