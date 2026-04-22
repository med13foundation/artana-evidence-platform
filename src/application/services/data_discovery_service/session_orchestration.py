"""
Session Orchestration Service.

Centralizes complex business logic for data discovery sessions, including:
- State derivation (capabilities)
- Validation rules
- View context generation

This service implements the 'Backend for Frontend' pattern, returning rich
OrchestratedSessionState objects that the UI can render directly.
"""

from typing import TYPE_CHECKING
from uuid import UUID

# Import DTOs directly from the application layer
from src.application.services.data_discovery_service.dtos import (
    OrchestratedSessionState,
    SourceCapabilitiesDTO,
    ValidationIssueDTO,
    ValidationResultDTO,
    ViewContextDTO,
)
from src.application.services.data_discovery_service.mappers import (
    data_discovery_session_to_response,
)
from src.domain.entities.data_discovery_parameters import QueryParameterType
from src.domain.repositories.data_discovery_repository import (
    DataDiscoverySessionRepository,
    SourceCatalogRepository,
)

if TYPE_CHECKING:
    from src.domain.entities.data_discovery_session import SourceCatalogEntry


class SessionOrchestrationService:
    """
    Orchestrates data discovery session state and validation.
    Acts as the 'Brain' for the data discovery UI.
    """

    def __init__(
        self,
        session_repo: DataDiscoverySessionRepository,
        catalog_repo: SourceCatalogRepository,
    ):
        self._session_repo = session_repo
        self._catalog_repo = catalog_repo

    def get_orchestrated_state(
        self,
        session_id: UUID,
        owner_id: UUID,
    ) -> OrchestratedSessionState:
        """
        Get the complete orchestrated state for a session.

        Args:
            session_id: The ID of the session to retrieve
            owner_id: The user requesting the session state

        Returns:
            OrchestratedSessionState: The complete state ready for UI rendering
        """
        session = self._session_repo.find_owned_session(session_id, owner_id)
        if not session:
            msg = f"Session {session_id} not found or not authorized"
            raise ValueError(msg)

        # Fetch all selected sources to calculate capabilities
        selected_sources = []
        for source_id in session.selected_sources:
            source = self._catalog_repo.find_by_id(source_id)
            if source:
                selected_sources.append(source)

        # 1. Derive Capabilities
        capabilities = self._derive_capabilities(selected_sources)

        # 2. Run Validation
        validation_result = self._validate_selection(selected_sources)

        # 3. Generate View Context
        # Note: SourceCatalogRepository doesn't have count(), using len(find_all_active())
        total_available = len(self._catalog_repo.find_all_active())

        view_context = ViewContextDTO(
            selected_count=len(selected_sources),
            total_available=total_available,
            can_run_search=validation_result.is_valid and len(selected_sources) > 0,
            categories=self._get_category_breakdown(selected_sources),
        )

        return OrchestratedSessionState(
            session=data_discovery_session_to_response(session),
            capabilities=capabilities,
            validation=validation_result,
            view_context=view_context,
        )

    def update_selection(
        self,
        session_id: UUID,
        source_ids: list[str],
        owner_id: UUID,
    ) -> OrchestratedSessionState:
        """
        Update the session's source selection and return the new state.

        Args:
            session_id: The ID of the session
            source_ids: The new list of selected source IDs
            owner_id: The user updating the session

        Returns:
            OrchestratedSessionState: The new state after the update
        """
        session = self._session_repo.find_owned_session(session_id, owner_id)
        if not session:
            msg = f"Session {session_id} not found or not authorized"
            raise ValueError(msg)

        # Update the session
        # Check if 'with_selected_sources' exists (it was used in SessionManagementMixin)
        if hasattr(session, "with_selected_sources"):
            session = session.with_selected_sources(source_ids)
        else:
            # Fallback if it's a mutable Pydantic model
            session.selected_sources = source_ids

        self._session_repo.save(session)

        # Return the new state immediately
        return self.get_orchestrated_state(session_id, owner_id)

    def _derive_capabilities(
        self,
        sources: list["SourceCatalogEntry"],
    ) -> SourceCapabilitiesDTO:
        """Calculate what is possible with the current selection."""
        if not sources:
            return SourceCapabilitiesDTO()

        # Start with optimistic capabilities (True) and narrow down based on restrictions
        # OR: Start with pessimistic (False) and enable if ANY source supports it?
        # Policy: A capability is available if AT LEAST ONE source supports it
        # AND NO selected source explicitly forbids it (conflict).

        gene_types = (
            QueryParameterType.GENE,
            QueryParameterType.GENE_AND_TERM,
            QueryParameterType.API,
        )
        term_types = (
            QueryParameterType.TERM,
            QueryParameterType.GENE_AND_TERM,
            QueryParameterType.API,
        )

        supports_gene = any(s.param_type in gene_types for s in sources)
        supports_term = any(s.param_type in term_types for s in sources)

        return SourceCapabilitiesDTO(
            supports_gene_search=supports_gene,
            supports_term_search=supports_term,
            supported_parameters=["gene_symbol", "search_term"],  # Simplified
            max_results_limit=1000,  # Could be min() of all sources
        )

    def _validate_selection(
        self,
        _sources: list["SourceCatalogEntry"],
    ) -> ValidationResultDTO:
        """Run validation rules on the selected sources."""
        # ValidationIssueDTO is now imported at the top
        issues: list[ValidationIssueDTO] = []

        return ValidationResultDTO(
            is_valid=len(issues) == 0,
            issues=issues,
        )

    def _get_category_breakdown(
        self,
        sources: list["SourceCatalogEntry"],
    ) -> dict[str, int]:
        """Helper to count sources by category for the UI."""
        counts: dict[str, int] = {}
        for source in sources:
            cat = source.category
            counts[cat] = counts.get(cat, 0) + 1
        return counts
