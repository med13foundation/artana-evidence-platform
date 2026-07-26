"""Unit tests for the remaining graph-harness SQLAlchemy domain stores."""

from __future__ import annotations

import hashlib
import sys
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import pytest
from artana_evidence_api.approval_store import (
    HarnessApprovalAction,
    HarnessApprovalStore,
)
from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimFrame,
    ClaimQualifier,
    EpistemicStatus,
    Polarity,
    SourceEvidenceSpan,
)
from artana_evidence_api.models.base import Base
from artana_evidence_api.models.harness import (
    HarnessDocumentModel,
    HarnessProposalModel,
    HarnessReviewItemModel,
    HarnessRunModel,
    HarnessStudyOutcomeModel,
)
from artana_evidence_api.models.research_space import (
    ResearchSpaceMembershipModel,
    ResearchSpaceModel,
)
from artana_evidence_api.proposal_store import (
    IDENTITY_PENDING_STATUS,
    HarnessProposalDraft,
)
from artana_evidence_api.research_space_store import HarnessResearchSpaceRecord
from artana_evidence_api.review_item_store import HarnessReviewItemDraft
from artana_evidence_api.sqlalchemy_stores import (
    SqlAlchemyHarnessApprovalStore,
    SqlAlchemyHarnessChatSessionStore,
    SqlAlchemyHarnessDocumentStore,
    SqlAlchemyHarnessGraphSnapshotStore,
    SqlAlchemyHarnessProposalStore,
    SqlAlchemyHarnessResearchSpaceStore,
    SqlAlchemyHarnessResearchStateStore,
    SqlAlchemyHarnessReviewItemStore,
    SqlAlchemyHarnessScheduleStore,
)
from artana_evidence_api.sqlalchemy_unit_of_work import session_unit_of_work
from artana_evidence_api.study_outcomes import SqlAlchemyStudyOutcomeStore
from artana_evidence_api.study_outcomes.contracts import StudyOutcomeDraft
from artana_evidence_api.types.review_actor import ReviewActor
from artana_evidence_api.types.source_provenance import (
    UNRECORDED_PROVENANCE_REASON,
    ClaimSourceProvenance,
    ExactEvidenceLocator,
    SourceIdentity,
)
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tests.sqlite_utils import attach_sqlite_schemas_for_metadata

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def _sqlite_schema_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        schema: tmp_path / f"sqlalchemy_store_{schema}.db"
        for schema in {
            table.schema for table in Base.metadata.tables.values() if table.schema
        }
    }


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    attach_sqlite_schemas_for_metadata(engine, Base.metadata)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    db_session = SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()
        engine.dispose()


@pytest.fixture
def shared_session_factory(
    tmp_path: Path,
) -> Iterator[sessionmaker[Session]]:
    database_path = tmp_path / "sqlalchemy_store_shared.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    attach_sqlite_schemas_for_metadata(
        engine,
        Base.metadata,
        schema_paths=_sqlite_schema_paths(tmp_path),
    )
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    try:
        yield session_local
    finally:
        engine.dispose()


def _create_run_catalog_entry(
    session: Session,
    *,
    space_id: str,
    harness_id: str,
    title: str,
    input_payload: dict[str, object],
) -> HarnessRunModel:
    model = HarnessRunModel(
        space_id=space_id,
        harness_id=harness_id,
        title=title,
        status="queued",
        input_payload=input_payload,
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )
    session.add(model)
    session.commit()
    session.refresh(model)
    return model


def test_harness_proposal_model_has_unique_active_fingerprint_index() -> None:
    index = next(
        index
        for index in HarnessProposalModel.__table__.indexes
        if index.name == "uq_harness_proposals_active_space_claim_fingerprint"
    )

    assert index.unique is True
    assert [column.name for column in index.columns] == [
        "space_id",
        "claim_fingerprint",
    ]
    assert "pending_review" in str(index.dialect_options["postgresql"]["where"])
    assert "promoted" in str(index.dialect_options["postgresql"]["where"])


def _claim_frame_for_persistence() -> ClaimFrame:
    """Return a minimal but real ClaimFrame, for its real dedupe identity."""

    span = "Osimertinib improved response versus chemotherapy."
    return ClaimFrame(
        subject="osimertinib",
        predicate="improves",
        object="response",
        source_evidence=SourceEvidenceSpan(
            exact_span=span,
            locator="chunk:1#sentence:1",
        ),
        polarity=Polarity.SUPPORT,
        epistemic_status=EpistemicStatus.ASSERTED,
        biological_or_variant_state=ClaimQualifier.not_applicable(),
        condition=ClaimQualifier.not_applicable(),
        population=ClaimQualifier.not_applicable(),
        intervention=ClaimQualifier.present(
            value="osimertinib",
            exact_span="Osimertinib",
        ),
        comparator=ClaimQualifier.present(
            value="chemotherapy",
            exact_span="chemotherapy",
        ),
        outcome=ClaimQualifier.present(
            value="response",
            exact_span="improved response",
        ),
        study_design=ClaimQualifier.not_applicable(),
        treatment_setting=ClaimQualifier.not_applicable(),
        timeframe=ClaimQualifier.not_applicable(),
        threshold=ClaimQualifier.not_applicable(),
        extraction_rationale="One unambiguous comparative finding.",
    )


def _fingerprint_column_length() -> int:
    length = HarnessProposalModel.__table__.c.claim_fingerprint.type.length
    assert length is not None, "claim_fingerprint must declare a bounded width"
    return int(length)


def test_a_frame_backed_proposal_fits_the_fingerprint_column(
    db_session: Session,
) -> None:
    """A frame-backed proposal must actually be persistable.

    ``ClaimFrame.dedupe_identity`` is a full 64-character SHA-256 and
    ``document_extraction_drafts`` writes it straight into ``claim_fingerprint``,
    which was declared varchar(32).  On Postgres every such insert raised
    ``StringDataRightTruncation``, so no frame-backed extraction proposal could
    be stored at all.

    This uses the shared ``db_session`` fixture rather than this module's
    in-memory SQLite one so that the gate runs it against real Postgres, where
    the insert is what fails.  The declared-width assertion is what fails on
    SQLite, which ignores VARCHAR length entirely and stores an over-long value
    happily -- that indifference is exactly how the defect survived a green
    suite.
    """

    frame = _claim_frame_for_persistence()
    fingerprint = frame.dedupe_identity
    assert len(fingerprint) == 64

    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        db_session,
        space_id=space_id,
        harness_id="document_extraction",
        title="Frame-backed extraction",
        input_payload={},
    )
    store = SqlAlchemyHarnessProposalStore(db_session)
    created = store.create_proposals(
        space_id=space_id,
        run_id=run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="document_extraction",
                source_key="document-1:0",
                title="Extracted claim: osimertinib improves response",
                summary="Osimertinib improved response versus chemotherapy.",
                confidence=0.8,
                ranking_score=0.9,
                reasoning_path={},
                evidence_bundle=[],
                payload={"proposed_claim_type": "ASSOCIATED_WITH"},
                metadata={"claim_frame_dedupe_identity": fingerprint},
                claim_fingerprint=fingerprint,
            ),
        ),
    )

    assert len(created) == 1
    assert created[0].claim_fingerprint == fingerprint
    reread = store.get_proposal(space_id=space_id, proposal_id=created[0].id)
    assert reread is not None
    assert reread.claim_fingerprint == fingerprint
    assert len(fingerprint) <= _fingerprint_column_length(), (
        "the store accepted a fingerprint wider than its own column; SQLite "
        "swallows that, Postgres raises StringDataRightTruncation"
    )


def test_an_evidence_selection_fingerprint_fits_its_column() -> None:
    """The other over-wide writer: a namespaced evidence-selection fingerprint.

    ``evidence_selection_review_staging`` writes
    ``evidence-selection:<sha256>`` (83 characters) and
    ``evidence-selection-review:<sha256>`` (90).  Both are produced by the same
    staging call, so widening only one side would turn a symmetric failure into
    a proposal that lands without its review item.
    """

    record_hash = hashlib.sha256(b"{}").hexdigest()
    proposal_fingerprint = f"evidence-selection:{record_hash}"
    review_fingerprint = f"evidence-selection-review:{record_hash}"

    proposal_width = _fingerprint_column_length()
    review_width = HarnessReviewItemModel.__table__.c.review_fingerprint.type.length
    assert review_width is not None

    assert len(proposal_fingerprint) <= proposal_width
    assert len(review_fingerprint) <= int(review_width)


def _parked_pair(
    session: Session,
    *,
    fingerprint: str,
) -> tuple[SqlAlchemyHarnessProposalStore, str, str, str]:
    """Persist one active proposal and one parked collision against it."""

    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="document_extraction",
        title="Cross-document collision",
        input_payload={},
    )
    store = SqlAlchemyHarnessProposalStore(session)

    def _draft(source_document: str, title: str) -> HarnessProposalDraft:
        # document_id is left unset: these rows are not linked to persisted
        # documents, and unknown provenance is treated as a distinct source,
        # which is what parks the second one.
        return HarnessProposalDraft(
            proposal_type="candidate_claim",
            source_kind="document_extraction",
            source_key=f"{source_document}:0",
            title=title,
            summary="A candidate claim from one document.",
            confidence=0.8,
            ranking_score=0.9,
            reasoning_path={},
            evidence_bundle=[],
            payload={"proposed_claim_type": "ASSOCIATED_WITH"},
            metadata={},
            claim_fingerprint=fingerprint,
        )

    first = store.create_proposals(
        space_id=space_id,
        run_id=run.id,
        proposals=(_draft(str(uuid4()), "First observation"),),
    )
    second = store.create_proposals(
        space_id=space_id,
        run_id=run.id,
        proposals=(_draft(str(uuid4()), "Second observation"),),
    )
    assert second[0].status == IDENTITY_PENDING_STATUS
    return store, space_id, first[0].id, second[0].id


def test_releasing_a_parked_proposal_does_not_collide_with_the_active_index(
    db_session: Session,
) -> None:
    """Release has to survive the very index that parked the record.

    ``uq_harness_proposals_active_space_claim_fingerprint`` covers
    (space_id, claim_fingerprint) while the status is pending_review or
    promoted.  Returning a parked row to pending_review with its fingerprint
    intact would therefore be rejected by the database, so releasing it clears
    the fingerprint the reviewer just declared non-identifying.
    """

    fingerprint = "e" * 48
    store, space_id, _active_id, parked_id = _parked_pair(
        db_session,
        fingerprint=fingerprint,
    )

    released = store.adjudicate_parked_proposal(
        space_id=space_id,
        proposal_id=parked_id,
        resolution="distinct",
        reason="Two different chemicals.",
        decided_by=ReviewActor(user_id=str(uuid4()), email="reviewer@example.com"),
    )

    assert released is not None
    assert released.status == "pending_review"
    assert released.claim_fingerprint is None
    assert released.decided_at is None
    assert released.identity_adjudication is not None
    assert released.identity_adjudication["released_claim_fingerprint"] == fingerprint
    reread = store.get_proposal(space_id=space_id, proposal_id=parked_id)
    assert reread is not None
    assert reread.identity_adjudication == released.identity_adjudication


def test_resolving_a_parked_proposal_as_duplicate_names_its_counterpart(
    db_session: Session,
) -> None:
    """A duplicate is retained and points at what it duplicates, not deleted."""

    fingerprint = "f" * 48
    store, space_id, active_id, parked_id = _parked_pair(
        db_session,
        fingerprint=fingerprint,
    )

    resolved = store.adjudicate_parked_proposal(
        space_id=space_id,
        proposal_id=parked_id,
        resolution="duplicate",
        reason="Same assertion in two papers.",
        decided_by=ReviewActor(user_id=str(uuid4()), email="reviewer@example.com"),
    )

    assert resolved is not None
    assert resolved.status == "duplicate"
    assert resolved.claim_fingerprint == fingerprint
    assert resolved.decided_by is not None
    assert resolved.identity_adjudication is not None
    assert (
        resolved.identity_adjudication["duplicate_of_proposal_id"] == active_id
    )
    still_active = store.get_proposal(space_id=space_id, proposal_id=active_id)
    assert still_active is not None
    assert still_active.status == "pending_review"


class _NoDuplicateResult:
    def first(self) -> None:
        return None


class _ConflictingHolderResult:
    def first(self) -> tuple[str, str, None]:
        return ("concurrent-proposal", "pending_review", None)


class _LostRaceSession:
    """A session that loses one fingerprint to a concurrent writer.

    The writer's row becomes visible only after the rollback, which is what
    really happens: it was committed by another transaction while this one held
    an older snapshot.  Reporting it as invisible forever would let the retry
    "succeed" for a reason no production race ever offers.
    """

    added: list[HarnessProposalModel]
    rolled_back: bool
    commits: int

    def __init__(self, *, contested_fingerprint: str) -> None:
        self.added = []
        self.rolled_back = False
        self.commits = 0
        self._contested_fingerprint = contested_fingerprint

    def execute(self, stmt) -> _NoDuplicateResult | _ConflictingHolderResult:  # noqa: ANN001
        if not self.rolled_back:
            return _NoDuplicateResult()
        queried = stmt.compile().params.values()
        if any(value == self._contested_fingerprint for value in queried):
            return _ConflictingHolderResult()
        return _NoDuplicateResult()

    def add(self, model: HarnessProposalModel) -> None:
        self.added.append(model)

    def commit(self) -> None:
        self.commits += 1
        if self.commits == 1:
            raise IntegrityError(
                statement="INSERT INTO harness_proposals",
                params={},
                orig=Exception("duplicate active fingerprint"),
            )

    def rollback(self) -> None:
        self.rolled_back = True

    def refresh(self, model: HarnessProposalModel) -> None:
        model.id = model.id or uuid4()
        model.created_at = model.created_at or datetime.now(UTC).replace(tzinfo=None)
        model.updated_at = model.updated_at or model.created_at


def _race_draft(*, source_key: str, fingerprint: str) -> HarnessProposalDraft:
    return HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key=source_key,
        title=f"Candidate {source_key}",
        summary="One claim extracted from a document.",
        confidence=0.83,
        ranking_score=0.91,
        reasoning_path={},
        evidence_bundle=[],
        payload={"proposed_claim_type": "ASSOCIATED_WITH"},
        metadata={},
        claim_fingerprint=fingerprint,
    )


def test_sqlalchemy_harness_proposal_store_retains_unique_conflict_race() -> None:
    """ART-DATA-001: losing the fingerprint race must not discard the batch.

    A concurrent writer can claim the fingerprint between the pre-check and the
    flush.  The batch is retried, and the proposal that lost is retained as
    IDENTITY_PENDING, which cannot collide because the unique index only covers
    active statuses.
    """

    contested = "duplicatefingerprint000000000001"
    session = _LostRaceSession(contested_fingerprint=contested)
    store = SqlAlchemyHarnessProposalStore(cast("Session", session))
    created = store.create_proposals(
        space_id=str(uuid4()),
        run_id=str(uuid4()),
        proposals=(
            _race_draft(source_key="duplicate-race", fingerprint=contested),
        ),
    )

    assert len(created) == 1, "the lost-race batch must survive"
    assert created[0].status == IDENTITY_PENDING_STATUS
    assert created[0].decision_reason is not None
    assert session.added
    assert session.rolled_back is True


def test_losing_one_fingerprint_race_parks_only_the_proposal_that_lost() -> None:
    """One collision must not take the rest of the document's claims with it.

    The retry used to re-persist the entire batch as IDENTITY_PENDING, so a
    single contested fingerprint removed every unrelated claim extracted from
    the same document from the review queue.  On BC5CDR that pattern would have
    parked 241 drafts across the 66 documents (4.4%) that contain a colliding
    pair.
    """

    contested = "contestedfingerprint000000000001"
    session = _LostRaceSession(contested_fingerprint=contested)
    store = SqlAlchemyHarnessProposalStore(cast("Session", session))

    created = store.create_proposals(
        space_id=str(uuid4()),
        run_id=str(uuid4()),
        proposals=(
            _race_draft(source_key="claim-0", fingerprint="uncontested0000000000000000000a"),
            _race_draft(source_key="claim-1", fingerprint=contested),
            _race_draft(source_key="claim-2", fingerprint="uncontested0000000000000000000b"),
            _race_draft(source_key="claim-3", fingerprint="uncontested0000000000000000000c"),
        ),
    )

    assert session.rolled_back is True
    by_source_key = {record.source_key: record for record in created}
    assert len(by_source_key) == 4, "nothing may be dropped"
    assert by_source_key["claim-1"].status == IDENTITY_PENDING_STATUS
    assert [
        source_key
        for source_key, record in sorted(by_source_key.items())
        if record.status == "pending_review"
    ] == ["claim-0", "claim-2", "claim-3"]


def test_two_drafts_in_one_batch_sharing_a_fingerprint_park_only_one(
    db_session: Session,
) -> None:
    """A collision inside one batch must cost one draft, not the batch.

    The pre-check queried committed rows and the session does not autoflush, so
    a sibling draft in the same batch was invisible to it: both were planned as
    pending_review, the partial unique index rejected the insert, and the whole
    batch was retained as IDENTITY_PENDING -- unreviewable.  One extraction pass
    producing two claims with the same fingerprint is ordinary, not exceptional.
    """

    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        db_session,
        space_id=space_id,
        harness_id="document_extraction",
        title="One document, four claims",
        input_payload={},
    )
    store = SqlAlchemyHarnessProposalStore(db_session)
    shared = "sharedwithinbatch00000000000001"

    created = store.create_proposals(
        space_id=space_id,
        run_id=run.id,
        proposals=(
            _race_draft(source_key="claim-0", fingerprint="distinct000000000000000000000a"),
            _race_draft(source_key="claim-1", fingerprint=shared),
            _race_draft(source_key="claim-2", fingerprint=shared),
            _race_draft(source_key="claim-3", fingerprint="distinct000000000000000000000b"),
        ),
    )

    assert len(created) == 4, "nothing may be dropped"
    statuses = {record.source_key: record.status for record in created}
    assert statuses["claim-0"] == "pending_review"
    assert statuses["claim-3"] == "pending_review"
    assert sorted([statuses["claim-1"], statuses["claim-2"]]) == [
        IDENTITY_PENDING_STATUS,
        "pending_review",
    ]

    persisted = store.list_proposals(space_id=space_id, run_id=run.id)
    assert len(persisted) == 4
    assert (
        sum(1 for record in persisted if record.status == "pending_review")
    ) == 3, "three of the four must still be reviewable"


def test_a_proposal_without_provenance_reads_back_as_explicitly_unverified(
    session: Session,
) -> None:
    """Absent provenance must not reach a reviewer as an empty field.

    Migration 025 records source_provenance_status on every row even when no
    envelope is written. The read path ignored it and returned None, so "never
    computed" and "computed and rejected" looked identical next to a claim
    someone is being asked to accept.
    """
    proposal_store = SqlAlchemyHarnessProposalStore(session)
    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="document-extraction",
        title="Provenance-free run",
        input_payload={},
    )

    created = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="entity_candidate",
                source_kind="document_extraction",
                source_key="doc:entity:1",
                title="Candidate entity",
                summary="No provenance was computed for this type",
                confidence=0.7,
                ranking_score=0.7,
                reasoning_path={},
                evidence_bundle=[],
                payload={},
                metadata={},
            ),
        ),
    )

    provenance = created[0].source_provenance
    assert provenance is not None, "absent provenance must not serialize as null"
    assert provenance.status == "unverified"
    assert provenance.reason_code == UNRECORDED_PROVENANCE_REASON
    assert provenance.source_identity is None
    assert provenance.evidence_locator is None

    reloaded = proposal_store.get_proposal(
        space_id=space_id,
        proposal_id=created[0].id,
    )
    assert reloaded is not None
    assert reloaded.source_provenance == provenance


def test_sqlalchemy_upsert_intent_preserves_decided_approvals(
    session: Session,
) -> None:
    """Re-proposing a run's intent must not erase decisions already made.

    upsert_intent deleted every approval for the run and recreated them all as
    pending, so a second POST of the intent destroyed the written reason and the
    reviewer identity on anything a person had already decided.
    """
    approval_store = SqlAlchemyHarnessApprovalStore(session)
    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="claim-curation",
        title="Intent replay run",
        input_payload={},
    )
    actions = (
        HarnessApprovalAction(
            approval_key="decided-key",
            title="Promote candidate claim",
            risk_level="high",
            target_type="claim",
            target_id="claim-1",
            requires_approval=True,
            metadata={},
        ),
        HarnessApprovalAction(
            approval_key="pending-key",
            title="Persist curation summary",
            risk_level="low",
            target_type="artifact",
            target_id="summary-1",
            requires_approval=True,
            metadata={},
        ),
    )
    reviewer = ReviewActor(
        user_id="66666666-6666-6666-6666-666666666666",
        email="intent-reviewer@example.com",
    )

    approval_store.upsert_intent(
        space_id=space_id,
        run_id=run.id,
        summary="Review proposed graph updates",
        proposed_actions=actions,
        metadata={},
    )
    approval_store.decide_approval(
        space_id=space_id,
        run_id=run.id,
        approval_key="decided-key",
        status="approved",
        decision_reason="Checked against the source; safe to write.",
        decided_by=reviewer,
    )

    approval_store.upsert_intent(
        space_id=space_id,
        run_id=run.id,
        summary="Review proposed graph updates",
        proposed_actions=actions,
        metadata={},
    )

    approvals = {
        approval.approval_key: approval
        for approval in approval_store.list_approvals(
            space_id=space_id,
            run_id=run.id,
        )
    }
    assert approvals["decided-key"].status == "approved"
    assert (
        approvals["decided-key"].decision_reason
        == "Checked against the source; safe to write."
    )
    assert approvals["decided-key"].decided_by == reviewer
    assert approvals["pending-key"].status == "pending"


def test_sqlalchemy_upsert_intent_reopens_an_approval_whose_action_changed(
    session: Session,
) -> None:
    """A decision describes one action, not one approval key.

    ``uq_harness_run_approvals_run_id_approval_key`` allows exactly one row per
    (run, key), so keeping the decided row when a re-proposed action reuses the
    key with different content leaves the run with nothing pending -- it would
    proceed on a human decision made about a different action.
    """
    approval_store = SqlAlchemyHarnessApprovalStore(session)
    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="claim-curation",
        title="Changed action run",
        input_payload={},
    )
    reviewer = ReviewActor(
        user_id="66666666-6666-6666-6666-666666666666",
        email="intent-reviewer@example.com",
    )

    approval_store.upsert_intent(
        space_id=space_id,
        run_id=run.id,
        summary="Review proposed graph updates",
        proposed_actions=(
            HarnessApprovalAction(
                approval_key="decided-key",
                title="Promote candidate claim",
                risk_level="high",
                target_type="claim",
                target_id="claim-1",
                requires_approval=True,
                metadata={"passage": "first"},
            ),
        ),
        metadata={},
    )
    approval_store.decide_approval(
        space_id=space_id,
        run_id=run.id,
        approval_key="decided-key",
        status="approved",
        decision_reason="Checked against the source; safe to write.",
        decided_by=reviewer,
    )

    changed = (
        HarnessApprovalAction(
            approval_key="decided-key",
            title="Promote candidate claim",
            risk_level="high",
            target_type="claim",
            target_id="claim-2",
            requires_approval=True,
            metadata={"passage": "first"},
        ),
    )
    approval_store.upsert_intent(
        space_id=space_id,
        run_id=run.id,
        summary="Review proposed graph updates",
        proposed_actions=changed,
        metadata={},
    )
    # A reopened row is pending, and pending rows are replaced on every
    # re-proposal -- the carried decision has to survive that too.
    approval_store.upsert_intent(
        space_id=space_id,
        run_id=run.id,
        summary="Review proposed graph updates",
        proposed_actions=changed,
        metadata={},
    )

    approvals = approval_store.list_approvals(space_id=space_id, run_id=run.id)
    assert len(approvals) == 1
    reopened = approvals[0]
    assert reopened.status == "pending"
    assert reopened.decision_reason is None
    assert reopened.decided_by is None
    assert reopened.target_id == "claim-2"
    assert reopened.metadata == {"passage": "first"}
    history = reopened.superseded_decisions
    assert len(history) == 1
    assert history[0].status == "approved"
    assert history[0].decision_reason == "Checked against the source; safe to write."
    assert history[0].decided_by == reviewer
    assert history[0].target_id == "claim-1"
    # The parameters that were actually approved, not just the target.
    assert history[0].metadata == {"passage": "first"}
    # Durable rows keep naive UTC; the trail must still say which zone it is in.
    assert history[0].decided_at.endswith("+00:00")


def test_both_approval_stores_render_a_superseded_decision_identically(
    session: Session,
) -> None:
    """The two stores disagree about tzinfo on ``updated_at``.

    The durable store writes naive UTC and the in-memory store keeps the offset,
    so a bare isoformat() renders the same audit record two different ways --
    the exact ambiguity ``serialize_timestamp`` exists to remove.
    """
    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="claim-curation",
        title="Timestamp parity run",
        input_payload={},
    )
    reviewer = ReviewActor(
        user_id="66666666-6666-6666-6666-666666666666",
        email="intent-reviewer@example.com",
    )
    approved = HarnessApprovalAction(
        approval_key="parity-key",
        title="Promote candidate claim",
        risk_level="high",
        target_type="claim",
        target_id="claim-1",
        requires_approval=True,
        metadata={},
    )
    changed = HarnessApprovalAction(
        approval_key="parity-key",
        title="Promote candidate claim",
        risk_level="high",
        target_type="claim",
        target_id="claim-2",
        requires_approval=True,
        metadata={},
    )

    trails = []
    for store in (SqlAlchemyHarnessApprovalStore(session), HarnessApprovalStore()):
        store.upsert_intent(
            space_id=space_id,
            run_id=run.id,
            summary="Review proposed graph updates",
            proposed_actions=(approved,),
            metadata={},
        )
        store.decide_approval(
            space_id=space_id,
            run_id=run.id,
            approval_key="parity-key",
            status="approved",
            decision_reason="Safe to write.",
            decided_by=reviewer,
        )
        store.upsert_intent(
            space_id=space_id,
            run_id=run.id,
            summary="Review proposed graph updates",
            proposed_actions=(changed,),
            metadata={},
        )
        trails.append(
            store.list_approvals(space_id=space_id, run_id=run.id)[0]
            .superseded_decisions[0]
            .decided_at,
        )

    durable, in_memory = trails
    assert durable.endswith("+00:00")
    assert in_memory.endswith("+00:00")


def test_sqlalchemy_harness_approval_store_persists_intents_and_decisions(
    session: Session,
) -> None:
    approval_store = SqlAlchemyHarnessApprovalStore(session)
    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="claim-curation",
        title="Curation run",
        input_payload={"proposal_id": "proposal-1"},
    )

    intent = approval_store.upsert_intent(
        space_id=space_id,
        run_id=run.id,
        summary="Review proposed graph updates",
        proposed_actions=(
            HarnessApprovalAction(
                approval_key="promote-claim-1",
                title="Promote candidate claim",
                risk_level="high",
                target_type="claim",
                target_id="claim-1",
                requires_approval=True,
                metadata={"origin": "chat"},
            ),
            HarnessApprovalAction(
                approval_key="save-summary",
                title="Persist curation summary",
                risk_level="low",
                target_type="artifact",
                target_id="summary-1",
                requires_approval=False,
                metadata={"origin": "run"},
            ),
        ),
        metadata={"stage": "review"},
    )
    assert intent.summary == "Review proposed graph updates"
    assert len(intent.proposed_actions) == 2

    fetched_intent = approval_store.get_intent(space_id=space_id, run_id=run.id)
    assert fetched_intent is not None
    assert fetched_intent.metadata["stage"] == "review"

    approvals = approval_store.list_approvals(space_id=space_id, run_id=run.id)
    assert len(approvals) == 1
    assert approvals[0].approval_key == "promote-claim-1"
    assert approvals[0].status == "pending"

    decided = approval_store.decide_approval(
        space_id=space_id,
        run_id=run.id,
        approval_key="promote-claim-1",
        status="approved",
        decision_reason="Evidence is sufficient",
        decided_by=None,
    )
    assert decided is not None
    assert decided.status == "approved"
    assert decided.decision_reason == "Evidence is sufficient"

    with pytest.raises(ValueError, match="already decided"):
        approval_store.decide_approval(
            space_id=space_id,
            run_id=run.id,
            approval_key="promote-claim-1",
            status="rejected",
            decision_reason="Trying to override the first decision",
            decided_by=None,
        )


def test_sqlalchemy_harness_approval_store_normalizes_oversized_titles(
    session: Session,
) -> None:
    approval_store = SqlAlchemyHarnessApprovalStore(session)
    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="claim-curation",
        title="Curation run",
        input_payload={"proposal_id": "proposal-1"},
    )

    long_title = "Apply proposal: " + ("very long extracted claim " * 20)
    intent = approval_store.upsert_intent(
        space_id=space_id,
        run_id=run.id,
        summary="Review oversized approval titles",
        proposed_actions=(
            HarnessApprovalAction(
                approval_key="promote-claim-1",
                title=long_title,
                risk_level="high",
                target_type="claim",
                target_id="claim-1",
                requires_approval=True,
                metadata={"origin": "chat"},
            ),
        ),
        metadata={},
    )

    assert len(intent.proposed_actions) == 1
    assert len(intent.proposed_actions[0].title) <= 256
    assert intent.proposed_actions[0].title.endswith("...")

    approvals = approval_store.list_approvals(space_id=space_id, run_id=run.id)
    assert len(approvals) == 1
    assert len(approvals[0].title) <= 256
    assert approvals[0].title.endswith("...")


def test_sqlalchemy_harness_chat_session_store_persists_sessions_and_messages(
    session: Session,
) -> None:
    chat_store = SqlAlchemyHarnessChatSessionStore(session)
    space_id = str(uuid4())
    user_id = str(uuid4())
    run_id = str(uuid4())

    created_session = chat_store.create_session(
        space_id=space_id,
        title="New Graph Chat",
        created_by=user_id,
    )
    assert created_session.created_by == user_id
    assert created_session.last_run_id is None

    fetched_session = chat_store.get_session(
        space_id=space_id,
        session_id=created_session.id,
    )
    assert fetched_session is not None
    assert fetched_session.title == "New Graph Chat"

    user_message = chat_store.add_message(
        space_id=space_id,
        session_id=created_session.id,
        role="user",
        content="What does MED13 do?",
        run_id=run_id,
        metadata={"message_kind": "question"},
    )
    assert user_message is not None
    assert user_message.run_id == run_id

    assistant_message = chat_store.add_message(
        space_id=space_id,
        session_id=created_session.id,
        role="assistant",
        content="Synthetic grounded answer.",
        run_id=run_id,
        metadata={"message_kind": "answer"},
    )
    assert assistant_message is not None

    updated_session = chat_store.update_session(
        space_id=space_id,
        session_id=created_session.id,
        title="What does MED13 do?",
        last_run_id=run_id,
        status="active",
    )
    assert updated_session is not None
    assert updated_session.title == "What does MED13 do?"
    assert updated_session.last_run_id == run_id
    assert updated_session.status == "active"

    listed_sessions = chat_store.list_sessions(space_id=space_id)
    assert [record.id for record in listed_sessions] == [created_session.id]

    messages = chat_store.list_messages(
        space_id=space_id,
        session_id=created_session.id,
    )
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].metadata["message_kind"] == "question"


def test_sqlalchemy_harness_document_store_persists_and_updates_documents(
    session: Session,
) -> None:
    document_store = SqlAlchemyHarnessDocumentStore(session)
    space_id = str(uuid4())
    user_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="document-ingestion",
        title="Document ingestion",
        input_payload={"title": "MED13 evidence note"},
    )

    created_document = document_store.create_document(
        space_id=space_id,
        created_by=user_id,
        title="<script>alert(1)</script>",
        source_type="text",
        filename=None,
        media_type="text/plain",
        sha256="abc123",
        byte_size=64,
        page_count=None,
        text_content="MED13 associates with cardiomyopathy.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=run.id,
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={"origin": "sqlalchemy-test"},
    )
    assert created_document.title == "alert(1)"
    assert created_document.text_excerpt.startswith("MED13 associates")

    fetched_document = document_store.get_document(
        space_id=space_id,
        document_id=created_document.id,
    )
    assert fetched_document is not None
    assert fetched_document.metadata["origin"] == "sqlalchemy-test"

    updated_document = document_store.update_document(
        space_id=space_id,
        document_id=created_document.id,
        title="<b>MED13 evidence note</b>",
        last_enrichment_run_id=str(uuid4()),
        extraction_status="completed",
        last_extraction_run_id=str(uuid4()),
        metadata_patch={"proposal_count": 1},
    )
    assert updated_document is not None
    assert updated_document.title == "MED13 evidence note"
    assert updated_document.extraction_status == "completed"
    assert updated_document.last_enrichment_run_id is not None
    assert updated_document.metadata["proposal_count"] == 1

    listed_documents = document_store.list_documents(space_id=space_id)
    assert [document.id for document in listed_documents] == [created_document.id]


def test_sqlalchemy_harness_document_store_counts_finds_and_updates_content(
    session: Session,
) -> None:
    document_store = SqlAlchemyHarnessDocumentStore(session)
    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="document-ingestion",
        title="Document ingestion",
        input_payload={"title": "Durable document"},
    )

    created = document_store.create_document(
        space_id=space_id,
        created_by=str(uuid4()),
        title="Durable document",
        source_type="pdf",
        filename="evidence.pdf",
        media_type="application/pdf",
        sha256="pdf-sha-123",
        byte_size=128,
        page_count=None,
        text_content="",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=run.id,
        last_enrichment_run_id=None,
        enrichment_status="not_started",
        extraction_status="not_started",
        metadata=None,
    )

    assert document_store.count_documents(space_id=space_id) == 1
    assert document_store.count_documents(space_id=str(uuid4())) == 0
    assert (
        document_store.find_document_by_sha256(
            space_id=space_id,
            sha256="pdf-sha-123",
        )
        is not None
    )
    assert (
        document_store.find_document_by_sha256(
            space_id=space_id,
            sha256="missing-sha",
        )
        is None
    )
    assert (
        document_store.get_document(space_id=str(uuid4()), document_id=created.id)
        is None
    )
    assert (
        document_store.update_document(
            space_id=space_id,
            document_id=str(uuid4()),
            text_content="missing",
        )
        is None
    )

    updated = document_store.update_document(
        space_id=space_id,
        document_id=created.id,
        text_content="Line one\nLine two",
        page_count=2,
        raw_storage_key="documents/raw/evidence.pdf",
        enriched_storage_key="documents/enriched/evidence.txt",
        enrichment_status="completed",
        metadata_patch={"page_range": "1-2"},
    )

    assert updated is not None
    assert updated.text_excerpt == "Line one Line two"
    assert updated.page_count == 2
    assert updated.raw_storage_key == "documents/raw/evidence.pdf"
    assert updated.enriched_storage_key == "documents/enriched/evidence.txt"
    assert updated.enrichment_status == "completed"
    assert updated.metadata["page_range"] == "1-2"


def test_sqlalchemy_document_delete_contract_removes_document_children(
    session: Session,
) -> None:
    document_store = SqlAlchemyHarnessDocumentStore(session)
    proposal_store = SqlAlchemyHarnessProposalStore(session)
    review_item_store = SqlAlchemyHarnessReviewItemStore(session)
    outcome_store = SqlAlchemyStudyOutcomeStore(session)
    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="document-ingestion",
        title="Document ingestion",
        input_payload={"title": "DrugMechDB document"},
    )
    document = document_store.create_document(
        space_id=space_id,
        created_by=str(uuid4()),
        title="DrugMechDB document",
        source_type="DrugMechDB",
        filename=None,
        media_type="text/plain",
        sha256="delete-sha",
        byte_size=128,
        page_count=None,
        text_content="DrugMechDB mechanism.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=run.id,
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="completed",
        metadata={},
    )
    proposal_store.create_proposals(
        space_id=space_id,
        run_id=run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="DrugMechDB",
                source_key="drugmechdb:proposal",
                title="DrugMechDB proposal",
                summary="DrugMechDB proposal.",
                confidence=0.8,
                ranking_score=0.8,
                reasoning_path={},
                evidence_bundle=[],
                payload={"proposed_claim_type": "ASSOCIATED_WITH"},
                metadata={},
                document_id=document.id,
            ),
        ),
    )
    review_item_store.create_review_items(
        space_id=space_id,
        run_id=run.id,
        review_items=(
            HarnessReviewItemDraft(
                review_type="source_review",
                source_family="DrugMechDB",
                source_kind="DrugMechDB",
                source_key="drugmechdb:review",
                title="DrugMechDB review",
                summary="DrugMechDB review.",
                priority="medium",
                confidence=0.7,
                ranking_score=0.7,
                evidence_bundle=[],
                payload={},
                metadata={},
                document_id=document.id,
            ),
        ),
    )
    outcome_store.create_outcomes(
        space_id=space_id,
        document_id=document.id,
        run_id=run.id,
        outcomes=(
            StudyOutcomeDraft(
                intervention="Drug",
                comparator=None,
                outcome_metric="median_os",
                value=12.0,
                unit="months",
                confidence_interval_low=None,
                confidence_interval_high=None,
                population="reported trial population",
                n=10,
                source_pmid="123",
                source_quote="Median OS was 12 months.",
                metadata={},
            ),
        ),
    )

    assert (
        proposal_store.delete_proposals_for_documents(
            space_id=space_id,
            document_ids=(document.id,),
        )
        == 1
    )
    assert (
        review_item_store.delete_review_items_for_documents(
            space_id=space_id,
            document_ids=(document.id,),
        )
        == 1
    )
    assert (
        outcome_store.delete_outcomes_for_documents(
            space_id=space_id,
            document_ids=(document.id,),
        )
        == 1
    )
    assert document_store.delete_documents(
        space_id=space_id,
        document_ids=(document.id,),
    ) == [document]

    assert session.execute(select(HarnessProposalModel)).scalars().all() == []
    assert session.execute(select(HarnessReviewItemModel)).scalars().all() == []
    assert session.execute(select(HarnessStudyOutcomeModel)).scalars().all() == []
    assert session.execute(select(HarnessDocumentModel)).scalars().all() == []


def test_sqlalchemy_harness_proposal_store_filters_by_document_id(
    session: Session,
) -> None:
    proposal_store = SqlAlchemyHarnessProposalStore(session)
    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="document-extraction",
        title="Document extraction",
        input_payload={"document_id": str(uuid4())},
    )
    target_document_id = str(uuid4())

    created = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="document_extraction",
                source_key="doc-a:0",
                title="Proposal A",
                summary="Summary A",
                confidence=0.82,
                ranking_score=0.91,
                reasoning_path={},
                evidence_bundle=[],
                payload={
                    "proposed_subject": str(uuid4()),
                    "proposed_claim_type": "ASSOCIATED_WITH",
                },
                metadata={"origin": "a"},
                document_id=target_document_id,
                evidence_grade="High",
            ),
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="document_extraction",
                source_key="doc-b:0",
                title="Proposal B",
                summary="Summary B",
                confidence=0.7,
                ranking_score=0.75,
                reasoning_path={},
                evidence_bundle=[],
                payload={
                    "proposed_subject": str(uuid4()),
                    "proposed_claim_type": "ASSOCIATED_WITH",
                },
                metadata={"origin": "b"},
                document_id=str(uuid4()),
                evidence_grade="Limited",
            ),
        ),
    )
    assert len(created) == 2

    filtered = proposal_store.list_proposals(
        space_id=space_id,
        document_id=target_document_id,
    )
    assert len(filtered) == 1
    assert filtered[0].document_id == target_document_id
    grade_filtered = proposal_store.list_proposals(
        space_id=space_id,
        evidence_grade="high",
    )
    assert len(grade_filtered) == 1
    assert grade_filtered[0].evidence_grade == "High"


def test_sqlalchemy_harness_research_space_store_generates_space_ids(
    session: Session,
) -> None:
    research_space_store = SqlAlchemyHarnessResearchSpaceStore(session)
    owner_id = str(uuid4())

    created_space = research_space_store.create_space(
        owner_id=owner_id,
        name="Graph Harness Research Space",
        description="DB-backed regression check for generated UUIDs.",
    )

    assert created_space.id != ""
    assert created_space.name == "Graph Harness Research Space"
    assert created_space.role == "owner"
    assert created_space.is_default is False


class _RecordingSpaceLifecycleSync:
    def __init__(self) -> None:
        self.spaces: list[HarnessResearchSpaceRecord] = []

    def sync_space(self, space: HarnessResearchSpaceRecord) -> None:
        self.spaces.append(space)


class _FailingSpaceLifecycleSync:
    def sync_space(self, space: HarnessResearchSpaceRecord) -> None:
        del space
        raise RuntimeError("graph sync unavailable")


def test_sqlalchemy_harness_research_space_store_syncs_created_space(
    session: Session,
) -> None:
    sync = _RecordingSpaceLifecycleSync()
    research_space_store = SqlAlchemyHarnessResearchSpaceStore(
        session,
        space_lifecycle_sync=sync,
    )
    owner_id = UUID("00000000-0000-4000-a000-000000e27001")

    created_space = research_space_store.create_space(
        owner_id=owner_id,
        owner_email="sync-owner@example.com",
        owner_role="researcher",
        name="Synchronized Space",
        description="Space creation should push the graph tenant snapshot.",
    )

    persisted_space = session.get(ResearchSpaceModel, UUID(created_space.id))
    assert persisted_space is not None
    persisted_membership = (
        session.query(ResearchSpaceMembershipModel)
        .filter(
            ResearchSpaceMembershipModel.space_id == UUID(created_space.id),
            ResearchSpaceMembershipModel.user_id == owner_id,
        )
        .one_or_none()
    )
    assert persisted_membership is not None
    assert len(sync.spaces) == 1
    assert sync.spaces[0].id == UUID(created_space.id)
    assert sync.spaces[0].slug == created_space.slug


def test_sqlalchemy_harness_research_space_store_rolls_back_when_sync_fails(
    session: Session,
) -> None:
    research_space_store = SqlAlchemyHarnessResearchSpaceStore(
        session,
        space_lifecycle_sync=_FailingSpaceLifecycleSync(),
    )
    owner_id = UUID("00000000-0000-4000-a000-000000e27002")

    with pytest.raises(RuntimeError, match="graph sync unavailable"):
        research_space_store.create_space(
            owner_id=owner_id,
            owner_email="failing-sync@example.com",
            owner_role="researcher",
            name="Unsynced Space",
            description="Creation should roll back when graph sync fails.",
        )

    persisted_spaces = (
        session.query(ResearchSpaceModel)
        .filter(ResearchSpaceModel.name == "Unsynced Space")
        .all()
    )
    persisted_memberships = (
        session.query(ResearchSpaceMembershipModel)
        .filter(ResearchSpaceMembershipModel.user_id == owner_id)
        .all()
    )
    assert persisted_spaces == []
    assert persisted_memberships == []


def test_sqlalchemy_harness_research_space_store_retries_slug_collision(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    research_space_store = SqlAlchemyHarnessResearchSpaceStore(session)
    existing_owner_id = UUID("00000000-0000-4000-a000-000000e27003")
    new_owner_id = UUID("00000000-0000-4000-a000-000000e27004")
    existing_space = research_space_store.create_space(
        owner_id=existing_owner_id,
        owner_email="existing-slug@example.com",
        owner_role="researcher",
        name="Collision",
        description="Existing space occupying the first slug.",
    )
    attempts: list[set[str]] = []

    def _colliding_slug(name: str, existing_slugs: set[str]) -> str:
        del name
        attempts.append(set(existing_slugs))
        if len(attempts) == 1:
            return existing_space.slug
        return "collision-retry"

    monkeypatch.setattr(
        sys.modules["artana_evidence_api.sqlalchemy_schedule_space_stores"],
        "build_unique_space_slug",
        _colliding_slug,
    )

    created_space = research_space_store.create_space(
        owner_id=new_owner_id,
        owner_email="new-slug@example.com",
        owner_role="researcher",
        name="Collision",
        description="Creation should retry after a slug uniqueness conflict.",
    )

    assert created_space.slug == "collision-retry"
    assert len(attempts) == 2


def test_sqlalchemy_chat_session_store_participates_in_unit_of_work(
    session: Session,
) -> None:
    chat_store = SqlAlchemyHarnessChatSessionStore(session)
    space_id = uuid4()
    created_by = uuid4()

    def _create_session_then_fail() -> None:
        with session_unit_of_work(session):
            chat_store.create_session(
                space_id=space_id,
                title="Rollback candidate",
                created_by=created_by,
            )
            raise RuntimeError("rollback requested")

    with pytest.raises(RuntimeError, match="rollback requested"):
        _create_session_then_fail()

    assert chat_store.list_sessions(space_id=space_id) == []


def test_sqlalchemy_harness_research_space_store_ensures_one_personal_default(
    session: Session,
) -> None:
    research_space_store = SqlAlchemyHarnessResearchSpaceStore(session)
    owner_id = str(uuid4())

    created_default = research_space_store.ensure_default_space(
        owner_id=owner_id,
        owner_email="sdk-owner@example.com",
        owner_role="researcher",
    )
    fetched_default = research_space_store.get_default_space(user_id=owner_id)
    accessible_default = research_space_store.get_space(
        space_id=created_default.id,
        user_id=owner_id,
        is_admin=False,
    )
    repeated_default = research_space_store.ensure_default_space(owner_id=owner_id)

    assert created_default.is_default is True
    assert fetched_default is not None
    assert fetched_default.id == created_default.id
    assert accessible_default is not None
    assert accessible_default.id == created_default.id
    assert repeated_default.id == created_default.id


def test_sqlalchemy_harness_research_space_store_uses_unique_default_slugs(
    session: Session,
) -> None:
    research_space_store = SqlAlchemyHarnessResearchSpaceStore(session)
    first_owner_id = "00000000-0000-4000-a000-000000e2e201"
    second_owner_id = "00000000-0000-4000-a000-000000e2e202"

    first_default = research_space_store.ensure_default_space(
        owner_id=first_owner_id,
        owner_email="first-default@example.com",
        owner_role="researcher",
    )
    second_default = research_space_store.ensure_default_space(
        owner_id=second_owner_id,
        owner_email="second-default@example.com",
        owner_role="researcher",
    )

    assert first_default.id != second_default.id
    assert first_default.slug == f"personal-{UUID(first_owner_id).hex}"
    assert second_default.slug == f"personal-{UUID(second_owner_id).hex}"
    assert first_default.slug != second_default.slug


def test_sqlalchemy_harness_research_space_store_syncs_default_space_creation(
    session: Session,
) -> None:
    sync = _RecordingSpaceLifecycleSync()
    research_space_store = SqlAlchemyHarnessResearchSpaceStore(
        session,
        space_lifecycle_sync=sync,
    )
    owner_id = UUID("00000000-0000-4000-a000-000000e2e203")

    created_default = research_space_store.ensure_default_space(
        owner_id=owner_id,
        owner_email="default-sync@example.com",
        owner_role="researcher",
    )

    persisted_membership = (
        session.query(ResearchSpaceMembershipModel)
        .filter(
            ResearchSpaceMembershipModel.space_id == UUID(created_default.id),
            ResearchSpaceMembershipModel.user_id == owner_id,
        )
        .one_or_none()
    )
    assert persisted_membership is not None
    assert len(sync.spaces) == 1
    assert sync.spaces[0].id == UUID(created_default.id)
    assert sync.spaces[0].slug == created_default.slug
    assert sync.spaces[0].name == created_default.name


def test_sqlalchemy_harness_proposal_store_persists_and_decides_proposals(
    session: Session,
) -> None:
    proposal_store = SqlAlchemyHarnessProposalStore(session)
    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="hypotheses",
        title="Hypothesis run",
        input_payload={"seed_entity_ids": ["entity-1"]},
    )

    created = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="hypothesis_run",
                source_key="entity-1:entity-1:ASSOCIATED_WITH:target-1",
                title="Candidate claim A",
                summary="First ranked candidate.",
                confidence=0.81,
                ranking_score=0.91,
                reasoning_path={"seed_entity_id": "entity-1"},
                evidence_bundle=[{"source_type": "db", "locator": "entity-1"}],
                payload={"proposed_claim_type": "ASSOCIATED_WITH"},
                metadata={"source_type": "pubmed"},
            ),
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="hypothesis_run",
                source_key="entity-1:entity-1:ASSOCIATED_WITH:target-2",
                title="Candidate claim B",
                summary="Second ranked candidate.",
                confidence=0.72,
                ranking_score=0.65,
                reasoning_path={"seed_entity_id": "entity-1"},
                evidence_bundle=[{"source_type": "db", "locator": "entity-2"}],
                payload={"proposed_claim_type": "ASSOCIATED_WITH"},
                metadata={"source_type": "pubmed"},
            ),
        ),
    )

    assert [proposal.title for proposal in created] == [
        "Candidate claim A",
        "Candidate claim B",
    ]

    listed = proposal_store.list_proposals(space_id=space_id, run_id=run.id)
    assert [proposal.id for proposal in listed] == [created[0].id, created[1].id]

    fetched = proposal_store.get_proposal(
        space_id=space_id,
        proposal_id=created[0].id,
    )
    assert fetched is not None
    assert fetched.status == "pending_review"

    promoted = proposal_store.decide_proposal(
        space_id=space_id,
        proposal_id=created[0].id,
        status="promoted",
        decision_reason="Evidence is strong",
        decided_by=None,
        metadata={"reviewed_by": "tester"},
    )
    assert promoted is not None
    assert promoted.status == "promoted"
    assert promoted.decision_reason == "Evidence is strong"
    assert promoted.metadata["reviewed_by"] == "tester"

    with pytest.raises(ValueError, match="already decided"):
        proposal_store.decide_proposal(
            space_id=space_id,
            proposal_id=created[0].id,
            status="rejected",
            decision_reason="Attempt to override the first decision",
            decided_by=None,
            metadata={"reviewed_by": "reviewer-2"},
        )

    rejected = proposal_store.decide_proposal(
        space_id=space_id,
        proposal_id=created[1].id,
        status="rejected",
        decision_reason="Needs more support",
        decided_by=None,
        metadata={"reviewed_by": "tester"},
    )
    assert rejected is not None
    assert rejected.status == "rejected"

    promoted_only = proposal_store.list_proposals(
        space_id=space_id,
        status="promoted",
        run_id=run.id,
    )
    assert [proposal.id for proposal in promoted_only] == [created[0].id]


def test_sqlalchemy_harness_proposal_store_round_trips_frozen_source_provenance(
    session: Session,
) -> None:
    proposal_store = SqlAlchemyHarnessProposalStore(session)
    document_store = SqlAlchemyHarnessDocumentStore(session)
    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="document-extraction",
        title="Source provenance round trip",
        input_payload={},
    )
    quote = "MED13 was associated with cardiomyopathy."
    snapshot_hash = hashlib.sha256(quote.encode("utf-8")).hexdigest()
    now = datetime.now(UTC)
    document = document_store.create_document(
        space_id=space_id,
        created_by=str(uuid4()),
        title="MED13 publication",
        source_type="pubmed",
        filename=None,
        media_type="text/plain",
        sha256=snapshot_hash,
        byte_size=len(quote.encode("utf-8")),
        page_count=None,
        text_content=quote,
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=run.id,
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="completed",
        metadata={},
    )
    provenance = ClaimSourceProvenance(
        status="verified",
        source_identity=SourceIdentity(
            source_kind="pubmed",
            authoritative_identifier="PMID:12345678",
            canonical_url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
            retrieved_at=now,
            content_sha256=snapshot_hash,
            pmid="12345678",
            artifact_sha256=snapshot_hash,
        ),
        evidence_locator=ExactEvidenceLocator(
            source_content_sha256=snapshot_hash,
            char_start=0,
            char_end=len(quote),
            exact_quote=quote,
            quote_sha256=snapshot_hash,
        ),
    )

    (created,) = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="document_extraction",
                source_key=f"{document.id}:relation:0",
                document_id=document.id,
                title="Source-backed claim",
                summary="Source-backed claim summary.",
                confidence=0.9,
                ranking_score=0.9,
                reasoning_path={},
                evidence_bundle=[{"excerpt": quote}],
                payload={"proposed_claim_type": "ASSOCIATED_WITH"},
                metadata={},
                source_provenance=provenance,
            ),
        ),
    )

    fetched = proposal_store.get_proposal(
        space_id=space_id,
        proposal_id=created.id,
    )

    assert fetched is not None
    assert fetched.source_provenance == provenance
    model = session.get(HarnessProposalModel, created.id)
    assert model is not None
    assert model.source_provenance_status == "verified"

    model.title = "Review metadata remains editable"
    session.flush()
    session.commit()

    model.source_provenance_status = "invalid"
    with pytest.raises(ValueError, match="proposal source provenance is immutable"):
        session.flush()
    session.rollback()

    model = session.get(HarnessProposalModel, created.id)
    assert model is not None
    model.source_provenance_payload = {"status": "unverified"}
    with pytest.raises(ValueError, match="proposal source provenance is immutable"):
        session.flush()
    session.rollback()


def test_sqlalchemy_harness_proposal_store_normalizes_oversized_titles(
    session: Session,
) -> None:
    proposal_store = SqlAlchemyHarnessProposalStore(session)
    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="document-extraction",
        title="Long title regression",
        input_payload={"document_id": str(uuid4())},
    )
    oversized_title = (
        "Extracted claim: "
        + ("MED13-associated transcriptional regulator " * 4)
        + "CAUSES "
        + ("neurodevelopmental disorder with variable expressivity " * 4)
    )

    created = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="document_extraction",
                source_key="doc-1:0",
                title=oversized_title,
                summary="Oversized extracted claim title should be normalized.",
                confidence=0.74,
                ranking_score=0.74,
                reasoning_path={"document_id": "doc-1"},
                evidence_bundle=[{"source_type": "paper", "locator": "doc-1"}],
                payload={"proposed_claim_type": "CAUSES"},
                metadata={"source_type": "pubmed"},
            ),
        ),
    )

    assert len(created) == 1
    assert len(created[0].title) == 256
    assert created[0].title.endswith("...")

    persisted_model = session.get(HarnessProposalModel, created[0].id)
    assert persisted_model is not None
    assert persisted_model.title == created[0].title


def test_sqlalchemy_harness_proposal_store_rejects_raw_unknown_candidate_claim_type(
    session: Session,
) -> None:
    proposal_store = SqlAlchemyHarnessProposalStore(session)
    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="document-extraction",
        title="Raw relation proposal guard",
        input_payload={"document_id": str(uuid4())},
    )

    with pytest.raises(ValueError, match="unknown relation type"):
        proposal_store.create_proposals(
            space_id=space_id,
            run_id=run.id,
            proposals=(
                HarnessProposalDraft(
                    proposal_type="candidate_claim",
                    source_kind="document_extraction",
                    source_key="doc-raw:0",
                    title="Raw unknown claim",
                    summary="This claim should not persist.",
                    confidence=0.74,
                    ranking_score=0.74,
                    reasoning_path={"document_id": "doc-raw"},
                    evidence_bundle=[],
                    payload={"proposed_claim_type": "PROTECTS_AGAINST"},
                    metadata={"source_type": "pubmed"},
                ),
            ),
        )

    assert session.query(HarnessProposalModel).count() == 0


def test_sqlalchemy_harness_proposal_store_canonicalizes_candidate_claim_type(
    session: Session,
) -> None:
    proposal_store = SqlAlchemyHarnessProposalStore(session)
    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="document-extraction",
        title="Canonical relation proposal guard",
        input_payload={"document_id": str(uuid4())},
    )

    created = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="document_extraction",
                source_key="doc-synonym:0",
                title="Synonym claim",
                summary="This claim should persist with canonical relation type.",
                confidence=0.74,
                ranking_score=0.74,
                reasoning_path={"document_id": "doc-synonym"},
                evidence_bundle=[],
                payload={"proposed_claim_type": "AFFECTS"},
                metadata={"source_type": "pubmed"},
            ),
        ),
    )

    assert created[0].payload["proposed_claim_type"] == "MODULATES"
    persisted_model = session.get(HarnessProposalModel, created[0].id)
    assert persisted_model is not None
    assert persisted_model.payload["proposed_claim_type"] == "MODULATES"


def test_sqlalchemy_harness_proposal_store_migrates_legacy_relation_type_key(
    session: Session,
) -> None:
    proposal_store = SqlAlchemyHarnessProposalStore(session)
    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="hypotheses",
        title="Legacy relation key proposal guard",
        input_payload={"seed_entity_ids": ["entity-1"]},
    )

    created = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="hypothesis_run",
                source_key="legacy-relation-key:0",
                title="Legacy relation key claim",
                summary="This claim uses the old relation_type payload key.",
                confidence=0.74,
                ranking_score=0.74,
                reasoning_path={},
                evidence_bundle=[],
                payload={"relation_type": "REGULATES"},
                metadata={"source_type": "pubmed"},
            ),
        ),
    )

    assert created[0].payload["relation_type"] == "REGULATES"
    assert created[0].payload["proposed_claim_type"] == "REGULATES"
    persisted_model = session.get(HarnessProposalModel, created[0].id)
    assert persisted_model is not None
    assert persisted_model.payload["proposed_claim_type"] == "REGULATES"


def test_sqlalchemy_harness_proposal_store_maps_legacy_suggests_relation(
    session: Session,
) -> None:
    proposal_store = SqlAlchemyHarnessProposalStore(session)
    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="graph-suggestions",
        title="Legacy suggestion proposal guard",
        input_payload={"seed_entity_ids": ["entity-1"]},
    )

    created = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="graph_suggestion",
                source_key="legacy-suggests:0",
                title="Legacy suggestion claim",
                summary="This claim uses an older graph suggestion placeholder.",
                confidence=0.74,
                ranking_score=0.74,
                reasoning_path={},
                evidence_bundle=[],
                payload={"proposed_claim_type": "SUGGESTS"},
                metadata={"source_type": "pubmed"},
            ),
        ),
    )

    assert created[0].payload["proposed_claim_type"] == "ASSOCIATED_WITH"
    persisted_model = session.get(HarnessProposalModel, created[0].id)
    assert persisted_model is not None
    assert persisted_model.payload["proposed_claim_type"] == "ASSOCIATED_WITH"


def test_sqlalchemy_harness_schedule_store_persists_and_updates_schedules(
    session: Session,
) -> None:
    schedule_store = SqlAlchemyHarnessScheduleStore(session)
    space_id = str(uuid4())
    created_by = str(uuid4())

    created = schedule_store.create_schedule(
        space_id=space_id,
        harness_id="continuous-learning",
        title="Daily refresh",
        cadence="daily",
        created_by=created_by,
        configuration={
            "seed_entity_ids": ["entity-1"],
            "source_type": "pubmed",
            "run_budget": {
                "max_tool_calls": 100,
                "max_external_queries": 101,
                "max_new_proposals": 20,
                "max_runtime_seconds": 300,
                "max_cost_usd": 5.0,
            },
        },
        metadata={"owner": "tester"},
    )
    assert created.harness_id == "continuous-learning"
    assert created.last_run_id is None
    assert created.active_trigger_claim_id is None

    listed = schedule_store.list_schedules(space_id=space_id)
    assert [schedule.id for schedule in listed] == [created.id]
    assert schedule_store.list_all_schedules(status="active")[0].id == created.id

    fetched = schedule_store.get_schedule(space_id=space_id, schedule_id=created.id)
    assert fetched is not None
    assert fetched.configuration["seed_entity_ids"] == ["entity-1"]
    assert fetched.configuration["run_budget"]["max_tool_calls"] == 100

    updated = schedule_store.update_schedule(
        space_id=space_id,
        schedule_id=created.id,
        title="Weekday refresh",
        cadence="weekday",
        status="paused",
        last_run_id=str(uuid4()),
    )
    assert updated is not None
    assert updated.title == "Weekday refresh"
    assert updated.cadence == "weekday"
    assert updated.status == "paused"
    assert updated.last_run_id is not None
    assert schedule_store.list_all_schedules(status="paused")[0].id == created.id


def test_sqlalchemy_harness_schedule_store_allows_only_one_active_trigger_claim(
    shared_session_factory: sessionmaker[Session],
) -> None:
    first_session = shared_session_factory()
    second_session = shared_session_factory()
    verifier_session = shared_session_factory()
    try:
        schedule_store_first = SqlAlchemyHarnessScheduleStore(first_session)
        schedule_store_second = SqlAlchemyHarnessScheduleStore(second_session)
        schedule_store_verifier = SqlAlchemyHarnessScheduleStore(verifier_session)
        space_id = str(uuid4())
        created = schedule_store_first.create_schedule(
            space_id=space_id,
            harness_id="continuous-learning",
            title="Claimed refresh",
            cadence="daily",
            created_by=str(uuid4()),
            configuration={"seed_entity_ids": ["entity-1"]},
            metadata={"owner": "primary"},
        )

        first_claim_id = str(uuid4())
        claimed = schedule_store_first.acquire_trigger_claim(
            space_id=space_id,
            schedule_id=created.id,
            claim_id=first_claim_id,
        )
        assert claimed is not None
        assert claimed.active_trigger_claim_id == first_claim_id

        blocked = schedule_store_second.acquire_trigger_claim(
            space_id=space_id,
            schedule_id=created.id,
            claim_id=str(uuid4()),
        )
        assert blocked is None

        released = schedule_store_first.release_trigger_claim(
            space_id=space_id,
            schedule_id=created.id,
            claim_id=first_claim_id,
        )
        assert released is not None
        assert released.active_trigger_claim_id is None

        second_claim_id = str(uuid4())
        reclaimed = schedule_store_second.acquire_trigger_claim(
            space_id=space_id,
            schedule_id=created.id,
            claim_id=second_claim_id,
        )
        assert reclaimed is not None
        assert reclaimed.active_trigger_claim_id == second_claim_id

        verified = schedule_store_verifier.get_schedule(
            space_id=space_id,
            schedule_id=created.id,
        )
        assert verified is not None
        assert verified.active_trigger_claim_id == second_claim_id
    finally:
        first_session.close()
        second_session.close()
        verifier_session.close()


def test_sqlalchemy_harness_schedule_store_expires_stale_trigger_claims(
    shared_session_factory: sessionmaker[Session],
) -> None:
    first_session = shared_session_factory()
    second_session = shared_session_factory()
    verifier_session = shared_session_factory()
    try:
        schedule_store_first = SqlAlchemyHarnessScheduleStore(first_session)
        schedule_store_second = SqlAlchemyHarnessScheduleStore(second_session)
        schedule_store_verifier = SqlAlchemyHarnessScheduleStore(verifier_session)
        space_id = str(uuid4())
        created = schedule_store_first.create_schedule(
            space_id=space_id,
            harness_id="continuous-learning",
            title="Expiring claim refresh",
            cadence="daily",
            created_by=str(uuid4()),
            configuration={"seed_entity_ids": ["entity-1"]},
            metadata={"owner": "primary"},
        )
        claimed_at = datetime(2026, 3, 26, 10, 0, tzinfo=UTC)
        first_claim_id = str(uuid4())

        claimed = schedule_store_first.acquire_trigger_claim(
            space_id=space_id,
            schedule_id=created.id,
            claim_id=first_claim_id,
            claimed_at=claimed_at,
            ttl_seconds=30,
        )
        assert claimed is not None
        assert claimed.active_trigger_claim_id == first_claim_id

        expired_claim_id = str(uuid4())
        reclaimed = schedule_store_second.acquire_trigger_claim(
            space_id=space_id,
            schedule_id=created.id,
            claim_id=expired_claim_id,
            claimed_at=claimed_at + timedelta(seconds=31),
            ttl_seconds=30,
        )
        assert reclaimed is not None
        assert reclaimed.active_trigger_claim_id == expired_claim_id

        verified = schedule_store_verifier.get_schedule(
            space_id=space_id,
            schedule_id=created.id,
        )
        assert verified is not None
        assert verified.active_trigger_claim_id == expired_claim_id
    finally:
        first_session.close()
        second_session.close()
        verifier_session.close()


def test_sqlalchemy_harness_approval_store_rejects_stale_cross_session_override(
    shared_session_factory: sessionmaker[Session],
) -> None:
    first_session = shared_session_factory()
    second_session = shared_session_factory()
    verifier_session = shared_session_factory()
    try:
        approval_store_first = SqlAlchemyHarnessApprovalStore(first_session)
        approval_store_second = SqlAlchemyHarnessApprovalStore(second_session)
        approval_store_verifier = SqlAlchemyHarnessApprovalStore(verifier_session)
        space_id = str(uuid4())
        run = _create_run_catalog_entry(
            first_session,
            space_id=space_id,
            harness_id="claim-curation",
            title="Cross-session approval",
            input_payload={"proposal_id": "proposal-cross-session"},
        )
        approval_store_first.upsert_intent(
            space_id=space_id,
            run_id=run.id,
            summary="Review a durable approval race.",
            proposed_actions=(
                HarnessApprovalAction(
                    approval_key="promote-cross-session",
                    title="Promote cross-session proposal",
                    risk_level="high",
                    target_type="proposal",
                    target_id="proposal-cross-session",
                    requires_approval=True,
                    metadata={"origin": "cross-session"},
                ),
            ),
            metadata={"stage": "approval"},
        )

        stale_snapshot = approval_store_second.list_approvals(
            space_id=space_id,
            run_id=run.id,
        )
        assert stale_snapshot[0].status == "pending"

        decided = approval_store_first.decide_approval(
            space_id=space_id,
            run_id=run.id,
            approval_key="promote-cross-session",
            status="approved",
            decision_reason="Primary reviewer approved it.",
            decided_by=None,
        )
        assert decided is not None
        assert decided.status == "approved"

        with pytest.raises(ValueError, match="already decided"):
            approval_store_second.decide_approval(
                space_id=space_id,
                run_id=run.id,
                approval_key="promote-cross-session",
                status="rejected",
                decision_reason="Secondary reviewer attempted an override.",
                decided_by=None,
            )

        verified = approval_store_verifier.list_approvals(
            space_id=space_id,
            run_id=run.id,
        )
        assert verified[0].status == "approved"
        assert verified[0].decision_reason == "Primary reviewer approved it."
    finally:
        first_session.close()
        second_session.close()
        verifier_session.close()


def test_sqlalchemy_harness_proposal_store_rejects_stale_cross_session_override(
    shared_session_factory: sessionmaker[Session],
) -> None:
    first_session = shared_session_factory()
    second_session = shared_session_factory()
    verifier_session = shared_session_factory()
    try:
        proposal_store_first = SqlAlchemyHarnessProposalStore(first_session)
        proposal_store_second = SqlAlchemyHarnessProposalStore(second_session)
        proposal_store_verifier = SqlAlchemyHarnessProposalStore(verifier_session)
        space_id = str(uuid4())
        run = _create_run_catalog_entry(
            first_session,
            space_id=space_id,
            harness_id="hypotheses",
            title="Cross-session proposal",
            input_payload={"seed_entity_ids": ["entity-1"]},
        )
        proposal = proposal_store_first.create_proposals(
            space_id=space_id,
            run_id=run.id,
            proposals=(
                HarnessProposalDraft(
                    proposal_type="candidate_claim",
                    source_kind="hypothesis_run",
                    source_key="entity-1:REGULATES:entity-2",
                    title="Cross-session candidate",
                    summary="Durable proposal race coverage.",
                    confidence=0.88,
                    ranking_score=0.93,
                    reasoning_path={"seed_entity_id": "entity-1"},
                    evidence_bundle=[{"source_type": "db", "locator": "entity-1"}],
                    payload={"proposed_claim_type": "REGULATES"},
                    metadata={"source_type": "pubmed"},
                ),
            ),
        )[0]

        stale_snapshot = proposal_store_second.get_proposal(
            space_id=space_id,
            proposal_id=proposal.id,
        )
        assert stale_snapshot is not None
        assert stale_snapshot.status == "pending_review"

        promoted = proposal_store_first.decide_proposal(
            space_id=space_id,
            proposal_id=proposal.id,
            status="promoted",
            decision_reason="Primary reviewer promoted it.",
            decided_by=None,
            metadata={"reviewed_by": "primary"},
        )
        assert promoted is not None
        assert promoted.status == "promoted"

        with pytest.raises(ValueError, match="already decided"):
            proposal_store_second.decide_proposal(
                space_id=space_id,
                proposal_id=proposal.id,
                status="rejected",
                decision_reason="Secondary reviewer attempted an override.",
                decided_by=None,
                metadata={"reviewed_by": "secondary"},
            )

        verified = proposal_store_verifier.get_proposal(
            space_id=space_id,
            proposal_id=proposal.id,
        )
        assert verified is not None
        assert verified.status == "promoted"
        assert verified.metadata["reviewed_by"] == "primary"
    finally:
        first_session.close()
        second_session.close()
        verifier_session.close()


def test_sqlalchemy_harness_review_item_store_reuses_existing_item_after_unique_conflict(
    shared_session_factory: sessionmaker[Session],
) -> None:
    with (
        shared_session_factory() as setup_session,
        shared_session_factory() as second_session,
        shared_session_factory() as verifier_session,
    ):
        first_store = SqlAlchemyHarnessReviewItemStore(setup_session)
        second_store = SqlAlchemyHarnessReviewItemStore(second_session)
        verifier_store = SqlAlchemyHarnessReviewItemStore(verifier_session)
        space_id = str(uuid4())
        run = _create_run_catalog_entry(
            setup_session,
            space_id=space_id,
            harness_id="document-extraction",
            title="Review item dedupe run",
            input_payload={"document_id": str(uuid4())},
        )
        review_item_draft = HarnessReviewItemDraft(
            review_type="phenotype_claim_review",
            source_family="document_extraction",
            source_kind="document_extraction",
            source_key="doc:phenotype:0",
            document_id=str(uuid4()),
            title="Review phenotype link",
            summary="developmental delay",
            priority="medium",
            confidence=0.72,
            ranking_score=0.72,
            evidence_bundle=[],
            payload={"phenotype_span": "developmental delay"},
            metadata={"source": "unit-test"},
            review_fingerprint="phenotype-review-fingerprint",
        )

        created = first_store.create_review_items(
            space_id=space_id,
            run_id=run.id,
            review_items=(review_item_draft,),
        )
        assert len(created) == 1

        original_find_existing = second_store._find_existing_review_item_model
        call_count = 0

        def _stale_lookup(*, space_id: str, review_item: HarnessReviewItemDraft):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None
            return original_find_existing(space_id=space_id, review_item=review_item)

        second_store._find_existing_review_item_model = _stale_lookup

        reused = second_store.create_review_items(
            space_id=space_id,
            run_id=run.id,
            review_items=(review_item_draft,),
        )

        assert len(reused) == 1
        assert reused[0].id == created[0].id
        assert call_count >= 2

        verified = verifier_store.list_review_items(space_id=space_id)
        assert len(verified) == 1
        assert verified[0].id == created[0].id

        stored_models = (
            verifier_session.execute(
                select(HarnessReviewItemModel).where(
                    HarnessReviewItemModel.space_id == space_id,
                ),
            )
            .scalars()
            .all()
        )
        assert len(stored_models) == 1


def test_sqlalchemy_harness_review_item_store_filters_counts_and_decides(
    session: Session,
) -> None:
    review_store = SqlAlchemyHarnessReviewItemStore(session)
    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="document-extraction",
        title="Review queue run",
        input_payload={"source": "unit-test"},
    )
    document_id = str(uuid4())
    created = review_store.create_review_items(
        space_id=space_id,
        run_id=run.id,
        review_items=(
            HarnessReviewItemDraft(
                review_type="phenotype_claim_review",
                source_family="document_extraction",
                source_kind="document_extraction",
                source_key="doc:phenotype:1",
                document_id=document_id,
                title="Review phenotype",
                summary="developmental delay",
                priority="high",
                confidence=0.91,
                ranking_score=0.91,
                evidence_bundle=[{"quote": "developmental delay"}],
                payload={"phenotype": "developmental delay"},
                metadata={"source": "unit-test"},
                review_fingerprint="review-fingerprint-1",
                evidence_grade="Moderate",
            ),
            HarnessReviewItemDraft(
                review_type="variant_claim_review",
                source_family="document_extraction",
                source_kind="document_extraction",
                source_key="doc:variant:1",
                document_id=str(uuid4()),
                title="Review variant",
                summary="variant evidence",
                priority="medium",
                confidence=0.72,
                ranking_score=0.72,
                evidence_bundle=[],
                payload={"variant": "c.1A>G"},
                metadata={},
                review_fingerprint=None,
                evidence_grade="Limited",
            ),
        ),
    )

    assert review_store.count_review_items(space_id=space_id) == 2
    assert len(review_store.list_review_items(space_id=space_id)) == 2
    assert (
        len(review_store.list_review_items(space_id=space_id, status="pending_review"))
        == 2
    )
    assert (
        len(
            review_store.list_review_items(
                space_id=space_id,
                review_type="phenotype_claim_review",
            ),
        )
        == 1
    )
    assert (
        len(
            review_store.list_review_items(
                space_id=space_id,
                source_family="document_extraction",
                run_id=run.id,
                document_id=document_id,
            ),
        )
        == 1
    )
    evidence_filtered = review_store.list_review_items(
        space_id=space_id,
        evidence_grade="moderate",
    )
    assert len(evidence_filtered) == 1
    assert evidence_filtered[0].evidence_grade == "Moderate"

    fetched = review_store.get_review_item(
        space_id=space_id,
        review_item_id=created[0].id,
    )
    assert fetched is not None
    assert fetched.metadata["source"] == "unit-test"
    assert (
        review_store.get_review_item(
            space_id=str(uuid4()),
            review_item_id=created[0].id,
        )
        is None
    )
    with pytest.raises(ValueError, match="Unsupported review item status"):
        review_store.decide_review_item(
            space_id=space_id,
            review_item_id=created[0].id,
            status="needs_more_magic",
            decision_reason=None,
            decided_by=None,
        )

    decided = review_store.decide_review_item(
        space_id=space_id,
        review_item_id=created[0].id,
        status="resolved",
        decision_reason=" accepted ",
        decided_by=None,
        metadata={"reviewed_by": "unit-test"},
        linked_proposal_id=f" {uuid4()} ",
        linked_approval_key=" approval-1 ",
    )
    assert decided is not None
    assert decided.status == "resolved"
    assert decided.decision_reason == "accepted"
    assert decided.metadata["reviewed_by"] == "unit-test"
    assert decided.linked_proposal_id is not None
    assert decided.linked_approval_key == "approval-1"

    with pytest.raises(ValueError, match="already decided"):
        review_store.decide_review_item(
            space_id=space_id,
            review_item_id=created[0].id,
            status="dismissed",
            decision_reason="duplicate",
            decided_by=None,
        )
    assert (
        review_store.decide_review_item(
            space_id=space_id,
            review_item_id=str(uuid4()),
            status="dismissed",
            decision_reason="missing",
            decided_by=None,
        )
        is None
    )


def test_sqlalchemy_harness_schedule_store_preserves_run_metadata_across_sessions(
    shared_session_factory: sessionmaker[Session],
) -> None:
    first_session = shared_session_factory()
    second_session = shared_session_factory()
    verifier_session = shared_session_factory()
    try:
        schedule_store_first = SqlAlchemyHarnessScheduleStore(first_session)
        schedule_store_second = SqlAlchemyHarnessScheduleStore(second_session)
        schedule_store_verifier = SqlAlchemyHarnessScheduleStore(verifier_session)
        space_id = str(uuid4())
        created_by = str(uuid4())
        created = schedule_store_first.create_schedule(
            space_id=space_id,
            harness_id="continuous-learning",
            title="Cross-session refresh",
            cadence="daily",
            created_by=created_by,
            configuration={"seed_entity_ids": ["entity-1"]},
            metadata={"owner": "primary"},
        )

        stale_snapshot = schedule_store_second.get_schedule(
            space_id=space_id,
            schedule_id=created.id,
        )
        assert stale_snapshot is not None
        assert stale_snapshot.last_run_id is None

        expected_run_id = str(uuid4())
        expected_run_at = datetime.now(UTC).replace(tzinfo=None)
        first_update = schedule_store_first.update_schedule(
            space_id=space_id,
            schedule_id=created.id,
            last_run_id=expected_run_id,
            last_run_at=expected_run_at,
        )
        assert first_update is not None
        assert first_update.last_run_id == expected_run_id

        retitled = schedule_store_second.update_schedule(
            space_id=space_id,
            schedule_id=created.id,
            title="Retitled after stale read",
        )
        assert retitled is not None
        assert retitled.title == "Retitled after stale read"
        assert retitled.last_run_id == expected_run_id
        assert retitled.last_run_at == expected_run_at

        verified = schedule_store_verifier.get_schedule(
            space_id=space_id,
            schedule_id=created.id,
        )
        assert verified is not None
        assert verified.title == "Retitled after stale read"
        assert verified.last_run_id == expected_run_id
        assert verified.last_run_at == expected_run_at
    finally:
        first_session.close()
        second_session.close()
        verifier_session.close()


def test_sqlalchemy_research_memory_stores_persist_state_and_snapshots(
    session: Session,
) -> None:
    research_state_store = SqlAlchemyHarnessResearchStateStore(session)
    graph_snapshot_store = SqlAlchemyHarnessGraphSnapshotStore(session)
    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="research-bootstrap",
        title="Bootstrap run",
        input_payload={"objective": "Map MED13"},
    )

    snapshot = graph_snapshot_store.create_snapshot(
        space_id=space_id,
        source_run_id=run.id,
        claim_ids=["claim-1", "claim-2"],
        relation_ids=["relation-1"],
        graph_document_hash="abc123",
        summary={"claim_count": 2, "mode": "seeded"},
        metadata={"seed_entity_ids": ["entity-1"]},
    )
    assert snapshot.source_run_id == run.id
    assert snapshot.graph_document_hash == "abc123"

    listed_snapshots = graph_snapshot_store.list_snapshots(space_id=space_id)
    assert [record.id for record in listed_snapshots] == [snapshot.id]

    state = research_state_store.upsert_state(
        space_id=space_id,
        objective="Map MED13",
        current_hypotheses=["MED13 may regulate transcription."],
        explored_questions=["Map MED13"],
        pending_questions=["What supports MED13 activation?"],
        last_graph_snapshot_id=snapshot.id,
        active_schedules=["schedule-1"],
        confidence_model={"proposal_ranking_model": "candidate_claim_v1"},
        budget_policy={"max_runtime_seconds": 300},
        metadata={"last_bootstrap_run_id": run.id},
    )
    assert state.objective == "Map MED13"
    assert state.last_graph_snapshot_id == snapshot.id
    assert state.active_schedules == ["schedule-1"]

    fetched_state = research_state_store.get_state(space_id=space_id)
    assert fetched_state is not None
    assert fetched_state.current_hypotheses == ["MED13 may regulate transcription."]
    assert fetched_state.metadata["last_bootstrap_run_id"] == run.id
