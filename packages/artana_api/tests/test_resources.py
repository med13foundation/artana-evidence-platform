from __future__ import annotations

import json
from uuid import UUID

import httpx
import pytest
from artana_api.exceptions import ArtanaConfigurationError
from artana_api_test_helpers import (
    ALT_SPACE_ID,
    DEFAULT_SPACE_ID,
    ENTITY_ID,
    RUN_ID,
    artifact_payload,
    graph_connection_response,
    graph_search_response,
    make_client,
    onboarding_start_response,
    run_payload,
)

DOCUMENT_ID = "77777777-7777-7777-7777-777777777777"
PROPOSAL_ID = "88888888-8888-8888-8888-888888888888"
REVIEW_ITEM_ID = "abababab-abab-abab-abab-abababababab"
SESSION_ID = "99999999-9999-9999-9999-999999999999"
JOB_ID = "12121212-1212-1212-1212-121212121212"


@pytest.fixture
def client_factory():
    return make_client


def _document_detail_payload(
    *,
    source_type: str = "text",
    enrichment_status: str | None = None,
    extraction_status: str = "not_started",
    page_count: int | None | object = ...,
    text_excerpt: str | None | object = ...,
    text_content: str | None | object = ...,
    last_enrichment_run_id: str | None = None,
    last_extraction_run_id: str | None = None,
) -> dict[str, object]:
    resolved_page_count = None if page_count is ... else page_count
    if page_count is ... and source_type == "pdf":
        resolved_page_count = None
    resolved_text_excerpt = (
        "MED13 associates with cardiomyopathy." if text_excerpt is ... else text_excerpt
    )
    if text_excerpt is ... and source_type == "pdf":
        resolved_text_excerpt = ""
    resolved_text_content = (
        "MED13 associates with cardiomyopathy." if text_content is ... else text_content
    )
    if text_content is ... and source_type == "pdf":
        resolved_text_content = ""
    return {
        "id": DOCUMENT_ID,
        "space_id": DEFAULT_SPACE_ID,
        "created_by": "user-1",
        "title": "MED13 evidence note",
        "source_type": source_type,
        "filename": None if source_type == "text" else "med13.pdf",
        "media_type": "text/plain" if source_type == "text" else "application/pdf",
        "sha256": "abc123",
        "byte_size": 128,
        "page_count": resolved_page_count,
        "text_excerpt": resolved_text_excerpt,
        "ingestion_run_id": RUN_ID,
        "last_enrichment_run_id": last_enrichment_run_id,
        "last_extraction_run_id": last_extraction_run_id,
        "enrichment_status": (
            "skipped"
            if enrichment_status is None and source_type == "text"
            else "not_started" if enrichment_status is None else enrichment_status
        ),
        "extraction_status": extraction_status,
        "metadata": {"origin": "test"},
        "created_at": "2026-03-20T10:00:00Z",
        "updated_at": "2026-03-20T10:00:01Z",
        "text_content": resolved_text_content,
    }


def _proposal_payload(*, status: str = "pending_review") -> dict[str, object]:
    return {
        "id": PROPOSAL_ID,
        "space_id": DEFAULT_SPACE_ID,
        "run_id": RUN_ID,
        "proposal_type": "candidate_claim",
        "source_kind": "document_extraction",
        "source_key": f"{DOCUMENT_ID}:0",
        "document_id": DOCUMENT_ID,
        "title": "Extracted claim: MED13 ASSOCIATED_WITH cardiomyopathy",
        "summary": "MED13 associates with cardiomyopathy.",
        "status": status,
        "confidence": 0.82,
        "ranking_score": 0.88,
        "reasoning_path": {"sentence": "MED13 associates with cardiomyopathy."},
        "evidence_bundle": [],
        "payload": {
            "proposed_subject": ENTITY_ID,
            "proposed_claim_type": "ASSOCIATED_WITH",
            "proposed_object": "44444444-4444-4444-4444-444444444444",
        },
        "metadata": {"origin": "document_extraction"},
        "decision_reason": None if status == "pending_review" else "Reviewed",
        "decided_at": None if status == "pending_review" else "2026-03-20T10:00:02Z",
        "created_at": "2026-03-20T10:00:00Z",
        "updated_at": "2026-03-20T10:00:01Z",
    }


def _review_queue_item_payload(
    *,
    item_type: str = "proposal",
    status: str = "pending_review",
) -> dict[str, object]:
    if item_type == "proposal":
        return {
            "id": f"proposal:{PROPOSAL_ID}",
            "item_type": "proposal",
            "resource_id": PROPOSAL_ID,
            "kind": "candidate_claim",
            "status": status,
            "title": "Extracted claim: MED13 ASSOCIATED_WITH cardiomyopathy",
            "summary": "MED13 associates with cardiomyopathy.",
            "priority": "medium",
            "confidence": 0.82,
            "ranking_score": 0.88,
            "run_id": RUN_ID,
            "document_id": DOCUMENT_ID,
            "source_family": "document_extraction",
            "source_kind": "document_extraction",
            "source_key": f"{DOCUMENT_ID}:0",
            "linked_resource": {"proposal_id": PROPOSAL_ID},
            "available_actions": [] if status != "pending_review" else ["promote", "reject"],
            "payload": {
                "proposed_subject": ENTITY_ID,
                "proposed_claim_type": "ASSOCIATED_WITH",
                "proposed_object": "44444444-4444-4444-4444-444444444444",
            },
            "metadata": {"origin": "document_extraction"},
            "evidence_bundle": [],
            "decision_reason": None if status == "pending_review" else "Reviewed",
            "decided_at": None if status == "pending_review" else "2026-03-20T10:00:02Z",
            "created_at": "2026-03-20T10:00:00Z",
            "updated_at": "2026-03-20T10:00:01Z",
        }
    return {
        "id": f"review_item:{REVIEW_ITEM_ID}",
        "item_type": "review_item",
        "resource_id": REVIEW_ITEM_ID,
        "kind": "phenotype_claim_review",
        "status": status,
        "title": "Review phenotype evidence for MED13",
        "summary": "developmental delay",
        "priority": "medium",
        "confidence": 0.7,
        "ranking_score": 0.74,
        "run_id": RUN_ID,
        "document_id": DOCUMENT_ID,
        "source_family": "document_extraction",
        "source_kind": "document_extraction",
        "source_key": f"{DOCUMENT_ID}:phenotype:0",
        "linked_resource": None,
        "available_actions": (
            [] if status != "pending_review" else ["convert_to_proposal", "dismiss", "mark_resolved"]
        ),
        "payload": {"phenotype_label": "developmental delay"},
        "metadata": {"origin": "variant_aware_extraction"},
        "evidence_bundle": [],
        "decision_reason": None if status == "pending_review" else "Handled",
        "decided_at": None if status == "pending_review" else "2026-03-20T10:00:02Z",
        "created_at": "2026-03-20T10:00:00Z",
        "updated_at": "2026-03-20T10:00:01Z",
    }


def _chat_session_payload() -> dict[str, object]:
    return {
        "id": SESSION_ID,
        "space_id": DEFAULT_SPACE_ID,
        "title": "Research chat",
        "created_by": "user-1",
        "last_run_id": RUN_ID,
        "status": "active",
        "created_at": "2026-03-20T10:00:00Z",
        "updated_at": "2026-03-20T10:00:01Z",
    }


def test_spaces_list_uses_expected_path(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/spaces"
        return httpx.Response(
            200,
            json={
                "spaces": [
                    {
                        "id": DEFAULT_SPACE_ID,
                        "slug": "demo-space",
                        "name": "Demo Space",
                        "description": "Demo description",
                        "status": "active",
                        "role": "owner",
                    },
                ],
                "total": 1,
            },
        )

    client = client_factory(handler)
    try:
        response = client.spaces.list()
    finally:
        client.close()

    assert response.total == 1
    assert response.spaces[0].slug == "demo-space"


def test_spaces_create_posts_expected_payload(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/spaces"
        assert json.loads(request.content.decode()) == {
            "name": "My Space",
            "description": "Research area",
        }
        return httpx.Response(
            201,
            json={
                "id": DEFAULT_SPACE_ID,
                "slug": "my-space",
                "name": "My Space",
                "description": "Research area",
                "status": "active",
                "role": "owner",
                "is_default": False,
            },
        )

    client = client_factory(handler)
    try:
        response = client.spaces.create(name="My Space", description="Research area")
    finally:
        client.close()

    assert response.slug == "my-space"
    assert response.is_default is False


def test_spaces_ensure_default_uses_expected_path(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.path == "/v1/spaces/default"
        return httpx.Response(
            200,
            json={
                "id": DEFAULT_SPACE_ID,
                "slug": "personal-111111111111",
                "name": "Personal Sandbox",
                "description": "Private default research space.",
                "status": "active",
                "role": "owner",
                "is_default": True,
            },
        )

    client = client_factory(handler, default_space_id=None)
    try:
        response = client.spaces.ensure_default()
    finally:
        client.close()

    assert response.is_default is True
    assert response.id == DEFAULT_SPACE_ID


def test_auth_bootstrap_api_key_posts_expected_payload(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/auth/bootstrap"
        assert request.headers["X-Artana-Bootstrap-Key"] == "bootstrap-secret"
        assert json.loads(request.content.decode()) == {
            "email": "developer@example.com",
            "username": "developer",
            "full_name": "Developer Example",
            "role": "researcher",
            "api_key_name": "Notebook Key",
            "api_key_description": "For notebooks",
            "create_default_space": True,
        }
        return httpx.Response(
            201,
            json={
                "user": {
                    "id": "99999999-9999-9999-9999-999999999999",
                    "email": "developer@example.com",
                    "username": "developer",
                    "full_name": "Developer Example",
                    "role": "researcher",
                    "status": "active",
                },
                "api_key": {
                    "id": "55555555-5555-5555-5555-555555555555",
                    "name": "Notebook Key",
                    "key_prefix": "art_sk_abc123",
                    "status": "active",
                    "api_key": "art_sk_super_secret",
                    "created_at": "2026-03-20T10:00:00Z",
                },
                "default_space": {
                    "id": DEFAULT_SPACE_ID,
                    "slug": "personal-111111111111",
                    "name": "Personal Sandbox",
                    "description": "Private default research space.",
                    "status": "active",
                    "role": "owner",
                    "is_default": True,
                },
            },
        )

    client = client_factory(handler, api_key=None, access_token=None)
    try:
        response = client.auth.bootstrap_api_key(
            bootstrap_key="bootstrap-secret",
            email="developer@example.com",
            username="developer",
            full_name="Developer Example",
            api_key_name="Notebook Key",
            api_key_description="For notebooks",
        )
    finally:
        client.close()

    assert response.api_key.api_key == "art_sk_super_secret"
    assert response.default_space is not None
    assert response.default_space.is_default is True


def test_auth_me_reads_current_identity(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/auth/me"
        return httpx.Response(
            200,
            json={
                "user": {
                    "id": "99999999-9999-9999-9999-999999999999",
                    "email": "developer@example.com",
                    "username": "developer",
                    "full_name": "Developer Example",
                    "role": "researcher",
                    "status": "active",
                },
                "default_space": {
                    "id": DEFAULT_SPACE_ID,
                    "slug": "personal-111111111111",
                    "name": "Personal Sandbox",
                    "description": "Private default research space.",
                    "status": "active",
                    "role": "owner",
                    "is_default": True,
                },
            },
        )

    client = client_factory(handler)
    try:
        response = client.auth.me()
    finally:
        client.close()

    assert response.user.email == "developer@example.com"
    assert response.default_space is not None
    assert response.default_space.id == DEFAULT_SPACE_ID


def test_auth_create_api_key_posts_expected_payload(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/auth/api-keys"
        assert json.loads(request.content.decode()) == {
            "name": "CLI Key",
            "description": "For automation",
        }
        return httpx.Response(
            201,
            json={
                "user": {
                    "id": "99999999-9999-9999-9999-999999999999",
                    "email": "developer@example.com",
                    "username": "developer",
                    "full_name": "Developer Example",
                    "role": "researcher",
                    "status": "active",
                },
                "api_key": {
                    "id": "66666666-6666-6666-6666-666666666666",
                    "name": "CLI Key",
                    "key_prefix": "art_sk_cli456",
                    "status": "active",
                    "api_key": "art_sk_cli_secret",
                    "created_at": "2026-03-20T10:00:00Z",
                },
                "default_space": None,
            },
        )

    client = client_factory(handler)
    try:
        response = client.auth.create_api_key(
            name="CLI Key",
            description="For automation",
        )
    finally:
        client.close()

    assert response.api_key.name == "CLI Key"
    assert response.api_key.api_key == "art_sk_cli_secret"


def test_spaces_delete_uses_explicit_space_id(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == f"/v1/spaces/{ALT_SPACE_ID}"
        assert request.url.params == httpx.QueryParams()
        return httpx.Response(204)

    client = client_factory(handler)
    try:
        response = client.spaces.delete(space_id=ALT_SPACE_ID)
    finally:
        client.close()

    assert response is None


def test_spaces_delete_supports_confirm_archive(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == f"/v1/spaces/{ALT_SPACE_ID}"
        assert request.url.params == httpx.QueryParams({"confirm": "true"})
        return httpx.Response(204)

    client = client_factory(handler)
    try:
        response = client.spaces.delete(space_id=ALT_SPACE_ID, confirm=True)
    finally:
        client.close()

    assert response is None


def test_graph_search_uses_default_space_and_parses_result(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert (
            request.url.path
            == f"/v1/spaces/{DEFAULT_SPACE_ID}/agents/graph-search/runs"
        )
        payload = json.loads(request.content.decode())
        assert payload["question"] == "What is known about MED13?"
        assert payload["top_k"] == 25
        return httpx.Response(201, json=graph_search_response())

    client = client_factory(handler)
    try:
        response = client.graph.search(question="What is known about MED13?")
    finally:
        client.close()

    assert response.result.decision == "generated"
    assert response.result.total_results == 1
    assert response.result.results[0].display_label == "MED13"


def test_graph_search_bootstraps_personal_default_space_once(client_factory) -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == "/v1/spaces/default":
            return httpx.Response(
                200,
                json={
                    "id": DEFAULT_SPACE_ID,
                    "slug": "personal-111111111111",
                    "name": "Personal Sandbox",
                    "description": "Private default research space.",
                    "status": "active",
                    "role": "owner",
                    "is_default": True,
                },
            )
        return httpx.Response(201, json=graph_search_response())

    client = client_factory(handler, default_space_id=None)
    try:
        first_response = client.graph.search(question="What is known about MED13?")
        second_response = client.graph.search(question="What is known about MED13?")
    finally:
        client.close()

    assert requested_paths == [
        "/v1/spaces/default",
        f"/v1/spaces/{DEFAULT_SPACE_ID}/agents/graph-search/runs",
        f"/v1/spaces/{DEFAULT_SPACE_ID}/agents/graph-search/runs",
    ]
    assert first_response.run.space_id == DEFAULT_SPACE_ID
    assert second_response.run.space_id == DEFAULT_SPACE_ID


def test_graph_connection_posts_uuid_seed_ids_and_explicit_space(
    client_factory,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert (
            request.url.path
            == f"/v1/spaces/{ALT_SPACE_ID}/agents/graph-connections/runs"
        )
        payload = json.loads(request.content.decode())
        assert payload["seed_entity_ids"] == [ENTITY_ID]
        assert payload["source_type"] == "pubmed"
        assert payload["relation_types"] == ["ASSOCIATED_WITH"]
        assert payload["max_depth"] == 3
        assert payload["shadow_mode"] is False
        return httpx.Response(201, json=graph_connection_response())

    client = client_factory(handler)
    try:
        response = client.graph.connect(
            seed_entity_ids=[UUID(ENTITY_ID)],
            space_id=ALT_SPACE_ID,
            source_type="pubmed",
            relation_types=["ASSOCIATED_WITH"],
            max_depth=3,
            shadow_mode=False,
        )
    finally:
        client.close()

    assert response.outcomes[0].proposed_relations[0].relation_type == "ASSOCIATED_WITH"


def test_graph_connection_rejects_invalid_seed_entity_id(client_factory) -> None:
    client = client_factory(lambda request: httpx.Response(200, json={}))
    try:
        with pytest.raises(ArtanaConfigurationError):
            client.graph.connect(seed_entity_ids=["not-a-uuid"])
    finally:
        client.close()


def test_onboarding_start_parses_assistant_message(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert (
            request.url.path
            == f"/v1/spaces/{DEFAULT_SPACE_ID}/agents/research-onboarding/runs"
        )
        payload = json.loads(request.content.decode())
        assert payload["research_title"] == "MED13"
        return httpx.Response(201, json=onboarding_start_response())

    client = client_factory(handler)
    try:
        response = client.onboarding.start(
            research_title="MED13",
            primary_objective="Understand disease mechanisms",
        )
    finally:
        client.close()

    assert response.assistant_message.message_type == "clarification_request"
    assert response.assistant_message.questions[0].id == "q-1"
    assert response.research_state.pending_questions == [
        "Which phenotype focus matters most?",
    ]


def test_onboarding_reply_posts_expected_payload(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert (
            request.url.path
            == f"/v1/spaces/{ALT_SPACE_ID}/agents/research-onboarding/turns"
        )
        payload = json.loads(request.content.decode())
        assert payload["thread_id"] == "thread-1"
        assert payload["message_id"] == "message-1"
        assert payload["attachments"] == [{"kind": "note", "value": "attached"}]
        assert payload["contextual_anchor"] == {"section": "Scope"}
        return httpx.Response(
            201,
            json={
                "run": run_payload(
                    harness_id="research-onboarding",
                    title="MED13 Onboarding",
                    input_payload={"thread_id": "thread-1"},
                ),
                "research_state": onboarding_start_response()["research_state"],
                "assistant_message": onboarding_start_response()["assistant_message"],
            },
        )

    client = client_factory(handler)
    try:
        response = client.onboarding.reply(
            space_id=ALT_SPACE_ID,
            thread_id="thread-1",
            message_id="message-1",
            intent="answer",
            mode="reply",
            reply_text="Focus on cardiomyopathy.",
            attachments=[{"kind": "note", "value": "attached"}],
            contextual_anchor={"section": "Scope"},
        )
    finally:
        client.close()

    assert response.run.harness_id == "research-onboarding"


def test_runs_list_and_get_use_expected_paths(client_factory) -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path.endswith("/runs"):
            return httpx.Response(
                200,
                json={
                    "runs": [
                        run_payload(
                            harness_id="graph-search",
                            title="Graph Search Agent Run",
                        ),
                    ],
                    "total": 1,
                },
            )
        return httpx.Response(
            200,
            json=run_payload(
                run_id=RUN_ID,
                space_id=ALT_SPACE_ID,
                harness_id="graph-search",
                title="Graph Search Agent Run",
            ),
        )

    client = client_factory(handler)
    try:
        listed = client.runs.list()
        fetched = client.runs.get(run_id=RUN_ID, space_id=ALT_SPACE_ID)
    finally:
        client.close()

    assert requested_paths == [
        f"/v1/spaces/{DEFAULT_SPACE_ID}/runs",
        f"/v1/spaces/{ALT_SPACE_ID}/runs/{RUN_ID}",
    ]
    assert listed.total == 1
    assert fetched.space_id == ALT_SPACE_ID


def test_artifact_methods_cover_list_get_and_workspace(client_factory) -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path.endswith("/artifacts"):
            return httpx.Response(
                200,
                json={
                    "artifacts": [artifact_payload(content={"decision": "generated"})],
                    "total": 1,
                },
            )
        if "/workspace" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "snapshot": {"status": "completed"},
                    "created_at": "2026-03-20T10:00:00Z",
                    "updated_at": "2026-03-20T10:00:01Z",
                },
            )
        return httpx.Response(
            200,
            json=artifact_payload(
                key="graph_search_result",
                content={"decision": "generated"},
            ),
        )

    client = client_factory(handler)
    try:
        listed = client.artifacts.list(run_id=RUN_ID)
        fetched = client.artifacts.get(
            run_id=RUN_ID,
            artifact_key="graph_search_result",
        )
        workspace = client.artifacts.workspace(run_id=RUN_ID)
    finally:
        client.close()

    assert requested_paths == [
        f"/v1/spaces/{DEFAULT_SPACE_ID}/runs/{RUN_ID}/artifacts",
        f"/v1/spaces/{DEFAULT_SPACE_ID}/runs/{RUN_ID}/artifacts/graph_search_result",
        f"/v1/spaces/{DEFAULT_SPACE_ID}/runs/{RUN_ID}/workspace",
    ]
    assert listed.total == 1
    assert fetched.key == "graph_search_result"
    assert workspace.snapshot["status"] == "completed"


def test_invalid_run_id_raises_configuration_error(client_factory) -> None:
    client = client_factory(lambda request: httpx.Response(200, json={}))
    try:
        with pytest.raises(ArtanaConfigurationError):
            client.runs.get(run_id="not-a-uuid")
    finally:
        client.close()


def test_documents_submit_text_posts_expected_payload(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/spaces/{DEFAULT_SPACE_ID}/documents/text"
        assert json.loads(request.content.decode()) == {
            "title": "MED13 evidence note",
            "text": "MED13 associates with cardiomyopathy.",
            "metadata": {"origin": "sdk-test"},
        }
        return httpx.Response(
            201,
            json={
                "run": run_payload(
                    harness_id="document-ingestion",
                    title="Document Ingestion: MED13 evidence note",
                ),
                "document": _document_detail_payload(),
            },
        )

    client = client_factory(handler)
    try:
        response = client.documents.submit_text(
            title="MED13 evidence note",
            text="MED13 associates with cardiomyopathy.",
            metadata={"origin": "sdk-test"},
        )
    finally:
        client.close()

    assert response.run.harness_id == "document-ingestion"
    assert response.document.id == DOCUMENT_ID
    assert response.document.source_type == "text"


def test_documents_upload_pdf_uses_multipart_form_fields(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/spaces/{DEFAULT_SPACE_ID}/documents/pdf"
        assert request.headers["content-type"].startswith(
            "multipart/form-data; boundary=",
        )
        body = request.content.decode("latin1")
        assert 'name="title"' in body
        assert "MED13 PDF" in body
        assert 'name="metadata_json"' in body
        assert '"origin": "sdk-test"' in body
        assert 'filename="med13.pdf"' in body
        assert "application/pdf" in body
        return httpx.Response(
            201,
            json={
                "run": run_payload(
                    harness_id="document-ingestion",
                    title="Document Ingestion: MED13 PDF",
                ),
                "document": _document_detail_payload(source_type="pdf"),
            },
        )

    client = client_factory(handler)
    try:
        response = client.documents.upload_pdf(
            file_path=b"%PDF-1.4\nsynthetic\n%%EOF\n",
            filename="med13.pdf",
            title="MED13 PDF",
            metadata={"origin": "sdk-test"},
        )
    finally:
        client.close()

    assert response.document.source_type == "pdf"
    assert response.document.filename == "med13.pdf"
    assert response.document.enrichment_status == "not_started"


def test_documents_get_uses_expected_path(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert (
            request.url.path == f"/v1/spaces/{DEFAULT_SPACE_ID}/documents/{DOCUMENT_ID}"
        )
        return httpx.Response(
            200,
            json=_document_detail_payload(
                source_type="pdf",
                enrichment_status="completed",
                extraction_status="completed",
                page_count=2,
                text_excerpt="MED13 associates with cardiomyopathy.",
                text_content="MED13 associates with cardiomyopathy.",
                last_enrichment_run_id="34343434-3434-3434-3434-343434343434",
                last_extraction_run_id=RUN_ID,
            ),
        )

    client = client_factory(handler)
    try:
        response = client.documents.get(document_id=DOCUMENT_ID)
    finally:
        client.close()

    assert response.id == DOCUMENT_ID
    assert response.last_enrichment_run_id == "34343434-3434-3434-3434-343434343434"
    assert response.last_extraction_run_id == RUN_ID


def test_proposals_list_and_decision_routes_use_expected_paths(client_factory) -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(str(request.url))
        if request.method == "GET":
            assert request.url.path == f"/v1/spaces/{DEFAULT_SPACE_ID}/proposals"
            assert request.url.params["document_id"] == DOCUMENT_ID
            return httpx.Response(
                200,
                json={"proposals": [_proposal_payload()], "total": 1},
            )
        assert (
            request.url.path
            == f"/v1/spaces/{DEFAULT_SPACE_ID}/proposals/{PROPOSAL_ID}/promote"
        )
        assert json.loads(request.content.decode()) == {
            "reason": "Looks good",
            "metadata": {"reviewer": "sdk-test"},
        }
        return httpx.Response(
            200,
            json=_proposal_payload(status="promoted")
            | {"decision_reason": "Looks good"},
        )

    client = client_factory(handler)
    try:
        listed = client.proposals.list(document_id=DOCUMENT_ID)
        promoted = client.proposals.promote(
            proposal_id=PROPOSAL_ID,
            reason="Looks good",
            metadata={"reviewer": "sdk-test"},
        )
    finally:
        client.close()

    assert listed.total == 1
    assert listed.proposals[0].document_id == DOCUMENT_ID
    assert promoted.status == "promoted"
    assert promoted.decision_reason == "Looks good"
    assert len(requested_paths) == 2


def test_proposals_get_uses_expected_path(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert (
            request.url.path == f"/v1/spaces/{DEFAULT_SPACE_ID}/proposals/{PROPOSAL_ID}"
        )
        return httpx.Response(200, json=_proposal_payload())

    client = client_factory(handler)
    try:
        response = client.proposals.get(proposal_id=PROPOSAL_ID)
    finally:
        client.close()

    assert response.id == PROPOSAL_ID
    assert response.document_id == DOCUMENT_ID


def test_review_queue_routes_use_expected_paths(client_factory) -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(str(request.url))
        if request.method == "GET" and request.url.path.endswith("/review-queue"):
            assert request.url.path == f"/v1/spaces/{DEFAULT_SPACE_ID}/review-queue"
            assert request.url.params["document_id"] == DOCUMENT_ID
            assert request.url.params["item_type"] == "proposal"
            return httpx.Response(
                200,
                json={
                    "items": [_review_queue_item_payload()],
                    "total": 1,
                    "offset": 0,
                    "limit": 50,
                },
            )
        if request.method == "GET":
            assert (
                request.url.path
                == f"/v1/spaces/{DEFAULT_SPACE_ID}/review-queue/proposal:{PROPOSAL_ID}"
            )
            return httpx.Response(200, json=_review_queue_item_payload())
        assert request.method == "POST"
        assert (
            request.url.path
            == f"/v1/spaces/{DEFAULT_SPACE_ID}/review-queue/proposal:{PROPOSAL_ID}/actions"
        )
        assert json.loads(request.content.decode()) == {
            "action": "reject",
            "reason": "Need a closer review",
            "metadata": {"reviewer": "sdk-test"},
        }
        return httpx.Response(
            200,
            json=_review_queue_item_payload(status="rejected")
            | {
                "available_actions": [],
                "decision_reason": "Need a closer review",
            },
        )

    client = client_factory(handler)
    try:
        listed = client.review_queue.list(document_id=DOCUMENT_ID, item_type="proposal")
        item = client.review_queue.get(item_id=f"proposal:{PROPOSAL_ID}")
        acted = client.review_queue.act(
            item_id=f"proposal:{PROPOSAL_ID}",
            action="reject",
            reason="Need a closer review",
            metadata={"reviewer": "sdk-test"},
        )
    finally:
        client.close()

    assert listed.total == 1
    assert listed.items[0].resource_id == PROPOSAL_ID
    assert listed.items[0].available_actions == ["promote", "reject"]
    assert item.item_type == "proposal"
    assert acted.status == "rejected"
    assert acted.decision_reason == "Need a closer review"
    assert len(requested_paths) == 3


def test_chat_session_methods_use_expected_paths(client_factory) -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.method == "POST":
            assert request.url.path == f"/v1/spaces/{DEFAULT_SPACE_ID}/chat-sessions"
            assert json.loads(request.content.decode()) == {"title": "MED13 chat"}
            return httpx.Response(201, json=_chat_session_payload())
        assert request.method == "GET"
        assert (
            request.url.path
            == f"/v1/spaces/{DEFAULT_SPACE_ID}/chat-sessions/{SESSION_ID}"
        )
        return httpx.Response(
            200,
            json={
                "session": _chat_session_payload(),
                "messages": [
                    {
                        "id": "message-1",
                        "session_id": SESSION_ID,
                        "role": "user",
                        "content": "Question",
                        "run_id": RUN_ID,
                        "metadata": {},
                        "created_at": "2026-03-20T10:00:00Z",
                        "updated_at": "2026-03-20T10:00:00Z",
                    },
                ],
            },
        )

    client = client_factory(handler)
    try:
        session = client.chat.create_session(title="MED13 chat")
        detail = client.chat.get_session(session_id=SESSION_ID)
    finally:
        client.close()

    assert requested_paths == [
        f"/v1/spaces/{DEFAULT_SPACE_ID}/chat-sessions",
        f"/v1/spaces/{DEFAULT_SPACE_ID}/chat-sessions/{SESSION_ID}",
    ]
    assert session.id == SESSION_ID
    assert detail.session.id == SESSION_ID
    assert detail.messages[0].role == "user"


def test_chat_send_message_posts_document_ids_and_refresh_flag(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert (
            request.url.path
            == f"/v1/spaces/{DEFAULT_SPACE_ID}/chat-sessions/{SESSION_ID}/messages"
        )
        assert "Prefer" not in request.headers
        assert json.loads(request.content.decode()) == {
            "content": "What does this note suggest?",
            "model_id": "gpt-test",
            "max_depth": 3,
            "top_k": 12,
            "include_evidence_chains": False,
            "document_ids": [DOCUMENT_ID],
            "refresh_pubmed_if_needed": False,
        }
        return httpx.Response(
            201,
            json={
                "run": run_payload(
                    harness_id="graph-chat",
                    title="Graph chat run",
                ),
                "session": _chat_session_payload(),
                "user_message": {
                    "id": "message-user",
                    "session_id": SESSION_ID,
                    "role": "user",
                    "content": "What does this note suggest?",
                    "run_id": RUN_ID,
                    "metadata": {"document_ids": [DOCUMENT_ID]},
                    "created_at": "2026-03-20T10:00:00Z",
                    "updated_at": "2026-03-20T10:00:00Z",
                },
                "assistant_message": {
                    "id": "message-assistant",
                    "session_id": SESSION_ID,
                    "role": "assistant",
                    "content": "Grounded answer.",
                    "run_id": RUN_ID,
                    "metadata": {},
                    "created_at": "2026-03-20T10:00:01Z",
                    "updated_at": "2026-03-20T10:00:01Z",
                },
                "result": {
                    "answer_text": "Grounded answer.",
                    "chat_summary": "Synthetic summary.",
                    "evidence_bundle": [],
                    "warnings": [],
                    "verification": {
                        "status": "verified",
                        "reason": "Grounded",
                        "grounded_match_count": 1,
                        "top_relevance_score": 0.95,
                        "warning_count": 0,
                        "allows_graph_write": True,
                    },
                    "graph_write_candidates": [],
                    "fresh_literature": None,
                    "search": graph_search_response()["result"],
                },
            },
        )

    client = client_factory(handler)
    try:
        response = client.chat.send_message(
            session_id=SESSION_ID,
            content="What does this note suggest?",
            model_id="gpt-test",
            max_depth=3,
            top_k=12,
            include_evidence_chains=False,
            document_ids=[DOCUMENT_ID],
            refresh_pubmed_if_needed=False,
        )
    finally:
        client.close()

    assert response.run.harness_id == "graph-chat"
    assert response.user_message.metadata["document_ids"] == [DOCUMENT_ID]
    assert response.result.verification.status == "verified"


def test_chat_send_message_prefers_respond_async_and_parses_stream_url(
    client_factory,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert (
            request.url.path
            == f"/v1/spaces/{DEFAULT_SPACE_ID}/chat-sessions/{SESSION_ID}/messages"
        )
        assert request.headers["Prefer"] == "respond-async"
        assert json.loads(request.content.decode()) == {
            "content": "Summarize the evidence.",
            "model_id": None,
            "max_depth": 2,
            "top_k": 10,
            "include_evidence_chains": True,
            "document_ids": [],
            "refresh_pubmed_if_needed": False,
        }
        return httpx.Response(
            202,
            json={
                "run": run_payload(
                    harness_id="graph-chat",
                    title="Graph chat run",
                ),
                "session": _chat_session_payload(),
                "progress_url": f"/v1/spaces/{DEFAULT_SPACE_ID}/runs/{RUN_ID}/progress",
                "events_url": f"/v1/spaces/{DEFAULT_SPACE_ID}/runs/{RUN_ID}/events",
                "workspace_url": f"/v1/spaces/{DEFAULT_SPACE_ID}/runs/{RUN_ID}/workspace",
                "artifacts_url": f"/v1/spaces/{DEFAULT_SPACE_ID}/runs/{RUN_ID}/artifacts",
                "stream_url": (
                    f"/v1/spaces/{DEFAULT_SPACE_ID}/chat-sessions/{SESSION_ID}/messages/{RUN_ID}/stream"
                ),
            },
        )

    client = client_factory(handler)
    try:
        response = client.chat.send_message(
            session_id=SESSION_ID,
            content="Summarize the evidence.",
            refresh_pubmed_if_needed=False,
            prefer_respond_async=True,
        )
    finally:
        client.close()

    assert response.run.status == "completed"
    assert response.session.id == SESSION_ID
    assert response.stream_url.endswith(f"/messages/{RUN_ID}/stream")


def test_chat_ask_with_text_sequences_document_ingestion_extraction_and_message(
    client_factory,
) -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == f"/v1/spaces/{DEFAULT_SPACE_ID}/chat-sessions":
            return httpx.Response(
                201,
                json=_chat_session_payload() | {"last_run_id": None},
            )
        if request.url.path == f"/v1/spaces/{DEFAULT_SPACE_ID}/documents/text":
            return httpx.Response(
                201,
                json={
                    "run": run_payload(
                        harness_id="document-ingestion",
                        title="Document Ingestion: MED13 evidence note",
                    ),
                    "document": _document_detail_payload(),
                },
            )
        if (
            request.url.path
            == f"/v1/spaces/{DEFAULT_SPACE_ID}/documents/{DOCUMENT_ID}/extract"
        ):
            return httpx.Response(
                201,
                json={
                    "run": run_payload(
                        harness_id="document-extraction",
                        title="Document Extraction: MED13 evidence note",
                    ),
                    "document": _document_detail_payload(
                        extraction_status="completed",
                    )
                    | {"last_extraction_run_id": RUN_ID},
                    "proposals": [_proposal_payload()],
                    "proposal_count": 1,
                    "review_items": [_review_queue_item_payload(item_type="review_item")],
                    "review_item_count": 1,
                    "skipped_candidates": [],
                },
            )
        assert (
            request.url.path
            == f"/v1/spaces/{DEFAULT_SPACE_ID}/chat-sessions/{SESSION_ID}/messages"
        )
        return httpx.Response(
            201,
            json={
                "run": run_payload(harness_id="graph-chat", title="Graph chat run"),
                "session": _chat_session_payload(),
                "user_message": {
                    "id": "message-user",
                    "session_id": SESSION_ID,
                    "role": "user",
                    "content": "What does this note suggest?",
                    "run_id": RUN_ID,
                    "metadata": {"document_ids": [DOCUMENT_ID]},
                    "created_at": "2026-03-20T10:00:00Z",
                    "updated_at": "2026-03-20T10:00:00Z",
                },
                "assistant_message": {
                    "id": "message-assistant",
                    "session_id": SESSION_ID,
                    "role": "assistant",
                    "content": "Grounded answer.",
                    "run_id": RUN_ID,
                    "metadata": {},
                    "created_at": "2026-03-20T10:00:01Z",
                    "updated_at": "2026-03-20T10:00:01Z",
                },
                "result": {
                    "answer_text": "Grounded answer.",
                    "chat_summary": "Synthetic summary.",
                    "evidence_bundle": [],
                    "warnings": [],
                    "verification": {
                        "status": "verified",
                        "reason": "Grounded",
                        "grounded_match_count": 1,
                        "top_relevance_score": 0.95,
                        "warning_count": 0,
                        "allows_graph_write": True,
                    },
                    "graph_write_candidates": [],
                    "fresh_literature": None,
                    "search": graph_search_response()["result"],
                },
            },
        )

    client = client_factory(handler)
    try:
        response = client.chat.ask_with_text(
            question="What does this note suggest?",
            title="MED13 evidence note",
            text="MED13 associates with cardiomyopathy.",
        )
    finally:
        client.close()

    assert requested_paths == [
        f"/v1/spaces/{DEFAULT_SPACE_ID}/chat-sessions",
        f"/v1/spaces/{DEFAULT_SPACE_ID}/documents/text",
        f"/v1/spaces/{DEFAULT_SPACE_ID}/documents/{DOCUMENT_ID}/extract",
        f"/v1/spaces/{DEFAULT_SPACE_ID}/chat-sessions/{SESSION_ID}/messages",
    ]
    assert response.ingestion.document.id == DOCUMENT_ID
    assert response.extraction.proposal_count == 1
    assert response.extraction.review_item_count == 1
    assert response.extraction.review_items[0].kind == "phenotype_claim_review"
    assert response.chat.session.id == SESSION_ID


def test_chat_ask_with_pdf_sequences_document_ingestion_extraction_and_message(
    client_factory,
) -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == f"/v1/spaces/{DEFAULT_SPACE_ID}/chat-sessions":
            return httpx.Response(
                201,
                json=_chat_session_payload() | {"last_run_id": None},
            )
        if request.url.path == f"/v1/spaces/{DEFAULT_SPACE_ID}/documents/pdf":
            return httpx.Response(
                201,
                json={
                    "run": run_payload(
                        harness_id="document-ingestion",
                        title="Document Ingestion: MED13 PDF",
                    ),
                    "document": _document_detail_payload(source_type="pdf"),
                },
            )
        if (
            request.url.path
            == f"/v1/spaces/{DEFAULT_SPACE_ID}/documents/{DOCUMENT_ID}/extract"
        ):
            return httpx.Response(
                201,
                json={
                    "run": run_payload(
                        harness_id="document-extraction",
                        title="Document Extraction: MED13 PDF",
                    ),
                    "document": _document_detail_payload(
                        source_type="pdf",
                        enrichment_status="completed",
                        extraction_status="completed",
                        page_count=2,
                        text_excerpt="MED13 associates with cardiomyopathy.",
                        text_content="MED13 associates with cardiomyopathy.",
                        last_enrichment_run_id="56565656-5656-5656-5656-565656565656",
                        last_extraction_run_id=RUN_ID,
                    ),
                    "proposals": [_proposal_payload()],
                    "proposal_count": 1,
                    "review_items": [_review_queue_item_payload(item_type="review_item")],
                    "review_item_count": 1,
                    "skipped_candidates": [],
                },
            )
        assert (
            request.url.path
            == f"/v1/spaces/{DEFAULT_SPACE_ID}/chat-sessions/{SESSION_ID}/messages"
        )
        return httpx.Response(
            201,
            json={
                "run": run_payload(harness_id="graph-chat", title="Graph chat run"),
                "session": _chat_session_payload(),
                "user_message": {
                    "id": "message-user",
                    "session_id": SESSION_ID,
                    "role": "user",
                    "content": "What does this PDF suggest?",
                    "run_id": RUN_ID,
                    "metadata": {"document_ids": [DOCUMENT_ID]},
                    "created_at": "2026-03-20T10:00:00Z",
                    "updated_at": "2026-03-20T10:00:00Z",
                },
                "assistant_message": {
                    "id": "message-assistant",
                    "session_id": SESSION_ID,
                    "role": "assistant",
                    "content": "Grounded answer.",
                    "run_id": RUN_ID,
                    "metadata": {},
                    "created_at": "2026-03-20T10:00:01Z",
                    "updated_at": "2026-03-20T10:00:01Z",
                },
                "result": {
                    "answer_text": "Grounded answer.",
                    "chat_summary": "Synthetic summary.",
                    "evidence_bundle": [],
                    "warnings": [],
                    "verification": {
                        "status": "verified",
                        "reason": "Grounded",
                        "grounded_match_count": 1,
                        "top_relevance_score": 0.95,
                        "warning_count": 0,
                        "allows_graph_write": True,
                    },
                    "graph_write_candidates": [],
                    "fresh_literature": None,
                    "search": graph_search_response()["result"],
                },
            },
        )

    client = client_factory(handler)
    try:
        response = client.chat.ask_with_pdf(
            question="What does this PDF suggest?",
            title="MED13 PDF",
            filename="med13.pdf",
            file_path=b"%PDF-1.4\nsynthetic\n%%EOF\n",
        )
    finally:
        client.close()

    assert requested_paths == [
        f"/v1/spaces/{DEFAULT_SPACE_ID}/chat-sessions",
        f"/v1/spaces/{DEFAULT_SPACE_ID}/documents/pdf",
        f"/v1/spaces/{DEFAULT_SPACE_ID}/documents/{DOCUMENT_ID}/extract",
        f"/v1/spaces/{DEFAULT_SPACE_ID}/chat-sessions/{SESSION_ID}/messages",
    ]
    assert response.ingestion.document.enrichment_status == "not_started"
    assert response.extraction.document.last_enrichment_run_id == (
        "56565656-5656-5656-5656-565656565656"
    )
    assert response.extraction.review_items[0].item_type == "review_item"
    assert response.chat.session.id == SESSION_ID


def test_pubmed_search_posts_expected_payload(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/spaces/{DEFAULT_SPACE_ID}/pubmed/searches"
        assert json.loads(request.content.decode()) == {
            "parameters": {
                "gene_symbol": "MED13",
                "search_term": "MED13 cardiomyopathy",
                "date_from": None,
                "date_to": None,
                "publication_types": [],
                "languages": [],
                "sort_by": "relevance",
                "max_results": 25,
                "additional_terms": None,
            },
        }
        return httpx.Response(
            201,
            json={
                "id": JOB_ID,
                "owner_id": "user-1",
                "session_id": DEFAULT_SPACE_ID,
                "provider": "pubmed",
                "status": "completed",
                "query_preview": "MED13 cardiomyopathy",
                "parameters": {
                    "gene_symbol": "MED13",
                    "search_term": "MED13 cardiomyopathy",
                    "date_from": None,
                    "date_to": None,
                    "publication_types": [],
                    "languages": [],
                    "sort_by": "relevance",
                    "max_results": 25,
                    "additional_terms": None,
                },
                "total_results": 3,
                "result_metadata": {"preview_records": [{"pmid": "pmid-1"}]},
                "error_message": None,
                "storage_key": None,
                "created_at": "2026-03-20T10:00:00Z",
                "updated_at": "2026-03-20T10:00:01Z",
                "completed_at": "2026-03-20T10:00:02Z",
            },
        )

    client = client_factory(handler)
    try:
        response = client.pubmed.search(
            gene_symbol="MED13",
            search_term="MED13 cardiomyopathy",
            max_results=25,
        )
    finally:
        client.close()

    assert response.id == JOB_ID
    assert response.status == "completed"
    assert response.result_metadata["preview_records"][0]["pmid"] == "pmid-1"


def test_pubmed_get_job_uses_expected_path(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert (
            request.url.path
            == f"/v1/spaces/{DEFAULT_SPACE_ID}/pubmed/searches/{JOB_ID}"
        )
        return httpx.Response(
            200,
            json={
                "id": JOB_ID,
                "owner_id": "user-1",
                "session_id": DEFAULT_SPACE_ID,
                "provider": "pubmed",
                "status": "completed",
                "query_preview": "MED13 cardiomyopathy",
                "parameters": {
                    "gene_symbol": "MED13",
                    "search_term": "MED13 cardiomyopathy",
                    "date_from": None,
                    "date_to": None,
                    "publication_types": [],
                    "languages": [],
                    "sort_by": "relevance",
                    "max_results": 25,
                    "additional_terms": None,
                },
                "total_results": 3,
                "result_metadata": {"preview_records": [{"pmid": "pmid-1"}]},
                "error_message": None,
                "storage_key": None,
                "created_at": "2026-03-20T10:00:00Z",
                "updated_at": "2026-03-20T10:00:01Z",
                "completed_at": "2026-03-20T10:00:02Z",
            },
        )

    client = client_factory(handler)
    try:
        response = client.pubmed.get_job(job_id=JOB_ID)
    finally:
        client.close()

    assert response.id == JOB_ID
    assert response.query_preview == "MED13 cardiomyopathy"
