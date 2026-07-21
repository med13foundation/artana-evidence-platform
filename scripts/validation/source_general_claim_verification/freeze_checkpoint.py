#!/usr/bin/env python3
"""Freeze a failed or ready exposed-source adjudication checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.validation.source_general_claim_verification.corpus import load_corpus
from scripts.validation.source_general_claim_verification.hashing import (
    canonical_sha256,
)
from scripts.validation.source_general_claim_verification.raw_resolution import (
    canonical_json,
    load_and_validate_raw_batch,
    resolution_report,
)

AGENT_IDS = {
    "first": "019f81c4-7f89-7e52-8e7d-a5e9c3b59c1c",
    "second": "019f81c4-803f-7871-8c76-f02b437ca319",
    "tiebreaker": "019f81cc-122c-7d31-b69d-4f89b61d9dbe",
}


def freeze_checkpoint(*, corpus_path: Path, artifact_dir: Path) -> dict[str, object]:
    corpus = load_corpus(corpus_path)
    first = load_and_validate_raw_batch(
        artifact_dir / "adjudicator_a.json",
        corpus=corpus,
        expected_count=31,
    )
    second = load_and_validate_raw_batch(
        artifact_dir / "adjudicator_b.json",
        corpus=corpus,
        expected_count=31,
    )
    tiebreaker = load_and_validate_raw_batch(
        artifact_dir / "adjudicator_c.json",
        corpus=corpus,
        expected_count=30,
    )
    resolution = resolution_report(
        corpus=corpus,
        first=first,
        second=second,
        tiebreaker=tiebreaker,
        adjudicator_ids=AGENT_IDS,
    )
    resolution["corpus_sha256"] = canonical_sha256(corpus)
    resolution["resolution_sha256"] = canonical_sha256(resolution)
    _write_json(artifact_dir / "resolution.json", resolution)

    stopped = resolution["terminal"] != "REFERENCE_SET_READY"
    preregistration = {
        "schema_version": "source_general_claim_verification.preregistration.v1",
        "status": ("INVALID_ADJUDICATION_CHECKPOINT" if stopped else "READY"),
        "exposed_sources_only": True,
        "untouched_sources_allowed": False,
        "graph_promotion_allowed": False,
        "maximum_repairs_per_claim": 1,
        "agent_numeric_scores_allowed": False,
        "corpus_sha256": canonical_sha256(corpus),
        "resolution_sha256": resolution["resolution_sha256"],
        "adjudicator_prompt_sha256": _file_sha256(
            artifact_dir.parents[1] / "prompts" / "adjudicator_v1.md",
        ),
        "tiebreaker_prompt_sha256": _file_sha256(
            artifact_dir.parents[1] / "prompts" / "tiebreaker_v1.md",
        ),
        "reference_packet_set_created": False,
        "experiment_execution_authorized": False,
        "stop_rule": "unresolved_adjudicator_disagreement_gt_20_percent",
    }
    preregistration["preregistration_sha256"] = canonical_sha256(preregistration)
    _write_json(artifact_dir / "preregistration.json", preregistration)

    receipt = {
        "schema_version": "source_general_claim_verification.receipts.v1",
        "packet_adjudication": resolution["adjudicators"],
        "packet_prompt_capture_status": (
            "SEMANTIC_CONTRACT_FROZEN_FROM_DISPATCH_CONTENT"
        ),
        "provider_experiment": {
            "executed": False,
            "stop_reason": resolution["terminal"],
            "provider_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "latency_seconds": 0,
            "cost_usd": 0,
            "provider_response_ids": [],
            "fallback_calls": 0,
            "graph_writes": 0,
            "untouched_sources_accessed": 0,
        },
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    _write_json(artifact_dir / "receipts.json", receipt)
    return resolution


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(canonical_json(payload), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--artifact-dir", required=True, type=Path)
    args = parser.parse_args()
    resolution = freeze_checkpoint(
        corpus_path=args.corpus,
        artifact_dir=args.artifact_dir,
    )
    print(json.dumps({"terminal": resolution["terminal"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
