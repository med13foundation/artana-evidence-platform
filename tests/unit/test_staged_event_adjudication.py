from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validation.public_gold.staged_event.adjudication import (
    StagedAdjudicationError,
    validate_and_summarize,
)

ROOT = Path(__file__).parents[2]
ADJUDICATION = ROOT / "docs/validation/adjudications/2026-07-22-staged-event-v1-scientific-adjudication.json"
STAGED_RESULT = ROOT / "docs/validation/reports/2026-07-22-staged-event-comparison-v1-result.json"
SOURCE = ROOT / "validation/public_gold/bionlp_cg/raw/bionlp-st-2013-cg-master/original-data/devel/PMID-16428936.txt"
GOLD = ROOT / "validation/public_gold/bionlp_cg/raw/bionlp-st-2013-cg-master/original-data/devel/PMID-16428936.a2"


def test_all_34_adjudications_match_preserved_source_gold_and_stages() -> None:
    result = validate_and_summarize(
        adjudication_path=ADJUDICATION,
        staged_result_path=STAGED_RESULT,
        source_path=SOURCE,
        gold_path=GOLD,
    )

    assert result["status"] == "ADJUDICATION_VALID"
    assert result["candidate_count"] == 34
    assert result["benchmark_exact_gold_events_recovered"] == 9
    assert result["benchmark_exact_recovery_rate"] == 0.3
    assert result["source_supported_complete_events"] == 19
    assert result["unsupported_by_source"] == 0
    verifier = result["verifier_audit"]
    assert isinstance(verifier, dict)
    assert verifier["entailed_total"] == 32
    assert verifier["false_accept_count"] == 15
    assert verifier["false_accept_rate"] == 15 / 32


def test_adjudication_rejects_evidence_that_is_not_the_candidate_passage(
    tmp_path: Path,
) -> None:
    payload = json.loads(ADJUDICATION.read_text(encoding="utf-8"))
    payload["adjudications"][0]["exact_source_evidence"] = "c-Myc"
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(StagedAdjudicationError, match="evidence differs"):
        validate_and_summarize(
            adjudication_path=tampered,
            staged_result_path=STAGED_RESULT,
            source_path=SOURCE,
            gold_path=GOLD,
        )


def test_adjudication_rejects_unknown_failure_label(tmp_path: Path) -> None:
    payload = json.loads(ADJUDICATION.read_text(encoding="utf-8"))
    payload["adjudications"][0]["failure_labels"] = ["NUMERIC_VIBE_SCORE"]
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(StagedAdjudicationError, match="invalid failure labels"):
        validate_and_summarize(
            adjudication_path=tampered,
            staged_result_path=STAGED_RESULT,
            source_path=SOURCE,
            gold_path=GOLD,
        )
