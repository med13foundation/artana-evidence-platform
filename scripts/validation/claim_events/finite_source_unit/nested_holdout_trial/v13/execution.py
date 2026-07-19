"""Executable V13 policy binding prompts, schema, and audit identity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    output_schema_json_sha256,
)

from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v13.prompts import (
    V13_NORMALIZATION_PROMPT_VERSION,
    V13_NORMALIZED_REVIEW_PROMPT_VERSION,
    V13_PROMPT_POLICY,
    v13_normalization_prompt,
    v13_normalized_review_prompt,
)
from scripts.validation.claim_events.finite_source_unit.normalization.execution import (
    NormalizationPromptBuilder,
    NormalizedReviewPromptBuilder,
    ThreeCallAgentRunEvidence,
    execute_three_source_unit_agents,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v12_contracts import (
    SourceUnitNormalizationOutputV12,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_contracts import (
    SourceUnitNormalizationOutputV13,
)

if TYPE_CHECKING:
    from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
        SourceUnitNormalizationOutput,
    )
    from scripts.validation.claim_events.finite_source_unit.normalization.execution import (
        ModelAttemptObserver,
        ThreeCallEvidenceObserver,
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
    """Run exactly the immutable V13 three-agent contract without retry."""

    policy = V13_EXECUTION_POLICY
    return await execute_three_source_unit_agents(
        client=client,
        tenant=tenant,
        model_id=model_id,
        execution_namespace=execution_namespace,
        unit=unit,
        extraction_prompt_policy=policy.extraction_prompt_policy,
        normalization_prompt_builder=policy.normalization_prompt_builder,
        normalization_prompt_version=policy.normalization_prompt_version,
        normalization_output_schema=policy.normalization_output_schema,
        review_prompt_builder=policy.review_prompt_builder,
        review_prompt_version=policy.review_prompt_version,
        execution_contract_version=policy.contract_version,
        audit_evidence_unit_id=audit_evidence_unit_id,
        evidence_observer=evidence_observer,
        attempt_observer=attempt_observer,
    )


__all__ = [
    "V13_EXECUTION_POLICY",
    "V13_V4_ISSUED_NORMALIZATION_SCHEMA_SHA256",
    "V13ExecutionPolicy",
    "V13HistoricalSchemaCustodyError",
    "execute_v13_source_unit_agents",
    "require_v13_v4_schema_custody",
]
