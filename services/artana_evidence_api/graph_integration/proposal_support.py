"""Deterministic metadata and error handling for proposal graph writes."""

from __future__ import annotations

import hashlib
import json
import re

from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.types.common import JSONObject
from fastapi import status

_VERIFIER_OWNED_PROMOTION_METADATA_KEYS = frozenset(
    {
        "agent_extraction_completed",
        "evidence_grounding",
        "fallback_output_used",
        "support_verification",
        "support_verification_floor",
        "review_reason_codes",
        "review_status",
        "source_provenance_reason_code",
        "source_provenance_status",
        "trust_floor_failures",
        "trust_tier",
        "trusted_evidence_eligible",
        "claim_verification",
        "claim_verification_terminal",
        "claim_verification_lineage_status",
        "claim_verification_qualification_complete",
    },
)
_RELATION_CONSTRAINT_ERROR_RE = re.compile(
    r"relation \((?P<triple>[^)]+)\) is not allowed by ACTIVE relation constraints",
    re.IGNORECASE,
)
_EXACT_RELATION_CONSTRAINT_PROMOTION_RE = re.compile(
    r"Triple \((?P<triple>[^)]+)\) requires an active exact relation constraint before promotion\.",
    re.IGNORECASE,
)
_SQLALCHEMY_SQL_MARKER = "[SQL:"
_SQLALCHEMY_BACKGROUND_MARKER = "Background on this error at:"


def stable_json_hash(payload: dict[str, object]) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def metadata_text(
    metadata: JSONObject,
    key: str,
    *,
    default: str,
) -> str:
    value = metadata.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def merge_promotion_metadata(
    *,
    proposal_metadata: JSONObject,
    request_metadata: JSONObject,
) -> JSONObject:
    return {
        **proposal_metadata,
        **{
            key: value
            for key, value in request_metadata.items()
            if key not in _VERIFIER_OWNED_PROMOTION_METADATA_KEYS
        },
    }


def extract_graph_service_error_detail(exc: GraphServiceClientError) -> str:
    detail = _normalize_raw_graph_detail(exc.detail)
    if detail == "":
        detail = str(exc)
    return _strip_sqlalchemy_detail_noise(detail)


def graph_promotion_error_response(
    exc: GraphServiceClientError,
) -> tuple[int, str]:
    detail = extract_graph_service_error_detail(exc)
    triple_match = _RELATION_CONSTRAINT_ERROR_RE.search(detail)
    if triple_match is None:
        triple_match = _EXACT_RELATION_CONSTRAINT_PROMOTION_RE.search(detail)
    if triple_match is not None:
        triple = " ".join(triple_match.group("triple").split())
        return (
            status.HTTP_409_CONFLICT,
            (
                "This proposal cannot be promoted as a canonical relation because "
                f"the active graph constraints do not allow {triple}. Review the "
                "claim structure or relation type before promoting."
            ),
        )
    return (
        exc.status_code or status.HTTP_503_SERVICE_UNAVAILABLE,
        detail or str(exc),
    )


def is_relation_constraint_error(exc: GraphServiceClientError) -> bool:
    detail = extract_graph_service_error_detail(exc)
    return (
        _RELATION_CONSTRAINT_ERROR_RE.search(detail) is not None
        or _EXACT_RELATION_CONSTRAINT_PROMOTION_RE.search(detail) is not None
    )


def _normalize_raw_graph_detail(raw_detail: str | None) -> str:
    if not isinstance(raw_detail, str):
        return ""
    stripped = raw_detail.strip()
    if stripped == "":
        return ""
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    return _message_from_graph_detail_mapping(parsed, fallback=stripped)


def _message_from_graph_detail_mapping(parsed: object, *, fallback: str) -> str:
    if not isinstance(parsed, dict):
        return fallback
    nested_detail = parsed.get("detail")
    if isinstance(nested_detail, str) and nested_detail.strip() != "":
        return nested_detail.strip()
    nested_message = parsed.get("message")
    if isinstance(nested_message, str) and nested_message.strip() != "":
        return nested_message.strip()
    return fallback


def _strip_sqlalchemy_detail_noise(detail: str) -> str:
    if _SQLALCHEMY_SQL_MARKER in detail:
        detail = detail.split(_SQLALCHEMY_SQL_MARKER, 1)[0].rstrip()
    if _SQLALCHEMY_BACKGROUND_MARKER in detail:
        detail = detail.split(_SQLALCHEMY_BACKGROUND_MARKER, 1)[0].rstrip()
    return detail.strip()


__all__ = [
    "extract_graph_service_error_detail",
    "graph_promotion_error_response",
    "is_relation_constraint_error",
    "merge_promotion_metadata",
    "metadata_text",
    "stable_json_hash",
]
