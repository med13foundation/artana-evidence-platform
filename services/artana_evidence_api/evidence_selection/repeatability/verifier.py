"""Authoritative semantic verification for serialized comparison evidence."""

from __future__ import annotations

from pathlib import Path

from artana_evidence_api.evidence_selection.diagnostics.agent_evaluation import (
    EvidenceSelectionSemanticAgentEvaluation,
    render_semantic_agent_evaluation_markdown,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.evaluation import (
    evaluate_benchmark_v2,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.loader import (
    LoadedEvidenceSelectionBenchmarkV2,
    load_benchmark_v2,
)
from artana_evidence_api.evidence_selection.diagnostics.fixture import (
    load_semantic_diagnostic_fixture,
)
from artana_evidence_api.evidence_selection.diagnostics.report import (
    EvidenceSelectionSemanticDiagnosticReport,
)

from .artifacts import render_comparison_markdown, render_protocol_markdown
from .bundle import SemanticBundleManifest, verify_bundle
from .comparison import build_semantic_model_comparison
from .contracts import (
    SemanticModelComparisonProtocol,
    SemanticModelComparisonReport,
)
from .integrity import resolve_comparison_artifact_path
from .protocol import protocol_sha256, sha256_path
from .source_provenance import (
    BUNDLED_REPOSITORY_ROOT,
    verify_repository_source_provenance,
)


def verify_semantic_comparison_bundle(
    directory: Path,
) -> SemanticModelComparisonReport:
    """Reload and deterministically recompute every serialized proof field."""

    manifest = verify_bundle(directory)
    protocol = SemanticModelComparisonProtocol.model_validate_json(
        (directory / "semantic_model_comparison_protocol.json").read_text(
            encoding="utf-8",
        ),
    )
    report = SemanticModelComparisonReport.model_validate_json(
        (directory / "semantic_model_comparison_report.json").read_text(
            encoding="utf-8",
        ),
    )
    _verify_protocol_identity(manifest=manifest, protocol=protocol, report=report)
    fixture_path = directory / "sources/fixture.json"
    baseline_path = directory / "sources/baseline_report.json"
    if sha256_path(fixture_path) != protocol.fixture_sha256:
        raise ValueError("bundled fixture does not match the frozen protocol")
    if sha256_path(baseline_path) != protocol.baseline_report_sha256:
        raise ValueError("bundled baseline does not match the frozen protocol")
    fixture = load_semantic_diagnostic_fixture(fixture_path)
    baseline = EvidenceSelectionSemanticDiagnosticReport.model_validate_json(
        baseline_path.read_text(encoding="utf-8"),
    )
    if baseline.fixture_sha256 != protocol.fixture_sha256:
        raise ValueError("bundled baseline does not describe the frozen fixture")
    verify_repository_source_provenance(
        expected_files=protocol.repository_source_files,
        fixture=fixture,
        baseline=baseline,
        benchmark=_load_bundled_benchmark(
            protocol, directory / BUNDLED_REPOSITORY_ROOT
        ),
        repository_root=directory / BUNDLED_REPOSITORY_ROOT,
    )
    recomputed = build_semantic_model_comparison(
        protocol=protocol,
        fixture=fixture,
        current_runs=report.current_runs,
        candidate_runs=report.candidate_runs,
        generated_at=report.generated_at,
        artifact_root=directory,
        fixture_source_path=fixture_path,
    )
    if recomputed != report:
        raise ValueError("serialized comparison report does not match recomputation")
    _verify_run_markdown(directory=directory, report=report)
    expected_protocol_markdown = render_protocol_markdown(protocol)
    if (directory / "semantic_model_comparison_protocol.md").read_text(
        encoding="utf-8"
    ) != expected_protocol_markdown:
        raise ValueError("serialized protocol Markdown does not match the protocol")
    expected_report_markdown = render_comparison_markdown(report)
    if (directory / "semantic_model_comparison_report.md").read_text(
        encoding="utf-8"
    ) != expected_report_markdown:
        raise ValueError("serialized report Markdown does not match the report")
    return report


def _load_bundled_benchmark(
    protocol: SemanticModelComparisonProtocol,
    repository_root: Path,
) -> LoadedEvidenceSelectionBenchmarkV2:
    source = next(
        item
        for item in protocol.repository_source_files
        if item.role == "benchmark_fixture"
    )
    loaded = load_benchmark_v2(
        fixture_path=repository_root / source.relative_path,
        repository_root=repository_root,
    )
    if evaluate_benchmark_v2(loaded) != protocol.benchmark_evaluation:
        raise ValueError("bundled benchmark evaluation does not match protocol")
    return loaded


def _verify_run_markdown(
    *,
    directory: Path,
    report: SemanticModelComparisonReport,
) -> None:
    for run in (*report.current_runs, *report.candidate_runs):
        evaluation_path = resolve_comparison_artifact_path(
            reference=run.evaluation_path,
            artifact_root=directory,
        )
        evaluation = EvidenceSelectionSemanticAgentEvaluation.model_validate_json(
            evaluation_path.read_text(encoding="utf-8"),
        )
        markdown_path = evaluation_path.with_suffix(".md")
        expected = render_semantic_agent_evaluation_markdown(evaluation)
        if markdown_path.read_text(encoding="utf-8") != expected:
            raise ValueError(
                f"serialized run Markdown does not match: {markdown_path.name}",
            )


def _verify_protocol_identity(
    *,
    manifest: SemanticBundleManifest,
    protocol: SemanticModelComparisonProtocol,
    report: SemanticModelComparisonReport,
) -> None:
    digest = protocol_sha256(protocol)
    if manifest.protocol_sha256 != digest:
        raise ValueError("bundle manifest protocol digest does not match")
    if report.protocol != protocol or report.protocol_sha256 != digest:
        raise ValueError("comparison report protocol identity does not match")


__all__ = ["verify_semantic_comparison_bundle"]
