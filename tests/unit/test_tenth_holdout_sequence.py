"""V10 authorization and deterministic scientific replay tests."""

from __future__ import annotations

import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from threading import Barrier

import pytest
from artana_evidence_api.document_extraction_support.claim_frames import (
    BoundClaimInventoryItem,
    link_controlled_events,
)
from artana_evidence_api.document_extraction_support.llm_extraction.attempt_audit import (
    ModelAttemptAuditRecord,
)
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    bind_prompt_to_invocation,
    kernel_run_id_for_invocation,
    output_schema_json_sha256,
)

from scripts.run_tenth_nested_event_holdout_trial import (
    tenth_nested_holdout_exit_code,
)
from scripts.validation.claim_events.bionlp_import import TG04_BIONLP_ARCHIVE_SHA256
from scripts.validation.claim_events.finite_source_unit.contracts import (
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
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v10 import (
    prompts as tenth_prompts,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v10 import (
    sequence as tenth_sequence,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v10.projection import (
    tenth_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v10.prompts import (
    v10_source_unit_extraction_prompt,
    v10_source_unit_verification_prompt,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v10.qualification import (
    TENTH_ARCHIVE_SHA256,
    TENTH_EXPERT_GRAPH_SHA256,
    TENTH_PROJECTION_SET_SHA256,
    TENTH_PROMPT_DIGESTS,
    TENTH_SOURCE_IDENTITY,
    require_replayed_tenth_qualification,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v10.sequence import (
    TenthRepeatAuthorization,
    finalize_tenth_repeat,
    reserve_tenth_repeat,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    bind_source_unit_extraction,
    bind_source_unit_verification,
)
from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
    SingleUnitAgentRunEvidence,
    sha256_json,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    FrozenSourceUnit,
)
from tests.unit.test_eighth_holdout_sequence import _LiveVerifier
from tests.unit.test_ninth_holdout_sequence import _entailed_verification
from tests.unit.test_tenth_nested_event_holdout import (
    _SOURCE,
    _SOURCE_START,
    _nested_inventory,
)

_UNIT_ID = (
    "source-unit-463bf8e1b37963d7547eb57c6d51545a466050b2c6c9faa9abc76ff8e2330914"
)
_SOURCE_SHA256 = "d452cea84a786851d0d5686c5acab618745b4b8ccaf09cc6fa638a48b370a17a"
_SELECTION_SEED = "59107ff0d23bf9543b23df2add9885d0bab4c7dd0c38ffbd18e030734cc2c897"


def test_tenth_reservation_freezes_identity_and_is_create_once(tmp_path: Path) -> None:
    repository = _git_repository(tmp_path)
    authorization = reserve_tenth_repeat(
        repository_root=repository,
        run_id="tg04-v10-reservation",
        repeat_index=1,
        output=tmp_path / "repeat-1.json",
        previous_report=None,
    )

    reservation = json.loads(authorization.reservation_path.read_text())
    assert reservation["schema_version"] == "tg04_v10_repeat_reservation.v2"
    assert reservation["selection_seed"] == _SELECTION_SEED
    assert reservation["projection_set_sha256"] == TENTH_PROJECTION_SET_SHA256
    assert reservation["unit_id"] == _UNIT_ID
    assert reservation["archive_sha256"] == TENTH_ARCHIVE_SHA256
    assert reservation["expert_graph_sha256"] == TENTH_EXPERT_GRAPH_SHA256
    assert reservation["source_identity"] == dict(TENTH_SOURCE_IDENTITY)
    assert reservation["prompt_digests"] == dict(TENTH_PROMPT_DIGESTS)

    provider_identity = json.loads(authorization.provider_evidence_unit_id())
    assert provider_identity["schema_version"] == "tg04_v10_provider_reservation.v2"
    assert provider_identity["archive_sha256"] == TENTH_ARCHIVE_SHA256
    assert provider_identity["expert_graph_sha256"] == TENTH_EXPERT_GRAPH_SHA256
    assert provider_identity["source_identity"] == dict(TENTH_SOURCE_IDENTITY)
    assert provider_identity["prompt_digests"] == dict(TENTH_PROMPT_DIGESTS)
    assert isinstance(provider_identity["execution_lease_sha256"], str)
    executing = json.loads(authorization.reservation_path.read_text())
    assert executing["status"] == "EXECUTING"
    assert (
        executing["execution_lease_sha256"]
        == (provider_identity["execution_lease_sha256"])
    )

    with pytest.raises(FileExistsError):
        reserve_tenth_repeat(
            repository_root=repository,
            run_id="tg04-v10-reservation",
            repeat_index=1,
            output=tmp_path / "other.json",
            previous_report=None,
        )


def test_tenth_execution_lease_is_consumed_after_one_provider_binding(
    tmp_path: Path,
) -> None:
    repository = _git_repository(tmp_path)
    authorization = reserve_tenth_repeat(
        repository_root=repository,
        run_id="tg04-v10-single-provider-use",
        repeat_index=1,
        output=tmp_path / "repeat-1.json",
        previous_report=None,
    )

    authorization.provider_evidence_unit_id()

    with pytest.raises(RuntimeError, match="execution lease is already consumed"):
        authorization.provider_evidence_unit_id()
    reservation = json.loads(authorization.reservation_path.read_text())
    assert reservation["status"] == "EXECUTING"


def test_tenth_execution_lease_crash_window_remains_consumed(tmp_path: Path) -> None:
    repository = _git_repository(tmp_path)
    authorization = reserve_tenth_repeat(
        repository_root=repository,
        run_id="tg04-v10-consumed-crash-window",
        repeat_index=1,
        output=tmp_path / "repeat-1.json",
        previous_report=None,
    )
    authorization.provider_evidence_unit_id()
    reservation = json.loads(authorization.reservation_path.read_text())
    reservation["status"] = "RESERVED"
    reservation.pop("execution_lease_sha256")
    authorization.reservation_path.write_text(
        json.dumps(reservation),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="execution lease is already consumed"):
        authorization.require_active()


def test_tenth_execution_lease_rejects_concurrent_second_claim(
    tmp_path: Path,
) -> None:
    repository = _git_repository(tmp_path)
    authorization = reserve_tenth_repeat(
        repository_root=repository,
        run_id="tg04-v10-concurrent-provider-use",
        repeat_index=1,
        output=tmp_path / "repeat-1.json",
        previous_report=None,
    )
    barrier = Barrier(2)

    def claim() -> str:
        barrier.wait()
        try:
            return authorization.provider_evidence_unit_id()
        except RuntimeError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (executor.submit(claim), executor.submit(claim))
        outcomes = tuple(future.result() for future in futures)

    assert sum(outcome.startswith("{") for outcome in outcomes) == 1
    assert (
        sum("execution lease is already consumed" in outcome for outcome in outcomes)
        == 1
    )
    reservation = json.loads(authorization.reservation_path.read_text())
    assert reservation["status"] == "EXECUTING"


def test_tenth_finalization_requires_consumed_execution_lease(tmp_path: Path) -> None:
    repository = _git_repository(tmp_path)
    authorization = reserve_tenth_repeat(
        repository_root=repository,
        run_id="tg04-v10-unclaimed-finalization",
        repeat_index=1,
        output=tmp_path / "repeat-1.json",
        previous_report=None,
    )

    with pytest.raises(RuntimeError, match="execution has not been claimed"):
        finalize_tenth_repeat(authorization, report={})


def test_tenth_complete_report_replays_and_tampering_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _complete_tenth_report(monkeypatch)

    require_replayed_tenth_qualification(report)
    gate = report["gate"]
    assert isinstance(gate, dict)
    assert gate["passed"] is True

    tampered = dict(report)
    tampered["controlled_event_links"] = []
    with pytest.raises(RuntimeError, match="controlled_event_links differs"):
        require_replayed_tenth_qualification(tampered)


def test_tenth_finalization_requires_real_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _git_repository(tmp_path)
    authorization = reserve_tenth_repeat(
        repository_root=repository,
        run_id="tg04-v10-complete",
        repeat_index=1,
        output=tmp_path / "complete.json",
        previous_report=None,
    )
    report = _complete_tenth_report(monkeypatch, authorization=authorization)
    authorization.output.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(
        tenth_sequence.OpenAIProviderReceiptVerifier,
        "from_environment",
        lambda: _LiveVerifier(),
    )

    finalize_tenth_repeat(authorization, report=report)

    reservation = json.loads(authorization.reservation_path.read_text())
    assert reservation["status"] == "FINALIZED"
    assert reservation["gate_passed"] is True


def test_tenth_later_repeat_replays_finalized_execution_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _git_repository(tmp_path)
    first = reserve_tenth_repeat(
        repository_root=repository,
        run_id="tg04-v10-sequence",
        repeat_index=1,
        output=tmp_path / "repeat-1.json",
        previous_report=None,
    )
    first_report = _complete_tenth_report(monkeypatch, authorization=first)
    first.output.write_text(json.dumps(first_report), encoding="utf-8")
    monkeypatch.setattr(
        tenth_sequence.OpenAIProviderReceiptVerifier,
        "from_environment",
        lambda: _LiveVerifier(),
    )
    finalize_tenth_repeat(first, report=first_report)

    second = reserve_tenth_repeat(
        repository_root=repository,
        run_id="tg04-v10-sequence",
        repeat_index=2,
        output=tmp_path / "repeat-2.json",
        previous_report=first.output,
    )

    reservation = json.loads(second.reservation_path.read_text())
    assert reservation["status"] == "RESERVED"
    assert reservation["previous_report_sha256"] == first_report["report_sha256"]


@pytest.mark.parametrize(
    ("section", "field", "replacement"),
    [
        ("source_corpus", "archive_sha256", "0" * 64),
        ("source_corpus", "expert_graph_sha256", "1" * 64),
        ("unit", "case_id", "tampered-case"),
        ("unit", "unit_id", "source-unit-tampered"),
        ("unit", "unit_index", 99),
        ("unit", "source_start", 0),
        ("unit", "source_end", 1),
        ("unit", "source_sha256", "2" * 64),
        ("unit", "input_sha256", "3" * 64),
    ],
)
def test_tenth_finalization_rejects_lineage_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    section: str,
    field: str,
    replacement: object,
) -> None:
    repository = _git_repository(tmp_path)
    authorization = reserve_tenth_repeat(
        repository_root=repository,
        run_id=f"tg04-v10-lineage-{section}-{field}",
        repeat_index=1,
        output=tmp_path / "lineage.json",
        previous_report=None,
    )
    report = _complete_tenth_report(monkeypatch, authorization=authorization)
    tampered = deepcopy(report)
    container = tampered[section]
    assert isinstance(container, dict)
    container[field] = replacement
    _resign_report(tampered)
    authorization.output.write_text(json.dumps(tampered), encoding="utf-8")
    monkeypatch.setattr(
        tenth_sequence.OpenAIProviderReceiptVerifier,
        "from_environment",
        lambda: _LiveVerifier(),
    )

    with pytest.raises(RuntimeError, match="identity"):
        finalize_tenth_repeat(authorization, report=tampered)


@pytest.mark.parametrize(
    "policy_name",
    ["_EXTRACTION_POLICY", "_VERIFICATION_POLICY"],
)
def test_tenth_replay_rejects_prompt_policy_text_drift(
    monkeypatch: pytest.MonkeyPatch,
    policy_name: str,
) -> None:
    report = _complete_tenth_report(monkeypatch)
    original = getattr(tenth_prompts, policy_name)
    monkeypatch.setattr(tenth_prompts, policy_name, f"{original}\nUNREGISTERED DRIFT")

    with pytest.raises(RuntimeError, match="prompt policy identity changed"):
        require_replayed_tenth_qualification(report)


def test_tenth_replay_rejects_scientific_contract_code_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _complete_tenth_report(monkeypatch)
    projection_set = tenth_projection_set()
    canonical = projection_set.canonical_projection
    drifted_graph = replace(canonical.graph, links=())
    drifted_canonical = replace(canonical, graph=drifted_graph)
    drifted_set = replace(
        projection_set,
        projections=(drifted_canonical, *projection_set.projections[1:]),
    )
    monkeypatch.setattr(
        "scripts.validation.claim_events.finite_source_unit.nested_holdout_trial."
        "v10.qualification.tenth_projection_set",
        lambda: drifted_set,
    )

    with pytest.raises(RuntimeError, match="scientific contract identity changed"):
        require_replayed_tenth_qualification(report)


def test_tenth_active_reservation_rejects_prompt_digest_mutation(
    tmp_path: Path,
) -> None:
    repository = _git_repository(tmp_path)
    authorization = reserve_tenth_repeat(
        repository_root=repository,
        run_id="tg04-v10-prompt-digest-tamper",
        repeat_index=1,
        output=tmp_path / "repeat-1.json",
        previous_report=None,
    )
    reservation = json.loads(authorization.reservation_path.read_text())
    prompt_digests = reservation["prompt_digests"]
    assert isinstance(prompt_digests, dict)
    prompt_digests["extraction_prompt_sha256"] = "0" * 64
    authorization.reservation_path.write_text(
        json.dumps(reservation),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="authorization is not active"):
        authorization.require_active()


def test_tenth_finalization_rejects_execution_lease_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _git_repository(tmp_path)
    authorization = reserve_tenth_repeat(
        repository_root=repository,
        run_id="tg04-v10-lease-tamper",
        repeat_index=1,
        output=tmp_path / "repeat-1.json",
        previous_report=None,
    )
    report = _complete_tenth_report(monkeypatch, authorization=authorization)
    authorization.output.write_text(json.dumps(report), encoding="utf-8")
    lease_path = authorization.reservation_path.with_name(
        f"{authorization.reservation_path.stem}.execution.json",
    )
    lease = json.loads(lease_path.read_text())
    lease["lease_sha256"] = "0" * 64
    lease_path.write_text(json.dumps(lease), encoding="utf-8")

    with pytest.raises(RuntimeError, match="execution lease is invalid"):
        finalize_tenth_repeat(authorization, report=report)


def test_tenth_sequence_and_cli_remain_fail_closed() -> None:
    requirements = tenth_sequence._DEFINITION.critical_gate_requirements

    assert "controlled_event_reference_orphan_zero" in requirements
    assert "controlled_event_target_orphan_zero" in requirements
    assert "single_representation_family_recovered" in requirements
    assert tenth_nested_holdout_exit_code({"gate": {"passed": True}}) == 0
    assert tenth_nested_holdout_exit_code({"gate": {"passed": False}}) == 1
    assert tenth_nested_holdout_exit_code({}) == 1


def _resign_report(report: dict[str, object]) -> None:
    report.pop("report_sha256", None)
    report["report_sha256"] = sha256_json(report)


def _complete_tenth_report(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authorization: TenthRepeatAuthorization | None = None,
) -> dict[str, object]:
    unit = FrozenSourceUnit(
        unit_id=_UNIT_ID,
        index=17,
        source_start=_SOURCE_START,
        source_end=_SOURCE_START + len(_SOURCE),
        text=_SOURCE,
        source_sha256=_SOURCE_SHA256,
    )
    projection_set = tenth_projection_set()
    graph = projection_set.canonical_projection.graph
    selection = NestedHoldoutSelection(
        case_id="bionlp-ge-2011-holdout:PMC-2222968-04-Results-03",
        unit=unit,
        expert_graph=graph,
        trial_generation=10,
        selection_seed=_SELECTION_SEED,
        selection_rule="test-reconstruction-of-frozen-v10",
        excluded_document_ids=("PMID-8622948",),
        selection_rank="a7b2a256",
        candidate_unit_count=3,
        holdout_document_count=219,
        incompatible_document_ids=(),
        archive_sha256=TG04_BIONLP_ARCHIVE_SHA256,
        expert_graph_sha256=TENTH_EXPERT_GRAPH_SHA256,
        authoritative_article_url=("https://pmc.ncbi.nlm.nih.gov/articles/PMC2222968/"),
        projection_set=projection_set,
        projection_set_sha256=TENTH_PROJECTION_SET_SHA256,
        expected_eligibility_category=SourceUnitEligibilityCategory.NULL_RESULT,
    )
    prototype = _nested_inventory()
    extraction = SourceUnitExtractionOutput(
        eligibility_category=SourceUnitEligibilityCategory.NULL_RESULT,
        decision=SourceUnitDecision.EXPLICIT_EVENT,
        events=tuple(candidate.item for candidate in prototype),
        reasoning="The source reports one complete nested null event.",
    )
    candidates = bind_source_unit_extraction(extraction, unit=unit).accepted
    verification = SourceUnitVerificationOutput(
        eligibility_category=SourceUnitEligibilityCategory.NULL_RESULT,
        coverage_decision=SourceUnitCoverageDecision.CANDIDATES_COMPLETE,
        coverage_reasoning="The controller and controlled target are complete.",
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
        observed_binding_rejections=(),
        unresolved_binding_rejections=(),
        schema_retry_count=0,
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
            "tg04-v10-replay-test" if authorization is None else authorization.run_id
        ),
        repeat_index=(1 if authorization is None else authorization.repeat_index),
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


def _attempt_records(
    *,
    unit: FrozenSourceUnit,
    candidates: tuple[BoundClaimInventoryItem, ...],
    extraction: SourceUnitExtractionOutput,
    verification: SourceUnitVerificationOutput,
    evidence_unit_sha256: str,
) -> tuple[ModelAttemptAuditRecord, ...]:
    payloads = (
        extraction.model_dump(mode="json"),
        verification.model_dump(mode="json"),
    )
    prompts = (
        v10_source_unit_extraction_prompt(unit),
        v10_source_unit_verification_prompt(unit=unit, candidates=candidates),
    )
    schemas = (SourceUnitExtractionOutput, SourceUnitVerificationOutput)
    roles = (("primary", "primary"), ("weak_review", "weak_review"))
    records: list[ModelAttemptAuditRecord] = []
    for index, (payload, prompt, schema, role) in enumerate(
        zip(payloads, prompts, schemas, roles, strict=True)
    ):
        invocation_id = f"v10-test-{role[0]}"
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
                attempt_role=role[0],
                pass_role=role[1],
                retry_context=None,
                model_id="openai/gpt-5.6-luna",
                step_key=f"v10-test-{index}",
                prompt_sha256=hashlib.sha256(provider_prompt.encode()).hexdigest(),
                source_sha256=unit.source_sha256,
                input_sha256=unit.input_sha256,
                evidence_unit_sha256=evidence_unit_sha256,
                semantic_unit_id=unit.unit_id,
                output_schema_identity=f"{schema.__module__}.{schema.__qualname__}",
                provider_execution_response_id=f"resp_v10_test_{index}",
                provider_response_id=f"resp_v10_test_{index}",
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
