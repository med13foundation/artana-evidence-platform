"""Workspace summarization helpers for the full-AI shadow planner."""

from __future__ import annotations

import re
from typing import cast

from artana_evidence_api.full_ai_orchestrator.shadow_planner.models import (
    _CONTEXT_ONLY_SOURCE_KEY_ORDER,
    _GROUNDING_SOURCE_KEY_ORDER,
    _LIVE_EVIDENCE_SOURCE_KEY_ORDER,
    _MAX_CHASE_SELECTION_ENTITIES,
    _MIN_OBJECTIVE_RELEVANCE_TERM_LENGTH,
    _NON_PENDING_SOURCE_STATUSES,
    _OBJECTIVE_RELEVANCE_STOPWORDS,
    _PARP_INHIBITOR_OBJECTIVE_ALIASES,
    _PENDING_SOURCE_PREVIEW_LIMIT,
    _PENDING_SOURCE_STATUSES,
    _RESERVED_SOURCE_KEY_ORDER,
    _STRUCTURED_ENRICHMENT_SOURCE_PREFERENCE,
    _int_or_zero,
    _ObjectiveRoutingHintsSummary,
    _PlannerConstraintsSummary,
    _string_list,
    _SynthesisReadinessSummary,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorActionSpec,
    ResearchOrchestratorActionType,
    ResearchOrchestratorChaseCandidate,
    ResearchOrchestratorChaseSelection,
)
from artana_evidence_api.types.common import (
    JSONObject,
    ResearchSpaceSourcePreferences,
    json_array_or_empty,
    json_int,
    json_object_or_empty,
    json_string_list,
    json_value,
)
from pydantic import ValidationError


def _planner_source_taxonomy(
    *,
    enabled_sources: dict[str, bool],
) -> JSONObject:
    return {
        "live_evidence": [
            source_key
            for source_key in _LIVE_EVIDENCE_SOURCE_KEY_ORDER
            if enabled_sources.get(source_key, False)
        ],
        "context_only": [
            source_key
            for source_key in _CONTEXT_ONLY_SOURCE_KEY_ORDER
            if enabled_sources.get(source_key, False)
        ],
        "grounding": [
            source_key
            for source_key in _GROUNDING_SOURCE_KEY_ORDER
            if enabled_sources.get(source_key, False)
        ],
        "reserved": [
            source_key
            for source_key in _RESERVED_SOURCE_KEY_ORDER
            if enabled_sources.get(source_key, False)
        ],
    }


def _structured_enrichment_source_keys_from_taxonomy(
    *,
    source_taxonomy: JSONObject,
) -> list[str]:
    live_evidence_source_keys = _string_list(source_taxonomy.get("live_evidence"))
    return [
        source_key
        for source_key in _STRUCTURED_ENRICHMENT_SOURCE_PREFERENCE
        if source_key in live_evidence_source_keys
    ]


def _workspace_chase_candidates(
    *,
    workspace_summary: JSONObject,
) -> list[ResearchOrchestratorChaseCandidate]:
    chase_candidates = workspace_summary.get("chase_candidates")
    if not isinstance(chase_candidates, list):
        return []
    candidates: list[ResearchOrchestratorChaseCandidate] = []
    for candidate_payload in chase_candidates:
        if not isinstance(candidate_payload, dict):
            continue
        try:
            candidates.append(
                ResearchOrchestratorChaseCandidate.model_validate(candidate_payload),
            )
        except ValidationError:
            continue
    return candidates


def _workspace_chase_candidate_map(
    *,
    workspace_summary: JSONObject,
) -> dict[str, ResearchOrchestratorChaseCandidate]:
    return {
        candidate.entity_id: candidate
        for candidate in _workspace_chase_candidates(
            workspace_summary=workspace_summary
        )
    }


def _workspace_chase_selection(
    *,
    workspace_summary: JSONObject,
) -> ResearchOrchestratorChaseSelection | None:
    pending_chase_round = json_object_or_empty(
        workspace_summary.get("pending_chase_round"),
    )
    selection = json_object_or_empty(
        pending_chase_round.get("deterministic_selection"),
    )
    if not selection:
        selection = json_object_or_empty(
            workspace_summary.get("deterministic_selection")
        )
    if not selection:
        return None
    try:
        return ResearchOrchestratorChaseSelection.model_validate(selection)
    except Exception:  # noqa: BLE001
        return None


def _objective_relevance_terms(
    *,
    objective: str,
    seed_terms: object,
) -> set[str]:
    terms: set[str] = set()
    seed_texts = (
        [seed_term for seed_term in seed_terms if isinstance(seed_term, str)]
        if isinstance(seed_terms, list)
        else []
    )
    for seed_term in seed_texts:
        normalized_seed = _normalized_objective_text(seed_term)
        if len(normalized_seed) >= _MIN_OBJECTIVE_RELEVANCE_TERM_LENGTH:
            terms.add(normalized_seed)
        terms.update(_objective_relevance_tokens(seed_term))
    terms.update(_objective_relevance_tokens(objective))
    normalized_context = _normalized_objective_text(
        " ".join([objective, *seed_texts]),
    )
    if "parp" in terms and (
        "inhibitor" in terms
        or "inhibition" in terms
        or "parpi" in normalized_context
        or "parpis" in normalized_context
    ):
        terms.update(_PARP_INHIBITOR_OBJECTIVE_ALIASES)
    return terms


def _objective_relevance_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.casefold())
        if len(token) >= _MIN_OBJECTIVE_RELEVANCE_TERM_LENGTH
        and token not in _OBJECTIVE_RELEVANCE_STOPWORDS
    }


def _normalized_objective_text(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def _objective_relevant_chase_labels(
    *,
    workspace_summary: JSONObject,
) -> list[str]:
    objective = (
        str(workspace_summary.get("objective"))
        if isinstance(workspace_summary.get("objective"), str)
        else ""
    )
    relevance_terms = _objective_relevance_terms(
        objective=objective,
        seed_terms=workspace_summary.get("seed_terms"),
    )
    if not relevance_terms:
        return []

    selection = _workspace_chase_selection(workspace_summary=workspace_summary)
    selected_labels = list(selection.selected_labels) if selection is not None else []
    if not selected_labels:
        selected_labels = [
            candidate.display_label
            for candidate in _workspace_chase_candidates(
                workspace_summary=workspace_summary,
            )
        ]

    relevant_labels: list[str] = []
    for label in selected_labels:
        normalized_label = _normalized_objective_text(label)
        label_tokens = _objective_relevance_tokens(label)
        if any(
            term in label_tokens or (len(term.split()) > 1 and term in normalized_label)
            for term in relevance_terms
        ):
            relevant_labels.append(label)
    return relevant_labels


def _chase_decision_posture(
    *,
    workspace_summary: JSONObject,
) -> JSONObject:
    deterministic_threshold_met = bool(
        workspace_summary.get("deterministic_threshold_met"),
    )
    selection = _workspace_chase_selection(workspace_summary=workspace_summary)
    if selection is None or selection.stop_instead or not deterministic_threshold_met:
        return {
            "posture": "stop_threshold_not_met",
            "basis": (
                "The deterministic chase baseline did not produce a continuing "
                "selection for this checkpoint."
            ),
            "objective_relevant_labels": [],
        }

    relevant_labels = _objective_relevant_chase_labels(
        workspace_summary=workspace_summary,
    )
    if relevant_labels:
        return {
            "posture": "continue_objective_relevant",
            "basis": (
                "The deterministic chase threshold is met and at least one selected "
                "candidate directly overlaps the objective or seed terms."
            ),
            "objective_relevant_labels": relevant_labels[
                :_MAX_CHASE_SELECTION_ENTITIES
            ],
        }
    return {
        "posture": "planner_discretion",
        "basis": (
            "The deterministic chase threshold is met, but the selected labels do "
            "not directly overlap objective or seed terms."
        ),
        "objective_relevant_labels": [],
    }


def _chase_decision_posture_value(
    *,
    workspace_summary: JSONObject,
) -> str:
    posture_payload = workspace_summary.get("chase_decision_posture")
    if isinstance(posture_payload, dict) and isinstance(
        posture_payload.get("posture"),
        str,
    ):
        return str(posture_payload["posture"])
    return str(
        _chase_decision_posture(workspace_summary=workspace_summary).get("posture"),
    )


def planner_action_registry_by_state(
    *,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
) -> dict[str, list[JSONObject]]:
    """Group the action registry by planner visibility state."""

    grouped: dict[str, list[JSONObject]] = {
        "live": [],
        "context_only": [],
        "reserved": [],
    }
    for spec in action_registry:
        grouped[spec.planner_state].append(spec.model_dump(mode="json"))
    return grouped


def planner_live_action_types(
    *,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
) -> frozenset[ResearchOrchestratorActionType]:
    """Return planner-selectable action types."""

    return frozenset(
        spec.action_type for spec in action_registry if spec.planner_state == "live"
    )


def _checkpoint_live_action_specs(
    *,
    checkpoint_key: str,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
) -> tuple[ResearchOrchestratorActionSpec, ...]:
    live_specs = tuple(spec for spec in action_registry if spec.planner_state == "live")
    if checkpoint_key in {"after_bootstrap", "after_chase_round_1"}:
        return tuple(
            spec
            for spec in live_specs
            if spec.action_type
            in {
                ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                ResearchOrchestratorActionType.STOP,
            }
        )
    return live_specs


def _structured_enrichment_source_keys(
    *,
    enabled_sources: dict[str, bool],
) -> list[str]:
    source_taxonomy = _planner_source_taxonomy(enabled_sources=enabled_sources)
    structured_source_keys = _structured_enrichment_source_keys_from_taxonomy(
        source_taxonomy=source_taxonomy,
    )
    structured_source_set = set(structured_source_keys)
    remaining_sources = sorted(
        source_key
        for source_key in json_string_list(source_taxonomy.get("live_evidence"))
        if source_key != "pubmed" and source_key not in structured_source_set
    )
    return [*structured_source_keys, *remaining_sources]


def _pubmed_ingest_pending(
    *,
    source_status_summary: JSONObject,
) -> bool:
    pubmed_summary = source_status_summary.get("pubmed")
    if not isinstance(pubmed_summary, dict):
        return False
    documents_discovered = _int_or_zero(pubmed_summary.get("documents_discovered"))
    documents_selected = _int_or_zero(pubmed_summary.get("documents_selected"))
    documents_ingested = _int_or_zero(pubmed_summary.get("documents_ingested"))
    if documents_selected > documents_ingested:
        return True
    return documents_discovered > 0 and documents_ingested == 0


def _objective_routing_tags(objective: str) -> list[str]:
    lowered = objective.casefold()
    tags: list[str] = []
    if any(
        token in lowered
        for token in (
            "drug",
            "therapy",
            "therapeut",
            "treatment",
            "inhibitor",
            "response",
            "repurpos",
            "target",
        )
    ):
        tags.append("drug_mechanism")
    if any(
        token in lowered
        for token in (
            "trial",
            "study",
            "studies",
            "recruit",
            "enrollment",
            "intervention",
            "outcome",
            "human",
        )
    ):
        tags.append("trial_evidence")
    if any(
        token in lowered
        for token in (
            "variant",
            "mutation",
            "pathogenic",
            "allele",
            "clinvar",
        )
    ):
        tags.append("variant_interpretation")
    if any(
        token in lowered
        for token in (
            "structure",
            "structural",
            "fold",
            "domain",
            "interface",
            "protein",
        )
    ):
        tags.append("protein_structure")
    if any(
        token in lowered
        for token in (
            "development",
            "developmental",
            "congenital",
            "phenotype",
            "syndrome",
            "model organism",
            "mouse",
            "mice",
            "zebrafish",
        )
    ):
        tags.append("model_organism")
    return tags


def _objective_preferred_structured_sources(
    *,
    objective: str,
    structured_enrichment_sources: list[str],
) -> list[str]:
    tags = _objective_routing_tags(objective)
    preferred_sources: list[str] = []
    if "trial_evidence" in tags:
        preferred_sources.extend(("clinical_trials", "drugbank"))
    if "drug_mechanism" in tags:
        preferred_sources.extend(("drugbank", "clinical_trials"))
    if "variant_interpretation" in tags:
        preferred_sources.extend(("clinvar", "alphafold", "marrvel"))
    if "protein_structure" in tags:
        preferred_sources.extend(("alphafold", "clinvar"))
    if "model_organism" in tags:
        preferred_sources.extend(("marrvel", "mgi", "zfin", "clinvar"))

    ordered_sources: list[str] = []
    seen_sources: set[str] = set()
    for source_key in [*preferred_sources, *structured_enrichment_sources]:
        if (
            source_key in structured_enrichment_sources
            and source_key not in seen_sources
        ):
            ordered_sources.append(source_key)
            seen_sources.add(source_key)
    return ordered_sources


def _structured_enrichment_pending_source_keys(
    *,
    workspace_summary: JSONObject,
    structured_enrichment_sources: list[str],
) -> list[str]:
    source_status_summary = workspace_summary.get("source_status_summary")
    source_status_lookup = (
        source_status_summary if isinstance(source_status_summary, dict) else {}
    )
    completed_sources: set[str] = set()
    for source_key, summary in source_status_lookup.items():
        if not isinstance(source_key, str) or not isinstance(summary, dict):
            continue
        raw_status = summary.get("status")
        if not isinstance(raw_status, str):
            continue
        if raw_status.casefold() in _NON_PENDING_SOURCE_STATUSES:
            completed_sources.add(source_key)

    for decision in _workspace_prior_decisions(workspace_summary):
        if not _matches_action_type(
            decision.get("action_type"),
            ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
        ):
            continue
        source_key = decision.get("source_key")
        if not isinstance(source_key, str):
            continue
        decision_status = decision.get("status")
        if isinstance(decision_status, str) and (
            decision_status.casefold() in _NON_PENDING_SOURCE_STATUSES
        ):
            completed_sources.add(source_key)

    pending_sources: list[str] = []
    for source_key in structured_enrichment_sources:
        source_summary = source_status_lookup.get(source_key)
        raw_status = (
            source_summary.get("status") if isinstance(source_summary, dict) else None
        )
        normalized_status = (
            raw_status.casefold() if isinstance(raw_status, str) else None
        )
        if normalized_status in _NON_PENDING_SOURCE_STATUSES:
            continue
        if (
            normalized_status in _PENDING_SOURCE_STATUSES
            or source_key not in completed_sources
        ):
            pending_sources.append(source_key)
    return pending_sources


def _objective_routing_hints(
    *,
    objective: str,
    structured_enrichment_sources: list[str],
    pending_structured_sources: list[str],
) -> _ObjectiveRoutingHintsSummary:
    objective_tags = _objective_routing_tags(objective)
    preferred_structured_sources = _objective_preferred_structured_sources(
        objective=objective,
        structured_enrichment_sources=structured_enrichment_sources,
    )
    preferred_pending_structured_sources = [
        source_key
        for source_key in preferred_structured_sources
        if source_key in pending_structured_sources
    ]
    if not preferred_pending_structured_sources:
        preferred_pending_structured_sources = list(pending_structured_sources)

    summary = (
        "No special objective routing hint was detected, so once the run reaches "
        "structured enrichment it should fall back to the deterministic "
        "structured-source order."
    )
    if "trial_evidence" in objective_tags:
        summary = (
            "Once the run reaches structured enrichment, the objective emphasizes "
            "trial activity or intervention evidence, so human-study sources should "
            "lead the remaining structured follow-up."
        )
    elif "drug_mechanism" in objective_tags:
        summary = (
            "Once the run reaches structured enrichment, the objective emphasizes "
            "therapy or inhibitor questions, so drug and target mechanism sources "
            "should lead the remaining structured follow-up."
        )
    elif "model_organism" in objective_tags:
        summary = (
            "Once the run reaches structured enrichment, the objective emphasizes "
            "developmental or phenotype context, so model organism sources should "
            "lead the remaining structured follow-up."
        )
    elif "variant_interpretation" in objective_tags:
        summary = (
            "Once the run reaches structured enrichment, the objective emphasizes "
            "variant interpretation, so ClinVar-style evidence should lead the "
            "remaining structured follow-up."
        )
    elif "protein_structure" in objective_tags:
        summary = (
            "Once the run reaches structured enrichment, the objective emphasizes "
            "protein structure or domain context, so structure-grounded sources "
            "should lead the remaining structured follow-up."
        )

    return {
        "objective_tags": objective_tags,
        "preferred_structured_sources": preferred_structured_sources,
        "preferred_pending_structured_sources": preferred_pending_structured_sources,
        "summary": summary,
    }


def _checkpoint_objective_routing_hints(
    *,
    checkpoint_key: str,
    objective: str,
    structured_enrichment_sources: list[str],
    pending_structured_sources: list[str],
    pubmed_ingest_pending: bool,
) -> _ObjectiveRoutingHintsSummary:
    hints = _objective_routing_hints(
        objective=objective,
        structured_enrichment_sources=structured_enrichment_sources,
        pending_structured_sources=pending_structured_sources,
    )
    if checkpoint_key in {"after_pubmed_ingest_extract", "after_driven_terms_ready"}:
        return hints
    if checkpoint_key == "after_pubmed_discovery" and pubmed_ingest_pending:
        return {
            **hints,
            "preferred_pending_structured_sources": [],
            "summary": (
                "Structured-source routing hints are recorded for later, but they "
                "stay inactive until PubMed ingest and extraction are complete."
            ),
        }
    return {
        **hints,
        "preferred_pending_structured_sources": [],
        "summary": (
            "Structured-source routing hints are recorded for later checkpoints and "
            "should not drive the current step selection yet."
        ),
    }


def _workspace_prior_decisions(workspace_summary: JSONObject) -> list[JSONObject]:
    raw_prior_decisions = workspace_summary.get("prior_decisions")
    if not isinstance(raw_prior_decisions, list):
        return []
    return [
        cast("JSONObject", decision)
        for decision in raw_prior_decisions
        if isinstance(decision, dict)
    ]


def _matches_action_type(
    raw_action_type: object,
    action_type: ResearchOrchestratorActionType,
) -> bool:
    return raw_action_type in {action_type, action_type.value}


def _preferred_structured_enrichment_source_from_workspace(
    *,
    workspace_summary: JSONObject,
    structured_enrichment_sources: list[str],
) -> str | None:
    objective_routing_hints = _workspace_objective_routing_hints(
        workspace_summary=workspace_summary,
    )
    for source_key in objective_routing_hints["preferred_pending_structured_sources"]:
        if source_key in structured_enrichment_sources:
            return source_key
    pending_sources = _structured_enrichment_pending_source_keys(
        workspace_summary=workspace_summary,
        structured_enrichment_sources=structured_enrichment_sources,
    )
    if pending_sources:
        return pending_sources[0]
    if structured_enrichment_sources:
        return structured_enrichment_sources[0]
    return None


def _chase_round_threshold_not_met(workspace_summary: JSONObject) -> bool:
    for decision in _workspace_prior_decisions(workspace_summary):
        if not _matches_action_type(
            decision.get("action_type"),
            ResearchOrchestratorActionType.RUN_CHASE_ROUND,
        ):
            continue
        if decision.get("status") != "skipped":
            continue
        if decision.get("stop_reason") == "threshold_not_met":
            return True
    return False


def shadow_planner_synthesis_readiness(
    *,
    workspace_summary: JSONObject,
) -> _SynthesisReadinessSummary:
    """Summarize whether the workspace is ready to move to synthesis."""

    counts = json_object_or_empty(workspace_summary.get("counts"))
    documents_ingested = _int_or_zero(counts.get("documents_ingested"))
    proposal_count = _int_or_zero(counts.get("proposal_count"))
    pending_question_count = _int_or_zero(counts.get("pending_question_count"))
    evidence_gap_count = _int_or_zero(counts.get("evidence_gap_count"))
    contradiction_count = _int_or_zero(counts.get("contradiction_count"))
    error_count = _int_or_zero(counts.get("error_count"))
    pending_structured_source_keys = (
        _workspace_pending_structured_enrichment_source_keys(
            workspace_summary=workspace_summary,
        )
    )
    grounded_evidence_present = documents_ingested > 0 and proposal_count > 0
    no_pending_questions = pending_question_count == 0
    no_evidence_gaps = evidence_gap_count == 0
    no_contradictions = contradiction_count == 0
    no_errors = error_count == 0
    no_pending_structured_sources = len(pending_structured_source_keys) == 0
    chase_round_threshold_not_met = _chase_round_threshold_not_met(workspace_summary)
    ready_for_brief = (
        grounded_evidence_present
        and no_pending_questions
        and no_evidence_gaps
        and no_contradictions
        and no_errors
        and no_pending_structured_sources
    )
    if chase_round_threshold_not_met:
        summary = (
            "A chase round was already skipped because the threshold was not met, so "
            "the workflow should synthesize instead of opening another chase round."
        )
    elif ready_for_brief:
        summary = (
            "Grounded evidence is already present, structured enrichment is exhausted, "
            "and there are no recorded pending questions, evidence gaps, "
            "contradictions, or errors."
        )
    else:
        missing_signals: list[str] = []
        if not grounded_evidence_present:
            missing_signals.append("grounded evidence is still limited")
        if not no_pending_structured_sources:
            pending_text = ", ".join(
                pending_structured_source_keys[:_PENDING_SOURCE_PREVIEW_LIMIT]
            )
            if len(pending_structured_source_keys) > _PENDING_SOURCE_PREVIEW_LIMIT:
                pending_text = f"{pending_text}, ..."
            missing_signals.append(
                f"structured sources remain pending ({pending_text})",
            )
        if not no_pending_questions:
            missing_signals.append("pending questions remain open")
        if not no_evidence_gaps:
            missing_signals.append("evidence gaps remain open")
        if not no_contradictions:
            missing_signals.append("active contradictions still need review")
        if not no_errors:
            missing_signals.append("errors are still recorded in the workspace")
        blockers_text = (
            "; ".join(missing_signals)
            or "another bounded retrieval step may still help"
        )
        summary = (
            "Another bounded retrieval step still has qualitative value because "
            f"{blockers_text}."
        )
    return {
        "ready_for_brief": ready_for_brief,
        "chase_round_threshold_not_met": chase_round_threshold_not_met,
        "grounded_evidence_present": grounded_evidence_present,
        "no_pending_questions": no_pending_questions,
        "no_evidence_gaps": no_evidence_gaps,
        "no_contradictions": no_contradictions,
        "no_errors": no_errors,
        "no_pending_structured_sources": no_pending_structured_sources,
        "pending_structured_source_keys": pending_structured_source_keys,
        "summary": summary,
    }


def build_shadow_planner_workspace_summary(  # noqa: PLR0913
    *,
    checkpoint_key: str,
    mode: str = "shadow",
    objective: str,
    seed_terms: list[str],
    sources: ResearchSpaceSourcePreferences,
    max_depth: int,
    max_hypotheses: int,
    workspace_snapshot: JSONObject,
    prior_decisions: list[JSONObject],
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
) -> JSONObject:
    """Build the planner-readable workspace snapshot for one planner mode."""

    source_results = workspace_snapshot.get("source_results")
    enabled_sources = {
        key: value for key, value in sources.items() if isinstance(value, bool)
    }
    source_taxonomy = _planner_source_taxonomy(enabled_sources=enabled_sources)
    checkpoint_round = workspace_snapshot.get("current_round", 0)
    source_status_summary: JSONObject = {}
    if isinstance(source_results, dict):
        for source_key, source_summary in source_results.items():
            if not isinstance(source_key, str) or not isinstance(source_summary, dict):
                continue
            source_status_summary[source_key] = {
                "status": source_summary.get("status"),
                "documents_discovered": source_summary.get("documents_discovered"),
                "documents_selected": source_summary.get("documents_selected"),
                "documents_ingested": source_summary.get("documents_ingested"),
                "records_processed": source_summary.get("records_processed"),
                "observations_created": source_summary.get("observations_created"),
            }

    pending_questions = workspace_snapshot.get("pending_questions")
    errors = workspace_snapshot.get("errors")
    evidence_gaps = workspace_snapshot.get("evidence_gaps")
    contradictions = workspace_snapshot.get("contradictions")
    grouped_actions = planner_action_registry_by_state(action_registry=action_registry)
    checkpoint_live_specs = _checkpoint_live_action_specs(
        checkpoint_key=checkpoint_key,
        action_registry=action_registry,
    )
    live_action_types = [spec.action_type.value for spec in checkpoint_live_specs]
    source_required_action_types = [
        spec.action_type.value for spec in checkpoint_live_specs if spec.source_bound
    ]
    control_action_types_without_source_key = [
        spec.action_type.value
        for spec in checkpoint_live_specs
        if not spec.source_bound
    ]
    structured_enrichment_source_keys = _structured_enrichment_source_keys(
        enabled_sources=enabled_sources,
    )
    pending_structured_enrichment_source_keys = (
        _structured_enrichment_pending_source_keys(
            workspace_summary=workspace_snapshot,
            structured_enrichment_sources=structured_enrichment_source_keys,
        )
    )
    pubmed_ingest_pending = _pubmed_ingest_pending(
        source_status_summary=source_status_summary,
    )
    objective_routing_hints = _checkpoint_objective_routing_hints(
        checkpoint_key=checkpoint_key,
        objective=objective,
        structured_enrichment_sources=structured_enrichment_source_keys,
        pending_structured_sources=pending_structured_enrichment_source_keys,
        pubmed_ingest_pending=pubmed_ingest_pending,
    )
    pending_chase_round = json_object_or_empty(
        workspace_snapshot.get("pending_chase_round"),
    )
    chase_candidates = json_array_or_empty(pending_chase_round.get("chase_candidates"))
    filtered_chase_candidates = json_array_or_empty(
        pending_chase_round.get("filtered_chase_candidates"),
    )
    deterministic_chase_threshold = (
        json_int(pending_chase_round.get("deterministic_chase_threshold"))
        if isinstance(pending_chase_round.get("deterministic_chase_threshold"), int)
        else 0
    )
    deterministic_candidate_count = (
        json_int(pending_chase_round.get("deterministic_candidate_count"))
        if isinstance(pending_chase_round.get("deterministic_candidate_count"), int)
        else 0
    )
    deterministic_threshold_met = bool(
        pending_chase_round.get("deterministic_threshold_met"),
    )
    available_chase_source_keys = json_string_list(
        pending_chase_round.get("available_chase_source_keys"),
    )
    filtered_chase_candidate_count = (
        json_int(pending_chase_round.get("filtered_chase_candidate_count"))
        if isinstance(pending_chase_round.get("filtered_chase_candidate_count"), int)
        else 0
    )
    filtered_chase_filter_reason_counts = json_object_or_empty(
        pending_chase_round.get("filtered_chase_filter_reason_counts"),
    )
    deterministic_selection = json_object_or_empty(
        pending_chase_round.get("deterministic_selection"),
    )

    summary: JSONObject = {
        "mode": mode,
        "checkpoint_key": checkpoint_key,
        "objective": objective,
        "seed_terms": list(seed_terms),
        "enabled_sources": enabled_sources,
        "current_round": checkpoint_round if isinstance(checkpoint_round, int) else 0,
        "counts": {
            "documents_ingested": workspace_snapshot.get("documents_ingested", 0),
            "proposal_count": workspace_snapshot.get("proposal_count", 0),
            "pending_question_count": (
                len(pending_questions) if isinstance(pending_questions, list) else 0
            ),
            "error_count": len(errors) if isinstance(errors, list) else 0,
            "evidence_gap_count": (
                len(evidence_gaps) if isinstance(evidence_gaps, list) else 0
            ),
            "contradiction_count": (
                len(contradictions) if isinstance(contradictions, list) else 0
            ),
        },
        "source_status_summary": source_status_summary,
        "top_evidence_gaps": (
            list(evidence_gaps[:5]) if isinstance(evidence_gaps, list) else []
        ),
        "active_contradictions": (
            list(contradictions[:5]) if isinstance(contradictions, list) else []
        ),
        "prior_decisions": list(prior_decisions[-10:]),
        "remaining_hard_limits": {
            "max_total_rounds": min(max_depth, 2) + 1,
            "max_chase_rounds": min(max_depth, 2),
            "max_hypotheses": max_hypotheses,
        },
        "source_taxonomy": source_taxonomy,
        "chase_candidates": chase_candidates,
        "filtered_chase_candidates": filtered_chase_candidates,
        "deterministic_chase_threshold": deterministic_chase_threshold,
        "deterministic_candidate_count": deterministic_candidate_count,
        "filtered_chase_candidate_count": filtered_chase_candidate_count,
        "filtered_chase_filter_reason_counts": filtered_chase_filter_reason_counts,
        "deterministic_threshold_met": deterministic_threshold_met,
        "available_chase_source_keys": available_chase_source_keys,
        "deterministic_selection": deterministic_selection,
        "planner_actions": grouped_actions,
        "planner_constraints": {
            "live_action_types": live_action_types,
            "source_required_action_types": source_required_action_types,
            "control_action_types_without_source_key": (
                control_action_types_without_source_key
            ),
            "pubmed_source_key": "pubmed",
            "pubmed_ingest_pending": pubmed_ingest_pending,
            "source_taxonomy": source_taxonomy,
            "structured_enrichment_source_keys": structured_enrichment_source_keys,
            "pending_structured_enrichment_source_keys": (
                pending_structured_enrichment_source_keys
            ),
        },
        "objective_routing_hints": json_value(objective_routing_hints),
    }
    summary["chase_decision_posture"] = _chase_decision_posture(
        workspace_summary=summary,
    )
    summary["synthesis_readiness"] = json_value(
        shadow_planner_synthesis_readiness(
            workspace_summary=summary,
        ),
    )
    return summary


def _normalize_shadow_planner_workspace_summary(
    *,
    checkpoint_key: str,
    objective: str,
    workspace_summary: JSONObject,
    sources: ResearchSpaceSourcePreferences,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
) -> JSONObject:
    normalized = dict(workspace_summary)
    enabled_sources = {
        key: value
        for key, value in sources.items()
        if isinstance(key, str) and isinstance(value, bool)
    }
    normalized["checkpoint_key"] = checkpoint_key
    normalized.setdefault("objective", objective)
    normalized.setdefault("enabled_sources", enabled_sources)

    raw_counts = normalized.get("counts")
    counts = dict(raw_counts) if isinstance(raw_counts, dict) else {}
    normalized["counts"] = {
        "documents_ingested": _int_or_zero(counts.get("documents_ingested")),
        "proposal_count": _int_or_zero(counts.get("proposal_count")),
        "pending_question_count": _int_or_zero(counts.get("pending_question_count")),
        "error_count": _int_or_zero(counts.get("error_count")),
        "evidence_gap_count": _int_or_zero(counts.get("evidence_gap_count")),
        "contradiction_count": _int_or_zero(counts.get("contradiction_count")),
    }
    normalized.setdefault("source_status_summary", {})
    normalized.setdefault("top_evidence_gaps", [])
    normalized.setdefault("active_contradictions", [])
    normalized.setdefault("prior_decisions", [])
    normalized.setdefault("remaining_hard_limits", {})
    source_taxonomy = _planner_source_taxonomy(enabled_sources=enabled_sources)
    normalized["source_taxonomy"] = source_taxonomy
    normalized.setdefault(
        "planner_actions",
        planner_action_registry_by_state(action_registry=action_registry),
    )
    normalized.setdefault(
        "planner_constraints",
        json_object_or_empty(
            _planner_constraints_from_action_registry(
                action_registry=action_registry,
                enabled_sources=enabled_sources,
            )
        ),
    )
    normalized["objective_routing_hints"] = json_value(
        _checkpoint_objective_routing_hints(
            checkpoint_key=checkpoint_key,
            objective=str(normalized.get("objective", objective)),
            structured_enrichment_sources=_structured_enrichment_source_keys(
                enabled_sources=enabled_sources,
            ),
            pending_structured_sources=_structured_enrichment_pending_source_keys(
                workspace_summary=normalized,
                structured_enrichment_sources=_structured_enrichment_source_keys(
                    enabled_sources=enabled_sources,
                ),
            ),
            pubmed_ingest_pending=_pubmed_ingest_pending(
                source_status_summary=(
                    normalized["source_status_summary"]
                    if isinstance(normalized["source_status_summary"], dict)
                    else {}
                ),
            ),
        )
    )
    normalized["planner_constraints"] = {
        **json_object_or_empty(
            _workspace_planner_constraints(workspace_summary=normalized)
        ),
        "source_taxonomy": source_taxonomy,
        "pubmed_ingest_pending": _pubmed_ingest_pending(
            source_status_summary=(
                normalized["source_status_summary"]
                if isinstance(normalized["source_status_summary"], dict)
                else {}
            ),
        ),
        "pending_structured_enrichment_source_keys": (
            _structured_enrichment_pending_source_keys(
                workspace_summary=normalized,
                structured_enrichment_sources=_workspace_structured_enrichment_source_keys(
                    workspace_summary=normalized,
                ),
            )
        ),
    }
    normalized["synthesis_readiness"] = json_value(
        shadow_planner_synthesis_readiness(
            workspace_summary=normalized,
        ),
    )
    return normalized


def _workspace_planner_constraints(
    *,
    workspace_summary: JSONObject,
) -> _PlannerConstraintsSummary:
    raw_constraints = workspace_summary.get("planner_constraints")
    if not isinstance(raw_constraints, dict):
        return {
            "live_action_types": [],
            "source_required_action_types": [],
            "control_action_types_without_source_key": [],
            "pubmed_source_key": "pubmed",
            "pubmed_ingest_pending": False,
            "source_taxonomy": {
                "live_evidence": [],
                "context_only": [],
                "grounding": [],
                "reserved": [],
            },
            "structured_enrichment_source_keys": [],
            "pending_structured_enrichment_source_keys": [],
        }
    raw_source_taxonomy = raw_constraints.get("source_taxonomy")
    source_taxonomy = (
        {
            "live_evidence": _string_list(raw_source_taxonomy.get("live_evidence")),
            "context_only": _string_list(raw_source_taxonomy.get("context_only")),
            "grounding": _string_list(raw_source_taxonomy.get("grounding")),
            "reserved": _string_list(raw_source_taxonomy.get("reserved")),
        }
        if isinstance(raw_source_taxonomy, dict)
        else {
            "live_evidence": [],
            "context_only": [],
            "grounding": [],
            "reserved": [],
        }
    )
    return {
        "live_action_types": _string_list(
            raw_constraints.get("live_action_types"),
        ),
        "source_required_action_types": _string_list(
            raw_constraints.get("source_required_action_types"),
        ),
        "control_action_types_without_source_key": _string_list(
            raw_constraints.get("control_action_types_without_source_key"),
        ),
        "pubmed_source_key": (
            str(raw_constraints.get("pubmed_source_key"))
            if isinstance(raw_constraints.get("pubmed_source_key"), str)
            else "pubmed"
        ),
        "pubmed_ingest_pending": bool(
            raw_constraints.get("pubmed_ingest_pending", False)
        ),
        "source_taxonomy": json_object_or_empty(source_taxonomy),
        "structured_enrichment_source_keys": _string_list(
            raw_constraints.get("structured_enrichment_source_keys"),
        ),
        "pending_structured_enrichment_source_keys": _string_list(
            raw_constraints.get("pending_structured_enrichment_source_keys"),
        ),
    }


def _workspace_structured_enrichment_source_keys(
    *,
    workspace_summary: JSONObject,
) -> list[str]:
    planner_constraints = _workspace_planner_constraints(
        workspace_summary=workspace_summary,
    )
    return planner_constraints["structured_enrichment_source_keys"]


def _workspace_pending_structured_enrichment_source_keys(
    *,
    workspace_summary: JSONObject,
) -> list[str]:
    planner_constraints = _workspace_planner_constraints(
        workspace_summary=workspace_summary,
    )
    return planner_constraints["pending_structured_enrichment_source_keys"]


def _workspace_objective_routing_hints(
    *,
    workspace_summary: JSONObject,
) -> _ObjectiveRoutingHintsSummary:
    raw_hints = workspace_summary.get("objective_routing_hints")
    if not isinstance(raw_hints, dict):
        structured_sources = _workspace_structured_enrichment_source_keys(
            workspace_summary=workspace_summary,
        )
        pending_sources = _structured_enrichment_pending_source_keys(
            workspace_summary=workspace_summary,
            structured_enrichment_sources=structured_sources,
        )
        return _objective_routing_hints(
            objective=str(workspace_summary.get("objective", "")),
            structured_enrichment_sources=structured_sources,
            pending_structured_sources=pending_sources,
        )
    return {
        "objective_tags": _string_list(raw_hints.get("objective_tags")),
        "preferred_structured_sources": _string_list(
            raw_hints.get("preferred_structured_sources"),
        ),
        "preferred_pending_structured_sources": _string_list(
            raw_hints.get("preferred_pending_structured_sources"),
        ),
        "summary": (
            str(raw_hints.get("summary"))
            if isinstance(raw_hints.get("summary"), str)
            else ""
        ),
    }


def _planner_constraints_from_action_registry(
    *,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
    enabled_sources: dict[str, bool],
) -> _PlannerConstraintsSummary:
    source_taxonomy = _planner_source_taxonomy(enabled_sources=enabled_sources)
    structured_enrichment_source_keys = (
        _structured_enrichment_source_keys_from_taxonomy(
            source_taxonomy=source_taxonomy,
        )
    )
    return {
        "live_action_types": [
            spec.action_type.value
            for spec in action_registry
            if spec.planner_state == "live"
        ],
        "source_required_action_types": [
            spec.action_type.value
            for spec in action_registry
            if spec.planner_state == "live" and spec.source_bound
        ],
        "control_action_types_without_source_key": [
            spec.action_type.value
            for spec in action_registry
            if spec.planner_state == "live" and not spec.source_bound
        ],
        "pubmed_source_key": "pubmed",
        "pubmed_ingest_pending": False,
        "source_taxonomy": source_taxonomy,
        "structured_enrichment_source_keys": structured_enrichment_source_keys,
        "pending_structured_enrichment_source_keys": (
            structured_enrichment_source_keys
        ),
    }
