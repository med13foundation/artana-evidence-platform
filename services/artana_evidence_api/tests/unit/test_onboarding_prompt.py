"""Unit tests for onboarding prompt construction."""

from __future__ import annotations

from artana_evidence_api.onboarding_prompt import (
    build_continuation_onboarding_prompt,
    build_initial_onboarding_prompt,
)


def test_initial_onboarding_prompt_requests_supportive_suggested_answers() -> None:
    prompt = build_initial_onboarding_prompt(
        research_title="MED13",
        primary_objective="",
        space_description="",
        current_state=None,
    )

    assert "suggested_answers" in prompt
    assert "help them reach a workable starting point" not in prompt
    assert "concrete first plan" in prompt


def test_initial_onboarding_prompt_preserves_symbol_title_as_anchor() -> None:
    prompt = build_initial_onboarding_prompt(
        research_title="med13",
        primary_objective="medicine repurposing that could be used",
        space_description="medicine repurposing that could be used",
        current_state=None,
    )

    assert "candidate_research_anchor" in prompt
    assert '"label": "MED13"' in prompt
    assert "Do not ask what the anchor refers to" in prompt
    assert "optional refinement" in prompt


def test_continuation_prompt_adds_uncertainty_overlay_for_example_requests() -> None:
    prompt = build_continuation_onboarding_prompt(
        thread_id="thread-1",
        message_id="message-1",
        intent="reply",
        mode="answer_question",
        reply_text="Can you provide some examples? I do not know.",
        attachments=[],
        contextual_anchor=None,
        objective="MED13",
        explored_questions=[],
        pending_questions=["What does MED13 refer to here?"],
        onboarding_status="awaiting_researcher_reply",
    )

    assert "Uncertainty handling:" in prompt
    assert "friendlier hand-hold" in prompt
    assert "Do not repeat the same broad ambiguity" in prompt


def test_continuation_prompt_preserves_persistent_space_anchor() -> None:
    prompt = build_continuation_onboarding_prompt(
        thread_id="thread-1",
        message_id="message-1",
        intent="reply",
        mode="answer_question",
        reply_text="med13",
        attachments=[],
        contextual_anchor={
            "type": "research_space_anchor",
            "label": "MED13",
            "role": "candidate_target_or_gene",
        },
        objective="MED13 is the research focus. medicine repurposing",
        explored_questions=[],
        pending_questions=["Which disease or condition should we focus on?"],
        onboarding_status="awaiting_researcher_reply",
    )

    assert "research_space_anchor" in prompt
    assert "Do not ask what the anchor means again" in prompt
    assert "that is enough for message_type='plan_ready'" in prompt


def test_continuation_prompt_skips_uncertainty_overlay_for_concrete_reply() -> None:
    prompt = build_continuation_onboarding_prompt(
        thread_id="thread-1",
        message_id="message-1",
        intent="reply",
        mode="answer_question",
        reply_text="MED13 is the gene, and I want hypotheses about epilepsy treatments.",
        attachments=[],
        contextual_anchor=None,
        objective="MED13 epilepsy",
        explored_questions=[],
        pending_questions=["What does MED13 refer to here?"],
        onboarding_status="awaiting_researcher_reply",
    )

    assert "Uncertainty handling:" not in prompt


def test_continuation_prompt_requires_explicit_plan_ready_handoff() -> None:
    prompt = build_continuation_onboarding_prompt(
        thread_id="thread-1",
        message_id="message-1",
        intent="reply",
        mode="answer_question",
        reply_text="MED13 syndrome, and I want literature search plus treatment hypotheses.",
        attachments=[],
        contextual_anchor=None,
        objective="MED13 syndrome treatment discovery",
        explored_questions=["What does MED13 refer to?"],
        pending_questions=[],
        onboarding_status="awaiting_researcher_reply",
    )

    assert "If message_type='plan_ready'" in prompt
    assert "what Artana will do next" in prompt
