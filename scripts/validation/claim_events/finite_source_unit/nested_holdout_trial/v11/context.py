"""Sealed experimental-factor topology for the V11 source unit."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Final

from scripts.validation.claim_events.finite_source_unit.normalization.context_dimensions import (
    ContextDimensionOperator,
    ContextDimensionType,
)

if TYPE_CHECKING:
    from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
        SourceUnitNormalizationOutput,
    )


@dataclass(frozen=True, slots=True)
class SealedContextDimension:
    """Source-adjudicated factor levels independent of agent-local IDs."""

    dimension_type: ContextDimensionType
    operator: ContextDimensionOperator
    factor_span: str
    level_spans: tuple[str, ...]
    crossed_factor_spans: tuple[str, ...]

    def as_json(self) -> dict[str, object]:
        return asdict(self)


V11_CONTEXT_DIMENSIONS: Final = (
    SealedContextDimension(
        dimension_type=ContextDimensionType.GENOTYPE,
        operator=ContextDimensionOperator.ALTERNATIVE_LEVELS,
        factor_span="CbfbF/F CD4-cre and CbfbF/F control mice",
        level_spans=("CbfbF/F CD4-cre", "CbfbF/F control mice"),
        crossed_factor_spans=("anti-IL-4 and anti-IFN-gamma neutralizing mAbs",),
    ),
    SealedContextDimension(
        dimension_type=ContextDimensionType.TREATMENT,
        operator=ContextDimensionOperator.ALTERNATIVE_LEVELS,
        factor_span="anti-IL-4 and anti-IFN-gamma neutralizing mAbs",
        level_spans=("absence", "presence"),
        crossed_factor_spans=("CbfbF/F CD4-cre and CbfbF/F control mice",),
    ),
)


def v11_context_dimensions_match(output: SourceUnitNormalizationOutput) -> bool:
    """Require both crossed factors to scope every normalized event."""

    dimensions = output.context_dimensions
    if len(dimensions) != len(V11_CONTEXT_DIMENSIONS):
        return False
    expected_by_factor = {
        dimension.factor_span: dimension for dimension in V11_CONTEXT_DIMENSIONS
    }
    actual_by_factor = {dimension.factor_span: dimension for dimension in dimensions}
    if set(actual_by_factor) != set(expected_by_factor):
        return False
    event_ids = {event.local_event_id for event in output.events}
    if None in event_ids:
        return False
    for factor_span, expected in expected_by_factor.items():
        actual = actual_by_factor[factor_span]
        crossed_factors = {
            dimension.factor_span
            for dimension in dimensions
            if dimension.dimension_id in actual.crossed_dimension_ids
        }
        if (
            actual.dimension_type is not expected.dimension_type
            or actual.operator is not expected.operator
            or actual.level_spans != expected.level_spans
            or set(actual.applies_to_local_event_ids) != event_ids
            or crossed_factors != set(expected.crossed_factor_spans)
        ):
            return False
    return True


def v11_context_dimensions_sha256() -> str:
    """Return the immutable identity of the sealed factor topology."""

    payload = [dimension.as_json() for dimension in V11_CONTEXT_DIMENSIONS]
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()


__all__ = [
    "SealedContextDimension",
    "V11_CONTEXT_DIMENSIONS",
    "v11_context_dimensions_match",
    "v11_context_dimensions_sha256",
]
