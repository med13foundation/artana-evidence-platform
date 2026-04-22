"""Binary document storage helpers for harness-side PDF enrichment flows."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from artana_evidence_api.storage_types import StorageUseCase


@dataclass(frozen=True, slots=True)
class HarnessBinaryStorageRecord:
    """One stored binary/text payload tracked by a storage key."""

    key: str
    byte_size: int
    content_type: str


class HarnessDocumentBinaryStore:
    """In-memory binary store used by unit tests and local overrides."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._payloads: dict[str, bytes] = {}

    async def store_bytes(
        self,
        *,
        use_case: StorageUseCase,
        key: str,
        payload: bytes,
        content_type: str,
    ) -> HarnessBinaryStorageRecord:
        del use_case
        with self._lock:
            self._payloads[key] = payload
        return HarnessBinaryStorageRecord(
            key=key,
            byte_size=len(payload),
            content_type=content_type,
        )

    async def read_bytes(self, *, key: str) -> bytes:
        with self._lock:
            payload = self._payloads.get(key)
        if payload is None:
            msg = f"Stored payload '{key}' was not found"
            raise FileNotFoundError(msg)
        return payload

    async def read_text(self, *, key: str, encoding: str = "utf-8") -> str:
        payload = await self.read_bytes(key=key)
        return payload.decode(encoding)


class LocalFilesystemHarnessDocumentBinaryStore(HarnessDocumentBinaryStore):
    """Filesystem-backed binary store used by the harness service."""

    def __init__(self, *, base_path: str | Path) -> None:
        super().__init__()
        normalized_base_path = Path(base_path).expanduser()
        if not normalized_base_path.is_absolute():
            msg = "Local filesystem storage base path must be absolute"
            raise ValueError(msg)
        self._base_path = normalized_base_path
        self._base_path.mkdir(parents=True, exist_ok=True)

    async def store_bytes(
        self,
        *,
        use_case: StorageUseCase,
        key: str,
        payload: bytes,
        content_type: str,
    ) -> HarnessBinaryStorageRecord:
        del use_case
        destination = self._base_path / key
        await asyncio.to_thread(destination.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(destination.write_bytes, payload)
        return HarnessBinaryStorageRecord(
            key=key,
            byte_size=len(payload),
            content_type=content_type,
        )

    async def read_bytes(self, *, key: str) -> bytes:
        resolved_path = await self._resolve_path(key=key)
        return await asyncio.to_thread(resolved_path.read_bytes)

    async def read_text(self, *, key: str, encoding: str = "utf-8") -> str:
        resolved_path = await self._resolve_path(key=key)
        return await asyncio.to_thread(resolved_path.read_text, encoding)

    async def _resolve_path(self, *, key: str) -> Path:
        resolved = self._base_path / key
        if not resolved.exists():
            msg = f"Stored payload '{key}' was not found"
            raise FileNotFoundError(msg)
        return resolved


__all__ = [
    "HarnessBinaryStorageRecord",
    "HarnessDocumentBinaryStore",
    "LocalFilesystemHarnessDocumentBinaryStore",
]
