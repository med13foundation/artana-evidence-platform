from __future__ import annotations

import base64
from dataclasses import dataclass

import pytest
from artana_evidence_db.phi_encryption_support import (
    PHIEncryptionService,
    PHIKeyMaterial,
    build_phi_encryption_service_from_env,
    is_phi_encryption_enabled,
)


def _b64_key(byte_value: int) -> str:
    return base64.b64encode(bytes([byte_value]) * 32).decode("utf-8")


@dataclass(slots=True)
class StaticKeyProvider:
    key_material: PHIKeyMaterial

    def get_key_material(self) -> PHIKeyMaterial:
        return self.key_material


def test_build_phi_encryption_service_from_env_reads_local_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTANA_PHI_ENCRYPTION_KEY_B64", _b64_key(1))
    monkeypatch.setenv("ARTANA_PHI_BLIND_INDEX_KEY_B64", _b64_key(2))
    monkeypatch.setenv("ARTANA_PHI_KEY_VERSION", "key-v2")
    monkeypatch.setenv("ARTANA_PHI_BLIND_INDEX_VERSION", "blind-v2")
    build_phi_encryption_service_from_env.cache_clear()

    service = build_phi_encryption_service_from_env()

    assert service.key_version == "key-v2"
    assert service.blind_index_version == "blind-v2"


def test_phi_encryption_round_trip() -> None:
    provider = StaticKeyProvider(
        PHIKeyMaterial(
            encryption_key=bytes([3]) * 32,
            blind_index_key=bytes([4]) * 32,
            key_version="v1",
            blind_index_version="v1",
        ),
    )
    service = PHIEncryptionService(provider)

    plaintext = "MRN-000123"
    encrypted = service.encrypt(plaintext)

    assert encrypted != plaintext
    assert service.is_encrypted_identifier(encrypted) is True
    assert service.decrypt(encrypted) == plaintext


def test_blind_index_is_deterministic() -> None:
    provider = StaticKeyProvider(
        PHIKeyMaterial(
            encryption_key=bytes([5]) * 32,
            blind_index_key=bytes([6]) * 32,
            key_version="v1",
            blind_index_version="v1",
        ),
    )
    service = PHIEncryptionService(provider)

    first = service.blind_index("value-a")
    second = service.blind_index("value-a")
    third = service.blind_index("value-b")

    assert first == second
    assert first != third


def test_is_phi_encryption_enabled_reads_feature_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTANA_ENABLE_PHI_ENCRYPTION", "1")

    assert is_phi_encryption_enabled() is True
