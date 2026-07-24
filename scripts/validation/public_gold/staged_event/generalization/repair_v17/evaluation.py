"""V17-local evaluation of inline participant spans versus anaphoric scope.

V17 deliberately retains the V16 output contract and uncertainty reference.  It
does not make a general participant-scope schema available: outside the frozen
anaphoric aggregate, a scope extension is examined only to fail closed with a
specific source-semantic reason.  An output with no extension is delegated to
the V14 evaluator byte-for-byte.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.generalization.repair_v13.acceptance import (
    failure_classification as classify_v13_failure,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.config import (
    DEFAULT_PATHS as V14_DEFAULT_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.evaluation import (
    evaluate_v14_case,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.evaluation import (
    V16ScopeAssessment,
    evaluate_v16_case,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.reference_policy import (
    UNCERTAINTY_CASE_ID,
)
from scripts.validation.public_gold.staged_event.generalization.span_identity import (
    token_bounded_spans,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.grading.contracts import (
        FrozenCasePolicy,
    )
    from scripts.validation.public_gold.staged_event.generalization.panel import (
        GeneralizationCase,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v13.acceptance import (
        ScientificFailure,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v13.contracts import (
        V13NestedTwoLaneContract,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v13.evaluation import (
        V13CaseMetrics,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v16.contracts import (
        ParticipantScopeLink,
        V16StagedGeneralizationOutput,
    )


SCOPE_POLICY = "INLINE_VERSUS_ANAPHORIC_SCOPE_BOUNDARY_V1"
_INLINE_REDUNDANCY = (
    "V17 scope link redundantly decomposes a restrictive modifier retained "
    "in a complete role-bearing participant span"
)
_UNTYPEABLE_SCOPE = (
    "V17 standalone scope restrictor has no approved frozen entity type "
    "for this scope relation"
)
_UNREVIEWED_SCOPE = (
    "V17 participant scope has no independently reviewed anaphoric "
    "reference for this case"
)
_UNREVIEWED_PARTITIVE = (
    "V17 partitive scope is unreviewed outside the frozen anaphoric aggregate"
)
_SCOPE_EVIDENCE_MISMATCH = (
    "V17 scope link evidence does not match both linked participant occurrences"
)


class V17EvaluationError(ValueError):
    """The V17-local boundary cannot be evaluated without changing history."""


@dataclass(frozen=True, slots=True)
class V17ScopeAssessment:
    """V17-local assessment kept separate from all frozen evaluator metrics."""

    policy: str
    passed: bool
    grounding_passed: bool
    scope_link_observed_count: int
    scope_link_accepted_count: int
    partitive_observed_count: int
    partitive_accepted_count: int
    optional_direct_context_observed_count: int
    optional_direct_context_accepted_count: int
    inline_redundant_scope_count: int
    unreviewed_scope_count: int
    untypeable_scope_count: int
    failure_reasons: tuple[str, ...]

    def as_json(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class V17CaseEvaluation:
    """Effective V17 metrics plus preserved V16 and V14 diagnostic lanes."""

    metrics: V13CaseMetrics
    raw_v16_metrics: V13CaseMetrics
    raw_v14_metrics: V13CaseMetrics
    scope_assessment: V17ScopeAssessment

    @property
    def raw_v13_metrics(self) -> V13CaseMetrics:
        """Preserve the historical raw-metrics accessor used by reports."""

        return self.raw_v14_metrics

    def as_json(self) -> dict[str, object]:
        return {
            "effective_metrics": self.metrics.as_json(),
            "raw_v16_metrics": self.raw_v16_metrics.as_json(),
            "raw_v14_metrics": self.raw_v14_metrics.as_json(),
            "participant_scope_assessment": self.scope_assessment.as_json(),
            "raw_bionlp_cg_projection_preserved": (
                self.metrics.benchmark_projection_status
                == self.raw_v16_metrics.benchmark_projection_status
                == self.raw_v14_metrics.benchmark_projection_status
                and self.metrics.benchmark_projection
                == self.raw_v16_metrics.benchmark_projection
                == self.raw_v14_metrics.benchmark_projection
            ),
        }


def evaluate_v17_case(
    case: GeneralizationCase,
    output: V16StagedGeneralizationOutput,
    policy: FrozenCasePolicy,
    contract: V13NestedTwoLaneContract,
    *,
    v14_consensus_path: Path = V14_DEFAULT_PATHS.consensus,
) -> V17CaseEvaluation:
    """Apply V17 without changing V14/V16 contracts or their diagnostics."""

    v16 = evaluate_v16_case(
        case,
        output,
        policy,
        contract,
        v14_consensus_path=v14_consensus_path,
    )
    if case.case_id == UNCERTAINTY_CASE_ID:
        return V17CaseEvaluation(
            metrics=v16.metrics,
            raw_v16_metrics=v16.metrics,
            raw_v14_metrics=v16.raw_v14_metrics,
            scope_assessment=_from_v16_assessment(v16.scope_assessment),
        )

    assessment = _assess_non_uncertainty_extension(output)
    effective = v16.raw_v14_metrics
    if not assessment.passed:
        legacy = _legacy_projection_without_scope_only_participants(output)
        baseline = evaluate_v14_case(
            case,
            legacy,
            policy,
            contract,
            consensus_path=v14_consensus_path,
        )
        effective = _apply_scope_assessment(baseline.metrics, assessment)
    return V17CaseEvaluation(
        metrics=effective,
        raw_v16_metrics=v16.metrics,
        raw_v14_metrics=v16.raw_v14_metrics,
        scope_assessment=assessment,
    )


def failure_classification(
    evaluation: V17CaseEvaluation,
) -> ScientificFailure | None:
    """Classify the V17-local scope boundary without altering V13 taxonomy."""

    if evaluation.metrics.passed:
        return None
    if not evaluation.scope_assessment.passed:
        return "SOURCE_SEMANTICS"
    return classify_v13_failure(evaluation.metrics)


def _from_v16_assessment(assessment: V16ScopeAssessment) -> V17ScopeAssessment:
    """Carry the independently reviewed anaphoric path forward unchanged."""

    return V17ScopeAssessment(
        policy=SCOPE_POLICY,
        passed=assessment.passed,
        grounding_passed=assessment.grounding_passed,
        scope_link_observed_count=assessment.scope_link_observed_count,
        scope_link_accepted_count=assessment.scope_link_accepted_count,
        partitive_observed_count=assessment.partitive_observed_count,
        partitive_accepted_count=assessment.partitive_accepted_count,
        optional_direct_context_observed_count=(
            assessment.optional_direct_context_observed_count
        ),
        optional_direct_context_accepted_count=(
            assessment.optional_direct_context_accepted_count
        ),
        inline_redundant_scope_count=0,
        unreviewed_scope_count=0,
        untypeable_scope_count=0,
        failure_reasons=assessment.failure_reasons,
    )


def _assess_non_uncertainty_extension(
    output: V16StagedGeneralizationOutput,
) -> V17ScopeAssessment:
    """Reject non-anaphoric extensions by their actual policy failure axis."""

    scope_links = output.participant_scope_links
    partitive_count = sum(
        argument.partitive_scope is not None
        for links in output.links
        for argument in links.arguments
    )
    if not scope_links and partitive_count == 0:
        return _not_applicable_assessment()

    participants = {item.participant_id: item for item in output.participants}
    grounding_passed = True
    inline_redundant = 0
    unreviewed = 0
    untypeable = 0
    reasons: list[str] = []
    for link in scope_links:
        restricted = participants.get(link.restricted_participant_id)
        restrictor = participants.get(link.restrictor_participant_id)
        if restricted is None or restrictor is None:
            raise V17EvaluationError("validated V16 scope link lost a participant")
        if not _link_evidence_matches_participants(link, restricted, restrictor):
            grounding_passed = False
            reasons.append(_SCOPE_EVIDENCE_MISMATCH)
        if _is_inline_redundancy(restricted.exact_text, restrictor.exact_text):
            inline_redundant += 1
            reasons.append(_INLINE_REDUNDANCY)
        else:
            unreviewed += 1
            reasons.append(_UNREVIEWED_SCOPE)
        if restrictor.entity_type == "OUTCOME":
            untypeable += 1
            reasons.append(_UNTYPEABLE_SCOPE)
    if partitive_count:
        reasons.append(_UNREVIEWED_PARTITIVE)
    return V17ScopeAssessment(
        policy=SCOPE_POLICY,
        passed=False,
        grounding_passed=grounding_passed,
        scope_link_observed_count=len(scope_links),
        scope_link_accepted_count=0,
        partitive_observed_count=partitive_count,
        partitive_accepted_count=0,
        optional_direct_context_observed_count=0,
        optional_direct_context_accepted_count=0,
        inline_redundant_scope_count=inline_redundant,
        unreviewed_scope_count=unreviewed,
        untypeable_scope_count=untypeable,
        failure_reasons=tuple(dict.fromkeys(reasons)),
    )


def _not_applicable_assessment() -> V17ScopeAssessment:
    return V17ScopeAssessment(
        policy=SCOPE_POLICY,
        passed=True,
        grounding_passed=True,
        scope_link_observed_count=0,
        scope_link_accepted_count=0,
        partitive_observed_count=0,
        partitive_accepted_count=0,
        optional_direct_context_observed_count=0,
        optional_direct_context_accepted_count=0,
        inline_redundant_scope_count=0,
        unreviewed_scope_count=0,
        untypeable_scope_count=0,
        failure_reasons=(),
    )


def _legacy_projection_without_scope_only_participants(
    output: V16StagedGeneralizationOutput,
) -> V16StagedGeneralizationOutput:
    """Isolate a V17 scope defect from V14's unknown-extra-node diagnostic.

    This is a measurement-only projection.  It never accepts the original
    extension: the caller always applies the failed V17 assessment afterward.
    A participant is removed only if it is a scope restrictor and has no event
    argument, so a scope link cannot erase or replace a mandatory participant.
    """

    event_argument_ids = {
        argument.target_id
        for links in output.links
        for argument in links.arguments
        if argument.target_kind == "PARTICIPANT"
    }
    scope_only_restrictor_ids = {
        link.restrictor_participant_id
        for link in output.participant_scope_links
        if link.restrictor_participant_id not in event_argument_ids
    }
    if not scope_only_restrictor_ids:
        return output
    participants = tuple(
        item
        for item in output.participants
        if item.participant_id not in scope_only_restrictor_ids
    )
    return output.model_copy(update={"participants": participants})


def _link_evidence_matches_participants(
    link: ParticipantScopeLink,
    restricted: object,
    restrictor: object,
) -> bool:
    """Require the relation and both participant claims to share one sentence."""

    restricted_evidence = getattr(restricted, "exact_evidence", None)
    restrictor_evidence = getattr(restrictor, "exact_evidence", None)
    return (
        isinstance(restricted_evidence, str)
        and isinstance(restrictor_evidence, str)
        and link.exact_evidence == restricted_evidence == restrictor_evidence
    )


def _is_inline_redundancy(
    restricted_text: str,
    restrictor_text: str,
) -> bool:
    """Identify a strict, token-bounded modifier already retained in its parent."""

    if restricted_text == restrictor_text:
        return False
    matches = token_bounded_spans(
        source=restricted_text,
        scope_start=0,
        scope_end=len(restricted_text),
        exact_text=restrictor_text,
    )
    return len(matches) == 1


def _apply_scope_assessment(
    metrics: V13CaseMetrics,
    assessment: V17ScopeAssessment,
) -> V13CaseMetrics:
    """Record a V17 failure without rewriting independent V14 dimensions."""

    reasons = tuple(
        dict.fromkeys((*metrics.failure_reasons, *assessment.failure_reasons))
    )
    return replace(
        metrics,
        passed=False,
        source_semantic_status="FAIL",
        exact_evidence_grounding=(
            metrics.exact_evidence_grounding and assessment.grounding_passed
        ),
        unsupported_extraction_count=metrics.unsupported_extraction_count + 1,
        failure_reasons=reasons,
        source_dimensions_except_root_passed=False,
        root_only_failure=False,
    )


__all__ = [
    "SCOPE_POLICY",
    "V17CaseEvaluation",
    "V17EvaluationError",
    "V17ScopeAssessment",
    "evaluate_v17_case",
    "failure_classification",
]
