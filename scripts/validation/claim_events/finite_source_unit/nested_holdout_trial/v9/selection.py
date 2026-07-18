"""Content-blind selection and source-complete gold for the V9 holdout."""

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
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v9.projection import (
    ninth_projection_set,
)

# Exact SHA-256 of the immutable V8 failed report.
_SELECTION_SEED: Final = (
    "b1498772852d13333a1201ddaa02c55098fdcc183bee01ef9da0915faf0ceafd"
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
_EXPECTED_CANDIDATE_COUNT: Final = 4
_EXPECTED_SELECTION_RANK: Final = (
    "2e832dd6d38b1666a42adf2f70f407ed6fb018f132d3c923a10a61da29c64c81"
)
_EXPECTED_CASE_ID: Final = "bionlp-ge-2011-holdout:PMID-8622948"
_EXPECTED_UNIT_INDEX: Final = 7
_EXPECTED_UNIT_ID: Final = (
    "source-unit-eb96c6e419821d8b930aebe6c1a891e185a0fcddccd3d05efa6ba05ef37601c0"
)
_EXPECTED_SOURCE_SHA256: Final = (
    "cac747e9b80090731f6e1e02e5e8ef70fc4254ae357de6ab2cd1835b3c5033ce"
)
_EXPECTED_INPUT_SHA256: Final = (
    "640f61f34918baf699cef470efe48a49ee13845b361d039021ef12424d421ffc"
)
_EXPECTED_EXPERT_GRAPH_SHA256: Final = (
    "d10955c29c243c95b7e089c10866d453bbf6992e79abd18753b2192b525e832a"
)
_EXPECTED_PROJECTION_SET_SHA256: Final = (
    "9163b0d185bdafdc093d158ec0a5b4da0e37d950904d998d822084d04f455915"
)
_ARTICLE_URL: Final = "https://pubmed.ncbi.nlm.nih.gov/8622948/"


def ninth_unit_identity() -> dict[str, object]:
    """Return the V9 unit identity frozen before Artana execution."""

    return {
        "case_id": _EXPECTED_CASE_ID,
        "unit_id": _EXPECTED_UNIT_ID,
        "unit_index": _EXPECTED_UNIT_INDEX,
        "source_start": 1266,
        "source_end": 1502,
        "source_sha256": _EXPECTED_SOURCE_SHA256,
        "input_sha256": _EXPECTED_INPUT_SHA256,
    }


def select_ninth_nested_event_holdout(
    *,
    corpus_root: Path,
    archive_sha256: str,
) -> NestedHoldoutSelection:
    """Recompute the content-blind V9 winner and attach frozen source gold."""

    if archive_sha256 != TG04_BIONLP_ARCHIVE_SHA256:
        raise RuntimeError("BioNLP holdout archive hash changed")
    universe = enumerate_complete_event_graph_candidates(
        corpus_root=corpus_root,
        selection_seed=_SELECTION_SEED,
        excluded_document_ids=_EXCLUDED_DOCUMENT_IDS,
        profile=CompleteGraphSelectionProfile.NEGATED_RESULT_GRAPH,
    )
    if universe.document_count != _EXPECTED_DOCUMENT_COUNT:
        raise RuntimeError("ninth holdout document universe changed")
    if universe.incompatible_document_ids != _EXPECTED_INCOMPATIBLE_DOCUMENT_IDS:
        raise RuntimeError("ninth holdout importer exclusions changed")
    if len(universe.candidates) != _EXPECTED_CANDIDATE_COUNT:
        raise RuntimeError("ninth holdout candidate count changed")

    selected = min(universe.candidates, key=lambda candidate: candidate.rank)
    projection_set = ninth_projection_set()
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
        raise RuntimeError("pre-registered ninth holdout selection changed")
    return NestedHoldoutSelection(
        case_id=selected.case_id,
        unit=selected.unit,
        expert_graph=graph,
        trial_generation=9,
        selection_seed=_SELECTION_SEED,
        selection_rule=(
            "lowest_sha256_hidden_candidate_with_pre_model_source_complete_gold"
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
        expected_eligibility_category=(SourceUnitEligibilityCategory.MIXED_SCIENTIFIC),
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
    "ninth_projection_set",
    "ninth_unit_identity",
    "select_ninth_nested_event_holdout",
]
