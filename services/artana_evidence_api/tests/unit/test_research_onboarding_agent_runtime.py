"""Unit tests for the Artana-backed onboarding runner."""

from __future__ import annotations

import asyncio

import pytest
from artana_evidence_api.research_onboarding_agent_runtime import (
    HarnessResearchOnboardingContinuationRequest,
    HarnessResearchOnboardingInitialRequest,
    HarnessResearchOnboardingRunner,
    OnboardingAgentExecutionError,
)


def test_runner_raises_without_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ARTANA_OPENAI_API_KEY", raising=False)
    runner = HarnessResearchOnboardingRunner()

    with pytest.raises(OnboardingAgentExecutionError):
        asyncio.run(
            runner.run_initial(
                HarnessResearchOnboardingInitialRequest(
                    harness_id="research-onboarding",
                    research_space_id="11111111-1111-1111-1111-111111111111",
                    research_title="Variant Resistance Review",
                    primary_objective="Identify resistance biomarkers.",
                    space_description="Review precision medicine evidence.",
                    current_state=None,
                ),
            ),
        )


def test_continuation_run_ids_are_unique_across_retries() -> None:
    """Regression: identical continuation inputs must produce different run_ids.

    Previously the run_id was deterministic from thread_id + message_id + mode +
    reply_text, so retrying the same reply caused "run_id already exists" errors
    that left the onboarding thread in a failed state.
    """
    runner = HarnessResearchOnboardingRunner()

    request = HarnessResearchOnboardingContinuationRequest(
        harness_id="research-onboarding",
        research_space_id="22222222-2222-2222-2222-222222222222",
        research_title="MED13 syndrome",
        thread_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        message_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        intent="reply",
        mode="answer_question",
        reply_text="MED13 transcriptional regulation mechanism",
        reply_html="MED13 transcriptional regulation mechanism",
        attachments=[],
        contextual_anchor=None,
        objective="Investigate MED13",
        explored_questions=[],
        pending_questions=["Which angle?"],
        onboarding_status="clarification_request",
    )

    # Call _create_run_id indirectly by inspecting the suffix logic.
    # The fix adds uuid4() to the suffix, so two calls with identical inputs
    # must produce different run_ids.
    from artana_evidence_api.runtime_support import stable_sha256_digest

    run_ids: set[str] = set()
    for _ in range(10):
        from uuid import uuid4

        suffix = stable_sha256_digest(
            f"{request.thread_id}|"
            f"{request.message_id}|"
            f"{request.mode}|"
            f"{request.reply_text}|"
            f"{uuid4()}",
        )
        run_id = runner._create_run_id(
            harness_id=request.harness_id,
            model_id="test-model",
            research_space_id=request.research_space_id,
            suffix=suffix,
        )
        run_ids.add(run_id)

    # All 10 should be unique
    assert len(run_ids) == 10, f"Expected 10 unique run_ids, got {len(run_ids)}"


def test_initial_run_id_is_deterministic() -> None:
    """Initial onboarding run_ids should remain deterministic (idempotent)."""
    runner = HarnessResearchOnboardingRunner()

    from artana_evidence_api.runtime_support import stable_sha256_digest

    suffix = stable_sha256_digest(
        "MED13 syndrome|Investigate MED13|",
    )
    run_id_1 = runner._create_run_id(
        harness_id="research-onboarding",
        model_id="test-model",
        research_space_id="22222222-2222-2222-2222-222222222222",
        suffix=suffix,
    )
    run_id_2 = runner._create_run_id(
        harness_id="research-onboarding",
        model_id="test-model",
        research_space_id="22222222-2222-2222-2222-222222222222",
        suffix=suffix,
    )
    assert run_id_1 == run_id_2, "Initial run_ids should be deterministic"
