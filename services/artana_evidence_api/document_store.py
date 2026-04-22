"""Service-local document storage contracts for graph-harness workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from threading import Lock
from uuid import UUID, uuid4

from artana_evidence_api.types.common import JSONObject  # noqa: TC001


class _DocumentTitleHTMLStripper(HTMLParser):
    """Collect the visible text content from one HTML fragment."""

    def __init__(self) -> None:
        super().__init__()
        self._fragments: list[str] = []

    def handle_data(self, data: str) -> None:
        self._fragments.append(data)

    def text_content(self) -> str:
        return "".join(self._fragments)


def normalize_document_title(title: str) -> str:
    """Normalize one document title to plain text with safe angle brackets."""
    stripped_title = title.strip()
    if stripped_title == "":
        msg = "Document title is required"
        raise ValueError(msg)

    parser = _DocumentTitleHTMLStripper()
    parser.feed(stripped_title)
    parser.close()
    normalized_text = " ".join(parser.text_content().split()).strip()
    if normalized_text == "":
        msg = "Document title must contain visible text"
        raise ValueError(msg)
    return normalized_text.replace("<", "&lt;").replace(">", "&gt;")


@dataclass(frozen=True, slots=True)
class HarnessDocumentRecord:
    """One persisted document tracked by the harness layer."""

    id: str
    space_id: str
    created_by: str
    title: str
    source_type: str
    filename: str | None
    media_type: str
    sha256: str
    byte_size: int
    page_count: int | None
    text_content: str
    text_excerpt: str
    raw_storage_key: str | None
    enriched_storage_key: str | None
    ingestion_run_id: str
    last_enrichment_run_id: str | None
    last_extraction_run_id: str | None
    enrichment_status: str
    extraction_status: str
    metadata: JSONObject
    created_at: datetime
    updated_at: datetime


class HarnessDocumentStore:
    """Store and retrieve tracked documents for graph-harness workflows."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._documents: dict[str, HarnessDocumentRecord] = {}
        self._document_ids_by_space: dict[str, list[str]] = {}

    def create_document(  # noqa: PLR0913
        self,
        *,
        document_id: UUID | str | None = None,
        space_id: UUID | str,
        created_by: UUID | str,
        title: str,
        source_type: str,
        filename: str | None,
        media_type: str,
        sha256: str,
        byte_size: int,
        page_count: int | None,
        text_content: str,
        raw_storage_key: str | None = None,
        enriched_storage_key: str | None = None,
        ingestion_run_id: UUID | str,
        last_enrichment_run_id: UUID | str | None = None,
        enrichment_status: str,
        extraction_status: str,
        metadata: JSONObject | None = None,
    ) -> HarnessDocumentRecord:
        """Persist one tracked document."""
        now = datetime.now(UTC)
        text_excerpt = text_content.strip().replace("\n", " ")[:280]
        normalized_title = normalize_document_title(title)
        record = HarnessDocumentRecord(
            id=str(uuid4()) if document_id is None else str(document_id),
            space_id=str(space_id),
            created_by=str(created_by),
            title=normalized_title,
            source_type=source_type,
            filename=filename,
            media_type=media_type,
            sha256=sha256,
            byte_size=byte_size,
            page_count=page_count,
            text_content=text_content,
            text_excerpt=text_excerpt,
            raw_storage_key=raw_storage_key,
            enriched_storage_key=enriched_storage_key,
            ingestion_run_id=str(ingestion_run_id),
            last_enrichment_run_id=(
                str(last_enrichment_run_id)
                if last_enrichment_run_id is not None
                else None
            ),
            last_extraction_run_id=None,
            enrichment_status=enrichment_status,
            extraction_status=extraction_status,
            metadata={} if metadata is None else dict(metadata),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._documents[record.id] = record
            self._document_ids_by_space.setdefault(record.space_id, []).append(
                record.id,
            )
        return record

    def list_documents(
        self,
        *,
        space_id: UUID | str,
    ) -> list[HarnessDocumentRecord]:
        """List tracked documents for one research space."""
        normalized_space_id = str(space_id)
        with self._lock:
            records = [
                self._documents[document_id]
                for document_id in self._document_ids_by_space.get(
                    normalized_space_id,
                    [],
                )
            ]
        return sorted(records, key=lambda record: record.updated_at, reverse=True)

    def find_document_by_sha256(
        self,
        *,
        space_id: UUID | str,
        sha256: str,
    ) -> HarnessDocumentRecord | None:
        """Return the most recent tracked document with one matching content hash."""
        normalized_space_id = str(space_id)
        with self._lock:
            records = [
                self._documents[document_id]
                for document_id in self._document_ids_by_space.get(
                    normalized_space_id,
                    [],
                )
            ]
        for record in sorted(records, key=lambda item: item.updated_at, reverse=True):
            if record.sha256 == sha256:
                return record
        return None

    def count_documents(
        self,
        *,
        space_id: UUID | str,
    ) -> int:
        """Return how many tracked documents belong to one research space."""
        normalized_space_id = str(space_id)
        with self._lock:
            return len(self._document_ids_by_space.get(normalized_space_id, []))

    def get_document(
        self,
        *,
        space_id: UUID | str,
        document_id: UUID | str,
    ) -> HarnessDocumentRecord | None:
        """Return one tracked document from the store."""
        with self._lock:
            record = self._documents.get(str(document_id))
        if record is None or record.space_id != str(space_id):
            return None
        return record

    def update_document(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        document_id: UUID | str,
        title: str | None = None,
        text_content: str | None = None,
        page_count: int | None = None,
        raw_storage_key: str | None = None,
        enriched_storage_key: str | None = None,
        last_enrichment_run_id: UUID | str | None = None,
        last_extraction_run_id: UUID | str | None = None,
        enrichment_status: str | None = None,
        extraction_status: str | None = None,
        metadata_patch: JSONObject | None = None,
    ) -> HarnessDocumentRecord | None:
        """Update one tracked document."""
        existing = self.get_document(space_id=space_id, document_id=document_id)
        if existing is None:
            return None
        resolved_text_content = (
            text_content if isinstance(text_content, str) else existing.text_content
        )
        resolved_title = existing.title
        if isinstance(title, str) and title.strip() != "":
            resolved_title = normalize_document_title(title)
        updated = HarnessDocumentRecord(
            id=existing.id,
            space_id=existing.space_id,
            created_by=existing.created_by,
            title=resolved_title,
            source_type=existing.source_type,
            filename=existing.filename,
            media_type=existing.media_type,
            sha256=existing.sha256,
            byte_size=existing.byte_size,
            page_count=page_count if page_count is not None else existing.page_count,
            text_content=resolved_text_content,
            text_excerpt=resolved_text_content.strip().replace("\n", " ")[:280],
            raw_storage_key=(
                raw_storage_key
                if isinstance(raw_storage_key, str) and raw_storage_key.strip() != ""
                else existing.raw_storage_key
            ),
            enriched_storage_key=(
                enriched_storage_key
                if isinstance(enriched_storage_key, str)
                and enriched_storage_key.strip() != ""
                else existing.enriched_storage_key
            ),
            ingestion_run_id=existing.ingestion_run_id,
            last_enrichment_run_id=(
                str(last_enrichment_run_id)
                if last_enrichment_run_id is not None
                else existing.last_enrichment_run_id
            ),
            last_extraction_run_id=(
                str(last_extraction_run_id)
                if last_extraction_run_id is not None
                else existing.last_extraction_run_id
            ),
            enrichment_status=(
                enrichment_status
                if isinstance(enrichment_status, str)
                and enrichment_status.strip() != ""
                else existing.enrichment_status
            ),
            extraction_status=(
                extraction_status
                if isinstance(extraction_status, str)
                and extraction_status.strip() != ""
                else existing.extraction_status
            ),
            metadata={
                **existing.metadata,
                **({} if metadata_patch is None else dict(metadata_patch)),
            },
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
        )
        with self._lock:
            self._documents[existing.id] = updated
        return updated


__all__ = [
    "HarnessDocumentRecord",
    "HarnessDocumentStore",
    "normalize_document_title",
]
