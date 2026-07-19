"""Five-call visible experiment with receipt and durability stop gates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Protocol

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

from scripts.validation.claim_events.finite_source_unit.completeness.comparison import (
    ControlledEventObligation,
    PairedCompletenessResult,
    VerifiedCompletenessArm,
    compare_completeness_arms,
)
from scripts.validation.claim_events.finite_source_unit.completeness.contracts import (
    SourceUnitCompletenessInventoryOutputV1,
)
from scripts.validation.claim_events.finite_source_unit.completeness.prompts import (
    COMPLETENESS_PROMPT_VERSION,
    COMPLETENESS_VERIFICATION_PROMPT_VERSION,
)
from scripts.validation.claim_events.finite_source_unit.completeness.service import (
    SourceUnitCompletenessResult,
    inventory_source_unit_completeness,
)
from scripts.validation.claim_events.finite_source_unit.completeness.verification import (
    verify_completeness_inventory,
)
from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitVerificationOutput,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v13.execution import (
    V13_V3_EXECUTION_CONTRACT_VERSION,
    V13_V3_EXECUTION_MANIFEST_SHA256,
    execute_v13_v3_source_unit_agents,
    has_locally_consistent_v13_v3_execution,
)
from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    canonical_json_sha256,
)
from scripts.validation.claim_frames.provider_receipts import (
    ProviderReceiptVerification,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.llm_extraction.attempt_audit import (
        ModelAttemptAuditRecord,
    )

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

EXPERIMENT_CONTRACT_VERSION: Final = (
    "tg04.finite_source_unit.completeness_ab.v1"
)
METRIC_VERSION: Final = "tg04.localization_obligation_recovery.v1"
EXPECTED_ROLES: Final = (
    "primary",
    "structure_normalization",
    "normalized_review",
    "whole_source_completeness",
    "whole_source_completeness_verification",
)


class CompletenessExperimentGateError(RuntimeError):
    """A frozen safety or custody gate stopped the live experiment."""


class ReceiptGate(Protocol):
    def __call__(
        self,
        records: tuple[ModelAttemptAuditRecord, ...],
    ) -> ProviderReceiptVerification: ...


class CheckpointSink(Protocol):
    def __call__(self, stage: str, payload: dict[str, object]) -> str:
        """Durably persist payload and return its canonical SHA-256."""


@dataclass(frozen=True, slots=True)
class CompletenessExperimentPolicy:
    """Frozen semantic obligations and executable contract identity."""

    obligations: tuple[ControlledEventObligation, ...]
    contract_version: str = EXPERIMENT_CONTRACT_VERSION
    metric_version: str = METRIC_VERSION
    manifest_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.obligations:
            raise ValueError("completeness experiment requires frozen obligations")
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
            "a_contract_version": V13_V3_EXECUTION_CONTRACT_VERSION,
            "a_manifest_sha256": V13_V3_EXECUTION_MANIFEST_SHA256,
            "completeness_prompt_version": COMPLETENESS_PROMPT_VERSION,
            "completeness_schema_sha256": output_schema_json_sha256(
                SourceUnitCompletenessInventoryOutputV1
            ),
            "verification_prompt_version": (
                COMPLETENESS_VERIFICATION_PROMPT_VERSION
            ),
            "verification_schema_sha256": output_schema_json_sha256(
                SourceUnitVerificationOutput
            ),
            "expected_roles": EXPECTED_ROLES,
            "obligations": [
                {
                    "obligation_id": item.obligation_id,
                    "target_event_type": item.target_event_type.value,
                    "target_participant_span": item.target_participant_span,
                    "target_cue_span": item.target_cue_span,
                    "target_destination_span": item.target_destination_span,
                    "controller_event_type": item.controller_event_type.value,
                    "controller_cause_span": item.controller_cause_span,
                    "controller_cue_fragment": item.controller_cue_fragment,
                }
                for item in self.obligations
            ],
        }
        if include_manifest:
            payload["manifest_sha256"] = self.manifest_sha256
        return payload


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
        _require_exact_receipts(self.receipts, expected_count=len(self.records))
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
                    "comparison": {
                        "decision": self.comparison.decision.value,
                        "a_covered_obligations": (
                            self.comparison.a_covered_obligations
                        ),
                        "c_covered_obligations": (
                            self.comparison.c_covered_obligations
                        ),
                        "a_plus_c_covered_obligations": (
                            self.comparison.a_plus_c_covered_obligations
                        ),
                        "recovered_obligations": (
                            self.comparison.recovered_obligations
                        ),
                    },
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
    receipt_gate: ReceiptGate,
    checkpoint_sink: CheckpointSink,
) -> CompletenessExperimentEvidence:
    """Run A, C, and C verification with no retry or semantic repair."""

    a_evidence = await execute_v13_v3_source_unit_agents(
        client=client,
        tenant=tenant,
        model_id=model_id,
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
        raise CompletenessExperimentGateError(
            "A failed local execution; C was not authorized"
        )
    a_receipts = receipt_gate(a_evidence.records)
    _require_exact_receipts(a_receipts, expected_count=3)
    _persist_checkpoint(
        checkpoint_sink,
        stage="A_VERIFIED",
        payload={
            "policy_manifest_sha256": policy.manifest_sha256,
            "a_evidence_sha256": a_evidence.evidence_sha256,
            "receipts": a_receipts.as_json(),
        },
    )

    contract_namespace = fingerprinted_step_key(
        policy.contract_version,
        policy.manifest_sha256,
        execution_namespace,
    )
    c_audit = start_model_attempt_audit(
        evidence_unit_id=unit.unit_id,
        execution_contract_version=policy.contract_version,
    )
    try:
        c_call = await inventory_source_unit_completeness(
            client=client,
            tenant=tenant,
            model_id=model_id,
            execution_namespace=contract_namespace,
            unit=unit,
        )
        c_receipts = receipt_gate((c_call.attempt_record,))
        _require_exact_receipts(c_receipts, expected_count=1)
        _persist_checkpoint(
            checkpoint_sink,
            stage="C_INVENTORY_VERIFIED",
            payload={
                "policy_manifest_sha256": policy.manifest_sha256,
                "c_raw_output": c_call.raw_output,
                "c_envelope_sha256": c_call.value.envelope_sha256,
                "receipt": c_receipts.as_json(),
            },
        )

        verification_call = await verify_completeness_inventory(
            client=client,
            tenant=tenant,
            model_id=model_id,
            execution_namespace=contract_namespace,
            unit=unit,
            candidates=c_call.value.accepted,
        )
        verification_receipts = receipt_gate((verification_call.attempt_record,))
        _require_exact_receipts(verification_receipts, expected_count=1)
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
    _persist_checkpoint(
        checkpoint_sink,
        stage="EXPERIMENT_COMPLETE",
        payload={
            "policy_manifest_sha256": policy.manifest_sha256,
            "evidence_sha256": evidence.evidence_sha256,
            "decision": comparison.decision.value,
        },
    )
    return evidence


def _require_exact_receipts(
    receipts: ProviderReceiptVerification,
    *,
    expected_count: int,
) -> None:
    if not (
        receipts.gate_passed
        and receipts.expected_count == expected_count
        and len(receipts.receipts) == expected_count
        and all(
            receipt.provider_output_hash_matched
            and receipt.provider_output_verification_source == "exact_provider_output"
            for receipt in receipts.receipts
        )
    ):
        raise CompletenessExperimentGateError(
            "provider receipts did not verify exact output custody"
        )


def _persist_checkpoint(
    sink: CheckpointSink,
    *,
    stage: str,
    payload: dict[str, object],
) -> None:
    expected_sha256 = canonical_json_sha256(payload)
    if sink(stage, payload) != expected_sha256:
        raise CompletenessExperimentGateError(
            f"{stage} checkpoint was not durably acknowledged"
        )


def _combine_receipts(
    *groups: ProviderReceiptVerification,
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
    _require_exact_receipts(combined, expected_count=len(receipts))
    return combined


__all__ = [
    "CheckpointSink",
    "CompletenessExperimentEvidence",
    "CompletenessExperimentGateError",
    "CompletenessExperimentPolicy",
    "EXPECTED_ROLES",
    "EXPERIMENT_CONTRACT_VERSION",
    "METRIC_VERSION",
    "ReceiptGate",
    "execute_completeness_experiment",
]
