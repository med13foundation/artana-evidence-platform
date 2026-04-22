"""Extraction processor adapters."""

from src.infrastructure.extraction.ai_required_pubmed_extraction_processor import (
    AiRequiredPubMedExtractionProcessor,
)
from src.infrastructure.extraction.clinvar_extraction_processor import (
    ClinVarExtractionProcessor,
)
from src.infrastructure.extraction.marrvel_extraction_processor import (
    MarrvelExtractionProcessor,
)
from src.infrastructure.extraction.placeholder_extraction_processor import (
    PlaceholderExtractionProcessor,
)
from src.infrastructure.extraction.uniprot_extraction_processor import (
    UniProtExtractionProcessor,
)

__all__ = [
    "AiRequiredPubMedExtractionProcessor",
    "ClinVarExtractionProcessor",
    "MarrvelExtractionProcessor",
    "PlaceholderExtractionProcessor",
    "UniProtExtractionProcessor",
]
