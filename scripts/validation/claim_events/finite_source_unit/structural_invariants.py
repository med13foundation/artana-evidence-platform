"""Lossless structural gates applied after categorical agent verification."""

from __future__ import annotations

import re

from artana_evidence_api.document_extraction_support.claim_frames import (
    BoundClaimInventoryItem,
    ClaimArgumentRole,
    ClaimEventRole,
    InventoryPolarity,
)

_TEMPORAL_MARKER = re.compile(
    r"\b(?:after|before|during|following|upon|prior\s+to|subsequent\s+to)\b",
    re.IGNORECASE,
)
_PROCESS_ROLES = frozenset(
    {
        ClaimArgumentRole.BIOLOGICAL_PROCESS,
        ClaimArgumentRole.MEASUREMENT,
        ClaimArgumentRole.OUTCOME,
    },
)
_PROCESS_EVENT_ROLES = frozenset(
    {ClaimEventRole.EFFECT, ClaimEventRole.MEASURE, ClaimEventRole.THEME},
)


def trusted_structure_violation(
    candidate: BoundClaimInventoryItem,
) -> str | None:
    """Return why an otherwise eligible candidate is structurally lossy."""

    item = candidate.item
    contextual_intervention_spans = tuple(
        argument.exact_span
        for argument in item.arguments
        if argument.role in {ClaimArgumentRole.EXPOSURE, ClaimArgumentRole.INTERVENTION}
        and argument.event_role is ClaimEventRole.CONTEXT
    )
    contextual_intervention_present = bool(contextual_intervention_spans)
    if contextual_intervention_present and _TEMPORAL_MARKER.search(item.exact_span):
        timeframe_preserved = any(
            argument.role is ClaimArgumentRole.TIMEFRAME
            and argument.event_role is ClaimEventRole.CONTEXT
            and _TEMPORAL_MARKER.search(argument.exact_span)
            and any(
                contextual_span in argument.exact_span
                for contextual_span in contextual_intervention_spans
            )
            for argument in item.arguments
        )
        if not timeframe_preserved:
            return (
                "trusted contextual event must preserve the complete temporal "
                "phrase and its intervention/exposure as a source-bound "
                "TIMEFRAME/CONTEXT argument"
            )
    if (
        item.polarity is InventoryPolarity.NULL_RESULT
        and item.relation_cue_span.casefold().strip() in {"no", "not"}
    ):
        theme_spans = tuple(
            argument.exact_span
            for argument in item.arguments
            if argument.event_role is ClaimEventRole.THEME
            and argument.role
            not in {
                ClaimArgumentRole.BIOLOGICAL_PROCESS,
                ClaimArgumentRole.MEASUREMENT,
                ClaimArgumentRole.OUTCOME,
            }
        )
        process_preserved = any(
            bound.argument.role in _PROCESS_ROLES
            and bound.argument.event_role in _PROCESS_EVENT_ROLES
            and bound.primary_mention.source_end
            <= candidate.trigger_mention.source_start
            and (
                bound.argument.role
                in {ClaimArgumentRole.MEASUREMENT, ClaimArgumentRole.OUTCOME}
                or any(theme in bound.argument.exact_span for theme in theme_spans)
            )
            for bound in candidate.bound_arguments
        )
        if not process_preserved:
            return (
                "trusted elliptical null event must preserve its inherited tested "
                "process as BIOLOGICAL_PROCESS, OUTCOME, or MEASUREMENT"
            )
    return None


__all__ = ["trusted_structure_violation"]
