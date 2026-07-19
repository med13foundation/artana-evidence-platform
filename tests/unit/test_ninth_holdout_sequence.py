"""V9-specific tests for sealed authorization and scientific replay."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimInventoryBindingRejection,
)
from artana_evidence_api.document_extraction_support.llm_extraction.attempt_audit import (
    ModelAttemptAuditRecord,
)
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    bind_prompt_to_invocation,
    kernel_run_id_for_invocation,
    output_schema_json_sha256,
)

from scripts.run_ninth_nested_event_holdout_trial import (
    main as ninth_main,
)
from scripts.run_ninth_nested_event_holdout_trial import (
    ninth_nested_holdout_exit_code,
)
from scripts.validation.claim_events.bionlp_import import TG04_BIONLP_ARCHIVE_SHA256
from scripts.validation.claim_events.finite_source_unit.contracts import (
    CandidateArgumentSemanticVerification,
    CandidateVerification,
    DirectionEncodingDecision,
    EntailmentDecision,
    EventStructureDecision,
    ProjectionEligibilityDecision,
    SemanticValidityDecision,
    SourceUnitCoverageDecision,
    SourceUnitDecision,
    SourceUnitEligibilityCategory,
    SourceUnitExtractionOutput,
    SourceUnitVerificationOutput,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial import (
    report as nested_report,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.report import (
    build_nested_holdout_report,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.selection import (
    NestedHoldoutSelection,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v9 import (
    sequence as ninth_sequence,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v9.projection import (
    ninth_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v9.qualification import (
    require_replayed_ninth_qualification,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v9.sequence import (
    NinthRepeatAuthorization,
    finalize_ninth_repeat,
    reserve_ninth_repeat,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    bind_source_unit_extraction,
    bind_source_unit_verification,
    canonical_source_unit_binding_repair_prompt,
    canonical_source_unit_extraction_prompt,
    canonical_source_unit_verification_prompt,
)
from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
    SingleUnitAgentRunEvidence,
    sha256_json,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    FrozenSourceUnit,
)
from tests.unit.test_eighth_holdout_sequence import _LiveVerifier
from tests.unit.test_nested_event_holdout_trial import (
    _V9_SOURCE,
    _V9_SOURCE_OFFSET,
    _v9_projection_inventory,
)

_UNIT_ID = (
    "source-unit-eb96c6e419821d8b930aebe6c1a891e185a0fcddccd3d05efa6ba05ef37601c0"
)
_SOURCE_SHA256 = "cac747e9b80090731f6e1e02e5e8ef70fc4254ae357de6ab2cd1835b3c5033ce"
_PROJECTION_SET_SHA256 = (
    "9163b0d185bdafdc093d158ec0a5b4da0e37d950904d998d822084d04f455915"
)
_SELECTION_SEED = "b1498772852d13333a1201ddaa02c55098fdcc183bee01ef9da0915faf0ceafd"


def test_ninth_reservation_freezes_v9_identity_and_is_create_once(
    tmp_path: Path,
) -> None:
    repository = _git_repository(tmp_path)
    output = tmp_path / "v9-repeat-1.json"
    authorization = reserve_ninth_repeat(
        repository_root=repository,
        run_id="tg04-v9-reservation",
        repeat_index=1,
        output=output,
        previous_report=None,
    )

    reservation = json.loads(authorization.reservation_path.read_text(encoding="utf-8"))
    assert reservation["schema_version"] == "tg04_v9_repeat_reservation.v1"
    assert reservation["selection_seed"] == _SELECTION_SEED
    assert reservation["projection_set_sha256"] == _PROJECTION_SET_SHA256
    assert reservation["unit_id"] == _UNIT_ID
    provider_identity = json.loads(authorization.provider_evidence_unit_id())
    assert provider_identity["schema_version"] == "tg04_v9_provider_reservation.v1"
    assert (
        provider_identity["repository_tree_oid"]
        == (authorization.repository_evidence["tracked_tree_oid"])
    )

    with pytest.raises(FileExistsError):
        reserve_ninth_repeat(
            repository_root=repository,
            run_id="tg04-v9-reservation",
            repeat_index=1,
            output=tmp_path / "different-output.json",
            previous_report=None,
        )


@pytest.mark.parametrize(
    ("field", "forged"),
    [
        ("schema_version", "forged-schema"),
        ("selection_seed", "forged-seed"),
        ("projection_set_sha256", "forged-projection"),
        ("unit_id", "forged-unit"),
    ],
)
def test_ninth_active_reservation_rejects_forged_frozen_identity(
    tmp_path: Path,
    field: str,
    forged: str,
) -> None:
    repository = _git_repository(tmp_path)
    authorization = reserve_ninth_repeat(
        repository_root=repository,
        run_id=f"tg04-v9-forged-{field}",
        repeat_index=1,
        output=tmp_path / f"{field}.json",
        previous_report=None,
    )
    reservation = json.loads(authorization.reservation_path.read_text(encoding="utf-8"))
    reservation[field] = forged
    authorization.reservation_path.write_text(
        json.dumps(reservation),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="authorization is not active"):
        authorization.require_active()


def test_ninth_real_replay_rejects_omitted_or_modified_orphan_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _complete_ninth_scientific_report(monkeypatch)

    require_replayed_ninth_qualification(report)

    for key, changed in (
        ("unlinked_controlled_event_references", None),
        ("unlinked_controlled_event_references", [{"forged": True}]),
        ("unlinked_controlled_target_ids", None),
        ("unlinked_controlled_target_ids", ["forged-target"]),
    ):
        tampered = dict(report)
        if changed is None:
            tampered.pop(key)
        else:
            tampered[key] = changed
        with pytest.raises(RuntimeError, match=f"nested holdout {key} differs"):
            require_replayed_ninth_qualification(tampered)


def test_ninth_repeat_finalizes_only_a_real_replayed_scientific_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _git_repository(tmp_path)
    output = tmp_path / "complete-v9-repeat.json"
    authorization = reserve_ninth_repeat(
        repository_root=repository,
        run_id="tg04-v9-complete",
        repeat_index=1,
        output=output,
        previous_report=None,
    )
    report = _complete_ninth_scientific_report(
        monkeypatch,
        authorization=authorization,
    )
    output.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(
        ninth_sequence.OpenAIProviderReceiptVerifier,
        "from_environment",
        lambda: _LiveVerifier(),
    )

    finalize_ninth_repeat(authorization, report=report)

    reservation = json.loads(authorization.reservation_path.read_text(encoding="utf-8"))
    assert reservation["status"] == "FINALIZED"
    assert reservation["gate_passed"] is True


def test_ninth_repeat_replays_and_finalizes_one_binding_repair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _git_repository(tmp_path)
    output = tmp_path / "repaired-v9-repeat.json"
    authorization = reserve_ninth_repeat(
        repository_root=repository,
        run_id="tg04-v9-binding-repair",
        repeat_index=1,
        output=output,
        previous_report=None,
    )
    report = _complete_ninth_scientific_report(
        monkeypatch,
        authorization=authorization,
        with_schema_repair=True,
    )
    output.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(
        ninth_sequence.OpenAIProviderReceiptVerifier,
        "from_environment",
        lambda: _LiveVerifier(),
    )

    require_replayed_ninth_qualification(report)
    finalize_ninth_repeat(authorization, report=report)

    assert report["provider_receipts"]["expected_count"] == 3  # type: ignore[index]
    assert report["gate"]["passed"] is True  # type: ignore[index]


def test_ninth_sequence_requires_both_orphan_zero_gates() -> None:
    requirements = ninth_sequence._DEFINITION.critical_gate_requirements

    assert "controlled_event_reference_orphan_zero" in requirements
    assert "controlled_event_target_orphan_zero" in requirements


def test_ninth_cli_exit_code_is_fail_closed() -> None:
    assert ninth_nested_holdout_exit_code({"gate": {"passed": True}}) == 0
    assert ninth_nested_holdout_exit_code({"gate": {"passed": False}}) == 1
    assert ninth_nested_holdout_exit_code({}) == 1


def test_ninth_cli_missing_archive_fails_before_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reservation_attempted = False

    def reserve_forbidden(**_kwargs: object) -> None:
        nonlocal reservation_attempted
        reservation_attempted = True

    monkeypatch.setattr(
        "scripts.run_ninth_nested_event_holdout_trial.reserve_ninth_repeat",
        reserve_forbidden,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_ninth_nested_event_holdout_trial.py",
            "--run-id",
            "missing-archive",
            "--repeat-index",
            "1",
            "--archive",
            str(tmp_path / "missing.tar.gz"),
            "--output",
            str(tmp_path / "reports" / "repeat-1.json"),
        ],
    )

    with pytest.raises(FileNotFoundError):
        ninth_main()

    assert reservation_attempted is False


def _complete_ninth_scientific_report(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authorization: NinthRepeatAuthorization | None = None,
    with_schema_repair: bool = False,
) -> dict[str, object]:
    unit = FrozenSourceUnit(
        unit_id=_UNIT_ID,
        index=7,
        source_start=_V9_SOURCE_OFFSET,
        source_end=_V9_SOURCE_OFFSET + len(_V9_SOURCE),
        text=_V9_SOURCE,
        source_sha256=_SOURCE_SHA256,
    )
    projection_set = ninth_projection_set()
    canonical_graph = projection_set.canonical_projection.graph
    selection = NestedHoldoutSelection(
        case_id="bionlp-ge-2011-holdout:PMID-8622948",
        unit=unit,
        expert_graph=canonical_graph,
        trial_generation=9,
        selection_seed=_SELECTION_SEED,
        selection_rule="test-reconstruction-of-frozen-v9",
        excluded_document_ids=(),
        selection_rank="2e832dd6",
        candidate_unit_count=4,
        holdout_document_count=219,
        incompatible_document_ids=(),
        archive_sha256=TG04_BIONLP_ARCHIVE_SHA256,
        expert_graph_sha256=sha256_json(canonical_graph.as_json()),
        authoritative_article_url="https://pubmed.ncbi.nlm.nih.gov/8622948/",
        projection_set=projection_set,
        projection_set_sha256=sha256_json(projection_set.as_json()),
        expected_eligibility_category=SourceUnitEligibilityCategory.MIXED_SCIENTIFIC,
    )
    prototype_candidates = _v9_projection_inventory()
    repaired_events = tuple(candidate.item for candidate in prototype_candidates)
    primary_events = repaired_events
    if with_schema_repair:
        repaired_first = repaired_events[0].model_copy(
            update={
                "exact_span": _V9_SOURCE[:113],
            }
        )
        repaired_events = (repaired_first, *repaired_events[1:])
        primary_first = repaired_first.model_copy(
            update={"exact_span": "not-in-source"}
        )
        primary_events = (primary_first, *repaired_events[1:])
    primary_extraction = SourceUnitExtractionOutput(
        eligibility_category=SourceUnitEligibilityCategory.MIXED_SCIENTIFIC,
        decision=SourceUnitDecision.EXPLICIT_EVENT,
        events=primary_events,
        reasoning="The source explicitly states the complete nested event family.",
    )
    extraction = primary_extraction.model_copy(update={"events": repaired_events})
    primary_binding = bind_source_unit_extraction(primary_extraction, unit=unit)
    candidates = bind_source_unit_extraction(extraction, unit=unit).accepted
    verification = SourceUnitVerificationOutput(
        eligibility_category=SourceUnitEligibilityCategory.MIXED_SCIENTIFIC,
        coverage_decision=SourceUnitCoverageDecision.CANDIDATES_COMPLETE,
        coverage_reasoning="Every source-explicit controller and target is present.",
        decisions=tuple(
            _entailed_verification(
                candidate.item.arguments,
                evidence_span=candidate.item.exact_span,
            )
            for candidate in candidates
        ),
    )
    verified = bind_source_unit_verification(
        verification,
        unit=unit,
        candidates=candidates,
    )
    from artana_evidence_api.document_extraction_support.claim_frames import (
        link_controlled_events,
    )

    links = link_controlled_events(candidates)
    evidence_unit_sha256 = (
        "a" * 64
        if authorization is None
        else hashlib.sha256(
            authorization.provider_evidence_unit_id().encode()
        ).hexdigest()
    )
    records = _attempt_records(
        unit=unit,
        candidates=candidates,
        extraction=extraction,
        primary_extraction=primary_extraction,
        primary_binding_errors=primary_binding.rejected,
        verification=verification,
        evidence_unit_sha256=evidence_unit_sha256,
    )
    agent_run = SingleUnitAgentRunEvidence(
        extraction=extraction,
        verification=verification,
        verified=verified,
        entailed=candidates,
        trusted=candidates,
        controlled_event_links=links.links,
        controlled_event_link_ambiguities=links.ambiguities,
        unlinked_controlled_event_references=links.unlinked_references,
        unlinked_controlled_target_ids=(),
        extracted_candidate_count=len(candidates),
        binding_rejection_count=0,
        observed_binding_rejections=primary_binding.rejected,
        unresolved_binding_rejections=(),
        schema_retry_count=int(with_schema_repair),
        records=records,
        error_type=None,
    )
    monkeypatch.setattr(
        nested_report.OpenAIProviderReceiptVerifier,
        "from_environment",
        lambda: _LiveVerifier(),
    )
    report = build_nested_holdout_report(
        selection=selection,
        run_id=(
            "tg04-v9-replay-test" if authorization is None else authorization.run_id
        ),
        repeat_index=1,
        configured_model_id="openai:gpt-5.6-luna",
        execution_model_id="openai/gpt-5.6-luna",
        repository_evidence=(
            {"clean": True}
            if authorization is None
            else authorization.repository_evidence
        ),
        agent_run=agent_run,
    )
    if authorization is not None:
        report.pop("report_sha256")
        report["repeat_authorization"] = {
            "run_id": authorization.run_id,
            "repeat_index": authorization.repeat_index,
            "token_sha256": hashlib.sha256(authorization.token.encode()).hexdigest(),
        }
        report["report_sha256"] = sha256_json(report)
    return report


def _entailed_verification(
    arguments: tuple[object, ...],
    *,
    evidence_span: str = _V9_SOURCE,
) -> CandidateVerification:
    return CandidateVerification(
        decision=EntailmentDecision.ENTAILED,
        structure_decision=EventStructureDecision.COMPLETE,
        direction_encoding=DirectionEncodingDecision.STRUCTURED,
        event_type_decision=SemanticValidityDecision.VALID,
        argument_semantic_decisions=tuple(
            CandidateArgumentSemanticVerification(
                type_decision=SemanticValidityDecision.VALID,
                event_role_decision=SemanticValidityDecision.VALID,
                reasoning="The source explicitly supports this typed role.",
            )
            for _ in arguments
        ),
        projection_eligibility=ProjectionEligibilityDecision.ELIGIBLE,
        evidence_spans=(evidence_span,),
        reasoning="The complete event is entailed by the frozen source.",
        falsification_condition="A required trigger, participant, or scope is absent.",
    )


def _attempt_records(
    *,
    unit: FrozenSourceUnit,
    candidates: tuple[object, ...],
    extraction: SourceUnitExtractionOutput,
    primary_extraction: SourceUnitExtractionOutput,
    primary_binding_errors: tuple[ClaimInventoryBindingRejection, ...],
    verification: SourceUnitVerificationOutput,
    evidence_unit_sha256: str,
) -> tuple[ModelAttemptAuditRecord, ...]:
    payloads = [primary_extraction.model_dump(mode="json")]
    prompts = [canonical_source_unit_extraction_prompt(unit)]
    schemas = [SourceUnitExtractionOutput]
    roles = ["primary"]
    pass_roles = ["primary"]
    if primary_binding_errors:
        payloads.append(extraction.model_dump(mode="json"))
        prompts.append(
            canonical_source_unit_binding_repair_prompt(
                unit=unit,
                rejected_output=primary_extraction,
                binding_errors=primary_binding_errors,
            )
        )
        schemas.append(SourceUnitExtractionOutput)
        roles.append("schema_retry")
        pass_roles.append("primary")
    payloads.append(verification.model_dump(mode="json"))
    prompts.append(
        canonical_source_unit_verification_prompt(unit=unit, candidates=candidates)
    )
    schemas.append(SourceUnitVerificationOutput)
    roles.append("weak_review")
    pass_roles.append("weak_review")
    records: list[ModelAttemptAuditRecord] = []
    for index, (role, pass_role, payload, prompt, schema) in enumerate(
        zip(roles, pass_roles, payloads, prompts, schemas, strict=True)
    ):
        invocation_id = f"v9-test-{role}"
        schema_sha256 = output_schema_json_sha256(schema)
        provider_prompt = bind_prompt_to_invocation(
            prompt=prompt,
            invocation_id=invocation_id,
            source_sha256=unit.source_sha256,
            input_sha256=unit.input_sha256,
            evidence_unit_sha256=evidence_unit_sha256,
            output_schema_sha256=schema_sha256,
        )
        records.append(
            ModelAttemptAuditRecord(
                invocation_id=invocation_id,
                attempt_role=role,
                pass_role=pass_role,
                retry_context=None,
                model_id="openai/gpt-5.6-luna",
                step_key=f"v9-test-{index}",
                prompt_sha256=hashlib.sha256(provider_prompt.encode()).hexdigest(),
                source_sha256=unit.source_sha256,
                input_sha256=unit.input_sha256,
                evidence_unit_sha256=evidence_unit_sha256,
                semantic_unit_id=unit.unit_id,
                output_schema_identity=f"{schema.__module__}.{schema.__qualname__}",
                provider_execution_response_id=f"resp_v9_test_{index}",
                provider_response_id=f"resp_v9_test_{index}",
                provider_output_sha256=f"provider-output-{index}",
                kernel_run_id=kernel_run_id_for_invocation(invocation_id),
                kernel_event_seq=index + 1,
                replayed=False,
                raw_model_payload_json=json.dumps(payload, sort_keys=True),
                payload_sha256=sha256_json(payload),
                validation_outcome="accepted",
                error_type=None,
            )
        )
    return tuple(records)


def _git_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(("git", "init", "-q", str(repository)), check=True)
    subprocess.run(
        ("git", "-C", str(repository), "config", "user.email", "test@example.com"),
        check=True,
    )
    subprocess.run(
        ("git", "-C", str(repository), "config", "user.name", "Artana Test"),
        check=True,
    )
    (repository / "tracked.txt").write_text("sealed\n", encoding="utf-8")
    subprocess.run(("git", "-C", str(repository), "add", "tracked.txt"), check=True)
    subprocess.run(
        ("git", "-C", str(repository), "commit", "-q", "-m", "seal test tree"),
        check=True,
    )
    return repository
