"""
Publication extraction API schemas for Artana Resource Library.

Pydantic models for extraction-related API responses.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from src.type_definitions.common import ExtractionFactType, JSONObject


class ExtractionOutcome(str, Enum):
    """Extraction outcome status."""

    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExtractionFactResponse(BaseModel):
    """Schema for a single extracted fact."""

    model_config = ConfigDict(strict=True)

    fact_type: ExtractionFactType = Field(..., description="Type of extracted fact")
    value: str = Field(..., description="Extracted value")
    normalized_id: str | None = Field(
        None,
        description="Normalized identifier (e.g., HPO ID)",
    )
    source: str | None = Field(None, description="Source text segment")
    attributes: JSONObject | None = Field(
        None,
        description="Additional fact metadata",
    )


class PublicationExtractionResponse(BaseModel):
    """Extraction output response schema."""

    model_config = ConfigDict(strict=True)

    id: str = Field(..., description="Extraction record identifier")
    publication_id: int | None = Field(
        None,
        description="Publication database ID when linked",
    )
    pubmed_id: str | None = Field(None, description="PubMed identifier")
    source_id: str = Field(..., description="Data source identifier")
    ingestion_job_id: str = Field(..., description="Ingestion job identifier")
    queue_item_id: str = Field(..., description="Extraction queue item identifier")
    status: ExtractionOutcome = Field(..., description="Extraction outcome")
    extraction_version: int = Field(..., description="Extraction version")
    processor_name: str = Field(..., description="Extraction processor name")
    processor_version: str | None = Field(
        None,
        description="Extraction processor version",
    )
    text_source: str = Field(..., description="Text source used for extraction")
    document_reference: str | None = Field(
        None,
        description="Storage key or URL for the processed document",
    )
    facts: list[ExtractionFactResponse] = Field(
        default_factory=list,
        description="Extracted facts",
    )
    metadata: JSONObject = Field(
        default_factory=dict,
        description="Extraction metadata",
    )
    extracted_at: datetime = Field(..., description="Extraction timestamp")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Record update timestamp")


class PublicationExtractionDocumentResponse(BaseModel):
    """Response schema for extraction document URLs."""

    model_config = ConfigDict(strict=True)

    extraction_id: str = Field(..., description="Extraction record identifier")
    document_reference: str = Field(
        ...,
        description="Storage key for the processed document",
    )
    url: str = Field(..., description="Resolved URL or path to the document")


__all__ = [
    "ExtractionFactResponse",
    "ExtractionOutcome",
    "PublicationExtractionDocumentResponse",
    "PublicationExtractionResponse",
]
