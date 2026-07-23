"""Build and verify the forward-only Fresh-CG V2 preregistration."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.provider import (
    provider_format,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.provider_contract import (
    FreshCGProviderOutput,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.provider_input import (
    provider_input,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.review_contracts import (
    FreshCGReviewPacket,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.review_packets import (
    build_review_packet,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.config import (
    BRANCH,
    CONSUMED_CASE_ID,
    EXPERIMENT_ID,
    GLOBAL_MAX_CALLS,
    GLOBAL_MAX_COST_USD,
    MODEL,
    REASONING_EFFORT,
    V1_ATTEMPT_SHA256,
    V1_PREREGISTRATION_SHA256,
    V1_REPORT_SHA256,
    V1_RESULT_SHA256,
    ExperimentPaths,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.review import (
    build_reference,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.selection import (
    load_v2_selection,
)
from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.contracts import (
    OccurrenceAwareBindings,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.contracts import (
        FreshCGSelection,
    )


def _git_executable() -> str:
    value = shutil.which("git")
    if value is None:  # pragma: no cover - repository execution requires Git.
        raise RuntimeError("git executable was not found")
    return value


REPO = Path(__file__).resolve().parents[6]
GIT = _git_executable()
V2_PACKAGE = REPO / (
    "scripts/validation/public_gold/staged_event/generalization/fresh_cg_v2"
)
OCCURRENCE_PACKAGE = REPO / (
    "scripts/validation/public_gold/staged_event/generalization/occurrence_evaluator_v2"
)
V1_SEALED_PATHS = {
    "preregistration": REPO
    / "docs/validation/preregistrations/2026-07-22-fresh-cg-occurrence-v2-v1.json",
    "attempt": REPO
    / (
        "docs/validation/receipts/"
        "2026-07-22-fresh-cg-occurrence-v2-v1-"
        "fresh-cg-pmid-21963494-e3-attempt.json"
    ),
    "result": REPO
    / "docs/validation/results/2026-07-22-fresh-cg-occurrence-v2-v1.json",
    "report": REPO
    / "docs/validation/reports/2026-07-22-fresh-cg-occurrence-v2-v1-final.md",
}
V1_SEALED_HASHES = {
    "preregistration": V1_PREREGISTRATION_SHA256,
    "attempt": V1_ATTEMPT_SHA256,
    "result": V1_RESULT_SHA256,
    "report": V1_REPORT_SHA256,
}
_ALLOWED_DIRTY_PATHS = (
    "coverage.xml",
    "docs/validation/reports/2026-07-17-tg04-work-summary-and-current-plan.md",
    "uv.lock",
    "validation/",
)
_REGRESSION_NODE_IDS = (
    "tests/unit/test_fresh_cg_v2.py::test_v2_request_omits_output_ceiling",
    "tests/unit/test_fresh_cg_v2.py::test_large_usage_is_scientifically_record_only",
    "tests/unit/test_fresh_cg_v2.py::test_budget_stop_prevents_the_next_call",
    "tests/unit/test_fresh_cg_v2.py::test_v1_artifacts_remain_byte_identical",
    "tests/unit/test_occurrence_evaluator_v2.py::"
    "test_v2_preserves_every_frozen_panel_reference_without_relaxing_science",
)


class FreshCGV2PreflightError(RuntimeError):
    """V2 differs from its frozen scientific or operational contract."""


def build_preregistration(paths: ExperimentPaths) -> dict[str, object]:
    selection = load_v2_selection(paths.selection)
    _verify_review_packet(paths, selection)
    reference = build_reference(paths, include_tiebreaker=True)
    loaded_reference = type(reference).model_validate_json(
        paths.reference.read_text(encoding="utf-8")
    )
    if loaded_reference != reference:
        raise FreshCGV2PreflightError("two-lane V2 reference changed")
    if reference.unresolved_field_ids:
        raise FreshCGV2PreflightError("source-semantic reference remains incomplete")
    _verify_v1_sealed()
    return {
        "schema_version": "artana.staged_generalization.fresh_cg_preregistration.v2",
        "experiment_id": EXPERIMENT_ID,
        "authorization": "REMOTE_PARITY_REQUIRED_BEFORE_PROVIDER",
        "scientific_change": "NONE",
        "instrumentation_change": "ABSOLUTE_SOURCE_OCCURRENCE_BINDINGS_V2",
        "operational_policy_change": (
            "RECORD_ONLY_USAGE_WITH_CUMULATIVE_5_USD_PRECALL_STOP"
        ),
        "frozen_state": {
            "selection_artifact_sha256": _file_sha256(paths.selection),
            "replacement_review_packet_sha256": _file_sha256(
                paths.replacement_review_packet
            ),
            "review_packet_sha256": _file_sha256(paths.review_packet),
            "review_prompt_sha256": _file_sha256(paths.review_prompt),
            "review_schema_sha256": _file_sha256(paths.review_schema),
            "replacement_review_schema_sha256": _file_sha256(
                paths.replacement_review_schema
            ),
            "reviewer_artifact_sha256_by_id": {
                "fresh-cg-reviewer-a": _file_sha256(paths.reviewer_a),
                "fresh-cg-reviewer-b": _file_sha256(paths.reviewer_b),
                "fresh-cg-tiebreaker": _file_sha256(paths.tiebreaker),
            },
            "replacement_reviewer_fragment_sha256_by_id": {
                "fresh-cg-reviewer-a": _file_sha256(paths.replacement_reviewer_a),
                "fresh-cg-reviewer-b": _file_sha256(paths.replacement_reviewer_b),
                "fresh-cg-tiebreaker": _file_sha256(paths.replacement_tiebreaker),
            },
            "tiebreak_request_sha256": _file_sha256(paths.tiebreak_request),
            "two_lane_reference_sha256": _file_sha256(paths.reference),
            "unresolved_reference_fields": [],
            "case_order": list(reference.case_order),
            "consumed_v1_case_id": CONSUMED_CASE_ID,
            "consumed_v1_case_reused": False,
            "source_sha256_by_case": {
                case.case_id: case.source_sha256 for case in selection.cases
            },
            "direct_cg_reference_sha256_by_case": {
                case.case_id: case.direct_cg_reference_sha256
                for case in selection.cases
            },
            "provider_input_sha256_by_case": {
                case.case_id: hashlib.sha256(
                    provider_input(
                        case,
                        scientific_prompt_path=paths.scientific_prompt,
                        binding_prompt_path=paths.binding_prompt,
                    ).encode()
                ).hexdigest()
                for case in selection.cases
            },
            "occurrence_evaluator_version": (
                "artana.staged_generalization.occurrence_evaluator.v2"
            ),
            "occurrence_evaluator_package_sha256": _package_sha256(OCCURRENCE_PACKAGE),
            "binding_schema_version": (
                "artana.staged_generalization.occurrence_bindings.v2"
            ),
            "binding_schema_sha256": _canonical_sha256(
                OccurrenceAwareBindings.model_json_schema()
            ),
            "v9_scientific_schema_sha256": _canonical_sha256(
                V9StagedGeneralizationOutput.model_json_schema()
            ),
            "v9_scientific_prompt_sha256": _file_sha256(paths.scientific_prompt),
            "combined_provider_schema_sha256": _canonical_sha256(
                FreshCGProviderOutput.model_json_schema()
            ),
            "provider_format_sha256": _canonical_sha256(provider_format()),
            "v1_sealed_artifact_sha256_by_role": dict(V1_SEALED_HASHES),
            "code_sha256_by_path": _code_hashes(),
            "model": f"openai:{MODEL}",
            "reasoning_effort": REASONING_EFFORT,
            "operational_budget": {
                "global_max_creation_calls": GLOBAL_MAX_CALLS,
                "global_max_cost_usd": GLOBAL_MAX_COST_USD,
                "application_max_output_tokens": None,
                "total_token_limit": None,
                "per_call_cost_limit": None,
                "usage_affects_scientific_scoring": False,
                "silent_retries": 0,
                "provider_retries": 0,
            },
        },
        "review_governance": {
            "primary_reviewer_ids": list(reference.primary_reviewer_ids),
            "tiebreaker_reviewer_id": reference.tiebreaker_reviewer_id,
            "replacement_independently_reviewed": True,
            "primary_answers_disclosed_to_tiebreaker": False,
            "review_only_scoring": "NO_AUTOMATIC_CREDIT_OR_PENALTY",
        },
        "execution_rules": {
            "case_order_immutable": True,
            "one_creation_call_per_case": True,
            "confirmation_retrieval_required": True,
            "stop_before_next_on_first_scientific_failure": True,
            "stop_before_next_when_cumulative_cost_reaches_budget": True,
            "completed_case_science_survives_operational_stop": True,
            "token_count_answer_length_latency_and_cost_are_record_only": True,
            "fallback": False,
            "manual_output_repair": False,
            "historical_rescoring": False,
            "graph_writes": False,
            "promotion": False,
            "qualification": False,
        },
        "precall_gates": {
            "offline_regression_node_ids": list(_REGRESSION_NODE_IDS),
            "remote_branch": BRANCH,
            "local_head_must_equal_remote_head": True,
            "preregistration_must_be_tracked_at_head": True,
            "preserved_unrelated_dirty_paths": list(_ALLOWED_DIRTY_PATHS),
        },
    }


def write_candidate(paths: ExperimentPaths) -> None:
    paths.preregistration.parent.mkdir(parents=True, exist_ok=True)
    paths.preregistration.write_text(
        json.dumps(build_preregistration(paths), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify(
    paths: ExperimentPaths,
    *,
    remote_gate: bool,
    offline_regression: bool,
) -> dict[str, object]:
    loaded: object = json.loads(paths.preregistration.read_text(encoding="utf-8"))
    expected = build_preregistration(paths)
    if loaded != expected:
        raise FreshCGV2PreflightError(
            "preregistration differs from independently recomputed frozen state"
        )
    if not isinstance(loaded, dict):
        raise FreshCGV2PreflightError("preregistration must be a JSON object")
    if offline_regression:
        _verify_offline_regression()
    if remote_gate:
        _verify_remote_gate(paths)
    return loaded


def _verify_review_packet(
    paths: ExperimentPaths,
    selection: object,
) -> FreshCGReviewPacket:
    expected = build_review_packet(
        cast("FreshCGSelection", selection),
        selection_artifact_sha256=_file_sha256(paths.selection),
    )
    loaded = FreshCGReviewPacket.model_validate_json(
        paths.review_packet.read_text(encoding="utf-8")
    )
    if loaded != expected:
        raise FreshCGV2PreflightError("blinded reviewer packet changed")
    return loaded


def _verify_v1_sealed() -> None:
    actual = {key: _file_sha256(path) for key, path in V1_SEALED_PATHS.items()}
    if actual != V1_SEALED_HASHES:
        raise FreshCGV2PreflightError("sealed V1 artifacts changed")


def _verify_offline_regression() -> None:
    completed = subprocess.run(  # noqa: S603 - fixed local test command.
        [sys.executable, "-m", "pytest", "-q", *_REGRESSION_NODE_IDS],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
        timeout=240,
    )
    if completed.returncode != 0:
        output = (completed.stdout + completed.stderr)[-4000:]
        raise FreshCGV2PreflightError(f"V2 offline regression failed:\n{output}")


def _verify_remote_gate(paths: ExperimentPaths) -> None:
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    if branch != BRANCH:
        raise FreshCGV2PreflightError(f"wrong execution branch: {branch}")
    head = _git("rev-parse", "HEAD")
    remote = _git("ls-remote", "--heads", "origin", f"refs/heads/{BRANCH}")
    remote_head = remote.split()[0] if remote else ""
    if head != remote_head:
        raise FreshCGV2PreflightError(
            "local HEAD does not equal live remote branch head"
        )
    relative = paths.preregistration.relative_to(REPO).as_posix()
    tracked = subprocess.run(  # noqa: S603 - fixed local Git read.
        [GIT, "show", f"HEAD:{relative}"],
        cwd=REPO,
        check=False,
        capture_output=True,
    )
    if tracked.returncode != 0 or tracked.stdout != paths.preregistration.read_bytes():
        raise FreshCGV2PreflightError(
            "remote-parity HEAD does not contain preregistration"
        )
    unexpected = [
        path
        for path in _dirty_paths()
        if not any(
            path == allowed.rstrip("/") or path.startswith(allowed)
            for allowed in _ALLOWED_DIRTY_PATHS
        )
    ]
    if unexpected:
        raise FreshCGV2PreflightError(
            f"experiment files differ from committed HEAD: {unexpected}"
        )


def _dirty_paths() -> tuple[str, ...]:
    completed = subprocess.run(  # noqa: S603 - fixed Git status command.
        [GIT, "status", "--porcelain=v1", "--untracked-files=normal"],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise FreshCGV2PreflightError(f"git status failed: {completed.stderr.strip()}")
    return tuple(line[3:].split(" -> ")[-1] for line in completed.stdout.splitlines())


def _git(*arguments: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed Git executable.
        [GIT, *arguments],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise FreshCGV2PreflightError(
            f"git {' '.join(arguments)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _code_hashes() -> dict[str, str]:
    files = list(V2_PACKAGE.glob("*.py"))
    files.extend(
        (
            REPO / "scripts/run_fresh_cg_occurrence_v2_v2.py",
            REPO / "scripts/validation/provider_receipt_boundary/contracts.py",
            REPO / "scripts/validation/provider_receipt_boundary/validation.py",
            REPO
            / "scripts/validation/provider_receipt_boundary/background/contracts.py",
            REPO
            / "scripts/validation/provider_receipt_boundary/background/execution.py",
        )
    )
    return {
        path.relative_to(REPO).as_posix(): _file_sha256(path) for path in sorted(files)
    }


def _package_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.glob("*.py")):
        digest.update(item.relative_to(REPO).as_posix().encode())
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "FreshCGV2PreflightError",
    "build_preregistration",
    "verify",
    "write_candidate",
]
