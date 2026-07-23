"""V13 recursive Python dependency-manifest regressions."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validation.public_gold.staged_event.generalization.repair_v13.dependency_manifest import (
    DependencyManifestError,
    build_dependency_manifest,
)

REPO = Path(__file__).resolve().parents[2]
_ROOT_FILES = (
    "scripts/run_staged_generalization_v13_exposed.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v8/config.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v9/config.py",
)
_CRITICAL_DEPENDENCIES = {
    "scripts/validation/provider_receipt_boundary/contracts.py",
    "scripts/validation/public_gold/lossless_event_experiment_contracts.py",
    "scripts/validation/public_gold/lossless_event_provider.py",
    "scripts/validation/public_gold/staged_event/generalization/anchors.py",
    "scripts/validation/public_gold/staged_event/generalization/contracts.py",
    "scripts/validation/public_gold/staged_event/generalization/panel.py",
    "scripts/validation/public_gold/staged_event/generalization/span_identity.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/artifacts.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/evaluation.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/policy.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v8/config.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v8/contracts.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v9/config.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v9/contracts.py",
    "services/artana_evidence_api/__init__.py",
    "services/artana_evidence_api/document_extraction_support/"
    "claim_frames/event_types.py",
    "services/artana_evidence_api/document_extraction_support/"
    "scientific_events/__init__.py",
    "services/artana_evidence_api/document_extraction_support/"
    "scientific_events/contracts.py",
    "services/artana_evidence_api/document_extraction_support/"
    "scientific_events/validation.py",
}
_MUTATED_DEPENDENCY = (
    "scripts/validation/public_gold/staged_event/generalization/panel.py"
)
_MUTATED_SERVICE_DEPENDENCY = (
    "services/artana_evidence_api/document_extraction_support/"
    "claim_frames/event_types.py"
)


def test_manifest_covers_runtime_science_and_tracked_local_contracts() -> None:
    manifest = build_dependency_manifest(REPO, _ROOT_FILES)
    paths = [entry.path for entry in manifest]
    path_set = set(paths)

    assert paths == sorted(paths)
    assert len(paths) == len(path_set)
    assert path_set >= _CRITICAL_DEPENDENCIES
    assert "scripts/__init__.py" in path_set
    assert (
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v13/__init__.py"
    ) in path_set

    for entry in manifest:
        relative = Path(entry.path)
        resolved = (REPO / relative).resolve(strict=True)
        assert not relative.is_absolute()
        assert ".." not in relative.parts
        assert resolved.is_relative_to(REPO.resolve())
        assert (
            entry.sha256 == hashlib.sha256((REPO / relative).read_bytes()).hexdigest()
        )

    completed = subprocess.run(  # noqa: S603
        ["git", "ls-files", "--", *sorted(_CRITICAL_DEPENDENCIES)],  # noqa: S607
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    assert set(completed.stdout.splitlines()) == _CRITICAL_DEPENDENCIES


def test_manifest_digest_changes_when_copied_dependency_changes(
    tmp_path: Path,
) -> None:
    before = build_dependency_manifest(REPO, _ROOT_FILES)
    copied_repo = tmp_path / "repo"
    for entry in before:
        destination = copied_repo / entry.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / entry.path, destination)

    copied_before = build_dependency_manifest(copied_repo, _ROOT_FILES)
    dependency = copied_repo / _MUTATED_DEPENDENCY
    dependency.write_text(
        dependency.read_text(encoding="utf-8") + "\n# manifest mutation\n",
        encoding="utf-8",
    )
    copied_after = build_dependency_manifest(copied_repo, _ROOT_FILES)

    before_by_path = {entry.path: entry.sha256 for entry in copied_before}
    after_by_path = {entry.path: entry.sha256 for entry in copied_after}
    assert before_by_path.keys() == after_by_path.keys()
    assert [
        path for path in before_by_path if before_by_path[path] != after_by_path[path]
    ] == [_MUTATED_DEPENDENCY]


def test_manifest_digest_changes_when_copied_service_dependency_changes(
    tmp_path: Path,
) -> None:
    copied_repo, before_by_path = _copy_closure(tmp_path)
    dependency = copied_repo / _MUTATED_SERVICE_DEPENDENCY
    dependency.write_text(
        dependency.read_text(encoding="utf-8") + "\n# service mutation\n",
        encoding="utf-8",
    )

    after = build_dependency_manifest(copied_repo, _ROOT_FILES)
    after_by_path = {entry.path: entry.sha256 for entry in after}

    assert before_by_path.keys() == after_by_path.keys()
    assert [
        path for path in before_by_path if before_by_path[path] != after_by_path[path]
    ] == [_MUTATED_SERVICE_DEPENDENCY]


def test_v13_entrypoint_prefers_current_services_over_helper_worktree(
    tmp_path: Path,
) -> None:
    helper_root = tmp_path / "b8c0-helper"
    helper_services = helper_root / "services"
    _write(
        helper_root,
        "services/artana_evidence_api/__init__.py",
        '"""Adversarial helper package."""\n',
    )
    current_package = (REPO / "services/artana_evidence_api/__init__.py").resolve(
        strict=True
    )
    current_event_types = (
        REPO / "services/artana_evidence_api/document_extraction_support/"
        "claim_frames/event_types.py"
    ).resolve(strict=True)
    probe = (
        "import runpy\n"
        "from pathlib import Path\n"
        f"runpy.run_path({str(REPO / _ROOT_FILES[0])!r}, "
        "run_name='v13_origin_probe')\n"
        "import artana_evidence_api\n"
        "from artana_evidence_api.document_extraction_support.claim_frames "
        "import event_types\n"
        "print(Path(artana_evidence_api.__file__).resolve())\n"
        "print(Path(event_types.__file__).resolve())\n"
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(helper_services)

    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-c", probe],
        cwd=REPO,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    origins = tuple(Path(value) for value in completed.stdout.splitlines())
    assert origins == (current_package, current_event_types)
    assert "b8c0-helper" not in completed.stdout
    assert "/worktrees/b8c0/" not in completed.stdout


def test_manifest_overapproximates_type_checking_and_candidate_submodules(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write(repo, "scripts/__init__.py", "")
    _write(
        repo,
        "scripts/root.py",
        "from typing import TYPE_CHECKING\n"
        "from scripts.pkg import runtime_dep\n"
        "if TYPE_CHECKING:\n"
        "    from scripts.pkg import type_dep\n",
    )
    _write(repo, "scripts/pkg/__init__.py", "from . import init_dep\n")
    _write(repo, "scripts/pkg/init_dep.py", "")
    _write(repo, "scripts/pkg/runtime_dep.py", "")
    _write(repo, "scripts/pkg/type_dep.py", "")

    paths = {
        entry.path for entry in build_dependency_manifest(repo, ("scripts/root.py",))
    }

    assert paths == {
        "scripts/__init__.py",
        "scripts/pkg/__init__.py",
        "scripts/pkg/init_dep.py",
        "scripts/pkg/runtime_dep.py",
        "scripts/pkg/type_dep.py",
        "scripts/root.py",
    }


def test_manifest_fails_closed_on_missing_or_escaping_local_imports(
    tmp_path: Path,
) -> None:
    missing_repo = tmp_path / "missing"
    _write(missing_repo, "scripts/__init__.py", "")
    _write(missing_repo, "scripts/root.py", "import scripts.absent\n")

    with pytest.raises(
        DependencyManifestError,
        match="repository-local import is missing",
    ):
        build_dependency_manifest(missing_repo, ("scripts/root.py",))

    escaping_repo = tmp_path / "escaping"
    outside = tmp_path / "outside.py"
    outside.write_text("", encoding="utf-8")
    _write(escaping_repo, "scripts/__init__.py", "")
    _write(escaping_repo, "scripts/root.py", "import scripts.escape\n")
    (escaping_repo / "scripts/escape.py").symlink_to(outside)

    with pytest.raises(DependencyManifestError, match="escapes repository"):
        build_dependency_manifest(escaping_repo, ("scripts/root.py",))


def _write(repo: Path, relative: str, value: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _copy_closure(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    source_manifest = build_dependency_manifest(REPO, _ROOT_FILES)
    copied_repo = tmp_path / "repo"
    for entry in source_manifest:
        destination = copied_repo / entry.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / entry.path, destination)
    copied_manifest = build_dependency_manifest(copied_repo, _ROOT_FILES)
    return copied_repo, {entry.path: entry.sha256 for entry in copied_manifest}
