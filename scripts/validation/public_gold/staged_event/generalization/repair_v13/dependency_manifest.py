"""Deterministically hash the repository-local Python import closure."""

from __future__ import annotations

import ast
import hashlib
import tokenize
from collections import deque
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path


class DependencyManifestError(RuntimeError):
    """A Python dependency cannot be frozen without ambiguity."""


@dataclass(frozen=True, slots=True)
class DependencyManifestEntry:
    """One repository-relative Python dependency and its byte digest."""

    path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class _LocalPackageRoot:
    module_name: str
    relative_directory: Path


@dataclass(frozen=True, slots=True)
class _ModuleLocation:
    name: str
    source: Path | None
    is_package: bool


@dataclass(frozen=True, slots=True)
class _ImportTarget:
    name: str
    required: bool


_LOCAL_PACKAGE_ROOTS = (
    _LocalPackageRoot("scripts", Path("scripts")),
    _LocalPackageRoot(
        "artana_evidence_api",
        Path("services/artana_evidence_api"),
    ),
)


def build_dependency_manifest(
    repo_root: Path,
    root_files: Iterable[str | Path],
) -> tuple[DependencyManifestEntry, ...]:
    """Return the sorted local scripts and Evidence API dependency manifest."""

    repository = _RepositoryPythonModules(repo_root)
    closure = _ImportClosure(repository).resolve(root_files)
    return tuple(
        DependencyManifestEntry(
            path=repository.relative_path(path),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in closure
    )


class _ImportClosure:
    """Traverse imports while keeping hashing and path custody separate."""

    def __init__(self, repository: _RepositoryPythonModules) -> None:
        self._repository = repository

    def resolve(self, root_files: Iterable[str | Path]) -> tuple[Path, ...]:
        pending: deque[Path] = deque()
        discovered: set[Path] = set()
        roots = tuple(root_files)
        if not roots:
            message = "at least one Python root file is required"
            raise DependencyManifestError(message)
        for root in roots:
            path = self._repository.root_file(root)
            self._enqueue_module_files(
                self._repository.location_for_source(path),
                pending,
                discovered,
            )

        while pending:
            source = pending.popleft()
            for target in _scan_imports(
                source,
                self._repository.module_name(source),
                is_package=source.name == "__init__.py",
            ):
                location = self._repository.find_module(
                    target.name,
                    required=target.required,
                )
                if location is not None:
                    self._enqueue_module_files(location, pending, discovered)

        return tuple(sorted(discovered, key=self._repository.relative_path))

    def _enqueue_module_files(
        self,
        location: _ModuleLocation,
        pending: deque[Path],
        discovered: set[Path],
    ) -> None:
        for path in self._repository.executed_files(location):
            if path in discovered:
                continue
            discovered.add(path)
            pending.append(path)


class _RepositoryPythonModules:
    """Resolve Python module names without importing or executing repository code."""

    def __init__(self, repo_root: Path) -> None:
        try:
            root = repo_root.resolve(strict=True)
        except OSError as exc:
            message = f"repository root is unavailable: {repo_root}"
            raise DependencyManifestError(message) from exc
        if not root.is_dir():
            message = f"repository root is not a directory: {repo_root}"
            raise DependencyManifestError(message)
        self.root = root

    def root_file(self, value: str | Path) -> Path:
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            message = f"root file must be repository-relative: {value}"
            raise DependencyManifestError(message)
        path = self.root / relative
        self._require_contained(path)
        if not path.is_file():
            message = f"Python root file is missing: {relative.as_posix()}"
            raise DependencyManifestError(message)
        if path.suffix != ".py":
            message = f"dependency root is not Python: {relative.as_posix()}"
            raise DependencyManifestError(message)
        self.module_name(path)
        return path

    def module_name(self, source: Path) -> str:
        relative = Path(self.relative_path(source))
        if relative.suffix != ".py" or not relative.parts:
            message = f"dependency is not a Python source file: {relative.as_posix()}"
            raise DependencyManifestError(message)
        package_root = _package_root_for_path(relative)
        if package_root is None:
            message = (
                "dependency roots and local imports must live under scripts/ "
                "or services/artana_evidence_api/: "
                f"{relative.as_posix()}"
            )
            raise DependencyManifestError(message)
        prefix_length = len(package_root.relative_directory.parts)
        parts = [
            package_root.module_name,
            *relative.with_suffix("").parts[prefix_length:],
        ]
        if parts[-1] == "__init__":
            parts.pop()
        if not all(part.isidentifier() for part in parts):
            message = f"dependency has an invalid module path: {relative.as_posix()}"
            raise DependencyManifestError(message)
        return ".".join(parts)

    def relative_path(self, path: Path) -> str:
        self._require_contained(path)
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError as exc:
            message = f"dependency path escapes repository: {path}"
            raise DependencyManifestError(message) from exc

    def location_for_source(self, source: Path) -> _ModuleLocation:
        return _ModuleLocation(
            name=self.module_name(source),
            source=source,
            is_package=source.name == "__init__.py",
        )

    def find_module(
        self,
        name: str,
        *,
        required: bool,
    ) -> _ModuleLocation | None:
        parts = name.split(".")
        package_root = _package_root_for_module(name)
        if (
            not parts
            or package_root is None
            or not all(part.isidentifier() for part in parts)
        ):
            message = f"invalid repository-local module name: {name}"
            raise DependencyManifestError(message)

        module_base = self.root / package_root.relative_directory
        if len(parts) > 1:
            module_base = module_base.joinpath(*parts[1:])
        source = module_base.with_suffix(".py")
        package = module_base
        self._require_contained(source, allow_missing=True)
        self._require_contained(package, allow_missing=True)
        source_exists = source.is_file()
        package_exists = package.is_dir()
        if source_exists and package_exists:
            message = f"ambiguous file and package module: {name}"
            raise DependencyManifestError(message)
        if source_exists:
            return _ModuleLocation(name=name, source=source, is_package=False)
        if package_exists:
            initializer = package / "__init__.py"
            self._require_contained(initializer, allow_missing=True)
            return _ModuleLocation(
                name=name,
                source=initializer if initializer.is_file() else None,
                is_package=True,
            )
        if required:
            message = f"repository-local import is missing: {name}"
            raise DependencyManifestError(message)
        return None

    def executed_files(self, location: _ModuleLocation) -> tuple[Path, ...]:
        parts = location.name.split(".")
        package_depth = len(parts) if location.is_package else len(parts) - 1
        executed: list[Path] = []
        for depth in range(1, package_depth + 1):
            package_name = ".".join(parts[:depth])
            package_root = _package_root_for_module(package_name)
            if package_root is None:
                message = f"unknown local package root: {location.name}"
                raise DependencyManifestError(message)
            package = self.root / package_root.relative_directory
            if depth > 1:
                package = package.joinpath(*parts[1:depth])
            self._require_contained(package)
            if not package.is_dir():
                message = f"module package directory is missing: {location.name}"
                raise DependencyManifestError(message)
            initializer = package / "__init__.py"
            self._require_contained(initializer, allow_missing=True)
            if initializer.is_file():
                executed.append(initializer)
        if location.source is not None and location.source not in executed:
            self._require_contained(location.source)
            if not location.source.is_file():
                message = f"module source is missing: {location.name}"
                raise DependencyManifestError(message)
            executed.append(location.source)
        return tuple(executed)

    def _require_contained(
        self,
        path: Path,
        *,
        allow_missing: bool = False,
    ) -> None:
        try:
            resolved = path.resolve(strict=not allow_missing)
        except OSError as exc:
            message = f"dependency path is unavailable: {path}"
            raise DependencyManifestError(message) from exc
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            message = f"dependency path escapes repository: {path}"
            raise DependencyManifestError(message) from exc


def _scan_imports(
    source: Path,
    module_name: str,
    *,
    is_package: bool,
) -> Iterator[_ImportTarget]:
    try:
        with tokenize.open(source) as handle:
            tree = ast.parse(handle.read(), filename=str(source))
    except (OSError, SyntaxError, UnicodeError) as exc:
        message = f"cannot parse dependency imports: {source}"
        raise DependencyManifestError(message) from exc

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_local_module(alias.name):
                    yield _ImportTarget(alias.name, required=True)
        elif isinstance(node, ast.ImportFrom):
            yield from _from_import_targets(
                node,
                module_name=module_name,
                is_package=is_package,
            )


def _from_import_targets(
    node: ast.ImportFrom,
    *,
    module_name: str,
    is_package: bool,
) -> Iterator[_ImportTarget]:
    base = _from_import_base(
        node,
        module_name=module_name,
        is_package=is_package,
    )
    if base is None:
        return
    yield _ImportTarget(base, required=True)
    for alias in node.names:
        if alias.name != "*":
            yield _ImportTarget(f"{base}.{alias.name}", required=False)


def _from_import_base(
    node: ast.ImportFrom,
    *,
    module_name: str,
    is_package: bool,
) -> str | None:
    if node.level == 0:
        return node.module if node.module and _is_local_module(node.module) else None

    package = module_name.split(".")
    if not is_package:
        package.pop()
    ascents = node.level - 1
    if ascents >= len(package):
        message = f"relative import escapes local package: {module_name}"
        raise DependencyManifestError(message)
    base_parts = package[: len(package) - ascents]
    if node.module:
        base_parts.extend(node.module.split("."))
    base = ".".join(base_parts)
    if not _is_local_module(base):
        message = f"relative import escapes local package: {module_name}"
        raise DependencyManifestError(message)
    return base


def _is_local_module(name: str) -> bool:
    return _package_root_for_module(name) is not None


def _package_root_for_module(name: str) -> _LocalPackageRoot | None:
    first = name.partition(".")[0]
    return next(
        (root for root in _LOCAL_PACKAGE_ROOTS if root.module_name == first),
        None,
    )


def _package_root_for_path(path: Path) -> _LocalPackageRoot | None:
    return next(
        (
            root
            for root in _LOCAL_PACKAGE_ROOTS
            if path.parts[: len(root.relative_directory.parts)]
            == root.relative_directory.parts
        ),
        None,
    )


__all__ = [
    "DependencyManifestEntry",
    "DependencyManifestError",
    "build_dependency_manifest",
]
