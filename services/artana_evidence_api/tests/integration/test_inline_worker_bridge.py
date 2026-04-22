"""Integration coverage for queue-and-wait graph chat execution."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest
from artana.models import TenantContext
from artana_evidence_api.agent_contracts import (
    EvidenceItem,
    GraphSearchContract,
    GraphSearchResultEntry,
)
from artana_evidence_api.app import create_app
from artana_evidence_api.artana_stores import (
    ArtanaBackedHarnessArtifactStore,
    ArtanaBackedHarnessRunRegistry,
)
from artana_evidence_api.chat_sessions import HarnessChatSessionStore
from artana_evidence_api.config import get_settings
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_chat_session_store,
    get_document_store,
    get_graph_api_gateway,
    get_graph_snapshot_store,
    get_harness_execution_services,
    get_proposal_store,
    get_research_space_store,
    get_research_state_store,
    get_run_registry,
)
from artana_evidence_api.graph_chat_runtime import (
    GraphChatResult,
    GraphChatVerification,
)
from artana_evidence_api.harness_runtime import (
    HarnessExecutionResult,
    HarnessExecutionServices,
)
from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
from artana_evidence_api.sqlalchemy_stores import (
    SqlAlchemyHarnessApprovalStore,
    SqlAlchemyHarnessChatSessionStore,
    SqlAlchemyHarnessDocumentStore,
    SqlAlchemyHarnessGraphSnapshotStore,
    SqlAlchemyHarnessProposalStore,
    SqlAlchemyHarnessResearchStateStore,
    SqlAlchemyHarnessScheduleStore,
)
from artana_evidence_api.tests.support import (
    FakeKernelRuntime,
    PermissiveHarnessResearchSpaceStore,
    auth_headers,
)
from artana_evidence_api.worker import _default_execute_run
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

_TEST_USER_ID = "11111111-1111-1111-1111-111111111111"

pytestmark = pytest.mark.integration


@contextmanager
def _fake_pubmed_discovery_context() -> Iterator[object]:
    yield object()


@dataclass
class _ObservedGraphChatRunner:
    """Graph-chat runner stub used to verify queue-and-wait persistence."""

    space_id: UUID
    session_id: UUID
    chat_session_store: HarnessChatSessionStore
    invocation_count: int = 0
    messages_seen_by_runner: tuple[str, ...] = ()

    async def run(self, request: object) -> GraphChatResult:
        del request
        self.invocation_count += 1
        messages = self.chat_session_store.list_messages(
            space_id=self.space_id,
            session_id=self.session_id,
        )
        self.messages_seen_by_runner = tuple(message.role for message in messages)
        assert self.messages_seen_by_runner == ("user",)

        search = GraphSearchContract(
            decision="generated",
            confidence_score=0.97,
            rationale="Synthetic grounded search result for queue-and-wait coverage.",
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator="queue-wait:test",
                    excerpt="Synthetic graph-chat evidence.",
                    relevance=0.97,
                ),
            ],
            research_space_id=str(self.space_id),
            original_query="What does the document say?",
            interpreted_intent="What does the document say?",
            query_plan_summary="Synthetic graph-chat plan.",
            total_results=1,
            results=[
                GraphSearchResultEntry(
                    entity_id="entity-1",
                    entity_type="GENE",
                    display_label="MED13",
                    relevance_score=0.97,
                    matching_observation_ids=["observation-1"],
                    matching_relation_ids=[],
                    evidence_chain=[],
                    explanation="Synthetic graph-chat explanation.",
                    support_summary="Synthetic graph-chat support.",
                ),
            ],
            executed_path="agent",
            warnings=[],
            agent_run_id="graph_chat:queue-wait",
        )
        return GraphChatResult(
            answer_text="Grounded graph answer: MED13 is supported.",
            chat_summary="Synthetic queue-and-wait result.",
            evidence_bundle=[],
            warnings=[],
            verification=GraphChatVerification(
                status="verified",
                reason="Synthetic verification.",
                grounded_match_count=1,
                top_relevance_score=0.97,
                warning_count=0,
                allows_graph_write=True,
            ),
            search=search,
        ).with_active_skill_names(("graph_harness.graph_chat",))


class _KernelRuntimeWithAdapter(FakeKernelRuntime):
    """Fake Artana runtime that exposes the kernel interface used by harnesses."""

    def __init__(self) -> None:
        super().__init__()
        self.kernel = _KernelAdapter(self)

    def tenant_context(self, *, tenant_id: str) -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            capabilities=frozenset(),
            budget_usd_limit=10.0,
        )


class _KernelAdapter:
    """Async Artana kernel facade over the in-memory fake runtime."""

    def __init__(self, runtime: _KernelRuntimeWithAdapter) -> None:
        self._runtime = runtime

    async def load_run(self, *, run_id: str, tenant: TenantContext) -> None:
        if (tenant.tenant_id, run_id) not in self._runtime._runs:
            raise ValueError("run not found")

    async def start_run(self, *, tenant: TenantContext, run_id: str) -> None:
        self._runtime.ensure_run(run_id=run_id, tenant_id=tenant.tenant_id)

    async def append_harness_event(self, **_: object) -> None:
        return None

    def list_tools(
        self,
        *,
        tenant_capabilities: frozenset[str],
        visible_tool_names: set[str] | None = None,
    ) -> tuple[object, ...]:
        _ = tenant_capabilities, visible_tool_names
        return ()

    async def step_model(self, **_: object) -> object:
        return SimpleNamespace(
            output=SimpleNamespace(model_dump_json=lambda: "{}"),
        )

    async def step_tool(self, **kwargs: object) -> object:
        return self._runtime.step_tool(
            run_id=cast("str", kwargs["run_id"]),
            tenant_id=cast("TenantContext", kwargs["tenant"]).tenant_id,
            tool_name=cast("str", kwargs["tool_name"]),
            arguments=cast("object", kwargs["arguments"]),
            step_key=cast("str", kwargs["step_key"]),
            parent_step_key=cast("str | None", kwargs.get("parent_step_key")),
        )

    async def get_events(
        self,
        *,
        run_id: str,
        tenant: TenantContext,
    ) -> tuple[object, ...]:
        return self._runtime.get_events(run_id=run_id, tenant_id=tenant.tenant_id)

    async def append_run_summary(
        self,
        *,
        run_id: str,
        tenant: TenantContext,
        summary_type: str,
        summary_json: str,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> int:
        return self._runtime.append_run_summary(
            run_id=run_id,
            tenant_id=tenant.tenant_id,
            summary_type=summary_type,
            summary_json=summary_json,
            step_key=step_key,
            parent_step_key=parent_step_key,
        )

    async def get_latest_run_summary(
        self,
        *,
        run_id: str,
        tenant: TenantContext,
        summary_type: str,
    ) -> object | None:
        return self._runtime.get_latest_run_summary(
            run_id=run_id,
            tenant_id=tenant.tenant_id,
            summary_type=summary_type,
        )


@dataclass(slots=True)
class _ChatHarnessFixture:
    artifact_store: ArtanaBackedHarnessArtifactStore
    chat_session_store: SqlAlchemyHarnessChatSessionStore
    execution_services: HarnessExecutionServices
    research_space_store: PermissiveHarnessResearchSpaceStore
    run_registry: ArtanaBackedHarnessRunRegistry


def _build_chat_harness_fixture(
    *,
    db_session: Session,
    runner: object,
    execution_override: Callable[
        [HarnessRunRecord, HarnessExecutionServices],
        Awaitable[HarnessExecutionResult],
    ],
) -> _ChatHarnessFixture:
    runtime = _KernelRuntimeWithAdapter()
    artifact_store = ArtanaBackedHarnessArtifactStore(
        runtime=cast("object", runtime),
    )
    run_registry = ArtanaBackedHarnessRunRegistry(
        session=db_session,
        runtime=cast("object", runtime),
    )
    chat_session_store = SqlAlchemyHarnessChatSessionStore(db_session)
    execution_services = HarnessExecutionServices(
        runtime=cast("object", runtime),
        run_registry=cast("HarnessRunRegistry", run_registry),
        artifact_store=artifact_store,
        chat_session_store=chat_session_store,
        document_store=SqlAlchemyHarnessDocumentStore(db_session),
        proposal_store=SqlAlchemyHarnessProposalStore(db_session),
        approval_store=SqlAlchemyHarnessApprovalStore(db_session),
        research_state_store=SqlAlchemyHarnessResearchStateStore(db_session),
        graph_snapshot_store=SqlAlchemyHarnessGraphSnapshotStore(db_session),
        schedule_store=SqlAlchemyHarnessScheduleStore(db_session),
        graph_connection_runner=cast("object", object()),
        graph_chat_runner=cast("object", runner),
        graph_api_gateway_factory=lambda: _StubGraphApiGateway(),
        pubmed_discovery_service_factory=_fake_pubmed_discovery_context,
        execution_override=execution_override,
    )
    return _ChatHarnessFixture(
        artifact_store=artifact_store,
        chat_session_store=chat_session_store,
        execution_services=execution_services,
        research_space_store=PermissiveHarnessResearchSpaceStore(),
        run_registry=run_registry,
    )


def _build_chat_app(fixture: _ChatHarnessFixture):
    app = create_app()
    app.dependency_overrides[get_artifact_store] = lambda: fixture.artifact_store
    app.dependency_overrides[get_chat_session_store] = (
        lambda: fixture.chat_session_store
    )
    app.dependency_overrides[get_document_store] = (
        lambda: fixture.execution_services.document_store
    )
    app.dependency_overrides[get_graph_api_gateway] = lambda: _StubGraphApiGateway()
    app.dependency_overrides[get_graph_snapshot_store] = (
        lambda: fixture.execution_services.graph_snapshot_store
    )
    app.dependency_overrides[get_harness_execution_services] = (
        lambda: fixture.execution_services
    )
    app.dependency_overrides[get_proposal_store] = (
        lambda: fixture.execution_services.proposal_store
    )
    app.dependency_overrides[get_research_space_store] = (
        lambda: fixture.research_space_store
    )
    app.dependency_overrides[get_research_state_store] = (
        lambda: fixture.execution_services.research_state_store
    )
    app.dependency_overrides[get_run_registry] = lambda: fixture.run_registry
    return app


async def _leave_chat_running(
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> HarnessExecutionResult:
    services.run_registry.set_run_status(
        space_id=run.space_id,
        run_id=run.id,
        status="running",
    )
    services.run_registry.set_progress(
        space_id=run.space_id,
        run_id=run.id,
        phase="execute",
        message="Run intentionally left active for queue timeout coverage.",
        progress_percent=0.5,
        completed_steps=1,
        total_steps=2,
        metadata={"executor": "integration-test", "mode": "leave_running"},
    )
    services.artifact_store.patch_workspace(
        space_id=run.space_id,
        run_id=run.id,
        patch={"status": "running"},
    )
    updated_run = services.run_registry.get_run(space_id=run.space_id, run_id=run.id)
    return updated_run or run


def test_chat_message_queue_wait_returns_completed_response_and_primary_artifact(
    db_session: Session,
) -> None:
    fixture_space_store = PermissiveHarnessResearchSpaceStore()
    space = fixture_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Queue wait space",
        description="Integration space for queue-and-wait graph chat coverage.",
    )

    runner = _ObservedGraphChatRunner(
        space_id=UUID(space.id),
        session_id=UUID(int=0),
        chat_session_store=SqlAlchemyHarnessChatSessionStore(db_session),
    )
    fixture = _build_chat_harness_fixture(
        db_session=db_session,
        runner=runner,
        execution_override=_default_execute_run,
    )
    fixture.research_space_store = fixture_space_store
    session = fixture.chat_session_store.create_session(
        space_id=space.id,
        title="Queue wait session",
        created_by=_TEST_USER_ID,
    )
    runner.session_id = UUID(session.id)
    runner.chat_session_store = fixture.chat_session_store
    app = _build_chat_app(fixture)

    with TestClient(app) as client:
        response = client.post(
            f"/v1/spaces/{space.id}/chat-sessions/{session.id}/messages",
            headers=auth_headers(),
            json={
                "content": "Summarize the grounded evidence in this space.",
                "include_evidence_chains": True,
                "refresh_pubmed_if_needed": False,
            },
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["run"]["harness_id"] == "graph-chat"
    assert payload["run"]["status"] == "completed"
    assert payload["result"]["verification"]["status"] == "verified"
    assert (
        payload["result"]["answer_text"] == "Grounded graph answer: MED13 is supported."
    )
    assert runner.invocation_count == 1
    assert runner.messages_seen_by_runner == ("user",)

    run_id = payload["run"]["id"]
    updated_session = fixture.chat_session_store.get_session(
        space_id=space.id,
        session_id=session.id,
    )
    assert updated_session is not None
    assert updated_session.last_run_id == run_id
    assert updated_session.status == "active"

    messages = fixture.chat_session_store.list_messages(
        space_id=space.id,
        session_id=session.id,
    )
    assert [message.role for message in messages] == ["user", "assistant"]

    workspace = fixture.artifact_store.get_workspace(space_id=space.id, run_id=run_id)
    assert workspace is not None
    assert workspace.snapshot["status"] == "completed"
    assert workspace.snapshot["primary_result_key"] == "chat_run_response"
    assert "chat_run_response" in workspace.snapshot["result_keys"]

    primary_result = fixture.artifact_store.get_artifact(
        space_id=space.id,
        run_id=run_id,
        artifact_key="chat_run_response",
    )
    assert primary_result is not None
    assert primary_result.content["result"]["answer_text"] == (
        "Grounded graph answer: MED13 is supported."
    )


def test_chat_message_queue_wait_returns_accepted_run_when_sync_wait_budget_expires(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTANA_EVIDENCE_API_SYNC_WAIT_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setenv("ARTANA_EVIDENCE_API_SYNC_WAIT_POLL_SECONDS", "0.01")
    get_settings.cache_clear()
    try:
        fixture_space_store = PermissiveHarnessResearchSpaceStore()
        space = fixture_space_store.create_space(
            owner_id=_TEST_USER_ID,
            name="Queue wait timeout space",
            description="Integration space for queue-and-wait timeout coverage.",
        )
        runner = _ObservedGraphChatRunner(
            space_id=UUID(space.id),
            session_id=UUID(int=0),
            chat_session_store=SqlAlchemyHarnessChatSessionStore(db_session),
        )
        fixture = _build_chat_harness_fixture(
            db_session=db_session,
            runner=runner,
            execution_override=_leave_chat_running,
        )
        fixture.research_space_store = fixture_space_store
        session = fixture.chat_session_store.create_session(
            space_id=space.id,
            title="Queue wait timeout session",
            created_by=_TEST_USER_ID,
        )
        runner.session_id = UUID(session.id)
        runner.chat_session_store = fixture.chat_session_store
        app = _build_chat_app(fixture)

        with TestClient(app) as client:
            response = client.post(
                f"/v1/spaces/{space.id}/chat-sessions/{session.id}/messages",
                headers=auth_headers(),
                json={
                    "content": "Leave this run active.",
                    "include_evidence_chains": False,
                    "refresh_pubmed_if_needed": False,
                },
            )

        assert response.status_code == 202
        payload = response.json()
        run_id = payload["run"]["id"]
        assert payload["progress_url"].endswith(f"/runs/{run_id}/progress")
        assert payload["events_url"].endswith(f"/runs/{run_id}/events")
        assert payload["workspace_url"].endswith(f"/runs/{run_id}/workspace")
        assert payload["artifacts_url"].endswith(f"/runs/{run_id}/artifacts")
        assert payload["session"]["id"] == session.id

        running_run = fixture.run_registry.get_run(space_id=space.id, run_id=run_id)
        assert running_run is not None
        assert running_run.status == "running"

        workspace = fixture.artifact_store.get_workspace(
            space_id=space.id,
            run_id=run_id,
        )
        assert workspace is not None
        assert workspace.snapshot["status"] == "running"
    finally:
        get_settings.cache_clear()


def test_chat_message_prefers_respond_async_and_returns_stream_url(
    db_session: Session,
) -> None:
    fixture_space_store = PermissiveHarnessResearchSpaceStore()
    space = fixture_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Async chat space",
        description="Integration space for respond-async chat coverage.",
    )

    runner = _ObservedGraphChatRunner(
        space_id=UUID(space.id),
        session_id=UUID(int=0),
        chat_session_store=SqlAlchemyHarnessChatSessionStore(db_session),
    )
    fixture = _build_chat_harness_fixture(
        db_session=db_session,
        runner=runner,
        execution_override=_default_execute_run,
    )
    fixture.research_space_store = fixture_space_store
    session = fixture.chat_session_store.create_session(
        space_id=space.id,
        title="Async chat session",
        created_by=_TEST_USER_ID,
    )
    runner.session_id = UUID(session.id)
    runner.chat_session_store = fixture.chat_session_store
    app = _build_chat_app(fixture)

    with TestClient(app) as client:
        response = client.post(
            f"/v1/spaces/{space.id}/chat-sessions/{session.id}/messages",
            headers={**auth_headers(), "Prefer": "respond-async"},
            json={
                "content": "Summarize the grounded evidence in this space.",
                "include_evidence_chains": True,
                "refresh_pubmed_if_needed": False,
            },
        )

    assert response.status_code == 202
    payload = response.json()
    run_id = payload["run"]["id"]
    assert payload["run"]["status"] == "queued"
    assert payload["session"]["id"] == session.id
    assert payload["session"]["last_run_id"] == run_id
    assert payload["session"]["status"] == "queued"
    assert payload["stream_url"].endswith(
        f"/chat-sessions/{session.id}/messages/{run_id}/stream",
    )
    assert response.headers["Preference-Applied"] == "respond-async"


def test_chat_message_stream_emits_durable_sse_events(
    db_session: Session,
) -> None:
    fixture_space_store = PermissiveHarnessResearchSpaceStore()
    space = fixture_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Chat stream space",
        description="Integration space for durable chat stream coverage.",
    )

    runner = _ObservedGraphChatRunner(
        space_id=UUID(space.id),
        session_id=UUID(int=0),
        chat_session_store=SqlAlchemyHarnessChatSessionStore(db_session),
    )
    fixture = _build_chat_harness_fixture(
        db_session=db_session,
        runner=runner,
        execution_override=_default_execute_run,
    )
    fixture.research_space_store = fixture_space_store
    session = fixture.chat_session_store.create_session(
        space_id=space.id,
        title="Chat stream session",
        created_by=_TEST_USER_ID,
    )
    runner.session_id = UUID(session.id)
    runner.chat_session_store = fixture.chat_session_store
    app = _build_chat_app(fixture)

    with TestClient(app) as client:
        response = client.post(
            f"/v1/spaces/{space.id}/chat-sessions/{session.id}/messages",
            headers=auth_headers(),
            json={
                "content": "Summarize the grounded evidence in this space.",
                "include_evidence_chains": True,
                "refresh_pubmed_if_needed": False,
            },
        )

        assert response.status_code == 201
        run_id = response.json()["run"]["id"]
        stream_url = (
            f"/v1/spaces/{space.id}/chat-sessions/{session.id}/messages/{run_id}/stream"
        )

        stream_response = client.get(
            stream_url,
            headers={
                **auth_headers(),
                "Accept": "text/event-stream",
            },
        )

    assert stream_response.status_code == 200
    assert stream_response.headers["content-type"].startswith("text/event-stream")
    body = stream_response.text
    assert "event: run.snapshot" in body
    assert "event: run.created" in body
    assert "event: chat.result" in body
    assert "event: run.completed" in body
    assert "event: stream.complete" in body
    assert "Grounded graph answer: MED13 is supported." in body


class _StubGraphApiGateway:
    def get_health(self) -> object:
        return type("Health", (), {"status": "ok", "version": "queue-wait"})()

    def close(self) -> None:
        return None
