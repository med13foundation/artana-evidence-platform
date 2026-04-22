"""Paper-link normalization helpers owned by the graph service."""

from __future__ import annotations

import re

from artana_evidence_db.common_types import JSONObject

_DOI_PATTERN = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.IGNORECASE)
_PMID_PATTERN = re.compile(r"(?:^|[:\s-])(\d{4,10})(?:$|\b)")
_PMCID_PATTERN = re.compile(r"(?:^|[:\s-])(PMC\d+)(?:$|\b)", re.IGNORECASE)
_LINK_LABEL_PRIORITY: dict[str, int] = {
    "PubMed": 0,
    "PMC": 1,
    "DOI": 2,
    "Source": 3,
    "Other": 4,
}
_IDENTIFIER_KEYS: tuple[str, ...] = (
    "doi",
    "pmid",
    "pmcid",
    "url",
    "source_url",
    "document_url",
)


def coerce_json_object(raw_value: object) -> JSONObject:
    """Normalize arbitrary runtime values into JSON-object form."""
    if not isinstance(raw_value, dict):
        return {}
    return {str(key): value for key, value in raw_value.items()}


def normalize_optional_string(raw_value: object) -> str | None:
    """Return one trimmed string or ``None`` for empty/non-string values."""
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    return normalized or None


def resolve_paper_links(  # noqa: C901
    *,
    source_type: str | None,
    external_record_id: str | None,
    metadata: JSONObject,
) -> list[JSONObject]:
    """Extract normalized PubMed/PMC/DOI/source links from record metadata."""
    links_by_url: dict[str, JSONObject] = {}

    def add_link(*, label: str, url: str, source: str) -> None:
        normalized_url = normalize_optional_string(url)
        if normalized_url is None:
            return
        existing = links_by_url.get(normalized_url)
        candidate: JSONObject = {
            "label": label,
            "url": normalized_url,
            "source": source,
        }
        if existing is None:
            links_by_url[normalized_url] = candidate
            return
        existing_label = normalize_optional_string(existing.get("label")) or "Other"
        if _LINK_LABEL_PRIORITY.get(label, 99) < _LINK_LABEL_PRIORITY.get(
            existing_label,
            99,
        ):
            links_by_url[normalized_url] = candidate

    def add_identifiers(value: str, *, source: str) -> None:
        normalized_value = value.strip()
        if not normalized_value:
            return
        lowered_value = normalized_value.lower()
        doi_match = _DOI_PATTERN.search(normalized_value)
        if doi_match is not None:
            doi = doi_match.group(1).strip()
            add_link(label="DOI", url=f"https://doi.org/{doi}", source=source)
        pmcid_match = _PMCID_PATTERN.search(normalized_value)
        if pmcid_match is not None:
            pmcid = pmcid_match.group(1).upper()
            add_link(
                label="PMC",
                url=f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/",
                source=source,
            )
        pmid_match = _PMID_PATTERN.search(normalized_value)
        if pmid_match is not None and (
            lowered_value.startswith("pmid")
            or (source_type or "").strip().lower() == "pubmed"
        ):
            pmid = pmid_match.group(1)
            add_link(
                label="PubMed",
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                source=source,
            )
        if lowered_value.startswith(("http://", "https://")):
            if "pubmed.ncbi.nlm.nih.gov" in lowered_value:
                add_link(label="PubMed", url=normalized_value, source=source)
            elif "pmc.ncbi.nlm.nih.gov" in lowered_value:
                add_link(label="PMC", url=normalized_value, source=source)
            elif "doi.org/" in lowered_value:
                add_link(label="DOI", url=normalized_value, source=source)
            else:
                add_link(label="Source", url=normalized_value, source=source)

    if external_record_id is not None:
        add_identifiers(external_record_id, source="external_record_id")
    for key in _IDENTIFIER_KEYS:
        raw_value = metadata.get(key)
        if isinstance(raw_value, str):
            add_identifiers(raw_value, source=f"metadata.{key}")
    raw_record = coerce_json_object(metadata.get("raw_record"))
    for key in _IDENTIFIER_KEYS:
        raw_value = raw_record.get(key)
        if isinstance(raw_value, str):
            add_identifiers(raw_value, source=f"metadata.raw_record.{key}")

    links = list(links_by_url.values())
    links.sort(
        key=lambda item: (
            _LINK_LABEL_PRIORITY.get(
                normalize_optional_string(item.get("label")) or "Other",
                99,
            ),
            normalize_optional_string(item.get("label")) or "",
            normalize_optional_string(item.get("url")) or "",
        ),
    )
    return links


__all__ = ["coerce_json_object", "normalize_optional_string", "resolve_paper_links"]
