"""Application service for graph-kernel entities."""

from __future__ import annotations

import logging
from typing import Protocol

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.dictionary_models import EntityResolutionPolicy
from artana_evidence_db.entity_resolution import normalize_entity_alias_labels
from artana_evidence_db.graph_core_models import KernelEntity, KernelEntityIdentifier
from artana_evidence_db.kernel_entity_errors import (
    KernelEntityConflictError,
    KernelEntityValidationError,
)
from artana_evidence_db.read_model_support import (
    ENTITY_EMBEDDING_STATUS_READ_MODEL,
    GraphReadModelTrigger,
    GraphReadModelUpdate,
    GraphReadModelUpdateDispatcher,
    NullGraphReadModelUpdateDispatcher,
)

logger = logging.getLogger(__name__)


def _normalize_entity_type(entity_type: str) -> str:
    normalized = entity_type.strip().upper()
    return normalized.replace("-", "_").replace("/", "_").replace(" ", "_")


class EntityRepositoryLike(Protocol):
    """Minimal entity repository surface required by the entity service."""

    def create(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        display_label: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelEntity: ...

    def get_by_id(self, entity_id: str) -> KernelEntity | None: ...

    def update(
        self,
        entity_id: str,
        *,
        display_label: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelEntity | None: ...

    def find_by_type(
        self,
        research_space_id: str,
        entity_type: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelEntity]: ...

    def search(
        self,
        research_space_id: str,
        query: str,
        *,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[KernelEntity]: ...

    def count_by_type(self, research_space_id: str) -> dict[str, int]: ...

    def delete(self, entity_id: str) -> bool: ...

    def add_identifier(
        self,
        *,
        entity_id: str,
        namespace: str,
        identifier_value: str,
        sensitivity: str = "INTERNAL",
    ) -> KernelEntityIdentifier: ...

    def add_alias(
        self,
        *,
        entity_id: str,
        alias_label: str,
        source: str,
    ) -> object: ...

    def resolve_candidates(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        identifiers: dict[str, str],
    ) -> list[KernelEntity]: ...

    def find_display_label_candidates(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        display_label: str,
    ) -> list[KernelEntity]: ...

    def find_alias_candidates(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        alias_label: str,
    ) -> list[KernelEntity]: ...


class DictionaryRepositoryLike(Protocol):
    """Minimal dictionary repository surface required by the entity service."""

    def get_resolution_policy(self, entity_type: str) -> EntityResolutionPolicy | None:
        """Return the active resolution policy for one entity type."""


class KernelEntityService:
    """
    Application service for kernel entities.

    Combines entity CRUD with resolution-policy enforcement.
    """

    def __init__(
        self,
        entity_repo: EntityRepositoryLike,
        dictionary_repo: DictionaryRepositoryLike,
        read_model_update_dispatcher: GraphReadModelUpdateDispatcher | None = None,
    ) -> None:
        self._entities = entity_repo
        self._dictionary = dictionary_repo
        self._read_model_update_dispatcher = (
            read_model_update_dispatcher or NullGraphReadModelUpdateDispatcher()
        )

    def create_or_resolve(  # noqa: C901, PLR0912, PLR0913
        self,
        *,
        research_space_id: str,
        entity_type: str,
        identifiers: dict[str, str] | None = None,
        display_label: str | None = None,
        aliases: list[str] | None = None,
        metadata: JSONObject | None = None,
        skip_conflicting_aliases: bool = False,
    ) -> tuple[KernelEntity, bool]:
        """
        Create an entity or return existing match.

        Uses the entity resolution policy to determine dedup strategy.
        Returns (entity, created) where ``created`` is False if resolved.
        """
        normalized_entity_type = _normalize_entity_type(entity_type)
        policy = self._dictionary.get_resolution_policy(normalized_entity_type)
        if policy is None:
            msg = (
                f"Unknown entity_type '{normalized_entity_type}'. "
                "Add an entity resolution policy before creating this type."
            )
            raise ValueError(msg)

        normalized_aliases = normalize_entity_alias_labels(
            alias
            for alias in [display_label or "", *(aliases or [])]
            if isinstance(alias, str)
        )
        strategy = (
            policy.policy_strategy.strip().upper()
            if isinstance(policy.policy_strategy, str)
            else "STRICT_MATCH"
        )
        required_anchors: list[str] = (
            policy.required_anchors if isinstance(policy.required_anchors, list) else []
        )
        provided_identifiers = identifiers or {}
        missing_required_anchors = [
            anchor
            for anchor in required_anchors
            if anchor not in provided_identifiers or not provided_identifiers[anchor]
        ]

        if strategy == "STRICT_MATCH" and missing_required_anchors:
            msg = f"Missing required anchors for {entity_type}: " + ", ".join(
                sorted(missing_required_anchors),
            )
            raise KernelEntityValidationError(msg)

        if strategy != "NONE" and provided_identifiers and not missing_required_anchors:
            existing = self._resolve_exact_candidates(
                candidates=self._entities.resolve_candidates(
                    research_space_id=research_space_id,
                    entity_type=normalized_entity_type,
                    identifiers=provided_identifiers,
                ),
                match_description="identifier anchors",
            )
            if existing is not None:
                logger.info(
                    "Resolved %s to existing entity %s via identifiers",
                    normalized_entity_type,
                    existing.id,
                )
                return existing, False

        if strategy in {"LOOKUP", "FUZZY"}:
            if display_label is not None and display_label.strip():
                existing_by_label = self._resolve_exact_candidates(
                    candidates=self._entities.find_display_label_candidates(
                        research_space_id=research_space_id,
                        entity_type=normalized_entity_type,
                        display_label=display_label,
                    ),
                    match_description=f"display label '{display_label}'",
                )
                if existing_by_label is not None:
                    logger.info(
                        "Resolved %s to existing entity %s via display label",
                        normalized_entity_type,
                        existing_by_label.id,
                    )
                    return existing_by_label, False

            existing_by_alias = self._resolve_exact_candidates(
                candidates=self._collect_alias_candidates(
                    research_space_id=research_space_id,
                    entity_type=normalized_entity_type,
                    alias_labels=normalized_aliases,
                ),
                match_description="alias anchors",
            )
            if existing_by_alias is not None:
                logger.info(
                    "Resolved %s to existing entity %s via aliases",
                    normalized_entity_type,
                    existing_by_alias.id,
                )
                return existing_by_alias, False

        entity = self._entities.create(
            research_space_id=research_space_id,
            entity_type=normalized_entity_type,
            display_label=display_label,
            metadata=metadata,
        )

        if provided_identifiers:
            for namespace, value in provided_identifiers.items():
                self._entities.add_identifier(
                    entity_id=str(entity.id),
                    namespace=namespace,
                    identifier_value=value,
                )

        self._persist_aliases(
            entity_id=str(entity.id),
            alias_labels=normalized_aliases,
            skip_conflicting_aliases=skip_conflicting_aliases,
        )

        persisted_entity = self._entities.get_by_id(str(entity.id))
        if persisted_entity is None:
            msg = f"Created entity '{entity.id}' could not be reloaded."
            raise RuntimeError(msg)

        logger.info("Created new %s entity %s", normalized_entity_type, entity.id)
        self._read_model_update_dispatcher.dispatch(
            GraphReadModelUpdate(
                model_name=ENTITY_EMBEDDING_STATUS_READ_MODEL.name,
                trigger=GraphReadModelTrigger.ENTITY_CHANGE,
                entity_ids=(str(entity.id),),
                space_id=research_space_id,
            ),
        )
        return persisted_entity, True

    def create_or_resolve_many(
        self,
        *,
        research_space_id: str,
        entity_inputs: list[dict[str, object]],
    ) -> list[tuple[KernelEntity, bool]]:
        """Process a batch of entity create-or-resolve operations in order.

        Each input dict carries the same fields ``create_or_resolve`` accepts:
        ``entity_type`` (required), ``identifiers``, ``display_label``,
        ``aliases``, ``metadata``.  This wrapper exists so HTTP callers can
        avoid one round-trip per entity — ontology loaders (MONDO, HPO,
        UBERON) batch ~26k terms through this method instead of issuing
        ~26k individual POSTs, which dominates load time.

        The method itself does not commit; the router commits the whole
        batch atomically so validation failures still abort the entire
        chunk. Alias collisions on newly created entities are skipped
        instead of aborting the whole batch so ontology loaders can keep
        their chunk-level throughput even when one synonym is already
        claimed elsewhere in the space.
        """
        results: list[tuple[KernelEntity, bool]] = []
        for entry in entity_inputs:
            entity_type_value = entry.get("entity_type")
            if not isinstance(entity_type_value, str) or not entity_type_value.strip():
                msg = "Each batch entry must include a non-empty 'entity_type'."
                raise KernelEntityValidationError(msg)
            display_label_value = entry.get("display_label")
            display_label = (
                display_label_value
                if isinstance(display_label_value, str) or display_label_value is None
                else None
            )
            aliases_value = entry.get("aliases")
            aliases = (
                [str(a) for a in aliases_value]
                if isinstance(aliases_value, list)
                else None
            )
            identifiers_value = entry.get("identifiers")
            identifiers = (
                {str(k): str(v) for k, v in identifiers_value.items()}
                if isinstance(identifiers_value, dict)
                else None
            )
            metadata_value = entry.get("metadata")
            metadata = metadata_value if isinstance(metadata_value, dict) else None
            results.append(
                self.create_or_resolve(
                    research_space_id=research_space_id,
                    entity_type=entity_type_value,
                    identifiers=identifiers,
                    display_label=display_label,
                    aliases=aliases,
                    metadata=metadata,
                    skip_conflicting_aliases=True,
                ),
            )
        return results

    def _persist_aliases(
        self,
        *,
        entity_id: str,
        alias_labels: list[str],
        skip_conflicting_aliases: bool,
    ) -> None:
        """Persist one entity's aliases with optional conflict tolerance."""
        for alias_label in alias_labels:
            try:
                self._entities.add_alias(
                    entity_id=entity_id,
                    alias_label=alias_label,
                    source="entity_write",
                )
            except KernelEntityConflictError:
                if not skip_conflicting_aliases:
                    raise
                logger.info(
                    "Skipping conflicting alias '%s' while creating entity %s in batch",
                    alias_label,
                    entity_id,
                )

    def _collect_alias_candidates(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        alias_labels: list[str],
    ) -> list[KernelEntity]:
        candidate_by_id: dict[str, KernelEntity] = {}
        for alias_label in alias_labels:
            for candidate in self._entities.find_alias_candidates(
                research_space_id=research_space_id,
                entity_type=entity_type,
                alias_label=alias_label,
            ):
                candidate_by_id[str(candidate.id)] = candidate
        return list(candidate_by_id.values())

    @staticmethod
    def _resolve_exact_candidates(
        *,
        candidates: list[KernelEntity],
        match_description: str,
    ) -> KernelEntity | None:
        candidate_by_id: dict[str, KernelEntity] = {}
        for candidate in candidates:
            candidate_by_id[str(candidate.id)] = candidate
        unique_candidates = list(candidate_by_id.values())
        if not unique_candidates:
            return None
        if len(unique_candidates) > 1:
            msg = f"Ambiguous exact match for {match_description}."
            raise KernelEntityConflictError(msg)
        return unique_candidates[0]

    def add_identifier(
        self,
        *,
        entity_id: str,
        namespace: str,
        identifier_value: str,
        sensitivity: str = "INTERNAL",
    ) -> KernelEntityIdentifier:
        """Add an external identifier to an entity."""
        return self._entities.add_identifier(
            entity_id=entity_id,
            namespace=namespace,
            identifier_value=identifier_value,
            sensitivity=sensitivity,
        )

    def get_entity(self, entity_id: str) -> KernelEntity | None:
        """Retrieve a single entity."""
        return self._entities.get_by_id(entity_id)

    def update_entity(
        self,
        entity_id: str,
        *,
        display_label: str | None = None,
        aliases: list[str] | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelEntity | None:
        """Update an entity's display label and/or metadata."""
        updated = self._entities.update(
            entity_id,
            display_label=display_label,
            metadata=metadata,
        )
        if updated is None:
            return None
        normalized_aliases = normalize_entity_alias_labels(
            alias
            for alias in [display_label or "", *(aliases or [])]
            if isinstance(alias, str)
        )
        for alias_label in normalized_aliases:
            self._entities.add_alias(
                entity_id=entity_id,
                alias_label=alias_label,
                source="entity_write",
            )
        refreshed = self._entities.get_by_id(entity_id)
        if refreshed is not None:
            self._read_model_update_dispatcher.dispatch(
                GraphReadModelUpdate(
                    model_name=ENTITY_EMBEDDING_STATUS_READ_MODEL.name,
                    trigger=GraphReadModelTrigger.ENTITY_CHANGE,
                    entity_ids=(entity_id,),
                    space_id=str(refreshed.research_space_id),
                ),
            )
        return refreshed

    def list_by_type(
        self,
        research_space_id: str,
        entity_type: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelEntity]:
        """List entities of a specific type in a research space."""
        return self._entities.find_by_type(
            research_space_id,
            _normalize_entity_type(entity_type),
            limit=limit,
            offset=offset,
        )

    def search(
        self,
        research_space_id: str,
        query: str,
        *,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[KernelEntity]:
        """Search canonical entity labels and aliases."""
        return self._entities.search(
            research_space_id,
            query,
            entity_type=(
                None if entity_type is None else _normalize_entity_type(entity_type)
            ),
            limit=limit,
        )

    def get_research_space_summary(self, research_space_id: str) -> dict[str, int]:
        """Return entity counts by type for a research space."""
        return self._entities.count_by_type(research_space_id)

    def delete_entity(self, entity_id: str) -> bool:
        """Delete an entity and all cascaded data."""
        return self._entities.delete(entity_id)


__all__ = ["KernelEntityService"]
