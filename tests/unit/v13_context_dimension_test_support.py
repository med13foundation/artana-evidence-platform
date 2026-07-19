"""Shared provider-free fixtures for V13 context-dimension tests."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import cast

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitExtractionOutput,
)
from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    MaterialAxis,
)
from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    SourceUnitNormalizationResult,
    bind_source_unit_normalization,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_contracts import (
    SourceUnitNormalizationOutputV13,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    SourceUnitExtractionResult,
    bind_source_unit_extraction,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    FrozenSourceUnit,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_PATH = (
    _REPOSITORY_ROOT
    / "docs"
    / "validation"
    / "receipts"
    / "2026-07-19-tg04-v13-visible-anaphoric-outputs.json"
)
_CONSUMED_REPORT_PATH = (
    _REPOSITORY_ROOT
    / "docs"
    / "validation"
    / "reports"
    / "2026-07-19-tg04-v13-visible-anaphoric-result.md"
)
_CONSUMED_RESULT_PATH = (
    _REPOSITORY_ROOT
    / "docs"
    / "validation"
    / "receipts"
    / "2026-07-19-tg04-v13-visible-anaphoric-result.json"
)
_CONSUMED_JOURNAL_PATH = (
    _REPOSITORY_ROOT
    / "docs"
    / "validation"
    / "receipts"
    / "2026-07-19-tg04-v13-visible-anaphoric-journal.jsonl"
)
_CONSUMED_NORMALIZATION_SHA256 = (
    "9d60dee6b209f3f2293942f46b36abd1a8b4f29b6a68d4c1e7d0ab10c09645d6"
)
_CONSUMED_SOURCE_SHA256 = (
    "5a9b163d436c6c64d8cc286f33a80a37d3821485165f9d010d7dc1a919e5e508"
)
_CONSUMED_ORIGINAL_SHA256 = (
    "0c500e172488802683fba60c92c1ba1e9823ef077e95baaede83ab097940a534"
)
_CONSUMED_FIXTURE_SHA256 = (
    "6512db3902a28447cc8a28b71335e6e734c7151a50779ca10839632e98b16f98"
)
_CONSUMED_REPORT_FILE_SHA256 = (
    "8ce42d8c4249fe1582f56a2104a7a4ca0cac71a0081e73743b4f427f54236634"
)


def _fixture() -> dict[str, object]:
    return cast(
        "dict[str, object]",
        json.loads(_FIXTURE_PATH.read_text(encoding="utf-8")),
    )


def _payload(fixture: dict[str, object], key: str) -> dict[str, object]:
    return cast("dict[str, object]", fixture[key])


def _unit(source: str) -> FrozenSourceUnit:
    source_sha256 = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return FrozenSourceUnit(
        unit_id=f"source-unit-{source_sha256}",
        index=0,
        source_start=0,
        source_end=len(source),
        text=source,
        source_sha256=source_sha256,
    )


def _original(
    *,
    fixture: dict[str, object],
    unit: FrozenSourceUnit,
) -> SourceUnitExtractionResult:
    output = SourceUnitExtractionOutput.model_validate(_payload(fixture, "original"))
    return bind_source_unit_extraction(output, unit=unit)


def _review_payload(
    *,
    source: str,
    dimension_id: str,
    factor_eligibility: str,
    level_set_validity: str,
    event_scope_validity: str,
    crossing_validity: str,
    dimension_decision: str,
    context_axis_decision: str,
    unsupported_additions: str,
    factor_span: str = "genotype",
    level_spans: tuple[str, ...] = ("MEK1-null genotype", "EGF"),
    contrast_evidence_span: str | None = None,
    event_scope_evidence_span: str | None = None,
    crossing_evidence_span: str | None = None,
) -> dict[str, object]:
    return {
        "eligibility_category": "FINDING",
        "inventory_coverage": "COMPLETE",
        "unsupported_additions": unsupported_additions,
        "family_validity": "VALID",
        "cue_alignment": "SURFACE_EQUIVALENT",
        "axis_reviews": [
            {
                "axis": axis.value,
                "decision": (
                    context_axis_decision
                    if axis is MaterialAxis.CONTEXT_SCOPE
                    else "PRESERVED"
                ),
                "evidence_spans": [source],
                "reasoning": "The source supports this categorical axis decision.",
                "falsification_condition": "Different source wording would change it.",
            }
            for axis in MaterialAxis
        ],
        "candidate_reviews": [
            {
                "normalized_event_position": position,
                "source_entailment": "ENTAILED",
                "evidence_spans": [source],
                "reasoning": "The complete normalized event is source entailed.",
                "falsification_condition": "A missing participant would falsify it.",
            }
            for position in range(2)
        ],
        "context_dimension_reviews": [
            _context_review(
                source=source,
                position=0,
                dimension_id=dimension_id,
                factor_eligibility=factor_eligibility,
                level_set_validity=level_set_validity,
                event_scope_validity=event_scope_validity,
                crossing_validity=crossing_validity,
                dimension_decision=dimension_decision,
                factor_span=factor_span,
                level_spans=level_spans,
                contrast_evidence_span=contrast_evidence_span,
                event_scope_evidence_span=event_scope_evidence_span,
                crossing_evidence_span=crossing_evidence_span,
            )
        ],
        "reasoning": "Every event and context proposal was reviewed independently.",
        "falsification_condition": "Contrary source evidence would change the review.",
    }


def _context_review(
    *,
    source: str,
    position: int,
    dimension_id: str,
    factor_eligibility: str,
    level_set_validity: str,
    event_scope_validity: str,
    crossing_validity: str,
    dimension_decision: str,
    factor_span: str,
    level_spans: tuple[str, ...],
    contrast_evidence_span: str | None = None,
    event_scope_evidence_span: str | None = None,
    crossing_evidence_span: str | None = None,
) -> dict[str, object]:
    memberships = _level_memberships(
        level_set_validity=level_set_validity,
        level_count=len(level_spans),
    )
    return {
        "context_dimension_position": position,
        "dimension_id": dimension_id,
        "factor_eligibility": factor_eligibility,
        "level_set_validity": level_set_validity,
        "event_scope_validity": event_scope_validity,
        "crossing_validity": crossing_validity,
        "decision": dimension_decision,
        "factor_evidence_spans": [factor_span],
        "level_reviews": [
            {
                "level_position": position,
                "level_span": level_span,
                "membership": membership,
                "evidence_spans": [level_span],
                "reasoning": "The level is reviewed against the proposed factor.",
                "falsification_condition": "A different factor would change membership.",
            }
            for position, (level_span, membership) in enumerate(
                zip(level_spans, memberships, strict=True)
            )
        ],
        "contrast_evidence_spans": [contrast_evidence_span or source],
        "event_scope_evidence_spans": [event_scope_evidence_span or source],
        "crossing_evidence_spans": (
            []
            if crossing_validity == "NOT_APPLICABLE"
            else [crossing_evidence_span or source]
        ),
        "reasoning": "The source-only categorical review is explicit.",
        "falsification_condition": "A different factor structure would change it.",
    }


def _level_memberships(*, level_set_validity: str, level_count: int) -> tuple[str, ...]:
    if level_set_validity == "MIXED_OR_UNRELATED":
        return ("SAME_FACTOR_LEVEL",) + ("UNRELATED_OR_MIXED",) * (level_count - 1)
    if level_set_validity == "IMPLICIT_OR_INFERRED":
        return ("SAME_FACTOR_LEVEL",) + ("IMPLICIT_OR_INFERRED",) * (level_count - 1)
    if level_set_validity == "ABSTAIN":
        return ("ABSTAIN",) * level_count
    return ("SAME_FACTOR_LEVEL",) * level_count


def _all_verbatim_mixed_context(
    *, fixture: dict[str, object], unit: FrozenSourceUnit
) -> SourceUnitNormalizationResult:
    original = _original(fixture=fixture, unit=unit)
    payload = deepcopy(_payload(fixture, "normalization"))
    payload["context_dimensions"] = [
        {
            "dimension_id": "mixed-participants",
            "dimension_type": "GENOTYPE",
            "operator": "ALTERNATIVE_LEVELS",
            "factor_span": "genotype",
            "level_spans": ["MEK1-null genotype", "EGF"],
            "applies_to_local_event_ids": ["reduction-1"],
            "crossed_dimension_ids": [],
            "reasoning": "Adversarial all-verbatim but unrelated level set.",
            "falsification_condition": "The levels are not one source factor.",
        }
    ]
    normalized = SourceUnitNormalizationOutputV13.model_validate(payload)
    return bind_source_unit_normalization(normalized, unit=unit, original=original)
