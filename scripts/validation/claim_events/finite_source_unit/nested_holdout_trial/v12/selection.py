"""Content-blind selection and frozen source identity for the V12 holdout."""

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
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.projection import (
    twelfth_projection_set,
)

# Exact SHA-256 of the immutable finalized V11 live report.
_SELECTION_SEED: Final = (
    "ac922afa3297dd94810ff8f96078357e36ab725efa1352c45f63f414d6a3f2e7"
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
        "PMC-2806624-08-MATERIALS_AND_METHODS-01",
        "PMID-10455128",
        "PMID-8622948",
        "PMID-8690900",
        "PMID-9233802",
    }
)
_EXPECTED_DOCUMENT_COUNT: Final = 219
_EXPECTED_INCOMPATIBLE_DOCUMENT_IDS: Final = (
    "PMC-1134658-08-Discussion",
    "PMC-1920263-11-RESULTS-03",
    "PMID-7747440",
)
_EXPECTED_CANDIDATE_COUNT: Final = 44
_EXPECTED_SELECTION_RANK: Final = (
    "058afbb94ae26c5224c5b1cb9e33d08fd99178bbaee223da242db4913f64394f"
)
_EXPECTED_CASE_ID: Final = "bionlp-ge-2011-holdout:PMID-10229231"
_EXPECTED_UNIT_INDEX: Final = 0
_EXPECTED_UNIT_ID: Final = (
    "source-unit-58bfd6e4d47486aa4c39f5f7b542b92d06108bd490a074ffae85f8a31fbb8ace"
)
_EXPECTED_SOURCE_SHA256: Final = (
    "1bd49ba3ef2ddcaaba8a26f16c9fb69479a946550bd37a60a71782123c651921"
)
_EXPECTED_INPUT_SHA256: Final = (
    "276f6c20c0fe7422111dc1d229ad1d03431449280fa4c645483ea42da85c7d87"
)
_EXPECTED_EXPERT_GRAPH_SHA256: Final = (
    "2ed9270cd4baae75ca69bb4308dd03d9fdc5b7ee0931fa9d6e7d2756cd708878"
)
_EXPECTED_PROJECTION_SET_SHA256: Final = (
    "7fefffec28dbfe70ce743afcdc413ca50f56d0093adfbc08f45014679693ef49"
)
_ARTICLE_URL: Final = "https://pubmed.ncbi.nlm.nih.gov/10229231/"


def twelfth_unit_identity() -> dict[str, object]:
    """Return the V12 source identity frozen before Artana execution."""

    return {
        "case_id": _EXPECTED_CASE_ID,
        "unit_id": _EXPECTED_UNIT_ID,
        "unit_index": _EXPECTED_UNIT_INDEX,
        "source_start": 0,
        "source_end": 78,
        "source_sha256": _EXPECTED_SOURCE_SHA256,
        "input_sha256": _EXPECTED_INPUT_SHA256,
    }


def select_twelfth_nested_event_holdout(
    *,
    corpus_root: Path,
    archive_sha256: str,
) -> NestedHoldoutSelection:
    """Recompute the broad closed-graph V12 winner and attach complete gold."""

    if archive_sha256 != TG04_BIONLP_ARCHIVE_SHA256:
        raise RuntimeError("BioNLP holdout archive hash changed")
    universe = enumerate_complete_event_graph_candidates(
        corpus_root=corpus_root,
        selection_seed=_SELECTION_SEED,
        excluded_document_ids=_EXCLUDED_DOCUMENT_IDS,
        profile=CompleteGraphSelectionProfile.ANY_CLOSED_GRAPH,
    )
    if universe.document_count != _EXPECTED_DOCUMENT_COUNT:
        raise RuntimeError("twelfth holdout document universe changed")
    if universe.incompatible_document_ids != _EXPECTED_INCOMPATIBLE_DOCUMENT_IDS:
        raise RuntimeError("twelfth holdout importer exclusions changed")
    if len(universe.candidates) != _EXPECTED_CANDIDATE_COUNT:
        raise RuntimeError("twelfth holdout candidate count changed")

    selected = min(universe.candidates, key=lambda candidate: candidate.rank)
    projection_set = twelfth_projection_set()
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
            "pre-registered twelfth holdout selection changed: "
            f"graph={graph_sha256}, projections={projection_set_sha256}"
        )
    return NestedHoldoutSelection(
        case_id=selected.case_id,
        unit=selected.unit,
        expert_graph=graph,
        trial_generation=12,
        selection_seed=_SELECTION_SEED,
        selection_rule=(
            "lowest_sha256_any_closed_graph_seeded_by_finalized_v11_report"
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
        expected_eligibility_category=SourceUnitEligibilityCategory.FINDING,
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
    "select_twelfth_nested_event_holdout",
    "twelfth_projection_set",
    "twelfth_unit_identity",
]
