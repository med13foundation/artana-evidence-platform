"""Pre-registered agent-expert gold for the eighth hidden holdout."""

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
    SealedEventSemantics,
    SealedGraphProjection,
    SealedNestedEventGraph,
    SealedProjectionSet,
    SealedTrigger,
    enumerate_complete_event_graph_candidates,
    validate_sealed_projection_set,
)

# Exact SHA-256 of the immutable V7 preflight JSON.
_SELECTION_SEED: Final = (
    "969619fd2b8faf60d81c34ba9b12c3f100d69f3af56dcda431072dd009156916"
)
_EXCLUDED_DOCUMENT_IDS: Final = frozenset(
    {
        "PMID-9233802",
        "PMC-2806624-07-DISCUSSION",
        "PMC-2222968-08-Discussion",
        "PMC-2222968-00-TIAB",
        "PMC-1920263-15-DISCUSSION",
        "PMID-8690900",
        "PMC-1134658-05-Results-04",
        "PMID-10455128",
    },
)
_EXPECTED_DOCUMENT_COUNT: Final = 219
_EXPECTED_INCOMPATIBLE_DOCUMENT_IDS: Final = (
    "PMC-1134658-08-Discussion",
    "PMC-1920263-11-RESULTS-03",
    "PMID-7747440",
)
_EXPECTED_CANDIDATE_COUNT: Final = 5
_EXPECTED_SELECTION_RANK: Final = (
    "35c6070fb7790cd858ee7ee13aabf5ac4f4c78cde085025ef1fecc5164b0655e"
)
_EXPECTED_CASE_ID: Final = "bionlp-ge-2011-holdout:PMC-2806624-04-RESULTS-03"
_EXPECTED_UNIT_INDEX: Final = 10
_EXPECTED_UNIT_ID: Final = (
    "source-unit-def51372591d9c4244a4dac031c801c8781aa4006f6718ddd8bfb77dece566a2"
)
_EXPECTED_SOURCE_SHA256: Final = (
    "09a14c9ddcfd3ef03820e5fe7f3a62164fdf051f3a46335b8523c0681ed5fe35"
)
_EXPECTED_INPUT_SHA256: Final = (
    "606efd1510850b66276d48b00a042680aa0982e9d233195c3b1906cfb9b513db"
)
_EXPECTED_EXPERT_GRAPH_SHA256: Final = (
    "2abda3dfab2fa4f2b35f321a7c603cf8f45c6adbb92ed63d7c69c7565dad7677"
)
_EXPECTED_PROJECTION_SET_SHA256: Final = (
    "5c8e13c4eac5087d151c1b4b391b1215555ce401fdbb1c38a95b61853ed6cde6"
)
_ARTICLE_URL: Final = "https://pmc.ncbi.nlm.nih.gov/articles/PMC2806624/"


def eighth_unit_identity() -> dict[str, object]:
    """Return the non-semantic identity sealed before the V8 model run."""

    return {
        "case_id": _EXPECTED_CASE_ID,
        "unit_id": _EXPECTED_UNIT_ID,
        "unit_index": _EXPECTED_UNIT_INDEX,
        "source_start": 1909,
        "source_end": 2051,
        "source_sha256": _EXPECTED_SOURCE_SHA256,
        "input_sha256": _EXPECTED_INPUT_SHA256,
    }


def eighth_projection_set() -> SealedProjectionSet:
    """Return the source-derived projection set frozen before execution."""

    return _projection_set()


def select_eighth_nested_event_holdout(
    *,
    corpus_root: Path,
    archive_sha256: str,
) -> NestedHoldoutSelection:
    """Select the deterministic winner and attach pre-model adjudicated gold."""

    if archive_sha256 != TG04_BIONLP_ARCHIVE_SHA256:
        raise RuntimeError("BioNLP holdout archive hash changed")
    universe = enumerate_complete_event_graph_candidates(
        corpus_root=corpus_root,
        selection_seed=_SELECTION_SEED,
        excluded_document_ids=_EXCLUDED_DOCUMENT_IDS,
        profile=CompleteGraphSelectionProfile.NEGATED_RESULT_GRAPH,
    )
    if universe.document_count != _EXPECTED_DOCUMENT_COUNT:
        raise RuntimeError("eighth holdout document universe changed")
    if universe.incompatible_document_ids != _EXPECTED_INCOMPATIBLE_DOCUMENT_IDS:
        raise RuntimeError("eighth holdout importer exclusions changed")
    if len(universe.candidates) != _EXPECTED_CANDIDATE_COUNT:
        raise RuntimeError("eighth holdout candidate count changed")

    selected = min(universe.candidates, key=lambda candidate: candidate.rank)
    projection_set = _projection_set()
    validate_sealed_projection_set(projection_set, unit=selected.unit)
    graph = projection_set.projections[0].graph
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
        raise RuntimeError("pre-registered eighth holdout selection changed")
    return NestedHoldoutSelection(
        case_id=selected.case_id,
        unit=selected.unit,
        expert_graph=graph,
        trial_generation=8,
        selection_seed=_SELECTION_SEED,
        selection_rule=(
            "lowest_sha256_hidden_candidate_with_pre_model_agent_expert_gold"
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


def _projection_set() -> SealedProjectionSet:
    projections = tuple(
        _projection(
            projection_id=projection_id,
            intervention_span=intervention_span,
            intervention_start=intervention_start,
        )
        for projection_id, intervention_span, intervention_start in (
            (
                "agent-expert-canonical",
                "the transfection of CD4+ T cells with RUNX3",
                1937,
            ),
            (
                "agent-expert-intervention-no-determiner",
                "transfection of CD4+ T cells with RUNX3",
                1941,
            ),
        )
    )
    return SealedProjectionSet(
        canonical_projection_id="agent-expert-canonical",
        projections=projections,
    )


def _projection(
    *,
    projection_id: str,
    intervention_span: str,
    intervention_start: int,
) -> SealedGraphProjection:
    shared_arguments = (
        SealedArgument(
            event_role="CONTEXT",
            reference_id="SOURCE-INTERVENTION",
            participant_type="INTERVENTION",
            exact_span=intervention_span,
            source_start=intervention_start,
            source_end=intervention_start + len(intervention_span),
        ),
        SealedArgument(
            event_role="CONTEXT",
            reference_id="SOURCE-POPULATION",
            participant_type="POPULATION",
            exact_span="CD4+ T cells",
            source_start=1957,
            source_end=1969,
        ),
        SealedArgument(
            event_role="CAUSE",
            reference_id="T37",
            participant_type="GENE_OR_PROTEIN",
            exact_span="RUNX3",
            source_start=1975,
            source_end=1980,
        ),
        SealedArgument(
            event_role="THEME",
            reference_id="T38",
            participant_type="GENE_OR_PROTEIN",
            exact_span="FOXP3",
            source_start=2035,
            source_end=2040,
        ),
        SealedArgument(
            event_role="MEASURE",
            reference_id="SOURCE-SIGNIFICANCE",
            participant_type="MEASUREMENT",
            exact_span="statistically significant",
            source_start=1997,
            source_end=2022,
        ),
    )
    events = (
        SealedEvent(
            event_id="AGENT-EXPERT-TREND",
            event_type="POSITIVE_REGULATION",
            trigger=SealedTrigger(
                exact_span="trend",
                source_start=1930,
                source_end=1935,
            ),
            arguments=shared_arguments,
        ),
        SealedEvent(
            event_id="AGENT-EXPERT-SIGNIFICANCE-NULL",
            event_type="POSITIVE_REGULATION",
            trigger=SealedTrigger(
                exact_span="did not lead to statistically significant increase",
                source_start=1981,
                source_end=2031,
            ),
            arguments=shared_arguments,
        ),
    )
    return SealedGraphProjection(
        projection_id=projection_id,
        provenance=ProjectionProvenance.AGENT_EXPERT_ADJUDICATED,
        scientific_rationale=(
            "Independent pre-model reviewers preserve the provisional positive "
            "trend separately from the asserted statistical-significance null, "
            "including RUNX3, CD4+ T cells, FOXP3, intervention context, and "
            "the significance measurement."
        ),
        graph=SealedNestedEventGraph(events=events, links=()),
        event_semantics=(
            SealedEventSemantics(
                event_id="AGENT-EXPERT-TREND",
                claim_kind=ClaimKind.SCIENTIFIC_FINDING,
                polarity=InventoryPolarity.SUPPORT,
                epistemic_status=InventoryEpistemicStatus.PROVISIONAL,
            ),
            SealedEventSemantics(
                event_id="AGENT-EXPERT-SIGNIFICANCE-NULL",
                claim_kind=ClaimKind.SCIENTIFIC_FINDING,
                polarity=InventoryPolarity.NULL_RESULT,
                epistemic_status=InventoryEpistemicStatus.ASSERTED,
            ),
        ),
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
    "eighth_projection_set",
    "eighth_unit_identity",
    "select_eighth_nested_event_holdout",
]
