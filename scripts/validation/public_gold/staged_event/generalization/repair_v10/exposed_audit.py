"""Offline V10 boundary audit over existing exposed V9 outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, cast

from pydantic import Field

from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    write_json_atomic,
)
from scripts.validation.public_gold.staged_event.contracts import StrictStageModel
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.config import (
    DEFAULT_PATHS,
    V10Paths,
)
from scripts.validation.public_gold.staged_event.generalization.span_identity import (
    source_spans_equivalent,
)

_GENERIC_SUFFIXES = (" gene", " protein")


class BoundaryAuditFinding(StrictStageModel):
    case_id: str = Field(min_length=1)
    participant_id: str = Field(min_length=1)
    original_text: str = Field(min_length=1)
    corrected_text: str = Field(min_length=1)
    suffix: Literal[" gene", " protein"]
    exact_source_compatibility: Literal[True]
    existing_evaluator_containment_compatibility: Literal[True]


class ExposedBoundaryAudit(StrictStageModel):
    schema_version: Literal[
        "artana.staged_generalization.v10_exposed_boundary_audit.v1"
    ] = "artana.staged_generalization.v10_exposed_boundary_audit.v1"
    exposed_case_count: int = Field(ge=1)
    exposed_participant_count: int = Field(ge=1)
    findings: tuple[BoundaryAuditFinding, ...]
    changed_participant_count: int = Field(ge=1)
    unchanged_participant_count: int = Field(ge=0)
    all_existing_evaluator_matches_preserved: Literal[True]
    provider_calls: Literal[0] = 0
    fresh_cases_consumed: Literal[0] = 0
    graph_writes: Literal[0] = 0
    qualification_credit: Literal[False] = False


def audit(paths: V10Paths = DEFAULT_PATHS) -> ExposedBoundaryAudit:
    """Find generic suffix expansions without changing any stored output."""

    panel = _object(json.loads(paths.exposed_panel.read_text(encoding="utf-8")))
    sources = {
        cast("str", item["case_id"]): cast("str", item["source"])
        for item in _objects(panel["cases"])
    }
    raw_paths = tuple(
        sorted(
            paths.exposed_raw_outputs.glob(
                "2026-07-22-staged-generalization-v9-*-raw.json"
            )
        )
    )
    findings: list[BoundaryAuditFinding] = []
    participant_count = 0
    for raw_path in raw_paths:
        output = V9StagedGeneralizationOutput.model_validate_json(
            raw_path.read_text(encoding="utf-8")
        )
        source = sources[output.case_id]
        participant_count += len(output.participants)
        for participant in output.participants:
            if participant.entity_type != "GENE_OR_PROTEIN":
                continue
            suffix = next(
                (
                    candidate
                    for candidate in _GENERIC_SUFFIXES
                    if participant.exact_text.endswith(candidate)
                ),
                None,
            )
            if suffix is None:
                continue
            corrected = participant.exact_text.removesuffix(suffix)
            evidence_start = source.find(participant.exact_evidence)
            evidence_end = evidence_start + len(participant.exact_evidence)
            source_compatible = (
                corrected in participant.exact_evidence and evidence_start >= 0
            )
            evaluator_compatible = source_spans_equivalent(
                source=source,
                scope_start=evidence_start,
                scope_end=evidence_end,
                actual_text=corrected,
                expected_text=participant.exact_text,
            )
            if not source_compatible or not evaluator_compatible:
                raise ValueError("V10 boundary correction breaks exposed compatibility")
            findings.append(
                BoundaryAuditFinding(
                    case_id=output.case_id,
                    participant_id=participant.participant_id,
                    original_text=participant.exact_text,
                    corrected_text=corrected,
                    suffix=cast('Literal[" gene", " protein"]', suffix),
                    exact_source_compatibility=True,
                    existing_evaluator_containment_compatibility=True,
                )
            )
    if not findings:
        raise ValueError("exposed audit did not exercise the V10 correction")
    return ExposedBoundaryAudit(
        exposed_case_count=len(raw_paths),
        exposed_participant_count=participant_count,
        findings=tuple(findings),
        changed_participant_count=len(findings),
        unchanged_participant_count=participant_count - len(findings),
        all_existing_evaluator_matches_preserved=True,
    )


def write_audit(
    path: Path,
    result: ExposedBoundaryAudit,
) -> None:
    write_json_atomic(path, result.model_dump(mode="json"))


def _object(value: object) -> dict[str, object]:
    return cast("dict[str, object]", value)


def _objects(value: object) -> list[dict[str, object]]:
    return [_object(item) for item in cast("list[object]", value)]


__all__ = ["BoundaryAuditFinding", "ExposedBoundaryAudit", "audit", "write_audit"]
