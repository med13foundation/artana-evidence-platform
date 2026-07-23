"""Validate complete occurrence coverage for one scientific output."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.resolver import (
    OccurrenceResolutionError,
    SourceScope,
    resolve_declared_span,
    resolve_mention_identity,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.contracts import (
        SemanticAxes,
        StagedGeneralizationOutput,
    )
    from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.contracts import (
        OccurrenceAwareBindings,
        SemanticEvidenceBinding,
    )
    from scripts.validation.public_gold.staged_event.generalization.panel import (
        GeneralizationCase,
    )
    from scripts.validation.public_gold.staged_event.generalization.span_identity import (
        ExactSpan,
    )


class OccurrenceBindingError(ValueError):
    """The occurrence sidecar is incomplete or identity-mismatched."""


@dataclass(frozen=True, slots=True)
class ValidatedMention:
    evidence: ExactSpan
    mention: ExactSpan


@dataclass(frozen=True, slots=True)
class ValidatedSemanticEvidence:
    evidence_items: tuple[ExactSpan, ...]
    statistical_observations: tuple[ExactSpan | None, ...]


@dataclass(frozen=True, slots=True)
class ValidatedBindings:
    events: dict[str, ValidatedMention]
    participants: dict[str, ValidatedMention]
    semantic: dict[str, ValidatedSemanticEvidence]


def validate_bindings(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    bindings: OccurrenceAwareBindings,
) -> ValidatedBindings:
    """Prove exact source identity for every textual output field."""

    if bindings.case_id != case.case_id or output.case_id != case.case_id:
        raise OccurrenceBindingError("case identity changed")
    event_nodes = {item.event_id: item for item in output.inventory}
    participant_nodes = {item.participant_id: item for item in output.participants}
    axes_nodes = {item.event_id: item for item in output.semantic_axes}
    event_sidecar = {item.node_id: item.identity for item in bindings.event_mentions}
    participant_sidecar = {
        item.node_id: item.identity for item in bindings.participant_mentions
    }
    semantic_sidecar = {
        item.event_id: item for item in bindings.semantic_evidence
    }
    _require_exact_coverage(event_nodes, event_sidecar, "event mention")
    _require_exact_coverage(participant_nodes, participant_sidecar, "participant mention")
    _require_exact_coverage(axes_nodes, semantic_sidecar, "semantic evidence")
    scope = SourceScope(case.source, case.context_start, case.context_end)
    try:
        events = {
            node_id: ValidatedMention(
                *resolve_mention_identity(
                    scope=scope,
                    declared_evidence=node.exact_evidence,
                    declared_mention=node.trigger_text,
                    identity=event_sidecar[node_id],
                )
            )
            for node_id, node in event_nodes.items()
        }
        participants = {
            node_id: ValidatedMention(
                *resolve_mention_identity(
                    scope=scope,
                    declared_evidence=node.exact_evidence,
                    declared_mention=node.exact_text,
                    identity=participant_sidecar[node_id],
                )
            )
            for node_id, node in participant_nodes.items()
        }
        semantic = {
            event_id: _validate_semantic_evidence(
                axes,
                semantic_sidecar[event_id],
                scope,
            )
            for event_id, axes in axes_nodes.items()
        }
    except OccurrenceResolutionError as exc:
        raise OccurrenceBindingError(str(exc)) from exc
    return ValidatedBindings(events, participants, semantic)


def _validate_semantic_evidence(
    axes: SemanticAxes,
    sidecar: SemanticEvidenceBinding,
    scope: SourceScope,
) -> ValidatedSemanticEvidence:
    evidence_items = axes.evidence_items
    observations = axes.statistical_observations
    evidence_spans = sidecar.evidence_item_spans
    observation_spans = sidecar.statistical_observation_spans
    if len(evidence_items) != len(evidence_spans):
        raise OccurrenceBindingError("semantic evidence span count changed")
    if len(observations) != len(observation_spans):
        raise OccurrenceBindingError("statistical observation span count changed")
    resolved_evidence = tuple(
        resolve_declared_span(
            scope=scope,
            declared_text=text,
            offsets=span,
            label="semantic evidence",
            require_token_boundaries=False,
        )
        for text, span in zip(evidence_items, evidence_spans, strict=True)
    )
    resolved_statistics: list[ExactSpan | None] = []
    for observation, span in zip(observations, observation_spans, strict=True):
        exact_text = observation.exact_text
        if exact_text is None:
            if span is not None:
                raise OccurrenceBindingError(
                    "NONE statistical observation cannot have source offsets"
                )
            resolved_statistics.append(None)
            continue
        if span is None:
            raise OccurrenceBindingError(
                "statistical observation source offsets are missing"
            )
        resolved_statistics.append(
            resolve_declared_span(
                scope=scope,
                declared_text=exact_text,
                offsets=span,
                label="statistical observation",
                require_token_boundaries=True,
            )
        )
    return ValidatedSemanticEvidence(
        resolved_evidence,
        tuple(resolved_statistics),
    )


def _require_exact_coverage(
    expected: Mapping[str, object],
    actual: Mapping[str, object],
    label: str,
) -> None:
    missing = set(expected) - set(actual)
    unknown = set(actual) - set(expected)
    if missing or unknown:
        raise OccurrenceBindingError(
            f"{label} binding coverage changed: "
            f"missing={sorted(missing)}, unknown={sorted(unknown)}"
        )


__all__ = [
    "OccurrenceBindingError",
    "ValidatedBindings",
    "ValidatedMention",
    "ValidatedSemanticEvidence",
    "validate_bindings",
]
