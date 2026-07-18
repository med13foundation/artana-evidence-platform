"""Source-adjudicated finite projection family for the V9 holdout."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from itertools import product

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


class _CauseShape(StrEnum):
    SPLIT_INTERVENTION_AND_MOLECULE = "split-cause"
    WHOLE_PROTEIN_CAUSE = "whole-cause"


class _TreatmentShape(StrEnum):
    COMPOUND = "compound-treatment"
    DECOMPOSED = "decomposed-treatment"


class _ProliferationCue(StrEnum):
    COMPLETE = "complete-proliferation-cue"
    HEAD = "proliferative-head-cue"


class _SupportedTargetShape(StrEnum):
    ATOMIC = "atomic-supported-targets"
    GROUPED = "grouped-supported-target"


class _NullTargetShape(StrEnum):
    ATOMIC = "atomic-null-targets"
    GROUPED = "grouped-null-target"


@dataclass(frozen=True, slots=True)
class _SourceSpan:
    exact: str
    start: int
    end: int


def ninth_projection_set() -> SealedProjectionSet:
    """Return every pre-model source-valid V9 event representation."""

    nested_projections = tuple(
        _projection(cue, supported_shape, null_shape)
        for cue, supported_shape, null_shape in product(
            _ProliferationCue,
            _SupportedTargetShape,
            _NullTargetShape,
        )
    )
    direct_projections = tuple(
        _source_valid_direct_projection(cue) for cue in _ProliferationCue
    )
    corpus_native_projections = tuple(
        _corpus_native_nested_projection(cue) for cue in _ProliferationCue
    )
    return SealedProjectionSet(
        canonical_projection_id=(
            f"{_ProliferationCue.COMPLETE.value}__bionlp-expert-nested-restoration"
        ),
        projections=(
            *nested_projections,
            *direct_projections,
            *corpus_native_projections,
        ),
    )


def _projection(
    cue: _ProliferationCue,
    supported_shape: _SupportedTargetShape,
    null_shape: _NullTargetShape,
) -> SealedGraphProjection:
    graph = _graph(cue, supported_shape, null_shape)
    return SealedGraphProjection(
        projection_id=_projection_id(cue, supported_shape, null_shape),
        provenance=ProjectionProvenance.AGENT_EXPERT_ADJUDICATED,
        scientific_rationale=(
            "Independent source-only reviewers require one grouped supported "
            "restoration controller, one grouped null restoration controller, "
            "all five source-distinct cytokine themes, treatment and Rel-/- T-cell "
            "context, and the approximate-normal comparator. The source permits "
            "the three supported and two null expression targets to be represented "
            "as grouped multi-theme events or equivalent atomic events. Event-local "
            "argument alternatives preserve independently valid cause and treatment "
            "shapes without mixing incomplete projections."
        ),
        graph=graph,
        event_semantics=tuple(_semantics(event.event_id) for event in graph.events),
    )


def _projection_id(
    cue: _ProliferationCue,
    supported_shape: _SupportedTargetShape,
    null_shape: _NullTargetShape,
) -> str:
    return f"{cue.value}__{supported_shape.value}__{null_shape.value}"


def _source_valid_direct_projection(cue: _ProliferationCue) -> SealedGraphProjection:
    graph = _source_valid_direct_graph(cue)
    return SealedGraphProjection(
        projection_id=f"{cue.value}__source-valid-direct-atomic-restoration",
        provenance=ProjectionProvenance.SOURCE_VALID_ALTERNATIVE,
        scientific_rationale=(
            "A source-valid direct representation preserves each cytokine as an "
            "atomic POSITIVE_REGULATION event sharing the restores trigger, with "
            "NULL_RESULT polarity for IL-3 and GM-CSF. It retains cause, treatment, "
            "population, variant, process, and comparator without claiming to be "
            "the official nested BioNLP topology."
        ),
        graph=graph,
        event_semantics=tuple(_semantics(event.event_id) for event in graph.events),
    )


def _source_valid_direct_graph(cue: _ProliferationCue) -> SealedNestedEventGraph:
    cytokine_events = tuple(
        _direct_atomic_restoration_event(
            event_id=event_id,
            gene=_SourceSpan(gene, start, end),
            process=process,
        )
        for event_id, gene, start, end, process in (
            (
                "V9-DIRECT-SUPPORT-IL5",
                "IL-5",
                1404,
                1408,
                _SourceSpan("production", 1390, 1400),
            ),
            (
                "V9-DIRECT-SUPPORT-TNF",
                "TNF-alpha",
                1410,
                1419,
                _SourceSpan("production", 1390, 1400),
            ),
            (
                "V9-DIRECT-SUPPORT-IFNG",
                "IFN-gamma",
                1425,
                1434,
                _SourceSpan("production", 1390, 1400),
            ),
            (
                "V9-DIRECT-NULL-IL3",
                "IL-3",
                1444,
                1448,
                _SourceSpan("expression", 1460, 1470),
            ),
            (
                "V9-DIRECT-NULL-GMCSF",
                "GM-CSF",
                1453,
                1459,
                _SourceSpan("expression", 1460, 1470),
            ),
        )
    )
    events = (
        _event_with_argument_sets(
            event_id="V9-PROLIFERATION-RESTORATION",
            event_type="POSITIVE_REGULATION",
            trigger=SealedTrigger("restitutes", 1288, 1298),
            argument_sets=_relative_controller_argument_sets(),
        ),
        _event_with_argument_sets(
            event_id="V9-PROLIFERATIVE-RESPONSE",
            event_type="PROLIFERATION",
            trigger=_proliferation_trigger(cue),
            argument_sets=_proliferation_argument_sets(),
        ),
        *cytokine_events,
    )
    return SealedNestedEventGraph(
        events=events,
        links=(
            _link(
                "V9-PROLIFERATION-RESTORATION",
                "V9-PROLIFERATIVE-RESPONSE",
                "the proliferative response of the anti-CD3- and "
                "anti-CD28-treated Rel-/- T cells",
                1299,
                1379,
            ),
        ),
    )


def _corpus_native_nested_projection(cue: _ProliferationCue) -> SealedGraphProjection:
    graph = _corpus_native_nested_graph(cue)
    return SealedGraphProjection(
        projection_id=f"{cue.value}__bionlp-expert-nested-restoration",
        provenance=(
            ProjectionProvenance.BIONLP_EXPERT
            if cue is _ProliferationCue.COMPLETE
            else ProjectionProvenance.SOURCE_VALID_ALTERNATIVE
        ),
        scientific_rationale=(
            "BioNLP events E16-E20 are five POSITIVE_REGULATION controllers sharing "
            "restores; E21-E25 are five controlled Gene_expression targets; M1 and "
            "M2 negate the IL-3 and GM-CSF controllers. This projection preserves "
            "that one-to-one nested topology while retaining all source-explicit "
            "treatment, population, variant, process, and comparator context."
        ),
        graph=graph,
        event_semantics=tuple(_semantics(event.event_id) for event in graph.events),
    )


def _corpus_native_nested_graph(cue: _ProliferationCue) -> SealedNestedEventGraph:
    outer_events = tuple(
        _event_with_argument_sets(
            event_id=event_id,
            event_type="POSITIVE_REGULATION",
            trigger=SealedTrigger("restores", 1381, 1389),
            argument_sets=_main_controller_argument_sets(),
        )
        for event_id in (
            "V9-BIONLP-E16",
            "V9-BIONLP-E17",
            "V9-BIONLP-E18",
            "V9-BIONLP-E19",
            "V9-BIONLP-E20",
        )
    )
    inner_events = (
        _expression_event(
            "V9-BIONLP-E21",
            gene=_SourceSpan("TNF-alpha", 1410, 1419),
            cue=_SourceSpan("production", 1390, 1400),
        ),
        _expression_event(
            "V9-BIONLP-E22",
            gene=_SourceSpan("IL-5", 1404, 1408),
            cue=_SourceSpan("production", 1390, 1400),
        ),
        _expression_event(
            "V9-BIONLP-E23",
            gene=_SourceSpan("IFN-gamma", 1425, 1434),
            cue=_SourceSpan("production", 1390, 1400),
        ),
        _expression_event(
            "V9-BIONLP-E24",
            gene=_SourceSpan("GM-CSF", 1453, 1459),
            cue=_SourceSpan("expression", 1460, 1470),
        ),
        _expression_event(
            "V9-BIONLP-E25",
            gene=_SourceSpan("IL-3", 1444, 1448),
            cue=_SourceSpan("expression", 1460, 1470),
        ),
    )
    events = (
        _event_with_argument_sets(
            event_id="V9-PROLIFERATION-RESTORATION",
            event_type="POSITIVE_REGULATION",
            trigger=SealedTrigger("restitutes", 1288, 1298),
            argument_sets=_relative_controller_argument_sets(),
        ),
        _event_with_argument_sets(
            event_id="V9-PROLIFERATIVE-RESPONSE",
            event_type="PROLIFERATION",
            trigger=_proliferation_trigger(cue),
            argument_sets=_proliferation_argument_sets(),
        ),
        *outer_events,
        *inner_events,
    )
    links = (
        _link(
            "V9-PROLIFERATION-RESTORATION",
            "V9-PROLIFERATIVE-RESPONSE",
            "the proliferative response of the anti-CD3- and anti-CD28-treated "
            "Rel-/- T cells",
            1299,
            1379,
        ),
        _link(
            "V9-BIONLP-E16",
            "V9-BIONLP-E23",
            "production of IL-5, TNF-alpha, and IFN-gamma",
            1390,
            1434,
        ),
        _link(
            "V9-BIONLP-E17",
            "V9-BIONLP-E21",
            "production of IL-5, TNF-alpha",
            1390,
            1419,
        ),
        _link(
            "V9-BIONLP-E18",
            "V9-BIONLP-E25",
            "IL-3 and GM-CSF expression",
            1444,
            1470,
        ),
        _link(
            "V9-BIONLP-E19",
            "V9-BIONLP-E22",
            "production of IL-5",
            1390,
            1408,
        ),
        _link(
            "V9-BIONLP-E20",
            "V9-BIONLP-E24",
            "IL-3 and GM-CSF expression",
            1444,
            1470,
        ),
    )
    return SealedNestedEventGraph(events=events, links=links)


def _direct_atomic_restoration_event(
    *,
    event_id: str,
    gene: _SourceSpan,
    process: _SourceSpan,
) -> SealedEvent:
    comparator = _argument(
        "MEASURE",
        "COMPARATOR",
        _SourceSpan("approximately normal levels", 1474, 1501),
    )
    argument_sets = tuple(
        (
            *_main_clause_cause(cause),
            _argument("THEME", "GENE_OR_PROTEIN", gene),
            _argument("EFFECT", "OUTCOME", process),
            *_shared_context(treatment),
            comparator,
        )
        for cause, treatment in product(_CauseShape, _TreatmentShape)
    )
    return _event_with_argument_sets(
        event_id=event_id,
        event_type="POSITIVE_REGULATION",
        trigger=SealedTrigger("restores", 1381, 1389),
        argument_sets=argument_sets,
    )


def _graph(
    cue: _ProliferationCue,
    supported_shape: _SupportedTargetShape,
    null_shape: _NullTargetShape,
) -> SealedNestedEventGraph:
    supported_events = _supported_expression_events(supported_shape)
    null_events = _null_expression_events(null_shape)
    events = (
        _event_with_argument_sets(
            event_id="V9-PROLIFERATION-RESTORATION",
            event_type="POSITIVE_REGULATION",
            trigger=SealedTrigger("restitutes", 1288, 1298),
            argument_sets=_relative_controller_argument_sets(),
        ),
        _event_with_argument_sets(
            event_id="V9-PROLIFERATIVE-RESPONSE",
            event_type="PROLIFERATION",
            trigger=_proliferation_trigger(cue),
            argument_sets=_proliferation_argument_sets(),
        ),
        _event_with_argument_sets(
            event_id="V9-CYTOKINE-RESTORATION-SUPPORT",
            event_type="POSITIVE_REGULATION",
            trigger=SealedTrigger("restores", 1381, 1389),
            argument_sets=_main_controller_argument_sets(),
        ),
        *supported_events,
        _event_with_argument_sets(
            event_id="V9-CYTOKINE-RESTORATION-NULL",
            event_type="POSITIVE_REGULATION",
            trigger=SealedTrigger("not", 1440, 1443),
            argument_sets=_main_controller_argument_sets(),
        ),
        *null_events,
    )
    links = (
        _link(
            "V9-PROLIFERATION-RESTORATION",
            "V9-PROLIFERATIVE-RESPONSE",
            "the proliferative response of the anti-CD3- and anti-CD28-treated "
            "Rel-/- T cells",
            1299,
            1379,
        ),
        *tuple(
            _link(
                "V9-CYTOKINE-RESTORATION-SUPPORT",
                controlled_event.event_id,
                "production of IL-5, TNF-alpha, and IFN-gamma",
                1390,
                1434,
            )
            for controlled_event in supported_events
        ),
        *tuple(
            _link(
                "V9-CYTOKINE-RESTORATION-NULL",
                controlled_event.event_id,
                "IL-3 and GM-CSF expression",
                1444,
                1470,
            )
            for controlled_event in null_events
        ),
    )
    return SealedNestedEventGraph(events=events, links=links)


def _event_with_argument_sets(
    *,
    event_id: str,
    event_type: str,
    trigger: SealedTrigger,
    argument_sets: tuple[tuple[SealedArgument, ...], ...],
) -> SealedEvent:
    return SealedEvent(
        event_id=event_id,
        event_type=event_type,
        trigger=trigger,
        arguments=argument_sets[0],
        argument_alternatives=argument_sets[1:],
    )


def _relative_controller_argument_sets() -> tuple[tuple[SealedArgument, ...], ...]:
    return tuple(
        (*_relative_clause_cause(cause), *_shared_context(treatment))
        for cause, treatment in product(_CauseShape, _TreatmentShape)
    )


def _main_controller_argument_sets() -> tuple[tuple[SealedArgument, ...], ...]:
    comparator = _argument(
        "MEASURE",
        "COMPARATOR",
        _SourceSpan("approximately normal levels", 1474, 1501),
    )
    return tuple(
        (*_main_clause_cause(cause), *_shared_context(treatment), comparator)
        for cause, treatment in product(_CauseShape, _TreatmentShape)
    )


def _proliferation_argument_sets() -> tuple[tuple[SealedArgument, ...], ...]:
    return tuple(
        (
            _argument(
                "THEME",
                "POPULATION",
                _SourceSpan("Rel-/- T cells", 1365, 1379),
            ),
            *_treatment_arguments(treatment),
            _argument(
                "CONTEXT",
                "VARIANT",
                _SourceSpan("Rel-/-", 1365, 1371),
            ),
        )
        for treatment in _TreatmentShape
    )


def _expression_event(
    event_id: str,
    *,
    gene: _SourceSpan,
    cue: _SourceSpan,
) -> SealedEvent:
    argument_sets = tuple(
        (
            _argument("THEME", "GENE_OR_PROTEIN", gene),
            *_shared_context(treatment),
        )
        for treatment in _TreatmentShape
    )
    return _event_with_argument_sets(
        event_id=event_id,
        event_type="EXPRESSION",
        trigger=SealedTrigger(cue.exact, cue.start, cue.end),
        argument_sets=argument_sets,
    )


def _supported_expression_events(
    shape: _SupportedTargetShape,
) -> tuple[SealedEvent, ...]:
    genes = (
        ("V9-IL5-EXPRESSION", _SourceSpan("IL-5", 1404, 1408)),
        ("V9-TNF-EXPRESSION", _SourceSpan("TNF-alpha", 1410, 1419)),
        ("V9-IFNG-EXPRESSION", _SourceSpan("IFN-gamma", 1425, 1434)),
    )
    cue = _SourceSpan("production", 1390, 1400)
    if shape is _SupportedTargetShape.GROUPED:
        return (
            _grouped_expression_event(
                "V9-SUPPORTED-CYTOKINES-EXPRESSION",
                genes=tuple(gene for _, gene in genes),
                cue=cue,
            ),
        )
    return tuple(
        _expression_event(event_id, gene=gene, cue=cue) for event_id, gene in genes
    )


def _null_expression_events(shape: _NullTargetShape) -> tuple[SealedEvent, ...]:
    genes = (
        ("V9-IL3-EXPRESSION", _SourceSpan("IL-3", 1444, 1448)),
        ("V9-GMCSF-EXPRESSION", _SourceSpan("GM-CSF", 1453, 1459)),
    )
    cue = _SourceSpan("expression", 1460, 1470)
    if shape is _NullTargetShape.GROUPED:
        return (
            _grouped_expression_event(
                "V9-NULL-CYTOKINES-EXPRESSION",
                genes=tuple(gene for _, gene in genes),
                cue=cue,
            ),
        )
    return tuple(
        _expression_event(event_id, gene=gene, cue=cue) for event_id, gene in genes
    )


def _grouped_expression_event(
    event_id: str,
    *,
    genes: tuple[_SourceSpan, ...],
    cue: _SourceSpan,
) -> SealedEvent:
    argument_sets = tuple(
        (
            *(_argument("THEME", "GENE_OR_PROTEIN", gene) for gene in genes),
            *_shared_context(treatment),
        )
        for treatment in _TreatmentShape
    )
    return _event_with_argument_sets(
        event_id=event_id,
        event_type="EXPRESSION",
        trigger=SealedTrigger(cue.exact, cue.start, cue.end),
        argument_sets=argument_sets,
    )


def _relative_clause_cause(shape: _CauseShape) -> tuple[SealedArgument, ...]:
    referent = SealedReferenceArgument(
        participant_type="GENE_OR_PROTEIN",
        exact_span="Exogenous IL-2",
        source_start=1266,
        source_end=1280,
    )
    anaphoric_cause = _argument(
        "CAUSE",
        "GENE_OR_PROTEIN",
        _SourceSpan("which", 1282, 1287),
        referents=(referent,),
    )
    if shape is _CauseShape.WHOLE_PROTEIN_CAUSE:
        return (anaphoric_cause,)
    return (
        _argument(
            "CONTEXT",
            "INTERVENTION",
            _SourceSpan("Exogenous IL-2", 1266, 1280),
        ),
        anaphoric_cause,
    )


def _main_clause_cause(shape: _CauseShape) -> tuple[SealedArgument, ...]:
    if shape is _CauseShape.WHOLE_PROTEIN_CAUSE:
        return (
            _argument(
                "CAUSE",
                "GENE_OR_PROTEIN",
                _SourceSpan("Exogenous IL-2", 1266, 1280),
            ),
        )
    return (
        _argument(
            "CONTEXT",
            "INTERVENTION",
            _SourceSpan("Exogenous IL-2", 1266, 1280),
        ),
        _argument("CAUSE", "GENE_OR_PROTEIN", _SourceSpan("IL-2", 1276, 1280)),
    )


def _shared_context(shape: _TreatmentShape) -> tuple[SealedArgument, ...]:
    return (
        *_treatment_arguments(shape),
        _argument("CONTEXT", "VARIANT", _SourceSpan("Rel-/-", 1365, 1371)),
        _argument(
            "CONTEXT",
            "POPULATION",
            _SourceSpan("Rel-/- T cells", 1365, 1379),
        ),
    )


def _treatment_arguments(shape: _TreatmentShape) -> tuple[SealedArgument, ...]:
    if shape is _TreatmentShape.COMPOUND:
        return (
            _argument(
                "CONTEXT",
                "INTERVENTION",
                _SourceSpan("anti-CD3- and anti-CD28-treated", 1333, 1364),
            ),
        )
    return (
        _argument(
            "CONTEXT",
            "INTERVENTION",
            _SourceSpan("anti-CD3", 1333, 1341),
        ),
        _argument(
            "CONTEXT",
            "INTERVENTION",
            _SourceSpan("anti-CD28", 1347, 1356),
        ),
        _argument(
            "CONTEXT",
            "TREATMENT_SETTING",
            _SourceSpan("anti-CD3- and anti-CD28-treated", 1333, 1364),
        ),
    )


def _proliferation_trigger(shape: _ProliferationCue) -> SealedTrigger:
    if shape is _ProliferationCue.HEAD:
        return SealedTrigger("proliferative", 1303, 1316)
    return SealedTrigger("proliferative response", 1303, 1325)


def _link(
    controller_event_id: str,
    controlled_event_id: str,
    span: str,
    start: int,
    end: int,
) -> SealedEventLink:
    return SealedEventLink(
        controller_event_id=controller_event_id,
        event_role="THEME",
        controlled_event_id=controlled_event_id,
        controller_argument=SealedReferenceArgument(
            participant_type="BIOLOGICAL_PROCESS",
            exact_span=span,
            source_start=start,
            source_end=end,
        ),
    )


def _argument(
    event_role: str,
    participant_type: str,
    source: _SourceSpan,
    *,
    referents: tuple[SealedReferenceArgument, ...] = (),
) -> SealedArgument:
    return SealedArgument(
        event_role=event_role,
        reference_id=f"SOURCE-{source.start}-{source.end}-{participant_type}",
        participant_type=participant_type,
        exact_span=source.exact,
        source_start=source.start,
        source_end=source.end,
        referents=referents,
    )


def _semantics(event_id: str) -> SealedEventSemantics:
    controlled_target = event_id in {
        "V9-PROLIFERATIVE-RESPONSE",
        "V9-IL5-EXPRESSION",
        "V9-TNF-EXPRESSION",
        "V9-IFNG-EXPRESSION",
        "V9-IL3-EXPRESSION",
        "V9-GMCSF-EXPRESSION",
        "V9-SUPPORTED-CYTOKINES-EXPRESSION",
        "V9-NULL-CYTOKINES-EXPRESSION",
        "V9-BIONLP-E21",
        "V9-BIONLP-E22",
        "V9-BIONLP-E23",
        "V9-BIONLP-E24",
        "V9-BIONLP-E25",
    }
    return SealedEventSemantics(
        event_id=event_id,
        claim_kind=ClaimKind.SCIENTIFIC_FINDING,
        polarity=(
            InventoryPolarity.UNSCOPED
            if controlled_target
            else (
                InventoryPolarity.NULL_RESULT
                if event_id == "V9-CYTOKINE-RESTORATION-NULL"
                or event_id.startswith("V9-DIRECT-NULL-")
                or event_id in {"V9-BIONLP-E18", "V9-BIONLP-E20"}
                else InventoryPolarity.SUPPORT
            )
        ),
        epistemic_status=(
            InventoryEpistemicStatus.UNASSERTED
            if controlled_target
            else InventoryEpistemicStatus.ASSERTED
        ),
        assertion_scope=(
            InventoryAssertionScope.CONTROLLED_TARGET
            if controlled_target
            else InventoryAssertionScope.SOURCE_ASSERTED
        ),
    )


__all__ = ["ninth_projection_set"]
