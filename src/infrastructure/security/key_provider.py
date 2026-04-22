"""Key provider utilities for PHI column encryption."""

from __future__ import annotations

import base64
import binascii
import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol


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
    "PHIKeyMaterial",
    "PHIKeyProvider",
    "SecretManagerKeyProvider",
    "build_phi_key_provider_from_env",
]
