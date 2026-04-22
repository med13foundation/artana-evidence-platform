"""
Exact matching mapper for the ingestion pipeline.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from artana_evidence_db.runtime import (
    create_graph_domain_context_policy,
    resolve_graph_domain_context,
)

from src.infrastructure.ingestion.types import MappedObservation, RawRecord

if TYPE_CHECKING:
    from artana_evidence_db.semantic_ports import DictionaryPort

    from src.type_definitions.common import JSONObject


class ExactMapper:
    """
    Maps raw records to observations using exact synonym lookup in the dictionary.
    """

    def __init__(self, dictionary_repository: DictionaryPort) -> None:
        self.dictionary_repo = dictionary_repository

    def map(self, record: RawRecord) -> list[MappedObservation]:
        """
        Map a raw record to a list of observations.
        Iterates through the data dictionary and attempts to match keys to variables.
        """
        observations: list[MappedObservation] = []

        for key, value in record.data.items():
            # Skip empty values
            if value is None or value == "":
                continue

            domain_context = self._extract_domain_context(record)
            # Try to find a variable definition matching the key
            # The repository method handles case-insensitivity
            variable = self.dictionary_repo.resolve_synonym(
                key,
                domain_context=domain_context,
            )

            if variable:
                # We found a match! Create an observation
                # TODO: Identify subject anchor and observed_at from the record or metadata
                # For now, we assume these are passed in a standard way or handled later
                # We'll put placeholders or extract generic fields if present

                # Subject anchor logic would go here. For now, we extract from generic keys
                # or pass empty if not found, to be handled by a specific SubjectResolver or Context
                subject_anchor = self._extract_subject_anchor(record)

                # Timestamp logic
                observed_at = self._extract_timestamp(record)

                observations.append(
                    MappedObservation(
                        subject_anchor=subject_anchor,
                        variable_id=variable.id,
                        value=value,
                        unit=None,  # Unit extraction is a separate concern or needs structured value
                        observed_at=observed_at,
                        provenance={
                            "source_id": record.source_id,
                            "original_key": key,
                            "method": "exact_match",
                            "metadata": record.metadata,
                        },
                    ),
                )

        return observations

    def _extract_subject_anchor(self, record: RawRecord) -> JSONObject:
        """Extract subject anchor from record data (e.g. MRN, Email)."""
        # This implementation is intentionally simple and deterministic.
        # Source-specific anchor extraction can evolve into dedicated mappers.
        anchors: JSONObject = {}

        record_type = record.metadata.get("type")
        entity_type = record.metadata.get("entity_type")
        if (
            isinstance(record_type, str)
            and record_type == "pubmed"
            and entity_type == "PUBLICATION"
        ):
            # Publications resolve by stable identifiers (pmid/doi) and optionally title.
            for key in ["pmid", "doi", "title"]:
                if key in record.data and record.data[key] is not None:
                    anchors[key] = record.data[key]
            return anchors

        # Common anchor keys across clinical/genomics payloads.
        for key in [
            "mrn",
            "issuer",
            "patient_id",
            "email",
            "hgnc_id",
            "gene_symbol",
            "clinvar_id",
            "variant_id",
            "variation_id",
            "hgvs_notation",
            "hgvs",
            "rsid",
            "display_label",
            "label",
            "mechanism_name",
        ]:
            if key in record.data and record.data[key] is not None:
                anchors[key] = record.data[key]

        # Extraction-stage payloads can carry stable identifiers in metadata.
        for key in ["source_record_id", "external_record_id"]:
            if key in anchors:
                continue
            raw_value = record.metadata.get(key)
            if raw_value is not None and raw_value != "":
                anchors[key] = raw_value

        # Last-resort deterministic fallback so ingestion can still resolve/create.
        if not anchors and record.source_id.strip():
            anchors["source_id"] = record.source_id.strip()
        return anchors

    @staticmethod
    def _extract_domain_context(record: RawRecord) -> str | None:
        raw_source_type = record.metadata.get("type")
        source_type = raw_source_type if isinstance(raw_source_type, str) else None
        return resolve_graph_domain_context(
            domain_context_policy=create_graph_domain_context_policy(),
            metadata=record.metadata,
            source_type=source_type,
            fallback=None,
        )

    def _extract_timestamp(self, record: RawRecord) -> datetime | None:
        """Extract timestamp from record data."""
        # Check standard keys
        for key in [
            "timestamp",
            "date",
            "created_at",
            "observed_at",
            "publication_date",
        ]:
            if key in record.data:
                val = record.data[key]
                if isinstance(val, str):
                    try:
                        dt = datetime.fromisoformat(val)
                    except ValueError:
                        continue

                    # Normalize naive timestamps to UTC for TIMESTAMPTZ columns.
                    if dt.tzinfo is None:
                        from datetime import UTC

                        dt = dt.replace(tzinfo=UTC)
                    return dt
        return None
