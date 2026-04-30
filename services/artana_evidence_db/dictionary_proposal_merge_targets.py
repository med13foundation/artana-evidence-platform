"""Merge-target resolution for dictionary proposal reviews."""

from __future__ import annotations

from artana_evidence_db.dictionary_proposal_support import normalize_required_text
from artana_evidence_db.kernel_dictionary_models import DictionaryProposalModel
from artana_evidence_db.semantic_ports import DictionaryPort


class DictionaryProposalMergeTargetResolver:
    """Resolve reviewed proposals onto existing dictionary records."""

    def __init__(self, dictionary_service: DictionaryPort) -> None:
        self._dictionary = dictionary_service

    def resolve(
        self,
        model: DictionaryProposalModel,
        *,
        target_id: str,
    ) -> tuple[str, str]:
        normalized_target_id = normalize_required_text(
            target_id,
            field_name="target_id",
        )
        merge_target = self._resolve_by_type(
            model,
            normalized_target_id=normalized_target_id,
        )
        if merge_target is None:
            msg = f"Unsupported proposal type '{model.proposal_type}'"
            raise ValueError(msg)
        return merge_target

    def _resolve_by_type(
        self,
        model: DictionaryProposalModel,
        *,
        normalized_target_id: str,
    ) -> tuple[str, str] | None:
        merge_target: tuple[str, str] | None = None
        if model.proposal_type == "DOMAIN_CONTEXT":
            merge_target = self._resolve_domain_context(normalized_target_id)
        elif model.proposal_type == "ENTITY_TYPE":
            merge_target = self._resolve_entity_type(normalized_target_id)
        elif model.proposal_type == "VARIABLE":
            merge_target = self._resolve_variable(normalized_target_id)
        elif model.proposal_type == "RELATION_TYPE":
            merge_target = self._resolve_relation_type(normalized_target_id)
        elif model.proposal_type == "VALUE_SET":
            merge_target = self._resolve_value_set(normalized_target_id)
        elif model.proposal_type == "RELATION_CONSTRAINT":
            merge_target = self._resolve_relation_constraint(
                model,
                normalized_target_id=normalized_target_id,
            )
        elif model.proposal_type == "RELATION_SYNONYM":
            merge_target = self._resolve_relation_synonym(
                model,
                normalized_target_id=normalized_target_id,
            )
        elif model.proposal_type == "VALUE_SET_ITEM":
            merge_target = self._resolve_value_set_item(
                model,
                normalized_target_id=normalized_target_id,
            )
        return merge_target

    def _resolve_domain_context(self, normalized_target_id: str) -> tuple[str, str]:
        contexts = self._dictionary.list_domain_contexts(include_inactive=True)
        if not any(context.id == normalized_target_id for context in contexts):
            msg = f"Domain context '{normalized_target_id}' not found"
            raise ValueError(msg)
        return "DOMAIN_CONTEXT", normalized_target_id

    def _resolve_entity_type(self, normalized_target_id: str) -> tuple[str, str]:
        if (
            self._dictionary.get_entity_type(
                normalized_target_id,
                include_inactive=True,
            )
            is None
        ):
            msg = f"Entity type '{normalized_target_id}' not found"
            raise ValueError(msg)
        return "ENTITY_TYPE", normalized_target_id

    def _resolve_variable(self, normalized_target_id: str) -> tuple[str, str]:
        if self._dictionary.get_variable(normalized_target_id) is None:
            msg = f"Variable '{normalized_target_id}' not found"
            raise ValueError(msg)
        return "VARIABLE", normalized_target_id

    def _resolve_relation_type(self, normalized_target_id: str) -> tuple[str, str]:
        if (
            self._dictionary.get_relation_type(
                normalized_target_id,
                include_inactive=True,
            )
            is None
        ):
            msg = f"Relation type '{normalized_target_id}' not found"
            raise ValueError(msg)
        return "RELATION_TYPE", normalized_target_id

    def _resolve_relation_constraint(
        self,
        model: DictionaryProposalModel,
        *,
        normalized_target_id: str,
    ) -> tuple[str, str]:
        try:
            constraint_id = int(normalized_target_id)
        except ValueError as exc:
            msg = "target_id must be a numeric relation constraint id"
            raise ValueError(msg) from exc
        constraints = self._dictionary.get_constraints(
            source_type=model.source_type,
            relation_type=model.relation_type,
            include_inactive=False,
        )
        if not any(
            constraint.id == constraint_id and constraint.target_type == model.target_type
            for constraint in constraints
        ):
            msg = f"Relation constraint '{constraint_id}' not found"
            raise ValueError(msg)
        return "RELATION_CONSTRAINT", str(constraint_id)

    def _resolve_relation_synonym(
        self,
        model: DictionaryProposalModel,
        *,
        normalized_target_id: str,
    ) -> tuple[str, str]:
        try:
            synonym_id = int(normalized_target_id)
        except ValueError as exc:
            msg = "target_id must be a numeric relation synonym id"
            raise ValueError(msg) from exc
        synonyms = self._dictionary.list_relation_synonyms(
            relation_type_id=model.relation_type,
            include_inactive=True,
        )
        if not any(synonym.id == synonym_id for synonym in synonyms):
            msg = f"Relation synonym '{synonym_id}' not found"
            raise ValueError(msg)
        return "RELATION_SYNONYM", str(synonym_id)

    def _resolve_value_set(self, normalized_target_id: str) -> tuple[str, str]:
        if self._dictionary.get_value_set(normalized_target_id) is None:
            msg = f"Value set '{normalized_target_id}' not found"
            raise ValueError(msg)
        return "VALUE_SET", normalized_target_id

    def _resolve_value_set_item(
        self,
        model: DictionaryProposalModel,
        *,
        normalized_target_id: str,
    ) -> tuple[str, str]:
        try:
            value_set_item_id = int(normalized_target_id)
        except ValueError as exc:
            msg = "target_id must be a numeric value-set item id"
            raise ValueError(msg) from exc
        items = self._dictionary.list_value_set_items(
            value_set_id=model.value_set_id or "",
            include_inactive=True,
        )
        if not any(item.id == value_set_item_id for item in items):
            msg = f"Value-set item '{value_set_item_id}' not found"
            raise ValueError(msg)
        return "VALUE_SET_ITEM", str(value_set_item_id)


__all__ = ["DictionaryProposalMergeTargetResolver"]
