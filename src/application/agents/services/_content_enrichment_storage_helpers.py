"""Storage and summary helpers for Tier-2 content-enrichment orchestration."""

# mypy: disable-error-code="misc"

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from src.application.agents.services._content_enrichment_helpers import (
    StorageResult,
    compute_character_count,
    infer_storage_format,
    merge_metadata,
    serialize_contract_payload,
    write_temp_payload,
)
from src.application.agents.services._content_enrichment_types import (
    ContentEnrichmentDocumentOutcome,
    ContentEnrichmentRunSummary,
)
from src.type_definitions.common import JSONObject  # noqa: TC001
from src.type_definitions.storage import StorageUseCase

if TYPE_CHECKING:
    from pathlib import Path

    from src.application.services.storage_operation_coordinator import (
        StorageOperationCoordinator,
    )
    from src.domain.agents.contracts.content_enrichment import ContentEnrichmentContract
    from src.domain.entities.source_document import EnrichmentStatus, SourceDocument
    from src.domain.repositories.source_document_repository import (
        SourceDocumentRepository,
    )


class _ContentEnrichmentStorageSelf(Protocol):
    _storage_coordinator: StorageOperationCoordinator | None
    _source_documents: SourceDocumentRepository

    @staticmethod
    def _build_inline_storage_result(
        *,
        document: SourceDocument,
        contract: ContentEnrichmentContract,
        payload: bytes,
    ) -> StorageResult: ...

    @staticmethod
    def _resolve_existing_or_inline_storage(
        *,
        document: SourceDocument,
        contract: ContentEnrichmentContract,
        payload: bytes | None,
    ) -> StorageResult | None: ...

    async def _store_generated_payload(
        self,
        *,
        document: SourceDocument,
        contract: ContentEnrichmentContract,
        payload: bytes,
        run_id: str | None,
        pipeline_run_id: str | None,
    ) -> StorageResult: ...

    async def _store_payload_with_fallback(
        self,
        *,
        key: str,
        file_path: Path,
        content_type: str,
        metadata: JSONObject,
    ) -> _StoredPayloadRecord: ...


class _StoredPayloadRecord(Protocol):
    key: str


class _ContentEnrichmentStorageHelpers:
    """Storage persistence and run-summary helper methods."""

    async def _resolve_content_storage(
        self: _ContentEnrichmentStorageSelf,
        *,
        document: SourceDocument,
        contract: ContentEnrichmentContract,
        run_id: str | None,
        pipeline_run_id: str | None,
    ) -> StorageResult | None:
        payload = serialize_contract_payload(contract)
        direct_result = self._resolve_existing_or_inline_storage(
            document=document,
            contract=contract,
            payload=payload,
        )
        if direct_result is not None:
            return direct_result

        if payload is None:
            return None
        if self._storage_coordinator is None:
            return self._build_inline_storage_result(
                document=document,
                contract=contract,
                payload=payload,
            )

        try:
            return await self._store_generated_payload(
                document=document,
                contract=contract,
                payload=payload,
                run_id=run_id,
                pipeline_run_id=pipeline_run_id,
            )
        except RuntimeError as exc:
            missing_storage_message = "No storage configuration defined for use case"
            if missing_storage_message not in str(exc):
                raise
            return self._build_inline_storage_result(
                document=document,
                contract=contract,
                payload=payload,
            )

    @staticmethod
    def _resolve_existing_or_inline_storage(
        *,
        document: SourceDocument,
        contract: ContentEnrichmentContract,
        payload: bytes | None,
    ) -> StorageResult | None:
        if contract.content_storage_key is not None:
            return _ContentEnrichmentStorageHelpers._build_storage_result_for_key(
                storage_key=contract.content_storage_key,
                contract=contract,
                payload=payload,
            )

        if contract.acquisition_method != "pass_through":
            return None

        if document.raw_storage_key is not None:
            return _ContentEnrichmentStorageHelpers._build_storage_result_for_key(
                storage_key=document.raw_storage_key,
                contract=contract,
                payload=payload,
            )

        if payload is None:
            return None

        content_hash = hashlib.sha256(payload).hexdigest()
        inline_storage_key = (
            f"inline://documents/{document.id}/pass_through/{content_hash}"
        )
        return _ContentEnrichmentStorageHelpers._build_storage_result_for_key(
            storage_key=inline_storage_key,
            contract=contract,
            payload=payload,
        )

    @staticmethod
    def _build_storage_result_for_key(
        *,
        storage_key: str,
        contract: ContentEnrichmentContract,
        payload: bytes | None,
    ) -> StorageResult:
        content_hash = (
            hashlib.sha256(payload).hexdigest() if payload is not None else None
        )
        if payload is None:
            content_length_chars = max(contract.content_length_chars, 0)
        else:
            content_length_chars = (
                contract.content_length_chars
                if contract.content_length_chars > 0
                else compute_character_count(contract, payload)
            )
        return StorageResult(
            storage_key=storage_key,
            content_hash=content_hash,
            content_length_chars=max(content_length_chars, 0),
        )

    @staticmethod
    def _build_inline_storage_result(
        *,
        document: SourceDocument,
        contract: ContentEnrichmentContract,
        payload: bytes,
    ) -> StorageResult:
        content_hash = hashlib.sha256(payload).hexdigest()
        inline_storage_key = (
            "inline://documents/"
            f"{document.id}/{contract.acquisition_method}/{content_hash}"
        )
        return _ContentEnrichmentStorageHelpers._build_storage_result_for_key(
            storage_key=inline_storage_key,
            contract=contract,
            payload=payload,
        )

    async def _store_generated_payload(
        self: _ContentEnrichmentStorageSelf,
        *,
        document: SourceDocument,
        contract: ContentEnrichmentContract,
        payload: bytes,
        run_id: str | None,
        pipeline_run_id: str | None,
    ) -> StorageResult:
        content_hash = hashlib.sha256(payload).hexdigest()
        extension, content_type = infer_storage_format(contract.content_format)
        key = f"documents/{document.id}/enriched/{content_hash}.{extension}"
        metadata: JSONObject = {
            "document_id": str(document.id),
            "source_id": str(document.source_id),
            "source_type": document.source_type.value,
            "external_record_id": document.external_record_id,
            "acquisition_method": contract.acquisition_method,
            "content_format": contract.content_format,
        }
        if run_id is not None:
            metadata["enrichment_run_id"] = run_id
        if pipeline_run_id is not None and pipeline_run_id.strip():
            metadata["pipeline_run_id"] = pipeline_run_id.strip()

        temp_path = write_temp_payload(payload, suffix=f".{extension}")
        try:
            record = await self._store_payload_with_fallback(
                key=key,
                file_path=temp_path,
                content_type=content_type,
                metadata=metadata,
            )
        finally:
            temp_path.unlink(missing_ok=True)

        return StorageResult(
            storage_key=record.key,
            content_hash=content_hash,
            content_length_chars=compute_character_count(contract, payload),
        )

    async def _store_payload_with_fallback(
        self: _ContentEnrichmentStorageSelf,
        *,
        key: str,
        file_path: Path,
        content_type: str,
        metadata: JSONObject,
    ) -> _StoredPayloadRecord:
        storage_coordinator = self._storage_coordinator
        if storage_coordinator is None:
            msg = "Storage coordinator is not configured"
            raise RuntimeError(msg)
        try:
            return await storage_coordinator.store_for_use_case(
                StorageUseCase.DOCUMENT_CONTENT,
                key=key,
                file_path=file_path,
                content_type=content_type,
                user_id=None,
                metadata=metadata,
            )
        except RuntimeError as exc:
            expected_fragment = f"use case {StorageUseCase.DOCUMENT_CONTENT.value}"
            if expected_fragment not in str(exc):
                raise
            fallback_metadata: JSONObject = dict(metadata)
            fallback_metadata["storage_use_case_fallback"] = (
                StorageUseCase.RAW_SOURCE.value
            )
            return await storage_coordinator.store_for_use_case(
                StorageUseCase.RAW_SOURCE,
                key=key,
                file_path=file_path,
                content_type=content_type,
                user_id=None,
                metadata=fallback_metadata,
            )

    def _persist_document_with_status(
        self: _ContentEnrichmentStorageSelf,
        *,
        document: SourceDocument,
        status: EnrichmentStatus,
        run_id: str | None,
        acquisition_method: str,
        metadata_patch: JSONObject,
    ) -> None:
        updated = document.model_copy(
            update={
                "enrichment_status": status,
                "enrichment_method": acquisition_method,
                "enrichment_agent_run_id": run_id,
                "updated_at": datetime.now(UTC),
                "metadata": merge_metadata(document.metadata, metadata_patch),
            },
        )
        self._source_documents.upsert(updated)

    @staticmethod
    def _build_run_summary(
        *,
        outcomes: list[ContentEnrichmentDocumentOutcome],
        requested: int,
        started_at: datetime,
        completed_at: datetime,
    ) -> ContentEnrichmentRunSummary:
        errors: list[str] = []
        enriched = 0
        skipped = 0
        failed = 0
        ai_runs = 0
        deterministic_runs = 0
        for outcome in outcomes:
            if outcome.status == "enriched":
                enriched += 1
            elif outcome.status == "skipped":
                skipped += 1
            elif outcome.status == "failed":
                failed += 1
            if outcome.execution_mode == "ai":
                ai_runs += 1
            else:
                deterministic_runs += 1
            errors.extend(error for error in outcome.errors if error)
        return ContentEnrichmentRunSummary(
            requested=requested,
            processed=len(outcomes),
            enriched=enriched,
            skipped=skipped,
            failed=failed,
            ai_runs=ai_runs,
            deterministic_runs=deterministic_runs,
            errors=tuple(dict.fromkeys(errors)),
            started_at=started_at,
            completed_at=completed_at,
        )
