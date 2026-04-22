"""Unit tests for chat document-reference validation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Final

import artana_evidence_api.routers.chat as chat_router
from artana_evidence_api.agent_contracts import GraphSearchContract
from artana_evidence_api.app import create_app
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.chat_sessions import HarnessChatSessionStore
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_chat_session_store,
    get_document_store,
    get_graph_api_gateway,
    get_graph_snapshot_store,
    get_harness_execution_services,
    get_research_space_store,
    get_research_state_store,
    get_run_registry,
)
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.graph_chat_runtime import (
    GraphChatResult,
    GraphChatVerification,
)
from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotStore
from artana_evidence_api.queued_run_support import QueuedRunWaitOutcome
from artana_evidence_api.research_space_store import HarnessResearchSpaceStore
from artana_evidence_api.research_state import HarnessResearchStateStore
from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
from fastapi.testclient import TestClient

_TEST_USER_ID: Final[str] = "11111111-1111-1111-1111-111111111111"
_TEST_USER_EMAIL: Final[str] = "graph-harness-chat@example.com"


def _auth_headers() -> dict[str, str]:
    return {
        "X-TEST-USER-ID": _TEST_USER_ID,
        "X-TEST-USER-EMAIL": _TEST_USER_EMAIL,
        "X-TEST-USER-ROLE": "researcher",
    }


class _StubGraphHealthResponse:
    status = "ok"
    version = "chat-test"


class _StubGraphApiGateway:
    def get_health(self) -> _StubGraphHealthResponse:
        return _StubGraphHealthResponse()

    def close(self) -> None:
        return None


def test_send_chat_message_rejects_missing_document_reference() -> None:
    app = create_app()
    artifact_store = HarnessArtifactStore()
    chat_session_store = HarnessChatSessionStore()
    document_store = HarnessDocumentStore()
    graph_snapshot_store = HarnessGraphSnapshotStore()
    research_space_store = HarnessResearchSpaceStore()
    research_state_store = HarnessResearchStateStore()
    run_registry = HarnessRunRegistry()

    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Chat Space",
        description="Owned test space for chat validation.",
    )
    session = chat_session_store.create_session(
        space_id=space.id,
        title="Chat Session",
        created_by=_TEST_USER_ID,
    )

    app.dependency_overrides[get_artifact_store] = lambda: artifact_store
    app.dependency_overrides[get_chat_session_store] = lambda: chat_session_store
    app.dependency_overrides[get_document_store] = lambda: document_store
    app.dependency_overrides[get_graph_api_gateway] = lambda: _StubGraphApiGateway()
    app.dependency_overrides[get_graph_snapshot_store] = lambda: graph_snapshot_store
    app.dependency_overrides[get_harness_execution_services] = lambda: object()
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    app.dependency_overrides[get_research_state_store] = lambda: research_state_store
    app.dependency_overrides[get_run_registry] = lambda: run_registry

    with TestClient(app) as client:
        response = client.post(
            f"/v1/spaces/{space.id}/chat-sessions/{session.id}/messages",
            headers=_auth_headers(),
            json={
                "content": "What does this document say?",
                "document_ids": ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"],
                "refresh_pubmed_if_needed": False,
            },
        )

    assert response.status_code == 404
    assert "document" in response.json()["detail"].lower()


def test_send_chat_message_rejects_cross_space_document_reference() -> None:
    app = create_app()
    artifact_store = HarnessArtifactStore()
    chat_session_store = HarnessChatSessionStore()
    document_store = HarnessDocumentStore()
    graph_snapshot_store = HarnessGraphSnapshotStore()
    research_space_store = HarnessResearchSpaceStore()
    research_state_store = HarnessResearchStateStore()
    run_registry = HarnessRunRegistry()

    first_space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Chat Space",
        description="Owned test space for chat validation.",
    )
    second_space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Other Space",
        description="Second owned space for cross-space validation.",
    )
    session = chat_session_store.create_session(
        space_id=first_space.id,
        title="Chat Session",
        created_by=_TEST_USER_ID,
    )
    foreign_document = document_store.create_document(
        space_id=second_space.id,
        created_by=_TEST_USER_ID,
        title="Other document",
        source_type="text",
        filename=None,
        media_type="text/plain",
        sha256="abc123",
        byte_size=32,
        page_count=None,
        text_content="MED13 associates with cardiomyopathy.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="11111111-1111-1111-1111-111111111112",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={},
    )

    app.dependency_overrides[get_artifact_store] = lambda: artifact_store
    app.dependency_overrides[get_chat_session_store] = lambda: chat_session_store
    app.dependency_overrides[get_document_store] = lambda: document_store
    app.dependency_overrides[get_graph_api_gateway] = lambda: _StubGraphApiGateway()
    app.dependency_overrides[get_graph_snapshot_store] = lambda: graph_snapshot_store
    app.dependency_overrides[get_harness_execution_services] = lambda: object()
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    app.dependency_overrides[get_research_state_store] = lambda: research_state_store
    app.dependency_overrides[get_run_registry] = lambda: run_registry

    with TestClient(app) as client:
        response = client.post(
            f"/v1/spaces/{first_space.id}/chat-sessions/{session.id}/messages",
            headers=_auth_headers(),
            json={
                "content": "What does this document say?",
                "document_ids": [foreign_document.id],
                "refresh_pubmed_if_needed": False,
            },
        )

    assert response.status_code == 404
    assert "document" in response.json()["detail"].lower()


def test_send_chat_message_offloads_preflight_to_thread(
    monkeypatch,
) -> None:
    app = create_app()
    artifact_store = HarnessArtifactStore()
    chat_session_store = HarnessChatSessionStore()
    document_store = HarnessDocumentStore()
    graph_snapshot_store = HarnessGraphSnapshotStore()
    research_space_store = HarnessResearchSpaceStore()
    research_state_store = HarnessResearchStateStore()
    run_registry = HarnessRunRegistry()
    execution_services = SimpleNamespace(runtime=object(), execution_override=object())

    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Chat Space",
        description="Owned test space for chat threading.",
    )
    session = chat_session_store.create_session(
        space_id=space.id,
        title="Chat Session",
        created_by=_TEST_USER_ID,
    )

    to_thread_calls: list[object] = []
    queued_run: HarnessRunRecord | None = None

    async def _fake_to_thread(func, /, *args, **kwargs):  # type: ignore[no-untyped-def]
        to_thread_calls.append(func)
        result = func(*args, **kwargs)
        nonlocal queued_run
        runs = run_registry.list_runs(space_id=space.id)
        queued_run = runs[-1] if runs else None
        return result

    async def _fake_wait_for_terminal_run(
        *,
        space_id,
        run_id,
        run_registry,
        timeout_seconds,
        poll_interval_seconds,
    ):
        del space_id, run_id, run_registry, timeout_seconds, poll_interval_seconds
        assert queued_run is not None
        return QueuedRunWaitOutcome(run=queued_run, timed_out=False)

    async def _fake_maybe_execute_test_worker_run(**_kwargs):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(chat_router.asyncio, "to_thread", _fake_to_thread)
    monkeypatch.setattr(
        chat_router,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        chat_router,
        "maybe_execute_test_worker_run",
        _fake_maybe_execute_test_worker_run,
    )
    monkeypatch.setattr(
        chat_router,
        "wait_for_terminal_run",
        _fake_wait_for_terminal_run,
    )
    monkeypatch.setattr(
        chat_router,
        "load_primary_result_artifact",
        lambda **_kwargs: {
            "run": {
                "id": queued_run.id if queued_run is not None else "",
                "space_id": space.id,
                "harness_id": "graph-chat",
                "title": session.title,
                "status": "completed",
                "input_payload": {
                    "session_id": session.id,
                    "question": "What does this document say?",
                },
                "graph_service_status": "ok",
                "graph_service_version": "chat-test",
                "created_at": "2026-04-03T00:00:00+00:00",
                "updated_at": "2026-04-03T00:00:01+00:00",
            },
            "session": {
                "id": session.id,
                "space_id": space.id,
                "title": session.title,
                "created_by": _TEST_USER_ID,
                "last_run_id": queued_run.id if queued_run is not None else None,
                "status": "active",
                "created_at": "2026-04-03T00:00:00+00:00",
                "updated_at": "2026-04-03T00:00:01+00:00",
            },
            "user_message": {
                "id": "user-message",
                "session_id": session.id,
                "role": "user",
                "content": "What does this document say?",
                "run_id": queued_run.id if queued_run is not None else None,
                "metadata": {},
                "created_at": "2026-04-03T00:00:00+00:00",
                "updated_at": "2026-04-03T00:00:00+00:00",
            },
            "assistant_message": {
                "id": "assistant-message",
                "session_id": session.id,
                "role": "assistant",
                "content": "Test answer",
                "run_id": queued_run.id if queued_run is not None else None,
                "metadata": {},
                "created_at": "2026-04-03T00:00:01+00:00",
                "updated_at": "2026-04-03T00:00:01+00:00",
            },
            "result": GraphChatResult(
                answer_text="Test answer",
                chat_summary="Test summary",
                evidence_bundle=[],
                warnings=[],
                verification=GraphChatVerification(
                    status="unverified",
                    reason="Test verification.",
                    grounded_match_count=0,
                    top_relevance_score=None,
                    warning_count=0,
                    allows_graph_write=False,
                ),
                search=GraphSearchContract(
                    decision="generated",
                    confidence_score=0.0,
                    rationale="Test search result.",
                    evidence=[],
                    research_space_id=str(space.id),
                    original_query="What does this document say?",
                    interpreted_intent="What does this document say?",
                    query_plan_summary="Test plan.",
                    total_results=0,
                    results=[],
                    executed_path="agent",
                    warnings=[],
                    agent_run_id="graph_chat:test",
                ),
            ).model_dump(mode="json"),
        },
    )

    app.dependency_overrides[get_artifact_store] = lambda: artifact_store
    app.dependency_overrides[get_chat_session_store] = lambda: chat_session_store
    app.dependency_overrides[get_document_store] = lambda: document_store
    app.dependency_overrides[get_graph_api_gateway] = lambda: _StubGraphApiGateway()
    app.dependency_overrides[get_graph_snapshot_store] = lambda: graph_snapshot_store
    app.dependency_overrides[get_harness_execution_services] = (
        lambda: execution_services
    )
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    app.dependency_overrides[get_research_state_store] = lambda: research_state_store
    app.dependency_overrides[get_run_registry] = lambda: run_registry

    with TestClient(app) as client:
        response = client.post(
            f"/v1/spaces/{space.id}/chat-sessions/{session.id}/messages",
            headers=_auth_headers(),
            json={
                "content": "What does this document say?",
                "document_ids": [],
                "refresh_pubmed_if_needed": False,
            },
        )

    assert response.status_code == 201
    assert to_thread_calls
    assert to_thread_calls[0] is chat_router._prepare_chat_message_run
    body = response.json()
    assert body["result"]["answer_text"] == "Test answer"
