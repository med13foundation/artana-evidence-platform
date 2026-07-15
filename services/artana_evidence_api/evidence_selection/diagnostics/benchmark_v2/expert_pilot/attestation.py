"""Canonical Ed25519 verification for externally signed pilot artifacts."""

from __future__ import annotations

import hashlib
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel


def canonical_payload_bytes(payload: BaseModel) -> bytes:
    """Serialize one typed payload for signing without presentation whitespace."""

    return json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_payload_sha256(payload: BaseModel) -> str:
    """Return the stable identity used by downstream signed artifacts."""

    return hashlib.sha256(canonical_payload_bytes(payload)).hexdigest()


def verify_ed25519_signature(
    *,
    payload: BaseModel,
    public_key_hex: str,
    signature_hex: str,
) -> None:
    """Verify an external signature and expose no signing capability."""

    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        signature = bytes.fromhex(signature_hex)
        public_key.verify(signature, canonical_payload_bytes(payload))
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("expert-pilot Ed25519 signature verification failed") from exc


__all__ = [
    "canonical_payload_bytes",
    "canonical_payload_sha256",
    "verify_ed25519_signature",
]
