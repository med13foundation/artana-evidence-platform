"""Helpers for reconciling graph-owned tenant state with platform truth."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_db.orm_base import Base
from sqlalchemy import delete

if TYPE_CHECKING:
    from sqlalchemy.sql.schema import Column
    from sqlalchemy.orm import Session


def _space_id_bind_value(column: "Column[object]", *, space_id: UUID) -> UUID | str:
    if getattr(column.type, "as_uuid", False):
        return space_id
    return str(space_id)


def purge_graph_space_snapshot(
    session: "Session",
    *,
    space_id: UUID,
) -> None:
    """Delete all graph-owned rows for one stale space snapshot.

    The graph registry is derived from platform truth. When the platform recreates a
    research space with the same slug but a new UUID, we need to remove the stale
    graph-owned tenant snapshot before inserting the replacement entry.
    """

    graph_spaces_table = None
    for table in reversed(Base.metadata.sorted_tables):
        if table.name == "graph_spaces":
            graph_spaces_table = table
            continue
        if table.name == "graph_space_memberships" and "space_id" in table.c:
            session.execute(
                delete(table).where(
                    table.c.space_id
                    == _space_id_bind_value(table.c.space_id, space_id=space_id),
                ),
            )
            continue
        if "research_space_id" in table.c:
            session.execute(
                delete(table).where(
                    table.c.research_space_id
                    == _space_id_bind_value(
                        table.c.research_space_id,
                        space_id=space_id,
                    ),
                ),
            )

    if graph_spaces_table is None:
        msg = "graph_spaces table is not registered in SQLAlchemy metadata"
        raise RuntimeError(msg)

    session.execute(
        delete(graph_spaces_table).where(
            graph_spaces_table.c.id
            == _space_id_bind_value(graph_spaces_table.c.id, space_id=space_id),
        ),
    )


__all__ = ["purge_graph_space_snapshot"]
