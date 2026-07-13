"""Tests for the shadow-review packet CLI."""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest
from artana_evidence_api.evidence_selection.ranking.contracts import (
    ReviewRankingCalibrationProtocol,
)
from artana_evidence_api.evidence_selection.ranking.protocol_integrity import (
    authenticate_calibration_protocol,
)
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
    assert packet["schema_version"] == "evidence_selection_shadow_review_packet.v3"
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


def test_shadow_review_packet_cli_requires_protocol_for_calibrated_probability(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli_module()
    run_result_path = tmp_path / "evidence-selection-result.json"
    output_path = tmp_path / "shadow-review-packet.json"
    protocol_path = tmp_path / "calibration-protocol.json"
    payload = _run_result_payload()
    ranking_item = payload["review_ranking_items"][0]
    ranking_item["calibrated_probability"] = _calibrated_probability(0.9)
    run_result_path.write_text(json.dumps(payload))
    protocol_path.write_text(json.dumps(_calibration_protocol()))

    missing_protocol_exit = cli.main(
        (
            "--run-result",
            str(run_result_path),
            "--study-id",
            "calibrated-shadow-study",
            "--output",
            str(output_path),
        ),
    )

    assert missing_protocol_exit == 1
    assert "validation failed" in capsys.readouterr().err
    assert output_path.exists() is False

    exit_code = cli.main(
        (
            "--run-result",
            str(run_result_path),
            "--study-id",
            "calibrated-shadow-study",
            "--calibration-protocol",
            str(protocol_path),
            "--output",
            str(output_path),
        ),
    )

    assert exit_code == 0
    packet = json.loads(output_path.read_text())
    assert packet["calibration_protocol"] == _calibration_protocol()
    assert packet["review_ranking_forms"][0]["calibrated_probability"]["value"] == 0.9


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
            "operational_ranking": _operational_ranking(0.91),
            "title": "Review candidate: BRAF response",
        },
    ]
    payload["review_items"] = [
        {
            "review_item_id": "review-item-1",
            "review_type": "source_record",
            "operational_ranking": _operational_ranking(7.2),
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
    ranking_forms = packet["review_ranking_forms"]
    assert [form["item_id"] for form in ranking_forms] == [
        "proposal-1",
        "review-item-1",
    ]
    assert [form["operational_ranking"]["value"] for form in ranking_forms] == [
        0.91,
        7.2,
    ]
    assert all(form["calibrated_probability"] is None for form in ranking_forms)


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
            "operational_ranking": _operational_ranking(9.1),
        },
        {
            **_decision(source_key="pubmed", decision="deferred", record_index=1),
            "deferral_reason": "shadow_mode",
            "shadow_decision": "skipped",
            "would_have_been_selected": False,
            "operational_ranking": _operational_ranking(2.5),
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
    ranking_forms = packet["review_ranking_forms"]
    assert [form["source_kind"] for form in ranking_forms] == [
        "proposal",
        "review_item",
    ]
    assert [form["operational_ranking"]["value"] for form in ranking_forms] == [
        9.1,
        2.5,
    ]


def test_shadow_review_packet_cli_excludes_unranked_failure_deferrals(
    tmp_path: Path,
) -> None:
    cli = _cli_module()
    run_result_path = tmp_path / "evidence-selection-result.json"
    output_path = tmp_path / "shadow-review-packet.json"
    payload = _run_result_payload()
    ranked_candidate = {
        **_decision(source_key="pubmed", decision="deferred", record_index=1),
        "deferral_reason": "shadow_mode",
        "shadow_decision": "selected",
        "would_have_been_selected": True,
    }
    unranked_failure = {
        "source_key": "clinvar",
        "source_family": "unknown",
        "search_id": _SEARCH_ID,
        "decision": "deferred",
        "relevance_label": "deferred",
        "reason": "Saved source search was not found.",
        "deferral_reason": "missing_source_search",
    }
    payload["selected_records"] = []
    payload["skipped_records"] = []
    payload["deferred_records"] = [unranked_failure, ranked_candidate]
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
    assert [form["item_id"] for form in packet["review_ranking_forms"]] == [
        f"pubmed:{_SEARCH_ID}:1",
    ]
    assert packet["selection_review_forms"][0]["harness_deferred_record_ids"] == []


def test_shadow_review_packet_cli_writes_selection_only_packet_without_ranking_items(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli_module()
    run_result_path = tmp_path / "evidence-selection-result.json"
    output_path = tmp_path / "shadow-review-packet.json"
    payload = _run_result_payload()
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
    assert exit_code == 0
    assert captured.err == ""
    packet = json.loads(output_path.read_text())
    assert packet["study_type"] == "selection_relevance"
    assert packet["review_ranking_forms"] == []
    assert packet["candidate_records"]
    assert machine_packet_sidecar_path(output_path).exists()


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


@pytest.mark.parametrize("mode", ["guarded", "full", None])
def test_shadow_review_packet_cli_rejects_non_shadow_result(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mode: str | None,
) -> None:
    cli = _cli_module()
    run_result_path = tmp_path / "evidence-selection-result.json"
    output_path = tmp_path / "shadow-review-packet.json"
    payload = _run_result_payload()
    if mode is None:
        payload.pop("mode")
    else:
        payload["mode"] = mode
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
    assert "mode must be 'shadow'" in captured.err
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
        "mode": "shadow",
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
                "research_question_id": _question_id(),
                "operational_ranking": _operational_ranking(0.91),
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
        "operational_ranking": _operational_ranking(
            0.91 if decision == "selected" else 0.2,
        ),
        "matched_terms": ["BRAF", "vemurafenib"],
        "excluded_terms": [],
        "caveats": [],
    }


def _operational_ranking(value: float) -> dict[str, object]:
    return {
        "origin": "deterministic_policy",
        "value": value,
        "policy_id": "test_review_ranking",
        "policy_version": "v1",
        "mapping_version": "v1",
        "categorical_inputs": [
            {"field": "evidence_state", "value": "supported"},
        ],
        "caps": [],
        "vetoes": [],
        "blocking_categories": [],
    }


def _calibration_identity() -> dict[str, object]:
    return {
        "input_policy_id": "test_review_ranking",
        "input_policy_version": "v1",
        "input_mapping_version": "v1",
        "categorical_schema_version": "v1",
        "selector_model_id": "test-selector-model",
        "selector_prompt_version": "v1",
        "objective_schema_version": "v1",
        "corpus_version": "v1",
        "calibration_algorithm": "isotonic",
        "calibration_version": "v1",
    }


def _calibrated_probability(value: float) -> dict[str, object]:
    return {
        "origin": "calibration_model",
        "value": value,
        "calibration_status": "diagnostic",
        "identity": _calibration_identity(),
        "training_set_sha256": "1" * 64,
        "partition_manifest_sha256": "2" * 64,
        "held_out_protocol": "frozen_question_partition_v1",
    }


def _calibration_protocol() -> dict[str, object]:
    payload = {
        "identity": _calibration_identity(),
        "partition_manifest_sha256": "2" * 64,
        "training_set_sha256": "1" * 64,
        "held_out_set_sha256": "3" * 64,
        "training_research_question_ids": [
            f"training-rq-{index:02d}" for index in range(1, 13)
        ],
        "held_out_research_question_ids": [
            _question_id(),
            *(f"heldout-rq-{index:02d}" for index in range(2, 9)),
        ],
        "independent_expert_labels": True,
        "held_out_protocol": "frozen_question_partition_v1",
    }
    protocol = ReviewRankingCalibrationProtocol.model_validate(payload)
    return authenticate_calibration_protocol(protocol).model_dump(mode="json")


def _question_id() -> str:
    return f"question:{hashlib.sha256(_GOAL.encode()).hexdigest()}"
