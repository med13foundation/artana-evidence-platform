"""Frozen semantic-axis rules with occurrence-aware statistical spans."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.matching import (
    source_span_matches_any,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.contracts import (
        StagedGeneralizationOutput,
    )
    from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.bindings import (
        ValidatedBindings,
    )
    from scripts.validation.public_gold.staged_event.generalization.panel import (
        GeneralizationCase,
    )


def evaluate_axes(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    *,
    event_map: dict[str, str],
    validated: ValidatedBindings,
    reasons: list[str],
) -> dict[str, bool]:
    actual = {
        event_map.get(item.event_id): (item, validated.semantic[item.event_id])
        for item in output.semantic_axes
    }
    fidelity = {
        "direction": True,
        "comparison": True,
        "polarity": True,
        "uncertainty": True,
        "statistics": True,
    }
    for expected in case.reference.axes:
        pair = actual.get(expected.event_key)
        if pair is None:
            for key in fidelity:
                fidelity[key] = False
            reasons.append(f"semantic axes absent for {expected.event_key}")
            continue
        item, identity = pair
        fidelity["direction"] &= item.direction == expected.direction
        fidelity["comparison"] &= item.comparison == expected.comparison
        fidelity["polarity"] &= item.polarity == expected.polarity
        fidelity["uncertainty"] &= item.uncertainty == expected.uncertainty
        observation_types = tuple(
            observation.observation_type
            for observation in item.statistical_observations
        )
        observation_spans = tuple(
            span
            for span in identity.statistical_observations
            if span is not None
        )
        statistical_spans_match = (
            not observation_spans and not expected.acceptable_statistical_texts
        ) or (
            len(observation_spans) == 1
            and source_span_matches_any(
                source=case.source,
                context_start=case.context_start,
                context_end=case.context_end,
                actual=observation_spans[0],
                acceptable_texts=expected.acceptable_statistical_texts,
            )
        )
        fidelity["statistics"] &= (
            observation_types == (expected.statistical_type,)
            and statistical_spans_match
            and item.author_interpretation == expected.author_interpretation
        )
    for axis, passed in fidelity.items():
        if not passed:
            reasons.append(f"{axis} fidelity failed")
    return fidelity


__all__ = ["evaluate_axes"]
