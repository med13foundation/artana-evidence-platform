"""Deterministic open-access full-text retrieval helpers for PubMed records."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from urllib.parse import quote

import requests
from defusedxml import ElementTree

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject
else:
    type JSONObject = dict[str, object]

FullTextAcquisitionMethod = Literal["pmc_oa", "europe_pmc", "skipped"]

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

    def as_json(self) -> JSONObject:
        return {
            "found": self.found,
            "acquisition_method": self.acquisition_method,
            "content_format": "text",
            "content_text": self.content_text,
            "content_length_chars": self.content_length_chars,
            "source_url": self.source_url,
            "warning": self.warning,
            "attempted_sources": list(self.attempted_sources),
        }


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


def fetch_europe_pmc_full_text(
    identifier: str,
    *,
    timeout_seconds: int = 20,
) -> FullTextFetchResult:
    """Fetch OA full text through Europe PMC fullTextXML endpoint."""
    normalized_identifier = identifier.strip()
    if not normalized_identifier:
        return FullTextFetchResult(
            found=False,
            acquisition_method="europe_pmc",
            content_text=None,
            content_length_chars=0,
            source_url=None,
            warning="Identifier is required for Europe PMC fetch.",
            attempted_sources=("europe_pmc:missing_identifier",),
        )

    encoded = quote(normalized_identifier, safe="")
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{encoded}/fullTextXML"
    attempt = f"europe_pmc:{normalized_identifier}"
    try:
        xml_content = _http_get_text(url, timeout_seconds=timeout_seconds)
    except (requests.RequestException, OSError, UnicodeDecodeError) as exc:
        return FullTextFetchResult(
            found=False,
            acquisition_method="europe_pmc",
            content_text=None,
            content_length_chars=0,
            source_url=url,
            warning=f"Europe PMC fetch failed: {exc!s}",
            attempted_sources=(attempt,),
        )

    full_text = _extract_article_body_text(xml_content)
    if full_text is None:
        return FullTextFetchResult(
            found=False,
            acquisition_method="europe_pmc",
            content_text=None,
            content_length_chars=0,
            source_url=url,
            warning=(
                "Europe PMC response did not include a usable article body "
                f"(min {_MIN_FULL_TEXT_CHARS} chars)."
            ),
            attempted_sources=(attempt,),
        )

    return FullTextFetchResult(
        found=True,
        acquisition_method="europe_pmc",
        content_text=full_text,
        content_length_chars=len(full_text),
        source_url=url,
        warning=None,
        attempted_sources=(attempt,),
    )


def fetch_pubmed_open_access_full_text(
    metadata: JSONObject,
    *,
    timeout_seconds: int = 20,
) -> FullTextFetchResult:
    """Resolve identifiers from metadata and fetch OA full text deterministically."""
    pmcid, pmid, doi = _resolve_pubmed_identifiers(metadata)
    attempts: list[str] = []
    warnings: list[str] = []

    resolved_pmcid, idconv_attempts, idconv_warning = _resolve_or_lookup_pmcid(
        pmcid=pmcid,
        pmid=pmid,
        doi=doi,
        timeout_seconds=timeout_seconds,
    )
    attempts.extend(idconv_attempts)
    if idconv_warning:
        warnings.append(idconv_warning)

    pmc_result = _attempt_pmc_fetch(
        pmcid=resolved_pmcid,
        timeout_seconds=timeout_seconds,
    )
    if pmc_result is not None:
        attempts.extend(pmc_result.attempted_sources)
        if pmc_result.found:
            return _merge_attempts(pmc_result, attempts)
        if pmc_result.warning:
            warnings.append(pmc_result.warning)

    for identifier in _build_europe_pmc_identifiers(
        pmcid=resolved_pmcid,
        pmid=pmid,
        doi=doi,
    ):
        europe_result = _attempt_europe_pmc_fetch(
            identifier,
            timeout_seconds=timeout_seconds,
        )
        attempts.extend(europe_result.attempted_sources)
        if europe_result.found:
            return _merge_attempts(europe_result, attempts)
        if europe_result.warning:
            warnings.append(europe_result.warning)

    if not attempts:
        warnings.append(
            "No deterministic full-text fetch attempted (missing PMCID/PMID/DOI).",
        )

    return FullTextFetchResult(
        found=False,
        acquisition_method="skipped",
        content_text=None,
        content_length_chars=0,
        source_url=None,
        warning=_deduplicate_warning(warnings),
        attempted_sources=_unique_attempts(attempts),
    )


def _resolve_or_lookup_pmcid(
    *,
    pmcid: str | None,
    pmid: str | None,
    doi: str | None,
    timeout_seconds: int,
) -> tuple[str | None, tuple[str, ...], str | None]:
    if pmcid is not None:
        return pmcid, (), None
    return _resolve_pmcid_via_idconv(
        pmid=pmid,
        doi=doi,
        timeout_seconds=timeout_seconds,
    )


def _attempt_pmc_fetch(
    *,
    pmcid: str | None,
    timeout_seconds: int,
) -> FullTextFetchResult | None:
    if pmcid is None:
        return None
    return fetch_pmc_open_access_full_text(
        pmcid,
        timeout_seconds=timeout_seconds,
    )


def _attempt_europe_pmc_fetch(
    identifier: str,
    *,
    timeout_seconds: int,
) -> FullTextFetchResult:
    return fetch_europe_pmc_full_text(
        identifier,
        timeout_seconds=timeout_seconds,
    )


def _resolve_pmcid_via_idconv(
    *,
    pmid: str | None,
    doi: str | None,
    timeout_seconds: int,
) -> tuple[str | None, tuple[str, ...], str | None]:
    attempts: list[str] = []
    warnings: list[str] = []
    for identifier, id_type in _build_idconv_query_candidates(pmid=pmid, doi=doi):
        attempts.append(f"idconv:{id_type}:{identifier}")
        response_text, fetch_warning = _fetch_idconv_response(
            identifier=identifier,
            id_type=id_type,
            timeout_seconds=timeout_seconds,
        )
        if fetch_warning is not None:
            warnings.append(fetch_warning)
            continue
        if response_text is None:
            continue

        resolved_pmcid, parse_warning = _extract_pmcid_from_idconv_response(
            response_text=response_text,
            identifier=identifier,
            id_type=id_type,
        )
        if parse_warning is not None:
            warnings.append(parse_warning)
        if resolved_pmcid is not None:
            return resolved_pmcid, _unique_attempts(attempts), None

    warning = _deduplicate_warning(warnings) if warnings else None
    return None, _unique_attempts(attempts), warning


def _build_idconv_query_candidates(
    *,
    pmid: str | None,
    doi: str | None,
) -> tuple[tuple[str, str], ...]:
    candidates: list[tuple[str, str]] = []
    if pmid is not None:
        candidates.append((pmid, "pmid"))
    if doi is not None:
        candidates.append((doi, "doi"))
    return tuple(candidates)


def _fetch_idconv_response(
    *,
    identifier: str,
    id_type: str,
    timeout_seconds: int,
) -> tuple[str | None, str | None]:
    encoded = quote(identifier, safe="")
    url = (
        "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
        f"?ids={encoded}&idtype={id_type}&format=json"
    )
    try:
        return _http_get_text(url, timeout_seconds=timeout_seconds), None
    except (requests.RequestException, OSError, UnicodeDecodeError) as exc:
        return None, f"PMCID idconv failed for {id_type}:{identifier}: {exc!s}"


def _extract_pmcid_from_idconv_response(
    *,
    response_text: str,
    identifier: str,
    id_type: str,
) -> tuple[str | None, str | None]:
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        warning = (
            f"PMCID idconv returned invalid JSON for {id_type}:{identifier}: {exc!s}"
        )
        return None, warning

    if not isinstance(payload, dict):
        warning = (
            "PMCID idconv returned unexpected payload type for "
            f"{id_type}:{identifier}."
        )
        return None, warning

    records = payload.get("records")
    if not isinstance(records, list):
        return None, None
    for record in records:
        if not isinstance(record, dict):
            continue
        pmcid_value = record.get("pmcid")
        if isinstance(pmcid_value, str) and pmcid_value.strip():
            return normalize_pmcid(pmcid_value), None
    return None, None


def _resolve_pubmed_identifiers(
    metadata: JSONObject,
) -> tuple[str | None, str | None, str | None]:
    source = metadata
    raw_record_value = metadata.get("raw_record")
    if isinstance(raw_record_value, dict):
        source = {str(key): value for key, value in raw_record_value.items()}

    pmcid = _coerce_string(
        source.get("pmc_id"),
        source.get("pmcid"),
    )
    if pmcid is not None:
        pmcid = normalize_pmcid(pmcid)

    pmid = _coerce_string(
        source.get("pubmed_id"),
        source.get("pmid"),
    )
    doi = _coerce_string(source.get("doi"))
    return pmcid, pmid, doi


def _build_europe_pmc_identifiers(
    *,
    pmcid: str | None,
    pmid: str | None,
    doi: str | None,
) -> tuple[str, ...]:
    candidates: list[str] = []
    if pmcid is not None:
        candidates.append(f"PMCID:{pmcid}")
        candidates.append(pmcid)
    if pmid is not None:
        candidates.append(f"MED:{pmid}")
        candidates.append(pmid)
    if doi is not None:
        candidates.append(f"DOI:{doi}")
        candidates.append(doi)
    return _unique_attempts(candidates)


def _coerce_string(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
    return None


def _merge_attempts(
    result: FullTextFetchResult,
    attempts: list[str],
) -> FullTextFetchResult:
    return FullTextFetchResult(
        found=result.found,
        acquisition_method=result.acquisition_method,
        content_text=result.content_text,
        content_length_chars=result.content_length_chars,
        source_url=result.source_url,
        warning=result.warning,
        attempted_sources=_unique_attempts(attempts),
    )


def _deduplicate_warning(warnings: list[str]) -> str:
    unique = [warning.strip() for warning in warnings if warning.strip()]
    if not unique:
        return "No open-access full-text endpoint returned a usable article body."
    return "; ".join(_unique_attempts(unique))


def _unique_attempts(attempts: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for attempt in attempts:
        normalized = attempt.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return tuple(unique)


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
    "fetch_europe_pmc_full_text",
    "fetch_pmc_open_access_full_text",
    "fetch_pubmed_open_access_full_text",
    "normalize_pmcid",
]
