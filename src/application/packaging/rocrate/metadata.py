"""
Metadata generation utilities for RO-Crate packages.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from src.domain.value_objects.provenance import Provenance
    from src.type_definitions.common import JSONObject


class MetadataGenerator:
    """Generate rich metadata for RO-Crate packages."""

    @staticmethod
    def generate_provenance_metadata(
        provenance_records: list[Provenance],
    ) -> JSONObject:
        """
        Generate provenance metadata from provenance records.

        Args:
            provenance_records: List of Provenance value objects

        Returns:
            Provenance metadata dictionary
        """
        sources: list[JSONObject] = []
        for prov in provenance_records:
            source_info: JSONObject = {
                "@type": "DataDownload",
                "name": prov.source.value,
                "url": prov.source_url or "",
                "datePublished": (
                    prov.acquired_at.isoformat()
                    if prov.acquired_at
                    else datetime.now(UTC).isoformat()
                ),
            }

            if prov.source_version:
                source_info["version"] = prov.source_version

            if prov.processing_steps:
                source_info["processingSteps"] = prov.processing_steps

            sources.append(source_info)

        return {"sources": sources}

    @staticmethod
    def generate_license_metadata(license_id: str) -> JSONObject:
        """
        Generate license metadata.

        Args:
            license_id: License identifier (e.g., "CC-BY-4.0")

        Returns:
            License metadata dictionary
        """
        license_urls = {
            "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
            "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
            "MIT": "https://opensource.org/licenses/MIT",
        }

        return {
            "@id": license_urls.get(
                license_id,
                f"https://spdx.org/licenses/{license_id}.html",
            ),
            "@type": "CreativeWork",
            "name": license_id,
            "url": license_urls.get(license_id, ""),
        }

    @staticmethod
    def generate_file_metadata(
        file_path: Path,
        description: str | None = None,
        mime_type: str | None = None,
    ) -> JSONObject:
        """
        Generate metadata for a file.

        Args:
            file_path: Path to the file
            description: Optional file description
            mime_type: Optional MIME type

        Returns:
            File metadata dictionary
        """
        metadata: JSONObject = {
            "@id": str(file_path),
            "@type": "File",
            "name": file_path.name,
        }

        if description:
            metadata["description"] = description

        if mime_type:
            metadata["encodingFormat"] = mime_type

        # Try to detect MIME type if not provided
        if not mime_type:
            ext = file_path.suffix.lower()
            mime_map = {
                ".json": "application/json",
                ".csv": "text/csv",
                ".tsv": "text/tab-separated-values",
                ".xml": "application/xml",
                ".txt": "text/plain",
            }
            if ext in mime_map:
                metadata["encodingFormat"] = mime_map[ext]

        return metadata

    @staticmethod
    def generate_dataset_metadata(  # noqa: PLR0913 - dataset metadata fields
        name: str,
        description: str,
        version: str,
        license_id: str,
        author: str,
        keywords: list[str] | None = None,
    ) -> JSONObject:
        """
        Generate root dataset metadata.

        Args:
            name: Dataset name
            description: Dataset description
            version: Dataset version
            license_id: License identifier
            author: Author/organization name
            keywords: Optional keywords

        Returns:
            Dataset metadata dictionary
        """
        return {
            "@id": "./",
            "@type": "Dataset",
            "name": name,
            "description": description,
            "version": version,
            "license": license_id,
            "datePublished": datetime.now(UTC).isoformat(),
            "creator": {
                "@type": "Organization",
                "name": author,
            },
            "keywords": keywords or [],
        }
