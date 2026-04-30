"""Shared constants for the live full-AI canary script."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

ReportMode = Literal["standard", "canary"]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BASE_URL_ENV = "ARTANA_EVIDENCE_API_LIVE_BASE_URL"
_API_KEY_ENV = "ARTANA_EVIDENCE_API_KEY"
_BEARER_TOKEN_ENV = "ARTANA_EVIDENCE_API_BEARER_TOKEN"
_DEFAULT_TEST_USER_ID = "11111111-1111-1111-1111-111111111111"
_DEFAULT_TEST_USER_EMAIL = "researcher@example.com"
_DEFAULT_TEST_USER_ROLE = "researcher"
_DEFAULT_POLL_REQUEST_TIMEOUT_SECONDS = 15.0
_HTTP_OK = 200
_HTTP_CREATED = 201
_HTTP_UNAUTHORIZED = 401
_HTTP_NOT_FOUND = 404
_RESERVED_SOURCE_KEYS = frozenset({"uniprot", "hgnc"})
_CONTEXT_ONLY_SOURCE_KEYS = frozenset({"pdf", "text"})
_GROUNDING_SOURCE_KEYS = frozenset({"mondo"})
_ACTION_DEFAULT_SOURCE_KEYS: dict[str, str] = {
    "QUERY_PUBMED": "pubmed",
    "INGEST_AND_EXTRACT_PUBMED": "pubmed",
    "REVIEW_PDF_WORKSET": "pdf",
    "REVIEW_TEXT_WORKSET": "text",
    "LOAD_MONDO_GROUNDING": "mondo",
    "RUN_UNIPROT_GROUNDING": "uniprot",
    "RUN_HGNC_GROUNDING": "hgnc",
}
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")

__all__ = [
    "ReportMode",
    "_ACTION_DEFAULT_SOURCE_KEYS",
    "_API_KEY_ENV",
    "_BASE_URL_ENV",
    "_BEARER_TOKEN_ENV",
    "_CONTEXT_ONLY_SOURCE_KEYS",
    "_DEFAULT_POLL_REQUEST_TIMEOUT_SECONDS",
    "_DEFAULT_TEST_USER_EMAIL",
    "_DEFAULT_TEST_USER_ID",
    "_DEFAULT_TEST_USER_ROLE",
    "_GROUNDING_SOURCE_KEYS",
    "_HTTP_CREATED",
    "_HTTP_NOT_FOUND",
    "_HTTP_OK",
    "_HTTP_UNAUTHORIZED",
    "_REPO_ROOT",
    "_RESERVED_SOURCE_KEYS",
    "_SAFE_FILENAME_RE",
]
