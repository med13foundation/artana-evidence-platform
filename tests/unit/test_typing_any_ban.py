"""The typing ban must be checked by something that runs, not by a promise.

The rule, the history that produced it, and the shapes it has to catch are
documented in `scripts/ci/check_typing_any_ban.py`.  The short version: AGENTS.md
has ruled the catch-all typing alias out of new Python for a long time, the
enforcement was people reading diffs, and seven annotations reached HEAD on one
branch regardless -- review caught three, a sweep for the rest was reported as
done, and four survived that sweep.  A rule enforced by having looked is a rule
that holds until someone is tired.

So there are two claims to hold the guard to, and each has tests here:

* it is green on the trees it guards, which is the check that runs, and
* it is red the moment the alias comes back, in every shape the branch actually
  used -- including the local variable annotation ruff's ANN401 does not cover
  and the `cast("...")` form that hides a type inside a string.

The second is the one that matters.  A guard nobody has watched fail is a guard
nobody knows works.

The banned token is spelled indirectly throughout this file.  This module sits
inside a guarded tree, and a literal occurrence here would be indistinguishable
-- to the guard's own scan, and to anyone grepping a diff of this branch --
from the annotations it exists to prevent.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from scripts.ci.check_typing_any_ban import (
    GUARDED_ROOTS,
    guarded_paths,
    python_files,
    violations_in_paths,
    violations_in_source,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: The banned alias, assembled rather than written.  See the module docstring.
_ALIAS = "An" + "y"

#: Every shape the reviewed branch actually introduced, plus the positions a
#: future edit is most likely to reach for.  Held as source text rather than as
#: committed fixture files, because a fixture carrying the alias inside a
#: guarded tree would make the guard fail on itself.
_REINTRODUCTIONS = {
    "local variable annotation": (
        f"from typing import {_ALIAS}\n\n\n"
        "def load() -> None:\n"
        f"    fixture: dict[str, {_ALIAS}] = read()\n"
    ),
    "string cast target": (
        "from typing import cast\n\n\n"
        "def load() -> None:\n"
        f'    fixture = cast("dict[str, {_ALIAS}]", read())\n'
    ),
    "parameter annotation": (
        f"from typing import {_ALIAS}\n\n\n"
        f"def score(payload: dict[str, {_ALIAS}]) -> None:\n"
        "    return None\n"
    ),
    "return annotation": (
        f"from typing import {_ALIAS}\n\n\ndef score() -> {_ALIAS}:\n"
        "    return None\n"
    ),
    "qualified attribute": (
        f"import typing\n\n\ndef score() -> typing.{_ALIAS}:\n    return None\n"
    ),
    "aliased import": f"from typing import {_ALIAS} as Whatever\n",
    "typing_extensions import": f"from typing_extensions import {_ALIAS}\n",
}

#: Prose that uses the word without meaning the type.  The first two are real
#: lines in guarded trees, and a grep-based guard fails on both -- which is why
#: this one parses instead.  A guard that cries wolf is a guard people learn to
#: bypass.
_INNOCENT = {
    "sentence in a comment": (
        f"#: Probe every STRIDE characters.  {_ALIAS} run of 32 is indexed.\nX = 1\n"
    ),
    "sentence in a docstring": (
        f'"""{_ALIAS} request that creates live source searches must set it."""\n'
    ),
    "sentence in a string literal": f'MESSAGE = "{_ALIAS} request must set it"\n',
    "longer identifier that contains it": f"{_ALIAS}thing = 1\n",
    "lower-case attribute of the same word": (
        f"value = payload.{_ALIAS.lower()}\n"
    ),
}


@pytest.mark.parametrize(("label", "source"), sorted(_REINTRODUCTIONS.items()))
def test_the_guard_is_red_when_the_alias_comes_back(label: str, source: str) -> None:
    """Watch the guard fail, once per shape, so its greens can be believed."""

    violations = violations_in_source(source, path=f"synthetic/{label}.py")

    assert violations, f"a reintroduced alias as a {label} was not reported"
    assert all(violation.line > 0 for violation in violations), (
        "every report must name a line, or it cannot be acted on"
    )


@pytest.mark.parametrize(("label", "source"), sorted(_INNOCENT.items()))
def test_the_guard_is_quiet_about_prose_that_merely_says_the_word(
    label: str,
    source: str,
) -> None:
    """The reason this guard parses rather than greps."""

    assert violations_in_source(source, path=f"synthetic/{label}.py") == [], (
        f"a {label} was reported as a banned annotation"
    )


def test_a_file_that_does_not_parse_is_reported_not_skipped() -> None:
    """Unreadable input must never be counted as clean."""

    violations = violations_in_source("def broken(\n", path="synthetic/broken.py")

    assert len(violations) == 1
    assert "could not be parsed" in violations[0].detail


def test_the_guarded_trees_are_clean() -> None:
    """The check itself.  This is what has to stay green."""

    violations = violations_in_paths(guarded_paths())

    assert violations == [], "\n".join(str(violation) for violation in violations)


def test_the_guard_covers_the_trees_the_lint_gate_could_not_see() -> None:
    """`tests/unit/` is where the seven landed, and ruff never opened it.

    The lint gate listed service packages and `tests/e2e/`, so every file this
    guard exists for sat outside it.  The Makefile now points ruff at the whole
    `tests` tree as well, but ruff still has no rule for a local variable
    annotation, so these roots must stay named here too.
    """

    assert "tests" in GUARDED_ROOTS
    assert "services/artana_evidence_api/tests" in GUARDED_ROOTS
    assert "services/artana_evidence_db/tests" in GUARDED_ROOTS
    assert "scripts" in GUARDED_ROOTS

    guarded = {
        path.resolve() for root in guarded_paths() for path in python_files(root)
    }

    assert (_REPO_ROOT / "tests/unit/test_corpus_attestation.py").resolve() in guarded
    assert (
        _REPO_ROOT / "scripts/validation/restricted_corpus_normalization.py"
    ).resolve() in guarded
    assert len(guarded) > 100, "the guard must be walking real trees, not an empty one"


def test_the_ban_is_wired_into_gates_that_run() -> None:
    """A check outside every gate is documentation, and documentation is what
    failed here.

    `service-checks` covers the local one-command gate and the full CI branch;
    pre-commit covers the commit; and the workflow job covers the case the
    planner would otherwise skip entirely -- a pull request touching only
    `tests/unit/` runs the changed test files and nothing else, which is
    exactly the shape that put the seven annotations on HEAD.
    """

    makefile = (_REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    pre_commit = (_REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    workflow = (
        _REPO_ROOT / ".github/workflows/evidence-api-service-checks.yml"
    ).read_text(encoding="utf-8")

    assert "scripts/ci/check_typing_any_ban.py" in makefile
    assert re.search(
        r"^service-checks:.*\n(?:\t@.*\n)*\t@\$\(MAKE\) -s typing-any-check",
        makefile,
        flags=re.MULTILINE,
    ), "the ban must run in the one-command gate"
    assert "entry: make -s typing-any-check\n" in pre_commit

    jobs = yaml.safe_load(workflow)["jobs"]
    guard = jobs["typing_any_guard"]

    assert "if" not in guard, "the guard must not be conditional on a plan"
    assert "needs" not in guard, "the guard must not wait on a job that can fail"
    assert [
        step for step in guard["steps"] if "typing-any-check" in str(step.get("run", ""))
    ], "the guard job must run the check"

    summary = jobs["evidence-api-service-checks"]
    assert "typing_any_guard" in summary["needs"]
    assert 'needs.typing_any_guard.result }}" != "success"' in str(summary["steps"]), (
        "the summary must fail on a skipped guard, not tolerate it"
    )
