"""Graph-backed alias writer for structured source ingestion."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Protocol

from artana_evidence_db.entity_resolution import normalize_entity_match_text

from src.application.services.structured_source_aliases import (
    StructuredEntityAliasCandidate,
    StructuredSourceAliasWriteResult,
    count_alias_candidates,
)
from src.domain.value_objects.entity_resolution import normalize_entity_alias_labels

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject


class _KernelEntityLike(Protocol):
    id: object


class _KernelEntityAliasLike(Protocol):
    alias_normalized: str


class _KernelEntityServiceLike(Protocol):
    def create_or_resolve(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        entity_type: str,
        identifiers: dict[str, str] | None = None,
        display_label: str | None = None,
        aliases: list[str] | None = None,
        metadata: JSONObject | None = None,
    ) -> tuple[_KernelEntityLike, bool]:
        """Resolve or create one kernel entity."""

    def update_entity(
        self,
        entity_id: str,
        *,
        display_label: str | None = None,
        aliases: list[str] | None = None,
        metadata: JSONObject | None = None,
    ) -> _KernelEntityLike | None:
        """Attach aliases to an existing kernel entity."""


class _KernelEntityAliasRepositoryLike(Protocol):
    def list_aliases(
        self,
        *,
        entity_id: str,
        include_inactive: bool = False,
    ) -> list[_KernelEntityAliasLike]:
        """List aliases attached to one kernel entity."""


class KernelStructuredSourceAliasWriter:
    """Persist source-extracted aliases through kernel entity resolution rules."""

    def __init__(
        self,
        *,
        entity_service: _KernelEntityServiceLike,
        entity_repository: _KernelEntityAliasRepositoryLike,
    ) -> None:
        self._entity_service = entity_service
        self._entity_repository = entity_repository

    def ensure_aliases(
        self,
        *,
        research_space_id: str,
        candidates: tuple[StructuredEntityAliasCandidate, ...],
    ) -> StructuredSourceAliasWriteResult:
        """Create/resolve entities and attach aliases with backend-derived counts."""
        result = StructuredSourceAliasWriteResult(
            alias_candidates_count=count_alias_candidates(candidates),
        )
        for candidate in candidates:
            result = self._ensure_candidate_aliases(
                research_space_id=research_space_id,
                candidate=candidate,
                result=result,
            )
        return result

    def _ensure_candidate_aliases(
        self,
        *,
        research_space_id: str,
        candidate: StructuredEntityAliasCandidate,
        result: StructuredSourceAliasWriteResult,
    ) -> StructuredSourceAliasWriteResult:
        aliases = normalize_entity_alias_labels(candidate.aliases)
        if not aliases:
            return result
        try:
            entity, created = self._entity_service.create_or_resolve(
                research_space_id=research_space_id,
                entity_type=candidate.entity_type,
                identifiers=candidate.identifiers,
                display_label=candidate.display_label,
                aliases=aliases,
                metadata=candidate.metadata,
            )
            entity_id = str(entity.id)
            before_keys: set[str] = set()
            if not created:
                before_keys = self._active_alias_keys(entity_id)
                updated = self._entity_service.update_entity(
                    entity_id,
                    aliases=aliases,
                )
                self._require_updated_entity(updated, entity_id)

            after_keys = self._active_alias_keys(entity_id)
            requested_keys = {
                normalize_entity_match_text(alias_label) for alias_label in aliases
            }
            newly_persisted_keys = requested_keys.intersection(
                after_keys.difference(before_keys),
            )
            already_existing_keys = requested_keys.intersection(before_keys)
            return replace(
                result,
                aliases_persisted=(
                    result.aliases_persisted + len(newly_persisted_keys)
                ),
                aliases_skipped=result.aliases_skipped + len(already_existing_keys),
                alias_entities_touched=result.alias_entities_touched + 1,
            )
        except Exception as exc:  # noqa: BLE001
            return replace(
                result,
                errors=(
                    *result.errors,
                    (
                        f"{candidate.source_type}:{candidate.entity_type}:"
                        f"{candidate.display_label}: {exc}"
                    ),
                ),
            )

    def _active_alias_keys(self, entity_id: str) -> set[str]:
        return {
            alias.alias_normalized
            for alias in self._entity_repository.list_aliases(
                entity_id=entity_id,
                include_inactive=False,
            )
        }

    @staticmethod
    def _require_updated_entity(
        updated: _KernelEntityLike | None,
        entity_id: str,
    ) -> None:
        if updated is None:
            msg = f"Kernel entity disappeared while persisting aliases: {entity_id}"
            raise RuntimeError(msg)


__all__ = ["KernelStructuredSourceAliasWriter"]
