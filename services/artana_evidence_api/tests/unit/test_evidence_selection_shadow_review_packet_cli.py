"""Tests for the shadow-review packet CLI."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from artana_evidence_api.evidence_selection.shadow_review_completion import (
    machine_packet_sidecar_path,
)
from artana_evidence_api.evidence_selection.shadow_review_packet import (
    EvidenceSelectionShadowReviewPacket,
)

_RUN_ID = "00000000-0000-0000-0000-000000000047"
_SEARCH_ID = "11111111-1111-1111-1111-111111111111"
_GOAL = "Find evidence that BRAF V600E predicts response to vemurafenib."


def test_shadow_review_packet_cli_writes_collection_packet(tmp_path: Path) -> None:
    cli = _cli_module()
    run_result_path = tmp_path / "evidence-selection-result.json"
    output_path = tmp_path / "shadow-review-packet.json"
    run_result_path.write_text(json.dumps(_run_result_payload()))

    exit_code = cli.main(
        (
            "--run-result",
            str(run_result_path),
            "--study-id",
            "shadow-study-2026-07-07",
            "--output",
            str(output_path),
        ),
    )

    assert exit_code == 0
    packet = json.loads(output_path.read_text())
    assert packet["schema_version"] == "evidence_selection_shadow_review_packet.v1"
    assert packet["source_run_id"] == _RUN_ID
    assert packet["production_readiness_claim"] is False
    assert packet["machine_packet_sha256"]
    assert packet["machine_packet_signature"]
    assert "selection_reviews" not in packet
    assert packet["selection_review_forms"][0]["human_selected_record_ids"] == []
    assert packet["review_ranking_forms"][0]["outcome"] is None
    machine_packet_path = machine_packet_sidecar_path(output_path)
    assert machine_packet_path.exists()
    assert json.loads(machine_packet_path.read_text()) == packet
    EvidenceSelectionShadowReviewPacket.model_validate(packet)


def test_shadow_review_packet_cli_maps_real_result_artifact_shape(
    tmp_path: Path,
) -> None:
    cli = _cli_module()
    run_result_path = tmp_path / "evidence-selection-result.json"
    output_path = tmp_path / "shadow-review-packet.json"
    payload = _run_result_payload()
    payload["selected_records"] = []
    payload["deferred_records"] = [
        {
            **_decision(source_key="clinvar", decision="deferred", record_index=0),
            "deferral_reason": "shadow_mode",
            "shadow_decision": "selected",
            "would_have_been_selected": True,
        },
    ]
    payload.pop("review_ranking_items")
    payload["proposals"] = [
        {
            "proposal_id": "proposal-1",
            "proposal_type": "candidate_claim",
            "ranking_score": 0.91,
            "title": "Review candidate: BRAF response",
        },
    ]
    payload["review_items"] = [
        {
            "review_item_id": "review-item-1",
            "review_type": "source_record",
            "ranking_score": 7.2,
            "title": "Review selected source record: BRAF response",
        },
    ]
    run_result_path.write_text(json.dumps(payload))

    exit_code = cli.main(
        (
            "--run-result",
            str(run_result_path),
            "--study-id",
            "shadow-study-2026-07-07",
            "--output",
            str(output_path),
        ),
    )

    assert exit_code == 0
    packet = json.loads(output_path.read_text())
    assert packet["selection_review_forms"][0]["harness_selected_record_ids"] == [
        f"clinvar:{_SEARCH_ID}:0",
    ]
    assert packet["selection_review_forms"][0]["harness_deferred_record_ids"] == []
    assert packet["review_ranking_forms"] == [
        {
            "source_kind": "proposal",
            "item_id": "proposal-1",
            "ranking_score": 0.91,
            "outcome": None,
            "reviewer_id": None,
            "goal": _GOAL,
            "evidence_shape": "candidate_claim",
        },
        {
            "source_kind": "review_item",
            "item_id": "review-item-1",
            "ranking_score": 0.72,
            "outcome": None,
            "reviewer_id": None,
            "goal": _GOAL,
            "evidence_shape": "source_record",
        },
    ]


def test_shadow_review_packet_cli_derives_ranking_forms_from_shadow_candidates(
    tmp_path: Path,
) -> None:
    cli = _cli_module()
    run_result_path = tmp_path / "evidence-selection-result.json"
    output_path = tmp_path / "shadow-review-packet.json"
    payload = _run_result_payload()
    payload["selected_records"] = []
    payload["skipped_records"] = []
    payload["deferred_records"] = [
        {
            **_decision(source_key="clinvar", decision="deferred", record_index=0),
            "deferral_reason": "shadow_mode",
            "shadow_decision": "selected",
            "would_have_been_selected": True,
            "score": 9.1,
        },
        {
            **_decision(source_key="pubmed", decision="deferred", record_index=1),
            "deferral_reason": "shadow_mode",
            "shadow_decision": "skipped",
            "would_have_been_selected": False,
            "score": 2.5,
        },
    ]
    payload.pop("review_ranking_items")
    run_result_path.write_text(json.dumps(payload))

    exit_code = cli.main(
        (
            "--run-result",
            str(run_result_path),
            "--study-id",
            "shadow-study-2026-07-07",
            "--output",
            str(output_path),
        ),
    )

    assert exit_code == 0
    packet = json.loads(output_path.read_text())
    assert packet["review_ranking_forms"] == [
        {
            "source_kind": "proposal",
            "item_id": f"clinvar:{_SEARCH_ID}:0",
            "ranking_score": 0.91,
            "outcome": None,
            "reviewer_id": None,
            "goal": _GOAL,
            "evidence_shape": "literature",
        },
        {
            "source_kind": "review_item",
            "item_id": f"pubmed:{_SEARCH_ID}:1",
            "ranking_score": 0.25,
            "outcome": None,
            "reviewer_id": None,
            "goal": _GOAL,
            "evidence_shape": "literature",
        },
    ]


def test_shadow_review_packet_cli_rejects_result_without_rankable_items(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli_module()
    run_result_path = tmp_path / "evidence-selection-result.json"
    output_path = tmp_path / "shadow-review-packet.json"
    payload = _run_result_payload()
    payload["selected_records"] = []
    payload["skipped_records"] = []
    payload["deferred_records"] = []
    payload.pop("review_ranking_items")
    run_result_path.write_text(json.dumps(payload))

    exit_code = cli.main(
        (
            "--run-result",
            str(run_result_path),
            "--study-id",
            "shadow-study-2026-07-07",
            "--output",
            str(output_path),
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "no rankable items" in captured.err
    assert not output_path.exists()
    assert not machine_packet_sidecar_path(output_path).exists()


def test_shadow_review_packet_cli_rejects_invalid_run_result_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli_module()
    run_result_path = tmp_path / "evidence-selection-result.json"
    output_path = tmp_path / "shadow-review-packet.json"
    payload = _run_result_payload()
    payload["selected_records"][0].pop("record_index")
    run_result_path.write_text(json.dumps(payload))

    exit_code = cli.main(
        (
            "--run-result",
            str(run_result_path),
            "--study-id",
            "shadow-study-2026-07-07",
            "--output",
            str(output_path),
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "record_index" in captured.err
    assert "Traceback" not in captured.err
    assert not output_path.exists()


def test_shadow_review_packet_cli_requires_producer_signing_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli_module()
    run_result_path = tmp_path / "evidence-selection-result.json"
    output_path = tmp_path / "shadow-review-packet.json"
    run_result_path.write_text(json.dumps(_run_result_payload()))
    monkeypatch.delenv("ARTANA_EVIDENCE_SHADOW_REVIEW_PACKET_SIGNING_KEY")

    exit_code = cli.main(
        (
            "--run-result",
            str(run_result_path),
            "--study-id",
            "shadow-study-2026-07-07",
            "--output",
            str(output_path),
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "ARTANA_EVIDENCE_SHADOW_REVIEW_PACKET_SIGNING_KEY" in captured.err
    assert not output_path.exists()
    assert not machine_packet_sidecar_path(output_path).exists()


def _cli_module() -> object:
    try:
        return importlib.import_module(
            "scripts.build_evidence_selection_shadow_review_packet",
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"shadow review packet CLI is missing: {exc}")


def _run_result_payload() -> dict[str, object]:
    return {
        "run": {"id": _RUN_ID},
        "goal": _GOAL,
        "selected_records": [
            _decision(source_key="pubmed", decision="selected", record_index=0),
        ],
        "skipped_records": [
            _decision(source_key="pubmed", decision="skipped", record_index=1),
        ],
        "deferred_records": [],
        "review_ranking_items": [
            {
                "source_kind": "proposal",
                "item_id": "proposal-1",
                "ranking_score": 0.91,
                "goal": _GOAL,
                "evidence_shape": "variant_drug_response",
            },
        ],
    }


def _decision(
    *,
    source_key: str,
    decision: str,
    record_index: int,
) -> dict[str, object]:
    return {
        "source_key": source_key,
        "source_family": "literature",
        "search_id": _SEARCH_ID,
        "decision": decision,
        "relevance_label": "strong_fit" if decision == "selected" else "context_only",
        "reason": "Candidate packet CLI fixture.",
        "record_index": record_index,
        "record_hash": f"{source_key}-hash-{record_index}",
        "title": f"{source_key} record {record_index}",
        "score": 0.91 if decision == "selected" else 0.2,
        "matched_terms": ["BRAF", "vemurafenib"],
        "excluded_terms": [],
        "caveats": [],
    }
