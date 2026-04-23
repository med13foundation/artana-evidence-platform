"""Entity chase-round helpers for research-init runs."""

# ruff: noqa: SLF001

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorChaseCandidate,
    ResearchOrchestratorChaseSelection,
    ResearchOrchestratorFilteredChaseCandidate,
)
from artana_evidence_api.low_signal_labels import filtered_low_signal_label_reason
from artana_evidence_api.objective_label_filters import (
    filtered_taxonomic_spillover_reason,
    filtered_underanchored_fragment_reason,
    is_organism_focused_objective,
    looks_like_taxonomic_name,
    text_tokens,
)
from artana_evidence_api.types.common import JSONObject, ResearchSpaceSourcePreferences

if TYPE_CHECKING:
    from artana_evidence_api.graph_client import GraphTransportBundle


from artana_evidence_api.research_init_models import (
    _ChaseRoundPreparation,
    _ChaseRoundResult,
)

_TOTAL_PROGRESS_STEPS = 5
_DOCUMENT_EXTRACTION_CONCURRENCY_LIMIT = 4
_DOCUMENT_EXTRACTION_STAGE_TIMEOUT_SECONDS = 30.0
_PUBMED_QUERY_CONCURRENCY_LIMIT = 2
_MIN_CHASE_ENTITIES = 3
_MAX_CHASE_CANDIDATES = 10
_OBSERVATION_BRIDGE_AGENT_TIMEOUT_SECONDS = 90.0
_OBSERVATION_BRIDGE_EXTRACTION_STAGE_TIMEOUT_SECONDS = 120.0
_OBSERVATION_BRIDGE_BATCH_TIMEOUT_SECONDS = 45.0
_MARRVEL_STRUCTURED_ENRICHMENT_TIMEOUT_SECONDS = 90.0
_OBSERVATION_BRIDGE_BATCH_SIZE = 3
_PUBMED_REPLAY_ARTIFACT_KEY = "research_init_pubmed_replay_bundle"
_STRUCTURED_REPLAY_SOURCE_KEYS = frozenset(
    {
        "clinvar",
        "drugbank",
        "alphafold",
        "clinical_trials",
        "mgi",
        "zfin",
        "marrvel",
    },
)
_STRUCTURED_REPLAY_SOURCE_KIND_TO_KEY = {
    "clinvar_enrichment": "clinvar",
    "drugbank_enrichment": "drugbank",
    "alphafold_enrichment": "alphafold",
    "clinicaltrials_enrichment": "clinical_trials",
    "mgi_enrichment": "mgi",
    "zfin_enrichment": "zfin",
    "marrvel_enrichment": "marrvel",
}
_MIN_GENE_FAMILY_TOKEN_LENGTH = 4



def _enabled_chase_source_keys(
    *,
    sources: ResearchSpaceSourcePreferences,
) -> list[str]:
    chase_source_keys: list[str] = []
    if sources.get("clinvar", True):
        chase_source_keys.append("clinvar")
    if sources.get("drugbank", False):
        chase_source_keys.append("drugbank")
    if sources.get("alphafold", False):
        chase_source_keys.append("alphafold")
    if sources.get("marrvel", True):
        chase_source_keys.append("marrvel")
    return chase_source_keys

def _filtered_chase_reason(
    *,
    display_label: str,
    objective: str | None,
) -> str | None:
    """Return the low-signal filter reason for one chase label, when present."""
    low_signal_reason = filtered_low_signal_label_reason(display_label)
    if low_signal_reason is not None:
        return low_signal_reason
    underanchored_reason = filtered_underanchored_fragment_reason(
        label=display_label,
        objective=objective,
    )
    if underanchored_reason is not None:
        return underanchored_reason
    return filtered_taxonomic_spillover_reason(
        label=display_label,
        objective=objective,
    )

def _filtered_chase_reason_counts(
    filtered_candidates: Sequence[ResearchOrchestratorFilteredChaseCandidate],
) -> JSONObject:
    counts: dict[str, int] = {}
    for candidate in filtered_candidates:
        counts[candidate.filter_reason] = counts.get(candidate.filter_reason, 0) + 1
    return counts

def _focus_token_matches(candidate_token: str, focus_token: str) -> bool:
    if candidate_token == focus_token:
        return True
    if min(len(candidate_token), len(focus_token)) < _MIN_GENE_FAMILY_TOKEN_LENGTH:
        return False
    if not (
        any(character.isdigit() for character in candidate_token)
        and any(character.isdigit() for character in focus_token)
    ):
        return False
    return candidate_token.startswith(focus_token) or focus_token.startswith(
        candidate_token,
    )

def _matching_focus_tokens(
    *,
    display_label: str,
    focus_tokens: frozenset[str],
) -> tuple[str, ...]:
    candidate_tokens = text_tokens(display_label)
    return tuple(
        focus_token
        for focus_token in sorted(focus_tokens)
        if any(
            _focus_token_matches(candidate_token, focus_token)
            for candidate_token in candidate_tokens
        )
    )

def _candidate_focus_rank_key(
    *,
    display_label: str,
    objective: str,
    previous_seed_terms: set[str],
    observed_rank: int,
) -> tuple[int, int, int, int]:
    seed_overlap = _matching_focus_tokens(
        display_label=display_label,
        focus_tokens=frozenset(
            token for term in previous_seed_terms for token in text_tokens(term)
        ),
    )
    objective_overlap = _matching_focus_tokens(
        display_label=display_label,
        focus_tokens=frozenset(text_tokens(objective)),
    )
    organism_bonus = int(
        looks_like_taxonomic_name(display_label)
        and is_organism_focused_objective(objective)
    )
    return (
        (len(seed_overlap) * 2) + len(objective_overlap) + organism_bonus,
        len(seed_overlap),
        len(objective_overlap) + organism_bonus,
        -observed_rank,
    )

def _chase_candidate_evidence_basis(
    *,
    display_label: str,
    objective: str,
    previous_seed_terms: set[str],
) -> str:
    seed_overlap = _matching_focus_tokens(
        display_label=display_label,
        focus_tokens=frozenset(
            token for term in previous_seed_terms for token in text_tokens(term)
        ),
    )
    objective_overlap = _matching_focus_tokens(
        display_label=display_label,
        focus_tokens=frozenset(text_tokens(objective)),
    )
    if seed_overlap or objective_overlap:
        overlap_terms = list(seed_overlap)
        overlap_terms.extend(
            token for token in objective_overlap if token not in set(seed_overlap)
        )
        focus_terms_text = ", ".join(overlap_terms[:4])
        return (
            "The entity was created recently in the graph, was not already present "
            "in the prior seed set, and overlaps the current research focus via "
            f"{focus_terms_text}."
        )
    if looks_like_taxonomic_name(display_label) and is_organism_focused_objective(
        objective
    ):
        return (
            "The entity was created recently in the graph, was not already present "
            "in the prior seed set, and remains in scope because the objective is "
            "organism-focused."
        )
    return (
        "The entity was created recently in the graph and its label was not "
        "already present in the prior seed set."
    )

def _serialize_chase_preparation(
    *,
    round_number: int,
    preparation: _ChaseRoundPreparation,
) -> JSONObject:
    deterministic_selection = preparation.deterministic_selection
    return {
        "round_number": round_number,
        "chase_candidates": [
            candidate.model_dump(mode="json") for candidate in preparation.candidates
        ],
        "filtered_chase_candidates": [
            candidate.model_dump(mode="json")
            for candidate in preparation.filtered_candidates
        ],
        "deterministic_selection": deterministic_selection.model_dump(mode="json"),
        "deterministic_chase_threshold": _MIN_CHASE_ENTITIES,
        "deterministic_candidate_count": len(preparation.candidates),
        "filtered_chase_candidate_count": len(preparation.filtered_candidates),
        "filtered_chase_filter_reason_counts": _filtered_chase_reason_counts(
            preparation.filtered_candidates
        ),
        "deterministic_threshold_met": not deterministic_selection.stop_instead,
        "available_chase_source_keys": (
            list(preparation.candidates[0].available_source_keys)
            if preparation.candidates
            else []
        ),
    }

def _chase_round_action_input(
    *,
    preparation: _ChaseRoundPreparation,
) -> JSONObject:
    selection = preparation.deterministic_selection
    return {
        "selected_entity_ids": list(selection.selected_entity_ids),
        "selected_labels": list(selection.selected_labels),
        "selection_basis": selection.selection_basis,
    }

def _chase_round_metadata(
    *,
    round_number: int,
    preparation: _ChaseRoundPreparation,
    chase_summary: JSONObject | None = None,
) -> JSONObject:
    payload = _serialize_chase_preparation(
        round_number=round_number,
        preparation=preparation,
    )
    if chase_summary is not None:
        payload.update(chase_summary)
    return payload

def _deterministic_chase_selection(
    *,
    candidates: Sequence[ResearchOrchestratorChaseCandidate],
) -> ResearchOrchestratorChaseSelection:
    if len(candidates) < _MIN_CHASE_ENTITIES:
        return ResearchOrchestratorChaseSelection(
            selected_entity_ids=[],
            selected_labels=[],
            stop_instead=True,
            stop_reason="threshold_not_met",
            selection_basis=(
                "Fewer than the deterministic chase threshold of new candidates were "
                "available, so the baseline stops instead of opening another chase "
                "round."
            ),
        )
    return ResearchOrchestratorChaseSelection(
        selected_entity_ids=[candidate.entity_id for candidate in candidates],
        selected_labels=[candidate.display_label for candidate in candidates],
        stop_instead=False,
        stop_reason=None,
        selection_basis=(
            "The deterministic baseline chases the bounded candidate set in "
            "objective-relevance rank order after filtering out prior seed terms."
        ),
    )

def _prepare_chase_round(
    *,
    space_id: UUID,
    objective: str,
    round_number: int,
    created_entity_ids: Sequence[str],
    previous_seed_terms: set[str],
    sources: ResearchSpaceSourcePreferences,
    graph_api_gateway: GraphTransportBundle,
) -> _ChaseRoundPreparation:
    try:
        entity_response = graph_api_gateway.list_entities(
            space_id=space_id,
            ids=list(created_entity_ids[-20:]),
            limit=20,
        )
    except Exception as exc:  # noqa: BLE001
        return _ChaseRoundPreparation(
            candidates=(),
            filtered_candidates=(),
            deterministic_selection=ResearchOrchestratorChaseSelection(
                selected_entity_ids=[],
                selected_labels=[],
                stop_instead=True,
                stop_reason="entity_lookup_failed",
                selection_basis=(
                    "The baseline could not derive chase candidates because entity "
                    "lookup failed."
                ),
            ),
            errors=[f"Chase round {round_number}: entity lookup failed: {exc}"],
        )

    upper_seen = {t.upper() for t in previous_seed_terms}
    available_source_keys = _enabled_chase_source_keys(sources=sources)
    candidate_rows: list[tuple[tuple[int, int, int, int], str, str]] = []
    filtered_candidates: list[ResearchOrchestratorFilteredChaseCandidate] = []
    for observed_rank, entity in enumerate(entity_response.entities, start=1):
        display_label = entity.display_label
        if not display_label:
            continue
        normalized_label = display_label.strip().upper()
        filter_reason = _filtered_chase_reason(
            display_label=display_label,
            objective=objective,
        )
        if filter_reason is not None:
            filtered_candidates.append(
                ResearchOrchestratorFilteredChaseCandidate(
                    entity_id=str(entity.id),
                    display_label=display_label,
                    normalized_label=normalized_label,
                    observed_rank=observed_rank,
                    observed_round=round_number,
                    filter_reason=filter_reason,
                )
            )
            continue
        if normalized_label in upper_seen:
            continue
        candidate_rows.append(
            (
                _candidate_focus_rank_key(
                    display_label=display_label,
                    objective=objective,
                    previous_seed_terms=previous_seed_terms,
                    observed_rank=observed_rank,
                ),
                str(entity.id),
                display_label,
            )
        )
    candidates: list[ResearchOrchestratorChaseCandidate] = []
    for candidate_rank, (_rank_key, entity_id, display_label) in enumerate(
        sorted(candidate_rows, key=lambda row: row[0], reverse=True)[
            :_MAX_CHASE_CANDIDATES
        ],
        start=1,
    ):
        candidates.append(
            ResearchOrchestratorChaseCandidate(
                entity_id=entity_id,
                display_label=display_label,
                normalized_label=display_label.strip().upper(),
                candidate_rank=candidate_rank,
                observed_round=round_number,
                available_source_keys=list(available_source_keys),
                evidence_basis=_chase_candidate_evidence_basis(
                    display_label=display_label,
                    objective=objective,
                    previous_seed_terms=previous_seed_terms,
                ),
                novelty_basis="not_in_previous_seed_terms",
            ),
        )

    deterministic_selection = _deterministic_chase_selection(candidates=candidates)
    return _ChaseRoundPreparation(
        candidates=tuple(candidates),
        filtered_candidates=tuple(filtered_candidates),
        deterministic_selection=deterministic_selection,
        errors=[],
    )

async def _execute_entity_chase_round_terms(
    *,
    space_id: UUID,
    round_number: int,
    new_terms: Sequence[str],
    sources: ResearchSpaceSourcePreferences,
    document_store: object,
    run_registry: object,
    artifact_store: object,
    parent_run: object,
) -> _ChaseRoundResult:
    """Execute the deterministic chase round using one fixed term selection."""

    errors: list[str] = []
    documents_created = 0
    proposals_created = 0

    clinvar_enabled = sources.get("clinvar", True)
    drugbank_enabled = sources.get("drugbank", False)
    alphafold_enabled = sources.get("alphafold", False)
    marrvel_chase_enabled = sources.get("marrvel", True)

    try:
        from artana_evidence_api.research_init_source_enrichment import (
            run_alphafold_enrichment,
            run_clinvar_enrichment,
            run_drugbank_enrichment,
            run_marrvel_enrichment,
        )
    except ImportError:
        run_clinvar_enrichment = None
        run_drugbank_enrichment = None
        run_alphafold_enrichment = None
        run_marrvel_enrichment = None
        errors.append("Chase round: structured enrichment modules not available")

    if run_clinvar_enrichment is not None:
        if clinvar_enabled:
            try:
                clinvar_result = await run_clinvar_enrichment(
                    space_id=space_id,
                    seed_terms=list(new_terms),
                    document_store=document_store,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    parent_run=parent_run,
                )
                documents_created += len(clinvar_result.documents_created)
                proposals_created += len(clinvar_result.proposals_created)
                errors.extend(clinvar_result.errors)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Chase round {round_number} ClinVar: {exc}")

        if drugbank_enabled and run_drugbank_enrichment is not None:
            try:
                drugbank_result = await run_drugbank_enrichment(
                    space_id=space_id,
                    seed_terms=list(new_terms),
                    document_store=document_store,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    parent_run=parent_run,
                )
                documents_created += len(drugbank_result.documents_created)
                proposals_created += len(drugbank_result.proposals_created)
                errors.extend(drugbank_result.errors)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Chase round {round_number} DrugBank: {exc}")

        if alphafold_enabled and run_alphafold_enrichment is not None:
            try:
                alphafold_result = await run_alphafold_enrichment(
                    space_id=space_id,
                    seed_terms=list(new_terms),
                    document_store=document_store,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    parent_run=parent_run,
                )
                documents_created += len(alphafold_result.documents_created)
                proposals_created += len(alphafold_result.proposals_created)
                errors.extend(alphafold_result.errors)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Chase round {round_number} AlphaFold: {exc}")

        if marrvel_chase_enabled and run_marrvel_enrichment is not None:
            try:
                marrvel_result = await run_marrvel_enrichment(
                    space_id=space_id,
                    seed_terms=list(new_terms),
                    document_store=document_store,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    parent_run=parent_run,
                )
                documents_created += len(marrvel_result.documents_created)
                proposals_created += len(marrvel_result.proposals_created)
                errors.extend(marrvel_result.errors)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Chase round {round_number} MARRVEL: {exc}")

    return _ChaseRoundResult(
        new_seed_terms=list(new_terms),
        documents_created=documents_created,
        proposals_created=proposals_created,
        errors=errors,
    )

async def _run_entity_chase_round(  # noqa: PLR0915
    *,
    space_id: UUID,
    objective: str,
    round_number: int,
    created_entity_ids: list[str],
    previous_seed_terms: set[str],
    sources: ResearchSpaceSourcePreferences,
    graph_api_gateway: GraphTransportBundle,
    document_store: object,
    run_registry: object,
    artifact_store: object,
    parent_run: object,
    preparation: _ChaseRoundPreparation | None = None,
) -> _ChaseRoundResult:
    """Run one entity chase round.

    Looks up entities created so far, finds new ones not in previous seeds,
    queries structured sources (ClinVar, DrugBank, AlphaFold) for them.
    """
    if preparation is None:
        preparation = _prepare_chase_round(
            space_id=space_id,
            objective=objective,
            round_number=round_number,
            created_entity_ids=created_entity_ids,
            previous_seed_terms=previous_seed_terms,
            sources=sources,
            graph_api_gateway=graph_api_gateway,
        )
    errors = list(preparation.errors)
    new_terms = list(preparation.deterministic_selection.selected_labels)

    if preparation.deterministic_selection.stop_instead:
        return _ChaseRoundResult(
            new_seed_terms=[
                candidate.display_label for candidate in preparation.candidates
            ],
            documents_created=0,
            proposals_created=0,
            errors=errors,
        )

    logging.getLogger(__name__).info(
        "Chase round %d: %d new terms — %s",
        round_number,
        len(new_terms),
        ", ".join(new_terms[:5]),
    )
    execution_result = await _execute_entity_chase_round_terms(
        space_id=space_id,
        round_number=round_number,
        new_terms=new_terms,
        sources=sources,
        document_store=document_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
        parent_run=parent_run,
    )
    return replace(
        execution_result,
        errors=[*errors, *execution_result.errors],
    )
