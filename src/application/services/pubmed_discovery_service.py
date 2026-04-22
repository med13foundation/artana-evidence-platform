"""
Application service orchestrating PubMed advanced discovery workflows.
"""

from __future__ import annotations

import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict

from src.domain.entities import (
    data_discovery_parameters,
    discovery_preset,
    discovery_search_job,
)
from src.domain.repositories.data_discovery_repository import (
    DiscoverySearchJobRepository,  # noqa: TC001
)
from src.domain.services.pubmed_search import (
    PubMedPdfGateway,  # noqa: TC001
    PubMedSearchGateway,  # noqa: TC001
)
from src.type_definitions.storage import StorageOperationRecord, StorageUseCase

if TYPE_CHECKING:
    from src.application.services.pubmed_query_builder import PubMedQueryBuilder
    from src.application.services.storage_operation_coordinator import (
        StorageOperationCoordinator,
    )
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)

PUBMED_STORAGE_METADATA_USE_CASE_KEY = "storage_use_case"
PUBMED_STORAGE_METADATA_JOB_ID_KEY = "pubmed_job_id"
PUBMED_STORAGE_METADATA_ARTICLE_ID_KEY = "pubmed_article_id"
PUBMED_STORAGE_METADATA_OWNER_ID_KEY = "pubmed_owner_id"
PUBMED_STORAGE_METADATA_PROVIDER_KEY = "discovery_provider"
PUBMED_STORAGE_METADATA_RETRYABLE_KEY = "retryable"


class RunPubmedSearchRequest(BaseModel):
    """Request payload for initiating a PubMed search job."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: UUID | None = None
    parameters: data_discovery_parameters.AdvancedQueryParameters


class PubmedDownloadRequest(BaseModel):
    """Request payload for downloading PubMed PDFs."""

    job_id: UUID
    article_id: str


class PubMedDiscoveryService:
    """Coordinates PubMed advanced discovery searches and downloads."""

    def __init__(
        self,
        job_repository: DiscoverySearchJobRepository,
        query_builder: PubMedQueryBuilder,
        search_gateway: PubMedSearchGateway,
        pdf_gateway: PubMedPdfGateway,
        storage_coordinator: StorageOperationCoordinator | None = None,
    ) -> None:
        self._job_repository = job_repository
        self._query_builder = query_builder
        self._search_gateway = search_gateway
        self._pdf_gateway = pdf_gateway
        self._storage_coordinator = storage_coordinator

    async def run_pubmed_search(
        self,
        owner_id: UUID,
        request: RunPubmedSearchRequest,
    ) -> discovery_search_job.DiscoverySearchJob:
        """Validate parameters, persist a job, and execute the search."""

        self._query_builder.validate(request.parameters)
        query_preview = self._query_builder.build_query(request.parameters)
        now = datetime.now(UTC)
        job = discovery_search_job.DiscoverySearchJob(
            id=uuid4(),
            owner_id=owner_id,
            session_id=request.session_id,
            provider=discovery_preset.DiscoveryProvider.PUBMED,
            status=discovery_search_job.DiscoverySearchStatus.QUEUED,
            query_preview=query_preview,
            parameters=request.parameters,
            total_results=0,
            result_metadata={},
            created_at=now,
            updated_at=now,
        )
        job = self._job_repository.create(job)

        running_job = job.model_copy(
            update={
                "status": discovery_search_job.DiscoverySearchStatus.RUNNING,
                "updated_at": datetime.now(UTC),
            },
        )
        self._job_repository.update(running_job)

        try:
            payload = await self._search_gateway.run_search(request.parameters)
        except Exception as exc:  # pragma: no cover - defensive logging upstream
            failed_job = running_job.model_copy(
                update={
                    "status": discovery_search_job.DiscoverySearchStatus.FAILED,
                    "error_message": str(exc),
                    "updated_at": datetime.now(UTC),
                },
            )
            self._job_repository.update(failed_job)
            logger.exception(
                "PubMed search failed",
                extra={
                    "metric_type": "discovery_search",
                    "job_id": str(job.id),
                    "owner_id": str(owner_id),
                    "status": "failed",
                    "error": str(exc),
                },
            )
            raise
        else:
            metadata: JSONObject = {
                "article_ids": payload.article_ids,
                "preview_records": payload.preview_records,
            }
            completed = running_job.model_copy(
                update={
                    "status": discovery_search_job.DiscoverySearchStatus.COMPLETED,
                    "total_results": payload.total_count,
                    "result_metadata": metadata,
                    "completed_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                },
            )
            self._job_repository.update(completed)
            logger.info(
                "PubMed search completed",
                extra={
                    "metric_type": "discovery_search",
                    "job_id": str(job.id),
                    "owner_id": str(owner_id),
                    "status": "completed",
                    "result_count": payload.total_count,
                },
            )
            return completed

    def get_search_job(
        self,
        owner_id: UUID,
        job_id: UUID,
    ) -> discovery_search_job.DiscoverySearchJob | None:
        """Return a search job if it belongs to the requesting owner."""

        job = self._job_repository.get(job_id)
        if job is None or job.owner_id != owner_id:
            return None
        return job

    async def download_article_pdf(
        self,
        owner_id: UUID,
        request: PubmedDownloadRequest,
    ) -> StorageOperationRecord:
        """Download an article PDF and persist it via the storage coordinator."""

        job = self.get_search_job(owner_id, request.job_id)
        if job is None:
            msg = "Search job not found"
            raise ValueError(msg)
        if job.status != discovery_search_job.DiscoverySearchStatus.COMPLETED:
            msg = "Search job is not completed"
            raise ValueError(msg)

        article_ids_raw = job.result_metadata.get("article_ids", [])
        article_ids = (
            [str(value) for value in article_ids_raw]
            if isinstance(article_ids_raw, list)
            else []
        )
        if request.article_id not in article_ids:
            msg = "Article not part of the search results"
            raise ValueError(msg)

        if self._storage_coordinator is None:
            msg = "Storage coordinator not configured"
            raise RuntimeError(msg)

        pdf_bytes = await self._pdf_gateway.fetch_pdf(request.article_id)
        temp_path = self._write_temp_pdf(pdf_bytes)
        key = f"discovery/pubmed/{job.id}/{request.article_id}.pdf"
        try:
            metadata = self._build_pdf_metadata(
                job=job,
                owner_id=owner_id,
                article_id=request.article_id,
            )
            record = await self._storage_coordinator.store_for_use_case(
                StorageUseCase.PDF,
                key=key,
                file_path=temp_path,
                content_type="application/pdf",
                user_id=owner_id,
                metadata=metadata,
            )
        finally:
            temp_path.unlink(missing_ok=True)

        stored_assets = job.result_metadata.get("stored_assets", {})
        if not isinstance(stored_assets, dict):
            stored_assets = {}
        stored_assets[str(request.article_id)] = key
        updated_metadata = dict(job.result_metadata)
        updated_metadata["stored_assets"] = stored_assets

        updated_job = job.model_copy(
            update={
                "result_metadata": updated_metadata,
                "storage_key": key,
                "updated_at": datetime.now(UTC),
            },
        )
        self._job_repository.update(updated_job)

        logger.info(
            "PubMed PDF downloaded and stored",
            extra={
                "metric_type": "discovery_automation_coverage",
                "job_id": str(job.id),
                "article_id": request.article_id,
                "status": "success",
                "storage_key": key,
            },
        )

        return record

    @staticmethod
    def _write_temp_pdf(payload: bytes) -> Path:
        """Persist bytes to a temporary PDF path."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as handle:
            handle.write(payload)
            return Path(handle.name)

    @staticmethod
    def _build_pdf_metadata(
        *,
        job: discovery_search_job.DiscoverySearchJob,
        owner_id: UUID,
        article_id: str,
    ) -> JSONObject:
        return {
            PUBMED_STORAGE_METADATA_USE_CASE_KEY: StorageUseCase.PDF.value,
            PUBMED_STORAGE_METADATA_JOB_ID_KEY: str(job.id),
            PUBMED_STORAGE_METADATA_ARTICLE_ID_KEY: str(article_id),
            PUBMED_STORAGE_METADATA_OWNER_ID_KEY: str(owner_id),
            PUBMED_STORAGE_METADATA_PROVIDER_KEY: job.provider.value,
            PUBMED_STORAGE_METADATA_RETRYABLE_KEY: True,
        }


__all__ = [
    "PubMedDiscoveryService",
    "PubmedDownloadRequest",
    "RunPubmedSearchRequest",
    "PUBMED_STORAGE_METADATA_ARTICLE_ID_KEY",
    "PUBMED_STORAGE_METADATA_JOB_ID_KEY",
    "PUBMED_STORAGE_METADATA_OWNER_ID_KEY",
    "PUBMED_STORAGE_METADATA_PROVIDER_KEY",
    "PUBMED_STORAGE_METADATA_RETRYABLE_KEY",
    "PUBMED_STORAGE_METADATA_USE_CASE_KEY",
]
