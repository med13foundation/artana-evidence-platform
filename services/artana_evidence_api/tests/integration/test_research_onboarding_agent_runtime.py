"""Integration tests for the real Artana-backed onboarding runner."""

from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import UUID

import pytest
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.research_onboarding_agent_runtime import (
    HarnessResearchOnboardingRunner,
)
from artana_evidence_api.research_onboarding_runtime import (
    ResearchOnboardingContinuationRequest,
    execute_research_onboarding_continuation,
    execute_research_onboarding_run,
)
from artana_evidence_api.research_state import HarnessResearchStateStore
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.runtime_support import has_configured_openai_api_key

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not has_configured_openai_api_key(),
        reason="OpenAI API key is required for real onboarding-agent integration tests.",
    ),
]

_SPACE_ID = UUID("22222222-2222-2222-2222-222222222222")


@dataclass(frozen=True)
class _StubGraphHealthResponse:
    status: str
    version: str


class _StubGraphApiGateway:
    def get_health(self) -> _StubGraphHealthResponse:
        return _StubGraphHealthResponse(status="ok", version="test")

    def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def use_postgres_artana_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force real onboarding integration tests onto the ephemeral Postgres store."""
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url.startswith("postgresql"):
        monkeypatch.setenv("ARTANA_EVIDENCE_API_DATABASE_URL", database_url)
        monkeypatch.delenv("ARTANA_STATE_URI", raising=False)


def test_real_onboarding_initial_run_persists_contract_and_public_artifacts() -> None:
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    research_state_store = HarnessResearchStateStore()

    result = execute_research_onboarding_run(
        space_id=_SPACE_ID,
        research_title="Resistance Evidence Review",
        primary_objective="Identify evidence-backed resistance biomarkers for review.",
        space_description="Use the onboarding agent to clarify the first research plan.",
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=_StubGraphApiGateway(),
        research_state_store=research_state_store,
        onboarding_runner=HarnessResearchOnboardingRunner(),
    )

    assert result.run.status == "completed"
    assert result.assistant_message.message_type in {
        "clarification_request",
        "plan_ready",
    }
    assert (
        artifact_store.get_artifact(
            space_id=_SPACE_ID,
            run_id=result.run.id,
            artifact_key="onboarding_agent_contract",
        )
        is not None
    )
    assert (
        artifact_store.get_artifact(
            space_id=_SPACE_ID,
            run_id=result.run.id,
            artifact_key="onboarding_assistant_message",
        )
        is not None
    )


def test_real_onboarding_continuation_updates_state_from_contract() -> None:
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    research_state_store = HarnessResearchStateStore()
    graph_api_gateway = _StubGraphApiGateway()
    runner = HarnessResearchOnboardingRunner()

    initial = execute_research_onboarding_run(
        space_id=_SPACE_ID,
        research_title="Resistance Evidence Review",
        primary_objective="Identify evidence-backed resistance biomarkers for review.",
        space_description="Use the onboarding agent to clarify the first research plan.",
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=graph_api_gateway,
        research_state_store=research_state_store,
        onboarding_runner=runner,
    )

    continuation = execute_research_onboarding_continuation(
        space_id=_SPACE_ID,
        research_title="Resistance Evidence Review",
        request=ResearchOnboardingContinuationRequest(
            thread_id="integration-thread",
            message_id="integration-message-1",
            intent="reply",
            mode="answer_question",
            reply_text=(
                "Start with a concise evidence-backed first plan. Prioritize clinical "
                "and review evidence, treat PubMed and ClinVar as authoritative, avoid "
                "speculative pathway work, and keep the exploration moderately broad."
            ),
            reply_html="",
            attachments=[],
            contextual_anchor=None,
        ),
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=graph_api_gateway,
        research_state_store=research_state_store,
        onboarding_runner=runner,
    )

    assert initial.run.status == "completed"
    assert continuation.run.status == "completed"
    assert continuation.assistant_message.message_type in {
        "clarification_request",
        "plan_ready",
    }
    assert continuation.research_state.metadata["last_onboarding_message_type"] == (
        continuation.assistant_message.message_type
    )
    assert (
        artifact_store.get_artifact(
            space_id=_SPACE_ID,
            run_id=continuation.run.id,
            artifact_key="onboarding_agent_contract",
        )
        is not None
    )
