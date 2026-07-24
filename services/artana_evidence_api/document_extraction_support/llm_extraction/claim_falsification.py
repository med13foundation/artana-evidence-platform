"""Blinded source-only categorical claim verification."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from artana_evidence_api.document_extraction_support.claim_frames.contracts import (
    ClaimFrame,
)
from artana_evidence_api.document_extraction_support.claim_frames.falsification import (
    ClaimVerificationOutput,
    ValidatedClaimVerification,
    validate_claim_verification,
)
from artana_evidence_api.document_extraction_support.llm_extraction.attempt_audit import (
    ModelAttemptPassRole,
    ModelAttemptRole,
)
from artana_evidence_api.document_extraction_support.llm_extraction.prompt_versions import (
    CLAIM_FALSIFICATION_PROMPT_VERSION,
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

_SYSTEM_PROMPT = """You are a blinded biomedical claim falsifier.

Judge only whether the supplied structured claim is faithfully supported by the
immutable claim-local source. You do not see the generator's reasoning. Return
categorical findings only; never return probabilities, confidence scores, or
numeric quality ratings.

Use exact source text for every evidence_spans entry. Evaluate the complete
event and participant roles, not merely whether its words occur. Distinguish
observed statistical evidence from an author's explicit significance claim. A
numeric P value alone does not establish SIGNIFICANT or NOT_SIGNIFICANT author
language. Mark a wrong core event, missing primary participant, unsupported
evidence, ambiguous source scope, or a claim needing discovery of another event
with the corresponding non-repairable failure axis. ABSTAIN rather than guess.
"""


@dataclass(frozen=True, slots=True)
class ClaimFalsificationStageResult:
    verification: ValidatedClaimVerification
    attempt_record: ModelAttemptAuditRecord
    raw_output: dict[str, object]
    prompt_version: str = CLAIM_FALSIFICATION_PROMPT_VERSION


def build_claim_falsification_prompt(
    *,
    claim_frame: ClaimFrame,
    source_region: str,
    source_sha256: str,
    phase: Literal["verification", "reverification"],
) -> str:
    """Build a blinded prompt without extraction or repair reasoning."""

    claim_payload = claim_frame.model_dump(mode="json")
    claim_payload.pop("extraction_rationale", None)
    serialized_claim = json.dumps(
        claim_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return (
        f"{_SYSTEM_PROMPT}\n"
        "MODEL CONTRACT\n"
        f"- prompt_version: {CLAIM_FALSIFICATION_PROMPT_VERSION}\n"
        f"- phase: {phase}\n"
        f"- source_sha256: {source_sha256}\n"
        f"- claim_sha256: {claim_frame.semantic_fingerprint}\n"
        "- evidence scope: exactly the immutable source region below\n"
        "- no generator or prior reviewer reasoning is available\n\n"
        "---\nFINAL STRUCTURED CLAIM\n---\n"
        f"{serialized_claim}\n"
        "---\nIMMUTABLE CLAIM-LOCAL SOURCE\n---\n"
        f"{source_region}\n---\n"
    )


async def run_claim_falsification_stage(
    *,
    claim_frame: ClaimFrame,
    source_region: str,
    source_sha256: str,
    semantic_unit_id: str,
    client: object,
    tenant: object,
    model_id: str,
    step_runner: ModelStepRunner,
    execution_namespace: str,
    phase: Literal["verification", "reverification"] = "verification",
) -> ClaimFalsificationStageResult:
    """Run one fresh blinded verifier invocation with no retry."""

    prompt = build_claim_falsification_prompt(
        claim_frame=claim_frame,
        source_region=source_region,
        source_sha256=source_sha256,
        phase=phase,
    )
    claim_sha256 = claim_frame.semantic_fingerprint
    input_sha256 = _canonical_sha256(
        {
            "phase": phase,
            "source_sha256": source_sha256,
            "source_region_sha256": hashlib.sha256(source_region.encode()).hexdigest(),
            "claim_sha256": claim_sha256,
        },
    )
    step_key = fingerprinted_step_key(
        f"research_init.claim_{phase}.v1",
        CLAIM_FALSIFICATION_PROMPT_VERSION,
        model_id,
        source_sha256,
        claim_sha256,
        semantic_unit_id,
        execution_namespace,
    )
    attempt_role: ModelAttemptRole = (
        "claim_verification" if phase == "verification" else "claim_reverification"
    )
    pass_role: ModelAttemptPassRole = (
        "claim_verification" if phase == "verification" else "claim_reverification"
    )
    audit_context = ModelAttemptAuditContext(
        attempt_role=attempt_role,
        pass_role=pass_role,
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
            output_schema=ClaimVerificationOutput,
            schema_id="document_extraction.claim_falsification.v1",
            step_key=step_key,
            replay_policy="fork_on_drift",
        )

    result = await run_audited_structured_step(
        invoke_model=_invoke_model,
        model_id=model_id,
        prompt=prompt,
        output_schema=ClaimVerificationOutput,
        step_key=step_key,
        audit_context=audit_context,
        validate_semantics=lambda output: validate_claim_verification(
            output=output,
            claim_frame=claim_frame,
            source_region=source_region,
            expected_source_sha256=source_sha256,
            expected_claim_sha256=claim_sha256,
        ),
    )
    return ClaimFalsificationStageResult(
        verification=result.value,
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
    "CLAIM_FALSIFICATION_PROMPT_VERSION",
    "ClaimFalsificationStageResult",
    "build_claim_falsification_prompt",
    "run_claim_falsification_stage",
]
