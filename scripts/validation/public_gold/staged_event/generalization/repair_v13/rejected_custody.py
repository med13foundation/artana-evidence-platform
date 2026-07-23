"""Exclusive V13 custody for rejected or invalid completed provider calls."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    StageCustodyRecord,
    write_json_exclusive,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

    from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
        StageCustodyInput,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
        CaseExecutionPaths,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v13.provider_execution import (
        V13ProviderExecutionError,
    )


class V13RejectedCustodyError(RuntimeError):
    """Rejected V13 evidence could not be persisted without overwriting data."""


@dataclass(frozen=True, slots=True)
class V13RejectedCustodyRecord:
    """Hashes binding the three normal-path rejected custody artifacts."""

    bundle_sha256: str
    receipt_sha256: str
    raw_output_sha256: str

    def as_json(self) -> dict[str, object]:
        return {
            "bundle_sha256": self.bundle_sha256,
            "receipt_sha256": self.receipt_sha256,
            "raw_output_sha256": self.raw_output_sha256,
        }


def persist_admitted_custody(
    *,
    custody_input: StageCustodyInput,
    output: BaseModel,
    canonical_payload: dict[str, object],
    receipt: dict[str, object],
) -> StageCustodyRecord:
    """Exclusively persist one admitted V13 call after complete prevalidation."""

    identity = receipt.get("identity")
    response_id = identity.get("response_id") if isinstance(identity, dict) else None
    if not isinstance(response_id, str) or not response_id:
        raise V13RejectedCustodyError("admitted receipt response ID is absent")
    budgets = receipt.get("budgets")
    if not isinstance(budgets, dict):
        raise V13RejectedCustodyError("admitted receipt budgets are absent")
    output_payload = output.model_dump(mode="json")
    if output_payload != canonical_payload:
        raise V13RejectedCustodyError(
            "typed output differs from canonical provider payload"
        )
    provider_input_sha256 = _sha256_text(custody_input.provider_input)
    output_sha256 = _canonical_sha256(canonical_payload)
    try:
        receipt_sha256 = write_json_exclusive(
            custody_input.paths.receipt,
            receipt,
        )
        raw_output_sha256 = write_json_exclusive(
            custody_input.paths.raw_output,
            output_payload,
        )
        bundle = {
            "stage": custody_input.stage,
            "response_id": response_id,
            "provider_input_sha256": provider_input_sha256,
            "output_sha256": output_sha256,
            "schema_sha256": custody_input.schema_sha256,
            "requested_and_observed_budgets": budgets,
            "receipt": receipt,
            "typed_output": canonical_payload,
            "receipt_sha256": receipt_sha256,
            "raw_output_sha256": raw_output_sha256,
        }
        bundle_sha256 = write_json_exclusive(
            custody_input.paths.bundle,
            bundle,
        )
    except Exception as exc:  # noqa: BLE001 - caller seals a custody failure.
        raise V13RejectedCustodyError(
            f"admitted V13 custody persistence failed: {type(exc).__name__}: {exc}"
        ) from exc
    return StageCustodyRecord(
        stage=custody_input.stage,
        response_id=response_id,
        provider_input_sha256=provider_input_sha256,
        output_sha256=output_sha256,
        schema_sha256=custody_input.schema_sha256,
        bundle_sha256=bundle_sha256,
        receipt_sha256=receipt_sha256,
        raw_output_sha256=raw_output_sha256,
    )


def persist_rejected_custody(
    *,
    paths: CaseExecutionPaths,
    stage: str,
    provider_input: str,
    schema_sha256: str,
    error: V13ProviderExecutionError,
) -> V13RejectedCustodyRecord:
    """Persist every available rejected-call envelope at the normal case paths."""

    evidence = error.evidence
    receipt = {
        "schema_version": "artana.staged_generalization.v13_rejected_receipt.v1",
        "status": "REJECTED_UNADMITTED",
        "stage": stage,
        "failure_stage": error.stage,
        "root_cause": error.root_cause,
        "provider_input_sha256": _sha256_text(provider_input),
        "schema_sha256": schema_sha256,
        "transport_evidence": evidence.as_json(),
        "diagnostics": error.diagnostics,
        "scientific_admission": False,
        "usage_affects_scientific_scoring": False,
        "provider_fallback_used": False,
    }
    raw_output = {
        "schema_version": ("artana.staged_generalization.v13_rejected_raw_output.v1"),
        "status": "REJECTED_UNADMITTED",
        "failure_stage": error.stage,
        "canonical_payload_available": evidence.canonical_payload is not None,
        "canonical_payload": evidence.canonical_payload,
    }
    try:
        receipt_sha256 = write_json_exclusive(paths.receipt, receipt)
        raw_output_sha256 = write_json_exclusive(paths.raw_output, raw_output)
        bundle = {
            "schema_version": ("artana.staged_generalization.v13_rejected_custody.v1"),
            "status": "REJECTED_UNADMITTED",
            "stage": stage,
            "failure_stage": error.stage,
            "root_cause": error.root_cause,
            "response_ids": list(evidence.response_ids),
            "provider_input_sha256": _sha256_text(provider_input),
            "schema_sha256": schema_sha256,
            "receipt_sha256": receipt_sha256,
            "raw_output_sha256": raw_output_sha256,
            "usage_accounting_status": evidence.usage_accounting_status,
            "scientific_admission": False,
            "receipt_path": str(paths.receipt),
            "raw_output_path": str(paths.raw_output),
        }
        bundle_sha256 = write_json_exclusive(paths.bundle, bundle)
    except Exception as exc:  # noqa: BLE001 - caller seals a custody failure.
        raise V13RejectedCustodyError(
            f"rejected V13 custody persistence failed: {type(exc).__name__}: {exc}"
        ) from exc
    return V13RejectedCustodyRecord(
        bundle_sha256=bundle_sha256,
        receipt_sha256=receipt_sha256,
        raw_output_sha256=raw_output_sha256,
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "V13RejectedCustodyError",
    "V13RejectedCustodyRecord",
    "persist_admitted_custody",
    "persist_rejected_custody",
]
