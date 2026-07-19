"""Content-blind selection and frozen source identity for the V11 holdout."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

from scripts.validation.claim_events.bionlp_import import TG04_BIONLP_ARCHIVE_SHA256
from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitEligibilityCategory,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.selection import (
    CompleteGraphSelectionProfile,
    NestedHoldoutSelection,
    enumerate_complete_event_graph_candidates,
    validate_sealed_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11.projection import (
    eleventh_projection_set,
)

# Exact SHA-256 of the immutable V10 failed scientific report.
_SELECTION_SEED: Final = (
    "a1347ca7588d7b1b83629f74406cadb294f65c091659daa64011b1d815018005"
)
_EXCLUDED_DOCUMENT_IDS: Final = frozenset(
    {
        "PMC-1134658-05-Results-04",
        "PMC-1920263-15-DISCUSSION",
        "PMC-2222968-00-TIAB",
        "PMC-2222968-04-Results-03",
        "PMC-2222968-08-Discussion",
        "PMC-2806624-04-RESULTS-03",
        "PMC-2806624-07-DISCUSSION",
        "PMID-10455128",
        "PMID-8622948",
        "PMID-8690900",
        "PMID-9233802",
    },
)
_EXPECTED_DOCUMENT_COUNT: Final = 219
_EXPECTED_INCOMPATIBLE_DOCUMENT_IDS: Final = (
    "PMC-1134658-08-Discussion",
    "PMC-1920263-11-RESULTS-03",
    "PMID-7747440",
)
_EXPECTED_CANDIDATE_COUNT: Final = 1
_EXPECTED_SELECTION_RANK: Final = (
    "ca698d8895284c653b4239293c028e33808352f023025a5207ac86294f7f5418"
)
_EXPECTED_CASE_ID: Final = (
    "bionlp-ge-2011-holdout:PMC-2806624-08-MATERIALS_AND_METHODS-01"
)
_EXPECTED_UNIT_INDEX: Final = 141
_EXPECTED_UNIT_ID: Final = (
    "source-unit-7c8d867e63ba86da5d69978529ab5ff25686efd7035d2ba50ac899cc8f89743d"
)
_EXPECTED_SOURCE_SHA256: Final = (
    "e8516818fb002201c7ca53c487d114ceb71fae1f35bc4d972977e5e181af37b9"
)
_EXPECTED_INPUT_SHA256: Final = (
    "d5242f5c0aae5bffc5874c486c5ef7d933a86c95bd7a9445ed32a80895e83b2f"
)
_EXPECTED_EXPERT_GRAPH_SHA256: Final = (
    "a77aa47edb35008c9149e9ab92bc0f01dce32510c92e1adb4b2bbca8df310a15"
)
_EXPECTED_PROJECTION_SET_SHA256: Final = (
    "e74d4cce878d1e6894bbd82345f438df437bddfbe8663bb26f91b161ce687f1a"
)
_ARTICLE_URL: Final = "https://pmc.ncbi.nlm.nih.gov/articles/PMC2806624/"


def eleventh_unit_identity() -> dict[str, object]:
    """Return the V11 source identity frozen before Artana execution."""

    return {
        "case_id": _EXPECTED_CASE_ID,
        "unit_id": _EXPECTED_UNIT_ID,
        "unit_index": _EXPECTED_UNIT_INDEX,
        "source_start": 19662,
        "source_end": 19960,
        "source_sha256": _EXPECTED_SOURCE_SHA256,
        "input_sha256": _EXPECTED_INPUT_SHA256,
    }


def select_eleventh_nested_event_holdout(
    *,
    corpus_root: Path,
    archive_sha256: str,
) -> NestedHoldoutSelection:
    """Recompute the content-blind V11 winner and attach frozen gold."""

    if archive_sha256 != TG04_BIONLP_ARCHIVE_SHA256:
        raise RuntimeError("BioNLP holdout archive hash changed")
    universe = enumerate_complete_event_graph_candidates(
        corpus_root=corpus_root,
        selection_seed=_SELECTION_SEED,
        excluded_document_ids=_EXCLUDED_DOCUMENT_IDS,
        profile=CompleteGraphSelectionProfile.NEGATED_RESULT_GRAPH,
    )
    if universe.document_count != _EXPECTED_DOCUMENT_COUNT:
        raise RuntimeError("eleventh holdout document universe changed")
    if universe.incompatible_document_ids != _EXPECTED_INCOMPATIBLE_DOCUMENT_IDS:
        raise RuntimeError("eleventh holdout importer exclusions changed")
    if len(universe.candidates) != _EXPECTED_CANDIDATE_COUNT:
        raise RuntimeError("eleventh holdout candidate count changed")

    selected = min(universe.candidates, key=lambda candidate: candidate.rank)
    projection_set = eleventh_projection_set()
    validate_sealed_projection_set(projection_set, unit=selected.unit)
    graph = projection_set.canonical_projection.graph
    graph_sha256 = _sha256_json(graph.as_json())
    projection_set_sha256 = _sha256_json(projection_set.as_json())
    if (
        selected.rank != _EXPECTED_SELECTION_RANK
        or selected.case_id != _EXPECTED_CASE_ID
        or selected.unit.index != _EXPECTED_UNIT_INDEX
        or selected.unit.unit_id != _EXPECTED_UNIT_ID
        or selected.unit.source_sha256 != _EXPECTED_SOURCE_SHA256
        or selected.unit.input_sha256 != _EXPECTED_INPUT_SHA256
        or graph_sha256 != _EXPECTED_EXPERT_GRAPH_SHA256
        or projection_set_sha256 != _EXPECTED_PROJECTION_SET_SHA256
    ):
        raise RuntimeError(
            "pre-registered eleventh holdout selection changed: "
            f"graph={graph_sha256}, projections={projection_set_sha256}"
        )
    return NestedHoldoutSelection(
        case_id=selected.case_id,
        unit=selected.unit,
        expert_graph=graph,
        trial_generation=11,
        selection_seed=_SELECTION_SEED,
        selection_rule=(
            "lowest_sha256_remaining_negated_graph_seeded_by_finalized_v10_report"
        ),
        excluded_document_ids=tuple(sorted(_EXCLUDED_DOCUMENT_IDS)),
        selection_rank=selected.rank,
        candidate_unit_count=len(universe.candidates),
        holdout_document_count=universe.document_count,
        incompatible_document_ids=universe.incompatible_document_ids,
        archive_sha256=archive_sha256,
        expert_graph_sha256=graph_sha256,
        authoritative_article_url=_ARTICLE_URL,
        projection_set=projection_set,
        projection_set_sha256=projection_set_sha256,
        expected_eligibility_category=SourceUnitEligibilityCategory.NULL_RESULT,
    )


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode(),
    ).hexdigest()


__all__ = [
    "eleventh_projection_set",
    "eleventh_unit_identity",
    "select_eleventh_nested_event_holdout",
]
