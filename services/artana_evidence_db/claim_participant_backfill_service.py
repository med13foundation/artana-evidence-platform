"""Backfill and coverage service for structured claim participants."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from artana_evidence_db.claim_metrics import increment_metric
from artana_evidence_db.claim_participant_backfill_support import (
    ClaimParticipantBackfillGlobalSummary,
    ClaimParticipantBackfillSummary,
    ClaimParticipantCoverageSummary,
    EntityRepositoryLike,
    list_projection_relevant_claim_models,
    resolve_claim_anchor,
)
from artana_evidence_db.claim_participant_service import KernelClaimParticipantService
from artana_evidence_db.relation_claim_service import KernelRelationClaimService
from artana_evidence_db.semantic_ports import ConceptPort

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class ReasoningPathServiceLike(Protocol):
    """Minimal reasoning-path surface required for claim-participant backfill."""

    def mark_stale_for_claim_ids(
        self,
        claim_ids: list[str],
        research_space_id: str,
    ) -> int:
        """Mark reasoning paths stale when claim anchors change."""


class KernelClaimParticipantBackfillService:
    """Populate and audit claim participants for existing relation claims."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        session: Session,
        relation_claim_service: KernelRelationClaimService,
        claim_participant_service: KernelClaimParticipantService,
        entity_repository: EntityRepositoryLike,
        concept_service: ConceptPort,
        reasoning_path_service: ReasoningPathServiceLike | None = None,
    ) -> None:
        self._session = session
        self._claims = relation_claim_service
        self._participants = claim_participant_service
        self._entities = entity_repository
        self._concepts = concept_service
        self._reasoning_paths = reasoning_path_service

    def backfill_for_space(  # noqa: C901
        self,
        *,
        research_space_id: str,
        dry_run: bool,
        limit: int,
        offset: int,
    ) -> ClaimParticipantBackfillSummary:
        claims = self._claims.list_by_research_space(
            research_space_id,
            limit=max(1, min(limit, 5000)),
            offset=max(0, offset),
        )

        created_participants = 0
        skipped_existing = 0
        unresolved_endpoints = 0
        touched_claim_ids: list[str] = []

        for claim in claims:
            existing = self._participants.list_participants_for_claim(str(claim.id))
            existing_roles = {participant.role for participant in existing}
            source_anchor = resolve_claim_anchor(
                research_space_id=research_space_id,
                claim_metadata=claim.metadata_payload,
                endpoint="source",
                fallback_label=claim.source_label,
                entities=self._entities,
                concepts=self._concepts,
            )
            target_anchor = resolve_claim_anchor(
                research_space_id=research_space_id,
                claim_metadata=claim.metadata_payload,
                endpoint="target",
                fallback_label=claim.target_label,
                entities=self._entities,
                concepts=self._concepts,
            )

            if "SUBJECT" in existing_roles:
                skipped_existing += 1
            elif source_anchor is None:
                unresolved_endpoints += 1
            else:
                if not dry_run:
                    self._participants.create_participant(
                        claim_id=str(claim.id),
                        research_space_id=research_space_id,
                        role="SUBJECT",
                        label=source_anchor.label,
                        entity_id=source_anchor.entity_id,
                        position=0,
                        qualifiers={"origin": "participant_backfill_v1"},
                    )
                    touched_claim_ids.append(str(claim.id))
                created_participants += 1

            if "OBJECT" in existing_roles:
                skipped_existing += 1
            elif target_anchor is None:
                unresolved_endpoints += 1
            else:
                if not dry_run:
                    self._participants.create_participant(
                        claim_id=str(claim.id),
                        research_space_id=research_space_id,
                        role="OBJECT",
                        label=target_anchor.label,
                        entity_id=target_anchor.entity_id,
                        position=1,
                        qualifiers={"origin": "participant_backfill_v1"},
                    )
                    touched_claim_ids.append(str(claim.id))
                created_participants += 1

        if not dry_run and touched_claim_ids and self._reasoning_paths is not None:
            self._reasoning_paths.mark_stale_for_claim_ids(
                touched_claim_ids,
                research_space_id,
            )
        self._record_metrics(
            created_participants=created_participants,
            unresolved_endpoints=unresolved_endpoints,
            tags={"research_space_id": research_space_id},
        )
        return ClaimParticipantBackfillSummary(
            scanned_claims=len(claims),
            created_participants=created_participants,
            skipped_existing=skipped_existing,
            unresolved_endpoints=unresolved_endpoints,
            dry_run=dry_run,
        )

    def backfill_globally(  # noqa: PLR0912, C901
        self,
        *,
        dry_run: bool,
        limit: int,
        offset: int,
    ) -> ClaimParticipantBackfillGlobalSummary:
        claims = list_projection_relevant_claim_models(
            self._session,
            limit=max(1, min(limit, 10000)),
            offset=max(0, offset),
        )

        created_participants = 0
        skipped_existing = 0
        unresolved_endpoints = 0
        research_space_ids: set[str] = set()
        touched_claim_ids_by_space: dict[str, list[str]] = {}

        for claim in claims:
            research_space_id = str(claim.research_space_id)
            research_space_ids.add(research_space_id)
            existing = self._participants.list_participants_for_claim(str(claim.id))
            existing_roles = {participant.role for participant in existing}
            source_anchor = resolve_claim_anchor(
                research_space_id=research_space_id,
                claim_metadata=claim.metadata_payload,
                endpoint="source",
                fallback_label=claim.source_label,
                entities=self._entities,
                concepts=self._concepts,
            )
            target_anchor = resolve_claim_anchor(
                research_space_id=research_space_id,
                claim_metadata=claim.metadata_payload,
                endpoint="target",
                fallback_label=claim.target_label,
                entities=self._entities,
                concepts=self._concepts,
            )

            if "SUBJECT" in existing_roles:
                skipped_existing += 1
            elif source_anchor is None or source_anchor.entity_id is None:
                unresolved_endpoints += 1
            else:
                if not dry_run:
                    self._participants.create_participant(
                        claim_id=str(claim.id),
                        research_space_id=research_space_id,
                        role="SUBJECT",
                        label=source_anchor.label,
                        entity_id=source_anchor.entity_id,
                        position=0,
                        qualifiers={"origin": "participant_backfill_global_v1"},
                    )
                    touched_claim_ids_by_space.setdefault(
                        research_space_id,
                        [],
                    ).append(str(claim.id))
                created_participants += 1

            if "OBJECT" in existing_roles:
                skipped_existing += 1
            elif target_anchor is None or target_anchor.entity_id is None:
                unresolved_endpoints += 1
            else:
                if not dry_run:
                    self._participants.create_participant(
                        claim_id=str(claim.id),
                        research_space_id=research_space_id,
                        role="OBJECT",
                        label=target_anchor.label,
                        entity_id=target_anchor.entity_id,
                        position=1,
                        qualifiers={"origin": "participant_backfill_global_v1"},
                    )
                    touched_claim_ids_by_space.setdefault(
                        research_space_id,
                        [],
                    ).append(str(claim.id))
                created_participants += 1

        if not dry_run and self._reasoning_paths is not None:
            for research_space_id, claim_ids in touched_claim_ids_by_space.items():
                self._reasoning_paths.mark_stale_for_claim_ids(
                    claim_ids,
                    research_space_id,
                )
        self._record_metrics(
            created_participants=created_participants,
            unresolved_endpoints=unresolved_endpoints,
            tags={"scope": "global_projection_repair"},
        )
        return ClaimParticipantBackfillGlobalSummary(
            scanned_claims=len(claims),
            created_participants=created_participants,
            skipped_existing=skipped_existing,
            unresolved_endpoints=unresolved_endpoints,
            research_spaces=len(research_space_ids),
            dry_run=dry_run,
        )

    def coverage_for_space(
        self,
        *,
        research_space_id: str,
        limit: int,
        offset: int,
    ) -> ClaimParticipantCoverageSummary:
        claims = self._claims.list_by_research_space(
            research_space_id,
            limit=max(1, min(limit, 5000)),
            offset=max(0, offset),
        )
        claims_with_any_participants = 0
        claims_with_subject = 0
        claims_with_object = 0
        unresolved_subject_endpoints = 0
        unresolved_object_endpoints = 0

        for claim in claims:
            participants = self._participants.list_participants_for_claim(str(claim.id))
            roles = {participant.role for participant in participants}
            if participants:
                claims_with_any_participants += 1
            if "SUBJECT" in roles:
                claims_with_subject += 1
            else:
                unresolved_subject_endpoints += 1
            if "OBJECT" in roles:
                claims_with_object += 1
            else:
                unresolved_object_endpoints += 1

        return ClaimParticipantCoverageSummary(
            total_claims=len(claims),
            claims_with_any_participants=claims_with_any_participants,
            claims_with_subject=claims_with_subject,
            claims_with_object=claims_with_object,
            unresolved_subject_endpoints=unresolved_subject_endpoints,
            unresolved_object_endpoints=unresolved_object_endpoints,
        )

    @staticmethod
    def _record_metrics(
        *,
        created_participants: int,
        unresolved_endpoints: int,
        tags: dict[str, str],
    ) -> None:
        if created_participants > 0:
            increment_metric(
                "claim_participants_backfilled_total",
                delta=created_participants,
                tags=tags,
            )
        if unresolved_endpoints > 0:
            increment_metric(
                "claim_participants_backfill_unresolved_total",
                delta=unresolved_endpoints,
                tags=tags,
            )


__all__ = [
    "ClaimParticipantBackfillGlobalSummary",
    "ClaimParticipantBackfillSummary",
    "ClaimParticipantCoverageSummary",
    "KernelClaimParticipantBackfillService",
]
