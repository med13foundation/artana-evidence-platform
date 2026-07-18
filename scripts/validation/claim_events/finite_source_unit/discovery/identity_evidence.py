"""Deterministic identity evidence shared by discovery diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
        ModelAttemptAuditRecord,
    )

    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )

_FORBIDDEN_MODEL_IDENTITY_FIELDS: Final = frozenset(
    {
        "candidate_id",
        "covered_candidate_ids",
        "input_sha256",
        "source_sha256",
        "unit_id",
    },
)


def count_model_identity_fields(value: object) -> int:
    """Count forbidden transport keys recursively in model-authored output."""

    if isinstance(value, dict):
        return sum(
            int(key in _FORBIDDEN_MODEL_IDENTITY_FIELDS)
            + count_model_identity_fields(item)
            for key, item in value.items()
        )
    if isinstance(value, list | tuple):
        return sum(count_model_identity_fields(item) for item in value)
    return 0


def audit_identity_mismatch_count(
    records: tuple[ModelAttemptAuditRecord, ...],
    *,
    unit: FrozenSourceUnit,
) -> int:
    """Count attempts detached from the deterministic source-unit envelope."""

    return sum(
        record.semantic_unit_id != unit.unit_id
        or record.source_sha256 != unit.source_sha256
        or record.input_sha256 != unit.input_sha256
        for record in records
    )


__all__ = ["audit_identity_mismatch_count", "count_model_identity_fields"]
