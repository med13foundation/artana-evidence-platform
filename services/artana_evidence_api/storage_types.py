"""Service-local storage type definitions for the harness API."""

from __future__ import annotations

from enum import StrEnum


class StorageUseCase(StrEnum):
    """Use cases that can be mapped to storage operations."""

    PDF = "pdf"
    EXPORT = "export"
    RAW_SOURCE = "raw_source"
    DOCUMENT_CONTENT = "document_content"
    BACKUP = "backup"


__all__ = ["StorageUseCase"]
