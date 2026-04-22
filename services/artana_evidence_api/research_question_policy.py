"""Question policy helpers for research-state follow-up prompts."""

from __future__ import annotations


def _normalized_question_key(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().lower().split())


def is_directional_follow_up_question(question: str) -> bool:
    """Return true when a pending prompt is the broad direction chooser."""
    normalized = _normalized_question_key(question)
    if normalized == "which seed entities should be expanded next?":
        return True
    return "which direction should i deepen next" in normalized


def is_evidence_support_question(question: str) -> bool:
    """Return true when a prompt asks the user to supply evidence support.

    These are useful internal review prompts, but they are not useful
    user-facing questions: Artana already owns evidence retrieval and ranking.
    """
    normalized = _normalized_question_key(question)
    return normalized.startswith("what evidence best supports ")


def has_prior_research_guidance(
    *,
    objective: str | None,
    explored_questions: list[str],
) -> bool:
    """Return true when the user already supplied a research direction."""
    objective_key = _normalized_question_key(objective)
    for question in explored_questions:
        question_key = _normalized_question_key(question)
        if question_key == "":
            continue
        if objective_key != "" and question_key == objective_key:
            continue
        return True
    return False


def should_allow_directional_follow_up(
    *,
    objective: str | None,
    explored_questions: list[str],
    last_graph_snapshot_id: str | None,
) -> bool:
    """Return whether the broad direction chooser may be generated."""
    if last_graph_snapshot_id is not None:
        return False
    return not has_prior_research_guidance(
        objective=objective,
        explored_questions=explored_questions,
    )


def filter_user_facing_pending_questions(
    *,
    objective: str | None,
    explored_questions: list[str],
    pending_questions: list[str],
    last_graph_snapshot_id: str | None,
) -> list[str]:
    """Return only prompts that should be shown to the researcher.

    Read paths are intentionally a little looser than generation paths: the first
    completed pass may store a broad direction chooser after graph snapshotting.
    That chooser should remain visible until the researcher answers it, then any
    stale broad copy is filtered.

    Evidence-support prompts are always filtered. They are internal Artana work,
    not user guidance requests.
    """
    _ = last_graph_snapshot_id
    visible_questions = [
        question
        for question in pending_questions
        if not is_evidence_support_question(question)
    ]
    if not has_prior_research_guidance(
        objective=objective,
        explored_questions=explored_questions,
    ):
        return visible_questions
    return [
        question
        for question in visible_questions
        if not is_directional_follow_up_question(question)
    ]


def filter_repeated_directional_questions(
    *,
    objective: str | None,
    explored_questions: list[str],
    pending_questions: list[str],
    last_graph_snapshot_id: str | None,
) -> list[str]:
    """Backward-compatible alias for the user-facing question filter."""
    return filter_user_facing_pending_questions(
        objective=objective,
        explored_questions=explored_questions,
        pending_questions=pending_questions,
        last_graph_snapshot_id=last_graph_snapshot_id,
    )
