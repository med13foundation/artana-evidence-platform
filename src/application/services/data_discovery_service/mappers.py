"""Mappers for data discovery service DTOs."""

from typing import TYPE_CHECKING

from src.application.services.data_discovery_service.dtos import (
    AdvancedQueryParametersModel,
    DataDiscoverySessionResponse,
)

if TYPE_CHECKING:
    from src.domain.entities.data_discovery_session import DataDiscoverySession


def data_discovery_session_to_response(
    session: "DataDiscoverySession",
) -> DataDiscoverySessionResponse:
    """Map DataDiscoverySession entity to response model."""
    return DataDiscoverySessionResponse(
        id=session.id,
        owner_id=session.owner_id,
        research_space_id=session.research_space_id,
        name=session.name,
        current_parameters=AdvancedQueryParametersModel.from_domain(
            session.current_parameters,
        ),
        selected_sources=session.selected_sources,
        tested_sources=session.tested_sources,
        total_tests_run=session.total_tests_run,
        successful_tests=session.successful_tests,
        is_active=session.is_active,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        last_activity_at=session.last_activity_at.isoformat(),
    )
