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

    normalized_creation = copy.deepcopy(creation)
    transport_differences = _normalize_foreground_transport(
        normalized_creation,
        confirmation,
    )
    creation_usage = creation.get("usage")
    confirmation_usage = confirmation.get("usage")
    if isinstance(creation_usage, dict) and isinstance(
        confirmation_usage,
        dict,
    ):
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
    differences.extend(transport_differences)
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


def _normalize_foreground_transport(
    creation: dict[str, object],
    confirmation: dict[str, object],
) -> list[dict[str, object]]:
    creation_output = creation.get("output")
    confirmation_output = confirmation.get("output")
    if not isinstance(creation_output, list) or not isinstance(
        confirmation_output,
        list,
    ):
        return []
    differences: list[dict[str, object]] = []
    for index, creation_item in enumerate(creation_output):
        if index >= len(confirmation_output):
            continue
        confirmation_item = confirmation_output[index]
        if not isinstance(creation_item, dict) or not isinstance(
            confirmation_item,
            dict,
        ):
            continue
        if (
            creation_item.get("type") != "reasoning"
            or confirmation_item.get("type") != "reasoning"
            or "encrypted_content" not in creation_item
            or "encrypted_content" in confirmation_item
        ):
            continue
        encrypted_content = creation_item.pop("encrypted_content")
        differences.append(
            {
                "path": f"$.output[{index}].encrypted_content",
                "difference": "OMITTED_ON_CONFIRMATION_RETRIEVAL",
                "creation_sha256": canonical_sha256(encrypted_content),
                "retrieval_sha256": canonical_sha256(
                    {"presence": "MISSING"}
                ),
                "allowlisted": True,
                "rationale": (
                    "foreground creation may include opaque encrypted reasoning "
                    "transport content that confirmation retrieval omits; the "
                    "reasoning item identity and scientific payload remain exact"
                ),
            }
        )
    return differences


__all__ = [
    "ForegroundTelemetryValidationV3",
    "validate_foreground_provider_receipt_telemetry_v3",
]
