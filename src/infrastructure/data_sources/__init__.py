"""Infrastructure adapters for data source integrations."""

from .clinicaltrials_gateway import ClinicalTrialsSourceGateway
from .clinvar_gateway import ClinVarSourceGateway
from .hgnc_gateway import HGNCSourceGateway
from .http_api_source_gateway import HttpxAPISourceGateway
from .local_file_upload_gateway import LocalFileUploadGateway
from .marrvel_gateway import MarrvelSourceGateway
from .mgi_gateway import MGISourceGateway
from .pubmed_gateway import PubMedSourceGateway
from .pubmed_pdf_gateway import SimplePubMedPdfGateway
from .pubmed_search_gateway import (
    DeterministicPubMedSearchGateway,
    NCBIPubMedGatewaySettings,
    NCBIPubMedSearchGateway,
    create_pubmed_search_gateway,
)  # noqa: F401
from .zfin_gateway import ZFINSourceGateway

__all__ = [
    "ClinVarSourceGateway",
    "ClinicalTrialsSourceGateway",
    "DeterministicPubMedSearchGateway",
    "HGNCSourceGateway",
    "HttpxAPISourceGateway",
    "LocalFileUploadGateway",
    "MarrvelSourceGateway",
    "MGISourceGateway",
    "NCBIPubMedGatewaySettings",
    "NCBIPubMedSearchGateway",
    "PubMedSourceGateway",
    "SimplePubMedPdfGateway",
    "ZFINSourceGateway",
    "create_pubmed_search_gateway",
]
