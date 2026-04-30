"""SQLAlchemy-backed durable stores for graph-harness runtime state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID

from artana_evidence_api.approval_store import (
    HarnessApprovalAction,
    HarnessApprovalRecord,
    HarnessApprovalStore,
    HarnessRunIntentRecord,
    normalize_approval_action,
    normalize_approval_title,
)
from artana_evidence_api.models import (
    HarnessApprovalModel,
    HarnessChatMessageModel,
    HarnessChatSessionModel,
    HarnessDocumentModel,
    HarnessGraphSnapshotModel,
    HarnessIntentModel,
    HarnessProposalModel,
    HarnessResearchStateModel,
    HarnessReviewItemModel,
    HarnessScheduleModel,
)
from artana_evidence_api.models.research_space import (
    MembershipRoleEnum,
    ResearchSpaceMembershipModel,
    ResearchSpaceModel,
    SpaceStatusEnum,
)
from artana_evidence_api.models.user import HarnessUserModel
from artana_evidence_api.research_space_store import (
    PERSONAL_DEFAULT_SETTING_KEY,
    PERSONAL_DEFAULT_SPACE_DESCRIPTION,
    PERSONAL_DEFAULT_SPACE_NAME,
    HarnessResearchSpaceRecord,
    HarnessResearchSpaceStore,
    HarnessSpaceMemberRecord,
    HarnessUserIdentityConflictError,
    build_unique_space_slug,
)
from artana_evidence_api.schedule_policy import normalize_schedule_cadence
from artana_evidence_api.space_sync_types import (
    SpaceLifecycleSyncPort,
    graph_sync_space_from_model,
)
from artana_evidence_api.sqlalchemy_unit_of_work import commit_or_flush
from artana_evidence_api.types.common import json_object_or_empty
from sqlalchemy import delete, func, select, update

from .chat_sessions import (
    HarnessChatMessageRecord,
    HarnessChatSessionRecord,
    HarnessChatSessionStore,
)
from .document_store import (
    HarnessDocumentRecord,
    HarnessDocumentStore,
    normalize_document_title,
)
from .graph_snapshot import (
    HarnessGraphSnapshotRecord,
    HarnessGraphSnapshotStore,
)
from .proposal_store import (
    HarnessProposalDraft,
    HarnessProposalRecord,
    HarnessProposalStore,
)
from .research_state import (
    HarnessResearchStateRecord,
    HarnessResearchStateStore,
)
from .review_item_store import (
    HarnessReviewItemDraft,
    HarnessReviewItemRecord,
    HarnessReviewItemStore,
)
from .schedule_store import (
    HarnessScheduleRecord,
    HarnessScheduleStore,
)

_ASSIGNABLE_MEMBER_ROLE_VALUES = frozenset(
    role.value for role in MembershipRoleEnum if role is not MembershipRoleEnum.OWNER
)

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject, ResearchSpaceSettings
    from sqlalchemy.orm import Session


def _json_object(value: object) -> JSONObject:
    return value if isinstance(value, dict) else {}


def _json_object_list(value: object) -> list[JSONObject]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _result_rowcount(result: object) -> int:
    rowcount = getattr(result, "rowcount", 0)
    return rowcount if isinstance(rowcount, int) else 0


def _normalize_assignable_member_role(role: str) -> str:
    normalized_role = role.strip().lower()
    if normalized_role == "":
        msg = f"Invalid space member role: {role!r}"
        raise ValueError(msg)
    try:
        resolved_role = MembershipRoleEnum(normalized_role)
    except ValueError as exc:
        msg = f"Invalid space member role: {role!r}"
        raise ValueError(msg) from exc
    if resolved_role.value not in _ASSIGNABLE_MEMBER_ROLE_VALUES:
        msg = f"Invalid space member role: {role!r}"
        raise ValueError(msg)
    return resolved_role.value


def _json_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized_values: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if normalized == "":
            continue
        normalized_values.append(normalized)
    return normalized_values


def _normalized_utc_datetime(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC).replace(tzinfo=None)
    normalized = (
        value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    )
    return normalized.replace(tzinfo=None)


def _normalize_owner_text(
    value: str | None,
    *,
    fallback: str,
    max_length: int | None = None,
) -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized != "":
            return normalized[:max_length] if max_length is not None else normalized
    return fallback[:max_length] if max_length is not None else fallback


def _is_personal_default_space(model: ResearchSpaceModel) -> bool:
    settings = _json_object(model.settings)
    flag = settings.get(PERSONAL_DEFAULT_SETTING_KEY)
    if isinstance(flag, bool):
        return flag
    if isinstance(flag, str):
        return flag.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _personal_default_slug(owner_id: UUID) -> str:
    # Use the full UUID hex so personal default slugs remain globally unique
    # even when callers share the same leading UUID prefix.
    return f"personal-{owner_id.hex}"


def _action_payload(action: HarnessApprovalAction) -> JSONObject:
    normalized_action = normalize_approval_action(action)
    return {
        "approval_key": normalized_action.approval_key,
        "title": normalized_action.title,
        "risk_level": normalized_action.risk_level,
        "target_type": normalized_action.target_type,
        "target_id": normalized_action.target_id,
        "requires_approval": normalized_action.requires_approval,
        "metadata": normalized_action.metadata,
    }


def _action_from_payload(payload: object) -> HarnessApprovalAction | None:
    if not isinstance(payload, dict):
        return None
    approval_key = payload.get("approval_key")
    title = payload.get("title")
    risk_level = payload.get("risk_level")
    target_type = payload.get("target_type")
    requires_approval = payload.get("requires_approval")
    if not (
        isinstance(approval_key, str)
        and isinstance(title, str)
        and isinstance(risk_level, str)
        and isinstance(target_type, str)
        and isinstance(requires_approval, bool)
    ):
        return None
    target_id = payload.get("target_id")
    normalized_target_id = target_id if isinstance(target_id, str) else None
    metadata = payload.get("metadata")
    return HarnessApprovalAction(
        approval_key=approval_key,
        title=normalize_approval_title(title),
        risk_level=risk_level,
        target_type=target_type,
        target_id=normalized_target_id,
        requires_approval=requires_approval,
        metadata=_json_object(metadata),
    )


def _intent_record_from_model(model: HarnessIntentModel) -> HarnessRunIntentRecord:
    actions = tuple(
        action
        for action in (
            _action_from_payload(payload)
            for payload in _json_object_list(model.proposed_actions_payload)
        )
        if action is not None
    )
    return HarnessRunIntentRecord(
        space_id=model.space_id,
        run_id=model.run_id,
        summary=model.summary,
        proposed_actions=actions,
        metadata=_json_object(model.metadata_payload),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _approval_record_from_model(model: HarnessApprovalModel) -> HarnessApprovalRecord:
    return HarnessApprovalRecord(
        space_id=model.space_id,
        run_id=model.run_id,
        approval_key=model.approval_key,
        title=model.title,
        risk_level=model.risk_level,
        target_type=model.target_type,
        target_id=model.target_id,
        status=model.status,
        decision_reason=model.decision_reason,
        metadata=_json_object(model.metadata_payload),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _chat_session_record_from_model(
    model: HarnessChatSessionModel,
) -> HarnessChatSessionRecord:
    return HarnessChatSessionRecord(
        id=model.id,
        space_id=model.space_id,
        title=model.title,
        created_by=model.created_by,
        last_run_id=model.last_run_id,
        status=model.status,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _chat_message_record_from_model(
    model: HarnessChatMessageModel,
) -> HarnessChatMessageRecord:
    return HarnessChatMessageRecord(
        id=model.id,
        session_id=model.session_id,
        space_id=model.space_id,
        role=model.role,
        content=model.content,
        run_id=model.run_id,
        metadata=_json_object(model.metadata_payload),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _proposal_record_from_model(model: HarnessProposalModel) -> HarnessProposalRecord:
    return HarnessProposalRecord(
        id=model.id,
        space_id=model.space_id,
        run_id=model.run_id,
        proposal_type=model.proposal_type,
        source_kind=model.source_kind,
        source_key=model.source_key,
        document_id=model.document_id,
        title=model.title,
        summary=model.summary,
        status=model.status,
        confidence=model.confidence,
        ranking_score=model.ranking_score,
        reasoning_path=_json_object(model.reasoning_path),
        evidence_bundle=_json_object_list(model.evidence_bundle_payload),
        payload=_json_object(model.payload),
        metadata=_json_object(model.metadata_payload),
        decision_reason=model.decision_reason,
        decided_at=model.decided_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
        claim_fingerprint=getattr(model, "claim_fingerprint", None),
    )


def _review_item_record_from_model(
    model: HarnessReviewItemModel,
) -> HarnessReviewItemRecord:
    return HarnessReviewItemRecord(
        id=model.id,
        space_id=model.space_id,
        run_id=model.run_id,
        review_type=model.review_type,
        source_family=model.source_family,
        source_kind=model.source_kind,
        source_key=model.source_key,
        document_id=model.document_id,
        title=model.title,
        summary=model.summary,
        priority=model.priority,
        status=model.status,
        confidence=model.confidence,
        ranking_score=model.ranking_score,
        evidence_bundle=_json_object_list(model.evidence_bundle_payload),
        payload=_json_object(model.payload),
        metadata=_json_object(model.metadata_payload),
        decision_reason=model.decision_reason,
        decided_at=model.decided_at,
        linked_proposal_id=model.linked_proposal_id,
        linked_approval_key=model.linked_approval_key,
        created_at=model.created_at,
        updated_at=model.updated_at,
        review_fingerprint=model.review_fingerprint,
    )


def _document_record_from_model(model: HarnessDocumentModel) -> HarnessDocumentRecord:
    return HarnessDocumentRecord(
        id=model.id,
        space_id=model.space_id,
        created_by=model.created_by,
        title=model.title,
        source_type=model.source_type,
        filename=model.filename,
        media_type=model.media_type,
        sha256=model.sha256,
        byte_size=model.byte_size,
        page_count=model.page_count,
        text_content=model.text_content,
        text_excerpt=model.text_excerpt,
        raw_storage_key=model.raw_storage_key,
        enriched_storage_key=model.enriched_storage_key,
        ingestion_run_id=model.ingestion_run_id,
        last_enrichment_run_id=model.last_enrichment_run_id,
        last_extraction_run_id=model.last_extraction_run_id,
        enrichment_status=model.enrichment_status,
        extraction_status=model.extraction_status,
        metadata=_json_object(model.metadata_payload),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _schedule_record_from_model(model: HarnessScheduleModel) -> HarnessScheduleRecord:
    return HarnessScheduleRecord(
        id=model.id,
        space_id=model.space_id,
        harness_id=model.harness_id,
        title=model.title,
        cadence=model.cadence,
        status=model.status,
        created_by=model.created_by,
        configuration=_json_object(model.configuration_payload),
        metadata=_json_object(model.metadata_payload),
        last_run_id=model.last_run_id,
        last_run_at=model.last_run_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
        active_trigger_claim_id=model.active_trigger_claim_id,
        active_trigger_claimed_at=model.active_trigger_claimed_at,
    )


def _research_state_record_from_model(
    model: HarnessResearchStateModel,
) -> HarnessResearchStateRecord:
    return HarnessResearchStateRecord(
        space_id=model.space_id,
        objective=model.objective,
        current_hypotheses=_json_string_list(model.current_hypotheses_payload),
        explored_questions=_json_string_list(model.explored_questions_payload),
        pending_questions=_json_string_list(model.pending_questions_payload),
        last_graph_snapshot_id=model.last_graph_snapshot_id,
        last_learning_cycle_at=model.last_learning_cycle_at,
        active_schedules=_json_string_list(model.active_schedules_payload),
        confidence_model=_json_object(model.confidence_model_payload),
        budget_policy=_json_object(model.budget_policy_payload),
        metadata=_json_object(model.metadata_payload),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _graph_snapshot_record_from_model(
    model: HarnessGraphSnapshotModel,
) -> HarnessGraphSnapshotRecord:
    return HarnessGraphSnapshotRecord(
        id=model.id,
        space_id=model.space_id,
        source_run_id=model.source_run_id,
        claim_ids=_json_string_list(model.claim_ids_payload),
        relation_ids=_json_string_list(model.relation_ids_payload),
        graph_document_hash=model.graph_document_hash,
        summary=_json_object(model.summary_payload),
        metadata=_json_object(model.metadata_payload),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _as_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _research_space_record_from_model(
    model: ResearchSpaceModel,
    *,
    role: str,
) -> HarnessResearchSpaceRecord:
    return HarnessResearchSpaceRecord(
        id=str(model.id),
        slug=model.slug,
        name=model.name,
        description=model.description,
        status=model.status.value,
        role=role,
        is_default=_is_personal_default_space(model),
        settings=(
            cast("ResearchSpaceSettings", model.settings)
            if isinstance(model.settings, dict)
            else None
        ),
    )


class _SessionBackedStore:
    """Common session accessor for durable harness stores."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            message = "Session not provided"
            raise ValueError(message)
        return self._session


class SqlAlchemyHarnessApprovalStore(HarnessApprovalStore, _SessionBackedStore):
    """Persist harness intent plans and approval decisions in relational storage."""

    def __init__(self, session: Session | None = None) -> None:
        _SessionBackedStore.__init__(self, session)

    def upsert_intent(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        summary: str,
        proposed_actions: tuple[HarnessApprovalAction, ...],
        metadata: JSONObject,
    ) -> HarnessRunIntentRecord:
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        normalized_actions = tuple(
            normalize_approval_action(action) for action in proposed_actions
        )
        model = self.session.get(HarnessIntentModel, normalized_run_id)
        if model is None:
            model = HarnessIntentModel(
                run_id=normalized_run_id,
                space_id=normalized_space_id,
                summary=summary,
                proposed_actions_payload=[
                    _action_payload(action) for action in normalized_actions
                ],
                metadata_payload=metadata,
            )
            self.session.add(model)
        else:
            model.space_id = normalized_space_id
            model.summary = summary
            model.proposed_actions_payload = [
                _action_payload(action) for action in normalized_actions
            ]
            model.metadata_payload = metadata

        self.session.execute(
            delete(HarnessApprovalModel).where(
                HarnessApprovalModel.run_id == normalized_run_id,
            ),
        )
        for action in normalized_actions:
            if not action.requires_approval:
                continue
            self.session.add(
                HarnessApprovalModel(
                    run_id=normalized_run_id,
                    space_id=normalized_space_id,
                    approval_key=action.approval_key,
                    title=action.title,
                    risk_level=action.risk_level,
                    target_type=action.target_type,
                    target_id=action.target_id,
                    status="pending",
                    decision_reason=None,
                    metadata_payload=action.metadata,
                ),
            )

        self.session.commit()
        self.session.refresh(model)
        return _intent_record_from_model(model)

    def get_intent(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessRunIntentRecord | None:
        model = self.session.get(HarnessIntentModel, str(run_id))
        if model is None or model.space_id != str(space_id):
            return None
        return _intent_record_from_model(model)

    def list_approvals(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> list[HarnessApprovalRecord]:
        stmt = (
            select(HarnessApprovalModel)
            .where(
                HarnessApprovalModel.space_id == str(space_id),
                HarnessApprovalModel.run_id == str(run_id),
            )
            .order_by(HarnessApprovalModel.created_at.asc())
        )
        models = self.session.execute(stmt).scalars().all()
        return [_approval_record_from_model(model) for model in models]

    def list_space_approvals(
        self,
        *,
        space_id: UUID | str,
        status: str | None = None,
        run_id: UUID | str | None = None,
    ) -> list[HarnessApprovalRecord]:
        stmt = select(HarnessApprovalModel).where(
            HarnessApprovalModel.space_id == str(space_id),
        )
        if isinstance(status, str) and status.strip() != "":
            stmt = stmt.where(HarnessApprovalModel.status == status.strip())
        if run_id is not None:
            stmt = stmt.where(HarnessApprovalModel.run_id == str(run_id))
        stmt = stmt.order_by(HarnessApprovalModel.updated_at.desc())
        models = self.session.execute(stmt).scalars().all()
        return [_approval_record_from_model(model) for model in models]

    def decide_approval(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        approval_key: str,
        status: str,
        decision_reason: str | None,
    ) -> HarnessApprovalRecord | None:
        normalized_status = status.strip().lower()
        if normalized_status not in {"approved", "rejected"}:
            message = f"Unsupported approval status '{status}'"
            raise ValueError(message)
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        normalized_reason = (
            decision_reason.strip()
            if isinstance(decision_reason, str) and decision_reason.strip() != ""
            else None
        )
        status_stmt = select(HarnessApprovalModel.status).where(
            HarnessApprovalModel.space_id == normalized_space_id,
            HarnessApprovalModel.run_id == normalized_run_id,
            HarnessApprovalModel.approval_key == approval_key,
        )
        current_status = self.session.execute(status_stmt).scalars().first()
        if current_status is None:
            return None
        if current_status != "pending":
            message = (
                f"Approval '{approval_key}' is already decided with status "
                f"'{current_status}'"
            )
            raise ValueError(message)
        update_result = self.session.execute(
            update(HarnessApprovalModel)
            .where(
                HarnessApprovalModel.space_id == normalized_space_id,
                HarnessApprovalModel.run_id == normalized_run_id,
                HarnessApprovalModel.approval_key == approval_key,
                HarnessApprovalModel.status == "pending",
            )
            .values(
                status=normalized_status,
                decision_reason=normalized_reason,
            ),
        )
        if _result_rowcount(update_result) != 1:
            refreshed_status = self.session.execute(status_stmt).scalars().first()
            if refreshed_status is None:
                return None
            message = (
                f"Approval '{approval_key}' is already decided with status "
                f"'{refreshed_status}'"
            )
            raise ValueError(message)
        self.session.commit()
        stmt = select(HarnessApprovalModel).where(
            HarnessApprovalModel.space_id == normalized_space_id,
            HarnessApprovalModel.run_id == normalized_run_id,
            HarnessApprovalModel.approval_key == approval_key,
        )
        model = self.session.execute(stmt).scalars().first()
        if model is None:
            return None
        return _approval_record_from_model(model)


class SqlAlchemyHarnessProposalStore(HarnessProposalStore, _SessionBackedStore):
    """Persist harness proposals in relational storage."""

    def __init__(self, session: Session | None = None) -> None:
        _SessionBackedStore.__init__(self, session)

    def create_proposals(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        proposals: tuple[HarnessProposalDraft, ...],
    ) -> list[HarnessProposalRecord]:
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        created_models: list[HarnessProposalModel] = []
        for proposal in proposals:
            normalized_proposal = self.normalize_proposal_draft(proposal)
            # Fingerprint-based dedup: skip if an existing pending/promoted
            # proposal has the same fingerprint in this space.
            if normalized_proposal.claim_fingerprint:
                dup_stmt = (
                    select(HarnessProposalModel.id, HarnessProposalModel.status)
                    .where(
                        HarnessProposalModel.space_id == normalized_space_id,
                        HarnessProposalModel.claim_fingerprint
                        == normalized_proposal.claim_fingerprint,
                        HarnessProposalModel.status.in_(["pending_review", "promoted"]),
                    )
                    .limit(1)
                )
                existing = self.session.execute(dup_stmt).first()
                if existing is not None:
                    continue  # skip duplicate

            model = HarnessProposalModel(
                space_id=normalized_space_id,
                run_id=normalized_run_id,
                proposal_type=normalized_proposal.proposal_type,
                source_kind=normalized_proposal.source_kind,
                source_key=normalized_proposal.source_key,
                document_id=normalized_proposal.document_id,
                title=normalized_proposal.title,
                summary=normalized_proposal.summary,
                status="pending_review",
                confidence=normalized_proposal.confidence,
                ranking_score=normalized_proposal.ranking_score,
                reasoning_path=normalized_proposal.reasoning_path,
                evidence_bundle_payload=normalized_proposal.evidence_bundle,
                payload=normalized_proposal.payload,
                metadata_payload=normalized_proposal.metadata,
                claim_fingerprint=normalized_proposal.claim_fingerprint,
                decision_reason=None,
                decided_at=None,
            )
            self.session.add(model)
            created_models.append(model)
        self.session.commit()
        for model in created_models:
            self.session.refresh(model)
        return sorted(
            [_proposal_record_from_model(model) for model in created_models],
            key=lambda record: (-record.ranking_score, record.created_at),
        )

    def list_proposals(
        self,
        *,
        space_id: UUID | str,
        status: str | None = None,
        proposal_type: str | None = None,
        run_id: UUID | str | None = None,
        document_id: UUID | str | None = None,
    ) -> list[HarnessProposalRecord]:
        stmt = select(HarnessProposalModel).where(
            HarnessProposalModel.space_id == str(space_id),
        )
        if isinstance(status, str) and status.strip() != "":
            stmt = stmt.where(HarnessProposalModel.status == status.strip())
        if isinstance(proposal_type, str) and proposal_type.strip() != "":
            stmt = stmt.where(
                HarnessProposalModel.proposal_type == proposal_type.strip(),
            )
        if run_id is not None:
            stmt = stmt.where(HarnessProposalModel.run_id == str(run_id))
        if document_id is not None:
            stmt = stmt.where(HarnessProposalModel.document_id == str(document_id))
        stmt = stmt.order_by(
            HarnessProposalModel.ranking_score.desc(),
            HarnessProposalModel.updated_at.desc(),
        )
        models = self.session.execute(stmt).scalars().all()
        return [_proposal_record_from_model(model) for model in models]

    def count_proposals(
        self,
        *,
        space_id: UUID | str,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(HarnessProposalModel)
            .where(
                HarnessProposalModel.space_id == str(space_id),
            )
        )
        return int(self.session.execute(stmt).scalar_one())

    def get_proposal(
        self,
        *,
        space_id: UUID | str,
        proposal_id: UUID | str,
    ) -> HarnessProposalRecord | None:
        model = self.session.get(HarnessProposalModel, str(proposal_id))
        if model is None or model.space_id != str(space_id):
            return None
        return _proposal_record_from_model(model)

    def decide_proposal(
        self,
        *,
        space_id: UUID | str,
        proposal_id: UUID | str,
        status: str,
        decision_reason: str | None,
        metadata: JSONObject | None = None,
    ) -> HarnessProposalRecord | None:
        normalized_status = status.strip().lower()
        if normalized_status not in {"promoted", "rejected"}:
            message = f"Unsupported proposal status '{status}'"
            raise ValueError(message)
        normalized_space_id = str(space_id)
        normalized_proposal_id = str(proposal_id)
        status_stmt = select(
            HarnessProposalModel.status,
            HarnessProposalModel.metadata_payload,
        ).where(
            HarnessProposalModel.id == normalized_proposal_id,
            HarnessProposalModel.space_id == normalized_space_id,
        )
        status_row = self.session.execute(status_stmt).one_or_none()
        if status_row is None:
            return None
        current_status = status_row[0]
        if current_status != "pending_review":
            message = (
                f"Proposal '{proposal_id}' is already decided with status "
                f"'{current_status}'"
            )
            raise ValueError(message)
        decision_reason_text = (
            decision_reason.strip()
            if isinstance(decision_reason, str) and decision_reason.strip() != ""
            else None
        )
        decision_timestamp = datetime.now(UTC).replace(tzinfo=None)
        update_result = self.session.execute(
            update(HarnessProposalModel)
            .where(
                HarnessProposalModel.id == normalized_proposal_id,
                HarnessProposalModel.space_id == normalized_space_id,
                HarnessProposalModel.status == "pending_review",
            )
            .values(
                status=normalized_status,
                decision_reason=decision_reason_text,
                decided_at=decision_timestamp,
                metadata_payload={
                    **_json_object(status_row[1]),
                    **(metadata or {}),
                },
            ),
        )
        if _result_rowcount(update_result) != 1:
            refreshed_status_row = self.session.execute(status_stmt).one_or_none()
            if refreshed_status_row is None:
                return None
            message = (
                f"Proposal '{proposal_id}' is already decided with status "
                f"'{refreshed_status_row[0]}'"
            )
            raise ValueError(message)
        self.session.commit()
        refreshed_stmt = select(HarnessProposalModel).where(
            HarnessProposalModel.id == normalized_proposal_id,
            HarnessProposalModel.space_id == normalized_space_id,
        )
        model = self.session.execute(refreshed_stmt).scalars().first()
        if model is None:
            return None
        return _proposal_record_from_model(model)

    def reject_pending_duplicates(
        self,
        *,
        space_id: UUID | str,
        claim_fingerprint: str,
        exclude_id: UUID | str,
        reason: str,
    ) -> int:
        """Reject all pending_review proposals with the same fingerprint."""
        decision_timestamp = datetime.now(UTC).replace(tzinfo=None)
        result = self.session.execute(
            update(HarnessProposalModel)
            .where(
                HarnessProposalModel.space_id == str(space_id),
                HarnessProposalModel.claim_fingerprint == claim_fingerprint,
                HarnessProposalModel.status == "pending_review",
                HarnessProposalModel.id != str(exclude_id),
            )
            .values(
                status="rejected",
                decision_reason=reason,
                decided_at=decision_timestamp,
            ),
        )
        self.session.commit()
        return _result_rowcount(result)


from .sqlalchemy_review_document_stores import (  # noqa: E402,I001
    SqlAlchemyHarnessDocumentStore,
    SqlAlchemyHarnessReviewItemStore,
)
from .sqlalchemy_schedule_space_stores import (  # noqa: E402,I001
    SqlAlchemyHarnessResearchSpaceStore,
    SqlAlchemyHarnessScheduleStore,
)
from .sqlalchemy_state_chat_stores import (  # noqa: E402,I001
    SqlAlchemyHarnessChatSessionStore,
    SqlAlchemyHarnessGraphSnapshotStore,
    SqlAlchemyHarnessResearchStateStore,
)

__all__ = [
    "HarnessChatMessageRecord",
    "HarnessChatSessionRecord",
    "HarnessChatSessionStore",
    "HarnessDocumentRecord",
    "HarnessDocumentStore",
    "HarnessGraphSnapshotRecord",
    "HarnessGraphSnapshotStore",
    "HarnessResearchSpaceRecord",
    "HarnessResearchSpaceStore",
    "HarnessResearchStateRecord",
    "HarnessResearchStateStore",
    "HarnessReviewItemDraft",
    "HarnessReviewItemRecord",
    "HarnessReviewItemStore",
    "HarnessScheduleRecord",
    "HarnessScheduleStore",
    "HarnessSpaceMemberRecord",
    "HarnessUserIdentityConflictError",
    "HarnessUserModel",
    "PERSONAL_DEFAULT_SPACE_DESCRIPTION",
    "PERSONAL_DEFAULT_SPACE_NAME",
    "PERSONAL_DEFAULT_SETTING_KEY",
    "ResearchSpaceMembershipModel",
    "ResearchSpaceModel",
    "SqlAlchemyHarnessApprovalStore",
    "SqlAlchemyHarnessChatSessionStore",
    "SqlAlchemyHarnessDocumentStore",
    "SqlAlchemyHarnessGraphSnapshotStore",
    "SqlAlchemyHarnessProposalStore",
    "SqlAlchemyHarnessResearchSpaceStore",
    "SqlAlchemyHarnessResearchStateStore",
    "SqlAlchemyHarnessReviewItemStore",
    "SqlAlchemyHarnessScheduleStore",
    "SpaceLifecycleSyncPort",
    "SpaceStatusEnum",
    "build_unique_space_slug",
    "commit_or_flush",
    "graph_sync_space_from_model",
    "json_object_or_empty",
    "normalize_document_title",
    "normalize_schedule_cadence",
]
