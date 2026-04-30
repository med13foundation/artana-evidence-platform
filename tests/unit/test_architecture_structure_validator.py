"""Unit tests for the architecture-structure validator."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_architecture_structure import (
    CompatibilityFacade,
    ImportCycleRoot,
    LargeHelperModuleOverride,
    PackageModuleCountOverride,
    RootModuleCountOverride,
    RootModuleFamilyOverride,
    build_import_graph,
    import_cycles,
    parse_config,
    root_family_prefix,
    validate_compatibility_facade_imports,
    validate_import_cycles,
    validate_large_helper_modules,
    validate_package_module_counts,
    validate_root_module_counts,
    validate_root_module_families,
    validate_structure,
)


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_parse_config_accepts_minimal_sections() -> None:
    raw = {
        "root_module_counts": [
            {
                "path": "services/artana_evidence_api",
                "max_modules": 237,
                "target_modules": 190,
                "reason": "baseline",
                "tracking_ref": "docs/architecture/module-packaging-plan.md",
            },
        ],
        "root_module_families": [
            {
                "path": "services/artana_evidence_api",
                "prefix": "full_ai",
                "max_modules": 29,
                "target_package": "services/artana_evidence_api/full_ai_orchestrator",
                "reason": "package later",
            },
        ],
        "package_module_counts": [
            {
                "path": "services/artana_evidence_api/routers",
                "max_modules": 36,
                "reason": "baseline",
                "tracking_ref": "docs/architecture/module-packaging-plan.md",
            },
        ],
        "large_helper_modules": [
            {
                "path": "services/artana_evidence_api/runtime_support.py",
                "max_lines": 866,
                "reason": "baseline",
            },
        ],
        "import_cycle_roots": [
            {
                "path": "services/artana_evidence_api/source_plugins",
                "reason": "must stay acyclic",
            },
        ],
        "compatibility_facades": [
            {
                "path": "scripts/run_full_ai_real_space_canary.py",
                "module": "scripts.run_full_ai_real_space_canary",
                "canonical_package": "scripts.full_ai_real_space_canary",
                "reason": "compatibility entrypoint",
            },
        ],
    }

    config, errors = parse_config(raw)

    assert errors == []
    assert config.root_module_counts[0].target_modules == 190
    assert config.root_module_families[0].prefix == "full_ai"
    assert config.package_module_counts[0].max_modules == 36
    assert config.large_helper_modules[0].max_lines == 866
    assert config.import_cycle_roots[0].path.endswith("source_plugins")
    assert config.compatibility_facades[0].canonical_package.endswith(
        "full_ai_real_space_canary",
    )


def test_root_family_prefix_uses_first_two_segments() -> None:
    assert root_family_prefix("full_ai_orchestrator_runtime") == "full_ai"
    assert root_family_prefix("research_init_runtime") == "research_init"
    assert root_family_prefix("settings") == "settings"


def test_root_module_count_ratchet_blocks_growth(tmp_path: Path) -> None:
    service_root = tmp_path / "services" / "artana_evidence_api"
    _write(service_root / "__init__.py")
    _write(service_root / "one.py")
    _write(service_root / "two.py")

    violations = validate_root_module_counts(
        repo_root=tmp_path,
        overrides=(
            RootModuleCountOverride(
                path="services/artana_evidence_api",
                max_modules=2,
                target_modules=1,
                reason="baseline",
                tracking_ref="docs/architecture/module-packaging-plan.md",
            ),
        ),
    )

    assert any("above allowed" in violation.message for violation in violations)


def test_root_module_count_ratchet_requires_updates_after_shrink(
    tmp_path: Path,
) -> None:
    service_root = tmp_path / "services" / "artana_evidence_api"
    _write(service_root / "__init__.py")
    _write(service_root / "one.py")

    violations = validate_root_module_counts(
        repo_root=tmp_path,
        overrides=(
            RootModuleCountOverride(
                path="services/artana_evidence_api",
                max_modules=3,
                target_modules=1,
                reason="baseline",
                tracking_ref="docs/architecture/module-packaging-plan.md",
            ),
        ),
    )

    assert any("below ratchet" in violation.message for violation in violations)


def test_root_module_count_requires_lower_target(tmp_path: Path) -> None:
    service_root = tmp_path / "services" / "artana_evidence_api"
    _write(service_root / "__init__.py")
    _write(service_root / "one.py")

    violations = validate_root_module_counts(
        repo_root=tmp_path,
        overrides=(
            RootModuleCountOverride(
                path="services/artana_evidence_api",
                max_modules=2,
                target_modules=2,
                reason="baseline",
                tracking_ref="docs/architecture/module-packaging-plan.md",
            ),
        ),
    )

    assert any(
        "target_modules must be lower" in violation.message for violation in violations
    )


def test_root_module_family_requires_documented_override(tmp_path: Path) -> None:
    service_root = tmp_path / "services" / "artana_evidence_api"
    for index in range(7):
        _write(service_root / f"alpha_beta_{index}.py")

    violations = validate_root_module_families(repo_root=tmp_path, overrides=())

    assert len(violations) == 1
    assert "alpha_beta_*.py" in violations[0].path


def test_root_module_family_override_is_a_ratchet(tmp_path: Path) -> None:
    service_root = tmp_path / "services" / "artana_evidence_api"
    for index in range(7):
        _write(service_root / f"alpha_beta_{index}.py")
    override = RootModuleFamilyOverride(
        path="services/artana_evidence_api",
        prefix="alpha_beta",
        max_modules=7,
        target_package="services/artana_evidence_api/alpha_beta",
        reason="package later",
    )

    assert (
        validate_root_module_families(repo_root=tmp_path, overrides=(override,)) == []
    )


def test_root_module_family_override_blocks_growth(tmp_path: Path) -> None:
    service_root = tmp_path / "services" / "artana_evidence_api"
    for index in range(8):
        _write(service_root / f"alpha_beta_{index}.py")
    override = RootModuleFamilyOverride(
        path="services/artana_evidence_api",
        prefix="alpha_beta",
        max_modules=7,
        target_package="services/artana_evidence_api/alpha_beta",
        reason="package later",
    )

    violations = validate_root_module_families(
        repo_root=tmp_path, overrides=(override,)
    )

    assert any("above allowed" in violation.message for violation in violations)


def test_root_module_family_override_fails_when_stale(tmp_path: Path) -> None:
    service_root = tmp_path / "services" / "artana_evidence_api"
    for index in range(2):
        _write(service_root / f"alpha_beta_{index}.py")

    violations = validate_root_module_families(
        repo_root=tmp_path,
        overrides=(
            RootModuleFamilyOverride(
                path="services/artana_evidence_api",
                prefix="alpha_beta",
                max_modules=7,
                target_package="services/artana_evidence_api/alpha_beta",
                reason="package later",
            ),
        ),
    )

    assert any(
        "stale root module-family override" in violation.message
        for violation in violations
    )


def test_package_module_count_requires_documented_override(tmp_path: Path) -> None:
    package_root = tmp_path / "services" / "artana_evidence_api" / "routers"
    for index in range(16):
        _write(package_root / f"route_{index}.py")

    violations = validate_package_module_counts(repo_root=tmp_path, overrides=())

    assert len(violations) == 1
    assert "16 direct Python modules" in violations[0].message


def test_package_module_count_override_blocks_growth(tmp_path: Path) -> None:
    package_root = tmp_path / "services" / "artana_evidence_api" / "routers"
    for index in range(17):
        _write(package_root / f"route_{index}.py")
    override = PackageModuleCountOverride(
        path="services/artana_evidence_api/routers",
        max_modules=16,
        reason="baseline",
        tracking_ref="docs/architecture/module-packaging-plan.md",
    )

    violations = validate_package_module_counts(
        repo_root=tmp_path, overrides=(override,)
    )

    assert any("above allowed" in violation.message for violation in violations)


def test_package_module_count_override_requires_existing_path(tmp_path: Path) -> None:
    violations = validate_package_module_counts(
        repo_root=tmp_path,
        overrides=(
            PackageModuleCountOverride(
                path="services/artana_evidence_api/routers",
                max_modules=16,
                reason="baseline",
                tracking_ref="docs/architecture/module-packaging-plan.md",
            ),
        ),
    )

    assert any("does not exist" in violation.message for violation in violations)


def test_large_helper_module_requires_documented_override(tmp_path: Path) -> None:
    helper_path = (
        tmp_path
        / "services"
        / "artana_evidence_api"
        / "full_ai_orchestrator_support.py"
    )
    _write(helper_path, "\n".join("pass" for _ in range(401)))

    violations = validate_large_helper_modules(repo_root=tmp_path, overrides=())

    assert len(violations) == 1
    assert "helper-like module" in violations[0].message


def test_large_helper_module_override_is_a_ratchet(tmp_path: Path) -> None:
    helper_path = (
        tmp_path
        / "services"
        / "artana_evidence_api"
        / "full_ai_orchestrator_support.py"
    )
    _write(helper_path, "\n".join("pass" for _ in range(401)))
    override = LargeHelperModuleOverride(
        path="services/artana_evidence_api/full_ai_orchestrator_support.py",
        max_lines=401,
        reason="package later",
    )

    assert (
        validate_large_helper_modules(repo_root=tmp_path, overrides=(override,)) == []
    )


def test_large_helper_module_override_blocks_growth(tmp_path: Path) -> None:
    helper_path = (
        tmp_path
        / "services"
        / "artana_evidence_api"
        / "full_ai_orchestrator_support.py"
    )
    _write(helper_path, "\n".join("pass" for _ in range(402)))
    override = LargeHelperModuleOverride(
        path="services/artana_evidence_api/full_ai_orchestrator_support.py",
        max_lines=401,
        reason="package later",
    )

    violations = validate_large_helper_modules(
        repo_root=tmp_path, overrides=(override,)
    )

    assert any("above allowed" in violation.message for violation in violations)


def test_large_helper_module_override_fails_when_stale(tmp_path: Path) -> None:
    helper_path = (
        tmp_path
        / "services"
        / "artana_evidence_api"
        / "full_ai_orchestrator_support.py"
    )
    _write(helper_path, "\n".join("pass" for _ in range(10)))
    override = LargeHelperModuleOverride(
        path="services/artana_evidence_api/full_ai_orchestrator_support.py",
        max_lines=401,
        reason="package later",
    )

    violations = validate_large_helper_modules(
        repo_root=tmp_path, overrides=(override,)
    )

    assert any(
        "stale large-helper override" in violation.message for violation in violations
    )


def test_import_cycle_checker_catches_relative_import_cycle(tmp_path: Path) -> None:
    package_root = tmp_path / "services" / "artana_evidence_api" / "demo_pkg"
    _write(package_root / "__init__.py")
    _write(package_root / "a.py", "from . import b\n")
    _write(package_root / "b.py", "from . import a\n")

    graph = build_import_graph(repo_root=tmp_path, package_root=package_root)

    assert import_cycles(graph) == [
        (
            "artana_evidence_api.demo_pkg.a",
            "artana_evidence_api.demo_pkg.b",
            "artana_evidence_api.demo_pkg.a",
        ),
    ]


def test_validate_import_cycles_reports_configured_root(tmp_path: Path) -> None:
    package_root = tmp_path / "services" / "artana_evidence_api" / "demo_pkg"
    _write(package_root / "__init__.py")
    _write(package_root / "a.py", "from . import b\n")
    _write(package_root / "b.py", "from . import a\n")

    violations = validate_import_cycles(
        repo_root=tmp_path,
        roots=(
            ImportCycleRoot(
                path="services/artana_evidence_api/demo_pkg",
                reason="must stay acyclic",
            ),
        ),
    )

    assert len(violations) == 1
    assert "import cycle detected" in violations[0].message


def test_validate_import_cycles_reports_parse_errors(tmp_path: Path) -> None:
    package_root = tmp_path / "services" / "artana_evidence_api" / "demo_pkg"
    _write(package_root / "__init__.py")
    _write(package_root / "bad.py", "def broken(:\n")

    violations = validate_import_cycles(
        repo_root=tmp_path,
        roots=(
            ImportCycleRoot(
                path="services/artana_evidence_api/demo_pkg",
                reason="must stay acyclic",
            ),
        ),
    )

    assert len(violations) == 1
    assert "could not parse Python" in violations[0].message


def test_validate_import_cycles_reports_decode_errors(tmp_path: Path) -> None:
    package_root = tmp_path / "services" / "artana_evidence_api" / "demo_pkg"
    _write(package_root / "__init__.py")
    bad_path = package_root / "bad.py"
    bad_path.write_bytes(b"\xff\xfe\x00")

    violations = validate_import_cycles(
        repo_root=tmp_path,
        roots=(
            ImportCycleRoot(
                path="services/artana_evidence_api/demo_pkg",
                reason="must stay acyclic",
            ),
        ),
    )

    assert len(violations) == 1
    assert "could not parse Python" in violations[0].message


def test_compatibility_facade_imports_block_internal_package_dependency(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "scripts" / "run_demo.py", "def main() -> int:\n    return 0\n")
    _write(
        tmp_path / "scripts" / "demo_package" / "runner.py",
        "from scripts.run_demo import main\n",
    )

    violations = validate_compatibility_facade_imports(
        repo_root=tmp_path,
        facades=(
            CompatibilityFacade(
                path="scripts/run_demo.py",
                module="scripts.run_demo",
                canonical_package="scripts.demo_package",
                reason="compatibility entrypoint",
            ),
        ),
    )

    assert len(violations) == 1
    assert "imports compatibility facade scripts.run_demo" in violations[0].message


def test_compatibility_facade_imports_block_package_level_import_form(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "scripts" / "run_demo.py", "def main() -> int:\n    return 0\n")
    _write(
        tmp_path / "scripts" / "demo_package" / "runner.py",
        "from scripts import run_demo\n",
    )

    violations = validate_compatibility_facade_imports(
        repo_root=tmp_path,
        facades=(
            CompatibilityFacade(
                path="scripts/run_demo.py",
                module="scripts.run_demo",
                canonical_package="scripts.demo_package",
                reason="compatibility entrypoint",
            ),
        ),
    )

    assert len(violations) == 1
    assert "imports compatibility facade scripts.run_demo" in violations[0].message


def test_compatibility_facade_imports_block_relative_package_import_form(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "scripts" / "run_demo.py", "def main() -> int:\n    return 0\n")
    _write(tmp_path / "scripts" / "demo_package" / "__init__.py")
    _write(
        tmp_path / "scripts" / "demo_package" / "runner.py",
        "from .. import run_demo\n",
    )

    violations = validate_compatibility_facade_imports(
        repo_root=tmp_path,
        facades=(
            CompatibilityFacade(
                path="scripts/run_demo.py",
                module="scripts.run_demo",
                canonical_package="scripts.demo_package",
                reason="compatibility entrypoint",
            ),
        ),
    )

    assert len(violations) == 1
    assert "imports compatibility facade scripts.run_demo" in violations[0].message


def test_compatibility_facade_imports_block_direct_import_form(tmp_path: Path) -> None:
    _write(tmp_path / "scripts" / "run_demo.py", "def main() -> int:\n    return 0\n")
    _write(
        tmp_path / "scripts" / "demo_package" / "runner.py",
        "import scripts.run_demo\n",
    )

    violations = validate_compatibility_facade_imports(
        repo_root=tmp_path,
        facades=(
            CompatibilityFacade(
                path="scripts/run_demo.py",
                module="scripts.run_demo",
                canonical_package="scripts.demo_package",
                reason="compatibility entrypoint",
            ),
        ),
    )

    assert len(violations) == 1
    assert "imports compatibility facade scripts.run_demo" in violations[0].message


def test_compatibility_facade_imports_allow_legacy_root_script_dependency(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "scripts" / "run_demo.py", "def main() -> int:\n    return 0\n")
    _write(
        tmp_path / "scripts" / "run_demo_wrapper.py",
        "from scripts.run_demo import main\n",
    )

    violations = validate_compatibility_facade_imports(
        repo_root=tmp_path,
        facades=(
            CompatibilityFacade(
                path="scripts/run_demo.py",
                module="scripts.run_demo",
                canonical_package="scripts.demo_package",
                reason="compatibility entrypoint",
            ),
        ),
    )

    assert violations == []


def test_real_structure_control_file_is_valid() -> None:
    raw = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "architecture_structure_overrides.json"
        ).read_text(encoding="utf-8"),
    )

    _, errors = parse_config(raw)

    assert errors == []


def test_real_structure_control_file_matches_current_repo() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    raw = json.loads(
        (repo_root / "architecture_structure_overrides.json").read_text(
            encoding="utf-8",
        ),
    )
    config, errors = parse_config(raw)

    assert errors == []
    assert validate_structure(repo_root=repo_root, config=config) == []
