"""Executable V13 policy binding prompts, schema, and audit identity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    output_schema_json_sha256,
)

from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v13.prompts import (
    V13_NORMALIZATION_PROMPT_VERSION,
    V13_NORMALIZATION_PROMPT_VERSION_V6,
    V13_NORMALIZED_REVIEW_PROMPT_VERSION,
    V13_NORMALIZED_REVIEW_PROMPT_VERSION_V6,
    V13_PROMPT_POLICY,
    v13_normalization_prompt,
    v13_normalization_prompt_v6,
    v13_normalized_review_prompt,
    v13_normalized_review_prompt_v6,
)
from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    SourceUnitNormalizedReviewOutput,
)
from scripts.validation.claim_events.finite_source_unit.normalization.execution import (
    NormalizationPromptBuilder,
    NormalizedReviewPromptBuilder,
    ThreeCallAgentRunEvidence,
    bind_issued_v13_executor,
)
from scripts.validation.claim_events.finite_source_unit.normalization.execution_custody import (
    issued_execution_policy_manifest_sha256,
)
from scripts.validation.claim_events.finite_source_unit.normalization.review import (
    bind_source_unit_normalized_review,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v12_contracts import (
    SourceUnitNormalizationOutputV12,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_contracts import (
    SourceUnitNormalizationOutputV13,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_review import (
    bind_v13_context_dimension_review,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_review_contracts import (
    SourceUnitNormalizedReviewOutputV13V6,
)

if TYPE_CHECKING:
    from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
        SourceUnitNormalizationOutput,
    )
    from scripts.validation.claim_events.finite_source_unit.normalization.execution import (
        ModelAttemptObserver,
        ThreeCallEvidenceObserver,
    )
    from scripts.validation.claim_events.finite_source_unit.normalization.review import (
        NormalizedReviewBinder,
    )
    from scripts.validation.claim_events.finite_source_unit.service import (
        FiniteSourceUnitModelClient,
        SourceUnitPromptPolicy,
    )
    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )


@dataclass(frozen=True, slots=True)
class V13ExecutionPolicy:
    """One immutable pairing of all provider-visible V13 contracts."""

    contract_version: str
    extraction_prompt_policy: SourceUnitPromptPolicy
    normalization_prompt_builder: NormalizationPromptBuilder
    normalization_prompt_version: str
    normalization_output_schema: type[SourceUnitNormalizationOutput]
    review_prompt_builder: NormalizedReviewPromptBuilder
    review_prompt_version: str
    review_output_schema: type[SourceUnitNormalizedReviewOutput]
    review_binder: NormalizedReviewBinder

    def as_json(self) -> dict[str, object]:
        schema = self.normalization_output_schema
        return {
            "contract_version": self.contract_version,
            "extraction_prompt_version": self.extraction_prompt_policy.extraction_version,
            "verification_prompt_version": (
                self.extraction_prompt_policy.verification_version
            ),
            "normalization_prompt_version": self.normalization_prompt_version,
            "normalization_output_schema": f"{schema.__module__}.{schema.__qualname__}",
            "normalization_output_schema_sha256": output_schema_json_sha256(schema),
            "review_prompt_version": self.review_prompt_version,
        }


@dataclass(frozen=True, slots=True)
class V13ExecutionPolicyV3:
    """Immutable V13-v3 pairing including source-only review enforcement."""

    contract_version: str
    extraction_prompt_policy: SourceUnitPromptPolicy
    normalization_prompt_builder: NormalizationPromptBuilder
    normalization_prompt_version: str
    normalization_output_schema: type[SourceUnitNormalizationOutput]
    review_prompt_builder: NormalizedReviewPromptBuilder
    review_prompt_version: str
    review_output_schema: type[SourceUnitNormalizedReviewOutput]
    review_binder: NormalizedReviewBinder

    def as_json(self) -> dict[str, object]:
        normalization_schema = self.normalization_output_schema
        review_schema = self.review_output_schema
        return {
            "contract_version": self.contract_version,
            "extraction_prompt_version": self.extraction_prompt_policy.extraction_version,
            "verification_prompt_version": (
                self.extraction_prompt_policy.verification_version
            ),
            "normalization_prompt_version": self.normalization_prompt_version,
            "normalization_output_schema": (
                f"{normalization_schema.__module__}.{normalization_schema.__qualname__}"
            ),
            "normalization_output_schema_sha256": output_schema_json_sha256(
                normalization_schema
            ),
            "review_prompt_version": self.review_prompt_version,
            "review_output_schema": (
                f"{review_schema.__module__}.{review_schema.__qualname__}"
            ),
            "review_output_schema_sha256": output_schema_json_sha256(review_schema),
            "review_binder": (
                f"{self.review_binder.__module__}.{self.review_binder.__qualname__}"
            ),
        }


class V13HistoricalSchemaCustodyError(RuntimeError):
    """An issued historical contract cannot be reconstructed exactly."""


V13_V4_ISSUED_NORMALIZATION_SCHEMA_SHA256: Final = (
    "627d8e53aaa24b4017fb24f28370b959502f2fe68fc41a2cb47a8d5de6b8b06f"
)


def require_v13_v4_schema_custody() -> None:
    """Fail closed because the exact schema issued in V13-v4 is unavailable."""

    available_hash = output_schema_json_sha256(SourceUnitNormalizationOutputV12)
    if available_hash != V13_V4_ISSUED_NORMALIZATION_SCHEMA_SHA256:
        raise V13HistoricalSchemaCustodyError(
            "V13-v4 normalization cannot be replayed or qualified: the issued "
            "provider schema is not reproducible from the committed V12 contract"
        )


V13_EXECUTION_POLICY: Final = V13ExecutionPolicy(
    contract_version="tg04.finite_source_unit.v13_execution.v2",
    extraction_prompt_policy=V13_PROMPT_POLICY,
    normalization_prompt_builder=v13_normalization_prompt,
    normalization_prompt_version=V13_NORMALIZATION_PROMPT_VERSION,
    normalization_output_schema=SourceUnitNormalizationOutputV13,
    review_prompt_builder=v13_normalized_review_prompt,
    review_prompt_version=V13_NORMALIZED_REVIEW_PROMPT_VERSION,
    review_output_schema=SourceUnitNormalizedReviewOutput,
    review_binder=bind_source_unit_normalized_review,
)

V13_EXECUTION_POLICY_V3: Final = V13ExecutionPolicyV3(
    contract_version="tg04.finite_source_unit.v13_execution.v3",
    extraction_prompt_policy=V13_PROMPT_POLICY,
    normalization_prompt_builder=v13_normalization_prompt_v6,
    normalization_prompt_version=V13_NORMALIZATION_PROMPT_VERSION_V6,
    normalization_output_schema=SourceUnitNormalizationOutputV13,
    review_prompt_builder=v13_normalized_review_prompt_v6,
    review_prompt_version=V13_NORMALIZED_REVIEW_PROMPT_VERSION_V6,
    review_output_schema=SourceUnitNormalizedReviewOutputV13V6,
    review_binder=bind_v13_context_dimension_review,
)

_EXECUTE_V13_V2 = bind_issued_v13_executor(V13_EXECUTION_POLICY)
_EXECUTE_V13_V3 = bind_issued_v13_executor(V13_EXECUTION_POLICY_V3)
V13_V3_EXECUTION_MANIFEST_SHA256: Final = issued_execution_policy_manifest_sha256(
    V13_EXECUTION_POLICY_V3
)
V13_V3_EXECUTION_CONTRACT_VERSION: Final = V13_EXECUTION_POLICY_V3.contract_version
_V13_V3_MODEL_IDS: Final = frozenset(
    {"openai:gpt-5.6-luna", "openai/gpt-5.6-luna"}
)
_V13_V3_SCHEMA_IDENTITIES: Final = (
    "scripts.validation.claim_events.finite_source_unit.contracts."
    "SourceUnitExtractionOutput",
    "scripts.validation.claim_events.finite_source_unit.normalization.v13_contracts."
    "SourceUnitNormalizationOutputV13",
    "scripts.validation.claim_events.finite_source_unit.normalization."
    "v13_review_contracts.SourceUnitNormalizedReviewOutputV13V6",
)


async def execute_v13_source_unit_agents(  # noqa: PLR0913
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
    audit_evidence_unit_id: str | None = None,
    evidence_observer: ThreeCallEvidenceObserver | None = None,
    attempt_observer: ModelAttemptObserver | None = None,
) -> ThreeCallAgentRunEvidence:
    """Reconstruct and run exactly the issued historical V13-v2 contract."""

    return await _EXECUTE_V13_V2(
        client=client,
        tenant=tenant,
        model_id=model_id,
        execution_namespace=execution_namespace,
        unit=unit,
        audit_evidence_unit_id=audit_evidence_unit_id,
        evidence_observer=evidence_observer,
        attempt_observer=attempt_observer,
    )


async def execute_v13_v3_source_unit_agents(  # noqa: PLR0913
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
    audit_evidence_unit_id: str | None = None,
    evidence_observer: ThreeCallEvidenceObserver | None = None,
    attempt_observer: ModelAttemptObserver | None = None,
) -> ThreeCallAgentRunEvidence:
    """Run exactly the immutable V13-v3 contract without retry or repair."""

    return await _EXECUTE_V13_V3(
        client=client,
        tenant=tenant,
        model_id=model_id,
        execution_namespace=execution_namespace,
        unit=unit,
        audit_evidence_unit_id=audit_evidence_unit_id,
        evidence_observer=evidence_observer,
        attempt_observer=attempt_observer,
    )


def has_locally_consistent_v13_v3_execution(
    evidence: ThreeCallAgentRunEvidence,
) -> bool:
    """Check local issued lineage; this does not verify live provider receipts."""

    expected_roles = ("primary", "structure_normalization", "normalized_review")
    return (
        evidence.execution_contract_version
        == V13_V3_EXECUTION_CONTRACT_VERSION
        and evidence.execution_manifest_sha256
        == V13_V3_EXECUTION_MANIFEST_SHA256
        and tuple(record.attempt_role for record in evidence.records) == expected_roles
        and tuple(record.output_schema_identity for record in evidence.records)
        == _V13_V3_SCHEMA_IDENTITIES
        and all(
            record.execution_contract_version
            == V13_V3_EXECUTION_CONTRACT_VERSION
            and record.validation_outcome == "accepted"
            and record.provider_response_id is not None
            and record.provider_output_sha256 is not None
            and record.model_id in _V13_V3_MODEL_IDS
            for record in evidence.records
        )
    )


def qualifies_v13_v3_agent_run(evidence: ThreeCallAgentRunEvidence) -> bool:
    """Remain false until a later contract binds completeness and live receipts."""

    del evidence
    return False


__all__ = [
    "V13_EXECUTION_POLICY",
    "V13_EXECUTION_POLICY_V3",
    "V13_V4_ISSUED_NORMALIZATION_SCHEMA_SHA256",
    "V13_V3_EXECUTION_MANIFEST_SHA256",
    "V13_V3_EXECUTION_CONTRACT_VERSION",
    "V13ExecutionPolicy",
    "V13ExecutionPolicyV3",
    "V13HistoricalSchemaCustodyError",
    "execute_v13_source_unit_agents",
    "execute_v13_v3_source_unit_agents",
    "has_locally_consistent_v13_v3_execution",
    "qualifies_v13_v3_agent_run",
    "require_v13_v4_schema_custody",
]
