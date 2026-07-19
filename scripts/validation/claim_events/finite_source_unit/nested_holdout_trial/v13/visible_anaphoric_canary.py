from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, TextIO
from uuid import uuid4

from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    bind_prompt_to_invocation,
    kernel_run_id_for_invocation,
    output_schema_json_sha256,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    fingerprinted_step_key,
)

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitExtractionOutput,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v13.execution import (
    V13_EXECUTION_POLICY,
    execute_v13_source_unit_agents,
)
from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    MaterialAxis,
    SourceUnitNormalizedReviewOutput,
)
from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    canonical_json_sha256,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_contracts import (
    SourceUnitNormalizationOutputV13,
)
from scripts.validation.claim_events.finite_source_unit.service import as_model_client
from scripts.validation.claim_events.finite_source_unit.source_units import (
    FrozenSourceUnit,
    enumerate_source_units,
)
from scripts.validation.claim_events.runner import (
    build_tg04_runtime,
    receipt_expectation_from_attempt,
)
from scripts.validation.claim_frames.provider_receipts import (
    OpenAIProviderReceiptVerifier,
    ProviderReceiptVerification,
    verify_provider_receipts,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.claim_frames import (
        ClaimInventoryArgument,
    )
    from artana_evidence_api.document_extraction_support.llm_extraction.attempt_audit import (
        ModelAttemptAuditRecord,
    )
    from pydantic import BaseModel

    from scripts.validation.claim_events.finite_source_unit.normalization.execution import (
        ThreeCallAgentRunEvidence,
    )

REPO: Final = Path("/Users/alvaro/.codex/worktrees/artana-evidence-recalibration-triad")
PREREG_DOC: Final = REPO / (
    "docs/validation/reports/2026-07-19-tg04-v13-visible-nested-preregistration.md"
)
RUNNER_REPO_PATH: Final = (
    "scripts/validation/claim_events/finite_source_unit/"
    "nested_holdout_trial/v13/visible_anaphoric_canary.py"
)
RUNNER_SHA_PATTERN: Final = re.compile(r"runner SHA-256:\s*`([0-9a-f]{64})`")
CODE_COMMIT_PATTERN: Final = re.compile(r"code-under-test commit:\s*`([0-9a-f]{40})`")
MODEL_ID: Final = "openai:gpt-5.6-luna"
CONTRACT_VERSION: Final = "tg04.finite_source_unit.v13_execution.v2"
CONTRACT_SHA256: Final = (
    "076878a72c9653d44f6f4bbedb5171194b8cb7599991c810ef374b26bd276776"
)
PROMPT_SHA256: Final = (
    "250b7db39dc7fea3c03f3d0d56cd99598e3f792cfba5ca363a9377c0aef32314"
)
SCHEMA_SHA256: Final = (
    "43418016713a4b848069e1a82babd0ab0706a5502889d14209ec371512456e0f"
)
CASE_ID: Final = "v13-visible-explicit-anaphoric-nested"
SOURCE: Final = "EGF activated ERK, and the MEK1-null genotype reduced that activation."
UNIT_ID: Final = (
    "source-unit-8f4110dc6f36311360f5b61f457fbf0e5a52551c415331d1a0c953bcb298d7d9"
)
SOURCE_SHA256: Final = (
    "5a9b163d436c6c64d8cc286f33a80a37d3821485165f9d010d7dc1a919e5e508"
)
INPUT_SHA256: Final = "1e4d51b0f100dec717645bef66f4b8edfb8e07980b935325354d4863c9555df5"
EXPECTED_ATTEMPT_COUNT: Final = 3
EXPECTED_EVENT_COUNT: Final = 2
RESERVATION_KEY: Final = hashlib.sha256(
    f"{CONTRACT_VERSION}|{MODEL_ID}|{SOURCE_SHA256}|{INPUT_SHA256}".encode()
).hexdigest()
ARTIFACT_DIR: Final = (
    Path("/Users/alvaro/.codex")
    / "artana-evidence-experiments"
    / "tg04"
    / f"v13-visible-anaphoric-{RESERVATION_KEY}"
)
JOURNAL: Final = ARTIFACT_DIR / "journal.jsonl"
OUTPUT: Final = ARTIFACT_DIR / "result.json"


class CrashJournal:
    def __init__(self, path: Path, header: dict[str, object]) -> None:
        self.path = path
        with path.open("x", encoding="utf-8") as stream:
            self._write(stream, {"entry_type": "reservation", **header})
        fsync_directory(path.parent)

    def record_attempt(self, record: ModelAttemptAuditRecord) -> None:
        self.append(
            {
                "entry_type": "attempt",
                "record": record.as_json(),
            }
        )

    def record_evidence(self, evidence: ThreeCallAgentRunEvidence) -> None:
        self.append(
            {
                "entry_type": "evidence",
                "execution_contract_version": evidence.execution_contract_version,
                "original_raw_output": evidence.original_raw_output,
                "normalized_raw_output": evidence.normalized_raw_output,
                "review_raw_output": evidence.review_raw_output,
                "records": [record.as_json() for record in evidence.records],
                "error_type": evidence.error_type,
                "failed_stage": evidence.failed_stage,
            }
        )

    def append(self, payload: dict[str, object]) -> None:
        with self.path.open("a", encoding="utf-8") as stream:
            self._write(stream, payload)

    @staticmethod
    def _write(stream: TextIO, payload: dict[str, object]) -> None:
        stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


@dataclass(frozen=True, slots=True)
class GateAContext:
    unit: FrozenSourceUnit
    execution_model_id: str
    run_uuid: str
    audit_evidence_unit_id: str


def sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def command(*parts: str) -> str:
    return subprocess.check_output(parts, cwd=REPO, text=True).strip()


def preflight() -> tuple[FrozenSourceUnit, dict[str, object]]:
    if OUTPUT.exists() or JOURNAL.exists():
        raise RuntimeError("one-shot V13 canary already has an artifact or reservation")
    if command("git", "status", "--porcelain"):
        raise RuntimeError("V13 canary requires a clean worktree")
    head = command("git", "rev-parse", "HEAD")
    preregistration = PREREG_DOC.read_text(encoding="utf-8")
    code_commit_match = CODE_COMMIT_PATTERN.search(preregistration)
    if code_commit_match is None:
        raise RuntimeError("V13 preregistration lacks the full code commit")
    code_commit = code_commit_match.group(1)
    if command("git", "rev-parse", "HEAD^") != code_commit:
        raise RuntimeError("V13 preregistration must directly follow its code commit")
    changed = command("git", "diff", "--name-only", code_commit, "HEAD")
    if changed != PREREG_DOC.relative_to(REPO).as_posix():
        raise RuntimeError("code changed after the frozen V13 code checkpoint")
    runner_sha_match = RUNNER_SHA_PATTERN.search(preregistration)
    if runner_sha_match is None:
        raise RuntimeError("V13 preregistration lacks the external runner SHA-256")
    runner_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if runner_sha256 != runner_sha_match.group(1):
        raise RuntimeError("committed V13 runner differs from its frozen hash")
    if Path(__file__).resolve() != (REPO / RUNNER_REPO_PATH).resolve():
        raise RuntimeError("V13 canary must execute its committed runner path")
    (unit,) = enumerate_source_units(case_id=CASE_ID, source_text=SOURCE)
    policy_json = V13_EXECUTION_POLICY.as_json()
    prompt = V13_EXECUTION_POLICY.extraction_prompt_policy.extraction_prompt(unit)
    observed = {
        "head": head,
        "code_commit": code_commit,
        "runner_sha256": runner_sha256,
        "reservation_key": RESERVATION_KEY,
        "artifact_directory": str(ARTIFACT_DIR),
        "unit_id": unit.unit_id,
        "source_sha256": unit.source_sha256,
        "input_sha256": unit.input_sha256,
        "source_start": unit.source_start,
        "source_end": unit.source_end,
        "contract_version": policy_json["contract_version"],
        "contract_sha256": sha256_json(policy_json),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "schema_sha256": output_schema_json_sha256(SourceUnitNormalizationOutputV13),
    }
    expected = {
        "unit_id": UNIT_ID,
        "source_sha256": SOURCE_SHA256,
        "input_sha256": INPUT_SHA256,
        "source_start": 0,
        "source_end": 70,
        "contract_version": CONTRACT_VERSION,
        "contract_sha256": CONTRACT_SHA256,
        "prompt_sha256": PROMPT_SHA256,
        "schema_sha256": SCHEMA_SHA256,
    }
    for key, expected_value in expected.items():
        if observed[key] != expected_value:
            raise RuntimeError(
                f"V13 preregistration mismatch for {key}: {observed[key]!r}"
            )
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    return unit, observed


def build_receipts(
    records: tuple[ModelAttemptAuditRecord, ...], execution_model_id: str
) -> tuple[ProviderReceiptVerification, str | None]:
    schema_by_role: dict[str, type[BaseModel]] = {
        "primary": SourceUnitExtractionOutput,
        "structure_normalization": SourceUnitNormalizationOutputV13,
        "normalized_review": SourceUnitNormalizedReviewOutput,
    }

    def require_semantic_unit(record: ModelAttemptAuditRecord) -> None:
        if record.semantic_unit_id != UNIT_ID:
            raise RuntimeError("V13 attempt has the wrong semantic unit")

    try:
        expectations = []
        for record in records:
            require_semantic_unit(record)
            schema = schema_by_role[record.attempt_role]
            expectations.append(
                receipt_expectation_from_attempt(
                    case_id=UNIT_ID,
                    report_model_id=execution_model_id,
                    record=record.as_json(),
                    expected_output_schema_sha256=output_schema_json_sha256(schema),
                )
            )
    except Exception as exc:
        return (
            ProviderReceiptVerification(
                status="not_verified",
                expected_count=len(records),
                verified_count=0,
                receipts=(),
            ),
            f"{type(exc).__name__}: {exc}",
        )
    return (
        verify_provider_receipts(
            expectations,
            OpenAIProviderReceiptVerifier.from_environment(),
        ),
        None,
    )


def raw_preserved(
    raw: dict[str, object] | None,
    model: BaseModel | None,
) -> bool:
    return (
        raw is not None and model is not None and raw == model.model_dump(mode="json")
    )


def seal_report(journal: CrashJournal, report: dict[str, object]) -> dict[str, object]:
    report["report_sha256"] = sha256_json(report)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=OUTPUT.parent,
        prefix=f".{OUTPUT.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, OUTPUT)
        fsync_directory(OUTPUT.parent)
        journal.append(
            {
                "entry_type": "terminal_result",
                "decision": report["decision"],
                "report_sha256": report["report_sha256"],
            }
        )
    finally:
        temporary.unlink(missing_ok=True)
    return report


def attempt_custody(
    *,
    agent_run: ThreeCallAgentRunEvidence,
    unit: FrozenSourceUnit,
    execution_model_id: str,
    run_uuid: str,
    audit_evidence_unit_id: str,
) -> dict[str, bool]:
    records = agent_run.records
    if (
        len(records) != EXPECTED_ATTEMPT_COUNT
        or agent_run.original_result is None
        or agent_run.normalized_result is None
        or agent_run.original_raw_output is None
        or agent_run.normalized_raw_output is None
    ):
        return {
            "attempt_static_bindings_exact": False,
            "attempt_prompt_chain_exact": False,
            "attempt_kernel_identity_exact": False,
        }
    try:
        contract_namespace = fingerprinted_step_key(
            "execution-contract",
            f"v13-visible-anaphoric:{run_uuid}",
            CONTRACT_VERSION,
        )
        evidence_unit_sha256 = hashlib.sha256(
            audit_evidence_unit_id.encode()
        ).hexdigest()
        schemas: tuple[type[BaseModel], ...] = (
            SourceUnitExtractionOutput,
            SourceUnitNormalizationOutputV13,
            SourceUnitNormalizedReviewOutput,
        )
        prompts = (
            V13_EXECUTION_POLICY.extraction_prompt_policy.extraction_prompt(unit),
            V13_EXECUTION_POLICY.normalization_prompt_builder(
                unit=unit,
                original=agent_run.original_result,
            ),
            V13_EXECUTION_POLICY.review_prompt_builder(
                unit=unit,
                original=agent_run.original_result,
                normalized=agent_run.normalized_result,
            ),
        )
        step_keys = (
            fingerprinted_step_key(
                V13_EXECUTION_POLICY.extraction_prompt_policy.extraction_version,
                execution_model_id,
                unit.input_sha256,
                contract_namespace,
            ),
            fingerprinted_step_key(
                V13_EXECUTION_POLICY.normalization_prompt_version,
                execution_model_id,
                unit.input_sha256,
                canonical_json_sha256(agent_run.original_raw_output),
                contract_namespace,
            ),
            fingerprinted_step_key(
                V13_EXECUTION_POLICY.review_prompt_version,
                execution_model_id,
                unit.input_sha256,
                canonical_json_sha256(agent_run.original_raw_output),
                canonical_json_sha256(agent_run.normalized_raw_output),
                contract_namespace,
            ),
        )
        bound_prompt_hashes = tuple(
            hashlib.sha256(
                bind_prompt_to_invocation(
                    prompt=prompt,
                    invocation_id=record.invocation_id,
                    source_sha256=SOURCE_SHA256,
                    input_sha256=INPUT_SHA256,
                    evidence_unit_sha256=evidence_unit_sha256,
                    output_schema_sha256=output_schema_json_sha256(schema),
                ).encode()
            ).hexdigest()
            for record, prompt, schema in zip(records, prompts, schemas, strict=True)
        )
        expected_roles = (
            "primary",
            "structure_normalization",
            "normalized_review",
        )
        static_bindings_exact = all(
            record.attempt_role == role
            and record.pass_role == role
            and record.retry_context is None
            and record.model_id == execution_model_id
            and record.source_sha256 == SOURCE_SHA256
            and record.input_sha256 == INPUT_SHA256
            and record.evidence_unit_sha256 == evidence_unit_sha256
            and record.semantic_unit_id == UNIT_ID
            and record.output_schema_identity
            == f"{schema.__module__}.{schema.__qualname__}"
            and record.validation_outcome == "accepted"
            and record.error_type is None
            and record.execution_contract_version == CONTRACT_VERSION
            and record.replayed is False
            and record.provider_execution_response_id is not None
            and record.provider_response_id is not None
            and record.provider_output_sha256 is not None
            and record.raw_model_payload_json is not None
            and record.payload_sha256 is not None
            for record, role, schema in zip(
                records,
                expected_roles,
                schemas,
                strict=True,
            )
        )
        prompt_chain_exact = all(
            record.step_key == expected_step_key
            and record.prompt_sha256 == expected_prompt_sha256
            for record, expected_step_key, expected_prompt_sha256 in zip(
                records,
                step_keys,
                bound_prompt_hashes,
                strict=True,
            )
        )
        kernel_identity_exact = all(
            record.kernel_run_id == kernel_run_id_for_invocation(record.invocation_id)
            for record in records
        )
    except Exception:
        return {
            "attempt_static_bindings_exact": False,
            "attempt_prompt_chain_exact": False,
            "attempt_kernel_identity_exact": False,
        }
    return {
        "attempt_static_bindings_exact": static_bindings_exact,
        "attempt_prompt_chain_exact": prompt_chain_exact,
        "attempt_kernel_identity_exact": kernel_identity_exact,
    }


def gate_a(
    *,
    agent_run: ThreeCallAgentRunEvidence,
    receipts: ProviderReceiptVerification,
    receipt_construction_error: str | None,
    context: GateAContext,
) -> dict[str, bool]:
    roles = [record.attempt_role for record in agent_run.records]
    step_keys = [record.step_key for record in agent_run.records]
    review = agent_run.normalized_review
    normalized = agent_run.normalized_extraction
    requirements = {
        "three_attempts_in_role_order": roles
        == ["primary", "structure_normalization", "normalized_review"],
        "all_attempts_accepted": all(
            record.validation_outcome == "accepted" for record in agent_run.records
        ),
        "contract_v2_in_run": agent_run.execution_contract_version == CONTRACT_VERSION,
        "contract_v2_in_every_attempt": all(
            record.execution_contract_version == CONTRACT_VERSION
            for record in agent_run.records
        ),
        "three_distinct_stage_keys": len(step_keys)
        == len(set(step_keys))
        == EXPECTED_ATTEMPT_COUNT,
        "all_outputs_present": all(
            value is not None
            for value in (
                agent_run.original_extraction,
                normalized,
                review,
            )
        ),
        "execution_has_no_error": agent_run.error_type is None,
        "all_raw_outputs_preserved": all(
            (
                raw_preserved(
                    agent_run.original_raw_output,
                    agent_run.original_extraction,
                ),
                raw_preserved(
                    agent_run.normalized_raw_output,
                    normalized,
                ),
                raw_preserved(agent_run.review_raw_output, review),
            )
        ),
        "review_covers_every_axis": review is not None
        and tuple(item.axis for item in review.axis_reviews) == tuple(MaterialAxis),
        "review_covers_every_candidate": review is not None
        and normalized is not None
        and tuple(item.normalized_event_position for item in review.candidate_reviews)
        == tuple(range(len(normalized.events))),
        "provider_ids_unique": len(
            {record.provider_response_id for record in agent_run.records}
        )
        == EXPECTED_ATTEMPT_COUNT
        and all(
            record.provider_response_id is not None for record in agent_run.records
        ),
        "three_live_receipts_verified": receipts.expected_count
        == receipts.verified_count
        == EXPECTED_ATTEMPT_COUNT,
        "receipt_gate_passed": receipts.gate_passed,
        "receipt_expectations_constructed": receipt_construction_error is None,
        "no_retry_fallback_or_repair_roles": set(roles)
        == {"primary", "structure_normalization", "normalized_review"},
    }
    requirements.update(
        attempt_custody(
            agent_run=agent_run,
            unit=context.unit,
            execution_model_id=context.execution_model_id,
            run_uuid=context.run_uuid,
            audit_evidence_unit_id=context.audit_evidence_unit_id,
        )
    )
    return requirements


def argument_signature(argument: ClaimInventoryArgument) -> tuple[str, str, str]:
    return (
        argument.role.value,
        argument.event_role.value,
        argument.exact_span,
    )


def gate_b(agent_run: ThreeCallAgentRunEvidence) -> dict[str, bool]:
    normalized = agent_run.normalized_extraction
    review = agent_run.normalized_review
    bound = agent_run.normalized_result
    review_result = agent_run.review_result
    if normalized is None or review is None or bound is None or review_result is None:
        return {"scientific_outputs_available": False}
    by_cue = {event.relation_cue_span: event for event in normalized.events}
    inner = by_cue.get("activated")
    outer = by_cue.get("reduced")
    links = bound.controlled_event_links
    inner_args = (
        set() if inner is None else {argument_signature(a) for a in inner.arguments}
    )
    outer_args = (
        set() if outer is None else {argument_signature(a) for a in outer.arguments}
    )
    outer_process = None
    if outer is not None:
        outer_process = next(
            (
                argument
                for argument in outer.arguments
                if argument.role.value == "BIOLOGICAL_PROCESS"
            ),
            None,
        )
    link = links[0] if len(links) == 1 else None
    bound_by_local_id = {
        item.item.local_event_id: item.inventory_id for item in bound.accepted
    }
    return {
        "eligibility_is_finding": normalized.eligibility_category.value == "FINDING",
        "family_is_nested": normalized.family.value == "NESTED",
        "normalization_did_not_abstain": normalized.abstention_reason.value == "NONE",
        "exactly_two_events": len(normalized.events) == EXPECTED_EVENT_COUNT,
        "exactly_two_mappings": len(normalized.mappings) == EXPECTED_EVENT_COUNT,
        "no_context_dimensions": normalized.context_dimensions == (),
        "both_claims_are_scientific_findings": all(
            event.claim_kind.value == "SCIENTIFIC_FINDING"
            for event in normalized.events
        ),
        "both_events_source_asserted": all(
            event.assertion_scope.value == "SOURCE_ASSERTED"
            for event in normalized.events
        ),
        "inner_axes_exact": inner is not None
        and inner.exact_span == "EGF activated ERK"
        and inner.event_type.value == "POSITIVE_REGULATION"
        and inner.polarity.value == "SUPPORT"
        and inner.epistemic_status.value == "ASSERTED",
        "inner_arguments_exact": inner_args
        == {
            ("GENE_OR_PROTEIN", "CAUSE", "EGF"),
            ("GENE_OR_PROTEIN", "THEME", "ERK"),
        }
        and inner is not None
        and all(argument.controlled_event_ref is None for argument in inner.arguments),
        "outer_axes_exact": outer is not None
        and outer.exact_span == "the MEK1-null genotype reduced that activation"
        and outer.event_type.value == "NEGATIVE_REGULATION"
        and outer.polarity.value == "SUPPORT"
        and outer.epistemic_status.value == "ASSERTED",
        "outer_arguments_exact": outer_args
        == {
            ("VARIANT", "CAUSE", "the MEK1-null genotype"),
            ("BIOLOGICAL_PROCESS", "THEME", "that activation"),
        },
        "anaphoric_referent_exact": outer_process is not None
        and tuple(anchor.mention_span for anchor in outer_process.referent_anchors)
        == ("EGF activated ERK",),
        "outer_ref_targets_inner": inner is not None
        and outer_process is not None
        and outer_process.controlled_event_ref == inner.local_event_id,
        "exactly_one_bound_outer_to_inner_link": link is not None
        and inner is not None
        and outer is not None
        and link.controller_event_role.value == "THEME"
        and link.controller_inventory_id == bound_by_local_id.get(outer.local_event_id)
        and link.controlled_inventory_id == bound_by_local_id.get(inner.local_event_id),
        "inventory_complete": review.inventory_coverage.value == "COMPLETE",
        "review_eligibility_is_finding": review.eligibility_category.value == "FINDING",
        "unsupported_additions_absent": review.unsupported_additions.value == "ABSENT",
        "family_valid": review.family_validity.value == "VALID",
        "cue_alignment_exact": review.cue_alignment.value == "EXACT",
        "all_axes_preserved": all(
            item.decision.value in {"PRESERVED", "COMPATIBLE_REFINEMENT"}
            for item in review.axis_reviews
        ),
        "both_candidates_entailed": len(review.candidate_reviews)
        == EXPECTED_EVENT_COUNT
        and all(
            item.source_entailment.value == "ENTAILED"
            for item in review.candidate_reviews
        ),
        "review_has_no_scientific_loss": review_result.scientific_loss_count == 0,
        "review_has_no_unsupported_addition": (
            review_result.unsupported_addition_count == 0
        ),
        "review_has_no_unresolved_axis": review_result.unresolved_axis_count == 0,
    }


async def execute(
    unit: FrozenSourceUnit,
    observed: dict[str, object],
) -> dict[str, object]:
    run_uuid = uuid4().hex
    audit_evidence_unit_id = f"v13-visible-anaphoric:{run_uuid}"
    # Runtime construction is a provider-free preflight. Do not consume the
    # one-shot reservation for a missing key, wrong model, or unavailable store.
    raw_client, tenant, execution_model_id, kernel, store = build_tg04_runtime(MODEL_ID)
    journal: CrashJournal | None = None
    agent_run = None
    try:
        journal = CrashJournal(
            JOURNAL,
            {
                "reserved_at": datetime.now(UTC).isoformat(),
                "run_uuid": run_uuid,
                "audit_evidence_unit_id": audit_evidence_unit_id,
                "execution_model_id": execution_model_id,
                "preflight": observed,
            },
        )
        terminal_base_error: BaseException | None = None
        try:
            agent_run = await execute_v13_source_unit_agents(
                client=as_model_client(raw_client),
                tenant=tenant,
                model_id=execution_model_id,
                execution_namespace=f"v13-visible-anaphoric:{run_uuid}",
                unit=unit,
                audit_evidence_unit_id=audit_evidence_unit_id,
                evidence_observer=journal.record_evidence,
                attempt_observer=journal.record_attempt,
            )
            receipts, receipt_construction_error = build_receipts(
                agent_run.records,
                execution_model_id,
            )
            requirements_a = gate_a(
                agent_run=agent_run,
                receipts=receipts,
                receipt_construction_error=receipt_construction_error,
                context=GateAContext(
                    unit=unit,
                    execution_model_id=execution_model_id,
                    run_uuid=run_uuid,
                    audit_evidence_unit_id=audit_evidence_unit_id,
                ),
            )
            requirements_b = gate_b(agent_run) if all(requirements_a.values()) else {}
            decision = (
                "STOP_WORKFLOW_INVALID"
                if not all(requirements_a.values())
                else (
                    "PASS_VISIBLE_CONTRACT_CANARY"
                    if all(requirements_b.values())
                    else "STOP_VISIBLE_CANARY_FAILED"
                )
            )
            report: dict[str, object] = {
                "schema_version": "tg04.v13.visible_anaphoric_canary.v1",
                "generated_at": datetime.now(UTC).isoformat(),
                "decision": decision,
                "qualification_eligible": False,
                "hidden_unit_authorized": False,
                "graph_persistence_authorized": False,
                "configured_model_id": MODEL_ID,
                "execution_model_id": execution_model_id,
                "preflight": observed,
                "run_uuid": run_uuid,
                "audit_evidence_unit_id": audit_evidence_unit_id,
                "gate_a": requirements_a,
                "gate_b": requirements_b,
                "agent_outputs": {
                    "original_extraction": agent_run.original_raw_output,
                    "normalized_extraction": agent_run.normalized_raw_output,
                    "normalized_review": agent_run.review_raw_output,
                    "error_type": agent_run.error_type,
                    "failed_stage": agent_run.failed_stage,
                },
                "attempts": [record.as_json() for record in agent_run.records],
                "provider_receipts": receipts.as_json(),
                "receipt_construction_error": receipt_construction_error,
            }
        except BaseException as exc:
            if not isinstance(exc, Exception):
                terminal_base_error = exc
            report = {
                "schema_version": "tg04.v13.visible_anaphoric_canary.v1",
                "generated_at": datetime.now(UTC).isoformat(),
                "decision": "STOP_RUNNER_ERROR",
                "qualification_eligible": False,
                "hidden_unit_authorized": False,
                "graph_persistence_authorized": False,
                "configured_model_id": MODEL_ID,
                "execution_model_id": execution_model_id,
                "preflight": observed,
                "run_uuid": run_uuid,
                "audit_evidence_unit_id": audit_evidence_unit_id,
                "gate_a": {},
                "gate_b": {},
                "agent_outputs": None
                if agent_run is None
                else {
                    "original_extraction": agent_run.original_raw_output,
                    "normalized_extraction": agent_run.normalized_raw_output,
                    "normalized_review": agent_run.review_raw_output,
                    "error_type": agent_run.error_type,
                    "failed_stage": agent_run.failed_stage,
                },
                "attempts": []
                if agent_run is None
                else [record.as_json() for record in agent_run.records],
                "provider_receipts": None,
                "receipt_construction_error": None,
                "runner_error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            }
        sealed = seal_report(journal, report)
        if terminal_base_error is not None:
            raise terminal_base_error
        return sealed
    finally:
        with suppress(Exception):
            await kernel.close()
        with suppress(Exception):
            await store.close()


def main() -> None:
    unit, observed = preflight()
    report = asyncio.run(execute(unit, observed))
    print(
        json.dumps(
            {
                "decision": report["decision"],
                "gate_a": report["gate_a"],
                "gate_b": report["gate_b"],
                "report_sha256": report["report_sha256"],
                "output": str(OUTPUT),
                "journal": str(JOURNAL),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
