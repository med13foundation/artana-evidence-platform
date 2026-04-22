"""Unit tests for the remaining graph-harness SQLAlchemy domain stores."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from artana_evidence_api.approval_store import HarnessApprovalAction
from artana_evidence_api.db_schema import resolve_harness_db_schema
from artana_evidence_api.models.base import Base
from artana_evidence_api.models.harness import (
    HarnessProposalModel,
    HarnessReviewItemModel,
    HarnessRunModel,
)
from artana_evidence_api.models.research_space import (
    ResearchSpaceMembershipModel,
    ResearchSpaceModel,
)
from artana_evidence_api.proposal_store import HarnessProposalDraft
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
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.domain.entities.research_space import ResearchSpace

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    harness_schema = resolve_harness_db_schema("graph_harness")
    public_schema = "public"

    @event.listens_for(engine, "connect")
    def _attach_harness_schema(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"ATTACH DATABASE ':memory:' AS {public_schema}")
            cursor.execute(f"ATTACH DATABASE ':memory:' AS {harness_schema}")
        finally:
            cursor.close()

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    db_session = SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()


@pytest.fixture
def shared_session_factory(
    tmp_path: Path,
) -> Iterator[sessionmaker[Session]]:
    database_path = tmp_path / "sqlalchemy_store_shared.db"
    harness_schema_path = tmp_path / "sqlalchemy_store_harness.db"
    public_schema_path = tmp_path / "sqlalchemy_store_public.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    harness_schema = resolve_harness_db_schema("graph_harness")
    public_schema = "public"

    @event.listens_for(engine, "connect")
    def _attach_harness_schema(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(
                f"ATTACH DATABASE '{public_schema_path}' AS {public_schema}",
            )
            cursor.execute(
                f"ATTACH DATABASE '{harness_schema_path}' AS {harness_schema}",
            )
        finally:
            cursor.close()

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
                payload={"proposed_subject": str(uuid4())},
                metadata={"origin": "a"},
                document_id=target_document_id,
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
                payload={"proposed_subject": str(uuid4())},
                metadata={"origin": "b"},
                document_id=str(uuid4()),
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
        self.spaces: list[ResearchSpace] = []

    def sync_space(self, space: ResearchSpace) -> None:
        self.spaces.append(space)


class _FailingSpaceLifecycleSync:
    def sync_space(self, space: ResearchSpace) -> None:
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
                source_key="entity-1:entity-1:SUGGESTS:target-1",
                title="Candidate claim A",
                summary="First ranked candidate.",
                confidence=0.81,
                ranking_score=0.91,
                reasoning_path={"seed_entity_id": "entity-1"},
                evidence_bundle=[{"source_type": "db", "locator": "entity-1"}],
                payload={"proposed_claim_type": "SUGGESTS"},
                metadata={"source_type": "pubmed"},
            ),
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="hypothesis_run",
                source_key="entity-1:entity-1:SUGGESTS:target-2",
                title="Candidate claim B",
                summary="Second ranked candidate.",
                confidence=0.72,
                ranking_score=0.65,
                reasoning_path={"seed_entity_id": "entity-1"},
                evidence_bundle=[{"source_type": "db", "locator": "entity-2"}],
                payload={"proposed_claim_type": "SUGGESTS"},
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
            metadata={"reviewed_by": "reviewer-2"},
        )

    rejected = proposal_store.decide_proposal(
        space_id=space_id,
        proposal_id=created[1].id,
        status="rejected",
        decision_reason="Needs more support",
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

        def _stale_lookup(*, space_id: str, review_item: HarnessReviewItemDraft):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None
            return original_find_existing(space_id=space_id, review_item=review_item)

        second_store._find_existing_review_item_model = _stale_lookup  # type: ignore[method-assign]

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

        stored_models = verifier_session.execute(
            select(HarnessReviewItemModel).where(
                HarnessReviewItemModel.space_id == space_id,
            ),
        ).scalars().all()
        assert len(stored_models) == 1


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
