"""Response and wait outcome models for queued harness runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from artana_evidence_api.run_registry import HarnessRunRecord

from artana_evidence_api.types.common import JSONObject


class HarnessAcceptedRunResponse(BaseModel):
    """Generic accepted response when the sync wait budget expires."""

    model_config = ConfigDict(strict=True)

    run: JSONObject
    progress_url: str = Field(..., min_length=1)
    events_url: str = Field(..., min_length=1)
    workspace_url: str = Field(..., min_length=1)
    artifacts_url: str = Field(..., min_length=1)
    stream_url: str | None = None
    session: JSONObject | None = None


@dataclass(frozen=True, slots=True)
class QueuedRunWaitOutcome:
    """Result of waiting on a queued worker-owned run."""

    run: HarnessRunRecord | None
    timed_out: bool


__all__ = ["HarnessAcceptedRunResponse", "QueuedRunWaitOutcome"]
