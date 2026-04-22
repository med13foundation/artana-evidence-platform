"""Service-local PHI-encryption runtime helpers."""

from __future__ import annotations

import base64
import binascii
import hmac
import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from hashlib import sha256
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_CIPHERTEXT_PREFIX = "artanaphi"
_DEFAULT_AAD = b"med13:entity_identifiers"
_CIPHERTEXT_PART_COUNT = 4


@dataclass(frozen=True, slots=True)
class PHIKeyMaterial:
    """Container for PHI encryption and blind-index keys."""

    encryption_key: bytes
    blind_index_key: bytes
    key_version: str
    blind_index_version: str


class PHIKeyProvider(Protocol):
    """Contract for loading PHI encryption key material."""

    def get_key_material(self) -> PHIKeyMaterial:
        """Return active key material for PHI encryption operations."""


class LocalKeyProvider:
    """Environment-backed key provider for local/dev/test usage."""

    def __init__(
        self,
        *,
        encryption_key_b64_env: str = "ARTANA_PHI_ENCRYPTION_KEY_B64",
        blind_index_key_b64_env: str = "ARTANA_PHI_BLIND_INDEX_KEY_B64",
        key_version_env: str = "ARTANA_PHI_KEY_VERSION",
        blind_index_version_env: str = "ARTANA_PHI_BLIND_INDEX_VERSION",
    ) -> None:
        self._encryption_key_b64_env = encryption_key_b64_env
        self._blind_index_key_b64_env = blind_index_key_b64_env
        self._key_version_env = key_version_env
        self._blind_index_version_env = blind_index_version_env

    def get_key_material(self) -> PHIKeyMaterial:
        encryption_raw = os.getenv(self._encryption_key_b64_env)
        blind_index_raw = os.getenv(self._blind_index_key_b64_env)
        if not encryption_raw:
            message = (
                f"Missing required PHI encryption key env var "
                f"{self._encryption_key_b64_env}"
            )
            raise RuntimeError(message)
        if not blind_index_raw:
            message = (
                f"Missing required PHI blind-index key env var "
                f"{self._blind_index_key_b64_env}"
            )
            raise RuntimeError(message)

        encryption_key = _decode_base64_key(
            encryption_raw,
            env_name=self._encryption_key_b64_env,
            min_length=32,
        )
        blind_index_key = _decode_base64_key(
            blind_index_raw,
            env_name=self._blind_index_key_b64_env,
            min_length=32,
        )
        key_version = os.getenv(self._key_version_env, "v1").strip() or "v1"
        blind_index_version = (
            os.getenv(self._blind_index_version_env, "v1").strip() or "v1"
        )

        return PHIKeyMaterial(
            encryption_key=encryption_key,
            blind_index_key=blind_index_key,
            key_version=key_version,
            blind_index_version=blind_index_version,
        )


class SecretManagerKeyProvider:
    """GCP Secret Manager-backed key provider with short-term caching."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        project_id: str,
        encryption_secret_id: str,
        blind_index_secret_id: str,
        secret_version: str,
        key_version: str = "v1",
        blind_index_version: str = "v1",
        cache_ttl_seconds: int = 300,
    ) -> None:
        if cache_ttl_seconds < 1:
            message = "cache_ttl_seconds must be >= 1"
            raise ValueError(message)
        self._project_id = project_id
        self._encryption_secret_id = encryption_secret_id
        self._blind_index_secret_id = blind_index_secret_id
        self._secret_version = secret_version
        self._key_version = key_version
        self._blind_index_version = blind_index_version
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._cache_lock = threading.Lock()
        self._cached: PHIKeyMaterial | None = None
        self._cached_at: datetime | None = None

    def get_key_material(self) -> PHIKeyMaterial:
        with self._cache_lock:
            if (
                self._cached is not None
                and self._cached_at is not None
                and datetime.now(UTC) - self._cached_at < self._cache_ttl
            ):
                return self._cached

            try:
                from google.cloud import secretmanager
            except ImportError as exc:  # pragma: no cover - env-specific failure
                message = (
                    "google-cloud-secret-manager is required when "
                    "ARTANA_PHI_KEY_PROVIDER is set to 'gcp'"
                )
                raise RuntimeError(message) from exc

            client = secretmanager.SecretManagerServiceClient()
            encryption_payload = self._access_secret_payload(
                client,
                secret_id=self._encryption_secret_id,
            )
            blind_index_payload = self._access_secret_payload(
                client,
                secret_id=self._blind_index_secret_id,
            )

            encryption_key = _decode_base64_key(
                encryption_payload,
                env_name=self._encryption_secret_id,
                min_length=32,
            )
            blind_index_key = _decode_base64_key(
                blind_index_payload,
                env_name=self._blind_index_secret_id,
                min_length=32,
            )

            material = PHIKeyMaterial(
                encryption_key=encryption_key,
                blind_index_key=blind_index_key,
                key_version=self._key_version,
                blind_index_version=self._blind_index_version,
            )
            self._cached = material
            self._cached_at = datetime.now(UTC)
            return material

    def _access_secret_payload(
        self,
        client: object,
        *,
        secret_id: str,
    ) -> str:
        secret_name = (
            f"projects/{self._project_id}/secrets/{secret_id}/"
            f"versions/{self._secret_version}"
        )
        access_secret_version = getattr(client, "access_secret_version", None)
        if not callable(access_secret_version):
            message = "Secret Manager client does not expose access_secret_version"
            raise TypeError(message)
        response = access_secret_version(request={"name": secret_name})
        payload = getattr(response, "payload", None)
        payload_bytes = getattr(payload, "data", None)
        if not isinstance(payload_bytes, bytes):
            message = "Secret Manager payload is missing bytes data"
            raise TypeError(message)
        return payload_bytes.decode("utf-8")


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


def build_phi_key_provider_from_env() -> PHIKeyProvider:
    """Build the configured PHI key provider from environment settings."""
    provider_name = os.getenv("ARTANA_PHI_KEY_PROVIDER", "local").strip().lower()
    if provider_name == "gcp":
        project_id = os.getenv("ARTANA_GCP_PROJECT_ID", "").strip()
        encryption_secret_id = os.getenv("ARTANA_PHI_ENCRYPTION_SECRET_ID", "").strip()
        blind_index_secret_id = os.getenv(
            "ARTANA_PHI_BLIND_INDEX_SECRET_ID",
            "",
        ).strip()
        if not project_id or not encryption_secret_id or not blind_index_secret_id:
            message = (
                "ARTANA_GCP_PROJECT_ID, ARTANA_PHI_ENCRYPTION_SECRET_ID, and "
                "ARTANA_PHI_BLIND_INDEX_SECRET_ID are required when "
                "ARTANA_PHI_KEY_PROVIDER=gcp"
            )
            raise RuntimeError(message)

        cache_ttl_seconds = _read_positive_int_env(
            "ARTANA_PHI_SECRET_CACHE_TTL_SECONDS",
            default=300,
        )
        return SecretManagerKeyProvider(
            project_id=project_id,
            encryption_secret_id=encryption_secret_id,
            blind_index_secret_id=blind_index_secret_id,
            secret_version=os.getenv("ARTANA_PHI_SECRET_VERSION", "latest"),
            key_version=os.getenv("ARTANA_PHI_KEY_VERSION", "v1"),
            blind_index_version=os.getenv("ARTANA_PHI_BLIND_INDEX_VERSION", "v1"),
            cache_ttl_seconds=cache_ttl_seconds,
        )

    return LocalKeyProvider()


def _decode_base64_key(raw_value: str, *, env_name: str, min_length: int) -> bytes:
    try:
        decoded = base64.b64decode(raw_value, validate=True)
    except (binascii.Error, ValueError) as exc:
        message = f"Invalid base64 key material in {env_name}"
        raise RuntimeError(message) from exc

    if len(decoded) < min_length:
        message = (
            f"Decoded key in {env_name} is too short "
            f"({len(decoded)} bytes; expected at least {min_length})"
        )
        raise RuntimeError(message)
    return decoded


def _read_positive_int_env(name: str, *, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        parsed = int(raw_value)
    except ValueError as exc:
        message = f"{name} must be an integer"
        raise RuntimeError(message) from exc
    if parsed < 1:
        message = f"{name} must be >= 1"
        raise RuntimeError(message)
    return parsed


__all__ = [
    "LocalKeyProvider",
    "PHIEncryptionService",
    "PHIKeyMaterial",
    "PHIKeyProvider",
    "SecretManagerKeyProvider",
    "build_phi_encryption_service_from_env",
    "build_phi_key_provider_from_env",
    "is_phi_encryption_enabled",
]
