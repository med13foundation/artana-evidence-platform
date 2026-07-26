"""SQLAlchemy review-item, approval, and document stores.

The approval and intent persistence lives here rather than in
``sqlalchemy_stores`` because it is part of the same review surface as the
review-item store, and because that module sits at its per-file size budget.
``sqlalchemy_stores`` re-exports these names, so importers are unaffected.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.approval_store import (
    HarnessApprovalAction,
    HarnessApprovalRecord,
    HarnessApprovalStore,
    HarnessRunIntentRecord,
    approval_still_describes_action,
    carried_superseded_payload,
    normalize_approval_action,
    normalize_approval_title,
    superseded_decisions_from_payload,
)
from artana_evidence_api.models.harness import HarnessIntentModel
from artana_evidence_api.sqlalchemy_stores import (
    HarnessApprovalModel,
    HarnessDocumentModel,
    HarnessDocumentRecord,
    HarnessDocumentStore,
    HarnessReviewItemDraft,
    HarnessReviewItemModel,
    HarnessReviewItemRecord,
    HarnessReviewItemStore,
    _decided_by_from_model,
    _document_record_from_model,
    _json_object,
    _json_object_list,
    _result_rowcount,
    _review_item_record_from_model,
    _SessionBackedStore,
    commit_or_flush,
    normalize_document_title,
)
from artana_evidence_api.types.evidence_grade import normalize_evidence_grade
from artana_evidence_api.types.review_actor import ReviewActor  # noqa: TC001
from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject
    from sqlalchemy.orm import Session

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
                        evidence_grade=normalized_item.evidence_grade,
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
        commit_or_flush(self.session)
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
        evidence_grade: str | None = None,
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
        normalized_evidence_grade = normalize_evidence_grade(evidence_grade)
        if normalized_evidence_grade is not None:
            stmt = stmt.where(
                HarnessReviewItemModel.evidence_grade == normalized_evidence_grade,
            )
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

    def delete_review_items_for_documents(
        self,
        *,
        space_id: UUID | str,
        document_ids: tuple[UUID | str, ...],
    ) -> int:
        target_ids = tuple(str(document_id) for document_id in document_ids)
        if not target_ids:
            return 0
        result = self.session.execute(
            delete(HarnessReviewItemModel).where(
                HarnessReviewItemModel.space_id == str(space_id),
                HarnessReviewItemModel.document_id.in_(target_ids),
            ),
        )
        commit_or_flush(self.session)
        return _result_rowcount(result)

    def decide_review_item(
        self,
        *,
        space_id: UUID | str,
        review_item_id: UUID | str,
        status: str,
        decision_reason: str | None,
        decided_by: ReviewActor | None,
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
                decided_by_user_id=(
                    decided_by.user_id if decided_by is not None else None
                ),
                decided_by_email=(
                    decided_by.email if decided_by is not None else None
                ),
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
        if _result_rowcount(update_result) != 1:
            refreshed_status_row = self.session.execute(status_stmt).one_or_none()
            if refreshed_status_row is None:
                return None
            msg = (
                f"Review item '{review_item_id}' is already decided with status "
                f"'{refreshed_status_row[0]}'"
            )
            raise ValueError(msg)
        commit_or_flush(self.session)
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
        commit_or_flush(self.session)
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

    def delete_documents(
        self,
        *,
        space_id: UUID | str,
        document_ids: tuple[UUID | str, ...],
    ) -> list[HarnessDocumentRecord]:
        target_ids = tuple(str(document_id) for document_id in document_ids)
        if not target_ids:
            return []
        stmt = (
            select(HarnessDocumentModel)
            .where(
                HarnessDocumentModel.space_id == str(space_id),
                HarnessDocumentModel.id.in_(target_ids),
            )
            .order_by(HarnessDocumentModel.updated_at.desc())
        )
        models = self.session.execute(stmt).scalars().all()
        deleted_records = [_document_record_from_model(model) for model in models]
        if not deleted_records:
            return []
        self.session.execute(
            delete(HarnessDocumentModel).where(
                HarnessDocumentModel.space_id == str(space_id),
                HarnessDocumentModel.id.in_(
                    tuple(record.id for record in deleted_records),
                ),
            ),
        )
        commit_or_flush(self.session)
        return deleted_records

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
        commit_or_flush(self.session)
        self.session.refresh(model)
        return _document_record_from_model(model)


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
        decided_by=_decided_by_from_model(model),
        metadata=_json_object(model.metadata_payload),
        superseded_decisions=superseded_decisions_from_payload(
            model.superseded_decisions_payload,
        ),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _repoint_approval_at_action(
    *,
    model: HarnessApprovalModel,
    action: HarnessApprovalAction,
) -> None:
    """Re-gate an approval row, keeping the decisions it replaces."""
    record = _approval_record_from_model(model)
    model.title = action.title
    model.risk_level = action.risk_level
    model.target_type = action.target_type
    model.target_id = action.target_id
    model.status = "pending"
    model.decision_reason = None
    model.decided_by_user_id = None
    model.decided_by_email = None
    model.metadata_payload = action.metadata
    model.superseded_decisions_payload = carried_superseded_payload(existing=record)


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

        # Only pending approvals are replaced. A decided approval is a record of
        # something a person did, with their written reason and their identity on
        # it -- re-proposing the run's intent must not erase that, and
        # decide_approval already treats a decision as final by refusing to
        # decide twice.
        existing_models = {
            existing.approval_key: existing
            for existing in self.session.execute(
                select(HarnessApprovalModel).where(
                    HarnessApprovalModel.run_id == normalized_run_id,
                ),
            )
            .scalars()
            .all()
        }
        proposed_keys: set[str] = set()
        for action in normalized_actions:
            if not action.requires_approval:
                continue
            proposed_keys.add(action.approval_key)
            existing_model = existing_models.get(action.approval_key)
            if existing_model is None:
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
                continue
            # A decision describes an action, not an approval key, so it only
            # stands while the re-proposed action still matches it. Rows are
            # updated rather than replaced: one row per (run_id, approval_key).
            if existing_model.status != "pending" and approval_still_describes_action(
                _approval_record_from_model(existing_model),
                action,
            ):
                continue
            _repoint_approval_at_action(model=existing_model, action=action)
        for approval_key, existing_model in existing_models.items():
            if approval_key not in proposed_keys and existing_model.status == "pending":
                self.session.delete(existing_model)

        commit_or_flush(self.session)
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
        decided_by: ReviewActor | None,
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
                decided_by_user_id=(
                    decided_by.user_id if decided_by is not None else None
                ),
                decided_by_email=(
                    decided_by.email if decided_by is not None else None
                ),
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
        commit_or_flush(self.session)
        stmt = select(HarnessApprovalModel).where(
            HarnessApprovalModel.space_id == normalized_space_id,
            HarnessApprovalModel.run_id == normalized_run_id,
            HarnessApprovalModel.approval_key == approval_key,
        )
        model = self.session.execute(stmt).scalars().first()
        if model is None:
            return None
        return _approval_record_from_model(model)
