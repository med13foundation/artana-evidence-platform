"""Secret-backed identifiers for model-blinded expert-pilot safety review."""

from __future__ import annotations

import hashlib
import hmac
import os
import stat
from pathlib import Path

_BLINDING_CONTEXT = b"artana-evidence-expert-pilot-safety-blinding.v1\x00"
_KEY_BYTES = 32


def load_safety_blinding_key(path: Path) -> bytes:
    """Load one owner-private 256-bit hex key retained across safety stages."""

    resolved = path.resolve()
    if os.name == "posix" and stat.S_IMODE(resolved.stat().st_mode) & 0o077:
        raise ValueError(
            "safety blinding key file must be accessible only by its owner"
        )
    value = resolved.read_text(encoding="ascii").strip()
    if len(value) != _KEY_BYTES * 2 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(
            "safety blinding key must be exactly 64 lowercase hexadecimal characters"
        )
    return bytes.fromhex(value)


def keyed_blind_digest(*, key: bytes, namespace: str, parts: tuple[str, ...]) -> str:
    """Derive a non-enumerable identifier without exposing the retained key."""

    if len(key) != _KEY_BYTES:
        raise ValueError("safety blinding requires exactly 32 key bytes")
    message = b"\x1f".join(part.encode("utf-8") for part in (namespace, *parts))
    return hmac.new(key, _BLINDING_CONTEXT + message, hashlib.sha256).hexdigest()


__all__ = ["keyed_blind_digest", "load_safety_blinding_key"]
