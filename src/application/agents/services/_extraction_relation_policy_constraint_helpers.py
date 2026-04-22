from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from src.application.agents.services._extraction_relation_synonym_proposal_store import (
    _PolicyProposalStoreResult,
    store_relation_synonym_proposals,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from artana_evidence_db.semantic_ports import DictionaryPort

    from src.domain.agents.contracts.extraction_policy import ExtractionPolicyContract
    from src.domain.entities.source_document import SourceDocument
    from src.type_definitions.common import ResearchSpaceSettings

logger = logging.getLogger(__name__)

type RelationGovernanceMode = Literal["HUMAN_IN_LOOP", "FULL_AUTO"]

_POLICY_AGENT_CREATED_BY = "agent:extraction_policy_step"


@dataclass(frozen=True)
class _PendingConstraintRequest:
    triple: tuple[str, str, str]
    is_allowed: bool
    requires_evidence: bool
    profile: str = "ALLOWED"
    domain_context: str | None = None


class _ExtractionRelationPolicyConstraintHelpers:
    _dictionary: DictionaryPort | None
    _review_queue_submitter: Callable[[str, str, str | None, str], None] | None

    def _store_policy_constraint_proposals(
        self,
        *,
        research_space_id: str,
        document: SourceDocument,
        policy_contract: ExtractionPolicyContract | None,
        policy_run_id: str | None,
        relation_governance_mode: RelationGovernanceMode,
    ) -> _PolicyProposalStoreResult:
        if self._dictionary is None or policy_contract is None:
            return _PolicyProposalStoreResult()
        source_ref = f"source_document:{document.id}"
        if policy_run_id is not None:
            source_ref = f"{source_ref}:policy_run:{policy_run_id}"

        created_count = 0
        errors: list[str] = []

        for request in self._iter_pending_constraint_requests(policy_contract):
            created, error = self._create_pending_constraint(
                request=request,
                source_ref=source_ref,
                relation_governance_mode=relation_governance_mode,
            )
            if error is not None:
                errors.append(error)

            review_priority: Literal["low", "medium"] | None
            if created:
                created_count += 1
                review_priority = "low"
            elif relation_governance_mode == "FULL_AUTO":
                review_priority = "medium"
            else:
                review_priority = None

            if review_priority is not None:
                self._enqueue_review_item(
                    entity_type="relation_constraint",
                    entity_id=self._constraint_entity_id(request.triple),
                    research_space_id=research_space_id,
                    priority=review_priority,
                )

        synonym_store_result = store_relation_synonym_proposals(
            policy_contract.relation_type_mapping_proposals,
            dictionary=self._dictionary,
        )
        return _PolicyProposalStoreResult(
            constraint_proposals_created_count=created_count,
            relation_type_mapping_proposals_count=(
                synonym_store_result.mapping_proposals_count
            ),
            relation_synonym_proposals_attempted_count=(
                synonym_store_result.attempted_count
            ),
            relation_synonym_proposals_created_count=synonym_store_result.created_count,
            relation_synonym_proposals_skipped_count=synonym_store_result.skipped_count,
            relation_synonym_proposals_failed_count=synonym_store_result.failed_count,
            errors=tuple(errors) + synonym_store_result.errors,
        )

    def _iter_pending_constraint_requests(
        self,
        policy_contract: ExtractionPolicyContract,
    ) -> tuple[_PendingConstraintRequest, ...]:
        seen_keys: set[tuple[str, str, str]] = set()
        requests: list[_PendingConstraintRequest] = []
        for proposal in policy_contract.relation_constraint_proposals:
            triple = self._proposal_triple_key(
                proposal.source_type,
                proposal.relation_type,
                proposal.target_type,
            )
            request = self._build_pending_constraint_request(
                triple=triple,
                seen_keys=seen_keys,
                is_allowed=proposal.proposed_is_allowed,
                requires_evidence=proposal.proposed_requires_evidence,
            )
            if request is not None:
                requests.append(request)

        for mapping in policy_contract.relation_type_mapping_proposals:
            triple = self._proposal_triple_key(
                mapping.source_type,
                mapping.mapped_relation_type,
                mapping.target_type,
            )
            request = self._build_pending_constraint_request(
                triple=triple,
                seen_keys=seen_keys,
                is_allowed=True,
                requires_evidence=True,
            )
            if request is not None:
                requests.append(request)

        return tuple(requests)

    def _build_pending_constraint_request(
        self,
        *,
        triple: tuple[str, str, str] | None,
        seen_keys: set[tuple[str, str, str]],
        is_allowed: bool,
        requires_evidence: bool,
    ) -> _PendingConstraintRequest | None:
        if triple is None or triple in seen_keys:
            return None
        seen_keys.add(triple)
        return _PendingConstraintRequest(
            triple=triple,
            is_allowed=is_allowed,
            requires_evidence=requires_evidence,
        )

    def _constraint_entity_id(self, triple: tuple[str, str, str]) -> str:
        return f"{triple[0]}:{triple[1]}:{triple[2]}"

    def _create_pending_constraint(
        self,
        *,
        request: _PendingConstraintRequest,
        source_ref: str,
        relation_governance_mode: RelationGovernanceMode,
    ) -> tuple[bool, str | None]:
        if self._dictionary is None:
            return False, None
        creation_policy: Literal["ACTIVE", "PENDING_REVIEW"] = (
            "ACTIVE" if relation_governance_mode == "FULL_AUTO" else "PENDING_REVIEW"
        )
        policy_settings: ResearchSpaceSettings = {
            "dictionary_agent_creation_policy": creation_policy,
        }
        triple = request.triple
        triple_key = f"{triple[0]}:{triple[1]}:{triple[2]}"

        def _do_write() -> None:
            self._write_constraint(
                triple=triple,
                is_allowed=request.is_allowed,
                requires_evidence=request.requires_evidence,
                profile=request.profile,
                domain_context=request.domain_context,
                source_ref=source_ref,
                policy_settings=policy_settings,
            )

        try:
            _do_write()
        except ValueError as exc:
            error_text = str(exc)
            fail = f"relation_policy_proposal_store_failed:{triple_key}:{error_text}"
            if not self._should_bootstrap_constraint_dependencies(error_text):
                return False, fail
            if not self._bootstrap_full_auto_proposal_dependencies(
                triple=triple,
                source_ref=f"{source_ref}:proposal_dependency_bootstrap",
                policy_settings=policy_settings,
            ):
                logger.warning("Bootstrap failed for %s (%s)", triple_key, exc)
                return False, fail
            try:
                _do_write()
            except ValueError as retry_exc:
                logger.warning(
                    "Store failed after bootstrap for %s (%s)",
                    triple_key,
                    retry_exc,
                )
                return (
                    False,
                    f"relation_policy_proposal_store_failed:{triple_key}:{retry_exc!s}",
                )
            return True, None
        else:
            return True, None

    @staticmethod
    def _should_bootstrap_constraint_dependencies(error_message: str) -> bool:
        normalized = error_message.lower()
        dependency_markers = (
            "unknown relation type",
            "relation type does not exist",
            "source type",
            "target type",
            "entity type",
            "not found",
            "does not exist",
        )
        return any(marker in normalized for marker in dependency_markers)

    def _ensure_full_auto_allowed_constraint(
        self,
        *,
        source_type: str,
        relation_type: str,
        target_type: str,
        source_ref: str,
    ) -> tuple[bool, str]:
        if self._dictionary is None:
            return False, "dictionary_service_unavailable"

        request = _PendingConstraintRequest(
            triple=(source_type, relation_type, target_type),
            is_allowed=True,
            requires_evidence=True,
        )
        created, error = self._create_pending_constraint(
            request=request,
            source_ref=source_ref,
            relation_governance_mode="FULL_AUTO",
        )
        if error is not None:
            return False, error
        if not created:
            return False, "full_auto_constraint_create_failed"

        constraints = self._dictionary.get_constraints(
            source_type=source_type,
            relation_type=relation_type,
            include_inactive=True,
        )
        for constraint in constraints:
            if constraint.target_type != target_type:
                continue
            if not constraint.is_active:
                continue
            if constraint.review_status != "ACTIVE":
                continue
            if not constraint.is_allowed:
                return False, "active_forbidden_constraint_exists"
            return True, "full_auto_constraint_active"
        return False, "full_auto_constraint_not_active"

    def _write_constraint(  # noqa: PLR0913
        self,
        *,
        triple: tuple[str, str, str],
        is_allowed: bool,
        requires_evidence: bool,
        profile: str = "ALLOWED",
        domain_context: str | None = None,
        source_ref: str,
        policy_settings: ResearchSpaceSettings,
    ) -> None:
        if self._dictionary is None:
            return
        kwargs: dict[str, object] = {
            "source_type": triple[0],
            "relation_type": triple[1],
            "target_type": triple[2],
            "is_allowed": is_allowed,
            "requires_evidence": requires_evidence,
            "created_by": _POLICY_AGENT_CREATED_BY,
            "source_ref": source_ref,
            "research_space_settings": policy_settings,
        }
        if profile != "ALLOWED":
            kwargs["profile"] = profile
        if domain_context is not None:
            kwargs["domain_context"] = domain_context
        self._dictionary.create_relation_constraint(**kwargs)

    def _bootstrap_full_auto_proposal_dependencies(
        self,
        *,
        triple: tuple[str, str, str],
        source_ref: str,
        policy_settings: ResearchSpaceSettings,
    ) -> bool:
        return (
            self._ensure_entity_type_exists(
                entity_type=triple[0],
                source_ref=source_ref,
                policy_settings=policy_settings,
            )
            and self._ensure_entity_type_exists(
                entity_type=triple[2],
                source_ref=source_ref,
                policy_settings=policy_settings,
            )
            and self._ensure_relation_type_exists(
                relation_type=triple[1],
                source_ref=source_ref,
                policy_settings=policy_settings,
            )
        )

    def _ensure_entity_type_exists(
        self,
        *,
        entity_type: str,
        source_ref: str,
        policy_settings: ResearchSpaceSettings,
    ) -> bool:
        if self._dictionary is None:
            return False
        try:
            resolved = self._dictionary.create_entity_type(
                entity_type=entity_type,
                display_name=entity_type.replace("_", " ").title(),
                description=("Auto-created to persist extraction policy proposal."),
                domain_context="general",
                created_by=_POLICY_AGENT_CREATED_BY,
                source_ref=source_ref,
                research_space_settings=policy_settings,
            )
        except ValueError as exc:
            logger.warning(
                "Failed to bootstrap entity_type=%s for relation proposals (%s)",
                entity_type,
                exc,
            )
            return False
        if resolved.is_active and resolved.review_status == "ACTIVE":
            return True
        try:
            self._dictionary.set_entity_type_review_status(
                resolved.id,
                review_status="ACTIVE",
                reviewed_by=_POLICY_AGENT_CREATED_BY,
            )
        except ValueError as exc:
            logger.warning(
                "Failed to activate entity_type=%s for relation proposals (%s)",
                resolved.id,
                exc,
            )
            return False
        return self._dictionary.get_entity_type(resolved.id) is not None

    def _ensure_relation_type_exists(  # noqa: C901, PLR0911
        self,
        *,
        relation_type: str,
        source_ref: str,
        policy_settings: ResearchSpaceSettings,
    ) -> bool:
        if self._dictionary is None:
            return False
        creation_policy = str(
            policy_settings.get("dictionary_agent_creation_policy", "ACTIVE"),
        ).upper()
        target_review_status: Literal["ACTIVE", "PENDING_REVIEW"] = (
            "ACTIVE" if creation_policy == "ACTIVE" else "PENDING_REVIEW"
        )
        existing = self._dictionary.get_relation_type(
            relation_type,
            include_inactive=True,
        )
        if existing is not None:
            if target_review_status == "ACTIVE":
                if existing.is_active and existing.review_status == "ACTIVE":
                    return True
                try:
                    self._dictionary.set_relation_type_review_status(
                        relation_type,
                        review_status="ACTIVE",
                        reviewed_by=_POLICY_AGENT_CREATED_BY,
                    )
                except ValueError as exc:
                    logger.warning(
                        "Failed to activate relation_type=%s for relation proposals (%s)",
                        relation_type,
                        exc,
                    )
                    return False
                refreshed = self._dictionary.get_relation_type(
                    relation_type,
                    include_inactive=True,
                )
                return (
                    refreshed is not None
                    and refreshed.is_active
                    and refreshed.review_status == "ACTIVE"
                )
            if existing.review_status == "PENDING_REVIEW":
                return True
            return True

        creation_settings = policy_settings
        try:
            self._dictionary.create_relation_type(
                relation_type=relation_type,
                display_name=relation_type.replace("_", " ").title(),
                description=("Auto-created to persist extraction policy proposal."),
                domain_context="general",
                is_directional=True,
                created_by=_POLICY_AGENT_CREATED_BY,
                source_ref=source_ref,
                research_space_settings=creation_settings,
            )
        except ValueError as exc:
            logger.warning(
                "Failed to bootstrap relation_type=%s for relation proposals (%s)",
                relation_type,
                exc,
            )
            return False
        created = self._dictionary.get_relation_type(
            relation_type,
            include_inactive=True,
        )
        if created is None:
            return False
        if target_review_status == "PENDING_REVIEW":
            return True
        if created.is_active and created.review_status == "ACTIVE":
            return True
        try:
            self._dictionary.set_relation_type_review_status(
                relation_type,
                review_status="ACTIVE",
                reviewed_by=_POLICY_AGENT_CREATED_BY,
            )
        except ValueError as exc:
            logger.warning(
                "Failed to activate relation_type=%s after creation for relation proposals (%s)",
                relation_type,
                exc,
            )
            return False
        activated = self._dictionary.get_relation_type(
            relation_type,
            include_inactive=True,
        )
        return (
            activated is not None
            and activated.is_active
            and activated.review_status == "ACTIVE"
        )

    def _proposal_triple_key(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> tuple[str, str, str] | None:
        msg = "subclass must implement _proposal_triple_key"
        raise NotImplementedError(msg)

    def _enqueue_review_item(
        self,
        *,
        entity_type: str,
        entity_id: str,
        research_space_id: str | None,
        priority: str,
    ) -> None:
        msg = "subclass must implement _enqueue_review_item"
        raise NotImplementedError(msg)


__all__ = [
    "RelationGovernanceMode",
    "_ExtractionRelationPolicyConstraintHelpers",
    "_PolicyProposalStoreResult",
]
