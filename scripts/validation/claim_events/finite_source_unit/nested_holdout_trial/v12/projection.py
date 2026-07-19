"""Source-complete representation families for the frozen V12 title claim."""

from __future__ import annotations

from dataclasses import dataclass

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


_REGULATION = _SourceSpan("Regulation", 0, 10)
_REGULATION_OF = _SourceSpan("Regulation of", 0, 13)
_FAS_LIGAND = _SourceSpan("Fas ligand", 14, 24)
_FAS_LIGAND_EXPRESSION = _SourceSpan("Fas ligand expression", 14, 35)
_EXPRESSION = _SourceSpan("expression", 25, 35)
_CELL_DEATH = _SourceSpan("cell death", 40, 50)
_ALG4 = _SourceSpan("apoptosis-linked gene 4", 54, 77)


def twelfth_projection_set() -> SealedProjectionSet:
    """Return four source-complete V12 representation families."""

    return SealedProjectionSet(
        canonical_projection_id="source-complete-split-nested-regulation",
        projections=(
            _split_nested_projection(),
            _joint_nested_projection(),
            _split_direct_projection(),
            _joint_direct_projection(),
        ),
    )


def _split_nested_projection() -> SealedGraphProjection:
    expression_controller = _controller("V12-EXPRESSION-REGULATION")
    death_controller = _controller("V12-CELL-DEATH-REGULATION")
    expression = _expression_target()
    death = _cell_death_target()
    graph = SealedNestedEventGraph(
        events=(expression_controller, death_controller, expression, death),
        links=(
            _link(
                expression_controller.event_id,
                expression.event_id,
                _FAS_LIGAND_EXPRESSION,
            ),
            _link(death_controller.event_id, death.event_id, _CELL_DEATH),
        ),
    )
    return SealedGraphProjection(
        projection_id="source-complete-split-nested-regulation",
        provenance=ProjectionProvenance.AGENT_EXPERT_ADJUDICATED,
        scientific_rationale=(
            "The title coordinates two complete regulation targets. Separate "
            "controllers preserve each target without inferring direction or a "
            "causal link between expression and cell death."
        ),
        graph=graph,
        event_semantics=(
            _asserted_semantics(expression_controller.event_id),
            _asserted_semantics(death_controller.event_id),
            _controlled_semantics(expression.event_id),
            _controlled_semantics(death.event_id),
        ),
    )


def _joint_nested_projection() -> SealedGraphProjection:
    controller = SealedEvent(
        event_id="V12-JOINT-NESTED-REGULATION",
        event_type="REGULATION",
        trigger=_trigger(_REGULATION),
        trigger_alternatives=(_trigger(_REGULATION_OF),),
        arguments=(_argument("CAUSE", "GENE_OR_PROTEIN", _ALG4),),
    )
    expression = _expression_target()
    death = _cell_death_target()
    graph = SealedNestedEventGraph(
        events=(controller, expression, death),
        links=(
            _link(controller.event_id, expression.event_id, _FAS_LIGAND_EXPRESSION),
            _link(controller.event_id, death.event_id, _CELL_DEATH),
        ),
    )
    return SealedGraphProjection(
        projection_id="source-complete-joint-nested-regulation",
        provenance=ProjectionProvenance.SOURCE_VALID_ALTERNATIVE,
        scientific_rationale=(
            "One controller may reference both coordinated targets when each "
            "target remains separately typed and linked."
        ),
        graph=graph,
        event_semantics=(
            _asserted_semantics(controller.event_id),
            _controlled_semantics(expression.event_id),
            _controlled_semantics(death.event_id),
        ),
    )


def _split_direct_projection() -> SealedGraphProjection:
    expression = _direct_expression_event("V12-DIRECT-EXPRESSION-REGULATION")
    death = _direct_death_event("V12-DIRECT-CELL-DEATH-REGULATION")
    return SealedGraphProjection(
        projection_id="source-complete-split-direct-regulation",
        provenance=ProjectionProvenance.SOURCE_VALID_ALTERNATIVE,
        scientific_rationale=(
            "Two direct events preserve the coordinated targets without claiming "
            "that either target occurred or that one caused the other."
        ),
        graph=SealedNestedEventGraph(events=(expression, death), links=()),
        event_semantics=(
            _asserted_semantics(expression.event_id),
            _asserted_semantics(death.event_id),
        ),
    )


def _joint_direct_projection() -> SealedGraphProjection:
    with_gene_theme = (
        _argument("CAUSE", "GENE_OR_PROTEIN", _ALG4),
        _argument("THEME", "GENE_OR_PROTEIN", _FAS_LIGAND),
        _argument("EFFECT", "OUTCOME", _FAS_LIGAND_EXPRESSION),
        _argument("EFFECT", "OUTCOME", _CELL_DEATH),
    )
    event = SealedEvent(
        event_id="V12-JOINT-DIRECT-REGULATION",
        event_type="REGULATION",
        trigger=_trigger(_REGULATION),
        trigger_alternatives=(_trigger(_REGULATION_OF),),
        arguments=with_gene_theme,
    )
    return SealedGraphProjection(
        projection_id="source-complete-joint-direct-regulation",
        provenance=ProjectionProvenance.SOURCE_VALID_ALTERNATIVE,
        scientific_rationale=(
            "One direct event is acceptable only when both coordinated outcomes "
            "remain separate arguments."
        ),
        graph=SealedNestedEventGraph(events=(event,), links=()),
        event_semantics=(_asserted_semantics(event.event_id),),
    )


def _controller(event_id: str) -> SealedEvent:
    return SealedEvent(
        event_id=event_id,
        event_type="REGULATION",
        trigger=_trigger(_REGULATION),
        trigger_alternatives=(_trigger(_REGULATION_OF),),
        arguments=(_argument("CAUSE", "GENE_OR_PROTEIN", _ALG4),),
    )


def _expression_target() -> SealedEvent:
    return SealedEvent(
        event_id="V12-FAS-LIGAND-EXPRESSION",
        event_type="EXPRESSION",
        trigger=_trigger(_EXPRESSION),
        arguments=(_argument("THEME", "GENE_OR_PROTEIN", _FAS_LIGAND),),
    )


def _cell_death_target() -> SealedEvent:
    return SealedEvent(
        event_id="V12-CELL-DEATH",
        event_type="OTHER_EXPLICIT",
        trigger=_trigger(_CELL_DEATH),
        arguments=(_argument("THEME", "OUTCOME", _CELL_DEATH),),
    )


def _direct_expression_event(event_id: str) -> SealedEvent:
    return SealedEvent(
        event_id=event_id,
        event_type="REGULATION",
        trigger=_trigger(_REGULATION),
        trigger_alternatives=(_trigger(_REGULATION_OF),),
        arguments=(
            _argument("CAUSE", "GENE_OR_PROTEIN", _ALG4),
            _argument("THEME", "GENE_OR_PROTEIN", _FAS_LIGAND),
            _argument("EFFECT", "OUTCOME", _FAS_LIGAND_EXPRESSION),
        ),
    )


def _direct_death_event(event_id: str) -> SealedEvent:
    return SealedEvent(
        event_id=event_id,
        event_type="REGULATION",
        trigger=_trigger(_REGULATION),
        trigger_alternatives=(_trigger(_REGULATION_OF),),
        arguments=(
            _argument("CAUSE", "GENE_OR_PROTEIN", _ALG4),
            _argument("EFFECT", "OUTCOME", _CELL_DEATH),
        ),
    )


def _link(controller_id: str, target_id: str, span: _SourceSpan) -> SealedEventLink:
    return SealedEventLink(
        controller_event_id=controller_id,
        event_role="THEME",
        controlled_event_id=target_id,
        controller_argument=SealedReferenceArgument(
            participant_type="BIOLOGICAL_PROCESS",
            exact_span=span.exact,
            source_start=span.start,
            source_end=span.end,
        ),
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


def _trigger(source: _SourceSpan) -> SealedTrigger:
    return SealedTrigger(source.exact, source.start, source.end)


def _asserted_semantics(event_id: str) -> SealedEventSemantics:
    return SealedEventSemantics(
        event_id=event_id,
        claim_kind=ClaimKind.SCIENTIFIC_FINDING,
        polarity=InventoryPolarity.SUPPORT,
        epistemic_status=InventoryEpistemicStatus.ASSERTED,
    )


def _controlled_semantics(event_id: str) -> SealedEventSemantics:
    return SealedEventSemantics(
        event_id=event_id,
        claim_kind=ClaimKind.SCIENTIFIC_FINDING,
        polarity=InventoryPolarity.UNSCOPED,
        epistemic_status=InventoryEpistemicStatus.UNASSERTED,
        assertion_scope=InventoryAssertionScope.CONTROLLED_TARGET,
    )


__all__ = ["twelfth_projection_set"]
