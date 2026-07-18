"""Pre-registered third holdout after bounded source-binding repair."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimKind,
    InventoryEpistemicStatus,
    InventoryPolarity,
)

from scripts.validation.claim_events.bionlp_import import TG04_BIONLP_ARCHIVE_SHA256
from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitEligibilityCategory,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.selection import (
    NestedHoldoutSelection,
    SealedEventSemantics,
    canonical_projection_set,
    enumerate_nested_event_candidates,
    seal_nested_event_graph,
    validate_sealed_projection_set,
)

# The prefix is the immutable failed v2 repeat-1 report SHA-256 recorded in 0ed9b652.
_SELECTION_SEED: Final = (
    "389cd720a6064e7546a56a5384c0b3a009b5bbe9a2f7dc78ecd3df41e2a3dd3e:"
    "binding-repair-holdout-v3"
)
_EXCLUDED_DOCUMENT_IDS: Final = frozenset(
    {"PMID-9233802", "PMC-2806624-07-DISCUSSION"},
)
_EXPECTED_DOCUMENT_COUNT: Final = 219
_EXPECTED_INCOMPATIBLE_DOCUMENT_IDS: Final = (
    "PMC-1134658-08-Discussion",
    "PMC-1920263-11-RESULTS-03",
    "PMID-7747440",
)
_EXPECTED_ELIGIBLE_UNIT_COUNT: Final = 14
_EXPECTED_SELECTION_RANK: Final = (
    "07554d1a49828e872cf448cd53466740f942852eb10fa783b2aa612beff7f329"
)
_EXPECTED_CASE_ID: Final = "bionlp-ge-2011-holdout:PMC-2222968-08-Discussion"
_EXPECTED_UNIT_INDEX: Final = 23
_EXPECTED_UNIT_ID: Final = (
    "source-unit-98f68d52a357c0fb1153c2fcdcbe1955287cfbfc9a53af84595baaae663cb84c"
)
_EXPECTED_SOURCE_SHA256: Final = (
    "776a4abf7b5831822379e135173dc8802ec57f0909e7e360b490bdc3e88ee568"
)
_EXPECTED_INPUT_SHA256: Final = (
    "0d677a3ed0916a231737e900a9484f453ae5ab1476dbc4c8058e01764a0aa457"
)
_EXPECTED_EXPERT_GRAPH_SHA256: Final = (
    "2de75032dafdf1072a7c86d592b89044c3b024f05ca679b0dd6461c7c81c696b"
)
_EXPECTED_PROJECTION_SET_SHA256: Final = (
    "7828ded0f5ccca1ed3e3af1362277688bffad30ccb7bd27318e0196d2a332a21"
)
_ARTICLE_URL: Final = "https://pmc.ncbi.nlm.nih.gov/articles/PMC2222968/"
_SCIENTIFIC_RATIONALE: Final = (
    "The source explicitly proposes GATA3 as the mediator of the IL-4-dependent "
    "inhibition of FOXP3. No additional complete projection was accepted: "
    "flattening GATA3 directly onto FOXP3 would lose the source-stated nested "
    "IL-4-dependent mechanism, while generic REGULATION would lose justified "
    "specificity. The two IL-13 null findings remain allowed as additional "
    "independently entailed claims."
)


def select_third_nested_event_holdout(
    *,
    corpus_root: Path,
    archive_sha256: str,
) -> NestedHoldoutSelection:
    """Recompute the content-blind v3 unit and its pre-inference projection set."""

    if archive_sha256 != TG04_BIONLP_ARCHIVE_SHA256:
        raise RuntimeError("BioNLP holdout archive hash changed")
    universe = enumerate_nested_event_candidates(
        corpus_root=corpus_root,
        selection_seed=_SELECTION_SEED,
        excluded_document_ids=_EXCLUDED_DOCUMENT_IDS,
    )
    if universe.document_count != _EXPECTED_DOCUMENT_COUNT:
        raise RuntimeError("third nested holdout document universe changed")
    if universe.incompatible_document_ids != _EXPECTED_INCOMPATIBLE_DOCUMENT_IDS:
        raise RuntimeError("third nested holdout importer exclusions changed")
    if len(universe.candidates) != _EXPECTED_ELIGIBLE_UNIT_COUNT:
        raise RuntimeError("third nested holdout candidate count changed")

    selected = min(universe.candidates, key=lambda candidate: candidate.rank)
    graph = seal_nested_event_graph(selected)
    graph_sha256 = _sha256_json(graph.as_json())
    projection_set = canonical_projection_set(
        graph,
        scientific_rationale=_SCIENTIFIC_RATIONALE,
        event_semantics=(
            SealedEventSemantics(
                event_id="E46",
                claim_kind=ClaimKind.SCIENTIFIC_FINDING,
                polarity=InventoryPolarity.SUPPORT,
                epistemic_status=InventoryEpistemicStatus.ASSERTED,
            ),
            SealedEventSemantics(
                event_id="E47",
                claim_kind=ClaimKind.SCIENTIFIC_HYPOTHESIS,
                polarity=InventoryPolarity.SUPPORT,
                epistemic_status=InventoryEpistemicStatus.HYPOTHESIS,
            ),
        ),
    )
    validate_sealed_projection_set(projection_set, unit=selected.unit)
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
        raise RuntimeError("pre-registered third nested holdout selection changed")
    return NestedHoldoutSelection(
        case_id=selected.case_id,
        unit=selected.unit,
        expert_graph=graph,
        trial_generation=3,
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
        projection_set=projection_set,
        projection_set_sha256=projection_set_sha256,
        expected_eligibility_category=SourceUnitEligibilityCategory.HYPOTHESIS,
    )


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode(),
    ).hexdigest()


__all__ = ["select_third_nested_event_holdout"]
