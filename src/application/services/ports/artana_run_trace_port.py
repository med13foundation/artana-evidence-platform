"""Port interface for Artana run trace inspection."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from src.type_definitions.common import JSONObject, JSONValue


@dataclass(frozen=True, slots=True)
class ArtanaRunTraceEventRecord:
    """Normalized kernel event used for trace inspection."""

    seq: int
    event_id: str
    event_type: str
    timestamp: datetime
    parent_step_key: str | None
    payload: JSONObject
    tool_name: str | None = None
    tool_outcome: str | None = None
    step_key: str | None = None


@dataclass(frozen=True, slots=True)
class ArtanaRunTraceSummaryRecord:
    """Latest run-summary payload for one summary type."""

    summary_type: str
    timestamp: datetime
    step_key: str | None
    payload: JSONValue


@dataclass(frozen=True, slots=True)
class ArtanaRunTraceRecord:
    """Composite Artana run detail resolved through the public kernel API."""

    run_id: str
    tenant_id: str
    status: str
    last_event_seq: int | None
    last_event_type: str | None
    updated_at: datetime | None
    blocked_on: str | None
    failure_reason: str | None
    error_category: str | None
    progress_percent: int | None
    current_stage: str | None
    completed_stages: tuple[str, ...]
    started_at: datetime | None
    eta_seconds: int | None
    explain: JSONObject
    events: tuple[ArtanaRunTraceEventRecord, ...]
    summaries: tuple[ArtanaRunTraceSummaryRecord, ...]


class ArtanaRunTracePort(ABC):
    """Abstraction for reading Artana run status, events, and summaries."""

    @abstractmethod
    def get_run_trace(
        self,
        *,
        run_id: str,
        tenant_id: str,
    ) -> ArtanaRunTraceRecord | None:
        """Return normalized Artana trace detail for one run when accessible."""
        ...


__all__ = [
    "ArtanaRunTraceEventRecord",
    "ArtanaRunTracePort",
    "ArtanaRunTraceRecord",
    "ArtanaRunTraceSummaryRecord",
]
