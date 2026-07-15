#!/usr/bin/env python3
"""Import externally signed human reviews through the staged expert-pilot gate."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

from artana_evidence_api.evidence_selection.cli_errors import (  # noqa: E402
    cli_error_message,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.expert_pilot.adjudication import (  # noqa: E402
    PreparedExpertPilotAdjudication,
    VerifiedExpertPilotAdjudication,
    build_expert_pilot_gold,
    load_and_verify_adjudication_completion,
    prepare_expert_pilot_adjudication,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.expert_pilot.evaluation import (  # noqa: E402
    LoadedExpertPilotModelRun,
    PreparedExpertPilotSafetyAudit,
    build_expert_pilot_result,
    load_and_verify_safety_completion,
    load_registered_model_runs,
    prepare_expert_pilot_safety_audit,
    render_expert_pilot_result_markdown,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.expert_pilot.publication import (  # noqa: E402
    publish_expert_pilot_stage,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.expert_pilot.review_loader import (  # noqa: E402
    LoadedExpertPilotPublication,
    VerifiedExpertPilotRegistry,
    VerifiedExpertPilotReviewCompletion,
    load_and_verify_first_pass_completions,
    load_and_verify_reviewer_registry,
    load_expert_pilot_evaluation_protocol,
    load_expert_pilot_publication,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.pilot_loader import (  # noqa: E402
    LoadedEvidenceSelectionExpertPilot,
    load_expert_pilot,
)

if TYPE_CHECKING:
    from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.expert_pilot.evaluation_contracts import (  # noqa: E402
        EvidenceSelectionExpertPilotEvaluationProtocol,
        EvidenceSelectionExpertPilotGoldArtifact,
    )


@dataclass(frozen=True, slots=True)
class _FirstPassContext:
    loaded_pilot: LoadedEvidenceSelectionExpertPilot
    evaluation_protocol: EvidenceSelectionExpertPilotEvaluationProtocol
    evaluation_protocol_sha256: str
    publication: LoadedExpertPilotPublication
    registry: VerifiedExpertPilotRegistry
    completions: tuple[VerifiedExpertPilotReviewCompletion, ...]
    prepared: PreparedExpertPilotAdjudication


@dataclass(frozen=True, slots=True)
class _GoldContext:
    first_pass: _FirstPassContext
    adjudication: VerifiedExpertPilotAdjudication | None
    gold: EvidenceSelectionExpertPilotGoldArtifact
    model_runs: tuple[LoadedExpertPilotModelRun, ...]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse one staged workflow command."""

    parser = argparse.ArgumentParser(
        description=(
            "Verify external expert attestations, create adjudicated gold, and "
            "compute deterministic semantic-selector pilot metrics."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_adjudication = subparsers.add_parser("prepare-adjudication")
    _add_common_args(prepare_adjudication)
    prepare_adjudication.add_argument("--output-dir", required=True, type=Path)

    prepare_safety = subparsers.add_parser("prepare-safety-audit")
    _add_common_args(prepare_safety)
    prepare_safety.add_argument("--adjudication-completion", type=Path)
    prepare_safety.add_argument("--output-dir", required=True, type=Path)

    finalize = subparsers.add_parser("finalize")
    _add_common_args(finalize)
    finalize.add_argument("--adjudication-completion", type=Path)
    finalize.add_argument("--safety-completion", required=True, type=Path)
    finalize.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Execute one stage and return a process-style status."""

    args = parse_args(argv)
    try:
        first_pass = _load_first_pass_context(args)
        if args.command == "prepare-adjudication":
            _publish_adjudication(first_pass=first_pass, output_dir=args.output_dir)
            item_count = len(first_pass.prepared.request.items)
            print(
                "evidence_selection_expert_pilot "
                f"stage=adjudication disagreements={item_count} "
                "production_readiness=false"
            )
            return 0
        gold_context = _load_gold_context(
            first_pass=first_pass,
            adjudication_path=args.adjudication_completion,
        )
        prepared_safety = prepare_expert_pilot_safety_audit(
            loaded_pilot=first_pass.loaded_pilot,
            evaluation_protocol_sha256=first_pass.evaluation_protocol_sha256,
            gold=gold_context.gold,
            model_runs=gold_context.model_runs,
        )
        if args.command == "prepare-safety-audit":
            _publish_safety(
                gold_context=gold_context,
                prepared_safety=prepared_safety,
                output_dir=args.output_dir,
            )
            print(
                "evidence_selection_expert_pilot "
                f"stage=safety claims={len(prepared_safety.request.items)} "
                f"expert_eligible={gold_context.gold.score_eligible_record_count} "
                "production_readiness=false"
            )
            return 0
        earliest_time = _latest_gold_input_time(gold_context)
        safety = load_and_verify_safety_completion(
            path=args.safety_completion,
            prepared=prepared_safety,
            registry=first_pass.registry,
            loaded_pilot=first_pass.loaded_pilot,
            earliest_time=earliest_time,
        )
        result = build_expert_pilot_result(
            protocol=first_pass.evaluation_protocol,
            gold=gold_context.gold,
            registry=first_pass.registry,
            model_runs=gold_context.model_runs,
            prepared_safety=prepared_safety,
            safety=safety,
        )
        publish_expert_pilot_stage(
            output_dir=args.output_dir,
            content_by_name={
                "adjudication_request.json": (
                    first_pass.prepared.request.model_dump_json(indent=2) + "\n"
                ),
                "gold.json": gold_context.gold.model_dump_json(indent=2) + "\n",
                "safety_request.json": prepared_safety.request.model_dump_json(indent=2)
                + "\n",
                "result.json": result.model_dump_json(indent=2) + "\n",
                "result.md": render_expert_pilot_result_markdown(result),
            },
        )
    except (OSError, ValueError, ValidationError) as exc:
        print(f"error: {cli_error_message(exc)}", file=sys.stderr)
        return 1
    print(
        "evidence_selection_expert_pilot "
        f"stage=final comparison={result.comparison_status} "
        f"expert_eligible={result.gold.score_eligible_record_count} "
        "production_readiness=false production_calibration=false "
        "trusted_graph_readiness=false"
    )
    print(f"Wrote verified expert-pilot result publication: {args.output_dir}")
    return 0


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pilot-protocol", required=True, type=Path)
    parser.add_argument("--evaluation-protocol", required=True, type=Path)
    parser.add_argument("--packet-publication", required=True, type=Path)
    parser.add_argument("--reviewer-registry", required=True, type=Path)
    parser.add_argument("--issuer-public-key-hex", required=True)
    parser.add_argument("--issuer-key-id", required=True)
    parser.add_argument("--first-pass-completions", required=True, type=Path)


def _load_first_pass_context(args: argparse.Namespace) -> _FirstPassContext:
    repository_root = Path.cwd().resolve()
    loaded_pilot = load_expert_pilot(
        protocol_path=args.pilot_protocol,
        repository_root=repository_root,
    )
    evaluation_protocol, evaluation_protocol_sha256 = (
        load_expert_pilot_evaluation_protocol(
            path=args.evaluation_protocol,
            repository_root=repository_root,
            loaded_pilot=loaded_pilot,
        )
    )
    publication = load_expert_pilot_publication(
        directory=args.packet_publication,
        loaded_pilot=loaded_pilot,
    )
    registry = load_and_verify_reviewer_registry(
        path=args.reviewer_registry,
        issuer_public_key_hex=args.issuer_public_key_hex,
        issuer_key_id=args.issuer_key_id,
        loaded_pilot=loaded_pilot,
        evaluation_protocol_sha256=evaluation_protocol_sha256,
        publication_manifest_sha256=publication.manifest_sha256,
    )
    completions = load_and_verify_first_pass_completions(
        directory=args.first_pass_completions,
        publication=publication,
        registry=registry,
        evaluation_protocol=evaluation_protocol,
        evaluation_protocol_sha256=evaluation_protocol_sha256,
    )
    prepared = prepare_expert_pilot_adjudication(
        loaded_pilot=loaded_pilot,
        evaluation_protocol_sha256=evaluation_protocol_sha256,
        registry=registry,
        completions=completions,
    )
    return _FirstPassContext(
        loaded_pilot=loaded_pilot,
        evaluation_protocol=evaluation_protocol,
        evaluation_protocol_sha256=evaluation_protocol_sha256,
        publication=publication,
        registry=registry,
        completions=completions,
        prepared=prepared,
    )


def _load_gold_context(
    *,
    first_pass: _FirstPassContext,
    adjudication_path: Path | None,
) -> _GoldContext:
    adjudication = load_and_verify_adjudication_completion(
        path=adjudication_path,
        prepared=first_pass.prepared,
        registry=first_pass.registry,
        loaded_pilot=first_pass.loaded_pilot,
    )
    gold = build_expert_pilot_gold(
        loaded_pilot=first_pass.loaded_pilot,
        evaluation_protocol_sha256=first_pass.evaluation_protocol_sha256,
        publication=first_pass.publication,
        registry=first_pass.registry,
        completions=first_pass.completions,
        prepared=first_pass.prepared,
        adjudication=adjudication,
    )
    model_runs = load_registered_model_runs(
        protocol=first_pass.evaluation_protocol,
        repository_root=Path.cwd(),
    )
    return _GoldContext(
        first_pass=first_pass,
        adjudication=adjudication,
        gold=gold,
        model_runs=model_runs,
    )


def _publish_adjudication(
    *,
    first_pass: _FirstPassContext,
    output_dir: Path,
) -> None:
    publish_expert_pilot_stage(
        output_dir=output_dir,
        content_by_name={
            "adjudication_request.json": (
                first_pass.prepared.request.model_dump_json(indent=2) + "\n"
            )
        },
    )


def _publish_safety(
    *,
    gold_context: _GoldContext,
    prepared_safety: PreparedExpertPilotSafetyAudit,
    output_dir: Path,
) -> None:
    publish_expert_pilot_stage(
        output_dir=output_dir,
        content_by_name={
            "adjudication_request.json": (
                gold_context.first_pass.prepared.request.model_dump_json(indent=2)
                + "\n"
            ),
            "gold.json": gold_context.gold.model_dump_json(indent=2) + "\n",
            "safety_request.json": prepared_safety.request.model_dump_json(indent=2)
            + "\n",
        },
    )


def _latest_gold_input_time(gold_context: _GoldContext) -> datetime:
    if gold_context.adjudication is not None:
        return gold_context.adjudication.signed_completion.payload.completed_at
    return max(
        completion.signed_completion.payload.completed_at
        for completion in gold_context.first_pass.completions
    )


if __name__ == "__main__":
    raise SystemExit(main())
