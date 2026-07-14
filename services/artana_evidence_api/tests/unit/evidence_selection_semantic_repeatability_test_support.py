"""Test builders for source-locked semantic model comparisons."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from artana_evidence_api.evidence_selection.diagnostics.agent_evaluation import (
    evaluate_semantic_selection_agent,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.contracts import (
    EvidenceSelectionBenchmarkEvaluation,
    EvidenceSelectionBenchmarkRecordEvaluation,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.evaluation import (
    evaluate_benchmark_v2,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.loader import (
    load_benchmark_v2,
)
from artana_evidence_api.evidence_selection.diagnostics.fixture import (
    EvidenceSelectionSemanticDiagnosticFixture,
    load_semantic_diagnostic_fixture,
)
from artana_evidence_api.evidence_selection.diagnostics.report import (
    EvidenceSelectionSemanticDiagnosticReport,
)
from artana_evidence_api.evidence_selection.repeatability.artifacts import (
    write_json_model,
)
from artana_evidence_api.evidence_selection.repeatability.contracts import (
    SemanticModelComparisonProtocol,
    SemanticModelEvaluationRun,
    SemanticModelRole,
    SemanticRunTelemetry,
    SemanticRuntimeLedgerObservation,
    SemanticRuntimeTerminalEvent,
    SemanticWallClockObservation,
    aggregate_semantic_terminal_events,
    semantic_terminal_events_sha256,
)
from artana_evidence_api.evidence_selection.repeatability.protocol import (
    build_semantic_model_comparison_protocol,
    build_semantic_model_evaluation_run,
    sha256_path,
)
from artana_evidence_api.evidence_selection.repeatability.source_provenance import (
    build_repository_source_files,
)
from artana_evidence_api.evidence_selection.semantic.contracts import (
    EvidenceSelectionSemanticBatchContract,
    EvidenceSelectionSemanticCandidateAssessment,
)
from artana_evidence_api.evidence_selection.semantic.evidence import (
    semantic_evidence_options,
)
from artana_evidence_api.evidence_selection.semantic.model import (
    EvidenceSelectionSemanticContext,
)
from artana_evidence_api.evidence_selection.semantic.references import (
    semantic_record_reference,
)
from artana_evidence_api.types.common import JSONObject

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
FIXTURE_PATH = (
    REPOSITORY_ROOT
    / "scripts/validation/evidence_selection/fixtures/semantic_relevance_failure_corpus_v1.json"
)
BASELINE_PATH = (
    REPOSITORY_ROOT
    / "docs/validation/reports/2026-07-11-pr-semantic-pr1-failure-corpus-baseline.json"
)
BENCHMARK_V2_PATH = (
    REPOSITORY_ROOT
    / "scripts/validation/evidence_selection/fixtures/semantic_relevance_benchmark_v2.json"
)
CURRENT_MODEL = "openai:current-semantic-model"
CANDIDATE_MODEL = "openai:candidate-semantic-model"


class ExpectedLabelRunner:
    """Return fixture labels as grounded categories with optional abstention."""

    def __init__(
        self,
        *,
        fixture: EvidenceSelectionSemanticDiagnosticFixture,
        model_id: str,
        abstain_record_ids: frozenset[str] = frozenset(),
        execution_prefix: str,
    ) -> None:
        self._expected_by_source_title = {
            (case.source_run_id, record.title): (
                record.record_id,
                record.expected_label,
            )
            for case in fixture.cases
            for record in case.records
        }
        self._model_id = model_id
        self._abstain_record_ids = abstain_record_ids
        self._execution_prefix = execution_prefix
        self._call_count = 0
        self._execution_ids: list[str] = []

    async def assess(
        self,
        *,
        context: EvidenceSelectionSemanticContext,
    ) -> EvidenceSelectionSemanticBatchContract:
        self._call_count += 1
        assessments: list[EvidenceSelectionSemanticCandidateAssessment] = []
        for index, record in zip(
            context.record_indices,
            context.records,
            strict=True,
        ):
            title = str(record["title"])
            record_id, expected = self._expected_by_source_title[
                (context.search_id, title)
            ]
            decision = "review" if record_id in self._abstain_record_ids else expected
            assessments.append(
                _assessment(
                    context=context,
                    index=index,
                    record=record,
                    decision=decision,
                ),
            )
        run_id = f"{self._execution_prefix}-batch-{self._call_count}"
        self._execution_ids.append(run_id)
        return EvidenceSelectionSemanticBatchContract(
            schema_version="evidence_selection_semantic_agent.v2",
            agent_run_id=run_id,
            reasoning_summary=(
                "Each record was compared categorically with every selection criterion."
            ),
            assessments=tuple(assessments),
        )

    def model_id(self) -> str | None:
        return self._model_id

    def execution_ids(self) -> tuple[str, ...]:
        return tuple(self._execution_ids)


async def build_model_runs(
    *,
    tmp_path: Path,
    fixture: EvidenceSelectionSemanticDiagnosticFixture,
    protocol: SemanticModelComparisonProtocol,
    role: SemanticModelRole,
    abstain_record_ids: frozenset[str] = frozenset(),
    abstain_record_ids_by_run: tuple[frozenset[str], ...] | None = None,
    telemetry_status: str = "available",
    cost_per_run: float = 0.01,
    latency_per_run: float = 1.0,
) -> tuple[SemanticModelEvaluationRun, ...]:
    """Build complete repeated runs through the production diagnostic scorer."""

    model_id = (
        protocol.current_model_id if role == "current" else protocol.candidate_model_id
    )
    if (
        abstain_record_ids_by_run is not None
        and len(abstain_record_ids_by_run) != protocol.runs_per_model
    ):
        raise ValueError("per-run abstention sets must match protocol runs_per_model")
    runs: list[SemanticModelEvaluationRun] = []
    for run_index in range(1, protocol.runs_per_model + 1):
        run_abstentions = (
            abstain_record_ids
            if abstain_record_ids_by_run is None
            else abstain_record_ids_by_run[run_index - 1]
        )
        runner = ExpectedLabelRunner(
            fixture=fixture,
            model_id=model_id,
            abstain_record_ids=run_abstentions,
            execution_prefix=f"{role}-{run_index}",
        )
        evaluation = await evaluate_semantic_selection_agent(
            fixture_path=FIXTURE_PATH,
            fixture=fixture,
            runner=runner,
            evaluated_commit=protocol.evaluated_commit,
            generated_at=datetime(2026, 7, 13, run_index, tzinfo=UTC),
            baseline_report_path=BASELINE_PATH,
            baseline_precision=0.2381,
            baseline_end_to_end_recall=0.3846,
            minimum_precision=0.8,
            minimum_end_to_end_recall=0.8,
        )
        path = tmp_path / f"{role}-run-{run_index}.json"
        write_json_model(path=path, model=evaluation)
        execution_ids = tuple(
            sorted(
                {
                    result.agent_run_id
                    for result in evaluation.record_results
                    if result.agent_run_id != "invalid_agent"
                },
            ),
        )
        telemetry = _telemetry(
            execution_ids=execution_ids,
            model_id=model_id,
            status=telemetry_status,
            cost_usd=cost_per_run,
            latency_seconds=latency_per_run,
        )
        runs.append(
            build_semantic_model_evaluation_run(
                role=role,
                run_index=run_index,
                evaluation_path=path,
                evaluation=evaluation,
                benchmark_evaluation=protocol.benchmark_evaluation,
                telemetry=telemetry,
            ),
        )
    return tuple(runs)


def comparison_protocol(
    *, pending_benchmark: bool = False
) -> SemanticModelComparisonProtocol:
    """Return the standard strict protocol used by unit tests."""

    fixture = load_semantic_diagnostic_fixture(FIXTURE_PATH)
    baseline = EvidenceSelectionSemanticDiagnosticReport.model_validate_json(
        BASELINE_PATH.read_text(encoding="utf-8"),
    )
    benchmark = load_benchmark_v2(
        fixture_path=BENCHMARK_V2_PATH,
        repository_root=REPOSITORY_ROOT,
    )
    benchmark_evaluation = (
        evaluate_benchmark_v2(benchmark)
        if pending_benchmark
        else _synthetic_externally_attested_evaluation(
            fixture, benchmark.fixture_sha256
        )
    )
    return build_semantic_model_comparison_protocol(
        generated_at=datetime(2026, 7, 13, tzinfo=UTC),
        evaluated_commit="a" * 40,
        trusted_mainline_ref="origin/main",
        trusted_mainline_commit="a" * 40,
        required_mainline_commit="a" * 40,
        fixture_path=FIXTURE_PATH,
        fixture_sha256=sha256_path(FIXTURE_PATH),
        benchmark_fixture_path=BENCHMARK_V2_PATH,
        benchmark_fixture_sha256=benchmark.fixture_sha256,
        benchmark_evaluation=benchmark_evaluation,
        baseline_report_path=BASELINE_PATH,
        baseline_report_sha256=sha256_path(BASELINE_PATH),
        repository_source_files=build_repository_source_files(
            fixture=fixture,
            baseline=baseline,
            benchmark=benchmark,
            repository_root=REPOSITORY_ROOT,
        ),
        current_model_id=CURRENT_MODEL,
        candidate_model_id=CANDIDATE_MODEL,
        runs_per_model=3,
    )


def _synthetic_externally_attested_evaluation(
    fixture: EvidenceSelectionSemanticDiagnosticFixture,
    fixture_sha256: str,
) -> EvidenceSelectionBenchmarkEvaluation:
    """Test-only eligible labels used to exercise policy branches."""

    return EvidenceSelectionBenchmarkEvaluation(
        fixture_sha256=fixture_sha256,
        historical_v1_sha256=sha256_path(FIXTURE_PATH),
        source_packet_manifest_sha256=(
            "1ef9e6a3ff1e4f9a2bd9bade5107d9951704bb2bf412bcf8ee00c9b6ffd492d2"
        ),
        expert_study_status="externally_attested",
        records=tuple(
            EvidenceSelectionBenchmarkRecordEvaluation(
                case_id=case.case_id,
                display_name=case.display_name,
                evaluation_role=case.evaluation_role,
                record_id=record.record_id,
                diagnostic_decision=record.expected_label,
                diagnostic_rationale="Synthetic test-only external attestation.",
                eligibility_status="score_eligible",
                score_eligible=True,
                expert_label=record.expected_label,
                exclusion_reasons=(),
            )
            for case in fixture.cases
            for record in case.records
        ),
    )


def load_fixture() -> EvidenceSelectionSemanticDiagnosticFixture:
    return load_semantic_diagnostic_fixture(FIXTURE_PATH)


def _assessment(
    *,
    context: EvidenceSelectionSemanticContext,
    index: int,
    record: JSONObject,
    decision: str,
) -> EvidenceSelectionSemanticCandidateAssessment:
    record_ref = semantic_record_reference(
        source_key=context.source_key,
        search_id=context.search_id,
        record_index=index,
        record=record,
    )
    payload: JSONObject = {
        "record_ref": record_ref,
        "decision": decision,
        "objective_match": "direct",
        "entity_variant_match": "match",
        "population_match": "match",
        "intervention_match": "not_required",
        "outcome_match": "match",
        "study_type_match": "match",
        "inclusion_assessment": "met",
        "exclusion_assessment": "not_triggered",
        "explanation": "Categorical fixture judgment grounded in the record.",
        "evidence_references": [
            semantic_evidence_options(
                record_ref=record_ref,
                record=record,
            )[0].reference,
        ],
    }
    if decision == "reject":
        payload["objective_match"] = "off_objective"
        payload["entity_variant_match"] = "no_match"
    if decision == "review":
        payload["objective_match"] = "uncertain"
        payload["inclusion_assessment"] = "uncertain"
    return EvidenceSelectionSemanticCandidateAssessment.model_validate(payload)


def _telemetry(
    *,
    execution_ids: tuple[str, ...],
    model_id: str,
    status: str,
    cost_usd: float,
    latency_seconds: float,
) -> SemanticRunTelemetry:
    event_count = len(execution_ids)
    cost_values = _split_float(cost_usd, event_count)
    elapsed_values = _split_int(round(latency_seconds * 1000), event_count)
    terminal_events = tuple(
        SemanticRuntimeTerminalEvent(
            execution_id=execution_id,
            outcome="completed",
            model_id=model_id,
            model_cycle_id=f"cycle-{execution_id}",
            source_model_requested_event_id=f"request-{execution_id}",
            elapsed_ms=elapsed_values[index],
            prompt_tokens=1000,
            completion_tokens=200,
            cost_usd=cost_values[index] if status == "available" else None,
            cost_derivation=(
                "provider_reported" if status == "available" else "unavailable"
            ),
        )
        for index, execution_id in enumerate(execution_ids)
    )
    aggregate = aggregate_semantic_terminal_events(terminal_events)
    ledger_payload: JSONObject = {
        "status": status,
        "expected_model_id": model_id,
        "execution_ids": execution_ids,
        "model_terminal_count": len(execution_ids),
        "terminal_events": tuple(
            event.model_dump(mode="json") for event in terminal_events
        ),
        "terminal_events_sha256": semantic_terminal_events_sha256(terminal_events),
        "prompt_tokens": aggregate.prompt_tokens,
        "completion_tokens": aggregate.completion_tokens,
        "total_tokens": aggregate.total_tokens,
        "cost_usd": aggregate.cost_usd,
        "model_latency_seconds": aggregate.model_latency_seconds,
        "cost_derivation": aggregate.cost_derivation,
    }
    return SemanticRunTelemetry(
        ledger=SemanticRuntimeLedgerObservation.model_validate(ledger_payload),
        wall_clock=SemanticWallClockObservation(
            execution_ids=execution_ids,
            elapsed_seconds=latency_seconds + 0.2,
        ),
    )


def _split_float(total: float, count: int) -> tuple[float, ...]:
    if count <= 0:
        return ()
    base = round(total / count, 8)
    values = [base] * count
    values[-1] = round(total - sum(values[:-1]), 8)
    return tuple(values)


def _split_int(total: int, count: int) -> tuple[int, ...]:
    if count <= 0:
        return ()
    quotient, remainder = divmod(total, count)
    return tuple(quotient + (1 if index < remainder else 0) for index in range(count))


__all__ = [
    "BASELINE_PATH",
    "BENCHMARK_V2_PATH",
    "CANDIDATE_MODEL",
    "CURRENT_MODEL",
    "FIXTURE_PATH",
    "ExpectedLabelRunner",
    "build_model_runs",
    "comparison_protocol",
    "load_fixture",
]
