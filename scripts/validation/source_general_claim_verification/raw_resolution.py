"""Validate and compare sealed raw adjudications without semantic inference."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from scripts.validation.source_general_claim_verification.raw_contracts import (
    RawAdjudicationBatch,
    RawAdjudicationPacket,
)

if TYPE_CHECKING:
    from scripts.validation.source_general_claim_verification.contracts import (
        CorpusArtifact,
    )

MATERIAL_FIELDS = (
    "decision",
    "event_type",
    "participants",
    "direction",
    "comparison",
    "polarity",
    "uncertainty",
    "quantitative_evidence",
    "statistical_observation",
    "author_interpretation",
    "required_modifiers",
    "completeness",
)


@dataclass(frozen=True, slots=True)
class BatchLoad:
    path: Path
    sha256: str
    batch: RawAdjudicationBatch | None
    errors: tuple[str, ...]


def load_and_validate_raw_batch(
    path: Path,
    *,
    corpus: CorpusArtifact,
    expected_count: int,
) -> BatchLoad:
    raw = path.read_bytes()
    sha256 = hashlib.sha256(raw).hexdigest()
    try:
        batch = RawAdjudicationBatch.model_validate_json(raw)
    except ValidationError as exc:
        return BatchLoad(path=path, sha256=sha256, batch=None, errors=(str(exc),))
    errors = _batch_errors(batch, corpus=corpus, expected_count=expected_count)
    return BatchLoad(path=path, sha256=sha256, batch=batch, errors=errors)


def compare_primary_batches(
    first: RawAdjudicationBatch,
    second: RawAdjudicationBatch,
) -> dict[str, tuple[str, ...]]:
    first_by_id = {packet.scope_id: packet for packet in first.packets}
    second_by_id = {packet.scope_id: packet for packet in second.packets}
    return {
        scope_id: tuple(
            field
            for field in MATERIAL_FIELDS
            if getattr(first_by_id[scope_id], field)
            != getattr(second_by_id[scope_id], field)
        )
        for scope_id in first_by_id
        if any(
            getattr(first_by_id[scope_id], field)
            != getattr(second_by_id[scope_id], field)
            for field in MATERIAL_FIELDS
        )
    }


def resolution_report(
    *,
    corpus: CorpusArtifact,
    first: BatchLoad,
    second: BatchLoad,
    tiebreaker: BatchLoad,
    adjudicator_ids: Mapping[str, str],
) -> dict[str, object]:
    if first.batch is None or second.batch is None:
        raise ValueError("both primary adjudications must be schema-valid")
    disputes = compare_primary_batches(first.batch, second.batch)
    unresolved = (
        tuple(sorted(disputes))
        if tiebreaker.batch is None
        else _unresolved(
            disputes=disputes,
            first=first.batch,
            second=second.batch,
            tiebreaker=tiebreaker.batch,
        )
    )
    total = len(corpus.scopes)
    unresolved_count = len(unresolved)
    artifact_valid = not first.errors and not second.errors and not tiebreaker.errors
    reliable = unresolved_count * 5 <= total and artifact_valid
    return {
        "schema_version": "source_general_claim_verification.resolution.v1",
        "source_scope_count": total,
        "material_fields": MATERIAL_FIELDS,
        "adjudicators": {
            "first": _batch_receipt(first, adjudicator_ids["first"]),
            "second": _batch_receipt(second, adjudicator_ids["second"]),
            "tiebreaker": _batch_receipt(tiebreaker, adjudicator_ids["tiebreaker"]),
        },
        "initial_disagreement": {
            "numerator": len(disputes),
            "denominator": total,
            "rate": len(disputes) / total,
            "fields_by_scope": disputes,
        },
        "primary_artifacts_valid": not first.errors and not second.errors,
        "tiebreaker_schema_valid": tiebreaker.batch is not None,
        "tiebreaker_errors": tiebreaker.errors,
        "unresolved_disagreement": {
            "numerator": unresolved_count,
            "denominator": total,
            "rate": unresolved_count / total,
            "scope_ids": unresolved,
        },
        "stop_threshold": {
            "operator": "GREATER_THAN",
            "numerator": 1,
            "denominator": 5,
        },
        "reference_set_reliable": reliable,
        "terminal": (
            "INVALID_ADJUDICATION_CHECKPOINT"
            if not artifact_valid
            else (
                "REFERENCE_SET_READY" if reliable else "STOP_REFERENCE_SET_UNRELIABLE"
            )
        ),
    }


def _unresolved(
    *,
    disputes: Mapping[str, tuple[str, ...]],
    first: RawAdjudicationBatch,
    second: RawAdjudicationBatch,
    tiebreaker: RawAdjudicationBatch,
) -> tuple[str, ...]:
    first_by_id = {packet.scope_id: packet for packet in first.packets}
    second_by_id = {packet.scope_id: packet for packet in second.packets}
    third_by_id = {packet.scope_id: packet for packet in tiebreaker.packets}
    unresolved: list[str] = []
    for scope_id, fields in disputes.items():
        third = third_by_id.get(scope_id)
        if third is None or any(
            getattr(third, field)
            not in {
                getattr(first_by_id[scope_id], field),
                getattr(second_by_id[scope_id], field),
            }
            for field in fields
        ):
            unresolved.append(scope_id)
    return tuple(sorted(unresolved))


def _batch_errors(
    batch: RawAdjudicationBatch,
    *,
    corpus: CorpusArtifact,
    expected_count: int,
) -> tuple[str, ...]:
    errors: list[str] = []
    if batch.scope_count != expected_count or len(batch.packets) != expected_count:
        errors.append("batch scope count does not match the sealed request")
    scopes = {scope.scope_id: scope for scope in corpus.scopes}
    sources = {source.source_id: source for source in corpus.sources}
    if len({packet.scope_id for packet in batch.packets}) != len(batch.packets):
        errors.append("batch contains duplicate scope IDs")
    for packet in batch.packets:
        scope = scopes.get(packet.scope_id)
        source = sources.get(packet.source_label)
        if scope is None or source is None:
            errors.append(f"unknown source or scope: {packet.scope_id}")
            continue
        if (
            packet.source_sha256 != source.source_sha256
            or packet.passage_start != scope.scope.start
            or packet.passage_end != scope.scope.end
            or packet.exact_passage != scope.scope.text
        ):
            errors.append(f"source custody mismatch: {packet.scope_id}")
            continue
        for exact in _exact_strings(packet):
            if exact not in packet.exact_passage:
                errors.append(f"unresolved local evidence: {packet.scope_id}")
                break
    return tuple(errors)


def _exact_strings(packet: RawAdjudicationPacket) -> tuple[str, ...]:
    values = [participant.exact_span for participant in packet.participants]
    values.extend(quantity.exact_span for quantity in packet.quantitative_evidence)
    values.extend(packet.statistical_observation.exact_spans)
    values.extend(modifier.exact_span for modifier in packet.required_modifiers)
    values.extend(packet.acceptable_equivalent_evidence_spans)
    values.extend(packet.evidence_spans)
    values.extend(
        span
        for span in (
            packet.comparison.lhs_exact_span,
            packet.comparison.rhs_exact_span,
        )
        if span is not None
    )
    return tuple(values)


def _batch_receipt(load: BatchLoad, agent_id: str) -> dict[str, object]:
    return {
        "agent_id": agent_id,
        "model_id": "gpt-5.6-sol",
        "artifact_sha256": load.sha256,
        "schema_parsed": load.batch is not None,
        "artifact_valid": load.batch is not None and not load.errors,
        "validation_error_count": len(load.errors),
        "provider_response_id": None,
        "token_accounting": "UNAVAILABLE_FOR_CODEX_SUBAGENT_TASK",
    }


def canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


__all__ = [
    "BatchLoad",
    "MATERIAL_FIELDS",
    "canonical_json",
    "compare_primary_batches",
    "load_and_validate_raw_batch",
    "resolution_report",
]
