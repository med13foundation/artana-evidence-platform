"""Guarded-mode observer hooks for research-init runs."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorChaseSelection,
)
from artana_evidence_api.research_init_models import (
    ResearchInitProgressObserver,
    _ChaseRoundPreparation,
)
from artana_evidence_api.types.common import JSONObject
from pydantic import ValidationError

if TYPE_CHECKING:
    from artana_evidence_api.harness_runtime import HarnessExecutionServices

__all__ = [
    "coerce_guarded_chase_selection",
    "maybe_select_guarded_chase_round_selection",
    "maybe_select_guarded_structured_enrichment_sources",
    "maybe_skip_guarded_chase_round",
    "maybe_verify_guarded_brief_generation",
    "maybe_verify_guarded_structured_enrichment",
]


def _workspace_snapshot(
    *,
    services: HarnessExecutionServices,
    space_id: UUID,
    run_id: str,
) -> JSONObject:
    workspace_record = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=run_id,
    )
    return workspace_record.snapshot if workspace_record is not None else {}


async def maybe_skip_guarded_chase_round(
    *,
    services: HarnessExecutionServices,
    space_id: UUID,
    run_id: str,
    next_round_number: int,
    progress_observer: ResearchInitProgressObserver | None,
) -> bool:
    if progress_observer is None:
        return False
    method = getattr(progress_observer, "maybe_skip_chase_round", None)
    if method is None:
        return False
    result = method(
        next_round_number=next_round_number,
        workspace_snapshot=_workspace_snapshot(
            services=services,
            space_id=space_id,
            run_id=run_id,
        ),
    )
    if inspect.isawaitable(result):
        return bool(await result)
    return bool(result)


def coerce_guarded_chase_selection(
    *,
    selection_payload: object,
    preparation: _ChaseRoundPreparation,
) -> ResearchOrchestratorChaseSelection | None:
    if isinstance(selection_payload, ResearchOrchestratorChaseSelection):
        selection = selection_payload
    elif isinstance(selection_payload, dict):
        try:
            selection = ResearchOrchestratorChaseSelection.model_validate(
                selection_payload
            )
        except ValidationError:
            return None
    else:
        return None
    return _validate_guarded_chase_selection(
        selection=selection,
        preparation=preparation,
    )


def _validate_guarded_chase_selection(  # noqa: PLR0911
    *,
    selection: ResearchOrchestratorChaseSelection,
    preparation: _ChaseRoundPreparation,
) -> ResearchOrchestratorChaseSelection | None:
    if selection.selection_basis.strip() == "":
        return None
    if selection.stop_instead:
        if selection.selected_entity_ids or selection.selected_labels:
            return None
        if selection.stop_reason is None or selection.stop_reason.strip() == "":
            return None
        return selection

    if (
        not selection.selected_entity_ids
        or not selection.selected_labels
        or len(selection.selected_entity_ids) != len(selection.selected_labels)
    ):
        return None

    candidate_map = {
        candidate.entity_id: candidate for candidate in preparation.candidates
    }
    deterministic_selection = preparation.deterministic_selection
    deterministic_entity_order = {
        entity_id: index
        for index, entity_id in enumerate(
            deterministic_selection.selected_entity_ids,
        )
    }
    deterministic_label_by_entity_id = dict(
        zip(
            deterministic_selection.selected_entity_ids,
            deterministic_selection.selected_labels,
            strict=True,
        )
    )
    if len(set(selection.selected_entity_ids)) != len(selection.selected_entity_ids):
        return None
    previous_index = -1
    for entity_id, selected_label in zip(
        selection.selected_entity_ids,
        selection.selected_labels,
        strict=True,
    ):
        candidate = candidate_map.get(entity_id)
        deterministic_index = deterministic_entity_order.get(entity_id)
        deterministic_label = deterministic_label_by_entity_id.get(entity_id)
        if (
            candidate is None
            or candidate.display_label != selected_label
            or deterministic_index is None
            or deterministic_label != selected_label
            or deterministic_index <= previous_index
        ):
            return None
        previous_index = deterministic_index
    return selection


async def maybe_select_guarded_chase_round_selection(
    *,
    services: HarnessExecutionServices,
    space_id: UUID,
    run_id: str,
    round_number: int,
    preparation: _ChaseRoundPreparation,
    progress_observer: ResearchInitProgressObserver | None,
) -> ResearchOrchestratorChaseSelection | None:
    if progress_observer is None:
        return None
    method = getattr(progress_observer, "maybe_select_chase_round_selection", None)
    if method is None:
        return None
    result = method(
        round_number=round_number,
        chase_candidates=preparation.candidates,
        deterministic_selection=preparation.deterministic_selection,
        workspace_snapshot=_workspace_snapshot(
            services=services,
            space_id=space_id,
            run_id=run_id,
        ),
    )
    if inspect.isawaitable(result):
        result = await result
    return coerce_guarded_chase_selection(
        selection_payload=result,
        preparation=preparation,
    )


async def maybe_select_guarded_structured_enrichment_sources(
    *,
    services: HarnessExecutionServices,
    space_id: UUID,
    run_id: str,
    available_source_keys: list[str],
    progress_observer: ResearchInitProgressObserver | None,
) -> tuple[str, ...] | None:
    if progress_observer is None or len(available_source_keys) <= 1:
        return None
    method = getattr(
        progress_observer, "maybe_select_structured_enrichment_sources", None
    )
    if method is None:
        return None
    result = method(
        available_source_keys=tuple(available_source_keys),
        workspace_snapshot=_workspace_snapshot(
            services=services,
            space_id=space_id,
            run_id=run_id,
        ),
    )
    resolved_result = await result if inspect.isawaitable(result) else result
    if not isinstance(resolved_result, tuple):
        return None
    valid_source_keys: list[str] = []
    seen_source_keys: set[str] = set()
    for source_key in resolved_result:
        if not isinstance(source_key, str):
            continue
        if source_key not in available_source_keys:
            continue
        if source_key in seen_source_keys:
            continue
        valid_source_keys.append(source_key)
        seen_source_keys.add(source_key)
    if not valid_source_keys:
        return None
    return tuple(valid_source_keys)


async def maybe_verify_guarded_structured_enrichment(
    *,
    services: HarnessExecutionServices,
    space_id: UUID,
    run_id: str,
    progress_observer: ResearchInitProgressObserver | None,
) -> bool:
    if progress_observer is None:
        return False
    method = getattr(progress_observer, "verify_guarded_structured_enrichment", None)
    if method is None:
        return False
    result = method(
        workspace_snapshot=_workspace_snapshot(
            services=services,
            space_id=space_id,
            run_id=run_id,
        )
    )
    if inspect.isawaitable(result):
        return bool(await result)
    return bool(result)


async def maybe_verify_guarded_brief_generation(
    *,
    services: HarnessExecutionServices,
    space_id: UUID,
    run_id: str,
    progress_observer: ResearchInitProgressObserver | None,
) -> bool:
    if progress_observer is None:
        return False
    method = getattr(progress_observer, "verify_guarded_brief_generation", None)
    if method is None:
        return False
    result = method(
        workspace_snapshot=_workspace_snapshot(
            services=services,
            space_id=space_id,
            run_id=run_id,
        )
    )
    if inspect.isawaitable(result):
        return bool(await result)
    return bool(result)
