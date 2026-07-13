"""Producer authentication for frozen ranking-calibration protocols."""

from __future__ import annotations

import hashlib
import hmac
import json
import os

from artana_evidence_api.evidence_selection.ranking.contracts import (
    ReviewRankingCalibrationProtocol,
)

_SIGNING_KEY_ENV = "ARTANA_EVIDENCE_SHADOW_REVIEW_PACKET_SIGNING_KEY"
_SIGNATURE_CONTEXT = b"artana-evidence-ranking-calibration-protocol.v1\x00"
_MIN_SIGNING_KEY_BYTES = 32


def calibration_protocol_digest(protocol: ReviewRankingCalibrationProtocol) -> str:
    """Return the canonical digest of producer-owned protocol fields."""

    payload = protocol.model_dump(
        mode="json",
        exclude={"producer_signature"},
    )
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def authenticate_calibration_protocol(
    protocol: ReviewRankingCalibrationProtocol,
) -> ReviewRankingCalibrationProtocol:
    """Return a protocol signed by the trusted machine-packet producer."""

    signature = _protocol_signature(protocol)
    return protocol.model_copy(update={"producer_signature": signature})


def verify_calibration_protocol_signature(
    protocol: ReviewRankingCalibrationProtocol,
) -> None:
    """Fail closed unless the frozen protocol has a valid producer signature."""

    signature = protocol.producer_signature
    if signature is None:
        msg = "Calibration protocol is missing its producer signature."
        raise ValueError(msg)
    expected = _protocol_signature(protocol)
    if not hmac.compare_digest(signature, expected):
        msg = "Calibration protocol producer signature does not match its contents."
        raise ValueError(msg)


def _protocol_signature(protocol: ReviewRankingCalibrationProtocol) -> str:
    return hmac.new(
        _signing_key(),
        _SIGNATURE_CONTEXT + calibration_protocol_digest(protocol).encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def _signing_key() -> bytes:
    value = os.getenv(_SIGNING_KEY_ENV, "").strip()
    if value == "":
        msg = (
            f"{_SIGNING_KEY_ENV} must be set to authenticate a production "
            "ranking-calibration protocol."
        )
        raise ValueError(msg)
    encoded = value.encode("utf-8")
    if len(encoded) < _MIN_SIGNING_KEY_BYTES:
        msg = (
            f"{_SIGNING_KEY_ENV} must contain at least "
            f"{_MIN_SIGNING_KEY_BYTES} bytes."
        )
        raise ValueError(msg)
    return encoded


__all__ = [
    "authenticate_calibration_protocol",
    "calibration_protocol_digest",
    "verify_calibration_protocol_signature",
]
