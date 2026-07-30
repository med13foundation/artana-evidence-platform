#!/usr/bin/env python3
"""Measure how far the stored graph is from three README invariant conditions.

The README states four invariants and, since the July 30 audit, admits that each
has known violations in the code.  Knowing a violation is *possible* says nothing
about whether it is *present*, and that difference decides whether each gap is a
documentation note or a roadmap item.  This script answers that with counts
rather than judgement.

**This is a partial report, deliberately.**  It measures three conditions: one
for invariant 3 (relations with no claim lineage) and two for invariant 1
(evidence with no typed provenance, evidence with no snapshot).  It does *not*
yet measure evidence missing a locator or span, accepted claim-to-claim edges
with no source grounding, manual observations without provenance, or anything
for invariant 4.  A low report here is not a clean bill of health for the
README's Known Gaps section, and must not be quoted as one.

It is read-only.  Every query is a SELECT and the session is never committed,
but it does set a graph RLS bypass on its own session, because a measurement
that respects per-space row filtering would silently undercount exactly what it
exists to find.  That is the "explicit system reason" AGENTS.md requires for
touching ``app.bypass_rls``; nothing else in this script writes.

Run against whatever database you want to characterise::

    GRAPH_DATABASE_URL=postgresql+psycopg2://... \\
      python3 scripts/measure_governance_invariants.py

``--json`` emits a machine-readable record so a run can be attached to a
readiness decision instead of retyped into one.  ``--space`` narrows every count
to a single research space.

Exit status is 0 whenever the measurement itself succeeded.  A non-zero count is
a finding, not a failure -- this reports, it does not gate.  Nothing in CI gates
these numbers: ``tests/unit/test_governance_invariants.py`` compares README
prose against source text and never opens a database, so stored violations can
grow without any test failing.  Closing that requires running this script against
a real environment on a schedule, which does not exist yet.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for _path in (REPO_ROOT, REPO_ROOT / "services"):
    _resolved = str(_path)
    if _resolved not in sys.path:
        sys.path.insert(0, _resolved)


@dataclass(frozen=True, slots=True)
class InvariantMeasurement:
    """One measured distance between a README invariant and the stored graph."""

    key: str
    invariant: str
    question: str
    count: int
    total: int
    detail: str

    @property
    def share(self) -> float:
        """Return the affected fraction, or 0.0 when nothing is stored yet."""

        if self.total <= 0:
            return 0.0
        return self.count / self.total


def _measure(session: object, space_id: str | None) -> list[InvariantMeasurement]:
    """Return every invariant measurement for one database session."""

    from artana_evidence_db.kernel_claim_models import ClaimEvidenceModel
    from artana_evidence_db.relation_projection_source_repository import (
        SqlAlchemyKernelRelationProjectionSourceRepository,
    )
    from sqlalchemy import func, select

    measurements: list[InvariantMeasurement] = []

    projection_repository = SqlAlchemyKernelRelationProjectionSourceRepository(session)
    orphan_relations = projection_repository.count_orphan_relations(
        research_space_id=space_id,
    )
    from artana_evidence_db.kernel_relation_models import RelationModel

    total_relations_stmt = select(func.count(RelationModel.id))
    if space_id is not None:
        total_relations_stmt = total_relations_stmt.where(
            RelationModel.research_space_id == space_id,
        )
    total_relations = int(session.scalar(total_relations_stmt) or 0)  # type: ignore[attr-defined]

    measurements.append(
        InvariantMeasurement(
            key="orphan_relations",
            invariant="3 -- canonical relations are rebuildable projections",
            question="How many canonical relations have no claim-backed lineage?",
            count=orphan_relations,
            total=total_relations,
            detail=(
                "A relation with no row in relation_projection_sources cannot be "
                "re-derived from the ledger, so dropping and rebuilding would "
                "lose it."
            ),
        ),
    )

    # Evidence rows carry no space of their own; they inherit it through the
    # claim. Without this join a --space run reports every other space's
    # violations against the one space the operator asked about, which is worse
    # than reporting nothing.
    from artana_evidence_db.kernel_claim_models import RelationClaimModel

    def _evidence_count(*conditions: object) -> int:
        stmt = select(func.count(ClaimEvidenceModel.id))
        for condition in conditions:
            stmt = stmt.where(condition)
        if space_id is not None:
            stmt = stmt.join(
                RelationClaimModel,
                RelationClaimModel.id == ClaimEvidenceModel.claim_id,
            ).where(RelationClaimModel.research_space_id == space_id)
        return int(session.scalar(stmt) or 0)  # type: ignore[attr-defined]

    unverified_evidence = _evidence_count(
        ClaimEvidenceModel.provenance_status == "LEGACY_UNVERIFIED",
    )
    total_evidence = _evidence_count()

    measurements.append(
        InvariantMeasurement(
            key="legacy_unverified_evidence",
            invariant="1 -- sources and evidence remain preserved",
            question="How much stored evidence carries no typed provenance?",
            count=unverified_evidence,
            total=total_evidence,
            detail=(
                "LEGACY_UNVERIFIED is the model default, so this counts rows "
                "written before typed provenance as well as any written without "
                "it since."
            ),
        ),
    )

    unbound_evidence = _evidence_count(
        ClaimEvidenceModel.source_snapshot_id.is_(None),
    )

    measurements.append(
        InvariantMeasurement(
            key="evidence_without_snapshot",
            invariant="1 -- sources and evidence remain preserved",
            question="How much evidence has no verified source snapshot?",
            count=unbound_evidence,
            total=total_evidence,
            detail=(
                "Without a snapshot there is no custody of what the source said "
                "at the time the claim was made, so the claim cannot be defended "
                "once the source moves."
            ),
        ),
    )

    return measurements


def _apply_measurement_rls_context(session: object) -> None:
    """Set the RLS session settings this read-only measurement needs.

    ``artana_evidence_db.database.set_session_rls_context`` is the canonical
    implementation and this deliberately does not call it, because importing
    that module runs ``get_settings()`` at import time -- which resolves the
    domain pack, the schema, and the JWT secret, and raises outright when
    ``ARTANA_ENV`` is staging or production without ``GRAPH_JWT_SECRET``.  That
    is the environment this script exists to measure, so booting the graph
    service runtime to issue four ``set_config`` calls is both disproportionate
    and self-defeating.

    Graph tables are ``FORCE ROW LEVEL SECURITY``.  A session with none of these
    settings sees zero rows under the normal service role, so without this a
    populated production database reports as empty and the report reads as a
    clean bill of health.  A read-only cross-space count is the justified system
    use AGENTS.md requires a stated reason for; nothing here writes.
    """

    from sqlalchemy import text

    for setting, value in (
        ("app.current_user_id", ""),
        ("app.has_phi_access", "false"),
        ("app.is_admin", "true"),
        ("app.bypass_rls", "true"),
    ):
        session.execute(  # type: ignore[attr-defined]
            text("SELECT set_config(:setting, :value, false)"),
            {"setting": setting, "value": value},
        )


def _safe_database_label(database_url: str) -> str:
    """Return a host/database label that cannot carry a credential.

    Splitting on ``@`` treats userinfo as the only place a secret can hide.  It
    is not: ``postgresql+psycopg2:///graph?host=db&user=x&password=secret`` is a
    valid URL with no ``@`` at all, and that form would have printed the
    password into both the report and the JSON an operator attaches to a
    readiness decision.  So this allowlists two fields instead of trying to
    strip the dangerous ones, because a strip has to be right every time and an
    allowlist only has to be right once.
    """

    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import ArgumentError

    try:
        url = make_url(database_url)
    except ArgumentError:
        return "<unparseable database url>"

    query_host = url.query.get("host")
    if isinstance(query_host, tuple):
        query_host = query_host[0] if query_host else None
    host = url.host or query_host or "<no host>"
    port = f":{url.port}" if url.port else ""
    return f"{host}{port}/{url.database or '<no database>'}"


def _render(
    measurements: list[InvariantMeasurement],
    database_label: str,
    space_id: str | None,
) -> str:
    """Return the human-readable report.

    The scope line is not decoration.  A ``--space`` run that a reader mistakes
    for a global one turns "this space is clean" into "the platform is clean",
    and the report is meant to be attached to readiness decisions.
    """

    lines = [
        "Governance invariant measurement",
        f"  database: {database_label}",
        f"  scope:    {f'research space {space_id}' if space_id else 'all spaces'}",
        "",
    ]
    for measurement in measurements:
        share = f"{measurement.share * 100:.1f}%" if measurement.total else "n/a"
        lines.append(f"[{measurement.key}]")
        lines.append(f"  invariant: {measurement.invariant}")
        lines.append(f"  {measurement.question}")
        lines.append(
            f"  affected: {measurement.count} of {measurement.total} ({share})",
        )
        lines.append(f"  why it matters: {measurement.detail}")
        lines.append("")

    if all(measurement.total == 0 for measurement in measurements):
        scope = (
            f"research space {space_id} holds no graph data. Other spaces in "
            f"this database may hold plenty; re-run without --space before "
            f"drawing any platform-level conclusion."
            if space_id
            else "This database holds no graph data."
        )
        lines.append(
            f"Every total is zero. {scope} The run proves the queries execute "
            f"and nothing else.",
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Measure invariant distance and report it."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--space",
        default=None,
        help="Restrict every count to one research space id.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable record instead of the report.",
    )
    args = parser.parse_args(argv)

    database_url = os.environ.get("GRAPH_DATABASE_URL") or os.environ.get(
        "DATABASE_URL",
    )
    if not database_url:
        print(
            "Set GRAPH_DATABASE_URL (or DATABASE_URL) to the database you want "
            "to measure.",
            file=sys.stderr,
        )
        return 2

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            # Every count has to describe one database state. Under the default
            # READ COMMITTED each SELECT takes a fresh snapshot, so a numerator
            # and its total can straddle concurrent writes and report a share
            # above 100%. One read-only REPEATABLE READ transaction instead.
            session.execute(
                text(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY",
                ),
            )
            _apply_measurement_rls_context(session)
            measurements = _measure(session, args.space)
    finally:
        engine.dispose()

    safe_label = _safe_database_label(database_url)
    if args.json:
        print(
            json.dumps(
                {
                    "database": safe_label,
                    "space_id": args.space,
                    "measurements": [asdict(m) for m in measurements],
                },
                indent=2,
            ),
        )
    else:
        print(_render(measurements, safe_label, args.space))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
