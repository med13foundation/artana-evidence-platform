"""PDF document-ingestion source plugin."""

from __future__ import annotations

from dataclasses import dataclass

from artana_evidence_api.source_plugins.ingestion.base import (
    DocumentIngestionSourceConfig,
    StaticDocumentIngestionSourcePlugin,
)
from artana_evidence_api.source_registry import SourceCapability, SourceDefinition

_SOURCE_DEFINITION = SourceDefinition(
    source_key="pdf",
    display_name="PDF Uploads",
    description="User-provided PDF evidence.",
    source_family="document",
    capabilities=(
        SourceCapability.DOCUMENT_CAPTURE,
        SourceCapability.PROPOSAL_GENERATION,
        SourceCapability.RESEARCH_PLAN,
    ),
    direct_search_enabled=False,
    research_plan_enabled=True,
    default_research_plan_enabled=True,
    live_network_required=False,
    requires_credentials=False,
    request_schema_ref="DocumentUploadRequest",
    result_capture="Uploaded PDFs become source documents.",
    proposal_flow="Extracted PDF text creates reviewable proposals.",
)

_CONFIG = DocumentIngestionSourceConfig(
    definition=_SOURCE_DEFINITION,
    document_kind="pdf",
    accepted_content_types=("application/pdf",),
    extraction_entrypoint="document_extraction",
    limitations=(
        "Uploaded PDFs must be parsed, extracted, and reviewed before promotion.",
    ),
)


@dataclass(frozen=True, slots=True)
class PdfIngestionPlugin(StaticDocumentIngestionSourcePlugin):
    """Source-owned behavior for PDF ingestion context."""

    config: DocumentIngestionSourceConfig = _CONFIG


PDF_INGESTION_PLUGIN = PdfIngestionPlugin()

__all__ = ["PDF_INGESTION_PLUGIN", "PdfIngestionPlugin"]
