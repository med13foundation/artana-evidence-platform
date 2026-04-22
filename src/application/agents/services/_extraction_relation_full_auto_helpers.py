"""Full-auto relation candidate resolution helpers."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Protocol

from src.domain.value_objects.relation_types import normalize_relation_type

if TYPE_CHECKING:
    from src.application.agents.services._extraction_relation_policy_helpers import (
        RelationValidationState,
        _ResolvedRelationCandidate,
    )
    from src.domain.agents.contracts.extraction_policy import (
        RelationTypeMappingProposal,
    )


class _FullAutoResolutionSelf(Protocol):
    def _resolve_relation_validation_state(
        self,
        *,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> tuple[RelationValidationState, str]: ...

    def _ensure_full_auto_allowed_constraint(
        self,
        *,
        source_type: str,
        relation_type: str,
        target_type: str,
        source_ref: str,
    ) -> tuple[bool, str]: ...


class _ExtractionRelationFullAutoHelpers:
    _COMPONENT_ALIAS_MAP: dict[str, str] = {
        "PUBMED": "PUBLICATION",
        "PMID": "PUBLICATION",
        "ARTICLE": "PUBLICATION",
        "PAPER": "PUBLICATION",
        "STUDY": "PUBLICATION",
    }

    def _resolve_full_auto_candidate(
        self: _FullAutoResolutionSelf,
        *,
        candidate: _ResolvedRelationCandidate,
        mapping_proposal: RelationTypeMappingProposal | None,
        source_ref: str,
    ) -> _ResolvedRelationCandidate:
        working_candidate = candidate

        mapped_relation_type = (
            normalize_relation_type(mapping_proposal.mapped_relation_type)
            if mapping_proposal is not None
            else ""
        )
        if mapped_relation_type and mapped_relation_type != candidate.relation_type:
            mapped_state, mapped_reason = self._resolve_relation_validation_state(
                source_type=candidate.source_type,
                relation_type=mapped_relation_type,
                target_type=candidate.target_type,
            )
            working_candidate = replace(
                candidate,
                relation_type=mapped_relation_type,
                validation_state=mapped_state,
                validation_reason=(
                    "mapped_to_existing_relation_type"
                    if mapped_state == "ALLOWED"
                    else mapped_reason
                ),
            )
            if mapped_state != "UNDEFINED":
                return working_candidate

        created, creation_reason = self._ensure_full_auto_allowed_constraint(
            source_type=working_candidate.source_type,
            relation_type=working_candidate.relation_type,
            target_type=working_candidate.target_type,
            source_ref=source_ref,
        )
        if not created:
            return replace(
                working_candidate,
                validation_state="UNDEFINED",
                validation_reason=creation_reason,
            )

        refreshed_state, refreshed_reason = self._resolve_relation_validation_state(
            source_type=working_candidate.source_type,
            relation_type=working_candidate.relation_type,
            target_type=working_candidate.target_type,
        )
        return replace(
            working_candidate,
            validation_state=refreshed_state,
            validation_reason=refreshed_reason,
        )

    @staticmethod
    def _normalize_component(raw_value: str) -> str:
        normalized = raw_value.strip().upper()
        return _ExtractionRelationFullAutoHelpers._COMPONENT_ALIAS_MAP.get(
            normalized,
            normalized,
        )
