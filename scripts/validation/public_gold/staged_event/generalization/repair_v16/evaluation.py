"""V16-local evaluation of source-semantic scope without changing V14.

The historical V14 result is retained as a diagnostic lane.  Only the
uncertainty case receives a prospective V16 overlay, and that overlay requires
both a participant scope link and a partitive qualifier before it can pass.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.acceptance import (
    failure_classification as classify_v13_failure,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.config import (
    DEFAULT_PATHS as V14_DEFAULT_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.evaluation import (
    evaluate_v14_case,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.reference_policy import (
    UNCERTAINTY_CASE_ID,
    UNCERTAINTY_SCOPE_REFERENCE,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.grading.contracts import (
        FrozenCasePolicy,
    )
    from scripts.validation.public_gold.staged_event.generalization.panel import (
        GeneralizationCase,
        GeneralizationReference,
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
        V16StagedGeneralizationOutput,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v16.reference_policy import (
        ExpectedOccurrence,
        UncertaintyScopeReference,
    )


class V16EvaluationError(ValueError):
    """The V16 local source-semantic overlay cannot be applied safely."""


@dataclass(frozen=True, slots=True)
class V16ScopeAssessment:
    """The explicit V16-only checks that cannot be delegated to V14."""

    passed: bool
    grounding_passed: bool
    scope_link_observed_count: int
    scope_link_accepted_count: int
    partitive_observed_count: int
    partitive_accepted_count: int
    optional_direct_context_observed_count: int
    optional_direct_context_accepted_count: int
    failure_reasons: tuple[str, ...]

    def as_json(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class V16CaseEvaluation:
    """Effective V16 metrics and a preserved V14 diagnostic measurement."""

    metrics: V13CaseMetrics
    raw_v14_metrics: V13CaseMetrics
    scope_assessment: V16ScopeAssessment

    @property
    def raw_v13_metrics(self) -> V13CaseMetrics:
        """Keep downstream report readers on the existing raw-metrics shape."""

        return self.raw_v14_metrics

    def as_json(self) -> dict[str, object]:
        return {
            "effective_metrics": self.metrics.as_json(),
            "raw_v14_metrics": self.raw_v14_metrics.as_json(),
            "participant_scope_assessment": self.scope_assessment.as_json(),
            "raw_bionlp_cg_projection_preserved": (
                self.metrics.benchmark_projection_status
                == self.raw_v14_metrics.benchmark_projection_status
                and self.metrics.benchmark_projection
                == self.raw_v14_metrics.benchmark_projection
            ),
        }


@dataclass(frozen=True, slots=True)
class _OptionalContextNormalization:
    participant_id: str | None
    observed_count: int
    accepted_count: int
    failure_reasons: tuple[str, ...]


def evaluate_v16_case(
    case: GeneralizationCase,
    output: V16StagedGeneralizationOutput,
    policy: FrozenCasePolicy,
    contract: V13NestedTwoLaneContract,
    *,
    v14_consensus_path: Path = V14_DEFAULT_PATHS.consensus,
) -> V16CaseEvaluation:
    """Evaluate unchanged cases through V14 and scope through a local overlay."""

    raw = evaluate_v14_case(
        case,
        output,
        policy,
        contract,
        consensus_path=v14_consensus_path,
    )
    if case.case_id != UNCERTAINTY_CASE_ID:
        assessment = _non_uncertainty_extension_assessment(output)
        return V16CaseEvaluation(
            metrics=_apply_scope_assessment(raw.metrics, assessment),
            raw_v14_metrics=raw.metrics,
            scope_assessment=assessment,
        )

    reference = UNCERTAINTY_SCOPE_REFERENCE
    try:
        reference.verify(case)
    except ValueError as exc:
        raise V16EvaluationError("frozen V16 scope reference cannot resolve") from exc
    normalization = _normalize_optional_direct_context(case, output, reference)
    assessment = _assess_uncertainty_scope(
        case,
        output,
        reference,
        normalization,
    )
    overlay_case = _overlay_case_without_direct_gene(case)
    overlay_policy = policy.model_copy(
        update={"core_reference_sha256": _reference_sha256(overlay_case.reference)}
    )
    legacy = _legacy_projection(
        output, remove_participant_id=normalization.participant_id
    )
    overlay = evaluate_v14_case(
        overlay_case,
        legacy,
        overlay_policy,
        contract,
        consensus_path=v14_consensus_path,
    )
    return V16CaseEvaluation(
        metrics=_apply_scope_assessment(overlay.metrics, assessment),
        raw_v14_metrics=raw.metrics,
        scope_assessment=assessment,
    )


def failure_classification(
    evaluation: V16CaseEvaluation,
) -> ScientificFailure | None:
    """Classify V16's intended scope failure without changing V13's taxonomy."""

    if evaluation.metrics.passed:
        return None
    if not evaluation.scope_assessment.passed:
        return "SOURCE_SEMANTICS"
    return classify_v13_failure(evaluation.metrics)


def _not_applicable_assessment() -> V16ScopeAssessment:
    return V16ScopeAssessment(
        passed=True,
        grounding_passed=True,
        scope_link_observed_count=0,
        scope_link_accepted_count=0,
        partitive_observed_count=0,
        partitive_accepted_count=0,
        optional_direct_context_observed_count=0,
        optional_direct_context_accepted_count=0,
        failure_reasons=(),
    )


def _non_uncertainty_extension_assessment(
    output: V16StagedGeneralizationOutput,
) -> V16ScopeAssessment:
    """Reject V16-only structure outside its independently reviewed boundary."""

    scope_count = len(output.participant_scope_links)
    partitive_count = sum(
        argument.partitive_scope is not None
        for links in output.links
        for argument in links.arguments
    )
    if scope_count == 0 and partitive_count == 0:
        return _not_applicable_assessment()
    reasons: list[str] = []
    if scope_count:
        reasons.append("V16 participant scope links are unsupported for this case")
    if partitive_count:
        reasons.append("V16 partitive scope is unsupported for this case")
    return V16ScopeAssessment(
        passed=False,
        grounding_passed=True,
        scope_link_observed_count=scope_count,
        scope_link_accepted_count=0,
        partitive_observed_count=partitive_count,
        partitive_accepted_count=0,
        optional_direct_context_observed_count=0,
        optional_direct_context_accepted_count=0,
        failure_reasons=tuple(reasons),
    )


def _assess_uncertainty_scope(
    case: GeneralizationCase,
    output: V16StagedGeneralizationOutput,
    reference: UncertaintyScopeReference,
    normalization: _OptionalContextNormalization,
) -> V16ScopeAssessment:
    reasons = list(normalization.failure_reasons)
    grounding = _legacy_grounding_is_exact(output, reference)
    if not grounding:
        reasons.append("V16 scope evidence is not the complete result sentence")

    cohort_ids = _matching_cohort_ids(case, output, reference)
    if len(cohort_ids) != 1:
        reasons.append("V16 requires one occurrence-bound 947-variant cohort")
    locus_ids = _matching_locus_ids(case, output, reference)
    if len(locus_ids) != 1:
        reasons.append("V16 requires one occurrence-bound locus restrictor")
    classification_ids = _classification_event_ids(output)
    if len(classification_ids) != 1:
        reasons.append("V16 requires one resolvable classification event")

    cohort_id = cohort_ids[0] if len(cohort_ids) == 1 else None
    locus_id = locus_ids[0] if len(locus_ids) == 1 else None
    classification_id = classification_ids[0] if len(classification_ids) == 1 else None
    accepted_scope = _accepted_scope_link_count(
        output,
        reference,
        cohort_id=cohort_id,
        locus_id=locus_id,
    )
    if len(output.participant_scope_links) != 1 or accepted_scope != 1:
        reasons.append("V16 cohort-to-locus scope link is missing or invalid")
    partitive_observed, accepted_partitive = _partitive_counts(
        output,
        reference,
        classification_id=classification_id,
        cohort_id=cohort_id,
    )
    if partitive_observed != 1 or accepted_partitive != 1:
        reasons.append("V16 majority partitive is missing or invalid")
    direct_is_acceptable = normalization.accepted_count in {0, 1}
    passed = all(
        (
            grounding,
            len(cohort_ids) == 1,
            len(locus_ids) == 1,
            len(classification_ids) == 1,
            len(output.participant_scope_links) == 1,
            accepted_scope == 1,
            partitive_observed == 1,
            accepted_partitive == 1,
            direct_is_acceptable,
            not normalization.failure_reasons,
        )
    )
    return V16ScopeAssessment(
        passed=passed,
        grounding_passed=grounding,
        scope_link_observed_count=len(output.participant_scope_links),
        scope_link_accepted_count=accepted_scope,
        partitive_observed_count=partitive_observed,
        partitive_accepted_count=accepted_partitive,
        optional_direct_context_observed_count=normalization.observed_count,
        optional_direct_context_accepted_count=normalization.accepted_count,
        failure_reasons=tuple(dict.fromkeys(reasons)),
    )


def _legacy_grounding_is_exact(
    output: V16StagedGeneralizationOutput,
    reference: UncertaintyScopeReference,
) -> bool:
    return (
        all(
            reference.accepts_evidence(item.exact_evidence) for item in output.inventory
        )
        and all(
            reference.accepts_evidence(item.exact_evidence)
            for item in output.participants
        )
        and all(
            len(item.evidence_items) == 1
            and reference.accepts_evidence(item.evidence_items[0])
            for item in output.semantic_axes
        )
    )


def _matching_cohort_ids(
    case: GeneralizationCase,
    output: V16StagedGeneralizationOutput,
    reference: UncertaintyScopeReference,
) -> tuple[str, ...]:
    return tuple(
        item.participant_id
        for item in output.participants
        if item.entity_type == "VARIANT"
        and _matches_occurrence(
            case, item.exact_text, item.exact_evidence, reference.cohort, reference
        )
    )


def _matching_locus_ids(
    case: GeneralizationCase,
    output: V16StagedGeneralizationOutput,
    reference: UncertaintyScopeReference,
) -> tuple[str, ...]:
    return tuple(
        item.participant_id
        for item in output.participants
        if item.entity_type == "GENE_OR_PROTEIN"
        and item.exact_text in reference.allowed_locus_texts
        and _matches_locus_occurrence(
            case, item.exact_text, item.exact_evidence, reference
        )
    )


def _matches_occurrence(
    case: GeneralizationCase,
    exact_text: str,
    exact_evidence: str,
    occurrence: ExpectedOccurrence,
    reference: UncertaintyScopeReference,
) -> bool:
    return (
        exact_text == occurrence.exact_text
        and reference.accepts_evidence(exact_evidence)
        and case.source[occurrence.start : occurrence.end] == exact_text
    )


def _matches_locus_occurrence(
    case: GeneralizationCase,
    exact_text: str,
    exact_evidence: str,
    reference: UncertaintyScopeReference,
) -> bool:
    occurrence = (
        reference.locus_full
        if exact_text == reference.locus_full.exact_text
        else reference.locus_identifier
    )
    return _matches_occurrence(case, exact_text, exact_evidence, occurrence, reference)


def _classification_event_ids(
    output: V16StagedGeneralizationOutput,
) -> tuple[str, ...]:
    return tuple(
        item.event_id
        for item in output.inventory
        if item.event_type == "CLASSIFICATION"
        and "classified" in item.trigger_text
        and "uncertain significance" in item.trigger_text
    )


def _accepted_scope_link_count(
    output: V16StagedGeneralizationOutput,
    reference: UncertaintyScopeReference,
    *,
    cohort_id: str | None,
    locus_id: str | None,
) -> int:
    return sum(
        1
        for item in output.participant_scope_links
        if cohort_id is not None
        and locus_id is not None
        and item.restricted_participant_id == cohort_id
        and item.restrictor_participant_id == locus_id
        and item.relation_type == reference.relation_type
        and reference.accepts_evidence(item.exact_evidence)
    )


def _partitive_counts(
    output: V16StagedGeneralizationOutput,
    reference: UncertaintyScopeReference,
    *,
    classification_id: str | None,
    cohort_id: str | None,
) -> tuple[int, int]:
    observed = 0
    accepted = 0
    for links in output.links:
        for argument in links.arguments:
            scope = argument.partitive_scope
            if scope is None:
                continue
            observed += 1
            if (
                classification_id is not None
                and cohort_id is not None
                and links.event_id == classification_id
                and argument.role == "AFFECTED_ENTITY"
                and argument.target_kind == "PARTICIPANT"
                and argument.target_id == cohort_id
                and scope.kind == reference.partitive_kind
                and scope.exact_text == reference.partitive.exact_text
                and reference.accepts_evidence(scope.exact_evidence)
                and scope.antecedent_participant_id == cohort_id
            ):
                accepted += 1
    return observed, accepted


def _normalize_optional_direct_context(
    case: GeneralizationCase,
    output: V16StagedGeneralizationOutput,
    reference: UncertaintyScopeReference,
) -> _OptionalContextNormalization:
    locus_ids = _matching_locus_ids(case, output, reference)
    if not locus_ids:
        return _OptionalContextNormalization(None, 0, 0, ())
    if len(locus_ids) != 1:
        return _OptionalContextNormalization(
            None,
            0,
            0,
            ("V16 optional direct locus context is duplicate or ambiguous",),
        )
    locus_id = locus_ids[0]
    classification_ids = _classification_event_ids(output)
    direct = [
        (links.event_id, argument)
        for links in output.links
        for argument in links.arguments
        if argument.target_kind == "PARTICIPANT" and argument.target_id == locus_id
    ]
    if not direct:
        return _OptionalContextNormalization(locus_id, 0, 0, ())
    if len(direct) != 1 or len(classification_ids) != 1:
        return _OptionalContextNormalization(
            None,
            len(direct),
            0,
            ("V16 optional direct locus context is duplicate or unresolved",),
        )
    event_id, argument = direct[0]
    valid = (
        event_id == classification_ids[0]
        and argument.role == "CONTEXTUAL_PARTICIPANT"
        and argument.partitive_scope is None
    )
    if not valid:
        return _OptionalContextNormalization(
            None,
            1,
            0,
            ("V16 optional direct locus context has an unsupported role",),
        )
    return _OptionalContextNormalization(locus_id, 1, 1, ())


def _overlay_case_without_direct_gene(case: GeneralizationCase) -> GeneralizationCase:
    reference = case.reference
    participants = tuple(
        item for item in reference.participants if item.participant_key != "gene"
    )
    arguments = tuple(item for item in reference.arguments if item.target_key != "gene")
    if len(participants) + 1 != len(reference.participants):
        raise V16EvaluationError("frozen uncertainty reference lacks one direct gene")
    if len(arguments) + 1 != len(reference.arguments):
        raise V16EvaluationError(
            "frozen uncertainty reference lacks one direct gene link"
        )
    overlay = replace(
        reference,
        participants=participants,
        arguments=arguments,
        reference_basis=(
            "V16 source-semantic overlay: direct locus argument is optional; "
            "scope link and partitive qualifier are required."
        ),
    )
    return replace(case, reference=overlay)


def _legacy_projection(
    output: V16StagedGeneralizationOutput,
    *,
    remove_participant_id: str | None,
) -> V9StagedGeneralizationOutput:
    participants = [
        item.model_dump(mode="json")
        for item in output.participants
        if item.participant_id != remove_participant_id
    ]
    links = []
    for event_links in output.links:
        arguments = [
            {
                "role": argument.role,
                "target_kind": argument.target_kind,
                "target_id": argument.target_id,
                "explanation": argument.explanation,
            }
            for argument in event_links.arguments
            if argument.target_id != remove_participant_id
        ]
        links.append({"event_id": event_links.event_id, "arguments": arguments})
    return V9StagedGeneralizationOutput.model_validate_json(
        json.dumps(
            {
                "case_id": output.case_id,
                "inventory": [
                    item.model_dump(mode="json") for item in output.inventory
                ],
                "participants": participants,
                "links": links,
                "semantic_axes": [
                    item.model_dump(mode="json") for item in output.semantic_axes
                ],
                "root_event_id": output.root_event_id,
                "completeness": output.completeness,
                "structure_explanation": output.structure_explanation,
            }
        )
    )


def _apply_scope_assessment(
    metrics: V13CaseMetrics,
    assessment: V16ScopeAssessment,
) -> V13CaseMetrics:
    if assessment.passed:
        return metrics
    reasons = tuple(
        dict.fromkeys((*metrics.failure_reasons, *assessment.failure_reasons))
    )
    return replace(
        metrics,
        passed=False,
        source_semantic_status="FAIL",
        mandatory_participants_passed=False,
        participant_roles_passed=False,
        exact_evidence_grounding=(
            metrics.exact_evidence_grounding and assessment.grounding_passed
        ),
        unsupported_extraction_count=metrics.unsupported_extraction_count + 1,
        failure_reasons=reasons,
        source_dimensions_except_root_passed=False,
        root_only_failure=False,
    )


def _reference_sha256(reference: GeneralizationReference) -> str:
    raw = json.dumps(asdict(reference), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "V16CaseEvaluation",
    "V16EvaluationError",
    "V16ScopeAssessment",
    "evaluate_v16_case",
    "failure_classification",
]
