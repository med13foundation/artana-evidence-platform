"""SQLAlchemy research-state, graph-snapshot, and chat-session stores."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.sqlalchemy_stores import (
    HarnessChatMessageModel,
    HarnessChatMessageRecord,
    HarnessChatSessionModel,
    HarnessChatSessionRecord,
    HarnessChatSessionStore,
    HarnessGraphSnapshotModel,
    HarnessGraphSnapshotRecord,
    HarnessGraphSnapshotStore,
    HarnessResearchStateModel,
    HarnessResearchStateRecord,
    HarnessResearchStateStore,
    _chat_message_record_from_model,
    _chat_session_record_from_model,
    _graph_snapshot_record_from_model,
    _json_object,
    _json_string_list,
    _research_state_record_from_model,
    _SessionBackedStore,
)
from sqlalchemy import func, select

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject
    from sqlalchemy.orm import Session

class SqlAlchemyHarnessResearchStateStore(
    HarnessResearchStateStore,
    _SessionBackedStore,
):
    """Persist structured research state in relational storage."""

    def __init__(self, session: Session | None = None) -> None:
        _SessionBackedStore.__init__(self, session)

    def get_state(
        self,
        *,
        space_id: UUID | str,
    ) -> HarnessResearchStateRecord | None:
        model = self.session.get(HarnessResearchStateModel, str(space_id))
        if model is None:
            return None
        return _research_state_record_from_model(model)

    def upsert_state(  # noqa: C901, PLR0912, PLR0913
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
        normalized_objective = objective.strip() if isinstance(objective, str) else None
        if isinstance(normalized_objective, str) and normalized_objective == "":
            normalized_objective = None
        model = self.session.get(HarnessResearchStateModel, str(space_id))
        if model is None:
            model = HarnessResearchStateModel(
                space_id=str(space_id),
                objective=normalized_objective,
                current_hypotheses_payload=_json_string_list(current_hypotheses or []),
                explored_questions_payload=_json_string_list(explored_questions or []),
                pending_questions_payload=_json_string_list(pending_questions or []),
                last_graph_snapshot_id=(
                    str(last_graph_snapshot_id)
                    if last_graph_snapshot_id is not None
                    else None
                ),
                last_learning_cycle_at=last_learning_cycle_at,
                active_schedules_payload=_json_string_list(active_schedules or []),
                confidence_model_payload=confidence_model or {},
                budget_policy_payload=budget_policy or {},
                metadata_payload=metadata or {},
            )
            self.session.add(model)
        else:
            if objective is not None:
                model.objective = normalized_objective or None
            if current_hypotheses is not None:
                model.current_hypotheses_payload = _json_string_list(current_hypotheses)
            if explored_questions is not None:
                model.explored_questions_payload = _json_string_list(explored_questions)
            if pending_questions is not None:
                model.pending_questions_payload = _json_string_list(pending_questions)
            if last_graph_snapshot_id is not None:
                model.last_graph_snapshot_id = str(last_graph_snapshot_id)
            if last_learning_cycle_at is not None:
                model.last_learning_cycle_at = last_learning_cycle_at
            if active_schedules is not None:
                model.active_schedules_payload = _json_string_list(active_schedules)
            if confidence_model is not None:
                model.confidence_model_payload = confidence_model
            if budget_policy is not None:
                model.budget_policy_payload = budget_policy
            if metadata is not None:
                model.metadata_payload = {
                    **_json_object(model.metadata_payload),
                    **metadata,
                }
        self.session.commit()
        self.session.refresh(model)
        return _research_state_record_from_model(model)


class SqlAlchemyHarnessGraphSnapshotStore(
    HarnessGraphSnapshotStore,
    _SessionBackedStore,
):
    """Persist run-scoped graph snapshots in relational storage."""

    def __init__(self, session: Session | None = None) -> None:
        _SessionBackedStore.__init__(self, session)

    def create_snapshot(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        source_run_id: UUID | str,
        claim_ids: list[str],
        relation_ids: list[str],
        graph_document_hash: str,
        summary: JSONObject,
        metadata: JSONObject | None = None,
    ) -> HarnessGraphSnapshotRecord:
        model = HarnessGraphSnapshotModel(
            space_id=str(space_id),
            source_run_id=str(source_run_id),
            claim_ids_payload=_json_string_list(claim_ids),
            relation_ids_payload=_json_string_list(relation_ids),
            graph_document_hash=graph_document_hash.strip(),
            summary_payload=summary,
            metadata_payload=metadata or {},
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return _graph_snapshot_record_from_model(model)

    def get_snapshot(
        self,
        *,
        space_id: UUID | str,
        snapshot_id: UUID | str,
    ) -> HarnessGraphSnapshotRecord | None:
        model = self.session.get(HarnessGraphSnapshotModel, str(snapshot_id))
        if model is None or model.space_id != str(space_id):
            return None
        return _graph_snapshot_record_from_model(model)

    def list_snapshots(
        self,
        *,
        space_id: UUID | str,
        limit: int = 20,
    ) -> list[HarnessGraphSnapshotRecord]:
        stmt = (
            select(HarnessGraphSnapshotModel)
            .where(HarnessGraphSnapshotModel.space_id == str(space_id))
            .order_by(HarnessGraphSnapshotModel.created_at.desc())
            .limit(max(limit, 0))
        )
        models = self.session.execute(stmt).scalars().all()
        return [_graph_snapshot_record_from_model(model) for model in models]

    def count_snapshots(self, *, space_id: UUID | str) -> int:
        stmt = (
            select(func.count())
            .select_from(HarnessGraphSnapshotModel)
            .where(
                HarnessGraphSnapshotModel.space_id == str(space_id),
            )
        )
        return int(self.session.execute(stmt).scalar_one())


class SqlAlchemyHarnessChatSessionStore(HarnessChatSessionStore, _SessionBackedStore):
    """Persist chat sessions and messages in relational storage."""

    def __init__(self, session: Session | None = None) -> None:
        _SessionBackedStore.__init__(self, session)

    def create_session(
        self,
        *,
        space_id: UUID | str,
        title: str,
        created_by: UUID | str,
        status: str = "active",
    ) -> HarnessChatSessionRecord:
        model = HarnessChatSessionModel(
            space_id=str(space_id),
            title=title,
            created_by=str(created_by),
            last_run_id=None,
            status=status,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return _chat_session_record_from_model(model)

    def list_sessions(self, *, space_id: UUID | str) -> list[HarnessChatSessionRecord]:
        stmt = (
            select(HarnessChatSessionModel)
            .where(HarnessChatSessionModel.space_id == str(space_id))
            .order_by(HarnessChatSessionModel.updated_at.desc())
        )
        models = self.session.execute(stmt).scalars().all()
        return [_chat_session_record_from_model(model) for model in models]

    def count_sessions(self, *, space_id: UUID | str) -> int:
        stmt = (
            select(func.count())
            .select_from(HarnessChatSessionModel)
            .where(
                HarnessChatSessionModel.space_id == str(space_id),
            )
        )
        return int(self.session.execute(stmt).scalar_one())

    def get_session(
        self,
        *,
        space_id: UUID | str,
        session_id: UUID | str,
    ) -> HarnessChatSessionRecord | None:
        model = self.session.get(HarnessChatSessionModel, str(session_id))
        if model is None or model.space_id != str(space_id):
            return None
        return _chat_session_record_from_model(model)

    def list_messages(
        self,
        *,
        space_id: UUID | str,
        session_id: UUID | str,
    ) -> list[HarnessChatMessageRecord]:
        stmt = (
            select(HarnessChatMessageModel)
            .where(
                HarnessChatMessageModel.space_id == str(space_id),
                HarnessChatMessageModel.session_id == str(session_id),
            )
            .order_by(HarnessChatMessageModel.created_at.asc())
        )
        models = self.session.execute(stmt).scalars().all()
        return [_chat_message_record_from_model(model) for model in models]

    def add_message(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        session_id: UUID | str,
        role: str,
        content: str,
        run_id: UUID | str | None = None,
        metadata: JSONObject | None = None,
    ) -> HarnessChatMessageRecord | None:
        session_model = self.session.get(HarnessChatSessionModel, str(session_id))
        if session_model is None or session_model.space_id != str(space_id):
            return None
        message_model = HarnessChatMessageModel(
            session_id=str(session_id),
            space_id=str(space_id),
            role=role,
            content=content,
            run_id=str(run_id) if run_id is not None else None,
            metadata_payload=metadata or {},
        )
        self.session.add(message_model)
        if run_id is not None:
            session_model.last_run_id = str(run_id)
        self.session.commit()
        self.session.refresh(message_model)
        return _chat_message_record_from_model(message_model)

    def update_session(
        self,
        *,
        space_id: UUID | str,
        session_id: UUID | str,
        title: str | None = None,
        last_run_id: UUID | str | None = None,
        status: str | None = None,
    ) -> HarnessChatSessionRecord | None:
        model = self.session.get(HarnessChatSessionModel, str(session_id))
        if model is None or model.space_id != str(space_id):
            return None
        if isinstance(title, str) and title.strip() != "":
            model.title = title
        if last_run_id is not None:
            model.last_run_id = str(last_run_id)
        if isinstance(status, str) and status.strip() != "":
            model.status = status
        self.session.commit()
        self.session.refresh(model)
        return _chat_session_record_from_model(model)

