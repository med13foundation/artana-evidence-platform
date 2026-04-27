"""Source-document identity helpers for source-search selection deduplication."""

from __future__ import annotations

from artana_evidence_api.document_store import HarnessDocumentRecord
from artana_evidence_api.evidence_selection_candidates import (
    record_dedup_key,
    record_hash,
)
from artana_evidence_api.types.common import json_object_or_empty


def source_document_dedup_key(document: HarnessDocumentRecord) -> str | None:
    """Return the source-search dedup key stored on a harness document."""

    metadata = document.metadata
    search_id = metadata.get("source_search_id")
    record_index = metadata.get("selected_record_index")
    if isinstance(search_id, str) and isinstance(record_index, int):
        return record_dedup_key(
            source_key=document.source_type,
            search_id=search_id,
            record_index=record_index,
        )
    return None


def source_document_record_hash(document: HarnessDocumentRecord) -> str | None:
    """Return the selected source-record hash stored on a harness document."""

    selected_record = document.metadata.get("selected_record")
    if isinstance(selected_record, dict):
        return record_hash(json_object_or_empty(selected_record))
    return None


__all__ = [
    "source_document_dedup_key",
    "source_document_record_hash",
]
