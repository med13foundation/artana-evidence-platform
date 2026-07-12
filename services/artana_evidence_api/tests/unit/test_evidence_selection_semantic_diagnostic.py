"""Regression tests for the semantic-selection diagnostic corpus."""

from __future__ import annotations

import hashlib
import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest
from artana_evidence_api.evidence_selection.diagnostics.fixture import (
    EvidenceSelectionSemanticDiagnosticFixture,
    load_semantic_diagnostic_fixture,
)
from artana_evidence_api.evidence_selection.diagnostics.predictions import (
    EvidenceSelectionSemanticPrediction,
    load_semantic_prediction_artifact,
    verify_prediction_provenance,
)
from artana_evidence_api.evidence_selection.diagnostics.report import (
    EvidenceSelectionSemanticDiagnosticReport,
)
from artana_evidence_api.evidence_selection.diagnostics.scoring import (
    score_semantic_diagnostic,
)
from pydantic import ValidationError

FIXTURE_PATH = Path(
    "scripts/validation/evidence_selection/fixtures/"
    "semantic_relevance_failure_corpus_v1.json",
)
REPORT_PATH = Path(
    "docs/validation/reports/2026-07-11-pr-semantic-pr1-failure-corpus-baseline.json",
)
PREDICTION_PATH = Path(
    "scripts/validation/evidence_selection/fixtures/"
    "semantic_relevance_live_baseline_predictions_v1.json",
)


def _baseline_predictions() -> tuple[EvidenceSelectionSemanticPrediction, ...]:
    return load_semantic_prediction_artifact(PREDICTION_PATH).predictions


def _fixture_payload() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_semantic_diagnostic_fixture_is_strict_and_complete() -> None:
    fixture = load_semantic_diagnostic_fixture(FIXTURE_PATH)

    assert fixture.provenance == "ai_adjudicated_diagnostic"
    assert fixture.schema_version == "evidence_selection_semantic_diagnostic.v1"
    assert [case.case_id for case in fixture.cases] == [
        "egfr_t790m_primary_evidence",
        "brca1_risk_penetrance",
        "cftr_f508del_eti_response",
        "egfr_exclusion_token_canary",
    ]
    assert sum(case.evaluation_role == "primary" for case in fixture.cases) == 3
    assert sum(case.evaluation_role == "canary" for case in fixture.cases) == 1
    assert len({case.source_run_id for case in fixture.cases}) == 4
    assert all(len(case.source_artifact_sha256) == 64 for case in fixture.cases)
    failure_tags = {
        tag
        for case in fixture.cases
        for record in case.records
        for tag in record.failure_tags
    }
    assert failure_tags >= {
        "primary_trial_false_negative",
        "secondary_review_false_positive",
        "off_target_gene_false_positive",
        "population_mismatch_false_positive",
        "exclusion_token_scope_failure",
    }


@pytest.mark.parametrize(
    ("mutate", "error_match"),
    [
        (
            lambda payload: payload["cases"].append(deepcopy(payload["cases"][0])),
            "case_id values must be unique",
        ),
        (
            lambda payload: payload["cases"][0]["records"].append(
                deepcopy(payload["cases"][0]["records"][0]),
            ),
            "record_id values must be unique",
        ),
        (
            lambda payload: payload["cases"][0]["records"][0].pop(
                "expected_label",
            ),
            "expected_label",
        ),
        (
            lambda payload: payload.update(
                {"provenance": "human_expert_review"},
            ),
            "ai_adjudicated_diagnostic",
        ),
    ],
)
def test_semantic_diagnostic_fixture_rejects_invalid_or_ambiguous_data(
    mutate: object,
    error_match: str,
) -> None:
    payload = _fixture_payload()
    assert callable(mutate)
    mutate(payload)

    with pytest.raises((ValidationError, ValueError), match=error_match):
        EvidenceSelectionSemanticDiagnosticFixture.model_validate(payload)


def test_semantic_diagnostic_scoring_does_not_credit_abstention_or_invalid_agent() -> (
    None
):
    fixture = EvidenceSelectionSemanticDiagnosticFixture.model_validate(
        {
            "schema_version": "evidence_selection_semantic_diagnostic.v1",
            "benchmark_name": "scoring-contract",
            "provenance": "ai_adjudicated_diagnostic",
            "adjudication_scope": "Synthetic scoring contract only.",
            "baseline_commit": "a" * 40,
            "baseline_model": "fixture-model",
            "cases": [
                {
                    "case_id": "primary-a",
                    "display_name": "Primary A",
                    "evaluation_role": "primary",
                    "source_run_id": "00000000-0000-4000-a000-000000000001",
                    "source_artifact_sha256": "b" * 64,
                    "source_artifact_path": "synthetic/primary-a.json",
                    "upstream_source_artifact_sha256": "1" * 64,
                    "goal": "Select useful evidence.",
                    "instructions": "Use the supplied evidence.",
                    "inclusion_criteria": ["Direct support"],
                    "exclusion_criteria": ["Off target"],
                    "records": [
                        {
                            "record_id": "pubmed:1",
                            "source_key": "pubmed",
                            "source_record_id": "1",
                            "title": "Positive record",
                            "evidence_excerpt": "Direct support is present.",
                            "expected_label": "select",
                            "expected_reason": "Direct evidence.",
                            "failure_tags": ["fixture"],
                        },
                        {
                            "record_id": "pubmed:2",
                            "source_key": "pubmed",
                            "source_record_id": "2",
                            "title": "Negative record",
                            "evidence_excerpt": "The record is off target.",
                            "expected_label": "reject",
                            "expected_reason": "Off target.",
                            "failure_tags": ["fixture"],
                        },
                    ],
                },
                {
                    "case_id": "primary-b",
                    "display_name": "Primary B",
                    "evaluation_role": "primary",
                    "source_run_id": "00000000-0000-4000-a000-000000000002",
                    "source_artifact_sha256": "c" * 64,
                    "source_artifact_path": "synthetic/primary-b.json",
                    "upstream_source_artifact_sha256": "2" * 64,
                    "goal": "Select another record.",
                    "instructions": "Use the supplied evidence.",
                    "inclusion_criteria": ["Direct support"],
                    "exclusion_criteria": ["Off target"],
                    "records": [
                        {
                            "record_id": "pubmed:3",
                            "source_key": "pubmed",
                            "source_record_id": "3",
                            "title": "Selected negative",
                            "evidence_excerpt": "The record is off target.",
                            "expected_label": "reject",
                            "expected_reason": "Off target.",
                            "failure_tags": ["fixture"],
                        }
                    ],
                },
                {
                    "case_id": "primary-c",
                    "display_name": "Primary C",
                    "evaluation_role": "primary",
                    "source_run_id": "00000000-0000-4000-a000-000000000003",
                    "source_artifact_sha256": "d" * 64,
                    "source_artifact_path": "synthetic/primary-c.json",
                    "upstream_source_artifact_sha256": "3" * 64,
                    "goal": "Select a third record.",
                    "instructions": "Use the supplied evidence.",
                    "inclusion_criteria": ["Direct support"],
                    "exclusion_criteria": ["Off target"],
                    "records": [
                        {
                            "record_id": "pubmed:4",
                            "source_key": "pubmed",
                            "source_record_id": "4",
                            "title": "Selected positive",
                            "evidence_excerpt": "Direct support is present.",
                            "expected_label": "select",
                            "expected_reason": "Direct evidence.",
                            "failure_tags": ["fixture"],
                        }
                    ],
                },
                {
                    "case_id": "canary",
                    "display_name": "Canary",
                    "evaluation_role": "canary",
                    "source_run_id": "00000000-0000-4000-a000-000000000004",
                    "source_artifact_sha256": "e" * 64,
                    "source_artifact_path": "synthetic/canary.json",
                    "upstream_source_artifact_sha256": "4" * 64,
                    "goal": "Canary.",
                    "instructions": "Canary.",
                    "inclusion_criteria": ["Canary"],
                    "exclusion_criteria": ["Off target"],
                    "records": [
                        {
                            "record_id": "pubmed:5",
                            "source_key": "pubmed",
                            "source_record_id": "5",
                            "title": "Canary record",
                            "evidence_excerpt": "Canary evidence.",
                            "expected_label": "select",
                            "expected_reason": "Canary evidence.",
                            "failure_tags": ["fixture"],
                        }
                    ],
                },
            ],
        },
    )

    score = score_semantic_diagnostic(
        fixture,
        (
            EvidenceSelectionSemanticPrediction(
                record_id="pubmed:1", decision="abstain", reason="test"
            ),
            EvidenceSelectionSemanticPrediction(
                record_id="pubmed:2", decision="invalid_agent", reason="test"
            ),
            EvidenceSelectionSemanticPrediction(
                record_id="pubmed:3", decision="select", reason="test"
            ),
            EvidenceSelectionSemanticPrediction(
                record_id="pubmed:4", decision="select", reason="test"
            ),
            EvidenceSelectionSemanticPrediction(
                record_id="pubmed:5", decision="reject", reason="test"
            ),
        ),
    )

    first_case = score.case_results[0]
    assert first_case.true_positive_count == 0
    assert first_case.false_negative_count == 0
    assert first_case.true_negative_count == 0
    assert first_case.abstention_count == 1
    assert first_case.invalid_agent_count == 1
    assert score.micro.true_positive_count == 1
    assert score.micro.false_positive_count == 1
    assert score.micro.false_negative_count == 0
    assert score.micro.true_negative_count == 0
    assert score.micro.abstention_count == 1
    assert score.micro.invalid_agent_count == 1
    assert score.micro.decision_coverage == pytest.approx(0.5)
    assert score.micro.end_to_end_recall == pytest.approx(0.5)
    assert score.scored_case_count == 3
    assert score.canary_case_count == 1


def test_semantic_failure_corpus_baseline_is_measurably_red() -> None:
    fixture = load_semantic_diagnostic_fixture(FIXTURE_PATH)
    score = score_semantic_diagnostic(fixture, _baseline_predictions())

    assert score.micro.true_positive_count == 5
    assert score.micro.false_positive_count == 16
    assert score.micro.false_negative_count == 8
    assert score.micro.precision == pytest.approx(5 / 21)
    assert score.micro.end_to_end_recall == pytest.approx(5 / 13)
    primary_results = score.case_results[:3]
    assert score.micro.record_count == sum(
        result.record_count for result in primary_results
    )
    assert score.macro.precision == pytest.approx(
        sum(result.precision for result in primary_results) / 3,
    )
    assert score.macro.end_to_end_recall == pytest.approx(
        sum(result.end_to_end_recall for result in primary_results) / 3,
    )
    assert score.case_results[-1].predicted_select_count == 0
    assert score.case_results[-1].precision == 0.0
    assert score.micro.invalid_agent_count == 0
    assert score.micro.abstention_count == 0
    assert [result.case_id for result in score.case_results] == [
        "egfr_t790m_primary_evidence",
        "brca1_risk_penetrance",
        "cftr_f508del_eti_response",
        "egfr_exclusion_token_canary",
    ]
    assert score.case_results[-1].evaluation_role == "canary"
    assert score.case_results[-1].false_negative_count > 0


def test_checked_in_report_matches_fixture_and_baseline_score() -> None:
    fixture = load_semantic_diagnostic_fixture(FIXTURE_PATH)
    artifact = load_semantic_prediction_artifact(PREDICTION_PATH)
    verify_prediction_provenance(
        fixture=fixture, artifact=artifact, repository_root=Path.cwd()
    )
    expected_score = score_semantic_diagnostic(fixture, artifact.predictions)
    report = EvidenceSelectionSemanticDiagnosticReport.model_validate_json(
        REPORT_PATH.read_text(encoding="utf-8"),
    )

    assert (
        report.fixture_sha256 == hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest()
    )
    assert report.fixture_path == str(FIXTURE_PATH)
    assert report.fixture_provenance == fixture.provenance
    assert (
        report.prediction_artifact_sha256
        == hashlib.sha256(PREDICTION_PATH.read_bytes()).hexdigest()
    )
    assert report.production_readiness_claim is False
    assert report.score == expected_score
    assert [artifact.source_run_id for artifact in report.source_artifacts] == [
        case.source_run_id for case in fixture.cases
    ]
    assert [
        artifact.source_artifact_sha256 for artifact in report.source_artifacts
    ] == [case.source_artifact_sha256 for case in fixture.cases]


def test_report_rejects_unknown_case_evaluation_role() -> None:
    payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    payload["score"]["case_results"][0]["evaluation_role"] = "future-role"

    with pytest.raises(ValidationError, match="evaluation_role"):
        EvidenceSelectionSemanticDiagnosticReport.model_validate_json(
            json.dumps(payload),
        )


def test_semantic_scoring_rejects_missing_duplicate_or_unknown_predictions() -> None:
    fixture = load_semantic_diagnostic_fixture(FIXTURE_PATH)
    predictions = list(_baseline_predictions())

    with pytest.raises(ValueError, match="missing predictions"):
        score_semantic_diagnostic(fixture, tuple(predictions[:-1]))
    with pytest.raises(ValueError, match="duplicate prediction"):
        score_semantic_diagnostic(fixture, (*predictions, predictions[0]))
    with pytest.raises(ValueError, match="unknown record IDs"):
        score_semantic_diagnostic(
            fixture,
            (
                *predictions[:-1],
                EvidenceSelectionSemanticPrediction(
                    record_id="pubmed:unknown",
                    decision="reject",
                    reason="Unknown candidate.",
                ),
            ),
        )

    invalid_decision_predictions = list(_baseline_predictions())
    object.__setattr__(invalid_decision_predictions[0], "decision", "future-decision")
    with pytest.raises(ValueError, match="unsupported prediction decision"):
        score_semantic_diagnostic(fixture, tuple(invalid_decision_predictions))


@pytest.mark.parametrize(
    ("field", "error_match"),
    [
        ("source_run_id", "source_run_id values must be unique"),
        ("source_artifact_sha256", "source_artifact_sha256 values must be unique"),
    ],
)
def test_fixture_rejects_reused_source_identities(
    field: str,
    error_match: str,
) -> None:
    payload = _fixture_payload()
    payload["cases"][1][field] = payload["cases"][0][field]

    with pytest.raises(ValidationError, match=error_match):
        EvidenceSelectionSemanticDiagnosticFixture.model_validate(payload)


def test_fixture_rejects_ambiguous_duplicate_groups() -> None:
    payload = _fixture_payload()
    records = payload["cases"][0]["records"]
    records[1]["source_record_id"] = records[0]["source_record_id"]
    records[1]["duplicate_group"] = "different-group"

    with pytest.raises(ValidationError, match="repeated source records"):
        EvidenceSelectionSemanticDiagnosticFixture.model_validate(payload)


def test_prediction_provenance_rejects_tampered_source_snapshot(
    tmp_path: Path,
) -> None:
    fixture = load_semantic_diagnostic_fixture(FIXTURE_PATH)
    artifact = load_semantic_prediction_artifact(PREDICTION_PATH)
    source = artifact.source_artifacts[0]
    tampered_path = tmp_path / source.source_artifact_path
    tampered_path.parent.mkdir(parents=True)
    tampered_path.write_text("tampered", encoding="utf-8")

    with pytest.raises(ValueError, match="digest mismatch"):
        verify_prediction_provenance(
            fixture=fixture,
            artifact=artifact,
            repository_root=tmp_path,
        )


def test_prediction_provenance_rejects_fixture_content_drift(tmp_path: Path) -> None:
    payload = _fixture_payload()
    payload["cases"][0]["records"][0]["title"] = "Semantically changed title."
    fixture = EvidenceSelectionSemanticDiagnosticFixture.model_validate(payload)
    artifact = load_semantic_prediction_artifact(PREDICTION_PATH)
    source_root = Path(
        "scripts/validation/evidence_selection/fixtures/source_artifacts"
    )
    shutil.copytree(source_root, tmp_path / source_root)

    with pytest.raises(ValueError, match="fixture content does not match"):
        verify_prediction_provenance(
            fixture=fixture,
            artifact=artifact,
            repository_root=tmp_path,
        )
