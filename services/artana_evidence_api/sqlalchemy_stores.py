"""SQLAlchemy-backed durable stores for graph-harness runtime state."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
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
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError

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
from .schedule_policy import normalize_schedule_cadence
from .schedule_store import (
    HarnessScheduleRecord,
    HarnessScheduleStore,
)
from .space_sync_types import SpaceLifecycleSyncPort, graph_sync_space_from_model

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


def _normalize_assignable_member_role(role: str) -> str:
    if not isinstance(role, str):
        msg = f"Invalid space member role: {role!r}"
        raise TypeError(msg)
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
        settings=model.settings if isinstance(model.settings, dict) else None,
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
        if update_result.rowcount != 1:
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
        if update_result.rowcount != 1:
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
        return result.rowcount


class SqlAlchemyHarnessReviewItemStore(HarnessReviewItemStore, _SessionBackedStore):
    """Persist harness review-only items in relational storage."""

    def __init__(self, session: Session | None = None) -> None:
        _SessionBackedStore.__init__(self, session)

    def _find_existing_review_item_model(
        self,
        *,
        space_id: str,
        review_item: HarnessReviewItemDraft,
    ) -> HarnessReviewItemModel | None:
        stmt = select(HarnessReviewItemModel).where(
            HarnessReviewItemModel.space_id == space_id,
        )
        if review_item.review_fingerprint is not None:
            stmt = stmt.where(
                HarnessReviewItemModel.review_fingerprint
                == review_item.review_fingerprint,
            )
        else:
            stmt = stmt.where(
                HarnessReviewItemModel.review_type == review_item.review_type,
                HarnessReviewItemModel.source_key == review_item.source_key,
            )
        models = (
            self.session.execute(
                stmt.order_by(HarnessReviewItemModel.updated_at.desc()),
            )
            .scalars()
            .all()
        )
        preferred_match = next(
            (model for model in models if model.status == "pending_review"),
            None,
        )
        if preferred_match is not None:
            return preferred_match
        return models[0] if models else None

    def create_review_items(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        review_items: tuple[HarnessReviewItemDraft, ...],
    ) -> list[HarnessReviewItemRecord]:
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        effective_models: list[HarnessReviewItemModel] = []
        for review_item in review_items:
            normalized_item = self.normalize_review_item_draft(review_item)
            existing_model = self._find_existing_review_item_model(
                space_id=normalized_space_id,
                review_item=normalized_item,
            )
            if existing_model is not None:
                effective_models.append(existing_model)
                continue
            try:
                with self.session.begin_nested():
                    model = HarnessReviewItemModel(
                        space_id=normalized_space_id,
                        run_id=normalized_run_id,
                        review_type=normalized_item.review_type,
                        source_family=normalized_item.source_family,
                        source_kind=normalized_item.source_kind,
                        source_key=normalized_item.source_key,
                        document_id=normalized_item.document_id,
                        title=normalized_item.title,
                        summary=normalized_item.summary,
                        priority=normalized_item.priority,
                        status="pending_review",
                        confidence=normalized_item.confidence,
                        ranking_score=normalized_item.ranking_score,
                        evidence_bundle_payload=normalized_item.evidence_bundle,
                        payload=normalized_item.payload,
                        metadata_payload=normalized_item.metadata,
                        review_fingerprint=normalized_item.review_fingerprint,
                        decision_reason=None,
                        decided_at=None,
                        linked_proposal_id=None,
                        linked_approval_key=None,
                    )
                    self.session.add(model)
                    self.session.flush()
                    self.session.refresh(model)
                effective_models.append(model)
            except IntegrityError:
                existing_after_conflict = self._find_existing_review_item_model(
                    space_id=normalized_space_id,
                    review_item=normalized_item,
                )
                if existing_after_conflict is None:
                    raise
                effective_models.append(existing_after_conflict)
        self.session.commit()
        unique_models_by_id: dict[str, HarnessReviewItemModel] = {
            model.id: model for model in effective_models
        }
        return sorted(
            [
                _review_item_record_from_model(model)
                for model in unique_models_by_id.values()
            ],
            key=lambda record: (-record.ranking_score, record.created_at),
        )

    def list_review_items(
        self,
        *,
        space_id: UUID | str,
        status: str | None = None,
        review_type: str | None = None,
        source_family: str | None = None,
        run_id: UUID | str | None = None,
        document_id: UUID | str | None = None,
    ) -> list[HarnessReviewItemRecord]:
        stmt = select(HarnessReviewItemModel).where(
            HarnessReviewItemModel.space_id == str(space_id),
        )
        if isinstance(status, str) and status.strip() != "":
            stmt = stmt.where(HarnessReviewItemModel.status == status.strip())
        if isinstance(review_type, str) and review_type.strip() != "":
            stmt = stmt.where(HarnessReviewItemModel.review_type == review_type.strip())
        if isinstance(source_family, str) and source_family.strip() != "":
            stmt = stmt.where(
                HarnessReviewItemModel.source_family == source_family.strip().lower(),
            )
        if run_id is not None:
            stmt = stmt.where(HarnessReviewItemModel.run_id == str(run_id))
        if document_id is not None:
            stmt = stmt.where(HarnessReviewItemModel.document_id == str(document_id))
        stmt = stmt.order_by(
            HarnessReviewItemModel.ranking_score.desc(),
            HarnessReviewItemModel.updated_at.desc(),
        )
        models = self.session.execute(stmt).scalars().all()
        return [_review_item_record_from_model(model) for model in models]

    def count_review_items(
        self,
        *,
        space_id: UUID | str,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(HarnessReviewItemModel)
            .where(HarnessReviewItemModel.space_id == str(space_id))
        )
        return int(self.session.execute(stmt).scalar_one())

    def get_review_item(
        self,
        *,
        space_id: UUID | str,
        review_item_id: UUID | str,
    ) -> HarnessReviewItemRecord | None:
        model = self.session.get(HarnessReviewItemModel, str(review_item_id))
        if model is None or model.space_id != str(space_id):
            return None
        return _review_item_record_from_model(model)

    def decide_review_item(
        self,
        *,
        space_id: UUID | str,
        review_item_id: UUID | str,
        status: str,
        decision_reason: str | None,
        metadata: JSONObject | None = None,
        linked_proposal_id: str | None = None,
        linked_approval_key: str | None = None,
    ) -> HarnessReviewItemRecord | None:
        normalized_status = status.strip().lower()
        if normalized_status not in {"resolved", "dismissed"}:
            msg = f"Unsupported review item status '{status}'"
            raise ValueError(msg)
        normalized_space_id = str(space_id)
        normalized_review_item_id = str(review_item_id)
        status_stmt = select(
            HarnessReviewItemModel.status,
            HarnessReviewItemModel.metadata_payload,
        ).where(
            HarnessReviewItemModel.id == normalized_review_item_id,
            HarnessReviewItemModel.space_id == normalized_space_id,
        )
        status_row = self.session.execute(status_stmt).one_or_none()
        if status_row is None:
            return None
        current_status = status_row[0]
        if current_status != "pending_review":
            msg = (
                f"Review item '{review_item_id}' is already decided with status "
                f"'{current_status}'"
            )
            raise ValueError(msg)
        decision_reason_text = (
            decision_reason.strip()
            if isinstance(decision_reason, str) and decision_reason.strip() != ""
            else None
        )
        decision_timestamp = datetime.now(UTC).replace(tzinfo=None)
        update_result = self.session.execute(
            update(HarnessReviewItemModel)
            .where(
                HarnessReviewItemModel.id == normalized_review_item_id,
                HarnessReviewItemModel.space_id == normalized_space_id,
                HarnessReviewItemModel.status == "pending_review",
            )
            .values(
                status=normalized_status,
                decision_reason=decision_reason_text,
                decided_at=decision_timestamp,
                linked_proposal_id=(
                    linked_proposal_id.strip()
                    if isinstance(linked_proposal_id, str)
                    and linked_proposal_id.strip() != ""
                    else None
                ),
                linked_approval_key=(
                    linked_approval_key.strip()
                    if isinstance(linked_approval_key, str)
                    and linked_approval_key.strip() != ""
                    else None
                ),
                metadata_payload={
                    **_json_object(status_row[1]),
                    **(metadata or {}),
                },
            ),
        )
        if update_result.rowcount != 1:
            refreshed_status_row = self.session.execute(status_stmt).one_or_none()
            if refreshed_status_row is None:
                return None
            msg = (
                f"Review item '{review_item_id}' is already decided with status "
                f"'{refreshed_status_row[0]}'"
            )
            raise ValueError(msg)
        self.session.commit()
        refreshed_stmt = select(HarnessReviewItemModel).where(
            HarnessReviewItemModel.id == normalized_review_item_id,
            HarnessReviewItemModel.space_id == normalized_space_id,
        )
        model = self.session.execute(refreshed_stmt).scalars().first()
        if model is None:
            return None
        return _review_item_record_from_model(model)


class SqlAlchemyHarnessDocumentStore(HarnessDocumentStore, _SessionBackedStore):
    """Persist harness-side documents in relational storage."""

    def __init__(self, session: Session | None = None) -> None:
        _SessionBackedStore.__init__(self, session)

    def create_document(  # noqa: PLR0913
        self,
        *,
        document_id: UUID | str | None = None,
        space_id: UUID | str,
        created_by: UUID | str,
        title: str,
        source_type: str,
        filename: str | None,
        media_type: str,
        sha256: str,
        byte_size: int,
        page_count: int | None,
        text_content: str,
        raw_storage_key: str | None = None,
        enriched_storage_key: str | None = None,
        ingestion_run_id: UUID | str,
        last_enrichment_run_id: UUID | str | None = None,
        enrichment_status: str,
        extraction_status: str,
        metadata: JSONObject | None = None,
    ) -> HarnessDocumentRecord:
        normalized_title = normalize_document_title(title)
        model_kwargs: dict[str, object] = {
            "space_id": str(space_id),
            "created_by": str(created_by),
            "title": normalized_title,
            "source_type": source_type,
            "filename": filename,
            "media_type": media_type,
            "sha256": sha256,
            "byte_size": byte_size,
            "page_count": page_count,
            "text_content": text_content,
            "text_excerpt": text_content.strip().replace("\n", " ")[:280],
            "raw_storage_key": raw_storage_key,
            "enriched_storage_key": enriched_storage_key,
            "ingestion_run_id": str(ingestion_run_id),
            "last_enrichment_run_id": (
                None if last_enrichment_run_id is None else str(last_enrichment_run_id)
            ),
            "last_extraction_run_id": None,
            "enrichment_status": enrichment_status,
            "extraction_status": extraction_status,
            "metadata_payload": {} if metadata is None else dict(metadata),
        }
        if document_id is not None:
            model_kwargs["id"] = str(document_id)
        model = HarnessDocumentModel(**model_kwargs)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return _document_record_from_model(model)

    def list_documents(
        self,
        *,
        space_id: UUID | str,
    ) -> list[HarnessDocumentRecord]:
        stmt = (
            select(HarnessDocumentModel)
            .where(HarnessDocumentModel.space_id == str(space_id))
            .order_by(HarnessDocumentModel.updated_at.desc())
        )
        models = self.session.execute(stmt).scalars().all()
        return [_document_record_from_model(model) for model in models]

    def find_document_by_sha256(
        self,
        *,
        space_id: UUID | str,
        sha256: str,
    ) -> HarnessDocumentRecord | None:
        stmt = (
            select(HarnessDocumentModel)
            .where(
                HarnessDocumentModel.space_id == str(space_id),
                HarnessDocumentModel.sha256 == sha256,
            )
            .order_by(HarnessDocumentModel.updated_at.desc())
        )
        model = self.session.execute(stmt).scalars().first()
        if model is None:
            return None
        return _document_record_from_model(model)

    def count_documents(
        self,
        *,
        space_id: UUID | str,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(HarnessDocumentModel)
            .where(
                HarnessDocumentModel.space_id == str(space_id),
            )
        )
        return int(self.session.execute(stmt).scalar_one())

    def get_document(
        self,
        *,
        space_id: UUID | str,
        document_id: UUID | str,
    ) -> HarnessDocumentRecord | None:
        stmt = select(HarnessDocumentModel).where(
            and_(
                HarnessDocumentModel.space_id == str(space_id),
                HarnessDocumentModel.id == str(document_id),
            ),
        )
        model = self.session.execute(stmt).scalar_one_or_none()
        if model is None:
            return None
        return _document_record_from_model(model)

    def update_document(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        document_id: UUID | str,
        title: str | None = None,
        text_content: str | None = None,
        page_count: int | None = None,
        raw_storage_key: str | None = None,
        enriched_storage_key: str | None = None,
        last_enrichment_run_id: UUID | str | None = None,
        last_extraction_run_id: UUID | str | None = None,
        enrichment_status: str | None = None,
        extraction_status: str | None = None,
        metadata_patch: JSONObject | None = None,
    ) -> HarnessDocumentRecord | None:
        stmt = select(HarnessDocumentModel).where(
            and_(
                HarnessDocumentModel.space_id == str(space_id),
                HarnessDocumentModel.id == str(document_id),
            ),
        )
        model = self.session.execute(stmt).scalar_one_or_none()
        if model is None:
            return None
        if isinstance(title, str) and title.strip() != "":
            model.title = normalize_document_title(title)
        if isinstance(text_content, str):
            model.text_content = text_content
            model.text_excerpt = text_content.strip().replace("\n", " ")[:280]
        if page_count is not None:
            model.page_count = page_count
        if isinstance(raw_storage_key, str) and raw_storage_key.strip() != "":
            model.raw_storage_key = raw_storage_key
        if isinstance(enriched_storage_key, str) and enriched_storage_key.strip() != "":
            model.enriched_storage_key = enriched_storage_key
        if last_enrichment_run_id is not None:
            model.last_enrichment_run_id = str(last_enrichment_run_id)
        if last_extraction_run_id is not None:
            model.last_extraction_run_id = str(last_extraction_run_id)
        if isinstance(enrichment_status, str) and enrichment_status.strip() != "":
            model.enrichment_status = enrichment_status
        if isinstance(extraction_status, str) and extraction_status.strip() != "":
            model.extraction_status = extraction_status
        if metadata_patch is not None:
            model.metadata_payload = {
                **_json_object(model.metadata_payload),
                **dict(metadata_patch),
            }
        self.session.commit()
        self.session.refresh(model)
        return _document_record_from_model(model)


class SqlAlchemyHarnessScheduleStore(HarnessScheduleStore, _SessionBackedStore):
    """Persist harness schedule definitions in relational storage."""

    def __init__(self, session: Session | None = None) -> None:
        _SessionBackedStore.__init__(self, session)

    def create_schedule(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        harness_id: str,
        title: str,
        cadence: str,
        created_by: UUID | str,
        configuration: JSONObject,
        metadata: JSONObject,
        status: str = "active",
    ) -> HarnessScheduleRecord:
        normalized_cadence = normalize_schedule_cadence(cadence)
        model = HarnessScheduleModel(
            space_id=str(space_id),
            harness_id=harness_id,
            title=title,
            cadence=normalized_cadence,
            status=status,
            created_by=str(created_by),
            configuration_payload=configuration,
            metadata_payload=metadata,
            last_run_id=None,
            last_run_at=None,
            active_trigger_claim_id=None,
            active_trigger_claimed_at=None,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return _schedule_record_from_model(model)

    def list_schedules(
        self,
        *,
        space_id: UUID | str,
    ) -> list[HarnessScheduleRecord]:
        stmt = (
            select(HarnessScheduleModel)
            .where(HarnessScheduleModel.space_id == str(space_id))
            .order_by(HarnessScheduleModel.updated_at.desc())
        )
        models = self.session.execute(stmt).scalars().all()
        return [_schedule_record_from_model(model) for model in models]

    def count_schedules(
        self,
        *,
        space_id: UUID | str,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(HarnessScheduleModel)
            .where(
                HarnessScheduleModel.space_id == str(space_id),
            )
        )
        return int(self.session.execute(stmt).scalar_one())

    def list_all_schedules(
        self,
        *,
        status: str | None = None,
    ) -> list[HarnessScheduleRecord]:
        stmt = select(HarnessScheduleModel).order_by(
            HarnessScheduleModel.updated_at.desc(),
        )
        if isinstance(status, str) and status.strip() != "":
            stmt = stmt.where(HarnessScheduleModel.status == status.strip())
        models = self.session.execute(stmt).scalars().all()
        return [_schedule_record_from_model(model) for model in models]

    def get_schedule(
        self,
        *,
        space_id: UUID | str,
        schedule_id: UUID | str,
    ) -> HarnessScheduleRecord | None:
        model = self.session.get(HarnessScheduleModel, str(schedule_id))
        if model is None or model.space_id != str(space_id):
            return None
        return _schedule_record_from_model(model)

    def update_schedule(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        schedule_id: UUID | str,
        title: str | None = None,
        cadence: str | None = None,
        status: str | None = None,
        configuration: JSONObject | None = None,
        metadata: JSONObject | None = None,
        last_run_id: UUID | str | None = None,
        last_run_at: datetime | None = None,
    ) -> HarnessScheduleRecord | None:
        model = self.session.get(HarnessScheduleModel, str(schedule_id))
        if model is None or model.space_id != str(space_id):
            return None
        if isinstance(title, str) and title.strip() != "":
            model.title = title
        if isinstance(cadence, str) and cadence.strip() != "":
            model.cadence = normalize_schedule_cadence(cadence)
        if isinstance(status, str) and status.strip() != "":
            model.status = status
        if configuration is not None:
            model.configuration_payload = configuration
        if metadata is not None:
            model.metadata_payload = metadata
        if last_run_id is not None:
            model.last_run_id = str(last_run_id)
        if last_run_at is not None:
            model.last_run_at = last_run_at
        self.session.commit()
        self.session.refresh(model)
        return _schedule_record_from_model(model)

    def acquire_trigger_claim(
        self,
        *,
        space_id: UUID | str,
        schedule_id: UUID | str,
        claim_id: UUID | str,
        claimed_at: datetime | None = None,
        ttl_seconds: int = 30,
    ) -> HarnessScheduleRecord | None:
        normalized_now = _normalized_utc_datetime(claimed_at)
        stale_before = normalized_now - timedelta(seconds=ttl_seconds)
        stmt = (
            update(HarnessScheduleModel)
            .where(HarnessScheduleModel.id == str(schedule_id))
            .where(HarnessScheduleModel.space_id == str(space_id))
            .where(
                or_(
                    HarnessScheduleModel.active_trigger_claim_id.is_(None),
                    HarnessScheduleModel.active_trigger_claimed_at.is_(None),
                    HarnessScheduleModel.active_trigger_claimed_at <= stale_before,
                    HarnessScheduleModel.active_trigger_claim_id == str(claim_id),
                ),
            )
            .values(
                active_trigger_claim_id=str(claim_id),
                active_trigger_claimed_at=normalized_now,
            )
        )
        result = self.session.execute(stmt)
        self.session.commit()
        if result.rowcount != 1:
            return None
        model = self.session.get(HarnessScheduleModel, str(schedule_id))
        if model is None or model.space_id != str(space_id):
            return None
        self.session.refresh(model)
        return _schedule_record_from_model(model)

    def release_trigger_claim(
        self,
        *,
        space_id: UUID | str,
        schedule_id: UUID | str,
        claim_id: UUID | str,
    ) -> HarnessScheduleRecord | None:
        stmt = (
            update(HarnessScheduleModel)
            .where(HarnessScheduleModel.id == str(schedule_id))
            .where(HarnessScheduleModel.space_id == str(space_id))
            .where(HarnessScheduleModel.active_trigger_claim_id == str(claim_id))
            .values(
                active_trigger_claim_id=None,
                active_trigger_claimed_at=None,
            )
        )
        result = self.session.execute(stmt)
        self.session.commit()
        if result.rowcount != 1:
            return None
        model = self.session.get(HarnessScheduleModel, str(schedule_id))
        if model is None or model.space_id != str(space_id):
            return None
        self.session.refresh(model)
        return _schedule_record_from_model(model)


class SqlAlchemyHarnessResearchSpaceStore(
    HarnessResearchSpaceStore,
    _SessionBackedStore,
):
    """Read and create research spaces backed by shared platform tables."""

    def __init__(
        self,
        session: Session | None = None,
        *,
        space_lifecycle_sync: SpaceLifecycleSyncPort | None = None,
    ) -> None:
        HarnessResearchSpaceStore.__init__(self)
        _SessionBackedStore.__init__(self, session)
        self._space_lifecycle_sync = space_lifecycle_sync

    def _sync_space_model(self, model: ResearchSpaceModel) -> None:
        if self._space_lifecycle_sync is None:
            return
        self._space_lifecycle_sync.sync_space(graph_sync_space_from_model(model))

    def _ensure_owner_user(  # noqa: PLR0913
        self,
        *,
        owner_id: UUID,
        owner_email: str | None = None,
        owner_username: str | None = None,
        owner_full_name: str | None = None,
        owner_role: str | None = None,
        owner_status: str | None = None,
    ) -> UUID:
        existing_owner = self.session.get(HarnessUserModel, owner_id)
        if existing_owner is not None:
            return owner_id

        fallback_email = f"{owner_id}@graph-harness.example.com"
        normalized_email = _normalize_owner_text(
            owner_email,
            fallback=fallback_email,
            max_length=255,
        )
        normalized_username = _normalize_owner_text(
            owner_username,
            fallback=normalized_email.split("@", maxsplit=1)[0],
            max_length=50,
        )
        normalized_full_name = _normalize_owner_text(
            owner_full_name,
            fallback=normalized_email,
            max_length=100,
        )
        identity_match = (
            self.session.execute(
                select(HarnessUserModel).where(
                    or_(
                        HarnessUserModel.email == normalized_email,
                        HarnessUserModel.username == normalized_username,
                    ),
                ),
            )
            .scalars()
            .first()
        )
        if identity_match is not None:
            if identity_match.email != normalized_email:
                msg = "Username is already in use"
                raise HarnessUserIdentityConflictError(msg)
            return _as_uuid(identity_match.id)
        self.session.add(
            HarnessUserModel(
                id=owner_id,
                email=normalized_email,
                username=normalized_username,
                full_name=normalized_full_name,
                hashed_password="external-auth-not-applicable",
                role=_normalize_owner_text(
                    owner_role,
                    fallback="viewer",
                    max_length=32,
                ).lower(),
                status=_normalize_owner_text(
                    owner_status,
                    fallback="active",
                    max_length=32,
                ).lower(),
                email_verified=True,
                login_attempts=0,
            ),
        )
        self.session.flush()
        return owner_id

    def _ensure_owner_membership(
        self,
        *,
        space_id: UUID,
        owner_id: UUID,
    ) -> None:
        membership = (
            self.session.execute(
                select(ResearchSpaceMembershipModel).where(
                    ResearchSpaceMembershipModel.space_id == space_id,
                    ResearchSpaceMembershipModel.user_id == owner_id,
                ),
            )
            .scalars()
            .first()
        )
        now = datetime.now(UTC).replace(tzinfo=None)
        if membership is None:
            self.session.add(
                ResearchSpaceMembershipModel(
                    space_id=space_id,
                    user_id=owner_id,
                    role=MembershipRoleEnum.OWNER,
                    invited_by=None,
                    invited_at=None,
                    joined_at=now,
                    is_active=True,
                ),
            )
            return

        membership.role = MembershipRoleEnum.OWNER
        membership.is_active = True
        if membership.joined_at is None:
            membership.joined_at = now

    def _role_for_space_row(
        self,
        *,
        space_model: ResearchSpaceModel,
        membership_role: MembershipRoleEnum | None,
        current_user_id: UUID,
        is_admin: bool,
    ) -> str:
        if isinstance(membership_role, MembershipRoleEnum):
            return membership_role.value
        if space_model.owner_id == current_user_id:
            return MembershipRoleEnum.OWNER.value
        if is_admin:
            return MembershipRoleEnum.ADMIN.value
        return MembershipRoleEnum.VIEWER.value

    def list_spaces(
        self,
        *,
        user_id: UUID | str,
        is_admin: bool,
    ) -> list[HarnessResearchSpaceRecord]:
        normalized_user_id = _as_uuid(user_id)
        membership_join = and_(
            ResearchSpaceMembershipModel.space_id == ResearchSpaceModel.id,
            ResearchSpaceMembershipModel.user_id == normalized_user_id,
            ResearchSpaceMembershipModel.is_active.is_(True),
        )
        stmt = (
            select(ResearchSpaceModel, ResearchSpaceMembershipModel.role)
            .outerjoin(ResearchSpaceMembershipModel, membership_join)
            .where(ResearchSpaceModel.status != SpaceStatusEnum.ARCHIVED)
            .order_by(ResearchSpaceModel.created_at.desc())
        )
        if not is_admin:
            stmt = stmt.where(
                or_(
                    ResearchSpaceModel.owner_id == normalized_user_id,
                    ResearchSpaceMembershipModel.id.is_not(None),
                ),
            )

        rows = self.session.execute(stmt).all()
        records: list[HarnessResearchSpaceRecord] = []
        for space_model, membership_role in rows:
            records.append(
                _research_space_record_from_model(
                    space_model,
                    role=self._role_for_space_row(
                        space_model=space_model,
                        membership_role=membership_role,
                        current_user_id=normalized_user_id,
                        is_admin=is_admin,
                    ),
                ),
            )
        return records

    def get_space(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        is_admin: bool,
    ) -> HarnessResearchSpaceRecord | None:
        normalized_space_id = _as_uuid(space_id)
        normalized_user_id = _as_uuid(user_id)
        membership_join = and_(
            ResearchSpaceMembershipModel.space_id == ResearchSpaceModel.id,
            ResearchSpaceMembershipModel.user_id == normalized_user_id,
            ResearchSpaceMembershipModel.is_active.is_(True),
        )
        stmt = (
            select(ResearchSpaceModel, ResearchSpaceMembershipModel.role)
            .outerjoin(ResearchSpaceMembershipModel, membership_join)
            .where(
                ResearchSpaceModel.id == normalized_space_id,
                ResearchSpaceModel.status != SpaceStatusEnum.ARCHIVED,
            )
        )
        if not is_admin:
            stmt = stmt.where(
                or_(
                    ResearchSpaceModel.owner_id == normalized_user_id,
                    ResearchSpaceMembershipModel.id.is_not(None),
                ),
            )
        row = self.session.execute(stmt).first()
        if row is None:
            return None
        space_model, membership_role = row
        return _research_space_record_from_model(
            space_model,
            role=self._role_for_space_row(
                space_model=space_model,
                membership_role=membership_role,
                current_user_id=normalized_user_id,
                is_admin=is_admin,
            ),
        )

    def get_default_space(
        self,
        *,
        user_id: UUID | str,
    ) -> HarnessResearchSpaceRecord | None:
        normalized_user_id = _as_uuid(user_id)
        models = (
            self.session.execute(
                select(ResearchSpaceModel)
                .where(
                    ResearchSpaceModel.owner_id == normalized_user_id,
                    ResearchSpaceModel.status != SpaceStatusEnum.ARCHIVED,
                )
                .order_by(ResearchSpaceModel.created_at.asc()),
            )
            .scalars()
            .all()
        )
        for model in models:
            if _is_personal_default_space(model):
                return _research_space_record_from_model(
                    model,
                    role=MembershipRoleEnum.OWNER.value,
                )
        return None

    def create_space(
        self,
        *,
        owner_id: UUID | str,
        owner_email: str | None = None,
        owner_username: str | None = None,
        owner_full_name: str | None = None,
        owner_role: str | None = None,
        owner_status: str | None = None,
        name: str,
        description: str | None,
        settings: ResearchSpaceSettings | None = None,
    ) -> HarnessResearchSpaceRecord:
        normalized_name = name.strip()
        if normalized_name == "":
            msg = "Space name is required"
            raise ValueError(msg)
        normalized_description = (
            description.strip() if isinstance(description, str) else ""
        )
        owner_uuid = _as_uuid(owner_id)
        owner_uuid = self._ensure_owner_user(
            owner_id=owner_uuid,
            owner_email=owner_email,
            owner_username=owner_username,
            owner_full_name=owner_full_name,
            owner_role=owner_role,
            owner_status=owner_status,
        )

        existing_slugs = set(
            self.session.execute(select(ResearchSpaceModel.slug)).scalars().all(),
        )
        model = ResearchSpaceModel(
            slug=build_unique_space_slug(normalized_name, existing_slugs),
            name=normalized_name,
            description=normalized_description,
            owner_id=owner_uuid,
            status=SpaceStatusEnum.ACTIVE,
            settings=settings or {},
            tags=[],
        )
        self.session.add(model)
        try:
            self.session.flush()
            self._ensure_owner_membership(space_id=model.id, owner_id=owner_uuid)
            self.session.flush()
            self._sync_space_model(model)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(model)
        return _research_space_record_from_model(
            model,
            role=MembershipRoleEnum.OWNER.value,
        )

    def ensure_default_space(  # noqa: PLR0913
        self,
        *,
        owner_id: UUID | str,
        owner_email: str | None = None,
        owner_username: str | None = None,
        owner_full_name: str | None = None,
        owner_role: str | None = None,
        owner_status: str | None = None,
    ) -> HarnessResearchSpaceRecord:
        owner_uuid = _as_uuid(owner_id)
        owner_uuid = self._ensure_owner_user(
            owner_id=owner_uuid,
            owner_email=owner_email,
            owner_username=owner_username,
            owner_full_name=owner_full_name,
            owner_role=owner_role,
            owner_status=owner_status,
        )
        existing_record = self.get_default_space(user_id=owner_uuid)
        if existing_record is not None:
            return existing_record

        model = ResearchSpaceModel(
            slug=_personal_default_slug(owner_uuid),
            name=PERSONAL_DEFAULT_SPACE_NAME,
            description=PERSONAL_DEFAULT_SPACE_DESCRIPTION,
            owner_id=owner_uuid,
            status=SpaceStatusEnum.ACTIVE,
            settings={PERSONAL_DEFAULT_SETTING_KEY: True},
            tags=["personal-default"],
        )
        self.session.add(model)
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            existing_after_conflict = self.get_default_space(user_id=owner_uuid)
            if existing_after_conflict is not None:
                return existing_after_conflict
            raise

        try:
            self._ensure_owner_membership(space_id=model.id, owner_id=owner_uuid)
            self.session.flush()
            self._sync_space_model(model)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(model)
        return _research_space_record_from_model(
            model,
            role=MembershipRoleEnum.OWNER.value,
        )

    def update_space_settings(
        self,
        *,
        space_id: UUID | str,
        settings: ResearchSpaceSettings,
    ) -> HarnessResearchSpaceRecord:
        """Replace one research space settings payload."""
        model = self.session.get(ResearchSpaceModel, _as_uuid(space_id))
        if model is None or model.status == SpaceStatusEnum.ARCHIVED:
            msg = "Space not found"
            raise KeyError(msg)
        model.settings = dict(settings)
        try:
            self.session.flush()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(model)
        return _research_space_record_from_model(
            model,
            role=MembershipRoleEnum.OWNER.value,
        )

    def prepare_space_archive(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        is_admin: bool,
    ) -> HarnessResearchSpaceRecord:
        """Return one archivable space when the caller may manage it."""
        space_uuid = _as_uuid(space_id)
        user_uuid = _as_uuid(user_id)

        model = self.session.get(ResearchSpaceModel, space_uuid)
        if model is None or model.status == SpaceStatusEnum.ARCHIVED:
            msg = "Space not found"
            raise KeyError(msg)

        if not is_admin and model.owner_id != user_uuid:
            msg = "Only the space owner or an admin can delete this space"
            raise PermissionError(msg)

        return _research_space_record_from_model(
            model,
            role=(
                MembershipRoleEnum.ADMIN.value
                if is_admin and model.owner_id != user_uuid
                else MembershipRoleEnum.OWNER.value
            ),
        )

    def archive_space(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        is_admin: bool,
    ) -> HarnessResearchSpaceRecord:
        """Archive one research space when the caller is allowed to manage it."""
        archivable_record = self.prepare_space_archive(
            space_id=space_id,
            user_id=user_id,
            is_admin=is_admin,
        )
        model = self.session.get(ResearchSpaceModel, _as_uuid(space_id))
        if model is None or model.status == SpaceStatusEnum.ARCHIVED:
            msg = "Space not found"
            raise KeyError(msg)
        model.status = SpaceStatusEnum.ARCHIVED
        self.session.commit()
        self.session.refresh(model)
        return _research_space_record_from_model(
            model,
            role=archivable_record.role,
        )

    def delete_space(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        is_admin: bool,
    ) -> HarnessResearchSpaceRecord:
        return self.archive_space(
            space_id=space_id,
            user_id=user_id,
            is_admin=is_admin,
        )

    # ------------------------------------------------------------------
    # Membership management
    # ------------------------------------------------------------------

    def list_members(
        self,
        *,
        space_id: UUID | str,
    ) -> list[HarnessSpaceMemberRecord]:
        normalized_space_id = _as_uuid(space_id)
        stmt = select(ResearchSpaceMembershipModel).where(
            ResearchSpaceMembershipModel.space_id == normalized_space_id,
            ResearchSpaceMembershipModel.is_active.is_(True),
        )
        rows = self.session.execute(stmt).scalars().all()
        return [
            HarnessSpaceMemberRecord(
                id=str(row.id),
                space_id=str(row.space_id),
                user_id=str(row.user_id),
                role=(
                    row.role.value
                    if isinstance(row.role, MembershipRoleEnum)
                    else str(row.role)
                ),
                invited_by=str(row.invited_by) if row.invited_by else None,
                invited_at=row.invited_at.isoformat() if row.invited_at else None,
                joined_at=row.joined_at.isoformat() if row.joined_at else None,
                is_active=row.is_active,
            )
            for row in rows
        ]

    def add_member(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        role: str,
        invited_by: UUID | str | None = None,
    ) -> HarnessSpaceMemberRecord:
        normalized_space_id = _as_uuid(space_id)
        normalized_user_id = _as_uuid(user_id)
        normalized_role = _normalize_assignable_member_role(role)
        now = datetime.now(UTC).replace(tzinfo=None)

        self._ensure_owner_user(owner_id=normalized_user_id)

        space = self.session.get(ResearchSpaceModel, normalized_space_id)
        if space is None:
            msg = "Space not found"
            raise KeyError(msg)

        existing = (
            self.session.execute(
                select(ResearchSpaceMembershipModel).where(
                    ResearchSpaceMembershipModel.space_id == normalized_space_id,
                    ResearchSpaceMembershipModel.user_id == normalized_user_id,
                ),
            )
            .scalars()
            .first()
        )

        if existing is not None:
            existing.role = MembershipRoleEnum(normalized_role)
            existing.is_active = True
            if existing.joined_at is None:
                existing.joined_at = now
            self.session.commit()
            self.session.refresh(existing)
            model = existing
        else:
            model = ResearchSpaceMembershipModel(
                space_id=normalized_space_id,
                user_id=normalized_user_id,
                role=MembershipRoleEnum(normalized_role),
                invited_by=_as_uuid(invited_by) if invited_by else None,
                invited_at=now,
                joined_at=now,
                is_active=True,
            )
            self.session.add(model)
            self.session.commit()
            self.session.refresh(model)

        return HarnessSpaceMemberRecord(
            id=str(model.id),
            space_id=str(model.space_id),
            user_id=str(model.user_id),
            role=(
                model.role.value
                if isinstance(model.role, MembershipRoleEnum)
                else str(model.role)
            ),
            invited_by=str(model.invited_by) if model.invited_by else None,
            invited_at=model.invited_at.isoformat() if model.invited_at else None,
            joined_at=model.joined_at.isoformat() if model.joined_at else None,
            is_active=model.is_active,
        )

    def remove_member(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
    ) -> HarnessSpaceMemberRecord | None:
        normalized_space_id = _as_uuid(space_id)
        normalized_user_id = _as_uuid(user_id)

        existing = (
            self.session.execute(
                select(ResearchSpaceMembershipModel).where(
                    ResearchSpaceMembershipModel.space_id == normalized_space_id,
                    ResearchSpaceMembershipModel.user_id == normalized_user_id,
                    ResearchSpaceMembershipModel.is_active.is_(True),
                ),
            )
            .scalars()
            .first()
        )
        if existing is None:
            return None

        existing.is_active = False
        self.session.commit()
        self.session.refresh(existing)
        return HarnessSpaceMemberRecord(
            id=str(existing.id),
            space_id=str(existing.space_id),
            user_id=str(existing.user_id),
            role=(
                existing.role.value
                if isinstance(existing.role, MembershipRoleEnum)
                else str(existing.role)
            ),
            invited_by=str(existing.invited_by) if existing.invited_by else None,
            invited_at=existing.invited_at.isoformat() if existing.invited_at else None,
            joined_at=existing.joined_at.isoformat() if existing.joined_at else None,
            is_active=existing.is_active,
        )


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


__all__ = [
    "SqlAlchemyHarnessApprovalStore",
    "SqlAlchemyHarnessChatSessionStore",
    "SqlAlchemyHarnessDocumentStore",
    "SqlAlchemyHarnessGraphSnapshotStore",
    "SqlAlchemyHarnessProposalStore",
    "SqlAlchemyHarnessResearchSpaceStore",
    "SqlAlchemyHarnessResearchStateStore",
    "SqlAlchemyHarnessScheduleStore",
]
