"""Frozen context-dimension expectation for the V12 title claim."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    canonical_json_sha256,
)

if TYPE_CHECKING:
    from scripts.validation.claim_events.finite_source_unit.normalization.context_dimensions import (
        ContextDimension,
    )
    from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
        SourceUnitNormalizationOutput,
    )

V12_CONTEXT_DIMENSIONS: Final[tuple[ContextDimension, ...]] = ()


def v12_context_dimensions_match(output: SourceUnitNormalizationOutput) -> bool:
    """Require no invented factorial context in the source-only title claim."""

    return not output.context_dimensions


def v12_context_dimensions_sha256() -> str:
    """Return the frozen empty context-topology identity."""

    return canonical_json_sha256(v12_context_dimensions_json())


def v12_context_dimensions_json() -> list[dict[str, object]]:
    """Serialize the frozen context contract once for reports and replay."""

    return [dimension.model_dump(mode="json") for dimension in V12_CONTEXT_DIMENSIONS]


__all__ = [
    "V12_CONTEXT_DIMENSIONS",
    "v12_context_dimensions_json",
    "v12_context_dimensions_match",
    "v12_context_dimensions_sha256",
]
