#!/usr/bin/env python3
"""Fail when `typing.Any` appears in the trees AGENTS.md bans it from.

AGENTS.md has said "avoid `Any` in new Python code" since before this guard
existed, and the rule was enforced by people reading diffs.  It did not hold.
Seven `dict[str, Any]` annotations reached HEAD on one branch; three were found
by review, a sweep for the rest was promised, and four survived it.  A rule
whose enforcement is a promise to have looked is not enforced.

Two things let them through.  `tests/unit/` was outside every ruff path, so the
linter never opened those files at all.  And ruff has no rule that fits anyway:
ANN401 covers parameter and return annotations, not
`fixture: dict[str, Any] = load(...)` on a local, which is the exact shape that
slipped.  So the ban is checked here, over the syntax tree, where it can see
every position `Any` can occupy.

Why the syntax tree rather than a grep: this repository's prose says "Any" a
lot -- "Any run of at least", "Any request that creates" -- and a guard that
cries wolf on a comment is a guard people learn to bypass.  Parsing means a
comment, a docstring and a plain string are simply not annotations, with no
allowlist to maintain and no false positive to explain away.

What it looks for:

* `from typing import Any` and `from typing_extensions import Any`, under any
  alias.  This is the backstop: `Any` has to be imported to be used, so a
  position this file forgets to inspect is still caught at the import.
* the name `Any` and the attribute `typing.Any`, anywhere -- annotation,
  subscript such as `dict[str, Any]`, `isinstance` argument, or plain
  assignment.  Nothing else in this repository is called `Any`.
* `Any` inside a string annotation or a `cast("...")` target, which is how the
  same widening was written on the branch that prompted this guard.

Run it with no arguments to check the guarded trees; pass paths to check
something else, which is how the tests exercise it.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The trees where the ban is enforced.  Deliberately whole trees rather than a
#: list of files: a list is a thing to forget to add to, and forgetting is the
#: failure this guard exists to remove.  Service runtime packages are absent on
#: purpose -- they normalize external JSON, Pydantic and SQLAlchemy payloads at
#: their boundaries, which is the case `disallow_any_expr = false` in
#: pyproject.toml already records as intentional.
GUARDED_ROOTS: tuple[str, ...] = (
    "scripts",
    "tests",
    "services/artana_evidence_api/tests",
    "services/artana_evidence_db/tests",
)

_SKIPPED_DIRECTORY_NAMES = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache"})
_ANY_MODULES = frozenset({"typing", "typing_extensions"})
_ANY_IN_TEXT = re.compile(r"(?<![A-Za-z0-9_])Any(?![A-Za-z0-9_])")


#: Marks a file the checker could not read.  Kept as a violation rather than a
#: skip, and distinguished from a real hit only when the report is printed: a
#: guard that treats unreadable input as clean is the failure mode this whole
#: family of checks was written against.
UNPARSED = "could not be parsed"


@dataclass(frozen=True)
class Violation:
    """One banned `Any`, ready to print as an editor-navigable line."""

    path: str
    line: int
    detail: str

    @property
    def unparsed(self) -> bool:
        """Whether this reports an unreadable file rather than a banned use."""

        return self.detail.startswith(UNPARSED)

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.detail}"


class _AnyVisitor(ast.NodeVisitor):
    """Collect every position where `Any` is imported or annotated."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.violations: list[Violation] = []

    def _record(self, node: ast.AST, detail: str) -> None:
        line = getattr(node, "lineno", 0)
        self.violations.append(Violation(self.path, line, detail))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if node.module in _ANY_MODULES:
            for alias in node.names:
                if alias.name == "Any":
                    imported = (
                        f"{node.module}.Any as {alias.asname}"
                        if alias.asname
                        else f"{node.module}.Any"
                    )
                    self._record(
                        node,
                        f"`{imported}` is imported; AGENTS.md bans `Any` here. "
                        "Use a concrete type, a protocol, or a narrowing helper "
                        "such as tests/json_narrowing.py.",
                    )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        if node.id == "Any":
            self._record(node, "`Any` referenced")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        if node.attr == "Any":
            self._record(node, "`Any` referenced")
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        self._check_string_annotation(node.annotation)
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> None:
        if node.annotation is not None:
            self._check_string_annotation(node.annotation)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        if node.returns is not None:
            self._check_string_annotation(node.returns)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        if node.returns is not None:
            self._check_string_annotation(node.returns)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        # `cast("dict[str, Any]", value)` is an annotation wearing a string, and
        # it is how the widening was written on the branch that prompted this.
        if _is_cast(node.func) and node.args:
            self._check_string_annotation(node.args[0])
        self.generic_visit(node)

    def _check_string_annotation(self, annotation: ast.expr) -> None:
        """Catch the alias where it hides inside a quoted type.

        The name and attribute forms are caught wherever they appear, so this
        only has to reach the one place the syntax tree stops looking like
        code: a type written as a string, which is legal in every annotation
        position and required in a `cast`.
        """

        for node in ast.walk(annotation):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and _ANY_IN_TEXT.search(node.value)
            ):
                self._record(
                    node,
                    f"`Any` used in the string annotation {node.value!r}",
                )


def _is_cast(func: ast.expr) -> bool:
    if isinstance(func, ast.Name):
        return func.id == "cast"
    return isinstance(func, ast.Attribute) and func.attr == "cast"


def violations_in_source(source: str, *, path: str) -> list[Violation]:
    """Report every banned `Any` in one module's source text.

    A file that does not parse is reported rather than skipped: a guard that
    treats unreadable input as clean is the failure mode this whole family of
    checks was written against.
    """

    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        detail = f"{UNPARSED}: {error.msg}"
        return [Violation(path, error.lineno or 0, detail)]

    visitor = _AnyVisitor(path)
    visitor.visit(tree)
    return sorted(visitor.violations, key=lambda item: (item.line, item.detail))


def python_files(target: Path) -> Iterator[Path]:
    """Every Python module the given file or directory stands for."""

    if not target.is_dir():
        yield target
        return
    for path in sorted(target.rglob("*.py")):
        if _SKIPPED_DIRECTORY_NAMES.isdisjoint(path.parts):
            yield path


def violations_in_paths(
    paths: Iterable[Path],
    *,
    repo_root: Path = REPO_ROOT,
) -> list[Violation]:
    """Report every banned `Any` under the given files or directories."""

    found: list[Violation] = []
    for given in paths:
        for path in python_files(given):
            try:
                relative = str(path.resolve().relative_to(repo_root))
            except ValueError:
                relative = str(path)
            found.extend(
                violations_in_source(
                    path.read_text(encoding="utf-8"),
                    path=relative,
                ),
            )
    return found


def guarded_paths(repo_root: Path = REPO_ROOT) -> list[Path]:
    """The guarded roots that exist in this checkout."""

    return [repo_root / root for root in GUARDED_ROOTS if (repo_root / root).is_dir()]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="files or directories to check; defaults to the guarded roots",
    )
    arguments = parser.parse_args(argv)

    targets = [Path(path) for path in arguments.paths] or guarded_paths()
    violations = violations_in_paths(targets)
    unreadable = [violation for violation in violations if violation.unparsed]
    banned = [violation for violation in violations if not violation.unparsed]
    if unreadable:
        # Almost always the wrong interpreter: this repository is Python 3.13,
        # and 3.9 cannot parse a match statement or a PEP 695 alias. Say so,
        # rather than reporting it as a banned annotation and sending the
        # reader to a line that does not have one.
        print(
            f"{len(unreadable)} file(s) could not be parsed by "
            f"Python {sys.version_info.major}.{sys.version_info.minor}; "
            "this repository requires 3.13:",
            file=sys.stderr,
        )
        for violation in unreadable:
            print(f"  {violation}", file=sys.stderr)
    if banned:
        print(f"{len(banned)} banned use(s) of `Any`:", file=sys.stderr)
        for violation in banned:
            print(f"  {violation}", file=sys.stderr)
        print(
            "AGENTS.md: avoid `Any` in new Python code. Use concrete types, "
            "protocols, dataclasses, Pydantic models, or service-local typed "
            "contracts.",
            file=sys.stderr,
        )
    if violations:
        return 1

    checked = sum(1 for target in targets for _ in python_files(target))
    print(f"typing `Any` ban: {checked} Python files clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
