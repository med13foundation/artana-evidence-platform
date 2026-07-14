"""Integrity regressions for semantic diagnostic benchmark v2."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2 import (
    build_benchmark_v2_report,
    evaluate_benchmark_v2,
    load_benchmark_v2,
    render_benchmark_v2_markdown,
    score_benchmark_v2,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.contracts import (
    EvidenceSelectionBenchmarkAIDiagnostic,
    EvidenceSelectionBenchmarkMetrics,
    EvidenceSelectionBenchmarkRecordEvaluation,
    EvidenceSelectionBenchmarkV2Score,
)
from artana_evidence_api.evidence_selection.diagnostics.predictions import (
    load_semantic_prediction_artifact,
)
from artana_evidence_api.evidence_selection.provenance import (
    EvidenceSelectionExpertStudySourceArtifact,
    EvidenceSelectionExpertStudySourceManifest,
)
from artana_evidence_api.evidence_selection.review.assessment import (
    EvidenceSelectionExplanationAssessment,
    EvidenceSelectionReviewCitation,
    EvidenceSelectionReviewInput,
)
from artana_evidence_api.evidence_selection.source_exports import (
    EvidenceSelectionReviewExport,
)
from artana_evidence_api.evidence_selection_validation import (
    EvidenceSelectionExpertStudyInput,
)
from pydantic import ValidationError

FIXTURE_PATH = Path(
    "scripts/validation/evidence_selection/fixtures/semantic_relevance_benchmark_v2.json",
)
PREDICTION_PATH = Path(
    "scripts/validation/evidence_selection/fixtures/semantic_relevance_live_baseline_predictions_v1.json",
)
V1_PATH = Path(
    "scripts/validation/evidence_selection/fixtures/semantic_relevance_failure_corpus_v1.json",
)
PACKET_MANIFEST_PATH = Path(
    "scripts/validation/evidence_selection/fixtures/semantic_relevance_benchmark_v2_packet_manifest.json",
)
V1_SHA256 = "a77e9db72d823c9bff8974afe6b2eaa74e423fb1de37ececa519bfa59b146a69"


def test_v2_preserves_v1_and_exposes_pending_and_ambiguous_records() -> None:
    loaded = load_benchmark_v2(fixture_path=FIXTURE_PATH, repository_root=Path.cwd())
    evaluation = evaluate_benchmark_v2(loaded)

    assert hashlib.sha256(V1_PATH.read_bytes()).hexdigest() == V1_SHA256
    assert evaluation.expert_study_status == "pending"
    assert len(evaluation.records) == 33
    assert (
        sum(
            record.eligibility_status == "pending_expert"
            for record in evaluation.records
        )
        == 30
    )
    ambiguous = {
        record.record_id
        for record in evaluation.records
        if record.eligibility_status == "ambiguous_pending_expert"
    }
    assert ambiguous == {
        "brca1:pmid:30191368",
        "canary:pmid:27959700",
        "canary:pmid:27393503",
    }
    assert not any(record.score_eligible for record in evaluation.records)


def test_agent_adjudication_cannot_forge_expert_provenance_or_numeric_score() -> None:
    base = {
        "record_id": "record-a",
        "provenance": "human_expert",
        "decision": "select",
        "rationale": "Agent-authored rationale.",
        "evidence_spans": [
            {"source_locator": "record-a:title", "quoted_text": "Source"},
        ],
    }
    with pytest.raises(ValidationError, match="ai_adjudicated_diagnostic"):
        EvidenceSelectionBenchmarkAIDiagnostic.model_validate(base)

    base["provenance"] = "ai_adjudicated_diagnostic"
    base["confidence_score"] = 0.99
    with pytest.raises(ValidationError, match="confidence_score"):
        EvidenceSelectionBenchmarkAIDiagnostic.model_validate(base)


def test_pending_records_and_ambiguous_canaries_never_leak_into_scores() -> None:
    loaded = load_benchmark_v2(fixture_path=FIXTURE_PATH, repository_root=Path.cwd())
    evaluation = evaluate_benchmark_v2(loaded)
    predictions = load_semantic_prediction_artifact(PREDICTION_PATH).predictions
    score = score_benchmark_v2(evaluation=evaluation, predictions=predictions)

    assert score.score_eligible_record_count == 0
    assert score.excluded_record_count == 33
    assert score.adoption_metrics is None
    assert score.canary_gate_status == "unavailable"
    assert score.ambiguous_record_count == 3
    assert score.pending_expert_record_count == 30


def test_partial_expert_eligibility_keeps_adoption_and_canaries_unavailable() -> None:
    loaded = load_benchmark_v2(fixture_path=FIXTURE_PATH, repository_root=Path.cwd())
    evaluation = evaluate_benchmark_v2(loaded)
    first_record = evaluation.records[0].model_copy(
        update={
            "eligibility_status": "score_eligible",
            "score_eligible": True,
            "expert_label": "select",
            "exclusion_reasons": (),
        },
    )
    partial_evaluation = evaluation.model_copy(
        update={
            "expert_study_status": "externally_attested",
            "records": (first_record, *evaluation.records[1:]),
        },
    )

    score = score_benchmark_v2(
        evaluation=partial_evaluation,
        predictions=load_semantic_prediction_artifact(PREDICTION_PATH).predictions,
    )

    assert score.score_eligible_record_count == 1
    assert score.excluded_record_count == 32
    assert score.adoption_metrics is None
    assert score.canary_gate_status == "unavailable"


def test_packet_manifest_marks_known_defects_insufficient() -> None:
    loaded = load_benchmark_v2(fixture_path=FIXTURE_PATH, repository_root=Path.cwd())

    assert {
        record_id
        for record_id, status in loaded.packet_status_by_record.items()
        if status.sufficiency == "known_insufficient"
    } == {
        "brca1:pmid:30191368",
        "canary:pmid:27959700",
        "canary:pmid:27393503",
    }


def test_pending_record_cannot_carry_an_expert_label() -> None:
    loaded = load_benchmark_v2(fixture_path=FIXTURE_PATH, repository_root=Path.cwd())
    record = evaluate_benchmark_v2(loaded).records[0]
    payload = record.model_dump()
    payload["expert_label"] = "select"

    with pytest.raises(ValidationError, match="eligibility, status, and expert label"):
        EvidenceSelectionBenchmarkRecordEvaluation.model_validate(payload)


def test_zero_eligible_score_cannot_carry_metrics_or_canary_pass() -> None:
    loaded = load_benchmark_v2(fixture_path=FIXTURE_PATH, repository_root=Path.cwd())
    evaluation = evaluate_benchmark_v2(loaded)
    predictions = load_semantic_prediction_artifact(PREDICTION_PATH).predictions
    score = score_benchmark_v2(evaluation=evaluation, predictions=predictions)
    fake_metrics = EvidenceSelectionBenchmarkMetrics(
        record_count=1,
        true_positive_count=1,
        false_positive_count=0,
        false_negative_count=0,
        true_negative_count=0,
        abstention_count=0,
        invalid_agent_count=0,
        precision=1.0,
        end_to_end_recall=1.0,
        decision_coverage=1.0,
    )
    payload = score.model_dump(mode="json")
    payload["adoption_metrics"] = fake_metrics.model_dump(mode="json")
    payload["canary_gate_status"] = "passed"

    with pytest.raises(ValidationError):
        EvidenceSelectionBenchmarkV2Score.model_validate(payload)


def test_report_builder_rejects_forged_score_for_pending_evaluation() -> None:
    loaded = load_benchmark_v2(fixture_path=FIXTURE_PATH, repository_root=Path.cwd())
    pending_evaluation = evaluate_benchmark_v2(loaded)
    predictions = load_semantic_prediction_artifact(PREDICTION_PATH).predictions
    first_record = pending_evaluation.records[0].model_copy(
        update={
            "eligibility_status": "score_eligible",
            "score_eligible": True,
            "expert_label": "select",
            "exclusion_reasons": (),
        },
    )
    forged_evaluation = pending_evaluation.model_copy(
        update={
            "expert_study_status": "externally_attested",
            "records": (first_record, *pending_evaluation.records[1:]),
        },
    )
    forged_score = score_benchmark_v2(
        evaluation=forged_evaluation,
        predictions=predictions,
    )
    assert forged_score.score_eligible_record_count == 1
    assert forged_score.adoption_metrics is None
    assert forged_score.canary_gate_status == "unavailable"

    with pytest.raises(TypeError, match="unexpected keyword argument 'score'"):
        build_benchmark_v2_report(
            fixture_path=FIXTURE_PATH,
            prediction_path=PREDICTION_PATH,
            evaluation=pending_evaluation,
            repository_root=Path.cwd(),
            score=forged_score,  # type: ignore[call-arg]
            generated_at=datetime(2026, 7, 13, tzinfo=UTC),
        )

    report = build_benchmark_v2_report(
        fixture_path=FIXTURE_PATH,
        prediction_path=PREDICTION_PATH,
        evaluation=pending_evaluation,
        repository_root=Path.cwd(),
        generated_at=datetime(2026, 7, 13, tzinfo=UTC),
    )
    assert report.score.score_eligible_record_count == 0
    assert report.score.adoption_metrics is None
    assert report.score.canary_gate_status == "unavailable"


def test_report_builder_rejects_prediction_with_wrong_baseline_provenance(
    tmp_path: Path,
) -> None:
    prediction_payload = json.loads(PREDICTION_PATH.read_text(encoding="utf-8"))
    prediction_payload["baseline_model"] = "openai:different-model"
    prediction_path = tmp_path / "wrong-baseline-predictions.json"
    prediction_path.write_text(json.dumps(prediction_payload), encoding="utf-8")
    loaded = load_benchmark_v2(fixture_path=FIXTURE_PATH, repository_root=Path.cwd())

    with pytest.raises(ValueError, match="baseline identity does not match"):
        build_benchmark_v2_report(
            fixture_path=FIXTURE_PATH,
            prediction_path=prediction_path,
            evaluation=evaluate_benchmark_v2(loaded),
            repository_root=Path.cwd(),
            generated_at=datetime(2026, 7, 13, tzinfo=UTC),
        )


def test_forged_numeric_metric_envelope_is_rejected() -> None:
    with pytest.raises(ValidationError, match="precision is inconsistent"):
        EvidenceSelectionBenchmarkMetrics(
            record_count=1,
            true_positive_count=1,
            false_positive_count=0,
            false_negative_count=0,
            true_negative_count=0,
            abstention_count=0,
            invalid_agent_count=0,
            precision=0.25,
            end_to_end_recall=1.0,
            decision_coverage=1.0,
        )


def test_source_packet_drift_fails_closed(tmp_path: Path) -> None:
    _copy_benchmark_inputs(tmp_path)
    packet_path = tmp_path / (
        "scripts/validation/evidence_selection/fixtures/source_artifacts/"
        "egfr_exclusion_token_canary.json"
    )
    packet_path.write_text(packet_path.read_text().replace("T790M-positive", "DRIFTED"))

    with pytest.raises(ValueError, match="artifact digest mismatch"):
        load_benchmark_v2(
            fixture_path=tmp_path / FIXTURE_PATH,
            repository_root=tmp_path,
        )


def test_ai_simulation_bundle_cannot_become_expert_evidence(tmp_path: Path) -> None:
    _copy_benchmark_inputs(tmp_path)
    bundle_path = tmp_path / "reports/ai-simulation-bundle.json"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(
        json.dumps(
            {
                "schema_version": "evidence_selection_expert_study.v2",
                "study_id": "forged-agent-study",
                "study_type": "selection_relevance",
                "study_evidence_kind": "ai_reviewer_simulation",
                "selection_reviews": [],
                "review_ranking": None,
                "source_manifest": None,
                "description": "Agent simulation must stay diagnostic.",
            },
        ),
    )
    fixture_path = tmp_path / FIXTURE_PATH
    fixture = json.loads(fixture_path.read_text())
    fixture["expert_study_bundle"] = {
        "path": "reports/ai-simulation-bundle.json",
        "sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
    }
    fixture["pending_expert_reason"] = None
    fixture_path.write_text(json.dumps(fixture))
    loaded = load_benchmark_v2(fixture_path=fixture_path, repository_root=tmp_path)

    with pytest.raises(ValueError, match="AI or synthetic"):
        evaluate_benchmark_v2(loaded)


def test_forged_real_shadow_review_source_export_is_rejected(
    tmp_path: Path,
) -> None:
    _copy_benchmark_inputs(tmp_path)
    fixture_path = tmp_path / FIXTURE_PATH
    omitted_record_id = "brca1:pmid:30191368"
    _link_real_study_bundle(
        root=tmp_path,
        fixture_path=fixture_path,
        omitted_record_id=omitted_record_id,
    )

    with pytest.raises(ValueError, match="not locally resolvable"):
        evaluate_benchmark_v2(
            load_benchmark_v2(fixture_path=fixture_path, repository_root=tmp_path),
        )


def test_verified_source_exports_still_require_external_reviewer_attestation(
    tmp_path: Path,
) -> None:
    _copy_benchmark_inputs(tmp_path)
    fixture_path = tmp_path / FIXTURE_PATH
    _link_real_study_bundle(
        root=tmp_path,
        fixture_path=fixture_path,
        omitted_record_id="",
        write_source_export=True,
    )

    evaluation = evaluate_benchmark_v2(
        load_benchmark_v2(fixture_path=fixture_path, repository_root=tmp_path),
    )

    assert evaluation.expert_study_status == (
        "source_verified_external_attestation_pending"
    )
    assert not any(record.score_eligible for record in evaluation.records)
    assert all(record.expert_label is None for record in evaluation.records)


def test_report_wording_is_honest_and_keeps_excluded_records_visible() -> None:
    loaded = load_benchmark_v2(fixture_path=FIXTURE_PATH, repository_root=Path.cwd())
    evaluation = evaluate_benchmark_v2(loaded)
    report = build_benchmark_v2_report(
        fixture_path=FIXTURE_PATH,
        prediction_path=PREDICTION_PATH,
        evaluation=evaluation,
        repository_root=Path.cwd(),
        generated_at=datetime(2026, 7, 13, tzinfo=UTC),
    )

    markdown = render_benchmark_v2_markdown(report)

    assert "Human/expert approval claim: **NO**" in markdown
    assert "**UNAVAILABLE**" in markdown
    assert "AI-adjudicated diagnostic" in markdown
    assert "brca1:pmid:30191368" in markdown
    assert "expert gold" in markdown
    assert "human approved" not in markdown.casefold()
    assert report.production_readiness_claim is False


def _copy_benchmark_inputs(root: Path) -> None:
    paths = [FIXTURE_PATH, V1_PATH, PACKET_MANIFEST_PATH]
    manifest = json.loads(PACKET_MANIFEST_PATH.read_text())
    paths.extend(Path(packet["path"]) for packet in manifest["packets"])
    for source in paths:
        destination = root / source
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def _link_real_study_bundle(
    *,
    root: Path,
    fixture_path: Path,
    omitted_record_id: str,
    write_source_export: bool = False,
) -> None:
    loaded = load_benchmark_v2(fixture_path=fixture_path, repository_root=root)
    reviews: list[EvidenceSelectionReviewInput] = []
    bindings: list[dict[str, str]] = []
    for index, case in enumerate(loaded.historical_v1.cases[:3], start=1):
        run_id = UUID(f"00000000-0000-0000-0000-{index:012d}")
        candidate_ids = tuple(record.record_id for record in case.records)
        citations = tuple(
            EvidenceSelectionReviewCitation(
                record_id=record.record_id,
                source_locator=f"{record.record_id}:evidence_excerpt",
                quoted_text=record.evidence_excerpt,
            )
            for record in case.records
            if record.record_id != omitted_record_id
        )
        reviews.append(
            EvidenceSelectionReviewInput(
                run_id=run_id,
                goal=case.goal,
                reviewer_id="reviewer-a",
                candidate_record_ids=candidate_ids,
                harness_selected_record_ids=candidate_ids,
                human_selected_record_ids=candidate_ids,
                explanation_assessment=EvidenceSelectionExplanationAssessment(
                    literal_citation_present="yes",
                    citation_entails_claim="yes",
                    all_required_criteria_addressed="yes",
                    unsupported_material_claim_present="no",
                    cited_evidence=citations,
                    reviewer_explanation="Every cited record was reviewed against the bounded packet.",
                ),
                high_severity_overclaim_findings=(),
            ),
        )
        bindings.append({"case_id": case.case_id, "review_run_id": str(run_id)})
    packet_manifest_sha = loaded.fixture.source_packet_manifest.sha256
    selection_export_path = root / "reports/selection-export.json"
    selection_export_sha = "f" * 64
    if write_source_export:
        selection_export_path.parent.mkdir(parents=True, exist_ok=True)
        selection_export = EvidenceSelectionReviewExport(
            schema_version="evidence_selection_review_export.v2",
            source_system="artana-shadow-review",
            export_id="benchmark-v2-test-export",
            exported_at="2026-07-13T00:00:00Z",
            exporter_id="review-ops",
            redaction_statement="No PHI included.",
            selection_reviews=tuple(reviews),
        )
        selection_export_path.write_text(
            json.dumps(selection_export.model_dump(mode="json"), indent=2) + "\n",
        )
        selection_export_sha = hashlib.sha256(
            selection_export_path.read_bytes()
        ).hexdigest()
    study = EvidenceSelectionExpertStudyInput(
        schema_version="evidence_selection_expert_study.v2",
        study_id="benchmark-v2-existing-gate-test",
        study_type="selection_relevance",
        study_evidence_kind="real_shadow_review",
        selection_reviews=tuple(reviews),
        source_manifest=EvidenceSelectionExpertStudySourceManifest(
            source_system="artana-shadow-review",
            export_id="benchmark-v2-test-export",
            exported_at="2026-07-13T00:00:00Z",
            exporter_id="review-ops",
            redaction_statement="No PHI included.",
            source_artifacts=(
                EvidenceSelectionExpertStudySourceArtifact(
                    artifact_id="selection-export",
                    artifact_kind="selection_review_export",
                    uri="reports/selection-export.json",
                    sha256=selection_export_sha,
                ),
                EvidenceSelectionExpertStudySourceArtifact(
                    artifact_id="benchmark-packet-manifest",
                    artifact_kind="adjudication_log",
                    uri=loaded.fixture.source_packet_manifest.path,
                    sha256=packet_manifest_sha,
                ),
            ),
            selection_review_run_ids=tuple(review.run_id for review in reviews),
            review_ranking_decision_keys=(),
            reviewer_roster=("reviewer-a",),
        ),
        description="Existing-gate integration fixture.",
    )
    bundle_path = root / "reports/real-shadow-review-bundle.json"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(
        json.dumps(study.model_dump(mode="json", exclude_none=True), indent=2) + "\n",
    )
    fixture = json.loads(fixture_path.read_text())
    fixture["expert_study_bundle"] = {
        "path": "reports/real-shadow-review-bundle.json",
        "sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
    }
    fixture["pending_expert_reason"] = None
    fixture["expert_review_bindings"] = bindings
    fixture_path.write_text(json.dumps(fixture))
