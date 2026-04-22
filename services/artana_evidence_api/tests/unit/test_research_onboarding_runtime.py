"""Unit tests for onboarding runtime orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pytest
from artana_evidence_api import research_onboarding_runtime
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
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.research_onboarding_agent_runtime import (
    HarnessResearchOnboardingContinuationRequest,
    HarnessResearchOnboardingInitialRequest,
    HarnessResearchOnboardingResult,
    OnboardingAgentExecutionError,
)
from artana_evidence_api.research_onboarding_runtime import (
    ResearchOnboardingContinuationRequest,
    execute_research_onboarding_continuation,
    execute_research_onboarding_run,
)
from artana_evidence_api.research_state import HarnessResearchStateStore
from artana_evidence_api.run_registry import HarnessRunRegistry
from pydantic import ValidationError

_SPACE_ID = UUID("11111111-1111-1111-1111-111111111111")


@dataclass(frozen=True)
class _StubGraphHealthResponse:
    status: str
    version: str


class _StubGraphApiGateway:
    def get_health(self) -> _StubGraphHealthResponse:
        return _StubGraphHealthResponse(status="ok", version="test")

    def close(self) -> None:
        return None


def _build_contract(
    *,
    message_type: str,
    pending_questions: list[str],
    explored_questions: list[str],
    objective: str | None,
) -> OnboardingAssistantContract:
    questions = [
        OnboardingQuestion(
            id=f"q-{index}",
            prompt=prompt,
            suggested_answers=[
                OnboardingSuggestedAnswer(
                    id=f"q-{index}-answer-1",
                    label="Start with disease cohorts.",
                ),
                OnboardingSuggestedAnswer(
                    id=f"q-{index}-answer-2",
                    label="Prioritize mechanistic papers.",
                ),
            ],
        )
        for index, prompt in enumerate(pending_questions, start=1)
    ]
    actions = (
        [
            OnboardingSuggestedAction(
                id="answer-question",
                label="Answer questions",
                action_type="reply",
            ),
        ]
        if message_type == "clarification_request"
        else [
            OnboardingSuggestedAction(
                id="approve-plan",
                label="Review plan",
                action_type="review",
            ),
        ]
    )
    artifacts = (
        []
        if message_type == "clarification_request"
        else [
            OnboardingArtifact(
                artifact_key="onboarding_plan_outline",
                label="Initial plan outline",
                kind="plan",
            ),
        ]
    )
    return OnboardingAssistantContract(
        message_type=message_type,
        title="Synthetic onboarding turn",
        summary="Synthetic onboarding response for unit tests.",
        sections=[
            OnboardingSection(
                heading="Summary",
                body="Synthetic content",
            ),
        ],
        questions=questions if message_type == "clarification_request" else [],
        suggested_actions=actions,
        artifacts=artifacts,
        state_patch=OnboardingStatePatch(
            thread_status=(
                "your_turn"
                if message_type == "clarification_request"
                else "review_needed"
            ),
            onboarding_status=(
                "awaiting_researcher_reply"
                if message_type == "clarification_request"
                else "plan_ready"
            ),
            pending_question_count=len(pending_questions),
            objective=objective,
            explored_questions=explored_questions,
            pending_questions=pending_questions,
            current_hypotheses=[],
        ),
        confidence_score=0.85,
        rationale="Synthetic rationale",
        evidence=[
            EvidenceItem(
                source_type="note",
                locator="synthetic",
                excerpt="Synthetic evidence",
                relevance=0.9,
            ),
        ],
        agent_run_id="onboarding-agent:test",
    )


def test_onboarding_contract_coerces_plan_ready_with_questions() -> None:
    contract = OnboardingAssistantContract(
        message_type="plan_ready",
        title="Synthetic onboarding turn",
        summary="Synthetic onboarding response for unit tests.",
        sections=[
            OnboardingSection(
                heading="Summary",
                body="Synthetic content",
            ),
        ],
        questions=[
            OnboardingQuestion(
                id="q-1",
                prompt="Which evidence types should the system prioritize first?",
                suggested_answers=[
                    OnboardingSuggestedAnswer(
                        id="q-1-answer-1",
                        label="Clinical evidence",
                    ),
                ],
            ),
        ],
        suggested_actions=[],
        artifacts=[],
        state_patch=OnboardingStatePatch(
            thread_status="review_needed",
            onboarding_status="plan_ready",
            pending_question_count=0,
            objective="Identify evidence-backed resistance biomarkers for review.",
            explored_questions=[],
            pending_questions=[],
            current_hypotheses=[],
        ),
        confidence_score=0.85,
        rationale="Synthetic rationale",
        evidence=[
            EvidenceItem(
                source_type="note",
                locator="synthetic",
                excerpt="Synthetic evidence",
                relevance=0.9,
            ),
        ],
        agent_run_id="onboarding-agent:test",
    )

    assert contract.message_type == "clarification_request"
    assert contract.state_patch.thread_status == "your_turn"
    assert contract.state_patch.onboarding_status == "awaiting_researcher_reply"
    assert contract.state_patch.pending_question_count == 1
    assert contract.state_patch.pending_questions == [
        "Which evidence types should the system prioritize first?",
    ]
    assert (
        "Normalized plan_ready output with open questions into "
        "clarification_request."
    ) in contract.warnings


class _SuccessRunner:
    async def run_initial(
        self,
        request: HarnessResearchOnboardingInitialRequest,
    ) -> HarnessResearchOnboardingResult:
        contract = _build_contract(
            message_type="clarification_request",
            pending_questions=[
                f"What would count as a useful first deliverable for {request.research_title}?",
                "Which evidence types should the system prioritize first?",
            ],
            explored_questions=[],
            objective=request.primary_objective or None,
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
        remaining_questions = list(request.pending_questions)
        explored_questions = list(request.explored_questions)
        if remaining_questions:
            explored_questions.append(remaining_questions.pop(0))
        message_type = "clarification_request" if remaining_questions else "plan_ready"
        contract = _build_contract(
            message_type=message_type,
            pending_questions=remaining_questions,
            explored_questions=explored_questions,
            objective=request.objective,
        )
        return HarnessResearchOnboardingResult(
            contract=contract,
            agent_run_id="onboarding-agent:continuation",
            active_skill_names=(),
        )


class _FailingRunner:
    async def run_initial(
        self,
        request: HarnessResearchOnboardingInitialRequest,
    ) -> HarnessResearchOnboardingResult:
        _ = request
        raise OnboardingAgentExecutionError("missing OpenAI configuration")

    async def run_continuation(
        self,
        request: HarnessResearchOnboardingContinuationRequest,
    ) -> HarnessResearchOnboardingResult:
        _ = request
        raise OnboardingAgentExecutionError("agent execution failed")


def test_onboarding_contract_validation_rejects_inconsistent_pending_count() -> None:
    with pytest.raises(ValidationError):
        OnboardingStatePatch(
            thread_status="your_turn",
            onboarding_status="awaiting_researcher_reply",
            pending_question_count=2,
            objective=None,
            explored_questions=[],
            pending_questions=["one"],
            current_hypotheses=[],
        )


def test_execute_research_onboarding_run_maps_contract_to_public_message() -> None:
    result = execute_research_onboarding_run(
        space_id=_SPACE_ID,
        research_title="Variant Resistance Review",
        primary_objective="Identify resistance biomarkers.",
        space_description="Review precision medicine evidence.",
        run_registry=HarnessRunRegistry(),
        artifact_store=HarnessArtifactStore(),
        graph_api_gateway=_StubGraphApiGateway(),
        research_state_store=HarnessResearchStateStore(),
        onboarding_runner=_SuccessRunner(),
    )

    assert result.assistant_message.message_type == "clarification_request"
    assert result.run.status == "completed"
    assert len(result.assistant_message.questions) == 2
    assert result.assistant_message.questions[0]["suggested_answers"] == [
        {"id": "q-1-answer-1", "label": "Start with disease cohorts."},
        {"id": "q-1-answer-2", "label": "Prioritize mechanistic papers."},
    ]
    assert result.research_state.pending_questions == [
        "What would count as a useful first deliverable for Variant Resistance Review?",
        "Which evidence types should the system prioritize first?",
    ]


def test_execute_research_onboarding_run_publishes_primary_result_before_marking_completed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    original_store_primary_result_artifact = (
        research_onboarding_runtime.store_primary_result_artifact
    )

    def _observing_store_primary_result_artifact(**kwargs: object) -> None:
        run_id = str(kwargs["run_id"])
        run_record = run_registry.get_run(space_id=_SPACE_ID, run_id=run_id)
        assert run_record is not None
        assert run_record.status == "running"
        content = kwargs["content"]
        assert isinstance(content, dict)
        assert content["run"]["status"] == "completed"
        original_store_primary_result_artifact(**kwargs)

    monkeypatch.setattr(
        research_onboarding_runtime,
        "store_primary_result_artifact",
        _observing_store_primary_result_artifact,
    )

    result = execute_research_onboarding_run(
        space_id=_SPACE_ID,
        research_title="Variant Resistance Review",
        primary_objective="Identify resistance biomarkers.",
        space_description="Review precision medicine evidence.",
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=_StubGraphApiGateway(),
        research_state_store=HarnessResearchStateStore(),
        onboarding_runner=_SuccessRunner(),
    )

    workspace = artifact_store.get_workspace(space_id=_SPACE_ID, run_id=result.run.id)
    artifact = artifact_store.get_artifact(
        space_id=_SPACE_ID,
        run_id=result.run.id,
        artifact_key="research_onboarding_run_result",
    )
    assert result.run.status == "completed"
    assert workspace is not None
    assert workspace.snapshot["primary_result_key"] == "research_onboarding_run_result"
    assert artifact is not None


def test_execute_research_onboarding_continuation_updates_state_from_contract() -> None:
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    research_state_store = HarnessResearchStateStore()
    graph_api_gateway = _StubGraphApiGateway()

    seed_result = execute_research_onboarding_run(
        space_id=_SPACE_ID,
        research_title="Variant Resistance Review",
        primary_objective="Identify resistance biomarkers.",
        space_description="Review precision medicine evidence.",
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=graph_api_gateway,
        research_state_store=research_state_store,
        onboarding_runner=_SuccessRunner(),
    )

    result = execute_research_onboarding_continuation(
        space_id=_SPACE_ID,
        research_title="Variant Resistance Review",
        request=ResearchOnboardingContinuationRequest(
            thread_id="thread-1",
            message_id="message-1",
            intent="reply",
            mode="answer_question",
            reply_text="Start with contradictory evidence.",
            reply_html="<p>Start with contradictory evidence.</p>",
            attachments=[],
            contextual_anchor=None,
        ),
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=graph_api_gateway,
        research_state_store=research_state_store,
        onboarding_runner=_SuccessRunner(),
    )

    assert seed_result.research_state.pending_questions
    assert result.run.status == "completed"
    assert result.research_state.explored_questions == [
        "What would count as a useful first deliverable for Variant Resistance Review?",
    ]
    assert result.research_state.pending_questions == [
        "Which evidence types should the system prioritize first?",
    ]


def test_execute_research_onboarding_continuation_publishes_primary_result_before_marking_completed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    research_state_store = HarnessResearchStateStore()
    original_store_primary_result_artifact = (
        research_onboarding_runtime.store_primary_result_artifact
    )

    seed_result = execute_research_onboarding_run(
        space_id=_SPACE_ID,
        research_title="Variant Resistance Review",
        primary_objective="Identify resistance biomarkers.",
        space_description="Review precision medicine evidence.",
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=_StubGraphApiGateway(),
        research_state_store=research_state_store,
        onboarding_runner=_SuccessRunner(),
    )

    def _observing_store_primary_result_artifact(**kwargs: object) -> None:
        run_id = str(kwargs["run_id"])
        run_record = run_registry.get_run(space_id=_SPACE_ID, run_id=run_id)
        assert run_record is not None
        assert run_record.status == "running"
        content = kwargs["content"]
        assert isinstance(content, dict)
        assert content["run"]["status"] == "completed"
        original_store_primary_result_artifact(**kwargs)

    monkeypatch.setattr(
        research_onboarding_runtime,
        "store_primary_result_artifact",
        _observing_store_primary_result_artifact,
    )

    result = execute_research_onboarding_continuation(
        space_id=_SPACE_ID,
        research_title="Variant Resistance Review",
        request=ResearchOnboardingContinuationRequest(
            thread_id="thread-1",
            message_id="message-1",
            intent="reply",
            mode="answer_question",
            reply_text="Start with contradictory evidence.",
            reply_html="<p>Start with contradictory evidence.</p>",
            attachments=[],
            contextual_anchor=None,
        ),
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=_StubGraphApiGateway(),
        research_state_store=research_state_store,
        onboarding_runner=_SuccessRunner(),
    )

    workspace = artifact_store.get_workspace(space_id=_SPACE_ID, run_id=result.run.id)
    artifact = artifact_store.get_artifact(
        space_id=_SPACE_ID,
        run_id=result.run.id,
        artifact_key="research_onboarding_turn_result",
    )
    assert seed_result.research_state.pending_questions
    assert result.run.status == "completed"
    assert workspace is not None
    assert workspace.snapshot["primary_result_key"] == "research_onboarding_turn_result"
    assert artifact is not None


def test_execute_research_onboarding_continuation_normalizes_plan_ready_objective_and_seed_terms() -> (
    None
):
    class _PlanReadyRunner:
        async def run_initial(
            self,
            request: HarnessResearchOnboardingInitialRequest,
        ) -> HarnessResearchOnboardingResult:
            del request
            raise AssertionError("run_initial should not be called")

        async def run_continuation(
            self,
            request: HarnessResearchOnboardingContinuationRequest,
        ) -> HarnessResearchOnboardingResult:
            del request
            return HarnessResearchOnboardingResult(
                contract=OnboardingAssistantContract(
                    message_type="plan_ready",
                    title="Plan ready",
                    summary=(
                        "The project is now anchored on Parkinson disease, with an "
                        "explicit goal of supporting treatment discovery and "
                        "hypothesis generation."
                    ),
                    sections=[
                        OnboardingSection(
                            heading="Immediate direction",
                            body=(
                                "A strong first pass is to map disease mechanisms, "
                                "summarize clinical features, and prioritize "
                                "treatment evidence."
                            ),
                        ),
                    ],
                    questions=[],
                    suggested_actions=[
                        OnboardingSuggestedAction(
                            id="review-plan",
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
                        objective="parkinson",
                        explored_questions=["What does 'parkinson' refer to?"],
                        pending_questions=[],
                        current_hypotheses=[],
                    ),
                    confidence_score=0.91,
                    rationale="Enough context exists for a first research pass.",
                    evidence=[
                        EvidenceItem(
                            source_type="note",
                            locator="reply",
                            excerpt="I want to study Parkinson disease and new treatments.",
                            relevance=0.94,
                        ),
                    ],
                    agent_run_id="onboarding-agent:plan-ready",
                ),
                agent_run_id="onboarding-agent:plan-ready",
                active_skill_names=(),
            )

    research_state_store = HarnessResearchStateStore()
    research_state_store.upsert_state(
        space_id=_SPACE_ID,
        objective="parkinson",
        explored_questions=["What does 'parkinson' refer to?"],
        pending_questions=["What does 'parkinson' refer to?"],
        metadata={"research_title": "Parkinson treatment research"},
    )

    result = execute_research_onboarding_continuation(
        space_id=_SPACE_ID,
        research_title="Parkinson treatment research",
        request=ResearchOnboardingContinuationRequest(
            thread_id="thread-1",
            message_id="message-1",
            intent="reply",
            mode="answer_question",
            reply_text="I want to study Parkinson disease and find treatment ideas.",
            reply_html="<p>I want to study Parkinson disease and find treatment ideas.</p>",
            attachments=[],
            contextual_anchor=None,
        ),
        run_registry=HarnessRunRegistry(),
        artifact_store=HarnessArtifactStore(),
        graph_api_gateway=_StubGraphApiGateway(),
        research_state_store=research_state_store,
        onboarding_runner=_PlanReadyRunner(),
    )

    assert result.assistant_message.message_type == "plan_ready"
    assert result.research_state.objective == (
        "Parkinson disease research focused on treatment evidence, "
        "new hypotheses, disease mechanisms, and clinical features"
    )
    assert result.research_state.metadata["search_seed_terms"] == [
        "Parkinson disease",
        "treatment evidence",
        "new hypotheses",
        "disease mechanisms",
        "clinical features",
    ]
    assert result.research_state.pending_questions == []


def test_execute_research_onboarding_run_marks_failed_without_fallback_message() -> (
    None
):
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()

    with pytest.raises(OnboardingAgentExecutionError):
        execute_research_onboarding_run(
            space_id=_SPACE_ID,
            research_title="Variant Resistance Review",
            primary_objective="Identify resistance biomarkers.",
            space_description="Review precision medicine evidence.",
            run_registry=run_registry,
            artifact_store=artifact_store,
            graph_api_gateway=_StubGraphApiGateway(),
            research_state_store=HarnessResearchStateStore(),
            onboarding_runner=_FailingRunner(),
        )

    runs = run_registry.list_runs(space_id=_SPACE_ID)
    assert len(runs) == 1
    assert runs[0].status == "failed"
    failure_artifact = artifact_store.get_artifact(
        space_id=_SPACE_ID,
        run_id=runs[0].id,
        artifact_key="onboarding_agent_error",
    )
    assert failure_artifact is not None
    message_artifact = artifact_store.get_artifact(
        space_id=_SPACE_ID,
        run_id=runs[0].id,
        artifact_key="onboarding_assistant_message",
    )
    assert message_artifact is None
