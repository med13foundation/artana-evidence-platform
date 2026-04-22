"""Helper utilities for Tier-2 content-enrichment orchestration."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src.domain.entities.user_data_source import SourceType
from src.type_definitions.common import JSONObject  # noqa: TC001
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from src.domain.agents.contexts.content_enrichment_context import (
        ContentEnrichmentContext,
    )
    from src.domain.agents.contracts.content_enrichment import (
        ContentEnrichmentContract,
    )
    from src.domain.entities.source_document import SourceDocument

PASS_THROUGH_SOURCE_TYPES = frozenset(
    {
        SourceType.CLINVAR,
        SourceType.MARRVEL,
        SourceType.API,
        SourceType.DATABASE,
        SourceType.FILE_UPLOAD,
    },
)
_FULL_TEXT_ACQUISITION_METHODS = frozenset({"pmc_oa", "europe_pmc", "publisher_pdf"})


@dataclass(frozen=True)
class StorageResult:
    """Resolved enrichment storage information."""

    storage_key: str
    content_hash: str | None
    content_length_chars: int


def extract_structured_payload(metadata: JSONObject) -> JSONObject:
    """Extract a normalized structured payload from document metadata."""
    raw_record = metadata.get("raw_record")
    if isinstance(raw_record, dict):
        return {str(key): to_json_value(value) for key, value in raw_record.items()}
    return {str(key): to_json_value(value) for key, value in metadata.items()}


def build_content_enrichment_context(
    document: SourceDocument,
) -> ContentEnrichmentContext:
    """Build an agent context payload from a source document."""
    from src.domain.agents.contexts.content_enrichment_context import (
        ContentEnrichmentContext,
    )

    return ContentEnrichmentContext(
        document_id=str(document.id),
        source_type=document.source_type.value,
        external_record_id=document.external_record_id,
        research_space_id=(
            str(document.research_space_id) if document.research_space_id else None
        ),
        raw_storage_key=document.raw_storage_key,
        existing_metadata=document.metadata,
    )


def serialize_contract_payload(contract: ContentEnrichmentContract) -> bytes | None:
    """Serialize contract content payload to bytes for hashing/storage."""
    if contract.content_payload is not None:
        serialized = json.dumps(contract.content_payload, default=str)
        return serialized.encode("utf-8")
    if contract.content_text is not None and contract.content_text.strip():
        return contract.content_text.strip().encode("utf-8")
    return None


def compute_character_count(
    contract: ContentEnrichmentContract,
    payload_bytes: bytes,
) -> int:
    """Resolve content character count from contract or payload bytes."""
    if contract.content_length_chars > 0:
        return contract.content_length_chars
    return len(payload_bytes.decode("utf-8", errors="replace"))


def infer_storage_format(content_format: str) -> tuple[str, str]:
    """Return file extension and MIME type for content format."""
    if content_format == "xml":
        return ("xml", "application/xml")
    if content_format == "structured_json":
        return ("json", "application/json")
    if content_format == "pdf_extracted":
        return ("txt", "text/plain")
    return ("txt", "text/plain")


def write_temp_payload(payload: bytes, *, suffix: str) -> Path:
    """Persist bytes to a temporary file and return its path."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(payload)
        return Path(handle.name)


def resolve_run_id(contract: ContentEnrichmentContract) -> str | None:
    """Normalize the optional agent run id from the contract."""
    run_id = contract.agent_run_id
    if run_id is None:
        return None
    normalized = run_id.strip()
    return normalized or None


def build_metadata_patch(  # noqa: PLR0913
    *,
    contract: ContentEnrichmentContract,
    run_id: str | None,
    pipeline_run_id: str | None = None,
    reason: str,
    content_storage_key: str | None,
    content_hash: str | None,
) -> JSONObject:
    """Build metadata patch persisted to the source document record."""
    full_text_acquired = (
        contract.decision == "enriched"
        and contract.acquisition_method in _FULL_TEXT_ACQUISITION_METHODS
        and contract.content_length_chars > 0
    )
    full_text_attempted = (
        contract.acquisition_method in _FULL_TEXT_ACQUISITION_METHODS
        or contract.warning is not None
    )
    fallback_reason: str | None = None
    if not full_text_acquired:
        if contract.warning is not None and contract.warning.strip():
            fallback_reason = contract.warning.strip()
        elif contract.acquisition_method == "pass_through":
            fallback_reason = "open_access_full_text_unavailable_fell_back_to_metadata"
        elif reason != "enriched":
            fallback_reason = reason

    metadata: JSONObject = {
        "content_enrichment_decision": contract.decision,
        "content_enrichment_reason": reason,
        "content_enrichment_acquisition_method": contract.acquisition_method,
        "content_enrichment_content_format": contract.content_format,
        "content_enrichment_content_length_chars": contract.content_length_chars,
        "content_enrichment_warning": contract.warning,
        "content_enrichment_rationale": contract.rationale,
        "content_enrichment_confidence_score": contract.confidence_score,
        "content_enrichment_agent_run_id": run_id,
        "content_enrichment_completed_at": datetime.now(UTC).isoformat(),
        "content_enrichment_storage_key": content_storage_key,
        "content_enrichment_content_hash": content_hash,
        "content_enrichment_full_text_attempted": full_text_attempted,
        "content_enrichment_full_text_acquired": full_text_acquired,
        "content_enrichment_full_text_source": (
            contract.acquisition_method if full_text_acquired else None
        ),
        "content_enrichment_fallback_reason": fallback_reason,
    }
    if pipeline_run_id is not None and pipeline_run_id.strip():
        metadata["pipeline_run_id"] = pipeline_run_id.strip()
    return metadata


def merge_metadata(
    base: JSONObject,
    patch: JSONObject,
) -> JSONObject:
    """Merge metadata payloads while normalizing values to JSONValue."""
    merged: JSONObject = {str(key): to_json_value(value) for key, value in base.items()}
    for key, value in patch.items():
        merged[str(key)] = to_json_value(value)
    return merged


__all__ = [
    "PASS_THROUGH_SOURCE_TYPES",
    "StorageResult",
    "build_metadata_patch",
    "build_content_enrichment_context",
    "compute_character_count",
    "extract_structured_payload",
    "infer_storage_format",
    "merge_metadata",
    "resolve_run_id",
    "serialize_contract_payload",
    "write_temp_payload",
]
