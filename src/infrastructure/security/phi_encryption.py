"""PHI identifier encryption utilities (AES-256-GCM + blind indexing)."""

from __future__ import annotations

import base64
import hmac
import os
from functools import lru_cache
from hashlib import sha256

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.infrastructure.security.key_provider import (
    PHIKeyProvider,
    build_phi_key_provider_from_env,
)

_CIPHERTEXT_PREFIX = "artanaphi"
_DEFAULT_AAD = b"med13:entity_identifiers"
_CIPHERTEXT_PART_COUNT = 4


class PHIEncryptionService:
    """Encrypt/decrypt PHI values and produce deterministic blind indexes."""

    def __init__(
        self,
        key_provider: PHIKeyProvider,
        *,
        associated_data: bytes = _DEFAULT_AAD,
    ) -> None:
        self._key_provider = key_provider
        self._associated_data = associated_data

    @property
    def key_version(self) -> str:
        """Current encryption key version identifier."""
        return self._key_provider.get_key_material().key_version

    @property
    def blind_index_version(self) -> str:
        """Current blind-index key version identifier."""
        return self._key_provider.get_key_material().blind_index_version

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a PHI identifier value."""
        if not plaintext:
            message = "Cannot encrypt an empty PHI identifier value"
            raise ValueError(message)

        material = self._key_provider.get_key_material()
        nonce = os.urandom(12)
        aesgcm = AESGCM(material.encryption_key)
        ciphertext = aesgcm.encrypt(
            nonce,
            plaintext.encode("utf-8"),
            self._associated_data,
        )
        nonce_token = base64.urlsafe_b64encode(nonce).decode("utf-8")
        payload_token = base64.urlsafe_b64encode(ciphertext).decode("utf-8")
        return (
            f"{_CIPHERTEXT_PREFIX}:{material.key_version}:"
            f"{nonce_token}:{payload_token}"
        )

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a PHI identifier value produced by :meth:`encrypt`."""
        prefix, key_version, nonce_token, payload_token = self._split_ciphertext(
            ciphertext,
        )
        if prefix != _CIPHERTEXT_PREFIX:
            message = "Unsupported PHI ciphertext format"
            raise ValueError(message)

        material = self._key_provider.get_key_material()
        if key_version != material.key_version:
            message = (
                "PHI ciphertext key version does not match active key material "
                f"({key_version} != {material.key_version})"
            )
            raise ValueError(message)

        nonce = base64.urlsafe_b64decode(nonce_token.encode("utf-8"))
        payload = base64.urlsafe_b64decode(payload_token.encode("utf-8"))
        aesgcm = AESGCM(material.encryption_key)
        plaintext = aesgcm.decrypt(nonce, payload, self._associated_data)
        return plaintext.decode("utf-8")

    def blind_index(self, plaintext: str) -> str:
        """Compute deterministic HMAC-SHA256 blind index for equality lookup."""
        material = self._key_provider.get_key_material()
        digest = hmac.new(
            material.blind_index_key,
            plaintext.encode("utf-8"),
            sha256,
        )
        return digest.hexdigest()

    @staticmethod
    def is_encrypted_identifier(value: str) -> bool:
        """Return True when identifier value appears to be encrypted."""
        return value.startswith(f"{_CIPHERTEXT_PREFIX}:")

    @staticmethod
    def _split_ciphertext(ciphertext: str) -> tuple[str, str, str, str]:
        parts = ciphertext.split(":")
        if len(parts) != _CIPHERTEXT_PART_COUNT:
            message = "Malformed PHI ciphertext payload"
            raise ValueError(message)
        return parts[0], parts[1], parts[2], parts[3]


@lru_cache(maxsize=1)
def build_phi_encryption_service_from_env() -> PHIEncryptionService:
    """Build and cache the configured PHI encryption service."""
    provider = build_phi_key_provider_from_env()
    return PHIEncryptionService(provider)


def is_phi_encryption_enabled() -> bool:
    """Return True when PHI identifier encryption is enabled."""
    return os.getenv("ARTANA_ENABLE_PHI_ENCRYPTION", "0") == "1"


__all__ = [
    "PHIEncryptionService",
    "build_phi_encryption_service_from_env",
    "is_phi_encryption_enabled",
]
