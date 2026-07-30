"""Tie the README's claims about governance to the code that implements them.

Four review rounds on README.md each found statements the code did not support,
including inside a section restructured specifically to separate durable intent
from current behaviour.  Every one was caught by a human or another model reading
prose against source.  That is not a control -- it is a person remembering.

These tests are the control.  Each one binds a specific README sentence to the
code fact it depends on.  Most fail in *both* directions:

* the code changes and the README is now wrong, or
* the gap the README documents is closed and the README is now stale.

The second direction matters as much as the first.  A README that keeps
apologising for a limitation somebody already fixed teaches readers to discount
it, and a discounted honesty section is worse than none.

One test is deliberately one-directional, and says so in its own docstring: the
orphan-relation caveat, where no static signal can prove the bad state
unreachable.  Claiming bidirectionality there would be the same overreach these
tests exist to catch.

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

    stale_claims = ("declared but unread", "no runtime path reads it")

    if production_callers:
        # Both phrasings have to go, not just whichever one this test happened
        # to name first. Leaving one behind is the same stale guarantee.
        remaining = [phrase for phrase in stale_claims if phrase in readme]
        assert not remaining, (
            f"formal_model() now has production callers ({production_callers}), "
            f"so the README must stop describing [models.formal] as unread. "
            f"Still present: {remaining}"
        )
    else:
        assert "declared but unread" in readme or "no runtime path reads it" in readme, (
            "formal_model() still has no production callers, so the README must "
            "keep saying so -- otherwise it promises a reproducibility guarantee "
            "the code does not provide"
        )


def test_readme_documents_the_orphan_relation_gap_while_repair_ships() -> None:
    """Require the lineage caveat while the tree ships machinery to repair it.

    This one is deliberately one-directional, unlike the others in this module,
    and it is worth saying why rather than quietly asserting less.

    The tempting version keys on the orphan *audit* and flips both ways: audit
    present means the README must caveat, audit absent means it must not.  Both
    halves are unsound.  A monitoring call can be kept as defence in depth long
    after every write path is lineage-safe, which would force the README to keep
    claiming a reachable state that is not; and renaming the function would
    licence deleting a caveat that is still true.  Presence of a probe is not
    evidence of the condition it probes for.

    So this asserts the weaker claim that actually holds: while the service
    ships both detection *and* a repair operation for unbacked relations, the
    tree is telling us it expects to find them, and the README may not claim
    invariant 3 holds universally.  It does not assert the reverse, because no
    static signal proves the state unreachable.  Whether unbacked relations
    exist in a given environment is a data question, answered by
    ``scripts/measure_governance_invariants.py`` against that database.
    """

    readme = _read("README.md")
    readiness = _read(
        "services/artana_evidence_db/claim_projection_readiness_service.py",
    )

    detects = "count_orphan_relations" in readiness
    repairs = "orphan" in readiness and "repair" in readiness.lower()

    if detects and repairs:
        assert "no claim-backed lineage" in readme, (
            "claim_projection_readiness_service.py ships both detection and "
            "repair for canonical relations with no claim-backed lineage, so "
            "README.md may not present invariant 3 as holding for every stored "
            "relation. Removing this caveat needs a measured argument from "
            "scripts/measure_governance_invariants.py, not a doc edit."
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


# ---------------------------------------------------------------------------
# Execution tests for scripts/measure_governance_invariants.py
#
# The tests above read files. These import and run the measurement script's
# pure logic, because the script had no coverage at all: a pull request
# touching only it planned every gate false, and the Makefile lint and type
# lists did not mention it either. Governance reporting could regress with no
# CI signal whatsoever, which is the same hole this module exists to close.
#
# The database-backed paths are not exercised here -- that needs a live graph
# schema and belongs in the service suites. What is covered is everything that
# decides whether a report can be trusted: credential redaction, deployment
# identity, and the wording of the zero-data conclusion.
# ---------------------------------------------------------------------------


def _measurement_module() -> object:
    import importlib
    import sys

    for path in (str(REPO_ROOT), str(REPO_ROOT / "services")):
        if path not in sys.path:
            sys.path.insert(0, path)
    return importlib.import_module("scripts.measure_governance_invariants")


def test_database_label_never_emits_a_credential() -> None:
    """Credentials must not reach a report attached to a readiness decision.

    Splitting on ``@`` missed the query-parameter form entirely, which is a
    valid URL shape with no ``@`` in it at all.
    """

    label = _measurement_module()._safe_database_label

    secretive = "postgresql+psycopg2:///graph?host=db&user=operator&password=hunter2"
    rendered = label(secretive)
    for secret in ("hunter2", "password", "operator"):
        assert secret not in rendered, f"{secret!r} leaked into {rendered!r}"

    userinfo = label("postgresql+psycopg2://someone:hunter2@prod-host:5432/artana")
    assert "hunter2" not in userinfo
    assert "prod-host:5432/artana" in userinfo


def test_database_label_distinguishes_deployments() -> None:
    """Host, port and schema all have to appear, wherever the URL carries them.

    Port and host can both live in the query string, and two graph deployments
    can share a database and differ only by schema. Any of those collapsing
    makes two datasets render identically.
    """

    label = _measurement_module()._safe_database_label

    assert "#" in label("postgresql://localhost:5432/artana"), (
        "the resolved graph schema must appear, or two deployments sharing one "
        "database are indistinguishable in the report"
    )

    # Host, port and database can each arrive in the authority or as a libpq
    # query parameter. This function was corrected three times, once per field,
    # because each was read from only one place -- so assert the query form and
    # the authority form render the same identity rather than testing whichever
    # field was most recently reported.
    authority = label("postgresql+psycopg2://db:6543/graph_a")
    query_form = label("postgresql+psycopg2:///?host=db&port=6543&dbname=graph_a")
    assert authority == query_form, (
        f"the same deployment renders differently depending on URL style: "
        f"{authority!r} vs {query_form!r}"
    )
    for part in ("db", "6543", "graph_a"):
        assert part in query_form, f"{part!r} missing from {query_form!r}"

    # A libpq service name is a third mechanism: the endpoint lives in
    # pg_service.conf, so no host or database appears in the URL and two
    # service-backed deployments would otherwise be indistinguishable.
    service_label = label("postgresql+psycopg2:///?service=graph_prod")
    assert "graph_prod" in service_label, (
        f"a service-backed URL carries its identity only in the service name, "
        f"which is missing from {service_label!r}"
    )
    assert service_label != label("postgresql+psycopg2:///?service=graph_stage")


def test_zero_report_does_not_claim_an_empty_graph() -> None:
    """A zero here covers two categories, not the whole graph.

    Entities, and claims carrying neither evidence nor a materialized relation,
    are ordinary states this script never counts. Reporting "no graph data"
    would let an attachment conceal governed records.
    """

    module = _measurement_module()
    empty = [
        module.InvariantMeasurement(
            key="orphan_relations",
            invariant="3",
            question="q",
            count=0,
            total=0,
            detail="d",
        ),
    ]

    global_report = module._render(empty, "host/db#graph_runtime", None)
    assert "no canonical relations and no claim evidence" in global_report
    assert "not the same as holding no graph data" in global_report

    scoped_report = module._render(empty, "host/db#graph_runtime", "space-1")
    assert "space-1" in scoped_report, "a scoped run must name its space"
    assert "re-run without --space" in scoped_report
