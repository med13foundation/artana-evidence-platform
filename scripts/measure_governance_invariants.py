#!/usr/bin/env python3
"""Measure how far the stored graph is from three README invariant conditions.

The README states four invariants and, since the July 30 audit, admits that each
has known violations in the code.  Knowing a violation is *possible* says nothing
about whether it is *present*, and that difference decides whether each gap is a
documentation note or a roadmap item.  This script answers that with counts
rather than judgement.

**This is a partial report, deliberately.**  It measures four conditions: one
for invariant 3 (relations with no claim lineage) and three for invariant 1
(claim evidence with no typed provenance, claim evidence with no snapshot,
relation evidence with no snapshot).  Both tables that carry
``source_snapshot_id`` are covered; ``provenance_status`` exists only on claim
evidence, so that signal is claim-evidence-only by construction rather than by
omission.

It does *not* measure evidence missing a locator or span, accepted
claim-to-claim edges with no source grounding, manual observations without
provenance, or anything for invariant 4.  A low report here is not a clean bill
of health for the README's Known Gaps section, and must not be quoted as one.

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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement
    from sqlalchemy.orm import Session

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


def _measure(session: Session, space_id: str | None) -> list[InvariantMeasurement]:
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
    total_relations = int(session.scalar(total_relations_stmt) or 0)

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

    def _evidence_count(*conditions: ColumnElement[bool]) -> int:
        stmt = select(func.count(ClaimEvidenceModel.id))
        for condition in conditions:
            stmt = stmt.where(condition)
        if space_id is not None:
            stmt = stmt.join(
                RelationClaimModel,
                RelationClaimModel.id == ClaimEvidenceModel.claim_id,
            ).where(RelationClaimModel.research_space_id == space_id)
        return int(session.scalar(stmt) or 0)

    unverified_evidence = _evidence_count(
        ClaimEvidenceModel.provenance_status == "LEGACY_UNVERIFIED",
    )
    total_evidence = _evidence_count()

    measurements.append(
        InvariantMeasurement(
            key="legacy_unverified_evidence",
            invariant="1 -- sources and evidence remain preserved",
            question="How much claim evidence carries no typed provenance?",
            count=unverified_evidence,
            total=total_evidence,
            detail=(
                "LEGACY_UNVERIFIED is the model default, so this counts rows "
                "written before typed provenance as well as any written without "
                "it since. Claim evidence only: relation_evidence has no "
                "provenance_status column, so this signal does not exist there."
            ),
        ),
    )

    unbound_evidence = _evidence_count(
        ClaimEvidenceModel.source_snapshot_id.is_(None),
    )

    measurements.append(
        InvariantMeasurement(
            key="claim_evidence_without_snapshot",
            invariant="1 -- sources and evidence remain preserved",
            question="How much claim evidence has no verified source snapshot?",
            count=unbound_evidence,
            total=total_evidence,
            detail=(
                "Without a snapshot there is no custody of what the source said "
                "at the time the claim was made, so the claim cannot be defended "
                "once the source moves."
            ),
        ),
    )

    # The graph stores supporting evidence in two places, and only this one and
    # claim_evidence carry source_snapshot_id -- checked across the whole
    # service, not inferred. Counting claim evidence alone let a canonical
    # relation whose evidence rows have no snapshot report as zero affected,
    # which is precisely the custody question invariant 1 is about.
    from artana_evidence_db.kernel_relation_models import RelationEvidenceModel

    def _relation_evidence_count(*conditions: ColumnElement[bool]) -> int:
        stmt = select(func.count(RelationEvidenceModel.id))
        for condition in conditions:
            stmt = stmt.where(condition)
        if space_id is not None:
            # relation_evidence has no space of its own; it inherits through
            # the relation.
            stmt = stmt.join(
                RelationModel,
                RelationModel.id == RelationEvidenceModel.relation_id,
            ).where(RelationModel.research_space_id == space_id)
        return int(session.scalar(stmt) or 0)

    total_relation_evidence = _relation_evidence_count()
    unbound_relation_evidence = _relation_evidence_count(
        RelationEvidenceModel.source_snapshot_id.is_(None),
    )

    measurements.append(
        InvariantMeasurement(
            key="relation_evidence_without_snapshot",
            invariant="1 -- sources and evidence remain preserved",
            question="How much relation evidence has no verified source snapshot?",
            count=unbound_relation_evidence,
            total=total_relation_evidence,
            detail=(
                "Evidence attached directly to a canonical relation rather than "
                "through a claim. It has no provenance_status column, so an "
                "absent snapshot is the only custody signal available here."
            ),
        ),
    )

    return measurements


def _apply_measurement_rls_context(session: Session) -> None:
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
        session.execute(
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

    def _from_query(key: str) -> str | None:
        value = url.query.get(key)
        if isinstance(value, tuple):
            return value[0] if value else None
        return value

    # Every part of the connection identity can arrive either in the URL
    # authority or as a libpq query parameter, and this function has now been
    # corrected three times -- once for host, once for port, once for dbname --
    # because each was read from only one of the two places. So all three
    # resolve the same way rather than being patched one at a time:
    # `postgresql+psycopg2:///?host=db&port=6543&dbname=graph_a` has to render
    # exactly like the equivalent authority form, or two deployments become
    # indistinguishable in a report meant to be attached to a decision.
    def _identity(authority: object, *query_keys: str) -> str | None:
        if authority not in (None, ""):
            return str(authority)
        for key in query_keys:
            resolved = _from_query(key)
            if resolved:
                return resolved
        return None

    host = _identity(url.host, "host") or "<no host>"
    raw_port = _identity(url.port, "port")
    port = f":{raw_port}" if raw_port else ""
    database = _identity(url.database, "dbname", "database") or "<no database>"

    # A libpq service name is a third mechanism, not a fourth field: the real
    # host, port and database live in pg_service.conf and never appear in the
    # URL at all, so the lookups above legitimately find nothing and two
    # service-backed deployments would render identically. The service name is
    # not a secret -- it is a key into a config file -- so it is safe to show,
    # and it is the only endpoint identity such a URL carries.
    service_name = _from_query("service")
    supplies_something = (
        host == "<no host>" or database == "<no database>" or raw_port is None
    )
    if service_name and supplies_something:
        # Requiring *every* field to be unresolved was wrong: `?service=x&host=db`
        # overrides only the host, so the service still chooses the database,
        # and two services sharing a host rendered identically. The service name
        # belongs in the identity whenever it supplies any field the URL does
        # not, which includes the partially-overridden case.
        if host == "<no host>" and database == "<no database>":
            endpoint = f"service={service_name}"
        else:
            endpoint = f"{host}{port}/{database} [service={service_name}]"
    else:
        endpoint = f"{host}{port}/{database}"

    # Two graph deployments can share one database and differ only by
    # GRAPH_DB_SCHEMA, which README.md documents as a supported shape. The ORM
    # models qualify their tables with the resolved schema at import time, so
    # the counts are already correct for whichever schema is configured -- but
    # without it here, two datasets render identically and a report can be
    # attached to the wrong one. schema_support does not resolve service
    # settings, so importing it is safe in every environment.
    from artana_evidence_db.schema_support import resolve_graph_db_schema

    schema = resolve_graph_db_schema()
    return f"{endpoint}#{schema}"


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
        # Not the same as an empty graph: only relations and claim evidence are
        # counted here, and entities or claims carrying neither are ordinary
        # states. Saying "no graph data" would let a readiness attachment
        # conceal governed records this script never looked at.
        where = (
            f"research space {space_id}" if space_id else "this database"
        )
        extra = (
            " Other spaces may hold plenty; re-run without --space before "
            "drawing any platform-level conclusion."
            if space_id
            else ""
        )
        lines.append(
            f"Every total is zero: {where} holds no canonical relations and no "
            f"claim evidence. That is not the same as holding no graph data -- "
            f"entities, and claims with neither evidence nor a materialized "
            f"relation, are not counted here.{extra} The run proves the queries "
            f"execute and nothing else.",
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
