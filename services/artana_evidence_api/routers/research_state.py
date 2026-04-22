"""Research-state read endpoint for retrieving current space research memory."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from artana_evidence_api.dependencies import (
    get_research_state_store,
    require_harness_space_read_access,
)
from artana_evidence_api.research_question_policy import (
    filter_repeated_directional_questions,
)
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from artana_evidence_api.research_state import HarnessResearchStateStore

router = APIRouter(tags=["research-state"])

_RESEARCH_STATE_STORE_DEPENDENCY = Depends(get_research_state_store)
_SPACE_READ_ACCESS_DEPENDENCY = Depends(require_harness_space_read_access)


class ResearchStateResponse(BaseModel):
    """Serialized structured research-state snapshot."""

    model_config = ConfigDict(strict=True)

    space_id: str
    objective: str | None
    current_hypotheses: list[str]
    explored_questions: list[str]
    pending_questions: list[str]
    last_graph_snapshot_id: str | None
    last_learning_cycle_at: datetime | None
    active_schedules: list[str]
    confidence_model: JSONObject
    budget_policy: JSONObject
    metadata: JSONObject
    created_at: datetime
    updated_at: datetime


@router.get(
    "/v1/spaces/{space_id}/research-state",
    response_model=ResearchStateResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the current research state for a space",
)
async def get_research_state(
    space_id: UUID,
    _access: None = _SPACE_READ_ACCESS_DEPENDENCY,
    research_state_store: HarnessResearchStateStore = _RESEARCH_STATE_STORE_DEPENDENCY,
) -> ResearchStateResponse:
    """Return the current research-state snapshot for the given space."""
    record = research_state_store.get_state(space_id=space_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No research state found for this space. Run a research bootstrap first.",
        )
    return ResearchStateResponse(
        space_id=record.space_id,
        objective=record.objective,
        current_hypotheses=list(record.current_hypotheses),
        explored_questions=list(record.explored_questions),
        pending_questions=filter_repeated_directional_questions(
            objective=record.objective,
            explored_questions=list(record.explored_questions),
            pending_questions=list(record.pending_questions),
            last_graph_snapshot_id=record.last_graph_snapshot_id,
        ),
        last_graph_snapshot_id=record.last_graph_snapshot_id,
        last_learning_cycle_at=record.last_learning_cycle_at,
        active_schedules=list(record.active_schedules),
        confidence_model=dict(record.confidence_model),
        budget_policy=dict(record.budget_policy),
        metadata=dict(record.metadata),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
