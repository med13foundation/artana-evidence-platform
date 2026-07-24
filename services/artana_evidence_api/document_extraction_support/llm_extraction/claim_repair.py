"""One typed, axis-limited semantic claim repair invocation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from artana_evidence_api.document_extraction_support.claim_frames.contracts import (
    ClaimFrame,
)
from artana_evidence_api.document_extraction_support.claim_frames.falsification import (
    AppliedClaimRepair,
    ClaimSemanticPatch,
    VerificationFailureAxis,
    apply_claim_semantic_patch,
)
from artana_evidence_api.document_extraction_support.llm_extraction.prompt_versions import (
    CLAIM_REPAIR_PROMPT_VERSION,
)
from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    run_audited_structured_step,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    ModelAttemptAuditContext,
    ModelAttemptAuditRecord,
    ModelStepResult,
    ModelStepRunner,
    fingerprinted_step_key,
)

_SYSTEM_PROMPT = """You repair one source-bound biomedical claim through a typed
semantic patch. Change only fields authorized by failure_axes. Never regenerate
the claim, change its relation/event type, add or remove a participant, borrow
evidence from another event, alter provenance, or expand the source scope.

Direction repair may only swap the two existing endpoints. Participant-role
repair may only correct a secondary participant while preserving both primary
participants. Every new qualifier, participant role, or measurement must be
supported by exact evidence in the immutable source. Return no scores or
probabilities. If an authorized source-supported patch cannot be expressed,
the caller will preserve the claim for review rather than retrying.
"""


@dataclass(frozen=True, slots=True)
class ClaimRepairStageResult:
    repair: AppliedClaimRepair
    patch: ClaimSemanticPatch
    attempt_record: ModelAttemptAuditRecord
    raw_output: dict[str, object]
    prompt_version: str = CLAIM_REPAIR_PROMPT_VERSION


def build_claim_repair_prompt(
    *,
    claim_frame: ClaimFrame,
    source_region: str,
    source_sha256: str,
    failure_axes: tuple[VerificationFailureAxis, ...],
    failure_evidence_spans: tuple[str, ...],
) -> str:
    """Build a repair prompt without verifier or generator reasoning."""

    claim_payload = claim_frame.model_dump(mode="json")
    claim_payload.pop("extraction_rationale", None)
    contract = {
        "source_sha256": source_sha256,
        "claim_sha256": claim_frame.semantic_fingerprint,
        "failure_axes": [axis.value for axis in failure_axes],
        "failure_evidence_spans": failure_evidence_spans,
        "claim": claim_payload,
    }
    return (
        f"{_SYSTEM_PROMPT}\n"
        "MODEL CONTRACT\n"
        f"- prompt_version: {CLAIM_REPAIR_PROMPT_VERSION}\n"
        f"{json.dumps(contract, sort_keys=True, separators=(',', ':'), ensure_ascii=True)}\n"
        "---\nIMMUTABLE CLAIM-LOCAL SOURCE\n---\n"
        f"{source_region}\n---\n"
    )


async def run_claim_repair_stage(
    *,
    claim_frame: ClaimFrame,
    source_region: str,
    source_sha256: str,
    failure_axes: tuple[VerificationFailureAxis, ...],
    failure_evidence_spans: tuple[str, ...],
    semantic_unit_id: str,
    client: object,
    tenant: object,
    model_id: str,
    step_runner: ModelStepRunner,
    execution_namespace: str,
) -> ClaimRepairStageResult:
    """Run exactly one repair call and apply it deterministically."""

    prompt = build_claim_repair_prompt(
        claim_frame=claim_frame,
        source_region=source_region,
        source_sha256=source_sha256,
        failure_axes=failure_axes,
        failure_evidence_spans=failure_evidence_spans,
    )
    claim_sha256 = claim_frame.semantic_fingerprint
    input_sha256 = _canonical_sha256(
        {
            "source_sha256": source_sha256,
            "source_region_sha256": hashlib.sha256(source_region.encode()).hexdigest(),
            "claim_sha256": claim_sha256,
            "failure_axes": [axis.value for axis in failure_axes],
            "failure_evidence_spans": failure_evidence_spans,
        },
    )
    step_key = fingerprinted_step_key(
        "research_init.claim_repair.v1",
        CLAIM_REPAIR_PROMPT_VERSION,
        model_id,
        source_sha256,
        claim_sha256,
        semantic_unit_id,
        execution_namespace,
    )
    audit_context = ModelAttemptAuditContext(
        attempt_role="claim_repair",
        pass_role="claim_repair",
        retry_context=None,
        source_sha256=source_sha256,
        input_sha256=input_sha256,
        semantic_unit_id=semantic_unit_id,
    )

    async def _invoke_model(
        invocation_id: str,
        provider_prompt: str,
    ) -> ModelStepResult:
        return await step_runner(
            client,
            run_id=f"research-init-extraction:{invocation_id}",
            tenant=tenant,
            model=model_id,
            prompt=provider_prompt,
            output_schema=ClaimSemanticPatch,
            schema_id="document_extraction.claim_repair.v1",
            step_key=step_key,
            replay_policy="fork_on_drift",
        )

    result = await run_audited_structured_step(
        invoke_model=_invoke_model,
        model_id=model_id,
        prompt=prompt,
        output_schema=ClaimSemanticPatch,
        step_key=step_key,
        audit_context=audit_context,
        validate_semantics=lambda patch: apply_claim_semantic_patch(
            original_frame=claim_frame,
            patch=patch,
            authorized_failure_axes=failure_axes,
            source_region=source_region,
            expected_source_sha256=source_sha256,
        ),
    )
    return ClaimRepairStageResult(
        repair=result.value,
        patch=result.parsed,
        attempt_record=result.attempt_record,
        raw_output=result.raw_output,
    )


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


__all__ = [
    "CLAIM_REPAIR_PROMPT_VERSION",
    "ClaimRepairStageResult",
    "build_claim_repair_prompt",
    "run_claim_repair_stage",
]
