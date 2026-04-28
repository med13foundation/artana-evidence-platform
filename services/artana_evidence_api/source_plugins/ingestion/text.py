"""Text document-ingestion source plugin."""

from __future__ import annotations

from dataclasses import dataclass

from artana_evidence_api.source_plugins.ingestion.base import (
    DocumentIngestionSourceConfig,
    StaticDocumentIngestionSourcePlugin,
)
from artana_evidence_api.source_registry import SourceCapability, SourceDefinition

_SOURCE_DEFINITION = SourceDefinition(
    source_key="text",
    display_name="Text Evidence",
    description="User-provided text evidence or copied abstracts.",
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
    request_schema_ref="TextDocumentCreateRequest",
    result_capture="Text payloads become source documents.",
    proposal_flow="Extracted text creates reviewable proposals.",
)

_CONFIG = DocumentIngestionSourceConfig(
    definition=_SOURCE_DEFINITION,
    document_kind="text",
    accepted_content_types=("text/plain", "text/markdown"),
    extraction_entrypoint="document_extraction",
    limitations=(
        "User-provided text must be extracted and reviewed before promotion.",
    ),
)


@dataclass(frozen=True, slots=True)
class TextIngestionPlugin(StaticDocumentIngestionSourcePlugin):
    """Source-owned behavior for text ingestion context."""

    config: DocumentIngestionSourceConfig = _CONFIG


TEXT_INGESTION_PLUGIN = TextIngestionPlugin()

__all__ = ["TEXT_INGESTION_PLUGIN", "TextIngestionPlugin"]
