"""Normalize publication identifiers for consistent cross-referencing."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from src.domain.transform.normalizers.publication_normalizer_mixin import (
    PublicationNormalizationMixin,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.domain.transform.normalizers.publication_models import (
        NormalizedPublication,
    )
    from src.type_definitions.common import JSONObject


class PublicationNormalizer(PublicationNormalizationMixin):
    """
    Normalizes publication identifiers from different sources.

    Handles standardization of publication IDs (PubMed, DOI, PMC, etc.)
    and metadata for consistent representation.
    """

    def __init__(self) -> None:
        # Identifier patterns
        self.identifier_patterns = {
            "pubmed": re.compile(r"^\d+$"),  # PubMed IDs are just numbers
            "doi": re.compile(r"^10\.\d{4,9}/[-._;()/:A-Z0-9]+$", re.IGNORECASE),
            "pmc": re.compile(r"^PMC\d+$", re.IGNORECASE),
        }

        # Cache for normalized publications
        self.normalized_cache: dict[str, NormalizedPublication] = {}

    def normalize(
        self,
        raw_publication_data: JSONObject,
        source: str = "unknown",
    ) -> NormalizedPublication | None:
        """
        Normalize publication data from various sources.

        Args:
            raw_publication_data: Raw publication data from parsers
            source: Source of the data (pubmed, uniprot, etc.)

        Returns:
            Normalized publication object or None if normalization fails
        """
        try:
            if source.lower() == "pubmed":
                return self._normalize_pubmed_publication(raw_publication_data)
            if source.lower() == "uniprot":
                return self._normalize_uniprot_publication(raw_publication_data)
            return self._normalize_generic_publication(raw_publication_data, source)

        except Exception as e:
            print(f"Error normalizing publication data from {source}: {e}")
            return None
