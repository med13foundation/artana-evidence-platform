"""HPO ontology gateway implementing the OntologyGateway protocol.

Fetches HPO OBO files from GitHub releases and parses them into
OntologyTerm objects for the loader/import path.
"""

from __future__ import annotations

import logging

from src.domain.services.ontology_ingestion import (
    OntologyFetchResult,
    OntologyRelease,
    OntologyTerm,
)

logger = logging.getLogger(__name__)

_HPO_STABLE_OBO_URL = "https://purl.obolibrary.org/obo/hp.obo"
_HPO_GITHUB_RAW_URL = (
    "https://raw.githubusercontent.com/obophenotype/"
    "human-phenotype-ontology/master/hp.obo"
)


def parse_obo_terms(content: str) -> list[OntologyTerm]:
    """Parse OBO format content into OntologyTerm objects.

    Handles the standard OBO flat-file format used by HPO, UBERON,
    Cell Ontology, and Gene Ontology.
    """
    terms: list[OntologyTerm] = []
    term_blocks = content.split("[Term]")

    for block in term_blocks:
        block_content = block.strip()
        if not block_content:
            continue

        fields: dict[str, str | list[str]] = {}
        for raw_line in block_content.splitlines():
            line = raw_line.strip()
            if not line or ":" not in line:
                continue
            # Stop at the next stanza header
            if line.startswith("["):
                break
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if not key or not value:
                continue
            existing = fields.get(key)
            if existing is None:
                fields[key] = value
            elif isinstance(existing, list):
                existing.append(value)
            else:
                fields[key] = [existing, value]

        term_id = _scalar(fields.get("id"))
        if not term_id:
            continue

        name = _scalar(fields.get("name")) or ""
        definition_raw = _scalar(fields.get("def")) or ""
        # OBO definitions are quoted: "Some definition." [source]
        definition = _strip_obo_quotes(definition_raw)

        synonyms_raw = _as_list(fields.get("synonym"))
        synonyms = tuple(_strip_obo_quotes(s) for s in synonyms_raw if s.strip())

        parents_raw = _as_list(fields.get("is_a"))
        parents = tuple(_extract_term_id(p) for p in parents_raw if p.strip())

        xrefs_raw = _as_list(fields.get("xref"))
        xrefs = tuple(x.strip() for x in xrefs_raw if x.strip())

        is_obsolete_raw = _scalar(fields.get("is_obsolete")) or "false"
        is_obsolete = is_obsolete_raw.strip().lower() == "true"

        namespace = _scalar(fields.get("namespace")) or ""
        comment = _scalar(fields.get("comment")) or ""

        terms.append(
            OntologyTerm(
                id=term_id,
                name=name,
                definition=definition,
                synonyms=synonyms,
                parents=parents,
                xrefs=xrefs,
                is_obsolete=is_obsolete,
                namespace=namespace,
                comment=comment,
            ),
        )

    return terms


def _scalar(value: str | list[str] | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _as_list(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _strip_obo_quotes(text: str) -> str:
    """Strip OBO-style quoting: \"Some text.\" [source] -> Some text."""
    stripped = text.strip()
    if stripped.startswith('"'):
        end_quote = stripped.find('"', 1)
        if end_quote > 0:
            return stripped[1:end_quote]
    return stripped


def _extract_term_id(is_a_value: str) -> str:
    """Extract the term ID from an is_a line: 'HP:0000001 ! All' -> 'HP:0000001'."""
    parts = is_a_value.strip().split("!", 1)
    return parts[0].strip()


class _OBOGatewayBase:
    """Shared base for OBO-format ontology gateways.

    Subclasses only need to provide ``stable_url`` and ``fallback_url``.
    """

    def __init__(
        self,
        *,
        stable_url: str,
        fallback_url: str,
        preloaded_content: str | None = None,
    ) -> None:
        self._stable_url = stable_url
        self._fallback_url = fallback_url
        self._preloaded_content = preloaded_content

    async def fetch_release(
        self,
        *,
        version: str | None = None,
        format_preference: str = "obo",
        namespace_filter: str | None = None,
        max_terms: int | None = None,
    ) -> OntologyFetchResult:
        """Fetch and parse an OBO release."""
        if self._preloaded_content is not None:
            content = self._preloaded_content
            release_version = version or "preloaded"
            download_url = "preloaded://memory"
        else:
            content, release_version, download_url = await self._fetch_obo(
                version=version,
            )

        terms = parse_obo_terms(content)

        if namespace_filter:
            terms = [t for t in terms if t.namespace == namespace_filter]

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

    async def get_latest_version(self) -> str | None:
        """Return the latest release version tag."""
        return None

    async def _fetch_obo(
        self,
        *,
        version: str | None = None,
    ) -> tuple[str, str, str]:
        """Fetch OBO content. Returns (content, version, url)."""
        import httpx

        url = self._stable_url
        resolved_version = version or "latest"

        async with httpx.AsyncClient(timeout=120) as client:
            content: str | None = None
            source_url = url
            try:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
                content = response.text
            except httpx.HTTPError:
                logger.warning(
                    "%s stable URL failed, trying fallback",
                    self.__class__.__name__,
                )
                response = await client.get(
                    self._fallback_url,
                    follow_redirects=True,
                )
                response.raise_for_status()
                content = response.text
                source_url = self._fallback_url
            return content, resolved_version, source_url


class HPOGateway(_OBOGatewayBase):
    """HPO ontology gateway."""

    def __init__(self, *, preloaded_content: str | None = None) -> None:
        super().__init__(
            stable_url=_HPO_STABLE_OBO_URL,
            fallback_url=_HPO_GITHUB_RAW_URL,
            preloaded_content=preloaded_content,
        )


__all__ = ["HPOGateway", "_OBOGatewayBase", "parse_obo_terms"]
