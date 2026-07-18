"""Shared two-agent execution for one finite source unit."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    start_model_attempt_audit,
    stop_model_attempt_audit,
)

from scripts.validation.claim_events.finite_source_unit.contracts import (
    EntailmentDecision,
    SourceUnitExtractionOutput,
    SourceUnitVerificationOutput,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    extract_source_unit,
    verify_source_unit_candidates,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.claim_frames import (
        BoundClaimInventoryItem,
    )
    from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
        ModelAttemptAuditRecord,
    )

    from scripts.validation.claim_events.finite_source_unit.service import (
        FiniteSourceUnitModelClient,
    )
    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )


@dataclass(frozen=True, slots=True)
class SingleUnitAgentRunEvidence:
    """Auditable result of one extractor and one blinded verifier."""

    extraction: SourceUnitExtractionOutput | None
    verification: SourceUnitVerificationOutput | None
    accepted: tuple[BoundClaimInventoryItem, ...]
    extracted_candidate_count: int
    binding_rejection_count: int
    records: tuple[ModelAttemptAuditRecord, ...]
    error_type: str | None


async def execute_source_unit_agents(
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
) -> SingleUnitAgentRunEvidence:
    """Run exactly one extraction and one independent verification call."""

    audit = start_model_attempt_audit(evidence_unit_id=unit.unit_id)
    extraction_output: SourceUnitExtractionOutput | None = None
    verification_output: SourceUnitVerificationOutput | None = None
    accepted: tuple[BoundClaimInventoryItem, ...] = ()
    extracted_candidate_count = binding_rejection_count = 0
    error_type: str | None = None
    try:
        extraction = await extract_source_unit(
            client=client,
            tenant=tenant,
            model_id=model_id,
            execution_namespace=execution_namespace,
            unit=unit,
        )
        extraction_output = extraction.value.output
        extracted_candidate_count = len(extraction.value.accepted)
        binding_rejection_count = len(extraction.value.rejected)
        verification = await verify_source_unit_candidates(
            client=client,
            tenant=tenant,
            model_id=model_id,
            execution_namespace=execution_namespace,
            unit=unit,
            candidates=extraction.value.accepted,
        )
        verification_output = verification.parsed
        accepted = tuple(
            candidate.claim
            for candidate in verification.value
            if candidate.verification.decision is EntailmentDecision.ENTAILED
        )
    except Exception as exc:  # noqa: BLE001 - retain categorical failure evidence
        error_type = type(exc).__name__
    finally:
        stop_model_attempt_audit(audit)
    return SingleUnitAgentRunEvidence(
        extraction=extraction_output,
        verification=verification_output,
        accepted=accepted,
        extracted_candidate_count=extracted_candidate_count,
        binding_rejection_count=binding_rejection_count,
        records=tuple(audit.records),
        error_type=error_type,
    )


def provider_response_ids(
    records: tuple[ModelAttemptAuditRecord, ...],
    pass_role: str,
) -> set[str]:
    """Return identified provider responses for one audited role."""

    return {
        record.provider_response_id
        for record in records
        if record.pass_role == pass_role and record.provider_response_id is not None
    }


def model_json(
    model: SourceUnitExtractionOutput | SourceUnitVerificationOutput | None,
) -> dict[str, object] | None:
    """Serialize one optional categorical model output."""

    return None if model is None else model.model_dump(mode="json")


def sha256_json(value: object) -> str:
    """Hash canonical JSON for create-once diagnostic reports."""

    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8"),
    ).hexdigest()


__all__ = [
    "SingleUnitAgentRunEvidence",
    "execute_source_unit_agents",
    "model_json",
    "provider_response_ids",
    "sha256_json",
]
