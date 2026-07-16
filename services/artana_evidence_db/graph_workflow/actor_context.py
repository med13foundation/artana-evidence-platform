"""Server-owned actor identity for graph workflow dispatch."""

from __future__ import annotations

from dataclasses import dataclass

from artana_evidence_db.common_types import JSONObject


@dataclass(frozen=True, slots=True)
class WorkflowActorContext:
    """Keep the authenticated user and effective AI actor distinct."""

    authenticated_user_actor: str
    authenticated_ai_principal: str | None = None

    @property
    def is_ai(self) -> bool:
        """Return whether the request was authenticated as an AI principal."""

        return self.authenticated_ai_principal is not None

    @property
    def effective_actor(self) -> str:
        """Return the actor that owns the workflow decision."""

        return self.authenticated_ai_principal or self.authenticated_user_actor

    def as_payload(self) -> JSONObject:
        """Serialize server-owned lineage without collapsing actor identities."""

        return {
            "authenticated_user_actor": self.authenticated_user_actor,
            "authenticated_ai_principal": self.authenticated_ai_principal,
            "effective_actor": self.effective_actor,
            "actor_type": "AI" if self.is_ai else "HUMAN",
        }


__all__ = ["WorkflowActorContext"]
