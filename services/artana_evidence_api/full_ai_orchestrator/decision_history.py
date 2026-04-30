"""Decision history builders for the full-AI orchestrator."""

from __future__ import annotations

import json
from uuid import NAMESPACE_URL, uuid5

from artana_evidence_api.full_ai_orchestrator.action_registry import (
    build_step_key,
    require_action_enabled_for_sources,
)
from artana_evidence_api.full_ai_orchestrator.response_summaries import _stop_reason
from artana_evidence_api.full_ai_orchestrator.runtime_constants import (
    _HARNESS_ID,
    _STRUCTURED_ENRICHMENT_SOURCES,
)
from artana_evidence_api.full_ai_orchestrator.workspace_support import (
    _chase_round_action_input_from_workspace,
    _chase_round_metadata_from_workspace,
    _chase_round_stop_reason,
    _source_decision_status,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorActionType,
    ResearchOrchestratorDecision,
)
from artana_evidence_api.research_init_runtime import ResearchInitExecutionResult
from artana_evidence_api.types.common import (
    JSONObject,
    ResearchSpaceSourcePreferences,
    json_array_or_empty,
    json_object_or_empty,
)


def _build_decision_history(  # noqa: PLR0913
    *,
    objective: str,
    seed_terms: list[str],
    max_depth: int,
    max_hypotheses: int,
    sources: ResearchSpaceSourcePreferences,
    workspace_snapshot: JSONObject,
    research_init_result: ResearchInitExecutionResult,
    source_execution_summary: JSONObject,
    bootstrap_summary: JSONObject | None,
    brief_metadata: JSONObject,
) -> list[ResearchOrchestratorDecision]:
    decisions: list[ResearchOrchestratorDecision] = []
    decisions.append(
        _build_decision(
            action_type=ResearchOrchestratorActionType.INITIALIZE_WORKSPACE,
            round_number=0,
            action_input={
                "objective": objective,
                "seed_terms": list(seed_terms),
                "max_depth": max_depth,
                "max_hypotheses": max_hypotheses,
            },
            evidence_basis="Queued Phase 1 deterministic full AI orchestrator baseline.",
            status="completed",
            metadata={"enabled_sources": json_object_or_empty(sources)},
        ),
    )
    pubmed_enabled = sources.get("pubmed", True)
    decisions.append(
        _build_decision(
            action_type=ResearchOrchestratorActionType.QUERY_PUBMED,
            round_number=0,
            source_key="pubmed",
            action_input={"seed_terms": list(seed_terms)},
            evidence_basis="Deterministic research-init PubMed discovery phase.",
            status="completed" if pubmed_enabled else "skipped",
            stop_reason=None if pubmed_enabled else "source_disabled",
            metadata={"pubmed_result_count": len(research_init_result.pubmed_results)},
        ),
    )
    decisions.append(
        _build_decision(
            action_type=ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED,
            round_number=0,
            source_key="pubmed",
            action_input={"max_hypotheses": max_hypotheses},
            evidence_basis="Selected PubMed records were ingested through the existing deterministic pipeline.",
            status="completed" if pubmed_enabled else "skipped",
            stop_reason=None if pubmed_enabled else "source_disabled",
            metadata={
                "documents_ingested": research_init_result.documents_ingested,
                "proposal_count": research_init_result.proposal_count,
            },
        ),
    )
    decisions.append(
        _build_decision(
            action_type=ResearchOrchestratorActionType.DERIVE_DRIVEN_TERMS,
            round_number=0,
            action_input={
                "seed_terms": list(seed_terms),
                "driven_terms_count": len(
                    json_array_or_empty(workspace_snapshot.get("driven_terms"))
                ),
            },
            evidence_basis="Driven terms were derived from PubMed findings plus initial seed terms.",
            status="completed",
            metadata={
                "driven_terms": json_array_or_empty(
                    workspace_snapshot.get("driven_terms")
                ),
                "driven_genes_from_pubmed": (
                    json_array_or_empty(
                        workspace_snapshot.get("driven_genes_from_pubmed")
                    )
                ),
            },
        ),
    )
    for source_key in _STRUCTURED_ENRICHMENT_SOURCES:
        if not sources.get(source_key, False):
            continue
        require_action_enabled_for_sources(
            action_type=ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
            source_key=source_key,
            sources=sources,
        )
        source_results = source_execution_summary.get("source_results")
        source_summary = (
            source_results.get(source_key, {})
            if isinstance(source_results, dict)
            and isinstance(source_results.get(source_key), dict)
            else {}
        )
        structured_status, structured_stop_reason = _source_decision_status(
            source_summary=source_summary,
            pending_status="running",
        )
        decisions.append(
            _build_decision(
                action_type=ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
                round_number=0,
                source_key=source_key,
                action_input={"source_key": source_key},
                evidence_basis="Structured enrichment reused the current deterministic research-init source family handlers.",
                status=structured_status,
                stop_reason=structured_stop_reason,
                metadata={"source_summary": source_summary},
            ),
        )
    bootstrap_run_id = workspace_snapshot.get("bootstrap_run_id")
    bootstrap_status = "completed" if isinstance(bootstrap_run_id, str) else "skipped"
    decisions.append(
        _build_decision(
            action_type=ResearchOrchestratorActionType.RUN_BOOTSTRAP,
            round_number=0,
            action_input={
                "bootstrap_source_type": workspace_snapshot.get(
                    "bootstrap_source_type"
                ),
            },
            evidence_basis="Bootstrap execution delegated to the governed research-bootstrap runtime.",
            status=bootstrap_status,
            stop_reason=(
                None if bootstrap_status == "completed" else "bootstrap_not_triggered"
            ),
            metadata={
                "bootstrap_run_id": bootstrap_run_id,
                "bootstrap_summary": bootstrap_summary or {},
            },
        ),
    )
    guarded_stop_after_chase_round = (
        workspace_snapshot.get("guarded_stop_after_chase_round")
        if isinstance(workspace_snapshot.get("guarded_stop_after_chase_round"), int)
        else None
    )
    guarded_terminal_control_after_chase_round = (
        workspace_snapshot.get("guarded_terminal_control_after_chase_round")
        if isinstance(
            workspace_snapshot.get("guarded_terminal_control_after_chase_round"),
            int,
        )
        else None
    )
    guarded_terminal_control_action = json_object_or_empty(
        workspace_snapshot.get("guarded_terminal_control_action")
    )
    guarded_execution_summary = json_object_or_empty(
        workspace_snapshot.get("guarded_execution")
    )
    for chase_round in (1, 2):
        chase_summary = workspace_snapshot.get(f"chase_round_{chase_round}")
        chase_action_input = _chase_round_action_input_from_workspace(
            workspace_snapshot=workspace_snapshot,
            round_number=chase_round,
        )
        chase_metadata = _chase_round_metadata_from_workspace(
            workspace_snapshot=workspace_snapshot,
            round_number=chase_round,
        )
        raw_guarded_stop_reason = guarded_terminal_control_action.get("stop_reason")
        guarded_terminal_stop_reason = (
            raw_guarded_stop_reason
            if isinstance(raw_guarded_stop_reason, str)
            else None
        )
        guarded_stop_reason = (
            "guarded_generate_brief"
            if guarded_stop_after_chase_round == chase_round - 1
            else guarded_terminal_stop_reason
            if guarded_terminal_control_after_chase_round == chase_round - 1
            else None
        )
        decisions.append(
            _build_decision(
                action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                round_number=chase_round,
                action_input=chase_action_input,
                evidence_basis="Chase rounds reused the current deterministic entity-chase thresholds.",
                status=("completed" if isinstance(chase_summary, dict) else "skipped"),
                stop_reason=(
                    None
                    if isinstance(chase_summary, dict)
                    else (
                        guarded_stop_reason
                        if guarded_stop_reason is not None
                        else _chase_round_stop_reason(chase_metadata)
                    )
                ),
                metadata=(
                    chase_metadata
                    if chase_metadata
                    else (
                        {
                            "guarded_execution": guarded_execution_summary,
                            "guarded_terminal_control_action": (
                                guarded_terminal_control_action
                                if guarded_terminal_control_action
                                else {}
                            ),
                        }
                        if guarded_stop_reason is not None
                        else {}
                    )
                ),
            ),
        )
    decisions.append(
        _build_decision(
            action_type=ResearchOrchestratorActionType.GENERATE_BRIEF,
            round_number=0,
            action_input={"result_key": "research_brief"},
            evidence_basis="Final brief generation reused the deterministic brief builder with optional LLM enhancement.",
            status="completed" if brief_metadata.get("present") else "skipped",
            stop_reason=(
                None if brief_metadata.get("present") else "brief_not_available"
            ),
            metadata=brief_metadata,
        ),
    )
    decisions.append(
        _build_decision(
            action_type=ResearchOrchestratorActionType.STOP,
            round_number=0,
            action_input={
                "error_count": len(research_init_result.errors),
                "pending_question_count": len(research_init_result.pending_questions),
            },
            evidence_basis=(
                "Deterministic baseline run reached a terminal state."
                if not guarded_terminal_control_action
                else "Guarded terminal control flow recorded the terminal decision."
            ),
            status="completed",
            stop_reason=(
                raw_stop_reason
                if isinstance(
                    (
                        raw_stop_reason := guarded_terminal_control_action.get(
                            "stop_reason"
                        )
                    ),
                    str,
                )
                else _stop_reason(
                    research_init_result=research_init_result,
                    workspace_snapshot=workspace_snapshot,
                )
            ),
            metadata=(
                {
                    "final_status": workspace_snapshot.get("status", "completed"),
                    "guarded_terminal_control_action": guarded_terminal_control_action,
                }
                if guarded_terminal_control_action
                else {
                    "final_status": workspace_snapshot.get("status", "completed"),
                }
            ),
        ),
    )
    return decisions


def _build_decision(
    *,
    action_type: ResearchOrchestratorActionType,
    round_number: int,
    action_input: JSONObject,
    evidence_basis: str,
    status: str,
    source_key: str | None = None,
    stop_reason: str | None = None,
    metadata: JSONObject | None = None,
) -> ResearchOrchestratorDecision:
    step_key = build_step_key(
        action_type=action_type,
        round_number=round_number,
        source_key=source_key,
    )
    decision_id = str(
        uuid5(
            NAMESPACE_URL,
            (
                f"{_HARNESS_ID}:{step_key}:"
                f"{json.dumps(action_input, sort_keys=True, default=str)}"
            ),
        ),
    )
    return ResearchOrchestratorDecision(
        decision_id=decision_id,
        round_number=round_number,
        action_type=action_type,
        action_input=action_input,
        source_key=source_key,
        evidence_basis=evidence_basis,
        stop_reason=stop_reason,
        step_key=step_key,
        status=status,
        metadata={} if metadata is None else metadata,
    )


__all__ = [
    "_build_decision",
    "_build_decision_history",
]
