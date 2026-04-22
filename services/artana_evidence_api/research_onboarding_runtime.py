"""Research onboarding runtime for inbox-style AI conversations."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast
from uuid import UUID  # noqa: TC003

from artana_evidence_api.agent_contracts import (
    OnboardingAssistantContract,
)
from artana_evidence_api.queued_run_support import store_primary_result_artifact
from artana_evidence_api.research_onboarding_agent_runtime import (
    HarnessResearchOnboardingContinuationRequest,
    HarnessResearchOnboardingInitialRequest,
    HarnessResearchOnboardingRunner,
    OnboardingAgentExecutionError,
)
from artana_evidence_api.response_serialization import serialize_run_record
from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.research_state import (
        HarnessResearchStateRecord,
        HarnessResearchStateStore,
    )
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry

_ONBOARDING_HARNESS_ID = "research-onboarding"
_CONTRACT_ARTIFACT_KEY = "onboarding_agent_contract"
_ASSISTANT_MESSAGE_ARTIFACT_KEY = "onboarding_assistant_message"
_FAILURE_ARTIFACT_KEY = "onboarding_agent_error"
_INTAKE_ARTIFACT_KEY = "research_onboarding_intake"
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
_PAIR_ITEM_COUNT = 2
_GENERIC_OBJECTIVE_MAX_WORDS = 2
_ANCHOR_LEADING_FILLER_TOKENS = {
    "a",
    "an",
    "anchored",
    "explore",
    "find",
    "focus",
    "focused",
    "for",
    "i",
    "identify",
    "investigate",
    "is",
    "map",
    "my",
    "new",
    "now",
    "on",
    "our",
    "project",
    "study",
    "the",
    "to",
    "understand",
    "want",
    "we",
}
_ANCHOR_WITH_CONTEXT_PATTERN = re.compile(
    r"\b([A-Za-z][A-Za-z0-9-]*(?:\s+[A-Za-z][A-Za-z0-9-]*){0,3}\s+"
    r"(?:syndrome|disease|disorder|condition|gene|protein|biomarker|"
    r"pathway|complex|receptor|mutation|variant))\b",
    re.IGNORECASE,
)
_ANCHOR_TOKEN_PATTERN = re.compile(
    r"\b([A-Za-z]{2,}[A-Za-z0-9-]*\d+[A-Za-z0-9-]*)\b",
)
_FOCUS_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\b(treatment|treatments|therapy|therapies|management)\b",
            re.IGNORECASE,
        ),
        "treatment evidence",
    ),
    (
        re.compile(r"\b(hypothesis|hypotheses)\b", re.IGNORECASE),
        "new hypotheses",
    ),
    (
        re.compile(
            r"\b(hidden|overlooked|novel)\s+(?:biological|clinical\s+)?connections?\b",
            re.IGNORECASE,
        ),
        "hidden connections",
    ),
    (
        re.compile(r"\b(mechanism|mechanisms|pathway|pathways)\b", re.IGNORECASE),
        "disease mechanisms",
    ),
    (
        re.compile(
            r"\b(phenotype|phenotypes|clinical feature|clinical features)\b",
            re.IGNORECASE,
        ),
        "clinical features",
    ),
)


def _resolve_research_title(
    *,
    research_title: str,
    existing_state: HarnessResearchStateRecord | None,
) -> str:
    normalized_research_title = _normalize_text(research_title)
    if normalized_research_title != "":
        return normalized_research_title
    if existing_state is not None:
        existing_title = existing_state.metadata.get("research_title")
        if isinstance(existing_title, str):
            normalized_existing_title = _normalize_text(existing_title)
            if normalized_existing_title != "":
                return normalized_existing_title
    return "Research space"


@dataclass(frozen=True, slots=True)
class ResearchAssistantMessage:
    """Channel-neutral AI-authored assistant message."""

    message_type: str
    title: str
    summary: str
    sections: list[JSONObject]
    questions: list[JSONObject]
    suggested_actions: list[JSONObject]
    artifacts: list[JSONObject]
    state_patch: JSONObject
    confidence_score: float
    rationale: str
    evidence: list[JSONObject]


@dataclass(frozen=True, slots=True)
class ResearchOnboardingExecutionResult:
    """One completed onboarding execution result."""

    run: HarnessRunRecord
    research_state: HarnessResearchStateRecord
    intake_artifact: JSONObject
    assistant_message: ResearchAssistantMessage


@dataclass(frozen=True, slots=True)
class ResearchOnboardingContinuationResult:
    """One completed onboarding continuation turn."""

    run: HarnessRunRecord
    research_state: HarnessResearchStateRecord
    assistant_message: ResearchAssistantMessage


@dataclass(frozen=True, slots=True)
class ResearchOnboardingContinuationRequest:
    """Input needed to continue one onboarding thread turn."""

    thread_id: str
    message_id: str
    intent: str
    mode: str
    reply_text: str
    reply_html: str
    attachments: list[JSONObject]
    contextual_anchor: JSONObject | None


def _normalize_text(value: str | None) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normalized_string_list(values: list[str] | None) -> list[str]:
    if values is None:
        return []
    normalized_values: list[str] = []
    seen_values: set[str] = set()
    for value in values:
        normalized = _normalize_text(value)
        if normalized == "":
            continue
        key = normalized.casefold()
        if key in seen_values:
            continue
        normalized_values.append(normalized)
        seen_values.add(key)
    return normalized_values


def _objective_context_texts(
    *,
    contract: OnboardingAssistantContract,
    reply_text: str | None,
    research_title: str,
    primary_objective: str,
) -> list[str]:
    texts: list[str] = []
    for value in (
        contract.state_patch.objective,
        reply_text,
        contract.summary,
        research_title,
        primary_objective,
        *contract.state_patch.current_hypotheses,
    ):
        normalized = _normalize_text(value)
        if normalized != "":
            texts.append(normalized)
    for section in contract.sections:
        normalized = _normalize_text(section.body)
        if normalized != "":
            texts.append(normalized)
    return texts


def _extract_anchor_terms(texts: list[str]) -> list[str]:
    def _trim_anchor_candidate(candidate: str) -> str:
        parts = candidate.split()
        while len(parts) > _PAIR_ITEM_COUNT:
            if parts[0].casefold() not in _ANCHOR_LEADING_FILLER_TOKENS:
                break
            parts = parts[1:]
        return " ".join(parts).strip()

    def _is_plausible_anchor_candidate(candidate: str) -> bool:
        parts = candidate.split()
        if not parts:
            return False
        if len(parts) == 1:
            return True
        leading_parts = parts[:-1]
        if len(leading_parts) <= _PAIR_ITEM_COUNT:
            return any(
                part.casefold() not in _ANCHOR_LEADING_FILLER_TOKENS
                for part in leading_parts
            )
        return any(
            any(character.isdigit() for character in part) or part[:1].isupper()
            for part in leading_parts
        )

    anchor_terms: list[str] = []
    seen_terms: set[str] = set()
    for text in texts:
        for pattern in (_ANCHOR_WITH_CONTEXT_PATTERN, _ANCHOR_TOKEN_PATTERN):
            for match in pattern.finditer(text):
                candidate = _trim_anchor_candidate(
                    _normalize_text(match.group(1)),
                )
                if candidate == "":
                    continue
                if not _is_plausible_anchor_candidate(candidate):
                    continue
                if " " not in candidate:
                    candidate = candidate.upper()
                key = candidate.casefold()
                if key in seen_terms:
                    continue
                anchor_terms.append(candidate)
                seen_terms.add(key)
    return anchor_terms


def _extract_focus_terms(texts: list[str]) -> list[str]:
    focus_terms: list[str] = []
    seen_terms: set[str] = set()
    for text in texts:
        for pattern, normalized_label in _FOCUS_PATTERNS:
            if not pattern.search(text):
                continue
            key = normalized_label.casefold()
            if key in seen_terms:
                continue
            focus_terms.append(normalized_label)
            seen_terms.add(key)
    return focus_terms


def _clean_objective_candidate(text: str) -> str:
    cleaned = _normalize_text(text)
    if cleaned == "":
        return ""
    prefixes = (
        "You've given enough to start.",
        "You’ve given enough to start.",
        "Artana will now build a first research plan around ",
        "Artana will now start a first research plan around ",
        "The project is now anchored on ",
    )
    for prefix in prefixes:
        if cleaned.casefold().startswith(prefix.casefold()):
            cleaned = cleaned[len(prefix) :].strip()
            break
    for marker in (" If you ", " If the researcher ", " Reply with "):
        if marker in cleaned:
            cleaned = cleaned.split(marker, maxsplit=1)[0].strip()
    sentences = _SENTENCE_SPLIT_PATTERN.split(cleaned)
    compact = " ".join(
        sentence.strip() for sentence in sentences[:2] if sentence.strip()
    )
    return compact.strip(" ,.;:")


def _format_focus_summary(focus_terms: list[str]) -> str:
    if not focus_terms:
        return ""
    if len(focus_terms) == 1:
        return focus_terms[0]
    if len(focus_terms) == _PAIR_ITEM_COUNT:
        return f"{focus_terms[0]} and {focus_terms[1]}"
    return f"{', '.join(focus_terms[:-1])}, and {focus_terms[-1]}"


def _looks_like_generic_objective(
    *,
    objective: str,
    research_title: str,
    primary_objective: str,
) -> bool:
    normalized_objective = objective.casefold()
    baseline_labels = {
        value.casefold()
        for value in (
            _normalize_text(research_title),
            _normalize_text(primary_objective),
        )
        if value != ""
    }
    return (
        normalized_objective in baseline_labels
        or len(objective.split()) <= _GENERIC_OBJECTIVE_MAX_WORDS
    )


def _resolve_plan_ready_objective(
    *,
    contract: OnboardingAssistantContract,
    research_title: str,
    primary_objective: str,
    reply_text: str | None,
) -> str | None:
    raw_objective = _normalize_text(contract.state_patch.objective)
    texts = _objective_context_texts(
        contract=contract,
        reply_text=reply_text,
        research_title=research_title,
        primary_objective=primary_objective,
    )
    anchor_terms = _extract_anchor_terms(texts)
    focus_terms = _extract_focus_terms(texts)
    if raw_objective != "" and not _looks_like_generic_objective(
        objective=raw_objective,
        research_title=research_title,
        primary_objective=primary_objective,
    ):
        return raw_objective
    if anchor_terms:
        anchor = anchor_terms[0]
        if focus_terms:
            return f"{anchor} research focused on {_format_focus_summary(focus_terms)}"
        return f"{anchor} research"
    for text in texts:
        cleaned = _clean_objective_candidate(text)
        if cleaned == "":
            continue
        if _looks_like_generic_objective(
            objective=cleaned,
            research_title=research_title,
            primary_objective=primary_objective,
        ):
            continue
        return cleaned
    fallback = (
        raw_objective
        or _normalize_text(primary_objective)
        or _normalize_text(
            research_title,
        )
    )
    return fallback or None


def _resolve_plan_ready_seed_terms(
    *,
    contract: OnboardingAssistantContract,
    research_title: str,
    primary_objective: str,
    reply_text: str | None,
    resolved_objective: str | None,
) -> list[str]:
    explicit_seed_terms = _normalized_string_list(contract.state_patch.seed_terms)
    if explicit_seed_terms:
        return explicit_seed_terms[:8]
    texts = _objective_context_texts(
        contract=contract,
        reply_text=reply_text,
        research_title=research_title,
        primary_objective=primary_objective,
    )
    if isinstance(resolved_objective, str) and resolved_objective.strip() != "":
        texts.append(resolved_objective)
    seed_terms = _normalized_string_list(
        [
            *_extract_anchor_terms(texts),
            *_extract_focus_terms(texts),
        ],
    )
    return seed_terms[:8]


def _normalize_plan_ready_contract(
    *,
    contract: OnboardingAssistantContract,
    research_title: str,
    primary_objective: str,
    reply_text: str | None,
) -> OnboardingAssistantContract:
    if contract.message_type != "plan_ready":
        return contract
    resolved_objective = _resolve_plan_ready_objective(
        contract=contract,
        research_title=research_title,
        primary_objective=primary_objective,
        reply_text=reply_text,
    )
    resolved_seed_terms = _resolve_plan_ready_seed_terms(
        contract=contract,
        research_title=research_title,
        primary_objective=primary_objective,
        reply_text=reply_text,
        resolved_objective=resolved_objective,
    )
    state_patch = contract.state_patch.model_copy(
        update={
            "objective": resolved_objective,
            "seed_terms": resolved_seed_terms,
        },
    )
    return contract.model_copy(update={"state_patch": state_patch})


def _json_object_from_model(model: BaseModel) -> JSONObject:
    return cast("JSONObject", model.model_dump(mode="json"))


def _json_objects_from_models(models: list[BaseModel]) -> list[JSONObject]:
    return [_json_object_from_model(model) for model in models]


def _assistant_message_from_contract(
    contract: OnboardingAssistantContract,
) -> ResearchAssistantMessage:
    return ResearchAssistantMessage(
        message_type=contract.message_type,
        title=contract.title,
        summary=contract.summary,
        sections=_json_objects_from_models(
            cast("list[BaseModel]", list(contract.sections)),
        ),
        questions=_json_objects_from_models(
            cast("list[BaseModel]", list(contract.questions)),
        ),
        suggested_actions=_json_objects_from_models(
            cast("list[BaseModel]", list(contract.suggested_actions)),
        ),
        artifacts=_json_objects_from_models(
            cast("list[BaseModel]", list(contract.artifacts)),
        ),
        state_patch=_json_object_from_model(contract.state_patch),
        confidence_score=contract.confidence_score,
        rationale=contract.rationale,
        evidence=_json_objects_from_models(
            cast("list[BaseModel]", list(contract.evidence)),
        ),
    )


def _assistant_message_payload(
    assistant_message: ResearchAssistantMessage,
) -> JSONObject:
    return {
        "message_type": assistant_message.message_type,
        "title": assistant_message.title,
        "summary": assistant_message.summary,
        "sections": assistant_message.sections,
        "questions": assistant_message.questions,
        "suggested_actions": assistant_message.suggested_actions,
        "artifacts": assistant_message.artifacts,
        "state_patch": assistant_message.state_patch,
        "confidence_score": assistant_message.confidence_score,
        "rationale": assistant_message.rationale,
        "evidence": assistant_message.evidence,
    }


def _research_state_payload(state: HarnessResearchStateRecord) -> JSONObject:
    return {
        "space_id": state.space_id,
        "objective": state.objective,
        "current_hypotheses": list(state.current_hypotheses),
        "explored_questions": list(state.explored_questions),
        "pending_questions": list(state.pending_questions),
        "last_graph_snapshot_id": state.last_graph_snapshot_id,
        "active_schedules": list(state.active_schedules),
        "confidence_model": state.confidence_model,
        "budget_policy": state.budget_policy,
        "metadata": state.metadata,
        "created_at": state.created_at.isoformat(),
        "updated_at": state.updated_at.isoformat(),
    }


def _run_payload(run: HarnessRunRecord) -> JSONObject:
    return serialize_run_record(run=run)


def _build_initial_run_result_payload(
    *,
    run: HarnessRunRecord,
    research_state: HarnessResearchStateRecord,
    intake_artifact: JSONObject,
    assistant_message: ResearchAssistantMessage,
) -> JSONObject:
    return {
        "run": _run_payload(run),
        "research_state": _research_state_payload(research_state),
        "intake_artifact": intake_artifact,
        "assistant_message": _assistant_message_payload(assistant_message),
    }


def _build_continuation_run_result_payload(
    *,
    run: HarnessRunRecord,
    research_state: HarnessResearchStateRecord,
    assistant_message: ResearchAssistantMessage,
) -> JSONObject:
    return {
        "run": _run_payload(run),
        "research_state": _research_state_payload(research_state),
        "assistant_message": _assistant_message_payload(assistant_message),
    }


def _mark_failed_onboarding_run(
    *,
    space_id: UUID,
    run_id: str,
    error_message: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> None:
    run_registry.set_run_status(space_id=space_id, run_id=run_id, status="failed")
    run_registry.set_progress(
        space_id=space_id,
        run_id=run_id,
        phase="failed",
        message=error_message,
        progress_percent=1.0,
        completed_steps=1,
        total_steps=1,
        metadata={"error": error_message},
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_FAILURE_ARTIFACT_KEY,
        media_type="application/json",
        content={"error": error_message},
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run_id,
        patch={"status": "failed", "error": error_message},
    )


def _state_metadata(
    *,
    existing_metadata: JSONObject | None,
    research_title: str,
    run_id: str,
    assistant_message: ResearchAssistantMessage,
    agent_run_id: str,
    last_researcher_reply_id: str | None = None,
    active_skill_names: tuple[str, ...] = (),
) -> JSONObject:
    metadata: JSONObject = dict(existing_metadata or {})
    seed_terms = assistant_message.state_patch.get("seed_terms")
    metadata.update(
        {
            "research_title": research_title,
            "onboarding_status": assistant_message.state_patch.get(
                "onboarding_status",
                "awaiting_researcher_reply",
            ),
            "last_onboarding_run_id": run_id,
            "last_onboarding_message_type": assistant_message.message_type,
            "last_onboarding_agent_run_id": agent_run_id,
            "last_onboarding_active_skill_names": list(active_skill_names),
            "search_seed_terms": (
                _normalized_string_list(
                    [value for value in seed_terms if isinstance(value, str)],
                )
                if isinstance(seed_terms, list)
                else []
            ),
        },
    )
    if isinstance(last_researcher_reply_id, str) and last_researcher_reply_id != "":
        metadata["last_researcher_reply_id"] = last_researcher_reply_id
    return metadata


def _persist_contract_artifacts(
    *,
    space_id: UUID,
    run_id: str,
    contract: OnboardingAssistantContract,
    assistant_message: ResearchAssistantMessage,
    artifact_store: HarnessArtifactStore,
) -> None:
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_CONTRACT_ARTIFACT_KEY,
        media_type="application/json",
        content=_json_object_from_model(contract),
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_ASSISTANT_MESSAGE_ARTIFACT_KEY,
        media_type="application/json",
        content=_assistant_message_payload(assistant_message),
    )


def queue_research_onboarding_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    research_title: str,
    primary_objective: str,
    space_description: str,
    graph_service_status: str,
    graph_service_version: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> HarnessRunRecord:
    """Create one queued onboarding run without executing it yet."""
    normalized_research_title = _normalize_text(research_title) or "New research space"
    normalized_objective = _normalize_text(primary_objective)
    normalized_description = _normalize_text(space_description)
    run = run_registry.create_run(
        space_id=space_id,
        harness_id=_ONBOARDING_HARNESS_ID,
        title=f"{normalized_research_title} Onboarding",
        input_payload={
            "research_title": normalized_research_title,
            "primary_objective": normalized_objective,
            "space_description": normalized_description,
        },
        graph_service_status=graph_service_status,
        graph_service_version=graph_service_version,
    )
    artifact_store.seed_for_run(run=run)
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "queued",
            "research_title": normalized_research_title,
            "primary_objective": normalized_objective,
            "space_description": normalized_description,
        },
    )
    return run


def queue_research_onboarding_continuation(  # noqa: PLR0913
    *,
    space_id: UUID,
    research_title: str,
    request: ResearchOnboardingContinuationRequest,
    graph_service_status: str,
    graph_service_version: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> HarnessRunRecord:
    """Create one queued onboarding continuation run without executing it yet."""
    normalized_research_title = _normalize_text(research_title) or "Research space"
    normalized_reply_text = _normalize_text(request.reply_text)
    run = run_registry.create_run(
        space_id=space_id,
        harness_id=_ONBOARDING_HARNESS_ID,
        title=f"{normalized_research_title} Onboarding Continuation",
        input_payload={
            "thread_id": request.thread_id,
            "message_id": request.message_id,
            "intent": request.intent,
            "mode": request.mode,
            "reply_text": normalized_reply_text,
            "reply_html": request.reply_html,
            "attachments": request.attachments,
            "contextual_anchor": request.contextual_anchor or {},
        },
        graph_service_status=graph_service_status,
        graph_service_version=graph_service_version,
    )
    artifact_store.seed_for_run(run=run)
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "queued",
            "research_title": normalized_research_title,
            "thread_id": request.thread_id,
            "message_id": request.message_id,
            "reply_mode": request.mode,
        },
    )
    return run


def execute_research_onboarding_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    research_title: str,
    primary_objective: str,
    space_description: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    graph_api_gateway: GraphTransportBundle,
    research_state_store: HarnessResearchStateStore,
    onboarding_runner: HarnessResearchOnboardingRunner,
    existing_run: HarnessRunRecord | None = None,
) -> ResearchOnboardingExecutionResult:
    """Create one onboarding assistant message and persist the result."""
    graph_health = graph_api_gateway.get_health()
    normalized_research_title = _normalize_text(research_title) or "New research space"
    normalized_objective = _normalize_text(primary_objective)
    normalized_description = _normalize_text(space_description)
    existing_state = research_state_store.get_state(space_id=space_id)
    run = existing_run or run_registry.create_run(
        space_id=space_id,
        harness_id=_ONBOARDING_HARNESS_ID,
        title=f"{normalized_research_title} Onboarding",
        input_payload={
            "research_title": normalized_research_title,
            "primary_objective": normalized_objective,
            "space_description": normalized_description,
        },
        graph_service_status=graph_health.status,
        graph_service_version=graph_health.version,
    )
    if existing_run is None:
        artifact_store.seed_for_run(run=run)
    run_registry.set_run_status(space_id=space_id, run_id=run.id, status="running")
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="drafting",
        message="Running the onboarding agent for the first assistant turn.",
        progress_percent=0.5,
        completed_steps=1,
        total_steps=2,
        metadata={"stage": "onboarding_initial"},
    )
    intake_artifact: JSONObject = {
        "research_title": normalized_research_title,
        "primary_objective": normalized_objective,
        "space_description": normalized_description,
    }
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key=_INTAKE_ARTIFACT_KEY,
        media_type="application/json",
        content=intake_artifact,
    )
    try:
        runner_result = asyncio.run(
            onboarding_runner.run_initial(
                HarnessResearchOnboardingInitialRequest(
                    harness_id=_ONBOARDING_HARNESS_ID,
                    research_space_id=str(space_id),
                    research_title=normalized_research_title,
                    primary_objective=normalized_objective,
                    space_description=normalized_description,
                    current_state=(
                        None
                        if existing_state is None
                        else {
                            "objective": existing_state.objective or "",
                            "current_hypotheses": list(
                                existing_state.current_hypotheses,
                            ),
                            "explored_questions": list(
                                existing_state.explored_questions,
                            ),
                            "pending_questions": list(existing_state.pending_questions),
                            "metadata": dict(existing_state.metadata),
                        }
                    ),
                ),
            ),
        )
    except OnboardingAgentExecutionError as exc:
        error_message = str(exc) or "Research onboarding agent execution failed."
        _mark_failed_onboarding_run(
            space_id=space_id,
            run_id=run.id,
            error_message=error_message,
            run_registry=run_registry,
            artifact_store=artifact_store,
        )
        raise
    normalized_contract = _normalize_plan_ready_contract(
        contract=runner_result.contract,
        research_title=normalized_research_title,
        primary_objective=normalized_objective,
        reply_text=None,
    )
    assistant_message = _assistant_message_from_contract(normalized_contract)
    _persist_contract_artifacts(
        space_id=space_id,
        run_id=run.id,
        contract=normalized_contract,
        assistant_message=assistant_message,
        artifact_store=artifact_store,
    )
    research_state = research_state_store.upsert_state(
        space_id=space_id,
        objective=normalized_contract.state_patch.objective,
        current_hypotheses=list(normalized_contract.state_patch.current_hypotheses),
        explored_questions=list(normalized_contract.state_patch.explored_questions),
        pending_questions=list(normalized_contract.state_patch.pending_questions),
        metadata=_state_metadata(
            existing_metadata=(
                existing_state.metadata if existing_state is not None else {}
            ),
            research_title=normalized_research_title,
            run_id=run.id,
            assistant_message=assistant_message,
            agent_run_id=runner_result.agent_run_id,
            active_skill_names=runner_result.active_skill_names,
        ),
    )
    completed_payload_run = replace(run, status="completed")
    store_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
        artifact_key="research_onboarding_run_result",
        content=_build_initial_run_result_payload(
            run=completed_payload_run,
            research_state=research_state,
            intake_artifact=intake_artifact,
            assistant_message=assistant_message,
        ),
        status_value="completed",
        result_keys=(
            _CONTRACT_ARTIFACT_KEY,
            _ASSISTANT_MESSAGE_ARTIFACT_KEY,
            _INTAKE_ARTIFACT_KEY,
        ),
        workspace_patch={
            "last_onboarding_message_key": _ASSISTANT_MESSAGE_ARTIFACT_KEY,
            "last_onboarding_contract_key": _CONTRACT_ARTIFACT_KEY,
            "last_onboarding_intake_key": _INTAKE_ARTIFACT_KEY,
            "pending_question_count": len(
                normalized_contract.state_patch.pending_questions,
            ),
            "agent_run_id": runner_result.agent_run_id,
        },
    )
    completed_run = run_registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="completed",
    )
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="completed",
        message="Research onboarding message completed.",
        progress_percent=1.0,
        completed_steps=2,
        total_steps=2,
        metadata={
            "pending_question_count": len(
                normalized_contract.state_patch.pending_questions,
            ),
            "message_type": assistant_message.message_type,
            "agent_run_id": runner_result.agent_run_id,
        },
    )
    return ResearchOnboardingExecutionResult(
        run=run if completed_run is None else completed_run,
        research_state=research_state,
        intake_artifact=intake_artifact,
        assistant_message=assistant_message,
    )


def execute_research_onboarding_continuation(  # noqa: PLR0913
    *,
    space_id: UUID,
    research_title: str,
    request: ResearchOnboardingContinuationRequest,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    graph_api_gateway: GraphTransportBundle,
    research_state_store: HarnessResearchStateStore,
    onboarding_runner: HarnessResearchOnboardingRunner,
    existing_run: HarnessRunRecord | None = None,
) -> ResearchOnboardingContinuationResult:
    """Continue one onboarding thread turn after a researcher reply."""
    graph_health = graph_api_gateway.get_health()
    existing_state = research_state_store.get_state(space_id=space_id)
    normalized_research_title = _resolve_research_title(
        research_title=research_title,
        existing_state=existing_state,
    )
    normalized_reply_text = _normalize_text(request.reply_text)
    run = existing_run or run_registry.create_run(
        space_id=space_id,
        harness_id=_ONBOARDING_HARNESS_ID,
        title=f"{normalized_research_title} Onboarding Continuation",
        input_payload={
            "thread_id": request.thread_id,
            "message_id": request.message_id,
            "intent": request.intent,
            "mode": request.mode,
            "reply_text": normalized_reply_text,
            "reply_html": request.reply_html,
            "attachments": request.attachments,
            "contextual_anchor": request.contextual_anchor or {},
        },
        graph_service_status=graph_health.status,
        graph_service_version=graph_health.version,
    )
    if existing_run is None:
        artifact_store.seed_for_run(run=run)
    run_registry.set_run_status(space_id=space_id, run_id=run.id, status="running")
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="reasoning",
        message="Running the onboarding agent on the latest researcher reply.",
        progress_percent=0.5,
        completed_steps=1,
        total_steps=2,
        metadata={"reply_mode": request.mode},
    )
    try:
        runner_result = asyncio.run(
            onboarding_runner.run_continuation(
                HarnessResearchOnboardingContinuationRequest(
                    harness_id=_ONBOARDING_HARNESS_ID,
                    research_space_id=str(space_id),
                    research_title=normalized_research_title,
                    thread_id=request.thread_id,
                    message_id=request.message_id,
                    intent=request.intent,
                    mode=request.mode,
                    reply_text=normalized_reply_text,
                    reply_html=request.reply_html,
                    attachments=list(request.attachments),
                    contextual_anchor=request.contextual_anchor,
                    objective=existing_state.objective if existing_state else None,
                    explored_questions=(
                        list(existing_state.explored_questions)
                        if existing_state is not None
                        else []
                    ),
                    pending_questions=(
                        list(existing_state.pending_questions)
                        if existing_state is not None
                        else []
                    ),
                    onboarding_status=(
                        str(existing_state.metadata.get("onboarding_status"))
                        if existing_state is not None
                        and isinstance(
                            existing_state.metadata.get("onboarding_status"),
                            str,
                        )
                        else None
                    ),
                ),
            ),
        )
    except OnboardingAgentExecutionError as exc:
        error_message = str(exc) or "Research onboarding continuation failed."
        _mark_failed_onboarding_run(
            space_id=space_id,
            run_id=run.id,
            error_message=error_message,
            run_registry=run_registry,
            artifact_store=artifact_store,
        )
        raise
    normalized_contract = _normalize_plan_ready_contract(
        contract=runner_result.contract,
        research_title=normalized_research_title,
        primary_objective=existing_state.objective if existing_state else "",
        reply_text=request.reply_text,
    )
    assistant_message = _assistant_message_from_contract(normalized_contract)
    _persist_contract_artifacts(
        space_id=space_id,
        run_id=run.id,
        contract=normalized_contract,
        assistant_message=assistant_message,
        artifact_store=artifact_store,
    )
    research_state = research_state_store.upsert_state(
        space_id=space_id,
        objective=normalized_contract.state_patch.objective,
        current_hypotheses=list(normalized_contract.state_patch.current_hypotheses),
        explored_questions=list(normalized_contract.state_patch.explored_questions),
        pending_questions=list(normalized_contract.state_patch.pending_questions),
        metadata=_state_metadata(
            existing_metadata=(
                existing_state.metadata if existing_state is not None else {}
            ),
            research_title=normalized_research_title,
            run_id=run.id,
            assistant_message=assistant_message,
            agent_run_id=runner_result.agent_run_id,
            last_researcher_reply_id=request.message_id,
            active_skill_names=runner_result.active_skill_names,
        ),
    )
    completed_payload_run = replace(run, status="completed")
    store_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
        artifact_key="research_onboarding_turn_result",
        content=_build_continuation_run_result_payload(
            run=completed_payload_run,
            research_state=research_state,
            assistant_message=assistant_message,
        ),
        status_value="completed",
        result_keys=(
            _CONTRACT_ARTIFACT_KEY,
            _ASSISTANT_MESSAGE_ARTIFACT_KEY,
        ),
        workspace_patch={
            "last_onboarding_message_key": _ASSISTANT_MESSAGE_ARTIFACT_KEY,
            "last_onboarding_contract_key": _CONTRACT_ARTIFACT_KEY,
            "pending_question_count": len(
                normalized_contract.state_patch.pending_questions,
            ),
            "last_onboarding_message_type": assistant_message.message_type,
            "agent_run_id": runner_result.agent_run_id,
        },
    )
    completed_run = run_registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="completed",
    )
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="completed",
        message="Research onboarding continuation completed.",
        progress_percent=1.0,
        completed_steps=2,
        total_steps=2,
        metadata={
            "pending_question_count": len(
                normalized_contract.state_patch.pending_questions,
            ),
            "message_type": assistant_message.message_type,
            "agent_run_id": runner_result.agent_run_id,
        },
    )
    return ResearchOnboardingContinuationResult(
        run=run if completed_run is None else completed_run,
        research_state=research_state,
        assistant_message=assistant_message,
    )


__all__ = [
    "ResearchAssistantMessage",
    "ResearchOnboardingContinuationRequest",
    "ResearchOnboardingContinuationResult",
    "ResearchOnboardingExecutionResult",
    "queue_research_onboarding_continuation",
    "queue_research_onboarding_run",
    "execute_research_onboarding_continuation",
    "execute_research_onboarding_run",
]
