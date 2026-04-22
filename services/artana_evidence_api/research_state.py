"""Service-local research-state storage contracts for graph-harness workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID  # noqa: TC003

from artana_evidence_api.types.common import JSONObject  # noqa: TC001


def _normalized_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalized_string_list(values: list[str] | None) -> list[str]:
    if values is None:
        return []
    normalized_values: list[str] = []
    seen_values: set[str] = set()
    for value in values:
        normalized = value.strip()
        if normalized == "" or normalized in seen_values:
            continue
        normalized_values.append(normalized)
        seen_values.add(normalized)
    return normalized_values


@dataclass(frozen=True, slots=True)
class HarnessResearchStateRecord:
    """One structured research-memory snapshot for a research space."""

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


class HarnessResearchStateStore:
    """Store and update structured research state for one space."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._records: dict[str, HarnessResearchStateRecord] = {}

    def get_state(
        self,
        *,
        space_id: UUID | str,
    ) -> HarnessResearchStateRecord | None:
        """Return the current research-state snapshot for one space."""
        with self._lock:
            return self._records.get(str(space_id))

    def upsert_state(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        objective: str | None = None,
        current_hypotheses: list[str] | None = None,
        explored_questions: list[str] | None = None,
        pending_questions: list[str] | None = None,
        last_graph_snapshot_id: UUID | str | None = None,
        last_learning_cycle_at: datetime | None = None,
        active_schedules: list[str] | None = None,
        confidence_model: JSONObject | None = None,
        budget_policy: JSONObject | None = None,
        metadata: JSONObject | None = None,
    ) -> HarnessResearchStateRecord:
        """Create or replace the structured research state for one space."""
        normalized_space_id = str(space_id)
        now = datetime.now(UTC)
        with self._lock:
            existing = self._records.get(normalized_space_id)
            record = HarnessResearchStateRecord(
                space_id=normalized_space_id,
                objective=(
                    _normalized_text(objective)
                    if objective is not None
                    else (existing.objective if existing is not None else None)
                ),
                current_hypotheses=(
                    _normalized_string_list(current_hypotheses)
                    if current_hypotheses is not None
                    else (
                        list(existing.current_hypotheses)
                        if existing is not None
                        else []
                    )
                ),
                explored_questions=(
                    _normalized_string_list(explored_questions)
                    if explored_questions is not None
                    else (
                        list(existing.explored_questions)
                        if existing is not None
                        else []
                    )
                ),
                pending_questions=(
                    _normalized_string_list(pending_questions)
                    if pending_questions is not None
                    else (
                        list(existing.pending_questions) if existing is not None else []
                    )
                ),
                last_graph_snapshot_id=(
                    str(last_graph_snapshot_id)
                    if last_graph_snapshot_id is not None
                    else (
                        existing.last_graph_snapshot_id
                        if existing is not None
                        else None
                    )
                ),
                last_learning_cycle_at=(
                    last_learning_cycle_at
                    if last_learning_cycle_at is not None
                    else (
                        existing.last_learning_cycle_at
                        if existing is not None
                        else None
                    )
                ),
                active_schedules=(
                    _normalized_string_list(active_schedules)
                    if active_schedules is not None
                    else (
                        list(existing.active_schedules) if existing is not None else []
                    )
                ),
                confidence_model=(
                    confidence_model
                    if confidence_model is not None
                    else (
                        dict(existing.confidence_model) if existing is not None else {}
                    )
                ),
                budget_policy=(
                    budget_policy
                    if budget_policy is not None
                    else (dict(existing.budget_policy) if existing is not None else {})
                ),
                metadata=(
                    {
                        **(existing.metadata if existing is not None else {}),
                        **(metadata or {}),
                    }
                ),
                created_at=existing.created_at if existing is not None else now,
                updated_at=now,
            )
            self._records[normalized_space_id] = record
            return record


__all__ = [
    "HarnessResearchStateRecord",
    "HarnessResearchStateStore",
]
