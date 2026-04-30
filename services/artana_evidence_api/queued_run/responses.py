"""Accepted-response builders for queued harness runs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_api.queued_run.models import HarnessAcceptedRunResponse
from artana_evidence_api.queued_run.urls import (
    artifacts_url,
    events_url,
    progress_url,
    workspace_url,
)
from artana_evidence_api.response_serialization import serialize_run_record
from artana_evidence_api.types.common import JSONObject

if TYPE_CHECKING:
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry


def build_accepted_run_response(
    *,
    run: HarnessRunRecord,
    run_registry: HarnessRunRegistry | None = None,
    stream_url: str | None = None,
    session: JSONObject | None = None,
) -> HarnessAcceptedRunResponse:
    """Build the generic accepted response for one queued run."""
    current_run = (
        run_registry.get_run(space_id=run.space_id, run_id=run.id)
        if run_registry is not None
        else None
    )
    response_run = current_run or run
    return HarnessAcceptedRunResponse(
        run=serialize_run_record(run=response_run),
        progress_url=progress_url(
            space_id=response_run.space_id,
            run_id=response_run.id,
        ),
        events_url=events_url(space_id=response_run.space_id, run_id=response_run.id),
        workspace_url=workspace_url(
            space_id=response_run.space_id,
            run_id=response_run.id,
        ),
        artifacts_url=artifacts_url(
            space_id=response_run.space_id,
            run_id=response_run.id,
        ),
        stream_url=stream_url,
        session=session,
    )


__all__ = ["build_accepted_run_response"]
