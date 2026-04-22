"""Application service for structured claim participants."""

from __future__ import annotations

from typing import Protocol

from artana_evidence_db.claim_participant_models import (
    ClaimParticipantRole,
    KernelClaimParticipant,
)
from artana_evidence_db.common_types import JSONObject


class ClaimParticipantRepositoryLike(Protocol):
    """Minimal repository contract required for claim-participant workflows."""

    def create(  # noqa: PLR0913
        self,
        *,
        claim_id: str,
        research_space_id: str,
        role: ClaimParticipantRole,
        label: str | None,
        entity_id: str | None,
        position: int | None,
        qualifiers: JSONObject | None = None,
    ) -> KernelClaimParticipant:
        """Create one participant row."""

    def find_by_claim_id(self, claim_id: str) -> list[KernelClaimParticipant]:
        """List participants for one claim."""

    def find_by_claim_ids(
        self,
        claim_ids: list[str],
    ) -> dict[str, list[KernelClaimParticipant]]:
        """List participants for multiple claims keyed by claim ID."""

    def list_claim_ids_by_entity(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[str]:
        """List distinct claim IDs for one entity in participant rows."""

    def count_claims_by_entity(
        self,
        *,
        research_space_id: str,
        entity_id: str,
    ) -> int:
        """Count distinct claim IDs for one entity in participant rows."""


class KernelClaimParticipantService:
    """Application service for claim participant writes and lookups."""

    def __init__(
        self,
        claim_participant_repo: ClaimParticipantRepositoryLike,
    ) -> None:
        self._participants = claim_participant_repo

    def create_participant(  # noqa: PLR0913
        self,
        *,
        claim_id: str,
        research_space_id: str,
        role: ClaimParticipantRole,
        label: str | None,
        entity_id: str | None,
        position: int | None = None,
        qualifiers: JSONObject | None = None,
    ) -> KernelClaimParticipant:
        """Create one participant row with qualifier validation."""
        if qualifiers:
            from artana_evidence_db.qualifier_registry import validate_qualifiers

            errors = validate_qualifiers(qualifiers)
            if errors:
                msg = f"Invalid qualifiers: {'; '.join(errors)}"
                raise ValueError(msg)

        return self._participants.create(
            claim_id=claim_id,
            research_space_id=research_space_id,
            role=role,
            label=label,
            entity_id=entity_id,
            position=position,
            qualifiers=qualifiers,
        )

    def list_participants_for_claim(
        self,
        claim_id: str,
    ) -> list[KernelClaimParticipant]:
        """List participants for one claim."""
        return self._participants.find_by_claim_id(claim_id)

    def list_for_claim_ids(
        self,
        claim_ids: list[str],
    ) -> dict[str, list[KernelClaimParticipant]]:
        """List participants for multiple claims keyed by claim ID."""
        return self._participants.find_by_claim_ids(claim_ids)

    def list_claim_ids_by_entity(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[str]:
        """List distinct claim IDs for one entity in participant rows."""
        return self._participants.list_claim_ids_by_entity(
            research_space_id=research_space_id,
            entity_id=entity_id,
            limit=limit,
            offset=offset,
        )

    def count_claims_by_entity(
        self,
        *,
        research_space_id: str,
        entity_id: str,
    ) -> int:
        """Count distinct claim IDs for one entity in participant rows."""
        return self._participants.count_claims_by_entity(
            research_space_id=research_space_id,
            entity_id=entity_id,
        )


__all__ = ["KernelClaimParticipantService"]
