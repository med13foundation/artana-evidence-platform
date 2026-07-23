"""Build and verify the fail-closed fresh-CG preregistration."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.agreement import (
    ReferenceBuildInputs,
    ReviewArtifactInput,
    build_two_lane_reference,
    load_reviewer_artifact,
    write_two_lane_reference,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.config import (
    BRANCH,
    EXPERIMENT_ID,
    GLOBAL_MAX_CALLS,
    GLOBAL_MAX_COST_USD,
    MAX_COST_USD,
    MAX_LATENCY_SECONDS,
    MAX_OUTPUT_TOKENS,
    MAX_TOTAL_TOKENS,
    MODEL,
    REASONING_EFFORT,
    ExperimentPaths,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.provider import (
    provider_format,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.provider_contract import (
    FreshCGProviderOutput,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.provider_input import (
    provider_input,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.reference_contracts import (
    FreshCGTwoLaneReference,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.review_contracts import (
    FreshCGReviewerArtifact,
    FreshCGReviewPacket,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.review_packets import (
    build_review_packet,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.selection import (
    load_frozen_selection,
)
from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.contracts import (
    OccurrenceAwareBindings,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)


def _resolve_git_executable() -> str:
    executable = shutil.which("git")
    if executable is None:  # pragma: no cover - repository execution requires Git.
        raise RuntimeError("git executable was not found")
    return executable


REPO = Path(__file__).resolve().parents[6]
GIT = _resolve_git_executable()
V9_PANEL = REPO / "docs/validation/fixtures/2026-07-22-staged-generalization-panel-v9.json"
OCCURRENCE_PACKAGE = REPO / (
    "scripts/validation/public_gold/staged_event/generalization/occurrence_evaluator_v2"
)
EXPECTED_OCCURRENCE_PACKAGE_SHA256 = (
    "610198ea76396485bf61bd16828402d1fd0ecb38e6565b3d0ce6367c110dd5d1"
)
EXPECTED_BINDING_SCHEMA_SHA256 = (
    "0db47c685c1d6e5dddf644891010cbda3b7694b2de55bf6052cb7856a8ecf68e"
)
EXPECTED_V9_SCHEMA_SHA256 = (
    "02594c4ce1cb089e1b23da0495269a8b457f68b3e57396f345a2258a94eb57c1"
)
EXPECTED_V9_PROMPT_SHA256 = (
    "4ce450b6a79fdb0cb99c48a69eae1390beef21dcf0094099503c03bdb4dd9234"
)
EXPECTED_V9_PANEL_SHA256 = (
    "00dad3d580755a1c2268e1db32e8ccd1d50771b4a8861138eb18f6593e8e188e"
)
_ALLOWED_DIRTY_PATHS = (
    "coverage.xml",
    "docs/validation/reports/2026-07-17-tg04-work-summary-and-current-plan.md",
    "uv.lock",
    "validation/",
)
_REGRESSION_NODE_IDS = (
    "tests/unit/test_occurrence_evaluator_v2.py::"
    "test_v2_preserves_every_frozen_panel_reference_without_relaxing_science",
    "tests/unit/test_occurrence_evaluator_v2.py::"
    "test_sealed_v5_v9_files_retain_their_pre_v2_bytes",
)


class FreshCGPreflightError(RuntimeError):
    """The fresh experiment is incomplete or differs from its frozen state."""


def build_preregistration(paths: ExperimentPaths) -> dict[str, object]:
    selection = load_frozen_selection(paths.selection)
    packet = _verify_review_packet(paths, selection)
    reference = _verify_reference(paths, selection, packet)
    if reference.unresolved_field_ids:
        raise FreshCGPreflightError("source-semantic reference remains incomplete")
    evaluator_sha256 = _package_sha256(OCCURRENCE_PACKAGE)
    binding_schema_sha256 = _canonical_sha256(
        OccurrenceAwareBindings.model_json_schema()
    )
    v9_schema_sha256 = _canonical_sha256(
        V9StagedGeneralizationOutput.model_json_schema()
    )
    if evaluator_sha256 != EXPECTED_OCCURRENCE_PACKAGE_SHA256:
        raise FreshCGPreflightError("occurrence evaluator V2 package changed")
    if binding_schema_sha256 != EXPECTED_BINDING_SCHEMA_SHA256:
        raise FreshCGPreflightError("occurrence binding V2 schema changed")
    if v9_schema_sha256 != EXPECTED_V9_SCHEMA_SHA256:
        raise FreshCGPreflightError("V9 scientific schema changed")
    if _file_sha256(paths.scientific_prompt) != EXPECTED_V9_PROMPT_SHA256:
        raise FreshCGPreflightError("V9 scientific prompt changed")
    if _file_sha256(V9_PANEL) != EXPECTED_V9_PANEL_SHA256:
        raise FreshCGPreflightError("V9 regression panel changed")
    review_schema: object = json.loads(paths.review_schema.read_text(encoding="utf-8"))
    if review_schema != FreshCGReviewerArtifact.model_json_schema():
        raise FreshCGPreflightError("reviewer schema differs from its strict contract")
    reviewers = tuple(
        load_reviewer_artifact(path)
        for path in (paths.reviewer_a, paths.reviewer_b, paths.tiebreaker)
    )
    expected_reviewer_ids = (
        "fresh-cg-reviewer-a",
        "fresh-cg-reviewer-b",
        "fresh-cg-tiebreaker",
    )
    if tuple(item.reviewer_id for item in reviewers) != expected_reviewer_ids:
        raise FreshCGPreflightError("reviewer identities changed")
    if len({item.reviewer_task_identity for item in reviewers}) != len(reviewers):
        raise FreshCGPreflightError("reviewer task identities are not independent")
    return {
        "schema_version": "artana.staged_generalization.fresh_cg_preregistration.v1",
        "experiment_id": EXPERIMENT_ID,
        "authorization": "REMOTE_PARITY_REQUIRED_BEFORE_PROVIDER",
        "scientific_change": "NONE",
        "instrumentation_change": "ABSOLUTE_SOURCE_OCCURRENCE_BINDINGS_V2",
        "frozen_state": {
            "selection_artifact_sha256": _file_sha256(paths.selection),
            "review_packet_sha256": _file_sha256(paths.review_packet),
            "review_prompt_sha256": _file_sha256(paths.review_prompt),
            "review_schema_sha256": _file_sha256(paths.review_schema),
            "reviewer_artifact_sha256_by_id": {
                reviewer.reviewer_id: _file_sha256(path)
                for reviewer, path in zip(
                    reviewers,
                    (paths.reviewer_a, paths.reviewer_b, paths.tiebreaker),
                    strict=True,
                )
            },
            "tiebreak_request_sha256": _file_sha256(paths.tiebreak_request),
            "two_lane_reference_sha256": _file_sha256(paths.reference),
            "unresolved_reference_fields": list(reference.unresolved_field_ids),
            "case_order": list(reference.case_order),
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
            "occurrence_evaluator_package_sha256": evaluator_sha256,
            "binding_schema_version": (
                "artana.staged_generalization.occurrence_bindings.v2"
            ),
            "binding_schema_sha256": binding_schema_sha256,
            "v9_scientific_schema_sha256": v9_schema_sha256,
            "v9_scientific_prompt_sha256": _file_sha256(paths.scientific_prompt),
            "v9_regression_panel_sha256": _file_sha256(V9_PANEL),
            "combined_provider_schema_sha256": _canonical_sha256(
                FreshCGProviderOutput.model_json_schema()
            ),
            "provider_format_sha256": _canonical_sha256(provider_format()),
            "historical_v9_artifact_sha256_by_path": _historical_v9_hashes(),
            "code_sha256_by_path": _code_hashes(),
            "model": f"openai:{MODEL}",
            "reasoning_effort": REASONING_EFFORT,
            "budgets": {
                "global_max_creation_calls": GLOBAL_MAX_CALLS,
                "global_max_cost_usd": GLOBAL_MAX_COST_USD,
                "per_call_max_output_tokens": MAX_OUTPUT_TOKENS,
                "per_call_max_total_tokens": MAX_TOTAL_TOKENS,
                "per_call_max_latency_seconds": MAX_LATENCY_SECONDS,
                "per_call_max_cost_usd": MAX_COST_USD,
                "silent_retries": 0,
                "provider_retries": 0,
            },
        },
        "review_governance": {
            "primary_reviewer_ids": list(reference.primary_reviewer_ids),
            "tiebreaker_reviewer_id": reference.tiebreaker_reviewer_id,
            "internet_enabled": all(item.internet_enabled for item in reviewers),
            "model_output_blinded": all(item.model_output_blinded for item in reviewers),
            "other_reviewer_output_blinded": all(
                item.other_reviewer_output_blinded for item in reviewers
            ),
            "implementation_reference_blinded": all(
                item.implementation_reference_blinded for item in reviewers
            ),
            "review_only_scoring": "NO_AUTOMATIC_CREDIT_OR_PENALTY",
        },
        "execution_rules": {
            "case_order_immutable": True,
            "one_creation_call_per_case": True,
            "stop_before_next_on_first_failure": True,
            "failure_stages": [
                "INVALID_RECEIPT",
                "OCCURRENCE_BINDING",
                "BUDGET",
                "SCIENTIFIC_ACCEPTANCE",
                "CONTRADICTION_OR_UNSUPPORTED",
                "EVALUATOR_DEFECT",
            ],
            "fallback": False,
            "manual_output_repair": False,
            "historical_rescoring": False,
            "graph_writes": False,
            "promotion": False,
            "qualification": False,
        },
        "precall_gates": {
            "offline_v2_regression_node_ids": list(_REGRESSION_NODE_IDS),
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


def write_reference_candidate(paths: ExperimentPaths) -> None:
    selection = load_frozen_selection(paths.selection)
    packet = _verify_review_packet(paths, selection)
    write_two_lane_reference(paths.reference, _build_reference(paths, selection, packet))


def verify(
    paths: ExperimentPaths,
    *,
    remote_gate: bool,
    offline_regression: bool,
) -> dict[str, object]:
    loaded: object = json.loads(paths.preregistration.read_text(encoding="utf-8"))
    expected = build_preregistration(paths)
    if loaded != expected:
        raise FreshCGPreflightError(
            "preregistration differs from independently recomputed frozen state"
        )
    if not isinstance(loaded, dict):
        raise FreshCGPreflightError("preregistration must be a JSON object")
    if offline_regression:
        _verify_offline_regression()
    if remote_gate:
        _verify_remote_gate(paths)
    return loaded


def _verify_review_packet(paths: ExperimentPaths, selection: object) -> FreshCGReviewPacket:
    from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.contracts import (
        FreshCGSelection,
    )

    if not isinstance(selection, FreshCGSelection):
        raise TypeError("selection has an unexpected contract")
    loaded = FreshCGReviewPacket.model_validate_json(
        paths.review_packet.read_text(encoding="utf-8")
    )
    expected = build_review_packet(
        selection,
        selection_artifact_sha256=_file_sha256(paths.selection),
    )
    if loaded != expected:
        raise FreshCGPreflightError("blinded reviewer packet changed")
    return loaded


def _verify_reference(
    paths: ExperimentPaths,
    selection: object,
    packet: FreshCGReviewPacket,
) -> FreshCGTwoLaneReference:
    from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.contracts import (
        FreshCGSelection,
    )

    if not isinstance(selection, FreshCGSelection):
        raise TypeError("selection has an unexpected contract")
    expected = _build_reference(paths, selection, packet)
    loaded = FreshCGTwoLaneReference.model_validate_json(
        paths.reference.read_text(encoding="utf-8")
    )
    if loaded != expected:
        raise FreshCGPreflightError("two-lane reference changed")
    return loaded


def _build_reference(
    paths: ExperimentPaths,
    selection: object,
    packet: FreshCGReviewPacket,
) -> FreshCGTwoLaneReference:
    from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.contracts import (
        FreshCGSelection,
    )

    if not isinstance(selection, FreshCGSelection):
        raise TypeError("selection has an unexpected contract")
    reviewer_a = load_reviewer_artifact(paths.reviewer_a)
    reviewer_b = load_reviewer_artifact(paths.reviewer_b)
    preliminary = build_two_lane_reference(
        ReferenceBuildInputs(
            selection=selection,
            packet=packet,
            selection_artifact_path=paths.selection,
            review_packet_path=paths.review_packet,
            review_prompt_path=paths.review_prompt,
            primary_reviewers=(
                ReviewArtifactInput(reviewer_a, paths.reviewer_a),
                ReviewArtifactInput(reviewer_b, paths.reviewer_b),
            ),
        )
    )
    _verify_tiebreak_request(paths, preliminary)
    tiebreaker = load_reviewer_artifact(paths.tiebreaker)
    return build_two_lane_reference(
        ReferenceBuildInputs(
            selection=selection,
            packet=packet,
            selection_artifact_path=paths.selection,
            review_packet_path=paths.review_packet,
            review_prompt_path=paths.review_prompt,
            primary_reviewers=(
                ReviewArtifactInput(reviewer_a, paths.reviewer_a),
                ReviewArtifactInput(reviewer_b, paths.reviewer_b),
            ),
            tiebreaker=ReviewArtifactInput(tiebreaker, paths.tiebreaker),
        )
    )


def _verify_tiebreak_request(
    paths: ExperimentPaths,
    preliminary: FreshCGTwoLaneReference,
) -> None:
    loaded: object = json.loads(paths.tiebreak_request.read_text(encoding="utf-8"))
    expected: dict[str, object] = {
        "schema_version": (
            "artana.staged_generalization.fresh_cg_tiebreak_request.v1"
        ),
        "review_packet_sha256": _file_sha256(paths.review_packet),
        "primary_reviewer_answers_disclosed": False,
        "instruction": (
            "Independently adjudicate these fields. A complete reviewer artifact is "
            "required for schema validation, but only listed fields will be used as "
            "tiebreak votes."
        ),
        "disputed_field_ids": list(preliminary.unresolved_field_ids),
    }
    if loaded != expected:
        raise FreshCGPreflightError(
            "tiebreak request differs from the mechanical primary disagreements"
        )
    if not preliminary.unresolved_field_ids:
        raise FreshCGPreflightError("tiebreaker was requested without a disagreement")


def _verify_offline_regression() -> None:
    command = [sys.executable, "-m", "pytest", "-q", *_REGRESSION_NODE_IDS]
    completed = subprocess.run(  # noqa: S603 - fixed local test command.
        command,
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if completed.returncode != 0:
        output = (completed.stdout + completed.stderr)[-4000:]
        raise FreshCGPreflightError(f"old-six V2 regression failed:\n{output}")


def _verify_remote_gate(paths: ExperimentPaths) -> None:
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    if branch != BRANCH:
        raise FreshCGPreflightError(f"wrong execution branch: {branch}")
    head = _git("rev-parse", "HEAD")
    remote = _git("ls-remote", "--heads", "origin", f"refs/heads/{BRANCH}")
    remote_head = remote.split()[0] if remote else ""
    if head != remote_head:
        raise FreshCGPreflightError("local HEAD does not equal live remote branch head")
    relative_preregistration = paths.preregistration.relative_to(REPO).as_posix()
    tracked_bytes = subprocess.run(  # noqa: S603 - fixed git command and path.
        [GIT, "show", f"HEAD:{relative_preregistration}"],
        cwd=REPO,
        check=False,
        capture_output=True,
    )
    if (
        tracked_bytes.returncode != 0
        or tracked_bytes.stdout != paths.preregistration.read_bytes()
    ):
        raise FreshCGPreflightError("remote-parity HEAD does not contain preregistration")
    unexpected = [
        path
        for path in _dirty_paths()
        if not any(
            path == allowed.rstrip("/") or path.startswith(allowed)
            for allowed in _ALLOWED_DIRTY_PATHS
        )
    ]
    if unexpected:
        raise FreshCGPreflightError(
            f"experiment files differ from committed HEAD: {unexpected}"
        )


def _dirty_paths() -> tuple[str, ...]:
    completed = subprocess.run(  # noqa: S603 - fixed git status command.
        [GIT, "status", "--porcelain=v1", "--untracked-files=normal"],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise FreshCGPreflightError(
            f"git status failed: {completed.stderr.strip()}"
        )
    return _parse_dirty_paths(completed.stdout)


def _parse_dirty_paths(output: str) -> tuple[str, ...]:
    paths: list[str] = []
    for line in output.splitlines():
        raw = line[3:]
        paths.append(raw.split(" -> ")[-1])
    return tuple(paths)


def _git(*arguments: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed git executable.
        [GIT, *arguments],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise FreshCGPreflightError(
            f"git {' '.join(arguments)} failed: {completed.stderr.strip()}"
        )
    return str(completed.stdout).strip()


def _code_hashes() -> dict[str, str]:
    files = sorted(
        (REPO / "scripts/validation/public_gold/staged_event/generalization/fresh_cg_v1").glob(
            "*.py"
        )
    )
    runner = REPO / "scripts/run_fresh_cg_occurrence_v2_v1.py"
    if runner.exists():
        files.append(runner)
    return {
        path.relative_to(REPO).as_posix(): _file_sha256(path)
        for path in sorted(files)
    }


def _historical_v9_hashes() -> dict[str, str]:
    paths = sorted(
        path
        for path in (REPO / "docs/validation").rglob("*")
        if path.is_file() and "2026-07-22-staged-generalization-v9" in path.name
    )
    return {
        path.relative_to(REPO).as_posix(): _file_sha256(path) for path in paths
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
    "FreshCGPreflightError",
    "build_preregistration",
    "verify",
    "write_candidate",
]
