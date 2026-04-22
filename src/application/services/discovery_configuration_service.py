"""
Service for managing discovery presets and advanced configuration.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.application.services.pubmed_query_builder import PubMedQueryBuilder
from src.domain.entities.discovery_preset import (
    DiscoveryPreset,
    DiscoveryProvider,
    PresetScope,
)

if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from src.application.services.discovery_configuration_requests import (
        CreatePubmedPresetRequest,
    )
    from src.domain.repositories.data_discovery_repository import (
        DiscoveryPresetRepository,
    )


class DiscoveryConfigurationService:
    """Coordinates discovery presets and advanced search configuration."""

    def __init__(
        self,
        preset_repository: DiscoveryPresetRepository,
        pubmed_query_builder: PubMedQueryBuilder | None = None,
    ):
        self._preset_repository = preset_repository
        self._pubmed_query_builder = pubmed_query_builder or PubMedQueryBuilder()

    def create_pubmed_preset(
        self,
        owner_id: UUID,
        request: CreatePubmedPresetRequest,
    ) -> DiscoveryPreset:
        """Validate and create a PubMed preset for the user."""

        if request.scope == PresetScope.SPACE and request.research_space_id is None:
            msg = "research_space_id is required for space-scoped presets"
            raise ValueError(msg)
        self._pubmed_query_builder.validate(request.parameters)
        now = datetime.now(UTC)
        preset = DiscoveryPreset(
            id=uuid4(),
            owner_id=owner_id,
            provider=DiscoveryProvider.PUBMED,
            scope=request.scope,
            name=request.name,
            description=request.description,
            parameters=request.parameters,
            metadata={
                "query_preview": self._pubmed_query_builder.build_query(
                    request.parameters,
                ),
            },
            research_space_id=request.research_space_id,
            created_at=now,
            updated_at=now,
        )
        return self._preset_repository.create(preset)

    def list_pubmed_presets(
        self,
        owner_id: UUID,
        *,
        research_space_id: UUID | None = None,
    ) -> list[DiscoveryPreset]:
        """List user presets plus optional shared presets for a space."""

        owned = self._preset_repository.list_for_owner(owner_id)
        if research_space_id is None:
            return [
                preset
                for preset in owned
                if preset.provider == DiscoveryProvider.PUBMED
            ]

        shared = self._preset_repository.list_for_space(research_space_id)
        combined = owned + shared
        seen: set[UUID] = set()
        result: list[DiscoveryPreset] = []
        for preset in combined:
            if preset.id in seen:
                continue
            seen.add(preset.id)
            result.append(preset)
        return result

    def delete_preset(self, preset_id: UUID, owner_id: UUID) -> bool:
        """Delete a preset owned by the user."""

        return self._preset_repository.delete(preset_id, owner_id)

    def preview_pubmed_query(self, parameters: CreatePubmedPresetRequest) -> str:
        """Generate a PubMed query string for preview."""

        self._pubmed_query_builder.validate(parameters.parameters)
        return self._pubmed_query_builder.build_query(parameters.parameters)
