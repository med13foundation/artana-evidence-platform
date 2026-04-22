"""
Packaging-related typed contracts for Artana Resource Library.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NotRequired, TypedDict

if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import datetime

    from src.domain.value_objects.provenance import Provenance
    from src.type_definitions.common import JSONObject


class ROCrateFileEntryRequired(TypedDict):
    """Required fields for a RO-Crate file entry."""

    path: str


class ROCrateFileEntry(ROCrateFileEntryRequired, total=False):
    """File metadata published within the RO-Crate."""

    name: str
    description: str
    encodingFormat: str
    dateCreated: str


ProvenanceSourceEntry = TypedDict(
    "ProvenanceSourceEntry",
    {
        "@type": str,  # noqa: A003 - JSON-LD field name
        "name": str,
        "url": str,
        "contentUrl": str,
        "datePublished": str,
        "version": str,
        "processingSteps": list[str],
        "qualityScore": float,
        "validationStatus": str,
    },
    total=False,
)


class ProvenanceMetadata(TypedDict, total=False):
    """Collection of provenance sources included in metadata exports."""

    sources: list[ProvenanceSourceEntry]


class LicenseSourceEntry(TypedDict, total=False):
    """License information for an upstream data source."""

    source: str
    license: str


class LicenseRecord(LicenseSourceEntry, total=False):
    """Structured representation of a source license entry."""

    license_url: str
    attribution: str


class LicenseValidationResult(TypedDict):
    """Result of validating a license identifier."""

    valid: bool
    license: str
    message: str


class ComplianceSection(TypedDict, total=False):
    """Compliance block embedded in license manifests."""

    status: str
    issues: list[str]
    warnings: list[str]


class LicenseManifest(TypedDict):
    """License manifest structure."""

    package_license: str
    sources: list[LicenseRecord]
    compliance: NotRequired[ComplianceSection]


class LicenseInfo(TypedDict):
    """Basic license information."""

    id: str
    url: str
    name: str


class DatasetMetadataOptions(TypedDict, total=False):
    """Optional keyword arguments accepted by DatasetMetadata."""

    contributors: list[JSONObject]
    keywords: list[str]
    date_created: datetime | None
    date_modified: datetime | None
    date_published: datetime | None
    temporal_coverage: JSONObject | None
    spatial_coverage: JSONObject | None
    license_url: str | None
    rights_statement: str | None
    access_rights: str
    conforms_to: list[str]
    encoding_format: str | None
    compression_format: str | None
    byte_size: int | None
    provenance: Provenance | None


__all__ = [
    "ComplianceSection",
    "DatasetMetadataOptions",
    "LicenseInfo",
    "LicenseManifest",
    "LicenseRecord",
    "LicenseSourceEntry",
    "LicenseValidationResult",
    "ProvenanceMetadata",
    "ProvenanceSourceEntry",
    "ROCrateFileEntry",
    "ROCrateFileEntryRequired",
]
