"""Audited agent normalization without deterministic scientific repair."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from artana_evidence_api.document_extraction_support.claim_frames import (
    BoundClaimInventoryItem,
    BoundControlledEventLink,
    bind_claim_inventory_items,
    link_controlled_events,
    unlinked_controlled_target_ids,
)
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    kernel_run_id_for_invocation,
)
from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    AuditedStructuredStepResult,
    StructuredModelSemanticError,
    run_audited_structured_step,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    ModelAttemptAuditContext,
    ModelStepResult,
    fingerprinted_step_key,
)

from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    NormalizationFamily,
    NormalizationOperation,
    SourceUnitNormalizationOutput,
)

_MIN_MERGED_SOURCE_EVENTS = 2
_MIN_SPLIT_NORMALIZED_EVENTS = 2

if TYPE_CHECKING:
    from scripts.validation.claim_events.finite_source_unit.service import (
        FiniteSourceUnitModelClient,
        SourceUnitExtractionResult,
    )
    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )


@dataclass(frozen=True, slots=True)
class SourceUnitNormalizationResult:
    """Source-bound normalized output preserved beside the original extraction."""

    output: SourceUnitNormalizationOutput
    accepted: tuple[BoundClaimInventoryItem, ...]
    controlled_event_links: tuple[BoundControlledEventLink, ...]
    envelope_sha256: str

    def require_canonical_envelope(
        self,
        *,
        unit: FrozenSourceUnit,
        original: SourceUnitExtractionResult,
    ) -> None:
        """Reject copied or mutated result fields before downstream review."""

        try:
            type(self.output).model_validate(
                self.output.model_dump(mode="python", warnings=False),
                strict=True,
            )
        except ValueError as exc:
            raise StructuredModelSemanticError(
                "normalization result contains unvalidated categorical values"
            ) from exc
        expected = bind_source_unit_normalization(
            self.output,
            unit=unit,
            original=original,
        )
        if self != expected:
            raise StructuredModelSemanticError(
                "normalization result does not match its canonical source envelope"
            )


def canonical_json_sha256(value: object) -> str:
    """Return the stable hash used to bind downstream agent calls."""

    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
    ).hexdigest()


def bind_source_unit_normalization(
    output: SourceUnitNormalizationOutput,
    *,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
) -> SourceUnitNormalizationResult:
    """Reject incomplete mappings, source drift, and mixed graph families."""

    original.require_canonical_envelope(unit=unit)
    if output.eligibility_category is not original.output.eligibility_category:
        raise StructuredModelSemanticError(
            "normalization cannot change the source eligibility category"
        )
    source_event_count = len(original.output.events)
    if output.family is NormalizationFamily.ABSTAIN:
        return SourceUnitNormalizationResult(
            output=output,
            accepted=(),
            controlled_event_links=(),
            envelope_sha256=_normalization_envelope_sha256(
                output=output,
                unit=unit,
                original=original,
            ),
        )
    if source_event_count == 0:
        raise StructuredModelSemanticError(
            "normalization cannot create events from an empty source extraction"
        )

    _require_complete_mapping(output=output, original=original)
    _require_context_dimensions(output=output, source_text=unit.text)

    binding = bind_claim_inventory_items(
        output.events,
        source_text=unit.text,
        source_sha256=unit.source_sha256,
        chunk_index=unit.index,
        source_start_offset=unit.source_start,
    )
    if binding.rejected:
        raise StructuredModelSemanticError(
            "normalization contains unresolved source-binding rejections"
        )
    link_result = link_controlled_events(binding.accepted)
    if link_result.ambiguities or link_result.unlinked_references:
        raise StructuredModelSemanticError(
            "normalized controlled-event topology is unresolved"
        )
    if unlinked_controlled_target_ids(binding.accepted, link_result.links):
        raise StructuredModelSemanticError("normalized controlled target is unlinked")
    return SourceUnitNormalizationResult(
        output=output,
        accepted=binding.accepted,
        controlled_event_links=link_result.links,
        envelope_sha256=_normalization_envelope_sha256(
            output=output,
            unit=unit,
            original=original,
        ),
    )


def _normalization_envelope_sha256(
    *,
    output: SourceUnitNormalizationOutput,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
) -> str:
    """Bind normalization meaning to the exact source and original extraction."""

    return canonical_json_sha256(
        {
            "unit": {
                "unit_id": unit.unit_id,
                "index": unit.index,
                "source_start": unit.source_start,
                "source_end": unit.source_end,
                "source_sha256": unit.source_sha256,
                "input_sha256": unit.input_sha256,
            },
            "original_output": original.output.model_dump(mode="json"),
            "original_envelope_sha256": original.envelope_sha256,
            "normalization_output": output.model_dump(mode="json"),
        }
    )


def _require_complete_mapping(
    *,
    output: SourceUnitNormalizationOutput,
    original: SourceUnitExtractionResult,
) -> None:
    source_event_count = len(original.output.events)
    mapped_positions = tuple(
        position
        for mapping in output.mappings
        for position in mapping.source_event_positions
    )
    if any(position >= source_event_count for position in mapped_positions):
        raise StructuredModelSemanticError(
            "normalization mapping references unknown event"
        )
    if set(mapped_positions) != set(range(source_event_count)):
        raise StructuredModelSemanticError(
            "normalization mappings must cover every source event"
        )
    for position in set(mapped_positions):
        mappings = tuple(
            mapping
            for mapping in output.mappings
            if position in mapping.source_event_positions
        )
        if len(mappings) > 1 and any(
            mapping.operation is not NormalizationOperation.SPLIT
            for mapping in mappings
        ):
            raise StructuredModelSemanticError(
                "one source event may map repeatedly only through SPLIT operations"
            )
    _require_mapping_operation_semantics(
        output=output,
        original=original,
        source_use_counts=Counter(mapped_positions),
    )


def _require_mapping_operation_semantics(
    *,
    output: SourceUnitNormalizationOutput,
    original: SourceUnitExtractionResult,
    source_use_counts: Counter[int],
) -> None:
    """Require transformation labels to agree with mapping shape and content."""

    for mapping in output.mappings:
        source_position_count = len(mapping.source_event_positions)
        if (
            mapping.operation is NormalizationOperation.MERGE
            and source_position_count < _MIN_MERGED_SOURCE_EVENTS
        ):
            raise StructuredModelSemanticError("MERGE requires multiple source events")
        if mapping.operation in {
            NormalizationOperation.UNCHANGED,
            NormalizationOperation.REFRAME,
            NormalizationOperation.SPLIT,
        } and source_position_count != 1:
            raise StructuredModelSemanticError(
                f"{mapping.operation.value} must reference exactly one source event"
            )
        if mapping.operation is NormalizationOperation.SPLIT:
            source_position = mapping.source_event_positions[0]
            if source_use_counts[source_position] < _MIN_SPLIT_NORMALIZED_EVENTS:
                raise StructuredModelSemanticError(
                    "SPLIT requires one source event to produce multiple normalized events"
                )
        if mapping.operation is NormalizationOperation.UNCHANGED:
            source_event = original.output.events[mapping.source_event_positions[0]]
            normalized_event = output.events[mapping.normalized_event_position]
            if source_event.model_dump(mode="json") != normalized_event.model_dump(
                mode="json"
            ):
                raise StructuredModelSemanticError(
                    "UNCHANGED mapping altered the source event"
                )
        if mapping.operation is NormalizationOperation.REFRAME:
            source_event = original.output.events[mapping.source_event_positions[0]]
            normalized_event = output.events[mapping.normalized_event_position]
            if source_event.model_dump(mode="json") == normalized_event.model_dump(
                mode="json"
            ):
                raise StructuredModelSemanticError(
                    "REFRAME must alter the source event representation"
                )


def _require_context_dimensions(
    *,
    output: SourceUnitNormalizationOutput,
    source_text: str,
) -> None:
    dimensions = output.context_dimensions
    if not dimensions:
        return
    local_event_ids = tuple(event.local_event_id for event in output.events)
    if any(event_id is None for event_id in local_event_ids):
        raise StructuredModelSemanticError(
            "context dimensions require local IDs on every normalized event"
        )
    known_event_ids = {event_id for event_id in local_event_ids if event_id is not None}
    dimension_ids = {dimension.dimension_id for dimension in dimensions}
    if len(dimension_ids) != len(dimensions):
        raise StructuredModelSemanticError("context dimension IDs must be unique")
    for dimension in dimensions:
        source_spans = (dimension.factor_span, *dimension.level_spans)
        if any(span not in source_text for span in source_spans):
            raise StructuredModelSemanticError(
                "context dimension spans must be verbatim source evidence"
            )
        if not set(dimension.applies_to_local_event_ids).issubset(known_event_ids):
            raise StructuredModelSemanticError(
                "context dimension references an unknown normalized event"
            )
        if not set(dimension.crossed_dimension_ids).issubset(dimension_ids):
            raise StructuredModelSemanticError(
                "context dimension references an unknown crossed factor"
            )
        for crossed_id in dimension.crossed_dimension_ids:
            crossed = next(
                item for item in dimensions if item.dimension_id == crossed_id
            )
            if dimension.dimension_id not in crossed.crossed_dimension_ids:
                raise StructuredModelSemanticError(
                    "crossed context dimensions must be symmetric"
                )


async def normalize_source_unit_extraction(  # noqa: PLR0913
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
    original_raw_output: dict[str, object],
    prompt: str,
    prompt_version: str,
    output_schema: type[SourceUnitNormalizationOutput] = SourceUnitNormalizationOutput,
) -> AuditedStructuredStepResult[
    SourceUnitNormalizationOutput,
    SourceUnitNormalizationResult,
]:
    """Run exactly one normalization call bound to the original raw payload."""

    original_raw_sha256 = canonical_json_sha256(original_raw_output)
    step_key = fingerprinted_step_key(
        prompt_version,
        model_id,
        unit.input_sha256,
        original_raw_sha256,
        execution_namespace,
    )

    async def invoke(invocation_id: str, provider_prompt: str) -> ModelStepResult:
        return await client.step(
            run_id=kernel_run_id_for_invocation(invocation_id),
            tenant=tenant,
            model=model_id,
            prompt=provider_prompt,
            output_schema=output_schema,
            step_key=step_key,
            replay_policy="fork_on_drift",
        )

    return await run_audited_structured_step(
        invoke_model=invoke,
        model_id=model_id,
        prompt=prompt,
        output_schema=output_schema,
        step_key=step_key,
        audit_context=ModelAttemptAuditContext(
            attempt_role="structure_normalization",
            pass_role="structure_normalization",  # noqa: S106 - audit role
            retry_context=None,
            source_sha256=unit.source_sha256,
            input_sha256=unit.input_sha256,
            semantic_unit_id=unit.unit_id,
        ),
        validate_semantics=lambda output: bind_source_unit_normalization(
            output,
            unit=unit,
            original=original,
        ),
    )


__all__ = [
    "SourceUnitNormalizationResult",
    "bind_source_unit_normalization",
    "canonical_json_sha256",
    "normalize_source_unit_extraction",
]
