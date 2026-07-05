#!/usr/bin/env python3
"""Run the relation feasibility audit against the current extractor."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

from artana_evidence_api.document_extraction import (
    discover_relation_candidates,  # noqa: E402
    extract_relation_candidates,  # noqa: E402
)
from artana_evidence_api.document_extraction_support.relation_specificity_pruning import (  # noqa: E402
    prune_redundant_generic_relation_candidates,
)
from artana_evidence_api.document_extraction_support.strict_relation_discovery import (  # noqa: E402
    discover_relation_candidates_strict,
)

from scripts.validation.relation_feasibility.io import (
    load_benchmark_cases,  # noqa: E402
)
from scripts.validation.relation_feasibility.live_agent_preflight import (  # noqa: E402
    LiveAgentPreflightError,
    ensure_live_agent_ready,
)
from scripts.validation.relation_feasibility.models import (
    ExtractedRelation,  # noqa: E402
    ExtractionTrace,  # noqa: E402
    RelationExtractionResult,  # noqa: E402
    RelationTypeSurface,  # noqa: E402
)
from scripts.validation.relation_feasibility.reporting import (  # noqa: E402
    render_markdown_report,
)
from scripts.validation.relation_feasibility.runner import (  # noqa: E402
    run_feasibility_audit,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_contracts import (
        DocumentCandidateExtractionDiagnostics,
        ExtractedRelationCandidate,
    )

_DEFAULT_CASES = (
    _REPO_ROOT
    / "scripts"
    / "validation"
    / "relation_feasibility"
    / "fixtures"
    / "biomedical_relation_goldset_v2.json"
)
_DEFAULT_REPORT_ROOT = _REPO_ROOT / "reports" / "relation_feasibility"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Run an agent-first relation extractor against a manually curated "
            "feasibility benchmark and emit JSON/Markdown quality reports."
        ),
    )
    parser.add_argument(
        "--extractor",
        choices=("agent", "deterministic"),
        default="agent",
        help=(
            "Extractor to evaluate. Defaults to agent, which runs the LLM-first "
            "document discovery path. deterministic is only for comparison."
        ),
    )
    parser.add_argument(
        "--allow-fallback",
        action="store_true",
        help=(
            "Allow LLM fallback/unavailable cases without forcing a RED verdict. "
            "By default, agent mode requires completed LLM extraction."
        ),
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=_DEFAULT_CASES,
        help="Benchmark JSON file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to reports/relation_feasibility/<timestamp>.",
    )
    return parser.parse_args(argv)


def extract_with_current_heuristic(text: str) -> RelationExtractionResult:
    """Run the current deterministic relation extractor."""

    pruning_result = prune_redundant_generic_relation_candidates(
        extract_relation_candidates(text),
    )
    candidates = pruning_result.candidates
    relations = tuple(
        ExtractedRelation(
            subject=candidate.subject_label,
            relation_type=candidate.relation_type,
            object=candidate.object_label,
            sentence=candidate.sentence,
            subject_curie=candidate.subject_curie,
            object_curie=candidate.object_curie,
            subject_curie_source=candidate.subject_curie_source,
            object_curie_source=candidate.object_curie_source,
            proposed_relation_type=candidate.proposed_relation_type,
            new_relation_type_rationale=candidate.new_relation_type_rationale,
            relation_governance_status=candidate.relation_governance_status,
        )
        for candidate in candidates
    )
    return RelationExtractionResult(
        relations=relations,
        trace=ExtractionTrace(
            extractor_mode="deterministic",
            pruned_generic_relation_count=pruning_result.pruned_count,
        ),
        relation_type_surfaces=_candidate_relation_type_surfaces(relations),
    )


def extract_with_agent(text: str) -> RelationExtractionResult:
    """Run the current LLM-first agent extraction path."""

    return asyncio.run(_extract_with_agent(text))


async def _extract_with_agent(text: str) -> RelationExtractionResult:
    candidates, diagnostics = await discover_relation_candidates_strict(
        text,
        space_context="Relation feasibility audit benchmark.",
    )
    return _agent_relation_extraction_result_from_candidates(
        candidates=candidates,
        diagnostics=diagnostics,
    )


def extract_with_agent_allowing_fallback(text: str) -> RelationExtractionResult:
    """Run the LLM-first discovery path that may use heuristic fallback."""

    return asyncio.run(_extract_with_agent_allowing_fallback(text))


async def _extract_with_agent_allowing_fallback(text: str) -> RelationExtractionResult:
    candidates, diagnostics = await discover_relation_candidates(
        text,
        space_context="Relation feasibility audit benchmark.",
    )
    return _agent_relation_extraction_result_from_candidates(
        candidates=candidates,
        diagnostics=diagnostics,
    )


def _agent_relation_extraction_result_from_candidates(
    *,
    candidates: Sequence[ExtractedRelationCandidate],
    diagnostics: DocumentCandidateExtractionDiagnostics,
) -> RelationExtractionResult:
    relations = tuple(
        ExtractedRelation(
            subject=candidate.subject_label,
            relation_type=candidate.relation_type,
            object=candidate.object_label,
            sentence=candidate.sentence,
            subject_curie=candidate.subject_curie,
            object_curie=candidate.object_curie,
            subject_curie_source=candidate.subject_curie_source,
            object_curie_source=candidate.object_curie_source,
            proposed_relation_type=candidate.proposed_relation_type,
            new_relation_type_rationale=candidate.new_relation_type_rationale,
            relation_governance_status=candidate.relation_governance_status,
        )
        for candidate in candidates
    )
    return RelationExtractionResult(
        relations=relations,
        trace=ExtractionTrace(
            extractor_mode="agent",
            llm_candidate_status=diagnostics.llm_candidate_status,
            llm_candidate_error=diagnostics.llm_candidate_error,
            llm_candidate_count=diagnostics.llm_candidate_count,
            fallback_candidate_count=diagnostics.fallback_candidate_count,
            pruned_generic_relation_count=diagnostics.pruned_generic_relation_count,
            quality_filtered_candidate_count=(
                diagnostics.quality_filtered_candidate_count
            ),
        ),
        relation_type_surfaces=_candidate_relation_type_surfaces(relations),
    )


def _candidate_relation_type_surfaces(
    relations: tuple[ExtractedRelation, ...],
) -> tuple[RelationTypeSurface, ...]:
    surfaces: list[RelationTypeSurface] = []
    for relation in relations:
        source_ref = f"{relation.subject}->{relation.object}"
        surfaces.append(
            RelationTypeSurface(
                surface="candidate_relation.relation_type",
                relation_type=relation.relation_type,
                source_ref=source_ref,
                governance_status=relation.relation_governance_status,
            ),
        )
        if relation.proposed_relation_type is not None:
            surfaces.append(
                RelationTypeSurface(
                    surface="candidate_relation.proposed_relation_type",
                    relation_type=relation.proposed_relation_type,
                    source_ref=source_ref,
                    governance_status=relation.relation_governance_status,
                ),
            )
    return tuple(surfaces)


def main() -> int:
    """Run the audit and write report artifacts."""

    args = parse_args()
    strict_agent = args.extractor == "agent" and not args.allow_fallback
    if strict_agent:
        try:
            ensure_live_agent_ready()
        except LiveAgentPreflightError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    output_dir = args.output_dir or _timestamped_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    cases = load_benchmark_cases(args.cases)
    extractor = (
        (extract_with_agent if strict_agent else extract_with_agent_allowing_fallback)
        if args.extractor == "agent"
        else extract_with_current_heuristic
    )
    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        require_agent_completion=args.extractor == "agent" and not args.allow_fallback,
    )
    json_path = output_dir / "relation_feasibility_report.json"
    markdown_path = output_dir / "relation_feasibility_report.md"
    json_path.write_text(json.dumps(report.to_json(), indent=2) + "\n")
    markdown_path.write_text(render_markdown_report(report))

    summary = report.summary
    print(
        "relation_feasibility "
        f"verdict={summary.verdict} "
        f"all_candidate_precision={summary.precision_against_gold:.4f} "
        f"all_candidate_recall={summary.recall_against_gold:.4f} "
        f"high_value_recall={summary.high_value_recall:.4f} "
        f"low_value_recall={summary.low_value_recall:.4f} "
        f"all_candidate_valuable_rate={summary.valuable_candidate_rate:.4f} "
        f"governed_proposal_recall={summary.proposal_recall_against_gold:.4f} "
        f"governed_proposal_eligible_recall={summary.proposal_recall_against_proposal_eligible_gold:.4f} "
        f"governed_proposal_candidates={summary.proposal_candidate_count} "
        f"completed_agent_precision={summary.completed_agent_precision_against_gold:.4f} "
        f"completed_agent_recall={summary.completed_agent_recall_against_gold:.4f} "
        f"completed_agent_valuable_rate={summary.completed_agent_valuable_candidate_rate:.4f} "
        f"all_candidate_generic_relation_rate={summary.generic_relation_rate:.4f} "
        f"pruned_generic_relations={summary.pruned_generic_relation_count} "
        f"quality_filtered_candidates={summary.quality_filtered_candidate_count} "
        f"candidate_curie_present_rate={summary.candidate_curie_present_rate:.4f} "
        f"verified_curie_match_rate={summary.verified_curie_match_rate:.4f} "
        f"model_curie_wrong_count={summary.model_curie_wrong_count} "
        f"all_candidate_curie_linked_gold_endpoint_rate={summary.curie_linked_gold_endpoint_rate:.4f} "
        f"agent_completed_cases={summary.agent_completed_case_count} "
        f"negative_control_cases={summary.negative_control_case_count} "
        f"negative_control_empty_cases={summary.negative_control_empty_count} "
        f"negative_control_leakage_cases={summary.negative_control_leakage_count} "
        f"fallback_cases={summary.fallback_case_count} "
        f"invalid_agent_cases={summary.invalid_agent_case_count}",
    )
    print(f"Wrote JSON report: {json_path}")
    print(f"Wrote Markdown report: {markdown_path}")
    return 0


def _timestamped_output_dir() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return _DEFAULT_REPORT_ROOT / timestamp


if __name__ == "__main__":
    raise SystemExit(main())
