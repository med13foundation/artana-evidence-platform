"""
Bulk Export Service for Artana Resource Library.

Kernel-native bulk export for research-space-scoped entities, observations, and
relations. Streams formatted payloads (JSON/CSV/TSV/JSONL) and optionally writes
exports to the configured storage backend.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar
from uuid import UUID, uuid4

from src.application.export.export_types import CompressionFormat, ExportFormat
from src.application.export.formatters import (
    export_as_csv,
    export_as_json,
    export_as_jsonl,
)
from src.application.export.utils import (
    copy_filters,
    get_entity_fields,
    get_observation_fields,
    get_relation_fields,
)
from src.type_definitions.storage import StorageUseCase

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from artana_evidence_db.kernel_repositories import (
        KernelEntityRepository,
        KernelObservationRepository,
        KernelRelationRepository,
    )

    from src.application.services.storage_configuration_service import (
        StorageConfigurationService,
    )
    from src.type_definitions.common import JSONObject, QueryFilters
    from src.type_definitions.storage import StorageOperationRecord

T = TypeVar("T")


class BulkExportService:
    """
    Service for bulk data export with streaming and multiple format support.

    Exports are always scoped to a research space to prevent cross-space leakage.
    """

    def __init__(
        self,
        entity_repo: KernelEntityRepository,
        observation_repo: KernelObservationRepository,
        relation_repo: KernelRelationRepository,
        storage_service: StorageConfigurationService | None = None,
    ) -> None:
        self._entities = entity_repo
        self._observations = observation_repo
        self._relations = relation_repo
        self._storage_service = storage_service

    async def export_to_storage(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        entity_type: str,
        export_format: ExportFormat,
        user_id: UUID,
        compression: CompressionFormat = CompressionFormat.NONE,
        filters: QueryFilters | None = None,
    ) -> StorageOperationRecord:
        """Export data to a file and store it using the configured EXPORT backend."""
        if not self._storage_service:
            msg = "Storage service not configured for export service"
            raise RuntimeError(msg)

        backend = self._storage_service.resolve_backend_for_use_case(
            StorageUseCase.EXPORT,
        )
        if not backend:
            msg = "No storage backend configured for EXPORT use case"
            raise ValueError(msg)

        suffix = f".{export_format.value}"
        if compression == CompressionFormat.GZIP:
            suffix += ".gz"

        tmp_path: Path | None = None
        # Create a temporary file to store the export
        with tempfile.NamedTemporaryFile(mode="wb", suffix=suffix, delete=False) as tmp:
            try:
                for chunk in self.export_data(
                    research_space_id=research_space_id,
                    entity_type=entity_type,
                    export_format=export_format,
                    compression=compression,
                    filters=filters,
                ):
                    if isinstance(chunk, str):
                        tmp.write(chunk.encode("utf-8"))
                    else:
                        tmp.write(chunk)
                tmp_path = Path(tmp.name)
            except Exception:
                Path(tmp.name).unlink(missing_ok=True)
                raise

        try:
            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            key = (
                "exports/"
                f"research-spaces/{research_space_id}/"
                f"{entity_type}/{timestamp}_{uuid4().hex[:8]}{suffix}"
            )

            return await self._storage_service.record_store_operation(
                configuration=backend,
                key=key,
                file_path=tmp_path,
                content_type=self._get_content_type(export_format, compression),
                user_id=user_id,
                metadata={
                    "research_space_id": research_space_id,
                    "entity_type": entity_type,
                    "format": export_format.value,
                    "compression": compression.value,
                },
            )
        finally:
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink()

    def _get_content_type(
        self,
        export_format: ExportFormat,
        compression: CompressionFormat,
    ) -> str:
        if compression == CompressionFormat.GZIP:
            return "application/gzip"

        content_types: dict[ExportFormat, str] = {
            ExportFormat.JSON: "application/json",
            ExportFormat.CSV: "text/csv",
            ExportFormat.TSV: "text/tab-separated-values",
            ExportFormat.JSONL: "application/x-jsonlines",
        }
        content_type = content_types.get(export_format)
        if content_type is None:
            msg = f"Unsupported export format: {export_format}"
            raise ValueError(msg)
        return content_type

    def export_data(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        entity_type: str,
        export_format: ExportFormat,
        compression: CompressionFormat = CompressionFormat.NONE,
        filters: QueryFilters | None = None,
        chunk_size: int = 1000,
    ) -> Generator[str | bytes]:
        """
        Export kernel data in the requested format.

        entity_type values:
        - entities
        - observations
        - relations
        """
        if entity_type == "entities":
            yield from self._export_entities(
                research_space_id=research_space_id,
                export_format=export_format,
                compression=compression,
                filters=filters,
                chunk_size=chunk_size,
            )
        elif entity_type == "observations":
            yield from self._export_observations(
                research_space_id=research_space_id,
                export_format=export_format,
                compression=compression,
                filters=filters,
                chunk_size=chunk_size,
            )
        elif entity_type == "relations":
            yield from self._export_relations(
                research_space_id=research_space_id,
                export_format=export_format,
                compression=compression,
                filters=filters,
                chunk_size=chunk_size,
            )
        else:
            msg = f"Unsupported entity type: {entity_type}"
            raise ValueError(msg)

    @staticmethod
    def _parse_limit(filters: QueryFilters | None) -> int | None:
        raw = None if filters is None else filters.get("limit")
        if raw is None or isinstance(raw, bool):
            return None

        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None

        return value if value > 0 else None

    def _export_entities(
        self,
        *,
        research_space_id: str,
        export_format: ExportFormat,
        compression: CompressionFormat,
        filters: QueryFilters | None,
        chunk_size: int,
    ) -> Generator[str | bytes]:
        filters_payload = copy_filters(filters)
        total_limit = self._parse_limit(filters_payload)
        entity_type_raw = filters_payload.get("entity_type")
        entity_type_filter = (
            entity_type_raw.strip()
            if isinstance(entity_type_raw, str) and entity_type_raw.strip()
            else None
        )

        entities = self._collect_offset_paginated(
            lambda offset, limit: self._entities.find_by_research_space(
                research_space_id,
                entity_type=entity_type_filter,
                limit=limit,
                offset=offset,
            ),
            chunk_size=chunk_size,
            total_limit=total_limit,
        )

        if export_format == ExportFormat.JSON:
            yield from export_as_json(entities, compression, "entities")
        elif export_format in (ExportFormat.CSV, ExportFormat.TSV):
            yield from export_as_csv(
                entities,
                export_format,
                compression,
                get_entity_fields(),
            )
        elif export_format == ExportFormat.JSONL:
            yield from export_as_jsonl(entities, compression)

    def _export_observations(
        self,
        *,
        research_space_id: str,
        export_format: ExportFormat,
        compression: CompressionFormat,
        filters: QueryFilters | None,
        chunk_size: int,
    ) -> Generator[str | bytes]:
        filters_payload = copy_filters(filters)
        total_limit = self._parse_limit(filters_payload)

        observations = self._collect_offset_paginated(
            lambda offset, limit: self._observations.find_by_research_space(
                research_space_id,
                limit=limit,
                offset=offset,
            ),
            chunk_size=chunk_size,
            total_limit=total_limit,
        )

        if export_format == ExportFormat.JSON:
            yield from export_as_json(observations, compression, "observations")
        elif export_format in (ExportFormat.CSV, ExportFormat.TSV):
            yield from export_as_csv(
                observations,
                export_format,
                compression,
                get_observation_fields(),
            )
        elif export_format == ExportFormat.JSONL:
            yield from export_as_jsonl(observations, compression)

    def _export_relations(
        self,
        *,
        research_space_id: str,
        export_format: ExportFormat,
        compression: CompressionFormat,
        filters: QueryFilters | None,
        chunk_size: int,
    ) -> Generator[str | bytes]:
        filters_payload = copy_filters(filters)
        total_limit = self._parse_limit(filters_payload)

        relations = self._collect_offset_paginated(
            lambda offset, limit: self._relations.find_by_research_space(
                research_space_id,
                limit=limit,
                offset=offset,
            ),
            chunk_size=chunk_size,
            total_limit=total_limit,
        )

        if export_format == ExportFormat.JSON:
            yield from export_as_json(relations, compression, "relations")
        elif export_format in (ExportFormat.CSV, ExportFormat.TSV):
            yield from export_as_csv(
                relations,
                export_format,
                compression,
                get_relation_fields(),
            )
        elif export_format == ExportFormat.JSONL:
            yield from export_as_jsonl(relations, compression)

    def get_export_info(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        filters: QueryFilters | None = None,
    ) -> JSONObject:
        """Return export metadata (counts + supported formats)."""
        filters_payload = copy_filters(filters)
        if entity_type == "entities":
            by_type = self._entities.count_by_type(research_space_id)
            entity_type_raw = filters_payload.get("entity_type")
            entity_type_filter = (
                entity_type_raw.strip()
                if isinstance(entity_type_raw, str) and entity_type_raw.strip()
                else None
            )
            if entity_type_filter is not None:
                estimated = int(by_type.get(entity_type_filter, 0))
            else:
                estimated = int(sum(by_type.values()))
        elif entity_type == "observations":
            estimated = int(
                self._observations.count_by_research_space(research_space_id),
            )
        elif entity_type == "relations":
            estimated = int(self._relations.count_by_research_space(research_space_id))
        else:
            msg = f"Unsupported entity type: {entity_type}"
            raise ValueError(msg)

        return {
            "entity_type": entity_type,
            "research_space_id": research_space_id,
            "supported_formats": [fmt.value for fmt in ExportFormat],
            "supported_compression": [comp.value for comp in CompressionFormat],
            "estimated_record_count": estimated,
            "last_updated": None,
        }

    @staticmethod
    def _collect_offset_paginated(
        fetch_page: Callable[[int, int], list[T]],
        *,
        chunk_size: int,
        total_limit: int | None,
    ) -> list[T]:
        """
        Collect items using offset/limit pagination.

        Kernel repositories expose offset/limit listing, but do not always return
        a total count with each page. This helper keeps the export logic simple.
        """
        results: list[T] = []
        offset = 0
        remaining = total_limit

        page_size = max(int(chunk_size), 1)

        while True:
            if remaining is not None and remaining <= 0:
                break

            limit = page_size if remaining is None else min(page_size, remaining)
            batch = fetch_page(offset, limit)
            if not batch:
                break
            results.extend(batch)

            offset += len(batch)
            if remaining is not None:
                remaining -= len(batch)

            # Stop when the backend returned fewer rows than requested.
            if len(batch) < limit:
                break

        return results


__all__ = ["BulkExportService", "CompressionFormat", "ExportFormat"]
