"""Space-scoped façade for data discovery operations."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TCH003

from src.application.services.data_discovery_service.requests import (
    CreateDataDiscoverySessionRequest,
    UpdateSessionParametersRequest,
)
from src.domain.entities.data_discovery_parameters import AdvancedQueryParameters

if TYPE_CHECKING:
    from collections.abc import Sequence

    from src.application.services.data_discovery_service import DataDiscoveryService
    from src.application.services.discovery_configuration_service import (
        DiscoveryConfigurationService,
    )
    from src.domain.entities.data_discovery_session import (
        DataDiscoverySession,
        SourceCatalogEntry,
    )
    from src.domain.entities.discovery_preset import DiscoveryPreset


class SpaceDataDiscoveryService:
    """Helper service that enforces research space boundaries."""

    def __init__(
        self,
        space_id: UUID,
        discovery_service: DataDiscoveryService,
        discovery_configuration_service: DiscoveryConfigurationService | None = None,
    ) -> None:
        self._space_id = space_id
        self._service = discovery_service
        self._config_service = discovery_configuration_service

    @property
    def space_id(self) -> UUID:
        """Return the scoped research space identifier."""
        return self._space_id

    def get_catalog(
        self,
        category: str | None = None,
        search_query: str | None = None,
    ) -> list[SourceCatalogEntry]:
        """Return catalog entries filtered for this space."""
        return self._service.get_source_catalog(
            category,
            search_query,
            research_space_id=self._space_id,
        )

    def create_session(
        self,
        *,
        owner_id: UUID,
        name: str,
        parameters: AdvancedQueryParameters,
    ) -> DataDiscoverySession:
        """Create a session pinned to this space."""
        request = CreateDataDiscoverySessionRequest(
            owner_id=owner_id,
            name=name,
            research_space_id=self._space_id,
            initial_parameters=parameters,
        )
        session = self._service.create_session(request)
        ensured = self._ensure_session_in_space(session)
        if ensured is None:  # pragma: no cover - defensive
            message = "Space-scoped session creation produced invalid session"
            raise RuntimeError(message)
        return ensured

    def list_sessions(
        self,
        *,
        owner_id: UUID | None,
        include_inactive: bool = False,
    ) -> list[DataDiscoverySession]:
        """List sessions inside this space."""
        return self._service.get_sessions_for_space(
            self._space_id,
            owner_id=owner_id,
            include_inactive=include_inactive,
        )

    def get_session(self, session_id: UUID) -> DataDiscoverySession | None:
        """Return session if it belongs to this space."""
        session = self._service.get_session(session_id)
        return self._ensure_session_in_space(session)

    def get_session_for_owner(
        self,
        session_id: UUID,
        owner_id: UUID,
    ) -> DataDiscoverySession | None:
        """Return session for owner if it belongs to this space."""
        session = self._service.get_session_for_owner(session_id, owner_id)
        return self._ensure_session_in_space(session)

    def update_parameters(
        self,
        session_id: UUID,
        parameters: AdvancedQueryParameters,
        *,
        owner_id: UUID | None,
    ) -> DataDiscoverySession | None:
        """Update parameters for a session inside this space."""
        if owner_id:
            current = self.get_session_for_owner(session_id, owner_id)
        else:
            current = self.get_session(session_id)
        if current is None:
            return None

        request = UpdateSessionParametersRequest(
            session_id=session_id,
            parameters=parameters,
        )
        updated = self._service.update_session_parameters(
            request,
            owner_id=owner_id,
        )
        return self._ensure_session_in_space(updated)

    def toggle_source_selection(
        self,
        session_id: UUID,
        catalog_entry_id: str,
        *,
        owner_id: UUID | None,
    ) -> DataDiscoverySession | None:
        """Toggle a source selection inside this space."""
        if not self._session_accessible(session_id, owner_id):
            return None
        updated = self._service.toggle_source_selection(
            session_id,
            catalog_entry_id,
            owner_id=owner_id,
        )
        return self._ensure_session_in_space(updated)

    def set_source_selection(
        self,
        session_id: UUID,
        catalog_entry_ids: Sequence[str],
        *,
        owner_id: UUID | None,
    ) -> DataDiscoverySession | None:
        """Replace selected sources for a session in this space."""
        if not self._session_accessible(session_id, owner_id):
            return None
        updated = self._service.set_source_selection(
            session_id,
            catalog_entry_ids,
            owner_id=owner_id,
        )
        return self._ensure_session_in_space(updated)

    def delete_session(
        self,
        session_id: UUID,
        *,
        owner_id: UUID | None,
    ) -> bool:
        """Delete a session within this space."""
        if not self._session_accessible(session_id, owner_id):
            return False
        return self._service.delete_session(session_id)

    def list_pubmed_presets(
        self,
        owner_id: UUID,
        *,
        include_space_presets: bool = True,
    ) -> list[DiscoveryPreset]:
        """Return PubMed presets visible within this space."""
        config_service = self._require_config_service()
        space_id = self._space_id if include_space_presets else None
        return config_service.list_pubmed_presets(
            owner_id,
            research_space_id=space_id,
        )

    def get_default_parameters(
        self,
        owner_id: UUID | None = None,
    ) -> AdvancedQueryParameters:
        """Return default advanced parameters for the space."""
        sessions = self._service.get_sessions_for_space(
            self._space_id,
            owner_id=owner_id,
            include_inactive=True,
        )
        if sessions:
            return sessions[0].current_parameters

        if owner_id:
            config_service = self._config_service
            if config_service:
                presets = config_service.list_pubmed_presets(
                    owner_id,
                    research_space_id=self._space_id,
                )
                if presets:
                    return presets[0].parameters

        return AdvancedQueryParameters(
            gene_symbol=None,
            search_term=None,
        )

    def _session_accessible(
        self,
        session_id: UUID,
        owner_id: UUID | None,
    ) -> bool:
        """Return True when the session exists in this space."""
        if owner_id:
            session = self.get_session_for_owner(session_id, owner_id)
        else:
            session = self.get_session(session_id)
        return session is not None

    def _ensure_session_in_space(
        self,
        session: DataDiscoverySession | None,
    ) -> DataDiscoverySession | None:
        """Validate that the session belongs to this space."""
        if session is None:
            return None
        if session.research_space_id != self._space_id:
            return None
        return session

    def _require_config_service(self) -> DiscoveryConfigurationService:
        if self._config_service is None:
            message = "Discovery configuration service is not configured"
            raise RuntimeError(message)
        return self._config_service


__all__ = ["SpaceDataDiscoveryService"]
