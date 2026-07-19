"""Fresh provider-receipt reconstruction at repeat finalization."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from scripts.validation.claim_frames.provider_receipts import (
    ProviderReceiptExpectation,
    ProviderReceiptVerification,
    ProviderReceiptVerifier,
)


@dataclass(frozen=True, slots=True)
class ReceiptReverificationContract:
    """Version-level requirements for final provider receipt custody."""

    label: str
    require_output_schema_custody: bool


def require_fresh_provider_receipts(
    report: dict[str, object],
    *,
    contract: ReceiptReverificationContract,
    verifier_factory: Callable[[], ProviderReceiptVerifier | None],
    verify: Callable[
        [Sequence[ProviderReceiptExpectation], ProviderReceiptVerifier | None],
        ProviderReceiptVerification,
    ],
    require_gate_passed: bool = True,
) -> None:
    """Re-retrieve provider evidence from stored, schema-bound expectations."""

    stored = report.get("provider_receipts")
    if not isinstance(stored, dict):
        raise TypeError(f"{contract.label} provider receipts are unavailable")
    receipt_items = stored.get("receipts")
    if not isinstance(receipt_items, list):
        raise TypeError(f"{contract.label} provider receipts are unavailable")
    expectations = tuple(
        _expectation_from_receipt(receipt, contract=contract)
        for receipt in receipt_items
    )
    fresh = verify(expectations, verifier_factory())
    if (require_gate_passed and not fresh.gate_passed) or fresh.as_json() != stored:
        raise RuntimeError(
            f"{contract.label} provider receipts failed independent live reverification"
        )


def _expectation_from_receipt(
    receipt: object,
    *,
    contract: ReceiptReverificationContract,
) -> ProviderReceiptExpectation:
    if not isinstance(receipt, dict):
        raise TypeError(f"{contract.label} provider receipt is invalid")
    payload_sha256 = receipt.get("expected_payload_sha256")
    schema_sha256 = receipt.get("expected_output_schema_sha256")
    if payload_sha256 is not None and not isinstance(payload_sha256, str):
        raise RuntimeError(f"{contract.label} provider payload identity is invalid")
    if schema_sha256 is not None and not isinstance(schema_sha256, str):
        raise RuntimeError(f"{contract.label} provider schema identity is invalid")
    if contract.require_output_schema_custody and not isinstance(schema_sha256, str):
        raise RuntimeError(f"{contract.label} provider schema identity is required")
    return ProviderReceiptExpectation(
        response_id=_string(receipt, "response_id", contract=contract),
        expected_case_id=_string(receipt, "expected_case_id", contract=contract),
        expected_model_id=_string(receipt, "expected_model_id", contract=contract),
        expected_output_sha256=_string(
            receipt, "expected_output_sha256", contract=contract
        ),
        expected_payload_sha256=payload_sha256,
        expected_prompt_sha256=_string(
            receipt, "expected_prompt_sha256", contract=contract
        ),
        expected_invocation_id=_string(
            receipt, "expected_invocation_id", contract=contract
        ),
        expected_kernel_run_id=_string(
            receipt, "expected_kernel_run_id", contract=contract
        ),
        expected_source_sha256=_string(
            receipt, "expected_source_sha256", contract=contract
        ),
        expected_input_sha256=_string(
            receipt, "expected_input_sha256", contract=contract
        ),
        expected_evidence_unit_sha256=_string(
            receipt, "expected_evidence_unit_sha256", contract=contract
        ),
        expected_output_schema_sha256=schema_sha256,
    )


def _string(
    value: dict[object, object],
    key: str,
    *,
    contract: ReceiptReverificationContract,
) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise TypeError(f"{contract.label} {key} must be a string")
    return item


__all__ = ["ReceiptReverificationContract", "require_fresh_provider_receipts"]
