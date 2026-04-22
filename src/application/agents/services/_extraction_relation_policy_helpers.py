"""Policy and validation helper mixin for extraction relation persistence."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from src.application.agents.services._extraction_relation_policy_constraint_helpers import (
    RelationGovernanceMode,
    _ExtractionRelationPolicyConstraintHelpers,
)
from src.application.agents.services._extraction_relation_rejection_helpers import (
    index_constraint_proposals,
    index_mapping_proposals,
    merge_unique_reasons,
    record_rejected_relation,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from artana_evidence_db.semantic_ports import DictionaryPort

    from src.domain.agents.contracts.extraction_policy import (
        ExtractionPolicyContract,
        RelationConstraintProposal,
        RelationTypeMappingProposal,
        UnknownRelationPattern,
    )
    from src.domain.agents.ports.extraction_policy_agent_port import (
        ExtractionPolicyAgentPort,
    )
    from src.domain.entities.source_document import SourceDocument
    from src.type_definitions.common import JSONObject, ResearchSpaceSettings

logger = logging.getLogger(__name__)

type RelationValidationState = Literal[
    "ALLOWED",
    "FORBIDDEN",
    "UNDEFINED",
    "INVALID_COMPONENTS",
    "ENDPOINT_UNRESOLVED",
    "SELF_LOOP",
]
type RelationPersistability = Literal["PERSISTABLE", "NON_PERSISTABLE"]
type RelationClaimPolarity = Literal["SUPPORT", "REFUTE", "UNCERTAIN", "HYPOTHESIS"]


@dataclass(frozen=True)
class _ResolvedRelationCandidate:
    source_entity_id: str | None
    target_entity_id: str | None
    source_type: str
    relation_type: str
    target_type: str
    source_label: str | None
    target_label: str | None
    source_anchors: JSONObject | None
    target_anchors: JSONObject | None
    confidence: float
    validation_state: RelationValidationState
    validation_reason: str
    evidence_excerpt: str | None = None
    evidence_locator: str | None = None
    polarity: RelationClaimPolarity = "UNCERTAIN"
    claim_text: str | None = None
    claim_section: str | None = None
    persistability: RelationPersistability = "PERSISTABLE"
    assessment: JSONObject | None = None
    constraint_profile: str = "ALLOWED"


@dataclass(frozen=True)
class _PolicyStepResult:
    contract: ExtractionPolicyContract | None = None
    errors: tuple[str, ...] = ()


class _ExtractionRelationPolicyHelpers(_ExtractionRelationPolicyConstraintHelpers):
    """Policy-step and dictionary-validation helpers."""

    _dictionary: DictionaryPort | None
    _policy_agent: ExtractionPolicyAgentPort | None
    _review_queue_submitter: Callable[[str, str, str | None, str], None] | None

    async def _run_policy_step(
        self,
        *,
        research_space_id: str,
        document: SourceDocument,
        source_type: str,
        unknown_patterns: tuple[UnknownRelationPattern, ...],
        model_id: str | None,
    ) -> _PolicyStepResult:
        policy_agent = self._policy_agent
        if policy_agent is None or not unknown_patterns:
            return _PolicyStepResult()

        from src.domain.agents.contexts.extraction_policy_context import (
            ExtractionPolicyContext,
        )

        context = ExtractionPolicyContext(
            document_id=str(document.id),
            source_type=source_type.strip().lower(),
            research_space_id=research_space_id,
            unknown_relation_patterns=list(unknown_patterns),
            current_constraints=list(
                self._build_constraints_snapshot(unknown_patterns),
            ),
            existing_relation_types=list(self._list_active_relation_types()),
            shadow_mode=False,
        )
        try:
            contract = await policy_agent.propose(context, model_id=model_id)
            return _PolicyStepResult(contract=contract)
        except Exception as exc:  # noqa: BLE001 - never block fail-open persistence
            logger.warning(
                "Policy step failed for document_id=%s: %s",
                document.id,
                exc,
            )
            return _PolicyStepResult(
                errors=(f"relation_policy_step_failed:{type(exc).__name__}",),
            )

    def _build_unknown_relation_patterns(
        self,
        candidates: tuple[_ResolvedRelationCandidate, ...],
    ) -> tuple[UnknownRelationPattern, ...]:
        from src.domain.agents.contracts.extraction_policy import UnknownRelationPattern

        aggregated: dict[
            tuple[str, str, str],
            tuple[str | None, str | None, int],
        ] = {}
        for candidate in candidates:
            if candidate.validation_state != "UNDEFINED":
                continue
            key = (
                candidate.source_type,
                candidate.relation_type,
                candidate.target_type,
            )
            current = aggregated.get(key)
            if current is None:
                aggregated[key] = (
                    candidate.source_label,
                    candidate.target_label,
                    1,
                )
                continue
            aggregated[key] = (current[0], current[1], current[2] + 1)

        patterns = [
            UnknownRelationPattern(
                source_type=source_type,
                relation_type=relation_type,
                target_type=target_type,
                source_label_example=source_label,
                target_label_example=target_label,
                occurrences=count,
            )
            for (source_type, relation_type, target_type), (
                source_label,
                target_label,
                count,
            ) in aggregated.items()
        ]
        return tuple(patterns)

    def _build_constraints_snapshot(
        self,
        unknown_patterns: tuple[UnknownRelationPattern, ...],
    ) -> tuple[JSONObject, ...]:
        if self._dictionary is None:
            return ()

        snapshot: list[JSONObject] = []
        seen_keys: set[tuple[str, str, str, str, bool, bool, bool]] = set()
        for pattern in unknown_patterns:
            constraints = self._dictionary.get_constraints(
                source_type=pattern.source_type,
                relation_type=pattern.relation_type,
                include_inactive=True,
            )
            for constraint in constraints:
                key = (
                    constraint.source_type,
                    constraint.relation_type,
                    constraint.target_type,
                    constraint.review_status,
                    bool(constraint.is_allowed),
                    bool(constraint.requires_evidence),
                    bool(constraint.is_active),
                )
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                snapshot.append(
                    {
                        "source_type": constraint.source_type,
                        "relation_type": constraint.relation_type,
                        "target_type": constraint.target_type,
                        "review_status": constraint.review_status,
                        "is_allowed": constraint.is_allowed,
                        "requires_evidence": constraint.requires_evidence,
                        "is_active": constraint.is_active,
                    },
                )
        return tuple(snapshot)

    def _list_active_relation_types(self) -> tuple[str, ...]:
        if self._dictionary is None:
            return ()

        relation_types = []
        for relation_type in self._dictionary.list_relation_types(
            include_inactive=False,
        ):
            if not relation_type.is_active:
                continue
            if relation_type.review_status != "ACTIVE":
                continue
            normalized = relation_type.id.strip().upper()
            if not normalized or normalized in relation_types:
                continue
            relation_types.append(normalized)
        return tuple(relation_types)

    @staticmethod
    def _resolve_relation_governance_mode(
        settings: ResearchSpaceSettings | None,
    ) -> RelationGovernanceMode:
        if settings is None:
            return "HUMAN_IN_LOOP"
        raw_mode = settings.get("relation_governance_mode")
        if isinstance(raw_mode, str):
            normalized = raw_mode.strip().upper()
            if normalized == "FULL_AUTO":
                return "FULL_AUTO"
        return "HUMAN_IN_LOOP"

    def _resolve_relation_validation_state(
        self,
        *,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> tuple[RelationValidationState, str]:
        if self._dictionary is None:
            return "UNDEFINED", "dictionary_service_unavailable"

        constraints = self._dictionary.get_constraints(
            source_type=source_type,
            relation_type=relation_type,
            include_inactive=True,
        )
        matching = [
            constraint
            for constraint in constraints
            if constraint.target_type == target_type
        ]
        if not matching:
            return "UNDEFINED", "constraint_not_defined"

        active_constraints = [
            constraint
            for constraint in matching
            if constraint.is_active and constraint.review_status == "ACTIVE"
        ]
        if active_constraints:
            has_forbidden_profile = any(
                getattr(c, "profile", "ALLOWED") == "FORBIDDEN"
                for c in active_constraints
            )
            if has_forbidden_profile or not any(
                c.is_allowed for c in active_constraints
            ):
                reason = (
                    "forbidden_by_profile"
                    if has_forbidden_profile
                    else "forbidden_by_active_constraint"
                )
                return "FORBIDDEN", reason
            return "ALLOWED", "allowed_by_active_constraint"

        if any(
            constraint.is_active and constraint.review_status == "PENDING_REVIEW"
            for constraint in matching
        ):
            return "UNDEFINED", "constraint_pending_review"
        return "UNDEFINED", "constraint_inactive_or_revoked"

    def _resolve_constraint_profile(
        self,
        *,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> str:
        """Return the governance profile for a constraint triple.

        Returns ``"EXPECTED"``, ``"REVIEW_ONLY"``, or ``"ALLOWED"`` (default).
        If the constraint is not found or the dictionary is unavailable,
        returns ``"ALLOWED"``.
        """
        if self._dictionary is None:
            return "ALLOWED"

        constraints = self._dictionary.get_constraints(
            source_type=source_type,
            relation_type=relation_type,
            include_inactive=False,
        )
        for constraint in constraints:
            if constraint.target_type == target_type:
                return constraint.profile or "ALLOWED"
        return "ALLOWED"

    def _build_relation_evidence_summary(
        self,
        *,
        document: SourceDocument,
        candidate: _ResolvedRelationCandidate,
        relation_governance_mode: RelationGovernanceMode,
        constraint_proposal: RelationConstraintProposal | None,
        mapping_proposal: RelationTypeMappingProposal | None,
    ) -> str:
        parts = [f"Extracted from source_document:{document.id}"]
        if (
            relation_governance_mode == "FULL_AUTO"
            and candidate.validation_state != "ALLOWED"
        ):
            parts.append(
                (
                    "governance_override:"
                    f"{candidate.validation_state.lower()}:"
                    f"{candidate.validation_reason}"
                ),
            )
        if candidate.validation_state == "UNDEFINED":
            parts.append(f"validation:{candidate.validation_reason}")
            if constraint_proposal is not None:
                parts.append(
                    (
                        "constraint_proposal:"
                        f"allowed={constraint_proposal.proposed_is_allowed},"
                        f"requires_evidence={constraint_proposal.proposed_requires_evidence}"
                    ),
                )
            if mapping_proposal is not None:
                parts.append(
                    (
                        "mapping_proposal:"
                        f"{mapping_proposal.observed_relation_type}"
                        f"->{mapping_proposal.mapped_relation_type}"
                    ),
                )
        return " | ".join(parts)

    def _index_constraint_proposals(
        self,
        policy_contract: ExtractionPolicyContract | None,
    ) -> dict[tuple[str, str, str], RelationConstraintProposal]:
        return index_constraint_proposals(
            policy_contract=policy_contract,
            proposal_triple_key=self._proposal_triple_key,
        )

    def _index_mapping_proposals(
        self,
        policy_contract: ExtractionPolicyContract | None,
    ) -> dict[tuple[str, str, str], RelationTypeMappingProposal]:
        return index_mapping_proposals(
            policy_contract=policy_contract,
            proposal_triple_key=self._proposal_triple_key,
        )

    def _proposal_triple_key(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> tuple[str, str, str] | None:
        normalized_source = self._normalize_component(source_type)
        normalized_relation = self._normalize_component(relation_type)
        normalized_target = self._normalize_component(target_type)
        if not normalized_source or not normalized_relation or not normalized_target:
            return None
        return normalized_source, normalized_relation, normalized_target

    def _record_rejected_relation(
        self,
        *,
        reasons: list[str],
        details: list[JSONObject],
        reason: str,
        payload: JSONObject,
        metadata: JSONObject | None = None,
    ) -> None:
        record_rejected_relation(
            reasons=reasons,
            details=details,
            reason=reason,
            payload=payload,
            metadata=metadata,
        )

    @staticmethod
    def _merge_unique_reasons(
        first: tuple[str, ...],
        second: tuple[str, ...],
    ) -> tuple[str, ...]:
        return merge_unique_reasons(first, second)

    def _enqueue_review_item(
        self,
        *,
        entity_type: str,
        entity_id: str,
        research_space_id: str | None,
        priority: str,
    ) -> None:
        submitter = self._review_queue_submitter
        if submitter is None:
            return
        try:
            submitter(entity_type, entity_id, research_space_id, priority)
        except Exception as exc:  # noqa: BLE001 - never block extraction on queue write
            logger.warning(
                "Failed to enqueue review item entity_type=%s entity_id=%s: %s",
                entity_type,
                entity_id,
                exc,
            )

    @staticmethod
    def _normalize_component(raw_value: str) -> str:
        msg = "subclass must implement _normalize_component"
        raise NotImplementedError(msg)

    @staticmethod
    def _normalize_run_id(run_id: str | None) -> str | None:
        msg = "subclass must implement _normalize_run_id"
        raise NotImplementedError(msg)


__all__ = [
    "RelationPersistability",
    "RelationGovernanceMode",
    "_ExtractionRelationPolicyHelpers",
    "_ResolvedRelationCandidate",
]
