"""Executable relation feasibility audit loop."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.evidence_support_verifier import (
        TripleSupportModel,
    )

from scripts.validation.relation_feasibility.models import (
    BenchmarkCase,
    CaseResult,
    ExtractedRelation,
    ExtractionTrace,
    FeasibilityReport,
    RelationExtractionResult,
)
from scripts.validation.relation_feasibility.scoring import (
    assess_case,
)
from scripts.validation.relation_feasibility.summary_scoring import (
    SummaryInputs,
    build_summary,
)

RelationExtractor = Callable[
    [str],
    Sequence[ExtractedRelation] | RelationExtractionResult,
]


def run_feasibility_audit(
    *,
    cases: Sequence[BenchmarkCase],
    extractor: RelationExtractor,
    require_agent_completion: bool = False,
    support_verifier: TripleSupportModel | None = None,
) -> FeasibilityReport:
    """Run extraction and quality scoring for all benchmark cases."""

    case_results: list[CaseResult] = []
    case_assessments = []
    extraction_traces: list[ExtractionTrace] = []
    relation_type_surface_sets = []
    case_gold_relation_sets = []
    case_categories: list[str] = []
    case_gold_relation_counts: list[int] = []
    case_missed_gold_counts: list[int] = []
    missed_gold_count = 0
    gold_relation_count = 0
    for case in cases:
        extraction_result = _normalize_extraction_result(extractor(case.text))
        candidates = extraction_result.relations
        trace = extraction_result.trace
        relation_type_surfaces = extraction_result.relation_type_surfaces
        assessments, missed_gold_indices = assess_case(
            case,
            candidates,
            support_verifier=support_verifier,
        )
        case_results.append(
            CaseResult(
                case=case,
                candidate_assessments=assessments,
                missed_gold_indices=missed_gold_indices,
                extraction_trace=trace,
                relation_type_surfaces=relation_type_surfaces,
            ),
        )
        case_assessments.append(assessments)
        extraction_traces.append(trace)
        relation_type_surface_sets.append(relation_type_surfaces)
        case_gold_relation_sets.append(case.gold_relations)
        case_categories.append(case.category)
        case_gold_relation_counts.append(len(case.gold_relations))
        case_missed_gold_counts.append(len(missed_gold_indices))
        missed_gold_count += len(missed_gold_indices)
        gold_relation_count += len(case.gold_relations)
    summary = build_summary(
        SummaryInputs(
            case_assessments=tuple(case_assessments),
            extraction_traces=tuple(extraction_traces),
            case_gold_relations=tuple(case_gold_relation_sets),
            case_gold_relation_counts=tuple(case_gold_relation_counts),
            case_missed_gold_counts=tuple(case_missed_gold_counts),
            case_categories=tuple(case_categories),
            relation_type_surfaces=tuple(relation_type_surface_sets),
            case_count=len(cases),
            gold_relation_count=gold_relation_count,
            missed_gold_count=missed_gold_count,
            require_agent_completion=require_agent_completion,
        ),
    )
    return FeasibilityReport(
        summary=summary,
        case_results=tuple(case_results),
    )


def _normalize_extraction_result(
    result: Sequence[ExtractedRelation] | RelationExtractionResult,
) -> RelationExtractionResult:
    if isinstance(result, RelationExtractionResult):
        return result
    return RelationExtractionResult(
        relations=tuple(result),
        trace=ExtractionTrace(extractor_mode="custom"),
    )
