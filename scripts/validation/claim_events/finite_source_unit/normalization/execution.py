"""Three-agent scientific extraction, normalization, and review execution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol

from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    fingerprinted_step_key,
    start_model_attempt_audit,
    stop_model_attempt_audit,
)

from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    SourceUnitNormalizationOutput,
    SourceUnitNormalizedReviewOutput,
)
from scripts.validation.claim_events.finite_source_unit.normalization.execution_custody import (
    IssuedExecutionContractBoundaryError,
    IssuedExecutionPolicy,
    NormalizationPromptBuilder,
    NormalizedReviewPromptBuilder,
    is_issued_component_manifest,
    register_issued_execution_policy,
    require_issued_execution_authority,
)
from scripts.validation.claim_events.finite_source_unit.normalization.execution_custody import (
    execution_components_manifest_sha256 as _execution_components_manifest_sha256,
)
from scripts.validation.claim_events.finite_source_unit.normalization.execution_evidence import (
    ModelAttemptObserver,
    ThreeCallAgentRunEvidence,
    ThreeCallEvidenceObserver,
)
from scripts.validation.claim_events.finite_source_unit.normalization.execution_evidence import (
    build_three_call_agent_evidence as _agent_run_evidence,
)
from scripts.validation.claim_events.finite_source_unit.normalization.review import (
    NormalizedReviewBinder,
    bind_source_unit_normalized_review,
    review_source_unit_normalization,
)
from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    SourceUnitNormalizationResult,
    normalize_source_unit_extraction,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    SourceUnitExtractionResult,
    extract_source_unit,
)

if TYPE_CHECKING:
    from scripts.validation.claim_events.finite_source_unit.contracts import (
        SourceUnitExtractionOutput,
    )
    from scripts.validation.claim_events.finite_source_unit.normalization.review import (
        SourceUnitNormalizedReviewResult,
    )
    from scripts.validation.claim_events.finite_source_unit.service import (
        FiniteSourceUnitModelClient,
        SourceUnitPromptPolicy,
    )
    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )


class IssuedSourceUnitExecutor(Protocol):
    async def __call__(  # noqa: PLR0913
        self,
        *,
        client: FiniteSourceUnitModelClient,
        tenant: object,
        model_id: str,
        execution_namespace: str,
        unit: FrozenSourceUnit,
        audit_evidence_unit_id: str | None = None,
        evidence_observer: ThreeCallEvidenceObserver | None = None,
        attempt_observer: ModelAttemptObserver | None = None,
    ) -> ThreeCallAgentRunEvidence: ...


def bind_issued_v13_executor(
    policy: IssuedExecutionPolicy,
) -> IssuedSourceUnitExecutor:
    """Capture one frozen V13 policy behind an opaque execution authority."""

    snapshot = register_issued_execution_policy(policy)

    async def execute(  # noqa: PLR0913
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
        return await _execute_three_source_unit_agents(
            client=client,
            tenant=tenant,
            model_id=model_id,
            execution_namespace=execution_namespace,
            unit=unit,
            extraction_prompt_policy=snapshot.extraction_prompt_policy,
            normalization_prompt_builder=snapshot.normalization_prompt_builder,
            normalization_prompt_version=snapshot.normalization_prompt_version,
            normalization_output_schema=snapshot.normalization_output_schema,
            review_prompt_builder=snapshot.review_prompt_builder,
            review_prompt_version=snapshot.review_prompt_version,
            review_output_schema=snapshot.review_output_schema,
            review_binder=snapshot.review_binder,
            execution_contract_version=snapshot.contract_version,
            audit_evidence_unit_id=audit_evidence_unit_id,
            evidence_observer=evidence_observer,
            attempt_observer=attempt_observer,
            issued_manifest_sha256=snapshot.manifest_sha256,
            issued_authority=snapshot.authority,
        )

    return execute


class SourceUnitPromptBuildError(RuntimeError):
    """Categorical local failure between audited provider stages."""


class SourceUnitEvidencePersistenceError(RuntimeError):
    """Durable evidence could not be persisted after an audited attempt."""


async def execute_three_source_unit_agents(  # noqa: PLR0913
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
    extraction_prompt_policy: SourceUnitPromptPolicy,
    prepared_extraction_prompt: str | None = None,
    normalization_prompt_builder: NormalizationPromptBuilder,
    normalization_prompt_version: str,
    normalization_output_schema: type[SourceUnitNormalizationOutput] = (
        SourceUnitNormalizationOutput
    ),
    review_prompt_builder: NormalizedReviewPromptBuilder,
    review_prompt_version: str,
    review_output_schema: type[SourceUnitNormalizedReviewOutput] = (
        SourceUnitNormalizedReviewOutput
    ),
    review_binder: NormalizedReviewBinder = bind_source_unit_normalized_review,
    execution_contract_version: str | None = None,
    audit_evidence_unit_id: str | None = None,
    evidence_observer: ThreeCallEvidenceObserver | None = None,
    attempt_observer: ModelAttemptObserver | None = None,
) -> ThreeCallAgentRunEvidence:
    """Run caller-composed contracts; issued V13 contracts use dedicated owners."""

    component_manifest = _execution_components_manifest_sha256(
        extraction_prompt_policy=extraction_prompt_policy,
        normalization_prompt_builder=normalization_prompt_builder,
        normalization_prompt_version=normalization_prompt_version,
        normalization_output_schema=normalization_output_schema,
        review_prompt_builder=review_prompt_builder,
        review_prompt_version=review_prompt_version,
        review_output_schema=review_output_schema,
        review_binder=review_binder,
    )
    if is_issued_component_manifest(component_manifest):
        raise IssuedExecutionContractBoundaryError(
            "issued V13 contracts require their dedicated executor; issued V13 "
            "components require their exact dedicated executor"
        )
    if execution_contract_version is not None and execution_contract_version.startswith(
        "tg04.finite_source_unit.v13_execution."
    ):
        raise IssuedExecutionContractBoundaryError(
            "issued V13 contracts require their dedicated executor"
        )
    return await _execute_three_source_unit_agents(
        client=client,
        tenant=tenant,
        model_id=model_id,
        execution_namespace=execution_namespace,
        unit=unit,
        extraction_prompt_policy=extraction_prompt_policy,
        prepared_extraction_prompt=prepared_extraction_prompt,
        normalization_prompt_builder=normalization_prompt_builder,
        normalization_prompt_version=normalization_prompt_version,
        normalization_output_schema=normalization_output_schema,
        review_prompt_builder=review_prompt_builder,
        review_prompt_version=review_prompt_version,
        review_output_schema=review_output_schema,
        review_binder=review_binder,
        execution_contract_version=execution_contract_version,
        audit_evidence_unit_id=audit_evidence_unit_id,
        evidence_observer=evidence_observer,
        attempt_observer=attempt_observer,
    )


async def _execute_three_source_unit_agents(  # noqa: PLR0913, PLR0915
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
    extraction_prompt_policy: SourceUnitPromptPolicy,
    prepared_extraction_prompt: str | None = None,
    normalization_prompt_builder: NormalizationPromptBuilder,
    normalization_prompt_version: str,
    normalization_output_schema: type[SourceUnitNormalizationOutput] = (
        SourceUnitNormalizationOutput
    ),
    review_prompt_builder: NormalizedReviewPromptBuilder,
    review_prompt_version: str,
    review_output_schema: type[SourceUnitNormalizedReviewOutput] = (
        SourceUnitNormalizedReviewOutput
    ),
    review_binder: NormalizedReviewBinder = bind_source_unit_normalized_review,
    execution_contract_version: str | None = None,
    audit_evidence_unit_id: str | None = None,
    evidence_observer: ThreeCallEvidenceObserver | None = None,
    attempt_observer: ModelAttemptObserver | None = None,
    issued_manifest_sha256: str | None = None,
    issued_authority: object | None = None,
) -> ThreeCallAgentRunEvidence:
    """Run exactly three stages; stop on first failure and never retry."""

    execution_contract_version = _resolve_execution_contract_version(
        prepared_extraction_prompt=prepared_extraction_prompt,
        requested_version=execution_contract_version,
        issued_manifest_sha256=issued_manifest_sha256,
        issued_authority=issued_authority,
    )
    if execution_contract_version is not None and (
        not execution_contract_version.strip()
        or execution_contract_version.strip() != execution_contract_version
    ):
        raise ValueError("execution_contract_version must be a nonempty trimmed value")
    contract_bound_namespace = (
        execution_namespace
        if execution_contract_version is None
        else fingerprinted_step_key(
            "execution-contract",
            execution_namespace,
            execution_contract_version,
        )
    )
    audit = start_model_attempt_audit(
        evidence_unit_id=audit_evidence_unit_id or unit.unit_id,
        execution_contract_version=execution_contract_version,
        record_observer=attempt_observer,
    )
    original_output: SourceUnitExtractionOutput | None = None
    original_result: SourceUnitExtractionResult | None = None
    original_raw: dict[str, object] | None = None
    normalized_output: SourceUnitNormalizationOutput | None = None
    normalized_result: SourceUnitNormalizationResult | None = None
    normalized_raw: dict[str, object] | None = None
    review_output: SourceUnitNormalizedReviewOutput | None = None
    review_result: SourceUnitNormalizedReviewResult | None = None
    review_raw: dict[str, object] | None = None
    error_type: str | None = None
    active_stage: Literal["primary", "structure_normalization", "normalized_review"] = (
        "primary"
    )
    failed_stage: (
        Literal["primary", "structure_normalization", "normalized_review"] | None
    ) = None
    try:
        original = await extract_source_unit(
            client=client,
            tenant=tenant,
            model_id=model_id,
            execution_namespace=contract_bound_namespace,
            unit=unit,
            prompt_policy=extraction_prompt_policy,
            prepared_prompt=prepared_extraction_prompt,
        )
        original_output = original.parsed
        original_result = original.value
        original_raw = original.raw_output
        _observe_evidence(
            evidence_observer,
            _agent_run_evidence(
                original_output=original_output,
                original_result=original_result,
                original_raw=original_raw,
                normalized_output=normalized_output,
                normalized_result=normalized_result,
                normalized_raw=normalized_raw,
                review_output=review_output,
                review_result=review_result,
                review_raw=review_raw,
                records=tuple(audit.records),
                error_type=None,
                execution_contract_version=execution_contract_version,
                execution_manifest_sha256=issued_manifest_sha256,
                failed_stage=None,
            ),
        )

        active_stage = "structure_normalization"
        try:
            normalization_prompt = normalization_prompt_builder(
                unit=unit,
                original=original_result,
            )
        except Exception as exc:  # noqa: BLE001 - normalize local failure category
            raise SourceUnitPromptBuildError from exc
        normalized = await normalize_source_unit_extraction(
            client=client,
            tenant=tenant,
            model_id=model_id,
            execution_namespace=contract_bound_namespace,
            unit=unit,
            original=original_result,
            original_raw_output=original_raw,
            prompt=normalization_prompt,
            prompt_version=normalization_prompt_version,
            output_schema=normalization_output_schema,
        )
        normalized_output = normalized.parsed
        normalized_result = normalized.value
        normalized_raw = normalized.raw_output
        _observe_evidence(
            evidence_observer,
            _agent_run_evidence(
                original_output=original_output,
                original_result=original_result,
                original_raw=original_raw,
                normalized_output=normalized_output,
                normalized_result=normalized_result,
                normalized_raw=normalized_raw,
                review_output=review_output,
                review_result=review_result,
                review_raw=review_raw,
                records=tuple(audit.records),
                error_type=None,
                execution_contract_version=execution_contract_version,
                execution_manifest_sha256=issued_manifest_sha256,
                failed_stage=None,
            ),
        )

        active_stage = "normalized_review"
        try:
            review_prompt = review_prompt_builder(
                unit=unit,
                original=original_result,
                normalized=normalized_result,
            )
        except Exception as exc:  # noqa: BLE001 - normalize local failure category
            raise SourceUnitPromptBuildError from exc
        review = await review_source_unit_normalization(
            client=client,
            tenant=tenant,
            model_id=model_id,
            execution_namespace=contract_bound_namespace,
            unit=unit,
            original=original_result,
            normalized=normalized_result,
            original_raw_output=original_raw,
            normalized_raw_output=normalized_raw,
            prompt=review_prompt,
            prompt_version=review_prompt_version,
            output_schema=review_output_schema,
            review_binder=review_binder,
        )
        review_output = review.parsed
        review_result = review.value
        review_raw = review.raw_output
        _observe_evidence(
            evidence_observer,
            _agent_run_evidence(
                original_output=original_output,
                original_result=original_result,
                original_raw=original_raw,
                normalized_output=normalized_output,
                normalized_result=normalized_result,
                normalized_raw=normalized_raw,
                review_output=review_output,
                review_result=review_result,
                review_raw=review_raw,
                records=tuple(audit.records),
                error_type=None,
                execution_contract_version=execution_contract_version,
                execution_manifest_sha256=issued_manifest_sha256,
                failed_stage=None,
            ),
        )
    except SourceUnitEvidencePersistenceError:
        raise
    except Exception as exc:  # noqa: BLE001 - preserve terminal failure category
        error_type = type(exc).__name__
        failed_stage = active_stage
        if audit.records:
            _observe_evidence(
                evidence_observer,
                _agent_run_evidence(
                    original_output=original_output,
                    original_result=original_result,
                    original_raw=original_raw,
                    normalized_output=normalized_output,
                    normalized_result=normalized_result,
                    normalized_raw=normalized_raw,
                    review_output=review_output,
                    review_result=review_result,
                    review_raw=review_raw,
                    records=tuple(audit.records),
                    error_type=error_type,
                    execution_contract_version=execution_contract_version,
                    execution_manifest_sha256=issued_manifest_sha256,
                    failed_stage=failed_stage,
                ),
            )
    finally:
        stop_model_attempt_audit(audit)
    return _agent_run_evidence(
        original_output=original_output,
        original_result=original_result,
        original_raw=original_raw,
        normalized_output=normalized_output,
        normalized_result=normalized_result,
        normalized_raw=normalized_raw,
        review_output=review_output,
        review_result=review_result,
        review_raw=review_raw,
        records=tuple(audit.records),
        error_type=error_type,
        execution_contract_version=execution_contract_version,
        execution_manifest_sha256=issued_manifest_sha256,
        failed_stage=failed_stage,
    )


def _resolve_execution_contract_version(
    *,
    prepared_extraction_prompt: str | None,
    requested_version: str | None,
    issued_manifest_sha256: str | None,
    issued_authority: object | None,
) -> str | None:
    """Require opaque registered authority before assigning issued lineage."""

    if requested_version is not None and requested_version.startswith(
        "tg04.finite_source_unit.v13_execution."
    ):
        if prepared_extraction_prompt is not None or not (
            require_issued_execution_authority(
                contract_version=requested_version,
                manifest_sha256=issued_manifest_sha256,
                authority=issued_authority,
            )
        ):
            raise IssuedExecutionContractBoundaryError(
                "issued V13 identity requires its sealed executor and prompt"
            )
        return requested_version
    if issued_manifest_sha256 is not None or issued_authority is not None:
        raise IssuedExecutionContractBoundaryError(
            "issued execution authority cannot label a caller-composed contract"
        )
    return requested_version


def _observe_evidence(
    observer: ThreeCallEvidenceObserver | None,
    evidence: ThreeCallAgentRunEvidence,
) -> None:
    if observer is None:
        return
    try:
        observer(evidence)
    except Exception as exc:  # noqa: BLE001 - persistence failures are fail-closed
        raise SourceUnitEvidencePersistenceError from exc


__all__ = [
    "IssuedExecutionContractBoundaryError",
    "ModelAttemptObserver",
    "NormalizationPromptBuilder",
    "NormalizedReviewPromptBuilder",
    "SourceUnitEvidencePersistenceError",
    "SourceUnitPromptBuildError",
    "ThreeCallAgentRunEvidence",
    "ThreeCallEvidenceObserver",
    "execute_three_source_unit_agents",
]
