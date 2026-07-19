"""Source-adjudicated representation family for the V10 holdout."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimKind,
    InventoryAssertionScope,
    InventoryEpistemicStatus,
    InventoryPolarity,
)

from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.selection import (
    ProjectionProvenance,
    SealedArgument,
    SealedEvent,
    SealedEventLink,
    SealedEventSemantics,
    SealedGraphProjection,
    SealedNestedEventGraph,
    SealedProjectionSet,
    SealedReferenceArgument,
    SealedTrigger,
)


@dataclass(frozen=True, slots=True)
class _SourceSpan:
    exact: str
    start: int
    end: int


class V10CueMode(StrEnum):
    """Scientifically distinct trigger policies admitted by V10."""

    BIONLP_CORPUS_NATIVE = "BIONLP_CORPUS_NATIVE"
    SOURCE_ONLY_MATERIAL_NEGATION = "SOURCE_ONLY_MATERIAL_NEGATION"


class V10EventScope(StrEnum):
    """Event-local destinations used by the frozen context-scope matrix."""

    BIONLP_OUTER = "BIONLP_OUTER"
    BIONLP_CONTROLLED_TARGET = "BIONLP_CONTROLLED_TARGET"
    SOURCE_ONLY_DIRECT = "SOURCE_ONLY_DIRECT"


@dataclass(frozen=True, slots=True)
class V10ContextScopeDecision:
    """One source-context decision sealed before V10 agent execution."""

    context_id: str
    exact_span: str
    source_start: int
    source_end: int
    participant_type: str | None
    event_role: str | None
    event_scopes: frozenset[V10EventScope]
    embedded_in_context_id: str | None
    scientific_rationale: str


_POPULATION = _SourceSpan("pre-existing iTreg cells", 2632, 2656)
_PRE_EXISTING_STATE = _SourceSpan("pre-existing", 2632, 2644)
_FOXP3 = _SourceSpan("FOXP3", 2674, 2679)
_EXPRESSION = _SourceSpan("FOXP3 expression", 2674, 2690)
_IL4 = _SourceSpan("IL-4", 2696, 2700)
_EXPOSURE = _SourceSpan("IL-4 exposure", 2696, 2709)
_TIMEFRAME = _SourceSpan("upon IL-4 exposure", 2691, 2709)

_CUES_BY_MODE: Final = {
    V10CueMode.BIONLP_CORPUS_NATIVE: SealedTrigger("decrease", 2665, 2673),
    V10CueMode.SOURCE_ONLY_MATERIAL_NEGATION: SealedTrigger(
        "not decrease",
        2661,
        2673,
    ),
}

V10_EVENT_CONTEXT_SCOPE_MATRIX: Final = (
    V10ContextScopeDecision(
        context_id="population_identity",
        exact_span=_POPULATION.exact,
        source_start=_POPULATION.start,
        source_end=_POPULATION.end,
        participant_type="POPULATION",
        event_role="CONTEXT",
        event_scopes=frozenset(V10EventScope),
        embedded_in_context_id=None,
        scientific_rationale=(
            "The pre-existing iTreg population is material to both the tested "
            "change and the controlled expression target."
        ),
    ),
    V10ContextScopeDecision(
        context_id="exposure",
        exact_span=_EXPOSURE.exact,
        source_start=_EXPOSURE.start,
        source_end=_EXPOSURE.end,
        participant_type="EXPOSURE",
        event_role="CONTEXT",
        event_scopes=frozenset(
            {
                V10EventScope.BIONLP_OUTER,
                V10EventScope.SOURCE_ONLY_DIRECT,
            }
        ),
        embedded_in_context_id=None,
        scientific_rationale=(
            "The exposure scopes the tested decrease, not the unasserted "
            "FOXP3-expression target by itself."
        ),
    ),
    V10ContextScopeDecision(
        context_id="exposure_timeframe",
        exact_span=_TIMEFRAME.exact,
        source_start=_TIMEFRAME.start,
        source_end=_TIMEFRAME.end,
        participant_type="TIMEFRAME",
        event_role="CONTEXT",
        event_scopes=frozenset(
            {
                V10EventScope.BIONLP_OUTER,
                V10EventScope.SOURCE_ONLY_DIRECT,
            }
        ),
        embedded_in_context_id=None,
        scientific_rationale=(
            "The temporal phrase scopes the tested decrease and does not "
            "independently assert a timeframe for the controlled target."
        ),
    ),
    V10ContextScopeDecision(
        context_id="pre_existing_state",
        exact_span=_PRE_EXISTING_STATE.exact,
        source_start=_PRE_EXISTING_STATE.start,
        source_end=_PRE_EXISTING_STATE.end,
        participant_type=None,
        event_role=None,
        event_scopes=frozenset(),
        embedded_in_context_id="population_identity",
        scientific_rationale=(
            "Pre-existing defines the source population identity; the source "
            "does not assert it as a separate event timeframe."
        ),
    ),
)


def tenth_projection_set() -> SealedProjectionSet:
    """Return the corpus-native and source-only V10 representations."""

    return SealedProjectionSet(
        canonical_projection_id="bionlp-nested-null-decrease",
        projections=(
            _nested_projection(),
            _source_only_direct_projection(),
        ),
    )


def _nested_projection() -> SealedGraphProjection:
    outer = _event(
        event_id="V10-IL4-NULL-DECREASE",
        event_type="NEGATIVE_REGULATION",
        arguments=(
            _argument("CAUSE", "GENE_OR_PROTEIN", _IL4),
            *_context_arguments(V10EventScope.BIONLP_OUTER),
        ),
        cue_mode=V10CueMode.BIONLP_CORPUS_NATIVE,
    )
    inner = SealedEvent(
        event_id="V10-FOXP3-EXPRESSION",
        event_type="EXPRESSION",
        trigger=SealedTrigger("expression", 2680, 2690),
        arguments=(
            _argument("THEME", "GENE_OR_PROTEIN", _FOXP3),
            *_context_arguments(V10EventScope.BIONLP_CONTROLLED_TARGET),
        ),
    )
    graph = SealedNestedEventGraph(
        events=(outer, inner),
        links=(
            SealedEventLink(
                controller_event_id=outer.event_id,
                event_role="THEME",
                controlled_event_id=inner.event_id,
                controller_argument=SealedReferenceArgument(
                    participant_type="BIOLOGICAL_PROCESS",
                    exact_span=_EXPRESSION.exact,
                    source_start=_EXPRESSION.start,
                    source_end=_EXPRESSION.end,
                ),
            ),
        ),
    )
    return SealedGraphProjection(
        projection_id="bionlp-nested-null-decrease",
        provenance=ProjectionProvenance.BIONLP_EXPERT,
        scientific_rationale=(
            "BioNLP E30 is a negated NEGATIVE_REGULATION controller whose cause "
            "is IL-4 and whose theme is E31, FOXP3 Gene_expression. Its corpus-native "
            "bare decrease trigger is qualified by BioNLP M11 negation, represented "
            "here as NULL_RESULT. Population scopes both events; exposure and its "
            "timeframe scope only the outer tested change."
        ),
        graph=graph,
        event_semantics=(
            _asserted_null_semantics(outer.event_id),
            _controlled_target_semantics(inner.event_id),
        ),
    )


def _source_only_direct_projection() -> SealedGraphProjection:
    event = _event(
        event_id="V10-SOURCE-ONLY-FOXP3-NULL-DECREASE",
        event_type="DECREASE",
        arguments=(
            _argument("THEME", "GENE_OR_PROTEIN", _FOXP3),
            _argument("EFFECT", "OUTCOME", _EXPRESSION),
            *_context_arguments(V10EventScope.SOURCE_ONLY_DIRECT),
        ),
        cue_mode=V10CueMode.SOURCE_ONLY_MATERIAL_NEGATION,
    )
    graph = SealedNestedEventGraph(events=(event,), links=())
    return SealedGraphProjection(
        projection_id="source-only-noncausal-direct-null-decrease",
        provenance=ProjectionProvenance.SOURCE_VALID_ALTERNATIVE,
        scientific_rationale=(
            "The source-only production policy does not infer causation from upon "
            "IL-4 exposure. It therefore preserves the asserted null DECREASE, "
            "FOXP3 theme, expression outcome, pre-existing iTreg population, and "
            "exposure/timeframe context without assigning IL-4 a CAUSE role. Its "
            "cue retains the shortest material negation: not decrease."
        ),
        graph=graph,
        event_semantics=(_asserted_null_semantics(event.event_id),),
    )


def _event(
    *,
    event_id: str,
    event_type: str,
    arguments: tuple[SealedArgument, ...],
    cue_mode: V10CueMode,
) -> SealedEvent:
    return SealedEvent(
        event_id=event_id,
        event_type=event_type,
        trigger=_CUES_BY_MODE[cue_mode],
        arguments=arguments,
    )


def _context_arguments(scope: V10EventScope) -> tuple[SealedArgument, ...]:
    return tuple(
        _argument(
            decision.event_role,
            decision.participant_type,
            _SourceSpan(
                decision.exact_span,
                decision.source_start,
                decision.source_end,
            ),
        )
        for decision in V10_EVENT_CONTEXT_SCOPE_MATRIX
        if scope in decision.event_scopes
        and decision.event_role is not None
        and decision.participant_type is not None
    )


def _argument(
    event_role: str,
    participant_type: str,
    source: _SourceSpan,
) -> SealedArgument:
    return SealedArgument(
        event_role=event_role,
        reference_id=f"SOURCE-{source.start}-{source.end}-{participant_type}",
        participant_type=participant_type,
        exact_span=source.exact,
        source_start=source.start,
        source_end=source.end,
    )


def _asserted_null_semantics(event_id: str) -> SealedEventSemantics:
    return SealedEventSemantics(
        event_id=event_id,
        claim_kind=ClaimKind.SCIENTIFIC_FINDING,
        polarity=InventoryPolarity.NULL_RESULT,
        epistemic_status=InventoryEpistemicStatus.ASSERTED,
    )


def _controlled_target_semantics(event_id: str) -> SealedEventSemantics:
    return SealedEventSemantics(
        event_id=event_id,
        claim_kind=ClaimKind.SCIENTIFIC_FINDING,
        polarity=InventoryPolarity.UNSCOPED,
        epistemic_status=InventoryEpistemicStatus.UNASSERTED,
        assertion_scope=InventoryAssertionScope.CONTROLLED_TARGET,
    )


__all__ = [
    "V10ContextScopeDecision",
    "V10CueMode",
    "V10EventScope",
    "V10_EVENT_CONTEXT_SCOPE_MATRIX",
    "tenth_projection_set",
]
