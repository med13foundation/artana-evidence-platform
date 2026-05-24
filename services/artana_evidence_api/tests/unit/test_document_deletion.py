"""Regression tests for supported document deletion paths."""

from __future__ import annotations

from uuid import UUID, uuid4

from artana_evidence_api.app import create_app
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_document_store,
    get_proposal_store,
    get_research_space_store,
    get_review_item_store,
    get_run_registry,
    get_study_outcome_store,
)
from artana_evidence_api.document_store import (
    HarnessDocumentRecord,
    HarnessDocumentStore,
)
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalStore,
)
from artana_evidence_api.research_space_store import HarnessResearchSpaceStore
from artana_evidence_api.review_item_store import (
    HarnessReviewItemDraft,
    HarnessReviewItemStore,
)
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.study_outcomes import (
    HarnessStudyOutcomeStore,
    StudyOutcomeDraft,
)
from fastapi.testclient import TestClient

_TEST_USER_ID = UUID("11111111-1111-1111-1111-111111111111")
_AUTH_HEADERS = {
    "X-TEST-USER-ID": str(_TEST_USER_ID),
    "X-TEST-USER-EMAIL": "document-deletion@example.com",
    "X-TEST-USER-ROLE": "researcher",
}


def test_delete_document_removes_children_and_writes_audit_run() -> None:
    built = _build_client()
    document = _seed_document(
        built.document_store,
        space_id=built.space_id,
        title="DrugMechDB MED13 mechanism",
        source_type="DrugMechDB",
        ingestion_run_id="drugmech-run",
    )
    _seed_child_records(built=built, document_id=document.id)

    response = built.client.delete(
        f"/v1/spaces/{built.space_id}/documents/{document.id}",
        headers=_AUTH_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted_document_count"] == 1
    assert payload["deleted_proposal_count"] == 1
    assert payload["deleted_review_item_count"] == 1
    assert payload["deleted_study_outcome_count"] == 1
    assert payload["scope"]["document_id"] == document.id
    assert payload["deleted_documents"][0]["title"] == "DrugMechDB MED13 mechanism"
    assert built.document_store.get_document(
        space_id=built.space_id,
        document_id=document.id,
    ) is None
    assert built.proposal_store.list_proposals(
        space_id=built.space_id,
        document_id=document.id,
    ) == []
    assert built.review_item_store.list_review_items(
        space_id=built.space_id,
        document_id=document.id,
    ) == []
    assert (
        built.study_outcome_store.count_outcomes(
            space_id=built.space_id,
            document_id=document.id,
        )
        == 0
    )

    audit_run = built.run_registry.get_run(
        space_id=built.space_id,
        run_id=payload["run"]["id"],
    )
    assert audit_run is not None
    assert audit_run.harness_id == "document-deletion"
    audit_artifact = built.artifact_store.get_artifact(
        space_id=built.space_id,
        run_id=payload["run"]["id"],
        artifact_key="document_deletion_audit",
    )
    assert audit_artifact is not None
    assert audit_artifact.content["actor_id"] == str(_TEST_USER_ID)
    assert audit_artifact.content["deleted_document_count"] == 1


def test_bulk_delete_documents_scopes_by_source_title_prefix_and_run() -> None:
    built = _build_client()
    target_run_id = str(uuid4())
    first = _seed_document(
        built.document_store,
        space_id=built.space_id,
        title="DrugMechDB MED13 mechanism",
        source_type="DrugMechDB",
        ingestion_run_id=target_run_id,
    )
    second = _seed_document(
        built.document_store,
        space_id=built.space_id,
        title="DrugMechDB MED13L mechanism",
        source_type="DrugMechDB",
        ingestion_run_id=target_run_id,
    )
    _seed_document(
        built.document_store,
        space_id=built.space_id,
        title="PubMed MED13 paper",
        source_type="pubmed",
        ingestion_run_id=target_run_id,
    )
    _seed_document(
        built.document_store,
        space_id=built.space_id,
        title="DrugMechDB stale outside run",
        source_type="DrugMechDB",
        ingestion_run_id=str(uuid4()),
    )

    response = built.client.delete(
        f"/v1/spaces/{built.space_id}/documents",
        headers=_AUTH_HEADERS,
        params={
            "source": "DrugMechDB",
            "title_prefix": "DrugMechDB MED13",
            "ingestion_run_id": target_run_id,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted_document_count"] == 2
    assert {document["id"] for document in payload["deleted_documents"]} == {
        first.id,
        second.id,
    }
    remaining_titles = {
        document.title
        for document in built.document_store.list_documents(space_id=built.space_id)
    }
    assert remaining_titles == {
        "PubMed MED13 paper",
        "DrugMechDB stale outside run",
    }


def test_bulk_delete_documents_rejects_unscoped_request() -> None:
    built = _build_client()

    response = built.client.delete(
        f"/v1/spaces/{built.space_id}/documents",
        headers=_AUTH_HEADERS,
    )

    assert response.status_code == 400
    assert "At least one delete scope" in response.json()["detail"]


class _BuiltClient:
    def __init__(  # noqa: PLR0913
        self,
        *,
        client: TestClient,
        space_id: UUID,
        artifact_store: HarnessArtifactStore,
        document_store: HarnessDocumentStore,
        proposal_store: HarnessProposalStore,
        review_item_store: HarnessReviewItemStore,
        run_registry: HarnessRunRegistry,
        study_outcome_store: HarnessStudyOutcomeStore,
    ) -> None:
        self.client = client
        self.space_id = space_id
        self.artifact_store = artifact_store
        self.document_store = document_store
        self.proposal_store = proposal_store
        self.review_item_store = review_item_store
        self.run_registry = run_registry
        self.study_outcome_store = study_outcome_store


def _build_client() -> _BuiltClient:
    app = create_app()
    artifact_store = HarnessArtifactStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    review_item_store = HarnessReviewItemStore()
    run_registry = HarnessRunRegistry()
    study_outcome_store = HarnessStudyOutcomeStore()
    research_space_store = HarnessResearchSpaceStore()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Document Deletion",
        description="Owned test space for document deletion routes.",
    )
    app.dependency_overrides[get_artifact_store] = lambda: artifact_store
    app.dependency_overrides[get_document_store] = lambda: document_store
    app.dependency_overrides[get_proposal_store] = lambda: proposal_store
    app.dependency_overrides[get_review_item_store] = lambda: review_item_store
    app.dependency_overrides[get_run_registry] = lambda: run_registry
    app.dependency_overrides[get_study_outcome_store] = lambda: study_outcome_store
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    return _BuiltClient(
        client=TestClient(app),
        space_id=UUID(space.id),
        artifact_store=artifact_store,
        document_store=document_store,
        proposal_store=proposal_store,
        review_item_store=review_item_store,
        run_registry=run_registry,
        study_outcome_store=study_outcome_store,
    )


def _seed_document(
    store: HarnessDocumentStore,
    *,
    space_id: UUID,
    title: str,
    source_type: str,
    ingestion_run_id: str,
) -> HarnessDocumentRecord:
    return store.create_document(
        space_id=space_id,
        created_by=_TEST_USER_ID,
        title=title,
        source_type=source_type,
        filename=None,
        media_type="text/plain",
        sha256=str(uuid4()),
        byte_size=64,
        page_count=None,
        text_content=f"{title} evidence.",
        ingestion_run_id=ingestion_run_id,
        enrichment_status="skipped",
        extraction_status="completed",
        metadata={"source": source_type},
    )


def _seed_child_records(*, built: _BuiltClient, document_id: str) -> None:
    run_id = uuid4()
    built.proposal_store.create_proposals(
        space_id=built.space_id,
        run_id=run_id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="DrugMechDB",
                source_key="drugmechdb:med13",
                title="MED13 mechanism",
                summary="MED13 mechanism proposal.",
                confidence=0.8,
                ranking_score=0.8,
                reasoning_path={},
                evidence_bundle=[{"quote": "MED13 mechanism."}],
                payload={"gene": "MED13"},
                metadata={},
                document_id=document_id,
            ),
        ),
    )
    built.review_item_store.create_review_items(
        space_id=built.space_id,
        run_id=run_id,
        review_items=(
            HarnessReviewItemDraft(
                review_type="source_review",
                source_family="DrugMechDB",
                source_kind="DrugMechDB",
                source_key="drugmechdb:review",
                title="Review MED13 mechanism",
                summary="Review-only item.",
                priority="medium",
                confidence=0.7,
                ranking_score=0.7,
                evidence_bundle=[{"quote": "Review MED13 mechanism."}],
                payload={"gene": "MED13"},
                metadata={},
                document_id=document_id,
            ),
        ),
    )
    built.study_outcome_store.create_outcomes(
        space_id=built.space_id,
        document_id=document_id,
        run_id=run_id,
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
