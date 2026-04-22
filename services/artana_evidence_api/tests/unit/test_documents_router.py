"""Unit tests for harness document ingestion and extraction routes."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from artana_evidence_api.app import create_app
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_document_binary_store,
    get_document_store,
    get_graph_api_gateway,
    get_proposal_store,
    get_research_space_store,
    get_research_state_store,
    get_review_item_store,
    get_run_registry,
)
from artana_evidence_api.document_binary_store import HarnessDocumentBinaryStore
from artana_evidence_api.document_extraction import (
    DocumentCandidateExtractionDiagnostics,
    DocumentProposalReviewDiagnostics,
    DocumentTextExtraction,
    ExtractedRelationCandidate,
)
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalStore,
)
from artana_evidence_api.research_space_store import HarnessResearchSpaceStore
from artana_evidence_api.research_state import HarnessResearchStateStore
from artana_evidence_api.review_item_store import (
    HarnessReviewItemDraft,
    HarnessReviewItemStore,
)
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.types.graph_contracts import (
    KernelEntityListResponse,
    KernelEntityResponse,
)
from artana_evidence_api.variant_aware_document_extraction import (
    VariantAwareDocumentExtractionResult,
)
from fastapi.testclient import TestClient

from src.domain.agents.contracts.extraction import (
    ExtractedEntityCandidate,
    ExtractionContract,
)
from src.domain.agents.contracts.fact_assessment import (
    FactAssessment,
    GroundingLevel,
    MappingStatus,
    SpeculationLevel,
    SupportBand,
)

_TEST_USER_ID: Final[str] = "11111111-1111-1111-1111-111111111111"
_TEST_USER_EMAIL: Final[str] = "graph-harness-docs@example.com"
_MED13_ID: Final[str] = "33333333-3333-3333-3333-333333333333"
_CARDIOMYOPATHY_ID: Final[str] = "44444444-4444-4444-4444-444444444444"
_FG_SYNDROME_ID: Final[str] = "55555555-5555-5555-5555-555555555555"
_LUJAN_FRYNS_ID: Final[str] = "66666666-6666-6666-6666-666666666666"
_OHDO_SYNDROME_ID: Final[str] = "77777777-7777-7777-7777-777777777777"


def _auth_headers(*, role: str = "researcher") -> dict[str, str]:
    return {
        "X-TEST-USER-ID": _TEST_USER_ID,
        "X-TEST-USER-EMAIL": _TEST_USER_EMAIL,
        "X-TEST-USER-ROLE": role,
    }


class _StubGraphHealthResponse:
    status = "ok"
    version = "documents-test"


class _StubGraphApiGateway:
    def get_health(self) -> _StubGraphHealthResponse:
        return _StubGraphHealthResponse()

    def list_entities(
        self,
        *,
        space_id: UUID | str,
        q: str | None = None,
        entity_type: str | None = None,
        ids: list[str] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelEntityListResponse:
        del entity_type, ids, offset, limit
        now = datetime.now(UTC)
        catalog = [
            KernelEntityResponse(
                id=UUID(_MED13_ID),
                research_space_id=UUID(str(space_id)),
                entity_type="GENE",
                display_label="MED13",
                aliases=[],
                metadata={},
                created_at=now,
                updated_at=now,
            ),
            KernelEntityResponse(
                id=UUID(_CARDIOMYOPATHY_ID),
                research_space_id=UUID(str(space_id)),
                entity_type="DISEASE",
                display_label="cardiomyopathy",
                aliases=["dilated cardiomyopathy"],
                metadata={},
                created_at=now,
                updated_at=now,
            ),
            KernelEntityResponse(
                id=UUID(_FG_SYNDROME_ID),
                research_space_id=UUID(str(space_id)),
                entity_type="DISEASE",
                display_label="FG Syndrome Type 1",
                aliases=["FG syndrome", "Opitz-Kaveggia"],
                metadata={},
                created_at=now,
                updated_at=now,
            ),
            KernelEntityResponse(
                id=UUID(_LUJAN_FRYNS_ID),
                research_space_id=UUID(str(space_id)),
                entity_type="DISEASE",
                display_label="Lujan-Fryns syndrome",
                aliases=[],
                metadata={},
                created_at=now,
                updated_at=now,
            ),
            KernelEntityResponse(
                id=UUID(_OHDO_SYNDROME_ID),
                research_space_id=UUID(str(space_id)),
                entity_type="DISEASE",
                display_label="Ohdo syndrome MKBT",
                aliases=["Ohdo syndrome"],
                metadata={},
                created_at=now,
                updated_at=now,
            ),
        ]
        if isinstance(q, str) and q.strip() != "":
            normalized_query = q.strip().casefold()
            catalog = [
                entity
                for entity in catalog
                if normalized_query in (entity.display_label or "").casefold()
                or any(normalized_query in alias.casefold() for alias in entity.aliases)
            ]
        return KernelEntityListResponse(
            entities=catalog,
            total=len(catalog),
            offset=0,
            limit=50,
        )

    def close(self) -> None:
        return None


class _StubEmptyGraphApiGateway(_StubGraphApiGateway):
    def list_entities(
        self,
        *,
        space_id: UUID | str,
        q: str | None = None,
        entity_type: str | None = None,
        ids: list[str] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelEntityListResponse:
        del space_id, q, entity_type, ids, offset, limit
        return KernelEntityListResponse(entities=[], total=0, offset=0, limit=50)


class _FailingEntityResolutionGraphApiGateway(_StubGraphApiGateway):
    def list_entities(
        self,
        *,
        space_id: UUID | str,
        q: str | None = None,
        entity_type: str | None = None,
        ids: list[str] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelEntityListResponse:
        del space_id, q, entity_type, ids, offset, limit
        raise GraphServiceClientError(
            "Synthetic entity resolution outage.",
            status_code=503,
            detail="Synthetic entity resolution outage.",
        )


def _build_client(
    *,
    graph_api_gateway_dependency: object = _StubGraphApiGateway,
    objective: str | None = None,
) -> tuple[
    TestClient,
    HarnessDocumentBinaryStore,
    HarnessDocumentStore,
    HarnessProposalStore,
    HarnessRunRegistry,
    str,
]:
    app = create_app()
    artifact_store = HarnessArtifactStore()
    binary_store = HarnessDocumentBinaryStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    review_item_store = HarnessReviewItemStore()
    research_state_store = HarnessResearchStateStore()
    research_space_store = HarnessResearchSpaceStore()
    run_registry = HarnessRunRegistry()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Documents Space",
        description="Owned test space for document routes.",
    )
    if objective is not None:
        research_state_store.upsert_state(space_id=space.id, objective=objective)
    app.dependency_overrides[get_artifact_store] = lambda: artifact_store
    app.dependency_overrides[get_document_binary_store] = lambda: binary_store
    app.dependency_overrides[get_document_store] = lambda: document_store
    app.dependency_overrides[get_graph_api_gateway] = graph_api_gateway_dependency
    app.dependency_overrides[get_proposal_store] = lambda: proposal_store
    app.dependency_overrides[get_research_state_store] = lambda: research_state_store
    app.dependency_overrides[get_review_item_store] = lambda: review_item_store
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    app.dependency_overrides[get_run_registry] = lambda: run_registry
    return (
        TestClient(app),
        binary_store,
        document_store,
        proposal_store,
        run_registry,
        space.id,
    )


def _strong_assessment(
    *,
    rationale: str = "Exact anchored variant candidate.",
) -> FactAssessment:
    return FactAssessment(
        support_band=SupportBand.STRONG,
        grounding_level=GroundingLevel.SPAN,
        mapping_status=MappingStatus.RESOLVED,
        speculation_level=SpeculationLevel.DIRECT,
        confidence_rationale=rationale,
    )


def test_submit_text_document_creates_tracked_document_and_run() -> None:
    client, _, document_store, _, _, space_id = _build_client()

    response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "MED13 evidence note",
            "text": "MED13 associates with cardiomyopathy.",
            "metadata": {"origin": "unit-test"},
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["run"]["harness_id"] == "document-ingestion"
    assert payload["document"]["title"] == "MED13 evidence note"
    assert payload["document"]["source_type"] == "text"
    stored_documents = document_store.list_documents(space_id=space_id)
    assert len(stored_documents) == 1
    assert stored_documents[0].metadata["origin"] == "unit-test"


def test_submit_text_document_sanitizes_title_across_read_paths_and_run_state() -> None:
    client, _, document_store, _, run_registry, space_id = _build_client()

    response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "<script>alert(1)</script>",
            "text": "Legitimate research content about angiosarcoma.",
            "metadata": {},
        },
    )

    assert response.status_code == 201
    payload = response.json()
    document_id = payload["document"]["id"]
    assert payload["document"]["title"] == "alert(1)"
    assert payload["run"]["title"] == "Document Ingestion: alert(1)"

    stored_document = document_store.get_document(
        space_id=space_id,
        document_id=document_id,
    )
    assert stored_document is not None
    assert stored_document.title == "alert(1)"

    stored_runs = run_registry.list_runs(space_id=space_id)
    assert len(stored_runs) == 1
    assert stored_runs[0].title == "Document Ingestion: alert(1)"
    assert stored_runs[0].input_payload["title"] == "alert(1)"

    list_response = client.get(
        f"/v1/spaces/{space_id}/documents",
        headers=_auth_headers(role="viewer"),
    )
    assert list_response.status_code == 200
    assert list_response.json()["documents"][0]["title"] == "alert(1)"

    detail_response = client.get(
        f"/v1/spaces/{space_id}/documents/{document_id}",
        headers=_auth_headers(role="viewer"),
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["title"] == "alert(1)"


def test_submit_text_document_rejects_duplicate_and_allows_force_create() -> None:
    client, _, document_store, _, run_registry, space_id = _build_client()

    first_response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "MED13 evidence note",
            "text": "MED13 associates with cardiomyopathy.",
            "metadata": {},
        },
    )
    assert first_response.status_code == 201
    first_payload = first_response.json()

    duplicate_response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "MED13 evidence note copy",
            "text": "MED13 associates with cardiomyopathy.",
            "metadata": {},
        },
    )

    assert duplicate_response.status_code == 409
    duplicate_payload = duplicate_response.json()
    assert duplicate_payload["detail"] == "Document already exists"
    assert (
        duplicate_payload["existing_document"]["id"] == first_payload["document"]["id"]
    )
    assert (
        duplicate_payload["existing_document"]["sha256"]
        == first_payload["document"]["sha256"]
    )
    assert len(document_store.list_documents(space_id=space_id)) == 1
    assert len(run_registry.list_runs(space_id=space_id)) == 1

    forced_response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        params={"force": "true"},
        json={
            "title": "MED13 evidence note forced copy",
            "text": "MED13 associates with cardiomyopathy.",
            "metadata": {},
        },
    )

    assert forced_response.status_code == 201
    assert len(document_store.list_documents(space_id=space_id)) == 2
    assert len(run_registry.list_runs(space_id=space_id)) == 2


def test_submit_text_document_rejects_oversized_payload() -> None:
    client, _, _, _, _, space_id = _build_client()

    response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "Oversized note",
            "text": "A" * 120001,
            "metadata": {},
        },
    )

    assert response.status_code == 422


def test_submit_text_document_rejects_blank_normalized_payload_without_side_effects() -> (
    None
):
    client, _, document_store, _, run_registry, space_id = _build_client()

    response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "Whitespace only",
            "text": " \n\t\r ",
            "metadata": {},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Document text cannot be blank"
    assert document_store.list_documents(space_id=space_id) == []
    assert run_registry.list_runs(space_id=space_id) == []


def test_submit_text_document_rejects_title_without_visible_text_after_sanitization() -> (
    None
):
    client, _, document_store, _, run_registry, space_id = _build_client()

    response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "<img src=x onerror=alert(1)>",
            "text": "Legitimate research content about angiosarcoma.",
            "metadata": {},
        },
    )

    assert response.status_code == 422
    assert "visible text" in response.text
    assert document_store.list_documents(space_id=space_id) == []
    assert run_registry.list_runs(space_id=space_id) == []


def test_upload_pdf_document_stores_raw_reference_without_populating_text() -> None:
    client, binary_store, document_store, _, _, space_id = _build_client()

    response = client.post(
        f"/v1/spaces/{space_id}/documents/pdf",
        headers=_auth_headers(),
        data={
            "title": "Uploaded MED13 PDF",
            "metadata_json": '{"origin": "pdf-test"}',
        },
        files={
            "file": (
                "med13.pdf",
                b"%PDF-1.4\nsynthetic\n%%EOF\n",
                "application/pdf",
            ),
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["document"]["source_type"] == "pdf"
    assert payload["document"]["page_count"] is None
    assert payload["document"]["text_content"] == ""
    assert payload["document"]["text_excerpt"] == ""
    assert payload["document"]["enrichment_status"] == "not_started"
    assert payload["document"]["metadata"]["origin"] == "pdf-test"
    stored_documents = document_store.list_documents(space_id=space_id)
    stored_document = stored_documents[0]
    assert stored_document.filename == "med13.pdf"
    assert stored_document.raw_storage_key is not None
    assert stored_document.enriched_storage_key is None
    assert stored_document.text_content == ""
    assert stored_document.page_count is None
    stored_payload = asyncio.run(
        binary_store.read_bytes(key=stored_document.raw_storage_key),
    )
    assert stored_payload.startswith(b"%PDF-1.4")


def test_upload_pdf_document_sanitizes_html_from_title() -> None:
    client, _, document_store, _, run_registry, space_id = _build_client()

    response = client.post(
        f"/v1/spaces/{space_id}/documents/pdf",
        headers=_auth_headers(),
        data={
            "title": "<b>Uploaded MED13 PDF</b>",
            "metadata_json": '{"origin": "pdf-test"}',
        },
        files={
            "file": (
                "med13.pdf",
                b"%PDF-1.4\nsynthetic\n%%EOF\n",
                "application/pdf",
            ),
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["document"]["title"] == "Uploaded MED13 PDF"
    stored_document = document_store.list_documents(space_id=space_id)[0]
    assert stored_document.title == "Uploaded MED13 PDF"
    stored_runs = run_registry.list_runs(space_id=space_id)
    assert len(stored_runs) == 1
    assert stored_runs[0].title == "Document Ingestion: Uploaded MED13 PDF"


def test_upload_pdf_document_rejects_duplicate_and_allows_force_create() -> None:
    client, binary_store, document_store, _, run_registry, space_id = _build_client()

    first_response = client.post(
        f"/v1/spaces/{space_id}/documents/pdf",
        headers=_auth_headers(),
        data={
            "title": "Uploaded MED13 PDF",
            "metadata_json": '{"origin": "pdf-test"}',
        },
        files={
            "file": (
                "med13.pdf",
                b"%PDF-1.4\nsynthetic\n%%EOF\n",
                "application/pdf",
            ),
        },
    )
    assert first_response.status_code == 201
    first_payload = first_response.json()

    duplicate_response = client.post(
        f"/v1/spaces/{space_id}/documents/pdf",
        headers=_auth_headers(),
        data={
            "title": "Uploaded MED13 PDF duplicate",
            "metadata_json": '{"origin": "pdf-test"}',
        },
        files={
            "file": (
                "med13.pdf",
                b"%PDF-1.4\nsynthetic\n%%EOF\n",
                "application/pdf",
            ),
        },
    )

    assert duplicate_response.status_code == 409
    duplicate_payload = duplicate_response.json()
    assert duplicate_payload["detail"] == "Document already exists"
    assert (
        duplicate_payload["existing_document"]["id"] == first_payload["document"]["id"]
    )
    assert len(document_store.list_documents(space_id=space_id)) == 1
    assert len(run_registry.list_runs(space_id=space_id)) == 1

    forced_response = client.post(
        f"/v1/spaces/{space_id}/documents/pdf",
        headers=_auth_headers(),
        params={"force": "true"},
        data={
            "title": "Uploaded MED13 PDF forced copy",
            "metadata_json": '{"origin": "pdf-test"}',
        },
        files={
            "file": (
                "med13.pdf",
                b"%PDF-1.4\nsynthetic\n%%EOF\n",
                "application/pdf",
            ),
        },
    )

    assert forced_response.status_code == 201
    assert len(document_store.list_documents(space_id=space_id)) == 2
    assert len(run_registry.list_runs(space_id=space_id)) == 2
    assert asyncio.run(
        binary_store.read_bytes(
            key=document_store.list_documents(space_id=space_id)[0].raw_storage_key,
        ),
    ).startswith(b"%PDF-1.4")


def test_upload_pdf_document_rejects_invalid_metadata_json() -> None:
    client, binary_store, document_store, _, run_registry, space_id = _build_client()

    response = client.post(
        f"/v1/spaces/{space_id}/documents/pdf",
        headers=_auth_headers(),
        data={"metadata_json": "[1, 2, 3]"},
        files={
            "file": (
                "med13.pdf",
                b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n",
                "application/pdf",
            ),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "metadata_json must decode to an object"
    assert document_store.list_documents(space_id=space_id) == []
    assert run_registry.list_runs(space_id=space_id) == []
    assert binary_store._payloads == {}  # noqa: SLF001


def test_upload_pdf_document_rejects_non_pdf_payload_without_side_effects() -> None:
    client, binary_store, document_store, _, run_registry, space_id = _build_client()

    response = client.post(
        f"/v1/spaces/{space_id}/documents/pdf",
        headers=_auth_headers(),
        files={
            "file": (
                "not-a-pdf.txt",
                b"plain text payload",
                "text/plain",
            ),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded payload is not a PDF"
    assert document_store.list_documents(space_id=space_id) == []
    assert run_registry.list_runs(space_id=space_id) == []
    assert binary_store._payloads == {}  # noqa: SLF001


def test_extract_document_creates_pending_review_proposals_and_supports_filtering() -> (
    None
):
    client, _, document_store, proposal_store, _, space_id = _build_client(
        objective="Map MED13 mechanism evidence in cardiomyopathy.",
    )

    submit_response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "MED13 evidence note",
            "text": "MED13 associates with cardiomyopathy.",
            "metadata": {},
        },
    )
    document_id = submit_response.json()["document"]["id"]

    extract_response = client.post(
        f"/v1/spaces/{space_id}/documents/{document_id}/extract",
        headers=_auth_headers(),
    )

    assert extract_response.status_code == 201
    payload = extract_response.json()
    assert payload["run"]["harness_id"] == "document-extraction"
    assert payload["proposal_count"] == 1
    assert payload["proposals"][0]["status"] == "pending_review"
    assert payload["proposals"][0]["document_id"] == document_id
    proposal_review = payload["proposals"][0]["metadata"]["proposal_review"]
    assert proposal_review["scale_version"] == "v1"
    assert proposal_review["factual_support"] in {"strong", "moderate", "tentative"}
    assert proposal_review["goal_relevance"] in {"direct", "supporting"}
    assert proposal_review["priority"] in {"prioritize", "review", "background"}
    stored_document = document_store.get_document(
        space_id=space_id,
        document_id=document_id,
    )
    assert stored_document is not None
    assert stored_document.extraction_status == "completed"
    listed_proposals = proposal_store.list_proposals(
        space_id=space_id,
        document_id=document_id,
    )
    assert len(listed_proposals) == 1

    filtered_response = client.get(
        f"/v1/spaces/{space_id}/proposals",
        headers=_auth_headers(),
        params={"document_id": document_id},
    )
    assert filtered_response.status_code == 200
    assert filtered_response.json()["total"] == 1


def test_extract_document_escalates_to_llm_when_regex_finds_no_candidates(
    monkeypatch,
) -> None:
    client, _, document_store, _, _, space_id = _build_client(
        objective="Map MED13 mechanism evidence in cardiomyopathy.",
    )

    monkeypatch.setattr(
        "artana_evidence_api.routers.documents.extract_relation_candidates",
        lambda _text: [],
    )

    async def _fake_extract_with_diagnostics(
        _text: str,
        *,
        max_relations: int = 10,
        space_context: str = "",
    ) -> tuple[
        list[ExtractedRelationCandidate],
        DocumentCandidateExtractionDiagnostics,
    ]:
        del max_relations, space_context
        return (
            [
                ExtractedRelationCandidate(
                    subject_label="MED13",
                    relation_type="ASSOCIATED_WITH",
                    object_label="cardiomyopathy",
                    sentence="MED13 associates with cardiomyopathy.",
                ),
            ],
            DocumentCandidateExtractionDiagnostics(
                llm_candidate_status="completed",
                llm_candidate_count=1,
            ),
        )

    monkeypatch.setattr(
        "artana_evidence_api.routers.documents.extract_relation_candidates_with_diagnostics",
        _fake_extract_with_diagnostics,
    )

    submit_response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "MED13 evidence note",
            "text": "MED13 associates with cardiomyopathy.",
            "metadata": {},
        },
    )
    document_id = submit_response.json()["document"]["id"]

    extract_response = client.post(
        f"/v1/spaces/{space_id}/documents/{document_id}/extract",
        headers=_auth_headers(),
    )

    assert extract_response.status_code == 201
    payload = extract_response.json()
    candidate_discovery = payload["document"]["metadata"]["candidate_discovery"]
    assert candidate_discovery == {
        "method": "llm",
        "regex_candidate_count": 0,
        "llm_attempted": True,
        "llm_candidate_count": 1,
        "llm_status": "completed",
    }
    assert payload["proposal_count"] == 1
    stored_document = document_store.get_document(
        space_id=space_id,
        document_id=document_id,
    )
    assert stored_document is not None
    assert stored_document.metadata["candidate_discovery"] == candidate_discovery


def test_extract_document_use_llm_query_param_forces_llm_first(
    monkeypatch,
) -> None:
    client, _, document_store, _, _, space_id = _build_client(
        objective="Map MED13 mechanism evidence in cardiomyopathy.",
    )

    def _fail_regex(_text: str) -> list[ExtractedRelationCandidate]:
        raise AssertionError("regex candidate discovery should not run first")

    async def _fake_extract_with_diagnostics(
        _text: str,
        *,
        max_relations: int = 10,
        space_context: str = "",
    ) -> tuple[
        list[ExtractedRelationCandidate],
        DocumentCandidateExtractionDiagnostics,
    ]:
        del max_relations, space_context
        return (
            [
                ExtractedRelationCandidate(
                    subject_label="MED13",
                    relation_type="ASSOCIATED_WITH",
                    object_label="cardiomyopathy",
                    sentence="MED13 associates with cardiomyopathy.",
                ),
            ],
            DocumentCandidateExtractionDiagnostics(
                llm_candidate_status="completed",
                llm_candidate_count=1,
            ),
        )

    monkeypatch.setattr(
        "artana_evidence_api.routers.documents.extract_relation_candidates",
        _fail_regex,
    )
    monkeypatch.setattr(
        "artana_evidence_api.routers.documents.extract_relation_candidates_with_diagnostics",
        _fake_extract_with_diagnostics,
    )

    submit_response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "MED13 evidence note",
            "text": "MED13 associates with cardiomyopathy.",
            "metadata": {},
        },
    )
    document_id = submit_response.json()["document"]["id"]

    extract_response = client.post(
        f"/v1/spaces/{space_id}/documents/{document_id}/extract?use_llm=true",
        headers=_auth_headers(),
    )

    assert extract_response.status_code == 201
    payload = extract_response.json()
    candidate_discovery = payload["document"]["metadata"]["candidate_discovery"]
    assert candidate_discovery["method"] == "llm"
    assert candidate_discovery["llm_attempted"] is True
    assert candidate_discovery["llm_candidate_count"] == 1
    assert payload["proposal_count"] == 1
    stored_document = document_store.get_document(
        space_id=space_id,
        document_id=document_id,
    )
    assert stored_document is not None
    assert stored_document.metadata["candidate_discovery"] == candidate_discovery


def test_extract_document_surfaces_llm_review_fallback_in_metadata(
    monkeypatch,
) -> None:
    client, _, document_store, _, _, space_id = _build_client(
        objective="Map MED13 mechanism evidence in cardiomyopathy.",
    )

    async def _fake_review_with_diagnostics(**kwargs: object):
        drafts = kwargs["drafts"]
        return (
            drafts,
            DocumentProposalReviewDiagnostics(
                llm_review_status="fallback_error",
                llm_review_error="synthetic llm outage",
            ),
        )

    async def _fake_extract_with_diagnostics(
        text: str,
        *,
        space_context: str = "",
    ):
        del text, space_context
        return (
            [],
            DocumentCandidateExtractionDiagnostics(
                llm_candidate_status="fallback_error",
                llm_candidate_error="synthetic candidate outage",
            ),
        )

    monkeypatch.setattr(
        "artana_evidence_api.routers.documents.extract_relation_candidates_with_diagnostics",
        _fake_extract_with_diagnostics,
    )
    monkeypatch.setattr(
        "artana_evidence_api.routers.documents.extract_relation_candidates",
        lambda _text: [],
    )
    monkeypatch.setattr(
        "artana_evidence_api.routers.documents.review_document_extraction_drafts_with_diagnostics",
        _fake_review_with_diagnostics,
    )

    submit_response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "MED13 evidence note",
            "text": "MED13 associates with cardiomyopathy.",
            "metadata": {},
        },
    )
    document_id = submit_response.json()["document"]["id"]

    extract_response = client.post(
        f"/v1/spaces/{space_id}/documents/{document_id}/extract",
        headers=_auth_headers(),
    )

    assert extract_response.status_code == 201
    payload = extract_response.json()
    diagnostics = payload["document"]["metadata"]["extraction_diagnostics"]
    assert diagnostics == {
        "llm_candidate_status": "fallback_error",
        "llm_candidate_attempted": True,
        "llm_candidate_failed": True,
        "llm_candidate_error": "synthetic candidate outage",
        "llm_review_status": "fallback_error",
        "llm_review_attempted": True,
        "llm_review_failed": True,
        "llm_review_error": "synthetic llm outage",
    }

    stored_document = document_store.get_document(
        space_id=space_id,
        document_id=document_id,
    )
    assert stored_document is not None
    assert stored_document.metadata["extraction_diagnostics"] == diagnostics


def test_extract_document_keeps_no_candidate_diagnostics_out_of_review_queue(
    monkeypatch,
) -> None:
    client, _, document_store, _, _, space_id = _build_client(
        objective="Map MED13 mechanism evidence in cardiomyopathy.",
    )
    artifact_store = client.app.dependency_overrides[get_artifact_store]()

    monkeypatch.setattr(
        "artana_evidence_api.routers.documents.extract_relation_candidates",
        lambda _text: [],
    )

    async def _fake_extract_with_diagnostics(
        text: str,
        *,
        space_context: str = "",
    ) -> tuple[
        list[ExtractedRelationCandidate],
        DocumentCandidateExtractionDiagnostics,
    ]:
        del text, space_context
        return (
            [],
            DocumentCandidateExtractionDiagnostics(
                llm_candidate_status="completed",
                llm_candidate_count=0,
            ),
        )

    monkeypatch.setattr(
        "artana_evidence_api.routers.documents.extract_relation_candidates_with_diagnostics",
        _fake_extract_with_diagnostics,
    )

    submit_response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "Sparse evidence note",
            "text": "This note does not make a concrete supported relation claim.",
            "metadata": {},
        },
    )
    document_id = submit_response.json()["document"]["id"]

    extract_response = client.post(
        f"/v1/spaces/{space_id}/documents/{document_id}/extract",
        headers=_auth_headers(),
    )

    assert extract_response.status_code == 201
    payload = extract_response.json()
    assert payload["proposal_count"] == 0
    assert payload["review_item_count"] == 0
    assert payload["review_items"] == []
    assert payload["skipped_candidates"] == [
        {
            "document_id": document_id,
            "document_title": "Sparse evidence note",
            "reason": "No relation candidates matched the current extraction heuristics.",
        },
    ]

    stored_document = document_store.get_document(
        space_id=space_id,
        document_id=document_id,
    )
    assert stored_document is not None
    assert stored_document.metadata["review_item_count"] == 0
    assert stored_document.metadata["skipped_candidate_count"] == 1

    artifact_payload = artifact_store.get_artifact(
        space_id=space_id,
        run_id=payload["run"]["id"],
        artifact_key="document_extraction_result",
    )
    assert artifact_payload is not None
    assert artifact_payload.content["review_item_count"] == 0
    assert artifact_payload.content["review_item_ids"] == []


def test_extract_document_can_create_proposals_from_llm_candidate_helper(
    monkeypatch,
) -> None:
    client, _, document_store, proposal_store, _, space_id = _build_client(
        objective="Find angiosarcoma evidence.",
    )

    async def _fake_extract_with_diagnostics(
        text: str,
        *,
        space_context: str = "",
    ):
        del text, space_context
        return (
            [
                ExtractedRelationCandidate(
                    subject_label="TP53",
                    relation_type="ASSOCIATED_WITH",
                    object_label="angiosarcoma",
                    sentence="TP53 is associated with angiosarcoma.",
                ),
            ],
            DocumentCandidateExtractionDiagnostics(
                llm_candidate_status="completed",
            ),
        )

    monkeypatch.setattr(
        "artana_evidence_api.routers.documents.extract_relation_candidates_with_diagnostics",
        _fake_extract_with_diagnostics,
    )

    submit_response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "Angiosarcoma note",
            "text": (
                "This note mentions TP53, PLCG1, KDR, pazopanib, sorafenib, and "
                "angiosarcoma."
            ),
            "metadata": {},
        },
    )
    document_id = submit_response.json()["document"]["id"]

    extract_response = client.post(
        f"/v1/spaces/{space_id}/documents/{document_id}/extract",
        headers=_auth_headers(),
    )

    assert extract_response.status_code == 201
    payload = extract_response.json()
    assert payload["proposal_count"] == 1
    assert payload["document"]["metadata"]["candidate_count"] == 1
    assert (
        payload["document"]["metadata"]["extraction_diagnostics"][
            "llm_candidate_status"
        ]
        == "completed"
    )
    stored_document = document_store.get_document(
        space_id=space_id,
        document_id=document_id,
    )
    assert stored_document is not None
    assert (
        len(proposal_store.list_proposals(space_id=space_id, document_id=document_id))
        == 1
    )


def test_extract_document_degrades_to_unresolved_entities_when_graph_resolution_fails() -> (
    None
):
    client, _, document_store, _, _, space_id = _build_client(
        graph_api_gateway_dependency=_FailingEntityResolutionGraphApiGateway,
    )

    submit_response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "MED13 evidence note",
            "text": "MED13 associates with cardiomyopathy.",
            "metadata": {},
        },
    )
    document_id = submit_response.json()["document"]["id"]

    extract_response = client.post(
        f"/v1/spaces/{space_id}/documents/{document_id}/extract",
        headers=_auth_headers(),
    )

    assert extract_response.status_code == 201
    payload = extract_response.json()
    assert payload["proposal_count"] == 1
    proposal_payload = payload["proposals"][0]["payload"]
    assert proposal_payload["proposed_subject"].startswith("unresolved:")
    assert proposal_payload["proposed_object"].startswith("unresolved:")

    stored_document = document_store.get_document(
        space_id=space_id,
        document_id=document_id,
    )
    assert stored_document is not None
    assert stored_document.extraction_status == "completed"

    artifacts_response = client.get(
        f"/v1/spaces/{space_id}/runs/{payload['run']['id']}/artifacts",
        headers=_auth_headers(role="viewer"),
    )
    artifact_keys = {
        artifact["key"] for artifact in artifacts_response.json()["artifacts"]
    }
    assert "document_error" not in artifact_keys


def test_extract_document_creates_deferred_resolution_proposals_for_empty_graph() -> (
    None
):
    app = create_app()
    artifact_store = HarnessArtifactStore()
    binary_store = HarnessDocumentBinaryStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    research_state_store = HarnessResearchStateStore()
    research_space_store = HarnessResearchSpaceStore()
    run_registry = HarnessRunRegistry()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Empty Graph Space",
        description="Owned test space for deferred extraction.",
    )
    app.dependency_overrides[get_artifact_store] = lambda: artifact_store
    app.dependency_overrides[get_document_binary_store] = lambda: binary_store
    app.dependency_overrides[get_document_store] = lambda: document_store
    app.dependency_overrides[get_graph_api_gateway] = (
        lambda: _StubEmptyGraphApiGateway()
    )
    app.dependency_overrides[get_proposal_store] = lambda: proposal_store
    app.dependency_overrides[get_research_state_store] = lambda: research_state_store
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    app.dependency_overrides[get_run_registry] = lambda: run_registry
    client = TestClient(app)

    submit_response = client.post(
        f"/v1/spaces/{space.id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "Narrative MED13 evidence note",
            "text": "The study found that MED13 was associated with cardiomyopathy in mice.",
            "metadata": {},
        },
    )
    document_id = submit_response.json()["document"]["id"]

    extract_response = client.post(
        f"/v1/spaces/{space.id}/documents/{document_id}/extract",
        headers=_auth_headers(),
    )

    assert extract_response.status_code == 201
    payload = extract_response.json()
    assert payload["proposal_count"] == 1
    assert payload["skipped_candidates"] == []
    proposal_payload = payload["proposals"][0]["payload"]
    assert proposal_payload["proposed_subject"].startswith("unresolved:")
    assert proposal_payload["proposed_subject_label"] == "MED13"
    assert proposal_payload["proposed_object"].startswith("unresolved:")
    assert proposal_payload["proposed_object_label"] == "cardiomyopathy"


def test_extract_document_splits_compound_object_labels_into_multiple_proposals() -> (
    None
):
    client, _, _, proposal_store, _, space_id = _build_client()

    submit_response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "MED13 syndrome note",
            "text": (
                "MED13 causes FG syndrome (Opitz-Kaveggia), "
                "Lujan-Fryns syndrome, and Ohdo syndrome."
            ),
            "metadata": {},
        },
    )
    document_id = submit_response.json()["document"]["id"]

    extract_response = client.post(
        f"/v1/spaces/{space_id}/documents/{document_id}/extract",
        headers=_auth_headers(),
    )

    assert extract_response.status_code == 201
    payload = extract_response.json()
    assert payload["proposal_count"] == 3
    assert [
        proposal["payload"]["proposed_object_label"]
        for proposal in payload["proposals"]
    ] == [
        "FG syndrome",
        "Lujan-Fryns syndrome",
        "Ohdo syndrome",
    ]
    assert [
        proposal["metadata"]["resolved_object_label"]
        for proposal in payload["proposals"]
    ] == [
        "FG Syndrome Type 1",
        "Lujan-Fryns syndrome",
        "Ohdo syndrome MKBT",
    ]
    assert (
        len(
            proposal_store.list_proposals(space_id=space_id, document_id=document_id),
        )
        == 3
    )


def test_extract_pdf_document_runs_enrichment_before_extraction(monkeypatch) -> None:
    client, _, document_store, proposal_store, run_registry, space_id = _build_client()

    monkeypatch.setattr(
        "artana_evidence_api.routers.documents.extract_pdf_text",
        lambda payload: DocumentTextExtraction(
            text_content="MED13 associates with cardiomyopathy.",
            page_count=2,
        ),
    )

    upload_response = client.post(
        f"/v1/spaces/{space_id}/documents/pdf",
        headers=_auth_headers(),
        data={"title": "Uploaded MED13 PDF"},
        files={
            "file": (
                "med13.pdf",
                b"%PDF-1.4\nsynthetic\n%%EOF\n",
                "application/pdf",
            ),
        },
    )
    document_id = upload_response.json()["document"]["id"]

    extract_response = client.post(
        f"/v1/spaces/{space_id}/documents/{document_id}/extract",
        headers=_auth_headers(),
    )

    assert extract_response.status_code == 201
    payload = extract_response.json()
    assert payload["run"]["harness_id"] == "document-extraction"
    assert payload["document"]["last_enrichment_run_id"] is not None
    assert payload["document"]["page_count"] == 2
    assert payload["document"]["enrichment_status"] == "completed"
    assert payload["document"]["extraction_status"] == "completed"
    assert payload["proposal_count"] == 1
    stored_document = document_store.get_document(
        space_id=space_id,
        document_id=document_id,
    )
    assert stored_document is not None
    assert stored_document.enriched_storage_key is not None
    assert stored_document.last_enrichment_run_id is not None
    assert stored_document.last_extraction_run_id == payload["run"]["id"]
    assert (
        len(proposal_store.list_proposals(space_id=space_id, document_id=document_id))
        == 1
    )
    run_harness_ids = [
        run.harness_id for run in run_registry.list_runs(space_id=space_id)
    ]
    assert run_harness_ids[:3] == [
        "document-extraction",
        "document-enrichment",
        "document-ingestion",
    ]


def test_extract_text_document_skips_enrichment_run() -> None:
    client, _, _, _, run_registry, space_id = _build_client()

    submit_response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "MED13 evidence note",
            "text": "MED13 associates with cardiomyopathy.",
            "metadata": {},
        },
    )
    document_id = submit_response.json()["document"]["id"]

    extract_response = client.post(
        f"/v1/spaces/{space_id}/documents/{document_id}/extract",
        headers=_auth_headers(),
    )

    assert extract_response.status_code == 201
    run_harness_ids = [
        run.harness_id for run in run_registry.list_runs(space_id=space_id)
    ]
    assert "document-enrichment" not in run_harness_ids
    assert run_harness_ids[:2] == ["document-extraction", "document-ingestion"]


def test_extract_document_is_idempotent_after_completion() -> None:
    client, _, document_store, proposal_store, _, space_id = _build_client()

    submit_response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "MED13 evidence note",
            "text": "MED13 associates with cardiomyopathy.",
            "metadata": {},
        },
    )
    document_id = submit_response.json()["document"]["id"]

    first_extract_response = client.post(
        f"/v1/spaces/{space_id}/documents/{document_id}/extract",
        headers=_auth_headers(),
    )
    second_extract_response = client.post(
        f"/v1/spaces/{space_id}/documents/{document_id}/extract",
        headers=_auth_headers(),
    )

    assert first_extract_response.status_code == 201
    assert second_extract_response.status_code == 201
    first_payload = first_extract_response.json()
    second_payload = second_extract_response.json()
    assert second_payload["run"]["id"] == first_payload["run"]["id"]
    assert second_payload["proposal_count"] == first_payload["proposal_count"] == 1
    assert (
        len(
            proposal_store.list_proposals(space_id=space_id, document_id=document_id),
        )
        == 1
    )
    stored_document = document_store.get_document(
        space_id=space_id,
        document_id=document_id,
    )
    assert stored_document is not None
    assert stored_document.last_extraction_run_id == first_payload["run"]["id"]


def test_extract_document_rejects_viewer_role_without_side_effects() -> None:
    client, _, document_store, proposal_store, run_registry, space_id = _build_client()

    submit_response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "MED13 evidence note",
            "text": "MED13 associates with cardiomyopathy.",
            "metadata": {},
        },
    )
    document_id = submit_response.json()["document"]["id"]

    extract_response = client.post(
        f"/v1/spaces/{space_id}/documents/{document_id}/extract",
        headers=_auth_headers(role="viewer"),
    )

    assert extract_response.status_code == 403
    stored_document = document_store.get_document(
        space_id=space_id,
        document_id=document_id,
    )
    assert stored_document is not None
    assert stored_document.extraction_status == "not_started"
    assert stored_document.last_extraction_run_id is None
    assert (
        proposal_store.list_proposals(space_id=space_id, document_id=document_id) == []
    )
    runs = run_registry.list_runs(space_id=space_id)
    assert len(runs) == 1
    assert runs[0].harness_id == "document-ingestion"


def test_extract_document_response_includes_text_content_and_stays_strict_json() -> (
    None
):
    client, _, _, _, _, space_id = _build_client()

    submit_response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "MED13 evidence note",
            "text": "MED13 associates with cardiomyopathy.\u000bMore text.\nNext line.",
            "metadata": {},
        },
    )
    document_id = submit_response.json()["document"]["id"]

    extract_response = client.post(
        f"/v1/spaces/{space_id}/documents/{document_id}/extract",
        headers=_auth_headers(),
    )

    assert extract_response.status_code == 201
    payload = extract_response.json()
    assert payload["document"]["text_content"] == (
        "MED13 associates with cardiomyopathy.\u000bMore text.\nNext line."
    )
    assert payload["document"]["extraction_status"] == "completed"
    assert json.loads(extract_response.text)["document"]["id"] == document_id


def test_extract_document_routes_variant_aware_documents_through_bridge(
    monkeypatch,
) -> None:
    client, _, document_store, proposal_store, _, space_id = _build_client()

    async def _fake_variant_extract(
        *,
        space_id: UUID,
        document,
        graph_api_gateway,
        review_context=None,
    ) -> VariantAwareDocumentExtractionResult:
        del space_id, graph_api_gateway, review_context
        contract = ExtractionContract(
            decision="generated",
            confidence_score=0.0,
            rationale="Variant-aware extraction staged one anchored variant.",
            evidence=[],
            source_type="pubmed",
            document_id=document.id,
            entities=[
                ExtractedEntityCandidate(
                    entity_type="VARIANT",
                    label="c.977C>A",
                    anchors={
                        "gene_symbol": "MED13",
                        "hgvs_notation": "c.977C>A",
                    },
                    metadata={
                        "transcript": "NM_015335.6",
                        "hgvs_protein": "p.Thr326Lys",
                    },
                    evidence_excerpt="MED13 NM_015335.6:c.977C>A (p.Thr326Lys)",
                    evidence_locator="text_span:20-52",
                    assessment=_strong_assessment(),
                ),
            ],
            observations=[],
            relations=[],
            rejected_facts=[],
            pipeline_payloads=[],
            shadow_mode=True,
            agent_run_id="variant-aware-test",
        )
        return VariantAwareDocumentExtractionResult(
            contract=contract,
            proposal_drafts=(
                HarnessProposalDraft(
                    proposal_type="entity_candidate",
                    source_kind="document_extraction",
                    source_key=f"{document.id}:variant:0",
                    document_id=document.id,
                    title="Extracted entity: VARIANT c.977C>A",
                    summary="MED13 NM_015335.6:c.977C>A (p.Thr326Lys)",
                    confidence=0.9,
                    ranking_score=0.9,
                    reasoning_path={"kind": "entity_candidate"},
                    evidence_bundle=[],
                    payload={
                        "entity_type": "VARIANT",
                        "display_label": "c.977C>A",
                        "label": "c.977C>A",
                        "anchors": {
                            "gene_symbol": "MED13",
                            "hgvs_notation": "c.977C>A",
                        },
                        "metadata": {
                            "transcript": "NM_015335.6",
                            "hgvs_protein": "p.Thr326Lys",
                        },
                        "identifiers": {
                            "gene_symbol": "MED13",
                            "hgvs_notation": "c.977C>A",
                        },
                        "assessment": _strong_assessment().model_dump(mode="json"),
                    },
                    metadata={"candidate_kind": "entity"},
                ),
            ),
            review_item_drafts=(
                HarnessReviewItemDraft(
                    review_type="phenotype_claim_review",
                    source_family="document_extraction",
                    source_kind="document_extraction",
                    source_key=f"{document.id}:phenotype-review:0",
                    document_id=document.id,
                    title="Review phenotype link for c.977C>A",
                    summary="developmental delay",
                    priority="medium",
                    confidence=0.7,
                    ranking_score=0.7,
                    evidence_bundle=[],
                    payload={"phenotype_span": "developmental delay"},
                    metadata={"candidate_kind": "phenotype_review"},
                ),
            ),
            skipped_items=[],
            candidate_discovery={
                "method": "variant_aware_extraction",
                "variant_aware_recommended": True,
                "llm_attempted": True,
                "llm_candidate_count": 0,
                "entity_candidate_count": 1,
                "observation_candidate_count": 0,
                "review_item_count": 1,
                "llm_status": "completed",
            },
            extraction_diagnostics={
                "extraction_mode": "variant_aware",
                "bridge_proposal_count": 1,
                "bridge_review_item_count": 1,
            },
        )

    monkeypatch.setattr(
        "artana_evidence_api.routers.documents.document_supports_variant_aware_extraction",
        lambda document: True,
    )
    monkeypatch.setattr(
        "artana_evidence_api.routers.documents.extract_variant_aware_document",
        _fake_variant_extract,
    )

    submit_response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "Variant note",
            "text": "MED13 NM_015335.6:c.977C>A (p.Thr326Lys) was identified.",
            "metadata": {},
        },
    )
    document_id = submit_response.json()["document"]["id"]

    extract_response = client.post(
        f"/v1/spaces/{space_id}/documents/{document_id}/extract",
        headers=_auth_headers(),
    )

    assert extract_response.status_code == 201
    payload = extract_response.json()
    assert payload["proposal_count"] == 1
    assert payload["review_item_count"] == 1
    assert payload["review_items"][0]["item_type"] == "review_item"
    assert payload["review_items"][0]["kind"] == "phenotype_claim_review"
    assert payload["review_items"][0]["summary"] == "developmental delay"
    assert payload["skipped_candidates"] == []
    assert payload["proposals"][0]["proposal_type"] == "entity_candidate"
    assert payload["document"]["metadata"]["variant_aware_extraction"] is True
    assert payload["document"]["metadata"]["review_item_count"] == 1
    assert payload["document"]["metadata"]["candidate_discovery"]["method"] == (
        "variant_aware_extraction"
    )

    stored_document = document_store.get_document(
        space_id=space_id,
        document_id=document_id,
    )
    assert stored_document is not None
    assert stored_document.metadata["variant_aware_extraction"] is True
    assert (
        len(proposal_store.list_proposals(space_id=space_id, document_id=document_id))
        == 1
    )

    artifact_response = client.get(
        f"/v1/spaces/{space_id}/runs/{payload['run']['id']}/artifacts/document_extraction_result",
        headers=_auth_headers(role="viewer"),
    )
    assert artifact_response.status_code == 200
    artifact_payload = artifact_response.json()["content"]
    assert artifact_payload["variant_aware_extraction"] is True
    assert artifact_payload["proposal_count"] == 1
    assert artifact_payload["review_item_count"] == 1


def test_extract_document_variant_aware_reuses_existing_deduped_outputs(
    monkeypatch,
) -> None:
    client, _, document_store, proposal_store, run_registry, space_id = _build_client()
    review_item_store = client.app.dependency_overrides[get_review_item_store]()

    async def _fake_variant_extract(
        *,
        space_id: UUID,
        document,
        graph_api_gateway,
        review_context=None,
    ) -> VariantAwareDocumentExtractionResult:
        del space_id, graph_api_gateway, review_context
        contract = ExtractionContract(
            decision="generated",
            confidence_score=0.0,
            rationale="Variant-aware extraction matched already staged outputs.",
            evidence=[],
            source_type="pubmed",
            document_id=document.id,
            entities=[
                ExtractedEntityCandidate(
                    entity_type="VARIANT",
                    label="c.977C>A",
                    anchors={
                        "gene_symbol": "MED13",
                        "hgvs_notation": "c.977C>A",
                    },
                    metadata={"transcript": "NM_015335.6"},
                    evidence_excerpt="MED13 NM_015335.6:c.977C>A (p.Thr326Lys)",
                    evidence_locator="text_span:20-52",
                    assessment=_strong_assessment(),
                ),
            ],
            observations=[],
            relations=[],
            rejected_facts=[],
            pipeline_payloads=[],
            shadow_mode=True,
            agent_run_id="variant-aware-reuse-test",
        )
        return VariantAwareDocumentExtractionResult(
            contract=contract,
            proposal_drafts=(
                HarnessProposalDraft(
                    proposal_type="entity_candidate",
                    source_kind="document_extraction",
                    source_key=f"{document.id}:variant:0",
                    document_id=document.id,
                    title="Extracted entity: VARIANT c.977C>A",
                    summary="MED13 NM_015335.6:c.977C>A (p.Thr326Lys)",
                    confidence=0.9,
                    ranking_score=0.9,
                    reasoning_path={"kind": "entity_candidate"},
                    evidence_bundle=[],
                    payload={
                        "entity_type": "VARIANT",
                        "display_label": "c.977C>A",
                        "label": "c.977C>A",
                        "anchors": {
                            "gene_symbol": "MED13",
                            "hgvs_notation": "c.977C>A",
                        },
                        "metadata": {"transcript": "NM_015335.6"},
                    },
                    metadata={"candidate_kind": "entity"},
                    claim_fingerprint="variant-reuse-proposal-fp",
                ),
            ),
            review_item_drafts=(
                HarnessReviewItemDraft(
                    review_type="phenotype_claim_review",
                    source_family="document_extraction",
                    source_kind="document_extraction",
                    source_key=f"{document.id}:phenotype-review:0",
                    document_id=document.id,
                    title="Review phenotype link for c.977C>A",
                    summary="developmental delay",
                    priority="medium",
                    confidence=0.7,
                    ranking_score=0.7,
                    evidence_bundle=[],
                    payload={"phenotype_span": "developmental delay"},
                    metadata={"candidate_kind": "phenotype_review"},
                    review_fingerprint="variant-reuse-review-fp",
                ),
            ),
            skipped_items=[],
            candidate_discovery={
                "method": "variant_aware_extraction",
                "variant_aware_recommended": True,
                "llm_attempted": True,
                "llm_candidate_count": 0,
                "entity_candidate_count": 1,
                "observation_candidate_count": 0,
                "review_item_count": 1,
                "llm_status": "completed",
            },
            extraction_diagnostics={
                "extraction_mode": "variant_aware",
                "bridge_proposal_count": 1,
                "bridge_review_item_count": 1,
            },
        )

    monkeypatch.setattr(
        "artana_evidence_api.routers.documents.document_supports_variant_aware_extraction",
        lambda document: True,
    )
    monkeypatch.setattr(
        "artana_evidence_api.routers.documents.extract_variant_aware_document",
        _fake_variant_extract,
    )

    submit_response = client.post(
        f"/v1/spaces/{space_id}/documents/text",
        headers=_auth_headers(),
        json={
            "title": "Variant note",
            "text": "MED13 NM_015335.6:c.977C>A (p.Thr326Lys) was identified.",
            "metadata": {},
        },
    )
    document_id = submit_response.json()["document"]["id"]

    prior_run = run_registry.create_run(
        space_id=space_id,
        harness_id="document-extraction",
        title="Earlier extraction attempt",
        input_payload={"document_id": document_id},
        graph_service_status="ok",
        graph_service_version="tests",
    )
    existing_proposal = proposal_store.create_proposals(
        space_id=space_id,
        run_id=prior_run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="entity_candidate",
                source_kind="document_extraction",
                source_key=f"{document_id}:variant:0",
                document_id=document_id,
                title="Extracted entity: VARIANT c.977C>A",
                summary="MED13 NM_015335.6:c.977C>A (p.Thr326Lys)",
                confidence=0.9,
                ranking_score=0.9,
                reasoning_path={"kind": "entity_candidate"},
                evidence_bundle=[],
                payload={"display_label": "c.977C>A"},
                metadata={"candidate_kind": "entity"},
                claim_fingerprint="variant-reuse-proposal-fp",
            ),
        ),
    )[0]
    existing_review_item = review_item_store.create_review_items(
        space_id=space_id,
        run_id=prior_run.id,
        review_items=(
            HarnessReviewItemDraft(
                review_type="phenotype_claim_review",
                source_family="document_extraction",
                source_kind="document_extraction",
                source_key=f"{document_id}:phenotype-review:0",
                document_id=document_id,
                title="Review phenotype link for c.977C>A",
                summary="developmental delay",
                priority="medium",
                confidence=0.7,
                ranking_score=0.7,
                evidence_bundle=[],
                payload={"phenotype_span": "developmental delay"},
                metadata={"candidate_kind": "phenotype_review"},
                review_fingerprint="variant-reuse-review-fp",
            ),
        ),
    )[0]
    document_store.update_document(
        space_id=space_id,
        document_id=document_id,
        last_extraction_run_id=prior_run.id,
        extraction_status="failed",
    )

    extract_response = client.post(
        f"/v1/spaces/{space_id}/documents/{document_id}/extract",
        headers=_auth_headers(),
    )

    assert extract_response.status_code == 201
    payload = extract_response.json()
    assert payload["proposal_count"] == 1
    assert payload["review_item_count"] == 1
    assert payload["proposals"][0]["id"] == existing_proposal.id
    assert payload["review_items"][0]["resource_id"] == existing_review_item.id
    assert payload["document"]["metadata"]["reused_existing_proposal_count"] == 1
    assert payload["document"]["metadata"]["reused_existing_review_item_count"] == 1
    assert (
        len(proposal_store.list_proposals(space_id=space_id, document_id=document_id))
        == 1
    )
    assert (
        len(review_item_store.list_review_items(space_id=space_id, document_id=document_id))
        == 1
    )

    artifact_response = client.get(
        f"/v1/spaces/{space_id}/runs/{payload['run']['id']}/artifacts/document_extraction_result",
        headers=_auth_headers(role="viewer"),
    )
    assert artifact_response.status_code == 200
    artifact_payload = artifact_response.json()["content"]
    assert artifact_payload["proposal_ids"] == [existing_proposal.id]
    assert artifact_payload["review_item_ids"] == [existing_review_item.id]
    assert artifact_payload["reused_existing_proposal_count"] == 1
    assert artifact_payload["reused_existing_review_item_count"] == 1


def test_get_document_returns_404_when_missing() -> None:
    client, _, _, _, _, space_id = _build_client()

    response = client.get(
        f"/v1/spaces/{space_id}/documents/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        headers=_auth_headers(),
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
