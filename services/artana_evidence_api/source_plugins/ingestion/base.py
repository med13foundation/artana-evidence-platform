"""Shared support for user-provided document evidence source plugins."""

from __future__ import annotations

from dataclasses import dataclass

from artana_evidence_api.source_plugins._helpers import (
    compact_json_object,
    metadata_from_definition,
    string_field,
)
from artana_evidence_api.source_plugins.contracts import (
    SourceDocumentIngestionContext,
    SourceDocumentInput,
    SourcePluginMetadata,
)
from artana_evidence_api.source_registry import SourceDefinition
from artana_evidence_api.types.common import JSONObject


@dataclass(frozen=True, slots=True)
class DocumentIngestionSourceConfig:
    """Source-specific configuration for document ingestion plugins."""

    definition: SourceDefinition
    document_kind: str
    accepted_content_types: tuple[str, ...]
    extraction_entrypoint: str
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StaticDocumentIngestionSourcePlugin:
    """Source-owned input validation and extraction-context construction."""

    config: DocumentIngestionSourceConfig

    @property
    def source_key(self) -> str:
        return self.config.definition.source_key

    @property
    def source_family(self) -> str:
        return self.config.definition.source_family

    @property
    def display_name(self) -> str:
        return self.config.definition.display_name

    @property
    def direct_search_supported(self) -> bool:
        return self.config.definition.direct_search_enabled

    @property
    def handoff_target_kind(self) -> str:
        return "source_document"

    @property
    def request_schema_ref(self) -> str | None:
        return self.config.definition.request_schema_ref

    @property
    def result_schema_ref(self) -> str | None:
        return self.config.definition.result_schema_ref

    @property
    def metadata(self) -> SourcePluginMetadata:
        return metadata_from_definition(self.config.definition)

    def source_definition(self) -> SourceDefinition:
        """Return this plugin's public source definition."""

        return self.config.definition

    def validate_document_input(self, document: SourceDocumentInput) -> None:
        """Validate source key, document kind, and content type."""

        if document.source_key != self.source_key:
            msg = f"{self.source_key} plugin cannot ingest '{document.source_key}'."
            raise ValueError(msg)
        if document.document_kind != self.config.document_kind:
            msg = (
                f"{self.display_name} expects document_kind "
                f"'{self.config.document_kind}', got '{document.document_kind}'."
            )
            raise ValueError(msg)
        if document.content_type not in self.config.accepted_content_types:
            accepted = ", ".join(self.config.accepted_content_types)
            msg = (
                f"{self.display_name} expects content_type in {accepted}; "
                f"got '{document.content_type}'."
            )
            raise ValueError(msg)

    def normalize_document_metadata(self, document: SourceDocumentInput) -> JSONObject:
        """Return stable metadata for a user-provided document."""

        self.validate_document_input(document)
        return compact_json_object(
            {
                **dict(document.metadata),
                "filename": document.filename,
                "document_kind": document.document_kind,
                "content_type": document.content_type,
                "title": string_field(document.metadata, "title"),
            },
        )

    def build_extraction_context(
        self,
        document: SourceDocumentInput,
    ) -> SourceDocumentIngestionContext:
        """Return extraction context without dispatching extraction side effects."""

        return SourceDocumentIngestionContext(
            source_key=self.source_key,
            source_family=self.source_family,
            display_name=self.display_name,
            document_kind=self.config.document_kind,
            content_type=document.content_type,
            normalized_metadata=self.normalize_document_metadata(document),
            extraction_entrypoint=self.config.extraction_entrypoint,
            limitations=self.config.limitations,
        )
