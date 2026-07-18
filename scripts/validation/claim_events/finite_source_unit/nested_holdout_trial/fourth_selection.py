"""Pre-registered complete-graph v4 holdout selected after prompt freeze."""

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
    CompleteGraphSelectionProfile,
    NestedHoldoutSelection,
    ProjectionProvenance,
    SealedArgument,
    SealedEvent,
    SealedEventLink,
    SealedEventSemantics,
    SealedGraphProjection,
    SealedNestedEventGraph,
    SealedProjectionSet,
    SealedTrigger,
    enumerate_complete_event_graph_candidates,
    seal_complete_event_graph,
    validate_sealed_projection_set,
)

# The seed is exactly the immutable failed v3 repeat-1 report SHA-256.
_SELECTION_SEED: Final = (
    "f2d1c55426cf241fa95b7bf06db11cab12749204b0cfd81e8d851811b230cff7"
)
_EXCLUDED_DOCUMENT_IDS: Final = frozenset(
    {
        "PMID-9233802",
        "PMC-2806624-07-DISCUSSION",
        "PMC-2222968-08-Discussion",
        "PMC-2222968-00-TIAB",
    },
)
_EXPECTED_DOCUMENT_COUNT: Final = 219
_EXPECTED_INCOMPATIBLE_DOCUMENT_IDS: Final = (
    "PMC-1134658-08-Discussion",
    "PMC-1920263-11-RESULTS-03",
    "PMID-7747440",
)
_EXPECTED_ELIGIBLE_UNIT_COUNT: Final = 11
_EXPECTED_SELECTION_RANK: Final = (
    "05cfb02937b265d91cd4669909ce4a940cecb302624f85ec1ff71e55da230e17"
)
_EXPECTED_CASE_ID: Final = "bionlp-ge-2011-holdout:PMC-1920263-15-DISCUSSION"
_EXPECTED_UNIT_INDEX: Final = 25
_EXPECTED_UNIT_ID: Final = (
    "source-unit-372b0632f7433058002746584f09b6a55db2fcde52724d1f59104731edb29870"
)
_EXPECTED_SOURCE_SHA256: Final = (
    "9548ffaadbde4f7f6f4419345ecd93d9f549c04c4c03b0988233610da28eb1cf"
)
_EXPECTED_INPUT_SHA256: Final = (
    "edad292a41024ae49be065c99d69c8036b6db71e4ae37cdb7a8b2134a08e7d0b"
)
_EXPECTED_EXPERT_GRAPH_SHA256: Final = (
    "1420609f10dbb6e2d667acdc6d3d0909a96ccd1572a032ef4986bd1ab4f746ca"
)
_EXPECTED_PROJECTION_SET_SHA256: Final = (
    "5d725c8feedfaf292cb3753c7c9cd8a557ceb7eeba23538068325f7f4f1f237d"
)
_ARTICLE_URL: Final = "https://pmc.ncbi.nlm.nih.gov/articles/PMC1920263/"


def select_fourth_nested_event_holdout(
    *,
    corpus_root: Path,
    archive_sha256: str,
) -> NestedHoldoutSelection:
    """Recompute the first direct-seed negated-result graph and frozen projections."""

    if archive_sha256 != TG04_BIONLP_ARCHIVE_SHA256:
        raise RuntimeError("BioNLP holdout archive hash changed")
    universe = enumerate_complete_event_graph_candidates(
        corpus_root=corpus_root,
        selection_seed=_SELECTION_SEED,
        excluded_document_ids=_EXCLUDED_DOCUMENT_IDS,
        profile=CompleteGraphSelectionProfile.NEGATED_RESULT_GRAPH,
    )
    if universe.document_count != _EXPECTED_DOCUMENT_COUNT:
        raise RuntimeError("fourth holdout document universe changed")
    if universe.incompatible_document_ids != _EXPECTED_INCOMPATIBLE_DOCUMENT_IDS:
        raise RuntimeError("fourth holdout importer exclusions changed")
    if len(universe.candidates) != _EXPECTED_ELIGIBLE_UNIT_COUNT:
        raise RuntimeError("fourth holdout negated-result candidate count changed")

    selected = min(universe.candidates, key=lambda candidate: candidate.rank)
    graph = seal_complete_event_graph(selected)
    graph_sha256 = _sha256_json(graph.as_json())
    projection_set = _projection_set()
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
        raise RuntimeError("pre-registered fourth complete-graph selection changed")
    return NestedHoldoutSelection(
        case_id=selected.case_id,
        unit=selected.unit,
        expert_graph=graph,
        trial_generation=4,
        selection_seed=_SELECTION_SEED,
        selection_rule=(
            "lowest_sha256_closed_top_level_negated_graph_outside_exposed_panels"
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
        expected_eligibility_category=SourceUnitEligibilityCategory.MIXED_SCIENTIFIC,
    )


def _projection_set() -> SealedProjectionSet:
    projections = tuple(
        _population_contrast_projection(
            cue=cue,
            cue_start=cue_start,
            cue_name=cue_name,
            cause_kind=cause_kind,
            theme_shape=theme_shape,
        )
        for cue, cue_start, cue_name in (
            ("enhanced", 3431, "direction"),
            ("enhanced expression", 3431, "direction-and-process"),
        )
        for cause_kind in ("protein", "process", "intervention", "exposure")
        for theme_shape in ("process", "resting-decomposed")
    )
    return SealedProjectionSet(
        canonical_projection_id=projections[0].projection_id,
        projections=projections,
    )


def _population_contrast_projection(
    *,
    cue: str,
    cue_start: int,
    cue_name: str,
    cause_kind: str,
    theme_shape: str,
) -> SealedGraphProjection:
    cause = _cause(cause_kind)
    entity_theme = SealedArgument(
        event_role="THEME",
        reference_id="T20",
        participant_type="GENE_OR_PROTEIN",
        exact_span="A3G",
        source_start=3454,
        source_end=3457,
    )
    process_theme = SealedArgument(
        event_role="THEME",
        reference_id="SOURCE-EXPRESSION-PROCESS",
        participant_type="BIOLOGICAL_PROCESS",
        exact_span="expression of A3G",
        source_start=3440,
        source_end=3457,
    )
    outcome_theme = SealedArgument(
        event_role="THEME",
        reference_id="SOURCE-EXPRESSION-OUTCOME",
        participant_type="OUTCOME",
        exact_span="expression of A3G",
        source_start=3440,
        source_end=3457,
    )
    populations = (
        (
            "RESTING",
            "resting primary CD4 T cells",
            3487,
            InventoryPolarity.SUPPORT,
        ),
        (
            "ACTIVATED",
            "activated T cells",
            3527,
            InventoryPolarity.NULL_RESULT,
        ),
    )
    contrast_events = tuple(
        SealedEvent(
            event_id=f"SOURCE-{population_id}",
            event_type="POSITIVE_REGULATION",
            trigger=SealedTrigger(cue, cue_start, cue_start + len(cue)),
            arguments=(
                cause,
                *(
                    ()
                    if theme_shape == "resting-decomposed"
                    and population_id == "RESTING"
                    else (
                        (
                            outcome_theme
                            if theme_shape == "resting-decomposed"
                            else process_theme
                        ),
                    )
                ),
                SealedArgument(
                    event_role="CONTEXT",
                    reference_id=f"SOURCE-{population_id}-POPULATION",
                    participant_type="POPULATION",
                    exact_span=population_span,
                    source_start=population_start,
                    source_end=population_start + len(population_span),
                ),
            ),
        )
        for population_id, population_span, population_start, _ in populations
    )
    expression_event = SealedEvent(
        event_id="SOURCE-EXPRESSION",
        event_type="EXPRESSION",
        trigger=SealedTrigger("expression", 3440, 3450),
        arguments=(
            entity_theme,
            SealedArgument(
                event_role="CONTEXT",
                reference_id="SOURCE-RESTING-POPULATION",
                participant_type="POPULATION",
                exact_span="resting primary CD4 T cells",
                source_start=3487,
                source_end=3514,
            ),
        ),
    )
    events = (
        (expression_event, *contrast_events)
        if theme_shape == "resting-decomposed"
        else contrast_events
    )
    semantics = tuple(
        SealedEventSemantics(
            event_id=event.event_id,
            claim_kind=ClaimKind.SCIENTIFIC_FINDING,
            polarity=(
                InventoryPolarity.SUPPORT
                if event.event_id == "SOURCE-EXPRESSION"
                else next(
                    item[3]
                    for item in populations
                    if event.event_id == f"SOURCE-{item[0]}"
                )
            ),
            epistemic_status=InventoryEpistemicStatus.ASSERTED,
        )
        for event in events
    )
    links = (
        (SealedEventLink("SOURCE-RESTING", "THEME", "SOURCE-EXPRESSION"),)
        if theme_shape == "resting-decomposed"
        else ()
    )
    return SealedGraphProjection(
        projection_id=f"source-valid-{cue_name}-{cause_kind}-{theme_shape}",
        provenance=ProjectionProvenance.SOURCE_VALID_ALTERNATIVE,
        scientific_rationale=(
            "The projection preserves IFN-alpha exposure, A3G, and the opposing "
            "resting-cell supported versus activated-cell null outcomes using the "
            f"{cue_name} cue, {cause_kind} cause representation, and {theme_shape} "
            "theme shape."
        ),
        graph=SealedNestedEventGraph(events=events, links=links),
        event_semantics=semantics,
    )


def _cause(kind: str) -> SealedArgument:
    if kind == "protein":
        return SealedArgument(
            event_role="CAUSE",
            reference_id="T21",
            participant_type="GENE_OR_PROTEIN",
            exact_span="IFN-alpha",
            source_start=3464,
            source_end=3473,
        )
    return SealedArgument(
        event_role="CAUSE",
        reference_id=f"SOURCE-{kind.upper()}",
        participant_type={
            "process": "BIOLOGICAL_PROCESS",
            "intervention": "INTERVENTION",
            "exposure": "EXPOSURE",
        }[kind],
        exact_span="IFN-alpha treatment",
        source_start=3464,
        source_end=3483,
    )


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode(),
    ).hexdigest()


__all__ = ["select_fourth_nested_event_holdout"]
