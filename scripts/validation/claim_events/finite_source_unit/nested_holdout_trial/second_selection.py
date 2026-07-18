"""Pre-registered second holdout after the anaphoric-reference remediation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

from scripts.validation.claim_events.bionlp_import import TG04_BIONLP_ARCHIVE_SHA256
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.selection import (
    NestedHoldoutSelection,
    enumerate_nested_event_candidates,
    seal_nested_event_graph,
)

# The prefix is the immutable failed repeat-1 report SHA-256 recorded in 3d5f4128.
_SELECTION_SEED: Final = (
    "97d984a6429df4e7bf70fd49964d9efab911c9f9677c8910f9d06654f6d9f129:"
    "anaphoric-holdout-v2"
)
_EXCLUDED_DOCUMENT_IDS: Final = frozenset({"PMID-9233802"})
_EXPECTED_DOCUMENT_COUNT: Final = 219
_EXPECTED_INCOMPATIBLE_DOCUMENT_IDS: Final = (
    "PMC-1134658-08-Discussion",
    "PMC-1920263-11-RESULTS-03",
    "PMID-7747440",
)
_EXPECTED_ELIGIBLE_UNIT_COUNT: Final = 15
_EXPECTED_SELECTION_RANK: Final = (
    "23e11013c67e5cc27925588c0999a74af6192f4a6626c9a4ea644ee7479adbac"
)
_EXPECTED_CASE_ID: Final = (
    "bionlp-ge-2011-holdout:PMC-2806624-07-DISCUSSION"
)
_EXPECTED_UNIT_INDEX: Final = 54
_EXPECTED_UNIT_ID: Final = (
    "source-unit-edb3591fbea79678533ddb57259dddfc3be3bb0e8f003c2e06c62fbf4b50f0cd"
)
_EXPECTED_SOURCE_SHA256: Final = (
    "70de20a933092f2eb987b0ac86b6c988e38c6acf5d71461eb132147699ef53b6"
)
_EXPECTED_INPUT_SHA256: Final = (
    "4e9bca5f89e9ece248a0acc9405ebdc7abb6b386ef69c3b910a9c8aaa82df920"
)
_EXPECTED_EXPERT_GRAPH_SHA256: Final = (
    "b881b0e63ac7ea503820a444b0352160277e5b4d6df695430a283a0eea610696"
)
_ARTICLE_URL: Final = "https://pmc.ncbi.nlm.nih.gov/articles/PMC2806624/"


def select_second_nested_event_holdout(
    *,
    corpus_root: Path,
    archive_sha256: str,
) -> NestedHoldoutSelection:
    """Recompute and verify the untouched post-remediation holdout."""

    if archive_sha256 != TG04_BIONLP_ARCHIVE_SHA256:
        raise RuntimeError("BioNLP holdout archive hash changed")
    universe = enumerate_nested_event_candidates(
        corpus_root=corpus_root,
        selection_seed=_SELECTION_SEED,
        excluded_document_ids=_EXCLUDED_DOCUMENT_IDS,
    )
    if universe.document_count != _EXPECTED_DOCUMENT_COUNT:
        raise RuntimeError("second nested holdout document universe changed")
    if universe.incompatible_document_ids != _EXPECTED_INCOMPATIBLE_DOCUMENT_IDS:
        raise RuntimeError("second nested holdout importer exclusions changed")
    if len(universe.candidates) != _EXPECTED_ELIGIBLE_UNIT_COUNT:
        raise RuntimeError("second nested holdout candidate count changed")
    selected = min(universe.candidates, key=lambda candidate: candidate.rank)
    graph = seal_nested_event_graph(selected)
    graph_sha256 = _sha256_json(graph.as_json())
    if (
        selected.rank != _EXPECTED_SELECTION_RANK
        or selected.case_id != _EXPECTED_CASE_ID
        or selected.unit.index != _EXPECTED_UNIT_INDEX
        or selected.unit.unit_id != _EXPECTED_UNIT_ID
        or selected.unit.source_sha256 != _EXPECTED_SOURCE_SHA256
        or selected.unit.input_sha256 != _EXPECTED_INPUT_SHA256
        or graph_sha256 != _EXPECTED_EXPERT_GRAPH_SHA256
    ):
        raise RuntimeError("pre-registered second nested holdout selection changed")
    return NestedHoldoutSelection(
        case_id=selected.case_id,
        unit=selected.unit,
        expert_graph=graph,
        trial_generation=2,
        selection_seed=_SELECTION_SEED,
        selection_rule=(
            "lowest_sha256_eligible_unit_outside_development_and_exposed_panels"
        ),
        excluded_document_ids=tuple(sorted(_EXCLUDED_DOCUMENT_IDS)),
        selection_rank=selected.rank,
        candidate_unit_count=len(universe.candidates),
        holdout_document_count=universe.document_count,
        incompatible_document_ids=universe.incompatible_document_ids,
        archive_sha256=archive_sha256,
        expert_graph_sha256=graph_sha256,
        authoritative_article_url=_ARTICLE_URL,
    )


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode(),
    ).hexdigest()


__all__ = ["select_second_nested_event_holdout"]
