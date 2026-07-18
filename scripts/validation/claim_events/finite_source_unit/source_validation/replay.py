"""Deterministic reconstruction of an optional source-binding repair."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitExtractionOutput,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    SourceUnitExtractionResult,
    bind_source_unit_extraction,
)
from scripts.validation.claim_events.finite_source_unit.source_validation.binding_repair import (
    require_minimal_exact_span_repairs,
    require_source_binding_repair_invariant,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.claim_frames import (
        ClaimInventoryBindingRejection,
    )

    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )


@dataclass(frozen=True, slots=True)
class ReplayedSourceBinding:
    """Original and final extraction state reconstructed from audit payloads."""

    extraction: SourceUnitExtractionOutput
    bound: SourceUnitExtractionResult
    primary_extraction: SourceUnitExtractionOutput
    primary_rejections: tuple[ClaimInventoryBindingRejection, ...]
    observed_rejections: tuple[ClaimInventoryBindingRejection, ...]
    unresolved_rejections: tuple[ClaimInventoryBindingRejection, ...]
    schema_retry_count: int


def replay_source_binding(
    *,
    unit: FrozenSourceUnit,
    agent_extraction: dict[str, object],
    attempts: list[object],
) -> ReplayedSourceBinding:
    """Replay the primary extraction and at most one meaning-preserving repair."""

    primary_payloads = _role_payloads(attempts, "primary")
    repair_payloads = _role_payloads(attempts, "schema_retry")
    if len(primary_payloads) != 1 or len(repair_payloads) > 1:
        raise RuntimeError("holdout extraction attempt topology is invalid")

    primary = SourceUnitExtractionOutput.model_validate(primary_payloads[0])
    primary_bound = bind_source_unit_extraction(primary, unit=unit)
    if not repair_payloads:
        final = SourceUnitExtractionOutput.model_validate(agent_extraction)
        if final != primary:
            raise RuntimeError("holdout final extraction is not primary-audit-bound")
        return ReplayedSourceBinding(
            extraction=final,
            bound=primary_bound,
            primary_extraction=primary,
            primary_rejections=primary_bound.rejected,
            observed_rejections=primary_bound.rejected,
            unresolved_rejections=primary_bound.rejected,
            schema_retry_count=0,
        )

    if not primary_bound.rejected:
        raise RuntimeError("holdout binding repair lacks an original rejection")
    repaired = SourceUnitExtractionOutput.model_validate(repair_payloads[0])
    final = SourceUnitExtractionOutput.model_validate(agent_extraction)
    if final != repaired:
        raise RuntimeError("holdout final extraction is not repair-audit-bound")
    repaired_bound = bind_source_unit_extraction(repaired, unit=unit)
    require_source_binding_repair_invariant(
        original=primary,
        repaired=repaired,
        binding_errors=primary_bound.rejected,
    )
    require_minimal_exact_span_repairs(
        repaired=repaired_bound.accepted,
        binding_errors=primary_bound.rejected,
    )
    return ReplayedSourceBinding(
        extraction=repaired,
        bound=repaired_bound,
        primary_extraction=primary,
        primary_rejections=primary_bound.rejected,
        observed_rejections=(*primary_bound.rejected, *repaired_bound.rejected),
        unresolved_rejections=repaired_bound.rejected,
        schema_retry_count=1,
    )


def _role_payloads(attempts: list[object], role: str) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for attempt in attempts:
        if not isinstance(attempt, dict) or attempt.get("attempt_role") != role:
            continue
        payload = attempt.get("raw_model_payload")
        if not isinstance(payload, dict):
            raise TypeError(f"holdout {role} attempt payload must be an object")
        payloads.append(payload)
    return payloads


__all__ = ["ReplayedSourceBinding", "replay_source_binding"]
