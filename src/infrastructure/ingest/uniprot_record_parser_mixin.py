"""UniProt record normalization helpers.

Contains mixin with extraction logic so the ingestor remains maintainable.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from .uniprot_record_extraction_mixin import UniProtRecordExtractionMixin

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.type_definitions.common import RawRecord

logger = logging.getLogger(__name__)
PROTEIN_RELEVANCE_THRESHOLD: int = 5


class UniProtRecordParserMixin(UniProtRecordExtractionMixin):
    def _parse_uniprot_record(self, record: RawRecord) -> RawRecord:
        """
        Parse and normalize UniProt record data.

        Args:
            record: Raw UniProt record

        Returns:
            Normalized protein record
        """
        try:
            # Extract basic information
            entry_audit = record.get("entryAudit")
            last_updated = ""
            if isinstance(entry_audit, dict):
                last_updated_value = entry_audit.get("lastAnnotationUpdateDate")
                if isinstance(last_updated_value, str):
                    last_updated = last_updated_value

            parsed: RawRecord = {
                "uniprot_id": record.get("primaryAccession", ""),
                "entry_name": record.get("uniProtkbId", ""),
                "protein_name": self._extract_protein_name(record),
                "alternative_names": self._extract_alternative_names(record),
                "gene_name": self._extract_gene_name(record),
                "gene_aliases": self._extract_gene_aliases(record),
                "organism": self._extract_organism(record),
                "sequence": self._extract_sequence(record),
                "function": self._extract_function(record),
                "subcellular_location": self._extract_subcellular_location(record),
                "pathway": self._extract_pathway(record),
                "disease_associations": self._extract_disease_associations(record),
                "isoforms": self._extract_isoforms(record),
                "domains": self._extract_domains(record),
                "ptm_sites": self._extract_ptm_sites(record),
                "interactions": self._extract_interactions(record),
                "references": self._extract_references(record),
                "last_updated": last_updated,
            }

            # Add MED13-specific analysis
            parsed["med13_analysis"] = self._analyze_med13_relevance(parsed)

        except Exception as e:  # noqa: BLE001
            return {
                "parsing_error": str(e),
                "uniprot_id": record.get("primaryAccession", "unknown"),
                "raw_record": json.dumps(record)[:1000],  # First 1000 chars
            }
        else:
            return parsed

    def _analyze_med13_relevance(self, record: RawRecord) -> RawRecord:  # noqa: C901
        """
        Analyze MED13 relevance of protein record.

        Args:
            record: Parsed protein record

        Returns:
            Relevance analysis
        """
        relevance_score = 0
        reasons = []

        # Check gene name
        gene_name_value = record.get("gene_name")
        gene_name = gene_name_value.lower() if isinstance(gene_name_value, str) else ""
        if "med13" in gene_name:
            relevance_score += 10
            reasons.append("MED13 gene")

        # Check protein name
        protein_name_value = record.get("protein_name")
        protein_name = (
            protein_name_value.lower() if isinstance(protein_name_value, str) else ""
        )
        if "mediator" in protein_name and "13" in protein_name:
            relevance_score += 8
            reasons.append("Mediator complex subunit 13")

        # Check function descriptions
        functions = record.get("function")
        if isinstance(functions, list):
            for func in functions:
                if not isinstance(func, str):
                    continue
                func_lower = func.lower()
                if "mediator" in func_lower and "transcription" in func_lower:
                    relevance_score += 5
                    reasons.append("Mediator complex function")
                    break

        # Check disease associations
        diseases = record.get("disease_associations")
        med13_diseases = ["intellectual disability", "developmental disorder", "autism"]
        if isinstance(diseases, list):
            for disease in diseases:
                if not isinstance(disease, dict):
                    continue
                disease_name_raw = disease.get("name")
                disease_name = (
                    disease_name_raw.lower()
                    if isinstance(disease_name_raw, str)
                    else ""
                )
                if any(d in disease_name for d in med13_diseases):
                    relevance_score += 3
                    reasons.append(f"Disease association: {disease.get('name')}")

        return {
            "score": relevance_score,
            "reasons": reasons,
            "is_relevant": relevance_score >= PROTEIN_RELEVANCE_THRESHOLD,
        }
