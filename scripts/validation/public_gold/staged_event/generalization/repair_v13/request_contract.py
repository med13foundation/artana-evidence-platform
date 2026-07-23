"""V13-local contract for one direct foreground provider request."""

from __future__ import annotations

from dataclasses import dataclass

from scripts.validation.provider_receipt_boundary.contracts import (
    TelemetryReceiptExpectationsV2,
)


@dataclass(frozen=True, slots=True)
class V13ForegroundProviderRequest:
    """A foreground request with record-only telemetry and no token ceiling."""

    provider_input: str
    provider_format: dict[str, object]
    provider_model_id: str
    reasoning_effort: str
    pricing: dict[str, float]
    metadata: dict[str, str]

    def receipt_expectations(self) -> TelemetryReceiptExpectationsV2:
        return TelemetryReceiptExpectationsV2(
            provider_input=self.provider_input,
            provider_format=self.provider_format,
            provider_model_id=self.provider_model_id,
            reasoning_effort=self.reasoning_effort,
            metadata=self.metadata,
            pricing=self.pricing,
        )


__all__ = ["V13ForegroundProviderRequest"]
