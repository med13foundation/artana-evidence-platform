"""Fail-closed classification of provider background response states."""

from __future__ import annotations

from typing import Literal

from scripts.validation.provider_receipt_boundary.canonical_payload import (
    canonical_sha256,
)
from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
)

BackgroundDisposition = Literal["PENDING", "COMPLETED"]
PENDING_STATUSES = frozenset({"queued", "in_progress"})
FAILED_STATUSES = frozenset({"failed", "cancelled", "incomplete"})


def classify_background_status(response: dict[str, object]) -> BackgroundDisposition:
    status = response.get("status")
    if status in PENDING_STATUSES:
        return "PENDING"
    if status == "completed":
        if response.get("error") is not None:
            raise _terminal_error(response, "completed response contains an error")
        if response.get("incomplete_details") is not None:
            raise _terminal_error(
                response,
                "completed response contains incomplete details",
            )
        return "COMPLETED"
    if status in FAILED_STATUSES:
        raise _terminal_error(response, f"provider reached terminal status {status}")
    raise ProviderExecutionError(
        "BACKGROUND_UNKNOWN_STATUS",
        "provider returned an unknown background status",
        diagnostics={
            "status_sha256": canonical_sha256(status),
        },
    )


def _terminal_error(
    response: dict[str, object], root_cause: str
) -> ProviderExecutionError:
    return ProviderExecutionError(
        "BACKGROUND_TERMINAL_FAILURE",
        root_cause,
        diagnostics={
            "status": response.get("status"),
            "error_sha256": canonical_sha256(response.get("error")),
            "incomplete_details_sha256": canonical_sha256(
                response.get("incomplete_details")
            ),
        },
    )


__all__ = [
    "FAILED_STATUSES",
    "PENDING_STATUSES",
    "BackgroundDisposition",
    "classify_background_status",
]
