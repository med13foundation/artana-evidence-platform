"""Freeze the corrected exposed adjudication checkpoint and its stop decision."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.validation.source_general_claim_verification.corpus import load_corpus
from scripts.validation.source_general_claim_verification.hashing import (
    canonical_sha256,
)
from scripts.validation.source_general_claim_verification.v2_resolution import (
    load_validated_batch,
    scientific_disagreements,
    unresolved_after_tiebreak,
)

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = ROOT / "artifacts" / "exposed_checkpoint_v2"
CORPUS_PATH = ROOT / "fixtures" / "exposed_31_scope_corpus.json"
MAX_UNRESOLVED_RATE = 0.20


def freeze_checkpoint() -> dict[str, object]:
    corpus = load_corpus(CORPUS_PATH)
    scope_ids = tuple(scope.scope_id for scope in corpus.scopes)
    first = load_validated_batch(
        ARTIFACT_DIR / "adjudicator_a.json",
        corpus=corpus,
        role="FIRST",
        expected_scope_ids=scope_ids,
    )
    second = load_validated_batch(
        ARTIFACT_DIR / "adjudicator_b.json",
        corpus=corpus,
        role="SECOND",
        expected_scope_ids=scope_ids,
    )
    tiebreaker = load_validated_batch(
        ARTIFACT_DIR / "adjudicator_c.json",
        corpus=corpus,
        role="TIEBREAKER",
        expected_scope_ids=tuple(
            item["scope_id"]
            for item in json.loads(
                (ARTIFACT_DIR / "disagreement_request.json").read_text(),
            )["disputes"]
        ),
    )
    if not (first.valid and second.valid and tiebreaker.valid):
        raise ValueError("corrected adjudicator artifacts must all validate")
    assert first.batch is not None
    assert second.batch is not None
    disputes = scientific_disagreements(first.batch, second.batch)
    unresolved = unresolved_after_tiebreak(
        disputes=disputes,
        first=first.batch,
        second=second.batch,
        tiebreaker=tiebreaker.batch,
    )
    unresolved_rate = len(unresolved) / len(scope_ids)
    ready = unresolved_rate <= MAX_UNRESOLVED_RATE
    result: dict[str, object] = {
        "schema_version": "source_general_claim_verification.resolution.v2",
        "corpus_sha256": canonical_sha256(corpus),
        "scope_count": len(scope_ids),
        "artifact_validation": {
            "adjudicator_a": {"valid": first.valid, "sha256": first.sha256},
            "adjudicator_b": {"valid": second.valid, "sha256": second.sha256},
            "adjudicator_c": {"valid": tiebreaker.valid, "sha256": tiebreaker.sha256},
        },
        "initial_disagreement_count": len(disputes),
        "initial_disagreement_rate": len(disputes) / len(scope_ids),
        "unresolved_disagreement_count": len(unresolved),
        "unresolved_disagreement_rate": unresolved_rate,
        "maximum_allowed_unresolved_rate": MAX_UNRESOLVED_RATE,
        "unresolved_scope_ids": list(unresolved),
        "reference_packet_set_created": False,
        "experiment_execution_authorized": False,
        "terminal": (
            "READY_FOR_EXPOSED_VERIFICATION"
            if ready
            else "STOP_REFERENCE_SET_UNRELIABLE"
        ),
        "decision": "ADVANCE" if ready else "PIVOT",
    }
    _write_frozen_json(ARTIFACT_DIR / "resolution.json", result)
    blocked = {
        "schema_version": "source_general_claim_verification.blocked_preregistration.v2",
        "corpus_sha256": result["corpus_sha256"],
        "reference_packet_set_sha256": None,
        "experiment_execution_authorized": False,
        "terminal": result["terminal"],
        "reason": "unresolved adjudicator disagreement exceeds 20 percent",
        "planned_experiment": {
            "source_class": "exposed_only",
            "promotion_enabled": False,
            "maximum_repairs_per_claim": 1,
            "outcomes_remain_review_only": True,
        },
    }
    _write_frozen_json(ARTIFACT_DIR / "blocked_preregistration.json", blocked)
    receipts = {
        "schema_version": "source_general_claim_verification.receipts.v2",
        "provider_experiment_executed": False,
        "provider_calls": "NOT_RUN",
        "provider_tokens": "NOT_RUN",
        "provider_cost_usd": "NOT_RUN",
        "provider_latency_ms": "NOT_RUN",
        "graph_writes": 0,
        "untouched_sources_accessed": "UNVERIFIED_BY_RUNNER",
        "fallback_invocations": 0,
        "adjudicator_task_usage": "UNAVAILABLE_FROM_CODEX_TASK_RUNTIME",
        "terminal": result["terminal"],
    }
    _write_frozen_json(ARTIFACT_DIR / "receipts.json", receipts)
    metrics = {
        "schema_version": "source_general_claim_verification.metrics.v2",
        "status": "NOT_RUN_REFERENCE_SET_UNRELIABLE",
        "reason": blocked["reason"],
        "requested_metrics": dict.fromkeys(
            (
                "false_acceptance_rate",
                "correct_rejection_rate",
                "abstention_rate",
                "valuable_claim_recall_before",
                "valuable_claim_recall_after",
                "repair_attempt_rate",
                "valid_repair_rate",
                "repair_laundering_rate",
                "unauthorized_change_rate",
                "role_fidelity",
                "polarity_fidelity",
                "comparison_fidelity",
                "uncertainty_fidelity",
                "statistical_fidelity",
                "unsupported_claims",
                "contradictions",
                "calls",
                "tokens",
                "latency",
                "cost",
            ),
            "NOT_RUN",
        ),
    }
    _write_frozen_json(ARTIFACT_DIR / "scientific_metrics.json", metrics)
    return result


def _write_frozen_json(path: Path, payload: dict[str, object]) -> None:
    content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists() and path.read_text() != content:
        raise ValueError(f"refusing to overwrite frozen artifact: {path.name}")
    path.write_text(content)


def main() -> None:
    result = freeze_checkpoint()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
