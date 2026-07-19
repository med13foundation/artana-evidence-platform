"""Content-blind selection and frozen source identity for the V10 holdout."""

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
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v10.projection import (
    tenth_projection_set,
)

_SELECTION_SEED: Final = (
    "59107ff0d23bf9543b23df2add9885d0bab4c7dd0c38ffbd18e030734cc2c897"
)
_EXCLUDED_DOCUMENT_IDS: Final = frozenset(
    {
        "PMC-1134658-05-Results-04",
        "PMC-1920263-15-DISCUSSION",
        "PMC-2222968-00-TIAB",
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
_EXPECTED_CANDIDATE_COUNT: Final = 3
_EXPECTED_SELECTION_RANK: Final = (
    "a7b2a256a3eb75f1efcea5bc01e581ca200c5d951043c6193645c4bebbac952d"
)
_EXPECTED_CASE_ID: Final = "bionlp-ge-2011-holdout:PMC-2222968-04-Results-03"
_EXPECTED_UNIT_INDEX: Final = 17
_EXPECTED_UNIT_ID: Final = (
    "source-unit-463bf8e1b37963d7547eb57c6d51545a466050b2c6c9faa9abc76ff8e2330914"
)
_EXPECTED_SOURCE_SHA256: Final = (
    "d452cea84a786851d0d5686c5acab618745b4b8ccaf09cc6fa638a48b370a17a"
)
_EXPECTED_INPUT_SHA256: Final = (
    "cc50c7039a85ec0c7512d0f8f9571331f4001a61e88284a040ec701ec619a121"
)
_EXPECTED_EXPERT_GRAPH_SHA256: Final = (
    "ddd564c4fc7a431358df7f193c4b0284ff5dcebc87a4fd6ce6f61d6b29f28cc5"
)
_EXPECTED_PROJECTION_SET_SHA256: Final = (
    "4f6add86982fe4eabb9df893ee71af9b8cce60aa1b280d18edff9598004821cd"
)
_ARTICLE_URL: Final = "https://pmc.ncbi.nlm.nih.gov/articles/PMC2222968/"


def tenth_unit_identity() -> dict[str, object]:
    """Return the V10 source identity frozen before Artana execution."""

    return {
        "case_id": _EXPECTED_CASE_ID,
        "unit_id": _EXPECTED_UNIT_ID,
        "unit_index": _EXPECTED_UNIT_INDEX,
        "source_start": 2622,
        "source_end": 2723,
        "source_sha256": _EXPECTED_SOURCE_SHA256,
        "input_sha256": _EXPECTED_INPUT_SHA256,
    }


def select_tenth_nested_event_holdout(
    *,
    corpus_root: Path,
    archive_sha256: str,
) -> NestedHoldoutSelection:
    """Recompute the content-blind V10 winner and attach frozen gold."""

    if archive_sha256 != TG04_BIONLP_ARCHIVE_SHA256:
        raise RuntimeError("BioNLP holdout archive hash changed")
    universe = enumerate_complete_event_graph_candidates(
        corpus_root=corpus_root,
        selection_seed=_SELECTION_SEED,
        excluded_document_ids=_EXCLUDED_DOCUMENT_IDS,
        profile=CompleteGraphSelectionProfile.NEGATED_RESULT_GRAPH,
    )
    if universe.document_count != _EXPECTED_DOCUMENT_COUNT:
        raise RuntimeError("tenth holdout document universe changed")
    if universe.incompatible_document_ids != _EXPECTED_INCOMPATIBLE_DOCUMENT_IDS:
        raise RuntimeError("tenth holdout importer exclusions changed")
    if len(universe.candidates) != _EXPECTED_CANDIDATE_COUNT:
        raise RuntimeError("tenth holdout candidate count changed")

    selected = min(universe.candidates, key=lambda candidate: candidate.rank)
    projection_set = tenth_projection_set()
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
        raise RuntimeError("pre-registered tenth holdout selection changed")
    return NestedHoldoutSelection(
        case_id=selected.case_id,
        unit=selected.unit,
        expert_graph=graph,
        trial_generation=10,
        selection_seed=_SELECTION_SEED,
        selection_rule=(
            "lowest_sha256_remaining_negated_graph_seeded_by_finalized_v9_report"
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
    "select_tenth_nested_event_holdout",
    "tenth_projection_set",
    "tenth_unit_identity",
]
