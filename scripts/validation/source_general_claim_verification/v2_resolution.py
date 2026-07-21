"""Deterministic validation and scientific agreement for corrected packets."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from scripts.validation.source_general_claim_verification.v2_contracts import (
    AdjudicationBatch,
    AdjudicationPacket,
    EvidenceSpan,
)

if TYPE_CHECKING:
    from scripts.validation.source_general_claim_verification.contracts import (
        CorpusArtifact,
        ExposedScope,
    )

SCIENTIFIC_FIELDS = (
    "decision",
    "ambiguity_reason",
    "event_type",
    "event_evidence",
    "participants",
    "direction",
    "comparison",
    "polarity",
    "uncertainty",
    "quantitative_evidence",
    "statistical_evidence",
    "author_interpretation",
    "author_interpretation_evidence",
    "required_modifiers",
    "completeness",
)


@dataclass(frozen=True, slots=True)
class ValidatedBatch:
    sha256: str
    batch: AdjudicationBatch | None
    errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return self.batch is not None and not self.errors


def load_validated_batch(
    path: Path,
    *,
    corpus: CorpusArtifact,
    role: str,
    expected_scope_ids: tuple[str, ...],
) -> ValidatedBatch:
    raw = path.read_bytes()
    sha256 = hashlib.sha256(raw).hexdigest()
    try:
        batch = AdjudicationBatch.model_validate_json(raw)
    except ValidationError as exc:
        return ValidatedBatch(sha256=sha256, batch=None, errors=(str(exc),))
    errors = _batch_errors(
        batch,
        corpus=corpus,
        role=role,
        expected_scope_ids=expected_scope_ids,
    )
    return ValidatedBatch(sha256=sha256, batch=batch, errors=errors)


def scientific_disagreements(
    first: AdjudicationBatch,
    second: AdjudicationBatch,
) -> dict[str, tuple[str, ...]]:
    first_by_id = {packet.scope_id: packet for packet in first.packets}
    second_by_id = {packet.scope_id: packet for packet in second.packets}
    return {
        scope_id: tuple(
            field
            for field in SCIENTIFIC_FIELDS
            if _field_value(first_by_id[scope_id], field)
            != _field_value(second_by_id[scope_id], field)
        )
        for scope_id in first_by_id
        if any(
            _field_value(first_by_id[scope_id], field)
            != _field_value(second_by_id[scope_id], field)
            for field in SCIENTIFIC_FIELDS
        )
    }


def unresolved_after_tiebreak(
    *,
    disputes: dict[str, tuple[str, ...]],
    first: AdjudicationBatch,
    second: AdjudicationBatch,
    tiebreaker: AdjudicationBatch | None,
) -> tuple[str, ...]:
    if tiebreaker is None:
        return tuple(sorted(disputes))
    first_by_id = {packet.scope_id: packet for packet in first.packets}
    second_by_id = {packet.scope_id: packet for packet in second.packets}
    third_by_id = {packet.scope_id: packet for packet in tiebreaker.packets}
    unresolved: list[str] = []
    for scope_id, fields in disputes.items():
        third = third_by_id.get(scope_id)
        if third is None:
            unresolved.append(scope_id)
            continue
        if any(
            _field_value(third, field)
            not in {
                _field_value(first_by_id[scope_id], field),
                _field_value(second_by_id[scope_id], field),
            }
            for field in fields
        ):
            unresolved.append(scope_id)
            continue
        if any(
            _field_value(third, field) != _field_value(first_by_id[scope_id], field)
            for field in SCIENTIFIC_FIELDS
            if field not in fields
        ):
            unresolved.append(scope_id)
    return tuple(sorted(unresolved))


def _batch_errors(
    batch: AdjudicationBatch,
    *,
    corpus: CorpusArtifact,
    role: str,
    expected_scope_ids: tuple[str, ...],
) -> tuple[str, ...]:
    errors: list[str] = []
    if batch.reviewer_role != role:
        errors.append("reviewer role mismatch")
    if tuple(packet.scope_id for packet in batch.packets) != expected_scope_ids:
        errors.append("packet IDs or order do not match the sealed request")
    scopes = {scope.scope_id: scope for scope in corpus.scopes}
    sources = {source.source_id: source for source in corpus.sources}
    for packet in batch.packets:
        scope = scopes.get(packet.scope_id)
        source = sources.get(packet.source_id)
        if scope is None or source is None:
            errors.append(f"unknown scope or source: {packet.scope_id}")
            continue
        if packet.source_sha256 != source.source_sha256:
            errors.append(f"source hash mismatch: {packet.scope_id}")
            continue
        if packet.scope_evidence.model_dump() != scope.scope.model_dump():
            errors.append(f"scope evidence mismatch: {packet.scope_id}")
            continue
        for span in _packet_spans(packet):
            if not _span_is_local(span, scope=scope, source_text=source.text):
                errors.append(f"non-local or unresolved evidence: {packet.scope_id}")
                break
        if packet.claim is not None and tuple(packet.claim.participants) != tuple(
            sorted(
                packet.claim.participants,
                key=lambda item: (
                    item.evidence.start,
                    item.evidence.end,
                    item.role,
                ),
            ),
        ):
            errors.append(
                f"participants are not canonically ordered: {packet.scope_id}"
            )
    return tuple(errors)


def _field_value(packet: AdjudicationPacket, field: str) -> object:
    if field in {"decision", "ambiguity_reason"}:
        return getattr(packet, field)
    claim = packet.claim
    if claim is None:
        return None
    if field == "event_type":
        return claim.event_type
    if field == "event_evidence":
        return claim.event_evidence
    if field == "author_interpretation_evidence":
        return claim.author_interpretation_evidence
    if field == "completeness":
        return claim.completeness
    return getattr(claim, field)


def _packet_spans(packet: AdjudicationPacket) -> tuple[EvidenceSpan, ...]:
    claim = packet.claim
    if claim is None:
        return (packet.scope_evidence,)
    spans = [
        packet.scope_evidence,
        claim.event_evidence,
        claim.direction_evidence,
        claim.polarity_evidence,
        claim.uncertainty_evidence,
    ]
    spans.extend(participant.evidence for participant in claim.participants)
    spans.extend(item.evidence for item in claim.quantitative_evidence)
    spans.extend(item.evidence for item in claim.statistical_evidence)
    spans.extend(item.evidence for item in claim.required_modifiers)
    spans.extend(claim.acceptable_equivalent_evidence)
    if claim.comparison.evidence is not None:
        spans.append(claim.comparison.evidence)
    if claim.comparison.left is not None:
        spans.append(claim.comparison.left)
    if claim.comparison.right is not None:
        spans.append(claim.comparison.right)
    if claim.author_interpretation_evidence is not None:
        spans.append(claim.author_interpretation_evidence)
    return tuple(spans)


def _span_is_local(
    span: EvidenceSpan,
    *,
    scope: ExposedScope,
    source_text: str,
) -> bool:
    return (
        scope.scope.start <= span.start < span.end <= scope.scope.end
        and source_text[span.start : span.end] == span.text
    )


__all__ = [
    "SCIENTIFIC_FIELDS",
    "ValidatedBatch",
    "load_validated_batch",
    "scientific_disagreements",
    "unresolved_after_tiebreak",
]
