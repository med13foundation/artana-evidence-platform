"""Tie the README's claims about governance to the code that implements them.

Four review rounds on README.md each found statements the code did not support,
including inside a section restructured specifically to separate durable intent
from current behaviour.  Every one was caught by a human or another model reading
prose against source.  That is not a control -- it is a person remembering.

These tests are the control.  Each one binds a specific README sentence to the
code fact it depends on, and each fails in *both* directions:

* the code changes and the README is now wrong, or
* the gap the README documents is closed and the README is now stale.

The second direction matters as much as the first.  A README that keeps
apologising for a limitation somebody already fixed teaches readers to discount
it, and a discounted honesty section is worse than none.

These are deliberately not data tests.  Whether a *stored* graph violates an
invariant is a question about an environment, not about the tree, and it is
answered by ``scripts/measure_governance_invariants.py`` against a real database.
"""

from __future__ import annotations

import re
from pathlib import Path


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "Makefile").exists() and (
            candidate / "services" / "artana_evidence_api"
        ).exists():
            return candidate
    message = "Unable to locate repository root from governance invariant tests"
    raise RuntimeError(message)


REPO_ROOT = _repo_root()


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_readme_quotes_the_real_quarantine_reason_code() -> None:
    """The reason code the README quotes must be the one the service returns.

    The README tells a reader they will see HTTP 409 with a specific code, which
    is the kind of detail an integrator writes an error branch against.  If the
    constant is renamed and the prose is not, the README hands out a string that
    matches nothing.
    """

    readme = _read("README.md")
    quarantine = _read(
        "services/artana_evidence_db/validation/ai_persistence_quarantine.py",
    )

    match = re.search(r'code: str = "(?P<code>[a-z_]+)"', quarantine)
    assert match is not None, (
        "ai_persistence_quarantine.py no longer declares a default reason code; "
        "the README quotes one, so either restore it or update the README"
    )
    code = match.group("code")

    assert code in readme, (
        f"the quarantine returns reason code {code!r}, which does not appear in "
        f"README.md. An integrator reading the README would branch on the wrong "
        f"string."
    )


def test_readme_does_not_claim_formal_runs_use_the_formal_model() -> None:
    """Guard the reproducibility claim that was wrong for three revisions.

    ``[models.formal]`` names the model formal runs are *meant* to use, and no
    production path reads it -- the only callers of ``formal_model()`` are tests.
    The README asserted the opposite until an external review caught it, which
    would have led an experiment operator to attribute a sealed result to a model
    that never ran.

    When somebody wires the profile in, this test fails and the README has to
    stop saying it is unread.  That is the intended behaviour, not a nuisance.
    """

    readme = _read("README.md")
    registry_dir = REPO_ROOT / "services"

    production_callers: list[str] = []
    for path in registry_dir.rglob("*.py"):
        relative = path.relative_to(REPO_ROOT).as_posix()
        if "/tests/" in relative or relative.endswith("runtime/model_registry.py"):
            continue
        if re.search(r"\bformal_model\s*\(", path.read_text(encoding="utf-8")):
            production_callers.append(relative)

    if production_callers:
        assert "declared but unread" not in readme, (
            f"formal_model() now has production callers ({production_callers}), "
            f"so the README must stop describing [models.formal] as unread"
        )
    else:
        assert "declared but unread" in readme or "no runtime path reads it" in readme, (
            "formal_model() still has no production callers, so the README must "
            "keep saying so -- otherwise it promises a reproducibility guarantee "
            "the code does not provide"
        )


def test_readme_documents_the_orphan_relation_gap_while_it_exists() -> None:
    """Keep the projection-lineage caveat honest in both directions.

    Invariant 3 says canonical relations are projections of the claim ledger.
    The readiness service audits relations that have no lineage, which means the
    system knows that state is reachable.  While that audit exists, the README
    has to admit it; when the audit becomes unnecessary, the README should stop
    hedging.
    """

    readme = _read("README.md")
    readiness = _read(
        "services/artana_evidence_db/claim_projection_readiness_service.py",
    )

    audit_exists = "count_orphan_relations" in readiness
    readme_admits = "no claim-backed lineage" in readme

    if audit_exists:
        assert readme_admits, (
            "claim_projection_readiness_service.py still audits relations with no "
            "claim-backed lineage, so README.md must disclose that invariant 3 "
            "does not hold for every stored relation"
        )
    else:
        assert not readme_admits, (
            "the orphan-relation audit is gone, so README.md should stop "
            "documenting it as a live gap"
        )


def test_readme_scoping_claim_matches_the_registry_that_computes_identity() -> None:
    """Bind the tissue example to the registry canonicalisation actually reads.

    Two builtin qualifier sets disagree about whether ``tissue`` scopes identity.
    Canonicalisation reads ``qualifier_registry``; the other set is dictionary
    seed data.  A previous revision took the example from the seed file and told
    readers that two claims differing by tissue were the same proposition.
    """

    readme = _read("README.md")
    registry = _read("services/artana_evidence_db/qualifier_registry.py")

    tissue_block = re.search(
        r'key="tissue".*?\)',
        registry,
        flags=re.DOTALL,
    )
    assert tissue_block is not None, (
        "qualifier_registry.py no longer defines a tissue qualifier; the README "
        "uses it as its worked example of scoping, so update both together"
    )

    tissue_is_scoping = "is_scoping=True" in tissue_block.group(0)
    readme_uses_tissue_as_scoping = "differ by tissue" in readme

    assert tissue_is_scoping == readme_uses_tissue_as_scoping, (
        f"qualifier_registry marks tissue scoping={tissue_is_scoping}, but "
        f"README.md treats it as scoping={readme_uses_tissue_as_scoping}. The "
        f"registry is what canonicalisation reads, so it wins."
    )
