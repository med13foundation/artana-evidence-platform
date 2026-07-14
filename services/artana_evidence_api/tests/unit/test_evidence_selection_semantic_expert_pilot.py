"""Regression coverage for the blinded semantic expert-pilot boundary."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2 import (
    build_expert_pilot_packet_bundles,
    load_expert_pilot,
    pilot_publication,
    verify_expert_pilot_packet_bundle,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.pilot_contracts import (
    EvidenceSelectionExpertPilotCandidate,
    EvidenceSelectionExpertPilotMachineSidecar,
    EvidenceSelectionExpertPilotProtocol,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.pilot_packets import (
    EvidenceSelectionExpertPilotPacketBundle,
)
from pydantic import ValidationError

PROTOCOL_PATH = Path(
    "scripts/validation/evidence_selection/fixtures/"
    "semantic_relevance_expert_pilot_protocol_v1.json"
)
SIGNING_KEY_ENV = "ARTANA_EVIDENCE_SHADOW_REVIEW_PACKET_SIGNING_KEY"


def test_protocol_binds_complete_diagnostic_pilot_inventory() -> None:
    loaded = load_expert_pilot(
        protocol_path=PROTOCOL_PATH,
        repository_root=Path.cwd(),
    )

    assert loaded.protocol.study_tier == "diagnostic_pilot"
    assert loaded.protocol.production_readiness_claim is False
    assert loaded.protocol.production_calibration_claim is False
    assert loaded.protocol.expected_record_count == 33
    assert loaded.protocol.diagnostic_pilot_question_count == 3
    assert loaded.protocol.production_calibration_minimum_question_count == 20
    assert loaded.protocol.production_calibration_minimum_record_count == 200
    assert (
        loaded.protocol.acceptance_thresholds.metric_origin
        == "deterministic_from_categorical_human_findings"
    )
    assert len(loaded.supplements_by_record) == 33
    assert len(
        {
            supplement.source_record_id
            for supplement in loaded.supplements_by_record.values()
        }
    ) == 29
    assert all(loaded.supplement_sha256_by_record.values())


def test_reviewer_packets_are_blinded_and_independently_ordered(monkeypatch) -> None:
    monkeypatch.setenv(SIGNING_KEY_ENV, "unit-test-producer-key")
    loaded = load_expert_pilot(
        protocol_path=PROTOCOL_PATH,
        repository_root=Path.cwd(),
    )

    bundles = build_expert_pilot_packet_bundles(loaded)
    historical_case_ids = {
        case.case_id for case in loaded.benchmark.historical_v1.cases
    }

    assert len(bundles) == 8
    assert sum(len(bundle.reviewer_packet.candidates) for bundle in bundles) == 66
    for bundle in bundles:
        verify_expert_pilot_packet_bundle(bundle)
        parsed_packet = type(bundle.reviewer_packet).model_validate_json(
            bundle.reviewer_packet.model_dump_json()
        )
        parsed_sidecar = type(bundle.machine_sidecar).model_validate_json(
            bundle.machine_sidecar.model_dump_json()
        )
        verify_expert_pilot_packet_bundle(
            EvidenceSelectionExpertPilotPacketBundle(
                reviewer_packet=parsed_packet,
                machine_sidecar=parsed_sidecar,
            )
        )
        payload = bundle.reviewer_packet.model_dump(mode="json")
        serialized_packet = json.dumps(payload, sort_keys=True)
        assert not any(
            case_id in serialized_packet for case_id in historical_case_ids
        )
        assert not _keys(payload).intersection(
            {
                "decision",
                "expected_label",
                "harness_selected_record_ids",
                "operational_ranking",
                "calibrated_probability",
                "model_id",
                "diagnostic_decision",
            }
        )
    first_case = [
        bundle
        for bundle in bundles
        if bundle.machine_sidecar.case_id == "egfr_t790m_primary_evidence"
    ]
    assert len(first_case) == 2
    assert (
        first_case[0].reviewer_packet.review_case_id
        != first_case[1].reviewer_packet.review_case_id
    )
    assert _source_order(first_case[0]) != _source_order(first_case[1])


def test_all_records_use_frozen_pubmed_source_snapshots(monkeypatch) -> None:
    monkeypatch.setenv(SIGNING_KEY_ENV, "unit-test-producer-key")
    loaded = load_expert_pilot(
        protocol_path=PROTOCOL_PATH,
        repository_root=Path.cwd(),
    )
    bundles = build_expert_pilot_packet_bundles(loaded)

    sections_by_record: dict[str, tuple[str, ...]] = {}
    text_by_record: dict[str, str] = {}
    title_by_record: dict[str, str] = {}
    for bundle in bundles:
        for candidate, binding in zip(
            bundle.reviewer_packet.candidates,
            bundle.machine_sidecar.candidate_bindings,
            strict=True,
        ):
            sections_by_record[binding.record_id] = tuple(
                section.section for section in candidate.bounded_source_text
            )
            text_by_record[binding.record_id] = candidate.bounded_source_text[0].text
            title_by_record[binding.record_id] = candidate.title
            assert binding.supplement_sha256 is not None

    assert set(sections_by_record.values()) == {("SOURCE_TEXT",)}
    for record_id, supplement in loaded.supplements_by_record.items():
        assert text_by_record[record_id] == "\n\n".join(
            section.text for section in supplement.abstract_sections
        )
        assert title_by_record[record_id] == supplement.title


def test_reviewer_packet_cannot_arrive_with_prefilled_judgments() -> None:
    with pytest.raises(ValidationError):
        EvidenceSelectionExpertPilotCandidate(
            candidate_id="candidate-0123456789abcdef",
            source_key="pubmed",
            source_record_id="123",
            source_url="https://pubmed.ncbi.nlm.nih.gov/123/",
            title="Source title",
            bounded_source_text=[
                {"section": "ABSTRACT", "text": "Bounded source text."}
            ],
            selection_label="select",  # type: ignore[arg-type]
        )


def test_reviewer_narrative_leakage_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv(SIGNING_KEY_ENV, "unit-test-producer-key")
    loaded = load_expert_pilot(
        protocol_path=PROTOCOL_PATH,
        repository_root=Path.cwd(),
    )
    cases = loaded.benchmark.historical_v1.cases
    tainted_case = cases[-1].model_copy(
        update={"instructions": "This canary has expected_label=reject."}
    )
    tainted_fixture = loaded.benchmark.historical_v1.model_copy(
        update={"cases": (*cases[:-1], tainted_case)}
    )
    tainted_benchmark = replace(
        loaded.benchmark,
        historical_v1=tainted_fixture,
    )

    with pytest.raises(ValueError, match="reviewer narrative leaks blinded context"):
        build_expert_pilot_packet_bundles(
            replace(loaded, benchmark=tainted_benchmark)
        )


def test_protocol_rejects_readiness_numeric_or_agent_judgment_drift() -> None:
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["production_readiness_claim"] = True
    with pytest.raises(ValidationError, match="production_readiness_claim"):
        EvidenceSelectionExpertPilotProtocol.model_validate(payload)

    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["reviewer_confidence_scale"] = [1, 2, 3, 4, 5]
    with pytest.raises(ValidationError, match="reviewer_confidence_scale"):
        EvidenceSelectionExpertPilotProtocol.model_validate(payload)

    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["acceptance_thresholds"]["minimum_adjudicated_precision"] = 0.79
    with pytest.raises(ValidationError, match="thresholds are frozen"):
        EvidenceSelectionExpertPilotProtocol.model_validate(payload)


def test_missing_benchmark_source_snapshot_fails_closed(tmp_path: Path) -> None:
    protocol_path = _copy_pilot_inputs(tmp_path)
    manifest_path = tmp_path / _supplement_manifest_path(protocol_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["supplements"] = manifest["supplements"][1:]
    _write_json(manifest_path, manifest)
    _rebind_protocol_manifest(protocol_path=protocol_path, manifest_path=manifest_path)

    with pytest.raises(ValueError, match="exactly cover every benchmark source"):
        load_expert_pilot(protocol_path=protocol_path, repository_root=tmp_path)


def test_supplement_identity_drift_fails_closed(tmp_path: Path) -> None:
    protocol_path = _copy_pilot_inputs(tmp_path)
    manifest_path = tmp_path / _supplement_manifest_path(protocol_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_ref = manifest["supplements"][0]
    source_path = tmp_path / source_ref["path"]
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["source_record_id"] = "99999999"
    source["source_url"] = "https://pubmed.ncbi.nlm.nih.gov/99999999/"
    _write_json(source_path, source)
    source_ref["sha256"] = _sha256(source_path)
    _write_json(manifest_path, manifest)
    _rebind_protocol_manifest(protocol_path=protocol_path, manifest_path=manifest_path)

    with pytest.raises(ValueError, match="supplement source identity mismatch"):
        load_expert_pilot(protocol_path=protocol_path, repository_root=tmp_path)


def test_supplement_url_identity_drift_fails_closed(tmp_path: Path) -> None:
    protocol_path = _copy_pilot_inputs(tmp_path)
    manifest_path = tmp_path / _supplement_manifest_path(protocol_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_ref = manifest["supplements"][0]
    source_path = tmp_path / source_ref["path"]
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["source_url"] = "https://pubmed.ncbi.nlm.nih.gov/99999999/"
    _write_json(source_path, source)
    source_ref["sha256"] = _sha256(source_path)
    _write_json(manifest_path, manifest)
    _rebind_protocol_manifest(protocol_path=protocol_path, manifest_path=manifest_path)

    with pytest.raises(ValidationError, match="URL must match source_record_id"):
        load_expert_pilot(protocol_path=protocol_path, repository_root=tmp_path)


def test_packet_and_mapping_tampering_fail_signature_verification(monkeypatch) -> None:
    monkeypatch.setenv(SIGNING_KEY_ENV, "unit-test-producer-key")
    loaded = load_expert_pilot(
        protocol_path=PROTOCOL_PATH,
        repository_root=Path.cwd(),
    )
    bundle = build_expert_pilot_packet_bundles(loaded)[0]
    candidate = bundle.reviewer_packet.candidates[0]
    tampered_candidate = candidate.model_copy(update={"title": "Tampered title"})
    tampered_packet = bundle.reviewer_packet.model_copy(
        update={
            "candidates": (
                tampered_candidate,
                *bundle.reviewer_packet.candidates[1:],
            )
        }
    )
    with pytest.raises(ValueError, match="packet digest mismatch"):
        verify_expert_pilot_packet_bundle(
            EvidenceSelectionExpertPilotPacketBundle(
                reviewer_packet=tampered_packet,
                machine_sidecar=bundle.machine_sidecar,
            )
        )

    first_binding = bundle.machine_sidecar.candidate_bindings[0]
    tampered_binding = first_binding.model_copy(update={"record_id": "forged-record"})
    sidecar_payload = bundle.machine_sidecar.model_dump()
    sidecar_payload["candidate_bindings"] = (
        tampered_binding,
        *bundle.machine_sidecar.candidate_bindings[1:],
    )
    tampered_sidecar = EvidenceSelectionExpertPilotMachineSidecar.model_validate(
        sidecar_payload
    )
    with pytest.raises(ValueError, match="signature"):
        verify_expert_pilot_packet_bundle(
            EvidenceSelectionExpertPilotPacketBundle(
                reviewer_packet=bundle.reviewer_packet,
                machine_sidecar=tampered_sidecar,
            )
        )


def test_packet_publication_failure_leaves_no_partial_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(SIGNING_KEY_ENV, "unit-test-producer-key")
    loaded = load_expert_pilot(
        protocol_path=PROTOCOL_PATH,
        repository_root=Path.cwd(),
    )
    original_write = pilot_publication._write_artifact
    write_count = 0

    def fail_second_write(**kwargs):
        nonlocal write_count
        write_count += 1
        if write_count == 2:
            raise OSError("simulated sidecar write failure")
        return original_write(**kwargs)

    monkeypatch.setattr(pilot_publication, "_write_artifact", fail_second_write)
    output_dir = tmp_path / "expert-pilot"

    with pytest.raises(OSError, match="simulated sidecar"):
        pilot_publication.publish_expert_pilot_packets(
            loaded=loaded,
            output_dir=output_dir,
        )

    assert not output_dir.exists()
    assert not list(tmp_path.glob(".expert-pilot.staging-*"))


def test_packet_publication_verifies_bundle_before_exposure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(SIGNING_KEY_ENV, "unit-test-producer-key")
    loaded = load_expert_pilot(
        protocol_path=PROTOCOL_PATH,
        repository_root=Path.cwd(),
    )
    bundle = build_expert_pilot_packet_bundles(loaded)[0]
    tampered_packet = bundle.reviewer_packet.model_copy(
        update={"instructions": "Tampered instructions"}
    )
    tampered_bundle = EvidenceSelectionExpertPilotPacketBundle(
        reviewer_packet=tampered_packet,
        machine_sidecar=bundle.machine_sidecar,
    )
    monkeypatch.setattr(
        pilot_publication,
        "build_expert_pilot_packet_bundles",
        lambda _loaded: (tampered_bundle,),
    )
    output_dir = tmp_path / "expert-pilot"

    with pytest.raises(ValueError, match="packet digest mismatch"):
        pilot_publication.publish_expert_pilot_packets(
            loaded=loaded,
            output_dir=output_dir,
        )

    assert not output_dir.exists()
    assert not list(tmp_path.glob(".expert-pilot.staging-*"))


def test_packet_publication_does_not_replace_racing_destination(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(SIGNING_KEY_ENV, "unit-test-producer-key")
    loaded = load_expert_pilot(
        protocol_path=PROTOCOL_PATH,
        repository_root=Path.cwd(),
    )
    original_publish = pilot_publication._publish_directory_no_replace

    def race_destination(*, staging: Path, destination: Path) -> None:
        destination.mkdir()
        original_publish(staging=staging, destination=destination)

    monkeypatch.setattr(
        pilot_publication,
        "_publish_directory_no_replace",
        race_destination,
    )
    output_dir = tmp_path / "expert-pilot"

    with pytest.raises(FileExistsError):
        pilot_publication.publish_expert_pilot_packets(
            loaded=loaded,
            output_dir=output_dir,
        )

    assert output_dir.is_dir()
    assert not list(output_dir.iterdir())
    assert not list(tmp_path.glob(".expert-pilot.staging-*"))


def _source_order(bundle: EvidenceSelectionExpertPilotPacketBundle) -> tuple[str, ...]:
    return tuple(
        candidate.source_record_id for candidate in bundle.reviewer_packet.candidates
    )


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_keys(item) for item in value), set())
    return set()


def _copy_pilot_inputs(root: Path) -> Path:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    benchmark_path = Path(protocol["benchmark_fixture"]["path"])
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    v1_path = Path(benchmark["historical_v1"]["path"])
    packet_manifest_path = Path(benchmark["source_packet_manifest"]["path"])
    packet_manifest = json.loads(packet_manifest_path.read_text(encoding="utf-8"))
    supplement_manifest_path = Path(protocol["supplement_manifest"]["path"])
    supplement_manifest = json.loads(
        supplement_manifest_path.read_text(encoding="utf-8")
    )
    paths = [
        PROTOCOL_PATH,
        benchmark_path,
        v1_path,
        packet_manifest_path,
        *(Path(item["path"]) for item in packet_manifest["packets"]),
        supplement_manifest_path,
        *(Path(item["path"]) for item in supplement_manifest["supplements"]),
    ]
    for source in paths:
        destination = root / source
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return root / PROTOCOL_PATH


def _supplement_manifest_path(protocol_path: Path) -> Path:
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    return Path(protocol["supplement_manifest"]["path"])


def _rebind_protocol_manifest(*, protocol_path: Path, manifest_path: Path) -> None:
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    protocol["supplement_manifest"]["sha256"] = _sha256(manifest_path)
    _write_json(protocol_path, protocol)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
