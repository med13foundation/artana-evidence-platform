"""Execute one frozen staged scientific-event comparison and stop."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.scientific_events import (
        ScientificEventDocument,
    )

from scripts.validation.provider_receipt_boundary.background import (
    BackgroundExecutionBudgets,
    execute_background_provider_call,
)
from scripts.validation.public_gold.bionlp_cg_event_projection import (
    project_development_directory,
)
from scripts.validation.public_gold.lossless_event_preflight import (
    DEVELOPMENT_DIRECTORY,
)
from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
    ProviderRequest,
)
from scripts.validation.public_gold.lossless_event_scoring import (
    LosslessEventScore,
    score_scientific_event_document,
)
from scripts.validation.public_gold.source_selection import (
    load_development_sources,
    select_lowest_sha256,
)
from scripts.validation.public_gold.staged_event.assembly import (
    AssemblyInputs,
    StagedAssemblyError,
    assemble_staged_document,
    completion_stage_outputs,
    resolve_discovery_candidates,
)
from scripts.validation.public_gold.staged_event.contracts import (
    CompletionOutput,
    DiscoveryCandidate,
    EventDiscoveryOutput,
    ModifierOutput,
    ParticipantInventoryOutput,
    RoleAssignmentOutput,
    VerificationOutput,
)
from scripts.validation.public_gold.staged_event.paths import repository_root
from scripts.validation.public_gold.staged_event.preflight import verify_preregistration
from scripts.validation.public_gold.staged_event.prompting import (
    build_provider_format,
    build_stage_input,
    event_context,
    load_prompt,
    role_context,
    verification_context,
)
from scripts.validation.public_gold.staged_event.registry import (
    COMPLETION,
    DISCOVERY,
    MODIFIERS,
    PARTICIPANTS,
    ROLES,
    VERIFICATION,
    StageSpec,
)

_OutputT = TypeVar("_OutputT", bound=BaseModel)
MINIMUM_COMPLETE_EVENTS = 10
MINIMUM_TRIGGERS = 24
MINIMUM_TYPED_ARGUMENTS = 15
MINIMUM_NESTED_ARGUMENTS = 5
MAXIMUM_UNSUPPORTED_EVENTS = 15
DECISIONS = {
    "STAGED_METRIC_GATE_PASSED_PENDING_ADJUDICATION",
    "STAGED_NO_MEANINGFUL_IMPROVEMENT",
    "INVALID_EXPERIMENT",
}


class StagedComparisonError(ValueError):
    """One frozen deterministic or aggregate experiment invariant failed."""


@dataclass(frozen=True, slots=True)
class ArtifactPaths:
    receipt: Path
    result: Path
    report: Path
    raw_output_directory: Path


@dataclass(slots=True)
class BudgetLedger:
    max_calls: int
    max_tokens: int
    max_output_tokens_per_call: int
    max_cost_usd: float
    max_latency_seconds: float
    calls: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    total_latency_seconds: float = 0.0
    receipts: list[dict[str, object]] = field(default_factory=list)
    terminal_violation: str | None = None

    def remaining(self) -> tuple[int, float, float]:
        return (
            self.max_tokens - self.total_tokens,
            self.max_cost_usd - self.total_cost_usd,
            self.max_latency_seconds - self.total_latency_seconds,
        )

    def ensure_call_available(self) -> None:
        if self.terminal_violation is not None:
            raise StagedComparisonError(self.terminal_violation)
        if self.calls >= self.max_calls:
            raise StagedComparisonError("agent call budget exhausted")

    def record(self, stage: str, receipt: dict[str, object]) -> None:
        usage = _required_dict(receipt, "usage")
        tokens = _required_int(usage, "total_tokens")
        output_tokens = _required_int(usage, "output_tokens")
        cost = _required_float(usage, "cost_usd", allow_zero=True)
        latency = _required_float(usage, "latency_seconds", allow_zero=True)
        self.calls += 1
        self.total_tokens += tokens
        self.total_cost_usd += cost
        self.total_latency_seconds += latency
        recorded = {"stage": stage, **receipt}
        self.receipts.append(recorded)
        if self.calls > self.max_calls:
            raise StagedComparisonError("agent call budget exceeded")
        if output_tokens > self.max_output_tokens_per_call:
            self.terminal_violation = (
                f"{stage} per-call output token budget exceeded"
            )
            raise StagedComparisonError(self.terminal_violation)
        if self.total_tokens > self.max_tokens:
            raise StagedComparisonError("aggregate token budget exceeded")
        if self.total_cost_usd > self.max_cost_usd:
            raise StagedComparisonError("aggregate cost budget exceeded")
        if self.total_latency_seconds > self.max_latency_seconds:
            raise StagedComparisonError("aggregate latency budget exceeded")

    def as_json(self) -> dict[str, object]:
        return {
            "provider_creation_calls": self.calls,
            "provider_retries": 0,
            "fallbacks": 0,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "total_latency_seconds": self.total_latency_seconds,
            "receipts": self.receipts,
            "terminal_violation": self.terminal_violation,
        }


@dataclass(frozen=True, slots=True)
class StageCallContext:
    repository_root: Path
    preregistration_path: Path
    document_id: str
    source_sha256: str
    model: dict[str, object]
    budgets: dict[str, object]
    ledger: BudgetLedger
    raw_output_directory: Path


def run_comparison(  # noqa: PLR0915 - linear orchestration mirrors frozen stage order.
    *,
    repository_root: Path,
    preregistration_path: Path,
    artifacts: ArtifactPaths,
) -> str:
    preflight = verify_preregistration(repository_root, preregistration_path)
    preregistration = json.loads(preregistration_path.read_text(encoding="utf-8"))
    frozen = _required_dict(preregistration, "frozen_state")
    model = _required_dict(frozen, "model")
    budgets = _required_dict(preregistration, "budgets")
    sources = load_development_sources(
        repository_root / DEVELOPMENT_DIRECTORY,
        expected_documents=100,
    )
    selected = select_lowest_sha256(sources)
    ledger = BudgetLedger(
        max_calls=_required_int(budgets, "max_agent_calls"),
        max_tokens=_required_int(budgets, "max_total_tokens"),
        max_output_tokens_per_call=_required_int(
            budgets, "max_output_tokens_per_call"
        ),
        max_cost_usd=_required_float(budgets, "max_total_cost_usd"),
        max_latency_seconds=_required_float(budgets, "max_total_latency_seconds"),
    )
    stage_context = StageCallContext(
        repository_root=repository_root,
        preregistration_path=preregistration_path,
        document_id=selected.document_id,
        source_sha256=selected.source_sha256,
        model=model,
        budgets=budgets,
        ledger=ledger,
        raw_output_directory=artifacts.raw_output_directory,
    )
    stage_outputs: dict[str, object] = {}
    current_stage = "PREFLIGHT"
    try:
        current_stage = DISCOVERY.name
        discovery = _run_stage(
            spec=DISCOVERY,
            output_model=EventDiscoveryOutput,
            payload={"source_text": selected.source_text},
            context=stage_context,
        )
        stage_outputs[current_stage] = discovery.model_dump(mode="json")
        if discovery.decision == "ABSTAIN":
            _raise_comparison_error("discovery stage abstained from the source")
        resolution = resolve_discovery_candidates(
            discovery.candidates,
            source_text=selected.source_text,
            source_sha256=selected.source_sha256,
        )
        candidates = resolution.candidates

        current_stage = PARTICIPANTS.name
        participants = _run_stage(
            spec=PARTICIPANTS,
            output_model=ParticipantInventoryOutput,
            payload={"events": event_context(candidates)},
            context=stage_context,
        )
        stage_outputs[current_stage] = participants.model_dump(mode="json")

        current_stage = ROLES.name
        roles = _run_stage(
            spec=ROLES,
            output_model=RoleAssignmentOutput,
            payload={"events": role_context(candidates, participants)},
            context=stage_context,
        )
        stage_outputs[current_stage] = roles.model_dump(mode="json")

        current_stage = MODIFIERS.name
        modifiers = _run_stage(
            spec=MODIFIERS,
            output_model=ModifierOutput,
            payload={"events": event_context(candidates)},
            context=stage_context,
        )
        stage_outputs[current_stage] = modifiers.model_dump(mode="json")

        current_stage = VERIFICATION.name
        verification = _run_stage(
            spec=VERIFICATION,
            output_model=VerificationOutput,
            payload={
                "source_text": selected.source_text,
                "assembled_event_claims": verification_context(
                    candidates,
                    participants,
                    roles,
                    modifiers,
                ),
            },
            context=stage_context,
        )
        stage_outputs[current_stage] = verification.model_dump(mode="json")
        base_assembly = assemble_staged_document(
            AssemblyInputs(
                candidates=candidates,
                participant_output=participants,
                role_output=roles,
                modifier_output=modifiers,
                verification_output=verification,
                document_id=selected.document_id,
                source_text=selected.source_text,
                source_sha256=selected.source_sha256,
                producer_identity=_required_string(model, "identity"),
            )
        )
        gold = _gold_document(repository_root, selected.document_id)
        base_score = score_scientific_event_document(
            gold=gold,
            predicted=base_assembly.document,
        )
        final_assembly = base_assembly
        completion_used = False
        if verification.missing_supported_events:
            current_stage = COMPLETION.name
            missing_candidates = tuple(
                DiscoveryCandidate(
                    trigger_text=item.trigger_text,
                    event_passage=item.event_passage,
                    source_event_type=item.source_event_type,
                    statement_kind=item.statement_kind,
                    explanation="source-only verifier identified a missing event",
                )
                for item in verification.missing_supported_events
            )
            missing_resolution = resolve_discovery_candidates(
                missing_candidates,
                source_text=selected.source_text,
                source_sha256=selected.source_sha256,
            )
            existing_ids = {item.event_id for item in candidates}
            if any(
                item.event_id in existing_ids for item in missing_resolution.candidates
            ):
                _raise_comparison_error(
                    "completion proposed an event already present in discovery"
                )
            completion = _run_stage(
                spec=COMPLETION,
                output_model=CompletionOutput,
                payload={
                    "source_text": selected.source_text,
                    "missing_events": event_context(missing_resolution.candidates),
                    "permitted_existing_event_ids": sorted(existing_ids),
                },
                context=stage_context,
            )
            stage_outputs[current_stage] = completion.model_dump(mode="json")
            completion_parts = completion_stage_outputs(completion)
            participants = ParticipantInventoryOutput(
                inventories=(
                    *participants.inventories,
                    *completion_parts[0].inventories,
                )
            )
            roles = RoleAssignmentOutput(
                events=(*roles.events, *completion_parts[1].events)
            )
            modifiers = ModifierOutput(
                events=(*modifiers.events, *completion_parts[2].events)
            )
            verification = VerificationOutput(
                events=(*verification.events, *completion_parts[3].events),
                missing_supported_events=(),
            )
            candidates = (*candidates, *missing_resolution.candidates)
            final_assembly = assemble_staged_document(
                AssemblyInputs(
                    candidates=candidates,
                    participant_output=participants,
                    role_output=roles,
                    modifier_output=modifiers,
                    verification_output=verification,
                    document_id=selected.document_id,
                    source_text=selected.source_text,
                    source_sha256=selected.source_sha256,
                    producer_identity=_required_string(model, "identity"),
                )
            )
            completion_used = True
        final_score = score_scientific_event_document(
            gold=gold,
            predicted=final_assembly.document,
        )
        completion_unsupported_increase = max(
            0,
            final_score.unsupported_or_invented_events
            - base_score.unsupported_or_invented_events,
        )
        decision = _scientific_decision(
            final_score,
            completion_unsupported_increase=completion_unsupported_increase,
        )
        result = {
            "schema_version": "artana.public_gold.staged_event_result.v2",
            "decision": decision,
            "qualification_status": "EXPOSED_DEVELOPMENT_NON_QUALIFYING",
            "preflight": preflight,
            "source": {
                "document_id": selected.document_id,
                "source_sha256": selected.source_sha256,
            },
            "discovery": {
                "resolved_candidates": len(resolution.candidates),
                "duplicate_candidates": resolution.duplicate_candidates,
            },
            "completion_used": completion_used,
            "completion_unsupported_increase": completion_unsupported_increase,
            "abstentions": final_assembly.abstentions,
            "stage_outputs": stage_outputs,
            "baseline": _required_dict(preregistration, "baseline"),
            "base_score": base_score.as_json(),
            "final_score": final_score.as_json(),
            "accounting": ledger.as_json(),
            "terminal_rules": _terminal_rules(),
            "recommendation": _recommendation(decision),
        }
        _write_artifacts(artifacts, ledger=ledger, result=result)
        return decision  # noqa: TRY300 - terminal artifact is written before return.
    except (ProviderExecutionError, StagedAssemblyError, StagedComparisonError) as exc:
        result = {
            "schema_version": "artana.public_gold.staged_event_result.v2",
            "decision": "INVALID_EXPERIMENT",
            "qualification_status": "EXPOSED_DEVELOPMENT_NON_QUALIFYING",
            "preflight": preflight,
            "failure": {
                "stage": current_stage,
                "boundary": getattr(exc, "stage", type(exc).__name__),
                "root_cause": getattr(exc, "root_cause", str(exc)),
                "diagnostics": getattr(exc, "diagnostics", {}),
            },
            "stage_outputs": stage_outputs,
            "accounting": ledger.as_json(),
            "terminal_rules": _terminal_rules(),
            "recommendation": "REVISE_ONCE",
        }
        _write_artifacts(artifacts, ledger=ledger, result=result)
        return "INVALID_EXPERIMENT"


def _run_stage(
    *,
    spec: StageSpec,
    output_model: type[_OutputT],
    payload: dict[str, object],
    context: StageCallContext,
) -> _OutputT:
    context.ledger.ensure_call_available()
    remaining_tokens, remaining_cost, remaining_latency = context.ledger.remaining()
    if remaining_tokens <= 0 or remaining_cost <= 0 or remaining_latency <= 0:
        raise StagedComparisonError("aggregate budget exhausted before next stage")
    prompt = load_prompt(context.repository_root, spec.prompt_path)
    provider_input = build_stage_input(
        prompt=prompt,
        document_id=context.document_id,
        source_sha256=context.source_sha256,
        payload=payload,
    )
    preregistration_sha256 = _file_sha256(context.preregistration_path)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise StagedComparisonError("OPENAI_API_KEY is absent after preflight")
    execution = execute_background_provider_call(
        api_key=api_key,
        output_model=output_model,
        transport_budgets=BackgroundExecutionBudgets(
            acknowledgement_timeout_seconds=_required_float(
                context.budgets, "acknowledgement_timeout_seconds"
            ),
            polling_interval_seconds=_required_float(
                context.budgets, "polling_interval_seconds"
            ),
            max_polling_seconds=min(
                _required_float(context.budgets, "max_polling_seconds_per_call"),
                remaining_latency,
            ),
        ),
        request=ProviderRequest(
            provider_input=provider_input,
            provider_format=build_provider_format(
                output_model,
                description=spec.description,
            ),
            provider_model_id=_required_string(context.model, "provider_model_id"),
            reasoning_effort=_required_string(context.model, "reasoning_effort"),
            max_output_tokens=_required_int(
                context.budgets, "max_output_tokens_per_call"
            ),
            max_total_tokens=remaining_tokens,
            max_cost_usd=remaining_cost,
            max_latency_seconds=remaining_latency,
            pricing=_pricing(_required_dict(context.budgets, "pricing_usd_per_token")),
            metadata={
                "artana_experiment": "staged-event-comparison-v2",
                "artana_preregistration_sha256": preregistration_sha256,
                "artana_source_sha256": context.source_sha256,
                "artana_stage": spec.name,
            },
        ),
    )
    context.raw_output_directory.mkdir(parents=True, exist_ok=True)
    (context.raw_output_directory / f"{spec.name}.json").write_text(
        json.dumps(
            {
                "acknowledgement": execution.acknowledgement_response,
                "terminal": execution.terminal_response,
                "confirmation": execution.confirmation_response,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    receipt = {
        **execution.receipt,
        "provider_input_sha256": hashlib.sha256(provider_input.encode()).hexdigest(),
        "stage_output_sha256": _canonical_sha256(
            execution.extraction.model_dump(mode="json")
        ),
    }
    context.ledger.record(spec.name, receipt)
    return execution.extraction


def _scientific_decision(
    score: LosslessEventScore,
    *,
    completion_unsupported_increase: int,
) -> str:
    if (
        score.complete_events.matched >= MINIMUM_COMPLETE_EVENTS
        and score.triggers.matched >= MINIMUM_TRIGGERS
        and score.typed_arguments.matched >= MINIMUM_TYPED_ARGUMENTS
        and score.nested_arguments.matched >= MINIMUM_NESTED_ARGUMENTS
        and score.unsupported_or_invented_events <= MAXIMUM_UNSUPPORTED_EVENTS
        and completion_unsupported_increase == 0
    ):
        return "STAGED_METRIC_GATE_PASSED_PENDING_ADJUDICATION"
    return "STAGED_NO_MEANINGFUL_IMPROVEMENT"


def _raise_comparison_error(message: str) -> None:
    raise StagedComparisonError(message)


def _gold_document(repository_root: Path, document_id: str) -> ScientificEventDocument:
    return next(
        item
        for item in project_development_directory(
            repository_root / DEVELOPMENT_DIRECTORY
        )
        if item.document_id == document_id
    )


def _write_artifacts(
    artifacts: ArtifactPaths,
    *,
    ledger: BudgetLedger,
    result: dict[str, object],
) -> None:
    _write_json(artifacts.receipt, ledger.as_json())
    _write_json(artifacts.result, result)
    decision = _required_string(result, "decision")
    if decision not in DECISIONS:
        raise ValueError("invalid terminal decision")
    report = [
        "# Staged Scientific Event Exposed Comparison",
        "",
        f"**Decision:** `{decision}`",
        "",
        "This comparison uses only the exposed PMID-16428936 development source. It does not qualify sealed data, graph writes, or promotion.",
        "",
        "## Accounting",
        "",
        "```json",
        json.dumps(result.get("accounting", {}), indent=2, sort_keys=True),
        "```",
    ]
    if "final_score" in result:
        report.extend(
            [
                "",
                "## Deterministic Comparison",
                "",
                "```json",
                json.dumps(
                    {
                        "baseline": result.get("baseline"),
                        "final_score": result.get("final_score"),
                        "abstentions": result.get("abstentions"),
                        "completion_used": result.get("completion_used"),
                        "completion_unsupported_increase": result.get(
                            "completion_unsupported_increase"
                        ),
                    },
                    indent=2,
                    sort_keys=True,
                ),
                "```",
            ]
        )
    if "failure" in result:
        report.extend(
            [
                "",
                "## Invalidating Failure",
                "",
                "```json",
                json.dumps(result["failure"], indent=2, sort_keys=True),
                "```",
            ]
        )
    report.extend(
        [
            "",
            "## Stage Outputs And Abstentions",
            "",
            "The complete categorical outputs are preserved here so every stage can be audited without consulting raw provider envelopes.",
            "",
            "```json",
            json.dumps(
                {
                    "stage_outputs": result.get("stage_outputs", {}),
                    "abstentions": result.get("abstentions", {}),
                },
                indent=2,
                sort_keys=True,
            ),
            "```",
        ]
    )
    report.extend(
        [
            "",
            "## Recommendation",
            "",
            f"`{result.get('recommendation')}`",
        ]
    )
    artifacts.report.parent.mkdir(parents=True, exist_ok=True)
    artifacts.report.write_text("\n".join(report) + "\n", encoding="utf-8")


def _terminal_rules() -> dict[str, int]:
    return {
        "provider_retries": 0,
        "fallbacks": 0,
        "alternate_models": 0,
        "graph_writes": 0,
        "promotions": 0,
        "sealed_test_sources_accessed": 0,
        "one_shot_baseline_calls": 0,
    }


def _recommendation(decision: str) -> str:
    if decision == "STAGED_METRIC_GATE_PASSED_PENDING_ADJUDICATION":
        return "REQUIRE_SOURCE_VALIDITY_ADJUDICATION"
    if decision == "STAGED_NO_MEANINGFUL_IMPROVEMENT":
        return "ABANDON_THIS_ARCHITECTURE"
    return "REVISE_ONCE"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _required_dict(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be an object")
    return value


def _required_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _required_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a nonnegative integer")
    return value


def _required_float(
    payload: dict[str, object], key: str, *, allow_zero: bool = False
) -> float:
    value = payload.get(key)
    if not isinstance(value, int | float):
        raise TypeError(f"{key} must be a valid number")
    if (allow_zero and value < 0) or (not allow_zero and value <= 0):
        raise ValueError(f"{key} must be a valid number")
    return float(value)


def _pricing(payload: dict[str, object]) -> dict[str, float]:
    return {
        key: _required_float(payload, key)
        for key in ("input", "cached_input", "output")
    }


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--raw-output-directory", type=Path, required=True)
    args = parser.parse_args()
    decision = run_comparison(
        repository_root=repository_root(),
        preregistration_path=args.preregistration,
        artifacts=ArtifactPaths(
            receipt=args.receipt,
            result=args.result,
            report=args.report,
            raw_output_directory=args.raw_output_directory,
        ),
    )
    print(decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
