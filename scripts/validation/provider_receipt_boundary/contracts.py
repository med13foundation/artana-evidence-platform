"""Typed evidence returned by provider receipt-boundary components."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class CanonicalPayload:
    payload: dict[str, object]
    sha256: str


@dataclass(frozen=True, slots=True)
class ReceiptIdentity:
    response_id: str
    object_type: str
    created_at: float
    model: str
    status: str
    output_items: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class FieldDifference:
    path: str
    difference: str
    creation_sha256: str
    retrieval_sha256: str
    allowlisted: bool
    rationale: str | None


@dataclass(frozen=True, slots=True)
class UsageAccounting:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    latency_seconds: float
    cost_usd: float


@dataclass(frozen=True, slots=True)
class BudgetAccounting:
    requested_max_output_tokens: int
    requested_max_total_tokens: int
    requested_max_latency_seconds: float
    requested_max_cost_usd: float
    observed_output_tokens: int
    observed_total_tokens: int
    observed_latency_seconds: float
    observed_cost_usd: float
    output_tokens: str
    total_tokens: str
    latency: str
    cost: str


@dataclass(frozen=True, slots=True)
class ReceiptExpectations:
    provider_input: str
    provider_format: dict[str, object]
    provider_model_id: str
    reasoning_effort: str
    metadata: dict[str, str]
    max_output_tokens: int
    max_total_tokens: int
    max_cost_usd: float
    max_latency_seconds: float
    pricing: dict[str, float]


@dataclass(frozen=True, slots=True)
class TelemetryReceiptExpectationsV2:
    """Scientific/custody expectations with record-only usage telemetry."""

    provider_input: str
    provider_format: dict[str, object]
    provider_model_id: str
    reasoning_effort: str
    metadata: dict[str, str]
    pricing: dict[str, float]


ReceiptExpectationsLike = ReceiptExpectations | TelemetryReceiptExpectationsV2


@dataclass(frozen=True, slots=True)
class ReceiptValidation:
    identity: ReceiptIdentity
    scientific_payload_sha256: str
    creation_envelope_sha256: str
    retrieval_envelope_sha256: str
    provider_input_sha256: str
    provider_schema_sha256: str
    differences: tuple[FieldDifference, ...]
    usage: UsageAccounting
    budgets: BudgetAccounting

    def as_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["status"] = "VERIFIED_LIVE"
        return payload


@dataclass(frozen=True, slots=True)
class TelemetryReceiptValidationV2:
    """Verified custody whose usage cannot affect scientific validity."""

    identity: ReceiptIdentity
    scientific_payload_sha256: str
    creation_envelope_sha256: str
    retrieval_envelope_sha256: str
    provider_input_sha256: str
    provider_schema_sha256: str
    differences: tuple[FieldDifference, ...]
    usage: UsageAccounting

    def as_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload.update(
            {
                "schema_version": (
                    "artana.provider_receipt_boundary.telemetry_only.v2"
                ),
                "status": "VERIFIED_LIVE",
                "token_and_cost_policy": "RECORD_ONLY_NOT_SCIENTIFIC_VALIDITY",
                "budgets": {
                    "policy": "RECORD_ONLY_NOT_PER_CALL_VALIDATION",
                    "requested_max_output_tokens": None,
                    "requested_max_total_tokens": None,
                    "requested_max_latency_seconds": None,
                    "requested_max_cost_usd": None,
                    "observed_output_tokens": self.usage.output_tokens,
                    "observed_total_tokens": self.usage.total_tokens,
                    "observed_latency_seconds": self.usage.latency_seconds,
                    "observed_cost_usd": self.usage.cost_usd,
                    "output_tokens": "RECORD_ONLY",
                    "total_tokens": "RECORD_ONLY",
                    "latency": "RECORD_ONLY",
                    "cost": "RECORD_ONLY",
                },
            }
        )
        return payload


__all__ = [
    "CanonicalPayload",
    "BudgetAccounting",
    "FieldDifference",
    "ReceiptIdentity",
    "ReceiptExpectations",
    "ReceiptExpectationsLike",
    "ReceiptValidation",
    "TelemetryReceiptExpectationsV2",
    "TelemetryReceiptValidationV2",
    "UsageAccounting",
]
