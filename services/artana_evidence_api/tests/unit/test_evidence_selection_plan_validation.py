"""Tests for evidence-selection source-plan validation."""

from __future__ import annotations

from uuid import uuid4

import pytest
from artana_evidence_api.evidence_selection_plan_validation import (
    MAX_CANDIDATE_SEARCHES,
    MAX_LIVE_SOURCE_SEARCHES,
    MAX_MODEL_PLANNED_SOURCE_SEARCHES,
    validate_source_plan_result,
)
from artana_evidence_api.evidence_selection_runtime import (
    EvidenceSelectionCandidateSearch,
)
from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
)


def _live_search(
    *,
    source_key: str = "clinvar",
    max_records: int | None = 2,
    timeout_seconds: float | None = None,
    query_payload: dict[str, object] | None = None,
) -> EvidenceSelectionLiveSourceSearch:
    return EvidenceSelectionLiveSourceSearch(
        source_key=source_key,
        query_payload=(
            {"gene_symbol": "MED13"} if query_payload is None else query_payload
        ),
        max_records=max_records,
        timeout_seconds=timeout_seconds,
    )


def _candidate_search(
    *,
    source_key: str = "clinvar",
    max_records: int | None = 2,
) -> EvidenceSelectionCandidateSearch:
    return EvidenceSelectionCandidateSearch(
        source_key=source_key,
        search_id=uuid4(),
        max_records=max_records,
    )


def test_source_plan_validation_accepts_bounded_live_and_candidate_searches() -> None:
    validate_source_plan_result(
        source_searches=(_live_search(),),
        candidate_searches=(_candidate_search(),),
        source_plan={"planner": {"kind": "deterministic"}},
        requested_sources=("clinvar",),
        max_records_per_search=3,
        live_network_allowed=True,
    )


def test_source_plan_validation_requires_live_network_opt_in() -> None:
    with pytest.raises(ValueError, match="live_network_allowed"):
        validate_source_plan_result(
            source_searches=(_live_search(),),
            candidate_searches=(),
            source_plan={"planner": {"kind": "deterministic"}},
            requested_sources=("clinvar",),
            max_records_per_search=3,
            live_network_allowed=False,
        )


def test_source_plan_validation_enforces_model_planned_search_cap() -> None:
    source_plan = {
        "planner": {
            "kind": "model",
            "planned_searches": [
                {"source_key": "clinvar"}
                for _ in range(MAX_MODEL_PLANNED_SOURCE_SEARCHES + 1)
            ],
        },
    }

    with pytest.raises(ValueError, match="model search budget"):
        validate_source_plan_result(
            source_searches=(_live_search(),),
            candidate_searches=(),
            source_plan=source_plan,
            requested_sources=("clinvar",),
            max_records_per_search=3,
            live_network_allowed=True,
        )


def test_source_plan_validation_enforces_total_live_search_cap() -> None:
    with pytest.raises(ValueError, match="search run budget"):
        validate_source_plan_result(
            source_searches=tuple(
                _live_search() for _ in range(MAX_LIVE_SOURCE_SEARCHES + 1)
            ),
            candidate_searches=(),
            source_plan={"planner": {"kind": "deterministic"}},
            requested_sources=("clinvar",),
            max_records_per_search=3,
            live_network_allowed=True,
        )


def test_source_plan_validation_enforces_candidate_search_cap() -> None:
    with pytest.raises(ValueError, match="candidate run budget"):
        validate_source_plan_result(
            source_searches=(),
            candidate_searches=tuple(
                _candidate_search() for _ in range(MAX_CANDIDATE_SEARCHES + 1)
            ),
            source_plan={"planner": {"kind": "deterministic"}},
            requested_sources=("clinvar",),
            max_records_per_search=3,
            live_network_allowed=False,
        )


@pytest.mark.parametrize(
    ("source_search", "message"),
    [
        (_live_search(source_key="not_real"), "unknown source"),
        (_live_search(source_key="hgnc"), "without direct search support"),
        (_live_search(source_key="clinvar", max_records=4), "above max_records"),
        (_live_search(source_key="clinvar", timeout_seconds=121.0), "above the 120"),
        (_live_search(source_key="clinvar", query_payload={}), "empty query_payload"),
        (
            _live_search(source_key="clinvar", query_payload={"query": "MED13"}),
            "invalid source_searches query_payload",
        ),
    ],
)
def test_source_plan_validation_rejects_invalid_live_searches(
    source_search: EvidenceSelectionLiveSourceSearch,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_source_plan_result(
            source_searches=(source_search,),
            candidate_searches=(),
            source_plan={"planner": {"kind": "deterministic"}},
            requested_sources=("clinvar", "hgnc"),
            max_records_per_search=3,
            live_network_allowed=True,
        )


def test_source_plan_validation_rejects_candidate_outside_requested_sources() -> None:
    with pytest.raises(ValueError, match="outside requested sources"):
        validate_source_plan_result(
            source_searches=(),
            candidate_searches=(_candidate_search(source_key="pubmed"),),
            source_plan={"planner": {"kind": "deterministic"}},
            requested_sources=("clinvar",),
            max_records_per_search=3,
            live_network_allowed=False,
        )
