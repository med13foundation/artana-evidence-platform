"""Opaque deterministic references for semantic source records and evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from artana_evidence_api.evidence_selection_candidates import record_hash
from artana_evidence_api.types.common import JSONObject

_REFERENCE_DIGEST_LENGTH = 32


def semantic_record_reference(
    *,
    source_key: str,
    search_id: str,
    record_index: int,
    record: JSONObject,
) -> str:
    """Bind an opaque reference to one record in one source-search execution."""

    if not source_key.strip():
        raise ValueError("semantic record source key must be non-empty")
    if not search_id.strip():
        raise ValueError("semantic record search identity must be non-empty")
    if record_index < 0:
        raise ValueError("semantic record index must be non-negative")
    payload = {
        "record_hash": record_hash(record),
        "record_index": record_index,
        "search_id": search_id,
        "source_key": source_key,
        "version": "semantic_record_reference.v1",
    }
    return _opaque_reference(prefix="sr", payload=payload)


def semantic_evidence_reference(
    *,
    record_ref: str,
    source_path: str,
    text: str,
) -> str:
    """Bind an opaque reference to one exact evidence span in one record."""

    payload = {
        "record_ref": record_ref,
        "source_path": source_path,
        "text": text,
        "version": "semantic_evidence_reference.v1",
    }
    return _opaque_reference(prefix="se", payload=payload)


def _opaque_reference(*, prefix: str, payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:_REFERENCE_DIGEST_LENGTH]
    return f"{prefix}_{digest}"


__all__ = ["semantic_evidence_reference", "semantic_record_reference"]
