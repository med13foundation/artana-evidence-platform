"""SQLAlchemy-backed durable stores for graph-harness runtime state."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID

from artana_evidence_api.models import (
    HarnessApprovalModel,
    HarnessChatMessageModel,
    HarnessChatSessionModel,
    HarnessDocumentModel,
    HarnessGraphSnapshotModel,
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
from artana_evidence_api.types.evidence_grade import normalize_evidence_grade
from artana_evidence_api.types.review_actor import ReviewActor
from artana_evidence_api.types.source_provenance import (
    ClaimSourceProvenance,
    SourceProvenanceStatus,
    unrecorded_source_provenance,
)
from sqlalchemy import delete, func, select, update
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
    DUPLICATE_RESOLUTION,
    DUPLICATE_STATUS,
    IDENTITY_PENDING_STATUS,
    HarnessProposalDraft,
    HarnessProposalRecord,
    HarnessProposalStore,
    _is_same_document_rederivation,
    _is_same_known_document,
    build_identity_adjudication,
    clean_decision_reason,
    in_batch_identity_collision_reason,
    missing_duplicate_counterpart_message,
    normalize_identity_resolution,
    require_fingerprint_for_bulk_reject,
    unadjudicable_proposal_message,
    undecidable_proposal_message,
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

logger = logging.getLogger(__name__)

_ASSIGNABLE_MEMBER_ROLE_VALUES = frozenset(
    role.value for role in MembershipRoleEnum if role is not MembershipRoleEnum.OWNER
)
_ACTIVE_PROPOSAL_FINGERPRINT_UNIQUE_INDEX = (
    "uq_harness_proposals_active_space_claim_fingerprint"
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


def _is_active_proposal_fingerprint_conflict(exc: IntegrityError) -> bool:
    message = f"{exc.orig} {exc}".lower()
    if _ACTIVE_PROPOSAL_FINGERPRINT_UNIQUE_INDEX in message:
        return True
    if "unique" not in message and "duplicate" not in message:
        return False
    return "claim_fingerprint" in message or "fingerprint" in message


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




def _decided_by_from_model(
    model: HarnessApprovalModel | HarnessProposalModel | HarnessReviewItemModel,
) -> ReviewActor | None:
    """Read the deciding actor off any decision-bearing row."""
    return ReviewActor.from_stored(
        user_id=model.decided_by_user_id,
        email=model.decided_by_email,
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
        evidence_grade=model.evidence_grade,
        decision_reason=model.decision_reason,
        decided_at=model.decided_at,
        decided_by=_decided_by_from_model(model),
        created_at=model.created_at,
        updated_at=model.updated_at,
        claim_fingerprint=getattr(model, "claim_fingerprint", None),
        source_provenance=_source_provenance_from_model(model),
        identity_adjudication=_identity_adjudication_from_model(model),
    )


def _identity_adjudication_from_model(
    model: HarnessProposalModel,
) -> JSONObject | None:
    """Read one proposal's identity adjudication, or None if never adjudicated."""

    payload = getattr(model, "identity_adjudication_payload", None)
    if not isinstance(payload, dict):
        return None
    return cast("JSONObject", payload)


def _source_provenance_from_model(
    model: HarnessProposalModel,
) -> ClaimSourceProvenance:
    """Read one proposal's provenance, honouring the persisted status column.

    Migration 025 records source_provenance_status on every row even when no
    envelope was written, but the read path only looked at the payload and
    returned None -- so "we never checked" and "we checked and rejected it"
    reached the reviewer as the same empty field. The status column is the
    system's own statement about the claim in front of them; discarding it left
    a reviewer no way to tell an unverified claim from an unexamined one.
    """
    payload = getattr(model, "source_provenance_payload", None)
    persisted_status = getattr(model, "source_provenance_status", None)
    if not isinstance(payload, dict):
        return unrecorded_source_provenance(
            cast("SourceProvenanceStatus", persisted_status)
            if persisted_status in {"unverified", "invalid"}
            else "unverified",
        )
    try:
        return ClaimSourceProvenance.model_validate(payload)
    except ValueError:
        return ClaimSourceProvenance(
            status="invalid",
            reason_code="malformed_persisted_source_provenance",
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
        evidence_grade=model.evidence_grade,
        decision_reason=model.decision_reason,
        decided_at=model.decided_at,
        decided_by=_decided_by_from_model(model),
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




class SqlAlchemyHarnessProposalStore(HarnessProposalStore, _SessionBackedStore):
    """Persist harness proposals in relational storage."""

    def __init__(self, session: Session | None = None) -> None:
        _SessionBackedStore.__init__(self, session)

    def _build_proposal_model(
        self,
        *,
        space_id: str,
        run_id: str,
        normalized_proposal: HarnessProposalDraft,
        status: str,
        decision_reason: str | None,
    ) -> HarnessProposalModel:
        """Build one proposal row so both write paths stay identical."""

        return HarnessProposalModel(
            space_id=space_id,
            run_id=run_id,
            proposal_type=normalized_proposal.proposal_type,
            source_kind=normalized_proposal.source_kind,
            source_key=normalized_proposal.source_key,
            document_id=normalized_proposal.document_id,
            title=normalized_proposal.title,
            summary=normalized_proposal.summary,
            status=status,
            confidence=normalized_proposal.confidence,
            ranking_score=normalized_proposal.ranking_score,
            reasoning_path=normalized_proposal.reasoning_path,
            evidence_bundle_payload=normalized_proposal.evidence_bundle,
            payload=normalized_proposal.payload,
            metadata_payload=normalized_proposal.metadata,
            source_provenance_payload=(
                normalized_proposal.source_provenance.model_dump(mode="json")
                if normalized_proposal.source_provenance is not None
                else None
            ),
            source_provenance_status=(
                normalized_proposal.source_provenance.status
                if normalized_proposal.source_provenance is not None
                else "unverified"
            ),
            evidence_grade=normalized_proposal.evidence_grade,
            claim_fingerprint=normalized_proposal.claim_fingerprint,
            decision_reason=decision_reason,
            decided_at=None,
        )

    def _active_fingerprint_holder(
        self,
        *,
        space_id: str,
        claim_fingerprint: str,
    ) -> tuple[str, str, str | None] | None:
        """Return (id, status, document_id) of whoever actively holds one fingerprint."""

        row = self.session.execute(
            select(
                HarnessProposalModel.id,
                HarnessProposalModel.status,
                HarnessProposalModel.document_id,
            )
            .where(
                HarnessProposalModel.space_id == space_id,
                HarnessProposalModel.claim_fingerprint == claim_fingerprint,
                HarnessProposalModel.status.in_(["pending_review", "promoted"]),
            )
            .limit(1),
        ).first()
        if row is None:
            return None
        return (str(row[0]), str(row[1]), row[2])

    def _plan_batch(
        self,
        *,
        space_id: str,
        proposals: tuple[HarnessProposalDraft, ...],
    ) -> list[tuple[HarnessProposalDraft, str, str | None]]:
        """Decide each draft's status before anything is written.

        ART-DATA-001: a fingerprint collision is retained, never dropped.
        Migration 024 makes (space_id, claim_fingerprint) unique while the
        status is active, so a colliding proposal cannot also be
        `pending_review`.  It is planned as IDENTITY_PENDING instead: outside
        that partial index, so it coexists; outside the *default* review queue,
        so it is never promoted or rejected while its identity is unsettled; and
        fully queryable, so the second independent observation survives with its
        own provenance.  It is reachable -- a reviewer asks for `status=parked`
        and answers `resolve_as_duplicate` or `release_as_distinct`.

        Retain first, merge later.  Deciding whether two proposals are the same
        assertion needs the identity model that does not exist yet, and a wrong
        merge is unrecoverable while a retained duplicate is not.

        Collisions between two drafts *inside one batch* are resolved here too.
        They used to reach the database undetected -- the pre-check queried
        committed rows and the session does not autoflush -- so the unique index
        rejected the insert and the whole batch was parked.  One extraction
        producing two claims with the same fingerprint is ordinary: under the
        mention-label rule it happens in 4.4% of BC5CDR documents (0.0% under
        MeSH labels; the figure is a property of the label rule, not the corpus).

        Both drafts are kept whichever document they came from.  Two drafts of
        one extraction pass are not one document read twice: each carries its
        own evidence bundle, spans and provenance, and the fingerprint is
        exactly what cannot tell them apart.  Only a collision with an
        *already-stored* proposal from the same document is a re-derivation, and
        only that one drops -- with a log line, because a proposal that leaves
        no row must still leave a trace.
        """

        planned: list[tuple[HarnessProposalDraft, str, str | None]] = []
        # fingerprint -> document_id of the draft in this batch already planned
        # as pending_review, which is the one that will take the index slot.
        claimed_in_batch: dict[str, str | None] = {}
        for proposal in proposals:
            normalized_proposal = self.normalize_proposal_draft(proposal)
            fingerprint = normalized_proposal.claim_fingerprint
            status = "pending_review"
            decision_reason: str | None = None
            if fingerprint:
                if fingerprint in claimed_in_batch:
                    status = IDENTITY_PENDING_STATUS
                    decision_reason = in_batch_identity_collision_reason(
                        claim_fingerprint=fingerprint,
                        same_document=_is_same_known_document(
                            existing_document_id=claimed_in_batch[fingerprint],
                            incoming_document_id=normalized_proposal.document_id,
                        ),
                    )
                else:
                    holder = self._active_fingerprint_holder(
                        space_id=space_id,
                        claim_fingerprint=fingerprint,
                    )
                    if holder is not None:
                        if _is_same_document_rederivation(
                            existing_document_id=holder[2],
                            incoming_document_id=normalized_proposal.document_id,
                        ):
                            # Re-extracting a stored document is the same
                            # observation arriving twice, not a second source.
                            # Retaining it would add a row on every
                            # re-extraction.  Logged so the drop is countable.
                            logger.info(
                                "Dropping re-derived proposal from the "
                                "already-stored document (fingerprint=%s, "
                                "existing=%s, source_key=%s)",
                                fingerprint[:12],
                                holder[0],
                                normalized_proposal.source_key,
                            )
                            continue
                        status = IDENTITY_PENDING_STATUS
                        decision_reason = (
                            "Retained by ART-DATA-001: claim fingerprint "
                            f"{fingerprint} already has an active proposal "
                            f"{holder[0]} with status '{holder[1]}' from a "
                            "different document in this space. Awaiting "
                            "identity adjudication; not auto-merged."
                        )
                if status == "pending_review":
                    claimed_in_batch[fingerprint] = normalized_proposal.document_id
            planned.append((normalized_proposal, status, decision_reason))
        return planned

    def _persist_planned_batch(
        self,
        *,
        space_id: str,
        run_id: str,
        planned: list[tuple[HarnessProposalDraft, str, str | None]],
    ) -> list[HarnessProposalModel]:
        models = [
            self._build_proposal_model(
                space_id=space_id,
                run_id=run_id,
                normalized_proposal=normalized_proposal,
                status=status,
                decision_reason=decision_reason,
            )
            for normalized_proposal, status, decision_reason in planned
        ]
        for model in models:
            self.session.add(model)
        return models

    def _records_from_models(
        self,
        models: list[HarnessProposalModel],
    ) -> list[HarnessProposalRecord]:
        for model in models:
            self.session.refresh(model)
        return sorted(
            [_proposal_record_from_model(model) for model in models],
            key=lambda record: (-record.ranking_score, record.created_at),
        )

    def create_proposals(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        proposals: tuple[HarnessProposalDraft, ...],
    ) -> list[HarnessProposalRecord]:
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        created_models = self._persist_planned_batch(
            space_id=normalized_space_id,
            run_id=normalized_run_id,
            planned=self._plan_batch(
                space_id=normalized_space_id,
                proposals=proposals,
            ),
        )
        try:
            commit_or_flush(self.session)
        except IntegrityError as exc:
            self.session.rollback()
            if not _is_active_proposal_fingerprint_conflict(exc):
                raise
            return self._repersist_after_fingerprint_race(
                space_id=normalized_space_id,
                run_id=normalized_run_id,
                proposals=proposals,
            )
        return self._records_from_models(created_models)

    def _repersist_after_fingerprint_race(
        self,
        *,
        space_id: str,
        run_id: str,
        proposals: tuple[HarnessProposalDraft, ...],
    ) -> list[HarnessProposalRecord]:
        """Re-plan a lost-race batch, parking only the drafts that actually lost.

        A concurrent writer claimed a fingerprint between the plan and the
        flush.  The whole batch used to be parked for it -- one collision took
        every unrelated claim from the same document out of the review queue
        with it, which on BC5CDR would have removed 241 drafts across 66
        documents from view under the mention-label rule -- and nothing at all
        under MeSH labels.  Re-planning after the rollback sees the winner's
        committed row, so only the draft that collided with it is parked.

        Nothing is dropped either way: if the re-plan loses another race, the
        batch is parked whole rather than lost, which is the old behaviour kept
        as a bounded last resort.
        """

        models = self._persist_planned_batch(
            space_id=space_id,
            run_id=run_id,
            planned=self._plan_batch(space_id=space_id, proposals=proposals),
        )
        try:
            commit_or_flush(self.session)
        except IntegrityError as exc:
            self.session.rollback()
            if not _is_active_proposal_fingerprint_conflict(exc):
                raise
            return self._park_whole_batch(
                space_id=space_id,
                run_id=run_id,
                proposals=proposals,
            )
        return self._records_from_models(models)

    def _park_whole_batch(
        self,
        *,
        space_id: str,
        run_id: str,
        proposals: tuple[HarnessProposalDraft, ...],
    ) -> list[HarnessProposalRecord]:
        """Retain every draft as IDENTITY_PENDING when re-planning keeps racing.

        IDENTITY_PENDING is outside the active unique index, so this cannot
        collide with anything.  It costs review visibility for the whole batch,
        which is why it is the last resort and not the first response, but it
        never costs evidence.
        """

        models = self._persist_planned_batch(
            space_id=space_id,
            run_id=run_id,
            planned=[
                (
                    self.normalize_proposal_draft(proposal),
                    IDENTITY_PENDING_STATUS,
                    (
                        "Retained by ART-DATA-001: concurrent writers kept "
                        "claiming claim fingerprint "
                        f"{proposal.claim_fingerprint} for this space while "
                        "this batch was being written. Awaiting identity "
                        "adjudication; not auto-merged."
                    ),
                )
                for proposal in proposals
            ],
        )
        commit_or_flush(self.session)
        return self._records_from_models(models)

    def list_proposals(
        self,
        *,
        space_id: UUID | str,
        status: str | None = None,
        proposal_type: str | None = None,
        run_id: UUID | str | None = None,
        document_id: UUID | str | None = None,
        evidence_grade: str | None = None,
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
        normalized_evidence_grade = normalize_evidence_grade(evidence_grade)
        if normalized_evidence_grade is not None:
            stmt = stmt.where(
                HarnessProposalModel.evidence_grade == normalized_evidence_grade,
            )
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

    def delete_proposals_for_documents(
        self,
        *,
        space_id: UUID | str,
        document_ids: tuple[UUID | str, ...],
    ) -> int:
        target_ids = tuple(str(document_id) for document_id in document_ids)
        if not target_ids:
            return 0
        result = self.session.execute(
            delete(HarnessProposalModel).where(
                HarnessProposalModel.space_id == str(space_id),
                HarnessProposalModel.document_id.in_(target_ids),
            ),
        )
        commit_or_flush(self.session)
        return _result_rowcount(result)

    def decide_proposal(
        self,
        *,
        space_id: UUID | str,
        proposal_id: UUID | str,
        status: str,
        decision_reason: str | None,
        decided_by: ReviewActor | None,
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
            raise ValueError(
                undecidable_proposal_message(
                    proposal_id=proposal_id,
                    status=current_status,
                ),
            )
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
                decided_by_user_id=(
                    decided_by.user_id if decided_by is not None else None
                ),
                decided_by_email=(
                    decided_by.email if decided_by is not None else None
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
            raise ValueError(
                undecidable_proposal_message(
                    proposal_id=proposal_id,
                    status=refreshed_status_row[0],
                ),
            )
        commit_or_flush(self.session)
        refreshed_stmt = select(HarnessProposalModel).where(
            HarnessProposalModel.id == normalized_proposal_id,
            HarnessProposalModel.space_id == normalized_space_id,
        )
        model = self.session.execute(refreshed_stmt).scalars().first()
        if model is None:
            return None
        return _proposal_record_from_model(model)

    def adjudicate_parked_proposal(
        self,
        *,
        space_id: UUID | str,
        proposal_id: UUID | str,
        resolution: str,
        reason: str | None,
        decided_by: ReviewActor | None,
    ) -> HarnessProposalRecord | None:
        """Settle a parked proposal's identity, durably.

        Mirrors the in-memory store so the two cannot diverge on what an exit
        from ``identity_pending`` means.  Releasing as distinct clears the claim
        fingerprint, which is what lets the row return to ``pending_review``
        without colliding with its counterpart under migration 024's active
        unique index.
        """

        normalized_resolution = normalize_identity_resolution(resolution)
        model = self.session.get(HarnessProposalModel, str(proposal_id))
        if model is None or model.space_id != str(space_id):
            return None
        if model.status != IDENTITY_PENDING_STATUS:
            raise ValueError(
                unadjudicable_proposal_message(
                    proposal_id=proposal_id,
                    status=model.status,
                ),
            )
        decided_at = datetime.now(UTC)
        naive_decided_at = decided_at.replace(tzinfo=None)
        if normalized_resolution == DUPLICATE_RESOLUTION:
            counterpart_id = self._active_fingerprint_counterpart_id(
                space_id=model.space_id,
                claim_fingerprint=model.claim_fingerprint,
                exclude_id=model.id,
            )
            if counterpart_id is None:
                raise ValueError(
                    missing_duplicate_counterpart_message(proposal_id=proposal_id),
                )
            model.status = DUPLICATE_STATUS
            model.decision_reason = clean_decision_reason(reason)
            model.decided_at = naive_decided_at
            model.decided_by_user_id = (
                decided_by.user_id if decided_by is not None else None
            )
            model.decided_by_email = (
                decided_by.email if decided_by is not None else None
            )
            model.identity_adjudication_payload = build_identity_adjudication(
                resolution=normalized_resolution,
                duplicate_of_proposal_id=counterpart_id,
                released_claim_fingerprint=None,
                reason=reason,
                decided_by=decided_by,
                decided_at=decided_at,
            )
        else:
            model.identity_adjudication_payload = build_identity_adjudication(
                resolution=normalized_resolution,
                duplicate_of_proposal_id=None,
                released_claim_fingerprint=model.claim_fingerprint,
                reason=reason,
                decided_by=decided_by,
                decided_at=decided_at,
            )
            model.status = "pending_review"
            model.claim_fingerprint = None
            model.decision_reason = None
            model.decided_at = None
            model.decided_by_user_id = None
            model.decided_by_email = None
        commit_or_flush(self.session)
        self.session.refresh(model)
        return _proposal_record_from_model(model)

    def _active_fingerprint_counterpart_id(
        self,
        *,
        space_id: str,
        claim_fingerprint: str | None,
        exclude_id: str,
    ) -> str | None:
        """Return the id of the active proposal a parked one collided with."""

        if not claim_fingerprint:
            return None
        row = (
            self.session.execute(
                select(HarnessProposalModel.id)
                .where(
                    HarnessProposalModel.space_id == space_id,
                    HarnessProposalModel.claim_fingerprint == claim_fingerprint,
                    HarnessProposalModel.status.in_(["pending_review", "promoted"]),
                    HarnessProposalModel.id != exclude_id,
                )
                .limit(1),
            )
            .scalars()
            .first()
        )
        return str(row) if row is not None else None

    def reject_pending_duplicates(
        self,
        *,
        space_id: UUID | str,
        claim_fingerprint: str,
        exclude_id: UUID | str,
        reason: str,
    ) -> int:
        """Reject all pending_review proposals with the same fingerprint.

        Refuses an absent fingerprint.  ``column == None`` is not a comparison
        that never matches here -- SQLAlchemy renders it ``IS NULL`` -- so the
        UPDATE would have swept every fingerprint-less pending proposal in the
        space.  See ``require_fingerprint_for_bulk_reject``.
        """
        require_fingerprint_for_bulk_reject(claim_fingerprint)
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
        commit_or_flush(self.session)
        return _result_rowcount(result)


from .sqlalchemy_review_document_stores import (  # noqa: E402,I001
    SqlAlchemyHarnessApprovalStore,
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
