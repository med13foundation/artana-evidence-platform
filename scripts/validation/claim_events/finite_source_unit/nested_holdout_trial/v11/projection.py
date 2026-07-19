"""Source-adjudicated representation families for the V11 holdout."""

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


class V11EventScope(StrEnum):
    """Event-local destinations in the frozen V11 context matrix."""

    REGULATION = "REGULATION"
    EXPRESSION_TARGET = "EXPRESSION_TARGET"
    DIRECT = "DIRECT"


@dataclass(frozen=True, slots=True)
class V11ContextScopeDecision:
    """One material source context and the events it qualifies."""

    context_id: str
    source: _SourceSpan
    participant_type: str
    event_role: str
    event_scopes: frozenset[V11EventScope]
    scientific_rationale: str


_ENDOGENOUS = _SourceSpan("endogenous", 19681, 19691)
_IL4 = _SourceSpan("IL-4", 19692, 19696)
_IFNG = _SourceSpan("IFN-gamma", 19701, 19710)
_BARE_EFFECT = _SourceSpan("effect", 19718, 19724)
_NEGATED_EFFECT = _SourceSpan("not effect", 19714, 19724)
_FULL_NEGATED_EFFECT = _SourceSpan("do not effect", 19711, 19724)
_FOXP3 = _SourceSpan("Foxp3", 19725, 19730)
_FOXP3_EXPRESSION = _SourceSpan("Foxp3 expression", 19725, 19741)
_EXPRESSION = _SourceSpan("expression", 19731, 19741)
_POPULATION = _SourceSpan("naive CD4+ T cells", 19745, 19763)
_CD4_CRE_VARIANT = _SourceSpan("CbfbF/F CD4-cre", 19767, 19782)
_CONTROL_VARIANT = _SourceSpan("CbfbF/F control mice", 19787, 19807)
_TCR_STIMULATION = _SourceSpan("anti-CD3 and anti-CD28 mAbs", 19836, 19863)
_IL2 = _SourceSpan("IL-2", 19865, 19869)
_TGFB = _SourceSpan("TGF-beta", 19874, 19882)
_NEUTRALIZATION_CONDITION = _SourceSpan(
    "in the absence or presence of anti-IL-4 and anti-IFN-gamma neutralizing mAbs",
    19883,
    19959,
)
_NEUTRALIZING_MABS = _SourceSpan(
    "anti-IL-4 and anti-IFN-gamma neutralizing mAbs",
    19913,
    19959,
)

V11_TRIGGER_EQUIVALENCE: Final = (
    _BARE_EFFECT,
    _NEGATED_EFFECT,
    _FULL_NEGATED_EFFECT,
)

V11_EVENT_CONTEXT_SCOPE_MATRIX: Final = (
    V11ContextScopeDecision(
        context_id="endogenous_agent_qualifier",
        source=_ENDOGENOUS,
        participant_type="CONDITION",
        event_role="CONTEXT",
        event_scopes=frozenset({V11EventScope.REGULATION, V11EventScope.DIRECT}),
        scientific_rationale=(
            "The source limits the tested IL-4 and IFN-gamma to endogenous factors."
        ),
    ),
    V11ContextScopeDecision(
        context_id="population",
        source=_POPULATION,
        participant_type="POPULATION",
        event_role="CONTEXT",
        event_scopes=frozenset(V11EventScope),
        scientific_rationale="The finding is scoped to naive CD4-positive T cells.",
    ),
    V11ContextScopeDecision(
        context_id="cd4_cre_variant",
        source=_CD4_CRE_VARIANT,
        participant_type="VARIANT",
        event_role="CONTEXT",
        event_scopes=frozenset(V11EventScope),
        scientific_rationale="The CD4-cre genotype identifies one tested cell source.",
    ),
    V11ContextScopeDecision(
        context_id="control_variant",
        source=_CONTROL_VARIANT,
        participant_type="VARIANT",
        event_role="CONTEXT",
        event_scopes=frozenset(V11EventScope),
        scientific_rationale="The control genotype identifies the comparison source.",
    ),
    V11ContextScopeDecision(
        context_id="tcr_stimulation",
        source=_TCR_STIMULATION,
        participant_type="INTERVENTION",
        event_role="CONTEXT",
        event_scopes=frozenset(V11EventScope),
        scientific_rationale="Anti-CD3/CD28 stimulation qualifies the tested null effect.",
    ),
    V11ContextScopeDecision(
        context_id="il2_stimulation",
        source=_IL2,
        participant_type="INTERVENTION",
        event_role="CONTEXT",
        event_scopes=frozenset(V11EventScope),
        scientific_rationale="IL-2 is an explicit component of the stimulation context.",
    ),
    V11ContextScopeDecision(
        context_id="tgfb_stimulation",
        source=_TGFB,
        participant_type="INTERVENTION",
        event_role="CONTEXT",
        event_scopes=frozenset(V11EventScope),
        scientific_rationale="TGF-beta is an explicit stimulation component.",
    ),
    V11ContextScopeDecision(
        context_id="neutralization_condition",
        source=_NEUTRALIZATION_CONDITION,
        participant_type="CONDITION",
        event_role="CONTEXT",
        event_scopes=frozenset(V11EventScope),
        scientific_rationale="Presence or absence of neutralization qualifies the result.",
    ),
    V11ContextScopeDecision(
        context_id="neutralizing_antibodies",
        source=_NEUTRALIZING_MABS,
        participant_type="INTERVENTION",
        event_role="CONTEXT",
        event_scopes=frozenset(V11EventScope),
        scientific_rationale="The neutralizing antibodies are explicit interventions.",
    ),
)


def eleventh_projection_set() -> SealedProjectionSet:
    """Return the nested, joint-direct, and split-direct V11 families."""

    return SealedProjectionSet(
        canonical_projection_id="bionlp-shared-expression-null-regulation",
        projections=(
            _nested_projection(),
            _joint_direct_projection(),
            _split_direct_projection(),
        ),
    )


def _nested_projection() -> SealedGraphProjection:
    il4 = _regulation_event("V11-IL4-NULL-REGULATION", _IL4)
    ifng = _regulation_event("V11-IFNG-NULL-REGULATION", _IFNG)
    expression = SealedEvent(
        event_id="V11-FOXP3-EXPRESSION",
        event_type="EXPRESSION",
        trigger=_trigger(_EXPRESSION),
        arguments=(
            _argument("THEME", "GENE_OR_PROTEIN", _FOXP3),
            *_context_arguments(V11EventScope.EXPRESSION_TARGET),
        ),
    )
    graph = SealedNestedEventGraph(
        events=(il4, ifng, expression),
        links=(
            _expression_link(il4.event_id, expression.event_id),
            _expression_link(ifng.event_id, expression.event_id),
        ),
    )
    return SealedGraphProjection(
        projection_id="bionlp-shared-expression-null-regulation",
        provenance=ProjectionProvenance.BIONLP_EXPERT,
        scientific_rationale=(
            "BioNLP encodes two negated REGULATION events, caused by IL-4 and "
            "IFN-gamma, that share one controlled Foxp3 EXPRESSION target. The "
            "population and genotypes scope every event; experimental "
            "interventions and neutralization conditions scope the tested "
            "regulation events."
        ),
        graph=graph,
        event_semantics=(
            _asserted_null_semantics(il4.event_id),
            _asserted_null_semantics(ifng.event_id),
            _controlled_target_semantics(expression.event_id),
        ),
    )


def _joint_direct_projection() -> SealedGraphProjection:
    event = SealedEvent(
        event_id="V11-JOINT-DIRECT-NO-EFFECT",
        event_type="NO_EFFECT",
        trigger=_trigger(_NEGATED_EFFECT),
        trigger_alternatives=_trigger_alternatives(_NEGATED_EFFECT),
        arguments=(
            _argument("AGENT", "GENE_OR_PROTEIN", _IL4),
            _argument("AGENT", "GENE_OR_PROTEIN", _IFNG),
            _argument("THEME", "GENE_OR_PROTEIN", _FOXP3),
            _argument("EFFECT", "OUTCOME", _FOXP3_EXPRESSION),
            *_context_arguments(V11EventScope.DIRECT),
        ),
    )
    return SealedGraphProjection(
        projection_id="source-only-joint-direct-null-effect",
        provenance=ProjectionProvenance.SOURCE_VALID_ALTERNATIVE,
        scientific_rationale=(
            "The coordinated source subject permits one joint NO_EFFECT event. "
            "AGENT roles preserve the tested agents without asserting a realized "
            "causal effect."
        ),
        graph=SealedNestedEventGraph(events=(event,), links=()),
        event_semantics=(_asserted_null_semantics(event.event_id),),
    )


def _split_direct_projection() -> SealedGraphProjection:
    il4 = _direct_event("V11-IL4-DIRECT-NO-EFFECT", _IL4)
    ifng = _direct_event("V11-IFNG-DIRECT-NO-EFFECT", _IFNG)
    return SealedGraphProjection(
        projection_id="source-only-split-direct-null-effect",
        provenance=ProjectionProvenance.SOURCE_VALID_ALTERNATIVE,
        scientific_rationale=(
            "The two expert-authored negated regulation events also permit two "
            "source-only direct NO_EFFECT events with shared outcome and context."
        ),
        graph=SealedNestedEventGraph(events=(il4, ifng), links=()),
        event_semantics=(
            _asserted_null_semantics(il4.event_id),
            _asserted_null_semantics(ifng.event_id),
        ),
    )


def _regulation_event(event_id: str, cause: _SourceSpan) -> SealedEvent:
    return SealedEvent(
        event_id=event_id,
        event_type="REGULATION",
        trigger=_trigger(_BARE_EFFECT),
        trigger_alternatives=_trigger_alternatives(_BARE_EFFECT),
        arguments=(
            _argument("CAUSE", "GENE_OR_PROTEIN", cause),
            *_context_arguments(V11EventScope.REGULATION),
        ),
    )


def _direct_event(event_id: str, agent: _SourceSpan) -> SealedEvent:
    return SealedEvent(
        event_id=event_id,
        event_type="NO_EFFECT",
        trigger=_trigger(_NEGATED_EFFECT),
        trigger_alternatives=_trigger_alternatives(_NEGATED_EFFECT),
        arguments=(
            _argument("AGENT", "GENE_OR_PROTEIN", agent),
            _argument("THEME", "GENE_OR_PROTEIN", _FOXP3),
            _argument("EFFECT", "OUTCOME", _FOXP3_EXPRESSION),
            *_context_arguments(V11EventScope.DIRECT),
        ),
    )


def _expression_link(controller_id: str, target_id: str) -> SealedEventLink:
    return SealedEventLink(
        controller_event_id=controller_id,
        event_role="THEME",
        controlled_event_id=target_id,
        controller_argument=SealedReferenceArgument(
            participant_type="BIOLOGICAL_PROCESS",
            exact_span=_FOXP3_EXPRESSION.exact,
            source_start=_FOXP3_EXPRESSION.start,
            source_end=_FOXP3_EXPRESSION.end,
        ),
    )


def _context_arguments(scope: V11EventScope) -> tuple[SealedArgument, ...]:
    return tuple(
        _argument(
            decision.event_role,
            decision.participant_type,
            decision.source,
        )
        for decision in V11_EVENT_CONTEXT_SCOPE_MATRIX
        if scope in decision.event_scopes
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


def _trigger(
    source: _SourceSpan,
) -> SealedTrigger:
    return SealedTrigger(source.exact, source.start, source.end)


def _trigger_alternatives(canonical: _SourceSpan) -> tuple[SealedTrigger, ...]:
    return tuple(
        _trigger(source) for source in V11_TRIGGER_EQUIVALENCE if source != canonical
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
    "V11ContextScopeDecision",
    "V11EventScope",
    "V11_EVENT_CONTEXT_SCOPE_MATRIX",
    "V11_TRIGGER_EQUIVALENCE",
    "eleventh_projection_set",
]
