"""Monarch Disease Ontology gateway implementing the OntologyGateway protocol.

The MONDO OBO file bundles imported ontologies (BFO, UBERON, HP, GO, etc.)
alongside the actual MONDO disease terms.  Terms do not carry an OBO
``namespace:`` tag, so this gateway filters by ID prefix (``MONDO:``)
to keep only disease terms and backfills the namespace field for the
ingestion service's entity-type mapping.
"""

from __future__ import annotations

from dataclasses import replace

from src.domain.services.ontology_ingestion import (
    OntologyFetchResult,
    OntologyRelease,
)
from src.infrastructure.ingest.hpo_gateway import _OBOGatewayBase, parse_obo_terms

_MONDO_STABLE_OBO_URL = "https://purl.obolibrary.org/obo/mondo.obo"
_MONDO_FALLBACK_URL = (
    "https://github.com/monarch-initiative/mondo/releases/latest/download/mondo.obo"
)

_MONDO_ID_PREFIX = "MONDO:"


class MondoGateway(_OBOGatewayBase):
    """Monarch Disease Ontology gateway."""

    def __init__(self, *, preloaded_content: str | None = None) -> None:
        super().__init__(
            stable_url=_MONDO_STABLE_OBO_URL,
            fallback_url=_MONDO_FALLBACK_URL,
            preloaded_content=preloaded_content,
        )

    async def fetch_release(
        self,
        *,
        version: str | None = None,
        format_preference: str = "obo",
        namespace_filter: str | None = None,  # noqa: ARG002 — interface compat
        max_terms: int | None = None,
    ) -> OntologyFetchResult:
        """Fetch MONDO and keep only MONDO: terms.

        The full OBO file contains ~50k imported terms from other
        ontologies.  We filter to the ~30k MONDO: terms and backfill
        their empty ``namespace`` field so the ingestion service maps
        them to entity_type ``DISEASE``.
        """
        if self._preloaded_content is not None:
            content = self._preloaded_content
            release_version = version or "preloaded"
            download_url = "preloaded://memory"
        else:
            content, release_version, download_url = await self._fetch_obo(
                version=version,
            )

        all_terms = parse_obo_terms(content)

        # Keep only MONDO: terms and backfill the namespace field
        terms = [
            replace(t, namespace="MONDO")
            for t in all_terms
            if t.id.startswith(_MONDO_ID_PREFIX)
        ]

        if max_terms is not None:
            terms = terms[:max_terms]

        release = OntologyRelease(
            version=release_version,
            download_url=download_url,
            format=format_preference,
        )

        return OntologyFetchResult(
            terms=terms,
            release=release,
            fetched_term_count=len(terms),
            checkpoint_after={
                "release_version": release_version,
                "terms_fetched": len(terms),
            },
        )


__all__ = ["MondoGateway"]
