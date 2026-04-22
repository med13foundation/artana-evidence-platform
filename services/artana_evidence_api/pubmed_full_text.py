"""Deterministic open-access full-text retrieval helpers for PubMed records."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

import requests
from defusedxml import ElementTree

FullTextAcquisitionMethod = Literal["pmc_oa", "skipped"]

_MIN_FULL_TEXT_CHARS = 400
_WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class FullTextFetchResult:
    """Outcome for one deterministic full-text retrieval attempt."""

    found: bool
    acquisition_method: FullTextAcquisitionMethod
    content_text: str | None
    content_length_chars: int
    source_url: str | None
    warning: str | None
    attempted_sources: tuple[str, ...]


def normalize_pmcid(value: str) -> str:
    """Normalize PMCID values to the canonical PMC-prefixed form."""
    candidate = value.strip().upper()
    if candidate.startswith("PMC"):
        return candidate
    return f"PMC{candidate}"


def fetch_pmc_open_access_full_text(
    pmcid: str,
    *,
    timeout_seconds: int = 20,
) -> FullTextFetchResult:
    """Fetch OA full text for a PMCID using NCBI PMC efetch."""
    normalized_pmcid = normalize_pmcid(pmcid)
    encoded = quote(normalized_pmcid, safe="")
    url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        f"efetch.fcgi?db=pmc&id={encoded}"
    )
    attempt = f"pmc_oa:{normalized_pmcid}"
    try:
        xml_content = _http_get_text(url, timeout_seconds=timeout_seconds)
    except (requests.RequestException, OSError, UnicodeDecodeError) as exc:
        return FullTextFetchResult(
            found=False,
            acquisition_method="pmc_oa",
            content_text=None,
            content_length_chars=0,
            source_url=url,
            warning=f"PMC OA fetch failed: {exc!s}",
            attempted_sources=(attempt,),
        )

    full_text = _extract_article_body_text(xml_content)
    if full_text is None:
        return FullTextFetchResult(
            found=False,
            acquisition_method="pmc_oa",
            content_text=None,
            content_length_chars=0,
            source_url=url,
            warning=(
                "PMC OA response did not include a usable article body "
                f"(min {_MIN_FULL_TEXT_CHARS} chars)."
            ),
            attempted_sources=(attempt,),
        )

    return FullTextFetchResult(
        found=True,
        acquisition_method="pmc_oa",
        content_text=full_text,
        content_length_chars=len(full_text),
        source_url=url,
        warning=None,
        attempted_sources=(attempt,),
    )


def _http_get_text(url: str, *, timeout_seconds: int) -> str:
    response = requests.get(url, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.content
    if not isinstance(payload, bytes | bytearray):
        msg = "Expected bytes payload from HTTP response."
        raise TypeError(msg)
    return bytes(payload).decode("utf-8", errors="replace")


def _extract_article_body_text(xml_content: str) -> str | None:
    try:
        root = ElementTree.fromstring(xml_content)
    except Exception:  # noqa: BLE001
        return None
    body = root.find(".//body")
    if body is None:
        return None
    text_fragments = [fragment for fragment in body.itertext() if fragment.strip()]
    if not text_fragments:
        return None
    normalized_text = _WHITESPACE_PATTERN.sub(" ", " ".join(text_fragments)).strip()
    if len(normalized_text) < _MIN_FULL_TEXT_CHARS:
        return None
    return normalized_text


__all__ = [
    "FullTextFetchResult",
    "fetch_pmc_open_access_full_text",
    "normalize_pmcid",
]
