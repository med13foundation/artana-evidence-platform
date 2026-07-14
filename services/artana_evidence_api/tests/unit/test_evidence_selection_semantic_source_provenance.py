"""Semantic comparison source-provenance regression tests."""

from __future__ import annotations

import pytest
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.loader import (
    load_benchmark_v2,
)
from artana_evidence_api.evidence_selection.diagnostics.report import (
    EvidenceSelectionSemanticDiagnosticReport,
)
from artana_evidence_api.evidence_selection.repeatability.source_provenance import (
    build_repository_source_files,
)

from .evidence_selection_semantic_repeatability_test_support import (
    BASELINE_PATH,
    BENCHMARK_V2_PATH,
    REPOSITORY_ROOT,
    load_fixture,
)


def test_source_provenance_recomputes_baseline_score_from_predictions() -> None:
    baseline = EvidenceSelectionSemanticDiagnosticReport.model_validate_json(
        BASELINE_PATH.read_text(encoding="utf-8"),
    )
    forged_baseline = baseline.model_copy(
        update={
            "score": baseline.score.model_copy(
                update={"scored_case_count": baseline.score.scored_case_count + 1},
            ),
        },
    )

    with pytest.raises(ValueError, match="categorical predictions"):
        build_repository_source_files(
            fixture=load_fixture(),
            baseline=forged_baseline,
            benchmark=load_benchmark_v2(
                fixture_path=BENCHMARK_V2_PATH,
                repository_root=REPOSITORY_ROOT,
            ),
            repository_root=REPOSITORY_ROOT,
        )
