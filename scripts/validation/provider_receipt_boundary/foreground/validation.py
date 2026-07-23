"""Foreground-specific receipt policy with confirmation-authoritative usage."""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass

from scripts.validation.provider_receipt_boundary import (
    TelemetryReceiptExpectationsV2,
    UsageAccounting,
    validate_provider_receipt_telemetry_v2,
)
from scripts.validation.provider_receipt_boundary.canonical_payload import (
    canonical_sha256,
)


@dataclass(frozen=True, slots=True)
class ForegroundTelemetryValidationV3:
    """Verified scientific custody plus record-only foreground usage."""

    usage: UsageAccounting
    receipt: dict[str, object]


def validate_foreground_provider_receipt_telemetry_v3(
    *,
    creation: dict[str, object],
    confirmation: dict[str, object],
    input_items: tuple[dict[str, object], ...],
    expectations: TelemetryReceiptExpectationsV2,
    latency_seconds: float,
) -> ForegroundTelemetryValidationV3:
    """Validate immutable custody while allowing usage snapshot convergence."""

    creation_usage = creation.get("usage")
    confirmation_usage = confirmation.get("usage")
    if not isinstance(creation_usage, dict) or not isinstance(
        confirmation_usage,
        dict,
    ):
        normalized_creation = creation
    else:
        normalized_creation = copy.deepcopy(creation)
        normalized_creation["usage"] = copy.deepcopy(confirmation_usage)
    validation = validate_provider_receipt_telemetry_v2(
        creation=normalized_creation,
        retrieval=confirmation,
        input_items=input_items,
        expectations=expectations,
        latency_seconds=latency_seconds,
    )
    receipt = validation.as_json()
    raw_differences = receipt.get("differences")
    if not isinstance(raw_differences, list | tuple):
        raise TypeError("validated foreground differences are malformed")
    differences = list(raw_differences)
    receipt["differences"] = differences
    usage_changed = creation_usage != confirmation_usage
    if usage_changed:
        differences.append(
            {
                "path": "$.usage",
                "difference": "FOREGROUND_USAGE_SNAPSHOT_CHANGED",
                "creation_sha256": canonical_sha256(creation_usage),
                "retrieval_sha256": canonical_sha256(confirmation_usage),
                "allowlisted": True,
                "rationale": (
                    "usage is record-only telemetry and confirmation is the "
                    "authoritative completed snapshot"
                ),
            }
        )
    receipt.update(
        {
            "schema_version": (
                "artana.provider_receipt_boundary.foreground_telemetry.v3"
            ),
            "creation_envelope_sha256": canonical_sha256(creation),
            "retrieval_envelope_sha256": canonical_sha256(confirmation),
            "usage": asdict(validation.usage),
            "foreground_usage_policy": {
                "scientific_validity_dependency": False,
                "authoritative_snapshot": "CONFIRMATION_RETRIEVAL",
                "creation_usage_sha256": canonical_sha256(creation_usage),
                "confirmation_usage_sha256": canonical_sha256(
                    confirmation_usage
                ),
                "snapshots_differ": usage_changed,
            },
        }
    )
    return ForegroundTelemetryValidationV3(
        usage=validation.usage,
        receipt=receipt,
    )


__all__ = [
    "ForegroundTelemetryValidationV3",
    "validate_foreground_provider_receipt_telemetry_v3",
]
