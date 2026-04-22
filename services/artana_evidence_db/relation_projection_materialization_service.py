"""Materialize canonical relations as claim-backed projections."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from artana_evidence_db.graph_core_models import RelationEvidenceWrite
from artana_evidence_db.read_model_support import (
    GraphReadModelTrigger,
    GraphReadModelUpdate,
    GraphReadModelUpdateDispatcher,
)
from artana_evidence_db.relation_projection_materialization_support import (
    ProjectionEndpoints,
    RelationProjectionMaterializationError,
    RelationProjectionMaterializationResult,
    backfill_claim_evidence_from_relation_cache,
    claim_evidence_provenance_id,
    claim_evidence_summary,
    claim_evidence_tier,
    dedupe_relation_ids,
    extract_scoping_qualifier_fingerprint,
    is_active_support_claim,
    participants_for_role,
    relation_provenance_id,
)
from artana_evidence_db.relation_projection_source_model import RelationProjectionOrigin
from artana_evidence_db.relation_type_support import normalize_relation_type


def _compute_canonicalization_fingerprint(
    participants: list[object],
) -> str:
    """Compute a stable fingerprint from scoping qualifiers on participants.

    Returns an empty string when no scoping qualifiers are present
    (backward-compatible with the pre-P0.2 triple-only identity).
    """
    import hashlib
    import json

    scoping = extract_scoping_qualifier_fingerprint(participants)
    if not scoping:
        return ""
    serialized = json.dumps(scoping, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:32]


if TYPE_CHECKING:
    from artana_evidence_db.graph_core_models import KernelEntity, KernelRelation
    from artana_evidence_db.kernel_domain_models import (
        DictionaryRelationType,
        KernelClaimParticipant,
        KernelRelationClaim,
        RelationConstraint,
    )


_PROMOTABLE_CONSTRAINT_PROFILES = frozenset({"ALLOWED", "EXPECTED"})


class RelationRepositoryLike(Protocol):
    """Minimal canonical relation write surface needed for projection materialization."""

    def get_by_id(
        self,
        relation_id: str,
        *,
        claim_backed_only: bool = True,
    ) -> KernelRelation | None: ...

    def upsert_relation(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        source_id: str,
        relation_type: str,
        target_id: str,
        canonicalization_fingerprint: str = "",
        curation_status: str = "DRAFT",
        provenance_id: str | None = None,
    ) -> KernelRelation: ...

    def delete(self, relation_id: str) -> bool: ...

    def list_evidence_for_relation(
        self,
        *,
        research_space_id: str,
        relation_id: str,
        claim_backed_only: bool = True,
        limit: int | None = None,
    ) -> list[object]: ...

    def replace_derived_evidence_cache(
        self,
        relation_id: str,
        *,
        evidences: list[RelationEvidenceWrite],
    ) -> KernelRelation: ...

    def find_by_triple(
        self,
        *,
        research_space_id: str,
        source_id: str,
        relation_type: str,
        target_id: str,
        canonicalization_fingerprint: str = "",
        claim_backed_only: bool = True,
    ) -> KernelRelation | None: ...


class RelationClaimRepositoryLike(Protocol):
    """Minimal relation-claim ledger surface needed by projection materialization."""

    def get_by_id(self, claim_id: str) -> KernelRelationClaim | None: ...

    def list_by_ids(self, claim_ids: list[str]) -> list[KernelRelationClaim]: ...

    def link_relation(
        self,
        claim_id: str,
        *,
        linked_relation_id: str,
    ) -> KernelRelationClaim: ...

    def clear_relation_link(self, claim_id: str) -> KernelRelationClaim: ...


class ClaimParticipantRepositoryLike(Protocol):
    """Minimal participant repository surface needed by projection materialization."""

    def find_by_claim_id(self, claim_id: str) -> list[KernelClaimParticipant]: ...

    def find_by_claim_ids(
        self,
        claim_ids: list[str],
    ) -> dict[str, list[KernelClaimParticipant]]: ...


class ClaimEvidenceRepositoryLike(Protocol):
    """Minimal claim-evidence repository surface needed by projection materialization."""

    def create(  # noqa: PLR0913
        self,
        *,
        claim_id: str,
        source_document_id: str | None,
        agent_run_id: str | None,
        sentence: str | None,
        sentence_source: str | None,
        sentence_confidence: str | None,
        sentence_rationale: str | None,
        figure_reference: str | None,
        table_reference: str | None,
        confidence: float,
        source_document_ref: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> object: ...

    def find_by_claim_id(self, claim_id: str) -> list[object]: ...


class EntityRepositoryLike(Protocol):
    """Minimal entity lookup surface needed by projection materialization."""

    def get_by_id(self, entity_id: str) -> KernelEntity | None: ...


class DictionaryRepositoryLike(Protocol):
    """Minimal dictionary governance surface needed by projection materialization."""

    def resolve_relation_synonym(
        self,
        relation_type: str,
    ) -> DictionaryRelationType | None: ...

    def is_triple_allowed(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> bool: ...

    def get_triple_profile(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> str: ...

    def get_constraints(
        self,
        *,
        source_type: str | None = None,
        relation_type: str | None = None,
        include_inactive: bool = False,
    ) -> list[RelationConstraint]: ...


class RelationProjectionSourceRepositoryLike(Protocol):
    """Minimal projection-lineage surface needed by projection materialization."""

    def create(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        relation_id: str,
        claim_id: str,
        projection_origin: RelationProjectionOrigin,
        source_document_id: str | None,
        agent_run_id: str | None,
        source_document_ref: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> object: ...

    def find_by_claim_id(
        self,
        *,
        research_space_id: str,
        claim_id: str,
    ) -> list[object]: ...

    def delete_projection_source(
        self,
        *,
        research_space_id: str,
        relation_id: str,
        claim_id: str,
    ) -> bool: ...

    def find_by_relation_id(self, relation_id: str) -> list[object]: ...

    def delete_by_claim_id(
        self,
        *,
        research_space_id: str,
        claim_id: str,
    ) -> list[str]: ...


class KernelRelationProjectionMaterializationService:
    """Canonical relation write owner for claim-backed projection materialization."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        relation_repo: RelationRepositoryLike,
        relation_claim_repo: RelationClaimRepositoryLike,
        claim_participant_repo: ClaimParticipantRepositoryLike,
        claim_evidence_repo: ClaimEvidenceRepositoryLike,
        entity_repo: EntityRepositoryLike,
        dictionary_repo: DictionaryRepositoryLike,
        relation_projection_repo: RelationProjectionSourceRepositoryLike,
        read_model_update_dispatcher: GraphReadModelUpdateDispatcher,
    ) -> None:
        self._relations = relation_repo
        self._claims = relation_claim_repo
        self._participants = claim_participant_repo
        self._claim_evidence = claim_evidence_repo
        self._entities = entity_repo
        self._dictionary = dictionary_repo
        self._projection_sources = relation_projection_repo
        self._read_model_updates = read_model_update_dispatcher

    def materialize_support_claim(
        self,
        claim_id: str,
        research_space_id: str,
        projection_origin: RelationProjectionOrigin,
        reviewed_by: str | None = None,
    ) -> RelationProjectionMaterializationResult:
        del reviewed_by
        claim = self._get_claim_or_raise(
            claim_id=claim_id,
            research_space_id=research_space_id,
        )
        self._assert_support_claim_materializable(claim)
        endpoints = self._resolve_projection_endpoints(
            claim=claim,
            research_space_id=research_space_id,
        )
        claim_evidences = self._claim_evidence.find_by_claim_id(claim_id)
        self._assert_projection_evidence_policy(
            endpoints=endpoints,
            claim_evidences=claim_evidences,
        )
        claim_participants = self._participants.find_by_claim_id(claim_id)
        fingerprint = _compute_canonicalization_fingerprint(claim_participants)
        relation = self._relations.upsert_relation(
            research_space_id=research_space_id,
            source_id=endpoints.source_id,
            relation_type=endpoints.relation_type,
            target_id=endpoints.target_id,
            canonicalization_fingerprint=fingerprint,
            curation_status="DRAFT",
            provenance_id=relation_provenance_id(
                claim=claim,
                evidences=claim_evidences,
            ),
        )
        stale_relation_ids: list[str] = []
        for existing_row in self._projection_sources.find_by_claim_id(
            research_space_id=research_space_id,
            claim_id=claim_id,
        ):
            existing_relation_id = str(existing_row.relation_id)
            if existing_relation_id == str(relation.id):
                continue
            if self._projection_sources.delete_projection_source(
                research_space_id=research_space_id,
                relation_id=existing_relation_id,
                claim_id=claim_id,
            ):
                stale_relation_ids.append(existing_relation_id)
        self._projection_sources.create(
            research_space_id=research_space_id,
            relation_id=str(relation.id),
            claim_id=claim_id,
            projection_origin=projection_origin,
            source_document_id=(
                str(claim.source_document_id)
                if claim.source_document_id is not None
                else None
            ),
            source_document_ref=claim.source_document_ref,
            agent_run_id=claim.agent_run_id,
            metadata={"origin": projection_origin.lower()},
        )
        self._claims.link_relation(claim_id, linked_relation_id=str(relation.id))
        rebuilt = self.rebuild_relation_projection(
            relation_id=str(relation.id),
            research_space_id=research_space_id,
        )
        deleted_relation_ids = list(rebuilt.deleted_relation_ids)
        rebuilt_relation_ids = list(rebuilt.rebuilt_relation_ids)
        for stale_relation_id in stale_relation_ids:
            stale_result = self.rebuild_relation_projection(
                relation_id=stale_relation_id,
                research_space_id=research_space_id,
            )
            deleted_relation_ids.extend(stale_result.deleted_relation_ids)
            rebuilt_relation_ids.extend(stale_result.rebuilt_relation_ids)
        return RelationProjectionMaterializationResult(
            relation=rebuilt.relation,
            rebuilt_relation_ids=tuple(
                dedupe_relation_ids([str(relation.id), *rebuilt_relation_ids]),
            ),
            deleted_relation_ids=tuple(dedupe_relation_ids(deleted_relation_ids)),
            derived_evidence_rows=rebuilt.derived_evidence_rows,
        )

    def detach_claim_projection(
        self,
        claim_id: str,
        research_space_id: str,
    ) -> RelationProjectionMaterializationResult:
        self._claims.clear_relation_link(claim_id)
        affected_relation_ids = self._projection_sources.delete_by_claim_id(
            research_space_id=research_space_id,
            claim_id=claim_id,
        )
        rebuilt_relation_ids: list[str] = []
        deleted_relation_ids: list[str] = []
        for relation_id in affected_relation_ids:
            rebuilt = self.rebuild_relation_projection(
                relation_id=relation_id,
                research_space_id=research_space_id,
            )
            rebuilt_relation_ids.extend(rebuilt.rebuilt_relation_ids)
            deleted_relation_ids.extend(rebuilt.deleted_relation_ids)
        return RelationProjectionMaterializationResult(
            relation=None,
            rebuilt_relation_ids=tuple(dedupe_relation_ids(rebuilt_relation_ids)),
            deleted_relation_ids=tuple(dedupe_relation_ids(deleted_relation_ids)),
            derived_evidence_rows=0,
        )

    def rebuild_relation_projection(  # noqa: C901, PLR0912, PLR0915
        self,
        relation_id: str,
        research_space_id: str,
    ) -> RelationProjectionMaterializationResult:
        current_relation = self._relations.get_by_id(
            relation_id,
            claim_backed_only=False,
        )
        projection_rows = self._projection_sources.find_by_relation_id(relation_id)
        if not projection_rows:
            if current_relation is None:
                return RelationProjectionMaterializationResult(
                    relation=None,
                    rebuilt_relation_ids=(),
                    deleted_relation_ids=(),
                    derived_evidence_rows=0,
                )
            self._relations.delete(relation_id)
            result = RelationProjectionMaterializationResult(
                relation=None,
                rebuilt_relation_ids=(),
                deleted_relation_ids=(relation_id,),
                derived_evidence_rows=0,
            )
            self._dispatch_projection_change(
                research_space_id=research_space_id,
                claim_ids=(),
                relation_ids=(relation_id,),
                entity_ids=(
                    str(current_relation.source_id),
                    str(current_relation.target_id),
                ),
            )
            return result

        claims_by_id = {
            str(claim.id): claim
            for claim in self._claims.list_by_ids(
                [str(row.claim_id) for row in projection_rows],
            )
        }
        participants_by_claim_id = self._participants.find_by_claim_ids(
            [str(row.claim_id) for row in projection_rows],
        )
        current_evidence = self._relations.list_evidence_for_relation(
            research_space_id=research_space_id,
            relation_id=relation_id,
            claim_backed_only=False,
        )
        valid_sources: list[tuple[str, KernelRelationClaim, ProjectionEndpoints]] = []
        pruned_claim_ids: list[str] = []
        expected_signature: tuple[str, str, str, str, str] | None = None

        for row in projection_rows:
            claim_id = str(row.claim_id)
            claim = claims_by_id.get(claim_id)
            if claim is None:
                pruned_claim_ids.append(claim_id)
                continue
            if not is_active_support_claim(claim):
                pruned_claim_ids.append(claim_id)
                continue
            try:
                endpoints = self._resolve_projection_endpoints(
                    claim=claim,
                    research_space_id=research_space_id,
                    participants=participants_by_claim_id.get(claim_id, []),
                )
            except RelationProjectionMaterializationError:
                pruned_claim_ids.append(claim_id)
                continue
            if not self._claim_satisfies_projection_evidence_policy(
                endpoints=endpoints,
                claim_id=claim_id,
            ):
                pruned_claim_ids.append(claim_id)
                continue
            claim_fingerprint = _compute_canonicalization_fingerprint(
                participants_by_claim_id.get(claim_id, []),
            )
            signature = (
                endpoints.source_id,
                endpoints.relation_type,
                endpoints.target_id,
                research_space_id,
                claim_fingerprint,
            )
            if expected_signature is None:
                expected_signature = signature
            if signature != expected_signature:
                pruned_claim_ids.append(claim_id)
                continue
            valid_sources.append((claim_id, claim, endpoints))

        for claim_id in pruned_claim_ids:
            self._projection_sources.delete_projection_source(
                research_space_id=research_space_id,
                relation_id=relation_id,
                claim_id=claim_id,
            )

        if not valid_sources:
            if current_relation is not None:
                self._relations.delete(relation_id)
                result = RelationProjectionMaterializationResult(
                    relation=None,
                    rebuilt_relation_ids=(),
                    deleted_relation_ids=(relation_id,),
                    derived_evidence_rows=0,
                )
                self._dispatch_projection_change(
                    research_space_id=research_space_id,
                    claim_ids=tuple(pruned_claim_ids),
                    relation_ids=(relation_id,),
                    entity_ids=(
                        str(current_relation.source_id),
                        str(current_relation.target_id),
                    ),
                )
                return result
            return RelationProjectionMaterializationResult(relation=None)

        if len(valid_sources) == 1 and not self._claim_evidence.find_by_claim_id(
            valid_sources[0][0],
        ):
            backfill_claim_evidence_from_relation_cache(
                claim_id=valid_sources[0][0],
                claim=valid_sources[0][1],
                current_evidence=current_evidence,
                claim_evidence_repo=self._claim_evidence,
            )

        endpoints = valid_sources[0][2]
        first_claim_id = valid_sources[0][0]
        rebuild_participants = participants_by_claim_id.get(first_claim_id, [])
        rebuild_fingerprint = _compute_canonicalization_fingerprint(
            rebuild_participants,
        )
        relation = self._relations.upsert_relation(
            research_space_id=research_space_id,
            source_id=endpoints.source_id,
            relation_type=endpoints.relation_type,
            target_id=endpoints.target_id,
            canonicalization_fingerprint=rebuild_fingerprint,
            curation_status=(
                current_relation.curation_status
                if current_relation is not None
                else "DRAFT"
            ),
            provenance_id=(
                str(current_relation.provenance_id)
                if current_relation is not None
                and current_relation.provenance_id is not None
                else None
            ),
        )
        for claim_id, _claim, _endpoints in valid_sources:
            self._claims.link_relation(claim_id, linked_relation_id=str(relation.id))

        derived_evidences: list[RelationEvidenceWrite] = []
        for claim_id, claim, _endpoints in valid_sources:
            derived_evidences.extend(
                [
                    RelationEvidenceWrite(
                        confidence=float(evidence.confidence),
                        evidence_summary=claim_evidence_summary(
                            claim=claim,
                            evidence=evidence,
                        ),
                        evidence_sentence=evidence.sentence,
                        evidence_sentence_source=evidence.sentence_source,
                        evidence_sentence_confidence=evidence.sentence_confidence,
                        evidence_sentence_rationale=evidence.sentence_rationale,
                        evidence_tier=claim_evidence_tier(evidence),
                        provenance_id=claim_evidence_provenance_id(evidence),
                        source_document_id=evidence.source_document_id,
                        source_document_ref=evidence.source_document_ref,
                        agent_run_id=evidence.agent_run_id or claim.agent_run_id,
                    )
                    for evidence in self._claim_evidence.find_by_claim_id(claim_id)
                ],
            )
        relation = self._relations.replace_derived_evidence_cache(
            str(relation.id),
            evidences=derived_evidences,
        )
        deleted_relation_ids: tuple[str, ...] = ()
        if current_relation is not None and str(current_relation.id) != str(
            relation.id,
        ):
            self._relations.delete(str(current_relation.id))
            deleted_relation_ids = (str(current_relation.id),)
        result = RelationProjectionMaterializationResult(
            relation=relation,
            rebuilt_relation_ids=(str(relation.id),),
            deleted_relation_ids=deleted_relation_ids,
            derived_evidence_rows=len(derived_evidences),
        )
        self._dispatch_projection_change(
            research_space_id=research_space_id,
            claim_ids=tuple(claim_id for claim_id, _claim, _endpoints in valid_sources),
            relation_ids=(
                str(relation.id),
                *deleted_relation_ids,
            ),
            entity_ids=tuple(
                dict.fromkeys(
                    entity_id
                    for _claim_id, _claim, endpoints in valid_sources
                    for entity_id in endpoints.entity_ids
                ),
            ),
        )
        return result

    def find_claim_backed_relation_for_claim(
        self,
        *,
        claim_id: str,
        research_space_id: str,
    ) -> KernelRelation | None:
        claim = self._get_claim_or_raise(
            claim_id=claim_id,
            research_space_id=research_space_id,
        )
        claim_participants = self._participants.find_by_claim_id(claim_id)
        endpoints = self._resolve_projection_endpoints(
            claim=claim,
            research_space_id=research_space_id,
            participants=claim_participants,
        )
        fingerprint = _compute_canonicalization_fingerprint(claim_participants)
        return self._relations.find_by_triple(
            research_space_id=research_space_id,
            source_id=endpoints.source_id,
            relation_type=endpoints.relation_type,
            target_id=endpoints.target_id,
            canonicalization_fingerprint=fingerprint,
            claim_backed_only=True,
        )

    def _get_claim_or_raise(
        self,
        *,
        claim_id: str,
        research_space_id: str,
    ) -> KernelRelationClaim:
        claim = self._claims.get_by_id(claim_id)
        if claim is None or str(claim.research_space_id) != research_space_id:
            msg = (
                f"Relation claim {claim_id} not found in research space "
                f"{research_space_id}"
            )
            raise RelationProjectionMaterializationError(msg)
        return claim

    def _assert_support_claim_materializable(
        self,
        claim: KernelRelationClaim,
    ) -> None:
        if claim.polarity != "SUPPORT":
            msg = "Only SUPPORT claims can materialize canonical relations"
            raise RelationProjectionMaterializationError(msg)
        if claim.claim_status != "RESOLVED":
            msg = "Only RESOLVED claims can materialize canonical relations"
            raise RelationProjectionMaterializationError(msg)
        if claim.persistability != "PERSISTABLE":
            msg = "Only PERSISTABLE claims can materialize canonical relations"
            raise RelationProjectionMaterializationError(msg)

    def _resolve_projection_endpoints(
        self,
        *,
        claim: KernelRelationClaim,
        research_space_id: str,
        participants: list[KernelClaimParticipant] | None = None,
    ) -> ProjectionEndpoints:
        claim_participants = (
            participants
            if participants is not None
            else self._participants.find_by_claim_id(str(claim.id))
        )
        subjects = participants_for_role(claim_participants, role="SUBJECT")
        object_participants = participants_for_role(claim_participants, role="OBJECT")
        endpoint_participants = [*subjects, *object_participants]
        if (
            not subjects
            or not object_participants
            or any(
                participant.entity_id is None for participant in endpoint_participants
            )
        ):
            msg = (
                "Claim-backed materialization requires SUBJECT/OBJECT participants "
                "with entity anchors"
            )
            raise RelationProjectionMaterializationError(msg)
        subject = subjects[0]
        object_participant = object_participants[0]
        source_entity = self._entities.get_by_id(str(subject.entity_id))
        target_entity = self._entities.get_by_id(str(object_participant.entity_id))
        if source_entity is None or target_entity is None:
            msg = "Claim participant endpoint entities must exist before projection"
            raise RelationProjectionMaterializationError(msg)
        if str(source_entity.research_space_id) != research_space_id:
            msg = (
                f"Source entity {source_entity.id} is not in research space "
                f"{research_space_id}"
            )
            raise RelationProjectionMaterializationError(msg)
        if str(target_entity.research_space_id) != research_space_id:
            msg = (
                f"Target entity {target_entity.id} is not in research space "
                f"{research_space_id}"
            )
            raise RelationProjectionMaterializationError(msg)
        endpoint_entity_ids = tuple(
            dict.fromkeys(
                str(participant.entity_id)
                for participant in endpoint_participants
                if participant.entity_id is not None
            ),
        )
        for endpoint_entity_id in endpoint_entity_ids:
            if endpoint_entity_id in {str(source_entity.id), str(target_entity.id)}:
                continue
            endpoint_entity = self._entities.get_by_id(endpoint_entity_id)
            if endpoint_entity is None:
                msg = "Claim participant endpoint entities must exist before projection"
                raise RelationProjectionMaterializationError(msg)
            if str(endpoint_entity.research_space_id) != research_space_id:
                msg = (
                    f"Endpoint entity {endpoint_entity.id} is not in research space "
                    f"{research_space_id}"
                )
                raise RelationProjectionMaterializationError(msg)
        normalized_relation_type = normalize_relation_type(claim.relation_type)
        if not normalized_relation_type:
            msg = "relation_type is required"
            raise RelationProjectionMaterializationError(msg)
        canonical_relation_type = normalized_relation_type
        resolved_relation_type = self._dictionary.resolve_relation_synonym(
            normalized_relation_type,
        )
        if resolved_relation_type is not None:
            resolved_relation_type_id = getattr(resolved_relation_type, "id", None)
            if (
                isinstance(resolved_relation_type_id, str)
                and resolved_relation_type_id.strip()
            ):
                canonical_relation_type = resolved_relation_type_id.strip().upper()
        if not self._dictionary.is_triple_allowed(
            source_entity.entity_type,
            canonical_relation_type,
            target_entity.entity_type,
        ):
            msg = (
                f"Triple ({source_entity.entity_type}, {canonical_relation_type}, "
                f"{target_entity.entity_type}) is not allowed by constraints"
            )
            raise RelationProjectionMaterializationError(msg)
        self._get_promotable_relation_constraint(
            source_type=source_entity.entity_type,
            relation_type=canonical_relation_type,
            target_type=target_entity.entity_type,
        )
        return ProjectionEndpoints(
            source_id=str(source_entity.id),
            source_label=source_entity.display_label,
            source_type=source_entity.entity_type,
            relation_type=canonical_relation_type,
            target_id=str(target_entity.id),
            target_label=target_entity.display_label,
            target_type=target_entity.entity_type,
            entity_ids=endpoint_entity_ids,
        )

    def _get_promotable_relation_constraint(
        self,
        *,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> RelationConstraint:
        constraints = self._dictionary.get_constraints(
            source_type=source_type,
            relation_type=relation_type,
            include_inactive=False,
        )
        for constraint in constraints:
            if constraint.target_type != target_type:
                continue
            profile = constraint.profile or (
                "ALLOWED" if constraint.is_allowed else "FORBIDDEN"
            )
            if (
                not constraint.is_allowed
                or profile not in _PROMOTABLE_CONSTRAINT_PROFILES
            ):
                msg = (
                    f"Triple ({source_type}, {relation_type}, {target_type}) "
                    f"uses {profile} governance and cannot be promoted."
                )
                raise RelationProjectionMaterializationError(msg)
            return constraint
        msg = (
            f"Triple ({source_type}, {relation_type}, {target_type}) requires an "
            "active exact relation constraint before promotion."
        )
        raise RelationProjectionMaterializationError(msg)

    def _assert_projection_evidence_policy(
        self,
        *,
        endpoints: ProjectionEndpoints,
        claim_evidences: list[object],
    ) -> None:
        constraint = self._get_promotable_relation_constraint(
            source_type=endpoints.source_type,
            relation_type=endpoints.relation_type,
            target_type=endpoints.target_type,
        )
        if constraint.requires_evidence and not claim_evidences:
            msg = "Claim projection requires supporting claim evidence."
            raise RelationProjectionMaterializationError(msg)

    def _claim_satisfies_projection_evidence_policy(
        self,
        *,
        endpoints: ProjectionEndpoints,
        claim_id: str,
    ) -> bool:
        constraint = self._get_promotable_relation_constraint(
            source_type=endpoints.source_type,
            relation_type=endpoints.relation_type,
            target_type=endpoints.target_type,
        )
        if not constraint.requires_evidence:
            return True
        return bool(self._claim_evidence.find_by_claim_id(claim_id))

    def _dispatch_projection_change(
        self,
        *,
        research_space_id: str,
        claim_ids: tuple[str, ...],
        relation_ids: tuple[str, ...],
        entity_ids: tuple[str, ...],
    ) -> None:
        normalized_claim_ids = tuple(dict.fromkeys(claim_ids))
        normalized_relation_ids = tuple(dict.fromkeys(relation_ids))
        normalized_entity_ids = tuple(dict.fromkeys(entity_ids))
        updates = (
            GraphReadModelUpdate(
                model_name="entity_neighbors",
                trigger=GraphReadModelTrigger.PROJECTION_CHANGE,
                claim_ids=normalized_claim_ids,
                relation_ids=normalized_relation_ids,
                entity_ids=normalized_entity_ids,
                space_id=research_space_id,
            ),
            GraphReadModelUpdate(
                model_name="entity_relation_summary",
                trigger=GraphReadModelTrigger.PROJECTION_CHANGE,
                claim_ids=normalized_claim_ids,
                relation_ids=normalized_relation_ids,
                entity_ids=normalized_entity_ids,
                space_id=research_space_id,
            ),
            GraphReadModelUpdate(
                model_name="entity_claim_summary",
                trigger=GraphReadModelTrigger.PROJECTION_CHANGE,
                claim_ids=normalized_claim_ids,
                relation_ids=normalized_relation_ids,
                entity_ids=normalized_entity_ids,
                space_id=research_space_id,
            ),
        )
        self._read_model_updates.dispatch_many(updates)


__all__ = [
    "KernelRelationProjectionMaterializationService",
    "RelationProjectionMaterializationError",
    "RelationProjectionMaterializationResult",
]
