"""Committed component identity for V14 deterministic-mapping execution."""

from __future__ import annotations

from importlib import import_module
from typing import Final

from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    output_schema_json_sha256,
)

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitExtractionOutput,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v14.prompts import (
    V14_NORMALIZATION_PROMPT_VERSION,
    V14_NORMALIZED_REVIEW_PROMPT_VERSION,
    V14_PROMPT_POLICY,
    v14_normalization_prompt,
    v14_normalized_review_prompt,
)
from scripts.validation.claim_events.finite_source_unit.normalization.execution_custody import (
    callable_source_fingerprint,
    module_runtime_fingerprints,
)
from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    bind_source_unit_normalization,
    canonical_json_sha256,
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
from scripts.validation.claim_events.finite_source_unit.normalization.v14_contracts import (
    SourceUnitNormalizationProposalV14,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v14_service import (
    V14_MAPPING_DERIVATION_VERSION,
    bind_source_unit_normalization_v14,
    derive_v14_mapping_operations,
    normalize_source_unit_proposal_v14,
)

V14_EXECUTION_CONTRACT_VERSION: Final = "tg04.finite_source_unit.v14_execution.v1"
V14_EXECUTION_MODEL_IDS: Final = frozenset(
    {"openai:gpt-5.6-luna", "openai/gpt-5.6-luna"}
)
V14_EXECUTION_MANIFEST_SHA256: Final = (
    "dd92876918c36c9bab9a0d16d5e031c5331e91b8554a1c7d2b85cab03d9849f8"
)


class V14ExecutionContractError(RuntimeError):
    """The running V14 components do not match the committed execution contract."""


def v14_execution_manifest() -> dict[str, object]:
    """Return every provider-visible and deterministic V14 component identity."""

    manifest = {
        "contract_version": V14_EXECUTION_CONTRACT_VERSION,
        "model_ids": sorted(V14_EXECUTION_MODEL_IDS),
        "extraction_prompt_version": V14_PROMPT_POLICY.extraction_version,
        "extraction_prompt": callable_source_fingerprint(
            V14_PROMPT_POLICY.extraction_prompt
        ),
        "extraction_schema_sha256": output_schema_json_sha256(
            SourceUnitExtractionOutput
        ),
        "normalization_prompt_version": V14_NORMALIZATION_PROMPT_VERSION,
        "normalization_prompt": callable_source_fingerprint(v14_normalization_prompt),
        "normalization_schema_sha256": output_schema_json_sha256(
            SourceUnitNormalizationProposalV14
        ),
        "normalization_binder": callable_source_fingerprint(
            bind_source_unit_normalization_v14
        ),
        "mapping_derivation": callable_source_fingerprint(
            derive_v14_mapping_operations
        ),
        "normalization_executor": callable_source_fingerprint(
            normalize_source_unit_proposal_v14
        ),
        "mapping_derivation_version": V14_MAPPING_DERIVATION_VERSION,
        "canonical_normalization_schema_sha256": output_schema_json_sha256(
            SourceUnitNormalizationOutputV13
        ),
        "canonical_normalization_binder": callable_source_fingerprint(
            bind_source_unit_normalization
        ),
        "review_prompt_version": V14_NORMALIZED_REVIEW_PROMPT_VERSION,
        "review_prompt": callable_source_fingerprint(v14_normalized_review_prompt),
        "review_schema_sha256": output_schema_json_sha256(
            SourceUnitNormalizedReviewOutputV13V6
        ),
        "review_binder": callable_source_fingerprint(
            bind_v13_context_dimension_review
        ),
    }
    manifest["owned_runtime_modules"] = {
        module_name: module_runtime_fingerprints(import_module(module_name))
        for module_name in _SEALED_RUNTIME_MODULES
    }
    return manifest


_SEALED_RUNTIME_MODULES: Final = (
    "artana_evidence_api.document_extraction_support.claim_frames.mentions",
    "artana_evidence_api.document_extraction_support.claim_frames.inventory",
    "scripts.validation.claim_events.finite_source_unit.service",
    "scripts.validation.claim_events.finite_source_unit.contracts",
    "scripts.validation.claim_events.finite_source_unit.normalization.service",
    "scripts.validation.claim_events.finite_source_unit.normalization.review",
    "scripts.validation.claim_events.finite_source_unit.normalization.v13_contracts",
    "scripts.validation.claim_events.finite_source_unit.normalization.v13_review",
    "scripts.validation.claim_events.finite_source_unit.normalization.v13_review_contracts",
    "scripts.validation.claim_events.finite_source_unit.normalization.v14_contracts",
    "scripts.validation.claim_events.finite_source_unit.normalization.v14_service",
    "scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v14.evidence",
    "scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v14.lineage",
    "scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v14.execution",
)


def computed_v14_execution_manifest_sha256() -> str:
    return canonical_json_sha256(v14_execution_manifest())


def require_v14_execution_manifest() -> None:
    if computed_v14_execution_manifest_sha256() != V14_EXECUTION_MANIFEST_SHA256:
        raise V14ExecutionContractError(
            "V14 execution components changed after the manifest was issued"
        )


__all__ = [
    "V14_EXECUTION_CONTRACT_VERSION",
    "V14_EXECUTION_MANIFEST_SHA256",
    "V14_EXECUTION_MODEL_IDS",
    "V14ExecutionContractError",
    "computed_v14_execution_manifest_sha256",
    "require_v14_execution_manifest",
    "v14_execution_manifest",
]
