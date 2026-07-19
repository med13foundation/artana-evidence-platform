"""Five-call visible experiment with receipt and durability stop gates."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimArgumentRole,
    ClaimEventRole,
    ClaimEventType,
    InventoryPolarity,
)
from artana_evidence_api.document_extraction_support.llm_extraction.attempt_audit import (
    start_model_attempt_audit,
    stop_model_attempt_audit,
)
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    output_schema_json_sha256,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    fingerprinted_step_key,
)

from scripts.validation.claim_events import runner as claim_event_runner_module
from scripts.validation.claim_events.finite_source_unit.completeness import (
    comparison as completeness_comparison_module,
)
from scripts.validation.claim_events.finite_source_unit.completeness import (
    journal as completeness_journal_module,
)
from scripts.validation.claim_events.finite_source_unit.completeness import (
    service as completeness_service_module,
)
from scripts.validation.claim_events.finite_source_unit.completeness import (
    verification as completeness_verification_module,
)
from scripts.validation.claim_events.finite_source_unit.completeness.comparison import (
    ArgumentObligation,
    ControlledEventObligation,
    DiagnosticClauseObligation,
    PairedCompletenessResult,
    VerifiedCompletenessArm,
    compare_completeness_arms,
    comparison_module_sha256,
    comparison_runtime_fingerprints,
)
from scripts.validation.claim_events.finite_source_unit.completeness.contracts import (
    SourceUnitCompletenessInventoryOutputV1,
)
from scripts.validation.claim_events.finite_source_unit.completeness.journal import (
    CompletenessExperimentJournal,
)
from scripts.validation.claim_events.finite_source_unit.completeness.prompts import (
    COMPLETENESS_PROMPT_VERSION,
    COMPLETENESS_VERIFICATION_PROMPT_VERSION,
    whole_source_completeness_prompt,
    whole_source_completeness_verification_prompt,
)
from scripts.validation.claim_events.finite_source_unit.completeness.service import (
    SourceUnitCompletenessResult,
    bind_source_unit_completeness,
    inventory_source_unit_completeness,
)
from scripts.validation.claim_events.finite_source_unit.completeness.verification import (
    verify_completeness_inventory,
)
from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitExtractionOutput,
    SourceUnitVerificationOutput,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v13.execution import (
    V13_V3_EXECUTION_CONTRACT_VERSION,
    V13_V3_EXECUTION_MANIFEST_SHA256,
    execute_v13_v3_source_unit_agents,
    has_locally_consistent_v13_v3_execution,
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
from scripts.validation.claim_events.finite_source_unit.normalization.v13_review_contracts import (
    SourceUnitNormalizedReviewOutputV13V6,
)
from scripts.validation.claim_events.runner import receipt_expectation_from_attempt
from scripts.validation.claim_frames import (
    provider_receipts as provider_receipts_module,
)
from scripts.validation.claim_frames.provider_receipts import (
    OPENAI_PROVIDER_RECEIPT_BASE_URL,
    OpenAIProviderReceiptVerifier,
    ProviderReceiptVerification,
    canonical_provider_model_id,
    verify_provider_receipts,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.llm_extraction.attempt_audit import (
        ModelAttemptAuditRecord,
    )
    from pydantic import BaseModel

    from scripts.validation.claim_events.finite_source_unit.normalization.execution import (
        ThreeCallAgentRunEvidence,
    )
    from scripts.validation.claim_events.finite_source_unit.service import (
        FiniteSourceUnitModelClient,
        VerifiedEventCandidate,
    )
    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )

EXPERIMENT_CONTRACT_VERSION: Final = "tg04.finite_source_unit.completeness_ab.v1"
METRIC_VERSION: Final = "tg04.localization_obligation_recovery.v1"
EXPERIMENT_MODEL_ID: Final = "openai:gpt-5.6-luna"
EXPERIMENT_EXECUTION_MODEL_ID: Final = "openai/gpt-5.6-luna"
EXPERIMENT_SOURCE_SHA256: Final = (
    "a3373f43f94b696ad2ac9830707eae96aa17e6e2e0bc4185f87d768169ca2272"
)
EXPERIMENT_SOURCE_TEXT_SHA256: Final = (
    "96d4fc413d71b55675e7f5d2c08b0ce08df582d778af58170576d20485bcb641"
)
EXPERIMENT_UNIT_INPUT_SHA256: Final = (
    "77f478eba1d0ac017d889c7623b478c84d5f7c123baa4fb61e2b5ea0553771ac"
)
EXPERIMENT_UNIT_ID: Final = (
    "source-unit-5ef1f16712fdc52972162a846d08993bf655b5d7e62d7f0d87599637b0de2f4e"
)
EXPERIMENT_UNIT_INDEX: Final = 6
EXPERIMENT_UNIT_SOURCE_START: Final = 947
EXPERIMENT_UNIT_SOURCE_END: Final = 1123
EXPECTED_COMPLETENESS_MANIFEST_SHA256: Final = (
    "00d12f4647f6dfc127e6a1b6650ca45443ae964e240783d20b47eae7bb2cf481"
)
EXPECTED_ROLES: Final = (
    "primary",
    "structure_normalization",
    "normalized_review",
    "whole_source_completeness",
    "whole_source_completeness_verification",
)
_POLICY_AUTHORITY: Final = object()
_FROZEN_OBLIGATIONS: Final = tuple(
    ControlledEventObligation(
        obligation_id=f"suppressed-nuclear-localization-{participant.casefold()}",
        target_event_type=ClaimEventType.LOCALIZATION,
        target_participant_span=participant,
        target_allowed_participant_spans=("RelA", "NF-kappaB1"),
        target_cue_span="localization",
        target_destination_span="nuclear",
        controller_event_type=ClaimEventType.NEGATIVE_REGULATION,
        controller_cause_span="RCC-S",
        controller_cue_span="suppress",
    )
    for participant in ("RelA", "NF-kappaB1")
)
_FROZEN_DIAGNOSTICS: Final = (
    DiagnosticClauseObligation(
        obligation_id="cytoplasmic-null-result",
        event_type=ClaimEventType.NO_EFFECT,
        cue_span="did not alter",
        polarity=InventoryPolarity.NULL_RESULT,
        exact_arguments=(
            ArgumentObligation(
                ClaimArgumentRole.OTHER_ENTITY,
                ClaimEventRole.CAUSE,
                "RCC-S",
            ),
            ArgumentObligation(
                ClaimArgumentRole.OUTCOME,
                ClaimEventRole.EFFECT,
                "cytoplasmic levels",
            ),
        ),
    ),
    DiagnosticClauseObligation(
        obligation_id="binding-activation-inhibited",
        event_type=ClaimEventType.NEGATIVE_REGULATION,
        cue_span="inhibited",
        polarity=InventoryPolarity.SUPPORT,
        exact_arguments=(
            ArgumentObligation(
                ClaimArgumentRole.OTHER_ENTITY,
                ClaimEventRole.CAUSE,
                "RCC-S",
            ),
            ArgumentObligation(
                ClaimArgumentRole.BIOLOGICAL_PROCESS,
                ClaimEventRole.THEME,
                "activation of RelA/NF-kappaB1 binding complexes",
                controlled_event_ref=True,
            ),
        ),
        controlled_target_event_type=ClaimEventType.BINDING,
        controlled_target_cue_span="binding",
        controlled_target_exact_arguments=(
            ArgumentObligation(
                ClaimArgumentRole.GENE_OR_PROTEIN,
                ClaimEventRole.THEME,
                "RelA",
            ),
            ArgumentObligation(
                ClaimArgumentRole.GENE_OR_PROTEIN,
                ClaimEventRole.THEME,
                "NF-kappaB1",
            ),
        ),
    ),
)


class CompletenessExperimentGateError(RuntimeError):
    """A frozen safety or custody gate stopped the live experiment."""


class _ReceiptVerifier(Protocol):
    def __call__(
        self,
        *,
        records: tuple[ModelAttemptAuditRecord, ...],
        model_id: str,
    ) -> ProviderReceiptVerification: ...


@dataclass(frozen=True, slots=True)
class CompletenessExperimentPolicy:
    """Frozen semantic obligations and executable contract identity."""

    obligations: tuple[ControlledEventObligation, ...]
    diagnostics: tuple[DiagnosticClauseObligation, ...]
    model_id: str
    source_sha256: str
    source_text_sha256: str
    unit_input_sha256: str
    completeness_prompt_sha256: str
    _authority: object = field(repr=False, compare=False)
    contract_version: str = EXPERIMENT_CONTRACT_VERSION
    metric_version: str = METRIC_VERSION
    manifest_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if self._authority is not _POLICY_AUTHORITY:
            raise ValueError("completeness policy was not issued by the frozen factory")
        if self.contract_version != EXPERIMENT_CONTRACT_VERSION:
            raise ValueError("completeness contract version is not frozen")
        if self.metric_version != METRIC_VERSION:
            raise ValueError("completeness metric version is not frozen")
        if self.model_id != EXPERIMENT_MODEL_ID:
            raise ValueError("completeness experiment model is not frozen")
        if self.source_sha256 != EXPERIMENT_SOURCE_SHA256:
            raise ValueError("completeness experiment source is not frozen")
        if self.source_text_sha256 != EXPERIMENT_SOURCE_TEXT_SHA256:
            raise ValueError("completeness source-unit text is not frozen")
        if self.unit_input_sha256 != EXPERIMENT_UNIT_INPUT_SHA256:
            raise ValueError("completeness source-unit identity is not frozen")
        if self.obligations != _FROZEN_OBLIGATIONS:
            raise ValueError("completeness obligations are not the issued set")
        if self.diagnostics != _FROZEN_DIAGNOSTICS:
            raise ValueError("completeness diagnostics are not the issued set")
        if not self.obligations:
            raise ValueError("completeness experiment requires frozen obligations")
        if not self.diagnostics:
            raise ValueError("completeness experiment requires frozen diagnostics")
        obligation_ids = tuple(item.obligation_id for item in self.obligations)
        if len(set(obligation_ids)) != len(obligation_ids):
            raise ValueError("completeness obligation IDs must be unique")
        object.__setattr__(
            self,
            "manifest_sha256",
            canonical_json_sha256(self.as_json(include_manifest=False)),
        )

    def as_json(self, *, include_manifest: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "contract_version": self.contract_version,
            "metric_version": self.metric_version,
            "model_id": self.model_id,
            "execution_model_id": EXPERIMENT_EXECUTION_MODEL_ID,
            "source_sha256": self.source_sha256,
            "source_text_sha256": self.source_text_sha256,
            "unit_input_sha256": self.unit_input_sha256,
            "source_unit_id": EXPERIMENT_UNIT_ID,
            "source_unit_index": EXPERIMENT_UNIT_INDEX,
            "source_unit_source_start": EXPERIMENT_UNIT_SOURCE_START,
            "source_unit_source_end": EXPERIMENT_UNIT_SOURCE_END,
            "completeness_prompt_sha256": self.completeness_prompt_sha256,
            "a_contract_version": V13_V3_EXECUTION_CONTRACT_VERSION,
            "a_manifest_sha256": V13_V3_EXECUTION_MANIFEST_SHA256,
            "completeness_prompt_version": COMPLETENESS_PROMPT_VERSION,
            "completeness_schema_sha256": output_schema_json_sha256(
                SourceUnitCompletenessInventoryOutputV1
            ),
            "verification_prompt_version": (COMPLETENESS_VERIFICATION_PROMPT_VERSION),
            "verification_schema_sha256": output_schema_json_sha256(
                SourceUnitVerificationOutput
            ),
            "provider_receipt_base_url": OPENAI_PROVIDER_RECEIPT_BASE_URL,
            "expected_roles": EXPECTED_ROLES,
            "callable_fingerprints": {
                "completeness_prompt": callable_source_fingerprint(
                    whole_source_completeness_prompt
                ),
                "completeness_binder": callable_source_fingerprint(
                    bind_source_unit_completeness
                ),
                "verification_prompt": callable_source_fingerprint(
                    whole_source_completeness_verification_prompt
                ),
                "verification_executor": callable_source_fingerprint(
                    verify_completeness_inventory
                ),
                "comparator": callable_source_fingerprint(compare_completeness_arms),
                "comparison_module_sha256": comparison_module_sha256(),
                "comparison_runtime": comparison_runtime_fingerprints(),
                "issued_receipt_verifier": callable_source_fingerprint(
                    _ISSUED_RECEIPT_VERIFIER
                ),
                "execution_model_resolver": callable_source_fingerprint(
                    _execution_model_id
                ),
                "a_normalization_binder": callable_source_fingerprint(
                    bind_source_unit_normalization
                ),
            },
            "runtime_module_fingerprints": {
                "claim_event_runner": module_runtime_fingerprints(
                    claim_event_runner_module
                ),
                "completeness_comparison": module_runtime_fingerprints(
                    completeness_comparison_module
                ),
                "completeness_journal": module_runtime_fingerprints(
                    completeness_journal_module
                ),
                "completeness_service": module_runtime_fingerprints(
                    completeness_service_module
                ),
                "completeness_verification": module_runtime_fingerprints(
                    completeness_verification_module
                ),
                "provider_receipts": module_runtime_fingerprints(
                    provider_receipts_module
                ),
            },
            "obligations": [
                {
                    "obligation_id": item.obligation_id,
                    "target_event_type": item.target_event_type.value,
                    "target_participant_span": item.target_participant_span,
                    "target_allowed_participant_spans": (
                        item.target_allowed_participant_spans
                    ),
                    "target_cue_span": item.target_cue_span,
                    "target_destination_span": item.target_destination_span,
                    "controller_event_type": item.controller_event_type.value,
                    "controller_cause_span": item.controller_cause_span,
                    "controller_cue_span": item.controller_cue_span,
                }
                for item in self.obligations
            ],
            "diagnostics": [
                {
                    "obligation_id": item.obligation_id,
                    "event_type": item.event_type.value,
                    "cue_span": item.cue_span,
                    "polarity": item.polarity.value,
                    "exact_arguments": [
                        {
                            "role": argument.role.value,
                            "event_role": argument.event_role.value,
                            "exact_span": argument.exact_span,
                            "controlled_event_ref": argument.controlled_event_ref,
                        }
                        for argument in item.exact_arguments
                    ],
                    "controlled_target_event_type": (
                        item.controlled_target_event_type.value
                        if item.controlled_target_event_type is not None
                        else None
                    ),
                    "controlled_target_cue_span": item.controlled_target_cue_span,
                    "controlled_target_exact_arguments": [
                        {
                            "role": argument.role.value,
                            "event_role": argument.event_role.value,
                            "exact_span": argument.exact_span,
                            "controlled_event_ref": argument.controlled_event_ref,
                        }
                        for argument in item.controlled_target_exact_arguments
                    ],
                }
                for item in self.diagnostics
            ],
        }
        if include_manifest:
            payload["manifest_sha256"] = self.manifest_sha256
        return payload


def issue_completeness_experiment_policy(
    *,
    unit: FrozenSourceUnit,
    model_id: str,
) -> CompletenessExperimentPolicy:
    """Issue the only preregistered policy accepted by the visible experiment."""

    if unit.source_sha256 != EXPERIMENT_SOURCE_SHA256:
        raise ValueError("source unit does not match the preregistered source")
    source_text_sha256 = hashlib.sha256(unit.text.encode()).hexdigest()
    if source_text_sha256 != EXPERIMENT_SOURCE_TEXT_SHA256:
        raise ValueError("source-unit text does not match the preregistration")
    if unit.input_sha256 != EXPERIMENT_UNIT_INPUT_SHA256:
        raise ValueError("source-unit identity does not match the preregistration")
    if (
        unit.unit_id != EXPERIMENT_UNIT_ID
        or unit.index != EXPERIMENT_UNIT_INDEX
        or unit.source_start != EXPERIMENT_UNIT_SOURCE_START
        or unit.source_end != EXPERIMENT_UNIT_SOURCE_END
    ):
        raise ValueError("source-unit location does not match the preregistration")
    if model_id != EXPERIMENT_MODEL_ID:
        raise ValueError("model does not match the preregistered experiment")
    prompt = whole_source_completeness_prompt(unit)
    policy = CompletenessExperimentPolicy(
        obligations=_FROZEN_OBLIGATIONS,
        diagnostics=_FROZEN_DIAGNOSTICS,
        model_id=model_id,
        source_sha256=unit.source_sha256,
        source_text_sha256=source_text_sha256,
        unit_input_sha256=unit.input_sha256,
        completeness_prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
        _authority=_POLICY_AUTHORITY,
    )
    if policy.manifest_sha256 != EXPECTED_COMPLETENESS_MANIFEST_SHA256:
        raise ValueError("completeness implementation changed after preregistration")
    return policy


@dataclass(frozen=True, slots=True)
class CompletenessExperimentEvidence:
    """Non-lossy five-call result plus exact receipt custody."""

    policy: CompletenessExperimentPolicy
    a_evidence: ThreeCallAgentRunEvidence
    c_output: SourceUnitCompletenessInventoryOutputV1
    c_result: SourceUnitCompletenessResult
    c_raw_output: dict[str, object]
    c_verification_output: SourceUnitVerificationOutput
    c_verified_events: tuple[VerifiedEventCandidate, ...]
    c_verification_raw_output: dict[str, object]
    records: tuple[ModelAttemptAuditRecord, ...]
    receipts: ProviderReceiptVerification
    comparison: PairedCompletenessResult
    evidence_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if tuple(record.attempt_role for record in self.records) != EXPECTED_ROLES:
            raise ValueError("experiment records do not match the five frozen roles")
        response_ids = tuple(record.provider_response_id for record in self.records)
        if any(response_id is None for response_id in response_ids) or len(
            set(response_ids)
        ) != len(response_ids):
            raise ValueError("experiment requires five distinct provider responses")
        _require_exact_receipts(self.receipts, records=self.records)
        object.__setattr__(
            self,
            "evidence_sha256",
            canonical_json_sha256(
                {
                    "policy": self.policy.as_json(),
                    "a_evidence_sha256": self.a_evidence.evidence_sha256,
                    "c_raw_output": self.c_raw_output,
                    "c_envelope_sha256": self.c_result.envelope_sha256,
                    "c_verification_raw_output": self.c_verification_raw_output,
                    "records": [record.as_json() for record in self.records],
                    "receipts": self.receipts.as_json(),
                    "comparison": self.comparison.as_json(),
                }
            ),
        )


async def execute_completeness_experiment(  # noqa: PLR0913
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
    policy: CompletenessExperimentPolicy,
    journal_path: Path,
) -> CompletenessExperimentEvidence:
    """Run A, C, and C verification with no retry or semantic repair."""

    return await _execute_completeness_experiment_with_receipt_verifier(
        client=client,
        tenant=tenant,
        model_id=model_id,
        execution_namespace=execution_namespace,
        unit=unit,
        policy=policy,
        journal_path=journal_path,
        receipt_verifier=_ISSUED_RECEIPT_VERIFIER,
    )


async def _execute_completeness_experiment_with_receipt_verifier(  # noqa: PLR0913
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
    policy: CompletenessExperimentPolicy,
    journal_path: Path,
    receipt_verifier: _ReceiptVerifier,
) -> CompletenessExperimentEvidence:
    """Internal boundary used to test orchestration without provider I/O."""

    expected_policy = issue_completeness_experiment_policy(
        unit=unit,
        model_id=model_id,
    )
    if (
        policy != expected_policy
        or policy.manifest_sha256 != expected_policy.manifest_sha256
    ):
        raise CompletenessExperimentGateError(
            "experiment policy does not match the issued preregistration"
        )
    reservation = _experiment_reservation(
        policy=policy,
        model_id=model_id,
        execution_namespace=execution_namespace,
        unit=unit,
    )
    journal = CompletenessExperimentJournal.reserve(
        path=journal_path,
        reservation=reservation,
    )
    try:
        return await _execute_completeness_experiment(
            client=client,
            tenant=tenant,
            model_id=model_id,
            execution_namespace=execution_namespace,
            unit=unit,
            policy=policy,
            journal=journal,
            receipt_verifier=receipt_verifier,
        )
    except BaseException as exc:  # noqa: BLE001 - seal custody before propagation.
        _record_terminal_failure(
            journal=journal,
            policy=policy,
            unit=unit,
            error=exc,
        )
        raise


async def _execute_completeness_experiment(  # noqa: PLR0913
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
    policy: CompletenessExperimentPolicy,
    journal: CompletenessExperimentJournal,
    receipt_verifier: _ReceiptVerifier,
) -> CompletenessExperimentEvidence:
    """Execute against an already-reserved create-once journal."""

    execution_model_id = _execution_model_id(model_id)
    a_evidence = await execute_v13_v3_source_unit_agents(
        client=client,
        tenant=tenant,
        model_id=execution_model_id,
        execution_namespace=execution_namespace,
        unit=unit,
        audit_evidence_unit_id=unit.unit_id,
    )
    if not (
        has_locally_consistent_v13_v3_execution(a_evidence)
        and a_evidence.local_review_passed
        and a_evidence.normalized_result is not None
        and a_evidence.review_result is not None
    ):
        _persist_checkpoint(
            journal,
            stage="A_EXECUTION_FAILED",
            payload={
                "policy_manifest_sha256": policy.manifest_sha256,
                "a_evidence_sha256": a_evidence.evidence_sha256,
                "records": [record.as_json() for record in a_evidence.records],
                "error_type": a_evidence.error_type,
                "failed_stage": a_evidence.failed_stage,
            },
        )
        raise CompletenessExperimentGateError(
            "A failed local execution; C was not authorized"
        )
    a_receipts = receipt_verifier(
        records=a_evidence.records,
        model_id=model_id,
    )
    _require_exact_receipts(a_receipts, records=a_evidence.records)
    _persist_checkpoint(
        journal,
        stage="A_VERIFIED",
        payload={
            "policy_manifest_sha256": policy.manifest_sha256,
            "a_evidence_sha256": a_evidence.evidence_sha256,
            "a_raw_outputs": {
                "primary": a_evidence.original_raw_output,
                "structure_normalization": a_evidence.normalized_raw_output,
                "normalized_review": a_evidence.review_raw_output,
            },
            "records": [record.as_json() for record in a_evidence.records],
            "receipts": a_receipts.as_json(),
        },
    )

    contract_namespace = fingerprinted_step_key(
        policy.contract_version,
        policy.manifest_sha256,
        execution_namespace,
    )
    _persist_checkpoint(
        journal,
        stage="C_INVENTORY_CALL_AUTHORIZED",
        payload={
            "policy_manifest_sha256": policy.manifest_sha256,
            "attempt_role": "whole_source_completeness",
            "call_number": 4,
        },
    )
    c_audit = start_model_attempt_audit(
        evidence_unit_id=unit.unit_id,
        execution_contract_version=policy.contract_version,
    )
    try:
        c_call = await inventory_source_unit_completeness(
            client=client,
            tenant=tenant,
            model_id=execution_model_id,
            execution_namespace=contract_namespace,
            unit=unit,
        )
        c_receipts = receipt_verifier(
            records=(c_call.attempt_record,),
            model_id=model_id,
        )
        _require_exact_receipts(
            c_receipts,
            records=(c_call.attempt_record,),
        )
        _persist_checkpoint(
            journal,
            stage="C_INVENTORY_VERIFIED",
            payload={
                "policy_manifest_sha256": policy.manifest_sha256,
                "c_raw_output": c_call.raw_output,
                "c_envelope_sha256": c_call.value.envelope_sha256,
                "record": c_call.attempt_record.as_json(),
                "receipt": c_receipts.as_json(),
            },
        )

        _persist_checkpoint(
            journal,
            stage="C_VERIFICATION_CALL_AUTHORIZED",
            payload={
                "policy_manifest_sha256": policy.manifest_sha256,
                "attempt_role": "whole_source_completeness_verification",
                "call_number": 5,
                "c_envelope_sha256": c_call.value.envelope_sha256,
            },
        )
        verification_call = await verify_completeness_inventory(
            client=client,
            tenant=tenant,
            model_id=execution_model_id,
            execution_namespace=contract_namespace,
            unit=unit,
            candidates=c_call.value.accepted,
        )
        verification_receipts = receipt_verifier(
            records=(verification_call.attempt_record,),
            model_id=model_id,
        )
        _require_exact_receipts(
            verification_receipts,
            records=(verification_call.attempt_record,),
        )
        _persist_checkpoint(
            journal,
            stage="C_VERIFICATION_VERIFIED",
            payload={
                "policy_manifest_sha256": policy.manifest_sha256,
                "c_verification_raw_output": verification_call.raw_output,
                "record": verification_call.attempt_record.as_json(),
                "receipt": verification_receipts.as_json(),
            },
        )
    except BaseException as exc:  # noqa: BLE001 - preserve interrupted call intent.
        _persist_checkpoint(
            journal,
            stage="C_EXECUTION_FAILED",
            payload={
                "policy_manifest_sha256": policy.manifest_sha256,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "records": [record.as_json() for record in c_audit.records],
            },
        )
        raise
    finally:
        stop_model_attempt_audit(c_audit)

    if tuple(c_audit.records) != (
        c_call.attempt_record,
        verification_call.attempt_record,
    ):
        raise CompletenessExperimentGateError(
            "C audit did not contain exactly two ordered calls"
        )
    records = (*a_evidence.records, *c_audit.records)
    receipts = _combine_receipts(
        a_receipts,
        c_receipts,
        verification_receipts,
        records=records,
    )
    c_arm = VerifiedCompletenessArm(
        completeness=c_call.value,
        verification_output=verification_call.parsed,
        verified_events=verification_call.value,
    )
    comparison = compare_completeness_arms(
        a_normalization=a_evidence.normalized_result,
        a_review=a_evidence.review_result,
        c_arm=c_arm,
        obligations=policy.obligations,
        diagnostics=policy.diagnostics,
    )
    evidence = CompletenessExperimentEvidence(
        policy=policy,
        a_evidence=a_evidence,
        c_output=c_call.parsed,
        c_result=c_call.value,
        c_raw_output=c_call.raw_output,
        c_verification_output=verification_call.parsed,
        c_verified_events=verification_call.value,
        c_verification_raw_output=verification_call.raw_output,
        records=records,
        receipts=receipts,
        comparison=comparison,
    )
    terminal_payload: dict[str, object] = {
        "policy_manifest_sha256": policy.manifest_sha256,
        "evidence_sha256": evidence.evidence_sha256,
        "decision": comparison.decision.value,
        "a_evidence_sha256": a_evidence.evidence_sha256,
        "c_raw_output": c_call.raw_output,
        "c_verification_raw_output": verification_call.raw_output,
        "records": [record.as_json() for record in records],
        "receipts": receipts.as_json(),
        "comparison": comparison.as_json(),
    }
    acknowledgement = journal.record_terminal_success(
        stage="EXPERIMENT_COMPLETE",
        payload=terminal_payload,
    )
    if not acknowledgement.proves(
        stage="EXPERIMENT_COMPLETE",
        payload=terminal_payload,
    ):
        raise CompletenessExperimentGateError(
            "successful experiment result was not durably acknowledged"
        )
    return evidence


def _verify_attempt_receipts(
    *,
    records: tuple[ModelAttemptAuditRecord, ...],
    model_id: str,
) -> ProviderReceiptVerification:
    expectations = tuple(
        receipt_expectation_from_attempt(
            case_id=record.semantic_unit_id or "unknown-source-unit",
            report_model_id=model_id,
            record=record.as_json(),
            expected_output_schema_sha256=output_schema_json_sha256(
                _schema_for_role(record.attempt_role)
            ),
        )
        for record in records
    )
    return verify_provider_receipts(
        expectations,
        OpenAIProviderReceiptVerifier.from_environment(),
    )


_ISSUED_RECEIPT_VERIFIER: Final = _verify_attempt_receipts


def _execution_model_id(report_model_id: str) -> str:
    if report_model_id != EXPERIMENT_MODEL_ID:
        raise CompletenessExperimentGateError(
            "experiment report model does not match the issued model"
        )
    return EXPERIMENT_EXECUTION_MODEL_ID


def _require_exact_receipts(
    receipts: ProviderReceiptVerification,
    *,
    records: tuple[ModelAttemptAuditRecord, ...],
) -> None:
    expected_count = len(records)
    if not (
        receipts.gate_passed
        and receipts.expected_count == expected_count
        and len(receipts.receipts) == expected_count
    ):
        raise CompletenessExperimentGateError(
            "provider receipts did not verify exact output custody"
        )
    for record, receipt in zip(records, receipts.receipts, strict=True):
        expected_schema = _schema_for_role(record.attempt_role)
        expected_schema_sha256 = output_schema_json_sha256(expected_schema)
        expected_schema_identity = (
            f"{expected_schema.__module__}.{expected_schema.__qualname__}"
        )
        if not (
            record.replayed is False
            and record.provider_response_id is not None
            and record.provider_output_sha256 is not None
            and record.kernel_run_id is not None
            and record.payload_sha256 is not None
            and record.output_schema_identity == expected_schema_identity
            and receipt.status == "verified_live"
            and receipt.failure == "none"
            and receipt.error_type is None
            and receipt.response_id == record.provider_response_id
            and receipt.expected_model_id
            == canonical_provider_model_id(record.model_id)
            and receipt.retrieved_model_id == receipt.expected_model_id
            and receipt.expected_output_sha256 == record.provider_output_sha256
            and receipt.retrieved_output_sha256 == receipt.expected_output_sha256
            and receipt.provider_output_hash_matched
            and receipt.provider_output_verification_source == "exact_provider_output"
            and receipt.expected_payload_sha256 == record.payload_sha256
            and receipt.retrieved_payload_sha256 == receipt.expected_payload_sha256
            and receipt.expected_prompt_sha256 == record.prompt_sha256
            and receipt.retrieved_prompt_sha256 == receipt.expected_prompt_sha256
            and receipt.expected_invocation_id == record.invocation_id
            and receipt.retrieved_invocation_id == receipt.expected_invocation_id
            and receipt.expected_kernel_run_id == record.kernel_run_id
            and receipt.retrieved_kernel_run_id == receipt.expected_kernel_run_id
            and receipt.expected_source_sha256 == record.source_sha256
            and receipt.retrieved_source_sha256 == receipt.expected_source_sha256
            and receipt.expected_input_sha256 == record.input_sha256
            and receipt.retrieved_input_sha256 == receipt.expected_input_sha256
            and receipt.expected_evidence_unit_sha256 == record.evidence_unit_sha256
            and receipt.retrieved_evidence_unit_sha256
            == receipt.expected_evidence_unit_sha256
            and receipt.expected_output_schema_sha256 == expected_schema_sha256
            and receipt.retrieved_output_schema_sha256
            == receipt.expected_output_schema_sha256
            and receipt.provider_status == "completed"
            and receipt.response_completed_verified
            and receipt.incomplete_details_absent
            and receipt.standalone_context_verified
            and receipt.input_topology_verified
            and receipt.invocation_topology_supported
            and receipt.invocation_topology_verified
        ):
            raise CompletenessExperimentGateError(
                "provider receipt identity did not match its audited attempt"
            )


def _schema_for_role(role: str) -> type[BaseModel]:
    schemas: dict[str, type[BaseModel]] = {
        "primary": SourceUnitExtractionOutput,
        "structure_normalization": SourceUnitNormalizationOutputV13,
        "normalized_review": SourceUnitNormalizedReviewOutputV13V6,
        "whole_source_completeness": SourceUnitCompletenessInventoryOutputV1,
        "whole_source_completeness_verification": SourceUnitVerificationOutput,
    }
    try:
        schema = schemas[role]
    except KeyError as exc:
        raise CompletenessExperimentGateError(
            f"unexpected audited attempt role: {role}"
        ) from exc
    return schema


def _persist_checkpoint(
    journal: CompletenessExperimentJournal,
    *,
    stage: str,
    payload: dict[str, object],
) -> None:
    acknowledgement = journal.append_stage(stage=stage, payload=payload)
    if not acknowledgement.proves(stage=stage, payload=payload):
        raise CompletenessExperimentGateError(
            f"{stage} checkpoint was not durably acknowledged"
        )


def _experiment_reservation(
    *,
    policy: CompletenessExperimentPolicy,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
) -> dict[str, object]:
    return {
        "contract_version": policy.contract_version,
        "policy_manifest_sha256": policy.manifest_sha256,
        "model_id": model_id,
        "execution_namespace_sha256": hashlib.sha256(
            execution_namespace.encode()
        ).hexdigest(),
        "unit_id": unit.unit_id,
        "unit_index": unit.index,
        "unit_source_start": unit.source_start,
        "unit_source_end": unit.source_end,
        "unit_source_sha256": unit.source_sha256,
        "unit_input_sha256": unit.input_sha256,
    }


def _record_terminal_failure(
    *,
    journal: CompletenessExperimentJournal,
    policy: CompletenessExperimentPolicy,
    unit: FrozenSourceUnit,
    error: BaseException,
) -> None:
    journal.record_terminal_failure(
        stage="EXPERIMENT_FAILED",
        error_type=type(error).__name__,
        error_message=str(error),
        evidence={
            "policy_manifest_sha256": policy.manifest_sha256,
            "unit_id": unit.unit_id,
            "unit_input_sha256": unit.input_sha256,
        },
    )


def _combine_receipts(
    *groups: ProviderReceiptVerification,
    records: tuple[ModelAttemptAuditRecord, ...],
) -> ProviderReceiptVerification:
    receipts = tuple(receipt for group in groups for receipt in group.receipts)
    combined = ProviderReceiptVerification(
        status=(
            "verified_live"
            if all(group.status == "verified_live" for group in groups)
            else "mismatched"
        ),
        expected_count=sum(group.expected_count for group in groups),
        verified_count=sum(group.verified_count for group in groups),
        receipts=receipts,
    )
    _require_exact_receipts(combined, records=records)
    return combined


__all__ = [
    "CompletenessExperimentEvidence",
    "CompletenessExperimentGateError",
    "CompletenessExperimentPolicy",
    "EXPECTED_ROLES",
    "EXPECTED_COMPLETENESS_MANIFEST_SHA256",
    "EXPERIMENT_EXECUTION_MODEL_ID",
    "EXPERIMENT_CONTRACT_VERSION",
    "EXPERIMENT_MODEL_ID",
    "EXPERIMENT_SOURCE_SHA256",
    "EXPERIMENT_SOURCE_TEXT_SHA256",
    "EXPERIMENT_UNIT_INPUT_SHA256",
    "EXPERIMENT_UNIT_ID",
    "EXPERIMENT_UNIT_INDEX",
    "EXPERIMENT_UNIT_SOURCE_END",
    "EXPERIMENT_UNIT_SOURCE_START",
    "METRIC_VERSION",
    "execute_completeness_experiment",
    "issue_completeness_experiment_policy",
]
