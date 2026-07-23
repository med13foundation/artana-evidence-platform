"""Offline-only V3 preflight and exposed-case replay."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    write_json_atomic,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.contracts import (
    FreshCGSelectionV2,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v3.config import (
    DEFAULT_PATHS,
    FreshCGV3Paths,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v3.contracts import (
    ExposedCaseReplayV3,
    RootCauseConsensus,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v3.evaluation import (
    evaluate_exposed_case,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v3.reference import (
    build_exposed_reference,
    write_exposed_reference,
)

SEALED_HASHES = {
    "docs/validation/preregistrations/2026-07-22-fresh-cg-occurrence-v2-v1.json": (
        "2b26d580422efedcb44b7de8d8b7e973f2dae04bff020cdce85f3b2b8d4c1b98"
    ),
    "docs/validation/receipts/"
    "2026-07-22-fresh-cg-occurrence-v2-v1-"
    "fresh-cg-pmid-21963494-e3-attempt.json": (
        "52a66f88efbda9982f7d90ff8b83b3eefcfed838e2ea622435ef867ada8538db"
    ),
    "docs/validation/results/2026-07-22-fresh-cg-occurrence-v2-v1.json": (
        "2a006ea527ef2f22670dd1ec61d9a39e099cac415047852a3f44cd4b8b67544a"
    ),
    "docs/validation/reports/2026-07-22-fresh-cg-occurrence-v2-v1-final.md": (
        "2b350fac9cd0cdc9a1207dc85b23cb9fd833b9b4d31af6ba4d3ac71d601c8a6a"
    ),
    "docs/validation/preregistrations/2026-07-22-fresh-cg-occurrence-v2-v2.json": (
        "144d54d3acbee866401499758603ace87a3e4c74deb0c970695234f8c7e52577"
    ),
    "docs/validation/fixtures/2026-07-22-fresh-cg-selection-v2.json": (
        "bd91c3472ccfb8b30bc0ae451a1c33c081b9336e2d4bd11762bae89559919b0d"
    ),
    "docs/validation/results/2026-07-22-fresh-cg-occurrence-v2-v2.json": (
        "b98ac29ae7d2899b2781329d1cd9462e1948818e7b7c1160ab1ecebfc34e2ab5"
    ),
    "docs/validation/reports/2026-07-22-fresh-cg-occurrence-v2-v2-final.md": (
        "c0ca28ecaa9701a6fc610165c8ae63f71286737c4da082204619d63f2d9041d9"
    ),
    "docs/validation/references/2026-07-22-fresh-cg-two-lane-reference-v2.json": (
        "e2f4ca70daa76501c6ca6038ac7c62655647b91425966ba84c8e733f02e04f0b"
    ),
}


def preflight(paths: FreshCGV3Paths = DEFAULT_PATHS) -> dict[str, object]:
    """Verify sealed inputs, adjudicator custody, and seven-case preservation."""

    for relative_path, expected in SEALED_HASHES.items():
        path = paths.selection.parents[3] / relative_path
        if _sha256(path) != expected:
            raise ValueError(f"sealed artifact changed: {relative_path}")
    consensus = RootCauseConsensus.model_validate_json(
        paths.consensus.read_text(encoding="utf-8")
    )
    if _sha256(paths.dispute_packet) != consensus.dispute_packet_sha256:
        raise ValueError("dispute packet differs from consensus pin")
    adjudicator_paths = {
        "fresh-cg-v2-occurrence-adjudicator-v1": paths.occurrence_adjudication,
        "fresh-cg-v2-semantics-adjudicator": paths.semantics_adjudication,
    }
    for adjudicator_id, path in adjudicator_paths.items():
        if _sha256(path) != consensus.adjudicator_sha256_by_id[adjudicator_id]:
            raise ValueError(f"adjudicator artifact changed: {adjudicator_id}")
    selection = FreshCGSelectionV2.model_validate_json(
        paths.selection.read_text(encoding="utf-8")
    )
    v2_result = _object(json.loads(paths.v2_evaluation.read_text(encoding="utf-8")))
    metrics = _object(v2_result["metrics"])
    if selection.cases[0].case_id != consensus.case_id:
        raise ValueError("consensus case is not the exposed V2 case")
    reference = build_exposed_reference(
        v2_reference_path=paths.v2_reference,
        dispute_packet_path=paths.dispute_packet,
        consensus_path=paths.consensus,
    )
    return {
        "status": "PASS",
        "case_id": consensus.case_id,
        "adjudicator_count": len(adjudicator_paths),
        "tiebreaker_run": consensus.tiebreaker_run,
        "v3_reference_sha256_if_written": hashlib.sha256(
            (
                json.dumps(reference.model_dump(mode="json"), indent=2, sort_keys=True)
                + "\n"
            ).encode()
        ).hexdigest(),
        "raw_v2_unsupported_count": metrics["unsupported_claim_count"],
        "remaining_fresh_cases_preserved": len(selection.cases) - 1,
        "scientific_provider_calls": 0,
        "graph_writes": 0,
        "qualification_credit": False,
    }


def replay(paths: FreshCGV3Paths = DEFAULT_PATHS) -> ExposedCaseReplayV3:
    """Write a new reference and diagnostic replay; never alter sealed V2."""

    preflight_result = preflight(paths)
    reference = build_exposed_reference(
        v2_reference_path=paths.v2_reference,
        dispute_packet_path=paths.dispute_packet,
        consensus_path=paths.consensus,
    )
    write_exposed_reference(paths.reference, reference)
    result = evaluate_exposed_case(
        reference_path=paths.reference,
        raw_output_path=paths.v2_raw_output,
        consensus_path=paths.consensus,
        raw_v2_unsupported_count=cast(
            "int",
            preflight_result["raw_v2_unsupported_count"],
        ),
    )
    write_json_atomic(paths.result, result.model_dump(mode="json"))
    return result


def _object(value: object) -> dict[str, object]:
    return cast("dict[str, object]", value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = ["SEALED_HASHES", "preflight", "replay"]
