"""Semantic evidence-selection diagnostic contracts and reporting."""

from .fixture import (
    EvidenceSelectionSemanticDiagnosticCase,
    EvidenceSelectionSemanticDiagnosticFixture,
    EvidenceSelectionSemanticDiagnosticRecord,
    load_semantic_diagnostic_fixture,
)
from .predictions import (
    EvidenceSelectionSemanticPrediction,
    EvidenceSelectionSemanticPredictionArtifact,
    EvidenceSelectionSemanticSourceArtifact,
    load_semantic_prediction_artifact,
    verify_prediction_provenance,
)
from .report import (
    EvidenceSelectionSemanticDiagnosticReport,
    build_semantic_diagnostic_report,
    render_semantic_diagnostic_markdown,
)
from .scoring import (
    EvidenceSelectionSemanticDiagnosticScore,
    score_semantic_diagnostic,
)

__all__ = [
    "EvidenceSelectionSemanticDiagnosticCase",
    "EvidenceSelectionSemanticDiagnosticFixture",
    "EvidenceSelectionSemanticDiagnosticRecord",
    "EvidenceSelectionSemanticDiagnosticReport",
    "EvidenceSelectionSemanticDiagnosticScore",
    "EvidenceSelectionSemanticSourceArtifact",
    "EvidenceSelectionSemanticPrediction",
    "EvidenceSelectionSemanticPredictionArtifact",
    "build_semantic_diagnostic_report",
    "load_semantic_diagnostic_fixture",
    "load_semantic_prediction_artifact",
    "render_semantic_diagnostic_markdown",
    "score_semantic_diagnostic",
    "verify_prediction_provenance",
]
