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
class ReceiptExpectations:
    provider_input: str
    provider_format: dict[str, object]
    provider_model_id: str
    reasoning_effort: str
    metadata: dict[str, str]
    max_total_tokens: int
    max_cost_usd: float
    max_latency_seconds: float
    pricing: dict[str, float]


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

    def as_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["status"] = "VERIFIED_LIVE"
        return payload


__all__ = [
    "CanonicalPayload",
    "FieldDifference",
    "ReceiptIdentity",
    "ReceiptExpectations",
    "ReceiptValidation",
    "UsageAccounting",
]
