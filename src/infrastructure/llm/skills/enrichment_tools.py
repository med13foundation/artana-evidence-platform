"""Skill builders for Tier-2 content acquisition and enrichment decisions."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from src.infrastructure.llm import content_enrichment_full_text as full_text_helpers
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.type_definitions.common import JSONObject
else:
    type JSONObject = dict[str, object]

_http_get_text_obj = getattr(full_text_helpers, "_http_get_text", None)
if not callable(_http_get_text_obj):
    msg = "content_enrichment_full_text._http_get_text is unavailable"
    raise TypeError(msg)
_http_get_text = _http_get_text_obj


def _normalize_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _sync_full_text_http_helper() -> None:
    current_helper = getattr(full_text_helpers, "_http_get_text", None)
    if current_helper is not _http_get_text:
        full_text_helpers.__dict__["_http_get_text"] = _http_get_text


def _parse_payload_json(payload: str | None) -> JSONObject | None:
    if payload is None:
        return None

    decoded: object = payload
    for _ in range(3):
        if not isinstance(decoded, str):
            break
        candidate = decoded.strip()
        if not candidate:
            return None
        try:
            decoded = json.loads(candidate)
        except json.JSONDecodeError:
            return None

    if not isinstance(decoded, dict):
        return None

    return {str(key): to_json_value(value) for key, value in decoded.items()}


def make_fetch_pmc_oa_tool(
    *,
    http_timeout_seconds: int = 20,
    **_: object,
) -> Callable[[str], JSONObject]:
    """Build a tool callable for deterministic PMC OA full-text fetching."""

    def fetch_pmc_oa(pmcid: str) -> JSONObject:
        _sync_full_text_http_helper()
        normalized = full_text_helpers.normalize_pmcid(pmcid)
        result = full_text_helpers.fetch_pmc_open_access_full_text(
            normalized,
            timeout_seconds=http_timeout_seconds,
        )
        return result.as_json()

    return fetch_pmc_oa


def make_fetch_europe_pmc_tool(
    *,
    http_timeout_seconds: int = 20,
    **_: object,
) -> Callable[[str], JSONObject]:
    """Build a tool callable for deterministic Europe PMC full-text fetching."""

    def fetch_europe_pmc(identifier: str) -> JSONObject:
        normalized = _normalize_identifier(identifier)
        if normalized is None:
            return {
                "found": False,
                "acquisition_method": "europe_pmc",
                "content_format": "text",
                "content_text": None,
                "content_length_chars": 0,
                "warning": "Identifier is required for Europe PMC fetch",
                "attempted_sources": [],
            }

        _sync_full_text_http_helper()
        result = full_text_helpers.fetch_europe_pmc_full_text(
            normalized,
            timeout_seconds=http_timeout_seconds,
        )
        return result.as_json()

    return fetch_europe_pmc


def make_check_open_access_tool(
    **_: object,
) -> Callable[[str | None, str | None], JSONObject]:
    """Build a tool callable for coarse open-access eligibility checks."""

    def check_open_access(
        pmcid: str | None = None,
        doi: str | None = None,
    ) -> JSONObject:
        normalized_pmcid = _normalize_identifier(pmcid)
        normalized_doi = _normalize_identifier(doi)
        if normalized_pmcid is not None:
            return {
                "is_open_access": True,
                "reason": "pmcid_present",
                "pmcid": full_text_helpers.normalize_pmcid(normalized_pmcid),
                "doi": normalized_doi,
            }
        return {
            "is_open_access": False,
            "reason": "pmcid_missing",
            "pmcid": None,
            "doi": normalized_doi,
        }

    return check_open_access


def make_pass_through_tool(
    **_: object,
) -> Callable[[str | None, str | None], JSONObject]:
    """Build a tool callable for deterministic structured-data pass-through."""

    def pass_through(
        payload: str | None = None,
        content_text: str | None = None,
    ) -> JSONObject:
        parsed_payload = _parse_payload_json(payload)
        if parsed_payload is not None:
            normalized_payload = parsed_payload
            serialized = json.dumps(normalized_payload, default=str)
            return {
                "decision": "enriched",
                "acquisition_method": "pass_through",
                "content_format": "structured_json",
                "content_payload": normalized_payload,
                "content_text": None,
                "content_length_chars": len(serialized),
            }
        if isinstance(content_text, str) and content_text.strip():
            normalized_text = content_text.strip()
            return {
                "decision": "enriched",
                "acquisition_method": "pass_through",
                "content_format": "text",
                "content_payload": None,
                "content_text": normalized_text,
                "content_length_chars": len(normalized_text),
            }
        return {
            "decision": "skipped",
            "acquisition_method": "skipped",
            "content_format": "text",
            "content_payload": None,
            "content_text": None,
            "content_length_chars": 0,
            "warning": "No pass-through payload available",
        }

    return pass_through


__all__ = [
    "make_check_open_access_tool",
    "make_fetch_europe_pmc_tool",
    "make_fetch_pmc_oa_tool",
    "make_pass_through_tool",
]
