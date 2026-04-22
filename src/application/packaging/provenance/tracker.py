"""
Provenance tracking utilities for packaging.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.value_objects.provenance import Provenance
    from src.type_definitions.common import JSONObject
    from src.type_definitions.packaging import (
        ProvenanceMetadata,
        ProvenanceSourceEntry,
    )


class ProvenanceTracker:
    """Track and serialize provenance information."""

    @staticmethod
    def serialize_provenance(
        provenance_records: list[Provenance],
    ) -> ProvenanceMetadata:
        """
        Serialize provenance records to JSON-LD format.

        Args:
            provenance_records: List of Provenance value objects

        Returns:
            Serialized provenance dictionary
        """
        sources: list[ProvenanceSourceEntry] = []

        for prov in provenance_records:
            source_info: ProvenanceSourceEntry = {
                "@type": "DataDownload",
                "name": prov.source.value,
                "datePublished": (
                    prov.acquired_at.isoformat()
                    if prov.acquired_at
                    else datetime.now(UTC).isoformat()
                ),
            }

            if prov.source_url:
                source_info["url"] = prov.source_url

            if prov.source_version:
                source_info["version"] = prov.source_version

            if prov.processing_steps:
                source_info["processingSteps"] = list(prov.processing_steps)

            if prov.quality_score is not None:
                source_info["qualityScore"] = prov.quality_score

            if prov.validation_status:
                source_info["validationStatus"] = prov.validation_status

            sources.append(source_info)

        return {"sources": sources}

    @staticmethod
    def write_provenance_metadata(
        provenance_records: list[Provenance],
        output_path: Path,
    ) -> None:
        """
        Write provenance metadata to file.

        Args:
            provenance_records: List of Provenance value objects
            output_path: Path to write metadata file
        """
        metadata = ProvenanceTracker.serialize_provenance(provenance_records)

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

    @staticmethod
    def enrich_with_provenance(
        metadata: JSONObject,
        provenance_records: list[Provenance],
    ) -> JSONObject:
        """
        Enrich metadata dictionary with provenance information.

        Args:
            metadata: Existing metadata dictionary
            provenance_records: List of Provenance value objects

        Returns:
            Enriched metadata dictionary
        """
        provenance_info = ProvenanceTracker.serialize_provenance(provenance_records)

        if "@graph" in metadata:
            graph_entities = metadata.get("@graph")
            if isinstance(graph_entities, list):
                sources_value = provenance_info.get("sources")
                if not isinstance(sources_value, list):
                    return metadata

                for entity in graph_entities:
                    if not isinstance(entity, dict):
                        continue
                    if entity.get("@id") != "./":
                        continue
                    has_part_value = entity.get("hasPart")
                    if isinstance(has_part_value, list):
                        has_part_list = has_part_value
                    else:
                        has_part_list = []
                        entity["hasPart"] = has_part_list
                    has_part_list.extend(sources_value)
                    break

        return metadata
