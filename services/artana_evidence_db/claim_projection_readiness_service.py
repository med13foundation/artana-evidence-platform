"""Operational readiness checks for claim-backed canonical relation projections."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

from artana_evidence_db.claim_projection_readiness_support import (
    ClaimProjectionReadinessIssue,
    ClaimProjectionReadinessReport,
    ClaimProjectionReadinessSample,
    ClaimProjectionRepairSummary,
    group_projection_rows_by_claim_id,
    has_required_projection_participants,
    has_role_anchor,
    has_usable_claim_evidence,
    is_active_support_claim,
    load_claims_by_ids,
    load_evidence_by_claim_id,
    load_participants_by_claim_id,
    load_projection_relevant_support_claims,
    load_projection_rows,
)

if TYPE_CHECKING:
    from artana_evidence_db.claim_participant_backfill_service import (
        ClaimParticipantBackfillGlobalSummary,
    )
    from artana_evidence_db.kernel_claim_models import (
        ClaimEvidenceModel,
        ClaimParticipantModel,
        RelationClaimModel,
        RelationProjectionSourceModel,
    )
    from artana_evidence_db.relation_projection_materialization_service import (
        RelationProjectionMaterializationResult,
    )
    from artana_evidence_db.relation_projection_source_model import (
        RelationProjectionOrigin,
    )
    from sqlalchemy.orm import Session


class _RelationLike(Protocol):
    @property
    def id(self) -> object: ...

    @property
    def research_space_id(self) -> object: ...


class RelationProjectionInvariantServiceLike(Protocol):
    """Minimal invariant-service contract required for readiness checks."""

    def list_orphan_relations(
        self,
        *,
        space_id: str | None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> Sequence[_RelationLike]:
        """List canonical relations without projection lineage."""

    def count_orphan_relations(
        self,
        *,
        space_id: str | None,
    ) -> int:
        """Count canonical relations without projection lineage."""


class RelationProjectionMaterializationServiceLike(Protocol):
    """Minimal materialization-service contract required for readiness repair."""

    def materialize_support_claim(
        self,
        claim_id: str,
        research_space_id: str,
        projection_origin: RelationProjectionOrigin,
        reviewed_by: str | None = None,
    ) -> RelationProjectionMaterializationResult:
        """Materialize one support claim into a canonical relation projection."""

    def detach_claim_projection(
        self,
        claim_id: str,
        research_space_id: str,
    ) -> RelationProjectionMaterializationResult:
        """Detach one claim-backed projection from the canonical relation graph."""


class ClaimParticipantBackfillServiceLike(Protocol):
    """Minimal backfill-service contract required for readiness repair."""

    def backfill_globally(
        self,
        *,
        dry_run: bool,
        limit: int,
        offset: int,
    ) -> ClaimParticipantBackfillGlobalSummary:
        """Backfill participants for projection-relevant claims."""


class KernelClaimProjectionReadinessService:
    """Single operational checker for claim-backed projection rollout readiness."""

    def __init__(
        self,
        *,
        session: Session,
        relation_projection_invariant_service: RelationProjectionInvariantServiceLike,
        relation_projection_materialization_service: (
            RelationProjectionMaterializationServiceLike
        ),
        claim_participant_backfill_service: ClaimParticipantBackfillServiceLike,
    ) -> None:
        self._session = session
        self._projection_invariants = relation_projection_invariant_service
        self._materializer = relation_projection_materialization_service
        self._participant_backfill = claim_participant_backfill_service

    def audit(
        self,
        *,
        sample_limit: int = 10,
    ) -> ClaimProjectionReadinessReport:
        normalized_sample_limit = max(1, sample_limit)
        orphan_issue = self._build_orphan_issue(sample_limit=normalized_sample_limit)
        support_claims = load_projection_relevant_support_claims(self._session)
        support_claim_ids = [str(claim.id) for claim in support_claims]
        projection_rows = load_projection_rows(self._session)
        projection_rows_by_claim_id = group_projection_rows_by_claim_id(
            projection_rows,
        )
        participants_by_claim_id = load_participants_by_claim_id(
            self._session,
            claim_ids=support_claim_ids,
        )
        evidence_by_claim_id = load_evidence_by_claim_id(
            self._session,
            claim_ids=support_claim_ids,
        )

        missing_participant_issue = self._build_missing_participant_issue(
            support_claims=support_claims,
            participants_by_claim_id=participants_by_claim_id,
            sample_limit=normalized_sample_limit,
        )
        missing_evidence_issue = self._build_missing_evidence_issue(
            support_claims=support_claims,
            evidence_by_claim_id=evidence_by_claim_id,
            sample_limit=normalized_sample_limit,
        )
        linked_mismatch_issue = self._build_linked_relation_mismatch_issue(
            support_claims=support_claims,
            participants_by_claim_id=participants_by_claim_id,
            projection_rows_by_claim_id=projection_rows_by_claim_id,
            sample_limit=normalized_sample_limit,
        )
        invalid_projection_issue = self._build_invalid_projection_relation_issue(
            projection_rows=projection_rows,
            participants_by_claim_id=participants_by_claim_id,
            sample_limit=normalized_sample_limit,
        )

        ready = (
            orphan_issue.count == 0
            and missing_participant_issue.count == 0
            and missing_evidence_issue.count == 0
            and linked_mismatch_issue.count == 0
            and invalid_projection_issue.count == 0
        )
        return ClaimProjectionReadinessReport(
            orphan_relations=orphan_issue,
            missing_claim_participants=missing_participant_issue,
            missing_claim_evidence=missing_evidence_issue,
            linked_relation_mismatches=linked_mismatch_issue,
            invalid_projection_relations=invalid_projection_issue,
            ready=ready,
        )

    def repair_global(
        self,
        *,
        dry_run: bool,
        batch_limit: int = 5000,
    ) -> ClaimProjectionRepairSummary:
        participant_backfill = self._participant_backfill.backfill_globally(
            dry_run=dry_run,
            limit=batch_limit,
            offset=0,
        )
        support_claims = load_projection_relevant_support_claims(self._session)
        projection_rows_by_claim_id = group_projection_rows_by_claim_id(
            load_projection_rows(self._session),
        )
        participants_by_claim_id = load_participants_by_claim_id(
            self._session,
            claim_ids=[str(claim.id) for claim in support_claims],
        )

        materialized_claims = 0
        detached_claims = 0
        unresolved_claims = 0

        for claim in support_claims:
            claim_id = str(claim.id)
            projection_rows = projection_rows_by_claim_id.get(claim_id, [])
            has_projection_rows = bool(projection_rows)
            has_linked_relation = claim.linked_relation_id is not None
            has_required_participants = has_required_projection_participants(
                participants_by_claim_id.get(claim_id, []),
            )

            if is_active_support_claim(claim) and has_required_participants:
                try:
                    self._materializer.materialize_support_claim(
                        claim_id=claim_id,
                        research_space_id=str(claim.research_space_id),
                        projection_origin="CLAIM_RESOLUTION",
                        reviewed_by=None,
                    )
                    materialized_claims += 1
                except ValueError:
                    unresolved_claims += 1
                continue

            if has_projection_rows or has_linked_relation:
                try:
                    self._materializer.detach_claim_projection(
                        claim_id=claim_id,
                        research_space_id=str(claim.research_space_id),
                    )
                    detached_claims += 1
                except ValueError:
                    unresolved_claims += 1

        return ClaimProjectionRepairSummary(
            participant_backfill=participant_backfill,
            materialized_claims=materialized_claims,
            detached_claims=detached_claims,
            unresolved_claims=unresolved_claims,
            dry_run=dry_run,
        )

    def _build_orphan_issue(
        self,
        *,
        sample_limit: int,
    ) -> ClaimProjectionReadinessIssue:
        orphan_relations = self._projection_invariants.list_orphan_relations(
            space_id=None,
            limit=sample_limit,
            offset=0,
        )
        return ClaimProjectionReadinessIssue(
            count=self._projection_invariants.count_orphan_relations(space_id=None),
            samples=tuple(
                ClaimProjectionReadinessSample(
                    research_space_id=str(relation.research_space_id),
                    claim_id=None,
                    relation_id=str(relation.id),
                    detail="Canonical relation has no claim-backed projection lineage",
                )
                for relation in orphan_relations
            ),
        )

    def _build_missing_participant_issue(
        self,
        *,
        support_claims: list[RelationClaimModel],
        participants_by_claim_id: dict[str, list[ClaimParticipantModel]],
        sample_limit: int,
    ) -> ClaimProjectionReadinessIssue:
        samples: list[ClaimProjectionReadinessSample] = []
        count = 0
        for claim in support_claims:
            claim_id = str(claim.id)
            participants = participants_by_claim_id.get(claim_id, [])
            has_subject = has_role_anchor(participants, role="SUBJECT")
            has_object = has_role_anchor(participants, role="OBJECT")
            if has_subject and has_object:
                continue
            count += 1
            if len(samples) < sample_limit:
                missing_roles: list[str] = []
                if not has_subject:
                    missing_roles.append("SUBJECT")
                if not has_object:
                    missing_roles.append("OBJECT")
                samples.append(
                    ClaimProjectionReadinessSample(
                        research_space_id=str(claim.research_space_id),
                        claim_id=claim_id,
                        relation_id=(
                            str(claim.linked_relation_id)
                            if claim.linked_relation_id is not None
                            else None
                        ),
                        detail=(
                            "Support claim is missing anchored participants for "
                            + ", ".join(missing_roles)
                        ),
                    ),
                )
        return ClaimProjectionReadinessIssue(count=count, samples=tuple(samples))

    def _build_missing_evidence_issue(
        self,
        *,
        support_claims: list[RelationClaimModel],
        evidence_by_claim_id: dict[str, list[ClaimEvidenceModel]],
        sample_limit: int,
    ) -> ClaimProjectionReadinessIssue:
        samples: list[ClaimProjectionReadinessSample] = []
        count = 0
        for claim in support_claims:
            claim_id = str(claim.id)
            if has_usable_claim_evidence(evidence_by_claim_id.get(claim_id, [])):
                continue
            count += 1
            if len(samples) < sample_limit:
                samples.append(
                    ClaimProjectionReadinessSample(
                        research_space_id=str(claim.research_space_id),
                        claim_id=claim_id,
                        relation_id=(
                            str(claim.linked_relation_id)
                            if claim.linked_relation_id is not None
                            else None
                        ),
                        detail="Support claim has no usable claim_evidence rows",
                    ),
                )
        return ClaimProjectionReadinessIssue(count=count, samples=tuple(samples))

    def _build_linked_relation_mismatch_issue(
        self,
        *,
        support_claims: list[RelationClaimModel],
        participants_by_claim_id: dict[str, list[ClaimParticipantModel]],
        projection_rows_by_claim_id: dict[str, list[RelationProjectionSourceModel]],
        sample_limit: int,
    ) -> ClaimProjectionReadinessIssue:
        samples: list[ClaimProjectionReadinessSample] = []
        count = 0
        for claim in support_claims:
            claim_id = str(claim.id)
            linked_relation_id = (
                str(claim.linked_relation_id)
                if claim.linked_relation_id is not None
                else None
            )
            projected_relation_ids = {
                str(row.relation_id)
                for row in projection_rows_by_claim_id.get(claim_id, [])
            }
            has_required_participants = has_required_projection_participants(
                participants_by_claim_id.get(claim_id, []),
            )
            mismatch_reason = self._linked_relation_mismatch_reason(
                claim=claim,
                linked_relation_id=linked_relation_id,
                projected_relation_ids=projected_relation_ids,
                has_required_participants=has_required_participants,
            )

            if mismatch_reason is None:
                continue
            count += 1
            if len(samples) < sample_limit:
                relation_id = linked_relation_id
                if relation_id is None and projected_relation_ids:
                    relation_id = sorted(projected_relation_ids)[0]
                samples.append(
                    ClaimProjectionReadinessSample(
                        research_space_id=str(claim.research_space_id),
                        claim_id=claim_id,
                        relation_id=relation_id,
                        detail=mismatch_reason,
                    ),
                )
        return ClaimProjectionReadinessIssue(count=count, samples=tuple(samples))

    def _linked_relation_mismatch_reason(
        self,
        *,
        claim: RelationClaimModel,
        linked_relation_id: str | None,
        projected_relation_ids: set[str],
        has_required_participants: bool,
    ) -> str | None:
        reason: str | None = None
        if is_active_support_claim(claim):
            if has_required_participants:
                if not projected_relation_ids and linked_relation_id is None:
                    reason = (
                        "Projection-eligible support claim has no materialized "
                        "canonical relation"
                    )
                elif linked_relation_id is None and projected_relation_ids:
                    reason = (
                        "Support claim has projection lineage but no "
                        "linked_relation_id compatibility pointer"
                    )
                elif (
                    linked_relation_id is not None
                    and linked_relation_id not in projected_relation_ids
                ):
                    reason = (
                        "Support claim linked_relation_id does not match current "
                        "projection lineage"
                    )
                elif len(projected_relation_ids) > 1:
                    reason = "Support claim resolves to multiple projection-lineage relations"
            elif linked_relation_id is not None or projected_relation_ids:
                reason = (
                    "Projection-eligible support claim is missing anchored participants "
                    "but still has canonical relation linkage"
                )
        elif linked_relation_id is not None or projected_relation_ids:
            reason = (
                "Inactive or non-materializable support claim still has "
                "canonical relation linkage"
            )
        return reason

    def _build_invalid_projection_relation_issue(
        self,
        *,
        projection_rows: list[RelationProjectionSourceModel],
        participants_by_claim_id: dict[str, list[ClaimParticipantModel]],
        sample_limit: int,
    ) -> ClaimProjectionReadinessIssue:
        claims_by_id = load_claims_by_ids(
            self._session,
            claim_ids=[str(row.claim_id) for row in projection_rows],
        )
        rows_by_relation_id: dict[str, list[RelationProjectionSourceModel]] = {}
        for row in projection_rows:
            rows_by_relation_id.setdefault(str(row.relation_id), []).append(row)

        samples: list[ClaimProjectionReadinessSample] = []
        count = 0
        for relation_id, rows in rows_by_relation_id.items():
            valid_source_exists = False
            relation_space_id = str(rows[0].research_space_id)
            for row in rows:
                claim = claims_by_id.get(str(row.claim_id))
                if claim is None or not is_active_support_claim(claim):
                    continue
                participants = participants_by_claim_id.get(str(row.claim_id), [])
                if has_required_projection_participants(participants):
                    valid_source_exists = True
                    break
            if valid_source_exists:
                continue
            count += 1
            if len(samples) < sample_limit:
                samples.append(
                    ClaimProjectionReadinessSample(
                        research_space_id=relation_space_id,
                        claim_id=None,
                        relation_id=relation_id,
                        detail=(
                            "Canonical relation has projection rows but no "
                            "currently valid support-claim source"
                        ),
                    ),
                )
        return ClaimProjectionReadinessIssue(count=count, samples=tuple(samples))


__all__ = [
    "ClaimProjectionReadinessIssue",
    "ClaimProjectionReadinessReport",
    "ClaimProjectionReadinessSample",
    "ClaimProjectionRepairSummary",
    "KernelClaimProjectionReadinessService",
]
