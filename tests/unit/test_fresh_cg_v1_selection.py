"""Regression tests for mechanical fresh-CG holdout selection."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.contracts import (
    FreshCGSelection,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.selection import (
    RESERVE_ORDER,
    build_selection,
    load_frozen_selection,
)

ROOT = Path(__file__).resolve().parents[2]
FROZEN_SELECTION = (
    ROOT / "docs/validation/fixtures/2026-07-22-fresh-cg-selection-v1.json"
)
FAILED_SELECTION = ROOT / (
    "docs/validation/preflight_failures/2026-07-22-fresh-cg-candidate-1/"
    "2026-07-22-fresh-cg-selection-v1.json"
)


def _write_document(directory: Path, document_id: str, *, eligible: bool) -> None:
    if eligible:
        source = "Cells grow. Drug activates GENE."
        a1 = (
            "T1\tCell 0 5\tCells\n"
            "T2\tSimple_chemical 12 16\tDrug\n"
            "T3\tGene_or_gene_product 27 31\tGENE\n"
        )
        a2 = (
            "T4\tGrowth 6 10\tgrow\n"
            "T5\tPositive_regulation 17 26\tactivates\n"
            "E1\tGrowth:T4 Theme:T1\n"
            "E2\tPositive_regulation:T5 Cause:T2 Theme:T3\n"
        )
    else:
        source = "Cells grow."
        a1 = "T1\tCell 0 5\tCells\n"
        a2 = "T4\tGrowth 6 10\tgrow\nE1\tGrowth:T4 Theme:T1\n"
    (directory / f"{document_id}.txt").write_text(source, encoding="utf-8")
    (directory / f"{document_id}.a1").write_text(a1, encoding="utf-8")
    (directory / f"{document_id}.a2").write_text(a2, encoding="utf-8")


def test_selection_uses_first_eligible_event_and_stops_after_eight(
    tmp_path: Path,
) -> None:
    development = tmp_path / "devel"
    development.mkdir()
    _write_document(development, RESERVE_ORDER[0], eligible=False)
    for document_id in RESERVE_ORDER[1:9]:
        _write_document(development, document_id, eligible=True)

    selection = build_selection(development)

    assert selection.selected_document_ids == RESERVE_ORDER[1:9]
    assert selection.unused_document_ids == (
        RESERVE_ORDER[0],
        *RESERVE_ORDER[9:],
    )
    assert selection.skipped_documents[0].document_id == RESERVE_ORDER[0]
    assert all(case.event.event_id == "E2" for case in selection.cases)
    assert all(
        tuple(item.disposition for item in case.considered_events)
        == ("INELIGIBLE", "SELECTED")
        for case in selection.cases
    )
    assert all(case.permitted_context.text == "Drug activates GENE." for case in selection.cases)


def test_frozen_selection_verifies_source_bytes_spans_and_direct_reference() -> None:
    selection = load_frozen_selection(FROZEN_SELECTION)

    assert selection.selected_document_ids == (
        "PMID-21963494",
        "PMID-2681013",
        "PMID-16098727",
        "PMID-7904970",
        "PMID-19648108",
        "PMID-11306510",
        "PMID-18841154",
        "PMID-20448329",
    )
    assert selection.model_outputs_used_for_selection is False
    assert selection.cases[5].permitted_context.end == 168
    skipped = {item.document_id: item for item in selection.skipped_documents}
    assert any(
        "OCCURRENCE_V2_TRIGGER_NOT_TOKEN_BOUNDED" in event.reasons
        for event in skipped["PMID-18165897"].considered_events
    )


def test_failed_candidate_is_preserved_but_cannot_pass_frozen_loading() -> None:
    with pytest.raises(ValueError, match="event mention splits a token"):
        load_frozen_selection(FAILED_SELECTION)


def test_frozen_selection_rejects_changed_case_order() -> None:
    payload = json.loads(FROZEN_SELECTION.read_text(encoding="utf-8"))
    payload["cases"][0], payload["cases"][1] = payload["cases"][1], payload["cases"][0]

    with pytest.raises(ValidationError, match="selected document order"):
        FreshCGSelection.model_validate_json(json.dumps(payload))


def test_frozen_selection_rejects_changed_source_bytes(tmp_path: Path) -> None:
    payload = json.loads(FROZEN_SELECTION.read_text(encoding="utf-8"))
    payload["cases"][0]["source_bytes_base64"] = base64.b64encode(b"changed").decode()
    candidate = tmp_path / "selection.json"
    candidate.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="source bytes differ from text"):
        load_frozen_selection(candidate)
