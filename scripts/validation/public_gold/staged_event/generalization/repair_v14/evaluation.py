"""V14-local normalization of one adjudicated source-entailed role edge."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, cast

from scripts.validation.public_gold.staged_event.generalization.repair_v13.evaluation import (
    V13CaseMetrics,
    evaluate_v13_case,
    resolve_focus_local_occurrence,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.config import (
    DEFAULT_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.span_identity import (
    SpanIdentityError,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.contracts import (
        StagedGeneralizationOutput,
    )
    from scripts.validation.public_gold.staged_event.generalization.grading.contracts import (
        FrozenCasePolicy,
    )
    from scripts.validation.public_gold.staged_event.generalization.panel import (
        GeneralizationCase,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v13.contracts import (
        V13NestedTwoLaneContract,
    )

_NESTED_CASE_ID = "generalization-explicit-nested-cause"
_OPTIONAL_EVENT_KEY = "elevating"
_OPTIONAL_PARTICIPANT_KEY = "proteins"
_OPTIONAL_ROLE = "CAUSAL_AGENT"
_OPTIONAL_TARGET_KIND = "PARTICIPANT"
_ROLE_FAILURE = "source-semantic event links or roles differ"


class V14EvaluationError(ValueError):
    """The local evaluator overlay differs from independent adjudication."""


@dataclass(frozen=True, slots=True)
class V14CaseEvaluation:
    """Effective source metrics plus immutable raw V13 measurement."""

    metrics: V13CaseMetrics
    raw_v13_metrics: V13CaseMetrics
    optional_edge_observed_count: int
    optional_edge_accepted_count: int
    normalization_status: str

    def as_json(self) -> dict[str, object]:
        return {
            "effective_metrics": self.metrics.as_json(),
            "raw_v13_metrics": self.raw_v13_metrics.as_json(),
            "optional_source_entailed_edge": {
                "event_key": _OPTIONAL_EVENT_KEY,
                "role": _OPTIONAL_ROLE,
                "target_kind": _OPTIONAL_TARGET_KIND,
                "target_key": _OPTIONAL_PARTICIPANT_KEY,
                "observed_count": self.optional_edge_observed_count,
                "accepted_count": self.optional_edge_accepted_count,
                "normalization_status": self.normalization_status,
            },
            "raw_bionlp_cg_projection_preserved": (
                self.metrics.benchmark_projection_status
                == self.raw_v13_metrics.benchmark_projection_status
                and self.metrics.benchmark_projection
                == self.raw_v13_metrics.benchmark_projection
            ),
        }


def evaluate_v14_case(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    policy: FrozenCasePolicy,
    contract: V13NestedTwoLaneContract,
    *,
    consensus_path: Path = DEFAULT_PATHS.consensus,
) -> V14CaseEvaluation:
    """Reuse V13 exactly except for the adjudicated optional nested role."""

    raw = evaluate_v13_case(case, output, policy, contract)
    if case.case_id != _NESTED_CASE_ID:
        return V14CaseEvaluation(
            metrics=raw,
            raw_v13_metrics=raw,
            optional_edge_observed_count=0,
            optional_edge_accepted_count=0,
            normalization_status="NOT_APPLICABLE",
        )
    _verify_consensus(consensus_path)
    candidate = _normalization_candidate(case, output, contract)
    if candidate is None:
        return V14CaseEvaluation(
            metrics=raw,
            raw_v13_metrics=raw,
            optional_edge_observed_count=_raw_optional_count(output, contract),
            optional_edge_accepted_count=0,
            normalization_status="NOT_APPLIED_FAIL_CLOSED",
        )
    normalized_output, observed_count = candidate
    normalized = evaluate_v13_case(case, normalized_output, policy, contract)
    if not normalized.participant_roles_passed:
        return V14CaseEvaluation(
            metrics=raw,
            raw_v13_metrics=raw,
            optional_edge_observed_count=observed_count,
            optional_edge_accepted_count=0,
            normalization_status="REJECTED_OTHER_LINK_DIVERGENCE",
        )
    effective = replace(
        normalized,
        benchmark_projection_status=raw.benchmark_projection_status,
        benchmark_projection_scope=raw.benchmark_projection_scope,
        full_focus_cg_status=raw.full_focus_cg_status,
        benchmark_projection=raw.benchmark_projection,
    )
    if _ROLE_FAILURE in effective.failure_reasons:
        raise V14EvaluationError("normalized role failure was not removed")
    return V14CaseEvaluation(
        metrics=effective,
        raw_v13_metrics=raw,
        optional_edge_observed_count=observed_count,
        optional_edge_accepted_count=1,
        normalization_status="ACCEPTED_SOURCE_ENTAILED_REDUNDANCY",
    )


def _normalization_candidate(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    contract: V13NestedTwoLaneContract,
) -> tuple[StagedGeneralizationOutput, int] | None:
    participant_id = _accepted_participant_id(case, output, contract)
    event_id = _accepted_event_id(output, contract)
    if participant_id is None or event_id is None:
        return None
    matching_count = 0
    normalized_links = []
    for link in output.links:
        kept_arguments = []
        for argument in link.arguments:
            matches = (
                link.event_id == event_id
                and argument.role == _OPTIONAL_ROLE
                and argument.target_kind == _OPTIONAL_TARGET_KIND
                and argument.target_id == participant_id
            )
            if matches:
                matching_count += 1
            else:
                kept_arguments.append(argument)
        normalized_links.append(
            link.model_copy(update={"arguments": tuple(kept_arguments)})
        )
    if matching_count != 1:
        return None
    normalized = output.model_copy(update={"links": tuple(normalized_links)})
    return normalized, matching_count


def _accepted_participant_id(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    contract: V13NestedTwoLaneContract,
) -> str | None:
    rule = next(
        (
            item
            for item in contract.source_lane.participants
            if item.participant_key == _OPTIONAL_PARTICIPANT_KEY
        ),
        None,
    )
    if rule is None:
        raise V14EvaluationError("frozen proteins participant rule is absent")
    matches: list[str] = []
    for participant in output.participants:
        if (
            participant.entity_type != rule.entity_type
            or participant.exact_text != rule.exact_text
        ):
            continue
        try:
            span = resolve_focus_local_occurrence(
                case,
                exact_evidence=participant.exact_evidence,
                exact_text=participant.exact_text,
            )
        except SpanIdentityError:
            continue
        if span.start == rule.start and span.end == rule.end:
            matches.append(participant.participant_id)
    return matches[0] if len(matches) == 1 else None


def _accepted_event_id(
    output: StagedGeneralizationOutput,
    contract: V13NestedTwoLaneContract,
) -> str | None:
    rule = next(
        (
            item
            for item in contract.source_lane.events
            if item.event_key == _OPTIONAL_EVENT_KEY
        ),
        None,
    )
    if rule is None:
        raise V14EvaluationError("frozen inner event rule is absent")
    matches = [
        event.event_id
        for event in output.inventory
        if event.event_type in rule.acceptable_event_types
        and event.trigger_text in rule.acceptable_triggers
    ]
    return matches[0] if len(matches) == 1 else None


def _raw_optional_count(
    output: StagedGeneralizationOutput,
    contract: V13NestedTwoLaneContract,
) -> int:
    event_id = _accepted_event_id(output, contract)
    if event_id is None:
        return 0
    participant_rule = next(
        item
        for item in contract.source_lane.participants
        if item.participant_key == _OPTIONAL_PARTICIPANT_KEY
    )
    participant_ids = {
        item.participant_id
        for item in output.participants
        if item.entity_type == participant_rule.entity_type
        and item.exact_text == participant_rule.exact_text
    }
    return sum(
        1
        for link in output.links
        if link.event_id == event_id
        for argument in link.arguments
        if argument.role == _OPTIONAL_ROLE
        and argument.target_kind == _OPTIONAL_TARGET_KIND
        and argument.target_id in participant_ids
    )


def _verify_consensus(path: Path) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise V14EvaluationError("V14 consensus is not an object")
    consensus = value.get("consensus")
    role = value.get("source_semantic_role_consensus")
    if not isinstance(consensus, dict) or not isinstance(role, dict):
        raise V14EvaluationError("V14 consensus sections are absent")
    if (
        consensus.get("overall_verdict") != "PASS"
        or role.get("all_other_links") != "REJECT"
        or role.get("duplicate_links") != "REJECT"
        or role.get("general_role_propagation_allowed") is not False
    ):
        raise V14EvaluationError("V14 consensus no longer authorizes local policy")
    optional = role.get("optional_links")
    if not isinstance(optional, list) or len(optional) != 1:
        raise V14EvaluationError("V14 optional-link policy changed")
    item = cast("dict[str, object]", optional[0])
    expected = {
        "event_key": _OPTIONAL_EVENT_KEY,
        "role": _OPTIONAL_ROLE,
        "target_key": _OPTIONAL_PARTICIPANT_KEY,
        "target_kind": _OPTIONAL_TARGET_KIND,
        "minimum_occurrences": 0,
        "maximum_occurrences": 1,
        "classification": "SOURCE_ENTAILED_REDUNDANT_BUT_TRUE",
        "binding_condition": (
            "The target must resolve to the accepted complete proteins "
            "participant occurrence."
        ),
    }
    if item != expected:
        raise V14EvaluationError("V14 optional-link tuple changed")


__all__ = [
    "V14CaseEvaluation",
    "V14EvaluationError",
    "evaluate_v14_case",
]
