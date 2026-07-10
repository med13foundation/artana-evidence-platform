"""Authenticate machine-owned shadow-review packet contents."""

from __future__ import annotations

import hashlib
import hmac
import os

_MACHINE_PACKET_SIGNING_KEY_ENV = "ARTANA_EVIDENCE_SHADOW_REVIEW_PACKET_SIGNING_KEY"
_MACHINE_PACKET_SIGNATURE_CONTEXT = b"artana-evidence-shadow-review-packet.v1\x00"


def sign_machine_packet_digest(digest: str) -> str:
    """Return a keyed signature for one machine-packet digest.

    The signing key belongs to the packet producer, not the human reviewer.
    A bare digest detects corruption but cannot establish that a machine
    artifact was not replaced with a new self-consistent packet.
    """

    return hmac.new(
        _signing_key(),
        _MACHINE_PACKET_SIGNATURE_CONTEXT + digest.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def verify_machine_packet_signature(*, digest: str, signature: str) -> None:
    """Fail closed unless a machine-packet signature matches its digest."""

    expected_signature = sign_machine_packet_digest(digest)
    if not hmac.compare_digest(signature, expected_signature):
        msg = "Machine packet signature does not match the producer-signed digest."
        raise ValueError(msg)


def _signing_key() -> bytes:
    value = os.getenv(_MACHINE_PACKET_SIGNING_KEY_ENV, "").strip()
    if value == "":
        msg = (
            f"{_MACHINE_PACKET_SIGNING_KEY_ENV} must be set to create or "
            "validate a trusted shadow-review packet."
        )
        raise ValueError(msg)
    return value.encode("utf-8")


__all__ = [
    "sign_machine_packet_digest",
    "verify_machine_packet_signature",
]
