"""Build and verify the frozen V11 run-2 operational continuation."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, cast

from scripts.validation.public_gold.staged_event.generalization.repair_v11.config import (
    DEFAULT_PATHS as V11_SCIENCE_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11.preflight import (
    ordered_cases as frozen_ordered_cases,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11.preflight import (
    provider_input as frozen_provider_input,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11.preflight import (
    verify as verify_v11,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.accounting import (
    prior_qualification_accounting,
    qualification_accounting,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.artifacts import (
    RUN1_SEALED_SHA256,
    verify_operational_artifacts,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
    EXPERIMENT_ID,
    FOREGROUND_REQUEST_TIMEOUT_SECONDS,
    GLOBAL_MAX_CALLS,
    GLOBAL_MAX_COST_USD,
    MODEL,
    REASONING_EFFORT,
    REPO,
    V11Run2Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.prior_qualification import (
    verify_prior_qualification,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.qualification import (
    QUALIFICATION_PASS,
    verify_qualification_preregistration,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.terminal import (
    BOUNDARY_FAIL_TERMINAL,
    GROUNDING_FAIL_TERMINAL,
    INVALID_TERMINAL,
    PASS_TERMINAL,
    UNRELATED_FAIL_TERMINAL,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.panel import (
        GeneralizationCase,
    )

_IMPLEMENTATION_FILES = (
    "scripts/run_staged_generalization_v11_exposed_run2.py",
    "scripts/validation/public_gold/staged_event/generalization/"
    "repair_v11_run2/__init__.py",
    "scripts/validation/public_gold/staged_event/generalization/"
    "repair_v11_run2/accounting.py",
    "scripts/validation/public_gold/staged_event/generalization/"
    "repair_v11_run2/artifacts.py",
    "scripts/validation/public_gold/staged_event/generalization/"
    "repair_v11_run2/config.py",
    "scripts/validation/public_gold/staged_event/generalization/"
    "repair_v11_run2/fresh_preregistration.py",
    "scripts/validation/public_gold/staged_event/generalization/"
    "repair_v11_run2/preflight.py",
    "scripts/validation/public_gold/staged_event/generalization/"
    "repair_v11_run2/prior_qualification.py",
    "scripts/validation/public_gold/staged_event/generalization/"
    "repair_v11_run2/provider.py",
    "scripts/validation/public_gold/staged_event/generalization/"
    "repair_v11_run2/qualification.py",
    "scripts/validation/public_gold/staged_event/generalization/"
    "repair_v11_run2/reporting.py",
    "scripts/validation/public_gold/staged_event/generalization/"
    "repair_v11_run2/runner.py",
    "scripts/validation/public_gold/staged_event/generalization/"
    "repair_v11_run2/terminal.py",
)
_FOREGROUND_RECEIPT_FILES = (
    "scripts/validation/provider_receipt_boundary/__init__.py",
    "scripts/validation/provider_receipt_boundary/canonical_payload.py",
    "scripts/validation/provider_receipt_boundary/contracts.py",
    "scripts/validation/provider_receipt_boundary/identity.py",
    "scripts/validation/provider_receipt_boundary/operational_accounting_v2.py",
    "scripts/validation/provider_receipt_boundary/structural_diff.py",
    "scripts/validation/provider_receipt_boundary/validation.py",
    "scripts/validation/provider_receipt_boundary/background/contracts.py",
    "scripts/validation/provider_receipt_boundary/foreground/__init__.py",
    "scripts/validation/provider_receipt_boundary/foreground/contracts.py",
    "scripts/validation/provider_receipt_boundary/foreground/execution.py",
    "scripts/validation/provider_receipt_boundary/foreground/validation.py",
)
_QUALIFICATION_ARTIFACT_NAMES = (
    "preregistration",
    "attempt",
    "bundle",
    "receipt",
    "raw_output",
    "result",
)
_REMOTE_REF_FIELD_COUNT = 2


class V11Run2PreflightError(RuntimeError):
    """Run 2 differs from the frozen V11 scientific contract."""


def ordered_cases() -> tuple[GeneralizationCase, ...]:
    """Return the unchanged V11 cases in the preregistered order."""

    cases = frozen_ordered_cases()
    if tuple(case.case_id for case in cases) != CASE_ORDER:
        raise V11Run2PreflightError("V11 run-2 case order changed")
    return cases


def provider_input(case_id: str) -> str:
    """Return the exact run-1 V11 scientific input for one case."""

    return frozen_provider_input(V11_SCIENCE_PATHS, case_id)


def build_preregistration(
    paths: V11Run2Paths = DEFAULT_PATHS,
) -> dict[str, object]:
    """Freeze unchanged science plus the qualified foreground transport."""

    verify_operational_artifacts(paths)
    run1 = verify_v11(V11_SCIENCE_PATHS)
    prior_qualification_result = verify_prior_qualification(paths)
    verify_qualification_preregistration(paths)
    qualification_result = _object(
        json.loads(paths.qualification.result.read_text(encoding="utf-8"))
    )
    if qualification_result.get("decision") != QUALIFICATION_PASS:
        raise V11Run2PreflightError("foreground transport qualification failed")
    qualification = qualification_accounting(qualification_result)
    prior_qualification = prior_qualification_accounting(
        prior_qualification_result
    )
    run1_frozen = _object(run1["frozen_state"])
    if tuple(cast("list[str]", run1_frozen["case_order"])) != CASE_ORDER:
        raise V11Run2PreflightError("run-1 frozen case order changed")
    expected_inputs = _object(run1_frozen["provider_input_sha256_by_case"])
    current_inputs = {
        case_id: hashlib.sha256(provider_input(case_id).encode()).hexdigest()
        for case_id in CASE_ORDER
    }
    if current_inputs != expected_inputs:
        raise V11Run2PreflightError("V11 scientific provider inputs changed")
    qualification_hashes = {
        name: _sha256(getattr(paths.qualification, name))
        for name in _QUALIFICATION_ARTIFACT_NAMES
    }
    return {
        "schema_version": "artana.staged_generalization.v11_exposed_run2.v1",
        "experiment_id": EXPERIMENT_ID,
        "authorization": (
            "PREREGISTERED_V11_OPERATIONAL_CONTINUATION_EXPOSED_CASES_ONLY"
        ),
        "scientific_version": "V11_UNCHANGED",
        "preregistered_root_cause_classification": (
            "SEMANTIC_EVIDENCE_PROMPT_CONTRACT_GAP"
        ),
        "single_scientific_change": (
            "UNIQUE_COMPLETE_SEMANTIC_EVIDENCE_GROUNDING"
        ),
        "operational_change": (
            "BACKGROUND_TO_QUALIFIED_DIRECT_FOREGROUND_RESPONSES"
        ),
        "frozen_scientific_contract": {
            "run1_preregistration_sha256": RUN1_SEALED_SHA256["preregistration"],
            "run1_scientific_contract_recomputed": True,
            "prompt_sha256": run1_frozen["prompt_sha256"],
            "schema_sha256": run1_frozen["schema_sha256"],
            "provider_format_sha256": run1_frozen["provider_format_sha256"],
            "panel_sha256": run1_frozen["panel_sha256"],
            "case_order": list(CASE_ORDER),
            "source_sha256_by_case": run1_frozen["source_sha256_by_case"],
            "provider_input_sha256_by_case": current_inputs,
            "authoritative_references": run1_frozen["authoritative_references"],
            "evaluator": run1_frozen["evaluator"],
            "v9_baseline": run1_frozen["v9_baseline"],
            "v10_baseline": run1_frozen["v10_baseline"],
            "grader_relaxed": False,
            "references_changed": False,
            "acceptance_changed": False,
        },
        "sealed_run1": {
            "disposition": "INVALID_UNSCORED_DIAGNOSTIC_ONLY",
            "late_output_admissible": False,
            "late_output_rescore_authorized": False,
            "sha256_by_role": RUN1_SEALED_SHA256,
            "operational_diagnosis_sha256": _sha256(
                paths.operational_diagnosis
            ),
            "report_correction_sha256": _sha256(paths.report_correction),
        },
        "qualified_transport": {
            "kind": "DIRECT_OPENAI_FOREGROUND_RESPONSES",
            "model": f"openai:{MODEL}",
            "reasoning_effort": REASONING_EFFORT,
            "background": False,
            "store": True,
            "request_timeout_seconds": FOREGROUND_REQUEST_TIMEOUT_SECONDS,
            "one_creation_call_per_scientific_case": True,
            "one_response_id_per_scientific_case": True,
            "one_confirmation_retrieval_per_scientific_case": True,
            "one_input_item_retrieval_per_scientific_case": True,
            "provider_retries": 0,
            "fallback": False,
            "application_max_output_tokens": None,
            "application_max_total_tokens": None,
            "qualification_credit": False,
            "qualification_artifact_sha256": qualification_hashes,
            "qualification_response_id": qualification.response_id,
            "prior_invalid_qualification": {
                "usage_addendum_sha256": _sha256(
                    paths.prior_qualification_usage_addendum
                ),
                "response_id": prior_qualification.response_id,
                "cost_usd": prior_qualification.usage.cost_usd,
                "scientific_credit": False,
            },
            "implementation_sha256": _hash_files(
                REPO,
                _FOREGROUND_RECEIPT_FILES,
            ),
        },
        "execution_implementation_sha256": _hash_files(
            REPO,
            _IMPLEMENTATION_FILES,
        ),
        "operational_budget": {
            "cumulative_max_cost_usd": GLOBAL_MAX_COST_USD,
            "includes_transport_qualification": True,
            "qualification_cost_usd": (
                prior_qualification.usage.cost_usd
                + qualification.usage.cost_usd
            ),
            "qualification_provider_calls": 2,
            "remaining_before_scientific_calls_usd": max(
                GLOBAL_MAX_COST_USD
                - prior_qualification.usage.cost_usd
                - qualification.usage.cost_usd,
                0.0,
            ),
            "maximum_scientific_creation_calls": GLOBAL_MAX_CALLS,
            "check_before_each_creation": True,
            "record_actual_spend_after_each_call": True,
            "stop_before_next_call_when_exhausted": True,
            "token_latency_and_cost_are_record_only": True,
            "scientific_results_are_not_retroactively_erased": True,
        },
        "acceptance": {
            "all_cases_scientific_grader_pass": True,
            "target_case_id": "generalization-uncertainty",
            "required_target_occurrence": "SLC12A3",
            "forbidden_target_suffix_expansion": "SLC12A3 gene",
            "all_semantic_evidence_items_complete_exact_and_unique": True,
            "negated_grounding_case_id": (
                "generalization-negated-association"
            ),
            "negated_semantic_evidence_is_complete_event_sentence": True,
            "no_v9_boolean_or_count_regression": True,
            "no_v10_boolean_or_count_regression": True,
            "all_receipts_valid": True,
            "provider_retries": 0,
            "duplicate_creation_calls": 0,
            "fresh_cases_consumed": 0,
            "graph_writes": 0,
            "trusted_promotion": False,
        },
        "stopping_rules": {
            "sequential_fail_fast": True,
            "first_scientific_failure": True,
            "invalid_schema_custody_or_exactly_once": True,
            "operational_budget_exhaustion": True,
            "provider_outage_or_missing_secret": True,
            "no_prompt_patch_v12_or_third_execution_after_failure": True,
        },
        "terminal_decisions": [
            PASS_TERMINAL,
            BOUNDARY_FAIL_TERMINAL,
            GROUNDING_FAIL_TERMINAL,
            UNRELATED_FAIL_TERMINAL,
            INVALID_TERMINAL,
        ],
        "rules": {
            "fresh_case_calls_allowed": False,
            "run1_case_reused": False,
            "graph_writes": False,
            "trusted_graph_promotion": False,
            "prepare_next_fresh_preregistration_only_on_pass": True,
        },
    }


def write_candidate(paths: V11Run2Paths = DEFAULT_PATHS) -> None:
    paths.preregistration.parent.mkdir(parents=True, exist_ok=True)
    paths.preregistration.write_text(
        json.dumps(build_preregistration(paths), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify(
    paths: V11Run2Paths = DEFAULT_PATHS,
    *,
    remote_gate: bool = False,
) -> dict[str, object]:
    loaded = _object(json.loads(paths.preregistration.read_text(encoding="utf-8")))
    expected = build_preregistration(paths)
    if loaded != expected:
        raise V11Run2PreflightError(
            "V11 run-2 preregistration differs from frozen state"
        )
    if remote_gate:
        _verify_remote_head()
    return loaded


def _verify_remote_head() -> None:
    branch = _git("branch", "--show-current")
    local = _git("rev-parse", "HEAD")
    remote = _git("ls-remote", "--heads", "origin", branch).split()
    if (
        not branch
        or len(remote) != _REMOTE_REF_FIELD_COUNT
        or remote[0] != local
    ):
        raise V11Run2PreflightError(
            "local and remote heads differ before V11 run-2 execution"
        )


def _git(*arguments: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed local Git executable.
        ["git", *arguments],  # noqa: S607
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise V11Run2PreflightError(completed.stderr.strip())
    return completed.stdout.strip()


def _hash_files(root: Path, names: tuple[str, ...]) -> dict[str, str]:
    return {name: _sha256(root / name) for name in names}


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise V11Run2PreflightError("expected JSON object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "V11Run2PreflightError",
    "build_preregistration",
    "ordered_cases",
    "provider_input",
    "verify",
    "write_candidate",
]
