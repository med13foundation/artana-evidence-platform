"""Gene Ontology gateway implementing the OntologyGateway protocol."""

from __future__ import annotations

from src.infrastructure.ingest.hpo_gateway import _OBOGatewayBase

_GO_STABLE_OBO_URL = "https://purl.obolibrary.org/obo/go/go-basic.obo"
_GO_FALLBACK_URL = (
    "https://raw.githubusercontent.com/geneontology/go-ontology/master/go-basic.obo"
)


class GeneOntologyGateway(_OBOGatewayBase):
    """Gene Ontology gateway."""

    def __init__(self, *, preloaded_content: str | None = None) -> None:
        super().__init__(
            stable_url=_GO_STABLE_OBO_URL,
            fallback_url=_GO_FALLBACK_URL,
            preloaded_content=preloaded_content,
        )


__all__ = ["GeneOntologyGateway"]
