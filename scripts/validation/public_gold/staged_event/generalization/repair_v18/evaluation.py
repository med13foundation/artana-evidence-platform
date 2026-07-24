"""V18-local reuse of the frozen V17 evaluator.

V18 changes only the provider-facing prompt.  It does not add a schema, a new
scope-assessment rule, or any new acceptance criterion: the cohort-to-locus
scope link and majority partitive were already mandatory under the V16/V17
evaluator, and the V17 inline-versus-anaphoric boundary is unchanged.  This
module only relabels the V17 evaluation under the V18 experiment lane so
reporting and preflight stay symmetric with every prior version.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.generalization.repair_v14.config import (
    DEFAULT_PATHS as V14_DEFAULT_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.evaluation import (
    V17CaseEvaluation,
    evaluate_v17_case,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.evaluation import (
    failure_classification as v17_failure_classification,
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
        V16StagedGeneralizationOutput,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v17.evaluation import (
        V17ScopeAssessment,
    )


@dataclass(frozen=True, slots=True)
class V18CaseEvaluation:
    """The byte-identical V17 evaluation, relabeled under the V18 lane."""

    v17_evaluation: V17CaseEvaluation

    @property
    def metrics(self) -> V13CaseMetrics:
        return self.v17_evaluation.metrics

    @property
    def raw_v16_metrics(self) -> V13CaseMetrics:
        return self.v17_evaluation.raw_v16_metrics

    @property
    def raw_v14_metrics(self) -> V13CaseMetrics:
        return self.v17_evaluation.raw_v14_metrics

    @property
    def scope_assessment(self) -> V17ScopeAssessment:
        return self.v17_evaluation.scope_assessment

    def as_json(self) -> dict[str, object]:
        return {
            "v17_evaluator_reused_byte_identical": True,
            **self.v17_evaluation.as_json(),
        }


def evaluate_v18_case(
    case: GeneralizationCase,
    output: V16StagedGeneralizationOutput,
    policy: FrozenCasePolicy,
    contract: V13NestedTwoLaneContract,
    *,
    v14_consensus_path: Path = V14_DEFAULT_PATHS.consensus,
) -> V18CaseEvaluation:
    """V18 changes only the prompt; scoring is the unmodified V17 evaluator."""

    return V18CaseEvaluation(
        v17_evaluation=evaluate_v17_case(
            case,
            output,
            policy,
            contract,
            v14_consensus_path=v14_consensus_path,
        )
    )


def failure_classification(
    evaluation: V18CaseEvaluation,
) -> ScientificFailure | None:
    """Delegate classification to the unmodified V17 taxonomy."""

    return v17_failure_classification(evaluation.v17_evaluation)


__all__ = [
    "V18CaseEvaluation",
    "evaluate_v18_case",
    "failure_classification",
]
