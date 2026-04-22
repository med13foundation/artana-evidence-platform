"""MGI (Mouse Genome Informatics) gene/phenotype client.

Fetches mouse gene records from the Alliance of Genome Resources REST API
(https://www.alliancegenome.org/api), filtered to mouse via the
``species=Mus musculus`` query parameter.  The Alliance API federates MGI
along with ZFIN, FlyBase, WormBase, RGD, and SGD into one consistent JSON
shape, so this client is a thin specialization of
:class:`AllianceGenomeIngestor` — it only configures the species filter,
provider prefix, and identifier key.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import ClassVar

from src.infrastructure.ingest.alliance_genome_base import (
    AllianceGenomeIngestor,
    AllianceGenomePage,
)

logger = logging.getLogger(__name__)

_MOUSE_SPECIES = "Mus musculus"
_MGI_PROVIDER = "MGI"


@dataclass(frozen=True)
class MGIFetchPage(AllianceGenomePage):
    """Result of an MGI gene-record fetch.

    Thin subclass of :class:`AllianceGenomePage` preserved so existing
    imports (``from src.infrastructure.ingest.mgi_ingestor import
    MGIFetchPage``) and ``isinstance(..., MGIFetchPage)`` checks in the
    test suite continue to work unchanged.
    """


class MGIIngestor(AllianceGenomeIngestor):
    """Async HTTP client for the Alliance of Genome Resources gene search API.

    Filters results to mouse via the ``species`` query parameter.  Shares
    the Alliance JSON shape with :class:`ZFINIngestor`, differing only in
    the species filter and the ``MGI`` provider prefix used to namespace
    ids.
    """

    _SOURCE_NAME: ClassVar[str] = "mgi"
    _SPECIES_FILTER: ClassVar[str] = _MOUSE_SPECIES
    _PROVIDER_PREFIX: ClassVar[str] = _MGI_PROVIDER
    _ID_KEY: ClassVar[str] = "mgi_id"
    _PAGE_CLASS: ClassVar[type[AllianceGenomePage]] = MGIFetchPage


__all__ = ["MGIFetchPage", "MGIIngestor"]
