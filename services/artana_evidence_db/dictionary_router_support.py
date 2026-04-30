"""Shared support for dictionary governance routes."""

from __future__ import annotations

from typing import Literal

from artana_evidence_db.auth import (
    to_graph_principal,
    to_graph_rls_session_context,
)
from artana_evidence_db.database import set_graph_rls_session_context
from artana_evidence_db.graph_access import evaluate_graph_admin_access
from artana_evidence_db.user_models import User
from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session


class RelationConstraintCreateRequest(BaseModel):
    """Create one relation constraint in the graph dictionary."""

    model_config = ConfigDict(strict=False)

    source_type: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_type: str = Field(..., min_length=1, max_length=64)
    is_allowed: bool = True
    requires_evidence: bool = True
    profile: Literal["EXPECTED", "ALLOWED", "REVIEW_ONLY", "FORBIDDEN"] = "ALLOWED"
    source_ref: str | None = Field(default=None, max_length=1024)


def _require_graph_admin(*, current_user: User, session: Session) -> None:
    if not evaluate_graph_admin_access(to_graph_principal(current_user)).allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Graph service admin access is required for this operation",
        )
    set_graph_rls_session_context(
        session,
        context=to_graph_rls_session_context(current_user, bypass_rls=True),
    )


def _manual_actor(current_user: User) -> str:
    return f"manual:{current_user.id}"

__all__ = [
    "RelationConstraintCreateRequest",
    "_manual_actor",
    "_require_graph_admin",
]
