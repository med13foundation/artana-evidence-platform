"""ZFIN (Zebrafish Information Network) gene/phenotype client.

Fetches zebrafish gene records from the Alliance of Genome Resources REST
API (https://www.alliancegenome.org/api), filtered to zebrafish via the
``species=Danio rerio`` query parameter.  This ingestor is the sibling of
:mod:`mgi_ingestor` — both are thin specializations of
:class:`AllianceGenomeIngestor`.  The only ZFIN-specific extra is the
``expression_terms`` field, which we contribute via the
``_extract_extra_fields`` template-method hook (zebrafish expression
patterns are one of the most useful signals from ZFIN).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from src.infrastructure.ingest.alliance_genome_base import (
    AllianceGenomeIngestor,
    AllianceGenomePage,
)

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject, RawRecord

logger = logging.getLogger(__name__)

_ZEBRAFISH_SPECIES = "Danio rerio"
_ZFIN_PROVIDER = "ZFIN"


@dataclass(frozen=True)
class ZFINFetchPage(AllianceGenomePage):
    """Result of a ZFIN gene-record fetch.

    Thin subclass of :class:`AllianceGenomePage` preserved so existing
    imports (``from src.infrastructure.ingest.zfin_ingestor import
    ZFINFetchPage``) and ``isinstance(..., ZFINFetchPage)`` checks in the
    test suite continue to work unchanged.
    """


class ZFINIngestor(AllianceGenomeIngestor):
    """Async HTTP client for the Alliance of Genome Resources gene search API.

    Filters results to zebrafish via the ``species`` query parameter.
    Shares the Alliance JSON shape with :class:`MGIIngestor`, differing
    only in the species filter, the ``ZFIN`` provider prefix used to
    namespace ids, and the extra ``expression_terms`` field contributed
    via :meth:`_extract_extra_fields`.
    """

    _SOURCE_NAME: ClassVar[str] = "zfin"
    _SPECIES_FILTER: ClassVar[str] = _ZEBRAFISH_SPECIES
    _PROVIDER_PREFIX: ClassVar[str] = _ZFIN_PROVIDER
    _ID_KEY: ClassVar[str] = "zfin_id"
    _PAGE_CLASS: ClassVar[type[AllianceGenomePage]] = ZFINFetchPage

    def _extract_extra_fields(self, entry: JSONObject) -> RawRecord:
        """Contribute the ZFIN-specific ``expression_terms`` list."""
        return {"expression_terms": self._extract_expression_terms(entry)}

    @staticmethod
    def _extract_expression_terms(entry: JSONObject) -> list[str]:
        """Extract zebrafish expression terms (anatomy/developmental stage).

        Zebrafish expression patterns are one of the most useful signals from
        ZFIN — many genes have characteristic spatial/temporal expression
        annotated against ZFA (zebrafish anatomy) terms.  Falls back through
        the response variants the Alliance API uses for expression data.
        """
        for key in ("expression", "expressionTerms", "expressedIn"):
            raw = entry.get(key)
            if isinstance(raw, list):
                terms: list[str] = []
                for item in raw:
                    if isinstance(item, str) and item.strip():
                        terms.append(item.strip())
                    elif isinstance(item, dict):
                        name = item.get("name") or item.get("term")
                        if isinstance(name, str) and name.strip():
                            terms.append(name.strip())
                return terms
        return []


__all__ = ["ZFINFetchPage", "ZFINIngestor"]
