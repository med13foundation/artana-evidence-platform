"""Cell Ontology gateway implementing the OntologyGateway protocol."""

from __future__ import annotations

from src.infrastructure.ingest.hpo_gateway import _OBOGatewayBase

_CL_STABLE_OBO_URL = "https://purl.obolibrary.org/obo/cl/cl-basic.obo"
_CL_FALLBACK_URL = (
    "https://raw.githubusercontent.com/obophenotype/cell-ontology/master/cl-basic.obo"
)


class CellOntologyGateway(_OBOGatewayBase):
    """Cell Ontology gateway."""

    def __init__(self, *, preloaded_content: str | None = None) -> None:
        super().__init__(
            stable_url=_CL_STABLE_OBO_URL,
            fallback_url=_CL_FALLBACK_URL,
            preloaded_content=preloaded_content,
        )


__all__ = ["CellOntologyGateway"]
