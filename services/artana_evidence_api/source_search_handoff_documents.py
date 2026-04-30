"""Document-building helpers for source-search handoffs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from artana_evidence_api.direct_source_search import DirectSourceSearchRecord
from artana_evidence_api.document_extraction import sha256_hex
from artana_evidence_api.document_store import (
    HarnessDocumentRecord,
    HarnessDocumentStore,
)
from artana_evidence_api.source_adapters import source_adapter
from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    SourceResultCapture,
    source_result_capture_metadata,
)
from artana_evidence_api.types.common import JSONObject, JSONValue


@dataclass(frozen=True, slots=True)
class _SelectedSourceRecord:
    index: int
    record: JSONObject
    external_id: str | None


def _provider_external_id(*, source_key: str, record: JSONObject) -> str | None:
    adapter = source_adapter(source_key)
    return adapter.provider_external_id(record) if adapter is not None else None


def _record_supports_variant_aware(
    *,
    source_key: str,
    selected: _SelectedSourceRecord,
) -> bool:
    adapter = source_adapter(source_key)
    return bool(
        adapter is not None
        and adapter.recommends_variant_aware(selected.record),
    )


def _document_capture(
    *,
    source_key: str,
    search_id: UUID,
    document_id: UUID,
    run_id: str,
    source_search: DirectSourceSearchRecord,
    selected: _SelectedSourceRecord,
) -> SourceResultCapture:
    metadata = source_result_capture_metadata(
        source_key=source_key,
        capture_stage=SourceCaptureStage.SOURCE_DOCUMENT,
        capture_method="direct_source_handoff",
        locator=f"{source_key}:search:{search_id}:record:{selected.index}",
        external_id=selected.external_id,
        retrieved_at=datetime.now(UTC),
        run_id=run_id,
        search_id=str(search_id),
        document_id=str(document_id),
        query=source_search.query,
        query_payload=source_search.source_capture.query_payload,
        result_count=1,
        provenance={
            **source_search.source_capture.provenance,
            "selected_record_index": selected.index,
        },
    )
    return SourceResultCapture.model_validate(metadata)


def _create_handoff_document(
    *,
    document_store: HarnessDocumentStore,
    source_key: str,
    space_id: UUID,
    created_by: UUID | str,
    document_id: UUID,
    ingestion_run_id: str,
    source_search: DirectSourceSearchRecord,
    selected: _SelectedSourceRecord,
    source_capture: SourceResultCapture,
    request_metadata: JSONObject,
) -> HarnessDocumentRecord:
    text = _source_record_text(
        source_key=source_key,
        source_search=source_search,
        selected=selected,
    )
    encoded = text.encode("utf-8")
    title = _source_record_title(
        source_key=source_key,
        source_search=source_search,
        selected=selected,
    )
    normalized_record = _normalized_source_record(
        source_key=source_key,
        selected=selected,
    )
    metadata: JSONObject = {
        "source_capture": source_capture.to_metadata(),
        "source_family": _source_family(source_key),
        "normalization_profile": f"{source_key}_source_document_v1",
        "source_search_id": str(source_search.id),
        "source_search_handoff": True,
        "selected_record_index": selected.index,
        "selected_record": selected.record,
        "normalized_record": normalized_record,
        "client_metadata": request_metadata,
        "variant_aware_recommended": _record_supports_variant_aware(
            source_key=source_key,
            selected=selected,
        ),
    }
    return document_store.create_document(
        document_id=document_id,
        space_id=space_id,
        created_by=created_by,
        title=title,
        source_type=source_key,
        filename=None,
        media_type="application/json",
        sha256=sha256_hex(encoded),
        byte_size=len(encoded),
        page_count=None,
        text_content=text,
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=ingestion_run_id,
        last_enrichment_run_id=None,
        enrichment_status="completed",
        extraction_status="pending",
        metadata=metadata,
    )


def _source_record_text(
    *,
    source_key: str,
    source_search: DirectSourceSearchRecord,
    selected: _SelectedSourceRecord,
) -> str:
    normalized_record = _normalized_source_record(
        source_key=source_key,
        selected=selected,
    )
    if normalized_record:
        lines = [
            f"# {_source_family(source_key).replace('_', ' ').title()} Source Record",
            "",
            f"Source: {source_key}",
            f"Search ID: {source_search.id}",
            f"Query: {source_search.query}",
            f"Record index: {selected.index}",
        ]
        if selected.external_id is not None:
            lines.append(f"External ID: {selected.external_id}")
        lines.extend(["", "## Normalized Fields"])
        for key, value in normalized_record.items():
            if _is_empty_json_value(value):
                continue
            lines.append(f"- {key}: {_display_json_value(value)}")
        lines.extend(
            [
                "",
                "## Raw Record JSON",
                json.dumps(
                    selected.record,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
            ],
        )
        return "\n".join(lines)
    return json.dumps(
        {
            "source_key": source_key,
            "query": source_search.query,
            "search_id": str(source_search.id),
            "record_index": selected.index,
            "record": selected.record,
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def _source_record_title(
    *,
    source_key: str,
    source_search: DirectSourceSearchRecord,
    selected: _SelectedSourceRecord,
) -> str:
    for key in (
        "title",
        "name",
        "panel_name",
        "gene_symbol",
        "uniprot_id",
        "brief_title",
    ):
        value: JSONValue | None = selected.record.get(key)
        if isinstance(value, str) and value.strip():
            return f"{source_key}: {value.strip()}"
    if selected.external_id is not None:
        return f"{source_key}: {selected.external_id}"
    return f"{source_key}: {source_search.query}"


def _source_family(source_key: str) -> str:
    adapter = source_adapter(source_key)
    return adapter.source_family if adapter is not None else "document"


def _normalized_source_record(
    *,
    source_key: str,
    selected: _SelectedSourceRecord,
) -> JSONObject:
    adapter = source_adapter(source_key)
    if adapter is not None:
        return adapter.normalize_record(selected.record)
    return {}


def _display_json_value(value: JSONValue) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, int | float | bool) or value is None:
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _is_empty_json_value(value: JSONValue | None) -> bool:
    if value is None:
        return True
    if value == "":
        return True
    return value == []

__all__ = [
    "_SelectedSourceRecord",
    "_create_handoff_document",
    "_document_capture",
    "_provider_external_id",
]
