"""Helper utilities for extraction runner batch orchestration."""

from __future__ import annotations

import logging
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src.domain.entities.publication_extraction import (
    ExtractionOutcome,
    ExtractionTextSource,
    PublicationExtraction,
)
from src.type_definitions.storage import StorageUseCase

from ._extraction_runner_text_helpers import (
    ExtractionBatchSummary,
    build_payload_from_segments,
    coerce_text,
    resolve_document_reference,
)

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.services.ports.extraction_processor_port import (
        ExtractionProcessorPort,
        ExtractionProcessorResult,
        ExtractionTextPayload,
    )
    from src.application.services.storage_operation_coordinator import (
        StorageOperationCoordinator,
    )
    from src.domain.entities import ExtractionQueueItem, Publication
    from src.domain.repositories import (
        ExtractionQueueRepository,
        PublicationExtractionRepository,
        PublicationRepository,
    )
    from src.type_definitions.common import (
        JSONObject,
        PublicationExtractionUpdate,
    )

logger = logging.getLogger(__name__)


class ExtractionRunnerBatchProcessor:
    """Execute a single extraction batch with side effects."""

    # Keep constructor dependency-rich for explicit wiring and traceability.
    def __init__(  # noqa: PLR0913 - explicit dependency injection keeps orchestration clear
        self,
        *,
        queue_repository: ExtractionQueueRepository,
        publication_repository: PublicationRepository,
        extraction_repository: PublicationExtractionRepository,
        processor_registry: dict[str, ExtractionProcessorPort] | None,
        storage_coordinator: StorageOperationCoordinator | None,
    ) -> None:
        self._queue_repository = queue_repository
        self._publication_repository = publication_repository
        self._extraction_repository = extraction_repository
        self._processor_registry = {
            key.strip().lower(): value
            for key, value in (processor_registry or {}).items()
            if key.strip()
        }
        self._storage_coordinator = storage_coordinator

    async def run_batch(
        self,
        *,
        limit: int,
        source_id: UUID | None,
        ingestion_job_id: UUID | None,
    ) -> ExtractionBatchSummary:
        items = self._queue_repository.claim_pending(
            limit=limit,
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
        )
        if not items:
            return ExtractionBatchSummary()

        completed = 0
        skipped = 0
        failed = 0

        for item in items:
            processor = self._resolve_processor(item.source_type)
            if processor is None:
                failed += 1
                error_message = (
                    f"no_extraction_processor_for_source_type:{item.source_type}"
                )
                self._queue_repository.mark_failed(
                    item.id,
                    error_message=error_message,
                )
                continue

            publication = self._resolve_publication(item)
            text_payload = self._build_text_payload(
                item=item,
                publication=publication,
            )
            if text_payload is not None:
                text_payload = await self._store_text_payload(
                    item=item,
                    publication=publication,
                    payload=text_payload,
                )
            try:
                result = processor.extract_publication(
                    queue_item=item,
                    publication=publication,
                    text_payload=text_payload,
                )
            except Exception as exc:  # pragma: no cover - defensive # noqa: BLE001
                failed += 1
                self._queue_repository.mark_failed(
                    item.id,
                    error_message=str(exc),
                )
                continue

            failed_increment = self._handle_result(
                item=item,
                publication=publication,
                result=result,
            )
            if failed_increment:
                failed += 1
            elif result.status == "skipped":
                skipped += 1
            else:
                completed += 1

        return ExtractionBatchSummary(
            processed=len(items),
            completed=completed,
            skipped=skipped,
            failed=failed,
        )

    def _resolve_processor(self, source_type: str) -> ExtractionProcessorPort | None:
        normalized_source_type = source_type.strip().lower()
        if (
            normalized_source_type
            and normalized_source_type in self._processor_registry
        ):
            return self._processor_registry[normalized_source_type]
        return None

    def _resolve_publication(
        self,
        item: ExtractionQueueItem,
    ) -> Publication | None:
        if item.publication_id is not None:
            try:
                publication = self._publication_repository.get_by_id(
                    item.publication_id,
                )
            except Exception:  # noqa: BLE001 - fallback to metadata-only extraction
                self._rollback_publication_repository_session()
                logger.warning(
                    "Publication lookup by id failed; continuing with metadata payload",
                    extra={
                        "publication_id": item.publication_id,
                        "source_record_id": item.source_record_id,
                    },
                )
                publication = None
            if publication is not None:
                return publication
        if item.pubmed_id:
            try:
                return self._publication_repository.find_by_pmid(item.pubmed_id)
            except Exception:  # noqa: BLE001 - fallback to metadata-only extraction
                self._rollback_publication_repository_session()
                logger.warning(
                    "Publication lookup by pmid failed; continuing with metadata payload",
                    extra={
                        "pubmed_id": item.pubmed_id,
                        "source_record_id": item.source_record_id,
                    },
                )
                return None
        return None

    def _rollback_publication_repository_session(self) -> None:
        repository_session = getattr(self._publication_repository, "session", None)
        if repository_session is None:
            return
        rollback = getattr(repository_session, "rollback", None)
        if callable(rollback):
            rollback()

    def _build_text_payload(
        self,
        *,
        item: ExtractionQueueItem,
        publication: Publication | None,
    ) -> ExtractionTextPayload | None:
        metadata_payload = self._payload_from_metadata(item)
        publication_payload = self._payload_from_publication(publication)
        return self._select_preferred_payload(
            metadata_payload,
            publication_payload,
        )

    @staticmethod
    def _select_preferred_payload(
        metadata_payload: ExtractionTextPayload | None,
        publication_payload: ExtractionTextPayload | None,
    ) -> ExtractionTextPayload | None:
        candidates = [
            payload
            for payload in (metadata_payload, publication_payload)
            if payload is not None
        ]
        if not candidates:
            return None

        return max(
            candidates,
            key=lambda payload: (
                ExtractionRunnerBatchProcessor._payload_priority(payload.text_source),
                len(payload.text),
            ),
        )

    @staticmethod
    def _payload_priority(text_source: str) -> int:
        if text_source == "full_text":
            return 4
        if text_source == "title_abstract":
            return 3
        if text_source == "abstract":
            return 2
        if text_source == "title":
            return 1
        return 0

    def _payload_from_publication(
        self,
        publication: Publication | None,
    ) -> ExtractionTextPayload | None:
        if publication is None:
            return None
        title = publication.title.strip() if publication.title else ""
        abstract = publication.abstract.strip() if publication.abstract else ""
        return build_payload_from_segments(
            title=title,
            abstract=abstract,
            full_text="",
            document_reference=None,
        )

    def _payload_from_metadata(
        self,
        item: ExtractionQueueItem,
    ) -> ExtractionTextPayload | None:
        raw_record_value = item.metadata.get("raw_record")
        if not isinstance(raw_record_value, dict):
            return None
        title = coerce_text(raw_record_value.get("title"))
        abstract = coerce_text(raw_record_value.get("abstract"))
        text_value = coerce_text(raw_record_value.get("text"))
        full_text = text_value or coerce_text(raw_record_value.get("full_text"))
        return build_payload_from_segments(
            title=title,
            abstract=abstract,
            full_text=full_text,
            document_reference=resolve_document_reference(item),
        )

    async def _store_text_payload(
        self,
        *,
        item: ExtractionQueueItem,
        publication: Publication | None,
        payload: ExtractionTextPayload,
    ) -> ExtractionTextPayload:
        if payload.document_reference or self._storage_coordinator is None:
            return payload

        key = self._build_storage_key(
            item=item,
            publication=publication,
            payload=payload,
        )
        metadata = self._build_storage_metadata(
            item=item,
            publication=publication,
            payload=payload,
        )
        temp_path = self._write_text_payload(payload.text)
        try:
            record = await self._storage_coordinator.store_for_use_case(
                StorageUseCase.RAW_SOURCE,
                key=key,
                file_path=temp_path,
                content_type="text/plain",
                user_id=None,
                metadata=metadata,
            )
        except (OSError, RuntimeError, ValueError):
            return payload
        finally:
            temp_path.unlink(missing_ok=True)
        return replace(payload, document_reference=record.key)

    @staticmethod
    def _write_text_payload(text: str) -> Path:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp.write(text)
            return Path(tmp.name)

    @staticmethod
    def _build_storage_key(
        *,
        item: ExtractionQueueItem,
        publication: Publication | None,
        payload: ExtractionTextPayload,
    ) -> str:
        identifier = (
            publication.identifier.pubmed_id
            if publication and publication.identifier.pubmed_id
            else item.source_record_id
        )
        return (
            "extractions/"
            f"{item.source_id}/"
            f"{item.ingestion_job_id}/"
            f"{identifier}/"
            f"v{item.extraction_version}/"
            f"{item.id}_{payload.text_source}.txt"
        )

    @staticmethod
    def _build_storage_metadata(
        *,
        item: ExtractionQueueItem,
        publication: Publication | None,
        payload: ExtractionTextPayload,
    ) -> JSONObject:
        metadata: JSONObject = {
            "queue_item_id": str(item.id),
            "source_id": str(item.source_id),
            "source_type": item.source_type,
            "source_record_id": item.source_record_id,
            "ingestion_job_id": str(item.ingestion_job_id),
            "extraction_version": item.extraction_version,
            "text_source": payload.text_source,
        }
        if item.raw_storage_key:
            metadata["raw_storage_key"] = item.raw_storage_key
        if item.payload_ref:
            metadata["payload_ref"] = item.payload_ref
        if item.publication_id is not None:
            metadata["publication_id"] = item.publication_id
        if publication is not None:
            metadata.update(
                {
                    "pubmed_id": publication.identifier.pubmed_id,
                    "pmc_id": publication.identifier.pmc_id,
                    "doi": publication.identifier.doi,
                },
            )
        return metadata

    def _handle_result(
        self,
        *,
        item: ExtractionQueueItem,
        publication: Publication | None,
        result: ExtractionProcessorResult,
    ) -> bool:
        try:
            extraction_record = self._persist_extraction(
                item=item,
                publication=publication,
                result=result,
            )
        except Exception as exc:  # pragma: no cover - defensive # noqa: BLE001
            self._queue_repository.mark_failed(
                item.id,
                error_message=str(exc),
            )
            return True

        if result.status == "failed":
            error_message = result.error_message or "extraction_failed"
            self._queue_repository.mark_failed(
                item.id,
                error_message=error_message,
            )
            return True

        metadata = self._build_metadata(
            item=item,
            publication=publication,
            result=result,
            extraction_id=extraction_record.id,
        )
        self._queue_repository.mark_completed(
            item.id,
            metadata=metadata,
        )
        return False

    def _build_metadata(
        self,
        *,
        item: ExtractionQueueItem,
        publication: Publication | None,
        result: ExtractionProcessorResult,
        extraction_id: UUID,
    ) -> JSONObject:
        payload: JSONObject = dict(result.metadata)
        payload["extraction_outcome"] = result.status
        payload["extraction_version"] = item.extraction_version
        payload["extracted_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        payload["extraction_id"] = str(extraction_id)
        payload["source_type"] = item.source_type
        payload["source_record_id"] = item.source_record_id
        payload["text_source"] = result.text_source
        payload["document_reference"] = result.document_reference

        if publication is not None:
            if publication.id is not None:
                payload["publication_id"] = publication.id
            payload["publication_title"] = publication.title
            payload["pubmed_id"] = publication.identifier.pubmed_id
            payload["pmc_id"] = publication.identifier.pmc_id
            payload["doi"] = publication.identifier.doi
        elif item.pubmed_id:
            payload["pubmed_id"] = item.pubmed_id

        return payload

    def _persist_extraction(
        self,
        *,
        item: ExtractionQueueItem,
        publication: Publication | None,
        result: ExtractionProcessorResult,
    ) -> PublicationExtraction:
        now = datetime.now(UTC)
        outcome = ExtractionOutcome(result.status)
        text_source = ExtractionTextSource(result.text_source)
        pubmed_id = publication.identifier.pubmed_id if publication else None

        existing = self._extraction_repository.find_by_queue_item_id(item.id)
        if existing is not None:
            updates: PublicationExtractionUpdate = {
                "status": outcome.value,
                "facts": list(result.facts),
                "metadata": dict(result.metadata),
                "extracted_at": now,
                "processor_name": result.processor_name,
                "processor_version": result.processor_version,
                "text_source": text_source.value,
                "document_reference": result.document_reference,
            }
            return self._extraction_repository.update(existing.id, updates)

        extraction = PublicationExtraction(
            id=item.id,
            publication_id=item.publication_id,
            pubmed_id=pubmed_id,
            source_id=item.source_id,
            ingestion_job_id=item.ingestion_job_id,
            queue_item_id=item.id,
            status=outcome,
            extraction_version=item.extraction_version,
            processor_name=result.processor_name,
            processor_version=result.processor_version,
            text_source=text_source,
            document_reference=result.document_reference,
            facts=list(result.facts),
            metadata=dict(result.metadata),
            extracted_at=now,
            created_at=now,
            updated_at=now,
        )
        return self._extraction_repository.create(extraction)


__all__ = ["ExtractionBatchSummary", "ExtractionRunnerBatchProcessor"]
