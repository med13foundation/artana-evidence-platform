#!/usr/bin/env python3
"""Validate package-sprawl and import-cycle architecture guardrails."""

from __future__ import annotations

import ast
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

try:
    from scripts.validate_architecture_size import count_lines, is_in_scope
except ModuleNotFoundError:  # pragma: no cover - direct file execution path
    from validate_architecture_size import count_lines, is_in_scope

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = REPO_ROOT / "architecture_structure_overrides.json"

DEFAULT_ROOT_FAMILY_MAX_MODULES = 6
DEFAULT_PACKAGE_MAX_MODULES = 15
DEFAULT_LARGE_HELPER_MAX_LINES = 400
ROOT_FAMILY_PREFIX_SEGMENTS = 2
SERVICE_MODULE_PATH_MIN_PARTS = 2
SCRIPT_INTERNAL_MODULE_MIN_PARTS = 3
SERVICE_INTERNAL_MODULE_MIN_PARTS = 4

SERVICE_ROOTS = (
    "services/artana_evidence_api",
    "services/artana_evidence_db",
)
PACKAGE_SCAN_ROOTS = SERVICE_ROOTS + ("scripts",)
EXCLUDED_DIRECTORY_PARTS = frozenset(
    {
        "__pycache__",
        ".pytest_cache",
        "tests",
        "alembic",
        "ci",
        "deploy",
        "postgres-init",
        "fixtures",
    },
)
HELPER_NAME_MARKERS = ("utils", "support", "common")


@dataclass(frozen=True)
class Violation:
    """A structure guardrail violation, ready to print."""

    path: str
    message: str


@dataclass(frozen=True)
class RootModuleCountOverride:
    """A ratcheted top-level module count for a service root."""

    path: str
    max_modules: int
    target_modules: int
    reason: str
    tracking_ref: str


@dataclass(frozen=True)
class RootModuleFamilyOverride:
    """A ratcheted exception for an existing service-root module family."""

    path: str
    prefix: str
    max_modules: int
    target_package: str
    reason: str


@dataclass(frozen=True)
class PackageModuleCountOverride:
    """A ratcheted exception for an existing dense package directory."""

    path: str
    max_modules: int
    reason: str
    tracking_ref: str


@dataclass(frozen=True)
class LargeHelperModuleOverride:
    """A ratcheted exception for an existing large helper-like module."""

    path: str
    max_lines: int
    reason: str


@dataclass(frozen=True)
class ImportCycleRoot:
    """A package root that must remain free of internal import cycles."""

    path: str
    reason: str


@dataclass(frozen=True)
class CompatibilityFacade:
    """A compatibility module that internal package code must not import."""

    path: str
    module: str
    canonical_package: str
    reason: str


@dataclass(frozen=True)
class StructureConfig:
    """Parsed architecture-structure control file."""

    root_module_counts: tuple[RootModuleCountOverride, ...]
    root_module_families: tuple[RootModuleFamilyOverride, ...]
    package_module_counts: tuple[PackageModuleCountOverride, ...]
    large_helper_modules: tuple[LargeHelperModuleOverride, ...]
    import_cycle_roots: tuple[ImportCycleRoot, ...]
    compatibility_facades: tuple[CompatibilityFacade, ...]


def _parse_compatibility_facades(
    raw: Mapping[str, object],
    *,
    errors: list[Violation],
) -> tuple[CompatibilityFacade, ...]:
    facades: list[CompatibilityFacade] = []
    for index, entry in enumerate(
        _entry_list(raw, "compatibility_facades", errors=errors)
    ):
        location = (
            f"architecture_structure_overrides.json[compatibility_facades][{index}]"
        )
        path = _string_field(entry, "path", location=location, errors=errors)
        module = _string_field(entry, "module", location=location, errors=errors)
        canonical_package = _string_field(
            entry,
            "canonical_package",
            location=location,
            errors=errors,
        )
        reason = _string_field(entry, "reason", location=location, errors=errors)
        if None not in (path, module, canonical_package, reason):
            facades.append(
                CompatibilityFacade(
                    path=path or "",
                    module=module or "",
                    canonical_package=canonical_package or "",
                    reason=reason or "",
                ),
            )
    return tuple(facades)


def _string_field(
    entry: Mapping[str, object],
    field: str,
    *,
    location: str,
    errors: list[Violation],
) -> str | None:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(Violation(location, f'missing or empty "{field}"'))
        return None
    return value.strip()


def _positive_int_field(
    entry: Mapping[str, object],
    field: str,
    *,
    location: str,
    errors: list[Violation],
) -> int | None:
    value = entry.get(field)
    if not isinstance(value, int) or value <= 0:
        errors.append(Violation(location, f'"{field}" must be a positive integer'))
        return None
    return value


def _entry_list(
    raw: Mapping[str, object],
    field: str,
    *,
    errors: list[Violation],
) -> list[Mapping[str, object]]:
    value = raw.get(field, [])
    if not isinstance(value, list):
        errors.append(
            Violation(
                "architecture_structure_overrides.json", f'"{field}" must be a list'
            )
        )
        return []
    entries: list[Mapping[str, object]] = []
    for index, entry in enumerate(value):
        if not isinstance(entry, dict):
            errors.append(
                Violation(
                    f"architecture_structure_overrides.json[{field}][{index}]",
                    "entry must be a JSON object",
                ),
            )
            continue
        entries.append(entry)
    return entries


def parse_config(raw: object) -> tuple[StructureConfig, list[Violation]]:
    """Parse the structure control file."""
    errors: list[Violation] = []
    if not isinstance(raw, dict):
        empty = StructureConfig((), (), (), (), (), ())
        return empty, [
            Violation(
                "architecture_structure_overrides.json",
                "config root must be a JSON object",
            ),
        ]

    root_counts: list[RootModuleCountOverride] = []
    for index, entry in enumerate(
        _entry_list(raw, "root_module_counts", errors=errors)
    ):
        location = f"architecture_structure_overrides.json[root_module_counts][{index}]"
        path = _string_field(entry, "path", location=location, errors=errors)
        max_modules = _positive_int_field(
            entry,
            "max_modules",
            location=location,
            errors=errors,
        )
        target_modules = _positive_int_field(
            entry,
            "target_modules",
            location=location,
            errors=errors,
        )
        reason = _string_field(entry, "reason", location=location, errors=errors)
        tracking_ref = _string_field(
            entry,
            "tracking_ref",
            location=location,
            errors=errors,
        )
        if None not in (path, max_modules, target_modules, reason, tracking_ref):
            root_counts.append(
                RootModuleCountOverride(
                    path=path or "",
                    max_modules=max_modules or 0,
                    target_modules=target_modules or 0,
                    reason=reason or "",
                    tracking_ref=tracking_ref or "",
                ),
            )

    root_families: list[RootModuleFamilyOverride] = []
    for index, entry in enumerate(
        _entry_list(raw, "root_module_families", errors=errors)
    ):
        location = (
            f"architecture_structure_overrides.json[root_module_families][{index}]"
        )
        path = _string_field(entry, "path", location=location, errors=errors)
        prefix = _string_field(entry, "prefix", location=location, errors=errors)
        max_modules = _positive_int_field(
            entry,
            "max_modules",
            location=location,
            errors=errors,
        )
        target_package = _string_field(
            entry,
            "target_package",
            location=location,
            errors=errors,
        )
        reason = _string_field(entry, "reason", location=location, errors=errors)
        if None not in (path, prefix, max_modules, target_package, reason):
            root_families.append(
                RootModuleFamilyOverride(
                    path=path or "",
                    prefix=prefix or "",
                    max_modules=max_modules or 0,
                    target_package=target_package or "",
                    reason=reason or "",
                ),
            )

    package_counts: list[PackageModuleCountOverride] = []
    for index, entry in enumerate(
        _entry_list(raw, "package_module_counts", errors=errors)
    ):
        location = (
            f"architecture_structure_overrides.json[package_module_counts][{index}]"
        )
        path = _string_field(entry, "path", location=location, errors=errors)
        max_modules = _positive_int_field(
            entry,
            "max_modules",
            location=location,
            errors=errors,
        )
        reason = _string_field(entry, "reason", location=location, errors=errors)
        tracking_ref = _string_field(
            entry,
            "tracking_ref",
            location=location,
            errors=errors,
        )
        if None not in (path, max_modules, reason, tracking_ref):
            package_counts.append(
                PackageModuleCountOverride(
                    path=path or "",
                    max_modules=max_modules or 0,
                    reason=reason or "",
                    tracking_ref=tracking_ref or "",
                ),
            )

    large_helpers: list[LargeHelperModuleOverride] = []
    for index, entry in enumerate(
        _entry_list(raw, "large_helper_modules", errors=errors)
    ):
        location = (
            f"architecture_structure_overrides.json[large_helper_modules][{index}]"
        )
        path = _string_field(entry, "path", location=location, errors=errors)
        max_lines = _positive_int_field(
            entry,
            "max_lines",
            location=location,
            errors=errors,
        )
        reason = _string_field(entry, "reason", location=location, errors=errors)
        if None not in (path, max_lines, reason):
            large_helpers.append(
                LargeHelperModuleOverride(
                    path=path or "",
                    max_lines=max_lines or 0,
                    reason=reason or "",
                ),
            )

    cycle_roots: list[ImportCycleRoot] = []
    for index, entry in enumerate(
        _entry_list(raw, "import_cycle_roots", errors=errors)
    ):
        location = f"architecture_structure_overrides.json[import_cycle_roots][{index}]"
        path = _string_field(entry, "path", location=location, errors=errors)
        reason = _string_field(entry, "reason", location=location, errors=errors)
        if None not in (path, reason):
            cycle_roots.append(ImportCycleRoot(path=path or "", reason=reason or ""))

    compatibility_facades = _parse_compatibility_facades(raw, errors=errors)

    config = StructureConfig(
        root_module_counts=tuple(root_counts),
        root_module_families=tuple(root_families),
        package_module_counts=tuple(package_counts),
        large_helper_modules=tuple(large_helpers),
        import_cycle_roots=tuple(cycle_roots),
        compatibility_facades=compatibility_facades,
    )
    return config, errors


def _direct_python_modules(directory: Path) -> list[Path]:
    if not directory.exists() or not directory.is_dir():
        return []
    return sorted(path for path in directory.glob("*.py") if path.is_file())


def root_family_prefix(module_stem: str) -> str:
    """Return the root-family prefix used to detect flat module sprawl."""
    parts = module_stem.split("_")
    if module_stem == "__init__" or len(parts) < ROOT_FAMILY_PREFIX_SEGMENTS:
        return module_stem
    return "_".join(parts[:ROOT_FAMILY_PREFIX_SEGMENTS])


def root_module_families(service_root: Path) -> dict[str, list[Path]]:
    """Group direct service-root modules by their shared prefix family."""
    families: dict[str, list[Path]] = defaultdict(list)
    for module_path in _direct_python_modules(service_root):
        if module_path.name == "__init__.py":
            continue
        families[root_family_prefix(module_path.stem)].append(module_path)
    return dict(families)


def _has_excluded_part(path: Path) -> bool:
    return bool(set(path.parts) & EXCLUDED_DIRECTORY_PARTS)


def package_direct_module_counts(repo_root: Path) -> dict[str, int]:
    """Return direct child Python module counts for in-scope package directories."""
    counts: dict[str, int] = {}
    for root_name in PACKAGE_SCAN_ROOTS:
        root = repo_root / root_name
        if not root.exists():
            continue
        for directory in (root, *[path for path in root.rglob("*") if path.is_dir()]):
            if directory == root or _has_excluded_part(
                directory.relative_to(repo_root)
            ):
                continue
            count = len(_direct_python_modules(directory))
            if count:
                counts[directory.relative_to(repo_root).as_posix()] = count
    return counts


def large_helper_modules(repo_root: Path) -> dict[str, int]:
    """Return helper-like modules that exceed the helper line budget."""
    helpers: dict[str, int] = {}
    for root_name in PACKAGE_SCAN_ROOTS:
        root = repo_root / root_name
        if not root.exists():
            continue
        for module_path in root.rglob("*.py"):
            relative_path = module_path.relative_to(repo_root).as_posix()
            if not is_in_scope(relative_path):
                continue
            if not any(marker in module_path.stem for marker in HELPER_NAME_MARKERS):
                continue
            line_count = count_lines(module_path)
            if line_count > DEFAULT_LARGE_HELPER_MAX_LINES:
                helpers[relative_path] = line_count
    return helpers


def _validate_count_override(
    *,
    actual: int,
    maximum: int,
    path: str,
    noun: str,
) -> list[Violation]:
    if actual > maximum:
        return [Violation(path, f"{noun} count is {actual}, above allowed {maximum}")]
    if actual < maximum:
        return [
            Violation(
                path,
                f"{noun} count is {actual}, below ratchet {maximum}; update the structure override",
            ),
        ]
    return []


def _validate_path_exists(repo_root: Path, relative_path: str) -> list[Violation]:
    if not (repo_root / relative_path).exists():
        return [
            Violation(
                relative_path, "configured architecture-structure path does not exist"
            )
        ]
    return []


def validate_root_module_counts(
    *,
    repo_root: Path,
    overrides: Sequence[RootModuleCountOverride],
) -> list[Violation]:
    """Validate top-level service module-count ratchets."""
    violations: list[Violation] = []
    by_path = {override.path: override for override in overrides}
    for service_root in SERVICE_ROOTS:
        override = by_path.get(service_root)
        if override is None:
            violations.append(
                Violation(service_root, "missing root module-count structure override"),
            )
            continue
        violations.extend(_validate_path_exists(repo_root, service_root))
        count = len(_direct_python_modules(repo_root / service_root))
        violations.extend(
            _validate_count_override(
                actual=count,
                maximum=override.max_modules,
                path=service_root,
                noun="root module",
            ),
        )
        if override.target_modules >= override.max_modules:
            violations.append(
                Violation(
                    service_root,
                    "target_modules must be lower than max_modules to keep the packaging ratchet meaningful",
                ),
            )
    for override in overrides:
        if override.path not in SERVICE_ROOTS:
            violations.append(
                Violation(
                    override.path,
                    "root module-count override points outside known service roots",
                ),
            )
    return violations


def validate_root_module_families(
    *,
    repo_root: Path,
    overrides: Sequence[RootModuleFamilyOverride],
    max_modules: int = DEFAULT_ROOT_FAMILY_MAX_MODULES,
) -> list[Violation]:
    """Validate service-root module-family sprawl."""
    violations: list[Violation] = []
    by_key = {(override.path, override.prefix): override for override in overrides}
    seen_keys: set[tuple[str, str]] = set()
    for service_root in SERVICE_ROOTS:
        families = root_module_families(repo_root / service_root)
        for prefix, module_paths in families.items():
            count = len(module_paths)
            if count <= max_modules:
                continue
            override = by_key.get((service_root, prefix))
            if override is None:
                violations.append(
                    Violation(
                        f"{service_root}/{prefix}_*.py",
                        f"root module family has {count} modules; package it or add a documented structure override",
                    ),
                )
                continue
            seen_keys.add((service_root, prefix))
            violations.extend(
                _validate_count_override(
                    actual=count,
                    maximum=override.max_modules,
                    path=f"{service_root}/{prefix}_*.py",
                    noun="root module family",
                ),
            )
    for override in overrides:
        violations.extend(_validate_path_exists(repo_root, override.path))
        if (override.path, override.prefix) not in seen_keys:
            violations.append(
                Violation(
                    f"{override.path}/{override.prefix}_*.py",
                    "stale root module-family override; family is no longer above the default threshold",
                ),
            )
    return violations


def validate_package_module_counts(
    *,
    repo_root: Path,
    overrides: Sequence[PackageModuleCountOverride],
    max_modules: int = DEFAULT_PACKAGE_MAX_MODULES,
) -> list[Violation]:
    """Validate package direct-module-count sprawl."""
    violations: list[Violation] = []
    counts = package_direct_module_counts(repo_root)
    by_path = {override.path: override for override in overrides}
    seen_paths: set[str] = set()
    for path, count in counts.items():
        if count <= max_modules:
            continue
        override = by_path.get(path)
        if override is None:
            violations.append(
                Violation(
                    path,
                    f"package has {count} direct Python modules; split it or add a documented structure override",
                ),
            )
            continue
        seen_paths.add(path)
        violations.extend(
            _validate_count_override(
                actual=count,
                maximum=override.max_modules,
                path=path,
                noun="package direct-module",
            ),
        )
    for override in overrides:
        violations.extend(_validate_path_exists(repo_root, override.path))
        if override.path not in seen_paths:
            violations.append(
                Violation(
                    override.path,
                    "stale package module-count override; package is no longer above the default threshold",
                ),
            )
    return violations


def validate_large_helper_modules(
    *,
    repo_root: Path,
    overrides: Sequence[LargeHelperModuleOverride],
) -> list[Violation]:
    """Validate helper-like module line-count sprawl."""
    violations: list[Violation] = []
    helpers = large_helper_modules(repo_root)
    by_path = {override.path: override for override in overrides}
    seen_paths: set[str] = set()
    for path, line_count in helpers.items():
        override = by_path.get(path)
        if override is None:
            violations.append(
                Violation(
                    path,
                    f"helper-like module has {line_count} lines; split it or add a documented structure override",
                ),
            )
            continue
        seen_paths.add(path)
        if line_count > override.max_lines:
            violations.append(
                Violation(
                    path,
                    f"helper-like module has {line_count} lines, above allowed {override.max_lines}",
                ),
            )
        elif line_count < override.max_lines:
            violations.append(
                Violation(
                    path,
                    f"helper-like module has {line_count} lines, below ratchet {override.max_lines}; update the structure override",
                ),
            )
    for override in overrides:
        violations.extend(_validate_path_exists(repo_root, override.path))
        if override.path not in seen_paths:
            violations.append(
                Violation(
                    override.path,
                    "stale large-helper override; module is no longer above the helper threshold",
                ),
            )
    return violations


def _module_name_for_path(repo_root: Path, module_path: Path) -> str:
    relative = module_path.relative_to(repo_root).with_suffix("")
    parts = relative.parts
    if len(parts) >= SERVICE_MODULE_PATH_MIN_PARTS and parts[0] == "services":
        parts = parts[1:]
    return ".".join(part for part in parts if part != "__init__")


def _resolve_relative_import(
    *,
    current_module: str,
    is_package_module: bool,
    level: int,
    imported_module: str | None,
    imported_names: Sequence[str],
) -> list[str]:
    current_package = (
        current_module if is_package_module else current_module.rpartition(".")[0]
    )
    package_parts = current_package.split(".") if current_package else []
    if level > 1:
        package_parts = package_parts[: -(level - 1)]
    base = ".".join(
        part for part in (*package_parts, *(imported_module or "").split(".")) if part
    )
    if imported_module:
        return [base]
    return [f"{base}.{name}" if base else name for name in imported_names]


def _import_targets_for_node(
    *,
    node: ast.AST,
    current_module: str,
    is_package_module: bool,
) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not isinstance(node, ast.ImportFrom):
        return []
    imported_names = [alias.name for alias in node.names if alias.name != "*"]
    if node.level:
        return _resolve_relative_import(
            current_module=current_module,
            is_package_module=is_package_module,
            level=node.level,
            imported_module=node.module,
            imported_names=imported_names,
        )
    return [node.module] if node.module else imported_names


def _internal_dependency_for_import(
    *,
    imported_name: str,
    module_names: Iterable[str],
) -> str | None:
    candidates = [
        module_name
        for module_name in module_names
        if imported_name == module_name
        or imported_name.startswith(f"{module_name}.")
        or module_name.startswith(f"{imported_name}.")
    ]
    if not candidates:
        return None
    return max(candidates, key=len)


def build_import_graph(repo_root: Path, package_root: Path) -> dict[str, set[str]]:
    """Build a best-effort internal import graph for a package root."""
    modules = {
        _module_name_for_path(repo_root, module_path): module_path
        for module_path in package_root.rglob("*.py")
        if not _has_excluded_part(module_path.relative_to(repo_root))
    }
    graph: dict[str, set[str]] = {module_name: set() for module_name in modules}
    module_names = set(modules)
    for module_name, module_path in modules.items():
        tree = ast.parse(
            module_path.read_text(encoding="utf-8"),
            filename=str(module_path),
        )
        is_package_module = module_path.name == "__init__.py"
        for node in ast.walk(tree):
            for imported_name in _import_targets_for_node(
                node=node,
                current_module=module_name,
                is_package_module=is_package_module,
            ):
                dependency = _internal_dependency_for_import(
                    imported_name=imported_name,
                    module_names=module_names,
                )
                if dependency is not None and dependency != module_name:
                    graph[module_name].add(dependency)
    return graph


def import_cycles(graph: Mapping[str, set[str]]) -> list[tuple[str, ...]]:
    """Return internal import cycles from a module graph."""
    visited: set[str] = set()
    active: set[str] = set()
    stack: list[str] = []
    cycles: list[tuple[str, ...]] = []
    seen_cycle_keys: set[tuple[str, ...]] = set()

    def visit(module_name: str) -> None:
        visited.add(module_name)
        active.add(module_name)
        stack.append(module_name)
        for dependency in sorted(graph.get(module_name, ())):
            if dependency not in visited:
                visit(dependency)
            elif dependency in active:
                cycle = tuple(stack[stack.index(dependency) :] + [dependency])
                cycle_key = tuple(sorted(set(cycle)))
                if cycle_key not in seen_cycle_keys:
                    seen_cycle_keys.add(cycle_key)
                    cycles.append(cycle)
        stack.pop()
        active.remove(module_name)

    for module_name in sorted(graph):
        if module_name not in visited:
            visit(module_name)
    return cycles


def validate_import_cycles(
    *,
    repo_root: Path,
    roots: Sequence[ImportCycleRoot],
) -> list[Violation]:
    """Validate configured package roots for internal import cycles."""
    violations: list[Violation] = []
    for root in roots:
        package_root = repo_root / root.path
        violations.extend(_validate_path_exists(repo_root, root.path))
        if not package_root.exists():
            continue
        try:
            graph = build_import_graph(repo_root, package_root)
        except (SyntaxError, UnicodeDecodeError) as exc:
            violations.append(
                Violation(
                    root.path,
                    f"could not parse Python while checking imports: {exc}",
                ),
            )
            continue
        cycles = import_cycles(graph)
        for cycle in cycles:
            violations.append(
                Violation(root.path, "import cycle detected: " + " -> ".join(cycle)),
            )
    return violations


def _imported_facade_modules(repo_root: Path, module_path: Path) -> set[str]:
    try:
        tree = ast.parse(
            module_path.read_text(encoding="utf-8"), filename=str(module_path)
        )
    except (SyntaxError, UnicodeDecodeError):
        return set()
    current_module = _module_name_for_path(repo_root, module_path)
    is_package_module = module_path.name == "__init__.py"
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
            imported_modules.update(
                f"{node.module}.{alias.name}"
                for alias in node.names
                if alias.name != "*"
            )
        elif isinstance(node, ast.ImportFrom) and node.level:
            imported_modules.update(
                _import_targets_for_node(
                    node=node,
                    current_module=current_module,
                    is_package_module=is_package_module,
                ),
            )
    return imported_modules


def _is_internal_package_module(relative_path: Path) -> bool:
    parts = relative_path.parts
    if len(parts) < SCRIPT_INTERNAL_MODULE_MIN_PARTS:
        return False
    if parts[0] == "scripts":
        return True
    return len(parts) >= SERVICE_INTERNAL_MODULE_MIN_PARTS and parts[0] == "services"


def validate_compatibility_facade_imports(
    *,
    repo_root: Path,
    facades: Sequence[CompatibilityFacade],
) -> list[Violation]:
    """Validate package internals do not import compatibility facades."""
    violations: list[Violation] = []
    facade_by_module = {facade.module: facade for facade in facades}
    facade_paths = {facade.path for facade in facades}
    for facade in facades:
        violations.extend(_validate_path_exists(repo_root, facade.path))
        if not facade.module.strip():
            violations.append(
                Violation(facade.path, "compatibility facade module is empty")
            )
        if not facade.canonical_package.strip():
            violations.append(
                Violation(
                    facade.path, "compatibility facade canonical_package is empty"
                ),
            )
    if not facade_by_module:
        return violations

    for root_name in PACKAGE_SCAN_ROOTS:
        root = repo_root / root_name
        if not root.exists():
            continue
        for module_path in root.rglob("*.py"):
            relative_path = module_path.relative_to(repo_root)
            relative_text = relative_path.as_posix()
            if relative_text in facade_paths:
                continue
            if _has_excluded_part(relative_path):
                continue
            if not _is_internal_package_module(relative_path):
                continue
            for imported_module in sorted(
                _imported_facade_modules(repo_root, module_path)
            ):
                facade = facade_by_module.get(imported_module)
                if facade is None:
                    continue
                violations.append(
                    Violation(
                        relative_text,
                        (
                            "internal package module imports compatibility facade "
                            f"{facade.module}; use {facade.canonical_package} instead"
                        ),
                    ),
                )
    return violations


def validate_structure(
    *,
    repo_root: Path,
    config: StructureConfig,
) -> list[Violation]:
    """Run all architecture-structure validations."""
    violations: list[Violation] = []
    violations.extend(
        validate_root_module_counts(
            repo_root=repo_root,
            overrides=config.root_module_counts,
        ),
    )
    violations.extend(
        validate_root_module_families(
            repo_root=repo_root,
            overrides=config.root_module_families,
        ),
    )
    violations.extend(
        validate_package_module_counts(
            repo_root=repo_root,
            overrides=config.package_module_counts,
        ),
    )
    violations.extend(
        validate_large_helper_modules(
            repo_root=repo_root,
            overrides=config.large_helper_modules,
        ),
    )
    violations.extend(
        validate_import_cycles(
            repo_root=repo_root,
            roots=config.import_cycle_roots,
        ),
    )
    violations.extend(
        validate_compatibility_facade_imports(
            repo_root=repo_root,
            facades=config.compatibility_facades,
        ),
    )
    return violations


def _load_config(config_path: Path) -> tuple[StructureConfig, list[Violation]]:
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return StructureConfig((), (), (), (), (), ()), [
            Violation(
                config_path.name, "architecture-structure config file is missing"
            ),
        ]
    except json.JSONDecodeError as exc:
        return StructureConfig((), (), (), (), (), ()), [
            Violation(config_path.name, f"invalid JSON: {exc.msg}"),
        ]
    return parse_config(raw)


def main() -> int:
    """CLI entrypoint."""
    config, parse_errors = _load_config(CONFIG_FILE)
    violations = [*parse_errors]
    if not violations:
        violations.extend(validate_structure(repo_root=REPO_ROOT, config=config))
    if not violations:
        root_counts = {
            service_root: len(_direct_python_modules(REPO_ROOT / service_root))
            for service_root in SERVICE_ROOTS
        }
        count_text = ", ".join(
            f"{service_root}={count}" for service_root, count in root_counts.items()
        )
        print(f"architecture_structure: ok ({count_text})")
        return 0

    print("architecture_structure: error")
    print(
        "Structure rules prevent new root-module sprawl, dense packages, large helper buckets, and import cycles.",
    )
    for violation in sorted(violations, key=lambda item: (item.path, item.message)):
        print(f"- {violation.path}: {violation.message}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
