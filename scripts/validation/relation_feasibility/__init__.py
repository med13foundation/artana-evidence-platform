"""Relation feasibility audit loop for evidence extraction quality."""

from scripts.validation.relation_feasibility.adversarial import (
    AdversarialFinding,
    find_quality_illusions,
)
from scripts.validation.relation_feasibility.io import load_benchmark_cases
from scripts.validation.relation_feasibility.models import (
    BenchmarkCase,
    CandidateAssessment,
    CaseResult,
    ExtractedRelation,
    ExtractionTrace,
    FeasibilityReport,
    FeasibilitySummary,
    GoldRelation,
    RelationExtractionResult,
)
from scripts.validation.relation_feasibility.reporting import render_markdown_report
from scripts.validation.relation_feasibility.runner import run_feasibility_audit

__all__ = [
    "AdversarialFinding",
    "BenchmarkCase",
    "CandidateAssessment",
    "CaseResult",
    "ExtractionTrace",
    "ExtractedRelation",
    "FeasibilityReport",
    "FeasibilitySummary",
    "GoldRelation",
    "RelationExtractionResult",
    "find_quality_illusions",
    "load_benchmark_cases",
    "render_markdown_report",
    "run_feasibility_audit",
]
