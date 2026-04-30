"""Checkpoint decision lookup helpers for shadow planner timelines."""

from __future__ import annotations

from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorActionType,
    ResearchOrchestratorDecision,
)
from artana_evidence_api.types.common import JSONObject


def _decision_prior_to(
    *,
    decisions: list[ResearchOrchestratorDecision],
) -> list[JSONObject]:
    return [decision.model_dump(mode="json") for decision in decisions]


def _first_comparable_decision(
    *,
    decisions: list[ResearchOrchestratorDecision],
) -> ResearchOrchestratorDecision | None:
    for decision in decisions:
        if decision.action_type in {
            ResearchOrchestratorActionType.INITIALIZE_WORKSPACE,
            ResearchOrchestratorActionType.STOP,
        }:
            continue
        if decision.status == "skipped":
            continue
        return decision
    return None


def _find_decision(
    *,
    decisions: list[ResearchOrchestratorDecision],
    action_type: ResearchOrchestratorActionType,
    round_number: int = 0,
    source_key: str | None = None,
) -> ResearchOrchestratorDecision | None:
    for decision in decisions:
        if (
            decision.action_type == action_type
            and decision.round_number == round_number
            and decision.source_key == source_key
        ):
            return decision
    return None


def _find_first_structured_enrichment_decision(
    *,
    decisions: list[ResearchOrchestratorDecision],
) -> ResearchOrchestratorDecision | None:
    for decision in decisions:
        if (
            decision.action_type
            != ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT
        ):
            continue
        if decision.status == "skipped":
            continue
        return decision
    return None


def _checkpoint_target_decision(
    *,
    checkpoint_key: str,
    decisions: list[ResearchOrchestratorDecision],
    workspace_summary: JSONObject | None = None,
) -> ResearchOrchestratorDecision | None:
    target: ResearchOrchestratorDecision | None = None
    if checkpoint_key == "before_first_action":
        target = _first_comparable_decision(decisions=decisions)
    elif checkpoint_key == "after_pubmed_discovery":
        target = _find_decision(
            decisions=decisions,
            action_type=ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED,
            source_key="pubmed",
        )
    elif checkpoint_key in {"after_pubmed_ingest_extract", "after_driven_terms_ready"}:
        structured_target = _find_first_structured_enrichment_decision(
            decisions=decisions,
        )
        target = structured_target or _find_decision(
            decisions=decisions,
            action_type=ResearchOrchestratorActionType.RUN_BOOTSTRAP,
        )
    else:
        chase_round_number_by_checkpoint = {
            "after_bootstrap": 1,
            "after_chase_round_1": 2,
        }
        chase_round_number = chase_round_number_by_checkpoint.get(checkpoint_key)
        if chase_round_number is not None:
            synthetic_stop_target = _synthetic_chase_stop_target(
                checkpoint_key=checkpoint_key,
                chase_round_number=chase_round_number,
                workspace_summary=workspace_summary,
            )
            if synthetic_stop_target is not None:
                return synthetic_stop_target
            target = _find_decision(
                decisions=decisions,
                action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                round_number=chase_round_number,
            )
            if target is None:
                checkpoint_key = "before_brief_generation"
        if target is None and checkpoint_key in {
            "after_chase_round_2",
            "before_brief_generation",
        }:
            target = _find_decision(
                decisions=decisions,
                action_type=ResearchOrchestratorActionType.GENERATE_BRIEF,
            )
        elif target is None and checkpoint_key == "before_terminal_stop":
            target = _find_decision(
                decisions=decisions,
                action_type=ResearchOrchestratorActionType.STOP,
            )
    return target


def _synthetic_chase_stop_target(
    *,
    checkpoint_key: str,
    chase_round_number: int,
    workspace_summary: JSONObject | None,
) -> ResearchOrchestratorDecision | None:
    if not isinstance(workspace_summary, dict):
        return None
    deterministic_selection = workspace_summary.get("deterministic_selection")
    stop_reason: str | None = None
    if isinstance(deterministic_selection, dict):
        raw_stop_reason = deterministic_selection.get("stop_reason")
        if deterministic_selection.get("stop_instead") is True:
            stop_reason = (
                str(raw_stop_reason)
                if isinstance(raw_stop_reason, str) and raw_stop_reason.strip()
                else "threshold_not_met"
            )
    if stop_reason is None:
        threshold_met = workspace_summary.get("deterministic_threshold_met")
        chase_candidates = workspace_summary.get("chase_candidates")
        if (
            threshold_met is False
            and isinstance(chase_candidates, list)
            and not chase_candidates
        ):
            stop_reason = "threshold_not_met"
    if stop_reason is None:
        return None
    return ResearchOrchestratorDecision(
        decision_id=f"synthetic-{checkpoint_key}-stop",
        round_number=chase_round_number,
        action_type=ResearchOrchestratorActionType.STOP,
        action_input={
            "checkpoint_key": checkpoint_key,
            "synthetic_deterministic_target": True,
        },
        source_key=None,
        evidence_basis=(
            "The workspace summary indicates the deterministic chase baseline "
            "did not expose a continuing chase selection at this checkpoint."
        ),
        stop_reason=stop_reason,
        step_key=f"full-ai-orchestrator.v1.synthetic.{checkpoint_key}.control.stop",
        status="completed",
        expected_value_band="low",
        qualitative_rationale=(
            "The deterministic chase threshold was not met, so the comparable "
            "baseline action at this checkpoint is to stop rather than open a "
            "new chase round."
        ),
        risk_level="low",
        requires_approval=False,
        metadata={"synthetic_deterministic_target": True},
    )


def _phase_record(
    *,
    phase_records: dict[str, list[JSONObject]],
    phase: str,
) -> JSONObject | None:
    records = phase_records.get(phase)
    if not isinstance(records, list) or not records:
        return None
    return records[0]


def _phase_record_with_chase(
    *,
    phase_records: dict[str, list[JSONObject]],
    round_number: int,
) -> JSONObject | None:
    for phase in ("deferred_mondo", "completed"):
        records = phase_records.get(phase)
        if not isinstance(records, list):
            continue
        for record in records:
            workspace_snapshot = record.get("workspace_snapshot")
            if not isinstance(workspace_snapshot, dict):
                continue
            if isinstance(workspace_snapshot.get(f"chase_round_{round_number}"), dict):
                return record
    next_phase = f"chase_round_{round_number + 1}"
    return _phase_record(phase_records=phase_records, phase=next_phase)


def _checkpoint_phase_record_map(
    *,
    initial_workspace_summary: JSONObject,
    initial_decisions: list[ResearchOrchestratorDecision],
    phase_records: dict[str, list[JSONObject]],
    final_workspace_snapshot: JSONObject,
    final_decisions: list[ResearchOrchestratorDecision],
) -> dict[str, JSONObject]:
    checkpoint_map: dict[str, JSONObject] = {
        "before_first_action": {
            "workspace_summary": initial_workspace_summary,
            "prior_decisions": [
                decision.model_dump(mode="json") for decision in initial_decisions
            ],
        },
    }
    for checkpoint_key, phase in (
        ("after_pubmed_discovery", "document_ingestion"),
        ("after_pubmed_ingest_extract", "structured_enrichment"),
        ("after_driven_terms_ready", "structured_enrichment"),
        ("after_bootstrap", "chase_round_1"),
        ("before_brief_generation", "completed"),
        ("before_terminal_stop", "completed"),
    ):
        record = _phase_record(phase_records=phase_records, phase=phase)
        if record is not None:
            checkpoint_map[checkpoint_key] = record
    chase_one_record = _phase_record_with_chase(
        phase_records=phase_records, round_number=1
    )
    if chase_one_record is not None:
        checkpoint_map["after_chase_round_1"] = chase_one_record
    chase_two_record = _phase_record_with_chase(
        phase_records=phase_records, round_number=2
    )
    if chase_two_record is not None:
        checkpoint_map["after_chase_round_2"] = chase_two_record
    if "after_bootstrap" not in checkpoint_map:
        for phase in ("deferred_mondo", "completed"):
            record = _phase_record(phase_records=phase_records, phase=phase)
            if record is not None:
                checkpoint_map["after_bootstrap"] = record
                break
    final_record: JSONObject = {
        "workspace_snapshot": final_workspace_snapshot,
        "decisions": [decision.model_dump(mode="json") for decision in final_decisions],
    }
    checkpoint_map.setdefault("before_brief_generation", final_record)
    checkpoint_map.setdefault("before_terminal_stop", final_record)
    return checkpoint_map


__all__ = [
    "_checkpoint_phase_record_map",
    "_checkpoint_target_decision",
    "_decision_prior_to",
    "_find_decision",
    "_find_first_structured_enrichment_decision",
    "_first_comparable_decision",
    "_phase_record",
    "_phase_record_with_chase",
    "_synthetic_chase_stop_target",
]
