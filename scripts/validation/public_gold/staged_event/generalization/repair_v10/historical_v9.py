"""Versioned isolation of V9 historical and current-code reproducibility."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    DEFAULT_PATHS,
    REPO,
    V10ExecutionPaths,
)

V9_PINNED_COMMIT = "13106a214afc0882e7382032f167e4b909e2d065"
V9_SEAL_COMMIT = "2a8ca565"
V10_BASE_COMMIT = "05bdfa44067d2eda5fcd3788069868fdda87de63"
RECEIPT_CHANGE_COMMIT = "8778bf427006d9e01daa76c56e56119457adc0e6"
V9_PREREGISTRATION_SHA256 = (
    "7a170db78370571f986208530547c5ee4ec85a148634002f87a18dcc486e85b9"
)
REPORTED_FILE = "scripts/validation/provider_receipt_boundary/__init__.py"
REPORTED_EXPECTED_SHA256 = (
    "f5352623348b5b3a2d30a217c535a9c4a19bd50eadeec2d583218337bff7260a"
)
REPORTED_OBSERVED_SHA256 = (
    "8291018b46a4db88ac589a730f4dc247c2aeb7ede6d01f3aeca41f0c47668510"
)


class HistoricalV9ProvenanceError(RuntimeError):
    """Historical V9 evidence cannot be reproduced without reinterpretation."""


def verify_historical_code_manifest(
    preregistration_path: Path,
    *,
    expected_preregistration_sha256: str,
    pinned_commit: str,
    repo: Path = REPO,
) -> dict[str, object]:
    """Verify one sealed preregistration against code at its historical pin."""

    if _sha256(preregistration_path) != expected_preregistration_sha256:
        raise HistoricalV9ProvenanceError(
            "sealed historical preregistration changed"
        )
    preregistration = _object(
        json.loads(preregistration_path.read_text(encoding="utf-8"))
    )
    frozen = _object(preregistration["frozen_state"])
    code_manifest = {
        str(file_name): str(expected)
        for file_name, expected in _object(frozen["code_sha256"]).items()
    }
    mismatches = _manifest_mismatches_at_commit(repo, code_manifest, pinned_commit)
    if mismatches:
        raise HistoricalV9ProvenanceError(
            f"historical pinned code no longer reproduces: {mismatches}"
        )
    return {
        "historical_preregistration_sha256": expected_preregistration_sha256,
        "historical_pinned_commit": pinned_commit,
        "historical_code_manifest_match": True,
        "historical_code_manifest_mismatches": [],
    }


def build_provenance(
    paths: V10ExecutionPaths = DEFAULT_PATHS,
    *,
    repo: Path = REPO,
) -> dict[str, object]:
    """Reproduce V9 at its pin and inventory current receipt-code drift."""

    historical = verify_historical_code_manifest(
        paths.v9_preregistration,
        expected_preregistration_sha256=V9_PREREGISTRATION_SHA256,
        pinned_commit=V9_PINNED_COMMIT,
        repo=repo,
    )
    preregistration = _object(
        json.loads(paths.v9_preregistration.read_text(encoding="utf-8"))
    )
    frozen = _object(preregistration["frozen_state"])
    code_manifest = {
        str(file_name): str(expected)
        for file_name, expected in _object(frozen["code_sha256"]).items()
    }
    current_mismatches = _manifest_mismatches_in_checkout(repo, code_manifest)
    reported = next(
        (
            item
            for item in current_mismatches
            if item["file"] == REPORTED_FILE
        ),
        None,
    )
    if reported != {
        "file": REPORTED_FILE,
        "expected_sha256": REPORTED_EXPECTED_SHA256,
        "observed_sha256": REPORTED_OBSERVED_SHA256,
    }:
        raise HistoricalV9ProvenanceError("reported V9 hash mismatch changed")
    if not _is_ancestor(repo, RECEIPT_CHANGE_COMMIT, V10_BASE_COMMIT):
        raise HistoricalV9ProvenanceError("receipt change does not predate V10 base")
    if not _is_ancestor(repo, V9_SEAL_COMMIT, RECEIPT_CHANGE_COMMIT):
        raise HistoricalV9ProvenanceError("receipt change does not postdate V9 seal")
    if _last_change(repo, REPORTED_FILE) != RECEIPT_CHANGE_COMMIT:
        raise HistoricalV9ProvenanceError("reported receipt change commit changed")
    return {
        "schema_version": (
            "artana.staged_generalization.v9_historical_isolation.v1"
        ),
        "historical_experiment_id": "staged-generalization-v9",
        "historical_preregistration_sha256": V9_PREREGISTRATION_SHA256,
        "historical_pinned_commit": V9_PINNED_COMMIT,
        "historical_seal_commit": V9_SEAL_COMMIT,
        "current_v10_base_commit": V10_BASE_COMMIT,
        "historical_code_manifest_match": historical[
            "historical_code_manifest_match"
        ],
        "historical_code_manifest_mismatches": historical[
            "historical_code_manifest_mismatches"
        ],
        "current_checkout_code_manifest_match": not current_mismatches,
        "current_checkout_code_manifest_mismatches": current_mismatches,
        "reported_failure": {
            "file": REPORTED_FILE,
            "expected_sha256": REPORTED_EXPECTED_SHA256,
            "observed_sha256": REPORTED_OBSERVED_SHA256,
            "change_commit": RECEIPT_CHANGE_COMMIT,
            "change_predates_v10_base": True,
            "change_postdates_v9_seal": True,
        },
        "disposition": {
            "sealed_v9_rewrite_authorized": False,
            "sealed_v9_rescore_authorized": False,
            "historical_v9_reproducibility_scope": V9_PINNED_COMMIT,
            "current_receipt_code_authorized_for_v9": False,
            "current_receipt_code_requires_separate_v10_execution_pin": True,
        },
    }


def write_provenance(
    paths: V10ExecutionPaths = DEFAULT_PATHS,
    *,
    repo: Path = REPO,
) -> None:
    paths.historical_provenance.parent.mkdir(parents=True, exist_ok=True)
    paths.historical_provenance.write_text(
        json.dumps(build_provenance(paths, repo=repo), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify_provenance(
    paths: V10ExecutionPaths = DEFAULT_PATHS,
    *,
    repo: Path = REPO,
) -> dict[str, object]:
    loaded = _object(
        json.loads(paths.historical_provenance.read_text(encoding="utf-8"))
    )
    expected = build_provenance(paths, repo=repo)
    if loaded != expected:
        raise HistoricalV9ProvenanceError("V9 provenance artifact changed")
    return loaded


def _manifest_mismatches_at_commit(
    repo: Path,
    manifest: dict[str, str],
    commit: str,
) -> list[dict[str, str]]:
    mismatches: list[dict[str, str]] = []
    for file_name, expected in sorted(manifest.items()):
        observed = hashlib.sha256(
            _git_bytes(repo, "show", f"{commit}:{file_name}")
        ).hexdigest()
        if observed != expected:
            mismatches.append(
                {
                    "file": file_name,
                    "expected_sha256": expected,
                    "observed_sha256": observed,
                }
            )
    return mismatches


def _manifest_mismatches_in_checkout(
    repo: Path,
    manifest: dict[str, str],
) -> list[dict[str, str]]:
    mismatches: list[dict[str, str]] = []
    for file_name, expected in sorted(manifest.items()):
        observed = _sha256(repo / file_name)
        if observed != expected:
            mismatches.append(
                {
                    "file": file_name,
                    "expected_sha256": expected,
                    "observed_sha256": observed,
                }
            )
    return mismatches


def _last_change(repo: Path, file_name: str) -> str:
    return _git_text(repo, "log", "-1", "--format=%H", "--", file_name).strip()


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    completed = subprocess.run(  # noqa: S603 - fixed local Git read.
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],  # noqa: S607
        cwd=repo,
        check=False,
        capture_output=True,
    )
    return completed.returncode == 0


def _git_text(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed local Git read.
        ["git", *arguments],  # noqa: S607
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise HistoricalV9ProvenanceError(completed.stderr.strip())
    return completed.stdout


def _git_bytes(repo: Path, *arguments: str) -> bytes:
    completed = subprocess.run(  # noqa: S603 - fixed local Git read.
        ["git", *arguments],  # noqa: S607
        cwd=repo,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise HistoricalV9ProvenanceError(completed.stderr.decode().strip())
    return completed.stdout


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise HistoricalV9ProvenanceError("expected JSON object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "HistoricalV9ProvenanceError",
    "build_provenance",
    "verify_historical_code_manifest",
    "verify_provenance",
    "write_provenance",
]
