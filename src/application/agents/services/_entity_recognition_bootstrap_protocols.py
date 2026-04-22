"""Protocols for entity recognition bootstrap helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from artana_evidence_db.semantic_ports import DictionaryPort

    from src.domain.agents.graph_domain_ai_contracts import (
        EntityRecognitionBootstrapConfig,
    )
    from src.type_definitions.common import JSONValue, ResearchSpaceSettings


class _EntityRecognitionBootstrapContext(Protocol):
    """Structural typing contract consumed by bootstrap helper methods."""

    _dictionary: DictionaryPort
    _agent_created_by: str
    _entity_recognition_bootstrap: EntityRecognitionBootstrapConfig

    @staticmethod
    def _infer_domain_context(source_type: str) -> str: ...

    @staticmethod
    def _to_display_name(field_name: str) -> str: ...

    @staticmethod
    def _normalize_identifier(
        value: str,
        *,
        prefix: str,
        max_length: int,
    ) -> str: ...

    @staticmethod
    def _is_domain_bootstrap_enabled(settings: ResearchSpaceSettings) -> bool: ...

    def _bootstrap_entity_types_for_domain(
        self,
        domain_context: str,
    ) -> tuple[str, ...]: ...

    @staticmethod
    def _bootstrap_review_settings(
        settings: ResearchSpaceSettings,
    ) -> ResearchSpaceSettings: ...

    def _bootstrap_variable_id(self, domain_context: str) -> str: ...

    def _ensure_relation_constraint(
        self,
        *,
        source_type: str,
        target_type: str,
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
    ) -> None: ...

    def _ensure_relation_constraint_for_type(
        self,
        *,
        relation_triplet: tuple[str, str, str],
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
        requires_evidence: bool = True,
    ) -> None: ...

    def _ensure_publication_baseline(
        self,
        *,
        domain_context: str,
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
    ) -> tuple[int, int]: ...

    def _ensure_publication_metadata_variable(  # noqa: PLR0913
        self,
        *,
        variable_id: str,
        canonical_name: str,
        display_name: str,
        data_type: str,
        description: str,
        constraints: dict[str, JSONValue] | None,
        synonyms: tuple[str, ...],
        domain_context: str,
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
    ) -> int: ...

    def _ensure_variable_synonyms(
        self,
        *,
        variable_id: str,
        synonyms: tuple[str, ...],
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
    ) -> None: ...

    def _activate_bootstrap_entity_type_if_needed(
        self,
        *,
        entity_type: str,
    ) -> None: ...

    def _activate_bootstrap_relation_type_if_needed(
        self,
        *,
        relation_type: str,
    ) -> None: ...


__all__ = ["_EntityRecognitionBootstrapContext"]
