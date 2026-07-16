"""Validate source-evidence bindings before graph claim mutations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from artana_evidence_db.graph_api_schemas.kernel_relation_schemas import (
    KernelRelationClaimCreateRequest,
    KernelRelationCreateRequest,
)

SourceEvidenceWriteRequest = (
    KernelRelationClaimCreateRequest | KernelRelationCreateRequest
)
SourceEvidenceWriteValidationCode = Literal["invalid_source_evidence_binding"]

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, slots=True)
class SourceEvidenceWriteValidationIssue:
    """One source sentence or endpoint-label binding failure."""

    code: SourceEvidenceWriteValidationCode
    message: str


class SourceEvidenceWriteValidationService:
    """Keep submitted source evidence bound to the graph write endpoints."""

    def validate(
        self,
        request: SourceEvidenceWriteRequest,
        *,
        subject_names: Sequence[str],
        object_names: Sequence[str],
    ) -> SourceEvidenceWriteValidationIssue | None:
        """Validate only writes carrying a typed source-evidence handoff."""

        source_evidence = request.source_evidence
        if source_evidence is None:
            return None
        exact_quote = source_evidence.locator.exact_quote
        evidence_sentence = request.evidence_sentence or exact_quote
        if evidence_sentence != exact_quote:
            return _issue(
                "evidence_sentence must equal source_evidence.locator.exact_quote "
                "when source_evidence is supplied."
            )
        subject_spans = _endpoint_spans(evidence=exact_quote, names=subject_names)
        if not subject_spans:
            return _issue(
                "source_evidence.locator.exact_quote must contain a complete "
                "source endpoint label or alias."
            )
        object_spans = _endpoint_spans(evidence=exact_quote, names=object_names)
        if not object_spans:
            return _issue(
                "source_evidence.locator.exact_quote must contain a complete "
                "target endpoint label or alias."
            )
        if not _has_distinct_endpoint_binding(subject_spans, object_spans):
            return _issue(
                "source_evidence.locator.exact_quote must bind source and target "
                "to distinct, non-overlapping text spans."
            )
        return None


def _issue(message: str) -> SourceEvidenceWriteValidationIssue:
    return SourceEvidenceWriteValidationIssue(
        code="invalid_source_evidence_binding",
        message=message,
    )


def _endpoint_spans(
    *,
    evidence: str,
    names: Sequence[str],
) -> set[tuple[int, int]]:
    spans: set[tuple[int, int]] = set()
    for name in names:
        normalized = name.strip()
        if not normalized:
            continue
        spans.update(
            (match.start(), match.end())
            for match in re.finditer(
                rf"(?<![A-Za-z0-9]){re.escape(normalized)}(?![A-Za-z0-9])",
                evidence,
                flags=re.IGNORECASE,
            )
        )
    return spans


def _has_distinct_endpoint_binding(
    subject_spans: set[tuple[int, int]],
    object_spans: set[tuple[int, int]],
) -> bool:
    return any(
        subject_end <= object_start or object_end <= subject_start
        for subject_start, subject_end in subject_spans
        for object_start, object_end in object_spans
    )


__all__ = [
    "SourceEvidenceWriteValidationIssue",
    "SourceEvidenceWriteValidationService",
]
