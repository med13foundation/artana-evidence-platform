"""Unit tests for harness research onboarding endpoints."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Final, cast
from uuid import UUID

import jwt
from artana_evidence_api.agent_contracts import (
    EvidenceItem,
    OnboardingArtifact,
    OnboardingAssistantContract,
    OnboardingQuestion,
    OnboardingSection,
    OnboardingStatePatch,
    OnboardingSuggestedAction,
    OnboardingSuggestedAnswer,
)
from artana_evidence_api.app import create_app
from artana_evidence_api.approval_store import HarnessApprovalStore
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.chat_sessions import HarnessChatSessionStore
from artana_evidence_api.composition import GraphHarnessKernelRuntime
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_graph_api_gateway,
    get_harness_execution_services,
    get_research_onboarding_runner,
    get_research_space_store,
    get_research_state_store,
    get_run_registry,
)
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.graph_chat_runtime import HarnessGraphChatRunner
from artana_evidence_api.graph_client import GraphTransportBundle
from artana_evidence_api.graph_connection_runtime import HarnessGraphConnectionRunner
from artana_evidence_api.graph_search_runtime import HarnessGraphSearchRunner
from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotStore
from artana_evidence_api.harness_runtime import (
    HarnessExecutionResult,
    HarnessExecutionServices,
)
from artana_evidence_api.proposal_store import HarnessProposalStore
from artana_evidence_api.pubmed_discovery import PubMedDiscoveryService
from artana_evidence_api.research_onboarding_agent_runtime import (
    HarnessResearchOnboardingContinuationRequest,
    HarnessResearchOnboardingInitialRequest,
    HarnessResearchOnboardingResult,
    HarnessResearchOnboardingRunner,
    OnboardingAgentExecutionError,
)
from artana_evidence_api.research_onboarding_runtime import (
    ResearchOnboardingContinuationRequest,
    execute_research_onboarding_continuation,
    execute_research_onboarding_run,
)
from artana_evidence_api.research_space_store import HarnessResearchSpaceStore
from artana_evidence_api.research_state import HarnessResearchStateStore
from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
from artana_evidence_api.schedule_store import HarnessScheduleStore
from artana_evidence_api.tests.support import FakeKernelRuntime
from fastapi.testclient import TestClient

_TEST_USER_ID: Final[str] = "11111111-1111-1111-1111-111111111111"
_TEST_USER_EMAIL: Final[str] = "graph-harness-test@example.com"
_AUTH_TEST_SECRET: Final[str] = os.environ["AUTH_JWT_SECRET"]


@dataclass(frozen=True)
class _StubGraphHealthResponse:
    status: str
    version: str


class _StubGraphApiGateway:
    def get_health(self) -> _StubGraphHealthResponse:
        return _StubGraphHealthResponse(status="ok", version="test")

    def close(self) -> None:
        return None


def _question_id(prompt: str) -> str:
    return prompt.lower().replace(" ", "_")[:64] or "question"


def _suggested_answers(prompt: str) -> list[OnboardingSuggestedAnswer]:
    base_id = _question_id(prompt)[:56]
    return [
        OnboardingSuggestedAnswer(
            id=f"{base_id}_gene",
            label="MED13 the gene",
        ),
        OnboardingSuggestedAnswer(
            id=f"{base_id}_cohort",
            label="Build a disease cohort",
        ),
    ]


class _StubResearchOnboardingRunner:
    async def run_initial(
        self,
        request: HarnessResearchOnboardingInitialRequest,
    ) -> HarnessResearchOnboardingResult:
        pending_questions = [
            f"What would count as a useful first deliverable for {request.research_title}?",
            "Which evidence types should the system prioritize first?",
            "Which connected or future sources should be treated as authoritative?",
        ]
        contract = OnboardingAssistantContract(
            message_type="clarification_request",
            title=f"{request.research_title}: clarify the starting constraints",
            summary="Need a small set of clarifications before starting the workflow.",
            sections=[
                OnboardingSection(
                    heading="What I understand so far",
                    body=request.primary_objective or "No explicit objective yet.",
                ),
            ],
            questions=[
                OnboardingQuestion(
                    id=_question_id(prompt),
                    prompt=prompt,
                    suggested_answers=_suggested_answers(prompt),
                )
                for prompt in pending_questions
            ],
            suggested_actions=[
                OnboardingSuggestedAction(
                    id="answer-question",
                    label="Answer questions",
                    action_type="reply",
                ),
            ],
            artifacts=[
                OnboardingArtifact(
                    artifact_key="research_onboarding_intake",
                    label="Onboarding intake",
                    kind="intake",
                ),
            ],
            state_patch=OnboardingStatePatch(
                thread_status="your_turn",
                onboarding_status="awaiting_researcher_reply",
                pending_question_count=len(pending_questions),
                objective=request.primary_objective or None,
                explored_questions=[],
                pending_questions=pending_questions,
                current_hypotheses=[],
            ),
            confidence_score=0.82,
            rationale="Initial onboarding should ask the minimum next questions.",
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator="research_onboarding_intake",
                    excerpt=request.primary_objective or request.research_title,
                    relevance=0.95,
                ),
            ],
            agent_run_id="onboarding-agent:initial",
        )
        return HarnessResearchOnboardingResult(
            contract=contract,
            agent_run_id="onboarding-agent:initial",
            active_skill_names=(),
        )

    async def run_continuation(
        self,
        request: HarnessResearchOnboardingContinuationRequest,
    ) -> HarnessResearchOnboardingResult:
        if request.mode == "request_revision":
            prompt = "What specifically should change in the plan or recommendation?"
            contract = OnboardingAssistantContract(
                message_type="clarification_request",
                title="I can revise the direction, but I need the change framed more tightly.",
                summary="Need one sharper constraint before revising the plan.",
                sections=[
                    OnboardingSection(
                        heading="Revision signal received",
                        body=request.reply_text,
                    ),
                ],
                questions=[
                    OnboardingQuestion(
                        id=_question_id(prompt),
                        prompt=prompt,
                        suggested_answers=_suggested_answers(prompt),
                    ),
                ],
                suggested_actions=[
                    OnboardingSuggestedAction(
                        id="request-revision",
                        label="Clarify revision",
                        action_type="reply",
                    ),
                ],
                artifacts=[],
                state_patch=OnboardingStatePatch(
                    thread_status="your_turn",
                    onboarding_status="awaiting_researcher_reply",
                    pending_question_count=1,
                    objective=request.objective,
                    explored_questions=list(request.explored_questions),
                    pending_questions=[prompt],
                    current_hypotheses=[],
                ),
                confidence_score=0.8,
                rationale="Revision requests should be narrowed before replanning.",
                evidence=[
                    EvidenceItem(
                        source_type="note",
                        locator="latest_reply",
                        excerpt=request.reply_text,
                        relevance=0.9,
                    ),
                ],
                agent_run_id="onboarding-agent:revision",
            )
            return HarnessResearchOnboardingResult(
                contract=contract,
                agent_run_id="onboarding-agent:revision",
                active_skill_names=(),
            )

        explored_questions = list(request.explored_questions)
        pending_questions = list(request.pending_questions)
        if pending_questions:
            explored_questions.append(pending_questions.pop(0))
        if pending_questions:
            next_prompt = pending_questions[0]
            contract = OnboardingAssistantContract(
                message_type="clarification_request",
                title="I have your latest answer. One more clarification before I plan.",
                summary="Need one remaining decision before activating the plan.",
                sections=[
                    OnboardingSection(
                        heading="Latest researcher reply",
                        body=request.reply_text,
                    ),
                ],
                questions=[
                    OnboardingQuestion(
                        id=_question_id(next_prompt),
                        prompt=next_prompt,
                        suggested_answers=_suggested_answers(next_prompt),
                    ),
                ],
                suggested_actions=[
                    OnboardingSuggestedAction(
                        id="answer-question",
                        label="Answer next question",
                        action_type="reply",
                    ),
                ],
                artifacts=[],
                state_patch=OnboardingStatePatch(
                    thread_status="your_turn",
                    onboarding_status="awaiting_researcher_reply",
                    pending_question_count=len(pending_questions),
                    objective=request.objective,
                    explored_questions=explored_questions,
                    pending_questions=pending_questions,
                    current_hypotheses=[],
                ),
                confidence_score=0.84,
                rationale="Still missing at least one explicit constraint.",
                evidence=[
                    EvidenceItem(
                        source_type="note",
                        locator="latest_reply",
                        excerpt=request.reply_text,
                        relevance=0.93,
                    ),
                ],
                agent_run_id="onboarding-agent:continuation",
            )
            return HarnessResearchOnboardingResult(
                contract=contract,
                agent_run_id="onboarding-agent:continuation",
                active_skill_names=(),
            )

        contract = OnboardingAssistantContract(
            message_type="plan_ready",
            title=f"{request.research_title}: initial plan is ready for review",
            summary="Enough onboarding context is now available for a first plan.",
            sections=[
                OnboardingSection(
                    heading="What I captured",
                    body=request.reply_text,
                ),
            ],
            questions=[],
            suggested_actions=[
                OnboardingSuggestedAction(
                    id="approve-plan",
                    label="Review plan",
                    action_type="review",
                ),
            ],
            artifacts=[
                OnboardingArtifact(
                    artifact_key="onboarding_plan_outline",
                    label="Initial plan outline",
                    kind="plan",
                ),
            ],
            state_patch=OnboardingStatePatch(
                thread_status="review_needed",
                onboarding_status="plan_ready",
                pending_question_count=0,
                objective=request.objective,
                explored_questions=explored_questions,
                pending_questions=[],
                current_hypotheses=[],
            ),
            confidence_score=0.87,
            rationale="The minimum onboarding constraints are now explicit.",
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator="latest_reply",
                    excerpt=request.reply_text,
                    relevance=0.92,
                ),
            ],
            agent_run_id="onboarding-agent:plan-ready",
        )
        return HarnessResearchOnboardingResult(
            contract=contract,
            agent_run_id="onboarding-agent:plan-ready",
            active_skill_names=(),
        )


class _FailingInitialResearchOnboardingRunner(_StubResearchOnboardingRunner):
    async def run_initial(
        self,
        request: HarnessResearchOnboardingInitialRequest,
    ) -> HarnessResearchOnboardingResult:
        del request
        raise OnboardingAgentExecutionError(
            "Synthetic onboarding agent initial failure.",
        )


class _FailingContinuationResearchOnboardingRunner(_StubResearchOnboardingRunner):
    async def run_continuation(
        self,
        request: HarnessResearchOnboardingContinuationRequest,
    ) -> HarnessResearchOnboardingResult:
        del request
        raise OnboardingAgentExecutionError(
            "Synthetic onboarding continuation failure.",
        )


@dataclass(frozen=True)
class _OnboardingTestBundle:
    client: TestClient
    run_registry: HarnessRunRegistry
    artifact_store: HarnessArtifactStore
    research_state_store: HarnessResearchStateStore


def _auth_headers(*, role: str = "researcher") -> dict[str, str]:
    return {
        "X-TEST-USER-ID": _TEST_USER_ID,
        "X-TEST-USER-EMAIL": _TEST_USER_EMAIL,
        "X-TEST-USER-ROLE": role,
    }


def _jwt_auth_headers(
    *,
    user_id: str,
    email: str,
    username: str,
    full_name: str,
    role: str,
    status: str = "active",
) -> dict[str, str]:
    token = jwt.encode(
        {
            "iss": "artana-platform",
            "sub": user_id,
            "type": "access",
            "role": role,
            "status": status,
            "email": email,
            "username": username,
            "full_name": full_name,
        },
        _AUTH_TEST_SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


class _UnusedGraphConnectionRunner:
    async def run(self, request: object) -> object:
        del request
        raise AssertionError("Graph connection runner is not used in onboarding tests.")


class _UnusedGraphChatRunner:
    async def run(self, request: object) -> object:
        del request
        raise AssertionError("Graph chat runner is not used in onboarding tests.")


@contextmanager
def _fake_pubmed_discovery_context() -> Iterator[PubMedDiscoveryService]:
    yield cast("PubMedDiscoveryService", object())


async def _execute_test_onboarding_run(
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> HarnessExecutionResult:
    payload = run.input_payload
    if isinstance(payload.get("reply_text"), str):
        return await asyncio.to_thread(
            execute_research_onboarding_continuation,
            space_id=UUID(run.space_id),
            research_title="",
            request=ResearchOnboardingContinuationRequest(
                thread_id=str(payload.get("thread_id", "")),
                message_id=str(payload.get("message_id", "")),
                intent=str(payload.get("intent", "")),
                mode=str(payload.get("mode", "")),
                reply_text=str(payload.get("reply_text", "")),
                reply_html=str(payload.get("reply_html", "")),
                attachments=(
                    list(payload.get("attachments"))
                    if isinstance(payload.get("attachments"), list)
                    else []
                ),
                contextual_anchor=(
                    payload.get("contextual_anchor")
                    if isinstance(payload.get("contextual_anchor"), dict)
                    else None
                ),
            ),
            run_registry=services.run_registry,
            artifact_store=services.artifact_store,
            graph_api_gateway=services.graph_api_gateway_factory(),
            research_state_store=services.research_state_store,
            onboarding_runner=services.research_onboarding_runner,
            existing_run=run,
        )
    return await asyncio.to_thread(
        execute_research_onboarding_run,
        space_id=UUID(run.space_id),
        research_title=str(payload.get("research_title", "")),
        primary_objective=str(payload.get("primary_objective", "")),
        space_description=str(payload.get("space_description", "")),
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        graph_api_gateway=services.graph_api_gateway_factory(),
        research_state_store=services.research_state_store,
        onboarding_runner=services.research_onboarding_runner,
        existing_run=run,
    )


def _build_client_bundle(
    research_space_store: HarnessResearchSpaceStore,
    *,
    graph_api_gateway_dependency: object = _StubGraphApiGateway,
    onboarding_runner_dependency: object = _StubResearchOnboardingRunner,
) -> _OnboardingTestBundle:
    app = create_app()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    research_state_store = HarnessResearchStateStore()
    runtime = FakeKernelRuntime()
    onboarding_runner = (
        onboarding_runner_dependency()
        if callable(onboarding_runner_dependency)
        else onboarding_runner_dependency
    )
    app.dependency_overrides[get_run_registry] = lambda: run_registry
    app.dependency_overrides[get_artifact_store] = lambda: artifact_store
    app.dependency_overrides[get_graph_api_gateway] = graph_api_gateway_dependency
    app.dependency_overrides[get_harness_execution_services] = (
        lambda: HarnessExecutionServices(
            runtime=cast("GraphHarnessKernelRuntime", runtime),
            run_registry=run_registry,
            artifact_store=artifact_store,
            chat_session_store=HarnessChatSessionStore(),
            document_store=HarnessDocumentStore(),
            proposal_store=HarnessProposalStore(),
            approval_store=HarnessApprovalStore(),
            research_state_store=research_state_store,
            graph_snapshot_store=HarnessGraphSnapshotStore(),
            schedule_store=HarnessScheduleStore(),
            graph_connection_runner=cast(
                "HarnessGraphConnectionRunner",
                _UnusedGraphConnectionRunner(),
            ),
            graph_chat_runner=cast(
                "HarnessGraphChatRunner",
                _UnusedGraphChatRunner(),
            ),
            graph_search_runner=HarnessGraphSearchRunner(),
            graph_api_gateway_factory=cast(
                "Callable[[], GraphTransportBundle]",
                graph_api_gateway_dependency,
            ),
            pubmed_discovery_service_factory=_fake_pubmed_discovery_context,
            research_onboarding_runner=cast(
                "HarnessResearchOnboardingRunner",
                onboarding_runner,
            ),
            execution_override=_execute_test_onboarding_run,
        )
    )
    app.dependency_overrides[get_research_onboarding_runner] = lambda: onboarding_runner
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    app.dependency_overrides[get_research_state_store] = lambda: research_state_store
    return _OnboardingTestBundle(
        client=TestClient(app),
        run_registry=run_registry,
        artifact_store=artifact_store,
        research_state_store=research_state_store,
    )


def _build_client_with_space_store(
    research_space_store: HarnessResearchSpaceStore,
) -> TestClient:
    return _build_client_bundle(research_space_store).client


def test_create_research_onboarding_run_returns_structured_assistant_message() -> None:
    research_space_store = HarnessResearchSpaceStore()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Onboarding Space",
        description="Research onboarding test space.",
    )
    client = _build_client_with_space_store(research_space_store)

    response = client.post(
        f"/v1/spaces/{space.id}/agents/research-onboarding/runs",
        headers=_auth_headers(),
        json={
            "research_title": "Variant Resistance Review",
            "primary_objective": "Identify evidence for resistance biomarkers.",
            "space_description": "Review precision medicine evidence.",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["run"]["harness_id"] == "research-onboarding"
    assert payload["assistant_message"]["message_type"] == "clarification_request"
    assert payload["assistant_message"]["title"].startswith("Variant Resistance Review")
    assert len(payload["assistant_message"]["questions"]) >= 3
    first_prompt = payload["assistant_message"]["questions"][0]["prompt"]
    assert payload["assistant_message"]["questions"][0]["suggested_answers"] == [
        answer.model_dump(mode="json") for answer in _suggested_answers(first_prompt)
    ]


def test_continue_research_onboarding_returns_plan_ready_when_questions_are_answered() -> (
    None
):
    research_space_store = HarnessResearchSpaceStore()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Onboarding Space",
        description="Research onboarding test space.",
    )
    client = _build_client_with_space_store(research_space_store)

    seed_response = client.post(
        f"/v1/spaces/{space.id}/agents/research-onboarding/runs",
        headers=_auth_headers(),
        json={
            "research_title": "Variant Resistance Review",
            "primary_objective": "Identify evidence for resistance biomarkers.",
            "space_description": "Review precision medicine evidence.",
        },
    )

    seed_questions = seed_response.json()["assistant_message"]["questions"]
    for index, _question in enumerate(seed_questions, start=1):
        response = client.post(
            f"/v1/spaces/{space.id}/agents/research-onboarding/turns",
            headers=_auth_headers(),
            json={
                "thread_id": "thread-1",
                "message_id": f"message-{index}",
                "intent": "reply",
                "mode": "answer_question",
                "reply_text": f"Answer {index}",
                "reply_html": f"<p>Answer {index}</p>",
                "attachments": [],
                "contextual_anchor": None,
            },
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["assistant_message"]["message_type"] == "plan_ready"


def test_continue_research_onboarding_returns_clarification_for_revision_request() -> (
    None
):
    research_space_store = HarnessResearchSpaceStore()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Onboarding Space",
        description="Research onboarding test space.",
    )
    client = _build_client_with_space_store(research_space_store)

    client.post(
        f"/v1/spaces/{space.id}/agents/research-onboarding/runs",
        headers=_auth_headers(),
        json={
            "research_title": "Variant Resistance Review",
            "primary_objective": "Identify evidence for resistance biomarkers.",
            "space_description": "Review precision medicine evidence.",
        },
    )

    response = client.post(
        f"/v1/spaces/{space.id}/agents/research-onboarding/turns",
        headers=_auth_headers(),
        json={
            "thread_id": "thread-1",
            "message_id": "message-1",
            "intent": "ask_ai",
            "mode": "request_revision",
            "reply_text": "Revise the plan so it emphasizes contradictory evidence.",
            "reply_html": "<p>Revise the plan so it emphasizes contradictory evidence.</p>",
            "attachments": [],
            "contextual_anchor": None,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["assistant_message"]["message_type"] == "clarification_request"
    assert payload["assistant_message"]["questions"][0]["prompt"].startswith(
        "What specifically should change",
    )


def test_research_onboarding_run_returns_503_and_persists_failed_state_when_agent_crashes() -> (
    None
):
    research_space_store = HarnessResearchSpaceStore()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Onboarding Space",
        description="Research onboarding test space.",
    )
    bundle = _build_client_bundle(
        research_space_store,
        onboarding_runner_dependency=_FailingInitialResearchOnboardingRunner,
    )

    response = bundle.client.post(
        f"/v1/spaces/{space.id}/agents/research-onboarding/runs",
        headers=_auth_headers(),
        json={
            "research_title": "Variant Resistance Review",
            "primary_objective": "Identify evidence for resistance biomarkers.",
            "space_description": "Review precision medicine evidence.",
        },
    )

    assert response.status_code == 503
    assert "Synthetic onboarding agent initial failure." in response.text

    runs = bundle.run_registry.list_runs(space_id=space.id)
    assert len(runs) == 1
    failed_run = runs[0]
    assert failed_run.harness_id == "research-onboarding"
    assert failed_run.status == "failed"

    failure_artifact = bundle.artifact_store.get_artifact(
        space_id=space.id,
        run_id=failed_run.id,
        artifact_key="onboarding_agent_error",
    )
    assert failure_artifact is not None
    assert failure_artifact.content["error"] == (
        "Synthetic onboarding agent initial failure."
    )
    message_artifact = bundle.artifact_store.get_artifact(
        space_id=space.id,
        run_id=failed_run.id,
        artifact_key="onboarding_assistant_message",
    )
    assert message_artifact is None

    workspace = bundle.artifact_store.get_workspace(
        space_id=space.id,
        run_id=failed_run.id,
    )
    assert workspace is not None
    assert workspace.snapshot["status"] == "failed"
    assert workspace.snapshot["error"] == "Synthetic onboarding agent initial failure."
    assert bundle.research_state_store.get_state(space_id=space.id) is None


def test_research_onboarding_turn_returns_503_and_preserves_prior_state_when_agent_crashes() -> (
    None
):
    research_space_store = HarnessResearchSpaceStore()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Onboarding Space",
        description="Research onboarding test space.",
    )
    bundle = _build_client_bundle(
        research_space_store,
        onboarding_runner_dependency=_FailingContinuationResearchOnboardingRunner,
    )

    seed_response = bundle.client.post(
        f"/v1/spaces/{space.id}/agents/research-onboarding/runs",
        headers=_auth_headers(),
        json={
            "research_title": "Variant Resistance Review",
            "primary_objective": "Identify evidence for resistance biomarkers.",
            "space_description": "Review precision medicine evidence.",
        },
    )
    assert seed_response.status_code == 201
    seed_run_id = seed_response.json()["run"]["id"]

    state_before = bundle.research_state_store.get_state(space_id=space.id)
    assert state_before is not None

    response = bundle.client.post(
        f"/v1/spaces/{space.id}/agents/research-onboarding/turns",
        headers=_auth_headers(),
        json={
            "thread_id": "thread-1",
            "message_id": "message-1",
            "intent": "reply",
            "mode": "answer_question",
            "reply_text": "Start with contradictory evidence.",
            "reply_html": "<p>Start with contradictory evidence.</p>",
            "attachments": [],
            "contextual_anchor": None,
        },
    )

    assert response.status_code == 503
    assert "Synthetic onboarding continuation failure." in response.text

    runs = bundle.run_registry.list_runs(space_id=space.id)
    assert len(runs) == 2
    failed_run = runs[0]
    assert failed_run.harness_id == "research-onboarding"
    assert failed_run.status == "failed"

    failure_artifact = bundle.artifact_store.get_artifact(
        space_id=space.id,
        run_id=failed_run.id,
        artifact_key="onboarding_agent_error",
    )
    assert failure_artifact is not None
    assert failure_artifact.content["error"] == (
        "Synthetic onboarding continuation failure."
    )
    message_artifact = bundle.artifact_store.get_artifact(
        space_id=space.id,
        run_id=failed_run.id,
        artifact_key="onboarding_assistant_message",
    )
    assert message_artifact is None

    workspace = bundle.artifact_store.get_workspace(
        space_id=space.id,
        run_id=failed_run.id,
    )
    assert workspace is not None
    assert workspace.snapshot["status"] == "failed"
    assert workspace.snapshot["error"] == "Synthetic onboarding continuation failure."

    state_after = bundle.research_state_store.get_state(space_id=space.id)
    assert state_after is not None
    assert state_after.pending_questions == state_before.pending_questions
    assert state_after.explored_questions == state_before.explored_questions
    assert state_after.metadata["last_onboarding_run_id"] == seed_run_id


def test_research_onboarding_rejects_access_to_another_users_space() -> None:
    research_space_store = HarnessResearchSpaceStore()
    other_space = research_space_store.create_space(
        owner_id="22222222-2222-2222-2222-222222222222",
        name="Other User Space",
        description="Not visible to the authenticated caller.",
    )
    client = _build_client_with_space_store(research_space_store)

    response = client.post(
        f"/v1/spaces/{other_space.id}/agents/research-onboarding/runs",
        headers=_auth_headers(),
        json={
            "research_title": "Variant Resistance Review",
            "primary_objective": "Identify evidence for resistance biomarkers.",
            "space_description": "Review precision medicine evidence.",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Space not found"


def test_runtime_style_researcher_token_cannot_access_another_users_space() -> None:
    research_space_store = HarnessResearchSpaceStore()
    other_space = research_space_store.create_space(
        owner_id="22222222-2222-2222-2222-222222222222",
        name="Other User Space",
        description="Not visible to the runtime service user.",
    )
    client = _build_client_with_space_store(research_space_store)

    response = client.post(
        f"/v1/spaces/{other_space.id}/agents/research-onboarding/runs",
        headers=_jwt_auth_headers(
            user_id="00000000-0000-0000-0000-000000000101",
            email="research-inbox-runtime@artana.dev",
            username="research_inbox_runtime",
            full_name="Research Inbox Runtime",
            role="researcher",
        ),
        json={
            "research_title": "Variant Resistance Review",
            "primary_objective": "Identify evidence for resistance biomarkers.",
            "space_description": "Review precision medicine evidence.",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Space not found"


def test_runtime_style_admin_token_can_access_another_users_space() -> None:
    research_space_store = HarnessResearchSpaceStore()
    other_space = research_space_store.create_space(
        owner_id="22222222-2222-2222-2222-222222222222",
        name="Other User Space",
        description="Visible to an admin runtime service user.",
    )
    client = _build_client_with_space_store(research_space_store)

    response = client.post(
        f"/v1/spaces/{other_space.id}/agents/research-onboarding/runs",
        headers=_jwt_auth_headers(
            user_id="00000000-0000-0000-0000-000000000101",
            email="research-inbox-runtime@artana.dev",
            username="research_inbox_runtime",
            full_name="Research Inbox Runtime",
            role="admin",
        ),
        json={
            "research_title": "Variant Resistance Review",
            "primary_objective": "Identify evidence for resistance biomarkers.",
            "space_description": "Review precision medicine evidence.",
        },
    )

    assert response.status_code == 201
    assert (
        response.json()["assistant_message"]["message_type"] == "clarification_request"
    )
