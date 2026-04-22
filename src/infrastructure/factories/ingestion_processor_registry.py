"""Extraction processor registry for scheduled ingestion runs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.entities.user_data_source import SourceType
from src.infrastructure.extraction import (
    AiRequiredPubMedExtractionProcessor,
    ClinVarExtractionProcessor,
    MarrvelExtractionProcessor,
    UniProtExtractionProcessor,
)

if TYPE_CHECKING:
    from src.application.services.ports.extraction_processor_port import (
        ExtractionProcessorPort,
    )


def build_processor_registry() -> dict[str, ExtractionProcessorPort]:
    """Build the extraction processor registry with lazy translational imports."""
    from src.infrastructure.extraction.alphafold_extraction_processor import (
        AlphaFoldExtractionProcessor,
    )
    from src.infrastructure.extraction.clinicaltrials_extraction_processor import (
        ClinicalTrialsExtractionProcessor,
    )
    from src.infrastructure.extraction.drugbank_extraction_processor import (
        DrugBankExtractionProcessor,
    )
    from src.infrastructure.extraction.mgi_extraction_processor import (
        MGIExtractionProcessor,
    )
    from src.infrastructure.extraction.zfin_extraction_processor import (
        ZFINExtractionProcessor,
    )

    return {
        SourceType.PUBMED.value: AiRequiredPubMedExtractionProcessor(),
        SourceType.CLINVAR.value: ClinVarExtractionProcessor(),
        SourceType.MARRVEL.value: MarrvelExtractionProcessor(),
        SourceType.UNIPROT.value: UniProtExtractionProcessor(),
        SourceType.DRUGBANK.value: DrugBankExtractionProcessor(),
        SourceType.ALPHAFOLD.value: AlphaFoldExtractionProcessor(),
        SourceType.CLINICAL_TRIALS.value: ClinicalTrialsExtractionProcessor(),
        SourceType.MGI.value: MGIExtractionProcessor(),
        SourceType.ZFIN.value: ZFINExtractionProcessor(),
    }


__all__ = ["build_processor_registry"]
