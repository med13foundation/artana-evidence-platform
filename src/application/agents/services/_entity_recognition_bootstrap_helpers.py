"""Cold-start dictionary bootstrap helpers for entity-recognition orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.services.domain_context_resolver import DomainContextResolver

if TYPE_CHECKING:
    from src.application.agents.services._entity_recognition_bootstrap_protocols import (
        _EntityRecognitionBootstrapContext,
    )
    from src.type_definitions.common import JSONValue, ResearchSpaceSettings


class _EntityRecognitionBootstrapHelpers:
    """Mixin with domain cold-start bootstrap support."""

    def _ensure_domain_bootstrap(  # noqa: PLR0913, C901
        self: _EntityRecognitionBootstrapContext,
        *,
        source_type: str,
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
    ) -> tuple[int, int]:
        if not self._is_domain_bootstrap_enabled(research_space_settings):
            return 0, 0

        bootstrap_review_settings = self._bootstrap_review_settings(
            research_space_settings,
        )
        bootstrap_config = self._entity_recognition_bootstrap
        domain_context = self._infer_domain_context(source_type)
        has_existing_entries = bool(
            self._dictionary.dictionary_search_by_domain(
                domain_context=domain_context,
                limit=1,
                include_inactive=False,
            ),
        )
        created_entity_types = 0
        entity_types = self._bootstrap_entity_types_for_domain(domain_context)
        if not has_existing_entries:
            for entity_type_id in entity_types:
                if self._dictionary.get_entity_type(entity_type_id) is not None:
                    continue
                self._dictionary.create_entity_type(
                    entity_type=entity_type_id,
                    display_name=self._to_display_name(entity_type_id),
                    description=(
                        f"Bootstrap entity type for domain '{domain_context}' "
                        f"generated from source type '{source_type}'."
                    ),
                    domain_context=domain_context,
                    created_by=self._agent_created_by,
                    source_ref=source_ref,
                    research_space_settings=bootstrap_review_settings,
                )
                created_entity_types += 1

        bootstrap_variable_id = self._bootstrap_variable_id(domain_context)
        created_variables = 0
        if (
            not has_existing_entries
            and self._dictionary.get_variable(bootstrap_variable_id) is None
        ):
            self._dictionary.create_variable(
                variable_id=bootstrap_variable_id,
                canonical_name=f"{domain_context}_evidence_signal",
                display_name=f"{self._to_display_name(domain_context)} Evidence Signal",
                data_type="STRING",
                domain_context=domain_context,
                sensitivity="INTERNAL",
                description=(
                    f"Bootstrap variable for domain '{domain_context}' used to "
                    "establish minimal dictionary coverage."
                ),
                created_by=self._agent_created_by,
                source_ref=source_ref,
                research_space_settings=bootstrap_review_settings,
            )
            created_variables += 1

        if not has_existing_entries:
            if (
                self._dictionary.get_relation_type(
                    bootstrap_config.default_relation_type,
                )
                is None
            ):
                self._dictionary.create_relation_type(
                    relation_type=bootstrap_config.default_relation_type,
                    display_name=bootstrap_config.default_relation_display_name,
                    description=bootstrap_config.default_relation_description,
                    domain_context=domain_context,
                    is_directional=True,
                    inverse_label=bootstrap_config.default_relation_inverse_label,
                    created_by=self._agent_created_by,
                    source_ref=source_ref,
                    research_space_settings=bootstrap_review_settings,
                )
            if (
                self._dictionary.get_relation_type(
                    bootstrap_config.interaction_relation_type,
                )
                is None
            ):
                self._dictionary.create_relation_type(
                    relation_type=bootstrap_config.interaction_relation_type,
                    display_name=bootstrap_config.interaction_relation_display_name,
                    description=bootstrap_config.interaction_relation_description,
                    domain_context=domain_context,
                    is_directional=False,
                    inverse_label=bootstrap_config.interaction_relation_inverse_label,
                    created_by=self._agent_created_by,
                    source_ref=source_ref,
                    research_space_settings=bootstrap_review_settings,
                )

            if (
                len(entity_types)
                >= bootstrap_config.min_entity_types_for_default_relation
            ):
                self._ensure_relation_constraint(
                    source_type=entity_types[0],
                    target_type=entity_types[1],
                    source_ref=source_ref,
                    research_space_settings=bootstrap_review_settings,
                )

            for interaction_entity_type in bootstrap_config.interaction_entity_types:
                if self._dictionary.get_entity_type(interaction_entity_type) is None:
                    self._dictionary.create_entity_type(
                        entity_type=interaction_entity_type,
                        display_name=self._to_display_name(interaction_entity_type),
                        description=(
                            "Bootstrap molecular entity type used for interaction "
                            "relation constraints."
                        ),
                        domain_context=domain_context,
                        created_by=self._agent_created_by,
                        source_ref=source_ref,
                        research_space_settings=bootstrap_review_settings,
                    )
                    created_entity_types += 1

            self._ensure_relation_constraint_for_type(
                relation_triplet=(
                    "GENE",
                    bootstrap_config.interaction_relation_type,
                    "GENE",
                ),
                source_ref=source_ref,
                research_space_settings=bootstrap_review_settings,
            )
            self._ensure_relation_constraint_for_type(
                relation_triplet=(
                    "PROTEIN",
                    bootstrap_config.interaction_relation_type,
                    "PROTEIN",
                ),
                source_ref=source_ref,
                research_space_settings=bootstrap_review_settings,
            )

        normalized_source_type = DomainContextResolver.normalize(source_type)
        if (
            normalized_source_type is not None
            and normalized_source_type
            in bootstrap_config.source_types_with_publication_baseline
        ):
            (
                publication_entity_types_created,
                publication_variables_created,
            ) = self._ensure_publication_baseline(
                domain_context=domain_context,
                source_ref=source_ref,
                research_space_settings=bootstrap_review_settings,
            )
            created_entity_types += publication_entity_types_created
            created_variables += publication_variables_created

        return created_variables, created_entity_types

    def _ensure_relation_constraint(
        self: _EntityRecognitionBootstrapContext,
        *,
        source_type: str,
        target_type: str,
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
    ) -> None:
        self._activate_bootstrap_entity_type_if_needed(entity_type=source_type)
        self._activate_bootstrap_relation_type_if_needed(
            relation_type=self._entity_recognition_bootstrap.default_relation_type,
        )
        self._activate_bootstrap_entity_type_if_needed(entity_type=target_type)
        self._dictionary.create_relation_constraint(
            source_type=source_type,
            relation_type=self._entity_recognition_bootstrap.default_relation_type,
            target_type=target_type,
            is_allowed=True,
            requires_evidence=True,
            created_by=self._agent_created_by,
            source_ref=source_ref,
            research_space_settings=research_space_settings,
        )

    def _ensure_relation_constraint_for_type(
        self: _EntityRecognitionBootstrapContext,
        *,
        relation_triplet: tuple[str, str, str],
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
        requires_evidence: bool = True,
    ) -> None:
        source_type, relation_type, target_type = relation_triplet
        self._activate_bootstrap_entity_type_if_needed(entity_type=source_type)
        self._activate_bootstrap_relation_type_if_needed(relation_type=relation_type)
        self._activate_bootstrap_entity_type_if_needed(entity_type=target_type)
        self._dictionary.create_relation_constraint(
            source_type=source_type,
            relation_type=relation_type,
            target_type=target_type,
            is_allowed=True,
            requires_evidence=requires_evidence,
            created_by=self._agent_created_by,
            source_ref=source_ref,
            research_space_settings=research_space_settings,
        )

    def _ensure_publication_baseline(
        self: _EntityRecognitionBootstrapContext,
        *,
        domain_context: str,
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
    ) -> tuple[int, int]:
        created_entity_types = 0
        created_variables = 0
        bootstrap_config = self._entity_recognition_bootstrap

        for entity_type_id in bootstrap_config.publication_baseline_entity_types:
            if self._dictionary.get_entity_type(entity_type_id) is not None:
                continue
            self._dictionary.create_entity_type(
                entity_type=entity_type_id,
                display_name=self._to_display_name(entity_type_id),
                description=bootstrap_config.publication_baseline_entity_description,
                domain_context=domain_context,
                created_by=self._agent_created_by,
                source_ref=source_ref,
                research_space_settings=research_space_settings,
            )
            created_entity_types += 1

        for relation_definition in bootstrap_config.publication_baseline_relation_types:
            if (
                self._dictionary.get_relation_type(relation_definition.relation_type)
                is not None
            ):
                continue
            self._dictionary.create_relation_type(
                relation_type=relation_definition.relation_type,
                display_name=relation_definition.display_name,
                description=relation_definition.description,
                domain_context=domain_context,
                is_directional=relation_definition.is_directional,
                inverse_label=relation_definition.inverse_label,
                created_by=self._agent_created_by,
                source_ref=source_ref,
                research_space_settings=research_space_settings,
            )

        for constraint_definition in bootstrap_config.publication_baseline_constraints:
            self._ensure_relation_constraint_for_type(
                relation_triplet=(
                    constraint_definition.source_type,
                    constraint_definition.relation_type,
                    constraint_definition.target_type,
                ),
                requires_evidence=constraint_definition.requires_evidence,
                source_ref=source_ref,
                research_space_settings=research_space_settings,
            )

        for variable_definition in bootstrap_config.publication_metadata_variables:
            created_variables += self._ensure_publication_metadata_variable(
                variable_id=variable_definition.variable_id,
                canonical_name=variable_definition.canonical_name,
                display_name=variable_definition.display_name,
                data_type=variable_definition.data_type,
                description=variable_definition.description,
                constraints=variable_definition.constraints,
                synonyms=variable_definition.synonyms,
                domain_context=domain_context,
                source_ref=source_ref,
                research_space_settings=research_space_settings,
            )

        return created_entity_types, created_variables

    def _activate_bootstrap_entity_type_if_needed(
        self: _EntityRecognitionBootstrapContext,
        *,
        entity_type: str,
    ) -> None:
        existing = self._dictionary.get_entity_type(
            entity_type,
            include_inactive=True,
        )
        if existing is None:
            return
        if existing.is_active and existing.review_status == "ACTIVE":
            return
        self._dictionary.set_entity_type_review_status(
            entity_type,
            review_status="ACTIVE",
            reviewed_by=self._agent_created_by,
        )

    def _activate_bootstrap_relation_type_if_needed(
        self: _EntityRecognitionBootstrapContext,
        *,
        relation_type: str,
    ) -> None:
        existing = self._dictionary.get_relation_type(
            relation_type,
            include_inactive=True,
        )
        if existing is None:
            return
        if existing.is_active and existing.review_status == "ACTIVE":
            return
        self._dictionary.set_relation_type_review_status(
            relation_type,
            review_status="ACTIVE",
            reviewed_by=self._agent_created_by,
        )

    def _ensure_publication_metadata_variable(  # noqa: PLR0913
        self: _EntityRecognitionBootstrapContext,
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
    ) -> int:
        variable = self._dictionary.get_variable(variable_id)
        if variable is None:
            for synonym in synonyms:
                resolved = self._dictionary.resolve_synonym(synonym)
                if resolved is not None:
                    variable = resolved
                    break

        created_variables = 0
        if variable is None:
            variable = self._dictionary.create_variable(
                variable_id=variable_id,
                canonical_name=canonical_name,
                display_name=display_name,
                data_type=data_type,
                domain_context=domain_context,
                sensitivity="PUBLIC",
                constraints=constraints,
                description=description,
                created_by=self._agent_created_by,
                source_ref=source_ref,
                research_space_settings=research_space_settings,
            )
            created_variables = 1

        self._ensure_variable_synonyms(
            variable_id=variable.id,
            synonyms=synonyms,
            source_ref=source_ref,
            research_space_settings=research_space_settings,
        )
        return created_variables

    def _ensure_variable_synonyms(
        self: _EntityRecognitionBootstrapContext,
        *,
        variable_id: str,
        synonyms: tuple[str, ...],
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
    ) -> None:
        for synonym in synonyms:
            resolved = self._dictionary.resolve_synonym(synonym)
            if resolved is not None:
                continue
            self._dictionary.create_synonym(
                variable_id=variable_id,
                synonym=synonym,
                source=self._entity_recognition_bootstrap.publication_baseline_source_label,
                created_by=self._agent_created_by,
                source_ref=source_ref,
                research_space_settings=research_space_settings,
            )

    def _bootstrap_entity_types_for_domain(
        self: _EntityRecognitionBootstrapContext,
        domain_context: str,
    ) -> tuple[str, ...]:
        normalized = domain_context.strip().lower()
        bootstrap_config = self._entity_recognition_bootstrap
        for definition in bootstrap_config.domain_entity_types:
            if definition.domain_context == normalized:
                return definition.entity_types
        for definition in bootstrap_config.domain_entity_types:
            if definition.domain_context == "general":
                return definition.entity_types
        return ()

    def _bootstrap_variable_id(
        self: _EntityRecognitionBootstrapContext,
        domain_context: str,
    ) -> str:
        normalized = self._normalize_identifier(
            domain_context,
            prefix="GENERAL",
            max_length=48,
        )
        return f"VAR_{normalized}_EVIDENCE_SIGNAL"[:64]

    @staticmethod
    def _bootstrap_review_settings(  # noqa: C901, PLR0912
        settings: ResearchSpaceSettings,
    ) -> ResearchSpaceSettings:
        normalized: ResearchSpaceSettings = {}
        if "auto_approve" in settings:
            normalized["auto_approve"] = settings["auto_approve"]
        if "require_review" in settings:
            normalized["require_review"] = settings["require_review"]
        if "review_threshold" in settings:
            normalized["review_threshold"] = settings["review_threshold"]
        if "relation_default_review_threshold" in settings:
            normalized["relation_default_review_threshold"] = settings[
                "relation_default_review_threshold"
            ]
        relation_governance_mode = settings.get("relation_governance_mode")
        if relation_governance_mode in {"HUMAN_IN_LOOP", "FULL_AUTO"}:
            normalized["relation_governance_mode"] = relation_governance_mode
        relation_review_thresholds = settings.get("relation_review_thresholds")
        if isinstance(relation_review_thresholds, dict):
            normalized["relation_review_thresholds"] = dict(relation_review_thresholds)
        if "max_data_sources" in settings:
            normalized["max_data_sources"] = settings["max_data_sources"]
        if "allowed_source_types" in settings:
            normalized["allowed_source_types"] = settings["allowed_source_types"]
        if "public_read" in settings:
            normalized["public_read"] = settings["public_read"]
        if "allow_invites" in settings:
            normalized["allow_invites"] = settings["allow_invites"]
        if "email_notifications" in settings:
            normalized["email_notifications"] = settings["email_notifications"]
        if "notification_frequency" in settings:
            normalized["notification_frequency"] = settings["notification_frequency"]
        if "custom" in settings and isinstance(settings["custom"], dict):
            normalized["custom"] = dict(settings["custom"])
        # Bootstrap entries are required for immediate kernel writes in the same run.
        # Keep them ACTIVE regardless of space-level agent-creation policy so
        # dictionary hard guarantees and runtime ingestion remain compatible.
        normalized["dictionary_agent_creation_policy"] = "ACTIVE"
        return normalized

    @staticmethod
    def _is_domain_bootstrap_enabled(settings: ResearchSpaceSettings) -> bool:
        custom = settings.get("custom")
        if isinstance(custom, dict):
            explicit = custom.get("dictionary_cold_start_bootstrap")
            if isinstance(explicit, bool):
                return explicit
        return True


__all__ = ["_EntityRecognitionBootstrapHelpers"]
