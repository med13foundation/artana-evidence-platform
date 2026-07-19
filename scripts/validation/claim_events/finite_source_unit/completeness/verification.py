"""Independent ordered verification for a completeness inventory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    kernel_run_id_for_invocation,
)
from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    AuditedStructuredStepResult,
    run_audited_structured_step,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    ModelAttemptAuditContext,
    ModelStepResult,
    fingerprinted_step_key,
)

from scripts.validation.claim_events.finite_source_unit.completeness.prompts import (
    COMPLETENESS_VERIFICATION_PROMPT_VERSION,
    whole_source_completeness_verification_prompt,
)
from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitVerificationOutput,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    bind_source_unit_verification,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.claim_frames import (
        BoundClaimInventoryItem,
    )

    from scripts.validation.claim_events.finite_source_unit.service import (
        FiniteSourceUnitModelClient,
        VerifiedEventCandidate,
    )
    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )


async def verify_completeness_inventory(  # noqa: PLR0913
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
    candidates: tuple[BoundClaimInventoryItem, ...],
) -> AuditedStructuredStepResult[
    SourceUnitVerificationOutput,
    tuple[VerifiedEventCandidate, ...],
]:
    """Run exactly one non-repairing source-only verification call."""

    prompt = whole_source_completeness_verification_prompt(
        unit=unit,
        candidates=candidates,
    )
    candidate_identity = "\n".join(
        candidate.inventory_id for candidate in candidates
    )
    step_key = fingerprinted_step_key(
        COMPLETENESS_VERIFICATION_PROMPT_VERSION,
        model_id,
        unit.input_sha256,
        candidate_identity,
        execution_namespace,
    )

    async def invoke(invocation_id: str, provider_prompt: str) -> ModelStepResult:
        return await client.step(
            run_id=kernel_run_id_for_invocation(invocation_id),
            tenant=tenant,
            model=model_id,
            prompt=provider_prompt,
            output_schema=SourceUnitVerificationOutput,
            step_key=step_key,
            replay_policy="fork_on_drift",
        )

    return await run_audited_structured_step(
        invoke_model=invoke,
        model_id=model_id,
        prompt=prompt,
        output_schema=SourceUnitVerificationOutput,
        step_key=step_key,
        audit_context=ModelAttemptAuditContext(
            attempt_role="whole_source_completeness_verification",
            pass_role="whole_source_completeness_verification",  # noqa: S106
            retry_context=None,
            source_sha256=unit.source_sha256,
            input_sha256=unit.input_sha256,
            semantic_unit_id=unit.unit_id,
        ),
        validate_semantics=lambda output: bind_source_unit_verification(
            output,
            unit=unit,
            candidates=candidates,
        ),
    )


__all__ = ["verify_completeness_inventory"]
