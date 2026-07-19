"""Audited source-only execution and deterministic completeness binding."""

from __future__ import annotations

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

from scripts.validation.claim_events.finite_source_unit.completeness.contracts import (
    SourceUnitCompletenessInventoryOutputV1,
)
from scripts.validation.claim_events.finite_source_unit.completeness.prompts import (
    COMPLETENESS_PROMPT_VERSION,
    whole_source_completeness_prompt,
)
from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    canonical_json_sha256,
    require_context_dimensions,
)

if TYPE_CHECKING:
    from scripts.validation.claim_events.finite_source_unit.service import (
        FiniteSourceUnitModelClient,
    )
    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )


@dataclass(frozen=True, slots=True)
class SourceUnitCompletenessResult:
    """Schema-valid inventory bound to one frozen source unit."""

    output: SourceUnitCompletenessInventoryOutputV1
    accepted: tuple[BoundClaimInventoryItem, ...]
    controlled_event_links: tuple[BoundControlledEventLink, ...]
    envelope_sha256: str

    def require_canonical_envelope(self, *, unit: FrozenSourceUnit) -> None:
        """Replay binding so copied or mutated result fields fail closed."""

        try:
            type(self.output).model_validate(
                self.output.model_dump(mode="python", warnings=False),
                strict=True,
            )
        except ValueError as exc:
            raise StructuredModelSemanticError(
                "completeness result contains unvalidated categorical values"
            ) from exc
        if self != bind_source_unit_completeness(self.output, unit=unit):
            raise StructuredModelSemanticError(
                "completeness result does not match its canonical source envelope"
            )


def bind_source_unit_completeness(
    output: SourceUnitCompletenessInventoryOutputV1,
    *,
    unit: FrozenSourceUnit,
) -> SourceUnitCompletenessResult:
    """Bind every item and topology without making biomedical judgments."""

    binding = bind_claim_inventory_items(
        output.events,
        source_text=unit.text,
        source_sha256=unit.source_sha256,
        chunk_index=unit.index,
        source_start_offset=unit.source_start,
    )
    if binding.rejected:
        raise StructuredModelSemanticError(
            "completeness inventory contains unresolved source-binding rejections"
        )
    link_result = link_controlled_events(binding.accepted)
    if link_result.ambiguities or link_result.unlinked_references:
        raise StructuredModelSemanticError(
            "completeness controlled-event topology is unresolved"
        )
    if unlinked_controlled_target_ids(binding.accepted, link_result.links):
        raise StructuredModelSemanticError(
            "completeness controlled target is unlinked"
        )
    require_context_dimensions(output=output, source_text=unit.text)
    if any(span not in unit.text for span in output.evidence_spans):
        raise StructuredModelSemanticError(
            "completeness evidence must be verbatim in the source unit"
        )
    return SourceUnitCompletenessResult(
        output=output,
        accepted=binding.accepted,
        controlled_event_links=link_result.links,
        envelope_sha256=canonical_json_sha256(
            {
                "unit": {
                    "unit_id": unit.unit_id,
                    "index": unit.index,
                    "source_start": unit.source_start,
                    "source_end": unit.source_end,
                    "source_sha256": unit.source_sha256,
                    "input_sha256": unit.input_sha256,
                },
                "output": output.model_dump(mode="json"),
            }
        ),
    )


async def inventory_source_unit_completeness(  # noqa: PLR0913
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
) -> AuditedStructuredStepResult[
    SourceUnitCompletenessInventoryOutputV1,
    SourceUnitCompletenessResult,
]:
    """Run exactly one source-only completeness call without retry or repair."""

    prompt = whole_source_completeness_prompt(unit)
    step_key = fingerprinted_step_key(
        COMPLETENESS_PROMPT_VERSION,
        model_id,
        unit.input_sha256,
        execution_namespace,
    )

    async def invoke(invocation_id: str, provider_prompt: str) -> ModelStepResult:
        return await client.step(
            run_id=kernel_run_id_for_invocation(invocation_id),
            tenant=tenant,
            model=model_id,
            prompt=provider_prompt,
            output_schema=SourceUnitCompletenessInventoryOutputV1,
            step_key=step_key,
            replay_policy="fork_on_drift",
        )

    return await run_audited_structured_step(
        invoke_model=invoke,
        model_id=model_id,
        prompt=prompt,
        output_schema=SourceUnitCompletenessInventoryOutputV1,
        step_key=step_key,
        audit_context=ModelAttemptAuditContext(
            attempt_role="whole_source_completeness",
            pass_role="whole_source_completeness",  # noqa: S106 - audit role
            retry_context=None,
            source_sha256=unit.source_sha256,
            input_sha256=unit.input_sha256,
            semantic_unit_id=unit.unit_id,
        ),
        validate_semantics=lambda output: bind_source_unit_completeness(
            output,
            unit=unit,
        ),
    )


__all__ = [
    "SourceUnitCompletenessResult",
    "bind_source_unit_completeness",
    "inventory_source_unit_completeness",
]
