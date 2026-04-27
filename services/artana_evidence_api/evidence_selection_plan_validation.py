"""Validation helpers for evidence-selection source plans."""

from __future__ import annotations

from collections.abc import Sequence

from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
    EvidenceSelectionSourceSearchError,
    validate_live_source_search,
)
from artana_evidence_api.source_registry import get_source_definition

LIVE_SOURCE_SEARCH_TIMEOUT_SECONDS = 120.0
LIVE_SOURCE_SEARCH_PHASE_TIMEOUT_SECONDS = 600.0
MAX_LIVE_SOURCE_SEARCHES = 50
MAX_CANDIDATE_SEARCHES = 100
MAX_MODEL_PLANNED_SOURCE_SEARCHES = 5


def validate_source_plan_result(
    *,
    source_searches: tuple[EvidenceSelectionLiveSourceSearch, ...],
    candidate_searches: Sequence[object],
    source_plan: object,
    requested_sources: tuple[str, ...],
    max_records_per_search: int,
    live_network_allowed: bool,
) -> None:
    """Validate executable planner output before any source side effects."""

    allowed_sources = set(requested_sources)
    if source_searches and not live_network_allowed:
        msg = (
            "live_network_allowed must be true before evidence selection can "
            "create live source searches."
        )
        raise ValueError(msg)
    if len(source_searches) > MAX_LIVE_SOURCE_SEARCHES:
        msg = (
            f"Planner returned {len(source_searches)} source_searches, above "
            f"the {MAX_LIVE_SOURCE_SEARCHES} search run budget."
        )
        raise ValueError(msg)
    if len(candidate_searches) > MAX_CANDIDATE_SEARCHES:
        msg = (
            f"Planner returned {len(candidate_searches)} candidate_searches, above "
            f"the {MAX_CANDIDATE_SEARCHES} candidate run budget."
        )
        raise ValueError(msg)
    _validate_model_planned_search_budget(source_plan)
    for source_search in source_searches:
        _validate_source_key_for_plan(
            source_key=source_search.source_key,
            allowed_sources=allowed_sources,
            requires_direct_search=True,
        )
        if not source_search.query_payload:
            msg = (
                "Planner returned source_searches with an empty query_payload "
                f"for '{source_search.source_key}'."
            )
            raise ValueError(msg)
        _validate_plan_record_limit(
            source_key=source_search.source_key,
            max_records=source_search.max_records,
            max_records_per_search=max_records_per_search,
        )
        _validate_plan_timeout(source_search)
        _validate_source_search_payload(source_search)
    for candidate_search in candidate_searches:
        source_key = _candidate_source_key(candidate_search)
        _validate_source_key_for_plan(
            source_key=source_key,
            allowed_sources=allowed_sources,
            requires_direct_search=False,
        )
        _validate_plan_record_limit(
            source_key=source_key,
            max_records=_candidate_max_records(candidate_search),
            max_records_per_search=max_records_per_search,
        )


def _candidate_source_key(candidate_search: object) -> str:
    value = getattr(candidate_search, "source_key", None)
    if isinstance(value, str) and value:
        return value
    msg = "Planner returned candidate_searches without a valid source_key."
    raise ValueError(msg)


def _validate_model_planned_search_budget(source_plan: object) -> None:
    if not isinstance(source_plan, dict):
        return
    planner = source_plan.get("planner")
    if not isinstance(planner, dict) or planner.get("kind") != "model":
        return
    planned_searches = planner.get("planned_searches")
    if not isinstance(planned_searches, list):
        return
    if len(planned_searches) <= MAX_MODEL_PLANNED_SOURCE_SEARCHES:
        return
    msg = (
        f"Model planner returned {len(planned_searches)} planned_searches, "
        f"above the {MAX_MODEL_PLANNED_SOURCE_SEARCHES} model search budget."
    )
    raise ValueError(msg)


def _candidate_max_records(candidate_search: object) -> int | None:
    value = getattr(candidate_search, "max_records", None)
    if value is None or isinstance(value, int):
        return value
    msg = "Planner returned candidate_searches with invalid max_records."
    raise ValueError(msg)


def _validate_source_key_for_plan(
    *,
    source_key: str,
    allowed_sources: set[str],
    requires_direct_search: bool,
) -> None:
    source = get_source_definition(source_key)
    if source is None:
        msg = f"Planner returned unknown source '{source_key}'."
        raise ValueError(msg)
    if allowed_sources and source_key not in allowed_sources:
        msg = f"Planner returned source '{source_key}' outside requested sources."
        raise ValueError(msg)
    if requires_direct_search and not source.direct_search_enabled:
        msg = f"Planner returned source '{source_key}' without direct search support."
        raise ValueError(msg)


def _validate_plan_record_limit(
    *,
    source_key: str,
    max_records: int | None,
    max_records_per_search: int,
) -> None:
    if max_records is None:
        return
    if max_records < 1:
        msg = f"Planner returned non-positive max_records for '{source_key}'."
        raise ValueError(msg)
    if max_records > max_records_per_search:
        msg = (
            f"Planner returned max_records={max_records} for '{source_key}', "
            f"above max_records_per_search={max_records_per_search}."
        )
        raise ValueError(msg)


def _validate_plan_timeout(source_search: EvidenceSelectionLiveSourceSearch) -> None:
    if source_search.timeout_seconds is None:
        return
    if source_search.timeout_seconds <= 0:
        msg = (
            "Planner returned source_searches with a non-positive timeout "
            f"for '{source_search.source_key}'."
        )
        raise ValueError(msg)
    if source_search.timeout_seconds > LIVE_SOURCE_SEARCH_TIMEOUT_SECONDS:
        msg = (
            "Planner returned source_searches with timeout_seconds="
            f"{source_search.timeout_seconds:g} for '{source_search.source_key}', "
            f"above the {LIVE_SOURCE_SEARCH_TIMEOUT_SECONDS:g} second limit."
        )
        raise ValueError(msg)


def _validate_source_search_payload(
    source_search: EvidenceSelectionLiveSourceSearch,
) -> None:
    try:
        validate_live_source_search(source_search)
    except (EvidenceSelectionSourceSearchError, ValueError) as exc:
        msg = (
            "Planner returned invalid source_searches query_payload for "
            f"'{source_search.source_key}': {exc}"
        )
        raise ValueError(msg) from exc


__all__ = [
    "LIVE_SOURCE_SEARCH_PHASE_TIMEOUT_SECONDS",
    "LIVE_SOURCE_SEARCH_TIMEOUT_SECONDS",
    "MAX_CANDIDATE_SEARCHES",
    "MAX_LIVE_SOURCE_SEARCHES",
    "MAX_MODEL_PLANNED_SOURCE_SEARCHES",
    "validate_source_plan_result",
]
