"""Tests for the completed shadow-review packet conversion CLI."""

from __future__ import annotations

import importlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from artana_evidence_api.evidence_selection.shadow_review_completion import (
    machine_packet_sidecar_path,
)
from artana_evidence_api.evidence_selection.shadow_review_integrity import (
    sign_machine_packet_digest,
)
from artana_evidence_api.evidence_selection.shadow_review_packet import (
    EvidenceSelectionShadowReviewPacket,
    machine_packet_digest,
)


def test_shadow_review_completion_cli_writes_source_input_files(
    tmp_path: Path,
) -> None:
    cli = _cli_module()
    packet_path = tmp_path / "completed-shadow-review-packet.json"
    selection_output = tmp_path / "selection-review-labels.json"
    ranking_output = tmp_path / "review-ranking-study.json"
    _write_completed_packet(packet_path, _completed_packet())

    exit_code = cli.main(
        (
            "--packet",
            str(packet_path),
            "--selection-reviews-output",
            str(selection_output),
            "--review-ranking-output",
            str(ranking_output),
            "--adjudication-note",
            "Reviewer A completed all labels.",
            "--description",
            "Completed packet conversion fixture.",
        ),
    )

    assert exit_code == 0
    selection_payload = json.loads(selection_output.read_text())
    ranking_payload = json.loads(ranking_output.read_text())
    assert selection_payload["selection_reviews"][0]["reviewer_id"] == "reviewer-a"
    assert selection_payload["selection_reviews"][0]["human_selected_record_ids"] == [
        "pubmed:search-1:0",
    ]
    assert ranking_payload["schema_version"] == (
        "evidence_selection_review_ranking_calibration.v1"
    )
    assert ranking_payload["adjudication_note"] == "Reviewer A completed all labels."
    assert ranking_payload["decisions"][0]["outcome"] == "positive"


def test_shadow_review_completion_cli_rejects_incomplete_packet_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli_module()
    packet = _completed_packet()
    packet["review_ranking_forms"][0]["outcome"] = None
    packet_path = tmp_path / "completed-shadow-review-packet.json"
    selection_output = tmp_path / "selection-review-labels.json"
    ranking_output = tmp_path / "review-ranking-study.json"
    _write_completed_packet(packet_path, packet)

    exit_code = cli.main(
        (
            "--packet",
            str(packet_path),
            "--selection-reviews-output",
            str(selection_output),
            "--review-ranking-output",
            str(ranking_output),
            "--adjudication-note",
            "Reviewer A completed all labels.",
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "outcome" in captured.err
    assert "Traceback" not in captured.err
    assert not selection_output.exists()
    assert not ranking_output.exists()


def test_shadow_review_completion_cli_does_not_echo_invalid_label_content(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli_module()
    packet = _completed_packet()
    sentinel = "sensitive-human-label-content"
    packet["review_ranking_forms"][0]["outcome"] = sentinel
    packet_path = tmp_path / "completed-shadow-review-packet.json"
    _write_completed_packet(packet_path, packet)

    exit_code = cli.main(
        (
            "--packet",
            str(packet_path),
            "--selection-reviews-output",
            str(tmp_path / "selection-review-labels.json"),
            "--review-ranking-output",
            str(tmp_path / "review-ranking-study.json"),
            "--adjudication-note",
            "Reviewer A completed all labels.",
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "validation failed for fields" in captured.err
    assert sentinel not in captured.err


def test_shadow_review_completion_cli_rejects_output_that_overwrites_packet(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli_module()
    packet_path = tmp_path / "completed-shadow-review-packet.json"
    _write_completed_packet(packet_path, _completed_packet())

    exit_code = cli.main(
        (
            "--packet",
            str(packet_path),
            "--selection-reviews-output",
            str(packet_path),
            "--review-ranking-output",
            str(tmp_path / "review-ranking-study.json"),
            "--adjudication-note",
            "Reviewer A completed all labels.",
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "must not overwrite source packet" in captured.err


def test_shadow_review_completion_cli_rejects_directory_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli_module()
    packet_path = tmp_path / "completed-shadow-review-packet.json"
    selection_output = tmp_path / "selection-review-labels.json"
    ranking_output = tmp_path / "review-ranking-study.json"
    _write_completed_packet(packet_path, _completed_packet())
    selection_output.mkdir()

    exit_code = cli.main(
        (
            "--packet",
            str(packet_path),
            "--selection-reviews-output",
            str(selection_output),
            "--review-ranking-output",
            str(ranking_output),
            "--adjudication-note",
            "Reviewer A completed all labels.",
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "must be a file path" in captured.err
    assert selection_output.is_dir()
    assert not ranking_output.exists()


@pytest.mark.parametrize(
    ("selection_relative_path", "ranking_relative_path"),
    [
        ("source-input", "source-input/review-ranking-study.json"),
        ("source-input/selection-review-labels.json", "source-input"),
    ],
)
def test_shadow_review_completion_cli_rejects_nested_outputs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    selection_relative_path: str,
    ranking_relative_path: str,
) -> None:
    cli = _cli_module()
    packet_path = tmp_path / "completed-shadow-review-packet.json"
    _write_completed_packet(packet_path, _completed_packet())
    selection_output = tmp_path / selection_relative_path
    ranking_output = tmp_path / ranking_relative_path

    exit_code = cli.main(
        (
            "--packet",
            str(packet_path),
            "--selection-reviews-output",
            str(selection_output),
            "--review-ranking-output",
            str(ranking_output),
            "--adjudication-note",
            "Reviewer A completed all labels.",
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "must not use nested parent/child paths" in captured.err
    assert not (tmp_path / "source-input").exists()


def test_shadow_review_completion_cli_overwrites_files_without_backup_artifacts(
    tmp_path: Path,
) -> None:
    cli = _cli_module()
    packet_path = tmp_path / "completed-shadow-review-packet.json"
    selection_output = tmp_path / "selection-review-labels.json"
    ranking_output = tmp_path / "review-ranking-study.json"
    _write_completed_packet(packet_path, _completed_packet())
    selection_output.write_text('{"old": "selection"}\n')
    ranking_output.write_text('{"old": "ranking"}\n')

    exit_code = cli.main(
        (
            "--packet",
            str(packet_path),
            "--selection-reviews-output",
            str(selection_output),
            "--review-ranking-output",
            str(ranking_output),
            "--adjudication-note",
            "Reviewer A completed all labels.",
        ),
    )

    assert exit_code == 0
    assert json.loads(selection_output.read_text())["selection_reviews"]
    assert json.loads(ranking_output.read_text())["decisions"]
    assert list(tmp_path.glob(".*.bak-*")) == []


def test_shadow_review_completion_cli_keeps_paired_outputs_all_or_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _cli_module()
    packet_path = tmp_path / "completed-shadow-review-packet.json"
    selection_output = tmp_path / "selection-review-labels.json"
    ranking_output = tmp_path / "review-ranking-study.json"
    _write_completed_packet(packet_path, _completed_packet())
    original_write_text = Path.write_text

    def _fail_ranking_write(
        self: Path,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        if self == ranking_output or self.name.startswith(
            ".review-ranking-study.json.tmp-",
        ):
            raise OSError("simulated ranking write failure")
        return original_write_text(
            self,
            data,
            encoding=encoding,
            errors=errors,
            newline=newline,
        )

    monkeypatch.setattr(Path, "write_text", _fail_ranking_write)

    exit_code = cli.main(
        (
            "--packet",
            str(packet_path),
            "--selection-reviews-output",
            str(selection_output),
            "--review-ranking-output",
            str(ranking_output),
            "--adjudication-note",
            "Reviewer A completed all labels.",
        ),
    )

    assert exit_code == 1
    assert not selection_output.exists()
    assert not ranking_output.exists()


def _cli_module() -> object:
    try:
        return importlib.import_module(
            "scripts.build_evidence_selection_shadow_review_source_inputs",
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"shadow review completion CLI is missing: {exc}")


def _completed_packet() -> dict[str, object]:
    packet = _completed_packet_payload()
    machine_packet = _machine_packet_for_completed_packet(packet)
    packet["machine_packet_sha256"] = machine_packet["machine_packet_sha256"]
    packet["machine_packet_signature"] = machine_packet["machine_packet_signature"]
    return packet


def _machine_packet_for_completed_packet(
    completed_packet: dict[str, object],
) -> dict[str, object]:
    machine_packet = deepcopy(completed_packet)
    selection_form = machine_packet["selection_review_forms"][0]
    selection_form["reviewer_id"] = None
    selection_form["human_selected_record_ids"] = []
    selection_form["duplicate_suggestion_ids"] = []
    selection_form["explanation_quality_score"] = None
    selection_form["high_severity_overclaim_count"] = None
    selection_form["reviewer_notes"] = None
    for ranking_form in machine_packet["review_ranking_forms"]:
        ranking_form["outcome"] = None
        ranking_form["reviewer_id"] = None
    machine_packet.pop("machine_packet_sha256", None)
    machine_packet.pop("machine_packet_signature", None)
    model = EvidenceSelectionShadowReviewPacket.model_validate(machine_packet)
    digest = machine_packet_digest(model)
    machine_packet["machine_packet_sha256"] = digest
    machine_packet["machine_packet_signature"] = sign_machine_packet_digest(digest)
    return machine_packet


def _write_completed_packet(
    path: Path,
    packet: dict[str, object],
) -> Path:
    path.write_text(json.dumps(packet))
    machine_packet_sidecar_path(path).write_text(
        json.dumps(_machine_packet_for_completed_packet(packet)),
    )
    return path


def _completed_packet_payload() -> dict[str, object]:
    return {
        "schema_version": "evidence_selection_shadow_review_packet.v1",
        "study_id": "shadow-study-2026-07-07",
        "source_run_id": "00000000-0000-0000-0000-000000000048",
        "goal": "Review BRAF V600E treatment-response evidence.",
        "production_readiness_claim": False,
        "completion_status": "requires_human_labels",
        "completion_required_fields": [
            "selection_review_forms[].reviewer_id",
            "selection_review_forms[].human_selected_record_ids",
            "selection_review_forms[].explanation_quality_score",
            "selection_review_forms[].high_severity_overclaim_count",
            "review_ranking_forms[].reviewer_id",
            "review_ranking_forms[].outcome",
        ],
        "candidate_records": [
            _candidate_record("pubmed:search-1:0"),
            _candidate_record("pubmed:search-1:1"),
        ],
        "selection_review_forms": [
            {
                "run_id": "00000000-0000-0000-0000-000000000048",
                "goal": "Review BRAF V600E treatment-response evidence.",
                "reviewer_id": "reviewer-a",
                "harness_selected_record_ids": ["pubmed:search-1:0"],
                "harness_skipped_record_ids": ["pubmed:search-1:1"],
                "harness_deferred_record_ids": [],
                "human_selected_record_ids": ["pubmed:search-1:0"],
                "duplicate_suggestion_ids": [],
                "explanation_quality_score": 4,
                "high_severity_overclaim_count": 0,
                "reviewer_notes": "Looks specific.",
            },
        ],
        "review_ranking_forms": [
            {
                "source_kind": "proposal",
                "item_id": "proposal-1",
                "ranking_score": 0.91,
                "outcome": "positive",
                "reviewer_id": "reviewer-a",
                "goal": "Review BRAF V600E treatment-response evidence.",
                "evidence_shape": "variant_drug_response",
            },
        ],
    }


def _candidate_record(record_id: str) -> dict[str, object]:
    source_key, search_id, record_index_text = record_id.split(":")
    return {
        "record_id": record_id,
        "source_key": source_key,
        "source_family": "literature",
        "search_id": search_id,
        "decision": "selected",
        "relevance_label": "strong_fit",
        "reason": "Candidate evidence fixture.",
        "record_index": int(record_index_text),
        "record_hash": f"hash-{record_index_text}",
        "title": f"Candidate {record_index_text}",
        "score": 0.8,
        "matched_terms": ["BRAF"],
        "excluded_terms": [],
        "caveats": [],
    }
