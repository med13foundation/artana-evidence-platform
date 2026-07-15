"""Adversarial coverage for external expert-pilot attestations and scoring."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path
from types import ModuleType

import pytest
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.expert_pilot import (
    review_loader as expert_pilot_review_loader,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.expert_pilot.adjudication import (
    PreparedExpertPilotAdjudication,
    VerifiedExpertPilotAdjudication,
    build_expert_pilot_gold,
    load_and_verify_adjudication_completion,
    prepare_expert_pilot_adjudication,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.expert_pilot.attestation import (
    canonical_payload_bytes,
    canonical_payload_sha256,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.expert_pilot.evaluation import (
    PreparedExpertPilotSafetyAudit,
    build_expert_pilot_result,
    load_and_verify_safety_completion,
    load_registered_model_runs,
    prepare_expert_pilot_safety_audit,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.expert_pilot.evaluation_contracts import (
    EvidenceSelectionExpertPilotEvaluationProtocol,
    EvidenceSelectionExpertPilotGoldArtifact,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.expert_pilot.publication import (
    publish_expert_pilot_stage,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.expert_pilot.review_contracts import (
    EvidenceSelectionExpertPilotAdjudicationCompletionPayload,
    EvidenceSelectionExpertPilotAdjudicationFinding,
    EvidenceSelectionExpertPilotReviewCompletionPayload,
    EvidenceSelectionExpertPilotReviewerCredential,
    EvidenceSelectionExpertPilotReviewerRegistryPayload,
    EvidenceSelectionExpertPilotReviewFinding,
    EvidenceSelectionExpertPilotSafetyCompletionPayload,
    EvidenceSelectionExpertPilotSafetyFinding,
    EvidenceSelectionExpertPilotSignedAdjudicationCompletion,
    EvidenceSelectionExpertPilotSignedReviewCompletion,
    EvidenceSelectionExpertPilotSignedReviewerRegistry,
    EvidenceSelectionExpertPilotSignedSafetyCompletion,
    SafetyAssessment,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.expert_pilot.review_loader import (
    LoadedExpertPilotPublication,
    VerifiedExpertPilotRegistry,
    VerifiedExpertPilotReviewCompletion,
    load_and_verify_first_pass_completions,
    load_and_verify_reviewer_registry,
    load_expert_pilot_evaluation_protocol,
    load_expert_pilot_publication,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.loader import (
    read_verified_artifact,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.pilot_loader import (
    LoadedEvidenceSelectionExpertPilot,
    load_expert_pilot,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.pilot_publication import (
    publish_expert_pilot_packets,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import BaseModel, ValidationError

PILOT_PROTOCOL_PATH = Path(
    "scripts/validation/evidence_selection/fixtures/"
    "semantic_relevance_expert_pilot_protocol_v1.json"
)
EVALUATION_PROTOCOL_PATH = Path(
    "scripts/validation/evidence_selection/fixtures/"
    "semantic_relevance_expert_pilot_evaluation_protocol_v1.json"
)
SIGNING_KEY_ENV = "ARTANA_EVIDENCE_SHADOW_REVIEW_PACKET_SIGNING_KEY"
IMPORT_SCRIPT_PATH = Path("scripts/import_evidence_selection_expert_pilot_reviews.py")
SAFETY_BLINDING_KEY = bytes.fromhex("ab" * 32)


@dataclass(frozen=True, slots=True)
class _SyntheticFirstPass:
    loaded_pilot: LoadedEvidenceSelectionExpertPilot
    evaluation_protocol: EvidenceSelectionExpertPilotEvaluationProtocol
    evaluation_protocol_sha256: str
    publication: LoadedExpertPilotPublication
    registry: VerifiedExpertPilotRegistry
    completions: tuple[VerifiedExpertPilotReviewCompletion, ...]
    prepared: PreparedExpertPilotAdjudication
    reviewer_private_keys: dict[str, Ed25519PrivateKey]
    desired_labels: dict[str, str]
    publication_dir: Path
    registry_path: Path
    completion_dir: Path
    issuer_public_key_hex: str


def test_protocol_pre_registers_six_runs_and_preserves_stronger_quality_gates() -> None:
    loaded_pilot = load_expert_pilot(
        protocol_path=PILOT_PROTOCOL_PATH,
        repository_root=Path.cwd(),
    )
    protocol, _ = load_expert_pilot_evaluation_protocol(
        path=EVALUATION_PROTOCOL_PATH,
        repository_root=Path.cwd(),
        loaded_pilot=loaded_pilot,
    )

    assert len(protocol.model_runs) == 6
    assert {run.model_id for run in protocol.model_runs} == {
        "openai:gpt-5.4-mini",
        "openai:gpt-5.6-luna",
    }
    assert protocol.expected_record_count == 33
    assert protocol.minimum_worst_decision_coverage == 0.8
    assert protocol.minimum_case_precision == 0.7
    assert protocol.minimum_case_recall == 0.7
    assert protocol.minimum_case_decision_coverage == 0.7
    assert protocol.minimum_exact_decision_repeatability == 1.0
    assert protocol.agent_numeric_judgments_allowed is False


def test_protocol_rejects_duplicate_run_artifact_bytes() -> None:
    payload = json.loads(EVALUATION_PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["model_runs"][1]["artifact"]["sha256"] = payload["model_runs"][0][
        "artifact"
    ]["sha256"]

    with pytest.raises(ValidationError, match="artifact bytes must be unique"):
        EvidenceSelectionExpertPilotEvaluationProtocol.model_validate_json(
            json.dumps(payload)
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("fixture", "fixture mismatch"),
        ("case", "inventory mismatch"),
        ("role", "case-role mismatch"),
    ],
)
def test_registered_runs_must_match_frozen_benchmark_partitions(
    mutation: str,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded_pilot = load_expert_pilot(
        protocol_path=PILOT_PROTOCOL_PATH,
        repository_root=Path.cwd(),
    )
    protocol = EvidenceSelectionExpertPilotEvaluationProtocol.model_validate_json(
        EVALUATION_PROTOCOL_PATH.read_bytes()
    )
    target = protocol.model_runs[0].artifact
    _, original_bytes = read_verified_artifact(
        reference=target,
        repository_root=Path.cwd(),
    )
    payload = json.loads(original_bytes)
    if mutation == "fixture":
        payload["fixture_sha256"] = "0" * 64
    elif mutation == "case":
        payload["record_results"][0]["case_id"] = "wrong-case"
    else:
        payload["score"]["case_results"][0]["evaluation_role"] = "canary"
    mutated_bytes = json.dumps(payload).encode("utf-8")

    def _read_artifact(*, reference, repository_root):
        if reference.path == target.path:
            return Path(reference.path), mutated_bytes
        return read_verified_artifact(
            reference=reference,
            repository_root=repository_root,
        )

    monkeypatch.setattr(
        expert_pilot_review_loader,
        "read_verified_artifact",
        _read_artifact,
    )

    with pytest.raises(ValueError, match=message):
        load_expert_pilot_evaluation_protocol(
            path=EVALUATION_PROTOCOL_PATH,
            repository_root=Path.cwd(),
            loaded_pilot=loaded_pilot,
        )


def test_signed_human_chain_builds_diagnostic_result_without_adoption_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_pass = _build_synthetic_first_pass(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        disagreement=True,
    )
    adjudication = _complete_adjudication(tmp_path=tmp_path, study=first_pass)
    gold = _gold(study=first_pass, adjudication=adjudication)
    model_runs = load_registered_model_runs(
        protocol=first_pass.evaluation_protocol,
        repository_root=Path.cwd(),
    )
    prepared_safety = prepare_expert_pilot_safety_audit(
        loaded_pilot=first_pass.loaded_pilot,
        evaluation_protocol_sha256=first_pass.evaluation_protocol_sha256,
        gold=gold,
        model_runs=model_runs,
        blinding_key=SAFETY_BLINDING_KEY,
    )
    alternate_safety = prepare_expert_pilot_safety_audit(
        loaded_pilot=first_pass.loaded_pilot,
        evaluation_protocol_sha256=first_pass.evaluation_protocol_sha256,
        gold=gold,
        model_runs=model_runs,
        blinding_key=bytes.fromhex("cd" * 32),
    )
    assert tuple(
        (item.blinded_run_id, item.audit_item_id)
        for item in prepared_safety.request.items
    ) != tuple(
        (item.blinded_run_id, item.audit_item_id)
        for item in alternate_safety.request.items
    )
    enumerable_id = (
        "blinded-run-"
        + hashlib.sha256(
            (
                f"{first_pass.loaded_pilot.protocol.study_id}"
                "\x1fcurrent-run-1\x1fsafety-run"
            ).encode()
        ).hexdigest()[:12]
    )
    assert all(
        item.blinded_run_id != enumerable_id for item in prepared_safety.request.items
    )
    safety = _complete_safety(
        tmp_path=tmp_path,
        study=first_pass,
        gold=gold,
        prepared=prepared_safety,
        adjudication=adjudication,
    )

    result = build_expert_pilot_result(
        protocol=first_pass.evaluation_protocol,
        gold=gold,
        registry=first_pass.registry,
        model_runs=model_runs,
        prepared_safety=prepared_safety,
        safety=safety,
    )

    assert gold.score_eligible_record_count == 33
    assert gold.first_pass_agreement_count == 32
    assert gold.first_pass_selection_agreement_count == 32
    assert gold.first_pass_sufficiency_agreement_count == 33
    assert result.expert_study_status == "externally_attested"
    assert result.external_identity_attestation_verified is True
    assert (
        result.issuer_public_key_sha256
        == hashlib.sha256(bytes.fromhex(first_pass.issuer_public_key_hex)).hexdigest()
    )
    assert result.model_adoption_decision == "not_evaluated_diagnostic_only"
    assert result.production_readiness_claim is False
    assert result.trusted_graph_readiness_claim is False
    candidate = next(
        summary
        for summary in result.model_summaries
        if summary.model_role == "candidate"
    )
    assert candidate.exact_decision_repeatability is not None
    assert candidate.exact_decision_repeatability < 1.0
    assert candidate.gate_status == "failed"


def test_forged_reviewer_signature_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="Ed25519 signature"):
        _build_synthetic_first_pass(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            forged_first_completion=True,
        )


def test_registry_must_bind_exact_packet_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="loaded study protocols"):
        _build_synthetic_first_pass(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            wrong_publication_hash=True,
        )


def test_publication_rejects_producer_signed_stale_bundles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(SIGNING_KEY_ENV, "synthetic-test-producer-key")
    loaded_pilot = load_expert_pilot(
        protocol_path=PILOT_PROTOCOL_PATH,
        repository_root=Path.cwd(),
    )
    stale_pilot = replace(
        loaded_pilot,
        protocol=loaded_pilot.protocol.model_copy(
            update={"study_id": "semantic-relevance-stale-study"}
        ),
        protocol_sha256="0" * 64,
    )
    publication_dir = tmp_path / "stale-publication"
    publish_expert_pilot_packets(
        loaded=stale_pilot,
        output_dir=publication_dir,
    )
    manifest_path = publication_dir / "publication_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["study_id"] = loaded_pilot.protocol.study_id
    manifest["protocol_sha256"] = loaded_pilot.protocol_sha256
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="exactly match the frozen pilot"):
        load_expert_pilot_publication(
            directory=publication_dir,
            loaded_pilot=loaded_pilot,
        )


def test_reviewer_cannot_supply_numeric_confidence() -> None:
    payload = {
        "candidate_id": "candidate-0123456789abcdef",
        "selection_label": "select",
        "packet_sufficiency": "sufficient",
        "supporting_spans": ["Literal source text"],
        "reviewer_explanation": "The source directly meets the frozen criteria.",
        "confidence": 0.99,
    }

    with pytest.raises(ValidationError, match="confidence"):
        EvidenceSelectionExpertPilotReviewFinding.model_validate(payload)


def test_adjudication_and_safety_spans_must_be_nonblank_and_trimmed() -> None:
    with pytest.raises(ValidationError, match="nonblank"):
        EvidenceSelectionExpertPilotAdjudicationFinding(
            adjudication_item_id="adjudication-0123456789abcdef",
            selection_label="select",
            packet_sufficiency="sufficient",
            supporting_spans=("",),
            reviewer_explanation="Literal evidence is required.",
        )
    with pytest.raises(ValidationError, match="nonblank"):
        EvidenceSelectionExpertPilotSafetyFinding(
            audit_item_id="safety-0123456789abcdef",
            assessment="supported",
            claim_spans=(),
            source_support_spans=("   ",),
            reviewer_explanation="Literal source support is required.",
        )


def test_stage_publication_rejects_empty_artifact_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="flat and nonempty"):
        publish_expert_pilot_stage(
            output_dir=tmp_path / "invalid-stage",
            content_by_name={"": "content"},
        )


def test_incomplete_adjudication_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = _build_synthetic_first_pass(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        disagreement=True,
    )
    path = _write_adjudication(
        tmp_path=tmp_path,
        study=study,
        findings=(),
    )

    with pytest.raises(ValueError, match="exactly follow request item order"):
        load_and_verify_adjudication_completion(
            path=path,
            prepared=study.prepared,
            registry=study.registry,
            loaded_pilot=study.loaded_pilot,
        )


def test_insufficient_gold_makes_all_model_gates_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = _build_synthetic_first_pass(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        disagreement=True,
    )
    adjudication = _complete_adjudication(
        tmp_path=tmp_path,
        study=study,
        insufficient=True,
    )
    gold = _gold(study=study, adjudication=adjudication)
    model_runs = load_registered_model_runs(
        protocol=study.evaluation_protocol,
        repository_root=Path.cwd(),
    )
    prepared_safety = prepare_expert_pilot_safety_audit(
        loaded_pilot=study.loaded_pilot,
        evaluation_protocol_sha256=study.evaluation_protocol_sha256,
        gold=gold,
        model_runs=model_runs,
        blinding_key=SAFETY_BLINDING_KEY,
    )
    safety = _complete_safety(
        tmp_path=tmp_path,
        study=study,
        gold=gold,
        prepared=prepared_safety,
        adjudication=adjudication,
    )
    result = build_expert_pilot_result(
        protocol=study.evaluation_protocol,
        gold=gold,
        registry=study.registry,
        model_runs=model_runs,
        prepared_safety=prepared_safety,
        safety=safety,
    )

    assert gold.score_eligible_record_count == 32
    assert result.comparison_status == "unavailable"
    assert all(
        summary.gate_status == "unavailable" for summary in result.model_summaries
    )
    assert all(run.metrics is None for run in result.model_run_results)


def test_cli_recomputes_and_atomically_publishes_verified_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = _build_synthetic_first_pass(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        disagreement=True,
    )
    adjudication = _complete_adjudication(tmp_path=tmp_path, study=study)
    gold = _gold(study=study, adjudication=adjudication)
    model_runs = load_registered_model_runs(
        protocol=study.evaluation_protocol,
        repository_root=Path.cwd(),
    )
    prepared_safety = prepare_expert_pilot_safety_audit(
        loaded_pilot=study.loaded_pilot,
        evaluation_protocol_sha256=study.evaluation_protocol_sha256,
        gold=gold,
        model_runs=model_runs,
        blinding_key=SAFETY_BLINDING_KEY,
    )
    _complete_safety(
        tmp_path=tmp_path,
        study=study,
        gold=gold,
        prepared=prepared_safety,
        adjudication=adjudication,
    )
    blinding_key_path = tmp_path / "safety-blinding.key"
    blinding_key_path.write_text(
        SAFETY_BLINDING_KEY.hex() + "\n",
        encoding="ascii",
    )
    blinding_key_path.chmod(0o600)
    output_dir = tmp_path / "verified-result"
    module = _load_import_script()

    exit_code = module.main(
        (
            "finalize",
            "--pilot-protocol",
            str(PILOT_PROTOCOL_PATH),
            "--evaluation-protocol",
            str(EVALUATION_PROTOCOL_PATH),
            "--packet-publication",
            str(study.publication_dir),
            "--reviewer-registry",
            str(study.registry_path),
            "--issuer-public-key-hex",
            study.issuer_public_key_hex,
            "--issuer-key-id",
            "issuer-key-synthetic-root",
            "--first-pass-completions",
            str(study.completion_dir),
            "--adjudication-completion",
            str(tmp_path / "adjudication-completion.json"),
            "--safety-blinding-key-file",
            str(blinding_key_path),
            "--safety-completion",
            str(tmp_path / "safety-completion.json"),
            "--output-dir",
            str(output_dir),
        )
    )

    assert exit_code == 0
    assert {path.name for path in output_dir.iterdir()} == {
        "adjudication_request.json",
        "gold.json",
        "safety_request.json",
        "result.json",
        "result.md",
    }
    result_payload = json.loads(
        (output_dir / "result.json").read_text(encoding="utf-8")
    )
    assert result_payload["model_adoption_decision"] == (
        "not_evaluated_diagnostic_only"
    )
    assert result_payload["production_readiness_claim"] is False


def test_not_assessable_safety_finding_keeps_diagnostic_gate_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = _build_synthetic_first_pass(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        disagreement=True,
    )
    adjudication = _complete_adjudication(tmp_path=tmp_path, study=study)
    gold = _gold(study=study, adjudication=adjudication)
    model_runs = load_registered_model_runs(
        protocol=study.evaluation_protocol,
        repository_root=Path.cwd(),
    )
    prepared_safety = prepare_expert_pilot_safety_audit(
        loaded_pilot=study.loaded_pilot,
        evaluation_protocol_sha256=study.evaluation_protocol_sha256,
        gold=gold,
        model_runs=model_runs,
        blinding_key=SAFETY_BLINDING_KEY,
    )
    safety = _complete_safety(
        tmp_path=tmp_path,
        study=study,
        gold=gold,
        prepared=prepared_safety,
        adjudication=adjudication,
        assessment="not_assessable",
    )
    result = build_expert_pilot_result(
        protocol=study.evaluation_protocol,
        gold=gold,
        registry=study.registry,
        model_runs=model_runs,
        prepared_safety=prepared_safety,
        safety=safety,
    )

    assert result.comparison_status == "unavailable"
    assert all(
        summary.gate_status == "unavailable" for summary in result.model_summaries
    )
    assert all(run.metrics is not None for run in result.model_run_results)


def _build_synthetic_first_pass(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    disagreement: bool = False,
    forged_first_completion: bool = False,
    wrong_publication_hash: bool = False,
) -> _SyntheticFirstPass:
    monkeypatch.setenv(SIGNING_KEY_ENV, "synthetic-test-producer-key")
    loaded_pilot = load_expert_pilot(
        protocol_path=PILOT_PROTOCOL_PATH,
        repository_root=Path.cwd(),
    )
    evaluation_protocol, evaluation_sha = load_expert_pilot_evaluation_protocol(
        path=EVALUATION_PROTOCOL_PATH,
        repository_root=Path.cwd(),
        loaded_pilot=loaded_pilot,
    )
    publication_dir = tmp_path / "packet-publication"
    publish_expert_pilot_packets(loaded=loaded_pilot, output_dir=publication_dir)
    publication = load_expert_pilot_publication(
        directory=publication_dir,
        loaded_pilot=loaded_pilot,
    )
    issuer_private_key = Ed25519PrivateKey.generate()
    reviewer_keys = {
        slot: Ed25519PrivateKey.generate()
        for slot in (
            *loaded_pilot.protocol.independent_reviewer_slots,
            loaded_pilot.protocol.adjudicator_slot,
        )
    }
    registry_payload = EvidenceSelectionExpertPilotReviewerRegistryPayload(
        schema_version="evidence_selection_expert_pilot_reviewer_registry.v1",
        study_id=loaded_pilot.protocol.study_id,
        pilot_protocol_sha256=loaded_pilot.protocol_sha256,
        evaluation_protocol_sha256=evaluation_sha,
        publication_manifest_sha256=(
            "0" * 64 if wrong_publication_hash else publication.manifest_sha256
        ),
        issuer_id="synthetic-test-credential-authority",
        valid_from=evaluation_protocol.registered_at,
        valid_until=evaluation_protocol.registered_at + timedelta(days=1),
        credentials=tuple(
            EvidenceSelectionExpertPilotReviewerCredential(
                reviewer_id=f"synthetic-human-{index}",
                subject_identity_id=f"verified-subject-synthetic-{index}",
                reviewer_slot=slot,
                review_role=(
                    "independent_first_pass"
                    if slot in loaded_pilot.protocol.independent_reviewer_slots
                    else "adjudicator_and_safety_reviewer"
                ),
                key_id=f"reviewer-key-synthetic-{index}",
                public_key_hex=reviewer_keys[slot]
                .public_key()
                .public_bytes_raw()
                .hex(),
                identity_assurance="issuer_verified_real_person",
                qualification_claim="domain_qualified_human",
                independence_claim=(
                    "independent_of_model_development_and_other_reviewers"
                ),
                conflict_of_interest_declaration="no_conflict_declared",
            )
            for index, slot in enumerate(reviewer_keys, start=1)
        ),
    )
    signed_registry = _sign(
        payload=registry_payload,
        private_key=issuer_private_key,
        wrapper=EvidenceSelectionExpertPilotSignedReviewerRegistry,
        issuer_key_id="issuer-key-synthetic-root",
    )
    registry_path = tmp_path / "reviewer-registry.json"
    _write_model(registry_path, signed_registry)
    registry = load_and_verify_reviewer_registry(
        path=registry_path,
        issuer_public_key_hex=issuer_private_key.public_key().public_bytes_raw().hex(),
        issuer_key_id="issuer-key-synthetic-root",
        loaded_pilot=loaded_pilot,
        evaluation_protocol_sha256=evaluation_sha,
        publication_manifest_sha256=publication.manifest_sha256,
    )
    model_runs = load_registered_model_runs(
        protocol=evaluation_protocol,
        repository_root=Path.cwd(),
    )
    candidate_run_one = next(
        run for run in model_runs if run.reference.run_id == "candidate-run-1"
    )
    desired_labels = {
        result.record_id: (
            result.prediction_decision
            if result.prediction_decision in {"select", "reject"}
            else "reject"
        )
        for result in candidate_run_one.evaluation.record_results
    }
    disagreement_record = next(iter(desired_labels)) if disagreement else None
    completion_dir = tmp_path / "first-pass-completions"
    completion_dir.mkdir()
    for bundle_index, bundle in enumerate(
        publication.bundles_by_packet_id.values(),
        start=1,
    ):
        packet = bundle.reviewer_packet
        credential = registry.credentials_by_slot[packet.reviewer_slot]
        findings = []
        for candidate, binding in zip(
            packet.candidates,
            bundle.machine_sidecar.candidate_bindings,
            strict=True,
        ):
            label = desired_labels[binding.record_id]
            if (
                binding.record_id == disagreement_record
                and packet.reviewer_slot
                == loaded_pilot.protocol.independent_reviewer_slots[1]
            ):
                label = "reject" if label == "select" else "select"
            findings.append(
                EvidenceSelectionExpertPilotReviewFinding(
                    candidate_id=candidate.candidate_id,
                    selection_label=label,
                    packet_sufficiency="sufficient",
                    supporting_spans=(candidate.title,),
                    reviewer_explanation=(
                        "Synthetic test finding exercises the signed categorical path."
                    ),
                )
            )
        payload = EvidenceSelectionExpertPilotReviewCompletionPayload(
            schema_version="evidence_selection_expert_pilot_review_completion.v1",
            study_id=packet.study_id,
            packet_id=packet.packet_id,
            reviewer_slot=packet.reviewer_slot,
            review_case_id=packet.review_case_id,
            reviewer_id=credential.reviewer_id,
            reviewer_packet_sha256=bundle.machine_sidecar.reviewer_packet_sha256,
            evaluation_protocol_sha256=evaluation_sha,
            completed_at=evaluation_protocol.registered_at
            + timedelta(minutes=bundle_index),
            findings=tuple(findings),
        )
        signed = _sign(
            payload=payload,
            private_key=reviewer_keys[packet.reviewer_slot],
            wrapper=EvidenceSelectionExpertPilotSignedReviewCompletion,
            reviewer_key_id=credential.key_id,
        )
        if forged_first_completion and bundle_index == 1:
            signed = signed.model_copy(update={"signature_hex": "0" * 128})
        _write_model(completion_dir / f"{packet.packet_id}.json", signed)
    completions = load_and_verify_first_pass_completions(
        directory=completion_dir,
        publication=publication,
        registry=registry,
        evaluation_protocol=evaluation_protocol,
        evaluation_protocol_sha256=evaluation_sha,
    )
    prepared = prepare_expert_pilot_adjudication(
        loaded_pilot=loaded_pilot,
        evaluation_protocol_sha256=evaluation_sha,
        registry=registry,
        completions=completions,
    )
    return _SyntheticFirstPass(
        loaded_pilot=loaded_pilot,
        evaluation_protocol=evaluation_protocol,
        evaluation_protocol_sha256=evaluation_sha,
        publication=publication,
        registry=registry,
        completions=completions,
        prepared=prepared,
        reviewer_private_keys=reviewer_keys,
        desired_labels=desired_labels,
        publication_dir=publication_dir,
        registry_path=registry_path,
        completion_dir=completion_dir,
        issuer_public_key_hex=issuer_private_key.public_key().public_bytes_raw().hex(),
    )


def _complete_adjudication(
    *,
    tmp_path: Path,
    study: _SyntheticFirstPass,
    insufficient: bool = False,
) -> VerifiedExpertPilotAdjudication:
    findings = tuple(
        EvidenceSelectionExpertPilotAdjudicationFinding(
            adjudication_item_id=item.adjudication_item_id,
            selection_label=study.desired_labels[
                study.prepared.record_id_by_item_id[item.adjudication_item_id]
            ],
            packet_sufficiency="insufficient" if insufficient else "sufficient",
            supporting_spans=() if insufficient else (item.title,),
            reviewer_explanation="Synthetic third-reviewer test resolution.",
        )
        for item in study.prepared.request.items
    )
    path = _write_adjudication(tmp_path=tmp_path, study=study, findings=findings)
    adjudication = load_and_verify_adjudication_completion(
        path=path,
        prepared=study.prepared,
        registry=study.registry,
        loaded_pilot=study.loaded_pilot,
    )
    assert adjudication is not None
    return adjudication


def _write_adjudication(
    *,
    tmp_path: Path,
    study: _SyntheticFirstPass,
    findings: tuple[EvidenceSelectionExpertPilotAdjudicationFinding, ...],
) -> Path:
    slot = study.loaded_pilot.protocol.adjudicator_slot
    credential = study.registry.credentials_by_slot[slot]
    payload = EvidenceSelectionExpertPilotAdjudicationCompletionPayload(
        schema_version="evidence_selection_expert_pilot_adjudication_completion.v1",
        study_id=study.loaded_pilot.protocol.study_id,
        adjudicator_slot=slot,
        reviewer_id=credential.reviewer_id,
        adjudication_request_sha256=canonical_payload_sha256(study.prepared.request),
        completed_at=max(
            completion.signed_completion.payload.completed_at
            for completion in study.completions
        )
        + timedelta(minutes=1),
        findings=findings,
    )
    signed = _sign(
        payload=payload,
        private_key=study.reviewer_private_keys[slot],
        wrapper=EvidenceSelectionExpertPilotSignedAdjudicationCompletion,
        reviewer_key_id=credential.key_id,
    )
    path = tmp_path / "adjudication-completion.json"
    _write_model(path, signed)
    return path


def _gold(
    *,
    study: _SyntheticFirstPass,
    adjudication: VerifiedExpertPilotAdjudication | None,
) -> EvidenceSelectionExpertPilotGoldArtifact:
    return build_expert_pilot_gold(
        loaded_pilot=study.loaded_pilot,
        evaluation_protocol_sha256=study.evaluation_protocol_sha256,
        publication=study.publication,
        registry=study.registry,
        completions=study.completions,
        prepared=study.prepared,
        adjudication=adjudication,
    )


def _complete_safety(
    *,
    tmp_path: Path,
    study: _SyntheticFirstPass,
    gold: EvidenceSelectionExpertPilotGoldArtifact,
    prepared: PreparedExpertPilotSafetyAudit,
    adjudication: VerifiedExpertPilotAdjudication | None,
    assessment: SafetyAssessment = "supported",
):
    slot = study.loaded_pilot.protocol.adjudicator_slot
    credential = study.registry.credentials_by_slot[slot]
    payload = EvidenceSelectionExpertPilotSafetyCompletionPayload(
        schema_version="evidence_selection_expert_pilot_safety_completion.v1",
        study_id=study.loaded_pilot.protocol.study_id,
        safety_reviewer_slot=slot,
        reviewer_id=credential.reviewer_id,
        safety_request_sha256=canonical_payload_sha256(prepared.request),
        frozen_gold_sha256=canonical_payload_sha256(gold),
        completed_at=(
            adjudication.signed_completion.payload.completed_at
            if adjudication is not None
            else max(
                completion.signed_completion.payload.completed_at
                for completion in study.completions
            )
        )
        + timedelta(minutes=1),
        findings=tuple(
            EvidenceSelectionExpertPilotSafetyFinding(
                audit_item_id=item.audit_item_id,
                assessment=assessment,
                claim_spans=(),
                source_support_spans=(
                    (item.title,) if assessment == "supported" else ()
                ),
                reviewer_explanation="Synthetic source-supported safety finding.",
            )
            for item in prepared.request.items
        ),
    )
    signed = _sign(
        payload=payload,
        private_key=study.reviewer_private_keys[slot],
        wrapper=EvidenceSelectionExpertPilotSignedSafetyCompletion,
        reviewer_key_id=credential.key_id,
    )
    path = tmp_path / "safety-completion.json"
    _write_model(path, signed)
    return load_and_verify_safety_completion(
        path=path,
        prepared=prepared,
        registry=study.registry,
        loaded_pilot=study.loaded_pilot,
        earliest_time=(
            adjudication.signed_completion.payload.completed_at
            if adjudication is not None
            else max(
                completion.signed_completion.payload.completed_at
                for completion in study.completions
            )
        ),
    )


def _sign(
    *,
    payload: BaseModel,
    private_key: Ed25519PrivateKey,
    wrapper,
    **identity: str,
):
    return wrapper(
        payload=payload,
        signature_algorithm="ed25519",
        signature_hex=private_key.sign(canonical_payload_bytes(payload)).hex(),
        **identity,
    )


def _write_model(path: Path, model: BaseModel) -> None:
    path.write_text(model.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _load_import_script() -> ModuleType:
    module_name = "import_evidence_selection_expert_pilot_reviews"
    spec = importlib.util.spec_from_file_location(module_name, IMPORT_SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("unable to load expert-pilot import CLI")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
