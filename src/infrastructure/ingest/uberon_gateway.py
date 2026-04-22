"""Uberon anatomy ontology gateway implementing the OntologyGateway protocol."""

from __future__ import annotations

from src.infrastructure.ingest.hpo_gateway import _OBOGatewayBase

_UBERON_STABLE_OBO_URL = "https://purl.obolibrary.org/obo/uberon/basic.obo"
_UBERON_FALLBACK_URL = (
    "https://raw.githubusercontent.com/obophenotype/uberon/master/uberon-basic.obo"
)


class UberonGateway(_OBOGatewayBase):
    """Uberon anatomy ontology gateway."""

    def __init__(self, *, preloaded_content: str | None = None) -> None:
        super().__init__(
            stable_url=_UBERON_STABLE_OBO_URL,
            fallback_url=_UBERON_FALLBACK_URL,
            preloaded_content=preloaded_content,
        )


__all__ = ["UberonGateway"]
