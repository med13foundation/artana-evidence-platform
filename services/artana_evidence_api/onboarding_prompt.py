"""Prompt builders for the Artana-backed research onboarding agent."""

from __future__ import annotations

import json
import re

from artana_evidence_api.types.common import JSONObject

_SYMBOL_ANCHOR_PATTERN = re.compile(
    r"^[A-Za-z]{2,}[A-Za-z0-9-]*\d[A-Za-z0-9-]*$",
)

ONBOARDING_SYSTEM_PROMPT = """
You are the graph-harness autonomous research onboarding agent.

Your job is to convert research-space intake and researcher replies into a strict
OnboardingAssistantContract.

Rules:
- Return channel-neutral structured content only.
- Do not emit HTML, markdown tables, or UI/component instructions.
- Ask only the minimum next clarification needed to keep the workflow grounded.
- Be supportive and concrete. Researchers may be unsure how to frame their goal, and
  your job is to help them reach a workable starting point instead of testing them.
- Emit message_type="plan_ready" only when the researcher has given enough explicit
  constraints to start a concrete first plan.
- When you emit message_type="plan_ready", make the handoff explicit: say what Artana
  will do next, what the researcher should expect, and what reply is useful only if
  they want to refine the direction.
- When you emit message_type="plan_ready", set state_patch.objective to the concrete
  clarified research objective, not the raw intake shorthand if the conversation has
  resolved it into something more specific.
- When you emit message_type="plan_ready", include 3-8 grounded state_patch.seed_terms
  that would help start literature search immediately. Use entities, diseases, pathways,
  phenotypes, drugs, or mechanism phrases from the conversation. Do not invent them.
- Never invent graph facts, external evidence, source inventories, or prior decisions.
- If the provided context is incomplete, say so in rationale and ask one sharp next
  question instead of hallucinating a plan.
- Use helper_text to explain why the question matters or what kind of answer would be
  enough. Keep that guidance short, specific, and friendly.
- When the researcher seems uncertain, asks for examples, or gives a partial answer,
  do not simply restate the same ambiguity. Offer 2-4 concrete example framings via
  suggested_answers and ask one narrower follow-up that is easier to answer.
- Keep evidence limited to the provided request context and identify it honestly.
- The state_patch must be internally consistent with the message_type and questions.
""".strip()


def _json_block(payload: JSONObject) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _symbol_anchor_label(value: str) -> str:
    normalized = value.strip()
    if not _SYMBOL_ANCHOR_PATTERN.fullmatch(normalized):
        return ""
    return normalized.upper()


def _reply_signals_uncertainty(reply_text: str) -> bool:
    normalized = reply_text.casefold()
    markers = (
        "don't know",
        "do not know",
        "not sure",
        "unsure",
        "no idea",
        "help me",
        "examples",
        "example",
        "can you provide",
        "can you give",
        "i do not know",
        "i don't know",
        "idk",
    )
    return any(marker in normalized for marker in markers)


def build_initial_onboarding_prompt(
    *,
    research_title: str,
    primary_objective: str,
    space_description: str,
    current_state: JSONObject | None,
) -> str:
    """Build the initial onboarding prompt for first-turn intake."""
    context: JSONObject = {
        "research_title": research_title,
        "primary_objective": primary_objective,
        "space_description": space_description,
        "current_state": current_state or {},
    }
    candidate_anchor = _symbol_anchor_label(research_title)
    if candidate_anchor != "":
        context["candidate_research_anchor"] = {
            "label": candidate_anchor,
            "source": "research_title",
            "interpretation": "candidate target/gene symbol",
        }
    return (
        "REQUEST CONTEXT\n"
        "---\n"
        "TURN TYPE: initial_onboarding\n"
        f"INTAKE JSON:\n{_json_block(context)}\n\n"
        "Output requirements:\n"
        "- Return a valid OnboardingAssistantContract.\n"
        "- Use message_type='clarification_request' unless the intake already provides "
        "enough explicit constraints for a concrete first plan.\n"
        "- If clarification is needed, include only the minimum next set of questions "
        "required to move forward.\n"
        "- If INTAKE JSON includes candidate_research_anchor, treat that label as an "
        "already-provided research anchor from the space title. Do not ask what the "
        "anchor refers to. If the remaining objective is broad, preserve the anchor "
        "and ask only for the next useful narrowing detail.\n"
        "- For treatment, therapy, or repurposing objectives with a candidate "
        "target/gene anchor, the anchor is enough to produce a first plan. Make a "
        "disease or indication focus an optional refinement, not a blocking "
        "clarification.\n"
        "- For each clarification question, include 2-4 short suggested_answers when "
        "there are plausible next replies the researcher could choose from. Each "
        "suggested answer must be concrete, non-overlapping, and grounded only in the "
        "provided intake context.\n"
        "- Do not emit HTML or UI-specific rendering instructions.\n"
    )


def build_continuation_onboarding_prompt(
    *,
    thread_id: str,
    message_id: str,
    intent: str,
    mode: str,
    reply_text: str,
    attachments: list[JSONObject],
    contextual_anchor: JSONObject | None,
    objective: str | None,
    explored_questions: list[str],
    pending_questions: list[str],
    onboarding_status: str | None,
) -> str:
    """Build the continuation prompt for a new researcher reply."""
    context: JSONObject = {
        "thread_id": thread_id,
        "message_id": message_id,
        "intent": intent,
        "mode": mode,
        "reply_text": reply_text,
        "attachments": attachments,
        "contextual_anchor": contextual_anchor or {},
        "objective": objective or "",
        "explored_questions": explored_questions,
        "pending_questions": pending_questions,
        "onboarding_status": onboarding_status or "",
    }
    uncertainty_overlay = (
        "Uncertainty handling:\n"
        "- The latest reply suggests the researcher may not know how to answer yet.\n"
        "- Respond with a friendlier hand-hold: explain what kind of answer would unblock "
        "planning, give concrete examples, and provide easy starter options.\n"
        "- Do not repeat the same broad ambiguity in different words.\n"
        "- Prefer a narrower follow-up question that the researcher can answer even if they "
        "are still exploring the space.\n\n"
        if _reply_signals_uncertainty(reply_text)
        else ""
    )
    return (
        "REQUEST CONTEXT\n"
        "---\n"
        "TURN TYPE: onboarding_continuation\n"
        f"TURN JSON:\n{_json_block(context)}\n\n"
        f"{uncertainty_overlay}"
        "Output requirements:\n"
        "- Return a valid OnboardingAssistantContract.\n"
        "- Treat the reply as the newest researcher constraint signal.\n"
        "- If contextual_anchor.type='research_space_anchor', carry that label forward "
        "as persistent space context from earlier turns. Do not ask what the anchor "
        "means again when the latest reply repeats the label or confirms it as a "
        "target/gene.\n"
        "- If a persistent target/gene anchor and a treatment, therapy, or repurposing "
        "objective are both present, that is enough for message_type='plan_ready'. "
        "Use the disease/condition focus as a later refinement unless the researcher "
        "explicitly says the anchor itself is a disease.\n"
        "- If mode='request_revision', ask one sharper clarification unless the reply is "
        "already concrete enough to produce a revised plan.\n"
        "- For each clarification question, include 2-4 short suggested_answers when "
        "the likely reply paths are clear from the conversation. Keep them grounded in "
        "the existing thread context and do not invent facts.\n"
        "- If the latest reply is uncertain or asks for examples, the next clarification "
        "must be easier than the last one: include specific examples and a narrower ask.\n"
        "- If message_type='plan_ready', all open questions must be resolved in "
        "state_patch.pending_questions.\n"
        "- If message_type='plan_ready', state_patch.objective must reflect the concrete "
        "clarified research goal rather than just repeating a raw shorthand label.\n"
        "- If message_type='plan_ready', include 3-8 grounded state_patch.seed_terms "
        "that would be useful for immediate literature search.\n"
        "- If message_type='plan_ready', the summary or sections must clearly state the "
        "next action from here in plain language, including what Artana will do next and "
        "when the researcher only needs to reply to refine the direction.\n"
        "- Do not emit HTML or UI-specific rendering instructions.\n"
    )


__all__ = [
    "ONBOARDING_SYSTEM_PROMPT",
    "build_continuation_onboarding_prompt",
    "build_initial_onboarding_prompt",
]
