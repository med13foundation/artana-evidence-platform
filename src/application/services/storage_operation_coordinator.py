"""
Helpers for orchestrating storage operations across use cases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path
    from uuid import UUID

    from src.application.services.storage_configuration_service import (
        StorageConfigurationService,
    )
    from src.type_definitions.common import JSONObject
    from src.type_definitions.storage import (
        StorageOperationRecord,
        StorageUseCase,
    )


class StorageOperationCoordinator:
    """Coordinates storing artifacts through registered storage providers."""

    def __init__(self, storage_service: StorageConfigurationService) -> None:
        self._storage_service = storage_service

    async def store_for_use_case(  # noqa: PLR0913 - explicit storage inputs maintain clarity
        self,
        use_case: StorageUseCase,
        *,
        key: str,
        file_path: Path,
        content_type: str | None = None,
        user_id: UUID | None = None,
        metadata: JSONObject | None = None,
    ) -> StorageOperationRecord:
        """
        Store an artifact using the storage configuration assigned to the use case.

        Raises:
            RuntimeError: If no configuration is mapped to the requested use case.
        """

        configuration = self._storage_service.get_default_for_use_case(use_case)
        if configuration is None:
            msg = f"No storage configuration defined for use case {use_case.value}"
            raise RuntimeError(msg)
        return await self._storage_service.record_store_operation(
            configuration,
            key=key,
            file_path=file_path,
            content_type=content_type,
            user_id=user_id,
            metadata=metadata,
        )


__all__ = ["StorageOperationCoordinator"]
