"""Session management mixin for data discovery service."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID, uuid4  # noqa: TCH003

from src.domain.entities.data_discovery_parameters import QueryParameterType
from src.domain.entities.data_discovery_session import DataDiscoverySession

from .catalog_methods import CatalogPermissionMixin

if TYPE_CHECKING:
    from collections.abc import Sequence

    from src.application.services.data_discovery_service.requests import (
        CreateDataDiscoverySessionRequest,
        UpdateSessionParametersRequest,
    )
    from src.domain.repositories.data_discovery_repository import (
        DataDiscoverySessionRepository,
        QueryTestResultRepository,
        SourceCatalogRepository,
    )

logger = logging.getLogger(__name__)


class SessionManagementMixin(CatalogPermissionMixin):
    _session_repo: DataDiscoverySessionRepository
    _catalog_repo: SourceCatalogRepository
    _query_repo: QueryTestResultRepository

    def get_sessions_for_space(
        self,
        space_id: UUID,
        owner_id: UUID | None = None,
        *,
        include_inactive: bool = False,
    ) -> list[DataDiscoverySession]:
        if owner_id:
            sessions = self._session_repo.find_by_owner(
                owner_id,
                include_inactive=include_inactive,
            )
        else:
            sessions = self._session_repo.find_by_space(
                space_id,
                include_inactive=include_inactive,
            )

        return [
            session for session in sessions if session.research_space_id == space_id
        ]

    def create_session(
        self,
        request: CreateDataDiscoverySessionRequest,
    ) -> DataDiscoverySession:
        # Create new session entity
        session = DataDiscoverySession(
            id=uuid4(),  # Will be set by repository
            owner_id=request.owner_id,
            research_space_id=request.research_space_id,
            name=request.name,
            current_parameters=request.initial_parameters,
        )

        # Save to repository
        saved_session = self._session_repo.save(session)
        logger.info(
            "Created data discovery session %s for user %s",
            saved_session.id,
            request.owner_id,
        )
        return saved_session

    def get_session(self, session_id: UUID) -> DataDiscoverySession | None:
        return self._session_repo.find_by_id(session_id)

    def get_session_for_owner(
        self,
        session_id: UUID,
        owner_id: UUID,
    ) -> DataDiscoverySession | None:
        return self._session_repo.find_owned_session(session_id, owner_id)

    def get_user_sessions(
        self,
        owner_id: UUID,
        *,
        include_inactive: bool = False,
    ) -> list[DataDiscoverySession]:
        return self._session_repo.find_by_owner(
            owner_id,
            include_inactive=include_inactive,
        )

    def update_session_parameters(
        self,
        request: UpdateSessionParametersRequest,
        owner_id: UUID | None = None,
    ) -> DataDiscoverySession | None:
        session = (
            self._session_repo.find_owned_session(request.session_id, owner_id)
            if owner_id
            else self._session_repo.find_by_id(request.session_id)
        )
        if not session:
            return None

        # Update parameters
        updated_session = session.update_parameters(request.parameters)

        # Save updated session
        saved_session = self._session_repo.save(updated_session)
        logger.info("Updated parameters for session %s", request.session_id)
        return saved_session

    def toggle_source_selection(
        self,
        session_id: UUID,
        catalog_entry_id: str,
        owner_id: UUID | None = None,
    ) -> DataDiscoverySession | None:
        session = (
            self._session_repo.find_owned_session(session_id, owner_id)
            if owner_id
            else self._session_repo.find_by_id(session_id)
        )
        if not session:
            logger.warning(
                "Unable to toggle source %s; session %s not found",
                catalog_entry_id,
                session_id,
            )
            return None

        catalog_entry = self._catalog_repo.find_by_id(catalog_entry_id)
        if not catalog_entry:
            logger.warning(
                "Catalog entry %s missing while toggling selection on session %s",
                catalog_entry_id,
                session_id,
            )
            return None

        if not catalog_entry.is_active:
            logger.warning(
                "Attempted to select inactive catalog entry %s on session %s",
                catalog_entry_id,
                session_id,
            )
            return None
        if not self._can_execute_source(catalog_entry_id, session.research_space_id):
            logger.warning(
                "Catalog entry %s disabled for session %s",
                catalog_entry_id,
                session_id,
            )
            return None

        if catalog_entry.param_type != QueryParameterType.NONE:
            current_parameters = session.current_parameters
            if not current_parameters.can_run_query(catalog_entry.param_type):
                logger.info(
                    "Allowing selection without required parameters for catalog entry %s on session %s",
                    catalog_entry_id,
                    session_id,
                )

        # Toggle selection
        updated_session = session.toggle_source_selection(catalog_entry_id)

        # Save updated session
        saved_session = self._session_repo.save(updated_session)
        logger.info(
            "Toggled source %s selection in session %s",
            catalog_entry_id,
            session_id,
        )
        return saved_session

    def set_source_selection(
        self,
        session_id: UUID,
        catalog_entry_ids: Sequence[str],
        owner_id: UUID | None = None,
    ) -> DataDiscoverySession | None:
        session = (
            self._session_repo.find_owned_session(session_id, owner_id)
            if owner_id
            else self._session_repo.find_by_id(session_id)
        )
        if not session:
            logger.warning("Unable to set selections; session %s not found", session_id)
            return None

        if not catalog_entry_ids:
            updated_session = session.with_selected_sources([])
            return self._session_repo.save(updated_session)

        valid_sources: list[str] = []
        seen_sources: set[str] = set()
        for catalog_entry_id in catalog_entry_ids:
            if catalog_entry_id in seen_sources:
                continue
            seen_sources.add(catalog_entry_id)

            catalog_entry = self._catalog_repo.find_by_id(catalog_entry_id)
            if not catalog_entry:
                logger.warning(
                    "Catalog entry %s missing while bulk updating selection on session %s",
                    catalog_entry_id,
                    session_id,
                )
                continue
            if not catalog_entry.is_active:
                logger.warning(
                    "Attempted to select inactive catalog entry %s on session %s",
                    catalog_entry_id,
                    session_id,
                )
                continue
            if not self._can_execute_source(
                catalog_entry_id,
                session.research_space_id,
            ):
                logger.warning(
                    "Catalog entry %s disabled for session %s",
                    catalog_entry_id,
                    session_id,
                )
                continue
            if catalog_entry.param_type != QueryParameterType.NONE:
                current_parameters = session.current_parameters
                if not current_parameters.can_run_query(catalog_entry.param_type):
                    logger.info(
                        "Allowing selection without required parameters for catalog entry %s on session %s",
                        catalog_entry_id,
                        session_id,
                    )

            valid_sources.append(catalog_entry_id)

        updated_session = session.with_selected_sources(valid_sources)
        saved_session = self._session_repo.save(updated_session)
        logger.info(
            "Updated selections for session %s (%d sources retained)",
            session_id,
            len(valid_sources),
        )
        return saved_session

    def delete_session(
        self,
        session_id: UUID,
        owner_id: UUID | None = None,
    ) -> bool:
        try:
            if owner_id:
                session = self._session_repo.find_owned_session(session_id, owner_id)
                if not session:
                    logger.warning(
                        "Owner %s attempted to delete unauthorized session %s",
                        owner_id,
                        session_id,
                    )
                    return False
            else:
                session = self._session_repo.find_by_id(session_id)
                if not session:
                    logger.warning("Session %s not found for deletion", session_id)
                    return False

            # Delete test results first
            self._query_repo.delete_session_results(session_id)

            # Delete session
            success = self._session_repo.delete(session_id)

        except Exception:
            logger.exception("Failed to delete session %s", session_id)
            return False
        else:
            if success:
                logger.info("Deleted data discovery session %s", session_id)
            return success
